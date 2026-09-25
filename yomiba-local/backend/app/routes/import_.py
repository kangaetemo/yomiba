"""POST /import — trigger a scrape + import for a query.

Operational entry point of the ImportService. Runs synchronously (the caller
waits for the report) but shares the SAME per-query concurrency guard as
background imports: while any import for a normalized query is running —
from either path — a second one is rejected with 409. It also takes the
shared catalog write gate (non-blocking, 409 when held by a running catalog
sync or background store import) so publisher rows can never change under
a running sync, no matter which path triggered the import. Route handlers
stay thin: all logic lives in the services.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import CatalogSeries, ImportRecord, Series, StoreListing, Volume
from ..schemas.import_ import (
    ImportRecordOut,
    ImportReportOut,
    ImportRequest,
    ImportStoreOut,
)
from ..services.background_import import (
    SYNC_GATE_KEY,
    normalized_query_key,
    record_import_result,
    upsert_failed_record,
    upsert_running_record,
)
from ..services.import_service import ImportService
from ..utils import utcnow

logger = logging.getLogger("yomiba.import")

router = APIRouter(tags=["import"])


@router.get("/import/records", response_model=list[ImportRecordOut])
def list_import_records(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> list[ImportRecordOut]:
    """Recent import attempts, most recent first (operational, no auth)."""
    rows = session.scalars(
        select(ImportRecord)
        .order_by(
            ImportRecord.last_attempt_at.desc().nullslast(),
            ImportRecord.id.desc(),
        )
        .limit(limit)
    ).all()
    return [
        ImportRecordOut(
            normalized_query=r.normalized_query,
            last_query=r.last_query,
            status=r.status,
            last_attempt_at=r.last_attempt_at,
            last_success_at=r.last_success_at,
            stores_ok=r.stores_ok,
            stores_failed=r.stores_failed,
            results_found=r.results_found,
            created=r.created,
            updated=r.updated,
            error=r.error,
        )
        for r in rows
    ]


@router.get("/import/coverage")
def import_coverage(session: Session = Depends(get_db)) -> dict:
    """Read-only shelf-health summary for the admin panel (no auth).

    Answers "how warmed up is the shelf": how many catalog series have at
    least one price listing, how fresh the import records are, and how the
    records break down by status. All counts are derived from the same rows
    the search flow serves, so this never triggers a scrape.
    """
    settings = get_settings()
    ttl_cutoff = utcnow() - timedelta(
        minutes=settings.import_freshness_ttl_minutes
    )

    catalog_total = (
        session.scalar(select(func.count(func.distinct(CatalogSeries.series_id)))) or 0
    )
    with_listings = (
        session.scalar(
            select(func.count(func.distinct(Volume.series_id)))
            .select_from(Volume)
            .join(CatalogSeries, CatalogSeries.series_id == Volume.series_id)
            .join(StoreListing, StoreListing.volume_id == Volume.id)
        )
        or 0
    )
    listings_total = session.scalar(select(func.count(StoreListing.id))) or 0
    records_total = session.scalar(select(func.count(ImportRecord.id))) or 0
    by_status: dict[str, int] = {}
    for status in session.scalars(select(ImportRecord.status)).all():
        if status is not None:
            by_status[status] = by_status.get(status, 0) + 1
    fresh = (
        session.scalar(
            select(func.count(ImportRecord.id)).where(
                ImportRecord.last_success_at >= ttl_cutoff
            )
        )
        or 0
    )
    return {
        "catalog_series": catalog_total,
        "series_with_listings": with_listings,
        "listings_total": listings_total,
        "records_total": records_total,
        "records_by_status": by_status,
        "fresh_records": fresh,
        "freshness_ttl_minutes": settings.import_freshness_ttl_minutes,
    }


@router.post("/import", response_model=ImportReportOut)
def run_import(
    request: Request,
    payload: ImportRequest,
    session: Session = Depends(get_db),
) -> ImportReportOut:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Sorgu 'query' boş olamaz.")

    key = normalized_query_key(query)
    runner = request.app.state.import_runner
    holder = f"manual-{uuid4().hex[:8]}"

    # Non-blocking (timeout=0): a concurrent background job (or another
    # manual import) for this query owns the lock.
    if not runner.acquire_import_lock(key, holder, timeout=0):
        raise HTTPException(
            status_code=409,
            detail=(
                "Bu sorgu için bir içe aktarma zaten çalışıyor "
                "(paylaşılan sorgu-bazlı içe aktarma kilidi). Birazdan tekrar deneyin."
            ),
        )
    try:
        # The shared catalog write gate is held by a running catalog sync
        # or a background store import. Refuse (409) rather than
        # create/merge publisher rows under it — the same rule the catalog
        # sync enforces on its side. Non-blocking (timeout=0): a manual
        # import cannot wait out a several-minute sync inside one request.
        if not runner.acquire_import_lock(SYNC_GATE_KEY, holder, timeout=0):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Bir katalog senkronu veya mağaza içe aktarması çalışıyor. "
                    "Birkaç dakika sonra tekrar deneyin."
                ),
            )
        try:
            upsert_running_record(session, key, query)
            service = ImportService(session)
            report = service.run_import(query)
            # Manual imports refresh the freshness state like background ones.
            record_import_result(session, key, report)
        except Exception as exc:
            # Never leave the record stuck as "running" after an unexpected
            # failure (the normal path is already isolated per store/result,
            # but e.g. a database failure can leak out here). The original
            # exception is re-raised so it is not hidden.
            try:
                session.rollback()
                upsert_failed_record(
                    session, key, query, f"{type(exc).__name__}: {exc}"
                )
            except Exception:  # noqa: BLE001 - record the failure if we can
                logger.exception("import: could not record failure for %r", query)
            raise
    finally:
        # Release the catalog write gate first (no-op if the 409 above
        # fired before it was acquired), then the per-query import lock.
        runner.release_import_lock(SYNC_GATE_KEY, holder)
        runner.release_import_lock(key, holder)

    stores = [
        ImportStoreOut(
            store_code=store.store_code,
            store_name=store.store_name,
            results_found=store.results_found,
            created=store.created,
            updated=store.updated,
            skipped=store.skipped,
            errors=store.errors,
            error=store.error,
        )
        for store in report.stores
    ]
    return ImportReportOut(
        query=report.query,
        started_at=report.started_at,
        finished_at=report.finished_at,
        stores=stores,
        total_created=report.total_created,
        total_updated=report.total_updated,
        total_skipped=report.total_skipped,
        total_errors=report.total_errors,
    )

@router.post("/import/warmup")
def warmup_catalog(
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, int]:
    """Queue a background price import for EVERY catalog series.

    Operational pre-warm: after the pass finishes, a search for any catalog
    manga finds price listings immediately instead of waiting for the first
    store scrape. Runner-side per-query dedup makes repeated calls safe —
    only titles not currently being imported are queued.
    """
    runner = request.app.state.import_runner
    titles = session.scalars(
        select(Series.title)
        .join(CatalogSeries, CatalogSeries.series_id == Series.id)
        .distinct()
    ).all()
    queued = 0
    for title in titles:
        key = normalized_query_key(title)
        if key and runner.submit(key, title):
            queued += 1
    return {"total": len(titles), "queued": queued}
