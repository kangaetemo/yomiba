"""Search endpoint schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SeriesSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    publisher: str
    cover_url: str | None = None
    volume_count: int
    #: In-stock priced store offers across the series' volumes.
    in_stock_offers: int = 0
    #: Lowest current in-stock price of any volume; ``None`` when none.
    lowest_price: float | None = None


class ImportStatusOut(BaseModel):
    """Legacy response envelope; search emits only fresh or idle.

    It does not report or initiate background import state.
    """

    state: str
    detail: str | None = None
    last_success_at: datetime | None = None


class SearchResponse(BaseModel):
    results: list[SeriesSummary]
    status: ImportStatusOut
