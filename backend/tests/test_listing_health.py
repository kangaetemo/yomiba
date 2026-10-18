"""Listing health: search sightings, product-page re-checks, the report's
search_miss / stale_listing / suspect_listing checks, and off-site products."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import Store, StoreListing, StoreObservation, Volume
from app.scrapers.base import BaseScraper, ListingCheck
from app.scrapers.search_result import SearchResult
from app.services.import_service import ImportService
from app.services.isbn_health import build_report
from tests.test_import_service import seed_catalog_series

NOW = datetime.now(timezone.utc)


def _naive(dt):
    return dt.replace(tzinfo=None) if dt else None


def _series(db_session, title="Mavi Kutu", publisher="Akılçelen", volumes=(1, 2)):
    series = seed_catalog_series(db_session, title, publisher, volumes=volumes)
    vols = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id))}
    for v in vols.values():
        v.catalog_present = v.catalog_released = True
    db_session.commit()
    return vols


class Shop(BaseScraper):
    """A store whose search returns ``results`` and whose product pages say ``page``."""
    store_id, store_name, base_url = "bkm", "BKM Kitap", "https://www.bkm.example"
    verifies_unseen_listings = True

    def __init__(self, results, page=None):
        super().__init__()
        self._results, self._page = results, page

    def search(self, query):
        return list(self._results)

    def check_listing(self, url):
        return self._page


def _product(title, url, isbn=None, price="161", publisher="Akılçelen"):
    return SearchResult(store_id="bkm", store_name="BKM Kitap", title=title, product_url=url, isbn=isbn,
                        publisher=publisher, price=Decimal(price), currency="TRY", in_stock=True)


def test_search_sets_seen_in_search_and_a_page_recheck_does_not(db_session):
    vols = _series(db_session)
    url = "https://bkm.example/blue-box-mavi-kutu-2"
    ImportService(db_session, scrapers=[Shop([_product("Mavi Kutu 2", url)])]).run_import("Mavi Kutu")
    listing = db_session.scalar(select(StoreListing))
    assert listing.volume_id == vols[2].id and listing.seen_in_search_at is not None
    seen = listing.seen_in_search_at
    # The search stops returning it; the product page still says in stock.
    started = NOW + timedelta(seconds=5)
    listing.last_checked = NOW - timedelta(days=1)
    db_session.commit()
    shop = Shop([], page=ListingCheck(in_stock=True, price=Decimal("150")))
    assert ImportService(db_session).verify_unseen_listings(shop, {vols[2].series_id}, started) == 1
    db_session.refresh(listing)
    assert listing.price == 15000 and _naive(listing.seen_in_search_at) == _naive(seen)


def test_report_lists_search_misses_stale_and_suspect_listings(db_session):
    vols = _series(db_session, volumes=(1, 2, 3, 4))
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()

    def listing(volume, url, *, checked, seen, in_stock=True):
        db_session.add(StoreListing(volume_id=volume.id, store_id=store.id, product_url=url, price=16100,
                                    in_stock=in_stock, last_checked=checked, seen_in_search_at=seen))

    listing(vols[1], "https://bkmkitap.com/mavi-kutu-1", checked=NOW, seen=NOW)
    listing(vols[2], "https://bkmkitap.com/mavi-kutu-2", checked=NOW, seen=NOW - timedelta(days=5))
    listing(vols[3], "https://bkmkitap.com/mavi-kutu-3", checked=NOW - timedelta(days=4), seen=NOW - timedelta(days=4))
    listing(vols[4], "https://www.primevideo.com/detail/X", checked=NOW, seen=NOW)
    db_session.add_all([
        StoreObservation(store_id=store.id, product_url="https://bkmkitap.com/mavi-kutu-1", title="Mavi Kutu 1. Sezon DVD",
                         publisher="Akılçelen Kitaplar", first_seen=NOW, last_seen=NOW),
        StoreObservation(store_id=store.id, product_url="https://bkmkitap.com/mavi-kutu-2", title="Mavi Kutu 2",
                         publisher="Kırmızı Kedi", first_seen=NOW, last_seen=NOW),
    ])
    db_session.commit()
    checks = build_report(db_session)["checks"]
    assert [r["volume_number"] for r in checks["search_miss"]["items"]] == [2]
    assert [r["volume_number"] for r in checks["stale_listing"]["items"]] == [3]
    suspect = {r["volume_number"]: r["reasons"] for r in checks["suspect_listing"]["items"]}
    assert suspect[1] == ["başlıkta: dvd, sezon"]          # same publisher under another spelling: fine
    assert suspect[2] == ["yayınevi farklı (Kırmızı Kedi)"]
    assert suspect[4] == ["başka siteye gidiyor (primevideo.com)"]
    assert 3 not in suspect


def test_a_product_on_another_site_is_refused(db_session):
    vols = _series(db_session)
    url = "https://bkm.example/mavi-kutu-1"
    ImportService(db_session, scrapers=[Shop([_product("Mavi Kutu 1", url)])]).run_import("Mavi Kutu")
    assert db_session.scalar(select(StoreListing.volume_id)) == vols[1].id
    # Same store, now pointing off-site (and a separate off-site product).
    moved = _product("Mavi Kutu 1", "https://www.primevideo.com/detail/X")
    service = ImportService(db_session, scrapers=[Shop([moved])])
    service.run_import("Mavi Kutu")
    assert db_session.scalar(select(StoreListing.product_url)) == url  # the off-site product never attached
    obs = db_session.scalar(select(StoreObservation).where(StoreObservation.product_url == moved.product_url))
    assert obs.reason == "foreign_url"
