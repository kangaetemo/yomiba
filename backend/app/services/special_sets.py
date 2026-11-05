"""Special sets: box sets and bundles shown on their series' pages.

A product such as Komik Şeyler's "JoJo Part 1 + Part 2 Bunkobon Sert
Kapaklı Kutulu Set" is not one catalog volume, so the importer drops it as
a collection. An admin adds it by its product URL and picks the series it
belongs to; its name, image, price and stock come from the store's product
page (``BaseScraper.read_product``) when it is added, on demand, and after
every price refresh of a linked series.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CatalogSeries, Series, SpecialSet, SpecialSetSeries, Store
from ..scrapers.base import BaseScraper
from ..utils import to_cents, utcnow

logger = logging.getLogger("yomiba.special_sets")


class SpecialSetError(ValueError):
    """A request an admin can fix (unknown store, no series, ...)."""


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def scraper_class_for(url: str) -> type[BaseScraper] | None:
    """The registered scraper whose store site serves ``url``."""
    from ..scrapers.registry import registered_scrapers

    host = _host(url)
    if not host:
        return None
    for cls in registered_scrapers().values():
        site = _host(getattr(cls, "base_url", "") or "")
        if site and (host == site or host.endswith("." + site)):
            return cls
    return None


def _store_row(session: Session, cls: type[BaseScraper]) -> Store:
    store = session.scalar(select(Store).where(Store.code == cls.store_id))
    if store is None:
        store = Store(code=cls.store_id, name=cls.store_name)
        session.add(store)
        session.flush()
    return store


def _catalog_series(session: Session, series_ids: list[int]) -> list[Series]:
    ids = list(dict.fromkeys(series_ids))
    if not ids:
        raise SpecialSetError("En az bir seri seç.")
    rows = list(session.scalars(
        select(Series).where(Series.id.in_(ids), Series.id.in_(select(CatalogSeries.series_id)))
    ))
    if len(rows) != len(ids):
        raise SpecialSetError("Seçilen serilerden biri katalogda yok.")
    return rows


def refresh(session: Session, special: SpecialSet, scraper: BaseScraper | None = None) -> bool:
    """Re-read the product page; True when it answered. Caller commits."""
    own = scraper is None
    if scraper is None:
        cls = scraper_class_for(special.product_url)
        if cls is None:
            special.check_error = "mağaza tanınmadı"
            return False
        scraper = cls()
    try:
        info = scraper.read_product(special.product_url)
    except Exception as exc:  # noqa: BLE001 - a store failure is recorded, not raised
        logger.warning("special set %s: product read failed: %s", special.id, exc)
        special.check_error = f"{type(exc).__name__}: {exc}"[:300]
        return False
    finally:
        if own:
            scraper.close()
    if info is None:
        special.check_error = "ürün sayfası okunamadı"
        return False
    special.last_checked = utcnow()
    special.check_error = None
    if info.price is not None:
        special.price = to_cents(info.price)
    if info.in_stock is not None:
        special.in_stock = info.in_stock
    if info.image_url:
        special.image_url = info.image_url
    if info.title and special.title == special.product_url:
        # No admin title yet: the store's product name.
        special.title = info.title[:500]
    return True


def create(
    session: Session, url: str, series_ids: list[int], *, title: str | None = None,
    preorder: bool = False, scraper: BaseScraper | None = None,
) -> SpecialSet:
    """Add a set by its product URL and read the page once. Caller commits."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise SpecialSetError("Geçerli bir ürün linki gir.")
    cls = scraper_class_for(url)
    if cls is None:
        raise SpecialSetError("Bu link takip ettiğimiz mağazalardan birine ait değil.")
    series = _catalog_series(session, series_ids)
    store = _store_row(session, cls)
    if session.scalar(select(SpecialSet.id).where(
            SpecialSet.store_id == store.id, SpecialSet.product_url == url)) is not None:
        raise SpecialSetError("Bu ürün zaten ekli.")
    special = SpecialSet(store_id=store.id, product_url=url, title=(title or "").strip() or url,
                         preorder=preorder)
    special.links = [SpecialSetSeries(series_id=s.id) for s in series]
    session.add(special)
    session.flush()
    refresh(session, special, scraper)
    return special


def update(session: Session, special: SpecialSet, *, title: str | None = None,
           series_ids: list[int] | None = None, preorder: bool | None = None,
           active: bool | None = None) -> SpecialSet:
    if title is not None and title.strip():
        special.title = title.strip()[:500]
    if series_ids is not None:
        series = _catalog_series(session, series_ids)
        special.links = [SpecialSetSeries(series_id=s.id) for s in series]
    if preorder is not None:
        special.preorder = preorder
    if active is not None:
        special.active = active
    session.flush()
    return special


def refresh_for_series(session: Session, series_ids: set[int]) -> int:
    """Re-read the active sets linked to ``series_ids`` (after their price
    refresh). Commits per set; returns how many answered."""
    if not series_ids:
        return 0
    sets = list(session.scalars(
        select(SpecialSet).join(SpecialSetSeries, SpecialSetSeries.set_id == SpecialSet.id)
        .where(SpecialSet.active.is_(True), SpecialSetSeries.series_id.in_(series_ids))
        .distinct()
    ))
    ok = 0
    for special in sets:
        try:
            ok += refresh(session, special)
            session.commit()
        except Exception:  # noqa: BLE001 - one set never fails the refresh
            logger.exception("special set %s: refresh failed", special.id)
            session.rollback()
    return ok


@dataclass
class PublicSet:
    id: int
    title: str
    store: str
    product_url: str
    image_url: str | None
    price: int | None
    in_stock: bool | None
    preorder: bool
    last_checked: object
    #: Other series the set belongs to: (title, slug).
    also: list[tuple[str, str]]


def for_series(session: Session, series_id: int) -> list[PublicSet]:
    """Active sets linked to ``series_id`` whose price was read at least once."""
    from . import series_slugs

    sets = list(session.scalars(
        select(SpecialSet).join(SpecialSetSeries, SpecialSetSeries.set_id == SpecialSet.id)
        .where(SpecialSetSeries.series_id == series_id, SpecialSet.active.is_(True),
               SpecialSet.price.is_not(None))
        .order_by(SpecialSet.created_at.desc())
    ))
    if not sets:
        return []
    other_ids = {link.series_id for s in sets for link in s.links if link.series_id != series_id}
    titles = dict(session.execute(select(Series.id, Series.title).where(Series.id.in_(other_ids))).tuples().all()) if other_ids else {}
    slugs = series_slugs.slugs_for(session, list(other_ids)) if other_ids else {}
    return [PublicSet(
        id=s.id, title=s.title, store=s.store.name, product_url=s.product_url,
        image_url=s.image_url, price=s.price, in_stock=s.in_stock, preorder=s.preorder,
        last_checked=s.last_checked,
        also=[(titles[link.series_id], slugs[link.series_id]) for link in s.links
              if link.series_id in titles and link.series_id in slugs],
    ) for s in sets]
