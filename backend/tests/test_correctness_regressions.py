"""Catalog boundary, import gate ownership and sync isolation regressions."""

from __future__ import annotations

import threading
import sqlite3
import sys

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.models import (
    CatalogExclusion, CatalogSeries, PriceAlert, Publisher, Series,
    Store, StoreListing, Volume, WishlistItem,
)
from app.scrapers import SearchResult
from app.services import background_import as background_module
from app.services.background_import import BackgroundImportRunner, SYNC_GATE_KEY
from app.services.catalog_sync import CatalogSyncService
from app.services.import_service import ImportAction, ImportService
from cleanup_catalog_orphans import has_protected_data, inspect_orphans, main as cleanup_main
from tests.test_catalog_sync import FakeMangakolScraper, _manga
from tests.test_import_service import seed_catalog_series


def test_two_background_imports_keep_catalog_gate_until_both_finish(engine):
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    runner = BackgroundImportRunner(sessions, max_concurrent=2)
    entered = {key: threading.Event() for key in ("a", "b")}
    release = {key: threading.Event() for key in ("a", "b")}

    def execute(key, query):
        entered[key].set()
        assert release[key].wait(5)

    runner._execute = execute
    assert runner.submit("a", "a")
    assert runner.submit("b", "b")
    try:
        assert entered["a"].wait(5) and entered["b"].wait(5)
        assert not runner.acquire_import_lock(SYNC_GATE_KEY, "catalog", timeout=0)
        release["a"].set()
        assert runner.wait_for("a", 5)
        assert not runner.acquire_import_lock(SYNC_GATE_KEY, "catalog", timeout=0)
        release["b"].set()
        assert runner.wait_for("b", 5)
        assert runner.acquire_import_lock(SYNC_GATE_KEY, "catalog", timeout=0)
        runner.release_import_lock(SYNC_GATE_KEY, "catalog")
    finally:
        release["a"].set()
        release["b"].set()
        runner.shutdown(5)


def test_gate_timeout_releases_query_lock_and_retry_succeeds(engine, monkeypatch):
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(
        background_module, "get_settings",
        lambda: Settings(catalog_gate_timeout_seconds=0.05),
    )
    runner = BackgroundImportRunner(sessions)
    calls = []
    runner._execute = lambda key, query: calls.append(query)
    assert runner.acquire_import_lock(SYNC_GATE_KEY, "catalog", timeout=0)
    try:
        assert runner.submit("a", "a")
        assert runner.wait_for("a", 5)
        assert runner.import_lock_holder("a") is None
        assert runner.get_record("a").status == "skipped"
    finally:
        runner.release_import_lock(SYNC_GATE_KEY, "catalog")
    assert runner.submit("a", "a")
    assert runner.wait_for("a", 5)
    assert calls == ["a"]
    assert runner.import_lock_holder("a") is None


def test_manual_import_still_refuses_background_gate(client):
    runner = client.app.state.import_runner
    entered = threading.Event()
    release = threading.Event()

    def execute(key, query):
        entered.set()
        assert release.wait(5)

    runner._execute = execute
    assert runner.submit("a", "a")
    try:
        assert entered.wait(5)
        assert client.post("/import", json={"query": "different"}).status_code == 409
    finally:
        release.set()
        assert runner.wait_for("a", 5)
    assert client.post("/import", json={"query": "different"}).status_code == 200


def test_failed_manga_rolls_back_only_its_own_changes(db_session):
    mangas = [_manga(key, key.upper(), pub=key.upper(), volumes=(1,)) for key in ("a", "b", "c")]
    service = CatalogSyncService(db_session, scraper=FakeMangakolScraper(mangas))
    original = service._merge_manga

    def merge_then_fail(manga, report):
        original(manga, report)
        if manga.slug == "b":
            raise RuntimeError("merge interrupted after writes")

    service._merge_manga = merge_then_fail
    report = service.sync()
    assert not report.ok and report.manga_failed == 1
    assert report.series_created == 2
    assert {s.title for s in db_session.scalars(select(Series))} == {"A", "C"}
    assert {s.mangakol_slug for s in db_session.scalars(select(CatalogSeries))} == {"a", "c"}
    assert {p.name for p in db_session.scalars(select(Publisher))} == {"A", "C"}
    assert len(db_session.scalars(select(Volume)).all()) == 2


def test_empty_catalog_report_is_failure_and_keeps_existing_data(db_session):
    CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([_manga("a", "A", volumes=(1,))])
    ).sync()
    empty_service = CatalogSyncService(db_session, scraper=FakeMangakolScraper([]))
    empty_service._consolidate_publisher_aliases = lambda report: pytest.fail(
        "empty catalog must not mutate publishers"
    )
    report = empty_service.sync()
    assert not report.ok
    assert "no manga" in report.errors[0]
    assert db_session.scalar(select(Series.title)) == "A"
    assert db_session.scalar(select(CatalogSeries.mangakol_slug)) == "a"


@pytest.mark.parametrize("protected", ["listing", "wishlist", "alert", "collection", "isbn"])
def test_legacy_exclusion_never_removes_store_or_user_data(db_session, protected):
    manga = _manga("excluded", "Excluded", volumes=(1,))
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    volume = db_session.scalar(select(Volume))
    if protected == "listing":
        store = Store(code="test", name="Test")
        db_session.add(store)
        db_session.flush()
        db_session.add(StoreListing(volume_id=volume.id, store_id=store.id,
                                    product_url="https://example.test/1", price=100))
    elif protected == "wishlist":
        db_session.add(WishlistItem(user_id=1, volume_id=volume.id))
    elif protected == "alert":
        db_session.add(PriceAlert(user_id=1, volume_id=volume.id, threshold_price=100))
    elif protected == "collection":
        from app.models import UserVolumeCollection
        db_session.add(UserVolumeCollection(user_id=1, volume_id=volume.id, status="owned"))
    else:
        volume.isbn = "9786051234567"
    db_session.add(CatalogExclusion(mangakol_slug="excluded"))
    db_session.commit()

    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    assert report.ok
    assert db_session.scalar(select(CatalogSeries.series_id)) is not None
    assert db_session.scalar(select(Series.id)) is not None
    assert db_session.scalar(select(Volume.id)) == volume.id
    if protected == "listing":
        assert db_session.scalar(select(StoreListing.id)) is not None
    elif protected == "wishlist":
        assert db_session.scalar(select(WishlistItem.id)) is not None
    elif protected == "alert":
        assert db_session.scalar(select(PriceAlert.id)) is not None
    elif protected == "collection":
        from app.models import UserVolumeCollection
        assert db_session.scalar(select(UserVolumeCollection.status)) == "owned"
    else:
        assert volume.isbn == "9786051234567"


def test_catalog_detail_endpoints_hide_manifestless_rows(client, db_session):
    pub = Publisher(name="Outside", normalized_name="outside")
    db_session.add(pub)
    db_session.flush()
    series = Series(publisher_id=pub.id, title="Outside", slug="outside",
                    normalized_title="outside")
    db_session.add(series)
    db_session.flush()
    volume = Volume(series_id=series.id, volume_number=1)
    db_session.add(volume)
    db_session.commit()
    assert client.get(f"/series/{series.id}").status_code == 404
    assert client.get(f"/volume/{volume.id}").status_code == 404
    assert client.get(f"/volume/{volume.id}/price-history").status_code == 404
    assert client.post(f"/volume/{volume.id}/wishlist").status_code == 404


def test_known_other_publisher_cannot_bridge_but_isbn_still_wins(db_session):
    catalog = seed_catalog_series(
        db_session, "Tek Yumruk", "Akilcelen Kitaplar", original="One Punch Man", volumes=(1,)
    )
    db_session.add(Publisher(name="Viz Media", normalized_name="viz media"))
    db_session.commit()
    service = ImportService(db_session)
    for title in ("One Punch Man 1", "One Punch Man 1 - Tek Yumruk"):
        result = SearchResult(
            store_id="bkm", store_name="BKM Kitap", title=title,
            product_url="https://example.test/one-punch-man-1", publisher="Viz Media",
        )
        assert service.import_result(result) == ImportAction.SKIPPED
    assert db_session.scalars(select(StoreListing)).all() == []

    volume = db_session.scalar(select(Volume).where(Volume.series_id == catalog.id))
    volume.isbn = "9786051234567"
    db_session.commit()
    assert service.import_result(result.model_copy(update={"isbn": volume.isbn})) == ImportAction.CREATED
    assert db_session.scalar(select(StoreListing.volume_id)) == volume.id


def test_cleanup_dry_run_detects_protected_data(engine, db_session):
    pub = Publisher(name="Outside", normalized_name="outside")
    db_session.add(pub)
    db_session.flush()
    series = Series(publisher_id=pub.id, title="Outside", slug="outside",
                    normalized_title="outside")
    db_session.add(series)
    db_session.flush()
    volume = Volume(series_id=series.id, volume_number=1)
    db_session.add(volume)
    db_session.flush()
    db_session.add(WishlistItem(user_id=1, volume_id=volume.id))
    db_session.commit()
    with sqlite3.connect(engine.url.database) as connection:
        rows = inspect_orphans(connection)
    assert len(rows) == 1
    assert rows[0]["volumes"] == 1 and rows[0]["wishlist_items"] == 1
    assert has_protected_data(rows)


def test_cleanup_apply_on_scratch_db_keeps_catalog_data(engine, db_session, monkeypatch):
    catalog = seed_catalog_series(db_session, "Catalog", "Publisher", volumes=(1,))
    pub = Publisher(name="Outside", normalized_name="outside")
    db_session.add(pub)
    db_session.flush()
    outside = Series(publisher_id=pub.id, title="Outside", slug="outside",
                     normalized_title="outside")
    db_session.add(outside)
    db_session.flush()
    db_session.add(Volume(series_id=outside.id, volume_number=1))
    db_session.commit()
    monkeypatch.setattr(sys, "argv", ["cleanup_catalog_orphans.py", "--db", engine.url.database, "--apply"])
    assert cleanup_main() == 0
    db_session.expire_all()
    assert {s.id for s in db_session.scalars(select(Series))} == {catalog.id}
    assert {s.series_id for s in db_session.scalars(select(CatalogSeries))} == {catalog.id}
    assert db_session.scalar(select(Volume.series_id)) == catalog.id
