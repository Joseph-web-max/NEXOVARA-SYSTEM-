from logging.config import fileConfig
import os
from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv
load_dotenv()
from backend.database import Base
from backend import models  # register all model tables
config=context.config
if config.config_file_name: fileConfig(config.config_file_name)
migration_url=os.getenv("MIGRATION_DATABASE_URL", "").strip()
app_url=os.getenv("DATABASE_URL", "").strip()
if os.getenv("ENVIRONMENT", "").lower()=="production" and not migration_url and ":6543" in app_url:
    raise RuntimeError("Set MIGRATION_DATABASE_URL to the Supabase session pooler URL (port 5432) for Alembic migrations.")
database_url=migration_url or app_url
if database_url:
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
    if "sslmode=" not in database_url and database_url.startswith("postgresql"):
        database_url += "&sslmode=require" if "?" in database_url else "?sslmode=require"
if database_url: config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata=Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"),target_metadata=target_metadata,literal_binds=True,dialect_opts={"paramstyle":"named"},compare_type=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    connect_args={"prepare_threshold":0} if ":6543" in config.get_main_option("sqlalchemy.url") else {}
    connectable=engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool,connect_args=connect_args)
    with connectable.connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction(): context.run_migrations()
if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
