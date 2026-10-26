"""Scraper base class and shared HTTP plumbing."""

from __future__ import annotations

import logging
import random
import threading
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

#: store id -> next free request slot (monotonic), shared by every scraper
#: instance of the process: concurrent imports take turns per store.
_store_slots: dict[str, float] = {}
_store_slots_lock = threading.Lock()
#: store id -> monotonic time until which the store is not contacted at
#: all (it kept answering 429 after every retry).
_store_cooldowns: dict[str, float] = {}


def _reserve_store_slot(store_id: str, min_interval: float) -> float:
    """Book the next request slot of ``store_id``; return seconds to wait."""
    with _store_slots_lock:
        now = time.monotonic()
        slot = max(now, _store_slots.get(store_id, 0.0))
        _store_slots[store_id] = slot + min_interval
    return slot - now


def _pause_store(store_id: str, seconds: float) -> None:
    """Hold back every import's next request to ``store_id`` for ``seconds``
    (a 429 is about the store's view of our host, not one request)."""
    with _store_slots_lock:
        until = time.monotonic() + seconds
        _store_slots[store_id] = max(_store_slots.get(store_id, 0.0), until)


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
    #: {product URL: (title, ISBN)} the importer already read for this
    #: store; detail-page enrichment spends its budget on the rest.
    known_isbns: dict[str, tuple[str, str]] = {}

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
    #: Cap for one wait after HTTP 429, Retry-After included.
    _MAX_RATE_LIMIT_DELAY = 60.0

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
        """Per-store politeness: keep a minimum gap between requests, both
        within this instance and across all concurrent imports."""
        min_interval = self.settings.scraper_min_request_interval_seconds
        if min_interval > 0:
            wait = self._last_request_at + min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        store_interval = self._store_min_interval()
        if store_interval > 0:
            wait = _reserve_store_slot(self._store_key(), store_interval)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _store_key(self) -> str:
        return self.store_id or type(self).__name__

    def _store_min_interval(self) -> float:
        """Process-wide gap between two requests to this store; stores that
        rate-limit bursts override it."""
        return self.settings.scraper_store_min_interval_seconds

    def _rate_limit_delay(self, attempt: int, retry_after: str | None) -> float:
        """Wait after an HTTP 429: Retry-After when the store sends one,
        otherwise SCRAPER_RATE_LIMIT_BACKOFF_SECONDS doubled per attempt;
        never shorter than the ordinary backoff, never over 60s."""
        base = self.settings.scraper_retry_backoff_seconds * (2 ** (attempt - 1))
        delay = self.settings.scraper_rate_limit_backoff_seconds * (2 ** (attempt - 1))
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                pass
        delay = max(delay, base) * random.uniform(1.0, 1.25)
        return min(delay, self._MAX_RATE_LIMIT_DELAY)

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
        ``scraper_max_retries`` times with exponential backoff + jitter;
        HTTP 429 waits longer and gets up to ``scraper_rate_limit_max_retries``
        retries (see :meth:`_rate_limit_delay`), pausing the store for every
        concurrent import meanwhile.
        Bot walls and other non-transient responses are returned / raised
        immediately — never faked, never spun on.

        The minimum request interval applies to every attempt, including
        retries (throttling happens at the top of the loop).
        """
        cooldown_left = _store_cooldowns.get(self._store_key(), 0.0) - time.monotonic()
        if cooldown_left > 0:
            raise ScraperError(
                f"{self.store_id}: rate limited (HTTP 429), not contacted for "
                f"another {cooldown_left / 60:.0f} min; skipped {url}"
            )
        max_retries = max(0, self.settings.scraper_max_retries)
        rate_limit_retries = max(max_retries, self.settings.scraper_rate_limit_max_retries)
        for attempt in range(1, max(max_retries, rate_limit_retries) + 2):
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
                rate_limited = response.status_code == 429
                allowed = rate_limit_retries if rate_limited else max_retries
                if attempt > allowed:
                    if rate_limited and self.settings.scraper_rate_limit_cooldown_seconds > 0:
                        with _store_slots_lock:
                            _store_cooldowns[self._store_key()] = (
                                time.monotonic() + self.settings.scraper_rate_limit_cooldown_seconds
                            )
                        logger.warning(
                            "%s: still HTTP 429 after %d attempts; cooling down for %.0fs",
                            self.store_id, attempt, self.settings.scraper_rate_limit_cooldown_seconds,
                        )
                    raise ScraperError(
                        f"{self.store_id}: HTTP {response.status_code} after "
                        f"{attempt} attempts for {url} (giving up)"
                    )
                logger.warning(
                    "%s: HTTP %d for %s (attempt %d/%d); retrying",
                    self.store_id, response.status_code, url, attempt, allowed + 1,
                )
                retry_after = response.headers.get("Retry-After")
                if rate_limited:
                    delay = self._rate_limit_delay(attempt, retry_after)
                    _pause_store(self._store_key(), delay)
                    if delay > 0:
                        time.sleep(delay)
                else:
                    self._sleep_backoff(attempt, retry_after=retry_after)
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
