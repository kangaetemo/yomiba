"""Kitapsec scraper tests (fixture-backed; endpoint contract live-verified
against kitapsec.com on 2026-09-10: /Arama/index.php?a=<q>&arama=<page>-1-...
SSR grid where every row carries schema.org microdata: name / sku=ISBN /
url / image / offers price + availability link)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from app.scrapers import base as scraper_base
from app.scrapers.base import ScraperError
from app.scrapers.kitapsec import KitapsecScraper
from tests.helpers import fixture_text, mock_client

SEARCH_P1 = fixture_text("ks_search_p1.html")
SEARCH_P2 = fixture_text("ks_search_p2.html")
EMPTY_PAGE = "<html><body><div id='urunListesi'></div></body></html>"
BLOCKED_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>challenge-platform Enable JavaScript and cookies to continue"
    "</body></html>"
)


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = KitapsecScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


def _page_of(request: httpx.Request) -> int:
    # page is the FIRST segment of the "arama" parameter (verified live:
    # arama=2-1-... -> page 2; the second segment is the sort option).
    value = request.url.params.get("arama", "1-1-0a0-0-0-0-0-0")
    return int(value.split("-", 1)[0])


def default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/Arama/index.php":
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


def _by_url(results, fragment: str):
    matches = [r for r in results if fragment in r.product_url]
    assert len(matches) == 1
    return matches[0]


def test_microdata_row_parsing(scraper):
    results = scraper.search("berserk")
    r1 = _by_url(results, "Berserk-Cilt-1")
    assert r1.title == "Berserk Cilt 1 Athica Yayınları"
    assert r1.series_title == "Berserk"
    assert r1.volume_number == 1
    assert r1.isbn == "9786256335424"
    assert r1.price == Decimal("196.00")
    assert r1.currency == "TRY"
    assert r1.in_stock is True
    assert r1.image_url == "https://www.kitapsec.com/images/products/105351.jpg"
    # publisher is embedded in the title; NOT split out (no guessing)
    assert r1.publisher is None
    assert r1.relevance == 1.0


def test_out_of_stock_availability(scraper):
    results = scraper.search("berserk")
    assert _by_url(results, "Berserk-Cilt-2").in_stock is False


def test_collection_range_filtered(scraper):
    results = scraper.search("berserk")
    titles = [r.title for r in results]
    assert not any("Set" in t for t in titles)
    assert scraper.stats["rejected"].get("collection") == 1


def test_pagination_first_segment_and_dedupe(scraper):
    results = scraper.search("berserk")
    # cilt 3 only exists on page 2 -> pagination happened (page = FIRST
    # segment of "arama"); cilt 1 deduped; page 2 has a new item so the
    # scraper also fetches (empty) page 3 and stops there
    assert any("Berserk-Cilt-3" in r.product_url for r in results)
    urls = [r.product_url for r in results]
    assert len(urls) == len(set(urls))
    stats = scraper.stats
    assert stats["pages_fetched"] == 3
    assert stats["duplicates_skipped"] == 1
    assert stats["stop_reason"] == "empty_page"


def test_no_new_items_stops_pagination():
    """A page where every row is a duplicate stops pagination early."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Arama/index.php":
            page = _page_of(request)
            if page == 1:
                return httpx.Response(200, text=SEARCH_P1)
            # page 2: only the cilt-1 row again
            return httpx.Response(200, text=SEARCH_P2.replace(
                "Berserk-Cilt-3_Athica_Yayinlari_p.105353",
                "Berserk-Cilt-1_Athica_Yayinlari_p.105351",
            ).replace("Berserk Cilt 3", "Berserk Cilt 1").replace(
                "9786256335448", "9786256335424"
            ))
        return httpx.Response(200, text=EMPTY_PAGE)

    scraper = make_scraper(handler)
    results = scraper.search("berserk")
    assert scraper.stats["pages_fetched"] == 2
    # page 2 carries the cilt-1 row twice (fixture row + converted row)
    assert scraper.stats["duplicates_skipped"] == 2
    assert scraper.stats["stop_reason"] == "no_new_items"


def test_no_detail_requests():
    """Search rows already carry ISBN + stock: zero detail-page traffic."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/Arama/index.php":
            page = _page_of(request)
            return httpx.Response(
                200, text=SEARCH_P1 if page == 1 else (SEARCH_P2 if page == 2 else EMPTY_PAGE)
            )
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    results = scraper.search("berserk")
    assert len(results) == 3
    assert all(p == "/Arama/index.php" for p in paths)


def test_blocked_search_fails_fast():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=BLOCKED_PAGE)

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="blocked"):
        scraper.search("berserk")


def test_max_results_stops_search():
    scraper = make_scraper(default_handler, kitapsec_max_search_results=1)
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
    page = SEARCH_P1.replace(
        "Berserk Cilt 1 Athica Yayınları", "Berserk Cilt 1 Grandista Athica Yayınları"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Arama/index.php":
            p = _page_of(request)
            return httpx.Response(200, text=page if p == 1 else EMPTY_PAGE)
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    results = scraper.search("berserk")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture books are untouched
    assert any("Berserk Cilt 2" in r.title for r in results)
