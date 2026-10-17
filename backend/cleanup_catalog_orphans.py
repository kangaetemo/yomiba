"""Inspect manifest-less series; delete only catalog-only rows on --apply.

The default run is read-only. --apply must be explicitly requested after the
dry-run has been reviewed. Store data, user data and store-enriched ISBNs are
hard blockers; a blocked cleanup never partially deletes rows.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def inspect_orphans(connection: sqlite3.Connection) -> list[dict]:
    connection.row_factory = sqlite3.Row
    volume_columns = {r[1] for r in connection.execute("PRAGMA table_info(volumes)")}
    collection_count = (
        "(SELECT COUNT(*) FROM volumes v WHERE v.series_id=s.id AND v.collection_status IS NOT NULL)"
        if "collection_status" in volume_columns else
        "(SELECT COUNT(*) FROM user_volume_collections c JOIN volumes v ON v.id=c.volume_id WHERE v.series_id=s.id)"
    )
    rows = connection.execute(
        f"""
        SELECT s.id, s.title,
          (SELECT COUNT(*) FROM volumes v WHERE v.series_id=s.id) AS volumes,
          (SELECT COUNT(*) FROM volumes v WHERE v.series_id=s.id AND v.cover_url IS NOT NULL) AS covers,
          (SELECT COUNT(*) FROM volumes v WHERE v.series_id=s.id AND v.isbn IS NOT NULL) AS isbns,
          {collection_count} AS collection_statuses,
          (SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id WHERE v.series_id=s.id) AS listings,
          (SELECT COUNT(*) FROM price_history h JOIN store_listings l ON l.id=h.listing_id JOIN volumes v ON v.id=l.volume_id WHERE v.series_id=s.id) AS price_history,
          (SELECT COUNT(*) FROM wishlist_items w JOIN volumes v ON v.id=w.volume_id WHERE v.series_id=s.id) AS wishlist_items,
          (SELECT COUNT(*) FROM price_alerts a JOIN volumes v ON v.id=a.volume_id WHERE v.series_id=s.id) AS price_alerts
        FROM series s
        WHERE NOT EXISTS (SELECT 1 FROM catalog_series cs WHERE cs.series_id=s.id)
        ORDER BY s.id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def has_protected_data(rows: list[dict]) -> bool:
    protected = (
        "isbns", "collection_statuses", "listings", "price_history",
        "wishlist_items", "price_alerts",
    )
    return any(row[column] for row in rows for column in protected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("yomiba.db"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db_path = args.db.resolve()
    if not db_path.is_file():
        parser.error(f"DB not found: {db_path}")

    if not args.apply:
        with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as connection:
            rows = inspect_orphans(connection)
        print(json.dumps({
            "mode": "dry-run", "db": str(db_path), "series": len(rows),
            "totals": {key: sum(row[key] for row in rows) for key in (
                "volumes", "covers", "isbns", "collection_statuses",
                "listings", "price_history", "wishlist_items", "price_alerts",
            )},
            "protected_data": has_protected_data(rows), "rows": rows,
        }, ensure_ascii=False, indent=2))
        return 0

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            rows = inspect_orphans(connection)
            if has_protected_data(rows):
                raise RuntimeError("cleanup blocked: store, user or ISBN data would be lost")
            backup_path = db_path.with_name(
                db_path.name + ".bak-catalog-cleanup-" +
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            )
            with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as source:
                with sqlite3.connect(backup_path) as backup:
                    source.backup(backup)
            for row in rows:
                connection.execute("DELETE FROM volumes WHERE series_id=?", (row["id"],))
                connection.execute("DELETE FROM series WHERE id=?", (row["id"],))
            remaining = inspect_orphans(connection)
            if remaining or connection.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("cleanup validation failed; transaction rolled back")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    print(f"Deleted {len(rows)} series; backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
