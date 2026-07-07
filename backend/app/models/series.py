from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.publisher import Publisher
    from app.models.volume import Volume


class Series(Base):
    __tablename__ = "series"

    __table_args__ = (
        UniqueConstraint(
            "publisher_id",
            "title",
            name="uq_series_publisher_title",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("publishers.id"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    cover_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    publisher: Mapped["Publisher"] = relationship(
        back_populates="series"
    )

    volumes: Mapped[list["Volume"]] = relationship(
        back_populates="series",
        cascade="all, delete-orphan",
    )