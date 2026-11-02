"""SQLAlchemy database configuration for local SQLite or Supabase PostgreSQL.

Render is IPv4-only in common deployments, so Supabase's shared pooler is the
safe default. Use the exact URL copied from Supabase Dashboard > Connect.
"""
import os
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import NullPool


def normalize_database_url(raw: str) -> tuple[str, bool]:
    raw = (raw or "sqlite:///./nexovara.db").strip()
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg://" + raw[len("postgres://"):]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+psycopg://" + raw[len("postgresql://"):]
    elif raw.startswith("postgresql+psycopg://"):
        pass
    elif raw.startswith("sqlite"):
        return raw, False
    else:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL or SQLite connection URL.")

    parsed = urlparse(raw)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    normalized = urlunparse(parsed._replace(query=urlencode(query)))
    # Supabase shared transaction pooler (6543) does not support prepared statements.
    transaction_pooler = parsed.port == 6543
    return normalized, transaction_pooler


DATABASE_URL, _transaction_pooler = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./nexovara.db"))
if (os.getenv("RENDER") or os.getenv("ENVIRONMENT", "").lower()=="production") and DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("Render production must use Supabase PostgreSQL. Set DATABASE_URL in Render Environment.")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
if not DATABASE_URL.startswith("sqlite") and _transaction_pooler:
    connect_args["prepare_threshold"] = 0
    # Supabase transaction pooler is shared; avoid holding client-side idle sessions.
    engine = create_engine(DATABASE_URL, connect_args=connect_args, poolclass=NullPool, pool_pre_ping=True)
else:
    engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True,
                           pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
                           max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "2")))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
