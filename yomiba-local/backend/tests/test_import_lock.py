"""Phase 20: shared per-query import lock.

Manual ``POST /import`` and background imports share ONE lock per normalized
query; two imports for the same normalized query can never run
simultaneously, no matter which path triggered them.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker

from app.services.background_import import (
    BackgroundImportRunner,
    ImportLock,
    normalized_query_key,
)
from tests.helpers import RecordingScraper
from tests.test_auto_import import seed_catalog, set_fresh
from tests.test_import_service import make_result


# -- ImportLock unit semantics -----------------------------------------------------

def test_import_lock_semantics():
    lock = ImportLock()
    assert lock.acquire("k", "a", timeout=0.01) is True
    assert lock.acquire("k", "b", timeout=0.01) is False  # held -> times out
    assert lock.holder("k") == "a"
    lock.release("k", "b")  # wrong holder: no-op
    assert lock.holder("k") == "a"
    lock.release("k", "a")
    assert lock.acquire("k", "b", timeout=0.01) is True


def test_import_lock_blocks_until_release():
    lock = ImportLock()
    lock.acquire("k", "a")
    result: dict = {}

    def waiter():
        result["acquired"] = lock.acquire("k", "b", timeout=5)

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.1)
    assert "acquired" not in result  # still waiting
    lock.release("k", "a")
    thread.join(2)
    assert result.get("acquired") is True


# -- fixtures -----------------------------------------------------------------------

@pytest.fixture()
def sessions(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def make_runner(sessions, scrapers: list, **kwargs) -> BackgroundImportRunner:
    return BackgroundImportRunner(
        sessions, scraper_factory=lambda ids=None: list(scrapers), **kwargs
    )


# -- manual vs background -------------------------------------------------------------

def test_manual_import_409_while_background_running(client):
    old_runner = client.app.state.import_runner
    session_factory = old_runner._session_factory
    slow = RecordingScraper(store_id="bkm", delay=0.8)
    runner = BackgroundImportRunner(
        session_factory, scraper_factory=lambda ids=None: [slow], max_concurrent=2
    )
    client.app.state.import_runner = runner

    key = normalized_query_key("berserk")
    # Start a background job directly (the search endpoint only schedules
    # imports for catalog-matching queries — this test's DB has no catalog).
    assert runner.submit(key, "berserk") is True

    # Wait until the background job actually owns the lock (deterministic).
    deadline = time.monotonic() + 3
    while runner.import_lock_holder(key) != "background" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert runner.import_lock_holder(key) == "background"

    # A manual import for the same (normalized) query must be rejected.
    blocked = client.post("/import", json={"query": "BERSERK"})
    assert blocked.status_code == 409
    assert "zaten çalışıyor" in blocked.json()["detail"]

    assert runner.wait_for(key, timeout=10)
    # After the background job finishes, the manual path works again.
    ok = client.post("/import", json={"query": "berserk"})
    assert ok.status_code == 200
    assert runner.import_lock_holder(key) is None


def test_manual_lock_released_after_finish(client):
    res = client.post("/import", json={"query": "berserk"})
    assert res.status_code == 200
    runner = client.app.state.import_runner
    assert runner.import_lock_holder(normalized_query_key("berserk")) is None
    # A second manual import (equivalent normalized query) is allowed.
    res2 = client.post("/import", json={"query": "BERSERK"})
    assert res2.status_code == 200


def test_background_waits_for_manual_lock(sessions):
    key = normalized_query_key("berserk")
    slow = RecordingScraper(store_id="bkm", delay=0.2)
    runner = make_runner(sessions, [slow])

    # A manual import owns the lock; the background job must wait for it.
    assert runner.acquire_import_lock(key, "manual-test")
    assert runner.submit(key, "berserk") is True
    time.sleep(0.2)
    assert slow.calls == []  # waiting for the lock, not scraping
    assert runner.import_lock_holder(key) == "manual-test"

    runner.release_import_lock(key, "manual-test")
    assert runner.wait_for(key, timeout=10)
    assert slow.calls == ["berserk"]  # ran exactly once, after the release
    assert runner.import_lock_holder(key) is None


def test_normalized_keys_are_shared_across_paths(sessions):
    """'BERSERK' (manual) and 'berserk' (background) must collide on one lock."""
    key = normalized_query_key("BERSERK")
    assert key == normalized_query_key("berserk")

    slow = RecordingScraper(store_id="bkm", delay=0.2)
    runner = make_runner(sessions, [slow])

    assert runner.acquire_import_lock(normalized_query_key("BERSERK"), "manual-test")
    assert runner.submit(normalized_query_key("berserk"), "berserk") is True
    time.sleep(0.2)
    assert slow.calls == []  # the background job is blocked on the same key
    runner.release_import_lock(normalized_query_key("BERSERK"), "manual-test")
    assert runner.wait_for(key, timeout=10)
    assert slow.calls == ["berserk"]


def test_background_skips_when_manual_made_data_fresh_while_waiting(sessions):
    """A job that waited on the lock must re-check freshness before scraping."""
    seed_catalog(sessions, make_result("bkm", "Berserk 1", "182"))
    key = normalized_query_key("berserk")
    set_fresh(sessions, key, minutes_ago=1)  # manual import finished moments ago

    slow = RecordingScraper(store_id="bkm", delay=0.1)
    runner = make_runner(sessions, [slow])

    assert runner.submit(key, "berserk") is True
    assert runner.wait_for(key, timeout=10)
    assert slow.calls == []  # already fresh -> skipped, zero store requests


def test_manual_import_unexpected_failure_marks_record_failed(client, db_session, monkeypatch):
    """An unexpected exception must not leave the ImportRecord stuck "running"."""
    import app.routes.import_ as import_route
    from sqlalchemy import select

    from app.models import ImportRecord
    from app.services.background_import import normalized_query_key

    class Boom:
        def __init__(self, session) -> None:
            pass

        def run_import(self, query):
            raise RuntimeError("kaboom")

    real_import_service = import_route.ImportService
    monkeypatch.setattr(import_route, "ImportService", Boom)

    key = normalized_query_key("berserk")
    with pytest.raises(RuntimeError, match="kaboom"):
        client.post("/import", json={"query": "berserk"})

    record = db_session.scalar(
        select(ImportRecord).where(ImportRecord.normalized_query == key)
    )
    assert record is not None
    assert record.status == "failed"  # not stuck as "running"
    assert "kaboom" in (record.error or "")
    assert client.app.state.import_runner.import_lock_holder(key) is None

    # And a subsequent manual import for the same query works again.
    # (Re-assert the real service instead of monkeypatch.undo(): the
    # function-scoped monkeypatch is shared with the client fixture, whose
    # fake-scraper patch must survive.)
    monkeypatch.setattr(import_route, "ImportService", real_import_service)
    res = client.post("/import", json={"query": "berserk"})
    assert res.status_code == 200


def test_runner_lock_timeout_gives_up_cleanly(sessions):
    key = normalized_query_key("berserk")
    slow = RecordingScraper(store_id="bkm")
    runner = make_runner(sessions, [slow])

    runner.lock.acquire(key, "manual-test")  # hold it
    # Tiny lock timeout so the job gives up quickly (module-level binding).
    import app.services.background_import as bg

    from dataclasses import replace

    from app.config import get_settings

    original = bg.get_settings
    bg.get_settings = lambda: replace(get_settings(), import_lock_timeout_seconds=0.1)
    try:
        assert runner.submit(key, "berserk") is True
        assert runner.wait_for(key, timeout=10)
    finally:
        bg.get_settings = original

    assert slow.calls == []  # skipped, not crashed
    assert runner.import_lock_holder(key) == "manual-test"
    runner.release_import_lock(key, "manual-test")
