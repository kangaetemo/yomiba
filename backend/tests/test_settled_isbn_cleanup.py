"""A settled ISBN removes another book's old listing; redundant legacy
phantoms fold into their catalog volume."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import PriceHistory, Store, StoreListing, Volume, WishlistItem, User
from app.services.catalog_sync import CatalogSyncReport, CatalogSyncService
from app.services.isbn_resolver import set_admin_isbn
from tests.test_import_service import seed_catalog_series
from tests.test_isbn_evidence import catalog, listings, product, run

MANGA, POCKET = "9786055541583", "9789944122801"
URL = "https://gerekliseyler.example/komunist-manifesto"


def _manifesto(db_session, wrong_isbn_source):
    """The pocket edition's ISBN sat on the manga, so the pocket edition's
    product attached (with price history)."""
    series = seed_catalog_series(db_session, "Komünist Manifesto", "Yordam", volumes=(1,))
    vols = catalog(db_session, series, {1: MANGA if wrong_isbn_source == "catalog" else None}, current={1: POCKET})
    pocket = [product("gerekliseyler", "Komünist Manifesto", POCKET, price="68", url=URL, publisher="Yordam")]
    run(db_session, {"gerekliseyler": pocket})
    assert (vols[1].id, URL) in listings(db_session)
    return vols[1], pocket


def test_settled_isbn_drops_the_other_books_listing_and_history(db_session):
    vol, pocket = _manifesto(db_session, "catalog")
    set_admin_isbn(db_session, vol, MANGA, user_id=1, reason="Yordam manga; …801 düz metin cep kitabı")
    db_session.commit()
    run(db_session, {"gerekliseyler": pocket})
    assert (vol.id, URL) not in listings(db_session)
    assert db_session.scalar(select(PriceHistory.id)) is None


def test_unsettled_isbn_keeps_the_listing(db_session):
    """No Mangakol ISBN, no admin decision: a mismatch proves nothing yet."""
    vol, pocket = _manifesto(db_session, "none")
    vol.isbn, vol.isbn_source = MANGA, "legacy"
    db_session.commit()
    run(db_session, {"gerekliseyler": pocket})
    assert (vol.id, URL) in listings(db_session)


def _phantom(db_session, series, isbn=None, urls=("https://a/1",)):
    store = db_session.scalar(select(Store)) or Store(code="kitapsec", name="Kitapseç")
    db_session.add(store)
    db_session.flush()
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    phantom = Volume(series_id=series.id, volume_number=-1, isbn=isbn)
    db_session.add(phantom)
    db_session.flush()
    for url in urls:
        listing = StoreListing(volume_id=phantom.id, store_id=store.id, product_url=url, price=15000,
                               in_stock=True, last_checked=now)
        db_session.add(listing)
        db_session.flush()
        db_session.add(PriceHistory(listing_id=listing.id, price=15000, in_stock=True, product_url=url, checked_at=now))
    db_session.commit()
    return phantom, store


def _catalog_listing(db_session, volume, store, url):
    db_session.add(StoreListing(volume_id=volume.id, store_id=store.id, product_url=url, price=14000,
                                in_stock=True, last_checked=datetime.now(timezone.utc)))
    db_session.commit()


def _merge(db_session):
    report = CatalogSyncReport()
    CatalogSyncService(db_session, scraper=object())._merge_redundant_phantoms(report)
    return report.isbn_phantoms_merged


def test_phantom_with_the_same_products_folds_into_the_catalog_volume(db_session):
    series = seed_catalog_series(db_session, "Yıldızların Sesi", "Komik Şeyler", volumes=(1,))
    vol = catalog(db_session, series, {1: "9786255607850"}, current={1: "9786255607874"})[1]
    phantom, store = _phantom(db_session, series, urls=("https://a/1",))
    _catalog_listing(db_session, vol, store, "https://a/1")
    pid = phantom.id
    assert _merge(db_session) == 1
    assert db_session.get(Volume, pid) is None
    rows = list(db_session.scalars(select(StoreListing).where(StoreListing.volume_id == vol.id)))
    assert len(rows) == 1 and db_session.scalar(select(PriceHistory.listing_id)) == rows[0].id


def test_phantom_is_kept_when_a_product_or_a_user_or_its_isbn_differs(db_session):
    series = seed_catalog_series(db_session, "Komünist Manifesto", "Yordam", volumes=(1,))
    vol = catalog(db_session, series, {1: MANGA}, current={1: MANGA})[1]
    # Another book's ISBN (Kırmızı Kedi edition): never merged.
    phantom, store = _phantom(db_session, series, isbn="9786254180835", urls=("https://a/1",))
    _catalog_listing(db_session, vol, store, "https://a/1")
    assert _merge(db_session) == 0
    # A product (another store's) the catalog volume does not list.
    phantom.isbn = None
    other = Store(code="bkm", name="BKM Kitap")
    db_session.add(other)
    db_session.flush()
    db_session.add(StoreListing(volume_id=phantom.id, store_id=other.id, product_url="https://a/other",
                                price=1, in_stock=True, last_checked=datetime.now(timezone.utc)))
    db_session.commit()
    assert _merge(db_session) == 0
    # A user's wishlist row.
    db_session.query(StoreListing).filter(StoreListing.product_url == "https://a/other").delete()
    db_session.add(WishlistItem(user_id=db_session.scalar(select(User.id)), volume_id=phantom.id))
    db_session.commit()
    assert _merge(db_session) == 0
    assert db_session.get(Volume, phantom.id) is not None
