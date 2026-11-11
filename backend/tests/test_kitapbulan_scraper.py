"""Kitapbulan scraper tests (Shopify storefront since 2026-10-24; contract
live-verified that day: /search?q=...&type=product&page=N lists product
links, /products/<handle>.js carries title, vendor, price in kuruş,
availability and the barcode/ISBN).

Kitapbulan-specific: the fuzzy search pads results with unrelated products,
which must be dropped (and must not cost a product JSON request), and
English editions are recognised by the ISBN in the handle."""

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
from app.scrapers.base import ScraperError
from app.scrapers.kitapbulan import KitapbulanScraper, product_handle
from tests.helpers import mock_client

BLOCKED_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>challenge-platform Enable JavaScript and cookies to continue"
    "</body></html>"
)

#: Handles of the "berserk" search as the live store lists them: Turkish
#: volumes, then fuzzy padding (another series, a VIZ edition).
BERSERK_8 = "berserk-8-9786256187986"
BERSERK_CILT_6 = "berserk-cilt-6-9786256187085"
IBLIS_KESER = "iblis-keser-3-cilt-9786257590365"
VIZ_BERSERK = "berserk-deluxe-edition-1-9781506711980"


def _product(handle: str, title: str, *, price: int = 22120, available: bool = True,
             vendor: str = "Athica Yayınları", tags=("Türkçe",)) -> dict:
    isbn = handle.rsplit("-", 1)[-1]
    return {
        "id": 1, "title": title, "handle": handle, "vendor": vendor, "type": "Kitap",
        "tags": list(tags), "price": price, "available": available,
        "featured_image": f"//cdn.shopify.com/s/files/1/0817/files/{isbn}_Default.jpg?v=1",
        "variants": [{"id": 2, "sku": isbn, "barcode": isbn, "price": price, "available": available}],
        "url": f"/products/{handle}",
    }


def _card(handle: str, title: str) -> str:
    # A cover link (image alt only) and a title link to the same product,
    # with Shopify's search tracking parameters.
    href = f"/products/{handle}?_pos=1&_sid=abc&_ss=r"
    return (
        f'<div class="card"><a href="{href}"><img src="x.jpg" alt="{title}"></a>'
        f'<h3><a href="{href}">{title}</a></h3><span>221,20 TL</span></div>'
    )


def _page(*cards: tuple[str, str], padding: int = 0) -> str:
    menu = "".join(f'<li><a href="/collections/k-{i}">Kategori {i}</a></li>' for i in range(padding))
    body = "".join(_card(h, t) for h, t in cards)
    return f"<html><body><nav><ul>{menu}</ul></nav><main>{body}</main><footer>{menu}</footer></body></html>"


EMPTY_PAGE = _page()


def make_scraper(handler, **settings_overrides):
    base_settings = scraper_base.get_settings()
    scraper = KitapbulanScraper(client=mock_client(handler))
    if settings_overrides:
        scraper.settings = replace(base_settings, **settings_overrides)
    return scraper


def _handler(pages: list[str], products: dict[str, dict], log: list[str] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(str(request.url))
        if request.url.path == "/search":
            assert request.url.params.get("type") == "product"
            page = int(request.url.params.get("page", "1"))
            return httpx.Response(200, text=pages[page - 1] if page <= len(pages) else EMPTY_PAGE)
        if request.url.path.startswith("/products/") and request.url.path.endswith(".js"):
            handle = request.url.path[len("/products/"):-len(".js")]
            if handle in products:
                return httpx.Response(200, text=json.dumps(products[handle]))
        return httpx.Response(404, text="not found")
    return handler


BERSERK_PAGES = [
    _page((BERSERK_8, "Berserk 8"), (BERSERK_CILT_6, "Berserk Cilt 6"),
          (VIZ_BERSERK, "Berserk Deluxe Edition 1"), (IBLIS_KESER, "İblis Keser 3.Cilt")),
    _page((BERSERK_8, "Berserk 8"), ("berserk-kutu-set-1-3-9786256180000", "Berserk Kutu Set 1-3")),
]
BERSERK_PRODUCTS = {
    BERSERK_8: _product(BERSERK_8, "Berserk 8"),
    BERSERK_CILT_6: _product(BERSERK_CILT_6, "Berserk Cilt 6", available=False, price=28000),
    IBLIS_KESER: _product(IBLIS_KESER, "İblis Keser 3.Cilt", vendor="Gerekli Şeyler Yayıncılık"),
}


@pytest.fixture()
def log():
    return []


@pytest.fixture()
def scraper(log):
    return make_scraper(_handler(BERSERK_PAGES, BERSERK_PRODUCTS, log))


# -- parsing + relevance guard ---------------------------------------------------

def test_parses_products(scraper):
    results = scraper.search("berserk")
    by_url = {r.product_url: r for r in results}
    assert set(by_url) == {
        f"https://kitapbulan.com/products/{BERSERK_8}",
        f"https://kitapbulan.com/products/{BERSERK_CILT_6}",
    }
    vol8 = by_url[f"https://kitapbulan.com/products/{BERSERK_8}"]
    assert vol8.title == "Berserk 8"
    assert vol8.series_title == "Berserk"
    assert vol8.volume_number == 8
    assert vol8.publisher == "Athica Yayınları"
    assert vol8.isbn == "9786256187986"
    assert vol8.language == "tr"
    assert vol8.price == Decimal("221.20")
    assert vol8.in_stock is True
    assert vol8.image_url == "https://cdn.shopify.com/s/files/1/0817/files/9786256187986_Default.jpg?v=1"

    vol6 = by_url[f"https://kitapbulan.com/products/{BERSERK_CILT_6}"]
    assert vol6.volume_number == 6
    assert vol6.in_stock is False
    assert vol6.price == Decimal("280.00")


def test_stats_counts(scraper):
    scraper.search("berserk")
    stats = scraper.stats
    assert stats["pages_fetched"] == 3  # p1 + p2 + empty p3
    assert stats["raw_products"] == 6
    assert stats["duplicates_skipped"] == 1  # Berserk 8 repeated on p2
    assert stats["rejected"] == {"foreign_edition": 1, "irrelevant": 1, "collection": 1}
    assert stats["accepted"] == 2
    assert stats["stop_reason"] == "empty_page"


def test_unrelated_and_foreign_products_cost_no_request(scraper, log):
    scraper.search("berserk")
    fetched = [url for url in log if url.endswith(".js")]
    assert sorted(fetched) == sorted(
        f"https://kitapbulan.com/products/{h}.js" for h in (BERSERK_8, BERSERK_CILT_6)
    )


def test_title_from_handle_when_links_have_no_text():
    page = (f'<html><body><a href="/products/{BERSERK_8}"><img src="x.jpg"></a>'
            f'<a href="/products/{IBLIS_KESER}"></a></body></html>')
    scraper = make_scraper(_handler([page], BERSERK_PRODUCTS))
    results = scraper.search("berserk")
    assert [r.title for r in results] == ["Berserk 8"]
    assert scraper.stats["rejected"] == {"irrelevant": 1}


def test_short_query_tokens_do_not_gate_relevance(scraper):
    """Tokens shorter than 3 characters ('v', 'tr') are noise."""
    results = scraper.search("v berserk")
    assert len(results) == 2


def test_missing_product_json_drops_the_card():
    products = {BERSERK_8: BERSERK_PRODUCTS[BERSERK_8]}
    scraper = make_scraper(_handler(BERSERK_PAGES[:1], products))
    results = scraper.search("berserk")
    assert [r.volume_number for r in results] == [8]
    assert scraper.stats["rejected"]["detail_failed"] == 1


def test_common_filter_rejects_merchandise_from_search():
    """'Grandista' is a merch token of the COMMON relevance filter only:
    this proves the filter is wired into the store pipeline."""
    handle = "berserk-guts-grandista-figur-4983164000000"
    products = {**BERSERK_PRODUCTS, handle: _product(handle, "Berserk Guts Grandista", vendor="Banpresto")}
    page = _page((BERSERK_8, "Berserk 8"), (handle, "Berserk Guts Grandista"))
    scraper = make_scraper(_handler([page], products))
    results = scraper.search("berserk")
    assert [r.title for r in results] == ["Berserk 8"]
    assert scraper.stats["rejected"].get("non_manga") == 1


# -- blocking -----------------------------------------------------------------------

def test_blocked_search_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text=BLOCKED_PAGE)

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="blocked"):
        scraper.search("berserk")
    assert scraper.stats["pages_fetched"] == 0


def test_search_404_raises():
    """The old T-Soft search (/arama) answers 404 since the move: a broken
    search must fail the store, never read as "no products"."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    with pytest.raises(ScraperError, match="HTTP 404"):
        make_scraper(handler).search("berserk")


# -- bounds -----------------------------------------------------------------------

def test_max_results_bound():
    scraper = make_scraper(_handler(BERSERK_PAGES, BERSERK_PRODUCTS), kitapbulan_max_search_results=1)
    results = scraper.search("berserk")
    assert len(results) == 1
    assert scraper.stats["stop_reason"] == "max_results"
    assert scraper.stats["pages_fetched"] == 1


def test_links_parse_inside_large_storefront_page():
    page = _page((BERSERK_8, "Berserk 8"), padding=2000)
    results = make_scraper(_handler([page], BERSERK_PRODUCTS)).search("berserk")
    assert [r.volume_number for r in results] == [8]


def _numbered(title: str, n: int) -> tuple[str, str]:
    return (f"{title.lower().replace(' ', '-')}-{n}-978625600{n:04d}", f"{title} {n}")


def test_stops_after_two_pages_without_relevant_products():
    pages = [
        _page(_numbered("Berserk", 1)),
        _page(_numbered("Chainsaw Man", 1)),
        _page(_numbered("Chainsaw Man", 2)),
        _page(_numbered("Berserk", 2)),  # never fetched
    ]
    products = {h: _product(h, t) for h, t in (_numbered("Berserk", 1), _numbered("Berserk", 2))}
    scraper = make_scraper(_handler(pages, products))
    results = scraper.search("berserk")
    assert [r.volume_number for r in results] == [1]
    assert scraper.stats["pages_fetched"] == 3
    assert scraper.stats["stop_reason"] == "no_relevant_items"


def test_one_unrelated_page_does_not_stop_paging():
    pages = [_page(_numbered("Berserk", 1)), _page(_numbered("Chainsaw Man", 1)), _page(_numbered("Berserk", 2))]
    products = {h: _product(h, t) for h, t in (_numbered("Berserk", 1), _numbered("Berserk", 2))}
    scraper = make_scraper(_handler(pages, products))
    results = scraper.search("berserk")
    assert sorted(r.volume_number for r in results) == [1, 2]
    assert scraper.stats["stop_reason"] == "empty_page"


# -- listing re-check ---------------------------------------------------------------

def test_check_listing_reads_product_json():
    scraper = make_scraper(_handler([], BERSERK_PRODUCTS))
    check = scraper.check_listing(f"https://kitapbulan.com/products/{BERSERK_CILT_6}")
    assert check.in_stock is False
    assert check.price == Decimal("280.00")


def test_check_listing_old_url_is_unknown(log):
    """Pre-Shopify listing URLs ("www.kitapbulan.com/one-piece-36") are
    gone; they are never requested again."""
    scraper = make_scraper(_handler([], BERSERK_PRODUCTS, log))
    assert scraper.check_listing("https://www.kitapbulan.com/one-piece-36") is None
    assert scraper.check_listing("https://kitapbulan.com/products/gone-9786250000000") is None
    assert log == ["https://kitapbulan.com/products/gone-9786250000000.js"]


def test_product_handle():
    assert product_handle(f"https://kitapbulan.com/products/{BERSERK_8}?_pos=1") == BERSERK_8
    assert product_handle("https://www.kitapbulan.com/berserk-8") is None


# -- collection snapshot -------------------------------------------------------------

def _catalog_entry(handle: str, title: str, *, price: str = "221.20", available: bool = True) -> dict:
    isbn = handle.rsplit("-", 1)[-1]
    return {
        "id": 1, "title": title, "handle": handle, "vendor": "Athica Yayınları",
        "product_type": "Kitap", "tags": ["Athica Yayınları", "Türkçe", "Çizgi Roman"],
        "variants": [{"id": 2, "price": price, "available": available, "sku": isbn}],
        "images": [{"src": f"https://cdn.shopify.com/s/files/1/0817/files/{isbn}.jpg"}],
    }


def _catalog_handler(catalog_pages: list[list[dict]], inner, log: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/products.json") and request.url.path != "/collections/kitap-cizgi-roman/products.json":
            return httpx.Response(200, text=json.dumps({"products": []}))  # kitap-manga
        if request.url.path == "/collections/kitap-cizgi-roman/products.json":
            log.append(str(request.url))
            page = int(request.url.params.get("page", "1"))
            items = catalog_pages[page - 1] if page <= len(catalog_pages) else []
            return httpx.Response(200, text=json.dumps({"products": items}))
        return inner(request)
    return handler


@pytest.fixture()
def snapshot():
    from app.scrapers import kitapbulan
    kitapbulan.reset_catalog()
    yield
    kitapbulan.reset_catalog()


def test_snapshot_products_cost_no_product_json(snapshot, log):
    catalog = [[_catalog_entry(BERSERK_8, "Berserk 8"),
                _catalog_entry(BERSERK_CILT_6, "Berserk Cilt 6", price="280.00", available=False)]]
    handler = _catalog_handler(catalog, _handler(BERSERK_PAGES, BERSERK_PRODUCTS, log), log)
    scraper = make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0)
    results = {r.title: r for r in scraper.search("Berserk")}

    assert results["Berserk 8"].price == Decimal("221.20")
    assert results["Berserk 8"].in_stock is True
    assert results["Berserk 8"].isbn == "9786256187986"
    assert results["Berserk 8"].language == "tr"
    assert results["Berserk Cilt 6"].in_stock is False
    assert results["Berserk Cilt 6"].price == Decimal("280.00")
    assert not any(url.endswith(".js") or "/search" in url for url in log)
    assert scraper.stats["snapshot_hits"] == 2
    assert scraper.stats["pages_fetched"] == 0
    assert scraper.stats["product_json_fetches"] == 0

    # A second search (another import worker) reuses the snapshot.
    log.clear()
    second = make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0)
    assert second.check_listing(f"https://kitapbulan.com/products/{BERSERK_CILT_6}").in_stock is False
    assert log == []


def test_snapshot_pages_until_short_page(snapshot, log):
    full = [_catalog_entry(f"x-{i}-978625000{i:04d}", f"X {i}") for i in range(250)]
    last = [_catalog_entry(BERSERK_8, "Berserk 8")]
    handler = _catalog_handler([full, last], _handler([], BERSERK_PRODUCTS, log), log)
    scraper = make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0)
    assert scraper.check_listing(f"https://kitapbulan.com/products/{BERSERK_8}") is not None
    assert len(log) == 2
    assert not any(url.endswith(".js") for url in log)


def test_product_missing_from_snapshot_uses_product_json(snapshot, log):
    """With snapshot search off, the search page finds a product the
    snapshot lacks and its product JSON fills it in."""
    catalog = [[_catalog_entry(BERSERK_8, "Berserk 8")]]
    handler = _catalog_handler(catalog, _handler(BERSERK_PAGES, BERSERK_PRODUCTS, log), log)
    scraper = make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0, kitapbulan_snapshot_search=False)
    results = {r.title: r for r in scraper.search("Berserk")}
    assert set(results) == {"Berserk 8", "Berserk Cilt 6"}
    assert [url for url in log if url.endswith(".js")] == [
        f"https://kitapbulan.com/products/{BERSERK_CILT_6}.js"
    ]


def test_failed_snapshot_fails_the_store_without_the_search_page(snapshot, log):
    """No snapshot (its read failed): the search page answers 429 for nearly
    every series and each 429 used to be waited out, so the store fails at
    once for the series instead, and the snapshot is not re-read on every
    search."""
    def handler(request: httpx.Request) -> httpx.Response:
        log.append(str(request.url))
        if request.url.path.endswith("/products.json"):
            return httpx.Response(404, text="not found")
        return _handler(BERSERK_PAGES, BERSERK_PRODUCTS)(request)

    with pytest.raises(ScraperError, match="product list not available"):
        make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0).search("Berserk")
    with pytest.raises(ScraperError):
        make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0).search("Berserk")
    assert sum(url.endswith("/products.json?limit=250&page=1") for url in log) == 1
    assert not any("/search" in url for url in log)


def test_snapshot_off_still_uses_the_search_page(snapshot, log):
    scraper = make_scraper(_handler(BERSERK_PAGES, BERSERK_PRODUCTS, log), kitapbulan_catalog_ttl_minutes=0.0)
    assert len(scraper.search("Berserk")) == 2
    assert any("/search" in url for url in log)


def _expire_snapshot(minutes: float) -> None:
    import time as _time
    from app.scrapers import kitapbulan
    kitapbulan._catalog_loaded_at = _time.monotonic() - minutes * 60
    kitapbulan._catalog_retry_at = 0.0


def test_snapshot_refresh_429_keeps_the_old_snapshot_without_waiting(snapshot, log):
    """2026-11-11: the hourly refresh got 429 and waited 4x60 s while every
    import worker waited for it. Now one request, no retry, no store
    cooldown: the previous snapshot keeps serving searches."""
    state = {"limited": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/collections/kitap-cizgi-roman/products.json":
            log.append(str(request.url))
            if state["limited"]:
                return httpx.Response(429, headers={"Retry-After": "60"}, text="slow down")
            return httpx.Response(200, text=json.dumps({"products": [_catalog_entry(BERSERK_8, "Berserk 8")]}))
        if request.url.path.endswith("/products.json"):
            return httpx.Response(200, text=json.dumps({"products": []}))
        return _handler([], BERSERK_PRODUCTS, log)(request)

    assert [r.title for r in make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0).search("berserk")] == ["Berserk 8"]
    _expire_snapshot(61)
    state["limited"] = True
    log.clear()
    scraper = make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0)
    assert [r.title for r in scraper.search("berserk")] == ["Berserk 8"]
    assert log == ["https://kitapbulan.com/collections/kitap-cizgi-roman/products.json?limit=250&page=1"]
    # No cooldown: the store's product JSON is still requested.
    assert scraper.check_listing(f"https://kitapbulan.com/products/{BERSERK_CILT_6}") is not None


def test_too_old_snapshot_is_not_used(snapshot, log):
    state = {"limited": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/products.json"):
            if state["limited"]:
                return httpx.Response(429, text="slow down")
            items = [_catalog_entry(BERSERK_8, "Berserk 8")] if "cizgi" in request.url.path else []
            return httpx.Response(200, text=json.dumps({"products": items}))
        return _handler([], BERSERK_PRODUCTS, log)(request)

    make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0).search("berserk")
    _expire_snapshot(7 * 60)
    state["limited"] = True
    with pytest.raises(ScraperError, match="product list not available"):
        make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0,
                     kitapbulan_catalog_max_stale_minutes=360.0).search("berserk")


def test_snapshot_search_never_requests_the_search_page(snapshot, log):
    """Shopify rate-limits /search (429 for 523 series, 2026-11-05): with a
    snapshot every series is matched by title in it, unrelated and foreign
    products dropped as on the search page."""
    catalog = [[
        _catalog_entry(BERSERK_8, "Berserk 8"),
        _catalog_entry(IBLIS_KESER, "İblis Keser 3.Cilt"),
        _catalog_entry(VIZ_BERSERK, "Berserk Deluxe Edition 1"),
        _catalog_entry("berserk-kutu-set-1-3-9786256180000", "Berserk Kutu Set 1-3"),
    ]]
    handler = _catalog_handler(catalog, _handler(BERSERK_PAGES, BERSERK_PRODUCTS, log), log)
    scraper = make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0)
    assert [r.title for r in scraper.search("berserk")] == ["Berserk 8"]
    assert not any("/search" in url or url.endswith(".js") for url in log)
    assert scraper.stats["stop_reason"] == "snapshot"
    assert scraper.stats["rejected"] == {"foreign_edition": 1, "collection": 1}

    log.clear()
    assert make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0).search("watchmen") == []
    assert log == []


def test_snapshot_reads_every_configured_collection(snapshot, log):
    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request.url.path)
        if request.url.path == "/collections/kitap-manga/products.json":
            return httpx.Response(200, text=json.dumps({"products": [_catalog_entry(BERSERK_8, "Berserk 8")]}))
        if request.url.path == "/collections/kitap-cizgi-roman/products.json":
            return httpx.Response(200, text=json.dumps({"products": [_catalog_entry(BERSERK_CILT_6, "Berserk Cilt 6")]}))
        return httpx.Response(404)

    scraper = make_scraper(handler, kitapbulan_catalog_ttl_minutes=60.0)
    assert sorted(r.volume_number for r in scraper.search("berserk")) == [6, 8]
    assert sorted(log) == ["/collections/kitap-cizgi-roman/products.json", "/collections/kitap-manga/products.json"]
