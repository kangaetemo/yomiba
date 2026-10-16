"""Read-only ISBN health report for admins.

Sizes the ways a wrong or missing ISBN turns into a wrong listing: volumes
without an ISBN (title-only matching), catalog ISBNs the sync deferred,
off-by-one suspicions, listings whose product URL names another volume,
price outliers, malformed ISBNs and one product attached to several volumes.

Never writes: every check is a SELECT over the current database plus the
persisted last catalog-sync summary.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from statistics import median
from urllib.parse import unquote, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import CatalogSeries, Series, Store, StoreListing, Volume
from ..normalization.isbn import is_foreign_isbn
from ..normalization.text import normalize_text
from ..utils import from_cents, utcnow
from . import catalog_state
from .series_slugs import slugs_for

#: Rows returned per check; the count is always the full number.
ITEM_LIMIT = 2000
#: A listing this far above / below the other stores' median is suspect.
LISTING_HIGH, LISTING_LOW = 1.8, 0.55
#: A volume this far from its series' typical price is suspect.
VOLUME_HIGH, VOLUME_LOW = 2.0, 0.5

_PRODUCT_ID_RE = re.compile(r"^\d{4,}$")
#: Numbers that describe the paper or packaging, not the volume.
_NON_VOLUME_FOLLOWERS = {"hamur", "adet", "li", "lu", "lı", "lü", "si", "in", "kitap", "sayfa"}


def isbn_checksum_ok(isbn: str) -> bool:
    """ISBN-13 / ISBN-10 check digit; other lengths are not ISBNs."""
    if len(isbn) == 13 and isbn.isdigit():
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(isbn[:12]))
        return (10 - total % 10) % 10 == int(isbn[12])
    if len(isbn) == 10 and isbn[:9].isdigit() and (isbn[9].isdigit() or isbn[9] == "X"):
        total = sum((10 - i) * int(d) for i, d in enumerate(isbn[:9]))
        check = 10 if isbn[9] == "X" else int(isbn[9])
        return (total + check) % 11 == 0
    return False


def url_volume_numbers(url: str | None, title_numbers: set[int]) -> set[int]:
    """Small numbers in a product URL's last path segment that may name the
    volume ("/urun/happiness-5" -> {5}). Product ids, years, ISBNs, numbers
    from the series title ("kaiju-no-8-...") and paper/packaging numbers
    ("2-hamur") are left out. Empty when the URL carries no slug."""
    if not url:
        return set()
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if not parts:
        return set()
    segment = unquote(parts[-1])
    segment = re.sub(r"\.(?:html?|xhtml|aspx|php)$", "", segment, flags=re.I)
    tokens = normalize_text(re.sub(r"[-_+.]", " ", segment)).split()
    if not any(re.search(r"[a-z]", t) for t in tokens):
        return set()
    numbers: set[int] = set()
    for i, token in enumerate(tokens):
        if not token.isdigit() or _PRODUCT_ID_RE.match(token):
            continue
        follower = tokens[i + 1] if i + 1 < len(tokens) else ""
        if follower in _NON_VOLUME_FOLLOWERS:
            continue
        numbers.add(int(token))
    return numbers - title_numbers


def _title_numbers(series: Series) -> set[int]:
    text = f"{series.normalized_title or ''} {series.original_title or ''}"
    return {int(n) for n in re.findall(r"\d+", text)}


def _released(volume: Volume, today: date) -> bool:
    if volume.catalog_released is False:
        return False
    return volume.release_date is None or volume.release_date <= today


def build_report(session: Session) -> dict:
    today = utcnow().date()
    catalog_ids = select(CatalogSeries.series_id).distinct()
    volumes = list(session.scalars(
        select(Volume)
        .options(joinedload(Volume.series).joinedload(Series.publisher))
        .where(Volume.series_id.in_(catalog_ids), Volume.volume_number >= 0,
               Volume.catalog_present.is_not(False))
    ).unique())
    by_id = {v.id: v for v in volumes}
    slugs = slugs_for(session, {v.series_id for v in volumes})

    listings_by_volume: dict[int, list[tuple[StoreListing, Store]]] = defaultdict(list)
    all_listings: list[tuple[StoreListing, Store]] = []
    for listing, store in session.execute(
        select(StoreListing, Store).join(Store, Store.id == StoreListing.store_id)
    ):
        all_listings.append((listing, store))
        if listing.volume_id in by_id:
            listings_by_volume[listing.volume_id].append((listing, store))

    def ref(v: Volume) -> dict:
        return dict(volume_id=v.id, series_id=v.series_id, series_slug=slugs.get(v.series_id),
                    series=v.series.title, publisher=v.series.publisher.name if v.series.publisher else None,
                    volume_number=v.volume_number, isbn=v.isbn)

    def offer(listing: StoreListing, store: Store) -> dict:
        return dict(store=store.name, url=listing.product_url, in_stock=listing.in_stock,
                    price=float(from_cents(listing.price)) if listing.price is not None else None)

    def in_stock_priced(vid: int):
        return [(l, s) for l, s in listings_by_volume.get(vid, []) if l.in_stock and l.price is not None]

    released = [v for v in volumes if _released(v, today)]

    # 1. Released volumes without an ISBN: every listing they have was matched by title alone.
    missing = []
    for v in released:
        if v.isbn:
            continue
        rows = listings_by_volume.get(v.id, [])
        missing.append(dict(ref(v), listings=len(rows), in_stock=sum(1 for l, _ in rows if l.in_stock)))
    missing.sort(key=lambda r: (-r["in_stock"], r["series"], r["volume_number"]))

    # 2–3. ISBNs the last catalog sync read but did not write, and off-by-one suspicions.
    last = catalog_state.read_state().get("last") or {}
    deferred, shifted = [], []
    for cand in last.get("isbn_candidates") or []:
        v = by_id.get(cand.get("volume_id"))
        source_isbn = cand.get("source_isbn")
        if v is None or not source_isbn:
            continue
        holder = session.scalar(select(Volume).where(Volume.isbn == source_isbn))
        if v.isbn == source_isbn:
            continue  # written since
        if holder is not None and holder.id != v.id:
            same_series = holder.series_id == v.series_id
            kind = "held_by_neighbor" if same_series and abs(holder.volume_number - v.volume_number) == 1 else "held_by_other"
            holder_ref = dict(volume_id=holder.id, series=holder.series.title if holder.series else None,
                              volume_number=holder.volume_number, series_slug=slugs.get(holder.series_id))
        elif v.isbn:
            kind, holder_ref = "differs", None
        elif not isbn_checksum_ok(source_isbn):
            kind, holder_ref = "invalid", None
        else:
            kind, holder_ref = "safe_to_write", None
        row = dict(ref(v), source_isbn=source_isbn, source_url=cand.get("source_url"), kind=kind, holder=holder_ref)
        (shifted if kind == "held_by_neighbor" else deferred).append(row)
    order = {"safe_to_write": 0, "differs": 1, "held_by_other": 2, "invalid": 3}
    deferred.sort(key=lambda r: (order.get(r["kind"], 9), r["series"], r["volume_number"]))

    # 4. Listings whose product URL names a different volume number.
    url_mismatch = []
    for vid, rows in listings_by_volume.items():
        v = by_id[vid]
        if v.covers_from is not None:
            continue  # omnibus: the URL carries the original span
        title_numbers = _title_numbers(v.series)
        if v.volume_number in title_numbers:
            continue
        for listing, store in rows:
            numbers = url_volume_numbers(listing.product_url, title_numbers)
            if len(numbers) == 1 and v.volume_number not in numbers:
                url_mismatch.append(dict(ref(v), url_number=next(iter(numbers)), **offer(listing, store)))
    url_mismatch.sort(key=lambda r: (not r["in_stock"], r["series"], r["volume_number"]))

    # 5a. A store's in-stock price far from the other stores' median for the same volume.
    listing_outliers = []
    volume_median: dict[int, float] = {}
    for v in released:
        rows = in_stock_priced(v.id)
        if rows:
            volume_median[v.id] = median(l.price for l, _ in rows)
        if len(rows) < 3:
            continue
        for listing, store in rows:
            others = median(l.price for l, s in rows if l.id != listing.id)
            ratio = listing.price / others if others else None
            if ratio and (ratio >= LISTING_HIGH or ratio <= LISTING_LOW):
                listing_outliers.append(dict(ref(v), ratio=round(ratio, 2),
                                             others_median=float(from_cents(int(others))), **offer(listing, store)))
    listing_outliers.sort(key=lambda r: -max(r["ratio"], 1 / r["ratio"]))

    # 5b. A whole volume priced far from its series' typical volume (edition mix-ups).
    volume_outliers = []
    by_series: dict[int, list[Volume]] = defaultdict(list)
    for v in released:
        if v.id in volume_median and v.covers_from is None:
            by_series[v.series_id].append(v)
    for series_volumes in by_series.values():
        if len(series_volumes) < 4:
            continue
        typical = median(volume_median[v.id] for v in series_volumes)
        for v in series_volumes:
            ratio = volume_median[v.id] / typical if typical else None
            if ratio and (ratio >= VOLUME_HIGH or ratio <= VOLUME_LOW):
                volume_outliers.append(dict(ref(v), ratio=round(ratio, 2),
                                            volume_median=float(from_cents(int(volume_median[v.id]))),
                                            series_median=float(from_cents(int(typical))),
                                            offers=[offer(l, s) for l, s in in_stock_priced(v.id)]))
    volume_outliers.sort(key=lambda r: -max(r["ratio"], 1 / r["ratio"]))

    # 6. Malformed or foreign ISBNs on catalog volumes.
    bad_isbn = []
    for v in volumes:
        if not v.isbn:
            continue
        problem = None
        if len(v.isbn) == 13 and not v.isbn.startswith(("978", "979")):
            problem = "not_book_barcode"
        elif not isbn_checksum_ok(v.isbn):
            problem = "checksum"
        elif len(v.isbn) == 10:
            problem = "isbn10"
        elif is_foreign_isbn(v.isbn):
            problem = "foreign"
        if problem:
            bad_isbn.append(dict(ref(v), problem=problem))

    # 7. The same store product attached to more than one volume.
    by_product: dict[tuple[int, str], list[tuple[StoreListing, Store]]] = defaultdict(list)
    for listing, store in all_listings:
        if listing.product_url:
            by_product[(store.id, listing.product_url)].append((listing, store))
    shared_product = []
    for (_, url), rows in by_product.items():
        if len(rows) < 2:
            continue
        shared_product.append(dict(store=rows[0][1].name, url=url,
                                   volumes=[ref(by_id[l.volume_id]) if l.volume_id in by_id
                                            else dict(volume_id=l.volume_id) for l, _ in rows]))

    checks = [
        ("missing_isbn", missing),
        ("deferred_catalog_isbn", deferred),
        ("off_by_one", shifted),
        ("url_volume_mismatch", url_mismatch),
        ("listing_price_outlier", listing_outliers),
        ("volume_price_outlier", volume_outliers),
        ("invalid_isbn", bad_isbn),
        ("shared_product", shared_product),
    ]
    return dict(
        generated_at=utcnow().isoformat(),
        last_sync_finished_at=last.get("finished_at"),
        totals=dict(
            catalog_volumes=len(volumes),
            released_volumes=len(released),
            released_with_isbn=sum(1 for v in released if v.isbn),
            released_without_isbn=len(missing),
            without_isbn_but_listed=sum(1 for r in missing if r["listings"]),
            listings=len(all_listings),
        ),
        checks={key: dict(count=len(rows), items=rows[:ITEM_LIMIT]) for key, rows in checks},
    )
