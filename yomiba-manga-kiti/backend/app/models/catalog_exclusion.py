"""Catalog exclusions: mangakol entries that must never be tracked.

The Mangakol catalog contains a handful of non-manga items (manga-format
adaptations of literature / novels, game novels, educational textbooks)
that the app deliberately does not track. Excluded slugs are skipped by
the catalog sync — they are never (re)added — and their ``catalog_series``
rows are removed, closing the manifest gate. All product data (series,
volumes, listings, price history) stays in the database untouched.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class CatalogExclusion(Base):
    __tablename__ = "catalog_exclusions"

    mangakol_slug: Mapped[str] = mapped_column(String(200), primary_key=True)
    #: Why this slug is excluded (audit trail).
    reason: Mapped[str | None] = mapped_column(String(300))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CatalogExclusion slug={self.mangakol_slug!r}>"
