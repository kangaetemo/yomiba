"""BKM Kitap scraper tests (fixture-backed; endpoint contract live-verified).

The paginated ``search_v2`` (WAW Labs) endpoint is the primary data source;
the ``searchAll`` suggestion feed is covered as a fallback.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

# Module reference on purpose: the autouse conftest fixture patches
# ``app.scrapers.base.get_settings`` (zero backoff / request interval), and
# calling it through the module at test time sees the patched binding.
from app.scrapers import base as scraper_base
from app.scrapers.bkm import BkmScraper
from tests.helpers import fixture_json, fixture_text, mock_client

PAGE1 = "bkm_searchv2_p1.json"
PAGE2 = "bkm_searchv2_p2.json"
PAGE3 = "bkm_searchv2_p3.json"
BERSERK_PAGE = "bkm_searchv2_berserk.json"
FALLBACK_PAGE = "bkm_search.json"

DETAIL_HTML = fixture_text("bkm_detail.html")


def _page_from_request(request: httpx.Request) -> int:
    raw = request.url.params.get("search_params")
    return int(json.loads(raw)["page_number"])


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = BkmScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


def default_handler(request: httpx.Request) -> httpx.Response:
    """One-Piece paginated search: p1/p2/p3 fixtures, then empty pages."""
    if "search_v2" in request.url.path:
        page = _page_from_request(request)
        fixture = {1: PAGE1, 2: PAGE2, 3: PAGE3}.get(page)
        if fixture is None:
            return httpx.Response(200, json={"res": [], "total_item_count": 6})
        return httpx.Response(200, json=fixture_json(fixture))
    if request.url.path.startswith("/berserk-"):
        return httpx.Response(200, text=DETAIL_HTML)
    return httpx.Response(404)


@pytest.fixture()
def scraper():
    """One-Piece search, 3 items per page (fixtures), generous caps."""
    return make_scraper(default_handler, bkm_search_page_size=3,
                        bkm_max_search_pages=5, bkm_max_search_results=100)


# -- pagination -----------------------------------------------------------------

def test_pagination_fetches_all_pages(scraper):
    results = scraper.search("one piece")
    assert len(results) == 4  # vols 55, 54, 53, 52 (toy + collection filtered)
    assert scraper.stats["source"] == "search_v2"
    assert scraper.stats["pages_fetched"] == 3
    assert scraper.stats["total_available"] == 6
    assert scraper.stats["stop_reason"] == "complete"


def test_stats_counts(scraper):
    scraper.search("one piece")
    stats = scraper.stats
    assert stats["raw_products"] == 7  # 3 + 3 + 1 items received
    assert stats["duplicates_skipped"] == 1  # vol 55 repeated on page 2
    assert stats["rejected"] == {"non_book_category": 1, "collection": 1}
    assert stats["accepted"] == 4


def test_results_deduplicated_and_normalized(scraper):
    results = scraper.search("one piece")
    urls = [r.product_url for r in results]
    assert len(urls) == len(set(urls))  # dup id across pages removed

    vol55 = next(r for r in results if r.volume_number == 55)
    assert vol55.title == "One Piece 55. Cilt"
    assert vol55.series_title == "One Piece"
    assert vol55.isbn == "9786256031791"
    assert vol55.price == Decimal("180")
    assert vol55.currency == "TRY"
    assert vol55.in_stock is True
    assert vol55.product_url == "https://bkmkitap.com/one-piece-55"
    assert vol55.publisher == "Gerekli Şeyler Yayıncılık"
    assert vol55.author == "Eiiçiro Oda"

    vol53 = next(r for r in results if r.volume_number == 53)
    assert vol53.in_stock is False  # stock_level "0"


def test_toy_and_collection_are_filtered(scraper):
    titles = [r.title for r in scraper.search("one piece")]
    assert not any("Figür" in t for t in titles)
    assert not any("Set" in t for t in titles)


def test_no_new_items_stops_pagination():
    p1 = fixture_json(PAGE1)
    p2 = {  # same items as page 1: pagination not honoured
        "res": p1["res"], "total_item_count": 10,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            page = _page_from_request(request)
            return httpx.Response(200, json=p1 if page == 1 else p2)
        return httpx.Response(404)

    s = make_scraper(handler, bkm_search_page_size=3)
    results = s.search("one piece")
    assert s.stats["pages_fetched"] == 2
    assert s.stats["stop_reason"] == "no_new_items"
    assert len(results) == 2  # vols 55, 54 (toy filtered)


def test_empty_page_stops_pagination():
    p1 = fixture_json(PAGE1)
    p2 = {"res": [], "total_item_count": 99}

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            page = _page_from_request(request)
            return httpx.Response(200, json=p1 if page == 1 else p2)
        return httpx.Response(404)

    s = make_scraper(handler, bkm_search_page_size=3)
    results = s.search("one piece")
    assert s.stats["pages_fetched"] == 2
    assert s.stats["stop_reason"] == "empty_page"
    assert len(results) == 2


def test_max_pages_bound():
    s = make_scraper(default_handler, bkm_search_page_size=3,
                     bkm_max_search_pages=2, bkm_max_search_results=100)
    results = s.search("one piece")
    assert s.stats["pages_fetched"] == 2
    assert s.stats["stop_reason"] == "max_pages"
    assert [r.volume_number for r in results] == [55, 54, 53]  # vol 52 on p3 unseen


def test_max_results_bound():
    s = make_scraper(default_handler, bkm_search_page_size=3,
                     bkm_max_search_pages=5, bkm_max_search_results=4)
    results = s.search("one piece")
    assert s.stats["stop_reason"] == "max_results"
    assert s.stats["raw_products"] == 4
    assert len(results) == 3  # 4 items kept, toy filtered


def test_mid_page_failure_keeps_collected_pages():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            calls["n"] += 1
            # Page 2 fails persistently (every retry attempt).
            if calls["n"] >= 2:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json=fixture_json(PAGE1))
        return httpx.Response(404)

    s = make_scraper(handler, bkm_search_page_size=3)
    results = s.search("one piece")
    assert s.stats["stop_reason"] == "page_error"
    assert s.stats["pages_fetched"] == 1
    assert len(results) == 2  # page-1 manga kept


def test_no_result_query_returns_empty_without_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            return httpx.Response(
                200, json={"res": [], "total_item_count": 0, "no_result": True}
            )
        return httpx.Response(500, text="fallback must not be called")

    s = make_scraper(handler, bkm_search_page_size=3)
    assert s.search("qarışık-şey") == []
    assert s.stats["source"] == "search_v2"


# -- searchAll fallback -----------------------------------------------------------

def test_falls_back_to_searchall_when_v2_unavailable():
    fallback_payload = fixture_json(FALLBACK_PAGE)

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            return httpx.Response(500, text="waw down")
        if "searchAll" in request.url.path:
            return httpx.Response(200, json=fallback_payload)
        if request.url.path.startswith("/berserk-"):
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(404)

    s = make_scraper(handler)
    results = s.search("berserk")
    assert s.stats["source"] == "searchAll"
    assert s.stats["pages_fetched"] == 1
    assert len(results) == 10

    first = next(r for r in results if r.title == "Berserk 1")
    assert first.isbn == "9786256335424"
    assert first.price == Decimal("182")
    # searchAll carries no publisher/author; detail enrichment fills them.
    assert first.publisher == "Athica Yayınları"
    assert first.author == "Kentaro Miura"
    assert first.language == "Turkish"


def test_fallback_out_of_stock():
    fallback_payload = fixture_json(FALLBACK_PAGE)
    fallback_payload["products"][0]["stock"] = 0

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            return httpx.Response(503, text="waw down")
        if "searchAll" in request.url.path:
            return httpx.Response(200, json=fallback_payload)
        return httpx.Response(404)

    s = make_scraper(handler)
    results = s.search("berserk")
    first = next(r for r in results if r.title == "Berserk 1")
    assert first.in_stock is False


# -- primary path: fields + enrichment ---------------------------------------------

def test_searchv2_fields_and_enrichment():
    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            return httpx.Response(200, json=fixture_json(BERSERK_PAGE))
        if request.url.path.startswith("/berserk-"):
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(404)

    s = make_scraper(handler, bkm_search_page_size=3)
    results = s.search("berserk")
    assert len(results) == 2
    assert s.stats["stop_reason"] == "complete"
    assert s.stats["total_available"] == 2

    first = next(r for r in results if r.title == "Berserk 1")
    assert first.series_title == "Berserk"
    assert first.volume_number == 1
    assert first.isbn == "9786256335424"
    assert first.price == Decimal("182")
    assert first.in_stock is True
    # publisher/author come from the search item; language from the detail page
    assert first.publisher == "Athica Yayınları"
    assert first.author == "Kentaro Miura"
    assert first.language == "Turkish"


def test_enrichment_failure_keeps_search_result():
    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            return httpx.Response(200, json=fixture_json(BERSERK_PAGE))
        return httpx.Response(500, text="detail page down")

    s = make_scraper(handler, bkm_search_page_size=3)
    results = s.search("berserk")
    assert len(results) == 2
    assert results[0].isbn == "9786256335424"
    assert results[0].publisher == "Athica Yayınları"  # from search item
    assert results[0].language is None  # enrichment failed


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a strong merch token of the COMMON relevance filter
    but not of this store's local keyword list: only the common layer can
    reject it, so this proves the filter is wired into the store pipeline.

    The mutated item deliberately keeps BKM's *book* category
    ("Edebiyat Kitapları"): a book category is only book evidence — it must
    NOT shield a strong title token (BKM has mislabeled figures under book
    categories before).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            page = _page_from_request(request)
            fixture = {1: PAGE1, 2: PAGE2, 3: PAGE3}.get(page)
            if fixture is None:
                return httpx.Response(200, json={"res": [], "total_item_count": 6})
            data = fixture_json(fixture)
            if page == 1:
                data["res"][0]["title"] = "One Piece 55. Cilt Grandista"
            return httpx.Response(200, json=data)
        if request.url.path.startswith("/berserk-"):
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(404)

    scraper = make_scraper(handler, bkm_search_page_size=3,
                           bkm_max_search_pages=5, bkm_max_search_results=100)
    results = scraper.search("one piece")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture books survive (toy/collection are local rejects)
    assert {r.title for r in results} == {
        "One Piece 54. Cilt", "One Piece 53. Cilt", "One Piece 52. Cilt",
    }
