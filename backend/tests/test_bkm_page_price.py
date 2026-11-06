"""BKM product pages do not carry BKM's selling price.

SEKIRO Yan Hikaye Cilt 1 (6 Nov 2026): the search said 210 TL, the product
page's JSON-LD 168 TL. A re-check of a listing the search missed stored
168 TL ("Fiyat düştü ... ürün sayfasından"), the next search put back 210.
"""

from __future__ import annotations

import json
from datetime import timedelta

import httpx
from sqlalchemy import select

from app.models import ListingChange, PriceHistory, Store, StoreListing, Volume
from app.scrapers.bkm import BkmScraper
from app.utils import utcnow
from fix_bkm_page_prices import repair
from tests.test_import_service import seed_catalog_series

URL = "https://www.bkmkitap.com/sekiro-yan-hikaye-olumsuz-hanbei-1"


def _page(availability: str, price: str = "168.00") -> str:
    node = {"@context": "https://schema.org", "@type": "Product", "name": "Sekiro 1",
            "offers": {"@type": "Offer", "price": price, "priceCurrency": "TRY",
                       "availability": f"https://schema.org/{availability}"}}
    return f'<html><script type="application/ld+json">{json.dumps(node)}</script></html>'


def _bkm(pages: dict[str, str]) -> BkmScraper:
    def handler(request: httpx.Request) -> httpx.Response:
        body = pages.get(str(request.url))
        return httpx.Response(200 if body else 404, text=body or "")

    scraper = BkmScraper(client=httpx.Client(transport=httpx.MockTransport(handler)))
    scraper._throttle = lambda: None  # noqa: SLF001 - no delays in tests
    return scraper


def _listing(db_session, price: int = 21000, in_stock: bool = True):
    series = seed_catalog_series(db_session, "SEKIRO-Yan Hikâye: Ölümsüz Hanbei", "Athica",
                                 volumes=(1,))
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()
    volume = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    listing = StoreListing(volume_id=volume.id, store_id=store.id, product_url=URL,
                           price=price, in_stock=in_stock,
                           last_checked=utcnow() - timedelta(hours=1))
    db_session.add(listing)
    db_session.commit()
    return series, store, volume, listing


def test_check_listing_reads_stock_not_price():
    check = _bkm({URL: _page("OutOfStock")}).check_listing(URL)
    assert check is not None
    assert check.in_stock is False
    assert check.price is None


def test_recheck_keeps_search_price(db_session, import_service):
    series, _, _, listing = _listing(db_session)
    scraper = _bkm({URL: _page("OutOfStock")})

    assert import_service.verify_unseen_listings(scraper, {series.id}, utcnow()) == 1
    db_session.refresh(listing)
    assert listing.price == 21000
    assert listing.in_stock is False
    change = db_session.scalar(select(ListingChange))
    assert (change.note, change.old_price, change.new_price) == ("recheck", 21000, 21000)


def _history(db_session, listing, price, at):
    db_session.add(PriceHistory(listing_id=listing.id, price=price, checked_at=at,
                                in_stock=True, product_url=URL))


def _change(db_session, store, volume, note, old, new, at):
    db_session.add(ListingChange(created_at=at, volume_id=volume.id, store_id=store.id,
                                 kind="update", note=note, old_price=old, new_price=new,
                                 old_in_stock=True, new_in_stock=True, product_url=URL))


def test_repair_drops_page_points_and_restores_search_price(db_session):
    _, store, volume, listing = _listing(db_session, price=16800)
    t0 = utcnow() - timedelta(days=3)
    _history(db_session, listing, 21000, t0)
    # Page price, then the search put 210 back, then another page price that
    # is still on the listing (plus one unchanged daily point).
    _history(db_session, listing, 16800, t0 + timedelta(hours=1))
    _change(db_session, store, volume, "recheck", 21000, 16800, t0 + timedelta(hours=1, seconds=1))
    _history(db_session, listing, 21000, t0 + timedelta(hours=2))
    _change(db_session, store, volume, None, 16800, 21000, t0 + timedelta(hours=2, seconds=1))
    _history(db_session, listing, 16800, t0 + timedelta(days=1))
    _change(db_session, store, volume, "recheck", 21000, 16800, t0 + timedelta(days=1, seconds=1))
    _history(db_session, listing, 16800, t0 + timedelta(days=2))
    db_session.commit()

    dry = repair(db_session, apply=False)
    assert (dry.listings, dry.history_deleted, len(dry.restored)) == (1, 3, 1)
    db_session.refresh(listing)
    assert listing.price == 16800  # dry run writes nothing

    repair(db_session, apply=True)
    db_session.refresh(listing)
    assert listing.price == 21000
    prices = db_session.scalars(select(PriceHistory.price).where(
        PriceHistory.listing_id == listing.id).order_by(PriceHistory.checked_at)).all()
    assert prices == [21000, 21000]


def test_repair_leaves_listing_the_search_corrected(db_session):
    _, store, volume, listing = _listing(db_session, price=21000)
    t0 = utcnow() - timedelta(days=1)
    _history(db_session, listing, 16800, t0)
    _change(db_session, store, volume, "recheck", 21000, 16800, t0 + timedelta(seconds=1))
    _history(db_session, listing, 21000, t0 + timedelta(minutes=18))
    _change(db_session, store, volume, None, 16800, 21000, t0 + timedelta(minutes=18, seconds=1))
    db_session.commit()

    report = repair(db_session, apply=True)
    assert (report.history_deleted, report.restored) == (1, [])
    db_session.refresh(listing)
    assert listing.price == 21000
