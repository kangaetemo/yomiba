"""Bounded background price-import worker regressions."""

from __future__ import annotations

import threading

from sqlalchemy.orm import sessionmaker

from app.services.background_import import BackgroundImportRunner


def test_fixed_workers_and_bounded_queue(engine):
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    runner = BackgroundImportRunner(sessions, max_concurrent=2, queue_capacity=3)
    release = threading.Event()
    both_active = threading.Event()
    lock = threading.Lock()
    active = 0
    peak = 0
    calls = []

    def execute(key, query):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append(key)
            if active == 2:
                both_active.set()
        try:
            assert release.wait(5)
        finally:
            with lock:
                active -= 1

    runner._execute = execute
    try:
        assert runner.submit("0", "0")
        assert runner.submit("1", "1")
        assert both_active.wait(5)
        assert all(runner.submit(str(i), str(i)) for i in range(2, 5))
        assert runner.queued_count == 3
        assert not runner.submit("5", "5")
        assert not runner.submit("2", "2")  # queued duplicate
        assert len(runner._workers) == 2
        assert peak == 2
    finally:
        release.set()
        for i in range(5):
            runner.wait_for(str(i), 5)
        runner.shutdown(5)
    assert len(calls) == 5
    assert peak <= 2


def test_failed_job_does_not_stop_other_queued_jobs(engine):
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    runner = BackgroundImportRunner(sessions, max_concurrent=1, queue_capacity=2)
    calls = []

    def execute(key, query):
        calls.append(key)
        if key == "bad":
            raise RuntimeError("store unavailable")

    runner._execute = execute
    try:
        assert runner.submit("bad", "bad")
        assert runner.submit("good", "good")
        assert runner.wait_for("bad", 5)
        assert runner.wait_for("good", 5)
    finally:
        runner.shutdown(5)
    assert calls == ["bad", "good"]


def test_startup_recovers_stale_running_record(engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.config import Settings
    from app.models import ImportRecord
    from app.main import create_app
    from app import database, main

    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as session:
        session.add(ImportRecord(normalized_query="stale", last_query="stale",
                                 status="running"))
        session.commit()

    monkeypatch.setattr(database, "SessionLocal", sessions)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "init_db", lambda: None)
    monkeypatch.setattr(main, "check_database_ready", lambda _engine, **_kwargs: None)
    monkeypatch.setattr(main, "get_settings", lambda: Settings(
        database_url=str(engine.url),
        catalog_sync_enabled=False, price_refresh_enabled=False
    ))
    with TestClient(create_app(auto_init=True)):
        pass

    with sessions() as session:
        record = session.scalar(select(ImportRecord).where(
            ImportRecord.normalized_query == "stale"
        ))
        assert record.status == "failed"
        assert record.error


def _catalog(sessions, *titles):
    from app.models import CatalogSeries, Publisher, Series

    with sessions() as session:
        pub = Publisher(name="Test", normalized_name="test")
        session.add(pub)
        session.flush()
        for title in titles:
            series = Series(publisher_id=pub.id, title=title, normalized_title=title, slug=title)
            session.add(series)
            session.flush()
            session.add(CatalogSeries(series_id=series.id, mangakol_slug=title))
        session.commit()


def _blocking_runner(sessions, workers=2):
    runner = BackgroundImportRunner(sessions, max_concurrent=workers, queue_capacity=10)
    release = threading.Event()
    started = []
    lock = threading.Lock()

    def execute(key, query):
        with lock:
            started.append(key)
        assert release.wait(5)

    runner._execute = execute
    return runner, release, started


def _wait(predicate, timeout=5.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_cancel_drops_queued_series_and_lets_running_ones_finish(engine):
    from app.services.price_refresh_scheduler import PriceRefreshScheduler

    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    _catalog(sessions, "a", "b", "c", "d", "e")
    runner, release, started = _blocking_runner(sessions)
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)
    try:
        assert sched.manual_refresh()
        assert _wait(lambda: len(runner.active_keys()) == 2)
        assert sched.cancel()
        status = sched.status()
        assert status["cancelling"] is True
        assert status["queued"] == 0 and status["pending"] == 0
        assert status["running"] == 2
        assert runner.queued_count == 0
        assert not sched.manual_refresh()  # still stopping
        release.set()
        assert _wait(lambda: not runner.active_keys())
        sched.tick()
        status = sched.status()
        assert status["current_cycle_started_at"] is None
        assert status["cancelling"] is False
        assert status["last_cycle_cancelled_at"] is not None
        assert status["last_cycle_completed_at"] is None
        assert status["next_scheduled_refresh"] is not None
        assert len(started) == 2  # the three queued series never ran
        assert not sched.cancel()  # nothing left to stop
    finally:
        release.set()
        runner.shutdown(5)


def test_restart_starts_a_new_cycle_after_running_series_finish(engine):
    from app.services.price_refresh_scheduler import PriceRefreshScheduler

    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    _catalog(sessions, "a", "b", "c", "d")
    runner, release, started = _blocking_runner(sessions, workers=1)
    sched = PriceRefreshScheduler(runner, sessions, interval_seconds=3600)
    try:
        assert sched.manual_refresh()
        assert _wait(lambda: len(runner.active_keys()) == 1)
        first_start = sched.status()["current_cycle_started_at"]
        assert sched.cancel(restart=True)
        assert sched.status()["restart_pending"] is True
        release.set()
        assert _wait(lambda: not runner.active_keys())
        sched.tick()
        status = sched.status()
        assert status["current_cycle_started_at"] is not None
        assert status["current_cycle_started_at"] != first_start
        assert status["current_cycle_mode"] == "full"
        assert status["restart_pending"] is False
        assert status["cancelling"] is False
        assert status["last_cycle_cancelled_at"] is not None
        # The series scraped before the stop is skipped only if it was a
        # real success; the stub job wrote no record, so all are queued.
        assert _wait(lambda: len(started) >= 4)
    finally:
        release.set()
        runner.shutdown(5)
