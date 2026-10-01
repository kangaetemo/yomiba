"""Büyülü Dükkan scraper (live-verified against buyuludukkan.com.tr and
from the production server, 2026-10-01).

Same IdeaSoft storefront as Gerekli Şeyler, so the parsing is inherited:

1. Search: ``GET https://www.buyuludukkan.com.tr/arama/<query>?tp=<n>`` —
   server-rendered ``div.showcase`` cards (title, publisher, price, the
   "Tükendi" sold-out label); 24 cards per page.
2. Detail page: the ISBN is the "Stok Kodu" info row.

A comics shop carrying Turkish manga from most publishers (Athica, Kayıp
Kıta, Akılçelen, Beta Byou, ...) plus foreign comics and merchandise; the
non-manga filter and the importer's catalog-only matching keep the rest out.

robots.txt: ``User-agent: * Allow: /``.

The scraper never writes to the database.
"""

from __future__ import annotations

from .gerekliseyler import GerekliseylerScraper


class BuyuludukkanScraper(GerekliseylerScraper):
    store_id = "buyuludukkan"
    store_name = "Büyülü Dükkan"
    base_url = "https://www.buyuludukkan.com.tr"

    def _limits(self) -> tuple[int, int]:
        return (self.settings.buyuludukkan_max_search_pages,
                self.settings.buyuludukkan_max_search_results)
