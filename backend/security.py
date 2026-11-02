import os
from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User

SECRET_KEY=os.getenv("SECRET_KEY","").strip()
if len(SECRET_KEY) < 32 or SECRET_KEY.lower() in {"replace-with-a-long-random-secret", "changeme", "secret"}:
    raise RuntimeError("SECRET_KEY must be set to a unique random value of at least 32 characters.")
ALGORITHM="HS256"
pwd=CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2=OAuth2PasswordBearer(tokenUrl="/api/auth/login",auto_error=False)

ROLE_PERMISSIONS={
 "admin":{"*"},
 "operations_manager":{"dashboard.view","careers.view","leads.view","leads.manage","customers.view","projects.view","projects.manage","quotes.view","quotes.manage","partners.view","partners.manage","support.view","support.manage","automation.view","automation.manage"},
 "finance_manager":{"dashboard.view","customers.view","products.view","projects.view","finance.view","finance.manage","licenses.view","licenses.manage","audit.view"},
 "support_agent":{"dashboard.view","customers.view","projects.view","support.view","support.manage","notifications.send"},
 "content_manager":{"dashboard.view","products.view","products.manage","content.manage","partners.view"},
 "developer":{"dashboard.view","products.view","integrations.manage","automation.view","automation.manage"},
 "client":set(),
}

def hash_password(password): return pwd.hash(password)
def verify_password(password, hashed): return pwd.verify(password, hashed)
def create_token(user):
    payload={"sub":str(user.id),"role":user.role,"ver":int(user.token_version or 0),"exp":datetime.now(timezone.utc)+timedelta(hours=12)}
    return jwt.encode(payload,SECRET_KEY,algorithm=ALGORITHM)
def create_mfa_challenge(user):
    payload={"sub":str(user.id),"purpose":"mfa","ver":int(user.token_version or 0),"exp":datetime.now(timezone.utc)+timedelta(minutes=5)}
    return jwt.encode(payload,SECRET_KEY,algorithm=ALGORITHM)
def decode_token(token): return jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
def current_user(request:Request, token:str|None=Depends(oauth2), db:Session=Depends(get_db)):
    token = token or request.cookies.get("nx_session")
    error=HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid or expired session",headers={"WWW-Authenticate":"Bearer"})
    try:
        payload=decode_token(token)
        if payload.get("purpose")=="mfa": raise ValueError("MFA challenge is not a session")
        uid=int(payload.get("sub")); version=int(payload.get("ver",0))
    except Exception: raise error
    user=db.query(User).filter(User.id==uid,User.active==True).first()
    if not user or int(user.token_version or 0)!=version: raise error
    enrollment_paths={"/api/auth/me","/api/auth/mfa/setup","/api/auth/mfa/confirm","/api/auth/logout","/api/auth/sessions/revoke-all"}
    if user.role!="client" and os.getenv("MFA_REQUIRED_FOR_STAFF", "true").lower()=="true" and not user.mfa_enabled and request.url.path not in enrollment_paths:
        raise HTTPException(403,"Staff MFA enrollment is required before using platform routes.")
    return user

def admin_user(user:User=Depends(current_user)):
    if user.role!="admin": raise HTTPException(403,"Administrator access required")
    if os.getenv("MFA_REQUIRED_FOR_STAFF", "true").lower()=="true" and not user.mfa_enabled:
        raise HTTPException(403,"Staff MFA enrollment is required. Use /api/auth/mfa/setup and /api/auth/mfa/confirm first.")
    return user

def staff_access(request:Request, user:User=Depends(current_user)):
    if user.role not in ROLE_PERMISSIONS: raise HTTPException(403,"Staff access required")
    if os.getenv("MFA_REQUIRED_FOR_STAFF", "true").lower()=="true" and not user.mfa_enabled:
        raise HTTPException(403,"Staff MFA enrollment is required. Use /api/auth/mfa/setup and /api/auth/mfa/confirm first.")
    if user.role=="admin": return user
    path=request.url.path; method=request.method
    rules=[
      ("/api/admin/overview","dashboard.view"),("/api/admin/leads","leads.manage" if method!="GET" else "leads.view"),
      ("/api/admin/customers","customers.manage" if method!="GET" else "customers.view"),
      ("/api/admin/projects","projects.manage" if method!="GET" else "projects.view"),
      ("/api/admin/invoices","finance.manage" if method!="GET" else "finance.view"),("/api/admin/payments","finance.view"),
      ("/api/admin/tickets","support.manage" if method!="GET" else "support.view"),
      ("/api/admin/products","products.manage" if method!="GET" else "products.view"),
      ("/api/admin/articles","content.manage"),("/api/admin/quotes","quotes.manage" if method!="GET" else "quotes.view"),
      ("/api/admin/audit-logs","audit.view"),("/api/admin/applications","careers.view"),
      ("/api/admin/integrations","integrations.manage"),("/api/admin/automations","automation.manage" if method!="GET" else "automation.view"),
      ("/api/admin/partners","partners.manage" if method!="GET" else "partners.view"),
      ("/api/admin/licenses","licenses.manage" if method!="GET" else "licenses.view"),
      ("/api/admin/notifications","notifications.send"),
    ]
    required=next((perm for prefix,perm in rules if path.startswith(prefix)),None)
    if not required or required not in ROLE_PERMISSIONS[user.role]: raise HTTPException(403,"Your staff role does not have permission for this action")
    return user
