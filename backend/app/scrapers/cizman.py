"""Cizman scraper (live-verified against cizman.com, 2026-09-10).

Data sources (all public, no authentication):

1. Search: the store's public search form is an ASP.NET form:
     POST https://www.cizman.com/   (fields: __VIEWSTATE, __VIEWSTATEGENERATOR,
      __RequestVerificationToken, ctl00$YeniHeader$txtbxArama=<query>)
   The anti-forgery token + viewstate are read from the public home page
   first (normal form usage — no session/cookie handling). The response is
   one server-side rendered results page (no pagination parameter observed;
   a "berserk" search returned the full 100+ card grid).
   Cards (``div.productItem``):
     * ``div.productImage a``          -> product URL (href) + title (title attr)
     * ``div.productMarka``            -> publisher (hidden label)
     * ``div.discountPrice .discountPriceSpan`` -> current price ("₺184,00")
     * ``div.regularPrice``            -> list price (ignored)
     * ``a.btnAddToCart``              -> present when in stock; out-of-stock
       cards render no add-to-cart button ("Tükendi" badge instead)
2. Detail page (enrichment, best effort): schema.org JSON-LD ``Product``
   (name / image / description) plus the ISBN rendered in the page (stok
   kodu / barcode). The JSON-LD carries no isbn/sku, so the first valid
   13-digit ISBN in the page text is used.

Behaviour mirrors the other store scrapers: non-manga / collection
filtering, bot-wall fail-fast (``looks_like_blocked_page`` ->
``ScraperError``, never retried), best-effort detail enrichment limited by
``settings.max_detail_requests``.

robots.txt disallows /Print/, /Handlers/, /Uploads/languages/, /Templates/
only; search / product pages are allowed for regular clients.

The scraper never writes to the database.
"""

from __future__ import annotations

import html as html_module
import logging
import re
import urllib.parse
from urllib.parse import urljoin

import httpx

from ..normalization import normalize_isbn, normalize_text, parse_volume_title
from .base import BaseScraper, ScraperError
from .common import looks_like_blocked_page, parse_tr_price
from .search_result import SearchResult
from .relevance import filter_manga_results

logger = logging.getLogger("yomiba.scraper.cizman")

NON_MANGA_KEYWORDS: tuple[str, ...] = (
    "figur", "asorti", "oyuncak", "puzzle", "kupa", "tisort", "tshirt",
    "poster", "defter", "pelus", "action", "fig", "model kit", "blind bag",
)

_ISBN_RE = re.compile(r"\b(978\d{10})\b")


class CizmanScraper(BaseScraper):
    store_id = "cizman"
    store_name = "Cizman"
    base_url = "https://www.cizman.com"
    _TOKEN_FIELD = "ctl00$YeniHeader$txtbxArama"
    #: Minimum token length for the relevance guard (same rule as kitapbulan).
    _RELEVANCE_TOKEN_MIN_LEN = 3

    def search(self, query: str) -> list[SearchResult]:
        self.stats = {
            "pages_fetched": 1,
            "raw_products": 0,
            "duplicates_skipped": 0,
            "rejected": {},
            "accepted": 0,
            "stop_reason": None,
        }

        response = self._post_search(query)
        soup = self.soup(response.text)

        query_core = normalize_text(parse_volume_title(query).base_title)
        query_tokens = [
            normalize_text(token)
            for token in query.split()
            if len(normalize_text(token)) >= self._RELEVANCE_TOKEN_MIN_LEN
        ]
        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        max_results = max(1, self.settings.cizman_max_search_results)

        for card in soup.select("div.productItem"):
            self.stats["raw_products"] += 1
            item = self._card_to_item(card)
            if item is None:
                continue
            if item["url"] in seen_urls:
                self.stats["duplicates_skipped"] += 1
                continue
            seen_urls.add(item["url"])

            result, reason = self._parse_card(item, query_core, query_tokens)
            if reason is not None:
                self.stats["rejected"][reason] = self.stats["rejected"].get(reason, 0) + 1
                continue
            results.append(result)
            if len(results) >= max_results:
                self.stats["stop_reason"] = "max_results"
                break
        else:
            self.stats["stop_reason"] = "single_page"

        results = self._enrich_with_details(results)
        self.stats["accepted"] = len(results)
        results = filter_manga_results(results, stats=self.stats)
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results

    # -- search (public form: token from home page, then POST) ----------------------
    def _post_search(self, query: str):
        home = self.get(f"{self.base_url}/")
        if looks_like_blocked_page(home.status_code, home.text):
            raise ScraperError(
                f"cizman: request blocked or robot-checked "
                f"(HTTP {home.status_code}) for query {query!r}"
            )
        if home.status_code >= 400:
            raise ScraperError(f"cizman: home page HTTP {home.status_code}")

        def field(name: str) -> str:
            m = re.search(
                rf'name="{re.escape(name)}"[^>]*value="([^"]*)"', home.text
            )
            return html_module.unescape(m.group(1)) if m else ""

        viewstate = field("__VIEWSTATE")
        viewstate_gen = field("__VIEWSTATEGENERATOR")
        token = field("__RequestVerificationToken")
        if not (viewstate and token):
            raise ScraperError(
                "cizman: could not read the public search form "
                "(__VIEWSTATE / __RequestVerificationToken missing)"
            )

        data = urllib.parse.urlencode(
            {
                "__VIEWSTATE": viewstate,
                "__VIEWSTATEGENERATOR": viewstate_gen,
                "__RequestVerificationToken": token,
                self._TOKEN_FIELD: query,
            }
        )
        response = self._post_request(
            f"{self.base_url}/",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{self.base_url}/",
            },
        )
        if looks_like_blocked_page(response.status_code, response.text):
            raise ScraperError(
                f"cizman: search blocked or robot-checked "
                f"(HTTP {response.status_code}) for query {query!r}"
            )
        if response.status_code >= 400:
            raise ScraperError(f"cizman: search HTTP {response.status_code} for {query!r}")
        return response

    def _post_request(self, url: str, **kwargs):
        """POST with the same politeness/retry rules as ``BaseScraper.get``
        (per-store throttle, bounded retries, bot-wall fail-fast)."""
        max_retries = max(0, self.settings.scraper_max_retries)
        for attempt in range(1, max_retries + 2):
            self._throttle()
            try:
                response = self.client.post(url, **kwargs)
            except httpx.HTTPError as exc:
                if attempt > max_retries:
                    raise ScraperError(
                        f"cizman: request failed after {attempt} attempts for {url}: {exc}"
                    ) from exc
                logger.warning(
                    "cizman: transport error for %s (attempt %d/%d): %s",
                    url, attempt, max_retries + 1, exc,
                )
                self._sleep_backoff(attempt)
                continue

            if response.status_code in self._RETRYABLE_STATUS:
                if self._is_bot_wall(response):
                    return response
                if attempt > max_retries:
                    raise ScraperError(
                        f"cizman: HTTP {response.status_code} after {attempt} attempts for {url}"
                    )
                logger.warning(
                    "cizman: HTTP %d for %s (attempt %d/%d); retrying",
                    response.status_code, url, attempt, max_retries + 1,
                )
                self._sleep_backoff(attempt, retry_after=response.headers.get("Retry-After"))
                continue
            return response
        raise ScraperError(f"cizman: request to {url} exhausted retries")

    # -- card parsing ----------------------------------------------------------------
    @staticmethod
    def _parse_price(card, price_el) -> Decimal | None:
        """Extract the TRY price from a cizman card.

        Turkish products render a TRY price (``₺205,00``) in
        ``.discountPrice .discountPriceSpan``. Imported English products are
        shown in their foreign currency (``$13.99``) in the same span; the
        store keeps the TRY equivalent in the hidden ``.tlfiyati`` element,
        which is what we record (the app tracks TRY).
        """
        if price_el is None:
            return None
        raw = price_el.get_text(" ", strip=True)
        if re.search(r"[$€£]", raw):
            # Foreign-currency display: fall back to the store's own TRY value.
            try_el = card.select_one("div.tlfiyati span")
            if try_el is None:
                return None
            return parse_tr_price(try_el.get_text(" ", strip=True))
        return parse_tr_price(raw)

    @staticmethod
    def _card_to_item(card) -> dict | None:
        anchor = card.select_one("div.productImage a")
        if anchor is None:
            return None
        title = re.sub(r"\s+", " ", anchor.get("title") or anchor.get_text(" ", strip=True))
        href = anchor.get("href")
        if not title or not href:
            return None
        url = href if href.startswith("http") else urljoin(CizmanScraper.base_url + "/", href)

        brand_el = card.select_one("div.productMarka")
        publisher = re.sub(r"\s+", " ", brand_el.get_text(" ", strip=True)) if brand_el else ""

        price_el = card.select_one("div.discountPrice .discountPriceSpan")
        price = CizmanScraper._parse_price(card, price_el)

        img = card.select_one("img")
        image = None
        if img is not None:
            image = img.get("data-src") or img.get("data-original") or img.get("src")
            if image and image.startswith("//"):
                image = "https:" + image

        # In stock: the rendered card carries an add-to-cart button;
        # out-of-stock cards render a "Tükendi" badge instead.
        add_to_cart = card.select_one("a.btnAddToCart") is not None
        sold_out_text = "Tükendi" in (card.get_text(" ", strip=True) or "")
        in_stock = add_to_cart or not sold_out_text

        return {
            "title": title,
            "url": url,
            "publisher": publisher or None,
            "price": price,
            "image": image,
            "in_stock": in_stock,
        }

    @staticmethod
    def _is_non_manga(title: str) -> bool:
        normalized = normalize_text(title)
        return any(keyword in normalized for keyword in NON_MANGA_KEYWORDS)

    def _parse_card(
        self, item: dict, query_core: str, query_tokens: list[str]
    ) -> tuple[SearchResult | None, str | None]:
        title = item["title"]
        if self._is_non_manga(title):
            logger.debug("cizman: skipping non-manga item: %r", title)
            return None, "non_manga_keyword"

        parsed = parse_volume_title(title)
        if parsed.is_collection:
            logger.debug("cizman: skipping collection: %r", title)
            return None, "collection"

        # Vitrin/loose-search guard: cizman's search is fuzzy and pads the
        # grid with unrelated products (verified live: "berserk" returns
        # English imports like "Lonely Deaths Lie Thick as Snow"). Require
        # every significant query token in the title (same rule as kitapbulan).
        if query_tokens:
            normalized_title = normalize_text(title)
            if not all(token in normalized_title for token in query_tokens):
                logger.debug("cizman: skipping irrelevant card: %r", title)
                return None, "irrelevant"

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

    # -- detail-page enrichment (isbn) -------------------------------------------------
    def _enrich_with_details(self, results: list[SearchResult]) -> list[SearchResult]:
        limit = self.settings.max_detail_requests
        for index, result in enumerate(results[:limit]):
            try:
                results[index] = self._enrich_one(result)
            except ScraperError:
                logger.warning(
                    "cizman: detail enrichment blocked/failed for %s (keeping search data)",
                    result.product_url,
                )
            except Exception:
                logger.exception("cizman: unexpected enrichment error for %s", result.product_url)
        return results

    def _enrich_one(self, result: SearchResult) -> SearchResult:
        if result.isbn:
            return result
        response = self.get(result.product_url)
        if response.status_code >= 400 or looks_like_blocked_page(
            response.status_code, response.text
        ):
            raise ScraperError(
                f"cizman: detail page HTTP {response.status_code} for {result.product_url}"
            )
        # The product page renders the barcode in the "stok kodu" area; take
        # the first valid ISBN-13 in the visible text.
        for match in _ISBN_RE.finditer(response.text):
            isbn = normalize_isbn(match.group(1))
            if isbn:
                return result.model_copy(update={"isbn": isbn})
        return result
