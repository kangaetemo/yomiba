"""Remove store listings that went stale because they were wrong matches.

A listing the store's search has not returned for ``--days`` (default 14)
while the same store's other listings kept being refreshed is re-read on
its product page (schema.org JSON-LD, one request per listing, store pacing
applies) and judged:

  * sil (delete): the page is gone (HTTP 404/410), or its ISBN is a foreign
    edition (Kitapbulan's English Fairy Tail on the Turkish volumes), or its
    ISBN differs from the volume's catalog ISBN (another book).
  * tut (keep): the page shows this volume's ISBN, or gives no ISBN; the
    store simply does not return it in search (Kitap Sepeti, 2026-10-21).

Unnumbered (-1) volumes are skipped: with listings they are legacy
phantoms, already hidden from the site (see legacy_phantom_condition).

Read-only unless ``--apply``; deleting a listing also deletes its price
history. Run on the server:
  docker compose run --rm --no-deps -T backend python cleanup_stale_listings.py
  docker compose run --rm --no-deps -T backend python cleanup_stale_listings.py --apply
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Store, StoreListing, Volume
from app.normalization import normalize_isbn
from app.normalization.isbn import book_isbn, is_foreign_isbn
from app.scrapers.base import BaseScraper
from app.scrapers.registry import registered_scrapers
from app.services.catalog_service import _aware


def page_isbn(scraper: BaseScraper, url: str) -> tuple[str, str | None]:
    """("gone" | "ok" | "unknown", ISBN on the product page)."""
    try:
        response = scraper.get(url)
    except Exception:  # noqa: BLE001 - a transport error decides nothing
        return "unknown", None
    if response.status_code in (404, 410):
        return "gone", None
    if response.status_code >= 400:
        return "unknown", None
    node = scraper.product_json_ld_node(scraper.extract_json_ld(response.text)) or {}
    for key in ("isbn", "gtin13", "gtin", "sku", "mpn"):
        isbn = book_isbn(normalize_isbn(str(node.get(key) or "")))
        if isbn:
            return "ok", isbn
    return "ok", None


def judge(status: str, isbn: str | None, volume: Volume) -> tuple[str, str]:
    if status == "gone":
        return "sil", "ürün sayfası yok"
    if isbn and is_foreign_isbn(isbn):
        return "sil", f"yabancı baskı ({isbn})"
    if isbn and volume.isbn and isbn != volume.isbn:
        return "sil", f"başka kitap ({isbn} ≠ katalog {volume.isbn})"
    if isbn and isbn == volume.isbn:
        return "tut", "doğru ürün, aramada çıkmıyor"
    return "tut", "karar için kanıt yok"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=14)
    parser.add_argument("--apply", action="store_true", help="delete the 'sil' listings")
    args = parser.parse_args()
    window = timedelta(days=args.days)
    classes = registered_scrapers()

    with SessionLocal() as session:
        stores = {s.id: s for s in session.scalars(select(Store))}
        newest = dict(session.execute(
            select(StoreListing.store_id, func.max(StoreListing.last_checked))
            .group_by(StoreListing.store_id)
        ).all())
        candidates = [
            (listing, volume)
            for listing, volume in session.execute(
                select(StoreListing, Volume).join(Volume, Volume.id == StoreListing.volume_id)
                .order_by(StoreListing.store_id, StoreListing.id)
            ).all()
            # -1 rows with listings are legacy phantoms: hidden from the
            # site, cleaned up only through the phantom review.
            if volume.volume_number >= 0 and (
                listing.last_checked is None
                or _aware(newest[listing.store_id]) - _aware(listing.last_checked) > window
            )
        ]
        scrapers: dict[int, BaseScraper] = {}
        verdicts = Counter()
        to_delete: list[StoreListing] = []
        for listing, volume in candidates:
            store = stores[listing.store_id]
            if store.code not in classes:
                continue
            scraper = scrapers.get(store.id) or scrapers.setdefault(store.id, classes[store.code]())
            status, isbn = page_isbn(scraper, listing.product_url)
            verdict, why = judge(status, isbn, volume)
            verdicts[verdict] += 1
            print(f"{verdict}  {store.name}  {volume.series.title} #{volume.volume_number}  "
                  f"{listing.product_url}  — {why}")
            if verdict == "sil":
                to_delete.append(listing)
        for scraper in scrapers.values():
            scraper.close()

        print(f"\n{len(candidates)} ilan {args.days:g} günden eski: "
              f"{verdicts['sil']} silinecek, {verdicts['tut']} kalacak")
        if args.apply and to_delete:
            for listing in to_delete:
                session.delete(listing)
            session.commit()
            print(f"{len(to_delete)} ilan silindi.")
        elif to_delete:
            print("Silmek için aynı komutu --apply ile çalıştır.")


if __name__ == "__main__":
    main()
