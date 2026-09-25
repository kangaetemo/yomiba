"""Cizman scraper tests (fixture-backed; endpoint contract live-verified
against cizman.com on 2026-09-10: public ASP.NET search form
(GET / -> __VIEWSTATE/__RequestVerificationToken -> POST / with
ctl00$YeniHeader$txtbxArama), single rendered results page,
``div.productItem`` cards, add-to-cart button == in stock,
product page "Stok Kodu" for the ISBN)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from app.scrapers import base as scraper_base
from app.scrapers.base import ScraperError
from app.scrapers.cizman import CizmanScraper
from tests.helpers import fixture_text, mock_client

HOME = fixture_text("cz_home.html")
SEARCH = fixture_text("cz_search.html")
DETAIL_19 = fixture_text("cz_detail.html")
HOME_NO_TOKEN = HOME.replace(
    '<input type="hidden" name="__VIEWSTATE" value="dDwxMDA+PgIKBAICBAICBA=="/>', ""
).replace(
    '<input type="hidden" name="__RequestVerificationToken" value="tKN-abc123"/>', ""
)
BLOCKED_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>challenge-platform Enable JavaScript and cookies to continue"
    "</body></html>"
)


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = CizmanScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


class PostRecorder:
    """Records the form fields of every POST the store receives."""

    def __init__(self):
        self.posts: list[bytes] = []


def make_handler(recorder: PostRecorder | None = None, *, blocked: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/" and request.method == "GET":
            if blocked:
                return httpx.Response(403, text=BLOCKED_PAGE)
            return httpx.Response(200, text=HOME)
        if request.url.path == "/" and request.method == "POST":
            if recorder is not None:
                recorder.posts.append(request.content)
            if blocked:
                return httpx.Response(403, text=BLOCKED_PAGE)
            if b"txtbxArama=" not in request.content:
                return httpx.Response(500, text="missing query")
            return httpx.Response(200, text=SEARCH)
        if request.url.path == "/berserk-19":
            return httpx.Response(200, text=DETAIL_19)
        return httpx.Response(404, text="not found")

    return handler


@pytest.fixture()
def recorder():
    return PostRecorder()


@pytest.fixture()
def scraper(recorder):
    return make_scraper(make_handler(recorder))


def _by_url(results, fragment: str):
    matches = [r for r in results if fragment in r.product_url]
    assert len(matches) == 1
    return matches[0]


def test_token_flow_posts_public_form(recorder):
    make_scraper(make_handler(recorder)).search("berserk")
    assert len(recorder.posts) == 1
    body = recorder.posts[0].decode()
    assert "__VIEWSTATE=dDwxMDA%2BPgIKBAICBAICBA%3D%3D" in body
    assert "__RequestVerificationToken=tKN-abc123" in body
    assert "ctl00%24YeniHeader%24txtbxArama=berserk" in body


def test_parses_cards(scraper):
    results = scraper.search("berserk")
    r19 = _by_url(results, "/berserk-19")
    assert r19.title == "Berserk 19"
    assert r19.series_title == "Berserk"
    assert r19.volume_number == 19
    assert r19.publisher == "Athica Yayınları"
    assert r19.price == Decimal("205.00")
    assert r19.in_stock is True
    assert r19.image_url == "https://cdn.cizman.com/images/9786258858068.jpg"
    assert r19.relevance == 1.0

    r18 = _by_url(results, "/berserk-18")
    assert r18.price == Decimal("238.00")
    assert r18.in_stock is True


def test_out_of_stock_card_has_no_add_to_cart(scraper):
    results = scraper.search("berserk")
    assert _by_url(results, "/berserk-cilt-8").in_stock is False


def test_non_manga_fig_filtered(scraper):
    results = scraper.search("berserk")
    titles = [r.title for r in results]
    assert not any("Fig" in t for t in titles)
    assert not any("Model Kit" in t for t in titles)
    # 25cm fig + plastic model kit
    assert scraper.stats["rejected"].get("non_manga_keyword") == 2
    assert scraper.stats["stop_reason"] == "single_page"


def test_relevance_guard_filters_unrelated_cards(scraper):
    """Cizman's search is loose: "berserk" returns unrelated products
    (verified live). They must be filtered out, not imported."""
    results = scraper.search("berserk")
    titles = [r.title for r in results]
    assert not any("Mushoku" in t for t in titles)
    assert not any("Lonely Deaths" in t for t in titles)
    assert scraper.stats["rejected"].get("irrelevant") == 2
    # only the real berserk cards survive
    assert sorted(r.title for r in results) == [
        "Berserk 18", "Berserk 19", "Berserk Cilt 8"
    ]


def test_usd_price_uses_tlfiyati():
    """English imports show a USD price; the hidden tlfiyati span carries
    the store's own TRY equivalent, which is what gets recorded."""
    results = make_scraper(make_handler(None)).search("lonely deaths")
    r = _by_url(results, "/lonely-deaths-lie-thick-as-snow-1")
    assert r.price == Decimal("720.49")
    assert r.currency == "TRY"
    assert r.in_stock is True
    # the unrelated TRY card is guarded out for this query
    assert all("Mushoku" not in t.title for t in results)


def test_isbn_enriched_from_product_page(scraper):
    results = scraper.search("berserk")
    assert _by_url(results, "/berserk-19").isbn == "9786258858068"
    # detail page 404 -> enrichment keeps search data, isbn stays None
    assert _by_url(results, "/berserk-18").isbn is None
    assert _by_url(results, "/berserk-18").price == Decimal("238.00")


def test_missing_token_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=HOME_NO_TOKEN)

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="search form"):
        scraper.search("berserk")


def test_blocked_fails_fast(recorder):
    scraper = make_scraper(make_handler(recorder, blocked=True))
    with pytest.raises(ScraperError, match="blocked"):
        scraper.search("berserk")
    assert recorder.posts == []  # never even reached the POST


def test_max_results_stops_search():
    scraper = make_scraper(make_handler(None), cizman_max_search_results=2)
    results = scraper.search("berserk")
    assert len(results) == 2
    assert scraper.stats["stop_reason"] == "max_results"


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a strong merch token of the COMMON relevance filter
    but not of this store's local keyword list: only the common layer can
    reject it, so this proves the filter is wired into the store pipeline.
    """
    merch_page = SEARCH.replace("Berserk 19", "Berserk 19 Grandista")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/" and request.method == "GET":
            return httpx.Response(200, text=HOME)
        if request.url.path == "/" and request.method == "POST":
            if b"txtbxArama=" not in request.content:
                return httpx.Response(500, text="missing query")
            return httpx.Response(200, text=merch_page)
        if request.url.path == "/berserk-19":
            return httpx.Response(200, text=DETAIL_19)
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    results = scraper.search("berserk")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture books are untouched
    assert any("Berserk 18" in r.title for r in results)
