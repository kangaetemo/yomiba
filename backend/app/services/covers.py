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
from datetime import timedelta
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy import exists, func, select
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
        rank = {code: i for i, code in enumerate(STORE_PRIORITY)}
        listings = self.session.execute(
            select(Store.code, StoreListing.image_url)
            .join(Store, Store.id == StoreListing.store_id)
            .where(StoreListing.volume_id == volume.id, StoreListing.image_url.isnot(None))
        ).all()
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for code, url in sorted(listings, key=lambda r: rank.get(r[0], len(rank))):
            if url and url.startswith(("http://", "https://")) and url not in seen and not _is_mangakol(url):
                for variant in larger_variants(url):
                    if variant not in seen:
                        out.append((f"store:{code}", variant))
                        seen.add(variant)
                seen.add(url)
        mangakol: list[tuple[str, str]] = []
        if volume.cover_url and volume.cover_url not in seen:
            if not _is_mangakol(volume.cover_url):
                out.append(("catalog", volume.cover_url))
            elif self.settings.cover_allow_mangakol:
                mangakol = [("mangakol", u) for u in larger_variants(volume.cover_url)]
        return mangakol + out if self.settings.cover_prefer_mangakol else out + mangakol

    def _pending(self):
        cutoff = utcnow() - RETRY_AFTER
        return (
            select(Volume)
            .where(
                Volume.cover_key.is_(None),
                Volume.volume_number >= 0,
                Volume.series_id.in_(select(CatalogSeries.series_id)),
                (Volume.cover_checked_at.is_(None)) | (Volume.cover_checked_at < cutoff),
            )
        )

    def run(self, budget: int) -> CoverFetchReport:
        """Store covers for pending volumes; ``budget`` caps downloads.
        Volumes with store offers go first (they are the ones on pages)."""
        report = CoverFetchReport()
        has_listing = exists().where(StoreListing.volume_id == Volume.id)
        queue = self.session.scalars(
            self._pending().order_by(has_listing.desc(), Volume.series_id, Volume.volume_number)
        ).all()
        for volume in queue:
            if report.downloads >= budget:
                break
            report.volumes += 1
            sources = self.candidates(volume)
            if not sources:
                report.without_source += 1
            for tag, url in sources:
                if report.downloads >= budget:
                    break
                report.downloads += 1
                raw = self.download(url)
                webp = to_cover_webp(raw) if raw else None
                if webp is None:
                    continue
                key = f"v/{volume.id}-{hashlib.sha256(webp).hexdigest()[:12]}.webp"
                self.store.save(key, webp, "image/webp")
                volume.cover_key, volume.cover_source = key, tag
                report.stored += 1
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
                 fetcher_factory: Callable[[Session], CoverFetcher] | None = None) -> None:
        self.settings = settings or get_settings()
        self._sessions = session_factory
        self._start_delay = start_delay
        self._backlog_pause = backlog_pause
        self._fetcher_factory = fetcher_factory or (lambda s: CoverFetcher(s, settings=self.settings))
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
        self._thread = threading.Thread(target=self._loop, name="cover-worker", daemon=True)
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
                    report = self._fetcher_factory(session).run(self.settings.cover_fetch_budget)
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
                logger.exception("covers: pass failed")
                shrinking = False
            delay = self._backlog_pause if shrinking else self.settings.cover_fetch_interval_minutes * 60
