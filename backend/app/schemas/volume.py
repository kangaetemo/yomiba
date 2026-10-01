"""Volume endpoint schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

#: Per-user collection statuses; anonymous detail responses use null.
CollectionStatus = Literal["owned", "missing", "wanted"]


class VolumeStoreOut(BaseModel):
    #: Listing id (admins remove a wrongly matched listing by it).
    id: int | None = None
    store: str
    price: float | None = None
    currency: str = "TRY"
    stock: bool = True
    #: Not seen by the store's recent scrapes: ``stock`` is the last known
    #: value and may be outdated (the product likely left the store's search).
    stale: bool = False
    product_url: str
    image_url: str | None = None
    last_checked: datetime | None = None


class SeriesRefOut(BaseModel):
    id: int
    slug: str = ""
    title: str
    publisher: str
    author: str | None = None
    illustrator: str | None = None


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
    #: Catalog details (None when unknown).
    isbn: str | None = None
    page_count: int | None = None
    release_date: date | None = None
    #: Original volumes an omnibus book collects (2-in-1: 9-10), else None.
    covers_from: int | None = None
    covers_to: int | None = None


class VolumeCollectionStatusIn(BaseModel):
    """Body for PATCH /volume/{id}/collection-status.

    ``null`` clears the tracking status.
    """

    status: CollectionStatus | None
