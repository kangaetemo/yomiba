"""Volume model.

A Volume belongs to exactly one Series. Uniqueness is enforced per series:
the same volume number cannot appear twice inside one series.

``volume_number`` uses :data:`UNNUMBERED_VOLUME` (-1) for legacy unresolved
items; it does not prove a box/set. Zero is a valid explicit volume number.
The sentinel keeps the unique
constraint effective for them as well.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..normalization.volume import UNNUMBERED_VOLUME

if TYPE_CHECKING:
    from .series import Series
    from .store_listing import StoreListing


class Volume(Base):
    __tablename__ = "volumes"
    __table_args__ = (
        UniqueConstraint("series_id", "volume_number", name="uq_volume_series_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: 0, 1, 2, ... for real volumes; UNNUMBERED_VOLUME (-1) for unresolved legacy rows.
    volume_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=UNNUMBERED_VOLUME
    )
    #: Canonical digit-string ISBN (10 or 13). Globally unique: the same ISBN
    #: is the same physical book, so it must map to a single volume. Nullable
    #: because not every store exposes an ISBN.
    isbn: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    #: Original volumes a 2-in-1 / 3-in-1 book collects (catalog source:
    #: Dragon Ball "Cilt 5" = 9-10). Stores title such books by that span
    #: ("Dragon Ball 9&10"); NULL for single-volume books.
    covers_from: Mapped[int | None] = mapped_column(Integer)
    covers_to: Mapped[int | None] = mapped_column(Integer)
    #: Catalog volume-page details (Mangakol "Sayfa Sayısı", "Yayın Tarihi
    #: (Yerel)"); None when the source has none.
    page_count: Mapped[int | None] = mapped_column(Integer)
    release_date: Mapped[date | None] = mapped_column(Date)
    #: When the catalog volume page was last read (ISBN + details); None =
    #: never, so the sync knows what is still to fetch.
    details_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Self-hosted cover (services/covers.py): storage key of the WebP copy,
    #: where it came from ("store:bkm", "catalog", "mangakol") and when the
    #: sources were last tried. ``cover_url`` above stays the external
    #: SOURCE candidate only — it is never sent to browsers.
    cover_key: Mapped[str | None] = mapped_column(String(200))
    cover_source: Mapped[str | None] = mapped_column(String(40))
    cover_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    series: Mapped[Series] = relationship(back_populates="volumes")
    listings: Mapped[list[StoreListing]] = relationship(
        back_populates="volume", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Volume id={self.id} series_id={self.series_id} "
            f"number={self.volume_number} isbn={self.isbn!r}>"
        )
