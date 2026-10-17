"""Optional development dataset.

Creates a small, clearly-labelled demo dataset (three stores, one series,
three volumes, a bit of price history) by running synthetic ``SearchResult``
objects through the real ImportService — i.e. the exact same code path a
live scrape uses. No fake prices are baked into application logic; this
script exists only to make local UI development possible offline.

Run from the ``backend/`` directory:

    python -m app.dev_data            # add demo data to the current database
    python -m app.dev_data --fresh    # drop all catalog rows first (stores kept)

Never run this against production data.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from decimal import Decimal

from app.database import SessionLocal, init_db
from app.models import PriceHistory, StoreListing
from app.normalization import parse_volume_title
from app.scrapers import SearchResult
from app.seed import seed_stores
from app.services.import_service import ImportService
from app.utils import to_cents, utcnow

DEMO_ISBN_1 = "9780000000011"  # demo ISBNs: reserved 000 ranges, clearly fake


def _result(
    store: str,
    store_name: str,
    title: str,
    price: Decimal,
    isbn: str | None = None,
    publisher: str | None = None,
    in_stock: bool = True,
    image: str | None = None,
) -> SearchResult:
    parsed = parse_volume_title(title)
    return SearchResult(
        store_id=store,
        store_name=store_name,
        title=title,
        product_url=f"https://example.invalid/demo/{store}/{title.lower().replace(' ', '-')}",
        series_title=parsed.base_title or None,
        volume_number=parsed.volume_number,
        isbn=isbn,
        publisher=publisher,
        price=price,
        currency="TRY",
        in_stock=in_stock,
        image_url=image,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh", action="store_true", help="wipe catalog data first")
    args = parser.parse_args()

    from app.models import Series, Store, Volume  # imported after models registered

    init_db()
    session = SessionLocal()
    try:
        seed_stores(session)

        if args.fresh:
            for model in (PriceHistory, StoreListing, Volume, Series):
                session.query(model).delete()
            session.commit()
            print("Wiped catalog data (stores kept).")

        service = ImportService(session)
        results = [
            # Volume 1: the classic three-store comparison.
            _result("bkm", "BKM Kitap", "Berserk 1", Decimal("169"), isbn=DEMO_ISBN_1,
                    publisher="Athica Yayınları", image="https://example.invalid/demo/b1.jpg"),
            _result("dr", "D&R", "Berserk 1", Decimal("260"), isbn=DEMO_ISBN_1,
                    publisher="Athica Yayınları"),
            _result("amazon", "Amazon", "Berserk 1", Decimal("163.54"), isbn=DEMO_ISBN_1,
                    publisher="Athica Yayınları"),
            # Volume 2: two stores.
            _result("bkm", "BKM Kitap", "Berserk 2", Decimal("220"),
                    publisher="Athica Yayınları", image="https://example.invalid/demo/b2.jpg"),
            _result("dr", "D&R", "Berserk 2", Decimal("235"),
                    publisher="Athica Yayınları"),
            # Volume 3: one store, out of stock.
            _result("amazon", "Amazon", "Berserk 3", Decimal("189"),
                    publisher="Athica Yayınları", in_stock=False,
                    image="https://example.invalid/demo/b3.jpg"),
        ]
        for result in results:
            service.import_result(result)
            session.commit()

        # A little price history for the Amazon volume-1 listing so the
        # history endpoint has something interesting to show.
        berserk = (
            session.query(Series).filter(Series.normalized_title == "berserk").first()
        )
        volume1 = (
            session.query(Volume)
            .filter(Volume.series_id == berserk.id, Volume.volume_number == 1)
            .first()
            if berserk
            else None
        )
        amazon = session.query(Store).filter(Store.code == "amazon").first()
        listing = (
            session.query(StoreListing)
            .filter(
                StoreListing.volume_id == volume1.id,
                StoreListing.store_id == amazon.id,
            )
            .first()
            if volume1
            else None
        )
        existing_points = (
            session.query(PriceHistory)
            .filter(PriceHistory.listing_id == listing.id)
            .count()
            if listing
            else 0
        )
        if listing is not None and existing_points == 1:
            session.add(
                PriceHistory(
                    listing_id=listing.id,
                    price=to_cents("179.90"),
                    checked_at=utcnow() - timedelta(days=30),
                )
            )
            session.commit()

        series_count = session.query(Series).count()
        volume_count = session.query(Volume).count()
        listing_count = session.query(StoreListing).count()
        print(
            f"Demo data ready: {series_count} series, {volume_count} volumes, "
            f"{listing_count} listings. Search for 'berserk'."
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
