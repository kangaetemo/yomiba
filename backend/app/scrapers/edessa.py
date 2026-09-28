"""Edessa Kitabevi scraper (live-verified against edessakitabevi.com, 2026-09-28).

The store runs on ikas (Next.js). Its search is client-side only, so this
scraper never calls a search endpoint. Instead it uses what the server
renders, all allowed by robots.txt (only /admin, /cart, /checkout,
/account and /_next/data are disallowed):

1. **Sitemaps** (cached per process for ``edessa_index_ttl_minutes``):
   ``/products.xml`` lists every product URL (~4000; the slug is the
   transliterated title, e.g. ``/frieren-cilt-6``, plus a cover image) and
   ``/collections.xml`` lists the category / series pages (``/frieren``,
   ``/one-piece``).
2. **Series collection page** (``/<collection-slug>``): its ``__NEXT_DATA__``
   embeds the first 20 products of the collection with name, slug, ISBN
   (``sku``/``barcodeList``), sell and discount price, stock count and
   brand (publisher). One request covers a whole short series, stock
   included. Only the first page is server-rendered (``?page=2`` is
   ignored), so longer series continue with step 3.
3. **Product pages** for matching product slugs not covered by step 2: the
   schema.org ``Product`` JSON-LD carries name, ``sku`` (ISBN), brand,
   ``offers.price`` and ``offers.availability``. Pages are large (~0.8 MB),
   so at most ``edessa_max_detail_requests`` are fetched per search; the
   window rotates hourly so every volume of a long series is refreshed
   over successive cycles.

A query matches a collection whose slug equals the query slug (optionally
with a ``-<n>`` duplicate suffix) and products whose slug equals it or
starts with ``<query-slug>-``. The scraper never writes to the database.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from ..normalization import normalize_isbn, normalize_text, parse_volume_title
from .base import BaseScraper, ScraperError
from .common import looks_like_blocked_page
from .relevance import filter_manga_results
from .search_result import SearchResult

logger = logging.getLogger("yomiba.scraper.edessa")

_SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)
#: Collections that are store-wide shelves, never a single series.
_GENERIC_COLLECTIONS = frozenset({"manga", "manga-ve-manhwa", "kitap", "cizgi-roman"})

# Process-wide sitemap index shared by every EdessaScraper instance (a new
# instance is created per import job). {name: (fetched_at, data)}
_INDEX_CACHE: dict[str, tuple[float, object]] = {}
_INDEX_LOCK = threading.Lock()


def slugify(text: str) -> str:
    """ikas-style slug: transliterated, lowercase, hyphen-separated."""
    return "-".join(normalize_text(text).split())


def _slug_of(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]


def _to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return price if price > 0 else None


def _find_products_lists(node) -> list[list]:
    """Every ``productsList.data`` array inside a ``__NEXT_DATA__`` tree."""
    found: list[list] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            products = current.get("productsList")
            if isinstance(products, dict) and isinstance(products.get("data"), list):
                found.append(products["data"])
            stack.extend(v for v in current.values() if isinstance(v, (dict, list)))
        elif isinstance(current, list):
            stack.extend(v for v in current if isinstance(v, (dict, list)))
    return found


class EdessaScraper(BaseScraper):
    store_id = "edessa"
    store_name = "Edessa Kitabevi"
    base_url = "https://edessakitabevi.com"

    def search(self, query: str) -> list[SearchResult]:
        self.stats = {
            "collections_fetched": 0,
            "details_fetched": 0,
            "matched_products": 0,
            "detail_capped": 0,
            "rejected": {},
            "accepted": 0,
        }
        query_slug = slugify(query)
        if len(query_slug) < 3:
            return []

        products = self._product_index()
        collections = self._collection_index()
        slug_re = re.compile(re.escape(query_slug) + r"(?:-\d+)?")
        matched_collections = sorted(
            c for c in collections
            if c not in _GENERIC_COLLECTIONS and slug_re.fullmatch(c)
        )[:2]
        matched_products = sorted(
            s for s in products
            if s == query_slug or s.startswith(query_slug + "-")
        )
        self.stats["matched_products"] = len(matched_products)

        items: dict[str, dict] = {}
        for collection in matched_collections:
            for item in self._collection_items(collection):
                items.setdefault(item["slug"], item)

        remaining = [s for s in matched_products if s not in items]
        limit = max(0, self.settings.edessa_max_detail_requests)
        if len(remaining) > limit:
            # Rotate the window hourly so long series are fully covered over
            # successive refresh cycles instead of always the same volumes.
            start = (int(time.time() // 3600) * limit) % len(remaining)
            window = (remaining + remaining)[start:start + limit]
            self.stats["detail_capped"] = len(remaining) - limit
            remaining = window
        for slug in remaining:
            try:
                item = self._detail_item(slug)
            except ScraperError as exc:
                logger.warning("edessa: product page %s failed: %s", slug, exc)
                self.stats["rejected"]["detail_error"] = (
                    self.stats["rejected"].get("detail_error", 0) + 1
                )
                continue
            if item is not None:
                items[slug] = item

        results: list[SearchResult] = []
        for slug, item in items.items():
            if not item.get("image"):
                item["image"] = products.get(slug)
            result, reason = self._to_result(item)
            if reason is not None:
                self.stats["rejected"][reason] = self.stats["rejected"].get(reason, 0) + 1
                continue
            results.append(result)

        results = filter_manga_results(results, stats=self.stats)
        self.stats["accepted"] = len(results)
        return results

    # -- sitemap index -------------------------------------------------------------
    def _cached(self, name: str, loader):
        ttl = max(0.0, self.settings.edessa_index_ttl_minutes) * 60
        with _INDEX_LOCK:
            hit = _INDEX_CACHE.get(name)
            if hit is not None and time.monotonic() - hit[0] < ttl:
                return hit[1]
            data = loader()
            _INDEX_CACHE[name] = (time.monotonic(), data)
            return data

    def _fetch_sitemap(self, path: str) -> ET.Element:
        url = f"{self.base_url}{path}"
        response = self.get(url)
        if response.status_code >= 400 or looks_like_blocked_page(
            response.status_code, response.text
        ):
            raise ScraperError(f"edessa: HTTP {response.status_code} for {url}")
        try:
            return ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ScraperError(f"edessa: invalid sitemap XML at {url}") from exc

    def _product_index(self) -> dict[str, str | None]:
        """product slug -> cover image URL (from ``products.xml``)."""

        def load() -> dict[str, str | None]:
            root = self._fetch_sitemap("/products.xml")
            index: dict[str, str | None] = {}
            for url in root.findall("sm:url", _SITEMAP_NS):
                loc = url.findtext("sm:loc", default="", namespaces=_SITEMAP_NS).strip()
                if not loc:
                    continue
                image = url.findtext("image:image/image:loc", default=None, namespaces=_SITEMAP_NS)
                index[_slug_of(loc)] = image.strip() if image else None
            return index

        return self._cached("products", load)

    def _collection_index(self) -> frozenset[str]:
        def load() -> frozenset[str]:
            root = self._fetch_sitemap("/collections.xml")
            return frozenset(
                _slug_of(loc.text.strip())
                for loc in root.findall("sm:url/sm:loc", _SITEMAP_NS)
                if loc.text and loc.text.strip()
            )

        return self._cached("collections", load)

    # -- collection page (__NEXT_DATA__) -------------------------------------------
    def _collection_items(self, collection: str) -> list[dict]:
        url = f"{self.base_url}/{collection}"
        response = self.get(url)
        if response.status_code >= 400 or looks_like_blocked_page(
            response.status_code, response.text
        ):
            logger.warning("edessa: collection %s HTTP %s", collection, response.status_code)
            return []
        self.stats["collections_fetched"] += 1
        match = _NEXT_DATA_RE.search(response.text)
        if match is None:
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []
        items: list[dict] = []
        for products in _find_products_lists(data):
            for product in products:
                item = self._collection_product(product)
                if item is not None:
                    items.append(item)
        return items

    @staticmethod
    def _collection_product(product) -> dict | None:
        if not isinstance(product, dict):
            return None
        name = " ".join(str(product.get("name") or "").split())
        slug = str((product.get("metaData") or {}).get("slug") or "").strip()
        variants = product.get("variants") or []
        if not name or not slug or not variants or not isinstance(variants[0], dict):
            return None
        variant = variants[0]
        prices = variant.get("prices") or []
        price_node = prices[0] if prices and isinstance(prices[0], dict) else {}
        # ``discountPrice`` is the price the shop actually charges when set
        # (``sellPrice`` is then the struck-through list price).
        price = _to_decimal(price_node.get("discountPrice")) or _to_decimal(
            price_node.get("sellPrice")
        )
        stock = variant.get("stock")
        if not isinstance(stock, (int, float)):
            stock = sum(
                s.get("stockCount") or 0
                for s in variant.get("stocks") or []
                if isinstance(s, dict)
            )
        in_stock = bool(variant.get("isActive", True)) and (
            stock > 0 or bool(variant.get("sellIfOutOfStock"))
        )
        barcodes = variant.get("barcodeList") or []
        isbn = normalize_isbn(variant.get("sku")) or (
            normalize_isbn(barcodes[0]) if barcodes else None
        )
        brand = product.get("brand") or {}
        return {
            "slug": slug,
            "title": name,
            "isbn": isbn,
            "publisher": brand.get("name") if isinstance(brand, dict) else None,
            "price": price,
            "in_stock": in_stock,
            "image": None,
            "category": None,
        }

    # -- product page (JSON-LD) ------------------------------------------------------
    def _detail_item(self, slug: str) -> dict | None:
        url = f"{self.base_url}/{slug}"
        response = self.get(url)
        if response.status_code == 404:
            return None
        if response.status_code >= 400 or looks_like_blocked_page(
            response.status_code, response.text
        ):
            raise ScraperError(f"edessa: product page HTTP {response.status_code} for {url}")
        self.stats["details_fetched"] += 1
        nodes = self.extract_json_ld(response.text)
        node = self.product_json_ld_node(nodes)
        if node is None:
            return None
        offers = node.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        offers = offers if isinstance(offers, dict) else {}
        availability = str(offers.get("availability") or "")
        images = node.get("image")
        image = images[0] if isinstance(images, list) and images else images
        brand = node.get("brand")
        category = None
        for crumb in nodes:
            if crumb.get("@type") == "BreadcrumbList":
                elements = crumb.get("itemListElement") or []
                if len(elements) >= 2 and isinstance(elements[1], dict):
                    category = elements[1].get("name")
        return {
            "slug": slug,
            "title": " ".join(str(node.get("name") or "").split()),
            "isbn": normalize_isbn(node.get("sku")) or normalize_isbn(node.get("mpn")),
            "publisher": brand.get("name") if isinstance(brand, dict) else None,
            "price": _to_decimal(offers.get("price")),
            # Unknown availability keeps the base-class convention (True).
            "in_stock": not ("OutOfStock" in availability or "Discontinued" in availability),
            "image": image if isinstance(image, str) else None,
            "category": category,
        }

    # -- normalization -------------------------------------------------------------
    def _to_result(self, item: dict) -> tuple[SearchResult | None, str | None]:
        title = item.get("title") or ""
        if not title:
            return None, "no_title"
        parsed = parse_volume_title(title)
        if parsed.is_collection:
            return None, "collection"
        return (
            SearchResult(
                store_id=self.store_id,
                store_name=self.store_name,
                title=title,
                product_url=f"{self.base_url}/{item['slug']}",
                series_title=parsed.base_title or None,
                volume_number=parsed.volume_number,
                isbn=item.get("isbn"),
                publisher=item.get("publisher"),
                category=item.get("category"),
                price=item.get("price"),
                currency="TRY",
                in_stock=bool(item.get("in_stock", True)),
                image_url=item.get("image"),
                relevance=1.0,
            ),
            None,
        )
