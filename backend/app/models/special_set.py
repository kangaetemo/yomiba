"""SpecialSet: a store product that is not one catalog volume.

A box set, a limited bundle or a pre-order package that spans one or more
catalog series (Komik Şeyler's "JoJo Part 1 + Part 2 Bunkobon Sert Kapaklı
Kutulu Set"). The importer never attaches such products to volumes; an
admin adds them by product URL and links them to the series whose pages
show them. Price and stock are re-read from the product page after each
price refresh of a linked series.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..utils import utcnow


class SpecialSet(Base):
    __tablename__ = "special_sets"
    __table_args__ = (UniqueConstraint("store_id", "product_url", name="uq_special_set_store_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    #: Current price in cents; None until the product page was read.
    price: Mapped[int | None] = mapped_column(Integer)
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    #: Admin flag: the store sells it as a pre-order.
    preorder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Hidden from public pages (kept for its history).
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Why the last product-page read failed; None when it worked.
    check_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    store = relationship("Store")
    links = relationship("SpecialSetSeries", cascade="all, delete-orphan", passive_deletes=True)


class SpecialSetSeries(Base):
    __tablename__ = "special_set_series"

    set_id: Mapped[int] = mapped_column(
        ForeignKey("special_sets.id", ondelete="CASCADE"), primary_key=True
    )
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), primary_key=True, index=True
    )
