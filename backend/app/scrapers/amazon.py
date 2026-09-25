"""Amazon Turkey scraper (amazon.com.tr).

Strategy
--------
1. Request the public search page ``/s?k=<query>`` with a realistic browser
   User-Agent and a Turkish Accept-Language header.
2. Parse each ``data-asin`` result block: title, link, image, price, stock.
3. Resolve sponsored / redirect URLs (``/gp/aw/crRedir/...``) to the actual
   ``/dp/<ASIN>`` product page.
4. Filter obvious non-manga products (T-shirts, posters, mugs, ...) and
   collections / deluxe boxes, using deterministic rules (no store-specific
   hardcoding of publishers or titles).
5. When the search page does not carry the metadata we need (it usually does
   not carry ISBN / publisher), issue a bounded number of product detail
   requests (``/dp/<ASIN>``) and read the detail bullets (ISBN-10/13,
   Yayıncı, Başlatıcı, Dil). Detail failures degrade gracefully: the result
   is kept with the metadata we already have.

The scraper never writes to the database.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

from ..normalization import normalize_text, parse_volume_title
from .base import BaseScraper, ScraperError
from .common import looks_like_blocked_page, parse_tr_price
from .search_result import SearchResult
from .relevance import filter_manga_results

logger = logging.getLogger("yomiba.scraper.amazon")

#: Product types that are obviously not a manga volume. Compared against the
#: *normalized* title, so Turkish characters and casing do not matter.
NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "tisort",  # tişört
    "tshirt",
    "kompresyon",
    "poster",
    "tablo",
    "tabela",
    "kupa",
    "mousepad",
    "hoodie",
    "sweatshirt",
    "esofman",
    "sapka",
    "corap",
    "canta",
    "kilif",
    "sticker",
    "dekal",
    "yastik",
    "battaniye",
    "kumas",
    "kanvas",
    "oyuncak",
)

_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})")
_OUT_OF_STOCK_RE = re.compile(
    r"stokta yok|stokta kalmad|stokta bulunam|out of stock|temporarily out", re.I
)


class AmazonScraper(BaseScraper):
    store_id = "amazon"
    store_name = "Amazon"
    base_url = "https://www.amazon.com.tr"

    def search(self, query: str) -> list[SearchResult]:
        url = f"{self.base_url}/s?k={quote_plus(query)}"
        response = self.get(url)
        if looks_like_blocked_page(response.status_code, response.text):
            raise ScraperError(
                f"amazon: request blocked or robot-checked "
                f"(HTTP {response.status_code}) for query {query!r}"
            )

        soup = self.soup(response.text)
        query_parsed = parse_volume_title(query)
        query_core = normalize_text(query_parsed.base_title)

        results: list[SearchResult] = []
        seen_asins: set[str] = set()
        for item in soup.select('div.s-result-item[data-asin], div[data-component-type="s-search-result"]'):
            asin = (item.get("data-asin") or "").strip()
            if not asin or asin in seen_asins:
                continue
            seen_asins.add(asin)

            title, link = self._extract_title_and_link(item)
            if not title:
                continue
            if self._is_non_manga(title):
                logger.debug("amazon: filtering non-manga title: %r", title)
                continue

            parsed = parse_volume_title(title)
            if parsed.is_collection:
                logger.debug("amazon: filtering collection: %r", title)
                continue

            # Unrelated series that merely contain the query word (e.g.
            # "Berserk of Gluttony" for the query "Berserk") are filtered:
            # only the queried series is imported from this store.
            if query_core and normalize_text(parsed.base_title) != query_core:
                logger.debug("amazon: filtering unrelated series: %r", title)
                continue

            product_url = self._resolve_product_url(link, asin)
            if not product_url:
                continue

            results.append(
                SearchResult(
                    store_id=self.store_id,
                    store_name=self.store_name,
                    title=title,
                    product_url=product_url,
                    series_title=parsed.base_title or None,
                    volume_number=parsed.volume_number,
                    price=self._extract_price(item),
                    currency="TRY",
                    in_stock=not _OUT_OF_STOCK_RE.search(item.get_text(" ", strip=True)),
                    image_url=self._extract_image(item),
                    relevance=self._relevance(
                        parsed.base_title, parsed.volume_number, query_core, query_parsed.volume_number
                    ),
                )
            )

        # Enrich the most relevant results with detail-page metadata. The
        # search page rarely contains ISBN/publisher, so detail requests are
        # the normal path; they are capped to stay well-behaved.
        limit = self.settings.max_detail_requests
        for index, result in enumerate(results[:limit]):
            if result.isbn:
                continue  # nothing to gain
            try:
                results[index] = self._enrich_one(result)
            except ScraperError:
                logger.warning(
                    "amazon: detail enrichment blocked/failed for %s (keeping search data)",
                    result.product_url,
                )
            except Exception:
                logger.exception(
                    "amazon: unexpected enrichment error for %s", result.product_url
                )

        results = filter_manga_results(results, stats=self.stats)
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results

    # -- search-page extraction ----------------------------------------------------
    @staticmethod
    def _extract_title_and_link(item) -> tuple[str, str | None]:
        anchor = item.select_one("h2 a") or item.select_one("a.a-link-normal")
        if anchor is None:
            return "", None
        title_el = anchor.select_one("span") or anchor
        title = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True))
        return title, anchor.get("href")

    @staticmethod
    def _extract_price(item) -> object:
        price_el = item.select_one(
            "span.a-price:not(.a-price-augmented) .a-offscreen, span.a-price .a-offscreen"
        )
        if price_el is None:
            return None
        return parse_tr_price(price_el.get_text(strip=True))

    @staticmethod
    def _extract_image(item) -> str | None:
        img = item.select_one("img.s-image")
        if img is None:
            return None
        return img.get("data-old-hires") or img.get("src")

    @staticmethod
    def _is_non_manga(title: str) -> bool:
        normalized = normalize_text(title)
        return any(keyword in normalized for keyword in NON_MANGA_KEYWORDS)

    @staticmethod
    def _relevance(
        base_title: str,
        volume: int | None,
        query_core: str,
        query_volume: int | None,
    ) -> float:
        """Deterministic relevance scoring for a parsed result.

        * Same series as the query AND (no specific volume asked OR the exact
          volume) -> 1.0
        * Same series, a different volume -> 0.8
        * No query series to compare against -> 0.5
        """
        if not query_core:
            return 0.5
        title_core = normalize_text(base_title)
        if title_core == query_core:
            if query_volume is None or volume == query_volume:
                return 1.0
            return 0.8
        return 0.3

    def _resolve_product_url(self, href: str | None, asin: str) -> str | None:
        """Return the canonical ``/dp/<ASIN>`` product URL.

        Sponsored results link through ``/gp/aw/crRedir/...`` (or similar
        tracking URLs) with the ASIN hidden in the query string; we resolve
        them so the stored product URL always points at the real product page.
        """
        if href and href.startswith("/"):
            href = urljoin(self.base_url + "/", href)
        if href:
            match = _ASIN_RE.search(href)
            if match:
                return f"{self.base_url}/dp/{match.group(1)}"
            asin_param = (parse_qs(urlparse(href).query).get("asin") or [None])[0]
            if asin_param:
                return f"{self.base_url}/dp/{asin_param}"
        if asin:
            return f"{self.base_url}/dp/{asin}"
        return None

    # -- detail-page enrichment ------------------------------------------------------
    def _enrich_one(self, result: SearchResult) -> SearchResult:
        match = _ASIN_RE.search(result.product_url)
        if not match:
            raise ScraperError(f"amazon: no ASIN in product URL {result.product_url}")
        asin = match.group(1)
        response = self.get(f"{self.base_url}/dp/{asin}")
        if looks_like_blocked_page(response.status_code, response.text):
            raise ScraperError(
                f"amazon: detail page blocked (HTTP {response.status_code}) for ASIN {asin}"
            )

        details = self._extract_detail_bullets(self.soup(response.text))
        updates: dict = {}
        if details.get("isbn"):
            from ..normalization import normalize_isbn

            isbn = normalize_isbn(details["isbn"])
            if isbn:
                updates["isbn"] = isbn
        for field in ("publisher", "author", "language"):
            if details.get(field) and not getattr(result, field):
                updates[field] = details[field]
        if not updates:
            return result
        return result.model_copy(update=updates)

    @staticmethod
    def _extract_detail_bullets(soup) -> dict:
        """Read label/value pairs from the product detail section.

        Amazon renders these either as a ``<table>`` (rows of th/td) or as a
        list of ``.a-list-item`` spans. Labels are matched in normalized form
        (Turkish + English), so nothing is hardcoded to one language.
        """
        found: dict = {}

        def store(label: str, value: str) -> None:
            key = normalize_text(label)
            value = re.sub(r"\s+", " ", value).strip()
            if not value:
                return
            if key.startswith("isbn 13") and not found.get("isbn"):
                found["isbn"] = value
            elif key.startswith("isbn 10") and not found.get("isbn"):
                found["isbn"] = value
            elif (key.startswith("yayinci") or key.startswith("publisher")) and not found.get("publisher"):
                found["publisher"] = value
            elif (
                key.startswith("baslat")  # başlatan / başlatıcı
                or key.startswith("yazar")
                or key.startswith("author")
            ) and not found.get("author"):
                found["author"] = value
            elif (key.startswith("dil") or key.startswith("language")) and not found.get("language"):
                found["language"] = value

        for row in soup.select("table tr"):
            header = row.select_one("th")
            cell = row.select_one("td")
            if header and cell:
                store(header.get_text(" ", strip=True), cell.get_text(" ", strip=True))

        selectors = (
            "#detailBulletsWrapper_feature_div li",
            "#detailBullets_feature_div li",
            ".detail-bullet-list li",
        )
        for selector in selectors:
            for li in soup.select(selector):
                items = [s.get_text(" ", strip=True) for s in li.select(".a-list-item")]
                items = [i for i in items if i and i != ":"]
                if len(items) >= 2:
                    store(items[0], " ".join(items[1:]))

        return found
