"""Phase 20: scraper reliability.

Retry with backoff on transient failures (transport errors, 429/5xx),
fail-fast on bot walls, per-store request interval, and BKM-level recovery
(transient page failure vs. persistent failure -> searchAll fallback).
"""

from __future__ import annotations

import json
import time

import httpx
import pytest
from dataclasses import replace

# Module reference on purpose: the autouse conftest fixture patches
# ``app.scrapers.base.get_settings``; call it through the module at test time.
from app.scrapers import base as scraper_base
from app.scrapers.base import ScraperError
from app.scrapers.bkm import BkmScraper
from tests.helpers import fixture_json, mock_client


def make_scraper(handler, **overrides) -> BkmScraper:
    scraper = BkmScraper(client=mock_client(handler))
    if overrides:
        scraper.settings = replace(scraper_base.get_settings(), **overrides)
    return scraper


def test_retry_transient_503_then_success():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return (
            httpx.Response(200, text="ok")
            if calls["n"] >= 3
            else httpx.Response(503, text="transient")
        )

    scraper = make_scraper(handler)
    assert scraper.get("https://x.test/page").status_code == 200
    assert calls["n"] == 3


def test_retry_transport_error_then_success():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200, text="ok")

    scraper = make_scraper(handler)
    assert scraper.get("https://x.test/page").status_code == 200
    assert calls["n"] == 3


def test_no_retry_on_404():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, text="not found")

    scraper = make_scraper(handler)
    assert scraper.get("https://x.test/page").status_code == 404
    assert calls["n"] == 1  # non-transient: fail fast


def test_no_retry_on_bot_wall():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="<html>Robot Check</html>")

    scraper = make_scraper(handler)
    # The response is returned (caller raises the descriptive error); the
    # point is: a bot wall is never retried.
    assert scraper.get("https://x.test/page").status_code == 503
    assert calls["n"] == 1


def test_retries_exhausted_raises_scraper_error():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="after 3 attempts"):
        scraper.get("https://x.test/page")
    assert calls["n"] == 3


def test_429_is_retried_and_recovers():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow down", headers={"Retry-After": "0"})
        return httpx.Response(200, text="ok")

    scraper = make_scraper(handler)
    assert scraper.get("https://x.test/page").status_code == 200
    assert calls["n"] == 2


def test_429_gets_more_attempts_than_other_errors():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, text="slow down")

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError, match="HTTP 429 after 4 attempts"):
        scraper.get("https://x.test/page")
    assert calls["n"] == 4  # SCRAPER_RATE_LIMIT_MAX_RETRIES=3 (5xx keeps 2)


def test_429_waits_longer_and_pauses_the_store(monkeypatch):
    """A 429 waits SCRAPER_RATE_LIMIT_BACKOFF_SECONDS (doubling, capped) and
    holds back the store's other imports for the same time."""
    scraper_base._store_slots.clear()
    sleeps: list[float] = []
    monkeypatch.setattr(scraper_base.time, "sleep", sleeps.append)
    monkeypatch.setattr(scraper_base.random, "uniform", lambda a, b: a)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429) if calls["n"] < 4 else httpx.Response(200, text="ok")

    scraper = make_scraper(handler, scraper_rate_limit_backoff_seconds=10.0)
    started = time.monotonic()
    assert scraper.get("https://x.test/page").status_code == 200
    assert sleeps == [10.0, 20.0, 40.0]
    assert scraper_base._store_slots["bkm"] >= started + 40.0

    sleeps.clear()
    calls["n"] = 0
    scraper_base._store_slots.clear()
    scraper = make_scraper(lambda r: httpx.Response(429, headers={"Retry-After": "300"}),
                           scraper_rate_limit_backoff_seconds=10.0)
    with pytest.raises(ScraperError):
        scraper.get("https://x.test/page")
    assert sleeps == [60.0, 60.0, 60.0]  # Retry-After honoured up to the cap
    scraper_base._store_slots.clear()


def test_kitapbulan_has_a_wider_store_interval():
    from app.scrapers.kitapbulan import KitapbulanScraper

    scraper = KitapbulanScraper(client=mock_client(lambda r: httpx.Response(200)))
    scraper.settings = replace(scraper_base.get_settings(), scraper_store_min_interval_seconds=0.25,
                               kitapbulan_min_request_interval_seconds=1.0)
    assert scraper._store_min_interval() == 1.0
    assert make_scraper(lambda r: httpx.Response(200), scraper_store_min_interval_seconds=0.25,
                        kitapbulan_min_request_interval_seconds=1.0)._store_min_interval() == 0.25


def test_rate_limit_keeps_per_store_interval():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    scraper = make_scraper(handler, scraper_min_request_interval_seconds=0.06)
    started = time.monotonic()
    scraper.get("https://x.test/1")
    scraper.get("https://x.test/2")
    assert time.monotonic() - started >= 0.05


def test_rate_limit_applies_between_retries():
    """The minimum interval must hold for EVERY attempt, retries included."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return (
            httpx.Response(500, text="boom")
            if calls["n"] < 3
            else httpx.Response(200, text="ok")
        )

    scraper = make_scraper(handler, scraper_min_request_interval_seconds=0.05)
    started = time.monotonic()
    assert scraper.get("https://x.test/page").status_code == 200
    assert calls["n"] == 3
    # interval enforced before attempts 2 and 3 (not just the first)
    assert time.monotonic() - started >= 0.09


def test_store_interval_is_shared_across_concurrent_imports():
    """Two imports scraping the same store take turns; other stores do not wait."""
    import threading

    from app.scrapers.kitapsepeti import KitapsepetiScraper

    scraper_base._store_slots.clear()
    times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(time.monotonic())
        return httpx.Response(200, text="ok")

    overrides = dict(scraper_min_request_interval_seconds=0.0, scraper_store_min_interval_seconds=0.1)
    same = [make_scraper(handler, **overrides) for _ in range(2)]
    threads = [threading.Thread(target=lambda s=s: [s.get(f"https://x.test/{i}") for i in range(2)]) for s in same]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    times.sort()
    assert all(b - a >= 0.09 for a, b in zip(times, times[1:]))

    other = KitapsepetiScraper(client=mock_client(handler))
    other.settings = replace(scraper_base.get_settings(), **overrides)
    started = time.monotonic()
    other.get("https://y.test/1")
    assert time.monotonic() - started < 0.09


def test_backoff_delay_never_exceeds_30s_cap(monkeypatch):
    """Jitter is applied before the cap, so the final delay <= 30s."""
    from app.scrapers import base as base_mod

    sleeps: list[float] = []
    monkeypatch.setattr(base_mod.time, "sleep", lambda s: sleeps.append(s))

    scraper = BkmScraper(client=mock_client(lambda r: httpx.Response(200, text="ok")))
    scraper.settings = replace(base_mod.get_settings(), scraper_retry_backoff_seconds=100.0)

    scraper._sleep_backoff(attempt=5)  # 100 * 2**4 = 1600s before the cap
    assert sleeps and sleeps[-1] <= 30.0
    sleeps.clear()

    scraper._sleep_backoff(attempt=1, retry_after="999")  # Retry-After above cap
    assert sleeps and sleeps[-1] <= 30.0
    sleeps.clear()

    # Normal case: jitter stays within [0.75x, 1.25x] of the base delay.
    scraper.settings = replace(base_mod.get_settings(), scraper_retry_backoff_seconds=1.0)
    for _ in range(20):
        scraper._sleep_backoff(attempt=1)
    assert sleeps and all(0.75 <= s <= 1.25 for s in sleeps)


def test_get_json_still_raises_after_exhausted_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    scraper = make_scraper(handler)
    with pytest.raises(ScraperError):
        scraper.get_json("https://x.test/page")


# -- BKM end-to-end reliability ---------------------------------------------------

def test_bkm_search_recovers_from_transient_first_page():
    payload = {"res": fixture_json("bkm_searchv2_p1.json")["res"], "total_item_count": 3}
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" not in request.url.path:
            return httpx.Response(404)
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="transient waw hiccup")
        params = json.loads(request.url.params["search_params"])
        if params["page_number"] == 1:
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json={"res": [], "total_item_count": 3})

    scraper = make_scraper(handler, bkm_search_page_size=3)
    results = scraper.search("one piece")

    assert calls["n"] == 2  # one failed attempt + the successful page
    assert len(results) == 2  # 3 items minus the toy
    assert scraper.stats["stop_reason"] == "complete"


def test_bkm_persistent_v2_failure_falls_back_to_searchall():
    calls = {"n": 0}
    fallback = fixture_json("bkm_search.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if "search_v2" in request.url.path:
            calls["n"] += 1
            return httpx.Response(500, text="waw down")
        if "searchAll" in request.url.path:
            return httpx.Response(200, json=fallback)
        return httpx.Response(404)

    scraper = make_scraper(handler)
    results = scraper.search("berserk")

    assert calls["n"] == 3  # all retries of the single page exhausted
    assert scraper.stats["source"] == "searchAll"
    assert len(results) == 10  # no faked data — real fallback feed
