"""GET /import/records — admin view of the import-attempt history."""

from __future__ import annotations

from app.models import ImportRecord
from app.utils import utcnow
from datetime import timedelta


def _record(session, key, **kw) -> ImportRecord:
    now = utcnow()
    record = ImportRecord(
        normalized_query=key,
        last_query=kw.get("last_query", key),
        status=kw.get("status", "success"),
        last_attempt_at=kw.get("last_attempt_at", now),
        last_success_at=kw.get("last_success_at", now),
        stores_ok=kw.get("stores_ok", 3),
        stores_failed=kw.get("stores_failed", 0),
        results_found=kw.get("results_found", 10),
        created=kw.get("created", 0),
        updated=kw.get("updated", 0),
        error=kw.get("error"),
    )
    session.add(record)
    return record


def test_records_empty(client, db_session):
    res = client.get("/import/records")
    assert res.status_code == 200
    assert res.json() == []


def test_records_most_recent_first_and_fields(client, db_session):
    now = utcnow()
    _record(db_session, "frieren", last_attempt_at=now - timedelta(hours=2))
    _record(
        db_session, "berserk", last_query="Berserk",
        last_attempt_at=now, created=1, updated=5, results_found=40,
    )
    _record(
        db_session, "kizil", status="failed",
        last_attempt_at=now - timedelta(minutes=5),
        last_success_at=None, stores_ok=0, stores_failed=2,
        error="amazon: blocked",
    )
    db_session.commit()

    body = client.get("/import/records").json()
    assert [r["normalized_query"] for r in body] == ["berserk", "kizil", "frieren"]
    assert body[0]["last_query"] == "Berserk"
    assert body[0]["created"] == 1
    assert body[0]["updated"] == 5
    failed = body[1]
    assert failed["status"] == "failed"
    assert failed["last_success_at"] is None
    assert "amazon" in failed["error"]


def test_records_limit_and_never_attempted_sink(client, db_session):
    now = utcnow()
    for i in range(5):
        _record(db_session, f"q{i}", last_attempt_at=now - timedelta(minutes=i))
    # a record that exists but was never attempted (no timestamps)
    _record(db_session, "ghost", status="running", last_attempt_at=None,
            last_success_at=None)
    db_session.commit()

    body = client.get("/import/records", params={"limit": 3}).json()
    assert [r["normalized_query"] for r in body] == ["q0", "q1", "q2"]

    full = client.get("/import/records").json()
    assert full[-1]["normalized_query"] == "ghost"  # NULL timestamps sink


def test_records_limit_bounds_rejected(client):
    assert client.get("/import/records", params={"limit": 0}).status_code == 422
    assert client.get("/import/records", params={"limit": 201}).status_code == 422
