"""Publisher model.

A publisher (e.g. "Athica Yayınları") represents a publishing company. A
series (edition) always belongs to exactly one publisher, which is what makes
"Berserk / Athica" distinct from "Berserk / Dark Horse".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .series import Series


class Publisher(Base):
    __tablename__ = "publishers"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Human-readable display name (first form seen / canonical).
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Normalized comparison key, unique at the database level so duplicate
    #: publishers can never be created (rule 11).
    normalized_name: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )

    series: Mapped[list[Series]] = relationship(
        back_populates="publisher", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Publisher id={self.id} name={self.name!r}>"
