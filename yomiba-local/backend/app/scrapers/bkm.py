"""BKM Kitap scraper (live-verified against bkmkitap.com).

Data sources (all public, no authentication):

1. Search (paginated): ``GET https://bkm-best.wawlabs.com/search_v2?search_params={json}``
   The search results page (``www.bkmkitap.com/arama?q=...``) is rendered by a
   WAW Labs widget that calls this endpoint with a JSON payload::

       {"row_per_page": N, "page_number": N, "query": "q",
        "facet": [...], "filter": [...]}

   The response carries ``res[]`` (the page of products), ``total_item_count``
   and, per item, ``gtin`` (ISBN-13), ``publisher``/``brand``, ``writer``,
   ``stock_level``, ``category`` and prices. This is the only BKM endpoint
   that supports pagination; the ``searchAll`` endpoint below is a suggestion
   feed capped at 10 items.

2. Fallback: ``GET https://cdn.bkmkitap.com/srv/service/product/searchAll/{q}?language=tr``
   BKM's own suggestion endpoint; used only when the WAW endpoint is
   unavailable (network error / HTTP error on the first page).

3. Detail page (enrichment, best effort): the product page embeds schema.org
   JSON-LD with ``publisher, author, inLanguage, isbn, offers``.

Behaviour:

* Pagination is bounded by the ``bkm_search_page_size``,
  ``bkm_max_search_pages`` and ``bkm_max_search_results`` settings and stops
  early when the API reports that all items were fetched, a page comes back
  empty, or a page yields no new items (pagination not honoured).
* Results are deduplicated by product id within a single search.
* Non-book merchandise (category without "kitap"), non-manga keywords and
  collections/boxes are filtered out.
* Diagnostics (pages fetched, raw / accepted / rejected counts) are exposed
  on ``self.stats`` after each search.

The scraper never writes to the database.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import quote_plus

from ..normalization import normalize_isbn, normalize_text, parse_volume_title
from .base import BaseScraper, ScraperError
from .common import parse_tr_price
from .search_result import SearchResult
from .relevance import filter_manga_results

logger = logging.getLogger("yomiba.scraper.bkm")

#: Merchandise that must never enter the manga catalog (folded Turkish
#: keywords, substring-matched on the normalized title).
NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "figur",
    "asorti",
    "oyuncak",
    "puzzle",
    "kupa",
    "tisort",
    "poster",
    "defter",
    "pelus",
    "kutulu fig",
)


class BkmScraper(BaseScraper):
    store_id = "bkm"
    store_name = "BKM Kitap"
    base_url = "https://www.bkmkitap.com"
    #: WAW Labs search service behind www.bkmkitap.com/arama (paginated).
    search_endpoint = "https://bkm-best.wawlabs.com/search_v2"
    #: BKM's own suggestion feed (max 10 items) - fallback only.
    fallback_search_endpoint = (
        "https://cdn.bkmkitap.com/srv/service/product/searchAll/{query}"
    )

    def search(self, query: str) -> list[SearchResult]:
        self.stats = {
            "source": None,
            "pages_fetched": 0,
            "total_available": None,
            "raw_products": 0,
            "duplicates_skipped": 0,
            "rejected": {},
            "accepted": 0,
            "stop_reason": None,
        }

        try:
            raw_items = self._search_v2(query)
            self.stats["source"] = "search_v2"
        except ScraperError as exc:
            # The WAW endpoint is third-party infrastructure; if it is down we
            # still want *something* from BKM's own CDN.
            logger.warning(
                "bkm: search_v2 unavailable (%s); falling back to searchAll", exc
            )
            raw_items = self._search_fallback(query)
            self.stats["source"] = "searchAll"

        results: list[SearchResult] = []
        for item in raw_items:
            try:
                result, reason = self._parse_search_item(item)
            except Exception:  # one bad product must not kill the whole search
                logger.exception("bkm: failed to parse product: %r", item.get("id"))
                self.stats["rejected"]["parse_error"] = (
                    self.stats["rejected"].get("parse_error", 0) + 1
                )
                continue
            if reason is not None:
                self.stats["rejected"][reason] = (
                    self.stats["rejected"].get(reason, 0) + 1
                )
                continue
            results.append(result)

        results = self._enrich_with_details(results)
        results = filter_manga_results(results, stats=self.stats)
        self.stats["accepted"] = len(results)
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results

    # -- search_v2 (paginated) ---------------------------------------------------
    def _search_v2(self, query: str) -> list[dict]:
        """Fetch search pages from the WAW ``search_v2`` endpoint (bounded)."""
        page_size = max(1, self.settings.bkm_search_page_size)
        max_pages = max(1, self.settings.bkm_max_search_pages)
        max_results = max(1, self.settings.bkm_max_search_results)

        items: list[dict] = []
        seen_ids: set[str] = set()
        total_available: int | None = None

        for page in range(1, max_pages + 1):
            try:
                data = self._fetch_searchv2_page(query, page, page_size)
            except ScraperError as exc:
                if page == 1:
                    raise  # nothing fetched yet -> let the caller fall back
                logger.warning(
                    "bkm: search_v2 page %s failed (%s); keeping %s items",
                    page,
                    exc,
                    len(items),
                )
                self.stats["stop_reason"] = "page_error"
                break
            self.stats["pages_fetched"] += 1

            page_items = data.get("res")
            if not isinstance(page_items, list):
                raise ScraperError(
                    "bkm: unexpected search_v2 payload (missing 'res' list)"
                )
            if total_available is None:
                total_available = data.get("total_item_count")
                if not isinstance(total_available, int):
                    total_available = None
                self.stats["total_available"] = total_available
            if not page_items:
                self.stats["stop_reason"] = "empty_page"
                break

            new_on_page = 0
            for item in page_items:
                if not isinstance(item, dict):
                    continue
                self.stats["raw_products"] += 1
                item_id = str(item.get("id") or item.get("link") or "")
                if item_id and item_id in seen_ids:
                    self.stats["duplicates_skipped"] += 1
                    continue
                if item_id:
                    seen_ids.add(item_id)
                items.append(item)
                new_on_page += 1
                if len(items) >= max_results:
                    self.stats["stop_reason"] = "max_results"
                    break

            if self.stats["stop_reason"] == "max_results":
                break
            if new_on_page == 0:
                # Server is repeating already-seen items: pagination is not
                # being honoured, so fetching more pages cannot help.
                self.stats["stop_reason"] = "no_new_items"
                break
            if total_available is not None and len(items) >= total_available:
                self.stats["stop_reason"] = "complete"
                break
        else:
            self.stats["stop_reason"] = "max_pages"

        return items

    def _fetch_searchv2_page(self, query: str, page: int, page_size: int) -> dict:
        payload = {
            "row_per_page": page_size,
            "page_number": page,
            "query": query,
            "facet": [
                {"field": "category", "type": "value"},
                {"field": "writer", "type": "value"},
            ],
            "filter": [
                {"field": "category", "type": "value", "values": []},
                {"field": "writer", "type": "value", "values": []},
            ],
        }
        url = (
            f"{self.search_endpoint}"
            f"?search_params={quote_plus(json.dumps(payload))}"
        )
        data = self.get_json(url, headers={"Referer": f"{self.base_url}/"})
        if not isinstance(data, dict):
            raise ScraperError("bkm: unexpected search_v2 payload (not an object)")
        return data

    # -- searchAll fallback (max 10 suggestions) ---------------------------------
    def _search_fallback(self, query: str) -> list[dict]:
        url = f"{self.fallback_search_endpoint.format(query=quote_plus(query))}?language=tr"
        data = self.get_json(
            url, headers={"Accept": "application/json", "Referer": f"{self.base_url}/"}
        )
        products = data.get("products", []) if isinstance(data, dict) else []
        if not isinstance(products, list):
            raise ScraperError(f"bkm: unexpected search payload for {query!r}")
        self.stats["pages_fetched"] = 1

        items: list[dict] = []
        for product in products:
            if not isinstance(product, dict):
                continue
            self.stats["raw_products"] += 1
            relative_url = (product.get("url") or "").strip()
            if relative_url and not relative_url.startswith("http"):
                relative_url = f"{self.base_url}/{relative_url.lstrip('/')}"
            items.append(
                {
                    "id": product.get("id"),
                    "title": product.get("title"),
                    "link": relative_url or None,
                    "image": product.get("image"),
                    "price": None,
                    "sale_price": None,
                    "price_sell": product.get("price_sell"),
                    "price_not_discounted": product.get("price_not_discounted"),
                    "stock_level": (
                        str(product["stock"])
                        if product.get("stock") is not None
                        else None
                    ),
                    "gtin": product.get("product_code") or product.get("barcode"),
                    "publisher": None,
                    "brand": None,
                    "writer": None,
                    "category": None,
                }
            )
        return items

    # -- parsing -------------------------------------------------------------------
    @staticmethod
    def _is_non_manga(title: str) -> bool:
        normalized = normalize_text(title)
        return any(keyword in normalized for keyword in NON_MANGA_KEYWORDS)

    def _parse_search_item(self, item: dict) -> tuple[SearchResult | None, str | None]:
        """Normalize one search item.

        Returns ``(result, None)`` on success or ``(None, reason)`` when the
        item is filtered out.
        """
        title = (item.get("title") or "").strip()
        if not title:
            return None, "no_title"

        category = (item.get("category") or "").strip()
        if category and "kitap" not in category.lower():
            logger.debug("bkm: skipping non-book item %r (%s)", title, category)
            return None, "non_book_category"

        if self._is_non_manga(title):
            logger.debug("bkm: skipping non-manga item: %r", title)
            return None, "non_manga_keyword"

        parsed = parse_volume_title(title)
        if parsed.is_collection:
            logger.debug("bkm: skipping collection: %r", title)
            return None, "collection"

        link = (item.get("link") or "").strip()
        if not link:
            return None, "no_url"
        product_url = (
            link if link.startswith("http") else f"{self.base_url}/{link.lstrip('/')}"
        )

        # price_sell is the effective selling price (equals price when there
        # is no discount); fall back to the raw fields.
        price = parse_tr_price(item.get("price_sell"))
        if price is None:
            price = parse_tr_price(item.get("sale_price"))
        if price is None:
            price = parse_tr_price(item.get("price"))
        if price is None:
            price = parse_tr_price(item.get("price_not_discounted"))

        stock = item.get("stock_level")
        in_stock = True if stock in (None, "") else str(stock) != "0"

        isbn = normalize_isbn(item.get("gtin"))
        publisher = (item.get("brand") or item.get("publisher") or "").strip() or None
        author = (item.get("writer") or "").strip() or None

        return (
            SearchResult(
                store_id=self.store_id,
                store_name=self.store_name,
                title=title,
                product_url=product_url,
                series_title=parsed.base_title or None,
                volume_number=parsed.volume_number,
                isbn=isbn,
                publisher=publisher,
                author=author,
                category=category or None,
                price=price,
                currency="TRY",
                in_stock=in_stock,
                image_url=item.get("image") or None,
                # search_v2 already filters on the query; rank exact volume
                # hits above unnumbered items.
                relevance=1.0 if parsed.volume_number is not None else 0.8,
            ),
            None,
        )

    # -- detail-page enrichment (publisher / author / language) --------------------
    def _enrich_with_details(self, results: list[SearchResult]) -> list[SearchResult]:
        """Best-effort enrichment with detail-page JSON-LD.

        One failing detail request never loses the search result; it is kept
        with whatever metadata the search endpoint provided.
        """
        limit = self.settings.max_detail_requests
        for index, result in enumerate(results[:limit]):
            try:
                enriched = self._enrich_one(result)
            except ScraperError:
                logger.warning(
                    "bkm: detail enrichment failed for %s (keeping search data)",
                    result.product_url,
                )
                continue
            except Exception:
                logger.exception(
                    "bkm: unexpected enrichment error for %s", result.product_url
                )
                continue
            results[index] = enriched
        return results

    def _enrich_one(self, result: SearchResult) -> SearchResult:
        response = self.get(result.product_url)
        if response.status_code >= 400:
            raise ScraperError(
                f"bkm: detail page HTTP {response.status_code} for {result.product_url}"
            )
        node = self.product_json_ld_node(self.extract_json_ld(response.text))
        if node is None:
            return result

        updates: dict = {}
        publisher = node.get("publisher")
        if isinstance(publisher, dict) and publisher.get("name"):
            updates["publisher"] = publisher.get("name")
        author = node.get("author")
        if isinstance(author, dict) and author.get("name"):
            updates["author"] = author.get("name")
        if node.get("inLanguage"):
            updates["language"] = node.get("inLanguage")
        if node.get("isbn") and not result.isbn:
            isbn = normalize_isbn(node.get("isbn"))
            if isbn:
                updates["isbn"] = isbn
        if not updates:
            return result
        return result.model_copy(update=updates)
