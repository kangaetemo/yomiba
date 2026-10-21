"""Admin view of what imports changed on store listings.

``ImportService`` writes a ``ListingChange`` row whenever a listing is
created, changes price or stock, switches product or is removed. This
module prunes old rows and groups a time window of them by series, then
volume, for the "Fiyat değişiklikleri" admin page.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ListingChange, Series, Store, Volume
from ..normalization.volume import UNNUMBERED_VOLUME
from ..utils import from_cents, utcnow
from . import series_slugs

#: Filters of the admin page; each tests one change row.
KINDS = {
    "new": lambda c: c.kind == "new" and c.note != "moved",
    "first": lambda c: c.kind == "new" and c.note == "first",
    "price": lambda c: c.kind == "update" and c.old_price is not None and c.new_price is not None
    and c.old_price != c.new_price,
    "stock": lambda c: c.kind == "update" and c.old_in_stock != c.new_in_stock,
    "product": lambda c: c.kind == "product",
    "removed": lambda c: c.kind == "removed" and c.note != "moved",
}

#: Newest rows read for one page; a refresh writes far fewer.
MAX_ROWS = 5000


def prune(session: Session, now: datetime | None = None) -> int:
    days = max(1, get_settings().listing_change_retention_days)
    cutoff = (now or utcnow()) - timedelta(days=days)
    result = session.execute(delete(ListingChange).where(ListingChange.created_at < cutoff))
    session.commit()
    return result.rowcount or 0


def _item(change: ListingChange, stores: dict[int, tuple[str, str]]) -> dict:
    code, name = stores.get(change.store_id, ("", "?"))
    return dict(
        id=change.id, at=change.created_at.isoformat(), kind=change.kind, note=change.note,
        store=name, store_code=code,
        old_price=from_cents(change.old_price), new_price=from_cents(change.new_price),
        old_in_stock=change.old_in_stock, new_in_stock=change.new_in_stock,
        product_url=change.product_url,
    )


def admin_report(session: Session, since: datetime, *, kind: str | None = None,
                 store: str | None = None) -> dict:
    """Changes since ``since``: counts per filter and store, and the rows
    (after the ``kind``/``store`` filters) grouped series → volume, series
    with first-time listings and the most changes first."""
    rows = list(session.scalars(
        select(ListingChange).where(ListingChange.created_at >= since)
        .order_by(ListingChange.created_at.desc(), ListingChange.id.desc()).limit(MAX_ROWS)
    ))
    stores = {sid: (code, name) for sid, code, name in session.execute(select(Store.id, Store.code, Store.name))}
    counts = {key: sum(1 for c in rows if test(c)) for key, test in KINDS.items()}
    by_store: dict[str, int] = {}
    for c in rows:
        code = stores.get(c.store_id, ("",))[0]
        by_store[code] = by_store.get(code, 0) + 1

    test = KINDS.get(kind or "")
    picked = [c for c in rows if (test is None or test(c))
              and (not store or stores.get(c.store_id, ("",))[0] == store)]
    volume_ids = {c.volume_id for c in picked}
    volumes = {
        vid: (sid, number, release) for vid, sid, number, release in session.execute(
            select(Volume.id, Volume.series_id, Volume.volume_number, Volume.release_date)
            .where(Volume.id.in_(volume_ids)))
    } if volume_ids else {}
    series_ids = {v[0] for v in volumes.values()}
    titles = dict(session.execute(select(Series.id, Series.title).where(Series.id.in_(series_ids))).all()) if series_ids else {}
    slugs = series_slugs.slugs_for(session, series_ids) if series_ids else {}

    grouped: dict[int, dict] = {}
    for c in picked:
        if c.volume_id not in volumes:
            continue
        sid, number, release = volumes[c.volume_id]
        serie = grouped.setdefault(sid, dict(
            id=sid, title=titles.get(sid, "?"), path=f"/series/{slugs.get(sid, sid)}",
            latest=c.created_at.isoformat(), first_listings=0, changes=0, volumes={}))
        unnumbered = number == UNNUMBERED_VOLUME
        volume = serie["volumes"].setdefault(c.volume_id, dict(
            id=c.volume_id, number=None if unnumbered else number,
            path=f"{serie['path']}/{'cilt-numarasiz' if unnumbered else f'cilt-{number}'}",
            release_date=release.isoformat() if release else None, changes=[]))
        volume["changes"].append(_item(c, stores))
        serie["changes"] += 1
        if c.kind == "new" and c.note == "first":
            serie["first_listings"] += 1

    series_out = []
    for serie in grouped.values():
        serie["volumes"] = sorted(serie["volumes"].values(),
                                  key=lambda v: (v["number"] is None, -(v["number"] or 0)))
        series_out.append(serie)
    # Series with first-time listings on top, newest activity first.
    series_out.sort(key=lambda s: s["latest"], reverse=True)
    series_out.sort(key=lambda s: s["first_listings"] > 0, reverse=True)
    return dict(
        since=since.isoformat(), total=len(rows), truncated=len(rows) >= MAX_ROWS,
        counts=counts, stores=[dict(code=code, name=name, count=by_store.get(code, 0))
                               for code, name in sorted(stores.values(), key=lambda s: s[1])
                               if by_store.get(code)],
        shown=len(picked), series=series_out,
        kept_since=_iso(session.scalar(select(func.min(ListingChange.created_at)))),
        retention_days=get_settings().listing_change_retention_days,
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
