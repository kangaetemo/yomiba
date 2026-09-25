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
