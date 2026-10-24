"""Stale-while-revalidate cache for site-wide, read-only feeds.

The home feed and the site-wide deals list are the same for every visitor
and take seconds to compute on the production database (more while a price
refresh competes for the CPU). A plain TTL cache made the first visitor
after each expiry wait for the whole computation; here an expired value is
still served at once while one background thread recomputes it. Only a cold
key (first request after a restart, before the warm-up finished) waits.

A committed write to a table the feeds read (prices, listings, catalog,
reader lists) marks every cached value stale, so the next warm-up round or
request rebuilds it: a new deal or an admin edit shows within about a
minute instead of after the full ``fresh_seconds``. Rebuilds are at least
MIN_REBUILD_SECONDS apart, so a price refresh committing all the time does
not keep the CPU busy rebuilding.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("yomiba.swr_cache")

MIN_REBUILD_SECONDS = 45.0
#: Writes to these tables change what the cached feeds show.
WATCHED_TABLES = (
    "store_listings", "price_history", "volumes", "series", "catalog_series", "publishers",
    "stores", "series_popularity", "wishlist_items", "user_volume_collections",
    "catalog_exclusions", "listing_exclusions",
)
_WATCHED_WRITE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE)\b.*?\b(" + "|".join(WATCHED_TABLES) + r")\b",
    re.IGNORECASE | re.DOTALL)
#: ...except a volume's text intro (the description worker writes one per
#: volume, all day): no cached feed shows it.
_IGNORED_WRITE = re.compile(
    r"^\s*UPDATE volumes SET (description(_source|_checked_at)?=\?(, )?)+ WHERE", re.IGNORECASE)
_caches: list["SwrCache"] = []


class SwrCache:
    def __init__(self, name: str, fresh_seconds: float) -> None:
        self.name = name
        self.fresh_seconds = fresh_seconds
        self._values: dict[tuple, tuple[float, Any]] = {}
        self._lock = threading.Lock()  # bookkeeping only, never held while computing
        self._compute_lock = threading.Lock()
        self._refreshing: set[tuple] = set()
        #: monotonic time of the last committed watched write; a value built
        #: (started) before it is stale.
        self._changed_at = 0.0
        _caches.append(self)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def mark_stale(self) -> None:
        self._changed_at = time.monotonic()

    def _is_stale(self, built_at: float) -> bool:
        age = time.monotonic() - built_at
        return age >= self.fresh_seconds or (built_at < self._changed_at and age >= MIN_REBUILD_SECONDS)

    def get(self, session: Session, key: tuple, compute: Callable[[Session], Any]) -> Any:
        """``compute(session)``'s value for ``key``; callers must not mutate it.

        Keys are per database (the session's bind), so tests never share."""
        key = (id(session.get_bind()), *key)
        hit = self._values.get(key)
        if hit is not None:
            if self._is_stale(hit[0]):
                self._refresh_in_background(session, key, compute)
            return hit[1]
        # Cold: one computation at a time, concurrent first visitors wait for it.
        with self._compute_lock:
            hit = self._values.get(key)
            if hit is not None:
                return hit[1]
            started = time.monotonic()
            value = compute(session)
            self._values[key] = (started, value)
            return value

    def _refresh_in_background(self, session: Session, key: tuple, compute) -> None:
        with self._lock:
            if key in self._refreshing:
                return
            self._refreshing.add(key)
        factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)

        def run() -> None:
            started = time.monotonic()
            try:
                with factory() as own:
                    value = compute(own)
                # Stamped with its start: a write committed while it was
                # being built makes it stale again.
                self._values[key] = (started, value)
                logger.info("%s refreshed in %.1fs", self.name, time.monotonic() - started)
            except Exception:  # noqa: BLE001 — keep serving the old value
                logger.exception("%s refresh failed; serving the previous value", self.name)
            finally:
                with self._lock:
                    self._refreshing.discard(key)

        threading.Thread(target=run, name=f"swr-{self.name}", daemon=True).start()


def mark_all_stale() -> None:
    for cache in _caches:
        cache.mark_stale()


@event.listens_for(Engine, "before_cursor_execute")
def _note_watched_write(conn, cursor, statement, parameters, context, executemany):
    if (not conn.info.get("swr_dirty") and _WATCHED_WRITE.match(statement)
            and not _IGNORED_WRITE.match(statement)):
        conn.info["swr_dirty"] = True


@event.listens_for(Engine, "commit")
def _commit(conn):
    if conn.info.pop("swr_dirty", False):
        mark_all_stale()


@event.listens_for(Engine, "rollback")
def _rollback(conn):
    conn.info.pop("swr_dirty", None)


class CacheWarmer:
    """Keeps the busiest cached feeds warm: ``warm(session)`` runs once at
    startup and then every ``every_seconds``. Each call goes through the
    cache, so a fresh value costs nothing and an expired one is rebuilt in
    the background before a visitor asks for it."""

    def __init__(self, session_factory, warm: Callable[[Session], None], every_seconds: float = 15.0) -> None:
        self._session_factory = session_factory
        self._warm = warm
        self._every = every_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="cache-warmer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                with self._session_factory() as session:
                    self._warm(session)
            except Exception:  # noqa: BLE001 — try again on the next round
                logger.exception("cache warm-up failed")
            else:
                logger.debug("cache warm-up round took %.1fs", time.monotonic() - started)
            self._stop.wait(self._every)
