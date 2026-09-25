"""Periodic catalog sync scheduler (P26).

Covered behaviour (see phase plan):

* no run before the first interval (no catch-up at startup — restart
  contract: gap between syncs stays within [interval, 2*interval));
* periodic runs; idempotent ``start()``; clean ``stop()``;
* ``"already_running"`` ticks are skipped without killing the loop;
* a held catalog gate is waited out (bounded) and the sync then starts;
* a gate held beyond the budget is skipped (no infinite loop), next tick
  still fires;
* a crashing ``start_sync`` does not kill the scheduler thread;
* ``stop()`` is prompt even while the worker waits on the gate;
* the FastAPI lifespan wires the scheduler ONLY when
  ``auto_init=True and catalog_sync_enabled`` — never in tests.

Timing note: intervals are sub-second and assertions use deadline polling
(recorders + events) instead of fixed sleeps.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker

from app.services.catalog_scheduler import CatalogSyncScheduler


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    """Poll until ``predicate()`` is true (deterministic test helper)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _Recorder:
    """start_sync stand-in: scripted replies, thread-safe counters."""

    def __init__(self, script: list[str] | None = None):
        # ``script``: list of replies to give for the first N calls;
        # when exhausted, keep repeating the last entry ("started").
        self.script = list(script or [])
        self.calls = 0
        self._lock = threading.Lock()
        self.excepthook = None  # optional exception for one call

    def __call__(self) -> str:
        with self._lock:
            self.calls += 1
            n = self.calls
        if self.excepthook is not None and n == 1:
            raise RuntimeError("simulated start_sync crash")
        if self.script:
            reply = self.script[0] if n <= len(self.script) else self.script[-1]
            return reply
        return "started"


def test_no_run_before_first_interval():
    rec = _Recorder()
    sched = CatalogSyncScheduler(rec, interval_seconds=0.3,
                                 gate_wait_seconds=1.0, poll_seconds=0.05)
    sched.start()
    try:
        time.sleep(0.1)
        assert rec.calls == 0  # no catch-up run right after start
        assert _wait_until(lambda: rec.calls >= 1, timeout=3.0)
    finally:
        sched.stop(timeout=2)
    assert not sched.is_running


def test_periodic_runs_and_stop():
    rec = _Recorder()
    sched = CatalogSyncScheduler(rec, interval_seconds=0.15,
                                 gate_wait_seconds=1.0, poll_seconds=0.05)
    sched.start()
    try:
        assert _wait_until(lambda: rec.calls >= 3, timeout=4.0)
    finally:
        sched.stop(timeout=2)
    n = rec.calls
    time.sleep(0.4)
    assert rec.calls == n  # no run after stop


def test_start_is_idempotent():
    rec = _Recorder()
    sched = CatalogSyncScheduler(rec, interval_seconds=60.0)
    sched.start()
    sched.start()  # second start must be ignored
    workers = [
        t for t in threading.enumerate()
        if t.name == "catalog-sync-scheduler"
    ]
    assert len(workers) == 1
    sched.stop(timeout=2)
    assert len([
        t for t in threading.enumerate() if t.name == "catalog-sync-scheduler"
    ]) == 0


def test_already_running_ticks_are_skipped_without_killing_loop():
    rec = _Recorder(script=["already_running", "already_running", "started"])
    sched = CatalogSyncScheduler(rec, interval_seconds=0.1,
                                 gate_wait_seconds=1.0, poll_seconds=0.05)
    sched.start()
    try:
        # three ticks fire (two skips + one start) — the loop survived
        assert _wait_until(lambda: rec.calls >= 3, timeout=4.0)
    finally:
        sched.stop(timeout=2)


def test_gate_held_is_waited_out_then_starts():
    rec = _Recorder(script=["gate_held", "gate_held", "started"])
    sched = CatalogSyncScheduler(rec, interval_seconds=0.1,
                                 gate_wait_seconds=2.0, poll_seconds=0.05)
    sched.start()
    try:
        assert _wait_until(lambda: rec.calls >= 3, timeout=4.0)
    finally:
        sched.stop(timeout=2)


def test_gate_held_beyond_budget_is_skipped_and_loop_continues():
    rec = _Recorder(script=["gate_held"])  # forever gate_held
    sched = CatalogSyncScheduler(rec, interval_seconds=0.3,
                                 gate_wait_seconds=0.2, poll_seconds=0.05)
    sched.start()
    try:
        # first tick burns its budget (several polls), then the NEXT tick
        # must fire too — no infinite loop, no dead scheduler
        assert _wait_until(lambda: rec.calls >= 10, timeout=6.0)
    finally:
        sched.stop(timeout=2)


def test_start_sync_exception_does_not_kill_thread():
    rec = _Recorder()
    rec.excepthook = True  # first call raises
    sched = CatalogSyncScheduler(rec, interval_seconds=0.15,
                                 gate_wait_seconds=1.0, poll_seconds=0.05)
    sched.start()
    try:
        assert sched.is_running
        # the tick that crashed is followed by a surviving tick
        assert _wait_until(lambda: rec.calls >= 2, timeout=4.0)
        assert sched.is_running
    finally:
        sched.stop(timeout=2)


def test_stop_is_prompt_during_gate_wait():
    rec = _Recorder(script=["gate_held"])  # worker parks in the gate wait
    sched = CatalogSyncScheduler(rec, interval_seconds=0.1,
                                 gate_wait_seconds=300.0, poll_seconds=0.05)
    sched.start()
    try:
        assert _wait_until(lambda: rec.calls >= 1, timeout=3.0)
        time.sleep(0.1)  # let the worker enter the gate-wait loop
        t0 = time.monotonic()
        sched.stop(timeout=2.0)
        assert time.monotonic() - t0 < 1.0  # prompt exit mid wait
        assert not sched.is_running
    finally:
        sched.stop(timeout=2)


def test_invalid_interval_rejected():
    with pytest.raises(ValueError):
        CatalogSyncScheduler(lambda: "started", interval_seconds=0)


# ---------------------------------------------------------------------------
# Lifespan wiring (real FastAPI app, test DB, DB touchpoints stubbed)
# ---------------------------------------------------------------------------

def _wired_client(monkeypatch, engine, **settings_overrides):
    """Build create_app(auto_init=True) against the test engine.

    init_db / seed_stores are stubbed so the real yomiba.db is never
    touched; the import runner is preset (lifespan never clobbers it);
    try_start_sync is recorder-patched so no real gate/sync is attempted.
    """
    from dataclasses import replace

    from app import database, seed as seed_mod
    from app.config import get_settings
    from app.main import create_app
    from app.services.background_import import BackgroundImportRunner
    from tests.helpers import RecordingScraper

    import app.main as main_mod
    import app.routes.catalog as catalog_route

    TestingSession = sessionmaker(bind=engine, autoflush=False,
                                  expire_on_commit=False)
    monkeypatch.setattr(database, "init_db", lambda: None)
    monkeypatch.setattr(database, "SessionLocal", TestingSession)
    monkeypatch.setattr(seed_mod, "seed_stores", lambda session: None)

    fast = replace(
        get_settings(),
        catalog_sync_interval_hours=0.0001,  # ~0.36s first tick
        **settings_overrides,
    )
    monkeypatch.setattr(main_mod, "get_settings", lambda: fast)

    app = create_app(auto_init=True)
    app.state.import_runner = BackgroundImportRunner(
        TestingSession,
        scraper_factory=lambda ids=None: [RecordingScraper(store_id="bkm")],
        max_concurrent=2,
    )

    calls: list[str] = []

    def fake_try_start_sync(runner) -> str:
        calls.append("started")
        return "started"

    monkeypatch.setattr(catalog_route, "try_start_sync", fake_try_start_sync)
    from fastapi.testclient import TestClient

    return TestClient(app), calls


def test_auto_init_wires_and_fires_scheduler(monkeypatch, engine):
    client, calls = _wired_client(monkeypatch, engine)
    with client:
        sched = client.app.state.catalog_scheduler
        assert sched is not None
        assert sched.is_running
        # the scheduled tick fires through the SAME start point
        assert _wait_until(lambda: len(calls) >= 1, timeout=5.0)
        assert calls[0] == "started"
    # context exit runs the shutdown: scheduler stopped
    assert client.app.state.catalog_scheduler is not None
    assert not client.app.state.catalog_scheduler.is_running


def test_auto_init_disabled_flag_blocks_scheduler(monkeypatch, engine):
    client, calls = _wired_client(monkeypatch, engine,
                                  catalog_sync_enabled=False)
    with client:
        assert client.app.state.catalog_scheduler is None
        time.sleep(0.1)
        assert calls == []


def test_auto_init_false_never_wires_scheduler(client):
    # every existing API test runs this shape: no scheduler, ever
    assert client.app.state.catalog_scheduler is None


def test_auto_init_marks_interrupted_imports_failed(monkeypatch, engine, db_session):
    # A process killed mid-import leaves status="running" forever. At the
    # next startup nothing can be running, so such records must be marked
    # failed — and only those.
    from datetime import timedelta

    from app.models import ImportRecord
    from app.utils import utcnow

    now = utcnow()
    zombie = ImportRecord(
        normalized_query="tokyo ghoul",
        last_query="Tokyo Ghoul",
        status="running",
        last_attempt_at=now - timedelta(hours=2),
    )
    healthy = ImportRecord(
        normalized_query="berserk",
        last_query="berserk",
        status="partial",
        last_attempt_at=now - timedelta(hours=2),
        last_success_at=now - timedelta(hours=2),
    )
    db_session.add_all([zombie, healthy])
    db_session.commit()

    client, _calls = _wired_client(monkeypatch, engine)
    with client:
        pass  # startup runs the cleanup; shutdown is irrelevant here

    db_session.expire_all()
    z = db_session.get(ImportRecord, zombie.id)
    h = db_session.get(ImportRecord, healthy.id)
    assert z.status == "failed"
    assert "yarıda kesildi" in (z.error or "")
    assert h.status == "partial"
    assert h.error is None
