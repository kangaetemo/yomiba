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
#: Any other product page: exists, carries no JSON-LD. (A 404 product page
#: now means "removed from the store"; see test_foreign_editions.)
PRODUCT_PAGE = "<html></html>"


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
    return httpx.Response(200, text=PRODUCT_PAGE)


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
    # PRODUCT_PAGE carries no offer: the stale search price is not used.
    assert vol55.price is None
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
        return httpx.Response(200, text=PRODUCT_PAGE)

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
        return httpx.Response(200, text=PRODUCT_PAGE)

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
        return httpx.Response(200, text=PRODUCT_PAGE)

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
        return httpx.Response(200, text=PRODUCT_PAGE)

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
        # The product page exists (sold out, not removed): see test_foreign_editions
        # for removed products (404 page) being dropped.
        return httpx.Response(200, text="<html></html>")

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
        return httpx.Response(200, text=PRODUCT_PAGE)

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
        return httpx.Response(200, text=PRODUCT_PAGE)

    scraper = make_scraper(handler, bkm_search_page_size=3,
                           bkm_max_search_pages=5, bkm_max_search_results=100)
    results = scraper.search("one piece")
    assert not any("Grandista" in r.title for r in results)
    assert scraper.stats["rejected"].get("non_manga") == 1
    # the other fixture books survive (toy/collection are local rejects)
    assert {r.title for r in results} == {
        "One Piece 54. Cilt", "One Piece 53. Cilt", "One Piece 52. Cilt",
    }


def _item(n, title, category, gtin, link):
    return {"ix": n, "id": str(n), "title": title, "category": category, "brand": "Akilcelen", "link": link,
            "price": "230,00", "sale_price": "161,00", "price_sell": "161,00", "price_not_discounted": "230,00",
            "image": None, "writer": "Kouji Miura", "publisher": "akilcelen", "stock_level": "1", "gtin": gtin}


def test_retries_with_cilt_when_the_plain_query_finds_nothing_of_the_series():
    """BKM answers "Mavi Kutu" with boxed pencils only; "Mavi Kutu cilt"
    lists the manga ("Blue Box - Mavi Kutu 2")."""
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            params = json.loads(request.url.params.get("search_params"))
            queries.append(params["query"])
            if params["page_number"] > 1:
                return httpx.Response(200, json={"res": [], "total_item_count": 2})
            if params["query"] == "Mavi Kutu":
                res = [_item(1, "Kalem Seti Mavi Kutu", "Kirtasiye", "8690000000001", "https://bkmkitap.com/kalem")]
            else:
                res = [_item(2, "Blue Box - Mavi Kutu 2", "Edebiyat Kitaplari", "9786256446649",
                             "https://bkmkitap.com/blue-box-mavi-kutu-2")]
            return httpx.Response(200, json={"res": res, "total_item_count": len(res)})
        return httpx.Response(200, text=PRODUCT_PAGE)

    s = make_scraper(handler, bkm_search_page_size=3)
    results = s.search("Mavi Kutu")
    assert [r.title for r in results] == ["Blue Box - Mavi Kutu 2"]
    assert s.stats["retry_query"] == "Mavi Kutu cilt"
    assert queries[0] == "Mavi Kutu" and "Mavi Kutu cilt" in queries
    # A query that already finds the series is not repeated.
    queries.clear()
    s.search("Mavi Kutu cilt")
    assert set(queries) == {"Mavi Kutu cilt"}


# -- product page price wins over the stale search index ----------------------------

def _offer_page(price: str, availability: str = "InStock") -> str:
    node = {"@context": "https://schema.org", "@type": "Product", "name": "x",
            "offers": {"@type": "Offer", "price": price, "priceCurrency": "TRY",
                       "availability": f"https://schema.org/{availability}"}}
    return f'<html><script type="application/ld+json">{json.dumps(node)}</script></html>'


def _sekiro_item(n: int) -> dict:
    return {"id": str(n), "title": f"SEKIRO-Yan Hikâye: Ölümsüz Hanbei {n}", "category": "Kitap",
            "link": f"https://www.bkmkitap.com/sekiro-{n}", "price": "210,00", "price_sell": "210,00",
            "stock_level": "1", "gtin": None, "brand": "Athica", "writer": None}


def test_product_page_price_and_stock_win_over_search():
    """SEKIRO Yan Hikaye Cilt 1, 2026-11-06: search 210 TL, the shop and
    its product page 168 TL. The listing flipped 210 -> 168 -> 210."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            return httpx.Response(200, json={"res": [_sekiro_item(1), _sekiro_item(2)],
                                             "total_item_count": 2})
        if request.url.path == "/sekiro-1":
            return httpx.Response(200, text=_offer_page("168.00"))
        return httpx.Response(200, text=_offer_page("245.00", "OutOfStock"))

    s = make_scraper(handler)
    results = {r.volume_number: r for r in s.search("SEKIRO-Yan Hikâye: Ölümsüz Hanbei")}
    assert (results[1].price, results[1].in_stock) == (Decimal("168.00"), True)
    assert (results[2].price, results[2].in_stock) == (Decimal("245.00"), False)
    assert s.stats["price_unverified"] == 0


def test_page_without_offers_drops_search_price():
    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            return httpx.Response(200, json={"res": [_sekiro_item(1)], "total_item_count": 1})
        return httpx.Response(200, text=PRODUCT_PAGE)

    s = make_scraper(handler)
    [result] = s.search("SEKIRO-Yan Hikâye: Ölümsüz Hanbei")
    assert result.price is None  # the listing keeps its last page price
    assert s.stats["price_unverified"] == 1


def test_related_query_never_writes_the_search_price():
    """Berserk 18-20, 2026-11-06: read at 14:42 (168 TL), flipped back to
    the search's 210 TL at 15:01 by a related title's query that read only
    its first 15 pages. Unread results now carry no price."""
    other = [dict(_sekiro_item(100 + n), title=f"Kalem Kutusu {n}", link=f"https://www.bkmkitap.com/kutu-{n}")
             for n in range(20)]

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            items = other + [_sekiro_item(n) for n in range(1, 31)]
            return httpx.Response(200, json={"res": items, "total_item_count": len(items)})
        return httpx.Response(200, text=_offer_page("168.00"))

    s = make_scraper(handler, bkm_search_page_size=100)
    results = s.search("Kalem Kutusu")
    sekiro = [r for r in results if r.title.startswith("SEKIRO")]
    assert len(sekiro) == 30
    prices = sorted(str(r.price) for r in sekiro)
    assert prices == ["168.00"] * 15 + ["None"] * 15  # 15 pages for other titles
    assert all(r.price == Decimal("168.00") for r in results if r.title.startswith("Kalem"))


def test_page_read_by_one_query_is_reused_by_the_next():
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            items = [_sekiro_item(n) for n in range(1, 31)]
            return httpx.Response(200, json={"res": items, "total_item_count": len(items)})
        pages.append(request.url.path)
        return httpx.Response(200, text=_offer_page("168.00"))

    first = make_scraper(handler, bkm_search_page_size=100)
    first.search("SEKIRO-Yan Hikâye: Ölümsüz Hanbei")
    assert len(pages) == 30
    second = make_scraper(handler, bkm_search_page_size=100)
    results = second.search("Ölümsüz Hanbei")
    assert len(pages) == 30  # nothing read again
    assert second.stats["pages_cached"] == 30
    assert all(r.price == Decimal("168.00") for r in results)


def test_subtitled_query_names_the_short_store_title():
    """"Kamisama Kiss 5" names "Kamisama Kiss -Tanrılık Görevine Başladım"."""
    s = make_scraper(lambda request: httpx.Response(404))
    assert s._names_query("kamisama kiss tanrilik gorevine basladim", "Kamisama Kiss 5")
    assert not s._names_query("berserk deluxe", "Kalem Kutusu 3")


def test_results_beyond_the_page_budget_carry_no_price():
    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            items = [_sekiro_item(n) for n in range(1, 6)]
            return httpx.Response(200, json={"res": items, "total_item_count": len(items)})
        return httpx.Response(200, text=_offer_page("168.00"))

    s = make_scraper(handler, bkm_max_detail_requests=3)
    results = s.search("SEKIRO-Yan Hikâye: Ölümsüz Hanbei")
    assert sorted(str(r.price) for r in results) == ["168.00"] * 3 + ["None"] * 2
    assert s.stats["price_unverified"] == 2


def test_pages_of_results_the_importer_rejects_are_not_read():
    """"Testere Adam", 2026-11-11: 149 of 178 BKM results were İkinci Adam
    Yayınları novels, each a product page read at BKM's request pace. The
    importer's ``page_read_filter`` says which results can never match."""
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            items = [_sekiro_item(1), dict(_sekiro_item(2), brand="İkinci Adam Yayınları")]
            return httpx.Response(200, json={"res": items, "total_item_count": 2})
        pages.append(request.url.path)
        return httpx.Response(200, text=_offer_page("168.00", "OutOfStock"))

    s = make_scraper(handler)
    s.page_read_filter = lambda result: result.publisher != "İkinci Adam Yayınları"
    results = {r.volume_number: r for r in s.search("SEKIRO-Yan Hikâye: Ölümsüz Hanbei")}
    assert pages == ["/sekiro-1"]  # no page read, no gone check for volume 2
    assert results[1].price == Decimal("168.00")
    assert results[2].price is None
    assert s.stats["pages_skipped_publisher"] == 1


def test_detail_reads_overlap_but_keep_budget_and_prices():
    """Slow responses overlap; the price budget and result order do not change."""
    import threading
    from app.scrapers.search_result import SearchResult

    lock = threading.Lock()
    pair = threading.Barrier(2)
    active = peak = calls = 0

    def handler(request):
        nonlocal active, peak, calls
        with lock:
            active += 1
            calls += 1
            peak = max(peak, active)
        try:
            pair.wait(timeout=5)
            return httpx.Response(200, text=DETAIL_HTML)
        finally:
            with lock:
                active -= 1

    scraper = make_scraper(handler, bkm_detail_workers=2, bkm_max_detail_requests=4)
    scraper._page_checked = set()
    scraper.gone_urls = set()
    rows = [SearchResult(store_id="bkm", store_name="BKM", title=f"Berserk {i}",
                         product_url=f"https://bkmkitap.com/parallel-{i}",
                         price=Decimal("999"), in_stock=True) for i in range(6)]
    results = scraper._enrich_with_details(rows, "Berserk")
    assert calls == 4
    assert peak == 2
    assert [r.product_url for r in results] == [r.product_url for r in rows]
    assert all(r.price is not None and r.price != Decimal("999") for r in results[:4])
    assert all(r.price is None for r in results[4:])
    assert scraper.stats["price_unverified"] == 2


def test_concurrent_requests_keep_per_scraper_spacing():
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    starts = []
    lock = threading.Lock()

    def handler(request):
        with lock:
            starts.append(time.monotonic())
        time.sleep(0.08)
        return httpx.Response(200, text=PRODUCT_PAGE)

    scraper = make_scraper(handler, scraper_min_request_interval_seconds=0.04)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(scraper.get, [f"https://bkmkitap.com/pacing-{i}" for i in range(4)]))
    assert len(starts) == 4
    assert all(b - a >= 0.035 for a, b in zip(starts, starts[1:]))


def test_queued_detail_request_obeys_new_store_cooldown(monkeypatch):
    import time
    from app.scrapers.base import ScraperError, _store_cooldowns

    def handler(request):
        pytest.fail("a queued request must not contact a store in cooldown")

    scraper = make_scraper(handler)
    def throttle():
        # A different in-flight request starts the cooldown while we wait.
        monkeypatch.setitem(_store_cooldowns, scraper._store_key(), time.monotonic() + 60)
    monkeypatch.setattr(scraper, "_throttle", throttle)
    with pytest.raises(ScraperError, match="cooldown"):
        scraper.get("https://bkmkitap.com/queued")


@pytest.mark.parametrize("workers", [1, 4])
def test_detail_completion_order_cannot_mix_prices_or_restore_search_price(workers):
    """Compare sequential and concurrent reads against distinct live offers,
    including incomplete and failed pages. Search prices are all stale 210 TL.
    """
    import threading

    second_finished = threading.Event()
    completion_order = []

    def handler(request):
        if "search_v2" in request.url.path:
            return httpx.Response(200, json={"res": [_sekiro_item(i) for i in range(1, 5)],
                                             "total_item_count": 4})
        n = int(request.url.path.rsplit("-", 1)[1])
        if n == 1:
            if workers > 1:
                assert second_finished.wait(timeout=5)
            completion_order.append(n)
            return httpx.Response(200, text=_offer_page("168.00", "OutOfStock"))
        if n == 2:
            completion_order.append(n)
            second_finished.set()
            return httpx.Response(200, text=_offer_page("245.50", "InStock"))
        if n == 3:
            return httpx.Response(200, text=PRODUCT_PAGE)
        return httpx.Response(404)

    scraper = make_scraper(handler, bkm_detail_workers=workers)
    results = {r.volume_number: r for r in scraper.search("SEKIRO-Yan Hikâye: Ölümsüz Hanbei")}
    assert (results[1].price, results[1].in_stock) == (Decimal("168.00"), False)
    assert (results[2].price, results[2].in_stock) == (Decimal("245.50"), True)
    assert results[3].price is None
    assert results[4].price is None
    assert scraper.stats["price_unverified"] == 2
    if workers > 1:
        assert completion_order == [2, 1]


def test_search_pages_after_the_first_are_requested_together():
    """The WAW service took ~20 s per page on 2026-11-12, five pages in a
    row = 100 s per BKM search. Pages 2..n now overlap; results keep page
    order."""
    import threading
    import time as _time

    active = {"now": 0, "max": 0}
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" not in request.url.path:
            return httpx.Response(200, text=PRODUCT_PAGE)
        page = _page_from_request(request)
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        _time.sleep(0.05)
        with lock:
            active["now"] -= 1
        res = [_item(page * 10 + i, f"Berserk {page * 10 + i}", "Kitap", None,
                     f"https://www.bkmkitap.com/berserk-{page * 10 + i}") for i in range(3)]
        return httpx.Response(200, json={"res": res, "total_item_count": 12})

    s = make_scraper(handler, bkm_search_page_size=3, bkm_max_search_pages=5, bkm_detail_workers=4)
    s.stats = {"pages_fetched": 0, "raw_products": 0, "duplicates_skipped": 0, "stop_reason": None}
    raw = s._search_v2("Berserk")
    assert [item["title"] for item in raw] == [f"Berserk {p * 10 + i}" for p in range(1, 5) for i in range(3)]
    assert s.stats["pages_fetched"] == 4
    assert s.stats["stop_reason"] == "complete"
    assert active["max"] >= 2
