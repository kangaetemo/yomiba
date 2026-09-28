"""Kitapsec scraper (live-verified against kitapsec.com, 2026-09-10).

Data source (public, no authentication):

``GET https://www.kitapsec.com/Arama/index.php?a=<query>&AnaKat=&arama=<page>-1-0a0-0-0-0-0-0``

The results grid is server-side rendered and every row carries schema.org
**microdata** (``itemtype="https://schema.org/Product"``) with:
  * ``meta[itemprop=name]``   -> title (includes the publisher suffix,
    e.g. "Berserk Cilt 1 Athica Yayınları")
  * ``meta[itemprop=sku]``    -> ISBN (canonical 13 digits)
  * ``meta[itemprop=url]``    -> product page URL
  * ``meta[itemprop=image]``  -> cover
  * ``div.offers`` -> ``meta[itemprop=price]`` ("196.00" TRY) and
    ``link[itemprop=availability]`` (InStock / OutOfStock)

Because the search page already provides ISBN and stock availability, no
detail-page enrichment is needed (cheapest possible integration).

The title embeds the publisher; per the "no guessing" rule the publisher is
NOT split out of the title — matching is ISBN-first (the sku is present for
catalog titles), which makes the embedded suffix harmless.

Pagination: the first segment of ``arama`` is the page number (1-based);
``-1-`` is the default sort. Pages stop at: empty page, no new items, or
the configured bounds.

robots.txt: ``User-Agent: * Allow: /`` — no restriction for regular clients.

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

logger = logging.getLogger("yomiba.scraper.kitapsec")

NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "figur", "asorti", "puzzle", "kupa", "tisort", "tshirt",
    "poster", "pelus", "kart oyun",
)

#: kitapsec embeds the publisher at the END of the product name, e.g.
#: "Berserk Cilt 1 Athica Yayınları". The suffix is structural (every Turkish
#: publisher name ends in "Yayın"/"Yayınları"), so it can be dropped for
#: series/volume parsing WITHOUT guessing which publisher it is — the
#: publisher field itself stays None (no invented mapping).
_PUBLISHER_SUFFIX_RE = re.compile(
    r"\s+\S+\s+[Yy\u0130][Aa][Yy][\u0131i][Nn](?:[Ll][Aa][Rr][\u0131i])?$"
)


class KitapsecScraper(BaseScraper):
    store_id = "kitapsec"
    store_name = "Kitapsec"
    base_url = "https://www.kitapsec.com"
    search_path = "/Arama/index.php"

    def search(self, query: str) -> list[SearchResult]:
        self.stats = {
            "pages_fetched": 0,
            "raw_products": 0,
            "duplicates_skipped": 0,
            "rejected": {},
            "accepted": 0,
            "stop_reason": None,
        }

        max_pages = max(1, self.settings.kitapsec_max_search_pages)
        max_results = max(1, self.settings.kitapsec_max_search_results)

        items: list[dict] = []
        seen_urls: set[str] = set()
        q = quote_plus(query)

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}{self.search_path}?a={q}&AnaKat=&arama={page}-1-0a0-0-0-0-0-0"
            response = self.get(url)
            if looks_like_blocked_page(response.status_code, response.text):
                raise ScraperError(
                    f"kitapsec: request blocked or robot-checked "
                    f"(HTTP {response.status_code}) for query {query!r}"
                )
            if response.status_code >= 400:
                if page == 1:
                    raise ScraperError(
                        f"kitapsec: HTTP {response.status_code} for search page 1 ({url})"
                    )
                logger.warning(
                    "kitapsec: search page %s failed (HTTP %s); keeping %s items",
                    page, response.status_code, len(items),
                )
                self.stats["stop_reason"] = "page_error"
                break
            self.stats["pages_fetched"] += 1

            soup = self.soup(response.text)
            rows = soup.select('div[itemtype="https://schema.org/Product"]')
            if not rows:
                self.stats["stop_reason"] = "empty_page"
                break

            new_on_page = 0
            for row in rows:
                self.stats["raw_products"] += 1
                item = self._row_to_item(row)
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

        query_core = normalize_text(parse_volume_title(query).base_title)
        results: list[SearchResult] = []
        for item in items:
            result, reason = self._parse_item(item, query_core)
            if reason is not None:
                self.stats["rejected"][reason] = self.stats["rejected"].get(reason, 0) + 1
                continue
            results.append(result)

        results = filter_manga_results(results, stats=self.stats)
        self.stats["accepted"] = len(results)
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results

    # -- microdata row parsing -------------------------------------------------------
    @staticmethod
    def _meta(node, prop: str) -> str | None:
        el = node.select_one(f'meta[itemprop="{prop}"]')
        if el is None:
            return None
        value = (el.get("content") or "").strip()
        return value or None

    def _row_to_item(self, row) -> dict | None:
        title = self._meta(row, "name")
        if not title:
            return None
        title = re.sub(r"\s+", " ", title)

        url = self._meta(row, "url")
        if not url:
            return None
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = urljoin(self.base_url + "/", url)

        sku = self._meta(row, "sku")
        image = self._meta(row, "image")
        if image and image.startswith("//"):
            image = "https:" + image

        offers = row.select_one('[itemtype="https://schema.org/Offer"]')
        price_raw = self._meta(offers, "price") if offers else None
        availability = None
        if offers is not None:
            avail_el = offers.select_one('link[itemprop="availability"]')
            if avail_el is not None:
                availability = avail_el.get("href") or None

        return {
            "title": title,
            "url": url,
            "isbn": normalize_isbn(sku) if sku else None,
            "image": image,
            "price": parse_tr_price(price_raw) if price_raw is not None else None,
            "availability": availability,
        }

    # -- filtering / result building ---------------------------------------------------
    @staticmethod
    def _is_non_manga(title: str) -> bool:
        normalized = normalize_text(title)
        return any(keyword in normalized for keyword in NON_MANGA_KEYWORDS)

    @staticmethod
    def _availability_flag(value: str | None) -> bool | None:
        if not value:
            return None
        if "OutOfStock" in value or "Discontinued" in value:
            return False
        if "InStock" in value or "LimitedAvailability" in value or "PreOrder" in value:
            return True
        return None

    @staticmethod
    def _strip_publisher_suffix(title: str) -> str:
        return _PUBLISHER_SUFFIX_RE.sub("", title)

    def _parse_item(self, item: dict, query_core: str) -> tuple[SearchResult | None, str | None]:
        title = item["title"]
        if self._is_non_manga(title):
            logger.debug("kitapsec: skipping non-manga item: %r", title)
            return None, "non_manga_keyword"

        # display title keeps the publisher suffix; only the PARSED
        # series/volume uses the cleaned title (ISBN stays the match key).
        parsed = parse_volume_title(self._strip_publisher_suffix(title))
        if parsed.is_collection:
            logger.debug("kitapsec: skipping collection: %r", title)
            return None, "collection"

        in_stock = self._availability_flag(item.get("availability"))
        relevance = 1.0 if normalize_text(parsed.base_title) == query_core else 0.5

        return (
            SearchResult(
                store_id=self.store_id,
                store_name=self.store_name,
                title=title,
                product_url=item["url"],
                series_title=parsed.base_title or None,
                volume_number=parsed.volume_number,
                # publisher is embedded in the title; not split (no guessing).
                publisher=None,
                isbn=item.get("isbn"),
                price=item.get("price"),
                currency="TRY",
                in_stock=True if in_stock is None else in_stock,
                image_url=item.get("image"),
                relevance=relevance,
            ),
            None,
        )
