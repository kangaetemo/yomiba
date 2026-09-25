"""DB-first search orchestration.

``/search`` always answers from the catalog first and never waits for
scraping. Because the app is **catalog-only** (search serves only series
registered by the Mangakol catalog sync), a background import is scheduled
ONLY when the query matches the catalog: an import for a non-matching query
could never produce visible results, so it must not run at all (no dead-end
"importing" wait, no store hammering on arbitrary queries).

States:

* **fresh**      — catalog results returned; last successful import within
                   TTL; no work.
* **refreshing** — catalog results returned; background refresh running /
                   just started (the frontend re-polls until it lands).
* **stale**      — catalog results returned; data older than TTL, refresh
                   not running (only possible inside the retry window after
                   a failed attempt).
* **idle**       — the catalog has no series for this query; nothing
                   scheduled. The UI shows the honest "not in catalog" state.
* **importing** / **failed** — historical states kept for API compatibility;
                   a background job can no longer be started for a
                   non-matching query, so search does not emit them (the
                   frontend still handles them defensively).

Freshness policy:

* fresh := record.last_success_at within ``import_freshness_ttl_minutes``.
  A *failed* attempt does not make good data stale — only ``last_success_at``
  matters.
* A new attempt is scheduled when the query matches the catalog, data is not
  fresh, no job is running for this query, and the last attempt (any status)
  is older than ``import_failure_retry_minutes`` (anti-hammering).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ImportRecord
from ..utils import utcnow
from . import catalog_service
from .background_import import (
    BackgroundImportRunner,
    aware_datetime,
    is_fresh_record,
    normalized_query_key,
)


@dataclass
class ImportStatus:
    state: str
    detail: str | None = None
    last_success_at: datetime | None = None


@dataclass
class SearchOutcome:
    matches: list[catalog_service.SeriesMatch]
    import_status: ImportStatus


def search_with_auto_import(
    session: Session, query: str, runner: BackgroundImportRunner
) -> SearchOutcome:
    """Search the catalog and schedule a background import when needed."""
    matches = catalog_service.search_series(session, query)
    key = normalized_query_key(query)
    record = session.scalar(
        select(ImportRecord).where(ImportRecord.normalized_query == key)
    )

    settings = get_settings()
    now = utcnow()
    retry_window = timedelta(minutes=settings.import_failure_retry_minutes)

    last_success_at = aware_datetime(record.last_success_at) if record else None
    last_attempt_at = aware_datetime(record.last_attempt_at) if record else None

    fresh = is_fresh_record(record, settings)
    running = runner.is_running(key)

    # Catalog-only policy: an import is scheduled only for queries the
    # catalog actually matches — for anything else it could never produce
    # visible results, so the search answers "not in catalog" immediately.
    submitted = False
    if matches and not fresh and not running:
        cooldown_blocked = (
            record is not None
            and last_attempt_at is not None
            and (now - last_attempt_at) < retry_window
        )
        if not cooldown_blocked:
            submitted = runner.submit(key, query)

    state = _state(matches, fresh, running, submitted)
    return SearchOutcome(
        matches=matches,
        import_status=ImportStatus(
            state=state,
            detail=_detail(record, running, submitted),
            last_success_at=last_success_at,
        ),
    )


def _state(
    matches: list,
    fresh: bool,
    running: bool,
    submitted: bool,
) -> str:
    if not matches:
        return "idle"
    if running or submitted:
        return "refreshing"
    return "fresh" if fresh else "stale"


def _detail(
    record: ImportRecord | None, running: bool, submitted: bool
) -> str | None:
    if submitted:
        return "Arka planda içe aktarma başlatıldı."
    if running:
        return "Arka planda içe aktarma sürüyor."
    if record is None:
        return None
    if record.status in ("success", "partial"):
        parts = []
        if record.created or record.updated:
            parts.append(f"{record.created} yeni, {record.updated} güncellendi")
        else:
            parts.append(f"{record.results_found} ürün bulundu")
        if record.stores_failed:
            parts.append(f"{record.stores_failed} mağazaya ulaşılamadı")
        return "; ".join(parts)
    if record.status == "failed":
        return (
            f"Son içe aktarma başarısız: {record.error}"
            if record.error
            else "Son içe aktarma başarısız."
        )
    return None  # running (handled above) or fresh
