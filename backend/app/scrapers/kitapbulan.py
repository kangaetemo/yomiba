"""Kitapbulan scraper (live-verified against kitapbulan.com, 2026-09-10).

Data sources (all public, no authentication):

1. Search (paginated): ``GET https://www.kitapbulan.com/arama?q=<query>&pg=<n>``
   Server-side rendered product cards (same T-Soft v5 template as
   Kitap Sepeti):
     * ``a.image-wrapper`` -> product URL (href) + cover (``img[data-original]``)
     * ``a.brand-title``   -> publisher
     * ``a.product-title`` -> title
     * ``.current-price span.product-price`` -> current price ("184,00")
   The pagination parameter is ``pg`` (page size is server-side, ~6 items).

2. Detail page (enrichment, best effort): schema.org JSON-LD ``Product`` with
   ``sku``/``mpn`` (ISBN) or ``isbn``, ``brand``, ``offers`` (price +
   availability).

RELEVANCE GUARD (specific to this store): when a query has no real match the
store pads the results grid with unrelated vitrin products (verified live:
searching "watchmen" renders "Sam & Watson" etc.). Every query token of
length >= 3 must appear in the normalized title or the card is dropped.
This prevents false "in stock" listings for series the store does not carry.

Behaviour mirrors the other store scrapers: bounded pagination, URL
deduplication, non-manga / collection filtering, bot-wall fail-fast
(``looks_like_blocked_page`` -> ``ScraperError``, never retried), and
best-effort JSON-LD enrichment limited by ``settings.max_detail_requests``.
The search cards carry no stock signal, so ``in_stock`` comes from the
detail page ``offers.availability`` when fetched (InStock -> True,
OutOfStock -> False); otherwise it defaults to True (unknown), like the
other stores.

robots.txt allows the site for regular clients (``User-agent: Python`` is
disallowed; the scraper uses the configured browser-like app UA).

The scraper never writes to the database.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus, urljoin

from ..normalization import normalize_isbn, normalize_text, parse_volume_range, parse_volume_title
from .base import BaseScraper, ScraperError
from .common import looks_like_blocked_page, parse_tr_price
from .search_result import SearchResult
from .relevance import filter_manga_results

logger = logging.getLogger("yomiba.scraper.kitapbulan")

NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "figur", "asorti", "puzzle", "kupa", "tisort", "tshirt",
    "poster", "pelus", "mousepad", "kutulu fig",
)


class KitapbulanScraper(BaseScraper):
    store_id = "kitapbulan"
    store_name = "Kitapbulan"
    base_url = "https://www.kitapbulan.com"
    search_path = "/arama?q={query}"
    #: Minimum token length for the relevance guard ("v", "for" etc. are noise).
    _RELEVANCE_TOKEN_MIN_LEN = 3

    def search(self, query: str) -> list[SearchResult]:
        self.stats = {
            "pages_fetched": 0,
            "raw_products": 0,
            "duplicates_skipped": 0,
            "rejected": {},
            "accepted": 0,
            "stop_reason": None,
        }

        query_tokens = [
            normalize_text(token)
            for token in query.split()
            if len(normalize_text(token)) >= self._RELEVANCE_TOKEN_MIN_LEN
        ]

        items = self._search_pages(query)
        results: list[SearchResult] = []
        for item in items:
            result, reason = self._parse_card(item, query_tokens)
            if reason is not None:
                self.stats["rejected"][reason] = self.stats["rejected"].get(reason, 0) + 1
                continue
            results.append(result)

        results = self._enrich_with_details(results)
        self.stats["accepted"] = len(results)
        results = filter_manga_results(results, stats=self.stats)
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results

    # -- paginated search ----------------------------------------------------------
    def _search_pages(self, query: str) -> list[dict]:
        max_pages = max(1, self.settings.kitapbulan_max_search_pages)
        max_results = max(1, self.settings.kitapbulan_max_search_results)

        items: list[dict] = []
        seen_urls: set[str] = set()

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}{self.search_path.format(query=quote_plus(query))}&pg={page}"
            response = self.get(url)
            if looks_like_blocked_page(response.status_code, response.text):
                raise ScraperError(
                    f"kitapbulan: request blocked or robot-checked "
                    f"(HTTP {response.status_code}) for query {query!r}"
                )
            if response.status_code >= 400:
                if page == 1:
                    raise ScraperError(
                        f"kitapbulan: HTTP {response.status_code} for search page 1 ({url})"
                    )
                logger.warning(
                    "kitapbulan: search page %s failed (HTTP %s); keeping %s items",
                    page, response.status_code, len(items),
                )
                self.stats["stop_reason"] = "page_error"
                break
            self.stats["pages_fetched"] += 1

            soup = self.soup(response.text)
            cards = soup.select("div.product-item")
            if not cards:
                self.stats["stop_reason"] = "empty_page"
                break

            new_on_page = 0
            for card in cards:
                self.stats["raw_products"] += 1
                item = self._card_to_item(card)
                if item is None:
                    continue
                if item["url"] in seen_urls:
                    self.stats["duplicates_skipped"] += 1
                    continue
                seen_urls.add(item["url"])
                items.append(item)
                new_on_page += 1
                if len(items) >= max_results:
                    self.stats["stop_reason"] = "max_results"
                    break

            if self.stats["stop_reason"] == "max_results":
                break
            if new_on_page == 0:
                self.stats["stop_reason"] = "no_new_items"
                break
        else:
            self.stats["stop_reason"] = "max_pages"

        return items

    @staticmethod
    def _card_to_item(card) -> dict | None:
        title_anchor = card.select_one("a.product-title")
        if title_anchor is None:
            return None
        title = re.sub(r"\s+", " ", title_anchor.get_text(" ", strip=True))
        href = title_anchor.get("href")
        if not title or not href:
            return None
        url = href if href.startswith("http") else urljoin(KitapbulanScraper.base_url + "/", href)

        publisher_el = card.select_one("a.brand-title")
        publisher = re.sub(r"\s+", " ", publisher_el.get_text(" ", strip=True)) if publisher_el else ""

        price_el = card.select_one(".current-price .product-price") or card.select_one(
            "span.product-price"
        )
        price = parse_tr_price(price_el.get_text(" ", strip=True)) if price_el else None

        img = card.select_one("img")
        image = None
        if img is not None:
            image = img.get("data-original") or img.get("data-src") or img.get("src")

        return {
            "title": title,
            "url": url,
            "publisher": publisher or None,
            "price": price,
            "image": image,
        }

    # -- parsing ---------------------------------------------------------------------
    @staticmethod
    def _is_non_manga(title: str) -> bool:
        normalized = normalize_text(title)
        return any(keyword in normalized for keyword in NON_MANGA_KEYWORDS)

    def _parse_card(
        self, item: dict, query_tokens: list[str]
    ) -> tuple[SearchResult | None, str | None]:
        title = item["title"]
        if self._is_non_manga(title):
            logger.debug("kitapbulan: skipping non-manga item: %r", title)
            return None, "non_manga_keyword"

        parsed = parse_volume_title(title)
        # An omnibus span ("Cilt 5 - 6") may be one 2-in-1 book: the importer
        # decides against the catalog, only real boxes are dropped here.
        if parsed.is_collection and parse_volume_range(title) is None:
            logger.debug("kitapbulan: skipping collection: %r", title)
            return None, "collection"

        # Vitrin fallback guard: the store pads empty results with unrelated
        # products; require every significant query token in the title.
        if query_tokens:
            normalized_title = normalize_text(title)
            if not all(token in normalized_title for token in query_tokens):
                logger.debug("kitapbulan: skipping irrelevant card: %r", title)
                return None, "irrelevant"

        return (
            SearchResult(
                store_id=self.store_id,
                store_name=self.store_name,
                title=title,
                product_url=item["url"],
                series_title=parsed.base_title or None,
                volume_number=parsed.volume_number,
                publisher=item.get("publisher"),
                price=item.get("price"),
                currency="TRY",
                in_stock=True,
                image_url=item.get("image"),
                relevance=1.0,
            ),
            None,
        )

    # -- detail-page enrichment (isbn / publisher / language / stock) ----------------
    def _enrich_with_details(self, results: list[SearchResult]) -> list[SearchResult]:
        limit = self.settings.max_detail_requests
        for index, result in enumerate(results[:limit]):
            try:
                results[index] = self._enrich_one(result)
            except ScraperError:
                logger.warning(
                    "kitapbulan: detail enrichment blocked/failed for %s (keeping search data)",
                    result.product_url,
                )
            except Exception:
                logger.exception("kitapbulan: unexpected enrichment error for %s", result.product_url)
        return results

    def _enrich_one(self, result: SearchResult) -> SearchResult:
        response = self.get(result.product_url)
        if response.status_code >= 400 or looks_like_blocked_page(
            response.status_code, response.text
        ):
            raise ScraperError(
                f"kitapbulan: detail page HTTP {response.status_code} for {result.product_url}"
            )

        node = self.product_json_ld_node(self.extract_json_ld(response.text))
        if node is None:
            return result

        updates: dict = {}
        raw_isbn = node.get("isbn") or node.get("sku") or node.get("mpn")
        if raw_isbn and not result.isbn:
            isbn = normalize_isbn(raw_isbn)
            if isbn:
                updates["isbn"] = isbn
        brand = node.get("brand")
        if isinstance(brand, dict) and brand.get("name") and not result.publisher:
            updates["publisher"] = brand.get("name")
        if node.get("inLanguage") and not result.language:
            updates["language"] = node.get("inLanguage")
        in_stock = self._availability(node.get("offers"))
        if in_stock is not None:
            updates["in_stock"] = in_stock
        if not updates:
            return result
        return result.model_copy(update=updates)

    @staticmethod
    def _availability(offers) -> bool | None:
        """Map schema.org offers.availability to a stock flag (None = unknown)."""
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if not isinstance(offers, dict):
            return None
        value = str(offers.get("availability") or "")
        if "OutOfStock" in value or "Discontinued" in value:
            return False
        if "InStock" in value or "LimitedAvailability" in value or "PreOrder" in value:
            return True
        return None
