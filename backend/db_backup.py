"""Consistent SQLite online backup; never copies a live database file."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
import sqlite3
from pathlib import Path


TABLES = ("series", "catalog_series", "volumes", "store_listings", "price_history")


def inspect_database(path: Path) -> dict:
    """Read-only backup/restore check, with no fixed catalog count."""
    if not path.is_file():
        raise ValueError(f"Database does not exist: {path}")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("SQLite quick_check failed")
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision is None:
            raise ValueError("Alembic revision is missing")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
        invalid = connection.execute(
            "SELECT COUNT(*) FROM catalog_series cs "
            "LEFT JOIN series s ON s.id=cs.series_id WHERE s.id IS NULL"
        ).fetchone()[0]
        if invalid:
            raise ValueError(f"Invalid CatalogSeries references: {invalid}")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("SQLite foreign key integrity check failed")
        from app.services.safety_backup import fingerprint
        return {"revision": revision[0], "counts": counts, "catalog_invalid_references": invalid,
                "identity_summary": fingerprint(connection)}


def backup_database(source: Path, output: Path) -> dict:
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise ValueError("Backup output must differ from source")
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if output.exists():
        raise FileExistsError("Backup output already exists")
    if not output.parent.is_dir():
        raise ValueError("Backup output directory does not exist")
    # Validate source before creating a destination. The online backup API
    # includes committed WAL pages consistently while writers are active.
    inspect_database(source)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as source_db:
        source_db.execute("PRAGMA query_only=ON")
        fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(output)) as backup_db:
                source_db.backup(backup_db)
            backup_report = inspect_database(output)
            from app.services.safety_backup import rehearse_restore
            backup_report["restore_verified"] = rehearse_restore(output)["verified"]
        except Exception:
            output.unlink(missing_ok=True)
            raise
    return backup_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = backup_database(args.source, args.output)
    except (ValueError, FileExistsError, sqlite3.DatabaseError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Backup failed: {exc}\n")
    print(json.dumps({"backup": str(args.output.resolve()), **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
