"""Series endpoint schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

CollectionStatus = Literal["owned", "missing", "wanted"]


class SeriesVolumeOut(BaseModel):
    id: int
    #: Volume number; ``None`` for unnumbered items (boxes / sets).
    number: int | None = None
    #: Cheapest current price (in-stock preferred); ``None`` when unknown.
    best_price: float | None = None
    store_count: int = 0
    #: Collection status; ``None`` when the volume is not tracked.
    collection_status: CollectionStatus | None = None


class SeriesOut(BaseModel):
    id: int
    title: str
    publisher: str
    slug: str
    cover_url: str | None = None
    volumes: list[SeriesVolumeOut] = []
