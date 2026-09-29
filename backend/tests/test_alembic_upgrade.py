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
    from app.readiness import check_database_ready

    database.init_db()
    runtime_engine = database.build_engine(f"sqlite:///{alembic_url}")
    try:
        check_database_ready(runtime_engine)
    finally:
        runtime_engine.dispose()

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
        ).fetchone()[0] == "0008_volume_covers_range"
    finally:
        conn.close()


def test_init_db_migrates_unstamped_legacy_database(alembic_url):
    from app import database

    # A genuine pre-auth Alembic schema, rather than today's ORM metadata.
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(config, "0004_catalog_exclusion")

    database.init_db()

    conn = sqlite3.connect(alembic_url)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(series)")}
        assert "original_title" in cols
        assert conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "0008_volume_covers_range"
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
        ).fetchall() == [("0008_volume_covers_range",)]
    finally:
        conn.close()


def test_preauth_personal_and_catalog_data_survive_upgrade(alembic_url):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from app import database

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(config, "0004_catalog_exclusion")
    with sqlite3.connect(alembic_url) as conn:
        conn.execute("INSERT INTO publishers (id,name,normalized_name) VALUES (1,'Legacy Pub','legacy pub')")
        conn.execute("INSERT INTO series (id,publisher_id,title,slug,normalized_title) VALUES (1,1,'Legacy Manga','legacy-manga','legacy manga')")
        conn.execute("INSERT INTO catalog_series (series_id,mangakol_slug) VALUES (1,'legacy-manga')")
        conn.execute("INSERT INTO volumes (id,series_id,volume_number,collection_status) VALUES (1,1,1,'owned')")
        conn.execute("INSERT INTO wishlist_items (id,user_id,volume_id,created_at) VALUES (1,1,1,'2026-01-01')")
        conn.execute("INSERT INTO price_alerts (id,user_id,volume_id,threshold_price,is_active,created_at,updated_at) VALUES (1,1,1,100,1,'2026-01-01','2026-01-01')")
    database.init_db()
    with sqlite3.connect(alembic_url) as conn:
        assert conn.execute("SELECT title FROM series").fetchall() == [("Legacy Manga",)]
        assert conn.execute("SELECT mangakol_slug FROM catalog_series").fetchall() == [("legacy-manga",)]
        assert conn.execute("SELECT status FROM user_volume_collections WHERE user_id=1 AND volume_id=1").fetchone() == ("owned",)
        assert conn.execute("SELECT user_id,volume_id FROM wishlist_items").fetchall() == [(1, 1)]
        assert conn.execute("SELECT user_id,volume_id,threshold_price FROM price_alerts").fetchall() == [(1, 1, 100)]
        assert conn.execute("SELECT is_active,password_hash,role FROM users WHERE id=1").fetchone() == (0, None, "USER")
        assert "collection_status" not in {r[1] for r in conn.execute("PRAGMA table_info(volumes)")}
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in ("wishlist_items", "price_alerts", "user_volume_collections", "user_sessions"):
            assert "users" in {r[2] for r in conn.execute(f"PRAGMA foreign_key_list({table})")}


def test_auth_downgrade_refuses_to_discard_user_data(alembic_url):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from app import database

    database.init_db()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    with pytest.raises(RuntimeError, match="discard multi-user ownership"):
        command.downgrade(config, "0004_catalog_exclusion")
    with sqlite3.connect(alembic_url) as conn:
        # 0006 (data-only alias correction) steps down cleanly; the account
        # migration 0005 refuses, so the user-owned schema stays in place.
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0005_user_accounts",)
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'users'").fetchone() == (1,)


def test_readiness_rejects_broken_catalog_reference(alembic_url):
    from app import database
    from app.readiness import check_database_ready

    database.init_db()
    with sqlite3.connect(alembic_url) as connection:
        connection.execute("INSERT INTO catalog_series (series_id,mangakol_slug) VALUES (999,'broken')")
    runtime_engine = database.build_engine(f"sqlite:///{alembic_url}")
    try:
        with pytest.raises(RuntimeError, match="CatalogSeries"):
            check_database_ready(runtime_engine)
    finally:
        runtime_engine.dispose()
