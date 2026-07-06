from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
    )

    base_url: Mapped[str] = mapped_column(
        String(255),
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    listings: Mapped[list["StoreListing"]] = relationship(
        back_populates="store"
    )