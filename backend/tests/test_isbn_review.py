"""Phase B API: authorization, evidence visibility, decisions and stale versions."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import IsbnAuditResult, IsbnAuditRun, IsbnDecision, IsbnReview, User, Volume
from app.services.isbn_audit import evidence_signature
from app.services.isbn_identity import digest, snapshot
from tests.test_import_service import seed_catalog_series
from tests.test_isbn_audit import ISBN, book
from app.services.isbn_sources import proof


@pytest.fixture
def review(db_session):
    seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=(29,))
    volume = db_session.scalar(select(Volume))
    volume.catalog_released = volume.catalog_present = True
    db_session.commit()
    target = snapshot(volume)
    evidence = [proof(code, code, target, book()) for code in ("kitapyurdu", "bkm")]
    run = IsbnAuditRun(status="COMPLETED", total=1, processed=1, errors=0)
    db_session.add(run); db_session.flush()
    result = IsbnAuditResult(run_id=run.id, volume_id=volume.id, snapshot=target, snapshot_hash=digest(target),
        status="MISSING_ISBN", proposed_isbn=ISBN, reason="İki kaynak, admin onayı gerekiyor.",
        evidence=evidence, evidence_hash=evidence_signature(evidence))
    db_session.add(result); db_session.flush()
    row = IsbnReview(volume_id=volume.id, result_id=result.id, version=1, workflow="REVIEW_PENDING",
                     next_check_at=datetime.utcnow()+timedelta(days=1))
    db_session.add(row); db_session.commit()
    return row


def payload(review, action="KEEP", **kwargs):
    return dict(version=review.version, result_id=review.result_id, action=action, reason="Kanıtları inceledim.") | kwargs


def test_queue_detail_and_history(client, review, db_session):
    assert client.get("/admin/isbn/summary").json()["pending"] == 1
    assert client.get("/admin/isbn/reviews?workflow=REVIEW_PENDING&q=Blue").json()["total"] == 1
    assert client.get("/admin/isbn/reviews?q=unrelated").json()["total"] == 0
    detail = client.get(f"/admin/isbn/reviews/{review.volume_id}").json()
    assert len(detail["evidence"]) == 2 and not detail["stale"]
    response = client.post(f"/admin/isbn/reviews/{review.volume_id}/decisions", json=payload(review))
    assert response.status_code == 200
    assert db_session.get(Volume, review.volume_id).isbn is None
    detail = client.get(f"/admin/isbn/reviews/{review.volume_id}").json()
    assert detail["workflow"] == "REVIEWED"
    assert detail["decisions"][0]["admin"] == "Test admin"
    assert detail["decisions"][0]["reason"] == "Kanıtları inceledim."


def test_stale_tabs_and_metadata_cannot_decide(client, review, db_session):
    body = payload(review, "DEFER")
    assert client.post(f"/admin/isbn/reviews/{review.volume_id}/decisions", json=body).status_code == 200
    assert client.post(f"/admin/isbn/reviews/{review.volume_id}/decisions", json=body).status_code == 409
    db_session.get(Volume, review.volume_id).page_count = 192
    db_session.commit()
    assert client.get(f"/admin/isbn/reviews/{review.volume_id}").json()["stale"]
    db_session.refresh(review)
    assert client.post(f"/admin/isbn/reviews/{review.volume_id}/decisions", json=payload(review)).status_code == 409
    assert len(list(db_session.scalars(select(IsbnDecision)))) == 1


def test_reason_and_protected_routes(client, review, db_session):
    assert client.post(f"/admin/isbn/reviews/{review.volume_id}/decisions", json=payload(review, reason="   ")).status_code == 422
    db_session.get(User, 1).role = "USER"; db_session.commit()
    for method, path in [("get", "/summary"), ("get", "/reviews"), ("post", "/runs"),
                         ("get", f"/reviews/{review.volume_id}")]:
        assert getattr(client, method)("/admin/isbn"+path).status_code == 403
    client.cookies.clear()
    assert client.get("/admin/isbn/summary").status_code == 401
