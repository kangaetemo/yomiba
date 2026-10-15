"""P0 production-shaped safety tests; exclusively temporary databases/fake sources."""
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app import config as config_mod, database
from app.models import (PriceAlert, PriceHistory, Store, StoreListing, User,
                        UserVolumeCollection, Volume, WishlistItem)
from app.services.isbn_safety import GUARDS, MutationPaused, check_guards, install_guards
from app.services.safety_backup import fingerprint, inspect_file, rehearse_restore
from tests.test_import_service import make_result, seed_catalog_series, _fake_scrapers

ISBN = "9786256335424"


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    path = tmp_path / "staging.db"
    settings = replace(config_mod.get_settings(), database_url=f"sqlite:///{path}")
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(cfg, "0014_catalog_membership")
    engine = database.build_engine(settings.database_url)
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        user = User(email="synthetic@example.com", display_name="Synthetic admin", role="ADMIN", is_active=True)
        session.add(user); session.flush()
        series = seed_catalog_series(session, "Berserk", "Athica Yayınları", volumes=(1, 2))
        first, second = list(session.scalars(select(Volume).order_by(Volume.id)))
        first.isbn = ISBN
        first.catalog_present = second.catalog_present = True
        first.catalog_released = second.catalog_released = True
        store = Store(code="bkm", name="BKM")
        session.add(store); session.flush()
        listing = StoreListing(volume_id=first.id, store_id=store.id, product_url="https://example.com/one", price=12000)
        session.add(listing); session.flush()
        session.add_all([
            PriceHistory(listing_id=listing.id, price=12000),
            WishlistItem(user_id=user.id, volume_id=first.id),
            PriceAlert(user_id=user.id, volume_id=first.id, threshold_price=10000),
            UserVolumeCollection(user_id=user.id, volume_id=first.id, status="owned"),
        ])
        session.commit()
    before = inspect_file(path)
    database.init_db()
    assert inspect_file(path) == before
    yield path, engine
    engine.dispose()


def test_activation_backup_and_restore_preserve_every_protected_row(guarded):
    path, engine = guarded
    manifest = json.loads(path.with_name(path.name + ".isbn-safety.json").read_text())
    assert manifest["existing_guard_baseline"]
    assert manifest["protected_rows_unchanged"]
    assert manifest["before"] == manifest["after"] == manifest["restore"]["tables"]
    assert manifest["restore"]["verified"]
    backup = Path(manifest["backup"])
    assert backup.is_file()
    if os.name == "posix":
        assert backup.stat().st_mode & 0o077 == 0
    assert rehearse_restore(backup)["tables"] == inspect_file(path)["tables"]
    with engine.connect() as connection:
        check_guards(connection.connection.driver_connection)


@pytest.mark.parametrize("sql", [
    "UPDATE volumes SET isbn='9786258657531' WHERE id=2",
    "UPDATE volumes SET isbn=NULL WHERE id=1",
    "UPDATE volumes SET id=99 WHERE id=1",
    "UPDATE volumes SET volume_number=99 WHERE id=1",
    "UPDATE volumes SET series_id=99 WHERE id=1",
    "INSERT INTO volumes (series_id,volume_number,isbn) VALUES (1,3,'9786258657531')",
    "INSERT OR REPLACE INTO volumes (id,series_id,volume_number,isbn) VALUES (1,1,1,NULL)",
    "INSERT OR REPLACE INTO volumes (series_id,volume_number,isbn) VALUES (1,1,NULL)",
    "DELETE FROM volumes WHERE id=1",
    "DELETE FROM series WHERE id=1",
    "UPDATE series SET publisher_id=99 WHERE id=1",
    "INSERT OR REPLACE INTO series (id,publisher_id,title,normalized_title,slug) VALUES (1,1,'Other','other','other')",
    "DELETE FROM publishers WHERE id=1",
    "UPDATE publishers SET id=99 WHERE id=1",
    "INSERT OR REPLACE INTO publishers (id,name,normalized_name) VALUES (1,'Other','other')",
    "DELETE FROM store_listings WHERE id=1",
    "UPDATE store_listings SET volume_id=2 WHERE id=1",
    "INSERT OR REPLACE INTO store_listings (id,volume_id,store_id,product_url,in_stock,last_checked) VALUES (1,2,1,'https://example.com/other',1,'2026-10-14')",
    "DELETE FROM price_history WHERE id=1",
    "UPDATE price_history SET price=1 WHERE id=1",
    "INSERT OR REPLACE INTO price_history (id,listing_id,price,checked_at) VALUES (1,1,1,'2026-10-14')",
    "UPDATE wishlist_items SET volume_id=2 WHERE id=1",
    "UPDATE user_volume_collections SET volume_id=2 WHERE id=1",
    "UPDATE price_alerts SET volume_id=2 WHERE id=1",
    "INSERT OR REPLACE INTO wishlist_items (id,user_id,volume_id) VALUES (1,1,2)",
    "INSERT OR REPLACE INTO wishlist_items (user_id,volume_id) VALUES (1,1)",
    "INSERT OR REPLACE INTO user_volume_collections (id,user_id,volume_id,status) VALUES (1,1,2,'missing')",
    "INSERT OR REPLACE INTO price_alerts (id,user_id,volume_id,threshold_price) VALUES (1,1,2,1)",
    "UPDATE price_history SET product_url='https://example.com/wrong' WHERE id=1",
    "DELETE FROM stores WHERE id=1",
    "UPDATE stores SET id=99 WHERE id=1",
    "INSERT OR REPLACE INTO stores (id,code,name) VALUES (1,'other','Other')",
])
def test_raw_sql_cannot_bypass_with_fk_or_recursive_triggers_disabled(guarded, sql):
    path, _ = guarded
    before = inspect_file(path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("PRAGMA recursive_triggers=OFF")
        with pytest.raises(sqlite3.IntegrityError, match="isbn_p0_write_paused"):
            connection.execute(sql)
        connection.rollback()
    assert inspect_file(path) == before


def test_orm_and_bulk_updates_are_blocked_but_prices_discovery_and_personal_status_work(guarded):
    path, engine = guarded
    with Session(engine) as session:
        volume = session.get(Volume, 2)
        volume.isbn = "9786258657531"
        with pytest.raises(IntegrityError, match="isbn_p0_write_paused"):
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError, match="isbn_p0_write_paused"):
            session.execute(update(Volume).where(Volume.id == 1).values(isbn=None))
        session.rollback()
        assert session.get(Volume, 1).isbn == ISBN
        assert session.get(Volume, 2).isbn is None
        session.add(Volume(series_id=1, volume_number=3, catalog_present=True, catalog_released=False))
        listing = session.get(StoreListing, 1); listing.price = 11000; listing.in_stock = False
        session.add(PriceHistory(listing_id=1, price=11000, in_stock=False))
        session.get(UserVolumeCollection, 1).status = "missing"
        session.commit()
    assert inspect_file(path)["tables"]["price_history"]["rows"] == 2
    assert inspect_file(path)["tables"]["volumes"]["rows"] == 3


@pytest.mark.parametrize("released,present", [(True, True), (False, True), (False, False)])
def test_store_import_never_writes_an_isbn_even_before_listing_guard(guarded, released, present):
    from app.services.import_service import ImportService
    path, engine = guarded
    with Session(engine, autoflush=False) as session:
        target = session.get(Volume, 2)
        target.catalog_released, target.catalog_present = released, present
        session.commit()
        result = make_result("bkm", "Berserk 2", "150", isbn="9786258657531", publisher="Athica Yayınları")
        service = ImportService(session, scrapers=_fake_scrapers({"bkm": [result]}, failing=set()))
        service.run_import("Berserk")
        assert session.get(Volume, 2).isbn is None
        assert session.get(Volume, 1).isbn == ISBN


def test_scheduler_entry_cannot_restore_isbn_and_preserves_history(guarded, monkeypatch):
    from app.routes import catalog
    from app.scrapers.mangakol import CatalogManga, CatalogVolume, CatalogVolumeDetails
    from app.services.catalog_sync import CatalogSyncService
    from app.services import catalog_state
    from tests.test_catalog_isbn import _DetailsFake
    path, engine = guarded
    with engine.connect() as connection:
        before = list(connection.execute(select(Volume.id, Volume.isbn, Volume.series_id, Volume.volume_number)))
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    fake = _DetailsFake([CatalogManga(slug="cat-berserk", title="Berserk", local_publisher="Athica Yayınları", volumes=[
        CatalogVolume(1, None, url="https://example.com/catalog1"),
        CatalogVolume(2, None, url="https://example.com/catalog2"),
    ])], {"https://example.com/catalog1": CatalogVolumeDetails("9786258657531"),
          "https://example.com/catalog2": CatalogVolumeDetails("9786258657562")})
    monkeypatch.setattr(catalog, "SessionLocal", session_factory)
    monkeypatch.setattr(catalog, "CatalogSyncService", lambda s: CatalogSyncService(s, scraper=fake))
    monkeypatch.setattr(catalog, "_running", False)
    monkeypatch.setattr(catalog, "_last", None)
    monkeypatch.setattr(catalog_state, "state_path", lambda: path.with_name("sync-state.json"))

    class Runner:
        def acquire_import_lock(self, *_args, **_kwargs): return True
        def release_import_lock(self, *_args): pass

    assert catalog.try_start_sync(Runner()) == "started"
    assert catalog.wait_for_active_sync(10)
    assert catalog._last_summary()["status"] == "success"
    assert catalog._last_summary()["isbn_writes_paused"]
    with engine.connect() as connection:
        assert list(connection.execute(select(Volume.id, Volume.isbn, Volume.series_id, Volume.volume_number))) == before
    assert inspect_file(path)["tables"]["price_history"]["rows"] == 1


@pytest.mark.parametrize("module", ["apply_task2_merges", "apply_task2_followup", "apply_task3_cleanup",
                                  "apply_task4_cleanup", "apply_task5_cleanup", "fix_task4_sync_duplicates"])
def test_legacy_maintenance_is_blocked_before_opening_a_database(module, monkeypatch):
    def forbidden(*_args, **_kwargs): raise AssertionError("must not open legacy database")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(MutationPaused):
        importlib.import_module(module).main()


def test_helpers_and_admin_apply_are_paused_without_mutating_rows(client, db_session, engine):
    from app.services.foreign_editions import apply_plan
    from app.services.isbn_conflict_fix import apply_case
    from app.services.phantom_review import merge_volume_rows, apply_safe_merge
    seed_catalog_series(db_session, "Pause manga", "Publisher", volumes=(1, 2))
    before = inspect_file(Path(engine.url.database))
    for call in (lambda: merge_volume_rows(db_session, 1, 2),
                 lambda: apply_safe_merge(db_session, 1, 2, products=[]),
                 lambda: apply_plan(db_session, {}), lambda: apply_case(None, {})):
        with pytest.raises(MutationPaused): call()
    assert client.post("/catalog/isbn-fix?apply=true").status_code == 409
    assert client.delete("/volume/1/listings/1").status_code == 409
    assert inspect_file(Path(engine.url.database)) == before


def test_readiness_detects_missing_or_tampered_database_guard(guarded):
    path, _ = guarded
    with sqlite3.connect(path) as connection:
        name = next(iter(GUARDS))
        connection.execute(f"DROP TRIGGER {name}")
        connection.execute(f"CREATE TRIGGER {name} BEFORE UPDATE ON volumes BEGIN SELECT 1; END")
        with pytest.raises(RuntimeError, match="incomplete"):
            check_guards(connection)


def test_guard_allows_safe_price_switch_without_rewriting_old_observations(guarded):
    from app.services.import_service import ImportService, ImportAction
    path, engine = guarded
    with Session(engine, autoflush=False) as session:
        service = ImportService(session, scrapers=[])
        result = make_result("bkm", "Berserk 1", "110", isbn=ISBN, publisher="Athica Yayınları").model_copy(
            update={"product_url": "https://example.com/new-printing"})
        assert service.import_result(result) == ImportAction.UPDATED
        session.commit()
        histories = list(session.scalars(select(PriceHistory).order_by(PriceHistory.id)))
        assert [(h.price, h.product_url) for h in histories] == [
            (12000, "https://example.com/one"), (11000, "https://example.com/new-printing")]
        assert service.import_result(result) == ImportAction.UPDATED
        session.commit()
        assert len(list(session.scalars(select(PriceHistory)))) == 2
        assert session.get(Volume, 1).isbn == ISBN


def test_removed_product_appends_stock_observation_without_deleting_history(guarded):
    from types import SimpleNamespace
    from app.services.import_service import ImportService
    path, engine = guarded
    with Session(engine, autoflush=False) as session:
        scraper = SimpleNamespace(store_id="bkm", gone_urls={"https://example.com/one"})
        service = ImportService(session, scrapers=[])
        assert service._remove_gone_listings(scraper) == 1
        assert service._remove_gone_listings(scraper) == 1
        histories = list(session.scalars(select(PriceHistory).order_by(PriceHistory.id)))
        assert [(h.price, h.in_stock) for h in histories] == [(12000, None), (12000, False)]
        assert session.get(StoreListing, 1).volume_id == 1
        assert session.get(StoreListing, 1).in_stock is False


@pytest.mark.parametrize("fail_at", ["backup", "restore"])
def test_activation_fails_closed_if_backup_or_restore_fails(tmp_path, monkeypatch, fail_at):
    from app.services import safety_backup
    path = tmp_path / "existing.db"
    settings = replace(config_mod.get_settings(), database_url=f"sqlite:///{path}")
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(cfg, "0014_catalog_membership")
    before = inspect_file(path)

    def failed(_source):
        raise OSError(f"synthetic {fail_at} failure")

    monkeypatch.setattr(safety_backup, "activation_backup" if fail_at == "backup" else "rehearse_restore", failed)
    monkeypatch.setenv("AUTO_MIGRATION_BACKUP", "0")  # cannot disable the P0 activation backup
    with pytest.raises(OSError, match=f"synthetic {fail_at} failure"):
        database.init_db()
    assert inspect_file(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0014_catalog_membership",)
        assert connection.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone() == (0,)
    assert not path.with_name(path.name + ".isbn-safety.json").exists()
    backups = list(tmp_path.glob("existing.db.p0-isbn-*.bak"))
    assert len(backups) == (1 if fail_at == "restore" else 0)
    for backup in backups:
        assert inspect_file(backup) == before
        if os.name == "posix":
            assert backup.stat().st_mode & 0o077 == 0


def test_backup_never_overwrites_an_existing_destination_or_source(guarded, tmp_path):
    from app.services.safety_backup import copy_backup
    path, _ = guarded
    before = inspect_file(path)
    existing = tmp_path / "keep-me"
    existing.write_text("untouched")
    with pytest.raises(FileExistsError):
        copy_backup(path, existing)
    with pytest.raises(ValueError):
        copy_backup(path, path)
    assert existing.read_text() == "untouched"
    assert inspect_file(path) == before


def test_operational_status_is_private_and_readiness_checks_actual_guards(guarded, monkeypatch):
    from fastapi.testclient import TestClient
    from app.auth import COOKIE_NAME, new_session
    from app.database import get_db
    from app.main import create_app
    path, engine = guarded
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    app = create_app(auto_init=False)

    def get_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = get_session
    with TestClient(app) as client:
        app.state.ready = True
        assert client.get("/catalog/isbn-safety").status_code == 401
        public = client.get("/ready")
        assert public.status_code == 200 and public.json()["isbn_writes_paused"]
        assert "backup" not in public.text and "sha256" not in public.text
        with factory() as session:
            token = new_session(session, session.get(User, 1))
            ordinary = User(email="ordinary@example.com", display_name="Ordinary", role="USER", is_active=True)
            session.add(ordinary); session.commit()
            ordinary_token = new_session(session, ordinary)
        client.cookies.set(COOKIE_NAME, ordinary_token)
        assert client.get("/catalog/isbn-safety").status_code == 403
        client.cookies.set(COOKIE_NAME, token)
        report = client.get("/catalog/isbn-safety")
        assert report.status_code == 200
        assert report.json()["database_guards"] == len(GUARDS)
        assert report.json()["activation"]["restore"]["verified"]
        with sqlite3.connect(path) as connection:
            connection.execute(f"DROP TRIGGER {next(iter(GUARDS))}")
        assert client.get("/ready").status_code == 503
        assert client.get("/catalog/isbn-safety").status_code == 503
