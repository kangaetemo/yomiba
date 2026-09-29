"""Mangakol CATALOG scraper (live-verified against mangakol.com, 2026-09-11).

This is a *catalog source*, NOT a price store: mangakol.com is a Turkish
manga catalog/community site. It knows every Turkish-released manga series
and its published volume list (with release dates), but it carries no
prices or stock. It is deliberately NOT in the scraper registry and NOT a
row in the ``stores`` table — it feeds the catalog sync service
(``app.services.catalog_sync``), which upserts series + volumes.

Data sources (all public, no authentication):

1. Catalog list (paginated): ``GET https://mangakol.com/manga/`` and
   ``?tab=popular&page=N&partial=true`` (HTML fragment). The default
   "popular" tab walks the WHOLE catalog ranked (verified 2026-09-11:
   20 pages x ~23 = 445 manga, the following page repeats the tail ->
   stop when no new slugs appear). Cards expose ``/manga/<slug>`` links
   and the display title (e.g. "Berserk (Athica)" — the parenthesized
   suffix is the local publisher, kept raw here; cleaning is the
   service's job).

2. Manga detail (SSR): ``GET /manga/<slug>`` — h1 first span = title,
   muted h2 below the h1 = original (foreign) title when present (e.g.
   "Tokyo Ghoul | 東京喰種トーキョーグール"), ``strong.text-secondary`` info
   rows (among them "Yerel Yayıncı"), and
   the volume grid (``div.mk-vol-item`` with ``data-volume-number`` and
   ``img.mk-vol-cover``). The SSR grid shows the FIRST 24 volumes only;
   longer series continue via the public fragment endpoint
   ``GET /manga/<id>/volumes/load-more?format=SingleVolume&pageIndex=N``
   (N starts at 2; N=0/1 repeat the first page — verified live: One Piece
   TR = 62 volumes over SSR + 2 fragment pages).

Behaviour mirrors the store scrapers: bounded pagination, per-source
throttle/retry from ``BaseScraper``, bot-wall fail-fast
(``looks_like_blocked_page`` -> ``ScraperError``).

robots.txt: ``Content-Signal: search=yes,ai-train=no,use=reference`` +
``Allow: /`` for regular clients (only auth/dashboard/search paths are
disallowed) — normal HTTP client access is permitted.

The scraper never writes to the database.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin

from .base import BaseScraper, ScraperError
from .common import looks_like_blocked_page

logger = logging.getLogger("yomiba.scraper.mangakol")

_LIST_CARD_ANCHOR = "p.mk-vol-card-wide-vol-title a[href]"
_SLANG_RE = re.compile(r"^/manga/([a-z0-9][a-z0-9-]*)/?$", re.I)
_PUB_SUFFIX_RE = re.compile(r"^\s*(.*)\s*\(([^()]+)\)\s*$")
_PUB_SUFFIX_MIN_LEN = 2
_PUB_MIN_MATCH_LEN = 3


@dataclass(frozen=True)
class CatalogMangaRef:
    """A manga entry from the catalog list (before the detail page)."""

    slug: str
    title: str  # raw display title, e.g. "Berserk (Athica)"


@dataclass(frozen=True)
class CatalogVolume:
    """One volume row from a manga detail page.

    ``number`` is None for unnumbered items (sync maps it to
    ``UNNUMBERED_VOLUME``).
    """

    number: int | None
    cover_url: str | None
    #: Original-volume span of a 2-in-1 / 3-in-1 book ((9, 10) for
    #: "Dragon Ball 9&10"); None for single-volume books.
    covers: tuple[int, int] | None = None
    #: Absolute URL of the volume's own page (carries the ISBN).
    url: str | None = None
    #: False for announced volumes ("Yakında"): no ISBN published yet.
    released: bool = True


@dataclass(frozen=True)
class CatalogManga:
    """A manga's detail-page data (catalog sync input)."""

    slug: str
    title: str
    local_publisher: str | None
    volumes: list[CatalogVolume]
    #: Raw original (foreign) title line from the detail page, e.g.
    #: "Tokyo Ghoul | 東京喰種トーキョーグール" — None when the page has none.
    original_title: str | None = None
    #: "Yazar" / "Çizer" info rows; None when the page has none.
    author: str | None = None
    illustrator: str | None = None


@dataclass(frozen=True)
class CatalogVolumeDetails:
    """A volume page's info rows (each None when the page lacks it)."""

    isbn: str | None = None
    page_count: int | None = None
    release_date: date | None = None


_TR_MONTHS = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
    "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
}


def parse_tr_date(value: str | None) -> date | None:
    """"22 Haziran 2023" -> date(2023, 6, 22); None when not a full date."""
    from ..normalization import normalize_text

    parts = normalize_text(value).split()
    if len(parts) != 3 or not parts[0].isdigit() or not parts[2].isdigit():
        return None
    month = _TR_MONTHS.get(parts[1])
    if month is None:
        return None
    try:
        return date(int(parts[2]), month, int(parts[0]))
    except ValueError:
        return None


class MangakolCatalogScraper(BaseScraper):
    source_id = "mangakol"
    source_name = "Mangakol"
    base_url = "https://mangakol.com"

    # -- catalog list -----------------------------------------------------------
    def list_manga(self) -> list[CatalogMangaRef]:
        max_pages = max(1, self.settings.mangakol_max_list_pages)
        refs: list[CatalogMangaRef] = []
        seen_slugs: set[str] = set()

        for page in range(1, max_pages + 1):
            url = f"{self.base_url}/manga/"
            if page > 1:
                url += f"?tab=popular&page={page}&partial=true"
            response = self.get(url)
            if looks_like_blocked_page(response.status_code, response.text):
                raise ScraperError(
                    f"mangakol: catalog list blocked or robot-checked "
                    f"(HTTP {response.status_code}) on page {page}"
                )
            if response.status_code >= 400:
                if page == 1:
                    raise ScraperError(
                        f"mangakol: catalog list HTTP {response.status_code} for {url}"
                    )
                logger.warning(
                    "mangakol: list page %s failed (HTTP %s); keeping %s manga",
                    page, response.status_code, len(refs),
                )
                break

            soup = self.soup(response.text)
            new_on_page = 0
            for anchor in soup.select(_LIST_CARD_ANCHOR):
                href = anchor.get("href") or ""
                match = _SLANG_RE.match(href)
                if not match:
                    continue
                slug = match.group(1).lower()
                if slug in seen_slugs:
                    continue
                title = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))
                if not title:
                    continue
                seen_slugs.add(slug)
                refs.append(CatalogMangaRef(slug=slug, title=title))
                new_on_page += 1

            # The tab wraps its tail when the catalog is exhausted (page N+1
            # repeats the last N cards) -> no new slugs is the stop signal.
            if new_on_page == 0:
                break
        return refs

    # -- manga detail -----------------------------------------------------------
    def fetch_manga(self, slug: str) -> CatalogManga:
        response = self.get(f"{self.base_url}/manga/{slug}")
        if looks_like_blocked_page(response.status_code, response.text):
            raise ScraperError(
                f"mangakol: detail page blocked or robot-checked "
                f"(HTTP {response.status_code}) for /manga/{slug}"
            )
        if response.status_code >= 400:
            raise ScraperError(
                f"mangakol: detail page HTTP {response.status_code} for /manga/{slug}"
            )
        soup = self.soup(response.text)

        title_el = soup.select_one("h1 > span")
        title = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True)) if title_el else ""

        # The original (foreign) title is the muted h2 right below the h1,
        # e.g. "Tokyo Ghoul | 東京喰種トーキョーグール". Not every detail page
        # has one — it is optional.
        original_title = None
        if title_el is not None:
            h1_el = title_el.find_parent("h1")
            h2_el = h1_el.find_next("h2") if h1_el is not None else None
            if h2_el is not None:
                original_title = re.sub(r"\s+", " ", h2_el.get_text(" ", strip=True)).strip() or None

        info = self._info_rows(soup)
        local_publisher = info.get("yerel yayıncı") or info.get("yerel yayinci")

        volumes = self._volume_items(soup)
        if len(volumes) >= self._SSR_VOLUME_PAGE_SIZE:
            # Possibly truncated: follow the public load-more fragment
            # endpoint (pageIndex starts at 2; 0/1 repeat the first page).
            manga_id = self._manga_id(soup)
            if manga_id:
                volumes = self._load_more_volumes(manga_id, volumes)
        return CatalogManga(
            slug=slug,
            title=title,
            local_publisher=local_publisher,
            volumes=volumes,
            original_title=original_title,
            author=info.get("yazar") or None,
            illustrator=info.get("cizer") or None,
        )

    #: The SSR detail grid shows at most this many volumes per page.
    _SSR_VOLUME_PAGE_SIZE = 24

    # -- parsing helpers ---------------------------------------------------------
    @staticmethod
    def _info_rows(soup) -> dict[str, str]:
        """Map normalized info-row label -> value (e.g. 'Yerel Yayıncı' -> 'Athica')."""
        from ..normalization import normalize_text

        rows: dict[str, str] = {}
        for strong in soup.select("strong.text-secondary"):
            label = strong.get_text(" ", strip=True).rstrip(":").strip()
            parent = strong.find_parent("span")
            if parent is None or not label:
                continue
            value = parent.get_text(" ", strip=True)
            value = value[len(strong.get_text(" ", strip=True)):].strip(" :")
            rows[normalize_text(label)] = value
        return rows

    @staticmethod
    def _manga_id(soup) -> str | None:
        el = soup.select_one("[data-manga-id]")
        if el is None:
            return None
        value = el.get("data-manga-id")
        return value if value and value.isdigit() else None

    @classmethod
    def _volume_items(cls, soup) -> list[CatalogVolume]:
        volumes: list[CatalogVolume] = []
        for item in soup.select("div.mk-vol-item"):
            number: int | None = None
            button = item.select_one("[data-volume-number]")
            if button is not None:
                raw = (button.get("data-volume-number") or "").strip()
                if raw.lstrip("-").isdigit():
                    number = int(raw)
            if number is None:
                badge = item.select_one(".mk-vol-badge")
                if badge is not None:
                    match = re.search(r"(\d+)", badge.get_text(" ", strip=True))
                    if match:
                        number = int(match.group(1))
            img = item.select_one("img.mk-vol-cover")
            cover = img.get("src") if img is not None else None
            if cover and not cover.startswith(("http://", "https://")):
                cover = urljoin(cls.base_url + "/", cover)
            link = item.select_one("a.mk-vol-card-link")
            href = (link.get("href") or "").strip() if link is not None else ""
            released = "yakında" not in item.get_text(" ", strip=True).lower()
            volumes.append(CatalogVolume(
                number=number, cover_url=cover or None, covers=cls._covers(item, img),
                url=urljoin(cls.base_url + "/", href) if href else None,
                released=released,
            ))
        return volumes

    _ISBN_RE = re.compile(r"ISBN:\s*</strong>\s*([0-9Xx][0-9Xx\- ]{8,20})", re.I)

    def fetch_volume_details(self, url: str) -> CatalogVolumeDetails | None:
        """ISBN, page count and local release date from a volume page's info
        rows ("ISBN: 9786258237337", "Sayfa Sayısı: 388", "Yayın Tarihi
        (Yerel): 22 Haziran 2023"). None when the page is missing; raises
        ScraperError when blocked."""
        from ..normalization import normalize_isbn

        response = self.get(url)
        if looks_like_blocked_page(response.status_code, response.text):
            raise ScraperError(f"mangakol: volume page blocked (HTTP {response.status_code}) {url}")
        if response.status_code >= 400:
            return None
        match = self._ISBN_RE.search(response.text)
        info = self._info_rows(self.soup(response.text))
        pages = re.sub(r"\D", "", info.get("sayfa sayisi", ""))
        return CatalogVolumeDetails(
            isbn=normalize_isbn(match.group(1)) if match else None,
            page_count=int(pages) if pages and 0 < int(pages) < 10000 else None,
            release_date=parse_tr_date(info.get("yayin tarihi yerel")),
        )

    def fetch_volume_isbn(self, url: str) -> str | None:
        """ISBN from a volume page ("ISBN: 9786258237337"); None when absent."""
        details = self.fetch_volume_details(url)
        return details.isbn if details else None

    @staticmethod
    def _covers(item, img) -> tuple[int, int] | None:
        """Span of an omnibus volume: ``data-binding-format="TwoInOne"``
        (or ThreeInOne) plus the volume label "Dragon Ball 9&10"."""
        from ..normalization import parse_volume_range

        binding = (item.get("data-binding-format") or "").lower()
        if "inone" not in binding:
            return None
        title_el = item.select_one(".mk-vol-title")
        label = (title_el.get("title") or title_el.get_text(" ", strip=True)) if title_el else None
        if not label and img is not None:
            label = img.get("alt")
        span = parse_volume_range(label)
        return (span.first, span.last) if span else None

    def _load_more_volumes(
        self, manga_id: str, volumes: list[CatalogVolume]
    ) -> list[CatalogVolume]:
        """Follow the volume fragment pages until the grid is exhausted."""
        max_pages = max(1, self.settings.mangakol_max_volume_pages)
        known_numbers: set[int] = {v.number for v in volumes if v.number is not None}
        page = 2
        while page <= max_pages + 1:
            url = (
                f"{self.base_url}/manga/{manga_id}/volumes/load-more"
                f"?format=SingleVolume&pageIndex={page}&sortDesc=false"
            )
            try:
                response = self.get(url)
            except ScraperError as exc:
                logger.warning(
                    "mangakol: volume page %s for manga %s failed (%s); "
                    "keeping %s volumes", page, manga_id, exc, len(volumes),
                )
                break
            if response.status_code >= 400 or looks_like_blocked_page(
                response.status_code, response.text
            ):
                logger.warning(
                    "mangakol: volume page %s for manga %s blocked/failed "
                    "(HTTP %s); keeping %s volumes",
                    page, manga_id, response.status_code, len(volumes),
                )
                break

            fresh = self._volume_items(self.soup(response.text))
            new_here = 0
            for volume in fresh:
                if volume.number is not None:
                    if volume.number in known_numbers:
                        continue
                    known_numbers.add(volume.number)
                volumes.append(volume)
                new_here += 1

            if not fresh or new_here == 0 or len(fresh) < self._SSR_VOLUME_PAGE_SIZE:
                break
            page += 1
        return volumes
