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
from .isbn_identity import bibliographic_title, canonical_isbn, catalog_search_title, edition, identity_reason, title_matches

HOSTS = {"www.kitapyurdu.com", "www.pandora.com.tr", "www.bkmkitap.com",
         "bkmkitap.com", "bkm-best.wawlabs.com", "cdn.bkmkitap.com", "www.dr.com.tr", "mangakol.com",
         "www.kitapsepeti.com", "boradagitim.com"}


class SearchIncompleteError(ScraperError):
    """This query is incomplete; do not put the entire provider in cooldown."""


class PoliteClient(httpx.Client):
    """Check robots before every destination, including redirects; fail closed."""
    def __init__(self):
        settings = get_settings()
        self.rules: dict[str, tuple[RobotFileParser | None, str | None]] = {}
        self.rules_checked_at: dict[str, float] = {}
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
        if host not in self.rules or (self.rules[host][0] is None
                and time.monotonic() - self.rules_checked_at.get(host, 0) >= 60):
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
            self.rules_checked_at[host] = time.monotonic()
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
    bora = urlsplit(url).hostname == "boradagitim.com"
    # Bora's UTF-8 page has no reliable charset declaration for BS autodetect.
    if bora and isinstance(html, bytes):
        html = html.decode("utf-8")
    soup = BeautifulSoup(html, "lxml")
    title = soup.select_one("h2.h2musteri") if bora else soup.find("h1")
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
    for row in soup.select("table.description_table tr, #tbldetaylar tr" if bora else "table tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) != 2:
            continue
        key, val = normalize_text(cells[0].get_text()), cells[1].get_text(" ", strip=True)
        if key in {"isbn", "isbn 13", "barkod", "barkod isbn"}: book["raw_isbns"].append(val)
        elif key in {"dil", "yayin dili", "basim dili"}: book["language"] = val
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
    elif len(codes) > 1:
        status, reason = "MISMATCH", "Kaynağın kendi ISBN alanları birbiriyle çelişiyor."
    elif None in codes:
        status, reason = "MISMATCH", "ISBN kontrol basamağı veya biçimi geçersiz."
    elif reason:
        incomplete = ((reason == "Yayınevi farklı veya eksik." and not book.get("publisher"))
            or (reason == "Türkçe baskı kanıtı eksik veya dil farklı." and not book.get("language"))
            or reason == "Cilt/kapak türü kaynakta doğrulanamadı."
            or (reason == "Seri başlığı farklı veya belirsiz." and not book.get("title")))
        status = "INCOMPLETE" if incomplete else "MISMATCH"
    else:
        status, reason = "MATCH", "Seri, cilt, yayınevi, Türkçe dil ve baskı eşleşti."
    return dict(source=source, independence_group=group, status=status, isbn=next(iter(codes)) if len(codes) == 1 else None,
                reason=reason, checked_at=(now or naive_utcnow()).isoformat(), **book)


class RetailerSource:
    def __init__(self, code, group, client):
        self.code, self.group, self.client = code, group, client
        self.base = {"kitapyurdu": "https://www.kitapyurdu.com", "pandora": "https://www.pandora.com.tr",
                     "bkm": "https://www.bkmkitap.com", "dr": "https://www.dr.com.tr",
                     "kitapsepeti": "https://www.kitapsepeti.com", "bora": "https://boradagitim.com"}[code]

    def get(self, url):
        r = self.client.get(url)
        if r.status_code >= 400 or has_block_marker(r.text):
            raise ScraperError(f"HTTP {r.status_code}: kaynak erişim hatası / koruma sayfası.")
        return r

    def collect(self, target: dict) -> list[dict]:
        # Publisher/edition annotations belong to identity validation; search
        # broadly and still validate every product against the full snapshot.
        search_title = catalog_search_title(target)
        query = f'{search_title} {target["volume_number"]}'
        if target.get("covers_from") is not None:
            query = f'{target["title"]} {target["covers_from"]} {target["covers_to"]}'
        urls = {}
        for url in target.get("source_product_urls", {}).get(self.code, []):
            try:
                parsed = urlsplit(url)
                port = parsed.port
            except ValueError:
                continue
            if (parsed.scheme == "https" and parsed.hostname in {urlsplit(self.base).hostname,
                    "bkmkitap.com" if self.code == "bkm" else urlsplit(self.base).hostname}
                    and parsed.username is None and parsed.password is None and port in (None, 443)):
                urls[url.replace("https://bkmkitap.com/", "https://www.bkmkitap.com/")] = "Önceden kayıtlı ürün bağlantısı"
        if urls:
            known = []
            for url in urls:
                try:
                    response = self.client.get(url)
                    if response.status_code in (404, 410):
                        continue  # A removed listing is a discovery miss, not proof.
                    if response.status_code >= 400 or has_block_marker(response.text):
                        raise ScraperError(f"HTTP {response.status_code}: ürün erişim hatası / koruma sayfası.")
                    book = page_book(response.content, str(response.url))
                    if not book["title"]:
                        raise ScraperError("Kayıtlı ürün sayfasının künyesi okunamadı.")
                    known.append(proof(self.code, self.group, target, book))
                except Exception as exc:
                    known.append(dict(source=self.code, independence_group=self.group, status="ERROR", isbn=None,
                        title=urls[url], url=url, reason=str(exc)[:500], checked_at=naive_utcnow().isoformat()))
            if known:
                return known  # Keep every known contradiction and access failure.
            urls.clear()
        if self.code == "bora":
            code = canonical_isbn(target.get("isbn"))
            if code:
                lookup = self.client.get(f"{self.base}/Istem/Urun/Detay.aspx?Barcode={code}")
                if lookup.status_code != 404:
                    if lookup.status_code >= 400 or has_block_marker(lookup.text):
                        raise ScraperError(f"HTTP {lookup.status_code}: Bora ürün erişim hatası.")
                    book = page_book(lookup.content, str(lookup.url))
                    if self.candidate(target, book["title"]):
                        record = proof(self.code, self.group, target, book)
                        if record["status"] in {"MATCH", "INCOMPLETE"}:
                            return [record]
                        urls[str(lookup.url)] = book["title"]
            search_url = f"{self.base}/Istem/Urun/Listele.aspx?ara={quote_plus(query)}&yazar=0&yayinEvi=0&kategori=0"
            response = self.get(search_url)
            soup = BeautifulSoup(response.content.decode("utf-8"), "lxml")
            products = soup.select(".products_container .product_item a.color_dark[href*='/Istem/Urun/Detay.aspx?']")
            all_urls = {urljoin(self.base, a["href"]) for a in products}
            text = normalize_text(soup.get_text(" ", strip=True))
            total = re.search(r"gosterilen (\d+) (\d+) hepsi (\d+)", text)
            if not total or int(total[3]) != len(all_urls):
                raise SearchIncompleteError("Bora araması eksik veya sayfalama doğrulanamadı; yokluk ve mutabakat varsayılmadı.")
            for a in products:
                title = a.get_text(" ", strip=True)
                if self.candidate(target, title):
                    urls[urljoin(self.base, a["href"])] = title
        elif self.code in {"bkm", "dr"}:
            scraper = (BkmScraper if self.code == "bkm" else DrScraper)(client=self.client)
            # Query one volume; do not let detail enrichment silently become proof.
            scraper.settings = replace(scraper.settings, max_detail_requests=0)
            isbn_query = canonical_isbn(target.get("isbn")) if self.code == "bkm" else None
            queries = list(dict.fromkeys([q for q in (isbn_query, query) if q]))
            for search_query in queries:
                results = scraper.search(search_query)
                if scraper.stats.get("stop_reason") in {"max_results", "max_pages", "page_error", "no_new_items"}:
                    raise SearchIncompleteError("Kaynak araması tamamlanamadı; sonuçlar eksik olabilir.")
                if any(self.candidate(target, item.title) for item in results) or urls:
                    break
            for item in results:
                if self.candidate(target, item.title):
                    # Both are BKM's own public product hostnames. The
                    # search feed uses the apex; the current site serves www.
                    url = item.product_url.replace("https://bkmkitap.com/", "https://www.bkmkitap.com/")
                    urls[url] = item.title
        elif self.code == "kitapsepeti":
            pending = {1: f"{self.base}/arama?q={quote_plus(query)}&pg=1"}
            seen, signatures = set(), set()
            while pending:
                page = min(pending)
                response = self.get(pending.pop(page))
                seen.add(page)
                soup = BeautifulSoup(response.content, "lxml")
                products = soup.select("div.product-item a.product-title[href]")
                text = normalize_text(soup.get_text(" ", strip=True))
                if not products and not any(phrase in text for phrase in (
                    "urun bulunamadi", "sonuc bulunamadi", "urun bulunmamaktadir"
                )):
                    raise ScraperError("Kitap Sepeti arama şablonu tanınmadı; yokluk varsayılmadı.")
                signature = tuple(sorted({urljoin(self.base, a["href"]).split("?")[0] for a in products}))
                if signature and signature in signatures:
                    raise ScraperError("Kitap Sepeti sayfalaması ürünleri tekrarlıyor; arama tamamlanamadı.")
                signatures.add(signature)
                for a in products:
                    title = a.get_text(" ", strip=True)
                    if self.candidate(target, title):
                        urls[urljoin(self.base, a["href"]).split("?")[0]] = title
                # Follow published search pagination; never request an out-of-range
                # page (the live site returns an ambiguous blank shell for those).
                for a in soup.select("a[href]"):
                    link = urljoin(self.base, a["href"])
                    parsed = urlsplit(link)
                    params = parse_qs(parsed.query)
                    number = params.get("pg", [""])[0]
                    if (parsed.scheme == "https" and parsed.hostname == "www.kitapsepeti.com"
                            and parsed.path == "/arama" and params.get("q") == [query]
                            and number.isdigit() and int(number) > 0 and int(number) not in seen):
                        pending[int(number)] = link
                if len(products) >= 32 and not pending:
                    raise ScraperError("Kitap Sepeti sonuç sayfası dolu; sayfalama doğrulanamadı.")
                if len(seen) + len(pending) > 1000:
                    raise ScraperError("Kitap Sepeti araması olağan dışı uzun; tam sonuç doğrulanamadı.")
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
                         url=None, title=None, reason=f"Aramada bu cilt listelenmedi. Sorgu: {query}", checked_at=naive_utcnow().isoformat())]
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
        return (title_matches(target, title)
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
    groups = {code: code for code in ("kitapyurdu", "bkm", "kitapsepeti", "bora", "pandora", "dr")}
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
            remaining = max(1, int(wait_until - time.monotonic()))
            previous = getattr(source, "last_error_reason", "İlk hata ayrıntısı kaydedilmemiş.")
            evidence.append(dict(source=source.code, independence_group=source.group, status="ERROR", isbn=None,
                url=None, title=None, reason=f"Kaynak {remaining} sn dinlendiriliyor. Önceki hata: {previous}",
                checked_at=naive_utcnow().isoformat()))
            continue
        try:
            collected = source.collect(target)
            evidence.extend(collected)
            if collected and all(e["status"] == "ERROR" for e in collected):
                raise ScraperError(collected[0].get("reason") or "Ürün sayfalarına erişilemedi.")
            source.failures, source.retry_after = 0, 0
        except Exception as exc:
            source.last_error_reason = str(exc)[:300]
            if isinstance(exc, SearchIncompleteError):
                source.failures, source.retry_after = 0, 0
            else:
                source.failures = min(getattr(source, "failures", 0) + 1, 6)
                source.retry_after = time.monotonic() + min(1800, 30 * 2**source.failures)
            if not evidence or evidence[-1].get("source") != source.code:
                evidence.append(dict(source=source.code, independence_group=source.group, status="ERROR",
                                     isbn=None, url=None, title=None, reason=str(exc)[:500], checked_at=naive_utcnow().isoformat()))
    return evidence
