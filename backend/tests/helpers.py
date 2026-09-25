"""Helpers for scraper tests: file fixtures and a mock httpx client."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class RecordingScraper:
    """Fake store scraper for import/search tests.

    Records every ``search()`` call, sleeps an optional ``delay`` (to
    simulate slow stores), optionally raises ``fail`` (str -> ScraperError),
    and returns canned ``SearchResult`` objects. Implements the scraper
    contract (``store_id`` / ``store_name`` / ``search`` / ``close``) without
    any network access.
    """

    def __init__(
        self,
        store_id: str = "bkm",
        store_name: str = "BKM Kitap",
        results: list | None = None,
        delay: float = 0.0,
        fail: str | Exception | None = None,
    ) -> None:
        from app.scrapers.base import ScraperError

        self.store_id = store_id
        self.store_name = store_name
        self.results = results or []
        self.delay = delay
        self.fail = fail
        self.calls: list[str] = []
        #: Same contract as BaseScraper.stats (ImportService logs it).
        self.stats: dict = {}
        self._ScraperError = ScraperError

    def search(self, query: str) -> list:
        self.calls.append(query)
        if self.delay:
            time.sleep(self.delay)
        if self.fail is not None:
            if isinstance(self.fail, Exception):
                raise self.fail
            raise self._ScraperError(f"{self.store_id}: {self.fail}")
        return list(self.results)

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass
