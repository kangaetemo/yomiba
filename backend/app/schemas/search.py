"""Search endpoint schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SeriesSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    #: Public number-free URL slug (``/series/<slug>``).
    slug: str = ""
    title: str
    publisher: str
    cover_url: str | None = None
    volume_count: int
    #: In-stock priced store offers across the series' volumes.
    in_stock_offers: int = 0
    #: Lowest current in-stock price of any volume; ``None`` when none.
    lowest_price: float | None = None


class VolumeHitOut(BaseModel):
    """One volume found by a "<series> <number>" query."""

    series_slug: str
    series_title: str
    publisher: str
    number: int
    cover_url: str | None = None
    in_stock_count: int = 0
    best_price: float | None = None


class ImportStatusOut(BaseModel):
    """Legacy response envelope; search emits only fresh or idle.

    It does not report or initiate background import state.
    """

    state: str
    detail: str | None = None
    last_success_at: datetime | None = None


class SearchResponse(BaseModel):
    results: list[SeriesSummary]
    #: Filled for queries like "one piece 47"; empty otherwise.
    volumes: list[VolumeHitOut] = []
    status: ImportStatusOut
