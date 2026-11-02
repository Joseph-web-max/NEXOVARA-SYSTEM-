"""Non-destructive metadata baseline for the platform's current schema.

Revision ID: 0001_global_platform_services
Revises:
"""
from alembic import op
from backend.database import Base
from backend import models  # register every current table on Base.metadata
revision="0001_global_platform_services"
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    # Idempotently creates missing tables. Existing records/tables are preserved.
    # Historical product metadata columns are added by ensure_product_columns().
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    # Deliberately non-destructive: the first migration establishes a baseline
    # over pre-existing MVP databases and must not drop customer/business data.
    pass
