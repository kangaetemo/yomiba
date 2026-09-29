"""2-in-1 / 3-in-1 editions and sold-out products hidden from search.

Real shapes seen 2026-09-29:
* Mangakol marks "Dragon Ball Cilt 5" as ``TwoInOne`` labelled
  "Dragon Ball 9&10"; BKM sells it as "Dragon Ball 9&10", Oldboy as
  "Oldboy Cilt 5-6", Kobayaşi as "... Cilt 1 ve 2".
* Kitapseç drops sold-out products from search (every row is InStock), so
  a listing it no longer returns is re-checked on its product page.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.models import Store, StoreListing, Volume
from app.normalization import parse_volume_range
from app.scrapers.base import BaseScraper, ListingCheck
from app.scrapers.mangakol import CatalogManga, MangakolCatalogScraper, CatalogVolume
from app.services.catalog_sync import CatalogSyncService
from app.services.import_service import ImportAction
from app.utils import utcnow
from tests.test_catalog_sync import FakeMangakolScraper
from tests.test_import_service import make_result, seed_catalog_series

GS = "Gerekli Şeyler Yayıncılık"


# -- parsing ---------------------------------------------------------------------

@pytest.mark.parametrize("title,base,first,last", [
    ("Dragon Ball 9&10", "Dragon Ball", 9, 10),
    ("Dragon Ball 5 ve 6", "Dragon Ball", 5, 6),
    ("Oldboy Cilt 5-6", "Oldboy", 5, 6),
    ("Oldboy Cilt: 7-8", "Oldboy", 7, 8),
    ("Oldboy 1-2 Cilt", "Oldboy", 1, 2),
    ("Kızların Kıyamet Yolculuğu Cilt 5 - 6", "Kızların Kıyamet Yolculuğu", 5, 6),
    ("Kobayaşi Hanesi’nin Hizmetçi Ejderhası Cilt 1 ve 2", "Kobayaşi Hanesi’nin Hizmetçi Ejderhası", 1, 2),
    ("Kobayaşi Hanesi`nin Hizmetçi Ejderhası 3&4", "Kobayaşi Hanesi`nin Hizmetçi Ejderhası", 3, 4),
    ("Vagabond 1-2-3", "Vagabond", 1, 3),
    # BKM 2026-09-29: Artemis sells Teogonia like this
    ("Teogonia 1. Cilt - 2. Cilt (İki Cilt Bir Arada)", "Teogonia", 1, 2),
    ("Teogonia 3. Cilt - 4. Cilt (İki Cilt Bir Arada)", "Teogonia", 3, 4),
    ("Oldboy Cilt 1 - Cilt 2", "Oldboy", 1, 2),
    ("Dragon Ball 1-2 (2'si 1 Arada)", "Dragon Ball", 1, 2),
    ("Vagabond 1-2-3 (3'ü 1 Arada)", "Vagabond", 1, 3),
])
def test_parse_volume_range(title, base, first, last):
    span = parse_volume_range(title)
    assert span is not None
    assert (span.base_title, span.first, span.last) == (base, first, last)


@pytest.mark.parametrize("title", [
    "Berserk 1-5",                    # not consecutive: a box, never an omnibus
    "Dragon Ball 9&11",
    "Dragon Ball 1-2 Kutu Set",       # collection word
    "Zom 100 Cilt 10",                # a single volume
    "Kaiju No: 8 - 8 No'lu Canavar",  # not a trailing span
    "9&10",                           # no title
    "Zom 100 Cilt 10",                # number inside the title, one volume
    "Teogonia 1. Cilt - 3. Cilt (İki Cilt Bir Arada)",  # not consecutive
    "Naruto 1-2 (Kutu Set)",          # collection word survives the note strip
])
def test_parse_volume_range_rejects(title):
    assert parse_volume_range(title) is None


def test_mangakol_volume_item_reads_span():
    html = """
    <div class="mk-vol-item" data-binding-format="TwoInOne">
      <div class="mk-vol-badge">Cilt 5</div>
      <img alt="Dragon Ball 9&amp;10" class="mk-vol-cover" src="/c5.webp"/>
      <button data-volume-number="5"></button>
      <h3 class="mk-vol-title" title="Dragon Ball 9&amp;10"><a>Dragon Ball 9&amp;10</a></h3>
    </div>
    <div class="mk-vol-item" data-binding-format="SingleVolume">
      <button data-volume-number="6"></button>
      <h3 class="mk-vol-title" title="Dragon Ball 11"></h3>
    </div>"""
    vols = MangakolCatalogScraper._volume_items(BeautifulSoup(html, "lxml"))
    assert [(v.number, v.covers) for v in vols] == [(5, (9, 10)), (6, None)]


def test_catalog_sync_stores_and_backfills_span(db_session):
    manga = CatalogManga(
        slug="dragon-ball", title="Dragon Ball", local_publisher="Gerekli Şeyler",
        volumes=[CatalogVolume(number=1, cover_url=None, covers=(1, 2)),
                 CatalogVolume(number=2, cover_url=None)],
    )
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    spans = {v.volume_number: (v.covers_from, v.covers_to) for v in db_session.scalars(select(Volume))}
    assert spans == {1: (1, 2), 2: (None, None)}

    # existing volume gets the span on a later sync; a missing span never erases
    manga = CatalogManga(
        slug="dragon-ball", title="Dragon Ball", local_publisher="Gerekli Şeyler",
        volumes=[CatalogVolume(number=1, cover_url=None),
                 CatalogVolume(number=2, cover_url=None, covers=(3, 4))],
    )
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    spans = {v.volume_number: (v.covers_from, v.covers_to) for v in db_session.scalars(select(Volume))}
    assert spans == {1: (1, 2), 2: (3, 4)}


# -- matching --------------------------------------------------------------------

def _omnibus(db_session, title, publisher, books, per_book=2):
    series = seed_catalog_series(db_session, title, publisher, volumes=range(1, books + 1))
    for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id)):
        v.covers_from = (v.volume_number - 1) * per_book + 1
        v.covers_to = v.volume_number * per_book
    db_session.commit()
    return series


def _target(db_session):
    v = db_session.scalar(select(StoreListing)).volume
    return v.series_id, v.volume_number


@pytest.mark.parametrize("catalog,publisher,store_pub,title,number", [
    ("Dragon Ball", "Gerekli Şeyler", GS, "Dragon Ball 9&10", 5),
    ("Dragon Ball", "Gerekli Şeyler", GS, "Dragon Ball 5 ve 6", 3),
    ("Oldboy", "Gerekli Şeyler", GS, "Oldboy Cilt: 7-8", 4),
    ("Oldboy", "Gerekli Şeyler", GS, "Oldboy 1-2 Cilt", 1),
    ("Kızların Kıyamet Yolculuğu", "Komik Şeyler", "Komikşeyler Yayıncılık",
     "Kızların Kıyamet Yolculuğu Cilt 5 - 6", 3),
    ("Kobayaşi Hanesi'nin Hizmetçi Ejderhası", "Komik Şeyler", "Komikşeyler Yayıncılık",
     "Kobayaşi Hanesi’nin Hizmetçi Ejderhası Cilt 1 ve 2", 1),
    ("Teogonia", "Artemis", "Artemis Yayınları",
     "Teogonia 3. Cilt - 4. Cilt (İki Cilt Bir Arada)", 2),
])
def test_omnibus_title_matches_catalog_span(db_session, import_service, catalog, publisher,
                                            store_pub, title, number):
    series = _omnibus(db_session, catalog, publisher, books=12)
    r = make_result("bkm", title, "100", publisher=store_pub)
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _target(db_session) == (series.id, number)


def test_three_in_one_span(db_session, import_service):
    series = _omnibus(db_session, "Vagabond", "Gerekli Şeyler", books=5, per_book=3)
    r = make_result("bkm", "Vagabond 4-5-6", "100", publisher=GS)
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _target(db_session) == (series.id, 2)


def test_range_on_single_volume_edition_stays_a_box(db_session, import_service):
    """No catalog span -> "1-2" is still a two-book box, never volume 1."""
    seed_catalog_series(db_session, "Berserk", "Athica", volumes=range(1, 10))
    r = make_result("bkm", "Berserk 1-2", "100", publisher="Athica Yayınları")
    assert import_service.import_result(r) == ImportAction.SKIPPED
    assert import_service.last_reason == "box_set"


def test_misaligned_span_is_rejected(db_session, import_service):
    _omnibus(db_session, "Dragon Ball", "Gerekli Şeyler", books=12)
    r = make_result("bkm", "Dragon Ball 10&11", "100", publisher=GS)
    assert import_service.import_result(r) == ImportAction.SKIPPED


def test_span_needs_publisher_family(db_session, import_service):
    _omnibus(db_session, "Dragon Ball", "Gerekli Şeyler", books=12)
    r = make_result("bkm", "Dragon Ball 9&10", "100", publisher="Epsilon Yayınevi")
    assert import_service.import_result(r) == ImportAction.SKIPPED


# -- product-page stock check ---------------------------------------------------------

def _jsonld_page(availability: str, price: str = "210.00") -> str:
    node = {"@context": "https://schema.org", "@type": "Product", "name": "X",
            "offers": {"@type": "Offer", "price": price, "priceCurrency": "TRY",
                       "availability": f"https://schema.org/{availability}"}}
    return f'<html><script type="application/ld+json">{json.dumps(node)}</script></html>'


def _scraper(pages: dict[str, tuple[int, str]]) -> BaseScraper:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = pages.get(str(request.url), (404, ""))
        return httpx.Response(status, text=body)

    scraper = BaseScraper(client=httpx.Client(transport=httpx.MockTransport(handler)))
    scraper.store_id, scraper.store_name = "kitapsec", "Kitapsec"
    scraper.verifies_unseen_listings = True
    scraper._throttle = lambda: None  # noqa: SLF001 - no delays in tests
    return scraper


@pytest.mark.parametrize("availability,expected", [
    ("OutOfStock", ListingCheck(False, Decimal("210.00"))),
    ("InStock", ListingCheck(True, Decimal("210.00"))),
    ("Something", None),
])
def test_check_listing_reads_json_ld(availability, expected):
    url = "https://www.kitapsec.com/Products/x.html"
    assert _scraper({url: (200, _jsonld_page(availability))}).check_listing(url) == expected


def test_check_listing_unknown_when_page_has_no_product():
    url = "https://www.kitapsec.com/Products/gone.html"
    assert _scraper({url: (200, "<html>anasayfa</html>")}).check_listing(url) is None


def _listing(db_session, url: str, hours_ago: float, in_stock: bool = True):
    series = seed_catalog_series(db_session, "Tokyo Gül - Yeniden", "Gerekli Şeyler", volumes=(8, 9))
    store = Store(code="kitapsec", name="Kitapsec")
    db_session.add(store)
    db_session.flush()
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 8))
    listing = StoreListing(volume_id=vol.id, store_id=store.id, product_url=url, price=20000,
                           in_stock=in_stock, last_checked=utcnow() - timedelta(hours=hours_ago))
    db_session.add(listing)
    db_session.commit()
    return series, listing


def test_unseen_listing_marked_out_of_stock(db_session, import_service):
    url = "https://www.kitapsec.com/Products/Tokyo-Gul-Yeniden-8.html"
    series, listing = _listing(db_session, url, hours_ago=1)
    since = utcnow() - timedelta(minutes=5)
    scraper = _scraper({url: (200, _jsonld_page("OutOfStock", "215.00"))})

    assert import_service.verify_unseen_listings(scraper, {series.id}, since) == 1
    db_session.refresh(listing)
    assert listing.in_stock is False
    assert listing.price == 21500


def test_listing_seen_in_this_run_is_not_rechecked(db_session, import_service):
    url = "https://www.kitapsec.com/Products/Tokyo-Gul-Yeniden-8.html"
    series, listing = _listing(db_session, url, hours_ago=0)
    since = utcnow() - timedelta(minutes=5)
    scraper = _scraper({})  # any request would 404 -> None; must not even be asked

    assert import_service.verify_unseen_listings(scraper, {series.id}, since) == 0
    db_session.refresh(listing)
    assert listing.in_stock is True


def test_unknown_page_keeps_listing(db_session, import_service):
    url = "https://www.kitapsec.com/Products/Tokyo-Gul-Yeniden-8.html"
    series, listing = _listing(db_session, url, hours_ago=1)
    scraper = _scraper({url: (200, "<html>anasayfa</html>")})

    assert import_service.verify_unseen_listings(scraper, {series.id}, utcnow()) == 0
    db_session.refresh(listing)
    assert listing.in_stock is True


def test_store_without_flag_is_never_rechecked(db_session, import_service):
    url = "https://www.kitapsec.com/Products/Tokyo-Gul-Yeniden-8.html"
    series, _ = _listing(db_session, url, hours_ago=1)
    scraper = _scraper({url: (200, _jsonld_page("OutOfStock"))})
    scraper.verifies_unseen_listings = False
    assert import_service.verify_unseen_listings(scraper, {series.id}, utcnow()) == 0


def test_hidden_store_flags():
    from app.scrapers.bkm import BkmScraper
    from app.scrapers.kitapsec import KitapsecScraper
    from app.scrapers.kitapsepeti import KitapsepetiScraper

    assert KitapsecScraper.verifies_unseen_listings
    assert KitapsepetiScraper.verifies_unseen_listings
    assert not BkmScraper.verifies_unseen_listings


# -- neutral order for equally cheap stores ----------------------------------------------

def test_equal_prices_are_ordered_neutrally(db_session):
    """Same price: in stock first, then store name — never "whichever store
    was imported first" (listing id), which reads like a paid placement."""
    from app.services import catalog_service

    series = seed_catalog_series(db_session, "Berserk", "Athica")
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    stores = {code: Store(code=code, name=name) for code, name in
              (("z", "Zeta Kitap"), ("a", "Alfa Kitap"), ("m", "Mega Kitap"), ("c", "Cheap"))}
    db_session.add_all(stores.values())
    db_session.flush()
    for code, price, stock in (("z", 15000, True), ("a", 15000, True), ("m", 15000, False), ("c", 14000, False)):
        db_session.add(StoreListing(volume_id=vol.id, store_id=stores[code].id,
                                    product_url=f"https://{code}.example/b1", price=price, in_stock=stock))
    db_session.commit()

    order = [l.store.name for l in catalog_service.get_volume(db_session, vol.id).listings]
    assert order == ["Cheap", "Alfa Kitap", "Zeta Kitap", "Mega Kitap"]
