"""Alembic environment for Yomiba.

The database URL always comes from the application settings (the same
source the running app uses via ``Settings.database_url``), never from
``alembic.ini`` — so ``alembic upgrade head`` and the app can never point
at different databases.

Autogenerate is supported: ``target_metadata`` is the ORM metadata, and
SQLite runs migrations in batch mode (required for ALTER operations on
that backend).
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (register all tables on the metadata)
from app.config import get_settings, validate_database_settings
from app.database import Base

config = context.config


target_metadata = Base.metadata


def _database_url() -> str:
    settings = get_settings()
    validate_database_settings(settings)
    return settings.database_url


def _connect_args(url: str) -> dict:
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with a live connection)."""
    url = _database_url()
    connectable = create_engine(url, poolclass=pool.NullPool,
                                connect_args=_connect_args(url))
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=url.startswith("sqlite"),
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
