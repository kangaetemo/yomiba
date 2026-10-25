"""GET /home — the home page shelves, computed from catalog data only.

* ``popular_series``: catalog series with at least one in-stock offer,
  ranked by popularity — stores' bestseller lists (services/popularity.py),
  a bonus for a volume released lately, and time-weighted reader interest
  (wishlist + collection rows; the last RECENT_DAYS count RECENT_WEIGHT
  times, capped) — then by in-stock offers PER VOLUME (so long series do not
  win just by length), then by total offers.
  The price shown is the lowest current in-stock price of any volume.
* ``new_volumes``: volumes by their LOCAL release date from the catalog
  source (Mangakol "Yayın Tarihi (Yerel)"), newest first, never in the
  future. Volumes without a known date are not listed.
* ``new_series``: series that started in Turkey lately, by the LOCAL release
  date of their first volume (cilt 0 or 1), newest first, never in the
  future. A series whose first volume has no known date is not listed, and
  neither is one whose catalog starts later than cilt 1 (a gap in the data,
  not a new series). Binding variants are left out.
* ``one_shots``: single-volume series that Mangakol marks completed both
  in Japan and in Turkey (Look Back, Soichi) — one book and the story is
  done. Binding variants ("Soichi (Bez Cilt)") are left out; in-stock
  titles first, then by reader interest and offers.
* ``stats``: catalog / store / offer counts for the hero.

Read-only; nothing here triggers a scrape. The feed is the same for every
visitor and takes seconds on the production database, so it is cached
(HOME_CACHE_SECONDS) and an expired copy is served while a new one is built.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    CatalogSeries,
    Publisher,
    Series,
    SeriesPopularity,
    StoreListing,
    UserVolumeCollection,
    Volume,
    WishlistItem,
)
from ..services import series_slugs
from ..services.catalog_service import (
    fresh_listing_condition,
    only_volume_numbers,
    public_volume_condition,
)
from ..services.covers import cover_url
from ..services.swr_cache import SwrCache
from ..utils import from_cents, utcnow

router = APIRouter(tags=["home"])


def _catalog_ids():
    return select(CatalogSeries.series_id).distinct()


def _series_covers(session: Session, series_ids: list[int]) -> dict[int, str]:
    """First numbered volume with a cover, per series."""
    covers: dict[int, str] = {}
    rows = session.execute(
        select(Volume.series_id, Volume.cover_key)
        .where(Volume.series_id.in_(series_ids), Volume.cover_key.isnot(None),
               Volume.volume_number >= 0, public_volume_condition())
        .order_by(Volume.series_id, Volume.volume_number)
    )
    for series_id, key in rows:
        covers.setdefault(series_id, cover_url(key))
    return covers


#: Reader activity within this window counts RECENT_WEIGHT times, so the
#: shelf follows what readers are into now, not what they added years ago.
RECENT_DAYS = 30
RECENT_WEIGHT = 3.0
#: "Popüler seriler": a volume released in the last RECENT_RELEASE_DAYS adds
#: RECENT_RELEASE_BONUS; reader interest adds at most 1 (at INTEREST_CAP).
RECENT_RELEASE_DAYS = 60
RECENT_RELEASE_BONUS = 0.5
INTEREST_CAP = 10.0


def reader_interest(session: Session) -> dict[int, float]:
    """Time-weighted reader interest per series: wishlist rows (by when they
    were added) plus collection rows (by their last status change)."""
    cutoff = utcnow() - timedelta(days=RECENT_DAYS)
    interest: dict[int, float] = {}
    for model, stamp in ((WishlistItem, WishlistItem.created_at),
                         (UserVolumeCollection, UserVolumeCollection.updated_at)):
        weight = case((stamp >= cutoff, RECENT_WEIGHT), else_=1.0)
        for sid, score in session.execute(
            select(Volume.series_id, func.sum(weight))
            .select_from(model).join(Volume, Volume.id == model.volume_id)
            .group_by(Volume.series_id)
        ):
            interest[sid] = interest.get(sid, 0.0) + float(score or 0)
    return interest


HOME_CACHE_SECONDS = 300
_home_cache = SwrCache("home feed", HOME_CACHE_SECONDS)
#: The parameters the SSR home page asks for (frontend getHomeFeed), warmed
#: in the background so no visitor waits for a cold feed.
SSR_HOME_PARAMS = {"popular": 24, "one_shot": 48, "new": 10, "new_series": 8, "hero": True}


def clear_cache() -> None:
    _home_cache.clear()


@router.get("/home")
def home(
    popular: int = Query(default=8, ge=1, le=24),
    one_shot: int = Query(default=8, ge=1, le=100),
    new: int = Query(default=10, ge=1, le=30),
    new_series: int = Query(default=8, ge=1, le=30),
    hero: bool = Query(default=False),
    session: Session = Depends(get_db),
) -> dict:
    return home_feed(session, popular=popular, one_shot=one_shot, new=new,
                     new_series=new_series, hero=hero)


def home_feed(session: Session, *, popular: int, one_shot: int, new: int,
              new_series: int, hero: bool) -> dict:
    """The cached feed; callers must not mutate it."""
    return _home_cache.get(
        session, (popular, one_shot, new, new_series, hero),
        lambda own: _compute_home(own, popular=popular, one_shot=one_shot, new=new,
                                  new_series=new_series, hero=hero))


def _compute_home(session: Session, *, popular: int, one_shot: int, new: int,
                  new_series: int, hero: bool) -> dict:
    catalog = _catalog_ids()
    real = (Volume.volume_number >= 0) & public_volume_condition(include_announced=False)

    # -- popular series ---------------------------------------------------------
    interest = reader_interest(session)
    offers = session.execute(
        select(Volume.series_id, func.count(StoreListing.id), func.min(StoreListing.price))
        .join(StoreListing, StoreListing.volume_id == Volume.id)
        .where(Volume.series_id.in_(catalog), real, StoreListing.in_stock.is_(True),
               StoreListing.price.isnot(None), fresh_listing_condition(session))
        .group_by(Volume.series_id)
    ).all()
    volume_counts = dict(session.execute(
        select(Volume.series_id, func.count())
        .where(Volume.series_id.in_([r[0] for r in offers]), real)
        .group_by(Volume.series_id)
    ).all())

    bestseller = dict(session.execute(select(SeriesPopularity.series_id, SeriesPopularity.bestseller_score)).all())
    recent_cutoff = utcnow().date() - timedelta(days=RECENT_RELEASE_DAYS)
    recent = set(session.scalars(
        select(Volume.series_id).where(Volume.series_id.in_([r[0] for r in offers]), real,
                                       Volume.release_date >= recent_cutoff,
                                       Volume.release_date <= utcnow().date())
    ))

    def rank(row):
        sid, offer_count, _ = row
        # Stores' bestseller lists lead; a volume released lately and
        # readers' interest add to it (interest is capped so a handful of
        # users cannot outweigh the stores). Offers per volume break ties:
        # how easy the series is to buy, without long series winning merely
        # by having many volumes.
        popularity = (bestseller.get(sid, 0.0) + (RECENT_RELEASE_BONUS if sid in recent else 0.0)
                      + min(interest.get(sid, 0.0), INTEREST_CAP) / INTEREST_CAP)
        availability = offer_count / max(1, volume_counts.get(sid, 0))
        return (-popularity, -availability, -offer_count, sid)

    ranked = sorted(offers, key=rank)[:popular]
    popular_ids = [r[0] for r in ranked]
    # The discovery hero draws from every buyable, covered catalog series,
    # independently of the popularity ranking. Only requested by the SSR page.
    detail_ids = [r[0] for r in offers] if hero else popular_ids
    series_rows = {
        s.id: (s, p) for s, p in session.execute(
            select(Series, Publisher.name).join(Publisher, Publisher.id == Series.publisher_id)
            .where(Series.id.in_(detail_ids))
        )
    }
    covers = _series_covers(session, detail_ids)
    slugs = series_slugs.slugs_for(session, detail_ids)
    only = only_volume_numbers(session, detail_ids)

    def series_card(row):
        sid, offer_count, min_price = row
        series, publisher = series_rows[sid]
        return {
            "id": sid,
            "slug": slugs[sid],
            "title": series.title,
            "publisher": publisher,
            "author": series.author,
            "cover_url": covers.get(sid),
            "volume_count": volume_counts.get(sid, 0),
            "only_volume": only.get(sid),
            "in_stock_offers": offer_count,
            "lowest_price": from_cents(min_price),
        }

    popular_series = [series_card(row) for row in ranked]
    hero_series = [series_card(row) for row in offers if row[0] in covers] if hero else None

    # -- new volumes (local release date) --------------------------------------------
    new_rows = session.execute(
        _release_query()
        .where(Volume.release_date <= date.today())
        .order_by(Volume.release_date.desc(), Volume.id.desc())
        .limit(new)
    ).all()
    new_volumes = _serialize_releases(session, new_rows)

    new_series_cards = _new_series(session, new_series)
    one_shots = _one_shots(session, interest, one_shot)

    stats = {
        "series": session.scalar(select(func.count(func.distinct(CatalogSeries.series_id)))) or 0,
        "stores": session.scalar(
            select(func.count(func.distinct(StoreListing.store_id)))) or 0,
        "offers": session.scalar(
            select(func.count(StoreListing.id)).where(StoreListing.price.isnot(None))) or 0,
    }
    result = {"popular_series": popular_series, "one_shots": one_shots,
              "new_volumes": new_volumes, "new_series": new_series_cards, "stats": stats}
    if hero_series is not None:
        result["hero_series"] = hero_series
    return result


def _release_query():
    price_sub = (
        select(StoreListing.volume_id, func.min(StoreListing.price).label("min_price"),
               func.count(StoreListing.id).label("stores"))
        .where(StoreListing.in_stock.is_(True), StoreListing.price.isnot(None))
        .group_by(StoreListing.volume_id)
        .subquery()
    )
    return (
        select(Volume, Series.title, Publisher.name, price_sub.c.min_price, price_sub.c.stores)
        .join(Series, Series.id == Volume.series_id)
        .join(Publisher, Publisher.id == Series.publisher_id)
        .outerjoin(price_sub, price_sub.c.volume_id == Volume.id)
        .where(Volume.series_id.in_(_catalog_ids()), Volume.volume_number >= 0,
               Volume.release_date.isnot(None), public_volume_condition())
    )


def _serialize_releases(session: Session, rows) -> list[dict]:
    fallback_covers = _series_covers(session, list({v.series_id for v, *_ in rows}))
    new_slugs = series_slugs.slugs_for(session, [v.series_id for v, *_ in rows])
    return [
        {
            "id": v.id,
            "series_id": v.series_id,
            "series_slug": new_slugs[v.series_id],
            "series_title": title,
            "publisher": publisher,
            "number": v.volume_number,
            "covers_from": v.covers_from,
            "covers_to": v.covers_to,
            "cover_url": cover_url(v.cover_key) or fallback_covers.get(v.series_id),
            "release_date": v.release_date.isoformat() if v.release_date else None,
            "lowest_price": from_cents(min_price),
            "in_stock_offers": stores or 0,
        }
        for v, title, publisher, min_price, stores in rows
    ]


@router.get("/releases")
def releases(
    month: str = Query(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$"),
    session: Session = Depends(get_db),
) -> dict:
    """All catalog releases in a month; no shelf limit and no scraping.

    Future dates are announced releases. Unknown dates and unresolved or
    non-catalog volumes cannot be placed on the calendar and are omitted.
    """
    year, month_number = map(int, month.split("-"))
    start = date(year, month_number, 1)
    end = date(year, month_number, monthrange(year, month_number)[1])
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
    rows = session.execute(
        _release_query()
        .where(Volume.release_date >= start, Volume.release_date <= end)
        .order_by(Volume.release_date.desc(), Volume.id.desc())
    ).all()
    latest = session.scalar(
        select(func.max(Volume.release_date))
        .where(Volume.series_id.in_(_catalog_ids()), Volume.volume_number >= 0,
               Volume.release_date <= today, public_volume_condition())
    )
    # Neighbouring months that have releases: the calendar steps between
    # them, so neither visitors nor crawlers wander through empty months.
    dated = (Volume.series_id.in_(_catalog_ids()), Volume.volume_number >= 0,
             Volume.release_date.isnot(None), public_volume_condition())
    previous = session.scalar(select(func.max(Volume.release_date)).where(*dated, Volume.release_date < start))
    following = session.scalar(select(func.min(Volume.release_date)).where(*dated, Volume.release_date > end))
    return {"month": month, "today": today.isoformat(),
            "latest_month": latest.isoformat()[:7] if latest else None,
            "previous_month": previous.isoformat()[:7] if previous else None,
            "next_month": following.isoformat()[:7] if following else None,
            "volumes": _serialize_releases(session, rows)}


def _new_series(session: Session, limit: int) -> list[dict]:
    real = (Volume.volume_number >= 0) & public_volume_condition(include_announced=False)
    main_catalog = select(CatalogSeries.series_id).where(~CatalogSeries.mangakol_slug.contains("~"))
    first = (
        select(Volume.series_id, func.min(Volume.volume_number).label("first"))
        .where(Volume.series_id.in_(main_catalog), real)
        .group_by(Volume.series_id)
        .subquery()
    )
    started = session.execute(
        select(Volume.series_id, Volume.release_date)
        .join(first, (first.c.series_id == Volume.series_id) & (first.c.first == Volume.volume_number))
        .where(first.c.first <= 1, real, Volume.release_date.isnot(None),
               Volume.release_date <= date.today())
        .order_by(Volume.release_date.desc(), Volume.series_id.desc())
        .limit(limit)
    ).all()
    ids = [sid for sid, _ in started]
    rows = {
        s.id: (s, p) for s, p in session.execute(
            select(Series, Publisher.name).join(Publisher, Publisher.id == Series.publisher_id)
            .where(Series.id.in_(ids))
        )
    }
    offers = {
        sid: (count, price) for sid, count, price in session.execute(
            select(Volume.series_id, func.count(StoreListing.id), func.min(StoreListing.price))
            .join(StoreListing, StoreListing.volume_id == Volume.id)
            .where(Volume.series_id.in_(ids), real, StoreListing.in_stock.is_(True),
                   StoreListing.price.isnot(None))
            .group_by(Volume.series_id)
        )
    }
    volume_counts = dict(session.execute(
        select(Volume.series_id, func.count()).where(Volume.series_id.in_(ids), real)
        .group_by(Volume.series_id)
    ).all())
    covers = _series_covers(session, ids)
    slugs = series_slugs.slugs_for(session, ids)
    only = only_volume_numbers(session, ids)
    return [
        {
            "id": sid,
            "slug": slugs[sid],
            "title": rows[sid][0].title,
            "publisher": rows[sid][1],
            "author": rows[sid][0].author,
            "cover_url": covers.get(sid),
            "volume_count": volume_counts.get(sid, 0),
            "only_volume": only.get(sid),
            "release_date": released.isoformat(),
            "in_stock_offers": offers.get(sid, (0, None))[0],
            "lowest_price": from_cents(offers.get(sid, (0, None))[1]),
        }
        for sid, released in started
    ]


@router.get("/one-shots")
def all_one_shots(
    limit: int = Query(default=500, ge=1, le=2000),
    session: Session = Depends(get_db),
) -> dict:
    """Every one shot (the home shelf only shows a rotating handful)."""
    return {"one_shots": _one_shots(session, reader_interest(session), limit)}


def _one_shots(session: Session, interest: dict[int, float], limit: int) -> list[dict]:
    real = (Volume.volume_number >= 0) & public_volume_condition(include_announced=False)
    main_catalog = select(CatalogSeries.series_id).where(~CatalogSeries.mangakol_slug.contains("~"))
    single = (
        select(Volume.series_id).where(real).group_by(Volume.series_id)
        .having(func.count(Volume.id) == 1)
    )
    rows = session.execute(
        select(Series, Publisher.name).join(Publisher, Publisher.id == Series.publisher_id)
        .where(Series.id.in_(main_catalog), Series.id.in_(single),
               Series.jp_status == "completed", Series.tr_status == "completed")
    ).all()
    ids = [s.id for s, _ in rows]
    offers = {
        sid: (count, price) for sid, count, price in session.execute(
            select(Volume.series_id, func.count(StoreListing.id), func.min(StoreListing.price))
            .join(StoreListing, StoreListing.volume_id == Volume.id)
            .where(Volume.series_id.in_(ids), real, StoreListing.in_stock.is_(True),
                   StoreListing.price.isnot(None))
            .group_by(Volume.series_id)
        )
    }

    def rank(row):
        sid = row[0].id
        count = offers.get(sid, (0, None))[0]
        return (count == 0, -interest.get(sid, 0.0), -count, row[0].title)

    picked = sorted(rows, key=rank)[:limit]
    released = dict(session.execute(
        select(Volume.series_id, Volume.release_date)
        .where(Volume.series_id.in_([s.id for s, _ in picked]), real)
    ).all())
    covers = _series_covers(session, [s.id for s, _ in picked])
    shot_slugs = series_slugs.slugs_for(session, [s.id for s, _ in picked])
    only = only_volume_numbers(session, [s.id for s, _ in picked])
    return [
        {
            "id": series.id,
            "slug": shot_slugs[series.id],
            "title": series.title,
            "publisher": publisher,
            "author": series.author,
            "cover_url": covers.get(series.id),
            "volume_count": 1,
            "only_volume": only.get(series.id),
            "release_date": released[series.id].isoformat() if released.get(series.id) else None,
            "in_stock_offers": offers.get(series.id, (0, None))[0],
            "lowest_price": from_cents(offers.get(series.id, (0, None))[1]),
        }
        for series, publisher in picked
    ]
