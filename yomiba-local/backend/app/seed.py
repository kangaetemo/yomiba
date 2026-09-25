"""Seed data.

Stores are the one kind of entity we pre-create: they are known ahead of time
and referenced by scraper codes. No fake series / volumes / prices are seeded
here — catalog data enters exclusively through the ImportService (or the
optional ``dev_data.py`` development dataset, which is clearly labelled).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Store

logger = logging.getLogger("yomiba.seed")

#: (code, display name) — codes must match the scrapers' ``store_id``.
SEED_STORES: tuple[tuple[str, str], ...] = (
    ("amazon", "Amazon"),
    ("bkm", "BKM Kitap"),
    ("dr", "D&R"),
    ("kitapsepeti", "Kitap Sepeti"),
    ("kitapbulan", "Kitapbulan"),
    ("gerekliseyler", "Gerekli Şeyler"),
    ("cizman", "Cizman"),
    ("kitapsec", "Kitapsec"),
    ("komikseyler", "Komikşeyler"),
)


def seed_stores(session: Session) -> None:
    """Idempotently create the known stores (matched by code)."""
    for code, name in SEED_STORES:
        existing = session.scalar(select(Store).where(Store.code == code))
        if existing is None:
            session.add(Store(code=code, name=name))
            logger.info("seed: created store %r (%s)", name, code)
    session.commit()
