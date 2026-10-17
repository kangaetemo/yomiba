"""Admin ISBN tools: health report, per-volume evidence, manual decisions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import IsbnChange, IsbnIssue, SharedIsbn, Store, StoreObservation, User, Volume
from ..services.isbn_health import build_report
from ..services.isbn_resolver import resolve_many, set_admin_isbn, store_votes
from ..utils import from_cents

router = APIRouter(prefix="/admin/isbn", tags=["isbn"], dependencies=[Depends(require_admin)])


@router.get("/health")
def health(session: Session = Depends(get_db)):
    """Read-only ISBN health report (sizes wrong / missing ISBN problems)."""
    return build_report(session)


@router.get("/volumes/{volume_id}")
def volume_evidence(volume_id: int, session: Session = Depends(get_db)):
    """Everything behind a volume's ISBN: catalog value, store observations
    (title-pointed and ISBN-pointed), shared ISBNs, open issue, change log."""
    volume = session.get(Volume, volume_id)
    if volume is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    stores = dict(session.execute(select(Store.id, Store.name)).all())
    observations = session.scalars(select(StoreObservation).where(
        (StoreObservation.title_volume_id == volume_id) | (StoreObservation.isbn_volume_id == volume_id)
        | (StoreObservation.volume_id == volume_id)
    ).order_by(StoreObservation.last_seen.desc()).limit(200))
    issue = session.get(IsbnIssue, volume_id)
    observations = list(observations)
    ids = {i for o in observations for i in (o.title_volume_id, o.isbn_volume_id, o.volume_id) if i}
    labels = {v.id: f"{v.series.title} · Cilt {v.volume_number}"
              for v in session.scalars(select(Volume).where(Volume.id.in_(ids)))} if ids else {}
    return dict(
        volume_id=volume.id, isbn=volume.isbn, isbn_source=volume.isbn_source, catalog_isbn=volume.catalog_isbn,
        shared=[r.isbn for r in session.scalars(select(SharedIsbn).where(SharedIsbn.volume_id == volume_id))],
        votes=store_votes(session, volume_id),
        issue=dict(kind=issue.kind, detail=issue.detail, updated_at=issue.updated_at) if issue else None,
        observations=[dict(store=stores.get(o.store_id), url=o.product_url, title=o.title, isbn=o.isbn,
                           price=from_cents(o.price), in_stock=o.in_stock, rule=o.rule, reason=o.reason,
                           title_volume_id=o.title_volume_id, isbn_volume_id=o.isbn_volume_id,
                           attached_volume_id=o.volume_id, title_volume=labels.get(o.title_volume_id),
                           isbn_volume=labels.get(o.isbn_volume_id), attached_volume=labels.get(o.volume_id),
                           last_seen=o.last_seen) for o in observations],
        changes=[dict(old=c.old_isbn, new=c.new_isbn, source=c.source, reason=c.reason, at=c.created_at)
                 for c in session.scalars(select(IsbnChange).where(IsbnChange.volume_id == volume_id)
                                          .order_by(IsbnChange.id.desc()).limit(50))],
    )


class IsbnDecisionIn(BaseModel):
    isbn: str | None = Field(default=None, max_length=20)
    reason: str = Field(min_length=3, max_length=500)
    #: Add as a shared ISBN (another edition of the same book holds it).
    share: bool = False
    #: Take the ISBN from the volume holding it.
    move: bool = False
    #: Release an earlier admin decision; the resolver decides again.
    automatic: bool = False


@router.post("/volumes/{volume_id}")
def decide(volume_id: int, body: IsbnDecisionIn, user: User = Depends(require_admin),
           session: Session = Depends(get_db)):
    volume = session.get(Volume, volume_id)
    if volume is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    if body.automatic:
        volume.isbn_source = "catalog" if volume.isbn else None
        resolve_many(session, [volume.id])
        session.commit()
        return dict(volume_id=volume.id, isbn=volume.isbn, isbn_source=volume.isbn_source)
    try:
        result = set_admin_isbn(session, volume, body.isbn or None, user_id=user.id,
                                reason=body.reason, share=body.share, move=body.move)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return result
