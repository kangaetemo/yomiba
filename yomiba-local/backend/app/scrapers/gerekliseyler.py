"""Gerekli Şeyler scraper (live-verified against gerekliseyler.com.tr,
2026-09-10).

Data sources (all public, no authentication):

1. Search (paginated): ``GET https://www.gerekliseyler.com.tr/arama/<query>?tp=<n>``
   Server-side rendered ``div.showcase`` cards (IdeaSoft/WAW platform, same
   family as BKM):
     * ``a[href]`` inside ``div.showcase-image`` -> product URL + cover
       (``img[data-src]``)
     * ``div.showcase-brand``   -> publisher
     * ``div.showcase-title a[title]`` -> title
     * ``div.showcase-price-new`` -> current price ("238,00 TL");
       ``div.showcase-price-old`` is the list price (ignored)
     * ``div.sold-out-label`` ("Tükendi") -> out of stock; cards without it
       show an "Sepete Ekle" button (in stock)
   The pagination parameter is ``tp`` (verified: ?tp=2 returns new items).

2. Detail page (enrichment, best effort): no JSON-LD; the ISBN is rendered
   in the "Stok Kodu" info row (``div.product-list-content`` next to the
   "Stok Kodu" title) and is usually a plain 13-digit barcode.

Behaviour mirrors the other store scrapers: bounded pagination, URL
deduplication, non-manga / collection filtering, bot-wall fail-fast
(``looks_like_blocked_page`` -> ``ScraperError``, never retried), and
best-effort detail enrichment limited by ``settings.max_detail_requests``.
Stock comes from the search card itself (sold-out label), so a failed
detail request never loses stock information.

robots.txt: ``User-agent: * Allow: /`` — no restriction for regular clients.

The scraper never writes to the database.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus, urljoin

from ..normalization import normalize_isbn, normalize_text, parse_volume_title
from .base import BaseScraper, ScraperError
from .common import looks_like_blocked_page, parse_tr_price
from .search_result import SearchResult
from .relevance import filter_manga_results

logger = logging.getLogger("yomiba.scraper.gerekliseyler")

NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "figur", "asorti", "oyuncak", "puzzle", "kupa", "tisort", "tshirt",
    "poster", "defter", "pelus", "heykel", "bust", "action", "kart oyun",
    "model kit", "blind bag",
)


class GerekliseylerScraper(BaseScraper):
    store_id = "gerekliseyler"
    store_name = "Gerekli Şeyler"
    base_url = "https://www.gerekliseyler.com.tr"

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
        max_pages = max(1, self.settings.gerekliseyler_max_search_pages)
        max_results = max(1, self.settings.gerekliseyler_max_search_results)

        items: list[dict] = []
        seen_urls: set[str] = set()
        q = quote_plus(query)

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/arama/{q}" + (f"?tp={page}" if page > 1 else "")
            response = self.get(url)
            if looks_like_blocked_page(response.status_code, response.text):
                raise ScraperError(
                    f"gerekliseyler: request blocked or robot-checked "
                    f"(HTTP {response.status_code}) for query {query!r}"
                )
            if response.status_code >= 400:
                if page == 1:
                    raise ScraperError(
                        f"gerekliseyler: HTTP {response.status_code} for search page 1 ({url})"
                    )
                logger.warning(
                    "gerekliseyler: search page %s failed (HTTP %s); keeping %s items",
                    page, response.status_code, len(items),
                )
                self.stats["stop_reason"] = "page_error"
                break
            self.stats["pages_fetched"] += 1

            soup = self.soup(response.text)
            cards = soup.select("div.showcase")
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
        title_anchor = card.select_one("div.showcase-title a")
        if title_anchor is None:
            return None
        title = re.sub(r"\s+", " ", title_anchor.get("title") or title_anchor.get_text(" ", strip=True))
        href = title_anchor.get("href")
        if not title or not href:
            return None
        url = href if href.startswith("http") else urljoin(GerekliseylerScraper.base_url + "/", href)

        brand_el = card.select_one("div.showcase-brand")
        publisher = re.sub(r"\s+", " ", brand_el.get_text(" ", strip=True)) if brand_el else ""

        price_el = card.select_one("div.showcase-price-new")
        price = parse_tr_price(price_el.get_text(" ", strip=True)) if price_el else None

        img = card.select_one("img")
        image = None
        if img is not None:
            image = img.get("data-src") or img.get("src")
            if image and image.startswith("//"):
                image = "https:" + image

        sold_out = card.select_one("div.sold-out-label") is not None

        return {
            "title": title,
            "url": url,
            "publisher": publisher or None,
            "price": price,
            "image": image,
            "in_stock": not sold_out,
        }

    # -- parsing ---------------------------------------------------------------------
    @staticmethod
    def _is_non_manga(title: str) -> bool:
        normalized = normalize_text(title)
        return any(keyword in normalized for keyword in NON_MANGA_KEYWORDS)

    def _parse_card(self, item: dict, query_core: str) -> tuple[SearchResult | None, str | None]:
        title = item["title"]
        if self._is_non_manga(title):
            logger.debug("gerekliseyler: skipping non-manga item: %r", title)
            return None, "non_manga_keyword"

        parsed = parse_volume_title(title)
        if parsed.is_collection:
            logger.debug("gerekliseyler: skipping collection: %r", title)
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
                in_stock=item.get("in_stock", True),
                image_url=item.get("image"),
                relevance=relevance,
            ),
            None,
        )

    # -- detail-page enrichment (isbn from the "Stok Kodu" row) ----------------------
    _STOK_KODU_ROW_RE = re.compile(
        r"Stok\s*Kodu</div>\s*<div[^>]*product-list-content[^>]*>\s*([^<]+?)\s*</div>",
        re.I,
    )

    def _enrich_with_details(self, results: list[SearchResult]) -> list[SearchResult]:
        limit = self.settings.max_detail_requests
        for index, result in enumerate(results[:limit]):
            try:
                results[index] = self._enrich_one(result)
            except ScraperError:
                logger.warning(
                    "gerekliseyler: detail enrichment blocked/failed for %s (keeping search data)",
                    result.product_url,
                )
            except Exception:
                logger.exception(
                    "gerekliseyler: unexpected enrichment error for %s", result.product_url
                )
        return results

    def _enrich_one(self, result: SearchResult) -> SearchResult:
        if result.isbn:
            return result
        response = self.get(result.product_url)
        if response.status_code >= 400 or looks_like_blocked_page(
            response.status_code, response.text
        ):
            raise ScraperError(
                f"gerekliseyler: detail page HTTP {response.status_code} for {result.product_url}"
            )

        match = self._STOK_KODU_ROW_RE.search(response.text)
        if not match:
            return result
        isbn = normalize_isbn(match.group(1))
        if not isbn:
            return result
        return result.model_copy(update={"isbn": isbn})
