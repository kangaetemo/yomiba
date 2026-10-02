"""Series endpoint schemas."""

from __future__ import annotations

from datetime import date
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
    #: Stores with the volume in stock; ``0 < store_count`` means sold out
    #: everywhere (``best_price`` is then an out-of-stock price).
    in_stock_count: int = 0
    #: Stores whose stock flag is stale (not seen lately): stock unknown.
    stale_count: int = 0
    #: Store offering ``best_price`` (e.g. "Edessa Kitabevi").
    best_store: str | None = None
    #: Collection status; ``None`` when the volume is not tracked.
    collection_status: CollectionStatus | None = None
    cover_url: str | None = None
    #: Local release date from the catalog source; ``None`` when unknown.
    release_date: date | None = None


class SeriesEditionOut(BaseModel):
    """Another edition of the same work (e.g. "Soichi" <-> "Soichi (Bez Cilt)")."""

    id: int
    slug: str
    title: str
    publisher: str
    volume_count: int = 0
    in_stock_offers: int = 0
    lowest_price: float | None = None


class SeriesOut(BaseModel):
    id: int
    title: str
    publisher: str
    slug: str
    author: str | None = None
    cover_url: str | None = None
    volumes: list[SeriesVolumeOut] = []
    #: Other editions of the same work; empty for most series.
    editions: list[SeriesEditionOut] = []
    #: A finished single-volume work (completed in Japan and in Turkey, one
    #: numbered volume): the site skips its volume list and opens the volume.
    one_shot: bool = False
