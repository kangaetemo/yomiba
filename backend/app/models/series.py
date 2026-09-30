"""Series model.

A Series is a publisher-specific edition of a work. "Berserk" published by
Athica and "Berserk" published by Dark Horse are two different Series rows.
Series are never merged across publishers merely because the titles match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .publisher import Publisher
    from .volume import Volume


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (
        # One edition per (publisher, normalized title). Prevents duplicate
        # series for the same edition at the database level.
        UniqueConstraint(
            "publisher_id", "normalized_title", name="uq_series_publisher_normalized_title"
        ),
        UniqueConstraint("publisher_id", "slug", name="uq_series_publisher_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("publishers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Display title (clean base title, e.g. "Berserk").
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    #: URL-friendly slug derived from the normalized title.
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    #: Normalized comparison key used for deterministic matching.
    normalized_title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    #: Normalized key of the original (foreign) title as shown by the
    #: catalog source (e.g. "tokyo ghoul" for "Tokyo Gül"). Filled by the
    #: catalog sync; None for series that never had one. Search-only.
    original_title: Mapped[str | None] = mapped_column(
        String(300), nullable=True, index=True
    )
    #: Credits from the catalog source ("Yazar" / "Çizer"); None when unknown.
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    illustrator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Publication status in Japan / Turkey from the catalog source
    #: ("completed", "ongoing", ...); None when unknown.
    jp_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tr_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    publisher: Mapped[Publisher] = relationship(back_populates="series")
    volumes: Mapped[list[Volume]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Series id={self.id} title={self.title!r} publisher_id={self.publisher_id}>"
