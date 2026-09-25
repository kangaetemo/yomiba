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

from fastapi import APIRouter, HTTPException, Request

from ..database import SessionLocal
from ..services.background_import import SYNC_GATE_KEY
from ..services.catalog_sync import CatalogSyncService

logger = logging.getLogger("yomiba.catalog.routes")

router = APIRouter(tags=["catalog"])

_state_lock = threading.Lock()
_running = False
_last: dict | None = None


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
        "errors": (_last.get("errors") or [])[:10],
    }


def _run_sync(runner) -> None:
    global _running, _last
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
            "errors": report.errors,
        }
        logger.info(
            "catalog sync finished: %s (scanned=%s failed=%s "
            "series + %s / merged %s, volumes +%s, pubs merged %s, "
            "series absorbed %s)",
            _last["status"], report.manga_scanned, report.manga_failed,
            report.series_created, report.series_merged, report.volumes_added,
            report.publishers_merged, report.series_absorbed,
        )
    except Exception as exc:  # noqa: BLE001 - never leave the flag stuck
        logger.exception("catalog sync crashed")
        _last = {"status": "failed", "finished_at": None, "error": f"{type(exc).__name__}: {exc}"}
    finally:
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
    global _running
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
    threading.Thread(
        target=_run_sync, args=(runner,), name="catalog-sync", daemon=True
    ).start()
    return "started"


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
