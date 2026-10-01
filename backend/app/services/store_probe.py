"""Store access test (admin): can THIS server reach a store?

Research probes from a developer machine are not enough: Cizman answers a
home connection but returns Cloudflare 403 to the Railway server. Before a
new store is integrated (Kitapyurdu, idefix, ...) its search and product
pages are fetched once from the production server, the way a scraper would.

Plain requests only — the app's normal User-Agent, no cookies, no retries,
one request per second. A wall (403/429/503, a challenge page, a WAF
rejection) is recorded, never worked around.

Each probe reports: HTTP status, size, time, wall marker, how many
distinct "Berserk N" / "Frieren N" volumes the search page shows (server-
rendered data), and whether a known volume ISBN is on the product page.
The job runs in a background thread; the admin polls its status.
"""

from __future__ import annotations

import html
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field

import httpx

from ..config import get_settings
from ..scrapers.common import has_block_marker
from ..utils import utcnow

logger = logging.getLogger("yomiba.store_probe")


def _volume_hits(term: str, text: str) -> int:
    """Distinct volumes of ``term`` a page shows when it carries real
    results: "Berserk 12", "Berserk Cilt 3", "Vanitas'ın Anı Defteri Cilt 5"."""
    pattern = re.compile(re.escape(term) + r"[^<>\d]{0,30}?(?:cilt\W{0,3})?0*(\d{1,2})\b", re.I)
    return len({int(m.group(1)) for m in pattern.finditer(html.unescape(text))})

#: Wall pages that has_block_marker (visible-text markers) does not know.
_EXTRA_WALL = re.compile(
    r"<title>\s*Just a moment|cf-chl|The requested URL was rejected|Attention Required",
    re.I,
)
_WALL_STATUS = {403, 429, 503, 511, 999}


@dataclass(frozen=True)
class Candidate:
    code: str
    name: str
    #: "aktif" (imported today), "kapalı" (disabled store), "aday" (new
    #: candidate), "metadata" (series information, not prices).
    group: str
    url: str
    product_url: str | None = None
    #: ISBN the product page must show (proves product data is readable).
    isbn: str | None = None
    note: str = ""
    #: Series the search URL looks for (its volumes are counted).
    term: str = "berserk"
    method: str = "GET"
    json: dict | None = None


_ANILIST_QUERY = {
    "query": "query{Media(search:\"Look Back\",type:MANGA){id format status volumes}}"
}

CANDIDATES: tuple[Candidate, ...] = (
    # -- stores imported today ----------------------------------------------------
    Candidate("bkm", "BKM Kitap", "aktif",
              "https://cdn.bkmkitap.com/srv/service/product/searchAll/berserk?language=tr"),
    Candidate("kitapsepeti", "Kitap Sepeti", "aktif", "https://www.kitapsepeti.com/arama?q=berserk"),
    Candidate("kitapbulan", "Kitapbulan", "aktif", "https://www.kitapbulan.com/arama?q=berserk"),
    Candidate("gerekliseyler", "Gerekli Şeyler", "aktif", "https://www.gerekliseyler.com.tr/arama/berserk"),
    Candidate("kitapsec", "Kitapseç", "aktif", "https://www.kitapsec.com/Arama/index.php?a=berserk"),
    Candidate("komikseyler", "Komikşeyler", "aktif",
              "https://komikseyler.com.tr/wp-json/wc/store/v1/products?search=vanitas&per_page=20",
              term="vanitas"),
    Candidate("edessa", "Edessa Kitabevi", "aktif", "https://edessakitabevi.com/frieren-cilt-6",
              isbn="9786256327726", term="frieren", note="arama JS ile; ürün sayfası test edilir"),
    # -- disabled stores ----------------------------------------------------------
    Candidate("cizman", "Cizman", "kapalı", "https://www.cizman.com/berserk-19",
              isbn="9786258858068", note="Cloudflare 403 yüzünden kapatıldı; arama POST, ürün sayfası test edilir"),
    Candidate("amazon", "Amazon TR", "kapalı", "https://www.amazon.com.tr/s?k=berserk"),
    Candidate("dr", "D&R", "kapalı", "https://www.dr.com.tr/arama?q=berserk"),
    # -- new candidates (docs/veri-kaynaklari-arastirmasi-2026-10-01.md) ----------------
    Candidate("kitapyurdu", "Kitapyurdu", "aday",
              "https://www.kitapyurdu.com/index.php?route=product/search&filter_name=berserk",
              "https://www.kitapyurdu.com/kitap/berserk-1/696554.html", "9786256335424"),
    Candidate("idefix", "idefix (D&R, BKM satıcıları)", "aday",
              "https://www.idefix.com/manga-c-330731344",
              "https://www.idefix.com/athica-yayinlari-berserk-cilt-1-p-3186465", "9786256335424",
              note="arama WAF'ta; manga kategorisi taranır"),
    Candidate("buyuludukkan", "Büyülü Dükkan", "aktif", "https://www.buyuludukkan.com.tr/arama/berserk",
              "https://www.buyuludukkan.com.tr/urun/berserk-cilt-18", "9786258858051"),
    Candidate("istanbulkitapcisi", "İstanbul Kitapçısı", "aktif",
              "https://www.istanbulkitapcisi.com/arama?q=berserk",
              "https://www.istanbulkitapcisi.com/berserk-12", "9786255610553"),
    Candidate("ucuzkitapal", "Ucuzkitapal", "aday",  # 2026-10-01: every manga sold out
              "https://www.ucuzkitapal.com/?dispatch=products.search&q=berserk&search_performed=Y",
              "https://www.ucuzkitapal.com/berserk-1-kentaro-miura-athica-yayinlari/", "9786256335424"),
    Candidate("marmaracizgi", "Marmara Çizgi Dükkan", "aday",
              "https://dukkan.marmaracizgi.com.tr/arama?q=frieren",
              "https://dukkan.marmaracizgi.com.tr/frieren-cilt-6", "9786256327726", term="frieren"),
    Candidate("ekinkitap", "Ekin Kitap", "aday", "https://www.ekinkitap.com/arama?q=frieren",
              "https://www.ekinkitap.com/frieren-cilt-7", "9786256327733", term="frieren"),
    Candidate("arkabahce", "Arka Bahçe", "aday", "https://www.arkabahce.com.tr/arama?q=berserk"),
    Candidate("trendyol", "Trendyol", "aday", "https://www.trendyol.com/sr?q=berserk"),
    Candidate("n11", "n11", "aday", "https://www.n11.com/arama?q=berserk"),
    Candidate("hepsiburada", "Hepsiburada", "aday", "https://www.hepsiburada.com/ara?q=berserk"),
    # -- series information -----------------------------------------------------------
    Candidate("anilist", "AniList", "metadata", "https://graphql.anilist.co",
              method="POST", json=_ANILIST_QUERY, note="tür, etiket, ONE_SHOT"),
    Candidate("1000kitap", "1000Kitap", "metadata", "https://1000kitap.com/ara?q=berserk&bolum=kitaplar",
              "https://1000kitap.com/kitap/berserk-cilt-4--85494", "9786059520119",
              note="Türkçe özet, okur puanı"),
)


@dataclass
class Fetch:
    url: str
    status: int | None = None
    bytes: int = 0
    ms: int = 0
    final_host: str | None = None
    wall: bool = False
    error: str | None = None


@dataclass
class ProbeResult:
    code: str
    name: str
    group: str
    note: str
    search: Fetch
    hits: int = 0
    product: Fetch | None = None
    isbn_found: bool | None = None
    verdict: str = ""
    detail: str = ""
    extra: dict = field(default_factory=dict)


def _fetch(client: httpx.Client, url: str, method: str = "GET", json: dict | None = None) -> tuple[Fetch, str]:
    started = time.monotonic()
    fetch = Fetch(url=url)
    try:
        response = client.request(method, url, json=json)
    except httpx.HTTPError as exc:
        fetch.ms = int((time.monotonic() - started) * 1000)
        fetch.error = f"{type(exc).__name__}: {str(exc)[:120]}"
        return fetch, ""
    text = response.text
    fetch.ms = int((time.monotonic() - started) * 1000)
    fetch.status = response.status_code
    fetch.bytes = len(response.content)
    fetch.final_host = response.url.host
    fetch.wall = (
        response.status_code in _WALL_STATUS
        or has_block_marker(text)
        or bool(_EXTRA_WALL.search(text[:20000]))
        # Amazon's JavaScript wall: an empty 202.
        or (response.status_code == 202 and len(text.strip()) < 3000)
    )
    return fetch, text


def _verdict(result: ProbeResult) -> tuple[str, str]:
    search, product = result.search, result.product
    if search.error and (product is None or product.error):
        return "hata", search.error
    if search.wall or (product is not None and product.wall):
        where = "arama" if search.wall else "ürün sayfası"
        status = search.status if search.wall else product.status
        return "engelli", f"{where}: HTTP {status}"
    if result.code == "anilist":
        ok = result.extra.get("format") is not None
        return ("erişilebilir", f"format={result.extra.get('format')}") if ok else ("veri yok", f"HTTP {search.status}")
    data = result.hits > 0 or bool(result.isbn_found)
    if search.status == 200 and data:
        parts = []
        if result.hits:
            parts.append(f"{result.hits} cilt görüldü")
        if result.isbn_found is not None:
            parts.append("ISBN okundu" if result.isbn_found else "ISBN bulunamadı")
        return "erişilebilir", ", ".join(parts)
    if search.status == 200:
        return "veri yok", "sayfa açıldı ama sonuç/ISBN görünmüyor (JS ile olabilir)"
    return f"HTTP {search.status}", ""


def probe(candidate: Candidate, client: httpx.Client, pause: float) -> ProbeResult:
    search, text = _fetch(client, candidate.url, candidate.method, candidate.json)
    result = ProbeResult(candidate.code, candidate.name, candidate.group, candidate.note, search)
    result.hits = _volume_hits(candidate.term, text)
    if candidate.code == "anilist":
        match = re.search(r'"format"\s*:\s*"([A-Z_]+)"', text)
        result.extra["format"] = match.group(1) if match else None
    if candidate.isbn and candidate.product_url:
        time.sleep(pause)
        result.product, page = _fetch(client, candidate.product_url)
        digits = re.sub(r"\D", "", page)
        result.isbn_found = candidate.isbn in page or candidate.isbn in digits
    elif candidate.isbn:
        result.isbn_found = candidate.isbn in text
    result.verdict, result.detail = _verdict(result)
    return result


class StoreProbeJob:
    """One run at a time; results kept in memory for the admin."""

    def __init__(self, candidates: tuple[Candidate, ...] = CANDIDATES, pause: float = 1.0,
                 client_factory=None) -> None:
        self._candidates = candidates
        self._pause = pause
        self._client_factory = client_factory
        self._lock = threading.Lock()
        self.state = "idle"  # idle | running | done | failed
        self.results: list[ProbeResult] = []
        self.started_at = None
        self.finished_at = None
        self.error: str | None = None

    def status(self) -> dict:
        return {
            "state": self.state,
            "total": len(self._candidates),
            "done": len(self.results),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "results": [asdict(r) for r in self.results],
        }

    def start(self) -> bool:
        with self._lock:
            if self.state == "running":
                return False
            self.state, self.results, self.error = "running", [], None
            self.started_at, self.finished_at = utcnow(), None
        threading.Thread(target=self.run, name="store-probe", daemon=True).start()
        return True

    def _client(self) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory()
        settings = get_settings()
        return httpx.Client(
            headers={
                "User-Agent": settings.http_user_agent,
                "Accept-Language": settings.http_accept_language,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            },
            timeout=20.0,
            follow_redirects=True,
        )

    def run(self) -> None:
        try:
            with self._client() as client:
                for i, candidate in enumerate(self._candidates):
                    if i:
                        time.sleep(self._pause)
                    self.results.append(probe(candidate, client, self._pause))
            self.state = "done"
        except Exception as exc:  # noqa: BLE001 - reported to the admin
            logger.exception("store probe failed")
            self.state, self.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            self.finished_at = utcnow()
