"""İstanbul Kitapçısı scraper (live-verified against istanbulkitapcisi.com
and from the production server, 2026-10-01).

Same T-Soft storefront as Kitap Sepeti, so the parsing is inherited:

1. Search: ``GET https://www.istanbulkitapcisi.com/arama?q=<query>&pg=<n>`` —
   server-rendered ``div.product-item`` cards (title, publisher, price).
2. Detail page: schema.org JSON-LD ``Product+Book`` with ``isbn``,
   ``publisher``, ``author``, ``inLanguage`` and ``offers`` (price +
   ``availability``) — the stock source, as the cards carry none. Unseen
   listings are re-checked through the same JSON-LD.

The scraper never writes to the database.
"""

from __future__ import annotations

from .kitapsepeti import KitapsepetiScraper


class IstanbulkitapcisiScraper(KitapsepetiScraper):
    store_id = "istanbulkitapcisi"
    store_name = "İstanbul Kitapçısı"
    base_url = "https://www.istanbulkitapcisi.com"

    def _limits(self) -> tuple[int, int]:
        return (self.settings.istanbulkitapcisi_max_search_pages,
                self.settings.istanbulkitapcisi_max_search_results)
