"""Scraper base class and shared HTTP plumbing."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..config import get_settings
from .common import has_block_marker, looks_like_blocked_page, parse_tr_price
from .search_result import SearchResult

logger = logging.getLogger("yomiba.scraper")


@dataclass(frozen=True)
class ListingCheck:
    """Stock (and price, when shown) read from one product page."""

    in_stock: bool
    price: Decimal | None = None


class ScraperError(RuntimeError):
    """Raised when a scraper cannot complete its job.

    Carries enough information (store, URL, reason) to debug the failure.
    ``ImportService`` catches this (and any other exception) per scraper so
    one failing store never crashes the whole import.
    """


class BaseScraper:
    """Common behaviour for all store scrapers.

    Subclasses set ``store_id`` / ``store_name`` / ``base_url`` and implement
    :meth:`search`. They must return a list of ``SearchResult`` and must NOT
    touch the database in any way.
    """

    store_id: str = ""
    store_name: str = ""
    base_url: str = ""
    #: The store drops sold-out products from its search results (Kitapseç,
    #: Kitap Sepeti), so a listing missing from a successful search is
    #: re-checked on its product page instead of keeping "in stock".
    verifies_unseen_listings: bool = False
    #: Product URLs the last search found REMOVED from the store (e.g. a
    #: 404 product page); the importer deletes their listings.
    gone_urls: set[str] = set()

    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self.settings = settings
        #: Per-search diagnostics filled in by scrapers that support it
        #: (e.g. BKM: pages fetched, raw/accepted/rejected counts).
        #: Read by ``ImportService`` for logging; not part of the contract.
        self.stats: dict = {}
        #: Last request time of this instance (per-store rate limit).
        self._last_request_at: float = 0.0
        if client is not None:
            self.client = client
            self._owns_client = False
        else:
            self.client = httpx.Client(
                headers={
                    "User-Agent": settings.http_user_agent,
                    "Accept-Language": settings.http_accept_language,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout=settings.http_timeout,
                follow_redirects=True,
            )
            self._owns_client = True

    # -- to be implemented by subclasses ----------------------------------------
    def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError

    # -- shared helpers ------------------------------------------------------------
    #: HTTP statuses worth retrying (transient server/load issues).
    #: Bot walls (403/429/503 with wall markers) are NOT retried — see
    #: :meth:`get`.
    _RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
    _MAX_RETRY_DELAY = 30.0

    @staticmethod
    def _is_bot_wall(response: httpx.Response) -> bool:
        """Transport-level wall check: 403, or known wall markers in the body.

        Deliberately stricter than ``looks_like_blocked_page``: a plain 503
        or 429 is usually a transient server/load issue and gets retried.
        """
        if response.status_code == 403:
            return True
        return has_block_marker(response.text)

    def _throttle(self) -> None:
        """Per-store politeness: keep a minimum gap between requests."""
        min_interval = self.settings.scraper_min_request_interval_seconds
        if min_interval <= 0:
            return
        wait = self._last_request_at + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _sleep_backoff(self, attempt: int, retry_after: str | None = None) -> None:
        """Exponential backoff with jitter; honours ``Retry-After`` on 429.

        Jitter is applied BEFORE the cap so the final delay never exceeds
        ``_MAX_RETRY_DELAY`` (30s).
        """
        base = self.settings.scraper_retry_backoff_seconds
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = base * (2 ** (attempt - 1))
        else:
            delay = base * (2 ** (attempt - 1))
        delay = min(delay * random.uniform(0.75, 1.25), self._MAX_RETRY_DELAY)
        if delay > 0:
            time.sleep(delay)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET ``url`` with per-store rate limiting and bounded retries.

        Transient failures (transport errors, 429/5xx) are retried up to
        ``scraper_max_retries`` times with exponential backoff + jitter.
        Bot walls and other non-transient responses are returned / raised
        immediately — never faked, never spun on.

        The minimum request interval applies to every attempt, including
        retries (throttling happens at the top of the loop).
        """
        max_retries = max(0, self.settings.scraper_max_retries)
        for attempt in range(1, max_retries + 2):
            self._throttle()
            try:
                response = self.client.get(url, **kwargs)
            except httpx.HTTPError as exc:
                if attempt > max_retries:
                    raise ScraperError(
                        f"{self.store_id}: request failed after {attempt} "
                        f"attempts for {url}: {exc}"
                    ) from exc
                logger.warning(
                    "%s: transport error for %s (attempt %d/%d): %s",
                    self.store_id, url, attempt, max_retries + 1, exc,
                )
                self._sleep_backoff(attempt)
                continue

            if response.status_code in self._RETRYABLE_STATUS:
                if self._is_bot_wall(response):
                    return response  # fail fast; caller raises the block error
                if attempt > max_retries:
                    raise ScraperError(
                        f"{self.store_id}: HTTP {response.status_code} after "
                        f"{attempt} attempts for {url} (giving up)"
                    )
                logger.warning(
                    "%s: HTTP %d for %s (attempt %d/%d); retrying",
                    self.store_id, response.status_code, url, attempt, max_retries + 1,
                )
                self._sleep_backoff(attempt, retry_after=response.headers.get("Retry-After"))
                continue
            return response
        # Unreachable: every loop path returns or raises.
        raise ScraperError(f"{self.store_id}: request to {url} exhausted retries")

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.get(url, **kwargs)
        if response.status_code >= 400:
            raise ScraperError(
                f"{self.store_id}: HTTP {response.status_code} for {url}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ScraperError(f"{self.store_id}: invalid JSON from {url}") from exc

    @staticmethod
    def soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def extract_json_ld(html: str) -> list[dict]:
        """Return all schema.org JSON-LD nodes found in ``html``.

        Works both with a flat ``{"@type": "Book", ...}`` document and with an
        ``@graph`` array.
        """
        import json
        import re

        nodes: list[dict] = []
        for block in re.findall(
            r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
            html,
            re.S | re.I,
        ):
            try:
                data = json.loads(block.strip())
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                nodes.extend(n for n in data if isinstance(n, dict))
            elif isinstance(data, dict):
                graph = data.get("@graph")
                if isinstance(graph, list):
                    nodes.extend(n for n in graph if isinstance(n, dict))
                else:
                    nodes.append(data)
        return nodes

    @staticmethod
    def product_json_ld_node(nodes: list[dict]) -> dict | None:
        """Find the Product/Book node among JSON-LD nodes."""
        for node in nodes:
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            if any(t in ("Product", "Book") for t in types if isinstance(t, str)):
                return node
        return None

    def check_listing(self, url: str) -> ListingCheck | None:
        """Read stock/price of one product page from its schema.org
        Product JSON-LD ``offers``. None when unknown: HTTP error, bot wall,
        a removed product redirecting elsewhere (no Product node), or an
        availability value without a clear meaning. May raise ScraperError
        on transport failure."""
        response = self.get(url)
        if response.status_code >= 400 or looks_like_blocked_page(
            response.status_code, response.text
        ):
            return None
        node = self.product_json_ld_node(self.extract_json_ld(response.text))
        if node is None:
            return None
        offers = node.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if not isinstance(offers, dict):
            return None
        availability = str(offers.get("availability") or "")
        if "OutOfStock" in availability or "Discontinued" in availability or "SoldOut" in availability:
            in_stock = False
        elif "InStock" in availability or "LimitedAvailability" in availability or "PreOrder" in availability:
            in_stock = True
        else:
            return None
        return ListingCheck(in_stock=in_stock, price=parse_tr_price(offers.get("price")))

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "BaseScraper":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
