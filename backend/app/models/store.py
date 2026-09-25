"""Store model.

A Store is a shop whose listings we track (Amazon, BKM Kitap, D&R, ...).
Stores are seeded on startup.

``code`` is a stable, scraper-defined identifier (e.g. "bkm") used for
deterministic matching between a scraper and its Store row; ``name`` is the
human-readable display name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .store_listing import StoreListing


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Stable machine identifier used by scrapers to identify the store.
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    listings: Mapped[list[StoreListing]] = relationship(back_populates="store")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Store id={self.id} code={self.code!r} name={self.name!r}>"
