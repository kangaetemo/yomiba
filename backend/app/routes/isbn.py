"""Authenticated ISBN review centre; audit triggers never mutate the catalogue."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import IsbnAuditResult, IsbnAuditRun, IsbnDecision, IsbnReview, Series, User, Volume
from ..services.isbn_audit import AuditConflict, control_run, create_run, tracked, volume_query
from ..services.isbn_decisions import DecisionError, decide
from ..services.isbn_identity import digest, snapshot
from ..services.isbn_triage import QUEUES, Queue, queue_expression, queue_for

router = APIRouter(prefix="/admin/isbn", tags=["isbn-review"], dependencies=[Depends(require_admin)])


def run_json(run):
    return {key: getattr(run, key) for key in ("id", "status", "started_at", "finished_at", "total", "processed", "errors", "error")} if run else None


@router.get("/summary")
def summary(session: Session = Depends(get_db)):
    counts = dict(session.execute(select(IsbnAuditResult.status, func.count()).join(
        IsbnReview, IsbnReview.result_id == IsbnAuditResult.id).join(Volume, Volume.id == IsbnReview.volume_id).where(
        tracked(), Volume.catalog_present.is_not(False)).group_by(IsbnAuditResult.status)).all())
    queues = dict.fromkeys(QUEUES, 0)
    queues.update(dict(session.execute(select(queue_expression(), func.count()).select_from(IsbnReview).join(
        IsbnAuditResult, IsbnReview.result_id == IsbnAuditResult.id).join(Volume, Volume.id == IsbnReview.volume_id).where(
        tracked(), Volume.catalog_present.is_not(False)).group_by(queue_expression())).all()))
    total = session.scalar(select(func.count()).select_from(Volume).where(tracked(), Volume.catalog_present.is_not(False)))
    latest = session.scalar(select(IsbnAuditRun).order_by(IsbnAuditRun.id.desc()).limit(1))
    return dict(counts=counts, queues=queues, pending=queues["APPROVAL"], scanned=sum(counts.values()), total=total,
                run=run_json(latest), approval_enabled=approval_enabled(session))


def approval_enabled(session):
    from sqlalchemy import inspect
    return inspect(session.get_bind()).has_table("isbn_approval_permits")


@router.post("/runs", status_code=202)
def start(request: Request, user: User = Depends(require_admin), session: Session = Depends(get_db)):
    return start_run(request, session, user.id)


def start_run(request, session, admin_id, volume_id=None):
    try:
        run = create_run(session, admin_id, volume_id=volume_id)
    except AuditConflict as exc:
        raise HTTPException(409, str(exc)) from None
    worker = getattr(request.app.state, "isbn_audit_worker", None)
    if worker: worker.wake()
    return run_json(run)


@router.post("/runs/{run_id}/{action}")
def control(run_id: int, action: Literal["pause", "resume", "stop"], request: Request, session: Session = Depends(get_db)):
    try:
        run = control_run(session, run_id, action)
    except AuditConflict as exc:
        raise HTTPException(409, str(exc)) from None
    worker = getattr(request.app.state, "isbn_audit_worker", None)
    if worker: worker.wake()
    return run_json(run)


@router.get("/reviews")
def reviews(status: str | None = None, workflow: Literal["REVIEW_PENDING", "REVIEWED"] | None = None,
            queue: Queue | None = None,
            q: str = Query("", max_length=200), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
            session: Session = Depends(get_db)):
    query = select(IsbnReview, IsbnAuditResult, Volume.isbn).join(IsbnAuditResult, IsbnReview.result_id == IsbnAuditResult.id).join(
        Volume, Volume.id == IsbnReview.volume_id).join(Series, Series.id == Volume.series_id).where(
        tracked(), Volume.catalog_present.is_not(False))
    if status: query = query.where(IsbnAuditResult.status == status)
    if workflow: query = query.where(IsbnReview.workflow == workflow)
    if queue: query = query.where(queue_expression() == queue)
    if q: query = query.where(Series.title.icontains(q, autoescape=True))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(query.order_by(IsbnReview.volume_id).offset(offset).limit(limit)).all()
    return dict(total=total, items=[review_json(r, a, isbn) for r, a, isbn in rows])


def review_json(review, result, current_isbn):
    return dict(volume_id=review.volume_id, version=review.version, workflow=review.workflow, queue=queue_for(review, result),
                result_id=result.id, status=result.status, proposed_isbn=result.proposed_isbn,
                reason=result.reason, checked_at=result.checked_at, snapshot=result.snapshot, current_isbn=current_isbn)


@router.get("/reviews/{volume_id}")
def detail(volume_id: int, session: Session = Depends(get_db)):
    review = session.get(IsbnReview, volume_id)
    if not review: raise HTTPException(404, "İnceleme bulunamadı.")
    result = session.get(IsbnAuditResult, review.result_id)
    volume = session.scalar(volume_query().where(Volume.id == volume_id))
    history = session.execute(select(IsbnDecision, User.display_name).join(User, User.id == IsbnDecision.admin_id).where(
        IsbnDecision.volume_id == volume_id).order_by(IsbnDecision.id.desc())).all()
    return dict(**review_json(review, result, volume.isbn if volume else None), evidence=result.evidence,
                stale=not volume or digest(snapshot(volume)) != result.snapshot_hash,
                current=snapshot(volume) if volume else None,
                approval_enabled=approval_enabled(session),
                decisions=[dict(id=d.id, action=d.action, reason=d.reason, admin=name,
                                old_isbn=d.old_isbn, new_isbn=d.new_isbn, decided_at=d.decided_at,
                                result_id=d.result_id, review_version=d.review_version) for d, name in history])


@router.post("/reviews/{volume_id}/recheck", status_code=202)
def recheck(volume_id: int, request: Request, user: User = Depends(require_admin), session: Session = Depends(get_db)):
    return start_run(request, session, user.id, volume_id)


class DecisionBody(BaseModel):
    version: int = Field(ge=1)
    result_id: int = Field(ge=1)
    action: Literal["KEEP", "ACCEPT", "MANUAL", "DEFER"]
    reason: str = Field(min_length=3, max_length=2000)
    isbn: str | None = Field(default=None, max_length=30)


@router.post("/reviews/{volume_id}/decisions")
def decision(volume_id: int, body: DecisionBody, user: User = Depends(require_admin), session: Session = Depends(get_db)):
    try:
        row = decide(session, admin_id=user.id, volume_id=volume_id, **body.model_dump())
    except DecisionError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    return dict(id=row.id, action=row.action, old_isbn=row.old_isbn, new_isbn=row.new_isbn)
