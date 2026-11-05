"""Admin: special sets (box sets / bundles linked to catalog series)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import CatalogSeries, Series, SpecialSet
from ..services import series_slugs, special_sets
from ..utils import from_cents

router = APIRouter(tags=["special-sets"], dependencies=[Depends(require_admin)])


def _out(session: Session, s: SpecialSet) -> dict:
    ids = [link.series_id for link in s.links]
    titles = dict(session.execute(select(Series.id, Series.title).where(Series.id.in_(ids))).tuples().all()) if ids else {}
    slugs = series_slugs.slugs_for(session, ids) if ids else {}
    return {
        "id": s.id, "title": s.title, "store": s.store.name, "product_url": s.product_url,
        "image_url": s.image_url, "price": from_cents(s.price), "in_stock": s.in_stock,
        "preorder": s.preorder, "active": s.active,
        "last_checked": s.last_checked, "check_error": s.check_error,
        "series": [{"id": i, "title": titles.get(i, "?"), "slug": slugs.get(i)} for i in ids],
    }


def _get(session: Session, set_id: int) -> SpecialSet:
    special = session.get(SpecialSet, set_id)
    if special is None:
        raise HTTPException(status_code=404, detail="Set bulunamadı.")
    return special


def _ids(value) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail="series_ids bir liste olmalı.")
    try:
        return [int(v) for v in value]
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="series_ids sayı olmalı.") from None


@router.get("/admin/special-sets")
def list_sets(session: Session = Depends(get_db)) -> dict:
    rows = session.scalars(select(SpecialSet).order_by(SpecialSet.created_at.desc()))
    return {"items": [_out(session, s) for s in rows]}


@router.get("/admin/special-sets/series")
def series_options(session: Session = Depends(get_db)) -> dict:
    """Catalog series to link a set to (id, title, publisher)."""
    rows = session.execute(
        select(Series.id, Series.title).where(Series.id.in_(select(CatalogSeries.series_id)))
        .order_by(Series.title)
    ).all()
    return {"items": [{"id": i, "title": t} for i, t in rows]}


@router.post("/admin/special-sets", status_code=201)
def create_set(payload: dict = Body(...), session: Session = Depends(get_db)) -> dict:
    try:
        special = special_sets.create(
            session, str(payload.get("product_url") or ""), _ids(payload.get("series_ids")) or [],
            title=payload.get("title"), preorder=bool(payload.get("preorder")),
        )
    except special_sets.SpecialSetError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _out(session, special)


@router.patch("/admin/special-sets/{set_id}")
def update_set(set_id: int, payload: dict = Body(...), session: Session = Depends(get_db)) -> dict:
    special = _get(session, set_id)
    try:
        special_sets.update(
            session, special, title=payload.get("title"), series_ids=_ids(payload.get("series_ids")),
            preorder=payload.get("preorder") if isinstance(payload.get("preorder"), bool) else None,
            active=payload.get("active") if isinstance(payload.get("active"), bool) else None,
        )
    except special_sets.SpecialSetError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _out(session, special)


@router.post("/admin/special-sets/{set_id}/refresh")
def refresh_set(set_id: int, session: Session = Depends(get_db)) -> dict:
    special = _get(session, set_id)
    special_sets.refresh(session, special)
    session.commit()
    return _out(session, special)


@router.delete("/admin/special-sets/{set_id}")
def delete_set(set_id: int, session: Session = Depends(get_db)) -> dict:
    special = _get(session, set_id)
    session.delete(special)
    session.commit()
    return {"deleted": set_id}
