"""GET /price-drops — recently observed price drops across all listings.

Data source is the append-only ``price_history`` log: every time a listing's
price changes, a new row is written. A "drop" is a row whose price is lower
than the previous row for the same listing (window-function LAG), so the
result reflects only changes the app actually observed — no store-side
"discount" badges are involved, and nothing here triggers a scrape.
Read-only by design.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import series_slugs
from ..services.covers import cover_url
from ..utils import from_cents, utcnow

router = APIRouter(tags=["drops"])


def _as_iso(value: object) -> str:
    """Raw SQL bypasses SQLAlchemy's type coercion, so SQLite hands back the
    stored text as a naive string — normalize it to a tz-aware ISO timestamp
    (all stored times are UTC)."""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

_DROP_SQL = text(
    """
    WITH deltas AS (
        SELECT
            h.listing_id,
            h.price,
            h.checked_at,
            LAG(h.price) OVER (
                PARTITION BY h.listing_id ORDER BY h.id
            ) AS prev_price
        FROM price_history h
    )
    SELECT
        d.listing_id,
        d.price,
        d.prev_price,
        d.checked_at,
        sl.volume_id,
        sl.in_stock,
        sl.product_url,
        v.cover_key,
        v.volume_number,
        s.id AS series_id,
        s.title AS series_title,
        st.name AS store_name,
        (SELECT MIN(p.price) FROM price_history p WHERE p.listing_id = d.listing_id) AS lowest_seen
    FROM deltas d
    JOIN store_listings sl ON sl.id = d.listing_id
    JOIN volumes v ON v.id = sl.volume_id
    JOIN series s ON s.id = v.series_id
    JOIN stores st ON st.id = sl.store_id
    WHERE d.prev_price IS NOT NULL
      AND d.price < d.prev_price
      AND v.volume_number >= 0
      AND d.checked_at >= :cutoff
    ORDER BY d.checked_at DESC, d.listing_id DESC
    """
)


@router.get("/price-drops")
def price_drops(
    hours: int = Query(default=24, ge=1, le=24 * 14, description="Bakılacak pencere (saat)"),
    limit: int = Query(default=12, ge=1, le=50, description="Dönüş yapılacak azami indirim sayısı"),
    session: Session = Depends(get_db),
) -> dict:
    """Latest price drops observed within the window, newest first."""
    cutoff = utcnow() - timedelta(hours=hours)
    rows = session.execute(_DROP_SQL, {"cutoff": cutoff}).fetchmany(limit)
    slugs = series_slugs.slugs_for(session, [r.series_id for r in rows])
    drops = []
    for r in rows:
        drops.append(
            {
                "listing_id": r.listing_id,
                "volume_id": r.volume_id,
                "series_id": r.series_id,
                "series_slug": slugs[r.series_id],
                "series_title": r.series_title,
                "volume_number": r.volume_number,
                "store_name": r.store_name,
                "old_price": from_cents(r.prev_price),
                "new_price": from_cents(r.price),
                "drop_pct": round((r.prev_price - r.price) * 100.0 / r.prev_price),
                # The lowest price this store listing has ever been seen at.
                "lowest_ever": r.lowest_seen is not None and r.price <= r.lowest_seen,
                "changed_at": _as_iso(r.checked_at),
                "in_stock": bool(r.in_stock),
                "product_url": r.product_url,
                # Our own copy of the cover, never the store's image URL.
                "image_url": cover_url(r.cover_key),
            }
        )
    return {
        "drops": drops,
        "window_hours": hours,
        "generated_at": utcnow().isoformat(),
    }
