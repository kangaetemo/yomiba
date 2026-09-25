"""Validate a Yomiba SQLite backup read-only before a manual restore."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from db_backup import inspect_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = inspect_database(args.db)
    except (ValueError, sqlite3.DatabaseError, OSError) as exc:
        parser.exit(1, f"Restore check failed: {exc}\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
