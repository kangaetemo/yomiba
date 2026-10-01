"""Public, number-free URL slugs for series ("berserk", not "123").

``Series.slug`` is only unique per publisher, so two publishers' editions of
one title share it. This module derives one globally unique slug per series
without a schema change: catalog series first, then the lowest id keeps the
plain slug; the others get their publisher appended ("berserk-panini"), and a
numeric suffix if that still collides. The mapping is rebuilt from the
database when the series set changes (and at most every 60 s otherwise).
"""

from __future__ import annotations

import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CatalogSeries, Publisher, Series
from ..normalization.text import slugify

_TTL_SECONDS = 60.0
_cache: dict[tuple, tuple[float, dict[int, str], dict[str, int]]] = {}


def _build(session: Session) -> tuple[dict[int, str], dict[str, int]]:
    catalog_ids = set(session.scalars(select(CatalogSeries.series_id)))
    rows = session.execute(
        select(Series.id, Series.slug, Publisher.name)
        .join(Publisher, Publisher.id == Series.publisher_id)
    ).all()
    rows.sort(key=lambda r: (r[0] not in catalog_ids, r[0]))

    by_id: dict[int, str] = {}
    by_slug: dict[str, int] = {}
    for sid, slug, publisher in rows:
        base = slug or "seri"
        candidate = base
        if candidate in by_slug:
            candidate = f"{base}-{slugify(publisher)}"
        n = 2
        while candidate in by_slug:
            candidate = f"{base}-{slugify(publisher)}-{n}"
            n += 1
        by_id[sid] = candidate
        by_slug[candidate] = sid
    return by_id, by_slug


def _maps(session: Session) -> tuple[dict[int, str], dict[str, int]]:
    count, last_id = session.execute(select(func.count(Series.id), func.max(Series.id))).one()
    key = (id(session.get_bind()), count, last_id)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL_SECONDS:
        return hit[1], hit[2]
    by_id, by_slug = _build(session)
    _cache.clear()
    _cache[key] = (now, by_id, by_slug)
    return by_id, by_slug


def slug_for(session: Session, series_id: int) -> str:
    """The public slug of a series (falls back to the id as text)."""
    return _maps(session)[0].get(series_id) or str(series_id)


def slugs_for(session: Session, series_ids) -> dict[int, str]:
    by_id = _maps(session)[0]
    return {sid: by_id.get(sid) or str(sid) for sid in set(series_ids)}


def series_id_for(session: Session, ref: str) -> int | None:
    """Resolve a public slug (or a legacy numeric id) to a series id."""
    by_slug = _maps(session)[1]
    if ref in by_slug:
        return by_slug[ref]
    return int(ref) if ref.isdigit() else None
