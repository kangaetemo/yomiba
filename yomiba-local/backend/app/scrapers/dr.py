"""D&R scraper (dr.com.tr).

D&R sits behind aggressive bot protection (HTTP 403 / a maintenance page for
plain HTTP clients). This scraper is written against the store's documented
public structure and is verified with recorded fixtures:

1. Search page ``/arama?q=<query>`` -> a grid of product cards, each with a
   product anchor (title + href), a price and a cover image.
2. Detail page -> schema.org JSON-LD (``Book``/``Product``) with ``isbn,
   publisher, author, inLanguage, offers`` (the same standard markup BKM uses).

Because the live site is bot-walled, treat the search-page selectors as the
part most likely to need a touch-up if D&R changes its template; the
JSON-LD enrichment path is stable and store-independent. The scraper never
writes to the database.
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

logger = logging.getLogger("yomiba.scraper.dr")

NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "tisort", "tshirt", "kompresyon", "poster", "tablo", "kupa",
    "mousepad", "hoodie", "sweatshirt", "esofman", "sapka", "corap",
    "sticker", "dekal", "yastik", "battaniye", "oyuncak",
)

# Candidate anchors that wrap a product in the search grid.
_PRODUCT_ANCHOR_SELECTORS = (
    "a[href*='/kitap/']",
    "a[href*='/manga/']",
    "a.product-item a",
    "a[href*='p=']",
)
_PRICE_SELECTORS = (
    ".price",
    ".product-price",
    "[class*='price']",
    "span.price",
)


class DrScraper(BaseScraper):
    store_id = "dr"
    store_name = "D&R"
    base_url = "https://www.dr.com.tr"
    search_path = "/arama?q={query}"

    def search(self, query: str) -> list[SearchResult]:
        url = f"{self.base_url}{self.search_path.format(query=quote_plus(query))}"
        response = self.get(url)
        if looks_like_blocked_page(response.status_code, response.text):
            raise ScraperError(
                f"dr: request blocked or robot-checked "
                f"(HTTP {response.status_code}) for query {query!r}"
            )

        soup = self.soup(response.text)
        query_core = normalize_text(parse_volume_title(query).base_title)

        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        for anchor in self._product_anchors(soup):
            href = anchor.get("href")
            if not href:
                continue
            product_url = urljoin(self.base_url + "/", href) if href.startswith("/") else href
            if product_url in seen_urls:
                continue
            seen_urls.add(product_url)

            title = re.sub(r"\s+", " ", (anchor.get("title") or anchor.get_text(" ", strip=True)))
            if not title:
                continue
            if self._is_non_manga(title):
                logger.debug("dr: filtering non-manga title: %r", title)
                continue

            parsed = parse_volume_title(title)
            if parsed.is_collection:
                logger.debug("dr: filtering collection: %r", title)
                continue

            card = self._card_for(anchor)
            results.append(
                SearchResult(
                    store_id=self.store_id,
                    store_name=self.store_name,
                    title=title,
                    product_url=product_url,
                    series_title=parsed.base_title or None,
                    volume_number=parsed.volume_number,
                    price=self._extract_price(card),
                    currency="TRY",
                    in_stock=True,
                    image_url=self._extract_image(card),
                    relevance=1.0 if normalize_text(parsed.base_title) == query_core else 0.5,
                )
            )

        results = self._enrich_with_details(results)
        results = filter_manga_results(results, stats=self.stats)
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results

    # -- search grid ----------------------------------------------------------------
    def _product_anchors(self, soup):
        anchors = []
        for selector in _PRODUCT_ANCHOR_SELECTORS:
            anchors.extend(soup.select(selector))
        return anchors

    @staticmethod
    def _card_for(anchor):
        node = anchor
        for _ in range(6):
            parent = node.parent
            if parent is None:
                break
            if parent.name in ("li", "div") and parent.select(_PRICE_SELECTORS[0]):
                return parent
            node = parent
        return anchor.parent if anchor.parent else anchor

    def _extract_price(self, card):
        if card is None:
            return None
        for selector in _PRICE_SELECTORS:
            el = card.select_one(selector)
            if el:
                price = parse_tr_price(el.get_text(" ", strip=True))
                if price is not None:
                    return price
        return None

    def _extract_image(self, card):
        if card is None:
            return None
        img = card.select_one("img")
        if img is None:
            return None
        return img.get("src") or img.get("data-src")

    @staticmethod
    def _is_non_manga(title: str) -> bool:
        normalized = normalize_text(title)
        return any(keyword in normalized for keyword in NON_MANGA_KEYWORDS)

    # -- detail-page enrichment --------------------------------------------------------
    def _enrich_with_details(self, results: list[SearchResult]) -> list[SearchResult]:
        limit = self.settings.max_detail_requests
        for index, result in enumerate(results[:limit]):
            try:
                results[index] = self._enrich_one(result)
            except ScraperError:
                logger.warning(
                    "dr: detail enrichment blocked/failed for %s (keeping search data)",
                    result.product_url,
                )
            except Exception:
                logger.exception("dr: unexpected enrichment error for %s", result.product_url)
        return results

    def _enrich_one(self, result: SearchResult) -> SearchResult:
        response = self.get(result.product_url)
        if response.status_code >= 400 or looks_like_blocked_page(response.status_code, response.text):
            raise ScraperError(f"dr: detail page HTTP {response.status_code} for {result.product_url}")

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
        if not updates:
            return result
        return result.model_copy(update=updates)
