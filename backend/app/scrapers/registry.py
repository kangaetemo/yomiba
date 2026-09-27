"""Scraper registry.

The single place that lists the available scrapers. Adding a new store means
implementing a ``BaseScraper`` subclass and adding it here (plus seeding the
matching ``Store`` row). Nothing else in the application needs to change —
that is the extensibility guarantee the architecture promises.
"""

from __future__ import annotations

from .amazon import AmazonScraper
from .bkm import BkmScraper
from .cizman import CizmanScraper
from .dr import DrScraper
from .gerekliseyler import GerekliseylerScraper
from .kitapbulan import KitapbulanScraper
from .kitapsec import KitapsecScraper
from .kitapsepeti import KitapsepetiScraper
from .komikseyler import KomikseylerScraper
from .base import BaseScraper
from ..config import get_settings

#: store_id -> scraper class
_SCRAPERS: dict[str, type[BaseScraper]] = {
    cls.store_id: cls
    for cls in (
        BkmScraper,
        AmazonScraper,
        DrScraper,
        KitapsepetiScraper,
        KitapbulanScraper,
        GerekliseylerScraper,
        CizmanScraper,
        KitapsecScraper,
        KomikseylerScraper,
    )
}


def registered_scrapers() -> dict[str, type[BaseScraper]]:
    """Return a copy of the store_id -> scraper class mapping."""
    return dict(_SCRAPERS)


def enabled_store_ids() -> list[str]:
    """Registered stores minus ``settings.disabled_stores`` (in order)."""
    disabled = set(get_settings().disabled_stores)
    return [sid for sid in _SCRAPERS if sid not in disabled]


def get_scrapers(store_ids: list[str] | None = None) -> list[BaseScraper]:
    """Instantiate scrapers, optionally restricted to ``store_ids``.

    Without ``store_ids`` only ENABLED stores run (``DISABLED_STORES`` is
    skipped: stores that block the production host would only add a
    guaranteed failure to every import). Explicit ``store_ids`` are honoured
    as given. Unknown ids are ignored (never raise), so a stale config can't
    take the import down.
    """
    if store_ids is None:
        classes = [_SCRAPERS[sid] for sid in enabled_store_ids()]
    else:
        wanted = set(store_ids)
        classes = [_SCRAPERS[sid] for sid in _SCRAPERS if sid in wanted]
    return [cls() for cls in classes]
