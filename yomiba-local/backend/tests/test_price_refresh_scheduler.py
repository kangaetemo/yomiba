"""Periodic price refresh scheduler.

Covered behaviour:

* tick() submits ONLY stale queries — fresh (last success within TTL)
  records are left alone;
* a stale query is resubmitted under its stored last_query text;
* a query inside its failure-retry window after an attempt (any status)
  is skipped — the same anti-hammering rule search_with_auto_import uses;
* a key already running in the runner is not double-submitted;
* an empty record table is a no-op;
* no pass before the first interval (no catch-up at startup — same
  restart contract as the catalog sync scheduler);
* a tick that raises does not kill the scheduler loop;
* clean start()/stop() lifecycle (idempotent start).

Timing note: intervals are sub-second and assertions use deadline polling
instead of fixed sleeps.
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import ImportRecord
from app.services.price_refresh_scheduler import PriceRefreshScheduler
from app.utils import utcnow


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _StubRunner:
    """BackgroundImportRunner stand-in: records submit() calls."""

    def __init__(self, running_keys: set[str] | None = None):
        self.submitted: list[tuple[str, str]] = []
        self._running = set(running_keys or set())
        self._lock = threading.Lock()

    def submit(self, key: str, query: str) -> bool:
        with self._lock:
            if key in self._running:
                return False
            self._running.add(key)
            self.submitted.append((key, query))
            return True

    def is_running(self, key: str) -> bool:
        with self._lock:
            return key in self._running


@pytest.fixture()
def sessions(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _add_record(sessions, key: str, **fields) -> None:
    session = sessions()
    try:
        record = ImportRecord(normalized_query=key)
        for name, value in fields.items():
            setattr(record, name, value)
        session.add(record)
        session.commit()
    finally:
        session.close()


def _seed(sessions, key: str, *, success_minutes_ago: float | None = None,
          attempt_minutes_ago: float | None = None, status: str = "success",
          last_query: str | None = None) -> None:
    fields = {"status": status, "last_query": last_query or key}
    if success_minutes_ago is not None:
        fields["last_success_at"] = utcnow() - timedelta(minutes=success_minutes_ago)
    if attempt_minutes_ago is not None:
        fields["last_attempt_at"] = utcnow() - timedelta(minutes=attempt_minutes_ago)
    _add_record(sessions, key, **fields)


# -- tick selection logic ----------------------------------------------------------

def test_fresh_record_not_submitted(sessions):
    _seed(sessions, "berserk", success_minutes_ago=5, attempt_minutes_ago=5)
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)

    assert sched.tick() == 0
    assert runner.submitted == []


def test_stale_record_submitted_with_stored_query(sessions):
    _seed(sessions, "berserk", success_minutes_ago=120, attempt_minutes_ago=120,
          last_query="Berserk Vol")
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)

    assert sched.tick() == 1
    assert runner.submitted == [("berserk", "Berserk Vol")]


def test_no_success_recent_attempt_skipped(sessions):
    # Failed 2 minutes ago (inside the 5-minute retry window): skip.
    _seed(sessions, "jujutsu", attempt_minutes_ago=2, status="failed")
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)

    assert sched.tick() == 0
    assert runner.submitted == []


def test_no_success_old_attempt_submitted(sessions):
    # Failed 30 minutes ago (outside the retry window): resubmit.
    _seed(sessions, "jujutsu", attempt_minutes_ago=30, status="failed")
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)

    assert sched.tick() == 1
    assert runner.submitted == [("jujutsu", "jujutsu")]


def test_never_imported_record_submitted(sessions):
    _add_record(sessions, "vinland")  # bare record, no attempts yet
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)

    assert sched.tick() == 1
    assert runner.submitted == [("vinland", "vinland")]


def test_running_key_not_resubmitted(sessions):
    _seed(sessions, "berserk", success_minutes_ago=120, attempt_minutes_ago=120)
    runner = _StubRunner(running_keys={"berserk"})
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)

    assert sched.tick() == 0
    assert runner.submitted == []


def test_empty_record_table_is_noop(sessions):
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)

    assert sched.tick() == 0
    assert runner.submitted == []


def test_tick_ignores_records_created_by_other_schedulers(sessions):
    """Only ImportRecord rows exist in this table — nothing else to touch."""
    _seed(sessions, "a", success_minutes_ago=5, attempt_minutes_ago=5)
    _seed(sessions, "b", success_minutes_ago=120, attempt_minutes_ago=120)
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)

    assert sched.tick() == 1
    assert [k for k, _ in runner.submitted] == ["b"]


# -- loop lifecycle ------------------------------------------------------------------

def test_no_pass_before_first_interval(sessions):
    _seed(sessions, "berserk", success_minutes_ago=120, attempt_minutes_ago=120)
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=0.3,
                                  poll_seconds=0.05)
    sched.start()
    try:
        time.sleep(0.1)
        assert runner.submitted == []  # no catch-up pass right after start
        assert _wait_until(lambda: len(runner.submitted) == 1, timeout=3.0)
    finally:
        sched.stop(timeout=2)
    assert not sched.is_running


def test_periodic_passes_and_stop(sessions):
    _seed(sessions, "berserk", success_minutes_ago=120, attempt_minutes_ago=120)
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=0.2,
                                  poll_seconds=0.05)
    sched.start()
    try:
        # The first pass submits; the key then stays "running" in the stub,
        # so later passes are no-ops — the loop is alive, just deduped.
        assert _wait_until(lambda: len(runner.submitted) == 1, timeout=3.0)
    finally:
        sched.stop(timeout=2)
    assert not sched.is_running


def test_crashing_tick_does_not_kill_loop(sessions):
    _seed(sessions, "berserk", success_minutes_ago=120, attempt_minutes_ago=120)
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=0.2,
                                  poll_seconds=0.05)
    # Break the session factory: the tick raises, the loop must survive.
    def broken_factory():
        raise RuntimeError("simulated db failure")

    sched._session_factory = broken_factory  # noqa: SLF001 - test access
    started_at = time.monotonic()
    sched.start()
    try:
        # Survive at least two loop iterations despite the crash.
        assert _wait_until(lambda: time.monotonic() - started_at > 0.5, timeout=3.0)
        assert sched.is_running
    finally:
        sched.stop(timeout=2)
    assert not sched.is_running


def test_start_is_idempotent(sessions):
    runner = _StubRunner()
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)
    sched.start()
    first_thread = sched._thread  # noqa: SLF001 - test access
    sched.start()
    try:
        assert sched._thread is first_thread  # noqa: SLF001
    finally:
        sched.stop(timeout=2)


# -- FastAPI lifespan wiring ---------------------------------------------------------

def test_auto_init_wires_price_refresh_scheduler(monkeypatch, engine):
    from tests.test_catalog_scheduler import _wired_client

    client, _ = _wired_client(monkeypatch, engine)
    with client:
        sched = client.app.state.price_refresh_scheduler
        assert sched is not None
        assert sched.is_running
    # context exit runs the shutdown: scheduler stopped
    assert not client.app.state.price_refresh_scheduler.is_running


def test_auto_init_disabled_flag_blocks_price_refresh(monkeypatch, engine):
    from tests.test_catalog_scheduler import _wired_client

    client, _ = _wired_client(monkeypatch, engine, price_refresh_enabled=False)
    with client:
        assert client.app.state.price_refresh_scheduler is None


def test_auto_init_false_never_wires_price_refresh(client):
    # every existing API test runs this shape: no scheduler, ever
    assert client.app.state.price_refresh_scheduler is None
