"""Read public product pages only; no importer and no catalogue writes.

Retailer groups are explicit, not inferred from URL counts. Deployments can
collapse providers known to share a catalogue feed via ISBN_SOURCE_GROUPS.
Mangakol is discovery provenance and is deliberately not a voting provider.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import os
import re
import time
from urllib.parse import parse_qs, quote_plus, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from ..config import get_settings
from ..utils import naive_utcnow
from ..normalization.text import normalize_text
from ..normalization.volume import parse_volume_title
from ..scrapers.base import BaseScraper, ScraperError
from ..scrapers.bkm import BkmScraper
from ..scrapers.dr import DrScraper
from ..scrapers.mangakol import MangakolCatalogScraper
from ..scrapers.common import has_block_marker
from .isbn_identity import base_key, bibliographic_title, canonical_isbn, edition, identity_reason

HOSTS = {"www.kitapyurdu.com", "www.pandora.com.tr", "www.bkmkitap.com",
         "bkmkitap.com", "bkm-best.wawlabs.com", "cdn.bkmkitap.com", "www.dr.com.tr", "mangakol.com"}


class PoliteClient(httpx.Client):
    """Check robots before every destination, including redirects; fail closed."""
    def __init__(self):
        settings = get_settings()
        self.rules: dict[str, tuple[RobotFileParser | None, str | None]] = {}
        self.last: dict[str, float] = {}
        self.agent = settings.http_user_agent
        self.interval = max(1.0, settings.scraper_min_request_interval_seconds)
        super().__init__(headers={"User-Agent": self.agent, "Accept-Language": "tr-TR,tr;q=0.9"},
                         timeout=min(20, settings.http_timeout), follow_redirects=True,
                         event_hooks={"request": [self.check_request]})

    def check_request(self, request):
        host = request.url.host
        if request.url.scheme != "https" or host not in HOSTS:
            raise ScraperError(f"Kaynak izin verilen alan adının dışına yönlendirdi: {host}.")
        if host not in self.rules:
            try:
                # No redirect to an unchecked host, no proxy/bot-wall workaround.
                r = httpx.get(f"https://{host}/robots.txt", headers={"User-Agent": self.agent}, timeout=15)
                if r.status_code == 404:
                    lines = ["User-agent: *", "Allow: /"]
                elif r.status_code == 200 and not has_block_marker(r.text):
                    lines = r.text.splitlines()
                else:
                    raise ScraperError(f"robots.txt erişilemiyor (HTTP {r.status_code}).")
                parser = RobotFileParser()
                parser.parse(lines)
                self.rules[host] = (parser, None)
            except Exception as exc:
                self.rules[host] = (None, str(exc)[:300])
        parser, error = self.rules[host]
        if parser is None:
            raise ScraperError(error)
        if not parser.can_fetch(self.agent, str(request.url)):
            raise ScraperError("robots.txt bu isteğe izin vermiyor.")
        delay = max(self.interval, parser.crawl_delay(self.agent) or 0)
        wait = self.last.get(host, 0) + delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last[host] = time.monotonic()


def page_book(html: bytes | str, url: str) -> dict:
    """Only the primary product, never ISBNs in recommendation widgets."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.find("h1")
    book = dict(title=title.get_text(" ", strip=True) if title else "", url=url,
                publisher=None, language=None, binding=None, raw_isbns=[])
    nodes = BaseScraper.extract_json_ld(str(soup))
    products = [n for n in nodes if any(t in (n.get("@type") if isinstance(n.get("@type"), list)
                     else [n.get("@type")]) for t in ("Book", "Product"))]
    canonical_url = url.split("?")[0].rstrip("/")
    primary = [n for n in products if str(n.get("url") or n.get("@id") or "").split("#")[0].split("?")[0].rstrip("/") == canonical_url]
    if not primary and len(products) == 1:
        primary = products
    for node in primary:
        if node.get("name") and not book["title"]:
            book["title"] = node["name"]
        publisher = node.get("publisher") or node.get("brand")
        if publisher:
            book["publisher"] = publisher.get("name") if isinstance(publisher, dict) else str(publisher)
        book["language"] = node.get("inLanguage") or book["language"]
        book["binding"] = node.get("bookFormat") or book["binding"]
        for key in ("isbn", "gtin13", "gtin12", "gtin"):
            if node.get(key):
                book["raw_isbns"].append(str(node[key]))
    # Kitapyurdu's live primary bibliography, not page-wide text regexes.
    for row in soup.select(".ky-pd-attributes__item"):
        label, value = row.select_one(".ky-pd-attributes__label"), row.select_one(".ky-pd-attributes__value")
        if not label or not value:
            continue
        key, val = normalize_text(label.get_text()), value.get_text(" ", strip=True)
        if key == "isbn": book["raw_isbns"].append(val)
        elif key == "dil": book["language"] = val
        elif key == "cilt tipi": book["binding"] = val
    # Shared product-specification table used by existing store adapters.
    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) != 2:
            continue
        key, val = normalize_text(cells[0].get_text()), cells[1].get_text(" ", strip=True)
        if key in {"isbn", "isbn 13", "barkod", "barkod isbn"}: book["raw_isbns"].append(val)
        elif key in {"dil", "yayin dili"}: book["language"] = val
        elif key in {"cilt tipi", "kapak turu", "kapak tipi"}: book["binding"] = val
        elif key in {"yayinevi", "yayinci"}: book["publisher"] = val
    book["raw_isbns"] = sorted(set(book["raw_isbns"]))
    return book


def proof(source: str, group: str, target: dict, book: dict, now=None) -> dict:
    raw = book.get("raw_isbns", [])
    codes = {canonical_isbn(v) for v in raw}
    reason = identity_reason(target, book)
    if not raw:
        status, reason = "NO_ISBN", "Ürün bulundu; ISBN belirtilmemiş." + (f" {reason}" if reason else "")
    elif reason:
        status = "MISMATCH"
    elif len(codes) > 1:
        status, reason = "MISMATCH", "Kaynağın kendi ISBN alanları birbiriyle çelişiyor."
    elif None in codes:
        status, reason = "MISMATCH", "ISBN kontrol basamağı veya biçimi geçersiz."
    else:
        status, reason = "MATCH", "Seri, cilt, yayınevi, Türkçe dil ve baskı eşleşti."
    return dict(source=source, independence_group=group, status=status, isbn=next(iter(codes)) if len(codes) == 1 else None,
                reason=reason, checked_at=(now or naive_utcnow()).isoformat(), **book)


class RetailerSource:
    def __init__(self, code, group, client):
        self.code, self.group, self.client = code, group, client
        self.base = {"kitapyurdu": "https://www.kitapyurdu.com", "pandora": "https://www.pandora.com.tr",
                     "bkm": "https://www.bkmkitap.com", "dr": "https://www.dr.com.tr"}[code]

    def get(self, url):
        r = self.client.get(url)
        if r.status_code >= 400 or has_block_marker(r.text):
            raise ScraperError(f"HTTP {r.status_code}: kaynak erişim hatası / koruma sayfası.")
        return r

    def collect(self, target: dict) -> list[dict]:
        query = f'{bibliographic_title(target["title"]).strip()} {target["volume_number"]}'
        if target.get("covers_from") is not None:
            query = f'{target["title"]} {target["covers_from"]} {target["covers_to"]}'
        urls = {}
        if self.code in {"bkm", "dr"}:
            scraper = (BkmScraper if self.code == "bkm" else DrScraper)(client=self.client)
            # Query one volume; do not let detail enrichment silently become proof.
            scraper.settings = replace(scraper.settings, max_detail_requests=0)
            results = scraper.search(query)
            for item in results:
                if self.candidate(target, item.title):
                    # Both are BKM's own public product hostnames. The
                    # search feed uses the apex; the current site serves www.
                    url = item.product_url.replace("https://bkmkitap.com/", "https://www.bkmkitap.com/")
                    urls[url] = item.title
            if scraper.stats.get("stop_reason") in {"max_results", "max_pages", "page_error"}:
                raise ScraperError("Kaynak araması tamamlanamadı; sonuçlar eksik olabilir.")
        elif self.code == "kitapyurdu":
            pending = {1: f"{self.base}/index.php?route=product/search&filter_name={quote_plus(query)}"}
            seen, signatures = set(), set()
            while pending:
                page = min(pending)
                r = self.get(pending.pop(page))
                seen.add(page)
                soup = BeautifulSoup(r.content, "lxml")
                products = soup.select("a.ky-product-title[href*='/kitap/'], .product-cr .name a")
                if not products and "uygun urun bulunamadi" not in normalize_text(soup.get_text()):
                    raise ScraperError("Kaynak arama şablonu tanınmadı; yokluk varsayılmadı.")
                signature = tuple(sorted({urljoin(self.base, a["href"]).split("?")[0] for a in products}))
                if signature and signature in signatures:
                    raise ScraperError("Kaynak sayfalaması aynı ürünleri tekrarlıyor; arama tamamlanamadı.")
                signatures.add(signature)
                for a in products:
                    title = a.get_text(" ", strip=True)
                    if self.candidate(target, title): urls[urljoin(self.base, a["href"]).split("?")[0]] = title
                # Follow actual public pagination URLs, including numeric-only
                # links (the current site has no rel=next or pagination class).
                for a in soup.select("a[href]"):
                    link = urljoin(self.base, a["href"])
                    parsed = urlsplit(link)
                    params = parse_qs(parsed.query)
                    number = params.get("page", [""])[0]
                    if (parsed.scheme == "https" and parsed.hostname == "www.kitapyurdu.com"
                            and params.get("route") == ["product/list"] and params.get("filter_name") == [query]
                            and number.isdigit() and int(number) > 0 and int(number) not in seen):
                        pending[int(number)] = link
                if len(seen) + len(pending) > 1000:
                    raise ScraperError("Kaynak araması olağan dışı uzun; tam sonuç doğrulanamadı.")
        else:
            # Discover the site's actual GET search form. Never guess/bypass a
            # blocked API. JS-only searches are explicit source errors.
            home = BeautifulSoup(self.get(self.base).content, "lxml")
            form = next((f for f in home.find_all("form") if f.find("input", attrs={"placeholder": re.compile("ISBN", re.I)})), None)
            field = form.find("input", attrs={"placeholder": re.compile("ISBN", re.I)}) if form else None
            if not form or not field.get("name") or form.get("method", "get").lower() != "get":
                raise ScraperError("Pandora araması erişilemiyor; doğrulanmış ürün adaptörü bekleniyor.")
            url = urljoin(self.base, form.get("action", ""))
            r = self.client.get(url, params={field["name"]: query})
            if r.status_code != 200 or has_block_marker(r.text): raise ScraperError(f"HTTP {r.status_code}")
            for a in BeautifulSoup(r.content, "lxml").select("a[href*='/kitap/']"):
                if self.candidate(target, a.get_text(" ", strip=True)):
                    urls[urljoin(self.base, a["href"])] = a.get_text(" ", strip=True)
            if not urls: raise ScraperError("Pandora sonuç şablonu doğrulanamadı; yokluk varsayılmadı.")
        if not urls:
            return [dict(source=self.code, independence_group=self.group, status="NO_RESULT", isbn=None,
                         url=None, title=None, reason="Aramada bu cilt listelenmedi.", checked_at=naive_utcnow().isoformat())]
        evidence = []
        # All candidates for the exact series/volume are checked, including
        # variants. No backfill budget and no dropping contradictory results.
        for url in urls:
            try:
                response = self.get(url)
                evidence.append(proof(self.code, self.group, target, page_book(response.content, str(response.url))))
            except Exception as exc:
                evidence.append(dict(source=self.code, independence_group=self.group, status="ERROR", isbn=None,
                                     title=urls[url], url=url, reason=str(exc)[:500], checked_at=naive_utcnow().isoformat()))
        return evidence

    @staticmethod
    def candidate(target, title):
        parsed = parse_volume_title(bibliographic_title(title))
        expected, actual = edition(target["title"]), edition(title)
        if expected["kind"] != actual["kind"] or expected["variant"] != actual["variant"]:
            return False  # explicitly another product, not an ISBN vote for this edition
        return (base_key(title) in {base_key(target["title"]), base_key(target.get("original_title") or "")}
                and (parsed.volume_number == target["volume_number"] or target.get("covers_from") is not None))


class DiscoverySource:
    code, group = "mangakol", None

    def __init__(self, client):
        self.scraper = MangakolCatalogScraper(client=client)
        self.manga_cache = {}

    def collect(self, target):
        records = []
        for slug in target.get("catalog_slugs", []):
            if slug not in self.manga_cache:
                self.manga_cache[slug] = self.scraper.fetch_manga(slug)
            manga = self.manga_cache[slug]
            if not manga.volumes_complete:
                raise ScraperError("MangaKol cilt listesi eksik; ISBN varsayılmadı.")
            volumes = manga.volumes
            for variant in manga.variants:
                if normalize_text(variant.label) in normalize_text(target["title"]):
                    volumes = variant.volumes
                    break
            matches = [v for v in volumes if v.number == target["volume_number"] and v.url]
            if len(matches) != 1:
                records.append(dict(source=self.code, independence_group=None, status="ERROR", isbn=None,
                    url=f"https://mangakol.com/manga/{slug}", title=manga.title,
                    checked_at=naive_utcnow().isoformat(), reason="MangaKol'da bu fiziksel cildin tekil ürün sayfası belirlenemedi."))
                continue
            item = matches[0]
            details = self.scraper.fetch_volume_details(item.url)
            records.append(dict(source=self.code, independence_group=None, status="DISCOVERY", isbn=details.isbn if details else None,
                url=item.url, title=manga.title, publisher=manga.local_publisher, language="Türkçe",
                checked_at=naive_utcnow().isoformat(), reason="Katalog kaynağındaki ISBN; bağımsız dış kanıt olarak sayılmaz."))
        return records


def source_groups():
    groups = {code: code for code in ("kitapyurdu", "bkm", "pandora", "dr")}
    # Operational override for established shared upstream provenance. Two
    # pages (or domains) in one group always count as a single vote.
    override = json.loads(os.getenv("ISBN_SOURCE_GROUPS", "{}"))
    groups.update({k: str(v) for k, v in override.items() if k in groups})
    return groups


def default_sources():
    client = PoliteClient()
    return client, [*[RetailerSource(code, group, client) for code, group in source_groups().items()], DiscoverySource(client)]


def collect_sources(target, sources) -> list[dict]:
    evidence = []
    for source in sources:
        wait_until = getattr(source, "retry_after", 0)
        if time.monotonic() < wait_until:
            evidence.append(dict(source=source.code, independence_group=source.group, status="ERROR", isbn=None,
                url=None, title=None, reason="Önceki erişim hatası nedeniyle kaynak dinlendiriliyor; daha sonra yeniden denenecek.",
                checked_at=naive_utcnow().isoformat()))
            continue
        try:
            collected = source.collect(target)
            evidence.extend(collected)
            if collected and all(e["status"] == "ERROR" for e in collected):
                raise ScraperError("Ürün sayfalarına erişilemedi.")
            source.failures = 0
        except Exception as exc:
            source.failures = min(getattr(source, "failures", 0) + 1, 6)
            source.retry_after = time.monotonic() + min(1800, 30 * 2**source.failures)
            if not evidence or evidence[-1].get("source") != source.code:
                evidence.append(dict(source=source.code, independence_group=source.group, status="ERROR",
                                     isbn=None, url=None, title=None, reason=str(exc)[:500], checked_at=naive_utcnow().isoformat()))
    return evidence
