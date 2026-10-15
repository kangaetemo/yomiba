"""Foreign-edition evidence preview; legacy application is paused during P0."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..models import CatalogSeries, Series, Store, StoreListing, Volume
from ..normalization.isbn import is_foreign_isbn, is_foreign_language

logger = logging.getLogger("yomiba.foreign_editions")

#: Stores whose catalogue mixes Turkish and imported (English, ...) books.
FOREIGN_PRONE = ("kitapbulan", "amazon")
MAX_PAGES = 400


def page_edition(html: str) -> tuple[str | None, str | None]:
    """(isbn, language) a product page shows; either may be None."""
    from ..scrapers.base import BaseScraper
    from .isbn_conflict_fix import page_isbn

    node = BaseScraper.product_json_ld_node(BaseScraper.extract_json_ld(html)) or {}
    language = node.get("inLanguage")
    if isinstance(language, dict):
        language = language.get("name") or language.get("alternateName")
    return page_isbn(html), (str(language) if language else None)


def build_plan(session: Session, fetch: Callable[[str], str | None], max_pages: int = MAX_PAGES) -> dict:
    catalog = select(CatalogSeries.series_id)
    volumes = {
        v.id: v for v in session.scalars(
            select(Volume).where(Volume.series_id.in_(catalog), Volume.isbn.isnot(None))
        ) if is_foreign_isbn(v.isbn)
    }
    rows = session.execute(
        select(StoreListing, Store.code, Volume, Series.title)
        .join(Store, Store.id == StoreListing.store_id)
        .join(Volume, Volume.id == StoreListing.volume_id)
        .join(Series, Series.id == Volume.series_id)
        .where(Volume.series_id.in_(catalog))
        .where((Volume.id.in_(list(volumes))) | (Store.code.in_(FOREIGN_PRONE)))
        .order_by(StoreListing.id)
    ).all()
    listings, checked = [], 0
    for listing, code, volume, title in rows:
        if checked >= max_pages:
            break
        checked += 1
        html = fetch(listing.product_url)
        isbn, language = page_edition(html) if html else (None, None)
        foreign = bool(
            is_foreign_isbn(isbn) or is_foreign_language(language)
            or (isbn and volume.id in volumes and isbn == volume.isbn)
        )
        listings.append({
            "listing_id": listing.id, "volume_id": volume.id, "series": title,
            "volume_number": volume.volume_number, "store": code,
            "product_url": listing.product_url, "page_isbn": isbn, "page_language": language,
            "action": "remove" if foreign else "keep",
            "why": None if foreign else ("sayfa Türkçe baskı gösteriyor" if isbn or language else "sayfadan kanıtlanamadı"),
        })
    return {
        "foreign_isbn_volumes": [
            {"volume_id": v.id, "isbn": v.isbn, "volume_number": v.volume_number,
             "series": session.get(Series, v.series_id).title}
            for v in volumes.values()
        ],
        "listings": listings,
        "scanned": checked,
        "total_candidates": len(rows),
    }


def apply_plan(session: Session, plan: dict, db_path: Path | None = None) -> dict:
    from .isbn_safety import reject_legacy_write
    reject_legacy_write()


class ForeignEditionJob:
    """One scan / apply at a time, state kept in memory for the admin."""

    def __init__(self, session_factory: sessionmaker[Session], fetch_factory: Callable[[], Callable[[str], str | None]] | None = None) -> None:
        self._sessions = session_factory
        self._fetch_factory = fetch_factory
        self._lock = threading.Lock()
        self.state = "idle"  # idle | scanning | ready | applying | done | failed
        self.plan: dict | None = None
        self.result: dict | None = None
        self.error: str | None = None

    def status(self) -> dict:
        return {"state": self.state, "plan": self.plan, "result": self.result, "error": self.error}

    def start_scan(self) -> bool:
        with self._lock:
            if self.state in ("scanning", "applying"):
                return False
            self.state, self.plan, self.result, self.error = "scanning", None, None, None
        threading.Thread(target=self._scan, name="foreign-edition-scan", daemon=True).start()
        return True

    def _scan(self) -> None:
        from .isbn_conflict_fix import default_fetch

        try:
            fetch = (self._fetch_factory or default_fetch)()
            with self._sessions() as session:
                self.plan = build_plan(session, fetch)
            self.state = "ready"
        except Exception as exc:  # noqa: BLE001 - reported to the admin
            logger.exception("foreign edition scan failed")
            self.state, self.error = "failed", f"{type(exc).__name__}: {exc}"

    def apply(self, db_path: Path | None) -> dict:
        with self._lock:
            if self.state != "ready" or self.plan is None:
                raise RuntimeError("Önce tarama yapılmalı.")
            self.state = "applying"
        try:
            with self._sessions() as session:
                self.result = apply_plan(session, self.plan, db_path)
            self.state = "done"
            return self.result
        except Exception as exc:
            self.state, self.error = "failed", f"{type(exc).__name__}: {exc}"
            raise
