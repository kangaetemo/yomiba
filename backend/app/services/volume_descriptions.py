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
import json
import logging
import re
import unicodedata
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


#: Text copied out of a print PDF keeps the accent as a separate spacing
#: mark after the letter ("gu¨çlu¨", "kis¸i", "degˆil"; the circumflex stands
#: in for the breve of ğ).
_SPACING_MARKS = {
    "\u00a8": {"u": "ü", "U": "Ü", "o": "ö", "O": "Ö"},
    "\u00b8": {"s": "ş", "S": "Ş", "c": "ç", "C": "Ç"},
    "\u02c6": {"g": "ğ", "G": "Ğ"},
    "\u02d8": {"g": "ğ", "G": "Ğ"},
}
_UPPER = "A-ZÇĞİÖŞÜ"


def _fix_letters(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for mark, letters in _SPACING_MARKS.items():
        for base, letter in letters.items():
            text = text.replace(base + mark, letter)
    # Backticks used as apostrophes or quotes ("Ryuk`un", "`gul`").
    return text.replace("`", "’")


def _join_wrapped_lines(lines: list[str]) -> list[str]:
    """A line break that does not end a sentence is the PDF's line wrap."""
    paragraphs: list[str] = []
    for line in lines:
        if paragraphs and not re.search(r"[.!?…:;\"”»)]$", paragraphs[-1]):
            paragraphs[-1] = f"{paragraphs[-1]} {line}"
        else:
            paragraphs.append(line)
    return paragraphs


def clean_description(raw: object) -> str | None:
    """Plain text with paragraph breaks, or None when it is not a blurb."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw
    if "<" in text:
        text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", text)
        text = BeautifulSoup(text, "html.parser").get_text()
    text = _fix_letters(html.unescape(text).replace("\xa0", " "))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line and not _SPEC_LINE.match(line)]
    text = "\n".join(_join_wrapped_lines(lines))
    # Hyphenated line ends rejoined with a space ("du- rum").
    text = re.sub(r"(?<=[a-zçğıöşü])- (?=[a-zçğıöşü])", "", text)
    # "biridir.Bu deftere", "defter:Death Note": a missing space after a sentence.
    text = re.sub(rf"([a-zçğıöşü)][.!?…:]|[.!?…]\))([{_UPPER}])", r"\1 \2", text)
    if len(text) < MIN_LENGTH or _SHOP_TEXT.search(text):
        return None
    if len(text) > MAX_LENGTH:
        cut = text[:MAX_LENGTH]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("\n"))
        text = cut[: end + 1].strip() if end > MIN_LENGTH else cut.rsplit(" ", 1)[0] + "…"
    return text


#: A blurb pulled out of the page markup is a block of prose; a block much
#: longer than a blurb is the page (several tabs, footer) rather than one.
_MAX_BLOCK = 3000
#: Tab and section labels the stores put over the blurb (Gerekli Şeyler
#: "Ürün Bilgisi", Büyülü Dükkan / Edessa "Ürün Açıklaması").
_LABEL = re.compile(
    r"^\s*(ürün açıklaması|açıklama|ürün bilgisi|ürün detayı|kitap hakkında|tanıtım|arka kapak( yazısı)?)\s*:?\s*$",
    re.IGNORECASE,
)
_CONTAINER = re.compile(r"descr|aciklama|açıklama|urun-?bilgi|product-?info|product-?detail|detay", re.IGNORECASE)
#: Embedded page state (Next.js / ikas __NEXT_DATA__, Shopify product JSON).
_JSON_DESCRIPTION = re.compile(r'"description"\s*:\s*"((?:[^"\\]|\\.){%d,})"' % MIN_LENGTH)
_NOISE = ("script", "style", "noscript", "svg", "button", "form", "select", "nav", "header", "footer")


def _block_text(element) -> str | None:
    raw = element.get_text("\n")
    if len(raw) > _MAX_BLOCK * 2:
        return None
    # Prose only: titles, prices and spec cells around the blurb are short
    # lines that do not end a sentence.
    lines = [line for line in (l.strip() for l in raw.splitlines())
             if line and not _LABEL.match(line) and (len(line) >= 40 or re.search(r"[.!?…\"”]$", line))]
    text = clean_description("\n".join(lines))
    return text if text and len(text) <= _MAX_BLOCK else None


def _from_markup(soup) -> str | None:
    for tag in soup(_NOISE):
        tag.decompose()
    # 1. The panel a "Ürün Açıklaması" tab points to, else the label's section.
    for label in soup.find_all(string=_LABEL):
        holder = label.parent
        target = None
        for attr in ("href", "aria-controls", "data-target", "data-bs-target", "data-tab"):
            ref = str(holder.get(attr) or "").lstrip("#")
            if ref and not ref.startswith(("http", "/")):
                target = soup.find(id=ref)
                if target is not None:
                    break
        if target is not None and (text := _block_text(target)):
            return text
        node = holder
        for _ in range(4):
            node = node.parent
            if node is None:
                break
            if text := _block_text(node):
                return text
    # 2. The most specific "description"-named container that reads as a blurb.
    named = [el for el in soup.find_all(True) if _CONTAINER.search(" ".join([el.get("id") or "", *el.get("class", [])]))]
    for element in sorted(named, key=lambda el: len(el.find_all(True))):
        if text := _block_text(element):
            return text
    return None


def description_from_page(page: str) -> str | None:
    node = BaseScraper.product_json_ld_node(BaseScraper.extract_json_ld(page))
    if node is not None:
        text = clean_description(node.get("description"))
        if text:
            return text
    for match in _JSON_DESCRIPTION.finditer(page):
        try:
            value = json.loads(f'"{match.group(1)}"')
        except ValueError:
            continue
        if text := clean_description(value):
            return text
    soup = BeautifulSoup(page, "html.parser")
    metas = [soup.find("meta", attrs=a) for a in ({"property": "og:description"}, {"name": "description"})]
    if text := _from_markup(soup):
        return text
    for meta in metas:
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
    #: (volume id, product URLs read) of volumes no page described.
    misses: list[tuple[int, list[str]]] = field(default_factory=list)

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
                tried: list[str] = []
                for listing in listings[:MAX_PAGES_PER_VOLUME]:
                    scraper = self._scraper(listing.store.code)
                    if scraper is None or report.pages >= budget:
                        continue
                    report.pages += 1
                    tried.append(listing.product_url)
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
                else:
                    report.misses.append((volume.id, tried))
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
