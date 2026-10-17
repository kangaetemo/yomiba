"""Store bestseller lists -> a popularity score per catalog series.

Readers' collections are still too few to rank "Popüler seriler" on their
own, so the stores' bestseller lists lead: idefix's manga category sorted by
best selling (D&R and BKM sell there) and BKM's bestselling comics. Each
product earns ``1 - rank / list length`` for its series (higher on the list
= more), summed over products and lists. BKM products are matched by ISBN,
idefix products by title and publisher (the importer's title path, which
only reads).

Refreshed after each catalog sync (daily); failures keep the last scores.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import SeriesPopularity, Volume
from ..normalization import normalize_text
from ..normalization.isbn import book_isbn
from ..scrapers import SearchResult
from ..utils import utcnow

logger = logging.getLogger("yomiba.popularity")

IDEFIX_URL = "https://www.idefix.com/manga-c-330731344?siralama=desc_score_best_selling&sayfa={page}"
IDEFIX_PAGES = 3
BKM_URL = "https://www.bkmkitap.com/cok-satan-cizgi-romanlar?pg={page}"
BKM_PAGES = 4

#: (title, publisher, isbn) in list order.
Product = tuple[str, str | None, str | None]


def parse_idefix(html: str) -> list[Product]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    items = json.loads(m.group(1))["props"]["pageProps"]["categoryData"]["items"]
    out = []
    for it in items:
        name = (it.get("variants") or [{}])[0].get("name") or ""
        brand = it.get("brandName") or None
        # "Blue Lock Cilt - 27 - Komik Şeyler": drop the trailing publisher.
        if brand:
            name = re.sub(rf"\s*-\s*{re.escape(brand)}\s*$", "", name).strip()
            name = re.sub(rf"^{re.escape(brand)}\s+", "", name).strip()
        name = re.sub(r"\s*-\s*$", "", name)
        if name:
            out.append((name, brand, None))
    return out


def parse_bkm(html: str) -> list[Product]:
    out = []
    for raw in re.findall(r"PRODUCT_DATA\.push\(JSON\.parse\('(.*?)'\)\);", html):
        try:
            d = json.loads(json.loads('"' + raw + '"'))
        except ValueError:
            continue
        out.append((d.get("name") or "", d.get("brand") or None, book_isbn(str(d.get("code") or ""))))
    return out


def fetch_lists(get: Callable[[str], str]) -> dict[str, list[Product]]:
    lists: dict[str, list[Product]] = {}
    for source, url, pages, parse in (("idefix", IDEFIX_URL, IDEFIX_PAGES, parse_idefix),
                                      ("bkm", BKM_URL, BKM_PAGES, parse_bkm)):
        products: list[Product] = []
        for page in range(1, pages + 1):
            try:
                found = parse(get(url.format(page=page)))
            except Exception as exc:  # noqa: BLE001 - keep what was read
                logger.warning("popularity: %s page %s failed: %s", source, page, exc)
                break
            if not found:
                break
            products.extend(found)
        lists[source] = products
    return lists


def series_for(session: Session, title: str, publisher: str | None, isbn: str | None) -> int | None:
    from .import_service import ImportService

    if isbn:
        sid = session.scalar(select(Volume.series_id).where(Volume.isbn == isbn))
        if sid is not None:
            return sid
    service = ImportService(session)
    service._non_catalog_holder = None  # noqa: SLF001 - read-only title path
    result = SearchResult(store_id="bestseller", store_name="Çok satanlar", title=title,
                          product_url="https://bestseller.invalid/", publisher=publisher)
    volume = service._title_path(result)  # noqa: SLF001
    if volume is not None:
        return volume.series_id
    # "Elden Ring - Altın Ağaç'a Yolculuk 1": the catalog title as a prefix.
    match = service._catalog_series_prefix(normalize_text(title), publisher or "")  # noqa: SLF001
    return match[0].id if match else None


def score(session: Session, lists: dict[str, list[Product]]) -> dict[int, float]:
    scores: dict[int, float] = defaultdict(float)
    for products in lists.values():
        n = len(products)
        for rank, (title, publisher, isbn) in enumerate(products):
            sid = series_for(session, title, publisher, isbn)
            if sid is not None:
                scores[sid] += 1 - rank / n
    return dict(scores)


def refresh(session: Session, get: Callable[[str], str]) -> int:
    """Re-read the lists and replace the scores; keeps the old ones when no
    list could be read. Commits. Returns the number of scored series."""
    lists = fetch_lists(get)
    if not any(lists.values()):
        logger.warning("popularity: no bestseller list could be read; keeping previous scores")
        return 0
    scores = score(session, lists)
    now = utcnow()
    session.execute(delete(SeriesPopularity))
    session.add_all(SeriesPopularity(series_id=sid, bestseller_score=round(v, 4), updated_at=now)
                    for sid, v in scores.items())
    session.commit()
    logger.info("popularity: %d series scored from %s",
                len(scores), {k: len(v) for k, v in lists.items()})
    return len(scores)
