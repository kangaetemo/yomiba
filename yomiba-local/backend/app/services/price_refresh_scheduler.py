"""Periodic background price refresh.

Keeps search results fresh WITHOUT searches ever blocking on a store
scrape:

Every interval the scheduler looks at every ``ImportRecord`` (one per
query that was ever searched / warmed up) and re-submits the ones whose
last successful import is stale (older than
``import_freshness_ttl_minutes``) to the existing
:class:`BackgroundImportRunner`. The runner's per-query dedup, bounded
concurrency semaphore and catalog write gate apply unchanged, so a refresh
pass can never hammer a store or fight a running catalog sync — and a
search that triggers a refresh at request time is simply joined by it.

Queries inside their ``import_failure_retry_minutes`` window after an
attempt are left alone (the same anti-hammering rule the search flow uses).

Production shape only (``auto_init``), enabled via env — tests run with
``auto_init=False`` and never start it. Like the catalog sync scheduler,
the first run happens one full interval AFTER process start (deliberately
no catch-up at startup).
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import ImportRecord
from ..utils import utcnow
from .background_import import BackgroundImportRunner, aware_datetime

logger = logging.getLogger("yomiba.price_refresh")


class PriceRefreshScheduler:
    """Re-imports stale search queries on a fixed interval (daemon thread)."""

    def __init__(
        self,
        runner: BackgroundImportRunner,
        session_factory: sessionmaker[Session],
        interval_seconds: float,
        *,
        poll_seconds: float = 60.0,
    ) -> None:
        self._runner = runner
        self._session_factory = session_factory
        self._interval = max(interval_seconds, 1.0)
        self._poll = max(poll_seconds, 1.0)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- lifecycle --------------------------------------------------------------
    def start(self) -> None:
        """Start the daemon loop (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="yomiba-price-refresh", daemon=True
        )
        self._thread.start()
        logger.info(
            "price refresh scheduler started (first run in %.1fh, then every %.1fh)",
            self._interval / 3600.0,
            self._interval / 3600.0,
        )

    def stop(self, timeout: float = 10.0) -> None:
        """Signal the loop to exit and join it (lifespan shutdown)."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        # Sleep-first: no catch-up pass right after process start (same
        # restart contract as the catalog sync scheduler).
        while not self._stop.is_set() and not self._stop.wait(self._interval):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the scheduler must not die
                logger.exception("price refresh tick failed")

    # -- one pass -----------------------------------------------------------------
    def tick(self) -> int:
        """Submit every stale query to the runner; return how many queued.

        A query is stale when it has no successful import yet, or its last
        success is older than the freshness TTL. A query whose most recent
        attempt (any status) is still inside the failure-retry window is
        skipped — the same rule ``search_with_auto_import`` applies.
        """
        settings = get_settings()
        ttl = timedelta(minutes=settings.import_freshness_ttl_minutes)
        retry_window = timedelta(minutes=settings.import_failure_retry_minutes)
        now = utcnow()

        session = self._session_factory()
        try:
            records = session.scalars(select(ImportRecord)).all()
        finally:
            session.close()

        submitted = 0
        for record in records:
            last_success = aware_datetime(record.last_success_at)
            last_attempt = aware_datetime(record.last_attempt_at)
            fresh = last_success is not None and (now - last_success) <= ttl
            if fresh:
                continue
            recent_attempt = (
                last_attempt is not None and (now - last_attempt) < retry_window
            )
            if recent_attempt:
                continue
            key = record.normalized_query
            query = record.last_query or record.normalized_query
            if self._runner.submit(key, query):
                submitted += 1

        if submitted:
            logger.info("price refresh: submitted %d stale quer(y/ies)", submitted)
        return submitted
