"""SQLAlchemy engine, session factory and declarative base.

The engine is built from ``Settings.database_url`` so the storage backend is
fully configurable. Nothing in the business layer imports a concrete engine
directly; they receive a ``Session`` via dependency injection, which keeps the
application portable between SQLite and PostgreSQL.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

logger = logging.getLogger("yomiba.database")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def build_engine(url: str) -> Engine:
    """Create a SQLAlchemy engine for ``url``.

    SQLite needs ``check_same_thread=False`` because FastAPI may use the
    connection from a worker thread different from the one that opened it.
    """
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Several background import jobs commit concurrently (bounded by
        # import_max_concurrent_jobs); give SQLite a generous busy timeout
        # instead of failing the first write that meets another writer.
        connect_args["timeout"] = 30
    kwargs: dict = {"connect_args": connect_args, "future": True}
    if url.startswith("sqlite://"):
        kwargs["pool_pre_ping"] = True
        # Enough headroom for import_max_concurrent_jobs concurrent import
        # jobs (each holds a session for its whole scrape) plus request and
        # scheduler threads, with room for pre-ping. The default QueuePool
        # (5+10) was exhausted during a 461-job warmup (2026-09-14); a file
        # SQLite connection is cheap, so prefer headroom. (:memory: keeps
        # its default pool class — tests.)
        if url.startswith("sqlite:///") and ":memory:" not in url:
            kwargs["pool_size"] = 10
            kwargs["max_overflow"] = 20
    return create_engine(url, **kwargs)


def _initial_url() -> str:
    return get_settings().database_url


# Module-level engine / session factory used by the app by default.
# Tests replace these via :func:`set_session_factory` or by overriding the
# FastAPI dependency.
engine: Engine = build_engine(_initial_url())
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def init_db() -> None:
    """Apply all pending schema migrations (Alembic) to head.

    The baseline migration is idempotent (``CREATE TABLE IF NOT EXISTS``),
    so an un-stamped legacy database created by an older ``create_all``-based
    release migrates cleanly on its first startup instead of crashing.
    """
    from . import models  # noqa: F401  (ensure models are registered)

    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent
    config = Config(str(backend_dir / "alembic.ini"))
    # Resolve the script location from this file, never from the CWD.
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(config, "head")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
