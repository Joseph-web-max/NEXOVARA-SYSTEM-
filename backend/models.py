from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__="users"
    id=Column(Integer, primary_key=True)
    name=Column(String(160), nullable=False)
    email=Column(String(255), unique=True, index=True, nullable=False)
    password_hash=Column(String(255), nullable=False)
    role=Column(String(40), default="client", nullable=False)
    token_version=Column(Integer, default=0, nullable=False)
    mfa_enabled=Column(Boolean, default=False, nullable=False)
    mfa_secret=Column(String(512), default="")
    mfa_pending_secret=Column(String(512), default="")
    company=Column(String(180), default="")
    active=Column(Boolean, default=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now())

class Lead(Base):
    __tablename__="leads"
    id=Column(Integer, primary_key=True)
    name=Column(String(160), nullable=False)
    email=Column(String(255), nullable=False)
    company=Column(String(180), default="")
    service=Column(String(120), default="")
    budget=Column(String(80), default="")
    message=Column(Text, nullable=False)
    status=Column(String(30), default="new")
    created_at=Column(DateTime(timezone=True), server_default=func.now())

class Product(Base):
    __tablename__="products"
    id=Column(Integer, primary_key=True)
    name=Column(String(160), unique=True, nullable=False)
    slug=Column(String(160), unique=True, nullable=False)
    category=Column(String(100), default="Software")
    description=Column(Text, default="")
    features=Column(Text, default="")
    price_label=Column(String(100), default="Request a quote")
    url=Column(String(500), default="")
    tagline=Column(String(240), default="")
    platforms=Column(Text, default="")
    version=Column(String(80), default="")
    github_url=Column(String(500), default="")
    docs_url=Column(String(500), default="")
    demo_url=Column(String(500), default="")
    image_url=Column(String(1000), default="")
    is_featured=Column(Boolean, default=False, nullable=False)
    sort_order=Column(Integer, default=0, nullable=False)
    archived_at=Column(DateTime(timezone=True), nullable=True)
    status=Column(String(30), default="draft")

class Project(Base):
    __tablename__="projects"
    id=Column(Integer, primary_key=True)
    client_id=Column(Integer, ForeignKey("users.id"), nullable=False)
    title=Column(String(180), nullable=False)
    description=Column(Text, default="")
    status=Column(String(40), default="Planning")
    progress=Column(Integer, default=0)
    due_date=Column(String(40), default="")

class Invoice(Base):
    __tablename__="invoices"
    id=Column(Integer, primary_key=True)
    client_id=Column(Integer, ForeignKey("users.id"), nullable=False)
    number=Column(String(50), unique=True, nullable=False)
    description=Column(String(255), default="")
    amount=Column(Float, nullable=False)
    currency=Column(String(8), default="KES")
    status=Column(String(30), default="unpaid")
    due_date=Column(String(40), default="")

class Ticket(Base):
    __tablename__="tickets"
    id=Column(Integer, primary_key=True)
    client_id=Column(Integer, ForeignKey("users.id"), nullable=False)
    subject=Column(String(200), nullable=False)
    message=Column(Text, nullable=False)
    status=Column(String(30), default="open")
    response=Column(Text, default="")
    created_at=Column(DateTime(timezone=True), server_default=func.now())

class Article(Base):
    __tablename__="articles"
    id=Column(Integer, primary_key=True)
    title=Column(String(200), nullable=False)
    slug=Column(String(200), unique=True, nullable=False)
    category=Column(String(100), default="Insights")
    excerpt=Column(Text, default="")
    body=Column(Text, default="")
    published=Column(Boolean, default=True)

class JobApplication(Base):
    __tablename__="job_applications"
    id=Column(Integer, primary_key=True)
    name=Column(String(160), nullable=False)
    email=Column(String(255), nullable=False)
    role=Column(String(160), nullable=False)
    portfolio=Column(String(500), default="")
    message=Column(Text, default="")

class Subscription(Base):
    __tablename__="subscriptions"
    id=Column(Integer, primary_key=True)
    client_id=Column(Integer, ForeignKey("users.id"), nullable=False)
    plan=Column(String(100), nullable=False)
    status=Column(String(30), default="pending")
    amount=Column(Float, default=0)
    currency=Column(String(8), default="KES")


class Quote(Base):
    __tablename__="quotes"
    id=Column(Integer, primary_key=True)
    name=Column(String(160), nullable=False)
    email=Column(String(255), nullable=False, index=True)
    company=Column(String(180), default="")
    service=Column(String(160), default="")
    product_slug=Column(String(160), default="")
    budget=Column(String(80), default="")
    timeline=Column(String(80), default="")
    details=Column(Text, default="")
    status=Column(String(30), default="new", nullable=False)
    admin_notes=Column(Text, default="")
    created_at=Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__="audit_logs"
    id=Column(Integer, primary_key=True)
    actor_id=Column(Integer, nullable=True, index=True)
    actor_email=Column(String(255), default="")
    action=Column(String(100), nullable=False, index=True)
    entity_type=Column(String(80), nullable=False)
    entity_id=Column(String(80), default="")
    details=Column(Text, default="")
    created_at=Column(DateTime(timezone=True), server_default=func.now(), index=True)


class AutomationWorkflow(Base):
    __tablename__="automation_workflows"
    id=Column(Integer, primary_key=True)
    name=Column(String(160), nullable=False)
    trigger_event=Column(String(60), nullable=False, index=True)
    action_type=Column(String(60), default="email_notification", nullable=False)
    enabled=Column(Boolean, default=False, nullable=False)
    created_by=Column(Integer, nullable=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    updated_at=Column(DateTime(timezone=True), onupdate=func.now())

class AutomationRun(Base):
    __tablename__="automation_runs"
    id=Column(Integer, primary_key=True)
    workflow_id=Column(Integer, ForeignKey("automation_workflows.id"), nullable=False, index=True)
    trigger_event=Column(String(60), nullable=False)
    entity_type=Column(String(60), default="")
    entity_id=Column(String(80), default="")
    status=Column(String(30), nullable=False)
    detail=Column(Text, default="")
    created_at=Column(DateTime(timezone=True), server_default=func.now(), index=True)


class License(Base):
    __tablename__="licenses"
    id=Column(Integer, primary_key=True)
    client_id=Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id=Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    license_key=Column(String(96), unique=True, nullable=False, index=True)
    status=Column(String(30), default="pending", nullable=False)
    starts_at=Column(DateTime(timezone=True), nullable=True)
    expires_at=Column(DateTime(timezone=True), nullable=True)
    seats=Column(Integer, default=1, nullable=False)
    notes=Column(Text, default="")
    created_at=Column(DateTime(timezone=True), server_default=func.now())

class Notification(Base):
    __tablename__="notifications"
    id=Column(Integer, primary_key=True)
    user_id=Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title=Column(String(180), nullable=False)
    body=Column(Text, default="")
    kind=Column(String(40), default="general")
    read_at=Column(DateTime(timezone=True), nullable=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now(), index=True)

class PartnerApplication(Base):
    __tablename__="partner_applications"
    id=Column(Integer, primary_key=True)
    name=Column(String(160), nullable=False)
    email=Column(String(255), nullable=False, index=True)
    organization=Column(String(180), default="")
    website=Column(String(500), default="")
    partnership_type=Column(String(100), default="")
    message=Column(Text, default="")
    status=Column(String(30), default="new", nullable=False)
    admin_notes=Column(Text, default="")
    created_at=Column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    __tablename__="password_reset_tokens"
    id=Column(Integer, primary_key=True)
    user_id=Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash=Column(String(128), unique=True, nullable=False, index=True)
    expires_at=Column(DateTime(timezone=True), nullable=False)
    used_at=Column(DateTime(timezone=True), nullable=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now())

class Payment(Base):
    __tablename__="payments"
    id=Column(Integer, primary_key=True)
    invoice_id=Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    client_id=Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider=Column(String(24), nullable=False)
    provider_reference=Column(String(180), unique=True, nullable=True, index=True)
    merchant_request_id=Column(String(180), nullable=True, index=True)
    payer_phone=Column(String(24), default="")
    merchant_reference=Column(String(120), nullable=False, index=True)
    amount=Column(Float, nullable=False)
    currency=Column(String(8), nullable=False)
    status=Column(String(24), default="pending", nullable=False, index=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
    paid_at=Column(DateTime(timezone=True), nullable=True)

class PaymentEvent(Base):
    __tablename__="payment_events"
    id=Column(Integer, primary_key=True)
    provider=Column(String(24), nullable=False)
    event_id=Column(String(200), nullable=False, unique=True, index=True)
    received_at=Column(DateTime(timezone=True), server_default=func.now())

class StoredFile(Base):
    __tablename__="stored_files"
    id=Column(Integer, primary_key=True)
    owner_id=Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    storage_path=Column(String(500), unique=True, nullable=False)
    original_filename=Column(String(255), nullable=False)
    content_type=Column(String(120), nullable=False)
    size_bytes=Column(Integer, nullable=False)
    sha256=Column(String(64), nullable=False)
    created_at=Column(DateTime(timezone=True), server_default=func.now())
