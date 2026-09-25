"""Komikşeyler scraper tests (fixture-backed; endpoint contract
live-verified against komikseyler.com.tr on 2026-09-10: public
WooCommerce Store API /wp-json/wc/store/v1/products?search=<q>
&per_page=100&page=N; sku=ISBN for catalog books, prices in integer
cents, explicit is_in_stock flag)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from app.scrapers import base as scraper_base
from app.scrapers.base import ScraperError
from app.scrapers.komikseyler import KomikseylerScraper
from tests.helpers import fixture_json, fixture_text, mock_client

SEARCH_P1 = fixture_json("kom_search_p1.json")
SEARCH_P2 = fixture_json("kom_search_p2.json")


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = KomikseylerScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


def _page_of(request: httpx.Request) -> int:
    return int(request.url.params.get("page", "1"))


def default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/wp-json/wc/store/v1/products":
        page = _page_of(request)
        payload = SEARCH_P1 if page == 1 else SEARCH_P2
        return httpx.Response(200, json=payload)
    return httpx.Response(404, text="not found")


@pytest.fixture()
def scraper():
    return make_scraper(default_handler)


def _by_url(results, fragment: str):
    matches = [r for r in results if fragment in r.product_url]
    assert len(matches) == 1
    return matches[0]


def test_parses_store_api_products(scraper):
    results = scraper.search("pamuk")
    r = _by_url(results, "kizil-sacli-pamuk-prenses-cilt-3")
    assert r.title == "Kızıl Saçlı Pamuk Prenses Cilt 3"
    assert r.series_title == "Kızıl Saçlı Pamuk Prenses"
    assert r.volume_number == 3
    assert r.isbn == "9786258630282"
    assert r.price == Decimal("175.00")  # 17500 cents -> 175.00
    assert r.currency == "TRY"
    assert r.in_stock is True
    assert r.image_url == "https://komikseyler.com.tr/wp-content/uploads/kpp3.jpg"
    assert r.relevance == 1.0
    assert r.store_id == "komikseyler"


def test_collection_name_filtered(scraper):
    results = scraper.search("manga")
    titles = [r.title for r in results]
    assert not any("SET" in t for t in titles)
    assert scraper.stats["rejected"].get("collection") == 1


def test_non_isbn_sku_kept_without_isbn(scraper):
    results = scraper.search("vanitas")
    r = _by_url(results, "vanitas-nova-cilt-1")
    assert r.isbn is None  # sku "KSY-13002" is not an ISBN
    assert r.in_stock is False
    assert r.price == Decimal("225.00")


def test_html_entity_title_unescaped(scraper):
    results = scraper.search("manga")
    r = _by_url(results, "manga-bir-antholoji")
    assert r.title == "Manga – Bir Antholoji"
    assert r.isbn is None  # empty sku


def test_pagination_stops_on_empty_page(scraper):
    scraper.search("manga")
    stats = scraper.stats
    assert stats["pages_fetched"] == 2
    assert stats["stop_reason"] == "empty_page"
    assert stats["raw_products"] == 4
    assert stats["accepted"] == 3  # collection filtered out


def test_page_error_after_first_page_keeps_items():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wp-json/wc/store/v1/products":
            if _page_of(request) == 1:
                return httpx.Response(200, json=SEARCH_P1)
            return httpx.Response(500, text="server error")
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler, scraper_max_retries=0)
    results = scraper.search("manga")
    assert len(results) == 3
    assert scraper.stats["stop_reason"] == "page_error"


def test_non_list_payload_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "rest_invalid_param"})

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="unexpected search payload"):
        scraper.search("manga")


def test_http_403_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="403"):
        scraper.search("manga")


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a strong merch token of the COMMON relevance filter
    but not of this store's local keyword list: only the common layer can
    reject it, so this proves the filter is wired into the store pipeline.
    """
    import copy

    p1 = copy.deepcopy(SEARCH_P1)
    p1[0]["name"] = p1[0]["name"] + " Grandista"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wp-json/wc/store/v1/products":
            p = int(request.url.params.get("page", "1"))
            return httpx.Response(200, json=p1 if p == 1 else SEARCH_P2)
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    results = scraper.search("pamuk")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture products are untouched (the SET item is dropped by
    # the collection filter, not the relevance filter)
    assert any("Vanitas Nova Cilt 1" in r.title for r in results)
