"""Kitap Sepeti scraper tests (fixture-backed; endpoint contract live-verified
against kitapsepeti.com on 2026-09-10: /arama?q=...&pg=N SSR cards +
product-page JSON-LD with isbn / price / availability)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

# Module reference on purpose: the autouse conftest fixture patches
# ``app.scrapers.base.get_settings`` (zero backoff / request interval), and
# calling it through the module at test time sees the patched binding.
from app.scrapers import base as scraper_base
from app.scrapers.base import ScraperError
from app.scrapers.kitapsepeti import KitapsepetiScraper
from tests.helpers import fixture_text, mock_client

SEARCH_P1 = fixture_text("kps_search_p1.html")
SEARCH_P2 = fixture_text("kps_search_p2.html")
DETAIL_INSTOCK = fixture_text("kps_detail_instock.html")
DETAIL_OUTOFSTOCK = fixture_text("kps_detail_outofstock.html")
EMPTY_PAGE = "<html><body><div id='product-list-panel'></div></body></html>"
BLOCKED_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>challenge-platform Enable JavaScript and cookies to continue"
    "</body></html>"
)


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = KitapsepetiScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


def _page_of(request: httpx.Request) -> int:
    return int(request.url.params.get("pg", "1"))


def default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/arama":
        page = _page_of(request)
        if page == 1:
            return httpx.Response(200, text=SEARCH_P1)
        if page == 2:
            return httpx.Response(200, text=SEARCH_P2)
        return httpx.Response(200, text=EMPTY_PAGE)
    if request.url.path == "/berserk-18":
        return httpx.Response(200, text=DETAIL_INSTOCK)
    return httpx.Response(404, text="not found")


@pytest.fixture()
def scraper():
    return make_scraper(default_handler)


# -- parsing -------------------------------------------------------------------

def test_parses_search_cards(scraper):
    results = scraper.search("berserk")
    assert len(results) == 3  # box (collection) + poster (non-manga) filtered
    by_url = {r.product_url: r for r in results}

    vol18 = by_url["https://www.kitapsepeti.com/berserk-18"]
    assert vol18.title == "Berserk 18"
    assert vol18.series_title == "Berserk"
    assert vol18.volume_number == 18
    assert vol18.publisher == "Athica Yayınları"
    assert vol18.price == Decimal("182.00")  # current price, not the 280,00 list price
    assert vol18.currency == "TRY"
    assert vol18.image_url == "https://asset.kitapsepeti.com/berserk-18-1053855-58-K.jpg"
    assert vol18.relevance == 1.0

    vol19 = by_url["https://www.kitapsepeti.com/berserk-19"]
    assert vol19.volume_number == 19
    assert vol19.price == Decimal("208.00")

    vol17 = by_url["https://www.kitapsepeti.com/berserk-17"]
    assert vol17.price == Decimal("221.20")


def test_stats_counts(scraper):
    scraper.search("berserk")
    stats = scraper.stats
    assert stats["pages_fetched"] == 3  # p1 + p2 + empty p3
    assert stats["raw_products"] == 6
    assert stats["duplicates_skipped"] == 1  # berserk-18 repeated on p2
    assert stats["rejected"] == {"non_manga_keyword": 1, "collection": 1}
    assert stats["accepted"] == 3
    assert stats["stop_reason"] == "empty_page"


def test_detail_404_keeps_search_data(scraper):
    # Only /berserk-18 has a detail page in the default handler.
    results = {r.volume_number: r for r in scraper.search("berserk")}
    vol19 = results[19]
    assert vol19.isbn is None  # 404 detail -> enrichment skipped
    assert vol19.in_stock is True  # unknown stock defaults to True
    assert vol19.publisher == "Athica Yayınları"  # from the search card


# -- enrichment -----------------------------------------------------------------

def test_enrichment_isbn_author_language_stock():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            return httpx.Response(200, text=SEARCH_P1 if _page_of(request) == 1 else EMPTY_PAGE)
        return httpx.Response(200, text=DETAIL_INSTOCK)

    results = make_scraper(handler).search("berserk")
    vol18 = next(r for r in results if r.volume_number == 18)
    assert vol18.isbn == "9786258858051"
    assert vol18.author == "Kentaro Miura"
    assert vol18.language == "Turkish"
    assert vol18.in_stock is True  # availability InStock


def test_enrichment_out_of_stock():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            return httpx.Response(200, text=SEARCH_P1 if _page_of(request) == 1 else EMPTY_PAGE)
        return httpx.Response(200, text=DETAIL_OUTOFSTOCK)

    results = make_scraper(handler).search("berserk")
    vol18 = next(r for r in results if r.volume_number == 18)
    assert vol18.in_stock is False  # availability OutOfStock
    assert vol18.isbn == "9786256335424"


# -- blocking --------------------------------------------------------------------

def test_blocked_search_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=BLOCKED_PAGE)

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="blocked"):
        scraper.search("berserk")
    assert scraper.stats["pages_fetched"] == 0


def test_detail_blocked_keeps_search_data():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            return httpx.Response(200, text=SEARCH_P1 if _page_of(request) == 1 else EMPTY_PAGE)
        return httpx.Response(403, text=BLOCKED_PAGE)

    results = make_scraper(handler).search("berserk")
    vol18 = next(r for r in results if r.volume_number == 18)
    assert vol18.isbn is None  # blocked detail -> search data kept
    assert vol18.price == Decimal("182.00")


# -- bounds -----------------------------------------------------------------------

def test_max_results_bound():
    scraper = make_scraper(default_handler, kitapsepeti_max_search_results=2)
    results = scraper.search("berserk")
    assert len(results) == 2
    assert scraper.stats["stop_reason"] == "max_results"
    assert scraper.stats["pages_fetched"] == 1  # stopped mid page 1


def test_no_new_items_stops_pagination():
    def handler(request: httpx.Request) -> httpx.Response:
        # Page 2 repeats page 1 exactly: pagination is not honoured.
        if request.url.path == "/arama":
            return httpx.Response(200, text=SEARCH_P1)
        return httpx.Response(404)

    scraper = make_scraper(handler)
    scraper.search("berserk")
    assert scraper.stats["stop_reason"] == "no_new_items"
    assert scraper.stats["pages_fetched"] == 2
    assert scraper.stats["duplicates_skipped"] == 4


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a strong merch token of the COMMON relevance filter
    but not of this store's local keyword list: only the common layer can
    reject it, so this proves the filter is wired into the store pipeline.
    """
    page = SEARCH_P1.replace(
        'class="product-title">Berserk 18', 'class="product-title">Berserk 18 Grandista'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            p = _page_of(request)
            return httpx.Response(200, text=page if p == 1 else EMPTY_PAGE)
        if request.url.path == "/berserk-18":
            return httpx.Response(200, text=DETAIL_INSTOCK)
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    results = scraper.search("berserk")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture books are untouched
    assert any("Berserk 19" in r.title for r in results)
