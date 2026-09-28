"""Single-process, bounded full-catalog price refresh dispatcher.

Each cycle reads current CatalogSeries membership. It dispatches only as
worker queue slots open, so catalog size never determines thread count.
The queue, cycle and SYNC_GATE are process-local; run one ASGI process.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import CatalogSeries, ImportRecord, Series, StoreListing, Volume
from ..utils import utcnow
from .background_import import BackgroundImportRunner, aware_datetime, normalized_query_key

logger = logging.getLogger("yomiba.price_refresh")


class PriceRefreshScheduler:
    def __init__(
        self,
        runner: BackgroundImportRunner,
        session_factory: sessionmaker[Session],
        interval_seconds: float,
        *,
        poll_seconds: float = 30.0,
        startup_delay_seconds: float | None = None,
    ) -> None:
        self._runner = runner
        self._session_factory = session_factory
        self._interval = max(interval_seconds, 1.0)
        self._poll = max(poll_seconds, 0.05)
        if startup_delay_seconds is None:
            startup_delay_seconds = get_settings().price_refresh_startup_delay_minutes * 60.0
        #: Short settle time after a (re)start before a catch-up cycle.
        self._startup_delay = min(max(startup_delay_seconds, 0.0), self._interval)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._pending: deque[tuple[str, str, int]] = deque()
        self._inflight: dict[str, int] = {}
        self._cycle_started_at: datetime | None = None
        self._last_cycle_completed_at: datetime | None = None
        self._last_successful_refresh: datetime | None = None
        self._next_scheduled_at: datetime | None = None
        self._total = 0
        self._completed = 0
        self._failed = 0
        self._submitted_jobs = 0
        self._successful_jobs = 0
        self._failed_jobs = 0
        self._skipped = 0
        #: "full" or "unpriced" while a cycle runs, else None.
        self._mode: str | None = None
        #: Full-cycle due time saved while an unpriced-only cycle runs, so
        #: that partial cycle never postpones the regular refresh.
        self._saved_next: datetime | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        with self._lock:
            self._next_scheduled_at = self._first_due_at()
        self._thread = threading.Thread(
            target=self._loop, name="yomiba-price-refresh", daemon=True
        )
        self._thread.start()
        logger.info("price refresh scheduler started (interval %.1fh)", self._interval / 3600)

    def _first_due_at(self) -> datetime:
        """When the first cycle after a (re)start should run.

        Restarts (e.g. every Railway redeploy) must not postpone refreshes by
        a full interval each time: the schedule is derived from persisted
        ImportRecord freshness. If the stalest catalog query last succeeded
        more than one interval ago (or never), a catch-up cycle starts after
        a short settle delay; otherwise the cycle is due when that query
        reaches one interval of age.
        """
        now = utcnow()
        try:
            with self._session_factory() as session:
                keys = {
                    normalized_query_key(title)
                    for (title,) in session.execute(
                        select(Series.title)
                        .join(CatalogSeries, CatalogSeries.series_id == Series.id)
                        .distinct()
                    )
                }
                keys.discard("")
                successes = {
                    r.normalized_query: aware_datetime(r.last_success_at)
                    for r in session.scalars(
                        select(ImportRecord).where(ImportRecord.normalized_query.in_(keys))
                    )
                } if keys else {}
        except Exception:  # noqa: BLE001 - fall back to the plain interval
            logger.exception("price refresh: could not derive first due time")
            return now + timedelta(seconds=self._interval)
        if not keys:
            return now + timedelta(seconds=self._interval)
        stalest = [successes.get(key) for key in keys]
        if any(value is None for value in stalest):
            wait = 0.0
        else:
            oldest = min(v for v in stalest if v is not None)
            wait = (oldest + timedelta(seconds=self._interval) - now).total_seconds()
        wait = min(max(wait, self._startup_delay), self._interval)
        return now + timedelta(seconds=wait)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                logger.warning("price refresh scheduler thread still alive after %.1fs", timeout)
            else:
                self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop.wait(self._poll):
            try:
                with self._lock:
                    due = self._cycle_started_at is not None or (
                        self._next_scheduled_at is not None
                        and utcnow() >= self._next_scheduled_at
                    )
                if due:
                    self.tick()
            except Exception:  # noqa: BLE001 - a bad cycle must not kill the loop
                logger.exception("price refresh tick failed")

    def _start_cycle(self, *, only_unpriced: bool = False) -> None:
        """Queue the catalog's queries. ``only_unpriced`` queues just the
        catalog series without any store listing and scrapes them even when
        their record is fresh (a zero-match import is a fresh success)."""
        now = utcnow()
        settings = get_settings()
        with self._session_factory() as session:
            stmt = (
                select(Series.id, Series.title)
                .join(CatalogSeries, CatalogSeries.series_id == Series.id)
                .distinct()
                .order_by(Series.id)
            )
            if only_unpriced:
                has_listing = (
                    select(Volume.id)
                    .join(StoreListing, StoreListing.volume_id == Volume.id)
                    .where(Volume.series_id == Series.id)
                    .exists()
                )
                stmt = stmt.where(~has_listing)
            catalog = session.execute(stmt).all()
            records = {
                r.normalized_query: r
                for r in session.scalars(select(ImportRecord)).all()
            }
        grouped: dict[str, tuple[str, int]] = {}
        for _, title in catalog:
            key = normalized_query_key(title)
            if not key:
                continue
            query, count = grouped.get(key, (title, 0))
            grouped[key] = (query, count + 1)

        self._pending.clear()
        self._inflight.clear()
        self._total = len(catalog)
        self._completed = 0
        self._failed = 0
        self._submitted_jobs = 0
        self._successful_jobs = 0
        self._failed_jobs = 0
        self._skipped = 0
        retry = timedelta(minutes=settings.import_failure_retry_minutes)
        freshness = timedelta(minutes=settings.import_freshness_ttl_minutes)
        for key, (query, weight) in grouped.items():
            record = records.get(key)
            attempt = aware_datetime(record.last_attempt_at) if record else None
            success = aware_datetime(record.last_success_at) if record else None
            if success and (self._last_successful_refresh is None or success > self._last_successful_refresh):
                self._last_successful_refresh = success
            if only_unpriced:
                self._pending.append((key, query, weight))
            # A recent manual success needs no immediate duplicate scrape.
            elif success and now - success < freshness:
                self._completed += weight
                self._skipped += weight
            elif record and record.status == "failed" and attempt and now - attempt < retry:
                # Retry on a later cycle; never leave FAILED permanently locked.
                self._failed += weight
                self._skipped += weight
            else:
                self._pending.append((key, query, weight))
        self._cycle_started_at = now
        self._mode = "unpriced" if only_unpriced else "full"
        self._saved_next = self._next_scheduled_at if only_unpriced else None
        self._next_scheduled_at = None
        logger.info("price refresh cycle started (%s): %d catalog series, %d queries",
                    self._mode, self._total, len(grouped))

    def _collect_finished(self) -> None:
        for key, weight in list(self._inflight.items()):
            if self._runner.is_running(key):
                continue
            record = self._runner.get_record(key)
            if record is not None and record.status in ("success", "partial"):
                self._completed += weight
                self._successful_jobs += weight
                success = aware_datetime(record.last_success_at)
                if success and (self._last_successful_refresh is None or success > self._last_successful_refresh):
                    self._last_successful_refresh = success
            else:
                self._failed += weight
                self._failed_jobs += weight
            del self._inflight[key]

    def tick(self) -> int:
        """Advance one cycle without blocking on scrapers; return submissions."""
        with self._lock:
            if self._cycle_started_at is None:
                self._start_cycle()
            self._collect_finished()
            submitted = 0
            while self._pending and self._runner.available_slots() > 0:
                key, query, weight = self._pending[0]
                if self._runner.submit(key, query, force=self._mode == "unpriced"):
                    self._inflight[key] = weight
                    self._pending.popleft()
                    submitted += 1
                    self._submitted_jobs += 1
                elif self._runner.is_running(key):
                    # An admin/manual import already covers the query.
                    self._inflight[key] = weight
                    self._pending.popleft()
                else:
                    break  # queue full or runner shutting down; keep pending
            if not self._pending and not self._inflight:
                ended = utcnow()
                duration = (ended - self._cycle_started_at).total_seconds()
                logger.info(
                    "price refresh cycle ended (%s): catalog=%d submitted=%d skipped=%d success=%d failed=%d duration=%.1fs",
                    self._mode, self._total, self._submitted_jobs, self._skipped,
                    self._successful_jobs, self._failed_jobs, duration,
                )
                self._cycle_started_at = None
                if self._mode == "unpriced":
                    # Keep the regular full-cycle schedule untouched.
                    self._next_scheduled_at = self._saved_next or ended + timedelta(seconds=self._interval)
                else:
                    self._last_cycle_completed_at = ended
                    self._next_scheduled_at = ended + timedelta(seconds=self._interval)
                self._mode = None
                self._saved_next = None
            return submitted

    def manual_refresh(self, *, only_unpriced: bool = False) -> bool:
        """Start a cycle now; return False if one is already active.
        ``only_unpriced`` refreshes just the catalog series with no price."""
        with self._lock:
            if self._cycle_started_at is not None:
                return False
            self._start_cycle(only_unpriced=only_unpriced)
            self.tick()
            return True

    def status(self) -> dict:
        with self._session_factory() as session:
            catalog_total = session.scalar(
                select(func.count(func.distinct(CatalogSeries.series_id)))
            ) or 0
        with self._lock:
            active = self._runner.active_keys()
            running = sum(weight for key, weight in self._inflight.items() if key in active)
            queued = sum(weight for key, weight in self._inflight.items() if key not in active)
            return {
                "enabled": self.is_running,
                "interval_hours": self._interval / 3600,
                "worker_concurrency": self._runner.worker_count,
                "queue_capacity": self._runner.queue_capacity,
                "queue_size": self._runner.queued_count,
                "queued": queued,
                "running": running,
                "completed": self._completed,
                "failed": self._failed,
                "pending": sum(weight for _, _, weight in self._pending),
                "total_catalog_series": catalog_total,
                "current_cycle_total": self._total,
                "current_cycle_started_at": self._cycle_started_at,
                "current_cycle_mode": self._mode,
                "last_cycle_completed_at": self._last_cycle_completed_at,
                "last_successful_refresh": self._last_successful_refresh,
                "next_scheduled_refresh": self._next_scheduled_at,
            }
