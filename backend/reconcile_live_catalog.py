"""Audited one-time Mangakol catalog reconciliation; dry-run by default.

The live snapshot is fetched afresh on every invocation. --apply requires
the reviewed snapshot hash and group counts, creates a timestamped SQLite
backup, then performs all catalog changes in one transaction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import build_engine
from app.scrapers.mangakol import MangakolCatalogScraper
from app.services.catalog_reconciliation import reconcile_snapshot


NEW_SLUGS = {
    "death-at-deaths-door",
    "jojo-no-kimyou-na-bouken-part-1-phantom-blood",
    "the-three-body-problem",
    "warcraft-legends-epsilon",
}
SLUG_MOVES = {
    "jojo-no-kimyou-na-bouken":
        "jojo-no-kimyou-na-bouken-part-1-phantom-blood",
}


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def inspect(db_path: Path, old_backup: Path, live_slugs: set[str]) -> tuple[dict, dict[str, int]]:
    with _read_only(db_path) as connection:
        catalog = {r[0] for r in connection.execute(
            "SELECT mangakol_slug FROM catalog_series"
        )}
        exclusions = {r[0] for r in connection.execute(
            "SELECT mangakol_slug FROM catalog_exclusions"
        )}
        orphans = {r[0] for r in connection.execute(
            "SELECT s.id FROM series s WHERE NOT EXISTS "
            "(SELECT 1 FROM catalog_series cs WHERE cs.series_id=s.id)"
        )}
        series_count = connection.execute("SELECT COUNT(*) FROM series").fetchone()[0]
    with _read_only(old_backup) as connection:
        former = dict(connection.execute(
            "SELECT mangakol_slug, series_id FROM catalog_series"
        ))

    groups = {
        "live": len(live_slugs), "series": series_count,
        "A": len(live_slugs & catalog),
        "B": len(live_slugs & exclusions),
        "C": len(live_slugs - catalog - exclusions),
        "D": len(catalog - live_slugs),
        "E": len(exclusions - live_slugs),
        "F": len(orphans),
        "new_slugs": sorted(live_slugs - catalog - exclusions),
        "stale_slugs": sorted(catalog - live_slugs),
    }
    restored = {slug: former[slug] for slug in live_slugs & exclusions if slug in former}
    groups["former_links_verified"] = (
        len(restored) == groups["B"] and set(restored.values()) == orphans
    )
    return groups, restored


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("yomiba.db"))
    parser.add_argument("--former-backup", type=Path, default=Path("yomiba.db.bak-nonmanga"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-hash")
    parser.add_argument("--expected-counts", help="Reviewed A,B,C,D,E,F counts, comma-separated")
    args = parser.parse_args()
    db_path, former_backup = args.db.resolve(), args.former_backup.resolve()
    if not db_path.is_file() or not former_backup.is_file():
        parser.error("database and former manifest backup must exist")

    scraper = MangakolCatalogScraper()
    try:
        refs = scraper.list_manga()
        live_slugs = {r.slug for r in refs}
        snapshot_hash = hashlib.sha256("\n".join(sorted(live_slugs)).encode()).hexdigest()
        groups, former_links = inspect(db_path, former_backup, live_slugs)
        print(json.dumps({"mode": "apply" if args.apply else "dry-run",
                          "snapshot_hash": snapshot_hash, **groups}, ensure_ascii=False, indent=2))
        if not args.apply:
            return 0

        if not args.expected_hash or not args.expected_counts:
            parser.error("--apply requires --expected-hash and --expected-counts")
        try:
            expected_counts = [int(x) for x in args.expected_counts.split(",")]
        except ValueError:
            parser.error("--expected-counts must contain six integers")
        observed_counts = [groups[key] for key in "ABCDEF"]
        if (
            snapshot_hash != args.expected_hash
            or len(expected_counts) != 6
            or observed_counts != expected_counts
            or groups["new_slugs"] != sorted(NEW_SLUGS)
            or groups["stale_slugs"] != sorted(SLUG_MOVES)
            or not groups["former_links_verified"]
        ):
            raise RuntimeError("live/DB state differs from the reviewed audit; no mutation")

        details = {slug: scraper.fetch_manga(slug) for slug in NEW_SLUGS}
    finally:
        scraper.close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = db_path.with_name(db_path.name + f".bak-catalog-reconcile-{stamp}")
    source = _read_only(db_path)
    version_before_backup = source.execute("PRAGMA data_version").fetchone()[0]
    with sqlite3.connect(backup_path) as target:
        source.backup(target)
    print(f"backup: {backup_path}")

    engine = build_engine("sqlite:///" + db_path.as_posix())
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                # A fresh check under the write lock closes the gap between
                # dry-run, backup, and the transactional mutation.
                if source.execute("PRAGMA data_version").fetchone()[0] != version_before_backup:
                    raise RuntimeError("database changed during backup; no mutation")
                current, current_links = inspect(db_path, former_backup, live_slugs)
                if current != groups or current_links != former_links:
                    raise RuntimeError("database changed after backup; no mutation")
                result = reconcile_snapshot(
                    session, live_slugs=live_slugs, former_links=former_links,
                    missing_manga=details, slug_moves=SLUG_MOVES,
                )
                if session.connection().exec_driver_sql(
                    "PRAGMA foreign_key_check"
                ).fetchone():
                    raise RuntimeError("foreign key check failed; transaction rolled back")
    finally:
        source.close()
        engine.dispose()

    with _read_only(db_path) as connection:
        represented = {r[0] for r in connection.execute(
            "SELECT mangakol_slug FROM catalog_series"
        )}
        excluded_live = {r[0] for r in connection.execute(
            "SELECT mangakol_slug FROM catalog_exclusions"
        )} & live_slugs
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    print(json.dumps({
        "result": result.__dict__, "live": len(live_slugs),
        "represented": len(represented & live_slugs),
        "missing": sorted(live_slugs - represented),
        "stale": sorted(represented - live_slugs),
        "excluded_live": sorted(excluded_live),
        "foreign_key_violations": len(foreign_keys),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
