"""Amazon scraper tests (fixture-backed against amazon.com.tr markup)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.scrapers.amazon import AmazonScraper
from app.scrapers.base import ScraperError
from tests.helpers import fixture_text, mock_client


@pytest.fixture()
def scraper():
    search_html = fixture_text("amazon_search.html")
    detail_html = fixture_text("amazon_detail.html")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/s?k=" in url:
            return httpx.Response(200, text=search_html)
        if "/dp/B0ATHICA0" in url:
            return httpx.Response(200, text=detail_html)
        return httpx.Response(404)

    return AmazonScraper(client=mock_client(handler))


def test_relevant_results_and_filters(scraper):
    results = scraper.search("berserk")
    titles = {r.title for r in results}

    # Relevant volumes kept (duplicate ASIN de-duplicated).
    assert titles == {"Berserk 1", "Berserk 2", "Berserk 3"}
    # Non-manga, collections and unrelated series filtered out.
    assert not any("Tişört" in t for t in titles)
    assert not any("1-4" in t for t in titles)
    assert not any("Gluttony" in t for t in titles)


def test_prices_and_stock(scraper):
    results = {r.title: r for r in scraper.search("berserk")}
    assert results["Berserk 1"].price == Decimal("163.54")
    assert results["Berserk 1"].in_stock is True
    assert results["Berserk 3"].in_stock is False
    assert results["Berserk 3"].price == Decimal("210.00")


def test_sponsored_url_resolved_to_product_page(scraper):
    results = {r.title: r for r in scraper.search("berserk")}
    # The fixture links "Berserk 2" through /gp/aw/crRedir/...; it must be
    # resolved to the canonical /dp/<ASIN> page.
    assert results["Berserk 2"].product_url == "https://www.amazon.com.tr/dp/B0ATHICA02"
    assert results["Berserk 1"].product_url == "https://www.amazon.com.tr/dp/B0ATHICA01"


def test_detail_enrichment_extracts_isbn_publisher_author_language(scraper):
    results = {r.title: r for r in scraper.search("berserk")}
    r1 = results["Berserk 1"]
    assert r1.isbn == "9786059544019"
    assert r1.publisher == "Athica Yayınları"
    assert r1.author == "Kentaro Miura"
    assert r1.language == "Türkçe"


def test_relevance_ordering(scraper):
    results = scraper.search("berserk 1")
    # Exact-volume match ranks first.
    assert results[0].title == "Berserk 1"
    assert results[0].relevance == 1.0


def test_blocked_search_raises_scraper_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="<html>Robot Check</html>")

    s = AmazonScraper(client=mock_client(handler))
    with pytest.raises(ScraperError):
        s.search("berserk")


def test_blocked_detail_keeps_search_result():
    search_html = fixture_text("amazon_search.html")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/s?k=" in url:
            return httpx.Response(200, text=search_html)
        return httpx.Response(503, text="blocked")

    s = AmazonScraper(client=mock_client(handler))
    results = s.search("berserk")
    assert len(results) == 3  # search data survives detail-page block
    assert all(r.isbn is None for r in results)


FIGURE_PRODUCT = (
    '<div data-asin="B0FIGURE01" data-component-type="s-search-result" class="s-result-item">'
    '<h2 class="a-size-mini"><a href="/dp/B0FIGURE01" class="a-link-normal">'
    "<span>Berserk Grandista 16</span></a></h2>"
    '<span class="a-price a-text-price"><span class="a-offscreen">₺1450,00</span></span>'
    '<img class="s-image" src="https://m.media-amazon.com/images/I/fig.jpg" /></div>'
)


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a strong merch token of the COMMON relevance filter
    but not of this store's local keyword list: only the common layer can
    reject it, so this proves the filter is wired into the store pipeline.

    Amazon's unrelated-series gate already drops most merch on exact-series
    queries (a figure title changes the base title), so the realistic path
    for a figure is the 'berserk grandista' query — the search a user would
    run for the figure line.
    """
    search_html = fixture_text("amazon_search.html").replace(
        "</body>", FIGURE_PRODUCT + "</body>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "s?k=" in url:
            return httpx.Response(200, text=search_html)
        if "/dp/" in url:
            return httpx.Response(200, text=fixture_text("amazon_detail.html"))
        return httpx.Response(404)

    scraper = AmazonScraper(client=mock_client(handler))
    results = scraper.search("berserk grandista")
    assert results == []
    assert scraper.stats["rejected"].get("non_manga") == 1

    # exact-series query behavior is unchanged: real volumes kept, figure
    # still dropped (by the unrelated-series gate)
    results = scraper.search("berserk")
    assert {r.title for r in results} == {"Berserk 1", "Berserk 2", "Berserk 3"}
