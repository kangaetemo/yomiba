"""Undo BKM prices that came from product pages instead of BKM's search.

Until 2026-11-06 a BKM listing the search missed was re-checked on its
product page, and the page's JSON-LD price was stored. That price is lower
than what BKM sells for (SEKIRO Yan Hikaye Cilt 1: page 168 TL, shop 210
TL), so listings dropped ~20% and the next search put them back. The
fake drops sit in the price history ("Fiyatı düşenler", normal-price
reference) and some listings still show the page price.

For every BKM price change logged with note "recheck" (change log keeps
30 days) this script:

  * deletes the price history points written while the listing carried a
    page price (from that change until the next search change), and
  * puts the last search price back on listings that still show a page
    price (the search corrects them anyway when it sees them again).

Read-only unless ``--apply``. Run on the server:
  docker compose run --rm --no-deps -T backend python fix_bkm_page_prices.py
  docker compose run --rm --no-deps -T backend python fix_bkm_page_prices.py --apply
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ListingChange, PriceHistory, Store, StoreListing
from app.services.catalog_service import _aware

#: A history point is written just before its change-log row.
_SLACK = timedelta(seconds=5)


@dataclass
class Report:
    listings: int = 0
    history_deleted: int = 0
    restored: list[tuple[StoreListing, int, int]] = field(default_factory=list)


def _page_periods(changes: list[ListingChange]) -> list[tuple[datetime, datetime | None, set[int]]]:
    """(start, end, page prices) for each run of recheck price changes;
    ``end`` is the next search change, None while the run is still current."""
    periods: list[tuple[datetime, datetime | None, set[int]]] = []
    start: datetime | None = None
    prices: set[int] = set()
    for change in changes:
        is_page_price = (change.note == "recheck" and change.new_price is not None
                         and change.new_price != change.old_price)
        if is_page_price:
            if start is None:
                start, prices = _aware(change.created_at), set()
            prices.add(change.new_price)
        elif change.note is None and start is not None and change.new_price is not None:
            periods.append((start, _aware(change.created_at), prices))
            start = None
    if start is not None:
        periods.append((start, None, prices))
    return periods


def repair(session: Session, *, apply: bool) -> Report:
    report = Report()
    store = session.scalar(select(Store).where(Store.code == "bkm"))
    if store is None:
        return report
    volume_ids = session.scalars(select(ListingChange.volume_id).where(
        ListingChange.store_id == store.id, ListingChange.note == "recheck",
        ListingChange.new_price.is_not(None),
    ).distinct()).all()
    for volume_id in volume_ids:
        listing = session.scalar(select(StoreListing).where(
            StoreListing.store_id == store.id, StoreListing.volume_id == volume_id))
        if listing is None:
            continue
        changes = session.scalars(select(ListingChange).where(
            ListingChange.store_id == store.id, ListingChange.volume_id == volume_id,
        ).order_by(ListingChange.created_at, ListingChange.id)).all()
        periods = _page_periods(changes)
        if not periods:
            continue
        report.listings += 1
        for start, end, prices in periods:
            points = session.scalars(select(PriceHistory).where(
                PriceHistory.listing_id == listing.id,
                PriceHistory.price.in_(prices),
                PriceHistory.checked_at >= start - _SLACK,
                *([PriceHistory.checked_at < end - _SLACK] if end else []),
            )).all()
            report.history_deleted += len(points)
            if apply:
                for point in points:
                    session.delete(point)
        start, end, prices = periods[-1]
        if end is None and listing.price in prices:
            # The run's first page change still holds the search price.
            first = next(c for c in changes if c.note == "recheck"
                         and _aware(c.created_at) == start)
            if first.old_price is not None:
                report.restored.append((listing, listing.price, first.old_price))
                if apply:
                    listing.price = first.old_price
    if apply:
        session.commit()
    return report


def main() -> None:
    from app.database import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repair")
    args = parser.parse_args()
    with SessionLocal() as session:
        report = repair(session, apply=args.apply)
        for listing, page, search in report.restored:
            volume = listing.volume
            print(f"{volume.series.title} #{volume.volume_number}: "
                  f"{page / 100:.2f} TL -> {search / 100:.2f} TL  {listing.product_url}")
        print(f"\n{report.listings} BKM ilanı ürün sayfası fiyatı almış; "
              f"{report.history_deleted} geçmiş fiyat noktası silinecek, "
              f"{len(report.restored)} ilanın fiyatı arama fiyatına dönecek.")
        if args.apply:
            print("Uygulandı.")
        elif report.listings:
            print("Uygulamak için aynı komutu --apply ile çalıştır.")


if __name__ == "__main__":
    main()
