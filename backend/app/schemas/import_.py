"""Import endpoint schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200, description="Search query to import, e.g. 'Berserk'")


class ImportStoreOut(BaseModel):
    store_code: str
    store_name: str
    results_found: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error: str | None = None


class ImportReportOut(BaseModel):
    query: str
    started_at: datetime
    finished_at: datetime | None = None
    stores: list[ImportStoreOut] = []
    total_created: int = 0
    total_updated: int = 0
    total_skipped: int = 0
    total_errors: int = 0


class ImportRecordOut(BaseModel):
    """One row of the import-attempt history (admin/records view)."""

    normalized_query: str
    last_query: str | None = None
    status: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    stores_ok: int = 0
    stores_failed: int = 0
    results_found: int = 0
    created: int = 0
    updated: int = 0
    error: str | None = None
    reasons: dict[str, dict[str, int]] | None = None


class MissingCoverageOut(BaseModel):
    """A catalog series with no store listing, plus why (admin view).

    ``outcome`` is derived from the last import of the series' query:
    ``never`` (not imported yet), ``failed`` (every store errored),
    ``empty`` (stores answered but returned no products — usually a search
    query problem), ``unmatched`` (products found, none matched the
    catalog — see ``reasons``), ``other_series`` (the query matched a
    different catalog series sharing the title).
    """

    series_id: int
    title: str
    publisher: str | None = None
    volume_count: int = 0
    query: str
    outcome: str
    status: str | None = None
    last_attempt_at: datetime | None = None
    results_found: int = 0
    reasons: dict[str, dict[str, int]] | None = None
    error: str | None = None
