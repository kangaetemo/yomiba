from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.store_listing import StoreListing


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    base_url: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    listings: Mapped[list["StoreListing"]] = relationship(
        back_populates="store",
        cascade="all, delete-orphan",
    )