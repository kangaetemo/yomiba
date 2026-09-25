"""Gerekli Şeyler scraper tests (fixture-backed; endpoint contract
live-verified against gerekliseyler.com.tr on 2026-09-10:
/arama/<q>?tp=N SSR ``div.showcase`` cards, sold-out label on OOS cards,
product-page "Stok Kodu" row for the ISBN)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from app.scrapers import base as scraper_base
from app.scrapers.base import ScraperError
from app.scrapers.gerekliseyler import GerekliseylerScraper
from tests.helpers import fixture_text, mock_client

SEARCH_P1 = fixture_text("gs_search_p1.html")
SEARCH_P2 = fixture_text("gs_search_p2.html")
DETAIL_17 = fixture_text("gs_detail.html")
DETAIL_15 = DETAIL_17.replace("9786258502763", "9786258502190")
EMPTY_PAGE = "<html><body><div id='showcase-container'></div></body></html>"
BLOCKED_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>challenge-platform Enable JavaScript and cookies to continue"
    "</body></html>"
)


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = GerekliseylerScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


def _page_of(request: httpx.Request) -> int:
    return int(request.url.params.get("tp", "1"))


def default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/arama/berserk":
        page = _page_of(request)
        if page == 1:
            return httpx.Response(200, text=SEARCH_P1)
        if page == 2:
            return httpx.Response(200, text=SEARCH_P2)
        return httpx.Response(200, text=EMPTY_PAGE)
    if request.url.path == "/urun/berserk-cilt-17":
        return httpx.Response(200, text=DETAIL_17)
    if request.url.path == "/urun/berserk-cilt-15":
        return httpx.Response(200, text=DETAIL_15)
    return httpx.Response(404, text="not found")


@pytest.fixture()
def scraper():
    return make_scraper(default_handler)


def _by_url(results, fragment: str):
    matches = [r for r in results if fragment in r.product_url]
    assert len(matches) == 1
    return matches[0]


def test_parses_showcase_cards(scraper):
    results = scraper.search("berserk")
    r17 = _by_url(results, "/urun/berserk-cilt-17")
    assert r17.title == "Berserk Cilt 17"
    assert r17.series_title == "Berserk"
    assert r17.volume_number == 17
    assert r17.publisher == "Athica Yayınları"
    assert r17.price == Decimal("238.00")
    assert r17.currency == "TRY"
    assert r17.in_stock is True
    assert r17.image_url == (
        "https://www.gerekliseyler.com.tr/myassets/products/"
        "594/9786258502763-front-cover_min.jpg"
    )
    assert r17.relevance == 1.0
    assert r17.store_id == "gerekliseyler"


def test_sold_out_label_flags_out_of_stock(scraper):
    results = scraper.search("berserk")
    assert _by_url(results, "/urun/berserk-cilt-16").in_stock is False
    assert _by_url(results, "/urun/berserk-cilt-17").in_stock is True


def test_pagination_tp_and_url_dedupe(scraper):
    results = scraper.search("berserk")
    urls = [r.product_url for r in results]
    # cilt 15 only exists on page 2 -> pagination via ?tp= happened;
    # page 2 has a new item, so the scraper also fetches (empty) page 3
    # and stops there
    assert any("/urun/berserk-cilt-15" in u for u in urls)
    assert len(urls) == len(set(urls))
    stats = scraper.stats
    assert stats["pages_fetched"] == 3
    assert stats["duplicates_skipped"] == 1
    assert stats["stop_reason"] == "empty_page"


def test_no_new_items_stops_pagination():
    """A page where every card is a duplicate stops pagination early."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama/berserk":
            page = _page_of(request)
            if page == 1:
                return httpx.Response(200, text=SEARCH_P1)
            # page 2: only the cilt-17 card again -> no new items
            return httpx.Response(200, text=SEARCH_P2.replace(
                '/urun/berserk-cilt-15', '/urun/berserk-cilt-17'
            ).replace('Berserk Cilt 15', 'Berserk Cilt 17'))
        return httpx.Response(200, text=EMPTY_PAGE)

    scraper = make_scraper(handler)
    results = scraper.search("berserk")
    assert scraper.stats["pages_fetched"] == 2
    assert scraper.stats["duplicates_skipped"] == 2
    assert scraper.stats["stop_reason"] == "no_new_items"
    # only cilt 17 + cilt 16 survive (figure filtered)
    assert {r.volume_number for r in results} == {17, 16}


def test_non_manga_merchandise_filtered(scraper):
    results = scraper.search("berserk")
    titles = [r.title for r in results]
    assert not any("Action Figure" in t for t in titles)
    assert not any("Model Kit" in t for t in titles)
    # action figure + plastic model kit
    assert scraper.stats["rejected"].get("non_manga_keyword") == 2


def test_isbn_enriched_from_stok_kodu_row(scraper):
    results = scraper.search("berserk")
    assert _by_url(results, "/urun/berserk-cilt-17").isbn == "9786258502763"
    assert _by_url(results, "/urun/berserk-cilt-15").isbn == "9786258502190"


def test_enrichment_failure_keeps_search_data():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama/berserk":
            page = _page_of(request)
            if page == 1:
                return httpx.Response(200, text=SEARCH_P1)
            return httpx.Response(200, text=EMPTY_PAGE)
        return httpx.Response(404, text="not found")  # every detail page fails

    scraper = make_scraper(handler)
    results = scraper.search("berserk")
    r17 = _by_url(results, "/urun/berserk-cilt-17")
    assert r17.isbn is None
    # search-page data must survive a failed enrichment request
    assert r17.price == Decimal("238.00")
    assert r17.in_stock is True
    assert r17.publisher == "Athica Yayınları"


def test_blocked_search_fails_fast():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=BLOCKED_PAGE)

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="blocked"):
        scraper.search("berserk")


def test_max_results_stops_search():
    scraper = make_scraper(default_handler, gerekliseyler_max_search_results=1)
    results = scraper.search("berserk")
    assert len(results) == 1
    assert scraper.stats["stop_reason"] == "max_results"
    assert scraper.stats["pages_fetched"] == 1


def test_empty_search_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=EMPTY_PAGE)

    scraper = make_scraper(handler)
    assert scraper.search("berserk") == []
    assert scraper.stats["stop_reason"] == "empty_page"


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a strong merch token of the COMMON relevance filter
    but not of this store's local keyword list: only the common layer can
    reject it, so this proves the filter is wired into the store pipeline.
    """
    page = SEARCH_P1.replace("Berserk Cilt 17", "Berserk Cilt 17 Grandista")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/arama/berserk":
            return httpx.Response(200, text=page)
        if request.url.path == "/urun/berserk-cilt-17":
            return httpx.Response(200, text=DETAIL_17)
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    results = scraper.search("berserk")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture books are untouched (the model-kit and action
    # figure cards in the fixture are rejected by the store's own list)
    assert any("Berserk Cilt 16" in r.title for r in results)
