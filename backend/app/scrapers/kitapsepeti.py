"""Kitap Sepeti scraper (live-verified against kitapsepeti.com, 2026-09-10).

Data sources (all public, no authentication):

1. Search (paginated): ``GET https://www.kitapsepeti.com/arama?q=<query>&pg=<n>``
   Server-side rendered product cards (T-Soft v5 template):
     * ``a.image-wrapper`` -> product URL (href) + cover image (``img[data-src]``)
     * ``a.brand-title``   -> publisher
     * ``a.product-title`` -> title
     * ``.current-price span.product-price`` -> current price ("182,00")
   The pagination parameter is ``pg`` (page size is server-side, ~32 items).

2. Detail page (enrichment, best effort): schema.org JSON-LD
   ``Product+Book`` with ``isbn, publisher, author, inLanguage, offers``
   (``price`` + ``availability``).

Behaviour mirrors the other store scrapers: bounded pagination, URL
deduplication, non-manga / collection filtering, bot-wall fail-fast
(``looks_like_blocked_page`` -> ``ScraperError``, never retried), and
best-effort JSON-LD enrichment limited by ``settings.max_detail_requests``.

The search cards carry NO stock signal, so ``in_stock`` comes from the
detail page ``offers.availability`` when it is fetched (``InStock`` -> True,
``OutOfStock`` -> False); results whose detail page could not be fetched keep
the default ``in_stock=True`` (unknown), the same convention as the other
stores.

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

logger = logging.getLogger("yomiba.scraper.kitapsepeti")

NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "figur", "asorti", "puzzle", "kupa", "tisort", "tshirt",
    "poster", "pelus", "mousepad", "sabit", "kutulu fig",
)


class KitapsepetiScraper(BaseScraper):
    store_id = "kitapsepeti"
    store_name = "Kitap Sepeti"
    base_url = "https://www.kitapsepeti.com"
    search_path = "/arama?q={query}"
    #: Drops sold-out products from search (see catalog_service
    #: stale_listing_ids); the detail JSON-LD carries offers.availability.
    verifies_unseen_listings = True

    def _limits(self) -> tuple[int, int]:
        """(max search pages, max results) for this store."""
        return (self.settings.kitapsepeti_max_search_pages,
                self.settings.kitapsepeti_max_search_results)

    def search(self, query: str) -> list[SearchResult]:
        self.stats = {
            "pages_fetched": 0,
            "raw_products": 0,
            "duplicates_skipped": 0,
            "rejected": {},
            "accepted": 0,
            "stop_reason": None,
        }

        items = self._search_pages(query)
        query_core = normalize_text(parse_volume_title(query).base_title)
        results: list[SearchResult] = []
        for item in items:
            result, reason = self._parse_card(item, query_core)
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
        pages_limit, results_limit = self._limits()
        max_pages = max(1, pages_limit)
        max_results = max(1, results_limit)

        items: list[dict] = []
        seen_urls: set[str] = set()

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}{self.search_path.format(query=quote_plus(query))}&pg={page}"
            response = self.get(url)
            if looks_like_blocked_page(response.status_code, response.text):
                raise ScraperError(
                    f"{self.store_id}: request blocked or robot-checked "
                    f"(HTTP {response.status_code}) for query {query!r}"
                )
            if response.status_code >= 400:
                if page == 1:
                    raise ScraperError(
                        f"{self.store_id}: HTTP {response.status_code} for search page 1 ({url})"
                    )
                logger.warning(
                    "%s: search page %s failed (HTTP %s); keeping %s items",
                    self.store_id, page, response.status_code, len(items),
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
                # Server is repeating already-seen items: pagination is not
                # being honoured, so fetching more pages cannot help.
                self.stats["stop_reason"] = "no_new_items"
                break
        else:
            self.stats["stop_reason"] = "max_pages"

        return items

    @classmethod
    def _card_to_item(cls, card) -> dict | None:
        title_anchor = card.select_one("a.product-title")
        if title_anchor is None:
            return None
        title = re.sub(r"\s+", " ", title_anchor.get_text(" ", strip=True))
        href = title_anchor.get("href")
        if not title or not href:
            return None
        url = href if href.startswith("http") else urljoin(cls.base_url + "/", href)

        publisher_el = card.select_one("a.brand-title")
        publisher = re.sub(r"\s+", " ", publisher_el.get_text(" ", strip=True)) if publisher_el else ""

        price_el = card.select_one(".current-price .product-price") or card.select_one(
            "span.product-price"
        )
        price = parse_tr_price(price_el.get_text(" ", strip=True)) if price_el else None

        img = card.select_one("img")
        image = None
        if img is not None:
            image = img.get("data-src") or img.get("data-original") or img.get("src")

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

    def _parse_card(self, item: dict, query_core: str) -> tuple[SearchResult | None, str | None]:
        title = item["title"]
        if self._is_non_manga(title):
            logger.debug("kitapsepeti: skipping non-manga item: %r", title)
            return None, "non_manga_keyword"

        parsed = parse_volume_title(title)
        # An omnibus span ("Cilt 5 - 6") may be one 2-in-1 book: the importer
        # decides against the catalog, only real boxes are dropped here.
        if parsed.is_collection and parse_volume_range(title) is None:
            logger.debug("kitapsepeti: skipping collection: %r", title)
            return None, "collection"

        relevance = 1.0 if normalize_text(parsed.base_title) == query_core else 0.5

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
                relevance=relevance,
            ),
            None,
        )

    # -- detail-page enrichment (isbn / publisher / author / language / stock) -------
    def _enrich_with_details(self, results: list[SearchResult]) -> list[SearchResult]:
        limit = self.settings.max_detail_requests
        for index, result in enumerate(results[:limit]):
            try:
                results[index] = self._enrich_one(result)
            except ScraperError:
                logger.warning(
                    "kitapsepeti: detail enrichment blocked/failed for %s (keeping search data)",
                    result.product_url,
                )
            except Exception:
                logger.exception("kitapsepeti: unexpected enrichment error for %s", result.product_url)
        return results

    def _enrich_one(self, result: SearchResult) -> SearchResult:
        response = self.get(result.product_url)
        if response.status_code >= 400 or looks_like_blocked_page(
            response.status_code, response.text
        ):
            raise ScraperError(
                f"{self.store_id}: detail page HTTP {response.status_code} for {result.product_url}"
            )

        node = self.product_json_ld_node(self.extract_json_ld(response.text))
        if node is None:
            return result

        updates: dict = {}
        if node.get("isbn") and not result.isbn:
            isbn = normalize_isbn(node.get("isbn"))
            if isbn:
                updates["isbn"] = isbn
        publisher = node.get("publisher")
        if isinstance(publisher, dict) and publisher.get("name") and not result.publisher:
            updates["publisher"] = publisher.get("name")
        author = node.get("author")
        if isinstance(author, dict) and author.get("name") and not result.author:
            updates["author"] = author.get("name")
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
