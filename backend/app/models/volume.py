from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.series import Series
    from app.models.store_listing import StoreListing


class Volume(Base):
    __tablename__ = "volumes"

    id: Mapped[int] = mapped_column(primary_key=True)

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id"),
        nullable=False,
        index=True,
    )

    volume_number: Mapped[float] = mapped_column(
        nullable=False,
    )

    isbn: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
    )

    cover_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    series: Mapped["Series"] = relationship(
        back_populates="volumes"
    )

    store_listings: Mapped[list["StoreListing"]] = relationship(
        back_populates="volume",
        cascade="all, delete-orphan",
    )