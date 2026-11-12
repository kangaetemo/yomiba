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
        ).fetchone()[0] == "0037_apostrophe_keys"
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
        ).fetchone()[0] == "0037_apostrophe_keys"
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
        ).fetchall() == [("0037_apostrophe_keys",)]
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
    with pytest.raises(RuntimeError, match="ISBN protection"):
        command.downgrade(config, "0004_catalog_exclusion")
    with sqlite3.connect(alembic_url) as conn:
        # 0023 refuses before any downgrade; neither evidence nor user data are removed.
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0037_apostrophe_keys",)
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


def test_retired_store_and_its_rows_are_removed(alembic_url):
    """0034: the retired store's listings, history, clicks, import errors and
    covers go; other stores and the volumes themselves stay."""
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from sqlalchemy.orm import Session
    from app import database
    from app.models import AnalyticsEvent, ImportRecord, PriceHistory, Store, StoreListing
    from tests.test_import_service import seed_catalog_series

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(config, "0033_cover_error")
    # The ORM below writes every current volume column; give the 0033 table
    # the ones later migrations add for the seeding only.
    later = ("last_in_stock_at", "stock_checked_at")
    with sqlite3.connect(alembic_url) as conn:
        for column in later:
            conn.execute(f"ALTER TABLE volumes ADD COLUMN {column} DATETIME")
    engine = database.build_engine(f"sqlite:///{alembic_url}")
    gone_key, shared_key = "v/1-aaaaaaaaaaaa.webp", "v/2-bbbbbbbbbbbb.webp"
    covers = alembic_url.parent / "covers" / "v"
    covers.mkdir(parents=True)
    for key in (gone_key, shared_key):
        (alembic_url.parent / "covers" / key).write_bytes(b"x")
    try:
        with Session(engine) as session:
            old, bkm = Store(code="amazon", name="Amazon"), Store(code="bkm", name="BKM Kitap")
            session.add_all([old, bkm])
            series = seed_catalog_series(session, "Eski Magaza", "Eski Yayin", volumes=(1, 2, 3))
            v1, v2, v3 = sorted(series.volumes, key=lambda v: v.volume_number)
            v1.cover_key, v1.cover_source = gone_key, "store:amazon"
            v2.cover_key, v2.cover_source, v2.cover_url = shared_key, "store:amazon", "https://m.media-amazon.com/x.jpg"
            v3.cover_key, v3.cover_source = shared_key, "catalog"
            session.flush()
            for store, price in ((old, 9000), (bkm, 15000)):
                listing = StoreListing(volume_id=v1.id, store_id=store.id, product_url=f"https://x/{store.code}", price=price)
                session.add(listing)
                session.flush()
                session.add(PriceHistory(listing_id=listing.id, price=price))
            session.add(AnalyticsEvent(day="2026-10-01", hour=1, kind="outbound", visitor="v", session="s",
                                       store_id=old.id, target_url="https://www.amazon.com.tr/dp/X"))
            session.add(ImportRecord(normalized_query="eski magaza", status="partial",
                                     error="amazon: blocked | dr: 403", reasons={"amazon": {"x": 1}, "bkm": {"y": 2}}))
            session.commit()
        engine.dispose()
        with sqlite3.connect(alembic_url) as conn:
            for column in later:
                conn.execute(f"ALTER TABLE volumes DROP COLUMN {column}")

        command.upgrade(config, "head")

        with Session(engine) as session:
            assert session.query(Store.code).all() == [("bkm",)]
            assert [l.price for l in session.query(StoreListing)] == [15000]
            assert [p.price for p in session.query(PriceHistory)] == [15000]
            assert session.query(AnalyticsEvent).count() == 0
            record = session.query(ImportRecord).one()
            assert (record.error, record.reasons) == ("dr: 403", {"bkm": {"y": 2}})
            vols = {v.volume_number: v for v in series_volumes(session)}
            assert (vols[1].cover_key, vols[1].cover_source) == (None, None)
            assert (vols[2].cover_key, vols[2].cover_url) == (None, None)
            assert vols[3].cover_key == shared_key
            # 0035: the last in-stock price point is the last time it was in stock.
            assert vols[1].last_in_stock_at is not None
            assert (vols[2].last_in_stock_at, vols[1].stock_checked_at) == (None, None)
        assert not (alembic_url.parent / "covers" / gone_key).exists()
        assert (alembic_url.parent / "covers" / shared_key).exists()  # v3 still uses it
    finally:
        engine.dispose()


def series_volumes(session):
    from app.models import Volume

    return session.query(Volume).all()


def test_0037_recomputes_apostrophe_keys_and_keeps_slug(alembic_url):
    from app import database

    database.init_db()
    conn = sqlite3.connect(alembic_url)
    try:
        conn.execute("INSERT INTO publishers (id, name, normalized_name) VALUES (1, 'Tokyo Manga', 'tokyo manga')")
        conn.execute("INSERT INTO series (id, publisher_id, title, slug, normalized_title) VALUES "
                     "(1, 1, 'İlahi Bahçe''nin Avcısı', 'ilahi-bahce-nin-avcisi', 'ilahi bahce nin avcisi'),"
                     "(2, 1, 'Kedi''nin Günü', 'kedi-nin-gunu', 'kedi nin gunu'),"
                     "(3, 1, 'Kedinin Günü', 'kedinin-gunu', 'kedinin gunu')")
        conn.execute("UPDATE alembic_version SET version_num = '0036_special_sets'")
        conn.commit()
    finally:
        conn.close()

    database.init_db()
    conn = sqlite3.connect(alembic_url)
    try:
        rows = dict((r[0], r[1:]) for r in conn.execute("SELECT id, normalized_title, slug FROM series"))
        assert rows[1] == ("ilahi bahcenin avcisi", "ilahi-bahce-nin-avcisi")
        # The new key is taken by another edition: the old key stays.
        assert rows[2] == ("kedi nin gunu", "kedi-nin-gunu")
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0037_apostrophe_keys",)
    finally:
        conn.close()
