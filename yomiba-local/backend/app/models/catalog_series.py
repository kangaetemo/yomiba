"""Catalog manifest: which series belong to the tracked catalog.

The tracked catalog is the set of manga the Mangakol catalog sync has
registered (see ``app.services.catalog_sync``). The sync records one row
per (series, mangakol slug) here.

The search endpoint only returns series present in this manifest, so
products that store imports pull in but the catalog does not cover
(foreign editions, books, figures) stay in the database — with their
listings and price history — while remaining out of the search results.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class CatalogSeries(Base):
    __tablename__ = "catalog_series"

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), primary_key=True
    )
    #: Slug of the mangakol entry this row came from (provenance; a series
    #: can be reachable from more than one entry, so the slug is part of
    #: the primary key and not unique on its own).
    mangakol_slug: Mapped[str] = mapped_column(String(200), primary_key=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CatalogSeries series_id={self.series_id} slug={self.mangakol_slug!r}>"
