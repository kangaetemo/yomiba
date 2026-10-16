"""Bulk conflict selection uses current reviews, never historical results or client claims."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import CatalogSeries, IsbnAuditItem, IsbnAuditResult, IsbnAuditRun, IsbnDecision, IsbnReview, User, Volume
from app.services.isbn_audit import IsbnAuditWorker, evidence_signature
from app.services.isbn_identity import digest, snapshot
from tests.test_import_service import seed_catalog_series
from tests.test_isbn_audit import ISBN, book
from app.services.isbn_sources import proof


@pytest.fixture
def catalogue(db_session):
    run=IsbnAuditRun(status="COMPLETED",total=8,processed=8,errors=0)
    db_session.add(run);db_session.flush()
    ids={}
    for name,status in [("conflict","CONFLICT"),("approval","CONFLICT"),("verified","VERIFIED"),
                        ("partial","INSUFFICIENT_EVIDENCE"),("upcoming","SKIPPED_UPCOMING"),
                        ("inactive","CONFLICT"),("untracked","CONFLICT"),("resolved","CONFLICT")]:
        series=seed_catalog_series(db_session,name,"Synthetic Publisher",volumes=(1,))
        volume=db_session.scalar(select(Volume).where(Volume.series_id==series.id))
        volume.catalog_present=name!="inactive";volume.catalog_released=name!="upcoming"
        db_session.flush();target=snapshot(volume)
        result=IsbnAuditResult(run_id=run.id,volume_id=volume.id,snapshot=target,snapshot_hash=digest(target),
            status=status,proposed_isbn=ISBN if name=="approval" else None,reason="Synthetic",evidence=[],evidence_hash=evidence_signature([]))
        db_session.add(result);db_session.flush()
        review=IsbnReview(volume_id=volume.id,result_id=result.id,version=1,workflow="REVIEW_PENDING",next_check_at=datetime.now()+timedelta(days=1))
        db_session.add(review);db_session.flush()
        if name=="resolved":
            new_run=IsbnAuditRun(status="COMPLETED",total=1,processed=1,errors=0)
            db_session.add(new_run);db_session.flush()
            newer=IsbnAuditResult(run_id=new_run.id,volume_id=volume.id,snapshot=target,snapshot_hash=digest(target),
                status="VERIFIED",proposed_isbn=ISBN,reason="Newer result",evidence=[],evidence_hash=evidence_signature([]))
            db_session.add(newer);db_session.flush();review.result_id=newer.id
        if name=="untracked":
            db_session.delete(db_session.scalar(select(CatalogSeries).where(CatalogSeries.series_id==series.id)))
        ids[name]=volume.id
    db_session.commit()
    return ids


def items(session,run_id):
    return list(session.scalars(select(IsbnAuditItem.volume_id).where(IsbnAuditItem.run_id==run_id).order_by(IsbnAuditItem.volume_id)))


def test_all_conflicts_include_all_pages_but_only_current_active_conflicts(client,db_session,catalogue):
    page=client.get("/admin/isbn/reviews?status=CONFLICT&limit=1").json()
    assert page["total"]==2 and len(page["items"])==1
    before=[(r.volume_id,r.result_id,r.version) for r in db_session.scalars(select(IsbnReview))]
    response=client.post("/admin/isbn/runs/conflicts",json={})
    assert response.status_code==202 and response.json()["total"]==2
    assert items(db_session,response.json()["id"])==[catalogue["conflict"],catalogue["approval"]]
    assert before==[(r.volume_id,r.result_id,r.version) for r in db_session.scalars(select(IsbnReview))]
    assert all(v.isbn is None for v in db_session.scalars(select(Volume)))
    assert db_session.scalar(select(IsbnDecision.id)) is None


def test_selected_conflicts_deduplicate_and_start_one_durable_run(client,db_session,catalogue):
    vid=catalogue["conflict"]
    response=client.post("/admin/isbn/runs/conflicts",json={"volume_ids":[vid,vid]})
    assert response.status_code==202 and response.json()["total"]==1
    assert items(db_session,response.json()["id"])==[vid]
    assert client.post("/admin/isbn/runs/conflicts",json={}).status_code==409
    assert client.post(f'/admin/isbn/runs/{response.json()["id"]}/pause').status_code==200
    assert client.post("/admin/isbn/runs/conflicts",json={}).status_code==409


@pytest.mark.parametrize("invalid",["verified","partial","upcoming","inactive","untracked","resolved","missing"])
def test_stale_or_non_conflicting_selection_is_rejected_atomically(client,db_session,catalogue,invalid):
    before=len(list(db_session.scalars(select(IsbnAuditRun.id))))
    response=client.post("/admin/isbn/runs/conflicts",json={"volume_ids":[catalogue["conflict"],catalogue.get(invalid,999999)]})
    assert response.status_code==409
    assert len(list(db_session.scalars(select(IsbnAuditRun.id))))==before
    assert not list(db_session.scalars(select(IsbnAuditItem)))


@pytest.mark.parametrize("body",[{"volume_ids":[]},{"volume_ids":[0]},{"volume_ids":[-1]},
    {"volume_ids":[True]},{"volume_ids":["1"]},{"volume_ids":[1]*5001},{"typo_ids":[1]}])
def test_bulk_request_rejects_empty_invalid_or_unknown_selection(client,body):
    assert client.post("/admin/isbn/runs/conflicts",json=body).status_code==422


def test_no_conflicts_does_not_start_a_full_catalogue_run(client,db_session):
    assert client.post("/admin/isbn/runs/conflicts",json={}).status_code==409
    assert db_session.scalar(select(IsbnAuditRun.id)) is None


def test_bulk_recheck_requires_admin(client,db_session):
    db_session.get(User,1).role="USER";db_session.commit()
    assert client.post("/admin/isbn/runs/conflicts",json={}).status_code==403
    client.cookies.clear()
    assert client.post("/admin/isbn/runs/conflicts",json={}).status_code==401


def test_bulk_worker_rechecks_selected_volumes_and_preserves_isbns(client,db_session,engine,catalogue):
    from sqlalchemy.orm import sessionmaker
    vid=catalogue["conflict"]
    response=client.post("/admin/isbn/runs/conflicts",json={"volume_ids":[vid]})
    class Source:
        def __init__(self,code):self.code=self.group=code
        def collect(self,target):
            return [proof(self.code,self.group,target,book(title="conflict 1",publisher="Synthetic Publisher"))]
    worker=IsbnAuditWorker(sessionmaker(bind=engine,expire_on_commit=False),source_factory=lambda:(None,[Source("bkm"),Source("kitapsepeti")]))
    worker.run_pending();db_session.expire_all()
    run=db_session.get(IsbnAuditRun,response.json()["id"])
    assert run.status=="COMPLETED" and run.processed==run.total==1
    updated=db_session.get(IsbnReview,vid)
    assert updated.version==2 and db_session.get(IsbnAuditResult,updated.result_id).run_id==run.id
    assert db_session.get(Volume,vid).isbn is None
    assert db_session.get(IsbnReview,catalogue["approval"]).version==1
    assert db_session.scalar(select(IsbnDecision.id)) is None
