"""Self-hosted volume covers.

Pages never hot-link an external image. A cover is downloaded ONCE from a
source candidate, checked to look like a book cover, resized to WebP and
written to our own storage; browsers load it from ``COVER_PUBLIC_BASE``.

Sources (``cover_source`` records which one won):
  * Mangakol's catalog image (``COVER_ALLOW_MANGAKOL``), full size rather
    than its thumbnail — tried FIRST with ``COVER_PREFER_MANGAKOL`` (the
    owner's choice, 2026-09-29), otherwise last;
  * the volume's store product images (``store_listings.image_url``), in
    ``STORE_PRIORITY`` order, larger CDN rendition first;
  * the volume's catalog ``cover_url`` when it is NOT a Mangakol image
    (a store image the importer back-filled).

Provisional covers: before a volume is out, the only image is usually the
Japanese original (Mangakol shows it for "Yakında" volumes, pre-order
pages often do too). A cover stored then is marked ``cover_provisional``.
Mangakol's image taken in the first ``MANGAKOL_SETTLE`` days after release
counts as provisional too (Mangakol may not have swapped it yet). Once the
volume is out (catalog release date passed / no longer "Yakında")
it is looked at again daily, for ``PROVISIONAL_GIVE_UP`` after release, and
replaced by the first candidate that is a different image from a different
source URL than the stored one (``cover_origin_url``): a store's product
photo or a new Mangakol image. The catalog sync re-queues a volume when
Mangakol swaps its image for a recently released volume.

Storage is behind :class:`CoverStore`. ``LocalCoverStore`` writes into a
directory (on Railway: next to the SQLite DB on the mounted volume) and the
``/covers/{key}`` route serves it. An object store (Cloudflare R2 / S3) is
another implementation of the same three methods whose ``public_url``
points at its CDN; nothing else changes. Keys are content-addressed
(``v/<volume id>-<sha>.webp``), so URLs can be cached forever.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings, get_settings
from ..models import CatalogSeries, Store, StoreListing, Volume
from ..utils import utcnow

logger = logging.getLogger("yomiba.covers")

KEY_RE = re.compile(r"^v/\d+-[0-9a-f]{12}\.webp$")
#: Store images tried first to last (sharpest / most reliable first).
STORE_PRIORITY = (
    "bkm", "kitapsepeti", "gerekliseyler", "komikseyler", "kitapsec",
    "edessa", "kitapbulan", "dr", "cizman", "amazon",
)
MANGAKOL_HOSTS = ("mangakol.com",)
#: A source that failed is tried again after this long.
RETRY_AFTER = timedelta(days=7)
#: A provisional cover of a volume that is out is looked at again this often…
PROVISIONAL_RETRY_AFTER = timedelta(days=1)
#: …until this long after the volume's release date.
PROVISIONAL_GIVE_UP = timedelta(days=120)
#: Mangakol may keep the announcement (Japanese) image for a while after
#: release: its image taken this soon after release is provisional too.
MANGAKOL_SETTLE = timedelta(days=14)
MAX_IMAGE_BYTES = 6 * 1024 * 1024
COVER_WIDTH = 480


# -- storage ------------------------------------------------------------------------------

class CoverStore(Protocol):
    def save(self, key: str, data: bytes, content_type: str) -> None: ...
    def public_url(self, key: str) -> str: ...
    #: Local file for the ``/covers`` route; None for stores that serve
    #: their files themselves (object storage / CDN).
    def local_path(self, key: str) -> Path | None: ...


class LocalCoverStore:
    def __init__(self, root: Path, public_base: str) -> None:
        self.root = root.resolve()
        self.public_base = public_base.rstrip("/")

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic: a reader never sees half a file

    def public_url(self, key: str) -> str:
        return f"{self.public_base}/{key}"

    def local_path(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.is_file() else None

    def _path(self, key: str) -> Path:
        if not KEY_RE.match(key):
            raise ValueError(f"invalid cover key {key!r}")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"cover key escapes the store: {key!r}")
        return path


def default_covers_dir(settings: Settings) -> Path:
    if settings.covers_dir:
        return Path(settings.covers_dir)
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        return Path(url.database).resolve().parent / "covers"
    return Path("covers").resolve()


_stores: dict[tuple, CoverStore] = {}


def get_cover_store(settings: Settings | None = None) -> CoverStore:
    settings = settings or get_settings()
    if settings.cover_storage != "local":
        # e.g. "r2": implement CoverStore with an S3 client + CDN base URL.
        raise RuntimeError(f"unsupported COVER_STORAGE={settings.cover_storage!r}")
    ident = ("local", str(default_covers_dir(settings)), settings.cover_public_base)
    if ident not in _stores:
        _stores[ident] = LocalCoverStore(default_covers_dir(settings), settings.cover_public_base)
    return _stores[ident]


def cover_url(key: str | None) -> str | None:
    """Public URL of a stored cover; None when the volume has none yet."""
    return get_cover_store().public_url(key) if key else None


# -- image processing ------------------------------------------------------------------------

def to_cover_webp(data: bytes) -> bytes | None:
    """Validate an image as a plausible book cover and return a WebP copy
    (``COVER_WIDTH`` wide at most). None for non-images, tiny thumbnails,
    and shapes no book cover has (banners, squares-ish logos)."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            width, height = img.size
            if width < 100 or height < 140 or not 0.45 <= width / height <= 0.9:
                return None
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                paper = Image.new("RGB", img.size, (255, 255, 255))
                paper.paste(img, mask=img.split()[-1])
                img = paper
            elif img.mode != "RGB":
                img = img.convert("RGB")
            if width > COVER_WIDTH:
                img = img.resize((COVER_WIDTH, round(height * COVER_WIDTH / width)), Image.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=82, method=6)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        return None


# -- fetching ------------------------------------------------------------------------------------

Download = Callable[[str], bytes | None]


def http_download(settings: Settings | None = None) -> Download:
    """Polite image download: store UA, per-host spacing, size cap."""
    settings = settings or get_settings()
    client = httpx.Client(
        headers={"User-Agent": settings.http_user_agent, "Accept": "image/avif,image/webp,image/*;q=0.8"},
        timeout=15.0,
        follow_redirects=True,
    )
    last_hit: dict[str, float] = {}

    def download(url: str) -> bytes | None:
        host = urlparse(url).netloc
        spacing = 0.6 if _is_mangakol(url) else 0.3  # gentler on the catalog source
        wait = last_hit.get(host, 0.0) + spacing - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        last_hit[host] = time.monotonic()
        try:
            response = client.get(url)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        if not response.headers.get("content-type", "").startswith("image/"):
            return None
        if len(response.content) > MAX_IMAGE_BYTES:
            return None
        return response.content

    return download


@dataclass
class CoverFetchReport:
    volumes: int = 0
    downloads: int = 0
    stored: int = 0
    without_source: int = 0
    #: Provisional (pre-release) covers replaced by a new image.
    replaced: int = 0
    #: Store covers forgotten (listing gone / volume not out).
    dropped: int = 0
    remaining: int = 0


#: IdeaSoft/WAW product images (BKM, Kitap Sepeti): "-K" is the 175x250
#: list thumbnail, "-B" the 320x457 product image (live-checked 2026-09-29).
_IDEASOFT_SMALL_RE = re.compile(r"-K(\.(?:jpe?g|png|webp))$", re.I)


def larger_variants(url: str) -> list[str]:
    """``url`` preceded by a larger rendition of the same image when the
    store's CDN has a known size suffix; a missing variant just 404s and the
    original is tried next."""
    if _IDEASOFT_SMALL_RE.search(url):
        return [_IDEASOFT_SMALL_RE.sub(r"-B\1", url), url]
    # Mangakol: ".../mangavolume/thumbnails/x.webp" is the 250 px thumbnail,
    # ".../mangavolume/x.webp" the full-size scan (500-1350 px).
    if _is_mangakol(url) and "/thumbnails/" in url:
        return [url.replace("/thumbnails/", "/", 1), url]
    return [url]


def volume_is_out(volume: Volume, today: date | None = None) -> bool:
    """The volume is on sale in Turkey: not "Yakında" in the catalog and its
    release date (when known) is not in the future."""
    if volume.catalog_released is False:
        return False
    today = today or utcnow().date()
    return volume.release_date is None or volume.release_date <= today


def is_provisional(volume: Volume, source: str | None, stored_on: date | None = None) -> bool:
    """Whether a cover from ``source`` stored on ``stored_on`` (today) is
    likely the Japanese original rather than the Turkish cover."""
    stored_on = stored_on or utcnow().date()
    if not volume_is_out(volume, stored_on):
        return True
    return (source == "mangakol" and volume.release_date is not None
            and stored_on < volume.release_date + MANGAKOL_SETTLE)


def is_mangakol_url(url: str | None) -> bool:
    return bool(url) and _is_mangakol(url)


def _is_mangakol(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in MANGAKOL_HOSTS)


class CoverFetcher:
    def __init__(self, session: Session, *, store: CoverStore | None = None,
                 download: Download | None = None, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.store = store or get_cover_store(self.settings)
        self.download = download or http_download(self.settings)

    def candidates(self, volume: Volume) -> list[tuple[str, str]]:
        """(source tag, url) in trial order; see the module docstring."""
        return [(tag, url) for tag, url, _ in self._sources(volume)]

    def _sources(self, volume: Volume) -> list[tuple[str, str, str]]:
        """(source tag, url, origin url) — the origin is the source's own URL
        before :func:`larger_variants`, recorded as ``cover_origin_url``."""
        rank = {code: i for i, code in enumerate(STORE_PRIORITY)}
        listings = self.session.execute(
            select(Store.code, StoreListing.image_url)
            .join(Store, Store.id == StoreListing.store_id)
            .where(StoreListing.volume_id == volume.id, StoreListing.image_url.isnot(None))
        ).all()
        out: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        # A store "selling" a volume that is not out in Turkey is a foreign
        # edition (Kitapbulan's English Fairy Tail, 2026-10): before release
        # only the catalog's own (Mangakol) image is used.
        is_out = volume_is_out(volume)
        if not is_out:
            listings = []
        for code, url in sorted(listings, key=lambda r: rank.get(r[0], len(rank))):
            if url and url.startswith(("http://", "https://")) and url not in seen and not _is_mangakol(url):
                for variant in larger_variants(url):
                    if variant not in seen:
                        out.append((f"store:{code}", variant, url))
                        seen.add(variant)
                seen.add(url)
        mangakol: list[tuple[str, str, str]] = []
        if volume.cover_url and volume.cover_url not in seen:
            if not _is_mangakol(volume.cover_url):
                if is_out:  # else: a store image the importer back-filled
                    out.append(("catalog", volume.cover_url, volume.cover_url))
            elif self.settings.cover_allow_mangakol:
                mangakol = [("mangakol", u, volume.cover_url) for u in larger_variants(volume.cover_url)]
        return mangakol + out if self.settings.cover_prefer_mangakol else out + mangakol

    def _pending(self):
        now = utcnow()
        today = now.date()
        missing = and_(
            Volume.cover_key.is_(None),
            (Volume.cover_checked_at.is_(None)) | (Volume.cover_checked_at < now - RETRY_AFTER),
        )
        # A pre-release cover of a volume that is out now (see volume_is_out).
        provisional = and_(
            Volume.cover_key.isnot(None),
            Volume.cover_provisional.is_(True),
            or_(Volume.catalog_released.is_(None), Volume.catalog_released.is_(True)),
            or_(Volume.release_date.is_(None), and_(
                Volume.release_date <= today,
                Volume.release_date >= today - PROVISIONAL_GIVE_UP,
            )),
            (Volume.cover_checked_at.is_(None)) | (Volume.cover_checked_at < now - PROVISIONAL_RETRY_AFTER),
        )
        return (
            select(Volume)
            .where(
                Volume.volume_number >= 0,
                Volume.series_id.in_(select(CatalogSeries.series_id)),
                or_(missing, provisional),
            )
        )

    def drop_orphan_store_covers(self) -> int:
        """Forget store covers whose listing is gone (deleted as a wrong
        match, cleanup_stale_listings.py) and store / back-filled covers of
        volumes that are not out (a foreign edition, see ``_sources``): the
        volume is fetched again from its remaining sources."""
        listing_left = exists().where(
            StoreListing.volume_id == Volume.id,
            StoreListing.store_id == Store.id,
            Store.code == func.substr(Volume.cover_source, 7),
        )
        today = utcnow().date()
        not_out = or_(Volume.catalog_released.is_(False), Volume.release_date > today)
        from_store = Volume.cover_source.like("store:%")
        volumes = self.session.scalars(select(Volume).where(
            Volume.cover_key.isnot(None),
            or_(
                and_(from_store, ~listing_left),
                and_(or_(from_store, Volume.cover_source == "catalog"), not_out),
            ),
        )).all()
        for volume in volumes:
            logger.info("covers: dropping %s cover of volume %s", volume.cover_source, volume.id)
            volume.cover_key = volume.cover_source = volume.cover_origin_url = None
            volume.cover_provisional = volume.cover_checked_at = None
        if volumes:
            self.session.commit()
        return len(volumes)

    def run(self, budget: int) -> CoverFetchReport:
        """Store covers for pending volumes; ``budget`` caps downloads.
        Volumes with store offers go first (they are the ones on pages).
        A provisional cover is replaced only by a different image from a
        different source URL; it stays until one turns up."""
        report = CoverFetchReport()
        report.dropped = self.drop_orphan_store_covers()
        has_listing = exists().where(StoreListing.volume_id == Volume.id)
        queue = self.session.scalars(
            self._pending().order_by(has_listing.desc(), Volume.series_id, Volume.volume_number)
        ).all()
        for volume in queue:
            if report.downloads >= budget:
                break
            report.volumes += 1
            replacing = volume.cover_key is not None
            sources = self._sources(volume)
            if replacing:
                sources = [s for s in sources if s[2] != volume.cover_origin_url]
            if not sources:
                report.without_source += 1
            for tag, url, origin in sources:
                if report.downloads >= budget:
                    break
                report.downloads += 1
                raw = self.download(url)
                webp = to_cover_webp(raw) if raw else None
                if webp is None:
                    continue
                key = f"v/{volume.id}-{hashlib.sha256(webp).hexdigest()[:12]}.webp"
                if key == volume.cover_key:
                    continue  # the same picture under another address
                self.store.save(key, webp, "image/webp")
                volume.cover_key, volume.cover_source, volume.cover_origin_url = key, tag, origin
                # A replacement is a new image after release: the Turkish one.
                volume.cover_provisional = (not volume_is_out(volume)) if replacing else is_provisional(volume, tag)
                report.stored += 1
                report.replaced += replacing
                break
            volume.cover_checked_at = utcnow()
            self.session.commit()
        report.remaining = self.session.scalar(select(func.count()).select_from(self._pending().subquery())) or 0
        logger.info("covers: %s", report)
        return report


# -- background worker -------------------------------------------------------------------------------

class CoverWorker:
    """Fills covers in the background: a pass shortly after start, then one
    per interval — sooner while a backlog is still shrinking (fresh deploy).
    ``trigger()`` runs a pass now (admin)."""

    def __init__(self, session_factory: sessionmaker[Session], *, settings: Settings | None = None,
                 start_delay: float = 30.0, backlog_pause: float = 60.0,
                 fetcher_factory: Callable[[Session], CoverFetcher] | None = None,
                 name: str = "cover-worker", budget: int | None = None) -> None:
        self.settings = settings or get_settings()
        self._sessions = session_factory
        self._start_delay = start_delay
        self._backlog_pause = backlog_pause
        self._fetcher_factory = fetcher_factory or (lambda s: CoverFetcher(s, settings=self.settings))
        #: The same loop also runs other page-fetching passes
        #: (volume_descriptions.DescriptionFetcher) under their own name/budget.
        self._name = name
        self._budget = budget
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.running = False
        self.last: dict | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def trigger(self) -> bool:
        """Ask for a pass now; False when one is already running."""
        if self.running:
            return False
        self._wake.set()
        return True

    def run_once(self) -> CoverFetchReport:
        with self._lock:
            self.running = True
            try:
                with self._sessions() as session:
                    report = self._fetcher_factory(session).run(
                        self.settings.cover_fetch_budget if self._budget is None else self._budget)
                self.last = {**report.__dict__, "finished_at": utcnow().isoformat()}
                return report
            finally:
                self.running = False

    def _loop(self) -> None:
        delay = self._start_delay
        while not self._stop.is_set():
            self._wake.wait(delay)
            self._wake.clear()
            if self._stop.is_set():
                return
            try:
                report = self.run_once()
                shrinking = report.stored > 0 and report.remaining > 0
            except Exception:  # noqa: BLE001 - the worker must not die
                logger.exception("%s: pass failed", self._name)
                shrinking = False
            delay = self._backlog_pause if shrinking else self.settings.cover_fetch_interval_minutes * 60
