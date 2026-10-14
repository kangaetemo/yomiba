from datetime import datetime, timedelta, timezone

import pytest

from app.services import catalog_state
from app.services.catalog_scheduler import CatalogSyncScheduler
from tests.test_catalog_scheduler import _Recorder, _wait_until


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "catalog-state.json"
    monkeypatch.setattr(catalog_state, "state_path", lambda: path)
    return path


def test_success_keeps_due_time_across_restarts(state_file):
    now = datetime.now(timezone.utc)
    catalog_state.record_start()
    catalog_state.record_finish({"status": "success", "finished_at": now.isoformat()})
    assert catalog_state.next_delay(86400, now=now + timedelta(hours=20)) == 14400
    assert catalog_state.next_delay(86400, now=now + timedelta(hours=25)) == 0


def test_failed_and_interrupted_runs_retry_in_one_hour(state_file):
    catalog_state.record_start()
    started = datetime.fromisoformat(catalog_state.read_state()["last_attempt_at"])
    assert catalog_state.next_delay(86400, now=started + timedelta(minutes=30)) == 1800
    catalog_state.record_finish({"status": "failed", "finished_at": started.isoformat()})
    assert catalog_state.next_delay(86400, now=started + timedelta(hours=2)) == 0


def test_missing_or_corrupt_state_catches_up(state_file):
    assert catalog_state.next_delay(86400) == 0
    state_file.write_text("broken json")
    assert catalog_state.next_delay(86400) == 0
    state_file.write_text('{"last":null,"last_success_at":"broken date"}')
    assert catalog_state.next_delay(86400) == 0


def test_scheduler_can_catch_up_immediately():
    rec = _Recorder()
    sched = CatalogSyncScheduler(rec, interval_seconds=86400, initial_delay_seconds=0)
    sched.start()
    try:
        assert _wait_until(lambda: rec.calls == 1)
    finally:
        sched.stop(timeout=2)
