"""Multi-printing dedup regression tests.

A store may list several printings of the same volume (duplicate offers) as
separate products — e.g. BKM sells "Titana Saldırısı: Çöküşten Önce 3" under
two ISBNs at two prices. A volume has exactly one listing per store, so one
import run must not flip the listing's price between the printings (that
fabricates price history and fake "drops"). Within a single run the cheapest
priced printing wins; different series (e.g. two publishers of the same
title) must still import independently.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models import (
    CatalogSeries,
    PriceHistory,
    Publisher,
    Series,
    Store,
    StoreListing,
    Volume,
)
from app.normalization import parse_volume_title
from app.normalization.text import normalize_publisher, normalize_text
from app.scrapers import SearchResult
from app.services.import_service import ImportAction, ImportService
from tests.helpers import RecordingScraper


def _seed_series(
    db_session,
    *,
    title: str,
    publisher_name: str,
    volume_number: int = 1,
) -> Volume:
    publisher = Publisher(
        name=publisher_name, normalized_name=normalize_publisher(publisher_name)
    )
    db_session.add(publisher)
    db_session.flush()
    slug = title.lower().replace(" ", "-")
    series = Series(
        publisher_id=publisher.id,
        title=title,
        slug=slug,
        normalized_title=normalize_text(title),
    )
    db_session.add(series)
    db_session.flush()
    db_session.add(CatalogSeries(series_id=series.id, mangakol_slug=slug))
    vol = Volume(series_id=series.id, volume_number=volume_number)
    db_session.add(vol)
    db_session.flush()
    db_session.commit()
    return vol


def _result(
    title: str,
    *,
    price,
    isbn: str | None = None,
    publisher: str | None = None,
    url: str,
) -> SearchResult:
    parsed = parse_volume_title(title)
    return SearchResult(
        store_id="bkm",
        store_name="BKM Kitap",
        title=title,
        product_url=url,
        series_title=parsed.base_title or None,
        volume_number=parsed.volume_number,
        isbn=isbn,
        publisher=publisher,
        price=Decimal(price) if price is not None else None,
        currency="TRY",
        in_stock=True,
    )


def _run(db_session, results) -> "ImportReport":
    if db_session.scalar(select(Store).where(Store.code == "bkm")) is None:
        db_session.add(Store(code="bkm", name="BKM Kitap"))
        db_session.commit()
    scraper = RecordingScraper(store_id="bkm", store_name="BKM Kitap", results=results)
    service = ImportService(db_session, scrapers=[scraper])
    return service.run_import("query")


def _listing(db_session, volume) -> StoreListing | None:
    return db_session.scalar(
        select(StoreListing).where(StoreListing.volume_id == volume.id)
    )


def _history(db_session, listing) -> list[int]:
    rows = db_session.scalars(
        select(PriceHistory)
        .where(PriceHistory.listing_id == listing.id)
        .order_by(PriceHistory.id)
    ).all()
    return [h.price for h in rows]


class TestMultiPrinting:
    def test_cheaper_printing_wins_regardless_of_order(self, db_session):
        vol = _seed_series(db_session, title="Titana Saldırı: Çöküşten Önce", publisher_name="YKY", volume_number=3)
        # Pricier printing first in the result set (relevance order), then the cheap one.
        report = _run(
            db_session,
            [
                _result(
                    "Titana Saldırı - Çöküşten Önce 3",
                    price="201.60",
                    isbn="9786256449824",
                    url="https://bkm.example/pricier",
                ),
                _result(
                    "Titana Saldırı - Çöküşten Önce 3",
                    price="180.00",
                    isbn="9786256449824",
                    url="https://bkm.example/cheap",
                ),
            ],
        )
        listing = _listing(db_session, vol)
        assert listing is not None
        assert listing.price == 18000  # the cheap printing
        assert listing.product_url == "https://bkm.example/cheap"
        assert _history(db_session, listing) == [18000]  # one observation, no flip
        assert report.total_created == 1
        assert report.total_skipped == 1

    def test_cheaper_printing_wins_when_listed_first(self, db_session):
        vol = _seed_series(db_session, title="Titana Saldırı: Çöküşten Önce", publisher_name="YKY", volume_number=3)
        report = _run(
            db_session,
            [
                _result(
                    "Titana Saldırı - Çöküşten Önce 3",
                    price="180.00",
                    isbn="9786256449824",
                    url="https://bkm.example/cheap",
                ),
                _result(
                    "Titana Saldırı - Çöküşten Önce 3",
                    price="201.60",
                    isbn="9786256449824",
                    url="https://bkm.example/pricier",
                ),
            ],
        )
        listing = _listing(db_session, vol)
        assert listing.price == 18000
        assert listing.product_url == "https://bkm.example/cheap"
        assert _history(db_session, listing) == [18000]
        assert report.total_skipped == 1

    def test_second_run_is_stable(self, db_session):
        """Once settled on the cheap printing, re-runs must not flip the price
        even though the store still lists both printings."""
        vol = _seed_series(db_session, title="Titana Saldırı: Çöküşten Önce", publisher_name="YKY", volume_number=3)
        pricier = _result(
            "Titana Saldırı - Çöküşten Önce 3",
            price="201.60",
            isbn="9786256449824",
            url="https://bkm.example/pricier",
        )
        cheap = _result(
            "Titana Saldırı - Çöküşten Önce 3",
            price="180.00",
            isbn="9786256449824",
            url="https://bkm.example/cheap",
        )
        _run(db_session, [pricier, cheap])
        listing = _listing(db_session, vol)
        assert _history(db_session, listing) == [18000]

        _run(db_session, [pricier, cheap])
        assert listing.price == 18000
        assert _history(db_session, listing) == [18000]  # no new rows

    def test_different_series_import_independently(self, db_session):
        """Two publishers of the same title (e.g. Berserk) are different
        series: dedup must NOT merge them across series."""
        vol_a = _seed_series(
            db_session, title="Berserk", publisher_name="Athica Yayınları"
        )
        vol_b = _seed_series(
            db_session, title="Berserk", publisher_name="Gerekli Şeyler Yayıncılık"
        )
        report = _run(
            db_session,
            [
                _result(
                    "Berserk 1",
                    price="150.00",
                    publisher="Athica Yayınları",
                    url="https://bkm.example/a",
                ),
                _result(
                    "Berserk 1",
                    price="140.00",
                    publisher="Gerekli Şeyler Yayıncılık",
                    url="https://bkm.example/b",
                ),
            ],
        )
        listing_a = _listing(db_session, vol_a)
        listing_b = _listing(db_session, vol_b)
        assert listing_a is not None and listing_b is not None
        assert listing_a.price == 15000
        assert listing_b.price == 14000
        assert report.total_created == 2

    def test_unpriced_printing_does_not_hide_priced_one(self, db_session):
        """A printing with no visible price must not block the priced one."""
        vol = _seed_series(db_session, title="Titana Saldırı: Çöküşten Önce", publisher_name="YKY", volume_number=3)
        report = _run(
            db_session,
            [
                _result(
                    "Titana Saldırı - Çöküşten Önce 3",
                    price=None,
                    isbn="9786256449824",
                    url="https://bkm.example/no-price",
                ),
                _result(
                    "Titana Saldırı - Çöküşten Önce 3",
                    price="180.00",
                    isbn="9786256449824",
                    url="https://bkm.example/cheap",
                ),
            ],
        )
        listing = _listing(db_session, vol)
        assert listing.price == 18000
        assert _history(db_session, listing) == [18000]
        assert report.total_created == 1
