"""The normalized result every scraper must return.

Scrapers are forbidden from returning ad-hoc dictionaries; they must produce
``SearchResult`` instances. This is the contract that keeps
``ImportService`` (and therefore the database layer) store-agnostic.

All fields except ``store_id``, ``store_name``, ``title`` and
``product_url`` are optional: a scraper must handle missing information
gracefully and simply leave the field ``None``.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    # --- store identification -------------------------------------------------
    #: Stable machine identifier of the store (e.g. "bkm", "amazon", "dr").
    store_id: str
    #: Human-readable store name (e.g. "BKM Kitap").
    store_name: str

    # --- product identification ------------------------------------------------
    #: Raw product title as shown by the store.
    title: str
    #: Canonical product page URL (sponsored / redirect URLs resolved).
    product_url: str

    # --- parsed / enriched metadata (best effort) -------------------------------
    #: Series title with volume tokens removed (e.g. "Berserk").
    series_title: str | None = None
    #: Volume number when unambiguous (1, 2, 3, ...). ``None`` = unnumbered.
    volume_number: int | None = None
    #: Canonical digit-string ISBN (10 or 13) when available.
    isbn: str | None = None
    #: Publisher name exactly as the store displays it (no guessing).
    publisher: str | None = None
    author: str | None = None
    language: str | None = None
    #: Product category as the store displays it (when available), e.g.
    #: BKM's "Çocuk ve Gençlik Kitapları". Used by the common relevance
    #: filter; ``None`` when the store exposes no category.
    category: str | None = None

    # --- commerce ----------------------------------------------------------------
    #: Current price (store currency). ``None`` when the store shows no price.
    price: Decimal | None = None
    currency: str = Field(default="TRY")
    in_stock: bool = True
    image_url: str | None = None

    # --- ranking -----------------------------------------------------------------
    #: 0..1 relevance of this result to the searched query.
    relevance: float = Field(default=1.0, ge=0.0, le=1.0)
