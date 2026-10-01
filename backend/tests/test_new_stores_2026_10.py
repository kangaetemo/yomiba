"""Büyülü Dükkan (IdeaSoft, Gerekli Şeyler's parser) and İstanbul Kitapçısı
(T-Soft, Kitap Sepeti's parser). Fixtures are trimmed real pages captured
2026-10-01; both stores were reachable from the production server."""

from __future__ import annotations

from decimal import Decimal

import httpx

from app.scrapers.base import ScraperError
from app.scrapers.buyuludukkan import BuyuludukkanScraper
from app.scrapers.istanbulkitapcisi import IstanbulkitapcisiScraper
from app.scrapers.registry import enabled_store_ids, registered_scrapers
from app.seed import SEED_STORES
from tests.helpers import fixture_text, mock_client

BD_SEARCH = fixture_text("bd_search_p1.html")
BD_DETAIL = fixture_text("bd_detail.html")
IK_SEARCH = fixture_text("ik_search_p1.html")
IK_DETAIL = fixture_text("ik_detail.html")
EMPTY = "<html><body></body></html>"


def _by_title(results, title):
    matches = [r for r in results if r.title == title]
    assert len(matches) == 1, [r.title for r in results]
    return matches[0]


# -- Büyülü Dükkan ------------------------------------------------------------------

def _bd_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host != "www.buyuludukkan.com.tr":
        return httpx.Response(404)
    if request.url.path == "/arama/berserk":
        page = int(request.url.params.get("tp", "1"))
        return httpx.Response(200, text=BD_SEARCH if page == 1 else EMPTY)
    if request.url.path == "/urun/berserk-cilt-18":
        return httpx.Response(200, text=BD_DETAIL)
    return httpx.Response(404, text="not found")


def test_buyuludukkan_search_cards_stock_and_isbn():
    results = BuyuludukkanScraper(client=mock_client(_bd_handler)).search("berserk")

    v18 = _by_title(results, "Berserk Cilt 18")
    assert v18.store_id == "buyuludukkan" and v18.store_name == "Büyülü Dükkan"
    assert v18.product_url == "https://www.buyuludukkan.com.tr/urun/berserk-cilt-18"
    assert (v18.series_title, v18.volume_number) == ("Berserk", 18)
    assert v18.publisher == "Athica Yayınları"
    assert v18.price == Decimal("238.00") and v18.in_stock is True
    assert v18.isbn == "9786258858051"  # "Stok Kodu" row of the detail page

    assert _by_title(results, "Berserk Cilt 4").in_stock is False  # "Tükendi" label
    assert not [r for r in results if "Set" in r.title]  # box set dropped


def test_buyuludukkan_wall_fails_fast():
    def blocked(request):
        return httpx.Response(403, text="<title>Just a moment...</title>")

    scraper = BuyuludukkanScraper(client=mock_client(blocked))
    try:
        scraper.search("berserk")
    except ScraperError as exc:
        assert "buyuludukkan" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ScraperError")


# -- İstanbul Kitapçısı -------------------------------------------------------------

def _ik_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host != "www.istanbulkitapcisi.com":
        return httpx.Response(404)
    if request.url.path == "/arama":
        page = int(request.url.params.get("pg", "1"))
        return httpx.Response(200, text=IK_SEARCH if page == 1 else EMPTY)
    if request.url.path == "/berserk-12":
        return httpx.Response(200, text=IK_DETAIL)
    return httpx.Response(404, text="not found")


def test_istanbulkitapcisi_search_and_json_ld():
    results = IstanbulkitapcisiScraper(client=mock_client(_ik_handler)).search("berserk")

    v12 = _by_title(results, "Berserk 12")
    assert v12.store_id == "istanbulkitapcisi" and v12.store_name == "İstanbul Kitapçısı"
    assert v12.product_url == "https://www.istanbulkitapcisi.com/berserk-12"
    assert (v12.series_title, v12.volume_number) == ("Berserk", 12)
    assert v12.publisher == "Athica Yayınları"
    assert v12.price == Decimal("224.00")
    assert v12.isbn == "9786255610553" and v12.in_stock is True
    assert v12.language == "Turkish"


def test_istanbulkitapcisi_rechecks_unseen_listings():
    scraper = IstanbulkitapcisiScraper(client=mock_client(_ik_handler))
    assert scraper.verifies_unseen_listings
    check = scraper.check_listing("https://www.istanbulkitapcisi.com/berserk-12")
    assert check is not None and check.in_stock is True and check.price == Decimal("224.00")


# -- registration -------------------------------------------------------------------

def test_new_stores_are_registered_seeded_and_enabled():
    for code in ("buyuludukkan", "istanbulkitapcisi"):
        assert code in registered_scrapers()
        assert code in enabled_store_ids()
        assert code in {c for c, _ in SEED_STORES}


def test_parent_stores_keep_their_identity():
    """The refactor that made the parsers reusable keeps the originals as they were."""
    from app.scrapers.gerekliseyler import GerekliseylerScraper
    from app.scrapers.kitapsepeti import KitapsepetiScraper

    assert GerekliseylerScraper.base_url == "https://www.gerekliseyler.com.tr"
    assert KitapsepetiScraper.base_url == "https://www.kitapsepeti.com"
