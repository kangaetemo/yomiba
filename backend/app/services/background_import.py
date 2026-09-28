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
import queue
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import CatalogSeries, ImportRecord, Series, StoreListing, Volume
from ..normalization import normalize_text
from ..scrapers.registry import get_scrapers
from ..utils import utcnow
from .import_service import _SUBTITLE_SEPARATOR_RE, ImportReport, ImportService

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




def fallback_queries(session: Session, query: str) -> list[str]:
    """Shorter/alternative store queries for a catalog title that matched
    nothing: the title before each subtitle separator (longest first),
    then the catalog's original (foreign) title. Store searches often
    return nothing for the full subtitled title. Matching still runs
    against the catalog, so a broader query can never create series or
    volumes.
    """
    candidates: list[str] = []
    # "Kamisama Kiss -Tanrılık Görevine Başladım" -> "Kamisama Kiss",
    # "Zom 100: Ölülerin Yapılacaklar Listesi" -> "Zom 100": the same
    # separators the importer's title-without-subtitle match uses.
    for sep in reversed(list(_SUBTITLE_SEPARATOR_RE.finditer(query))):
        head = query[: sep.start()].strip()
        if len(head) >= 3:
            candidates.append(head)
    original = session.scalar(
        select(Series.original_title)
        .where(Series.title == query, Series.original_title.is_not(None))
        .limit(1)
    )
    if original:
        candidates.append(original)
    seen = {normalize_text(query)}
    out: list[str] = []
    for candidate in candidates:
        key = normalize_text(candidate)
        if key and key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


def catalog_series_unpriced(session: Session, query: str) -> bool:
    """True when ``query`` is a catalog series title and none of its
    catalog editions has a store listing yet. A query that merely matched
    ANOTHER series' products ("Oşi No Ko: Seçtiğim Yıldız" pulling in
    unrelated listings) still leaves its own series unpriced."""
    catalog = select(CatalogSeries.series_id).distinct()
    series_ids = list(session.scalars(
        select(Series.id).where(Series.title == query, Series.id.in_(catalog))
    ))
    if not series_ids:
        return False
    listed = session.scalar(
        select(StoreListing.id)
        .join(Volume, Volume.id == StoreListing.volume_id)
        .where(Volume.series_id.in_(series_ids))
        .limit(1)
    )
    return listed is None


def merge_reports(primary: ImportReport, extra: ImportReport) -> None:
    """Fold a fallback-query report into ``primary`` per store, so the
    ImportRecord counts stores once and sums what every query found."""
    by_code = {s.store_code: s for s in primary.stores}
    for s in extra.stores:
        target = by_code.get(s.store_code)
        if target is None:
            primary.stores.append(s)
            by_code[s.store_code] = s
            continue
        target.results_found += s.results_found
        target.created += s.created
        target.updated += s.updated
        target.skipped += s.skipped
        target.errors += s.errors
        for reason, n in s.reasons.items():
            target.reasons[reason] = target.reasons.get(reason, 0) + n
        # A store that answered on any query is not a failed store.
        if target.error is not None and s.error is None:
            target.error = None
    primary.finished_at = extra.finished_at or primary.finished_at


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
        self._shared_holders: dict[str, set[str]] = {}
        #: Announced exclusive intent per key (writer preference): while a
        #: catalog sync waits for the gate, NEW shared holders must queue
        #: behind it; otherwise a continuously fed price-refresh queue keeps
        #: the shared gate held forever and the sync starves.
        self._exclusive_intent: dict[str, int] = {}

    def acquire(
        self, key: str, holder: str, timeout: float | None = None, *, shared: bool = False
    ) -> bool:
        """Acquire ``key`` for ``holder``; block up to ``timeout`` seconds.

        ``timeout=None`` waits forever. Returns False when the timeout
        expires before the lock is free.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                current = self._holders.get(key)
                shared_holders = self._shared_holders.get(key, set())
                if shared and current is None and not self._exclusive_intent.get(key):
                    self._shared_holders.setdefault(key, set()).add(holder)
                    return True
                if not shared and current is None and not shared_holders:
                    self._holders[key] = holder
                    return True
                if not shared and current == holder:  # re-entrancy safety
                    return True
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            time.sleep(min(0.05, remaining if remaining is not None else 0.05))

    def release(self, key: str, holder: str) -> None:
        with self._lock:
            if self._holders.get(key) == holder:
                del self._holders[key]
            shared_holders = self._shared_holders.get(key)
            if shared_holders is not None:
                shared_holders.discard(holder)
                if not shared_holders:
                    del self._shared_holders[key]

    def set_exclusive_intent(self, key: str, active: bool) -> None:
        """Announce (or withdraw) that an exclusive holder is waiting for
        ``key``. Existing shared holders finish normally; new shared
        acquisitions wait until the exclusive holder has come and gone."""
        with self._lock:
            count = self._exclusive_intent.get(key, 0) + (1 if active else -1)
            if count > 0:
                self._exclusive_intent[key] = count
            else:
                self._exclusive_intent.pop(key, None)

    def holder(self, key: str) -> str | None:
        with self._lock:
            return self._holders.get(key) or next(iter(self._shared_holders.get(key, ())), None)


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
    record.reasons = {
        s.store_code: dict(s.reasons) for s in report.stores if s.reasons
    } or None
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
        queue_capacity: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._scraper_factory = scraper_factory or get_scrapers
        self._store_ids = store_ids
        settings = get_settings()
        self._max_workers = max(1, max_concurrent or settings.import_max_concurrent_jobs)
        self._queue_capacity = max(1, queue_capacity or settings.import_queue_capacity)
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=self._queue_capacity)
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self._active: set[str] = set()
        self._completion: dict[str, threading.Event] = {}
        #: Queued keys that must scrape even when their record is fresh.
        self._forced: set[str] = set()
        self._workers: list[threading.Thread] = []
        self._closing = False
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

    @property
    def worker_count(self) -> int:
        return self._max_workers

    @property
    def queue_capacity(self) -> int:
        return self._queue_capacity

    @property
    def queued_count(self) -> int:
        return self._queue.qsize()

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def available_slots(self) -> int:
        return max(0, self._queue_capacity - self._queue.qsize())

    def active_keys(self) -> set[str]:
        with self._lock:
            return set(self._active)

    def submit(self, key: str, query: str, *, force: bool = False) -> bool:
        """Start a background import for ``key`` unless one is already running.

        Returns ``True`` when a job was started, ``False`` when an existing
        job already covers this normalized query. ``force`` scrapes even when
        the record is fresh: an unpriced series' zero-match import still
        counts as a fresh success.
        """
        with self._lock:
            if self._closing or key in self._running:
                return False
            try:
                self._queue.put_nowait((key, query))
            except queue.Full:
                logger.warning("import queue full (capacity=%d); submission rejected", self._queue_capacity)
                return False
            if self._queue.qsize() == max(1, (self._queue_capacity * 4 + 4) // 5):
                logger.warning("import queue reached 80%% capacity (%d/%d)", self._queue.qsize(), self._queue_capacity)
            self._running.add(key)
            if force:
                self._forced.add(key)
            self._completion[key] = threading.Event()
            if not self._workers:
                for index in range(self._max_workers):
                    worker = threading.Thread(
                        target=self._worker_loop,
                        name=f"yomiba-import-worker-{index + 1}",
                        daemon=True,
                    )
                    self._workers.append(worker)
                    worker.start()
        return True

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if self._closing and self._queue.empty():
                    return
            try:
                key, query = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            with self._lock:
                self._active.add(key)
            try:
                self._guarded(key, query)
            finally:
                with self._lock:
                    self._active.discard(key)
                    self._running.discard(key)
                    self._forced.discard(key)
                    done = self._completion.pop(key, None)
                    if done is not None:
                        done.set()
                self._queue.task_done()

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
            done = self._completion.get(key)
        if done is None:
            return True
        return done.wait(timeout)

    def shutdown(self, timeout: float = 10.0) -> None:
        """Stop accepting work, discard queued jobs, and join active workers."""
        with self._lock:
            self._closing = True
            workers = list(self._workers)
            discarded = 0
            while True:
                try:
                    key, _ = self._queue.get_nowait()
                except queue.Empty:
                    break
                self._running.discard(key)
                discarded += 1
                done = self._completion.pop(key, None)
                if done is not None:
                    done.set()
                self._queue.task_done()
        deadline = time.monotonic() + timeout
        for worker in workers:
            worker.join(max(0.0, deadline - time.monotonic()))
        alive = sum(worker.is_alive() for worker in workers)
        logger.info("import runner shutdown: discarded=%d active=%d", discarded, self.active_count)
        if alive:
            logger.warning("import runner shutdown timed out with %d active worker threads", alive)

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
            query_holder = "background"
            gate_holder = f"background-{uuid4().hex}"
            # The shared lock may be held by a manual /import; wait for
            # it instead of scraping in parallel with it.
            if not self.lock.acquire(
                key, query_holder, timeout=get_settings().import_lock_timeout_seconds
            ):
                logger.warning(
                    "background import for %r skipped: import lock still "
                    "held by %r",
                    key,
                    self.lock.holder(key),
                )
                return
            try:
                # Store imports share the gate with each other, but a
                # catalog sync or manual import requires exclusive access.
                # Each job owns its own share until its work is finished.
                if not self.lock.acquire(
                    SYNC_GATE_KEY,
                    gate_holder,
                    timeout=get_settings().catalog_gate_timeout_seconds,
                    shared=True,
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
                    self.lock.release(SYNC_GATE_KEY, gate_holder)
            finally:
                self.lock.release(key, query_holder)
        except Exception:  # noqa: BLE001 - the job must die quietly, logged
            logger.exception("background import job for %r crashed", query)

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
                with self._lock:
                    forced = key in self._forced
                if not forced and is_fresh_record(record):
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
                if (
                    report.total_created + report.total_updated == 0
                    or catalog_series_unpriced(session, query)
                ) and any(s.error is None for s in report.stores):
                    for alt in fallback_queries(session, query):
                        logger.info(
                            "background import for %r matched nothing; "
                            "retrying with %r",
                            query,
                            alt,
                        )
                        service = ImportService(
                            session, scrapers=self._scraper_factory(self._store_ids)
                        )
                        merge_reports(report, service.run_import(alt))
                        if not catalog_series_unpriced(session, query) and (
                            report.total_created + report.total_updated > 0
                        ):
                            break
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
