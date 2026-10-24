"""Kitapbulan scraper (live-verified against kitapbulan.com, 2026-10-24).

The store moved from T-Soft (``www.kitapbulan.com/arama?q=``, ``/<slug>``
product pages) to Shopify on 2026-10-23/24. Every old URL answers 404.

Data sources (all public, no authentication):

1. Search (paginated): ``GET https://kitapbulan.com/search?q=<query>&type=product&page=<n>``
   Shopify search page, 24 products per page. Only the product links are
   read (``a[href*="/products/<handle>"]``, link text / image alt as the
   title): the theme's card markup is not part of the contract. The handle
   ends with the product's ISBN-13 ("berserk-8-9786256187986").

2. Product JSON (one per relevant result): ``GET /products/<handle>.js``,
   Shopify's public storefront product JSON: ``title``, ``vendor``
   (publisher), ``price`` (kuruş), ``available`` (stock), ``tags``
   ("Türkçe"), ``variants[0].barcode`` (ISBN) and ``featured_image``.

RELEVANCE GUARD (specific to this store): the search is fuzzy and pads the
results with unrelated products (verified live: "berserk" lists Chainsaw Man
and İblis Keser after the 17 Berserk volumes, "1000 sonuç"). Every query
token of length >= 3 must appear in the title or the product is dropped,
and paging stops after two pages without a relevant product.

Foreign editions (VIZ, Yen Press ...) are recognised by the ISBN in the
handle and dropped before their product JSON is fetched: the catalog lists
Turkish editions only, and a long series lists dozens of English volumes.

The scraper never writes to the database.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from urllib.parse import quote_plus, urljoin, urlsplit

from bs4 import BeautifulSoup, SoupStrainer

from ..normalization import normalize_isbn, normalize_text, parse_volume_range, parse_volume_title
from ..normalization.isbn import is_foreign_isbn
from .base import BaseScraper, ListingCheck, ScraperError
from .common import looks_like_blocked_page
from .search_result import SearchResult
from .relevance import filter_manga_results

logger = logging.getLogger("yomiba.scraper.kitapbulan")

NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "figur", "asorti", "puzzle", "kupa", "tisort", "tshirt",
    "poster", "pelus", "mousepad", "kutulu fig",
)

#: Only the product links are built into a tree (a search page is a full
#: storefront page; parsing whole pages kept the VDS backend near one core,
#: py-spy 2026-10-21).
_PRODUCT_LINKS = SoupStrainer("a", href=re.compile(r"/products/"))
_HANDLE_RE = re.compile(r"/products/([^/?#]+)")
_HANDLE_ISBN_RE = re.compile(r"-(97[89]\d{10})$")
#: Stop paging after this many pages in a row without a product that passes
#: the relevance guard: past the series the store only lists unrelated ones.
_IRRELEVANT_PAGE_LIMIT = 2


def product_handle(url: str) -> str | None:
    """Shopify handle of a kitapbulan product URL (None for any other URL,
    e.g. an old T-Soft ``www.kitapbulan.com/<slug>`` page)."""
    match = _HANDLE_RE.search(urlsplit(url).path)
    return match.group(1) if match else None


class KitapbulanScraper(BaseScraper):
    store_id = "kitapbulan"
    store_name = "Kitapbulan"
    base_url = "https://kitapbulan.com"
    #: The product JSON carries stock and price: listings the search misses
    #: are re-checked there (BaseScraper.check_listing).
    verifies_unseen_listings = True
    search_path = "/search?q={query}&type=product"
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

        items = self._search_pages(query, query_tokens)
        results: list[SearchResult] = []
        for item in items:
            result, reason = self._item_to_result(item, query_tokens)
            if reason is not None:
                self._reject(reason)
                continue
            results.append(result)

        self.stats["accepted"] = len(results)
        results = filter_manga_results(results, stats=self.stats)
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results

    def _reject(self, reason: str) -> None:
        self.stats["rejected"][reason] = self.stats["rejected"].get(reason, 0) + 1

    # -- paginated search ----------------------------------------------------------
    def _search_pages(self, query: str, query_tokens: list[str] | None = None) -> list[dict]:
        max_pages = max(1, self.settings.kitapbulan_max_search_pages)
        max_results = max(1, self.settings.kitapbulan_max_search_results)

        items: list[dict] = []
        seen_handles: set[str] = set()
        irrelevant_pages = 0

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}{self.search_path.format(query=quote_plus(query))}&page={page}"
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

            cards = self._page_items(response.text)
            if not cards:
                self.stats["stop_reason"] = "empty_page"
                break

            new_on_page = 0
            relevant_on_page = 0
            for item in cards:
                self.stats["raw_products"] += 1
                if item["handle"] in seen_handles:
                    self.stats["duplicates_skipped"] += 1
                    continue
                seen_handles.add(item["handle"])
                items.append(item)
                new_on_page += 1
                if self._is_relevant(item["title"], query_tokens):
                    relevant_on_page += 1
                if len(items) >= max_results:
                    self.stats["stop_reason"] = "max_results"
                    break

            if self.stats["stop_reason"] == "max_results":
                break
            if new_on_page == 0:
                self.stats["stop_reason"] = "no_new_items"
                break
            irrelevant_pages = 0 if relevant_on_page else irrelevant_pages + 1
            if irrelevant_pages >= _IRRELEVANT_PAGE_LIMIT:
                self.stats["stop_reason"] = "no_relevant_items"
                break
        else:
            self.stats["stop_reason"] = "max_pages"

        return items

    @staticmethod
    def _page_items(html: str) -> list[dict]:
        """Products of one search page, in page order: one item per handle
        (a card links the cover and the title to the same product). The
        title is the longest link text / image alt; without one, the handle
        words stand in (the product JSON has the real title)."""
        soup = BeautifulSoup(html, "lxml", parse_only=_PRODUCT_LINKS)
        by_handle: dict[str, dict] = {}
        for anchor in soup.find_all("a"):
            handle = product_handle(anchor.get("href") or "")
            if not handle:
                continue
            text = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))
            if not text:
                img = anchor.find("img")
                text = re.sub(r"\s+", " ", (img.get("alt") or "") if img else "").strip()
            item = by_handle.setdefault(handle, {"handle": handle, "title": ""})
            if len(text) > len(item["title"]):
                item["title"] = text
        for item in by_handle.values():
            if not item["title"]:
                item["title"] = _HANDLE_ISBN_RE.sub("", item["handle"]).replace("-", " ")
        return list(by_handle.values())

    @staticmethod
    def _is_relevant(title: str, query_tokens: list[str] | None) -> bool:
        """The relevance guard: every significant query token in the title."""
        if not query_tokens:
            return True
        normalized_title = normalize_text(title)
        return all(token in normalized_title for token in query_tokens)

    # -- parsing ---------------------------------------------------------------------
    @staticmethod
    def _is_non_manga(title: str) -> bool:
        normalized = normalize_text(title)
        return any(keyword in normalized for keyword in NON_MANGA_KEYWORDS)

    def _title_reason(self, title: str, query_tokens: list[str]) -> str | None:
        if self._is_non_manga(title):
            return "non_manga_keyword"
        # An omnibus span ("Cilt 5 - 6") may be one 2-in-1 book: the importer
        # decides against the catalog, only real boxes are dropped here.
        if parse_volume_title(title).is_collection and parse_volume_range(title) is None:
            return "collection"
        if not self._is_relevant(title, query_tokens):
            return "irrelevant"
        return None

    def _item_to_result(
        self, item: dict, query_tokens: list[str]
    ) -> tuple[SearchResult | None, str | None]:
        # Cheap checks on the search page first: every product JSON is one
        # request, and the fuzzy search lists many unrelated products.
        handle_isbn = _HANDLE_ISBN_RE.search(item["handle"])
        if handle_isbn and is_foreign_isbn(handle_isbn.group(1)):
            return None, "foreign_edition"
        reason = self._title_reason(item["title"], query_tokens)
        if reason is not None:
            logger.debug("kitapbulan: skipping %s card: %r", reason, item["title"])
            return None, reason

        try:
            product = self._product_json(item["handle"])
        except ScraperError:
            logger.warning("kitapbulan: product JSON blocked/failed for %s", item["handle"])
            return None, "detail_failed"
        if product is None:
            return None, "detail_failed"

        title = re.sub(r"\s+", " ", str(product.get("title") or "")).strip() or item["title"]
        reason = self._title_reason(title, query_tokens)
        if reason is not None:
            return None, reason
        return self._product_to_result(product, title, item["handle"]), None

    def _product_to_result(self, product: dict, title: str, handle: str) -> SearchResult:
        variants = product.get("variants") or [{}]
        variant = variants[0] if isinstance(variants[0], dict) else {}
        isbn = normalize_isbn(variant.get("barcode") or variant.get("sku"))
        if isbn is None:
            match = _HANDLE_ISBN_RE.search(handle)
            isbn = match.group(1) if match else None
        image = product.get("featured_image")
        if isinstance(image, str) and image.startswith("//"):
            image = "https:" + image
        parsed = parse_volume_title(title)
        return SearchResult(
            store_id=self.store_id,
            store_name=self.store_name,
            title=title,
            product_url=f"{self.base_url}/products/{handle}",
            series_title=parsed.base_title or None,
            volume_number=parsed.volume_number,
            isbn=isbn,
            publisher=(product.get("vendor") or None),
            language=self._language(product.get("tags")),
            price=self._price(variant.get("price", product.get("price"))),
            currency="TRY",
            in_stock=bool(product.get("available")),
            image_url=image or None,
            relevance=1.0,
        )

    # -- product JSON ----------------------------------------------------------------
    def _product_json(self, handle: str) -> dict | None:
        """``/products/<handle>.js``; None when the product is gone (4xx).
        Raises ScraperError on a bot wall."""
        response = self.get(urljoin(self.base_url + "/", f"products/{handle}.js"))
        if looks_like_blocked_page(response.status_code, response.text):
            raise ScraperError(f"kitapbulan: product JSON blocked (HTTP {response.status_code}) for {handle}")
        if response.status_code >= 400:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def check_listing(self, url: str) -> ListingCheck | None:
        """Stock and price of one listing from its product JSON. None when
        unknown (an old pre-Shopify URL, HTTP error, bot wall)."""
        handle = product_handle(url)
        if handle is None:
            return None
        try:
            product = self._product_json(handle)
        except ScraperError:
            return None
        if product is None or "available" not in product:
            return None
        variants = product.get("variants") or [{}]
        variant = variants[0] if isinstance(variants[0], dict) else {}
        return ListingCheck(
            in_stock=bool(product.get("available")),
            price=self._price(variant.get("price", product.get("price"))),
        )

    @staticmethod
    def _price(kurus) -> Decimal | None:
        """Shopify prices are integers in kuruş (22120 -> 221.20)."""
        if isinstance(kurus, bool) or not isinstance(kurus, (int, str)):
            return None
        try:
            value = int(kurus)
        except ValueError:
            return None
        return (Decimal(value) / 100).quantize(Decimal("0.01")) if value >= 0 else None

    @staticmethod
    def _language(tags) -> str | None:
        """The store tags each book with its language ("Türkçe", "İngilizce")."""
        if not isinstance(tags, list):
            return None
        for tag in tags:
            key = normalize_text(str(tag))
            if key == "turkce":
                return "tr"
            if key in ("ingilizce", "english"):
                return "en"
        return None
