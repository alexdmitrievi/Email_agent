"""Alembic env.py — sync migration runner (works with both PG and SQLite)."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Ensure env vars are set for app.config import
os.environ.setdefault("OPENAI_API_KEY", "placeholder")
os.environ.setdefault("GOOGLE_DELEGATED_EMAIL", "placeholder@example.com")
os.environ.setdefault("GOOGLE_PUBSUB_TOPIC", "projects/p/topics/t")
os.environ.setdefault("GOOGLE_SHEET_ID", "placeholder")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:placeholder")
os.environ.setdefault("TELEGRAM_MANAGER_CHAT_ID", "0")

from app.config import settings
from app.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Convert async URL to sync for Alembic
sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")
config.set_main_option("sqlalchemy.url", sync_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
