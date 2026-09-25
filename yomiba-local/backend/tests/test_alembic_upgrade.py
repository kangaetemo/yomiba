"""init_db() runs the Alembic migration chain.

Covers the three deployment shapes:
* a brand-new empty database gets the full schema (stamped at head);
* an un-stamped legacy database (created by an old ``create_all`` release,
  e.g. missing ``series.original_title``) migrates instead of crashing;
* a database already at head is left untouched (idempotent no-op).

The Alembic environment reads the URL from the application settings, so the
tests point ``app.config.get_settings`` at a scratch file — the real
``yomiba.db`` is never touched.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable


@pytest.fixture()
def alembic_url(tmp_path, monkeypatch):
    """Scratch database URL wired into the (future) alembic env.py import."""
    import app.config as config_mod

    scratch = tmp_path / "alembic_test.db"
    real = config_mod.get_settings()

    def fake_get_settings():
        from dataclasses import replace

        return replace(real, database_url=f"sqlite:///{scratch}")

    monkeypatch.setattr(config_mod, "get_settings", fake_get_settings)
    return scratch


def test_init_db_builds_full_schema_on_fresh_database(alembic_url):
    from app import database

    database.init_db()

    conn = sqlite3.connect(alembic_url)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        from app import models  # noqa: F401
        expected = set(database.Base.metadata.tables.keys())
        assert expected - tables == set()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(series)")}
        assert "original_title" in cols
        assert conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "0003_publisher_alias"
    finally:
        conn.close()


def test_init_db_migrates_unstamped_legacy_database(alembic_url):
    from app import database

    # Legacy shape: the pre-original-title schema, no alembic_version row.
    engine = create_engine(f"sqlite:///{alembic_url}",
                           connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        for table in database.Base.metadata.sorted_tables:
            conn.execute(CreateTable(table))
    engine.dispose()

    legacy = sqlite3.connect(alembic_url)
    legacy.execute("ALTER TABLE series DROP COLUMN original_title")
    legacy.execute("DROP INDEX IF EXISTS ix_series_original_title")
    legacy.commit()
    legacy.close()

    database.init_db()

    conn = sqlite3.connect(alembic_url)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(series)")}
        assert "original_title" in cols
        assert conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "0003_publisher_alias"
    finally:
        conn.close()


def test_init_db_is_noop_when_already_at_head(alembic_url):
    from app import database

    database.init_db()  # first run: builds + stamps
    database.init_db()  # second run: must be a clean no-op

    conn = sqlite3.connect(alembic_url)
    try:
        assert conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall() == [("0003_publisher_alias",)]
    finally:
        conn.close()
