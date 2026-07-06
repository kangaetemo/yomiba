from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)

    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("publishers.id"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255))

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    cover_path: Mapped[str | None] = mapped_column(
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