"""Volume descriptions: the back-cover text stores show on product pages.

Read from the page's schema.org Product/Book JSON-LD ``description``, else
its ``og:description`` / meta description, and kept only when it reads like
a blurb (long enough, no shop boilerplate such as "en uygun fiyat"). One
volume tries up to ``MAX_PAGES_PER_VOLUME`` of its listings; a volume none
of them describes is tried again after ``RETRY_DAYS``.

The series page shows its first volume's text (least spoilers), the volume
page its own. Pages go through the scrapers' ``get``, so the per-store
request spacing is shared with imports and price refreshes.
"""

from __future__ import annotations

import html
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from bs4 import BeautifulSoup
from sqlalchemy import case, exists, or_, select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import CatalogSeries, Store, StoreListing, Volume
from ..scrapers.base import BaseScraper
from ..scrapers.common import looks_like_blocked_page
from ..scrapers.registry import enabled_store_ids, registered_scrapers
from ..utils import utcnow

logger = logging.getLogger("yomiba.descriptions")

MIN_LENGTH = 80
MAX_LENGTH = 1500
RETRY_DAYS = 30
MAX_PAGES_PER_VOLUME = 3

#: Store SEO text, not a blurb.
_SHOP_TEXT = re.compile(
    r"satın al|en uygun fiyat|uygun fiyatla|kargo|sipariş|taksit|indirimli fiyat|kampanya",
    re.IGNORECASE,
)
#: Spec lines some stores put under the blurb ("ISBN: ...", "Sayfa Sayısı: 192").
_SPEC_LINE = re.compile(
    r"^(isbn|barkod|sayfa( sayısı)?|yayınevi|yayın tarihi|yazar|çizer|çevirmen|çeviri|boyut|ebat|"
    r"kağıt( türü)?|kapak( türü)?|cilt( tipi)?|basım( yılı)?|dil|orijinal ad[ıi]?)\s*:",
    re.IGNORECASE,
)


def clean_description(raw: object) -> str | None:
    """Plain text with paragraph breaks, or None when it is not a blurb."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw
    if "<" in text:
        text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", text)
        text = BeautifulSoup(text, "html.parser").get_text()
    text = html.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line and not _SPEC_LINE.match(line)]
    text = "\n".join(lines)
    if len(text) < MIN_LENGTH or _SHOP_TEXT.search(text):
        return None
    if len(text) > MAX_LENGTH:
        cut = text[:MAX_LENGTH]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("\n"))
        text = cut[: end + 1].strip() if end > MIN_LENGTH else cut.rsplit(" ", 1)[0] + "…"
    return text


def description_from_page(page: str) -> str | None:
    node = BaseScraper.product_json_ld_node(BaseScraper.extract_json_ld(page))
    if node is not None:
        text = clean_description(node.get("description"))
        if text:
            return text
    soup = BeautifulSoup(page, "html.parser")
    for attrs in ({"property": "og:description"}, {"name": "description"}):
        meta = soup.find("meta", attrs=attrs)
        text = clean_description(meta.get("content") if meta else None)
        if text:
            return text
    return None


@dataclass
class DescriptionReport:
    volumes: int = 0
    pages: int = 0
    stored: int = 0
    remaining: int = 0
    by_store: Counter = field(default_factory=Counter)
    #: Dry run only: (volume id, store code, text) of what would be stored.
    samples: list[tuple[int, str, str]] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"volumes={self.volumes} pages={self.pages} stored={self.stored} "
                f"remaining={self.remaining} by_store={dict(self.by_store)}")


class DescriptionFetcher:
    """Fills ``Volume.description`` from store product pages, first volumes
    of each series first. ``dry_run`` reads pages but writes nothing."""

    def __init__(self, session: Session, *, settings: Settings | None = None,
                 scrapers: dict[str, BaseScraper] | None = None, dry_run: bool = False) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self._scrapers = scrapers if scrapers is not None else {}
        self._own_scrapers = scrapers is None
        self._stores = set(self._scrapers) if scrapers is not None else set(enabled_store_ids())
        self.dry_run = dry_run

    def _pending(self):
        retry_before = utcnow() - timedelta(days=RETRY_DAYS)
        has_page = exists().where(
            StoreListing.volume_id == Volume.id, StoreListing.product_url.isnot(None),
            StoreListing.store_id.in_(select(Store.id).where(Store.code.in_(self._stores))),
        )
        return select(Volume).where(
            Volume.series_id.in_(select(CatalogSeries.series_id)),
            Volume.volume_number >= 0, Volume.description.is_(None), has_page,
            or_(Volume.description_checked_at.is_(None), Volume.description_checked_at < retry_before),
        )

    def _scraper(self, code: str) -> BaseScraper | None:
        if code not in self._stores:
            return None
        if code not in self._scrapers:
            cls = registered_scrapers().get(code)
            if cls is None:
                return None
            self._scrapers[code] = cls()
        return self._scrapers[code]

    def _read(self, scraper: BaseScraper, url: str) -> str | None:
        try:
            response = scraper.get(url)
        except Exception:  # noqa: BLE001 - one page must not stop the pass
            logger.info("descriptions: %s failed", url)
            return None
        if response.status_code >= 400 or looks_like_blocked_page(response.status_code, response.text):
            return None
        return description_from_page(response.text)

    def run(self, budget: int) -> DescriptionReport:
        report = DescriptionReport()
        # Volume 1 (or a series' first) before the rest: it is the series intro.
        first = case((Volume.volume_number <= 1, 0), else_=1)
        queue = self.session.scalars(
            self._pending().order_by(first, Volume.series_id, Volume.volume_number)
        ).all()
        try:
            for volume in queue:
                if report.pages >= budget:
                    break
                report.volumes += 1
                listings = sorted(
                    (l for l in volume.listings if l.product_url and l.store and l.store.code in self._stores),
                    key=lambda l: (not l.in_stock, l.store.code),
                )
                for listing in listings[:MAX_PAGES_PER_VOLUME]:
                    scraper = self._scraper(listing.store.code)
                    if scraper is None or report.pages >= budget:
                        continue
                    report.pages += 1
                    text = self._read(scraper, listing.product_url)
                    if not text:
                        continue
                    report.stored += 1
                    report.by_store[listing.store.code] += 1
                    if self.dry_run:
                        report.samples.append((volume.id, listing.store.code, text))
                    else:
                        volume.description, volume.description_source = text, listing.store.code
                    break
                if not self.dry_run:
                    volume.description_checked_at = utcnow()
                    self.session.commit()
            if self.dry_run:
                self.session.rollback()
            report.remaining = max(0, len(queue) - report.volumes)
        finally:
            if self._own_scrapers:
                for scraper in self._scrapers.values():
                    scraper.close()
                self._scrapers.clear()
        logger.info("descriptions: %s", report)
        return report


#: A later volume's blurb tells the story so far: only the opening volumes
#: stand for the series.
SERIES_INTRO_MAX_VOLUME = 3


def series_description(session: Session, series_id: int) -> tuple[str, str] | None:
    """(text, store code) of the series' first described opening volume."""
    row = session.execute(
        select(Volume.description, Volume.description_source)
        .where(Volume.series_id == series_id, Volume.volume_number >= 0,
               Volume.volume_number <= SERIES_INTRO_MAX_VOLUME, Volume.description.isnot(None))
        .order_by(Volume.volume_number)
        .limit(1)
    ).first()
    return (row[0], row[1] or "") if row else None


def store_name(session: Session, code: str | None) -> str | None:
    """Display name of a description's source store."""
    return session.scalar(select(Store.name).where(Store.code == code)) if code else None
