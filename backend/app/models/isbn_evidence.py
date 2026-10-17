"""ISBN evidence and provenance (migration 0018).

* ``IsbnChange``: every change of ``Volume.isbn`` (or of a shared ISBN),
  who/what made it and why. Lets an admin see and undo any decision.
* ``SharedIsbn``: another edition of the same work that carries an ISBN
  owned by a different volume ("Limitli Sert Kapak" printed under the
  regular book's ISBN). ``Volume.isbn`` stays unique; this table holds the
  extra holders.
* ``StoreObservation``: one row per store product an import saw: its
  title, ISBN, the volume the title points to, the volume the ISBN points
  to, and where (and by which rule) it was attached — or why not.
* ``IsbnIssue``: a contradiction the resolver did not settle by itself.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class IsbnChange(Base):
    __tablename__ = "isbn_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    volume_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    old_isbn: Mapped[str | None] = mapped_column(String(20))
    new_isbn: Mapped[str | None] = mapped_column(String(20))
    #: "catalog" | "stores" | "admin" | "shared" | "unshared" | "moved"
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    user_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SharedIsbn(Base):
    __tablename__ = "shared_isbns"
    __table_args__ = (UniqueConstraint("isbn", "volume_id", name="uq_shared_isbn_volume"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    volume_id: Mapped[int] = mapped_column(ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StoreObservation(Base):
    __tablename__ = "store_observations"
    __table_args__ = (UniqueConstraint("store_id", "product_url", name="uq_observation_store_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    product_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    #: Canonical book ISBN the store gave for the product (None = none / not a book ISBN).
    isbn: Mapped[str | None] = mapped_column(String(20))
    publisher: Mapped[str | None] = mapped_column(String(300))
    price: Mapped[int | None] = mapped_column(Integer)
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    #: Catalog volume the title alone points to (ISBN ignored).
    title_volume_id: Mapped[int | None] = mapped_column(Integer, index=True)
    #: Catalog volume holding the product's ISBN.
    isbn_volume_id: Mapped[int | None] = mapped_column(Integer, index=True)
    #: Volume the product was attached to (None = not attached).
    volume_id: Mapped[int | None] = mapped_column(Integer, index=True)
    #: How it was attached: "isbn+title", "isbn", "title", "edition", "shared".
    rule: Mapped[str | None] = mapped_column(String(40))
    #: Why it was not attached (import reject reason).
    reason: Mapped[str | None] = mapped_column(String(60))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class IsbnIssue(Base):
    __tablename__ = "isbn_issues"

    volume_id: Mapped[int] = mapped_column(ForeignKey("volumes.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
