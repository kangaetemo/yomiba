"""Catalog write gate: the Mangakol catalog sync and store imports must
never write publisher rows simultaneously.

* ``POST /catalog/sync`` returns 409 while an import holds the gate.
* The sync holds the gate for its whole run (released afterwards).
* A background import job waits for the gate; when it times out the job
  is recorded as "skipped" instead of writing under the running sync.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import app.routes.catalog as catalog_route
import app.services.background_import as background_import_mod
from app.config import Settings, get_settings
from app.models import ImportRecord
from app.services.background_import import (
    SYNC_GATE_KEY,
    BackgroundImportRunner,
    normalized_query_key,
)
from app.services.catalog_sync import CatalogSyncReport
from tests.helpers import RecordingScraper


@pytest.fixture()
def sessions(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def make_runner(sessions, scrapers: list, **kwargs) -> BackgroundImportRunner:
    return BackgroundImportRunner(
        sessions, scraper_factory=lambda ids=None: list(scrapers), **kwargs
    )


def test_sync_refused_while_import_holds_gate(client):
    runner = client.app.state.import_runner
    assert runner.acquire_import_lock(SYNC_GATE_KEY, "background")
    try:
        res = client.post("/catalog/sync")
    finally:
        runner.release_import_lock(SYNC_GATE_KEY, "background")
    assert res.status_code == 409
    assert "mağaza içe aktarması" in res.json()["detail"]
    # and the sync did NOT start
    assert client.get("/catalog/sync/status").json()["running"] is False


class _FakeCatalogSyncService:
    """Stands in for the real service: no scraper, no network, fast."""

    def __init__(self, session, delay: float = 0.3):
        self.session = session
        self._delay = delay
        self.called = False

    def sync(self) -> CatalogSyncReport:
        time.sleep(self._delay)
        self.called = True
        report = CatalogSyncReport()
        report.manga_total = 2
        report.manga_scanned = 2
        report.series_created = 1
        report.series_merged = 1
        report.volumes_added = 3
        return report


def _wait_status(client, running: bool, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get("/catalog/sync/status").json()
        if body["running"] == running:
            return body
        time.sleep(0.02)
    raise AssertionError(f"status.running did not reach {running} in {timeout}s")


def test_sync_holds_gate_for_whole_run(client, monkeypatch, engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    fake = _FakeCatalogSyncService(None)
    monkeypatch.setattr(catalog_route, "SessionLocal", TestingSession)
    monkeypatch.setattr(catalog_route, "CatalogSyncService",
                        lambda session: fake)

    res = client.post("/catalog/sync")
    assert res.status_code == 202
    runner = client.app.state.import_runner
    # while the (fake) sync runs, the gate belongs to the sync
    _wait_status(client, running=True)
    assert runner.import_lock_holder(SYNC_GATE_KEY) == "catalog"
    body = _wait_status(client, running=False)
    # released afterwards; summary carries the (new) consolidation fields
    assert runner.import_lock_holder(SYNC_GATE_KEY) is None
    assert body["last"]["status"] == "success"
    assert body["last"]["series_created"] == 1
    assert "publishers_merged" in body["last"]
    assert "series_absorbed" in body["last"]
    assert "volumes_merged" in body["last"]
    assert fake.called


def _fast_gate_settings(monkeypatch, gate_timeout: float) -> None:
    """Point background_import's settings at a short catalog gate timeout."""
    fast = Settings(catalog_gate_timeout_seconds=gate_timeout)
    monkeypatch.setattr(
        background_import_mod, "get_settings", lambda: fast
    )


def test_background_import_skipped_when_gate_held(sessions, monkeypatch):
    _fast_gate_settings(monkeypatch, gate_timeout=1.0)
    scraper = RecordingScraper(store_id="bkm")
    runner = make_runner(sessions, [scraper])
    key = normalized_query_key("kizil")

    assert runner.acquire_import_lock(SYNC_GATE_KEY, "catalog")
    assert runner.submit(key, "kizil") is True
    runner.wait_for(key, timeout=10)
    runner.release_import_lock(SYNC_GATE_KEY, "catalog")

    assert scraper.calls == []  # never scraped under the running sync
    record = runner.get_record(key)
    assert record is not None
    assert record.status == "skipped"
    assert "katalog senkronu" in (record.error or "")


def test_background_import_proceeds_after_gate_released(sessions, monkeypatch):
    _fast_gate_settings(monkeypatch, gate_timeout=5.0)
    scraper = RecordingScraper(store_id="bkm")
    runner = make_runner(sessions, [scraper])
    key = normalized_query_key("berserk")

    assert runner.acquire_import_lock(SYNC_GATE_KEY, "catalog")
    assert runner.submit(key, "berserk") is True
    time.sleep(0.2)
    assert scraper.calls == []  # still waiting for the gate
    runner.release_import_lock(SYNC_GATE_KEY, "catalog")
    assert runner.wait_for(key, timeout=10)

    assert scraper.calls == ["berserk"]
    record = runner.get_record(key)
    assert record.status == "success"


# ---------------------------------------------------------------------------
# Manual /import path (P27): it must respect the catalog write gate too
# ---------------------------------------------------------------------------

def test_manual_import_409_while_sync_holds_gate(client):
    """A manual import running while the sync holds the gate must refuse
    (409) instead of writing publisher rows under the sync."""
    runner = client.app.state.import_runner
    assert runner.acquire_import_lock(SYNC_GATE_KEY, "catalog")
    try:
        res = client.post("/import", json={"query": "kizil"})
    finally:
        runner.release_import_lock(SYNC_GATE_KEY, "catalog")

    assert res.status_code == 409
    assert "katalog senkronu veya mağaza içe aktarması" in res.json()["detail"]
    # the gate refusal happens BEFORE any scraping / record bookkeeping
    key = normalized_query_key("kizil")
    assert runner.get_record(key) is None
    # and the per-query lock the request took in the meantime is released
    assert runner.import_lock_holder(key) is None

    # after the gate is free, the same import proceeds (nothing stuck)
    res2 = client.post("/import", json={"query": "kizil"})
    assert res2.status_code == 200


def test_manual_import_holds_gate_for_whole_run(client, monkeypatch):
    """The manual /import route itself holds the catalog gate for its whole
    run, so the sync side can refuse while a manual import is in flight."""
    import app.routes.import_ as import_route
    from app.services.import_service import ImportReport, StoreImportResult
    from app.utils import utcnow

    entered = threading.Event()
    release = threading.Event()

    class _HoldingImportService:
        def __init__(self, session):
            pass

        def run_import(self, query):
            entered.set()
            assert release.wait(10)
            now = utcnow()
            return ImportReport(
                query=query,
                started_at=now,
                finished_at=now,
                stores=[StoreImportResult(store_code="bkm", store_name="BKM")],
            )

    monkeypatch.setattr(import_route, "ImportService", _HoldingImportService)

    result: dict = {}
    thread = threading.Thread(
        target=lambda: result.update(
            res=client.post("/import", json={"query": "kizil"})
        )
    )
    thread.start()
    assert entered.wait(10)
    try:
        holder = client.app.state.import_runner.import_lock_holder(SYNC_GATE_KEY)
        assert holder is not None and holder.startswith("manual-")
    finally:
        release.set()
    thread.join(10)
    assert not thread.is_alive()
    assert client.app.state.import_runner.import_lock_holder(SYNC_GATE_KEY) is None
    assert result["res"].status_code == 200


def test_sync_409_while_manual_import_holds_gate(client):
    """Symmetry: a running manual import (which now holds the gate) blocks
    the catalog sync — with the SAME 409 message a background import
    produces (the /catalog/sync messages are unchanged)."""
    runner = client.app.state.import_runner
    assert runner.acquire_import_lock(SYNC_GATE_KEY, "manual-abc123")
    try:
        res = client.post("/catalog/sync")
    finally:
        runner.release_import_lock(SYNC_GATE_KEY, "manual-abc123")

    assert res.status_code == 409
    assert "mağaza içe aktarması" in res.json()["detail"]
