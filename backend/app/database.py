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

from sqlalchemy import create_engine, event
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
    built = create_engine(url, **kwargs)
    if built.url.get_backend_name() == "sqlite":
        @event.listens_for(built, "connect")
        def _sqlite_connection_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=30000")
            finally:
                cursor.close()
    return built


def enable_sqlite_wal(target: Engine) -> None:
    """Enable persistent WAL on file SQLite before workers or schedulers start.

    Keep synchronous=FULL for durability; the online backup API handles WAL.
    In-memory test databases do not support WAL and are left alone.
    """
    if target.url.get_backend_name() != "sqlite" or target.url.database in (None, ":memory:"):
        return
    with target.connect() as connection:
        mode = connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar()
        if str(mode).lower() != "wal":
            raise RuntimeError(f"SQLite WAL could not be enabled: {mode}")
        logger.info("SQLite WAL enabled")


def _initial_url() -> str:
    return get_settings().database_url


# Module-level engine / session factory used by the app by default.
# Tests replace these via :func:`set_session_factory` or by overriding the
# FastAPI dependency.
engine: Engine = build_engine(_initial_url())
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def backup_before_migration(url: str, head: str) -> Path | None:
    """Online-backup a file SQLite DB before Alembic changes its schema.

    Migrations are forward-only (0005 refuses to downgrade), so starting the
    app against an older database — e.g. a developer running uvicorn next to
    the real ``backend/yomiba.db`` — must never be the only copy. Returns the
    backup path, or None when nothing needs migrating (already at head, new
    or empty file, non-SQLite). Raises if the backup cannot be verified, so
    the migration does not run unprotected.
    """
    import sqlite3
    from datetime import datetime, timezone

    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        return None
    source = Path(parsed.database).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        return None
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables:
            return None
        current = None
        if "alembic_version" in tables:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            current = row[0] if row else None
    if current == head:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = source.with_name(f"{source.name}.pre-migration-{current or 'unversioned'}-{stamp}.bak")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target.as_uri() + "?mode=ro", uri=True) as check:
        if check.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise RuntimeError(f"pre-migration backup failed quick_check: {target}")
    logger.warning("pre-migration backup written: %s (from revision %s to %s)", target, current, head)
    return target


def init_db() -> None:
    """Apply all pending schema migrations (Alembic) to head.

    The baseline migration is idempotent (``CREATE TABLE IF NOT EXISTS``),
    so an un-stamped legacy database created by an older ``create_all``-based
    release migrates cleanly on its first startup instead of crashing.
    A file SQLite database that is not yet at head is first copied with the
    online backup API (disable only deliberately via
    ``AUTO_MIGRATION_BACKUP=0``).
    """
    import os

    from . import models  # noqa: F401  (ensure models are registered)
    from .readiness import expected_revision

    if os.getenv("AUTO_MIGRATION_BACKUP", "1").strip().lower() not in {"0", "false", "no", "off"}:
        # Resolve the URL exactly like alembic/env.py does (config module
        # attribute at call time), so the backup always targets the database
        # Alembic is about to migrate — never a different default file.
        from . import config as _config

        backup_before_migration(_config.get_settings().database_url, expected_revision())

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
