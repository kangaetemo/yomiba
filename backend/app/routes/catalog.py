"""Catalog sync endpoints (operational, no auth — same as /import).

``POST /catalog/sync``  -> starts a background Mangakol catalog sync
                           (445 manga x detail pages; several minutes).
                           409 when a sync is already running, or when a
                           store import is in flight (the two share the
                           catalog write gate so publisher rows cannot
                           change under a running sync).
``GET  /catalog/sync/status`` -> running flag + last run summary.

Route handlers stay thin: the merge strategy and all DB writes live in
``app.services.catalog_sync``; the scraper stays DB-independent.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..auth import require_admin
from ..services.background_import import SYNC_GATE_KEY
from ..services import isbn_conflict_fix as isbn_fix
from ..services.catalog_sync import CatalogSyncService

logger = logging.getLogger("yomiba.catalog.routes")

router = APIRouter(tags=["catalog"], dependencies=[Depends(require_admin)])

_state_lock = threading.Lock()
_running = False
_last: dict | None = None
_sync_thread: threading.Thread | None = None


def _last_summary() -> dict | None:
    if _last is None:
        return None
    return {
        "status": _last["status"],
        "finished_at": _last.get("finished_at"),
        "manga_total": _last.get("manga_total"),
        "manga_failed": _last.get("manga_failed"),
        "series_created": _last.get("series_created"),
        "series_merged": _last.get("series_merged"),
        "volumes_added": _last.get("volumes_added"),
        "covers_backfilled": _last.get("covers_backfilled"),
        "publishers_merged": _last.get("publishers_merged"),
        "series_absorbed": _last.get("series_absorbed"),
        "volumes_merged": _last.get("volumes_merged"),
        "isbn_pages": _last.get("isbn_pages"),
        "isbns_added": _last.get("isbns_added"),
        "isbn_conflicts": _last.get("isbn_conflicts"),
        "isbn_conflict_details": _last.get("isbn_conflict_details") or [],
        "isbn_phantoms_merged": _last.get("isbn_phantoms_merged"),
        "errors": (_last.get("errors") or [])[:10],
    }


def _run_sync(runner) -> None:
    global _running, _last
    started = time.monotonic()
    try:
        with SessionLocal() as session:
            report = CatalogSyncService(session).sync()
        _last = {
            "status": "success" if report.ok else "failed",
            "finished_at": report.started_at.isoformat(),
            "manga_total": report.manga_total,
            "manga_failed": report.manga_failed,
            "series_created": report.series_created,
            "series_merged": report.series_merged,
            "volumes_added": report.volumes_added,
            "covers_backfilled": report.covers_backfilled,
            "publishers_merged": report.publishers_merged,
            "series_absorbed": report.series_absorbed,
            "volumes_merged": report.volumes_merged,
            "isbn_pages": report.isbn_pages,
            "isbns_added": report.isbns_added,
            "isbn_conflicts": report.isbn_conflicts,
            "isbn_conflict_details": report.isbn_conflict_details,
            "isbn_phantoms_merged": report.isbn_phantoms_merged,
            "errors": report.errors,
        }
        logger.info(
            "catalog sync finished: %s (scanned=%s failed=%s "
            "series + %s / merged %s, volumes +%s, pubs merged %s, "
            "series absorbed %s, isbn pages %s / added %s / conflicts %s)",
            _last["status"], report.manga_scanned, report.manga_failed,
            report.series_created, report.series_merged, report.volumes_added,
            report.publishers_merged, report.series_absorbed,
            report.isbn_pages, report.isbns_added, report.isbn_conflicts,
        )
    except Exception as exc:  # noqa: BLE001 - never leave the flag stuck
        logger.exception("catalog sync crashed")
        _last = {"status": "failed", "finished_at": None, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        logger.info("catalog sync ended after %.1fs", time.monotonic() - started)
        runner.release_import_lock(SYNC_GATE_KEY, "catalog")
        with _state_lock:
            _running = False


def try_start_sync(runner) -> str:
    """Single start point for catalog syncs (manual endpoint AND scheduler).

    Returns ``"started"`` when a sync thread was launched,
    ``"already_running"`` when a sync is already in flight, or
    ``"gate_held"`` when a store import currently holds the shared
    catalog write gate (the sync refuses rather than race it).
    """
    global _running, _sync_thread
    with _state_lock:
        if _running:
            return "already_running"
    # Take the shared catalog write gate. A background import holds it
    # for the duration of its run; we refuse rather than race it.
    if not runner.acquire_import_lock(SYNC_GATE_KEY, "catalog", timeout=0):
        return "gate_held"
    try:
        with _state_lock:
            _running = True
    except Exception:
        runner.release_import_lock(SYNC_GATE_KEY, "catalog")
        raise
    try:
        thread = threading.Thread(
            target=_run_sync, args=(runner,), name="catalog-sync", daemon=True
        )
        with _state_lock:
            _sync_thread = thread
        thread.start()
        logger.info("catalog sync started")
    except Exception:
        with _state_lock:
            _running = False
            _sync_thread = None
        runner.release_import_lock(SYNC_GATE_KEY, "catalog")
        raise
    return "started"


def wait_for_active_sync(timeout: float) -> bool:
    """Bounded shutdown wait for the actual catalog sync worker, if any."""
    with _state_lock:
        thread = _sync_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout)
    return thread is None or not thread.is_alive()


@router.post("/catalog/sync", status_code=202)
def start_catalog_sync(request: Request) -> dict:
    result = try_start_sync(request.app.state.import_runner)
    if result == "already_running":
        raise HTTPException(
            status_code=409,
            detail="Zaten bir katalog senkronu çalışıyor. "
                   "Durumu GET /api/catalog/sync/status ile kontrol edin.",
        )
    if result == "gate_held":
        raise HTTPException(
            status_code=409,
            detail="Bir mağaza içe aktarması çalışıyor. Katalog senkronunu "
                   "birkaç dakika sonra tekrar deneyin.",
        )
    return {"status": "started"}


@router.get("/catalog/sync/status")
def catalog_sync_status() -> dict:
    with _state_lock:
        return {"running": _running, "last": _last_summary()}


@router.post("/catalog/isbn-fix")
def isbn_conflict_fix(apply: bool = False, session: Session = Depends(get_db)) -> dict:
    """Admin: preview (default) or apply the known ISBN conflict fixes
    (app.services.isbn_conflict_fix) without shell access. Refused while a
    catalog sync runs; the fix itself re-checks the DB inside its own
    transaction and backs the SQLite file up before writing."""
    with _state_lock:
        if _running:
            raise HTTPException(status_code=409, detail="Katalog senkronu çalışıyor; bitince tekrar deneyin.")
    url = session.get_bind().url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise HTTPException(status_code=400, detail="ISBN düzeltmesi yalnızca dosya tabanlı SQLite ile çalışır.")
    session.close()  # release the request's connection before the fix locks the file
    try:
        return isbn_fix.run(Path(url.database).resolve(), apply=apply)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/catalog/covers")
def cover_status(request: Request, session: Session = Depends(get_db)) -> dict:
    """Admin: self-hosted cover progress (see services/covers.py)."""
    from sqlalchemy import func, select

    from ..models import CatalogSeries, Volume

    catalog = Volume.series_id.in_(select(CatalogSeries.series_id))
    real = Volume.volume_number >= 0
    total = session.scalar(select(func.count()).where(catalog, real)) or 0
    stored = session.scalar(select(func.count()).where(catalog, real, Volume.cover_key.isnot(None))) or 0
    worker = getattr(request.app.state, "cover_worker", None)
    return {
        "enabled": worker is not None,
        "running": bool(worker and worker.running),
        "total": total,
        "stored": stored,
        "last": worker.last if worker else None,
    }


@router.post("/catalog/covers/fetch", status_code=202)
def start_cover_fetch(request: Request) -> dict:
    """Admin: run a cover pass now instead of waiting for the next one."""
    worker = getattr(request.app.state, "cover_worker", None)
    if worker is None:
        raise HTTPException(status_code=503, detail="Kapak indirici kapalı.")
    if not worker.trigger():
        raise HTTPException(status_code=409, detail="Kapak indirme zaten çalışıyor.")
    return {"status": "started"}


def _foreign_job(request: Request, session: Session):
    from sqlalchemy.orm import sessionmaker

    from ..services.foreign_editions import ForeignEditionJob

    job = getattr(request.app.state, "foreign_job", None)
    if job is None:
        job = ForeignEditionJob(sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False))
        request.app.state.foreign_job = job
    return job


@router.get("/catalog/foreign-editions")
def foreign_editions_status(request: Request, session: Session = Depends(get_db)) -> dict:
    """Admin: state + reviewed plan of the foreign-edition clean-up."""
    return _foreign_job(request, session).status()


@router.post("/catalog/foreign-editions/scan", status_code=202)
def foreign_editions_scan(request: Request, session: Session = Depends(get_db)) -> dict:
    """Admin: start the background scan (product pages are read)."""
    if not _foreign_job(request, session).start_scan():
        raise HTTPException(status_code=409, detail="Tarama ya da uygulama zaten çalışıyor.")
    return {"status": "scanning"}


@router.post("/catalog/foreign-editions/apply")
def foreign_editions_apply(request: Request, session: Session = Depends(get_db)) -> dict:
    """Admin: remove the proven foreign-edition listings of the last scan."""
    job = _foreign_job(request, session)
    url = session.get_bind().url
    db_path = (Path(url.database).resolve()
               if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:" else None)
    session.close()
    try:
        return job.apply(db_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _probe_job(request: Request):
    from ..services.store_probe import StoreProbeJob

    job = getattr(request.app.state, "store_probe_job", None)
    if job is None:
        job = StoreProbeJob()
        request.app.state.store_probe_job = job
    return job


@router.get("/catalog/store-probe")
def store_probe_status(request: Request) -> dict:
    """Admin: last store access test (from this server) and its progress."""
    return _probe_job(request).status()


@router.post("/catalog/store-probe/run", status_code=202)
def store_probe_run(request: Request) -> dict:
    """Admin: fetch every store / candidate once from this server."""
    if not _probe_job(request).start():
        raise HTTPException(status_code=409, detail="Erişim testi zaten çalışıyor.")
    return {"status": "running"}
