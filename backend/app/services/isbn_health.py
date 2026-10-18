"""Read-only ISBN health report for admins.

Sizes the ways a wrong or missing ISBN turns into a wrong listing:

* released volumes without an ISBN (their listings are title matches);
* catalog ISBNs (Mangakol) that differ from the volume's decided ISBN;
* catalog ISBNs Mangakol lists on two different books (source duplicates,
  e.g. Blue Lock 28 and 29);
* store products whose title names one volume and whose ISBN another
  (attached by title, rule ``title_over_isbn``);
* contradictions the resolver left open, and the latest ISBN changes;
* price outliers, malformed ISBNs and one product on several volumes;
* listings the store's search no longer returns (kept fresh only by their
  product page: ``search_miss``), listings gone stale (hidden), and
  suspicious listings (not a book, another publisher, off-site link).

Never writes: every check is a SELECT over the current database.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..models import (CatalogSeries, IsbnChange, IsbnIssue, PublisherAlias, Series, SharedIsbn, Store,
                      StoreListing, StoreObservation, Volume)
from ..normalization import normalize_publisher, normalize_text
from ..normalization.isbn import is_foreign_isbn, isbn_checksum_ok
from ..utils import from_cents, utcnow
from .series_slugs import slugs_for

#: Rows returned per check; the count is always the full number.
ITEM_LIMIT = 2000
#: A listing this far above / below the other stores' median is suspect.
LISTING_HIGH, LISTING_LOW = 1.8, 0.55
#: A volume this far from its series' typical price is suspect.
VOLUME_HIGH, VOLUME_LOW = 2.0, 0.5
OBSERVATION_WINDOW = timedelta(days=90)
#: An in-stock listing whose search sighting lags its last check this much
#: is kept alive only by product-page re-checks.
SEARCH_MISS_AFTER = timedelta(hours=48)
#: Words in a store title that point to something other than this manga
#: volume: a TV season, a disc, the novel, an art book. Whole words of the
#: normalized title ("bolum" is NOT here: "Heartslabyul Bölümü" is a manga).
SUSPECT_WORDS = frozenset({"sezon", "dvd", "bluray", "novel", "artbook", "kartpostal", "poster",
                           "ekitap", "kindle", "sesli"})


def _site(url: str | None) -> str | None:
    from urllib.parse import urlparse

    host = (urlparse(url or "").hostname or "").lower()
    return host.removeprefix("www.") or None


def _store_sites() -> dict[str, str]:
    """store code -> the store's own host ("bkmkitap.com")."""
    from ..scrapers import registry

    return {code: site for code, cls in getattr(registry, "_SCRAPERS", {}).items()
            if (site := _site(getattr(cls, "base_url", "")))}


def _released(volume: Volume, today) -> bool:
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
    base_slug: dict[int, set[str]] = defaultdict(set)
    for sid, slug in session.execute(select(CatalogSeries.series_id, CatalogSeries.mangakol_slug)):
        base_slug[sid].add(slug.split("~")[0])
    shared = defaultdict(set)
    for isbn, vid in session.execute(select(SharedIsbn.isbn, SharedIsbn.volume_id)):
        shared[vid].add(isbn)

    def same_book(a: Volume, b: Volume) -> bool:
        return a.volume_number == b.volume_number and bool(base_slug[a.series_id] & base_slug[b.series_id])

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
                    volume_number=v.volume_number, isbn=v.isbn, isbn_source=v.isbn_source,
                    catalog_isbn=v.catalog_isbn)

    def short(vid: int | None) -> dict | None:
        v = by_id.get(vid) if vid else None
        return dict(volume_id=v.id, series=v.series.title, volume_number=v.volume_number,
                    series_slug=slugs.get(v.series_id), isbn=v.isbn) if v else None

    def offer(listing: StoreListing, store: Store) -> dict:
        return dict(store=store.name, url=listing.product_url, in_stock=listing.in_stock,
                    price=float(from_cents(listing.price)) if listing.price is not None else None)

    def in_stock_priced(vid: int):
        return [(l, s) for l, s in listings_by_volume.get(vid, []) if l.in_stock and l.price is not None]

    released = [v for v in volumes if _released(v, today)]

    # 1. Released volumes without an ISBN: their listings are title matches.
    missing = []
    for v in released:
        if v.isbn or shared[v.id]:
            continue
        rows = listings_by_volume.get(v.id, [])
        missing.append(dict(ref(v), listings=len(rows), in_stock=sum(1 for l, _ in rows if l.in_stock)))
    missing.sort(key=lambda r: (-r["in_stock"], r["series"], r["volume_number"]))

    # 2. Mangakol's ISBN differs from the decided one.
    differs = []
    for v in released:
        if v.catalog_isbn and v.catalog_isbn != v.isbn and v.catalog_isbn not in shared[v.id]:
            differs.append(dict(ref(v), kind="empty" if not v.isbn else "differs"))
    differs.sort(key=lambda r: (r["kind"] != "differs", r["series"], r["volume_number"]))

    # 3. Mangakol lists one ISBN on two different books.
    by_catalog: dict[str, list[Volume]] = defaultdict(list)
    for v in volumes:
        if v.catalog_isbn:
            by_catalog[v.catalog_isbn].append(v)
    duplicates = []
    for isbn, group in by_catalog.items():
        if len(group) < 2:
            continue
        if all(same_book(group[0], other) for other in group[1:]):
            continue  # one book in several editions: a legitimate shared ISBN
        duplicates.append(dict(isbn=isbn, volumes=[ref(v) for v in group]))
    duplicates.sort(key=lambda r: r["volumes"][0]["series"])

    # 4. Store title names one volume, ISBN another: attached by title.
    since = utcnow() - OBSERVATION_WINDOW
    stores = dict(session.execute(select(Store.id, Store.name)).all())
    conflicts = []
    for o in session.scalars(select(StoreObservation).where(
            (StoreObservation.rule == "title_over_isbn") | (StoreObservation.reason == "isbn_title_conflict")
    ).order_by(StoreObservation.last_seen.desc())):
        seen = o.last_seen if o.last_seen.tzinfo else o.last_seen.replace(tzinfo=since.tzinfo)
        if seen < since:
            continue
        conflicts.append(dict(store=stores.get(o.store_id), url=o.product_url, title=o.title, isbn=o.isbn,
                              price=from_cents(o.price), title_volume=short(o.title_volume_id),
                              isbn_volume=short(o.isbn_volume_id), attached=o.volume_id is not None))

    # 5. Contradictions the resolver left open; latest ISBN changes.
    issues = [dict(ref(by_id[i.volume_id]) if i.volume_id in by_id else dict(volume_id=i.volume_id),
                   kind=i.kind, detail=i.detail)
              for i in session.scalars(select(IsbnIssue).order_by(IsbnIssue.kind, IsbnIssue.volume_id))]
    changes = [dict(short(c.volume_id) or dict(volume_id=c.volume_id), old_isbn=c.old_isbn, new_isbn=c.new_isbn,
                    source=c.source, reason=c.reason, at=c.created_at.isoformat() if c.created_at else None)
               for c in session.scalars(select(IsbnChange).order_by(IsbnChange.id.desc()).limit(300))]

    # 6a. A store's in-stock price far from the other stores' median for the same volume.
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

    # 6b. A whole volume priced far from its series' typical volume (edition mix-ups).
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

    # 7. Malformed or foreign ISBNs on catalog volumes.
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

    # 8. The same store product attached to more than one volume.
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

    # 9. Listing freshness and suspicious listings.
    now = utcnow()

    def aware(dt):
        return dt.replace(tzinfo=dt.tzinfo or now.tzinfo) if dt else None

    newest: dict[int, object] = {}
    for listing, store in all_listings:
        checked = aware(listing.last_checked)
        if checked and (store.id not in newest or checked > newest[store.id]):
            newest[store.id] = checked
    stale_window = timedelta(hours=get_settings().listing_stale_hours)
    observations = {(o.store_id, o.product_url): o for o in session.scalars(select(StoreObservation))}
    aliases: dict[int, set[str]] = defaultdict(set)
    for alias, pid in session.execute(select(PublisherAlias.normalized_alias, PublisherAlias.publisher_id)):
        aliases[pid].add(alias)
    sites = _store_sites()
    search_miss, stale_listings, suspect = [], [], []
    for listing, store in all_listings:
        v = by_id.get(listing.volume_id)
        if v is None:
            continue
        checked, seen = aware(listing.last_checked), aware(listing.seen_in_search_at)
        when = dict(last_checked=checked.isoformat() if checked else None,
                    seen_in_search=seen.isoformat() if seen else None)
        if listing.in_stock and checked and seen and checked - seen >= SEARCH_MISS_AFTER:
            search_miss.append(dict(ref(v), **offer(listing, store), **when))
        latest = newest.get(store.id)
        if listing.in_stock and checked and latest and latest - checked > stale_window:
            stale_listings.append(dict(ref(v), **offer(listing, store), **when))
        reasons = []
        site = sites.get(store.code)
        host = _site(listing.product_url)
        if site and host and host != site and not host.endswith("." + site):
            reasons.append(f"başka siteye gidiyor ({host})")
        obs = observations.get((store.id, listing.product_url))
        if obs is not None:
            words = set(normalize_text(obs.title or "").split())
            hit = sorted(words & SUSPECT_WORDS)
            if hit:
                reasons.append("başlıkta: " + ", ".join(hit))
            pub = normalize_publisher(obs.publisher) if obs.publisher else ""
            ours = v.series.publisher
            if pub and ours is not None:
                known = {ours.normalized_name, *aliases[ours.id]}
                if not any(k and (k in pub or pub in k) for k in known):
                    reasons.append(f"yayınevi farklı ({obs.publisher})")
        if reasons:
            suspect.append(dict(ref(v), **offer(listing, store), title=obs.title if obs else None,
                                reasons=reasons))
    for rows in (search_miss, stale_listings, suspect):
        rows.sort(key=lambda r: (r["store"], r["series"], r["volume_number"]))

    checks = [
        ("search_miss", search_miss),
        ("stale_listing", stale_listings),
        ("suspect_listing", suspect),
        ("isbn_issues", issues),
        ("catalog_duplicate", duplicates),
        ("title_isbn_conflict", conflicts),
        ("catalog_differs", differs),
        ("volume_price_outlier", volume_outliers),
        ("listing_price_outlier", listing_outliers),
        ("missing_isbn", missing),
        ("invalid_isbn", bad_isbn),
        ("shared_product", shared_product),
        ("recent_changes", changes),
    ]
    return dict(
        generated_at=utcnow().isoformat(),
        totals=dict(
            catalog_volumes=len(volumes),
            released_volumes=len(released),
            released_with_isbn=sum(1 for v in released if v.isbn or shared[v.id]),
            released_without_isbn=len(missing),
            without_isbn_but_listed=sum(1 for r in missing if r["listings"]),
            listings=len(all_listings),
            observations=session.query(StoreObservation).count(),
            catalog_isbn_read=sum(1 for v in released if v.catalog_isbn),
        ),
        checks={key: dict(count=len(rows), items=rows[:ITEM_LIMIT]) for key, rows in checks},
    )
