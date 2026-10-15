"""Prove guard migration on a private, disposable copy of an existing backup."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

from db_backup import inspect_database
from app.services.safety_backup import copy_backup


def rehearse(backup: Path) -> dict:
    """Only the newly allocated temp DB can be migrated; the input is read-only."""
    from app.readiness import check_database_ready, expected_revision
    from app.database import build_engine
    from app.services.isbn_safety import GUARDS

    backup = backup.resolve()
    before = inspect_database(backup)
    head = expected_revision()
    if before["revision"] not in {"0014_catalog_membership", head}:
        raise ValueError("P0 rehearsal requires a 0014 or current-head backup")
    backend = Path(__file__).resolve().parent
    with TemporaryDirectory(prefix="yomiba-p0-migration-") as directory:
        restored = Path(directory) / "restored.db"
        copy_backup(backup, restored)
        if inspect_database(restored) != before:
            raise RuntimeError("Restore differs from the input backup")
        # A child process confines settings changes and runs no API, workers
        # or scrapers. Never change global settings/engine in the parent.
        env = dict(os.environ, DATABASE_URL=f"sqlite:///{restored}", APP_ENV="development",
                   PYTHONPATH=str(backend), AUTO_MIGRATION_BACKUP="1")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend,
            env=env, capture_output=True, text=True, timeout=120,
        )
        if result.returncode:
            raise RuntimeError("P0 migration rehearsal failed; input backup was not modified")
        after = inspect_database(restored)
        if after["identity_summary"] != before["identity_summary"]:
            raise RuntimeError("P0 migration changed protected rows")
        private_files_verified = os.name == "posix"
        if private_files_verified:
            for private_file in Path(directory).iterdir():
                if private_file.is_file() and private_file.stat().st_mode & 0o077:
                    raise RuntimeError("Rehearsal files are not owner-only")
        engine = build_engine(f"sqlite:///{restored}")
        try:
            check_database_ready(engine, check_foreign_keys=True)
        finally:
            engine.dispose()
        if inspect_database(backup) != before:
            raise RuntimeError("Input backup changed during rehearsal")
        return {"verified": True, "source_revision": before["revision"],
                "restored_revision": after["revision"], "database_guards": len(GUARDS),
                "protected_rows_unchanged": True, "source_unchanged": True,
                "private_files_verified": private_files_verified,
                "identity_summary": after["identity_summary"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = rehearse(args.backup)
    except (ValueError, RuntimeError, OSError, sqlite3.DatabaseError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"P0 rehearsal failed: {exc}\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
