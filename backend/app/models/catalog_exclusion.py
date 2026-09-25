"""Legacy exclusion audit rows; no longer used for catalog membership.

Every live Mangakol entry belongs in the catalog. The table remains in the
Alembic schema for compatibility and historical records.
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
    #: Historical reason, retained only for audit compatibility.
    reason: Mapped[str | None] = mapped_column(String(300))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CatalogExclusion slug={self.mangakol_slug!r}>"
