from datetime import date

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.series import Series


class Volume(Base):
    __tablename__ = "volumes"

    id: Mapped[int] = mapped_column(primary_key=True)

    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id"),
        nullable=False,
        index=True,
    )

    volume_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    isbn: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
        index=True,
    )

    cover_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    release_date: Mapped[date | None] = mapped_column(
        nullable=True,
    )

    series: Mapped["Series"] = relationship(
        back_populates="volumes"
    )
   
store_listings: Mapped[list["StoreListing"]] = relationship(
    back_populates="volume",
    cascade="all, delete-orphan",
)