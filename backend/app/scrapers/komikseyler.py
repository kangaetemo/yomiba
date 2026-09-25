"""Komikşeyler scraper (live-verified against komikseyler.com.tr, 2026-09-10).

Data source (public, no authentication): the store runs WooCommerce and its
**Store API is public**:

    GET https://komikseyler.com.tr/wp-json/wc/store/v1/products
        ?search=<query>&per_page=100&page=<n>
    GET https://komikseyler.com.tr/wp-json/wc/store/v1/products/categories

Each product is clean JSON:
  * ``name``        -> title (HTML entities escaped, e.g. "&#8211;")
  * ``sku``         -> ISBN-13 for catalog books (validated with
                       ``normalize_isbn``; non-ISBN skus are dropped)
  * ``is_in_stock`` -> explicit stock flag
  * ``prices``      -> ``{"price": "17500", "currency_code": "TRY",
                       "currency_minor_unit": 2, ...}`` (integer CENTS)
  * ``permalink``   -> product page URL
  * ``images[0]``   -> cover

This is the only scraper that talks to a structured JSON API; no HTML
parsing is involved and no detail-page enrichment is needed (ISBN and stock
come straight from the search response).

Catalog note (verified 2026-09-10): Komikşeyler carries niche Turkish manga
(its own "Manga" / "Tezuka Manga" categories); big licensed titles
(Berserk, One Piece, ...) are NOT in this store's catalog — it complements
the other stores rather than duplicating them.

robots.txt allows /wp-json and product pages (only wp-admin and upload
logs are disallowed).

The scraper never writes to the database.
"""

from __future__ import annotations

import html as html_module
import logging
from urllib.parse import quote_plus

from ..normalization import normalize_isbn, parse_volume_title
from .base import BaseScraper, ScraperError
from .search_result import SearchResult
from .relevance import filter_manga_results

logger = logging.getLogger("yomiba.scraper.komikseyler")

STORE_API = "/wp-json/wc/store/v1/products"


class KomikseylerScraper(BaseScraper):
    store_id = "komikseyler"
    store_name = "Komikşeyler"
    base_url = "https://komikseyler.com.tr"

    def search(self, query: str) -> list[SearchResult]:
        self.stats = {
            "pages_fetched": 0,
            "raw_products": 0,
            "duplicates_skipped": 0,
            "rejected": {},
            "accepted": 0,
            "stop_reason": None,
        }

        max_pages = max(1, self.settings.komikseyler_max_search_pages)
        max_results = max(1, self.settings.komikseyler_max_search_results)

        items: list[dict] = []
        seen_ids: set[str] = set()

        for page in range(1, max_pages + 1):
            url = (
                f"{self.base_url}{STORE_API}"
                f"?search={quote_plus(query)}&per_page=100&page={page}"
            )
            try:
                data = self.get_json(url)
            except ScraperError as exc:
                if page == 1:
                    raise
                logger.warning(
                    "komikseyler: search page %s failed (%s); keeping %s items",
                    page, exc, len(items),
                )
                self.stats["stop_reason"] = "page_error"
                break
            self.stats["pages_fetched"] += 1

            if not isinstance(data, list):
                raise ScraperError(
                    f"komikseyler: unexpected search payload (not a list) for {query!r}"
                )
            if not data:
                self.stats["stop_reason"] = "empty_page"
                break

            new_on_page = 0
            for product in data:
                if not isinstance(product, dict):
                    continue
                self.stats["raw_products"] += 1
                pid = str(product.get("id") or product.get("permalink") or "")
                if pid and pid in seen_ids:
                    self.stats["duplicates_skipped"] += 1
                    continue
                if pid:
                    seen_ids.add(pid)
                items.append(product)
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

        results: list[SearchResult] = []
        for product in items:
            result, reason = self._parse_product(product)
            if reason is not None:
                self.stats["rejected"][reason] = self.stats["rejected"].get(reason, 0) + 1
                continue
            results.append(result)

        results = filter_manga_results(results, stats=self.stats)
        self.stats["accepted"] = len(results)
        return results

    # -- parsing ---------------------------------------------------------------------
    @staticmethod
    def _price_cents_to_decimal(prices: dict) -> "object | None":
        from decimal import Decimal, InvalidOperation

        raw = (prices or {}).get("price")
        if raw is None:
            return None
        try:
            cents = int(str(raw).strip())
        except ValueError:
            return None
        if cents < 0:
            return None
        return Decimal(cents) / Decimal(100)

    def _parse_product(self, product: dict) -> tuple[SearchResult | None, str | None]:
        raw_name = product.get("name")
        title = html_module.unescape(str(raw_name)).strip() if raw_name else ""
        title = " ".join(title.split())
        if not title:
            return None, "no_title"

        permalink = str(product.get("permalink") or "").strip()
        if not permalink:
            return None, "no_url"

        parsed = parse_volume_title(title)
        if parsed.is_collection:
            logger.debug("komikseyler: skipping collection: %r", title)
            return None, "collection"

        sku = product.get("sku")
        isbn = normalize_isbn(sku) if sku else None

        prices = product.get("prices") or {}
        currency = str(prices.get("currency_code") or "TRY")
        price = self._price_cents_to_decimal(prices)

        images = product.get("images") or []
        image = images[0].get("src") if images and isinstance(images[0], dict) else None

        in_stock = bool(product.get("is_in_stock", True))

        return (
            SearchResult(
                store_id=self.store_id,
                store_name=self.store_name,
                title=title,
                product_url=permalink,
                series_title=parsed.base_title or None,
                volume_number=parsed.volume_number,
                isbn=isbn,
                price=price,
                currency=currency,
                in_stock=in_stock,
                image_url=image,
                relevance=1.0,
            ),
            None,
        )
