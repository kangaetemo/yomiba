"""Fix catalog ISBN conflicts where OUR database put an ISBN on the wrong volume.

Found by the Mangakol ISBN sync (2026-09-29), verified against BKM:

* Akame, Keser!: ISBN 9786256335523 is "Akame, Keser 3" but sits on Cilt 2.
* Teogonia: ISBN 9786258667103 is "Teogonia 1. Cilt - 2. Cilt (İki Cilt Bir
  Arada)" = catalog Cilt 1, but an old import put it on Cilt 2.

For each case the ISBN moves from the wrong volume to the right one. Store
listings of the wrong volume are moved only with proof: the product page is
fetched and must carry that ISBN (JSON-LD isbn/gtin13/sku or Gerekli Şeyler's
"Stok Kodu" row). Other listings stay. Every price-history point survives; a
store that already lists the right volume keeps one listing (the fresher offer).

The default run is read-only (it only fetches product pages). --apply must be
requested after the dry-run was reviewed; it writes a DB backup first and runs
in one transaction.

    python fix_isbn_conflicts.py --db /data/yomiba.db
    python fix_isbn_conflicts.py --db /data/yomiba.db --apply
    python fix_isbn_conflicts.py --db ... --case "Seri Adı|ISBN|yanlış_cilt|doğru_cilt"
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

DEFAULT_CASES = [
    ("Akame, Keser!", "9786256335523", 2, 3),
    ("Teogonia", "9786258667103", 2, 1),
]

_STOK_KODU_RE = re.compile(
    r"Stok\s*Kodu</div>\s*<div[^>]*product-list-content[^>]*>\s*([^<]+?)\s*</div>", re.I
)


def _isbn(value) -> str | None:
    from app.normalization import normalize_isbn

    return normalize_isbn(str(value)) if value else None


def page_isbn(html: str) -> str | None:
    """ISBN of the product a store page shows, or None when not provable."""
    from app.scrapers.base import BaseScraper

    node = BaseScraper.product_json_ld_node(BaseScraper.extract_json_ld(html))
    if node is not None:
        for key in ("isbn", "gtin13", "gtin", "sku"):
            isbn = _isbn(node.get(key))
            if isbn:
                return isbn
    match = _STOK_KODU_RE.search(html)
    return _isbn(match.group(1)) if match else None


def default_fetch() -> Callable[[str], str | None]:
    from app.scrapers.base import BaseScraper

    scraper = BaseScraper()

    def fetch(url: str) -> str | None:
        try:
            response = scraper.get(url)
        except Exception:  # noqa: BLE001 - unreachable page = no proof
            return None
        return response.text if response.status_code < 400 else None

    return fetch


def inspect_case(connection: sqlite3.Connection, case) -> dict:
    title, isbn, wrong, right = case
    out = {"series": title, "isbn": isbn, "from_volume": wrong, "to_volume": right,
           "status": "blocked", "reason": None, "listings": []}
    series = connection.execute(
        "SELECT s.id FROM series s JOIN catalog_series c ON c.series_id = s.id "
        "WHERE s.title = ?", (title,)).fetchall()
    if len(series) != 1:
        out["reason"] = f"catalog series found {len(series)} times"
        return out
    series_id = series[0][0]

    def volume(number):
        return connection.execute(
            "SELECT id, isbn FROM volumes WHERE series_id = ? AND volume_number = ?",
            (series_id, number)).fetchone()

    holder, target = volume(wrong), volume(right)
    if holder is None or target is None:
        out["reason"] = "volume missing"
        return out
    if holder[1] != isbn:
        out["reason"] = f"Cilt {wrong} holds {holder[1]!r}, not {isbn} (already fixed?)"
        return out
    if target[1] not in (None, isbn):
        out["reason"] = f"Cilt {right} already holds another ISBN {target[1]}"
        return out
    out.update(status="ok", holder_id=holder[0], target_id=target[0])
    for lid, store_id, code, url, price, checked in connection.execute(
            "SELECT l.id, l.store_id, st.code, l.product_url, l.price, l.last_checked "
            "FROM store_listings l JOIN stores st ON st.id = l.store_id "
            "WHERE l.volume_id = ? ORDER BY l.id", (holder[0],)):
        existing = connection.execute(
            "SELECT id FROM store_listings WHERE volume_id = ? AND store_id = ?",
            (target[0], store_id)).fetchone()
        out["listings"].append({"listing_id": lid, "store": code, "product_url": url,
                                "price": price, "last_checked": checked,
                                "target_listing_id": existing[0] if existing else None})
    return out


def add_evidence(plan: dict, fetch: Callable[[str], str | None]) -> None:
    for listing in plan["listings"]:
        html = fetch(listing["product_url"])
        found = page_isbn(html) if html else None
        listing["page_isbn"] = found
        if found == plan["isbn"]:
            listing["action"] = "move"
        else:
            listing["action"] = "keep"
            listing["why"] = "page shows another ISBN" if found else "ISBN not provable from page"


def apply_case(connection: sqlite3.Connection, plan: dict) -> None:
    connection.execute("UPDATE volumes SET isbn = NULL WHERE id = ?", (plan["holder_id"],))
    connection.execute("UPDATE volumes SET isbn = ? WHERE id = ?", (plan["isbn"], plan["target_id"]))
    for listing in plan["listings"]:
        if listing["action"] != "move":
            continue
        existing = listing["target_listing_id"]
        if existing is None:
            connection.execute("UPDATE store_listings SET volume_id = ? WHERE id = ?",
                               (plan["target_id"], listing["listing_id"]))
            continue
        connection.execute("UPDATE price_history SET listing_id = ? WHERE listing_id = ?",
                           (existing, listing["listing_id"]))
        moved = connection.execute(
            "SELECT product_url, price, in_stock, last_checked FROM store_listings WHERE id = ?",
            (listing["listing_id"],)).fetchone()
        kept_checked = connection.execute(
            "SELECT last_checked FROM store_listings WHERE id = ?", (existing,)).fetchone()[0]
        if moved[3] and (kept_checked is None or str(moved[3]) > str(kept_checked)):
            connection.execute(
                "UPDATE store_listings SET product_url = ?, price = ?, in_stock = ?, last_checked = ? "
                "WHERE id = ?", (*moved, existing))
        connection.execute("DELETE FROM store_listings WHERE id = ?", (listing["listing_id"],))


def _cases(raw: list[str] | None):
    if not raw:
        return DEFAULT_CASES
    cases = []
    for item in raw:
        title, isbn, wrong, right = item.split("|")
        cases.append((title.strip(), _isbn(isbn), int(wrong), int(right)))
    return cases


def main(argv: list[str] | None = None, fetch: Callable[[str], str | None] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=Path("yomiba.db"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--case", action="append", help="'Seri|ISBN|yanlış_cilt|doğru_cilt'")
    args = parser.parse_args(argv)
    db_path = args.db.resolve()
    if not db_path.is_file():
        parser.error(f"DB not found: {db_path}")
    cases = _cases(args.case)
    fetch = fetch or default_fetch()

    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as connection:
        plans = [inspect_case(connection, case) for case in cases]
    for plan in plans:  # network outside any write lock
        if plan["status"] == "ok":
            add_evidence(plan, fetch)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "db": str(db_path),
                      "cases": plans}, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0

    todo = [p for p in plans if p["status"] == "ok"]
    if not todo:
        print("Nothing to apply.")
        return 0
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            for plan in todo:  # the DB must still look exactly as inspected
                again = inspect_case(connection, (plan["series"], plan["isbn"],
                                                  plan["from_volume"], plan["to_volume"]))
                if again["status"] != "ok" or [l["listing_id"] for l in again["listings"]] != \
                        [l["listing_id"] for l in plan["listings"]]:
                    raise RuntimeError(f"{plan['series']}: DB changed since inspection; nothing applied")
            backup_path = db_path.with_name(
                db_path.name + ".bak-isbn-fix-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as source:
                with sqlite3.connect(backup_path) as backup:
                    source.backup(backup)
            for plan in todo:
                apply_case(connection, plan)
            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("foreign key check failed; rolled back")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    moved = sum(1 for p in todo for l in p["listings"] if l["action"] == "move")
    print(f"Fixed {len(todo)} case(s), moved {moved} listing(s); backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
