"""Background import runner.

Runs ``ImportService`` jobs off the request path using plain daemon threads
(no Redis / Celery) so that ``/search`` can answer from the database
immediately while scraping happens in the background.

Design goals:

* **Per-query dedup** — at most one job at a time for a normalized query,
  so "Berserk", "BERSERK" and "berserk" never run simultaneous imports.
* **Shared import lock** — the runner owns an :class:`ImportLock`; the
  manual ``POST /import`` route acquires the same lock (non-blocking,
  409 on conflict). Two imports for one normalized query can therefore
  never run simultaneously, no matter which path triggered them.
* **Bounded concurrency** — a small semaphore caps how many jobs run at once.
* **Durable state** — every job updates the ``ImportRecord`` row for its
  query (freshness + last outcome), which survives restarts.
* **Job-ready** — ``submit(key, query)`` is the only entry point a future
  scheduler needs to call; the runner is storage-agnostic beyond a session
  factory.

Scraper failures never delete catalog data: jobs only upsert through
``ImportService``; a crashing job just records ``status="failed"``.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import ImportRecord
from ..normalization import normalize_text
from ..scrapers.registry import get_scrapers
from ..utils import utcnow
from .import_service import ImportReport, ImportService

logger = logging.getLogger("yomiba.import.background")

ScraperFactory = Callable[[list[str] | None], list]

#: Shared import-lock key used as a process-wide "catalog write gate".
#: The Mangakol catalog sync (routes/catalog.py) holds it for the whole
#: run, and every background import job waits on it before touching the
#: database — so imports never create or merge publisher rows under a
#: running catalog sync (and the sync never starts while an import runs).
SYNC_GATE_KEY = "__catalog_sync__"


def normalized_query_key(query: str) -> str:
    """Dedup key for imports: the normalized query ("BERSERK" -> "berserk")."""
    return normalize_text(query)


def aware_datetime(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; force UTC so comparisons are safe."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def is_fresh_record(record: ImportRecord | None, settings=None) -> bool:
    """True when the query's last successful import is within the TTL."""
    if record is None or record.last_success_at is None:
        return False
    settings = settings or get_settings()
    last_success_at = aware_datetime(record.last_success_at)
    return (utcnow() - last_success_at) <= timedelta(
        minutes=settings.import_freshness_ttl_minutes
    )


class ImportLock:
    """Process-wide, per-normalized-query import mutex.

    Shared by BOTH import paths (manual ``POST /import`` and background
    jobs) so that two imports for the same normalized query can never run
    simultaneously. In-memory on purpose: the app runs as a single process,
    and an in-memory lock cannot outlive its owner (a crash releases it).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._holders: dict[str, str] = {}

    def acquire(self, key: str, holder: str, timeout: float | None = None) -> bool:
        """Acquire ``key`` for ``holder``; block up to ``timeout`` seconds.

        ``timeout=None`` waits forever. Returns False when the timeout
        expires before the lock is free.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                current = self._holders.get(key)
                if current is None:
                    self._holders[key] = holder
                    return True
                if current == holder:  # re-entrancy safety
                    return True
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            time.sleep(min(0.05, remaining if remaining is not None else 0.05))

    def release(self, key: str, holder: str) -> None:
        with self._lock:
            if self._holders.get(key) == holder:
                del self._holders[key]

    def holder(self, key: str) -> str | None:
        with self._lock:
            return self._holders.get(key)


def upsert_running_record(
    session: Session, key: str, query: str
) -> ImportRecord:
    """Mark a query's record as running (keeps ``last_success_at``)."""
    record = session.scalar(
        select(ImportRecord).where(ImportRecord.normalized_query == key)
    )
    if record is None:
        record = ImportRecord(normalized_query=key)
        session.add(record)
    record.last_query = query
    record.status = "running"
    record.last_attempt_at = utcnow()
    session.commit()
    return record


def record_import_result(
    session: Session, key: str, report: ImportReport
) -> ImportRecord:
    """Upsert the ``ImportRecord`` for a finished import.

    Used by both the background runner and the synchronous ``/import``
    endpoint so every import (whoever triggered it) refreshes freshness.
    """
    stores_ok = sum(1 for s in report.stores if s.error is None)
    stores_failed = len(report.stores) - stores_ok
    if stores_failed == 0:
        status = "success"
    elif stores_ok == 0:
        status = "failed"
    else:
        status = "partial"
    now = utcnow()

    record = session.scalar(
        select(ImportRecord).where(ImportRecord.normalized_query == key)
    )
    if record is None:
        record = ImportRecord(normalized_query=key)
        session.add(record)
    record.last_query = report.query
    record.last_attempt_at = now
    record.status = status
    record.stores_ok = stores_ok
    record.stores_failed = stores_failed
    record.results_found = sum(s.results_found for s in report.stores)
    record.created = report.total_created
    record.updated = report.total_updated
    record.error = (
        " | ".join(f"{s.store_code}: {s.error}" for s in report.stores if s.error)
        or None
    )
    if stores_ok > 0:
        record.last_success_at = now
    session.commit()
    return record


class BackgroundImportRunner:
    """Schedules and tracks per-query background imports.

    ``session_factory`` must yield a fresh ``Session`` per call — the runner
    opens one per job, because jobs outlive request sessions.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        scraper_factory: ScraperFactory | None = None,
        store_ids: list[str] | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._scraper_factory = scraper_factory or get_scrapers
        self._store_ids = store_ids
        settings = get_settings()
        self._semaphore = threading.BoundedSemaphore(
            max_concurrent or settings.import_max_concurrent_jobs
        )
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self._threads: dict[str, threading.Thread] = {}
        #: Shared with the manual /import route (see routes/import_.py).
        self.lock = ImportLock()

    # -- shared per-query import lock --------------------------------------------
    def acquire_import_lock(
        self, key: str, holder: str, timeout: float | None = None
    ) -> bool:
        return self.lock.acquire(key, holder, timeout)

    def release_import_lock(self, key: str, holder: str) -> None:
        self.lock.release(key, holder)

    def import_lock_holder(self, key: str) -> str | None:
        return self.lock.holder(key)

    # -- scheduling -------------------------------------------------------------
    def is_running(self, key: str) -> bool:
        with self._lock:
            return key in self._running

    def running_queries(self) -> list[str]:
        with self._lock:
            return sorted(self._running)

    def submit(self, key: str, query: str) -> bool:
        """Start a background import for ``key`` unless one is already running.

        Returns ``True`` when a job was started, ``False`` when an existing
        job already covers this normalized query.
        """
        with self._lock:
            if key in self._running:
                return False
            self._running.add(key)
        thread = threading.Thread(
            target=self._guarded,
            args=(key, query),
            name=f"yomiba-import-{key[:20]}",
            daemon=True,
        )
        with self._lock:
            self._threads[key] = thread
        thread.start()
        return True

    # -- introspection (tests / future admin UI) ----------------------------------
    def get_record(self, key: str) -> ImportRecord | None:
        session = self._session_factory()
        try:
            return session.scalar(
                select(ImportRecord).where(ImportRecord.normalized_query == key)
            )
        finally:
            session.close()

    def wait_for(self, key: str, timeout: float = 10.0) -> bool:
        """Block until the job for ``key`` finishes (test helper)."""
        with self._lock:
            thread = self._threads.get(key)
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def shutdown(self, timeout: float = 10.0) -> None:
        """Wait for in-flight jobs (lifespan shutdown)."""
        with self._lock:
            threads = list(self._threads.values())
            self._threads.clear()
            self._running.clear()
        for thread in threads:
            thread.join(timeout)

    def _record_gate_timeout(self, key: str, query: str) -> None:
        """Mark the job as skipped (catalog sync held the write gate)."""
        session = self._session_factory()
        try:
            record = session.scalar(
                select(ImportRecord).where(ImportRecord.normalized_query == key)
            )
            if record is None:
                record = ImportRecord(normalized_query=key)
                session.add(record)
            record.last_query = query
            record.last_attempt_at = utcnow()
            record.status = "skipped"
            record.error = "atlandı: katalog senkronu çalışıyor"
            session.commit()
        except Exception:  # noqa: BLE001 - bookkeeping must not crash the job
            logger.exception("could not record skipped import for %r", key)
            session.rollback()
        finally:
            session.close()

    # -- job execution ------------------------------------------------------------
    def _guarded(self, key: str, query: str) -> None:
        try:
            with self._semaphore:
                # The shared lock may be held by a manual /import; wait for
                # it instead of scraping in parallel with it.
                if not self.lock.acquire(
                    key, "background", timeout=get_settings().import_lock_timeout_seconds
                ):
                    logger.warning(
                        "background import for %r skipped: import lock still "
                        "held by %r",
                        key,
                        self.lock.holder(key),
                    )
                    return
                # The catalog write gate is held by a running catalog sync;
                # wait for it so publisher rows cannot change mid-sync.
                if not self.lock.acquire(
                    SYNC_GATE_KEY,
                    "background",
                    timeout=get_settings().catalog_gate_timeout_seconds,
                ):
                    logger.warning(
                        "background import for %r skipped: catalog sync still "
                        "running after waiting %ss",
                        key,
                        get_settings().catalog_gate_timeout_seconds,
                    )
                    self._record_gate_timeout(key, query)
                    return
                try:
                    self._execute(key, query)
                finally:
                    self.lock.release(SYNC_GATE_KEY, "background")
                    self.lock.release(key, "background")
        except Exception:  # noqa: BLE001 - the job must die quietly, logged
            logger.exception("background import job for %r crashed", query)
        finally:
            with self._lock:
                self._running.discard(key)
                self._threads.pop(key, None)

    def _execute(self, key: str, query: str) -> None:
        session = self._session_factory()
        try:
            # --- fresh check + mark running -------------------------------------
            try:
                # A manual /import (or another fresh job) may have finished
                # while we waited for the lock — don't scrape what is already
                # fresh.
                record = session.scalar(
                    select(ImportRecord).where(ImportRecord.normalized_query == key)
                )
                if is_fresh_record(record):
                    logger.info(
                        "background import for %r skipped: catalog already fresh",
                        query,
                    )
                    return
                upsert_running_record(session, key, query)
            except Exception:
                # A job that dies before it starts must still leave a trace:
                # without a failed record the query silently drops out of the
                # warmup / refresh cycle (2026-09-14 pool-exhaustion incident:
                # 461 warmup jobs vanished this way). Best effort — if even
                # the failure record cannot be written, the log line above
                # is all we get.
                logger.exception(
                    "could not mark background import %r as running", key
                )
                session.rollback()
                try:
                    upsert_failed_record(
                        session, key, query, "içe aktarma başlatılamadı (DB hatası)"
                    )
                except Exception:  # pragma: no cover - DB already broken
                    logger.exception("could not record startup failure for %r", key)
                return
            # --- scrape + import --------------------------------------------------
            try:
                service = ImportService(
                    session, scrapers=self._scraper_factory(self._store_ids)
                )
                report = service.run_import(query)
                record = record_import_result(session, key, report)
                logger.info(
                    "background import for %r finished: status=%s ok=%d failed=%d "
                    "found=%d created=%d updated=%d",
                    query,
                    record.status,
                    record.stores_ok,
                    record.stores_failed,
                    record.results_found,
                    record.created,
                    record.updated,
                )
            except Exception as exc:  # noqa: BLE001 - isolation by design
                logger.exception("background import for %r failed", query)
                session.rollback()
                try:
                    upsert_failed_record(session, key, query, str(exc))
                except Exception:  # pragma: no cover - DB already broken
                    logger.exception("could not record failure for %r", key)
        finally:
            # Covers BOTH early returns (fresh-skip / startup failure): a
            # session dropped without close leaks its pool connection until
            # garbage collection — never acceptable with a bounded pool.
            session.close()


def upsert_failed_record(session: Session, key: str, query: str, error: str) -> None:
    """Record a crashed import attempt (keeps ``last_success_at``)."""
    record = session.scalar(
        select(ImportRecord).where(ImportRecord.normalized_query == key)
    )
    if record is None:
        record = ImportRecord(normalized_query=key)
        session.add(record)
    record.last_query = query
    record.status = "failed"
    record.last_attempt_at = utcnow()
    record.error = error[:2000]
    session.commit()
