"""D&R scraper tests (fixture-backed; live site is bot-walled)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.scrapers.base import ScraperError
from app.scrapers.dr import DrScraper
from tests.helpers import fixture_text, mock_client


@pytest.fixture()
def scraper():
    search_html = fixture_text("dr_search.html")
    detail_html = fixture_text("dr_detail.html")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/arama") or "?q=" in url:
            return httpx.Response(200, text=search_html)
        return httpx.Response(200, text=detail_html)

    return DrScraper(client=mock_client(handler))


def test_search_parses_product_grid(scraper):
    results = scraper.search("berserk")
    titles = {r.title for r in results}
    assert titles == {"Berserk 1", "Berserk 2"}
    # Box set + T-shirt filtered.
    assert not any("1-4" in t for t in titles)
    assert not any("Tişört" in t for t in titles)


def test_result_fields(scraper):
    results = {r.title: r for r in scraper.search("berserk")}
    r1 = results["Berserk 1"]
    assert r1.store_id == "dr"
    assert r1.store_name == "D&R"
    assert r1.series_title == "Berserk"
    assert r1.volume_number == 1
    assert r1.price == Decimal("199.90")
    assert r1.product_url == "https://www.dr.com.tr/kitap/berserk-1-athica"
    assert r1.image_url == "https://img.dr.com.tr/berserk-1.jpg"


def test_detail_enrichment(scraper):
    results = {r.title: r for r in scraper.search("berserk")}
    r1 = results["Berserk 1"]
    assert r1.isbn == "9786256335424"
    assert r1.publisher == "Athica Yayınları"
    assert r1.author == "Kentaro Miura"
    assert r1.language == "Turkish"


def test_blocked_site_raises_scraper_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Access Denied")

    s = DrScraper(client=mock_client(handler))
    with pytest.raises(ScraperError):
        s.search("berserk")


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a strong merch token of the COMMON relevance filter
    but not of this store's local keyword list: only the common layer can
    reject it, so this proves the filter is wired into the store pipeline.
    """
    search_html = fixture_text("dr_search.html").replace(
        'title="Berserk 1"', 'title="Berserk 1 Grandista"'
    ).replace(
        '>Berserk 1<', '>Berserk 1 Grandista<'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/arama") or "?q=" in url:
            return httpx.Response(200, text=search_html)
        return httpx.Response(200, text=fixture_text("dr_detail.html"))

    scraper = DrScraper(client=mock_client(handler))
    results = scraper.search("berserk")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture books are untouched
    assert any(r.title == "Berserk 2" for r in results)
