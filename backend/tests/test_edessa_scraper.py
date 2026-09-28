"""Edessa Kitabevi scraper tests (fixture-backed; trimmed from live pages of
edessakitabevi.com, 2026-09-28: products.xml / collections.xml sitemaps, the
``frieren-1`` series collection page's ``__NEXT_DATA__`` product list, and
the ``frieren-cilt-6`` product page JSON-LD)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from app.scrapers import base as scraper_base
from app.scrapers import edessa as edessa_mod
from app.scrapers.base import ScraperError
from app.scrapers.edessa import EdessaScraper, slugify
from tests.helpers import fixture_text, mock_client

PRODUCTS_XML = fixture_text("edessa_products.xml")
COLLECTIONS_XML = fixture_text("edessa_collections.xml")
COLLECTION = fixture_text("edessa_collection_frieren.html")
DETAIL = fixture_text("edessa_detail.html")
BLOCKED_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>challenge-platform Enable JavaScript and cookies to continue"
    "</body></html>"
)


@pytest.fixture(autouse=True)
def _fresh_index_cache():
    edessa_mod._INDEX_CACHE.clear()
    yield
    edessa_mod._INDEX_CACHE.clear()


def make_scraper(handler, **settings_overrides):
    scraper = EdessaScraper(client=mock_client(handler))
    scraper.settings = replace(
        scraper_base.get_settings(),
        scraper_min_request_interval_seconds=0,
        **settings_overrides,
    )
    return scraper


class Site:
    """Fake edessakitabevi.com; records every requested path."""

    def __init__(self, *, detail=DETAIL, collection=COLLECTION, sitemap_status=200,
                 detail_status=200):
        self.paths: list[str] = []
        self.detail = detail
        self.detail_status = detail_status
        self.collection = collection
        self.sitemap_status = sitemap_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        if path == "/products.xml":
            return httpx.Response(self.sitemap_status, text=PRODUCTS_XML)
        if path == "/collections.xml":
            return httpx.Response(self.sitemap_status, text=COLLECTIONS_XML)
        if path == "/frieren-1":
            return httpx.Response(200, text=self.collection)
        if path == "/frieren":
            # The parent collection renders no products server-side.
            return httpx.Response(200, text="<html><body>no data</body></html>")
        if path.startswith("/frieren-cilt-"):
            return httpx.Response(self.detail_status, text=self.detail)
        return httpx.Response(404, text="not found")


def _by_slug(results, slug):
    matches = [r for r in results if r.product_url.endswith("/" + slug)]
    assert len(matches) == 1, [r.product_url for r in results]
    return matches[0]


def test_slugify_matches_ikas_slugs():
    assert slugify("Frieren") == "frieren"
    assert slugify("Ajin: Yarı İnsan") == "ajin-yari-insan"
    assert slugify("One Piece") == "one-piece"


def test_collection_products_carry_price_stock_isbn():
    site = Site()
    results = make_scraper(site).search("Frieren")
    cilt7 = _by_slug(results, "frieren-cilt-7")
    assert cilt7.title == "Frieren Cilt 7"
    assert cilt7.series_title == "Frieren"
    assert cilt7.volume_number == 7
    assert cilt7.isbn == "9786256327733"
    assert cilt7.publisher == "Marmara Çizgi"
    assert cilt7.price == Decimal("143")  # discountPrice, not the 220 list price
    assert cilt7.in_stock is True
    # cover comes from the product sitemap
    assert cilt7.image_url and cilt7.image_url.startswith("https://cdn.myikas.com/")

    cilt5 = _by_slug(results, "frieren-cilt-5")
    assert cilt5.in_stock is False  # stock 0, sellIfOutOfStock false


def test_volumes_missing_from_collection_use_product_page():
    site = Site()
    scraper = make_scraper(site)
    results = scraper.search("Frieren")
    # 7 product slugs; 2 came from the collection page, 5 from product pages.
    assert len(results) == 7
    assert scraper.stats["collections_fetched"] == 2
    assert scraper.stats["details_fetched"] == 5
    assert "/frieren-cilt-7" not in site.paths  # covered by the collection
    detail = _by_slug(results, "frieren-cilt-6")
    assert detail.isbn == "9786256327726"
    assert detail.price == Decimal("143.00")
    assert detail.publisher == "Marmara Çizgi"
    assert detail.category == "Manga ve Manhwa"
    assert detail.in_stock is True


def test_out_of_stock_product_page():
    site = Site(detail=DETAIL.replace("schema.org/InStock", "schema.org/OutOfStock"))
    results = make_scraper(site).search("Frieren")
    assert _by_slug(results, "frieren-cilt-6").in_stock is False


def test_detail_requests_are_capped():
    site = Site()
    scraper = make_scraper(site, edessa_max_detail_requests=2)
    results = scraper.search("Frieren")
    assert scraper.stats["details_fetched"] == 2
    assert scraper.stats["detail_capped"] == 3
    assert len(results) == 4  # 2 from the collection + 2 product pages


def test_unrelated_query_makes_no_page_requests():
    site = Site()
    assert make_scraper(site).search("Berserk") == []
    assert site.paths == ["/products.xml", "/collections.xml"]


def test_prefix_does_not_match_other_titles():
    # "fri" must not pull in "frieren-*" products: only whole slug segments.
    site = Site()
    assert make_scraper(site).search("Fri") == []


def test_sitemaps_are_cached_between_instances():
    site = Site()
    make_scraper(site).search("Frieren")
    site.paths.clear()
    make_scraper(site).search("Berserk")
    assert "/products.xml" not in site.paths
    assert "/collections.xml" not in site.paths


def test_blocked_sitemap_raises():
    site = Site(sitemap_status=403)
    with pytest.raises(ScraperError):
        make_scraper(site).search("Frieren")


def test_blocked_product_page_is_skipped_not_fatal():
    site = Site(detail=BLOCKED_PAGE, detail_status=403)
    scraper = make_scraper(site)
    results = scraper.search("Frieren")
    assert len(results) == 2  # collection products survive
    assert scraper.stats["rejected"]["detail_error"] == 5
