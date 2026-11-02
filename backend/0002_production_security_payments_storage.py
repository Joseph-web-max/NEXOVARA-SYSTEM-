"""Add production security, payment and private-file metadata.

Revision ID: 0002_production_services
Revises: 0001_global_platform_services
"""
from alembic import op
from sqlalchemy import inspect, text
from backend.database import Base
from backend import models  # register all tables
revision = "0002_production_services"
down_revision = "0001_global_platform_services"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "users" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("users")}
        additions = {
            "token_version": "INTEGER NOT NULL DEFAULT 0",
            "mfa_enabled": "BOOLEAN NOT NULL DEFAULT FALSE",
            "mfa_secret": "VARCHAR(512) DEFAULT ''",
            "mfa_pending_secret": "VARCHAR(512) DEFAULT ''",
        }
        for name, ddl in additions.items():
            if name not in cols:
                op.add_column("users", __import__("sqlalchemy").Column(name, __import__("sqlalchemy").Boolean if name == "mfa_enabled" else __import__("sqlalchemy").Integer if name == "token_version" else __import__("sqlalchemy").String(512), nullable=False, server_default=text("false") if name == "mfa_enabled" else text("0") if name == "token_version" else text("''")))
        # Invalidate pre-hardening JWTs which did not carry a token-version claim.
        op.execute("UPDATE users SET token_version = token_version + 1")
    if "products" in inspect(bind).get_table_names():
        product_cols = {c["name"] for c in inspect(bind).get_columns("products")}
        product_additions = {
            "tagline": "VARCHAR(240) DEFAULT ''", "platforms": "TEXT DEFAULT ''",
            "version": "VARCHAR(80) DEFAULT ''", "github_url": "VARCHAR(500) DEFAULT ''",
            "docs_url": "VARCHAR(500) DEFAULT ''", "demo_url": "VARCHAR(500) DEFAULT ''",
            "image_url": "VARCHAR(1000) DEFAULT ''", "is_featured": "BOOLEAN NOT NULL DEFAULT FALSE",
            "sort_order": "INTEGER NOT NULL DEFAULT 0", "archived_at": "TIMESTAMP NULL",
        }
        for name, ddl in product_additions.items():
            if name not in product_cols:
                op.execute(f"ALTER TABLE products ADD COLUMN {name} {ddl}")
    if "payments" in inspect(bind).get_table_names():
        payment_cols = {c["name"] for c in inspect(bind).get_columns("payments")}
        for name, ddl in {"merchant_request_id": "VARCHAR(180) NULL", "payer_phone": "VARCHAR(24) DEFAULT ''"}.items():
            if name not in payment_cols:
                op.execute(f"ALTER TABLE payments ADD COLUMN {name} {ddl}")
    # create_all adds newly introduced tables but does not alter existing tables.
    Base.metadata.create_all(bind=bind)

def downgrade():
    # Keep customer payment/file records and security state; downgrade is intentionally non-destructive.
    pass
