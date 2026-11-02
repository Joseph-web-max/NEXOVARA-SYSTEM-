import os, re, smtplib, json, urllib.parse, hashlib, secrets, base64, socket, uuid, io, zipfile, hmac, logging
from pathlib import Path
import httpx
from dotenv import load_dotenv
load_dotenv()
from email.message import EmailMessage
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, inspect, text
from .database import Base, engine, get_db, SessionLocal, DATABASE_URL
from .models import User, Lead, Product, Project, Invoice, Ticket, Article, JobApplication, Subscription, Quote, AuditLog, AutomationWorkflow, AutomationRun, License, Notification, PartnerApplication, PasswordResetToken, Payment, PaymentEvent, StoredFile
from .schemas import *
from .security import hash_password, verify_password, create_token, create_mfa_challenge, decode_token, current_user, admin_user, staff_access, ROLE_PERMISSIONS


logger=logging.getLogger("nexovara")
FRONTEND_DIR=Path(__file__).resolve().parent.parent/"frontend"


def ensure_product_columns():
    """Additive compatibility migration for databases created by earlier MVP versions."""
    existing = {column["name"] for column in inspect(engine).get_columns("products")}
    additions = {
        "tagline": "VARCHAR(240) DEFAULT ''",
        "platforms": "TEXT DEFAULT ''",
        "version": "VARCHAR(80) DEFAULT ''",
        "github_url": "VARCHAR(500) DEFAULT ''",
        "docs_url": "VARCHAR(500) DEFAULT ''",
        "demo_url": "VARCHAR(500) DEFAULT ''",
        "image_url": "VARCHAR(1000) DEFAULT ''",
        "is_featured": "BOOLEAN NOT NULL DEFAULT FALSE",
        "sort_order": "INTEGER NOT NULL DEFAULT 0",
        "archived_at": "TIMESTAMP NULL",
    }
    with engine.begin() as connection:
        for name, sql_type in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE products ADD COLUMN {name} {sql_type}"))

if os.getenv("ALLOW_LEGACY_SCHEMA_PATCH", "false").lower() == "true":
    ensure_product_columns()
app=FastAPI(title="NEXOVARA Technologies API",version="1.0.0",description="Corporate platform, customer portal and administration API")
allowed_origins = list(dict.fromkeys([origin.strip().rstrip("/") for origin in (os.getenv("CORS_ORIGINS", "")+","+os.getenv("FRONTEND_ORIGIN", "")+","+os.getenv("PUBLIC_APP_URL", "http://localhost:8000")).split(",") if origin.strip()]))
app.add_middleware(CORSMiddleware,allow_origins=allowed_origins,allow_credentials=True,allow_methods=["GET","POST","PATCH","PUT","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type"])

# Per-process abuse controls. Use a shared gateway/Redis limiter for multi-worker production.
from collections import defaultdict, deque
from time import time
from starlette.middleware.base import BaseHTTPMiddleware
_rate_events=defaultdict(deque)
_redis_client=None
_redis_configured=bool(os.getenv("REDIS_URL"))
if _redis_configured:
    try:
        import redis
        _redis_client=redis.Redis.from_url(os.getenv("REDIS_URL"),decode_responses=True,socket_connect_timeout=2,socket_timeout=2)
        _redis_client.ping()
    except Exception:
        _redis_client=None
class PlatformSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path=request.url.path
        if request.method in ("POST","PUT","PATCH","DELETE") and request.cookies.get("nx_session"):
            origin=request.headers.get("origin")
            own_origin=f"{request.url.scheme}://{request.url.netloc}"
            if origin and origin.rstrip("/") not in allowed_origins and origin.rstrip("/")!=own_origin:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail":"Request origin is not allowed."},status_code=403)
        if request.method=="POST" and (path.startswith("/api/auth/") or path.startswith("/api/payments/") or path=="/api/files/upload" or path in ("/api/leads","/api/quotes","/api/partners/apply","/api/careers/apply")):
            client=request.client.host if request.client else "unknown"
            key=f"nx:rate:{client}:{path}"; limit=8 if path.startswith("/api/auth/") else 15
            if _redis_configured:
                if not _redis_client:
                    from fastapi.responses import JSONResponse
                    return JSONResponse({"detail":"Configured Redis rate limiter is unavailable; request rejected."},status_code=503)
                try:
                    count=_redis_client.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]); end; return n",1,key,60)
                    blocked=count>limit
                except Exception:
                    from fastapi.responses import JSONResponse
                    return JSONResponse({"detail":"Rate limiting service unavailable; request rejected."},status_code=503)
            else:
                local_key=(client,path); now=time(); events=_rate_events[local_key]
                while events and now-events[0]>60: events.popleft()
                blocked=len(events)>=limit
                if not blocked: events.append(now)
            if blocked:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail":"Too many requests. Please try again shortly."},status_code=429)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["X-Frame-Options"]="DENY"
        response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
        return response
app.add_middleware(PlatformSecurityMiddleware)



def record_audit(db:Session, user:User|None, action:str, entity_type:str, entity_id, details:dict|None=None):
    """Persist a minimal admin activity record; never store passwords or tokens here."""
    row=AuditLog(actor_id=user.id if user else None, actor_email=user.email if user else "system",
                 action=action,entity_type=entity_type,entity_id=str(entity_id or ""),
                 details=json.dumps(details or {},ensure_ascii=False,default=str))
    db.add(row)

def user_names(db:Session, ids):
    ids={i for i in ids if i}
    if not ids: return {}
    return {u.id:{"name":u.name,"email":u.email} for u in db.query(User).filter(User.id.in_(ids)).all()}

def seed():
    db=SessionLocal()
    try:
        email=os.getenv("ADMIN_EMAIL","").strip().lower()
        admin_password=os.getenv("ADMIN_PASSWORD","")
        # Never create an administrator with a built-in or fallback password.
        if bool(email) != bool(admin_password):
            raise RuntimeError("Set both ADMIN_EMAIL and ADMIN_PASSWORD to bootstrap the administrator.")
        if admin_password and len(admin_password) < 12:
            raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters.")
        if email and not db.query(User).filter(User.email==email).first():
            db.add(User(name=os.getenv("ADMIN_NAME","Founder"),email=email,password_hash=hash_password(admin_password),role="admin"))
        defaults=[
          ("AURORA AI","aurora-ai","Artificial Intelligence","An intelligent AI assistant and knowledge platform designed to help people find answers, work with documents and streamline knowledge workflows.","AI assistance;Document knowledge;Search and retrieval;Business productivity","Request a demo",""),
          ("Smart Cash Desk","smart-cash-desk","Financial Management","A church finance and accounting platform for contributions, cash tracking, expenses and financial reporting.","Contribution tracking;Cash and M-Pesa records;General ledger;Financial statements","Request a demo",""),
          ("Nexovara Business","nexovara-business","Business Management","A configurable business management platform for sales, expenses, inventory, customers and reporting.","Sales;Inventory;Invoices;Expenses;Analytics","Coming soon",""),
          ("Nexovara Secure","nexovara-secure","Cybersecurity","A security management platform concept for asset visibility, risk tracking and security operations.","Asset inventory;Risk register;Incident tracking;Security reports","Coming soon",""),
          ("Nexovara Automate","nexovara-automate","Automation","Workflow automation for customer enquiries, reminders, document processing and routine business operations.","Workflow builder;Notifications;Document workflows;Task automation","Coming soon","")
        ]
        for index,(n,s,c,d,f,p,u) in enumerate(defaults):
            existing=db.query(Product).filter(Product.slug==s).first()
            public_url=os.getenv("AURORA_PUBLIC_URL", "https://joseph-web-max.github.io/AURORA-AI-v2/") if s=="aurora-ai" else u
            if not existing:
                db.add(Product(name=n,slug=s,category=c,description=d,features=f,price_label=p,url=public_url,
                               status="draft",sort_order=index,is_featured=(index < 2)))
            elif s=="aurora-ai" and not existing.url:
                existing.url=public_url
        articles=[
          ("How AI can support a growing business","ai-for-growing-business","AI & Innovation","Practical ways to introduce AI into everyday business workflows.","Start with a clear business problem, choose a narrow workflow and measure whether the solution saves time or improves quality."),
          ("Building better digital security habits","digital-security-habits","Cybersecurity","Simple practices that help teams reduce common digital risks.","Use unique passwords, multi-factor authentication, software updates, least-privilege access and tested backups.")
        ]
        for t,s,c,e,b in articles:
            if not db.query(Article).filter(Article.slug==s).first(): db.add(Article(title=t,slug=s,category=c,excerpt=e,body=b))
        db.commit()
    finally: db.close()
if DATABASE_URL.startswith("sqlite"):
    # Local development convenience only; production uses Alembic against PostgreSQL.
    Base.metadata.create_all(bind=engine)
seed()

@app.get("/api/health")
def health(db:Session=Depends(get_db)):
    return {"status":"healthy","service":"NEXOVARA Technologies","database":"connected","database_engine":"Supabase PostgreSQL" if "supabase" in os.getenv("DATABASE_URL", "").lower() else ("PostgreSQL" if DATABASE_URL.startswith("postgresql") else "SQLite"),"products":db.query(Product).count(),"migrations":"Alembic configured; run upgrade before production rollout"}

def _fernet():
    from cryptography.fernet import Fernet
    key=base64.urlsafe_b64encode(hashlib.sha256((os.getenv("MFA_ENCRYPTION_KEY") or os.getenv("SECRET_KEY","")).encode()).digest())
    return Fernet(key)
def encrypt_mfa_secret(secret:str)->str: return _fernet().encrypt(secret.encode()).decode()
def decrypt_mfa_secret(value:str)->str: return _fernet().decrypt(value.encode()).decode()
def issue_session_cookie(response:Response,user:User):
    response.set_cookie("nx_session",create_token(user),httponly=True,secure=os.getenv("COOKIE_SECURE","true").lower()=="true",samesite="lax",max_age=12*60*60,path="/")

@app.post("/api/auth/register")
def register(data:RegisterIn,response:Response,db:Session=Depends(get_db)):
    email=data.email.lower()
    if db.query(User).filter(User.email==email).first(): raise HTTPException(409,"An account with this email already exists")
    user=User(name=data.name,email=email,password_hash=hash_password(data.password),company=data.company or "",role="client")
    db.add(user);db.commit();db.refresh(user);issue_session_cookie(response,user)
    return {"authenticated":True,"user":{"id":user.id,"name":user.name,"email":user.email,"role":user.role}}

@app.post("/api/auth/login")
def login(data:LoginIn,response:Response,db:Session=Depends(get_db)):
    user=db.query(User).filter(User.email==data.email.lower()).first()
    if not user or not verify_password(data.password,user.password_hash): raise HTTPException(401,"Incorrect email or password")
    if not user.active: raise HTTPException(403,"Account disabled")
    if user.role != "client" and user.mfa_enabled:
        return {"mfa_required":True,"challenge_token":create_mfa_challenge(user),"message":"Enter the current code from your authenticator app."}
    issue_session_cookie(response,user)
    return {"authenticated":True,"user":{"id":user.id,"name":user.name,"email":user.email,"role":user.role}}

@app.post("/api/auth/mfa/verify")
def verify_mfa_login(data:dict,response:Response,db:Session=Depends(get_db)):
    import pyotp
    token=str(data.get("challenge_token", "")); code=str(data.get("code", ""))
    try:
        payload=decode_token(token)
        if payload.get("purpose")!="mfa": raise ValueError()
        user=db.query(User).filter(User.id==int(payload["sub"]),User.active==True).first()
        if not user or int(user.token_version or 0)!=int(payload.get("ver",0)) or not user.mfa_enabled: raise ValueError()
        secret=decrypt_mfa_secret(user.mfa_secret)
        if not pyotp.TOTP(secret).verify(code,valid_window=1): raise ValueError()
    except Exception: raise HTTPException(401,"Invalid or expired MFA challenge/code")
    issue_session_cookie(response,user)
    return {"authenticated":True,"user":{"id":user.id,"name":user.name,"email":user.email,"role":user.role}}

@app.post("/api/auth/mfa/setup")
def setup_mfa(user:User=Depends(current_user),db:Session=Depends(get_db)):
    if user.role=="client": raise HTTPException(403,"MFA setup is currently restricted to staff accounts")
    import pyotp
    secret=pyotp.random_base32(); user.mfa_pending_secret=encrypt_mfa_secret(secret); db.commit()
    return {"secret":secret,"otpauth_url":pyotp.TOTP(secret).provisioning_uri(name=user.email,issuer_name="NEXOVARA Technologies"),"message":"Add this account to an authenticator app, then confirm with /api/auth/mfa/confirm."}

@app.post("/api/auth/mfa/confirm")
def confirm_mfa(data:dict,response:Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
    import pyotp
    if not user.mfa_pending_secret: raise HTTPException(400,"Start MFA setup first")
    secret=decrypt_mfa_secret(user.mfa_pending_secret)
    if not pyotp.TOTP(secret).verify(str(data.get("code","")),valid_window=1): raise HTTPException(400,"Invalid authenticator code")
    user.mfa_secret=user.mfa_pending_secret; user.mfa_pending_secret=""; user.mfa_enabled=True; user.token_version=(user.token_version or 0)+1; db.commit(); response.delete_cookie("nx_session",path="/",httponly=True,secure=os.getenv("COOKIE_SECURE","true").lower()=="true",samesite="lax")
    return {"message":"MFA enabled. Sign in again and complete the authenticator challenge."}

@app.post("/api/auth/sessions/revoke-all")
def revoke_all_sessions(user:User=Depends(current_user),db:Session=Depends(get_db)):
    user.token_version=(user.token_version or 0)+1; db.commit()
    return {"message":"All existing sessions have been revoked. Sign in again."}

@app.post("/api/auth/password/reset/request")
def request_password_reset(data:dict,db:Session=Depends(get_db)):
    email=str(data.get("email", "")).strip().lower()
    user=db.query(User).filter(User.email==email,User.active==True).first()
    if user and smtp_is_configured():
        raw=secrets.token_urlsafe(36); digest=hashlib.sha256(raw.encode()).hexdigest()
        from datetime import datetime, timedelta, timezone
        reset_row=PasswordResetToken(user_id=user.id,token_hash=digest,expires_at=datetime.now(timezone.utc)+timedelta(minutes=30))
        db.add(reset_row); db.commit()
        if not send_email_to(user.email,"NEXOVARA password reset",f"Your password reset code is:\n\n{raw}\n\nIt expires in 30 minutes and can only be used once."):
            db.delete(reset_row); db.commit()
    return {"message":"If the account exists and email is configured, password reset instructions have been sent."}

@app.post("/api/auth/password/reset/complete")
def complete_password_reset(data:dict,db:Session=Depends(get_db)):
    raw=str(data.get("token", "")); password=str(data.get("new_password", ""))
    if len(password)<12 or len(password)>128: raise HTTPException(400,"New password must be 12–128 characters")
    digest=hashlib.sha256(raw.encode()).hexdigest()
    row=db.query(PasswordResetToken).filter(PasswordResetToken.token_hash==digest,PasswordResetToken.used_at.is_(None)).first()
    from datetime import datetime, timezone
    expires=row.expires_at if row else None
    if expires is not None and expires.tzinfo is None: expires=expires.replace(tzinfo=timezone.utc)
    if not row or expires<datetime.now(timezone.utc): raise HTTPException(400,"Reset token is invalid or expired")
    user=db.query(User).filter(User.id==row.user_id,User.active==True).first()
    if not user: raise HTTPException(400,"Reset token is invalid or expired")
    user.password_hash=hash_password(password); user.token_version=(user.token_version or 0)+1; row.used_at=datetime.now(timezone.utc); db.commit()
    return {"message":"Password changed. All previous sessions have been revoked."}

@app.post("/api/auth/logout")
def logout(response:Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
    user.token_version=(user.token_version or 0)+1; db.commit()
    response.delete_cookie("nx_session",path="/",httponly=True,secure=os.getenv("COOKIE_SECURE","true").lower()=="true",samesite="lax")
    return {"message":"Signed out; this account's existing sessions have been revoked."}

@app.get("/api/auth/me")
def me(user:User=Depends(current_user)):
    return {"id":user.id,"name":user.name,"email":user.email,"role":user.role,"company":user.company,"mfa_enabled":bool(user.mfa_enabled),"permissions":sorted(ROLE_PERMISSIONS.get(user.role,set())) if user.role!="admin" else ["*"]}

def product_payload(p):
    return {"id":p.id,"name":p.name,"slug":p.slug,"category":p.category,"description":p.description,
            "tagline":p.tagline or "","features":[x.strip() for x in (p.features or "").split(";") if x.strip()],
            "price_label":p.price_label,"url":p.url,"platforms":[x.strip() for x in (p.platforms or "").split(";") if x.strip()],
            "version":p.version or "","github_url":p.github_url or "","docs_url":p.docs_url or "",
            "demo_url":p.demo_url or "","image_url":p.image_url or "","is_featured":bool(p.is_featured),"status":p.status}

@app.get("/api/products")
def products(category:str|None=None, search:str|None=None, featured:bool|None=None, db:Session=Depends(get_db)):
    query=db.query(Product).filter(Product.status=="published",Product.archived_at.is_(None))
    if category: query=query.filter(func.lower(Product.category)==category.lower())
    if search:
        term=f"%{search.strip()}%"
        query=query.filter((Product.name.ilike(term))|(Product.description.ilike(term))|(Product.category.ilike(term)))
    if featured is not None: query=query.filter(Product.is_featured==featured)
    return [product_payload(p) for p in query.order_by(Product.sort_order,Product.name).all()]

@app.get("/api/products/{slug}")
def product_detail(slug:str,db:Session=Depends(get_db)):
    p=db.query(Product).filter(Product.slug==slug,Product.status=="published",Product.archived_at.is_(None)).first()
    if not p: raise HTTPException(404,"Product not found")
    return product_payload(p)

def smtp_is_configured():
    return all(os.getenv(k, "").strip() for k in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "ADMIN_EMAIL"))

def run_automations(db:Session, event:str, entity_type:str, entity_id:int, payload:dict):
    """Execute enabled, explicitly supported email-notification workflows and persist every result."""
    workflows=db.query(AutomationWorkflow).filter(AutomationWorkflow.trigger_event==event, AutomationWorkflow.enabled==True).all()
    for workflow in workflows:
        if workflow.action_type != "email_notification":
            run=AutomationRun(workflow_id=workflow.id,trigger_event=event,entity_type=entity_type,entity_id=str(entity_id),status="failed",detail="Unsupported action type; no action was executed.")
        else:
            body=(f"Workflow: {workflow.name}\nEvent: {event}\nRecord: {entity_type} #{entity_id}\n\n" +
                  "\n".join(f"{k}: {str(v)[:1000]}" for k,v in payload.items()))
            delivered=send_email(f"[NEXOVARA automation] {workflow.name}",body)
            run=AutomationRun(workflow_id=workflow.id,trigger_event=event,entity_type=entity_type,entity_id=str(entity_id),
                              status="succeeded" if delivered else "failed",
                              detail="Email handed to configured SMTP server." if delivered else "Email delivery was not confirmed. Check SMTP configuration and server logs.")
        db.add(run)

def aurora_config():
    base=os.getenv("AURORA_BASE_URL", "").strip().rstrip("/")
    token=os.getenv("AURORA_API_TOKEN", "").strip()
    if not base or not token:
        return None, None
    parsed=urllib.parse.urlparse(base)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(503,"AURORA_BASE_URL must be a clean http(s) service URL.")
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise HTTPException(503,"AURORA_BASE_URL must use HTTPS outside local development.")
    return base, token

@app.get("/api/admin/integrations/aurora/status")
async def aurora_status(user:User=Depends(staff_access)):
    base,token=aurora_config()
    if not base or not token:
        return {"configured":False,"status":"not_configured","message":"Set AURORA_BASE_URL and AURORA_API_TOKEN on the server."}
    try:
        async with httpx.AsyncClient(timeout=8,follow_redirects=False) as client:
            response=await client.get(base+"/ai/native/models",headers={"Authorization":"Bearer "+token})
        if response.status_code==200:
            try: upstream=response.json()
            except ValueError: upstream={}
            return {"configured":True,"status":"reachable","service":"AURORA AI","inference_configured":True}
        if response.status_code==401: return {"configured":True,"status":"authentication_error","message":"The AURORA service token is invalid or expired."}
        return {"configured":True,"status":"upstream_error","http_status":response.status_code,"message":"AURORA model endpoint returned a non-success response."}
    except httpx.HTTPError:
        return {"configured":True,"status":"unreachable","message":"Could not reach the configured AURORA service."}

@app.post("/api/admin/integrations/aurora/chat")
async def aurora_chat(data:AuroraChatIn,user:User=Depends(staff_access)):
    base,token=aurora_config()
    if not base or not token: raise HTTPException(503,"AURORA is not configured. Set AURORA_BASE_URL and AURORA_API_TOKEN on the server.")
    payload={"model":data.model,"messages":[m.model_dump() for m in data.messages],"stream":False,"max_tokens":data.max_tokens,"temperature":data.temperature}
    try:
        async with httpx.AsyncClient(timeout=150,follow_redirects=False) as client:
            response=await client.post(base+"/ai/native/chat/completions",headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"},json=payload)
        if response.status_code==401: raise HTTPException(502,"AURORA rejected its service token. It may have expired; refresh AURORA_API_TOKEN.")
        if response.status_code==503: raise HTTPException(503,"AURORA inference is not configured or is temporarily unavailable.")
        if response.status_code>=400: raise HTTPException(502,f"AURORA returned HTTP {response.status_code}.")
        return response.json()
    except httpx.HTTPError: raise HTTPException(502,"Could not reach AURORA chat service.")
    except ValueError: raise HTTPException(502,"AURORA returned an invalid response.")

@app.post("/api/admin/integrations/aurora/knowledge/ask")
async def aurora_knowledge_ask(data:AuroraKnowledgeAskIn,user:User=Depends(staff_access)):
    base,token=aurora_config()
    if not base or not token: raise HTTPException(503,"AURORA is not configured. Set AURORA_BASE_URL and AURORA_API_TOKEN on the server.")
    try:
        async with httpx.AsyncClient(timeout=90,follow_redirects=False) as client:
            response=await client.post(base+"/foundry/knowledge/ask",headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"},json={"question":data.question})
        if response.status_code==401: raise HTTPException(502,"AURORA rejected its service token. It may have expired; refresh AURORA_API_TOKEN.")
        if response.status_code>=400: raise HTTPException(502,f"AURORA knowledge service returned HTTP {response.status_code}.")
        return response.json()
    except httpx.HTTPError: raise HTTPException(502,"Could not reach AURORA knowledge service.")
    except ValueError: raise HTTPException(502,"AURORA returned an invalid response.")

@app.get("/api/admin/automations")
def admin_automations(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return [{"id":w.id,"name":w.name,"trigger_event":w.trigger_event,"action_type":w.action_type,"enabled":w.enabled,"created_at":str(w.created_at)} for w in db.query(AutomationWorkflow).order_by(AutomationWorkflow.id.desc()).all()]

@app.post("/api/admin/automations")
def create_automation(data:AutomationWorkflowIn,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    if data.enabled and not smtp_is_configured(): raise HTTPException(400,"Configure SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD and ADMIN_EMAIL before enabling email workflows.")
    workflow=AutomationWorkflow(name=data.name,trigger_event=data.trigger_event,action_type="email_notification",enabled=data.enabled,created_by=user.id)
    db.add(workflow);db.flush();record_audit(db,user,"automation.created","automation",workflow.id,{"trigger_event":workflow.trigger_event,"enabled":workflow.enabled});db.commit();db.refresh(workflow)
    return {"message":"Automation workflow created","workflow":{"id":workflow.id,"name":workflow.name,"trigger_event":workflow.trigger_event,"enabled":workflow.enabled}}

@app.patch("/api/admin/automations/{workflow_id}")
def update_automation(workflow_id:int,data:AutomationWorkflowIn,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    workflow=db.query(AutomationWorkflow).filter(AutomationWorkflow.id==workflow_id).first()
    if not workflow: raise HTTPException(404,"Automation workflow not found")
    if data.enabled and not smtp_is_configured(): raise HTTPException(400,"Configure SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD and ADMIN_EMAIL before enabling email workflows.")
    workflow.name=data.name;workflow.trigger_event=data.trigger_event;workflow.enabled=data.enabled
    record_audit(db,user,"automation.updated","automation",workflow.id,{"trigger_event":workflow.trigger_event,"enabled":workflow.enabled});db.commit()
    return {"message":"Automation workflow updated"}

@app.get("/api/admin/automations/runs")
def automation_runs(limit:int=100,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    limit=max(1,min(limit,300))
    rows=db.query(AutomationRun).order_by(AutomationRun.id.desc()).limit(limit).all()
    return [{"id":r.id,"workflow_id":r.workflow_id,"trigger_event":r.trigger_event,"entity_type":r.entity_type,"entity_id":r.entity_id,"status":r.status,"detail":r.detail,"created_at":str(r.created_at)} for r in rows]

@app.post("/api/leads")
def create_lead(data:LeadIn,background:BackgroundTasks,db:Session=Depends(get_db)):
    lead=Lead(**data.model_dump());db.add(lead);db.commit();db.refresh(lead)
    run_automations(db,"lead.created","lead",lead.id,{"name":lead.name,"email":lead.email,"company":lead.company,"service":lead.service,"budget":lead.budget,"message":lead.message});db.commit()
    background.add_task(send_email,"New website enquiry",f"Name: {lead.name}\nEmail: {lead.email}\nCompany: {lead.company}\nService: {lead.service}\nMessage: {lead.message}")
    return {"message":"Thank you. Your enquiry has been received.","id":lead.id}

@app.post("/api/careers/apply")
def apply(data:CareerApplicationIn,db:Session=Depends(get_db)):
    row=JobApplication(name=data.name,email=data.email.lower(),role=data.role,portfolio=data.portfolio,message=data.message)
    db.add(row);db.commit()
    return {"message":"Application received. Thank you."}

@app.post("/api/quotes")
def create_quote(data:QuoteIn,background:BackgroundTasks,db:Session=Depends(get_db)):
    values=data.model_dump();values["email"]=data.email.lower()
    quote=Quote(**values)
    db.add(quote);db.commit();db.refresh(quote)
    run_automations(db,"quote.created","quote",quote.id,{"name":quote.name,"email":quote.email,"company":quote.company,"service":quote.service,"product":quote.product_slug,"budget":quote.budget,"timeline":quote.timeline,"details":quote.details});db.commit()
    background.add_task(send_email,"New quote request",f"Name: {quote.name}\nEmail: {quote.email}\nCompany: {quote.company}\nService: {quote.service}\nProduct: {quote.product_slug}\nBudget: {quote.budget}\nTimeline: {quote.timeline}\nDetails: {quote.details}")
    return {"message":"Quote request received","id":quote.id}

@app.get("/api/resources")
def resources(db:Session=Depends(get_db)):
    return [{"id":a.id,"title":a.title,"slug":a.slug,"category":a.category,"excerpt":a.excerpt,"body":a.body} for a in db.query(Article).filter(Article.published==True).all()]

@app.post("/api/client/tickets")
def new_ticket(data:TicketIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    t=Ticket(client_id=user.id,subject=data.subject,message=data.message);db.add(t);db.commit();db.refresh(t)
    run_automations(db,"ticket.created","ticket",t.id,{"client_id":user.id,"subject":t.subject,"message":t.message});db.commit()
    return {"message":"Support ticket created","id":t.id}

@app.get("/api/client/dashboard")
def client_dashboard(db:Session=Depends(get_db),user:User=Depends(current_user)):
    projects=db.query(Project).filter(Project.client_id==user.id).all()
    invoices=db.query(Invoice).filter(Invoice.client_id==user.id).all()
    tickets=db.query(Ticket).filter(Ticket.client_id==user.id).all()
    subs=db.query(Subscription).filter(Subscription.client_id==user.id).all()
    return {"projects":[{"id":p.id,"title":p.title,"description":p.description,"status":p.status,"progress":p.progress,"due_date":p.due_date} for p in projects],
      "invoices":[{"id":i.id,"number":i.number,"description":i.description,"amount":i.amount,"currency":i.currency,"status":i.status,"due_date":i.due_date} for i in invoices],
      "tickets":[{"id":t.id,"subject":t.subject,"message":t.message,"status":t.status,"response":t.response} for t in tickets],
      "subscriptions":[{"id":s.id,"plan":s.plan,"status":s.status,"amount":s.amount,"currency":s.currency} for s in subs]}

@app.get("/api/admin/overview")
def admin_overview(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return {"customers":db.query(User).filter(User.role=="client").count(),"leads":db.query(Lead).count(),
      "new_leads":db.query(Lead).filter(Lead.status=="new").count(),"new_quotes":db.query(Quote).filter(Quote.status=="new").count(),"quotes":db.query(Quote).count(),"products":db.query(Product).count(),
      "projects":db.query(Project).count(),"open_tickets":db.query(Ticket).filter(Ticket.status=="open").count(),
      "unpaid_invoices":db.query(Invoice).filter(Invoice.status=="unpaid").count(),
      "revenue_recorded":db.query(func.coalesce(func.sum(Invoice.amount),0)).filter(Invoice.status=="paid").scalar()}

@app.get("/api/admin/leads")
def admin_leads(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return [{"id":x.id,"name":x.name,"email":x.email,"company":x.company,"service":x.service,"budget":x.budget,"message":x.message,"status":x.status,"created_at":str(x.created_at)} for x in db.query(Lead).order_by(Lead.id.desc()).all()]

@app.patch("/api/admin/leads/{lead_id}")
def update_lead(lead_id:int,data:dict,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    x=db.query(Lead).filter(Lead.id==lead_id).first()
    if not x: raise HTTPException(404,"Lead not found")
    if data.get("status") in ["new","contacted","qualified","closed"]: x.status=data["status"]
    record_audit(db,user,"lead.updated","lead",x.id,{"status":x.status})
    db.commit();return {"message":"Lead updated"}

@app.get("/api/admin/customers")
def customers(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return [{"id":u.id,"name":u.name,"email":u.email,"company":u.company,"active":bool(u.active),"created_at":str(u.created_at)} for u in db.query(User).filter(User.role=="client").order_by(User.id).all()]

@app.get("/api/admin/projects")
def all_projects(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    rows=db.query(Project).order_by(Project.id.desc()).all(); names=user_names(db,[r.client_id for r in rows])
    return [{"id":p.id,"client_id":p.client_id,"client_name":names.get(p.client_id,{}).get("name",""),"title":p.title,"description":p.description,"status":p.status,"progress":p.progress,"due_date":p.due_date} for p in rows]

@app.post("/api/admin/projects")
def add_project(data:ProjectIn,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    if not db.query(User).filter(User.id==data.client_id,User.role=="client").first(): raise HTTPException(404,"Client not found")
    p=Project(**data.model_dump());db.add(p);db.flush();record_audit(db,user,"project.created","project",p.id,{"client_id":p.client_id,"title":p.title});db.commit();db.refresh(p);return {"id":p.id,"message":"Project created"}

@app.patch("/api/admin/projects/{project_id}")
def update_project(project_id:int,data:ProjectUpdate,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    proj=db.query(Project).filter(Project.id==project_id).first()
    if not proj: raise HTTPException(404,"Project not found")
    changes={k:v for k,v in data.model_dump(exclude_unset=True).items() if v is not None}
    for key,value in changes.items(): setattr(proj,key,value)
    if "status" in changes or "progress" in changes:
        db.add(Notification(user_id=proj.client_id,title="Project update",body=f"{proj.title}: {proj.status}, {proj.progress}% complete.",kind="project"))
    record_audit(db,user,"project.updated","project",proj.id,{"fields":list(changes.keys())}); db.commit()
    return {"message":"Project updated"}

@app.get("/api/admin/invoices")
def all_invoices(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    rows=db.query(Invoice).order_by(Invoice.id.desc()).all(); names=user_names(db,[r.client_id for r in rows])
    return [{"id":i.id,"client_id":i.client_id,"client_name":names.get(i.client_id,{}).get("name",""),"number":i.number,"description":i.description,"amount":i.amount,"currency":i.currency,"status":i.status,"due_date":i.due_date} for i in rows]

@app.post("/api/admin/invoices")
def add_invoice(data:InvoiceIn,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    if not db.query(User).filter(User.id==data.client_id,User.role=="client").first(): raise HTTPException(404,"Client not found")
    if db.query(Invoice).filter(Invoice.number==data.number).first(): raise HTTPException(409,"Invoice number already exists")
    x=Invoice(**data.model_dump());db.add(x);db.flush();record_audit(db,user,"invoice.created","invoice",x.id,{"number":x.number,"client_id":x.client_id,"amount":x.amount,"currency":x.currency});db.commit();return {"message":"Invoice created"}

@app.patch("/api/admin/invoices/{invoice_id}")
def update_invoice(invoice_id:int,data:dict,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    x=db.query(Invoice).filter(Invoice.id==invoice_id).first()
    if not x: raise HTTPException(404,"Invoice not found")
    # A paid state must only be set by a verified payment-provider callback, and a settled invoice is never reopened.
    if x.status=="paid": raise HTTPException(409,"A paid invoice cannot be changed")
    if data.get("status") in ["unpaid","overdue","cancelled"]: x.status=data["status"]
    elif "status" in data: raise HTTPException(400,"Status must be unpaid, overdue or cancelled")
    record_audit(db,user,"invoice.updated","invoice",x.id,{"status":x.status})
    db.commit();return {"message":"Invoice updated"}

@app.get("/api/admin/tickets")
def all_tickets(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    rows=db.query(Ticket).order_by(Ticket.id.desc()).all(); names=user_names(db,[r.client_id for r in rows])
    return [{"id":t.id,"client_id":t.client_id,"client_name":names.get(t.client_id,{}).get("name",""),"client_email":names.get(t.client_id,{}).get("email",""),"subject":t.subject,"message":t.message,"status":t.status,"response":t.response} for t in rows]

@app.patch("/api/admin/tickets/{ticket_id}")
def update_ticket(ticket_id:int,data:TicketUpdate,background:BackgroundTasks,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    t=db.query(Ticket).filter(Ticket.id==ticket_id).first()
    if not t: raise HTTPException(404,"Ticket not found")
    previous_response=t.response or ""
    if data.response is not None: t.response=data.response
    if data.status is not None: t.status=data.status
    client=db.query(User).filter(User.id==t.client_id).first()
    if data.response is not None and data.response.strip() and data.response!=previous_response:
        db.add(Notification(user_id=t.client_id,title=f"Reply to your request: {t.subject}"[:180],body=data.response[:2000],kind="support"))
        if client: background.add_task(send_email_to,client.email,f"NEXOVARA support reply: {t.subject}",f"Hello {client.name},\n\n{data.response}\n\nYou can view the full thread in your client portal.")
    record_audit(db,user,"ticket.updated","ticket",t.id,{"status":t.status})
    db.commit();return {"message":"Ticket updated"}

@app.post("/api/admin/products")
def add_product(data:ProductIn,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    if db.query(Product).filter((Product.slug==data.slug)|(func.lower(Product.name)==data.name.lower())).first():
        raise HTTPException(409,"A product with this name or slug already exists")
    values=data.model_dump()
    p=Product(**values);db.add(p)
    try: db.commit()
    except Exception: db.rollback();raise HTTPException(409,"Product could not be saved; check name and slug uniqueness")
    db.refresh(p);record_audit(db,user,"product.created","product",p.id,{"slug":p.slug,"status":p.status});db.commit();return {"message":"Product created","product":product_payload(p)}

@app.get("/api/admin/products")
def admin_products(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return [product_payload(p) for p in db.query(Product).order_by(Product.sort_order,Product.name).all()]

@app.patch("/api/admin/products/{product_id}")
def edit_product(product_id:int,data:ProductUpdate,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    p=db.query(Product).filter(Product.id==product_id).first()
    if not p: raise HTTPException(404,"Product not found")
    values=data.model_dump(exclude_unset=True)
    if "slug" in values and db.query(Product).filter(Product.slug==values["slug"],Product.id!=product_id).first():
        raise HTTPException(409,"That product slug is already in use")
    if "name" in values and db.query(Product).filter(func.lower(Product.name)==values["name"].lower(),Product.id!=product_id).first():
        raise HTTPException(409,"That product name is already in use")
    for key,value in values.items(): setattr(p,key,value)
    if values.get("status")=="archived":
        from datetime import datetime, timezone
        p.archived_at=datetime.now(timezone.utc)
    elif values.get("status")=="published": p.archived_at=None
    record_audit(db,user,"product.updated","product",p.id,{"fields":list(values.keys())})
    db.commit();db.refresh(p);return {"message":"Product updated","product":product_payload(p)}

@app.delete("/api/admin/products/{product_id}")
def archive_product(product_id:int,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    p=db.query(Product).filter(Product.id==product_id).first()
    if not p: raise HTTPException(404,"Product not found")
    from datetime import datetime, timezone
    p.status="archived";p.archived_at=datetime.now(timezone.utc);record_audit(db,user,"product.archived","product",p.id,{"slug":p.slug});db.commit()
    return {"message":"Product archived"}

@app.post("/api/admin/articles")
def add_article(data:ArticleIn,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    if db.query(Article).filter(Article.slug==data.slug).first(): raise HTTPException(409,"An article with this slug already exists")
    a=Article(**data.model_dump());db.add(a);db.flush();record_audit(db,user,"article.created","article",a.id,{"slug":a.slug});db.commit()
    return {"message":"Article saved","id":a.id}

def article_admin_payload(a): return {"id":a.id,"title":a.title,"slug":a.slug,"category":a.category,"excerpt":a.excerpt,"body":a.body,"published":bool(a.published)}

@app.get("/api/admin/articles")
def admin_articles(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return [article_admin_payload(a) for a in db.query(Article).order_by(Article.id.desc()).all()]

@app.patch("/api/admin/articles/{article_id}")
def edit_article(article_id:int,data:ArticleUpdate,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    a=db.query(Article).filter(Article.id==article_id).first()
    if not a: raise HTTPException(404,"Article not found")
    changes={k:v for k,v in data.model_dump(exclude_unset=True).items() if v is not None}
    if "slug" in changes and db.query(Article).filter(Article.slug==changes["slug"],Article.id!=article_id).first(): raise HTTPException(409,"That article slug is already in use")
    for key,value in changes.items(): setattr(a,key,value)
    record_audit(db,user,"article.updated","article",a.id,{"fields":list(changes.keys())}); db.commit()
    return {"message":"Article updated"}

@app.delete("/api/admin/articles/{article_id}")
def delete_article(article_id:int,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    a=db.query(Article).filter(Article.id==article_id).first()
    if not a: raise HTTPException(404,"Article not found")
    record_audit(db,user,"article.deleted","article",a.id,{"slug":a.slug}); db.delete(a); db.commit()
    return {"message":"Article deleted"}

@app.get("/api/admin/quotes")
def admin_quotes(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return [{"id":q.id,"name":q.name,"email":q.email,"company":q.company,"service":q.service,
             "product_slug":q.product_slug,"budget":q.budget,"timeline":q.timeline,"details":q.details,
             "status":q.status,"admin_notes":q.admin_notes,"created_at":str(q.created_at)}
            for q in db.query(Quote).order_by(Quote.id.desc()).all()]

@app.patch("/api/admin/quotes/{quote_id}")
def update_quote(quote_id:int,data:QuoteUpdate,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    q=db.query(Quote).filter(Quote.id==quote_id).first()
    if not q: raise HTTPException(404,"Quote request not found")
    changes=data.model_dump(exclude_unset=True)
    for key,value in changes.items(): setattr(q,key,value)
    record_audit(db,user,"quote.updated","quote",q.id,{"fields":list(changes.keys())})
    db.commit();return {"message":"Quote request updated"}

@app.get("/api/admin/audit-logs")
def admin_audit_logs(limit:int=100,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    limit=max(1,min(limit,500))
    return [{"id":a.id,"actor_email":a.actor_email,"action":a.action,"entity_type":a.entity_type,
             "entity_id":a.entity_id,"details":a.details,"created_at":str(a.created_at)}
            for a in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()]

@app.get("/api/admin/applications")
def applications(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return [{"id":a.id,"name":a.name,"email":a.email,"role":a.role,"portfolio":a.portfolio,"message":a.message} for a in db.query(JobApplication).all()]

@app.get("/api/admin/payments")
def admin_payments(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    rows=db.query(Payment).order_by(Payment.id.desc()).limit(500).all()
    return [{"id":p.id,"invoice_id":p.invoice_id,"client_id":p.client_id,"provider":p.provider,"reference":p.provider_reference,"merchant_reference":p.merchant_reference,"amount":p.amount,"currency":p.currency,"status":p.status,"created_at":str(p.created_at),"paid_at":str(p.paid_at or "")} for p in rows]

@app.get("/api/admin/staff/roles")
def staff_roles(user:User=Depends(admin_user)):
    return {role:sorted(perms) if "*" not in perms else ["*"] for role,perms in ROLE_PERMISSIONS.items() if role not in ("client",)}

@app.get("/api/admin/staff")
def list_staff(db:Session=Depends(get_db),user:User=Depends(admin_user)):
    return [{"id":u.id,"name":u.name,"email":u.email,"role":u.role,"active":u.active,"mfa_enabled":u.mfa_enabled} for u in db.query(User).filter(User.role!="client").order_by(User.id).all()]

@app.post("/api/admin/staff")
def create_staff(data:dict,db:Session=Depends(get_db),user:User=Depends(admin_user)):
    email=str(data.get("email", "")).strip().lower(); role=str(data.get("role", "")); password=str(data.get("password", "")); name=str(data.get("name", "")).strip()
    if role not in ROLE_PERMISSIONS or role in ("admin","client"): raise HTTPException(400,"Select a permitted staff role")
    if len(password)<12 or len(password)>128 or len(name)<2 or "@" not in email: raise HTTPException(400,"Provide valid name, email and a 12+ character password")
    if db.query(User).filter(User.email==email).first(): raise HTTPException(409,"Email already exists")
    row=User(name=name,email=email,password_hash=hash_password(password),role=role); db.add(row); db.flush()
    record_audit(db,user,"staff.created","user",row.id,{"role":role}); db.commit()
    return {"id":row.id,"message":"Staff account created. MFA enrollment is required before production access."}

@app.post("/api/admin/staff/{staff_id}/mfa/reset")
def reset_staff_mfa(staff_id:int,db:Session=Depends(get_db),user:User=Depends(admin_user)):
    row=db.query(User).filter(User.id==staff_id,User.role!="client").first()
    if not row: raise HTTPException(404,"Staff account not found")
    if row.id==user.id: raise HTTPException(400,"Use your own authenticator; self-reset is disabled")
    row.mfa_enabled=False; row.mfa_secret=""; row.mfa_pending_secret=""; row.token_version=(row.token_version or 0)+1
    record_audit(db,user,"staff.mfa_reset","user",row.id,{"reason":"administrator_reset"}); db.commit()
    return {"message":"Staff MFA reset. The staff member must enroll a new authenticator before accessing staff routes."}

@app.patch("/api/admin/staff/{staff_id}")
def update_staff(staff_id:int,data:dict,db:Session=Depends(get_db),user:User=Depends(admin_user)):
    row=db.query(User).filter(User.id==staff_id,User.role!="client").first()
    if not row: raise HTTPException(404,"Staff account not found")
    if "role" in data:
        role=str(data["role"])
        if role not in ROLE_PERMISSIONS or role in ("admin","client"): raise HTTPException(400,"Invalid staff role")
        row.role=role
    if "active" in data:
        if not isinstance(data["active"],bool): raise HTTPException(400,"active must be boolean")
        if row.id==user.id and not data["active"]: raise HTTPException(400,"You cannot deactivate your own account")
        row.active=data["active"]
    row.token_version=(row.token_version or 0)+1
    record_audit(db,user,"staff.updated","user",row.id,{"role":row.role,"active":row.active}); db.commit()
    return {"message":"Staff account updated; previous sessions revoked."}

PENDING_PAYMENT_TTL={"stripe":45,"mpesa":10}  # minutes; Stripe sessions are created to expire sooner (31 min)

def expire_stale_payments(db:Session, invoice_id:int):
    """Mark abandoned pending attempts as expired so the customer can retry."""
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    for pay in db.query(Payment).filter(Payment.invoice_id==invoice_id,Payment.status=="pending").all():
        created=pay.created_at
        if created is None: continue
        if created.tzinfo is None: created=created.replace(tzinfo=timezone.utc)
        if now-created>timedelta(minutes=PENDING_PAYMENT_TTL.get(pay.provider,30)): pay.status="expired"
    db.commit()

def _invoice_for_user(invoice_id:int, user:User, db:Session):
    inv=db.query(Invoice).filter(Invoice.id==invoice_id,Invoice.client_id==user.id).first()
    if not inv: raise HTTPException(404,"Invoice not found")
    if inv.status=="paid": raise HTTPException(409,"Invoice is already paid")
    if inv.status not in ("unpaid","overdue"): raise HTTPException(400,"Invoice cannot be paid in its current state")
    expire_stale_payments(db,inv.id)
    return inv

@app.get("/api/payments/{payment_id}")
def payment_status(payment_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    pay=db.query(Payment).filter(Payment.id==payment_id,Payment.client_id==user.id).first()
    if not pay: raise HTTPException(404,"Payment not found")
    inv=db.query(Invoice).filter(Invoice.id==pay.invoice_id).first()
    return {"id":pay.id,"provider":pay.provider,"status":pay.status,"invoice_id":pay.invoice_id,"invoice_status":inv.status if inv else None}

@app.post("/api/payments/stripe/checkout")
def stripe_checkout(data:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if not os.getenv("STRIPE_SECRET_KEY") or not os.getenv("STRIPE_WEBHOOK_SECRET") or not os.getenv("PUBLIC_APP_URL"):
        raise HTTPException(503,"Stripe keys and PUBLIC_APP_URL are required")
    try:
        import stripe
        stripe.api_key=os.getenv("STRIPE_SECRET_KEY")
        invoice=_invoice_for_user(int(data.get("invoice_id")),user,db)
        if invoice.currency.lower() not in {"kes","usd","eur","gbp"}: raise HTTPException(400,"Unsupported Stripe currency")
        if db.query(Payment).filter(Payment.invoice_id==invoice.id,Payment.provider=="stripe",Payment.status=="pending").first(): raise HTTPException(409,"A Stripe payment attempt is already pending for this invoice")
        payment=Payment(invoice_id=invoice.id,client_id=user.id,provider="stripe",merchant_reference=f"NXV-INV-{invoice.id}-{secrets.token_hex(5)}",amount=invoice.amount,currency=invoice.currency.upper(),status="pending")
        db.add(payment);db.flush()
        session=stripe.checkout.Session.create(mode="payment",payment_method_types=["card"],success_url=os.getenv("PAYMENT_SUCCESS_URL","") or (os.getenv("PUBLIC_APP_URL","").rstrip("/")+"/portal?payment=return"),cancel_url=os.getenv("PAYMENT_CANCEL_URL","") or (os.getenv("PUBLIC_APP_URL","").rstrip("/")+"/portal?payment=cancelled"),client_reference_id=str(invoice.id),expires_at=int(__import__("time").time())+31*60,metadata={"payment_id":str(payment.id),"invoice_id":str(invoice.id)},line_items=[{"price_data":{"currency":invoice.currency.lower(),"product_data":{"name":f"NEXOVARA invoice {invoice.number}"},"unit_amount":int(round(invoice.amount*100))},"quantity":1}],idempotency_key=payment.merchant_reference)
        payment.provider_reference=session.id;db.commit()
        return {"checkout_url":session.url,"payment_id":payment.id,"status":"pending"}
    except HTTPException: raise
    except Exception as exc:
        db.rollback(); raise HTTPException(502,"Could not create Stripe checkout session")

@app.post("/api/webhooks/stripe")
async def stripe_webhook(request:Request,db:Session=Depends(get_db)):
    secret=os.getenv("STRIPE_WEBHOOK_SECRET","")
    if not secret: raise HTTPException(503,"Stripe webhook is not configured")
    try:
        import stripe
        payload=await request.body(); signature=request.headers.get("stripe-signature","")
        event=stripe.Webhook.construct_event(payload,signature,secret)
    except Exception: raise HTTPException(400,"Invalid Stripe webhook signature or payload")
    if db.query(PaymentEvent).filter(PaymentEvent.event_id==event.id).first(): return {"received":True,"duplicate":True}
    db.add(PaymentEvent(provider="stripe",event_id=event.id))
    if event.type=="checkout.session.completed":
        obj=event.data.object; payment=db.query(Payment).filter(Payment.id==int(obj.metadata.get("payment_id",0)),Payment.provider=="stripe").first()
        if payment and payment.provider_reference==obj.id and payment.status!="succeeded" and obj.payment_status=="paid":
            invoice=db.query(Invoice).filter(Invoice.id==payment.invoice_id,Invoice.client_id==payment.client_id).first()
            total=int(round(payment.amount*100)); currency=payment.currency.lower()
            if invoice and invoice.status!="paid" and int(obj.amount_total or -1)==total and str(obj.currency).lower()==currency:
                from datetime import datetime,timezone
                payment.status="succeeded"; invoice.status="paid"; payment.paid_at=datetime.now(timezone.utc)
                payment.provider_reference=obj.id
                db.add(Notification(user_id=payment.client_id,title="Payment received",body=f"Payment for invoice {invoice.number} was confirmed.",kind="payment"))
    elif event.type=="checkout.session.expired":
        obj=event.data.object
        try: pid=int(obj.metadata.get("payment_id",0))
        except (TypeError,ValueError): pid=0
        payment=db.query(Payment).filter(Payment.id==pid,Payment.provider=="stripe").first()
        if payment and payment.status=="pending" and payment.provider_reference==obj.id: payment.status="expired"
    db.commit()
    return {"received":True}

@app.post("/api/payments/mpesa/stk-push")
async def mpesa_stk_push(data:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    required=["MPESA_CONSUMER_KEY","MPESA_CONSUMER_SECRET","MPESA_SHORTCODE","MPESA_PASSKEY","MPESA_CALLBACK_TOKEN"]
    if any(not os.getenv(k) for k in required) or not os.getenv("PUBLIC_APP_URL"): raise HTTPException(503,"M-PESA Daraja settings and PUBLIC_APP_URL are required")
    if not os.getenv("PUBLIC_APP_URL", "").startswith("https://"): raise HTTPException(503,"PUBLIC_APP_URL must use HTTPS for Safaricom callbacks")
    invoice=_invoice_for_user(int(data.get("invoice_id")),user,db)
    if invoice.currency.upper()!="KES": raise HTTPException(400,"M-PESA payments require a KES invoice")
    if abs(invoice.amount-round(invoice.amount))>0.000001: raise HTTPException(400,"M-PESA STK invoices must be whole KES amounts")
    if db.query(Payment).filter(Payment.invoice_id==invoice.id,Payment.provider=="mpesa",Payment.status=="pending").first(): raise HTTPException(409,"An M-PESA payment attempt is already pending for this invoice")
    phone=re.sub(r"\D", "", str(data.get("phone", "")))
    if phone.startswith("0"): phone="254"+phone[1:]
    if phone.startswith("7") or phone.startswith("1"): phone="254"+phone
    if not re.fullmatch(r"254[17]\d{8}",phone): raise HTTPException(400,"Enter a valid Kenyan mobile number, e.g. 2547XXXXXXXX")
    mpesa_env=os.getenv("MPESA_ENV","sandbox").lower()
    if mpesa_env not in ("sandbox","live"): raise HTTPException(503,"MPESA_ENV must be sandbox or live")
    base="https://sandbox.safaricom.co.ke" if mpesa_env=="sandbox" else "https://api.safaricom.co.ke"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            auth=await client.get(base+"/oauth/v1/generate?grant_type=client_credentials",auth=(os.getenv("MPESA_CONSUMER_KEY"),os.getenv("MPESA_CONSUMER_SECRET")))
            auth.raise_for_status(); access=auth.json()["access_token"]
            from datetime import datetime, timezone, timedelta
            timestamp=datetime.now(timezone(timedelta(hours=3))).strftime("%Y%m%d%H%M%S")  # East Africa Time, no DST
            shortcode=os.getenv("MPESA_SHORTCODE")
            password=base64.b64encode((shortcode+os.getenv("MPESA_PASSKEY")+timestamp).encode()).decode()
            callback=os.getenv("PUBLIC_APP_URL","").rstrip("/")+"/api/webhooks/mpesa/"+os.getenv("MPESA_CALLBACK_TOKEN")
            payment=Payment(invoice_id=invoice.id,client_id=user.id,provider="mpesa",merchant_reference=f"NXV-{invoice.id}-{secrets.token_hex(5)}",amount=invoice.amount,currency="KES",status="pending")
            db.add(payment);db.flush()
            body={"BusinessShortCode":shortcode,"Password":password,"Timestamp":timestamp,"TransactionType":os.getenv("MPESA_TRANSACTION_TYPE","CustomerPayBillOnline"),"Amount":int(round(invoice.amount)),"PartyA":phone,"PartyB":shortcode,"PhoneNumber":phone,"CallBackURL":callback,"AccountReference":payment.merchant_reference,"TransactionDesc":f"Invoice {invoice.number}"}
            resp=await client.post(base+"/mpesa/stkpush/v1/processrequest",headers={"Authorization":"Bearer "+access},json=body)
            resp.raise_for_status(); result=resp.json()
            if result.get("ResponseCode")!="0": raise HTTPException(502,"Safaricom did not accept the STK request")
            payment.provider_reference=result.get("CheckoutRequestID"); payment.merchant_request_id=result.get("MerchantRequestID"); payment.payer_phone=phone; db.commit()
            return {"message":"STK push sent. Complete the prompt on your phone.","payment_id":payment.id,"checkout_request_id":payment.provider_reference,"status":"pending"}
    except HTTPException: db.rollback(); raise
    except Exception:
        db.rollback(); raise HTTPException(502,"Could not initiate M-PESA STK push")

@app.post("/api/webhooks/mpesa/{callback_token}")
async def mpesa_callback(callback_token:str,request:Request,db:Session=Depends(get_db)):
    expected=os.getenv("MPESA_CALLBACK_TOKEN","")
    if not expected or not hmac.compare_digest(callback_token,expected): raise HTTPException(404,"Not found")
    try: payload=await request.json(); body=payload["Body"]["stkCallback"]
    except Exception: raise HTTPException(400,"Invalid M-PESA callback payload")
    checkout=str(body.get("CheckoutRequestID", "")); event_id="mpesa:"+checkout
    if not checkout: raise HTTPException(400,"Missing checkout request reference")
    if db.query(PaymentEvent).filter(PaymentEvent.event_id==event_id).first(): return {"ResultCode":0,"ResultDesc":"Duplicate callback acknowledged"}
    payment=db.query(Payment).filter(Payment.provider=="mpesa",Payment.provider_reference==checkout).first()
    db.add(PaymentEvent(provider="mpesa",event_id=event_id))
    if payment and payment.status in ("pending","expired"):
        if int(body.get("ResultCode",-1))==0:
            metadata={x.get("Name"):x.get("Value") for x in body.get("CallbackMetadata",{}).get("Item",[])}
            try: paid_amount=float(metadata.get("Amount",-1)); receipt=str(metadata.get("MpesaReceiptNumber", ""))
            except (TypeError,ValueError): paid_amount=-1; receipt=""
            invoice=db.query(Invoice).filter(Invoice.id==payment.invoice_id,Invoice.client_id==payment.client_id).first()
            merchant_request=str(body.get("MerchantRequestID", ""))
            callback_phone=str(metadata.get("PhoneNumber", ""))
            if invoice and invoice.status!="paid" and merchant_request==str(payment.merchant_request_id or "") and callback_phone==payment.payer_phone and receipt and abs(paid_amount-payment.amount)<0.01 and abs(paid_amount-invoice.amount)<0.01 and invoice.currency.upper()=="KES":
                from datetime import datetime,timezone
                payment.status="succeeded"; payment.provider_reference=checkout; payment.merchant_reference=receipt
                payment.paid_at=datetime.now(timezone.utc); invoice.status="paid"
                db.add(Notification(user_id=payment.client_id,title="M-PESA payment received",body=f"Payment for invoice {invoice.number} was confirmed. Receipt: {receipt}",kind="payment"))
            else: payment.status="review"
        else: payment.status="failed"
    db.commit()
    return {"ResultCode":0,"ResultDesc":"Callback processed"}

@app.get("/api/client/files")
def client_files(db:Session=Depends(get_db),user:User=Depends(current_user)):
    rows=db.query(StoredFile).filter(StoredFile.owner_id==user.id).order_by(StoredFile.id.desc()).limit(200).all()
    return [{"id":f.id,"filename":f.original_filename,"content_type":f.content_type,"size_bytes":f.size_bytes,"created_at":str(f.created_at)} for f in rows]

@app.post("/api/files/upload")
async def upload_private_file(file:UploadFile=File(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    max_bytes=int(os.getenv("MAX_UPLOAD_BYTES","10485760")); data=await file.read(max_bytes+1)
    if not data or len(data)>max_bytes: raise HTTPException(413,"File is empty or exceeds the upload limit")
    ext=os.path.splitext(file.filename or "")[1].lower()
    allowed={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".txt":"text/plain",".csv":"text/csv",".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if ext not in allowed: raise HTTPException(415,"File type is not allowed")
    valid=(ext==".pdf" and data.startswith(b"%PDF-")) or (ext==".png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or (ext in (".jpg",".jpeg") and data.startswith(b"\xff\xd8\xff")) or (ext in (".txt",".csv") and b"\x00" not in data[:4096]) or (ext==".docx" and data.startswith(b"PK\x03\x04"))
    if not valid: raise HTTPException(415,"File content does not match its extension")
    if ext==".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names=archive.namelist()
                if any(name.lower().endswith("vbaproject.bin") or name.startswith("word/embeddings/") for name in names):
                    raise HTTPException(415,"Macro-enabled or embedded-object documents are not accepted")
        except zipfile.BadZipFile: raise HTTPException(415,"Invalid DOCX archive")
    clam_host=os.getenv("CLAMAV_HOST",""); clam_port=int(os.getenv("CLAMAV_PORT","3310"))
    if not clam_host: raise HTTPException(503,"Malware scanning is not configured; uploads are disabled until CLAMAV_HOST is set")
    try:
        with socket.create_connection((clam_host,clam_port),timeout=15) as sock:
            sock.sendall(b"zINSTREAM\0")
            for offset in range(0,len(data),65536):
                chunk=data[offset:offset+65536]; sock.sendall(len(chunk).to_bytes(4,"big")+chunk)
            sock.sendall((0).to_bytes(4,"big")); response_parts=[]
            while True:
                part=sock.recv(4096)
                if not part: break
                response_parts.append(part)
                if b"\x00" in part: break
            scan=b"".join(response_parts).decode("utf-8","replace")
        if "OK" not in scan: raise HTTPException(422,"File failed malware scanning")
    except HTTPException: raise
    except Exception: raise HTTPException(503,"Malware scanning service is unavailable; upload rejected")
    supabase=os.getenv("SUPABASE_URL","").rstrip("/"); key=os.getenv("SUPABASE_SERVICE_ROLE_KEY",""); bucket=os.getenv("SUPABASE_STORAGE_BUCKET","nexovara-private")
    if not supabase or not key: raise HTTPException(503,"Supabase private storage is not configured")
    safe_name=re.sub(r"[^A-Za-z0-9._-]","_",os.path.basename(file.filename or "upload"))[:120]
    storage_path=f"users/{user.id}/{uuid.uuid4().hex}_{safe_name}"
    url=f"{supabase}/storage/v1/object/{bucket}/{storage_path}"
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            response=await client.post(url,content=data,headers={"apikey":key,"Authorization":"Bearer "+key,"Content-Type":allowed[ext],"x-upsert":"false"})
        if response.status_code>=300: raise HTTPException(502,"Supabase Storage rejected the upload")
    except HTTPException: raise
    except httpx.HTTPError: raise HTTPException(502,"Could not reach Supabase Storage")
    row=StoredFile(owner_id=user.id,storage_path=storage_path,original_filename=safe_name,content_type=allowed[ext],size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    db.add(row);db.flush();record_audit(db,user,"file.uploaded","stored_file",row.id,{"filename":row.original_filename,"size_bytes":row.size_bytes,"sha256":row.sha256});db.commit();db.refresh(row)
    return {"id":row.id,"filename":row.original_filename,"size_bytes":row.size_bytes,"sha256":row.sha256}

@app.delete("/api/files/{file_id}")
async def delete_private_file(file_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=db.query(StoredFile).filter(StoredFile.id==file_id).first()
    if not row or (row.owner_id!=user.id and user.role!="admin"): raise HTTPException(404,"File not found")
    supabase=os.getenv("SUPABASE_URL","").rstrip("/"); key=os.getenv("SUPABASE_SERVICE_ROLE_KEY",""); bucket=os.getenv("SUPABASE_STORAGE_BUCKET","nexovara-private")
    if not supabase or not key: raise HTTPException(503,"Supabase Storage is not configured")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.delete(f"{supabase}/storage/v1/object/{bucket}/{row.storage_path}",headers={"apikey":key,"Authorization":"Bearer "+key})
        if response.status_code>=300: raise HTTPException(502,"Supabase Storage deletion failed")
    except HTTPException: raise
    except httpx.HTTPError: raise HTTPException(502,"Could not reach Supabase Storage")
    record_audit(db,user,"file.deleted","stored_file",row.id,{"filename":row.original_filename});db.delete(row);db.commit()
    return {"message":"Document deleted"}

@app.get("/api/files/{file_id}")
async def download_private_file(file_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=db.query(StoredFile).filter(StoredFile.id==file_id).first()
    if not row: raise HTTPException(404,"File not found")
    if row.owner_id!=user.id and user.role!="admin": raise HTTPException(404,"File not found")
    supabase=os.getenv("SUPABASE_URL","").rstrip("/"); key=os.getenv("SUPABASE_SERVICE_ROLE_KEY",""); bucket=os.getenv("SUPABASE_STORAGE_BUCKET","nexovara-private")
    if not supabase or not key: raise HTTPException(503,"Supabase Storage is not configured")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.get(f"{supabase}/storage/v1/object/{bucket}/{row.storage_path}",headers={"apikey":key,"Authorization":"Bearer "+key})
        if response.status_code==404: raise HTTPException(404,"Stored file not found")
        if response.status_code>=300: raise HTTPException(502,"Supabase Storage download failed")
        return Response(content=response.content,media_type=row.content_type,headers={"Content-Disposition":f'attachment; filename="{row.original_filename}"','X-Content-Type-Options':'nosniff'})
    except HTTPException: raise
    except httpx.HTTPError: raise HTTPException(502,"Could not retrieve file from Supabase Storage")

@app.get("/api/platform/config")
def platform_config():
    return {"default_currency":os.getenv("DEFAULT_CURRENCY","KES"),"supported_currencies":["KES","USD","EUR","GBP","TZS","UGX","RWF","NGN","ZAR"],"default_locale":os.getenv("DEFAULT_LOCALE","en"),"supported_locales":["en","sw","fr","ar"],"timezone":os.getenv("DEFAULT_TIMEZONE","Africa/Nairobi")}

@app.get("/api/admin/integrations/readiness")
def integration_readiness(user:User=Depends(staff_access)):
    return {"aurora_ai":{"configured":bool(os.getenv("AURORA_BASE_URL") and os.getenv("AURORA_API_TOKEN")),"mode":"server-to-server"},"smtp":{"configured":smtp_is_configured(),"mode":"SMTP STARTTLS configured; use the admin test-email action to verify server acceptance"},"mpesa":{"configured":bool(os.getenv("MPESA_CONSUMER_KEY") and os.getenv("MPESA_CONSUMER_SECRET") and os.getenv("MPESA_SHORTCODE") and os.getenv("MPESA_PASSKEY") and os.getenv("MPESA_CALLBACK_TOKEN") and os.getenv("PUBLIC_APP_URL")),"mode":"Daraja STK push and callback validation code present; sandbox/live transaction and reconciliation still required"},"card_payments":{"configured":bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_WEBHOOK_SECRET") and os.getenv("PUBLIC_APP_URL")),"mode":"Stripe Checkout and signed webhook verification implemented; provider test transaction still required"},"database":{"configured":bool(os.getenv("DATABASE_URL")) and not os.getenv("DATABASE_URL","").startswith("sqlite"),"engine":"Supabase PostgreSQL" if "supabase" in os.getenv("DATABASE_URL","") or "pooler.supabase" in os.getenv("DATABASE_URL","") else "configured PostgreSQL/SQLite"},"redis_rate_limit":{"configured":bool(_redis_client),"required_env_present":_redis_configured,"mode":"shared Redis" if _redis_client else "per-process fallback only; not production-ready"},"supabase_storage":{"configured":bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY") and os.getenv("SUPABASE_STORAGE_BUCKET") and os.getenv("CLAMAV_HOST")),"mode":"Private bucket, server-side owner checks and ClamAV scan required"},"offsite_backups":{"configured":False,"mode":"Configured and verified through the separate Render Cron Job; not inferred from web-service variables"}}

@app.post("/api/partners/apply")
def partner_apply(data:PartnerApplicationIn,background:BackgroundTasks,db:Session=Depends(get_db)):
    values=data.model_dump(); values["email"]=data.email.lower()
    row=PartnerApplication(**values); db.add(row); db.commit(); db.refresh(row)
    background.add_task(send_email,"New partnership application",f"Name: {row.name}\nEmail: {row.email}\nOrganization: {row.organization}\nType: {row.partnership_type}\nWebsite: {row.website}\nMessage: {row.message}")
    run_automations(db,"partner.created","partner_application",row.id,{"name":row.name,"email":row.email,"organization":row.organization}); db.commit()
    return {"message":"Partnership application received.","id":row.id}

@app.get("/api/admin/partners")
def admin_partners(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    return [{"id":p.id,"name":p.name,"email":p.email,"organization":p.organization,"website":p.website,"partnership_type":p.partnership_type,"message":p.message,"status":p.status,"admin_notes":p.admin_notes,"created_at":str(p.created_at)} for p in db.query(PartnerApplication).order_by(PartnerApplication.id.desc()).all()]

@app.patch("/api/admin/partners/{partner_id}")
def update_partner(partner_id:int,data:dict,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    row=db.query(PartnerApplication).filter(PartnerApplication.id==partner_id).first()
    if not row: raise HTTPException(404,"Partner application not found")
    if "status" in data:
        if data["status"] not in ("new","reviewing","approved","declined","closed"): raise HTTPException(400,"Invalid partner status")
        row.status=data["status"]
    if "admin_notes" in data: row.admin_notes=str(data["admin_notes"])[:10000]
    record_audit(db,user,"partner.updated","partner_application",row.id,{"status":row.status}); db.commit()
    return {"message":"Partner application updated"}

@app.get("/api/client/notifications")
def client_notifications(db:Session=Depends(get_db),user:User=Depends(current_user)):
    rows=db.query(Notification).filter(Notification.user_id==user.id).order_by(Notification.id.desc()).limit(100).all()
    return [{"id":n.id,"title":n.title,"body":n.body,"kind":n.kind,"read":bool(n.read_at),"created_at":str(n.created_at)} for n in rows]

@app.patch("/api/client/notifications/{notification_id}/read")
def mark_notification_read(notification_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from datetime import datetime, timezone
    row=db.query(Notification).filter(Notification.id==notification_id,Notification.user_id==user.id).first()
    if not row: raise HTTPException(404,"Notification not found")
    row.read_at=datetime.now(timezone.utc); db.commit()
    return {"message":"Notification marked as read"}

@app.post("/api/admin/notifications")
def create_notification(data:NotificationIn,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    target=db.query(User).filter(User.id==data.user_id,User.active==True).first()
    if not target: raise HTTPException(404,"Active customer not found")
    row=Notification(**data.model_dump()); db.add(row)
    record_audit(db,user,"notification.created","notification","",{"user_id":target.id,"kind":row.kind}); db.commit(); db.refresh(row)
    return {"id":row.id,"message":"Notification created"}

@app.get("/api/client/licenses")
def client_licenses(db:Session=Depends(get_db),user:User=Depends(current_user)):
    rows=db.query(License).filter(License.client_id==user.id).order_by(License.id.desc()).all()
    pnames={pr.id:pr.name for pr in db.query(Product).filter(Product.id.in_([r.product_id for r in rows if r.product_id])).all()} if rows else {}
    return [{"id":x.id,"product_id":x.product_id,"product_name":pnames.get(x.product_id,""),"license_key":x.license_key,"status":x.status,"starts_at":str(x.starts_at or ""),"expires_at":str(x.expires_at or ""),"seats":x.seats} for x in rows]

@app.get("/api/admin/licenses")
def admin_licenses(db:Session=Depends(get_db),user:User=Depends(staff_access)):
    rows=db.query(License).order_by(License.id.desc()).all(); names=user_names(db,[r.client_id for r in rows])
    pnames={pr.id:pr.name for pr in db.query(Product).all()}
    return [{"id":x.id,"client_id":x.client_id,"client_name":names.get(x.client_id,{}).get("name",""),"product_name":pnames.get(x.product_id,""),"product_id":x.product_id,"license_key":x.license_key,"status":x.status,"expires_at":str(x.expires_at or ""),"seats":x.seats,"notes":x.notes} for x in rows]

@app.post("/api/admin/licenses")
def create_license(data:LicenseIn,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    import secrets
    from datetime import datetime, timezone
    client=db.query(User).filter(User.id==data.client_id,User.active==True).first()
    if not client: raise HTTPException(404,"Active customer not found")
    if data.product_id and not db.query(Product).filter(Product.id==data.product_id).first(): raise HTTPException(404,"Product not found")
    expires=None
    if data.expires_at:
        try: expires=datetime.fromisoformat(data.expires_at.replace("Z","+00:00"))
        except ValueError: raise HTTPException(400,"expires_at must be an ISO-8601 date/time")
    row=License(client_id=data.client_id,product_id=data.product_id,license_key="NXV-"+secrets.token_urlsafe(32),status="active",starts_at=datetime.now(timezone.utc),expires_at=expires,seats=data.seats,notes=data.notes)
    db.add(row); db.flush(); db.add(Notification(user_id=client.id,title="New product licence",body="A product licence has been assigned to your account.",kind="licence"))
    record_audit(db,user,"license.created","license",row.id,{"client_id":client.id,"product_id":data.product_id}); db.commit(); db.refresh(row)
    return {"id":row.id,"license_key":row.license_key,"status":row.status}

@app.patch("/api/admin/customers/{customer_id}")
def update_customer(customer_id:int,data:dict,db:Session=Depends(get_db),user:User=Depends(staff_access)):
    customer=db.query(User).filter(User.id==customer_id).first()
    if not customer: raise HTTPException(404,"Customer not found")
    if "active" in data:
        if not isinstance(data["active"],bool): raise HTTPException(400,"active must be true or false")
        if customer.id==user.id and data["active"] is False: raise HTTPException(400,"You cannot disable your own account")
        customer.active=data["active"]
    if "company" in data: customer.company=str(data["company"])[:180]
    record_audit(db,user,"customer.updated","user",customer.id,{"active":customer.active}); db.commit()
    return {"message":"Customer updated","active":customer.active}

def send_email_to(recipient,subject,body):
    host=os.getenv("SMTP_HOST","").strip()
    if not host or not recipient: return False
    try:
        msg=EmailMessage();msg["Subject"]=subject;msg["From"]=os.getenv("SMTP_FROM",os.getenv("SMTP_USERNAME",""));msg["To"]=recipient;msg.set_content(body)
        port=int(os.getenv("SMTP_PORT","587"))
        if port==465:
            with smtplib.SMTP_SSL(host,port,timeout=15) as server:
                server.login(os.getenv("SMTP_USERNAME"),os.getenv("SMTP_PASSWORD")); server.send_message(msg)
        else:
            with smtplib.SMTP(host,port,timeout=15) as server:
                server.ehlo(); server.starttls(); server.ehlo(); server.login(os.getenv("SMTP_USERNAME"),os.getenv("SMTP_PASSWORD")); server.send_message(msg)
        return True
    except Exception as exc:
        logger.warning("SMTP delivery failed: %s",type(exc).__name__)
        return False

def send_email(subject,body): return send_email_to(os.getenv("ADMIN_EMAIL", ""),subject,body)

@app.post("/api/admin/integrations/smtp/test")
def smtp_test(user:User=Depends(admin_user)):
    recipient=os.getenv("ADMIN_EMAIL", "")
    if not smtp_is_configured(): raise HTTPException(503,"SMTP settings are incomplete")
    if not send_email_to(recipient,"NEXOVARA SMTP delivery test","This is a test message from your NEXOVARA Render service."):
        raise HTTPException(502,"SMTP server did not accept the test message. Check host, port, TLS and credentials.")
    return {"message":"SMTP server accepted the test message. Check the recipient inbox and spam folder to confirm delivery."}

@app.get("/")
def home(): return FileResponse(FRONTEND_DIR/"index.html")
@app.get("/admin")
def admin_page(): return FileResponse(FRONTEND_DIR/"index.html")
@app.get("/portal")
def portal_page(): return FileResponse(FRONTEND_DIR/"index.html")
@app.get("/privacy")
def privacy_page(): return FileResponse(FRONTEND_DIR/"index.html")
@app.get("/terms")
def terms_page(): return FileResponse(FRONTEND_DIR/"index.html")
app.mount("/static",StaticFiles(directory=str(FRONTEND_DIR)),name="static")
