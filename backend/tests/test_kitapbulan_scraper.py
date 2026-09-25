"""Kitapbulan scraper tests (fixture-backed; endpoint contract live-verified
against kitapbulan.com on 2026-09-10: /arama?q=...&pg=N SSR cards +
product-page JSON-LD. Same T-Soft CMS as Kitap Sepeti.

Kitapbulan-specific: the vitrin fallback guard — queries without a real
match return a grid of unrelated products, which must be dropped."""

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
from app.scrapers.kitapbulan import KitapbulanScraper
from tests.helpers import fixture_text, mock_client

SEARCH_P1 = fixture_text("kb_search_p1.html")
SEARCH_P2 = fixture_text("kb_search_p2.html")
SEARCH_NOMATCH = fixture_text("kb_search_nomatch.html")
DETAIL = fixture_text("kb_detail.html")
EMPTY_PAGE = "<html><body><div id='product-list-panel'></div></body></html>"
BLOCKED_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>challenge-platform Enable JavaScript and cookies to continue"
    "</body></html>"
)


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = KitapbulanScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


def _page_of(request: httpx.Request) -> int:
    return int(request.url.params.get("pg", "1"))


def default_handler(request: httpx.Request) -> httpx.Response:
    """One-Piece search: p1 (4 cards, one collection + one vitrin fallback),
    p2 (duplicate + one new card), then empty pages. Details: 404."""
    if request.url.path == "/arama":
        page = _page_of(request)
        if page == 1:
            return httpx.Response(200, text=SEARCH_P1)
        if page == 2:
            return httpx.Response(200, text=SEARCH_P2)
        return httpx.Response(200, text=EMPTY_PAGE)
    return httpx.Response(404, text="not found")


@pytest.fixture()
def scraper():
    return make_scraper(default_handler)


# -- parsing + relevance guard ---------------------------------------------------

def test_parses_search_cards(scraper):
    results = scraper.search("one piece")
    assert len(results) == 3  # collection + vitrin fallback filtered
    by_url = {r.product_url: r for r in results}

    vol36 = by_url["https://www.kitapbulan.com/one-piece-36"]
    assert vol36.title == "One Piece 36"
    assert vol36.series_title == "One Piece"
    assert vol36.volume_number == 36
    assert vol36.publisher == "Atlas Yayıncılık"
    assert vol36.price == Decimal("184.00")
    assert vol36.currency == "TRY"
    assert vol36.image_url == (
        "https://static.ticimax.cloud/61090/Uploads/UrunResimleri/buyuk/one-piece-36.jpg"
    )

    # Imported English edition: "Volume 99" marker parsed, publisher Shueisha.
    vol99 = by_url["https://www.kitapbulan.com/one-piece-volume-99-one-piece"]
    assert vol99.volume_number == 99
    assert vol99.publisher == "Shueisha"
    assert vol99.price == Decimal("250.00")
    assert vol99.series_title.startswith("One Piece")

    vol10 = by_url["https://www.kitapbulan.com/one-piece-10"]
    assert vol10.volume_number == 10
    assert vol10.price == Decimal("184.00")


def test_stats_counts(scraper):
    scraper.search("one piece")
    stats = scraper.stats
    assert stats["pages_fetched"] == 3  # p1 + p2 + empty p3
    assert stats["raw_products"] == 6
    assert stats["duplicates_skipped"] == 1  # one-piece-36 repeated on p2
    assert stats["rejected"] == {"collection": 1, "irrelevant": 1}
    assert stats["accepted"] == 3
    assert stats["stop_reason"] == "empty_page"


def test_vitrin_fallback_returns_empty():
    """A query with no real match: the store pads the grid with unrelated
    vitrin products; none of them may leak into the results."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            page = _page_of(request)
            if page == 1:
                return httpx.Response(200, text=SEARCH_NOMATCH)
            return httpx.Response(200, text=EMPTY_PAGE)
        return httpx.Response(404)

    scraper = make_scraper(handler)
    results = scraper.search("watchmen")
    assert results == []
    assert scraper.stats["rejected"] == {"irrelevant": 2}
    assert scraper.stats["accepted"] == 0


def test_short_query_tokens_do_not_gate_relevance():
    """Tokens shorter than 3 characters ('v', 'for') are noise: a query like
    'v one piece' must keep the One Piece cards (title lacks the 'v' token)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            page = _page_of(request)
            if page == 1:
                return httpx.Response(200, text=SEARCH_P1)
            return httpx.Response(200, text=EMPTY_PAGE)
        return httpx.Response(404)

    scraper = make_scraper(handler)
    results = scraper.search("v one piece")
    assert len(results) == 2  # 'v' ignored; 'one' + 'piece' match the page-1 cards


# -- enrichment -------------------------------------------------------------------

def test_enrichment_isbn_from_sku_brand_and_stock():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            page = _page_of(request)
            if page == 1:
                return httpx.Response(200, text=SEARCH_P1)
            return httpx.Response(200, text=EMPTY_PAGE)
        return httpx.Response(200, text=DETAIL)

    results = make_scraper(handler).search("one piece")
    vol36 = next(r for r in results if r.volume_number == 36)
    assert vol36.isbn == "9786256335424"  # from sku/mpn
    assert vol36.publisher == "Atlas Yayıncılık"  # card value kept (already set)
    assert vol36.in_stock is True  # availability InStock


def test_detail_404_keeps_search_data(scraper):
    results = scraper.search("one piece")
    vol36 = next(r for r in results if r.volume_number == 36)
    assert vol36.isbn is None
    assert vol36.in_stock is True  # unknown defaults to True
    assert vol36.publisher == "Atlas Yayıncılık"


# -- blocking -----------------------------------------------------------------------

def test_blocked_search_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=BLOCKED_PAGE)

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="blocked"):
        scraper.search("one piece")
    assert scraper.stats["pages_fetched"] == 0


def test_detail_blocked_keeps_search_data():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            page = _page_of(request)
            if page == 1:
                return httpx.Response(200, text=SEARCH_P1)
            return httpx.Response(200, text=EMPTY_PAGE)
        return httpx.Response(403, text=BLOCKED_PAGE)

    results = make_scraper(handler).search("one piece")
    vol36 = next(r for r in results if r.volume_number == 36)
    assert vol36.isbn is None
    assert vol36.price == Decimal("184.00")


# -- bounds -----------------------------------------------------------------------

def test_max_results_bound():
    scraper = make_scraper(default_handler, kitapbulan_max_search_results=1)
    results = scraper.search("one piece")
    assert len(results) == 1
    assert scraper.stats["stop_reason"] == "max_results"
    assert scraper.stats["pages_fetched"] == 1


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a strong merch token of the COMMON relevance filter
    but not of this store's local keyword list: only the common layer can
    reject it, so this proves the filter is wired into the store pipeline.
    """
    page = SEARCH_P1.replace("One Piece 36", "One Piece 36 Grandista")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama":
            p = _page_of(request)
            return httpx.Response(200, text=page if p == 1 else EMPTY_PAGE)
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    results = scraper.search("one piece")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture books are untouched
    assert any("One Piece. Volume 99" in r.title for r in results)
