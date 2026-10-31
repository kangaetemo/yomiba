"""Delete prices of stores that allow keeping them only for a while.

Amazon's associate terms let a site keep and show Amazon pricing for at
most 24 hours (``STORE_PRICE_MAX_AGE_HOURS``). The read side already hides
older listings (``catalog_service.price_expired``); this removes them from
the database: price history and change log rows past the limit, and the
listings themselves once their last check is past it (an import that finds
the product again re-creates the listing).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..models import ListingChange, PriceHistory, Store, StoreListing
from ..utils import utcnow
from .catalog_service import price_max_age

logger = logging.getLogger("yomiba.price_retention")


def purge_expired_prices(session: Session, now: datetime | None = None) -> dict[str, int]:
    """store code -> listings deleted. Commits."""
    now = now or utcnow()
    deleted: dict[str, int] = {}
    for code, limit in price_max_age().items():
        store_id = session.scalar(select(Store.id).where(Store.code == code))
        if store_id is None:
            continue
        cutoff = now - limit
        listing_ids = select(StoreListing.id).where(StoreListing.store_id == store_id)
        expired_ids = listing_ids.where(
            or_(StoreListing.last_checked.is_(None), StoreListing.last_checked < cutoff)
        )
        session.execute(delete(PriceHistory).where(
            PriceHistory.listing_id.in_(listing_ids),
            or_(PriceHistory.checked_at < cutoff, PriceHistory.listing_id.in_(expired_ids)),
        ))
        session.execute(delete(ListingChange).where(
            ListingChange.store_id == store_id, ListingChange.created_at < cutoff
        ))
        result = session.execute(delete(StoreListing).where(StoreListing.id.in_(expired_ids)))
        deleted[code] = result.rowcount or 0
    session.commit()
    if any(deleted.values()):
        logger.info("deleted expired store prices: %s", deleted)
    return deleted
