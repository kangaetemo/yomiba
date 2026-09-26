"""Volume endpoint schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

#: Per-user collection statuses; anonymous detail responses use null.
CollectionStatus = Literal["owned", "missing", "wanted"]


class VolumeStoreOut(BaseModel):
    store: str
    price: float | None = None
    currency: str = "TRY"
    stock: bool = True
    product_url: str
    image_url: str | None = None
    last_checked: datetime | None = None


class SeriesRefOut(BaseModel):
    id: int
    title: str
    publisher: str


class VolumeOut(BaseModel):
    id: int
    #: Volume number; ``None`` for unnumbered items (boxes / sets).
    number: int | None = None
    cover_url: str | None = None
    series: SeriesRefOut
    #: Sorted by price ascending; the cheapest store is first.
    stores: list[VolumeStoreOut] = []
    #: Collection status; ``None`` when the volume is not tracked.
    collection_status: CollectionStatus | None = None
    #: True for a legacy store-created phantom (unresolved ``-1`` row). Its
    #: frozen store listings are withheld until an approved cleanup.
    unverified: bool = False


class VolumeCollectionStatusIn(BaseModel):
    """Body for PATCH /volume/{id}/collection-status.

    ``null`` clears the tracking status.
    """

    status: CollectionStatus | None
