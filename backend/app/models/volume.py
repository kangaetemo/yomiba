"""Volume model.

A Volume belongs to exactly one Series. Uniqueness is enforced per series:
the same volume number cannot appear twice inside one series.

``volume_number`` uses :data:`UNNUMBERED_VOLUME` (-1) for legacy unresolved
items; it does not prove a box/set. Zero is a valid explicit volume number.
The sentinel keeps the unique
constraint effective for them as well.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
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

    series: Mapped[Series] = relationship(back_populates="volumes")
    listings: Mapped[list[StoreListing]] = relationship(
        back_populates="volume", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Volume id={self.id} series_id={self.series_id} "
            f"number={self.volume_number} isbn={self.isbn!r}>"
        )
