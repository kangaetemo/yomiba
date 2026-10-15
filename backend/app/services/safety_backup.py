"""Private SQLite snapshots and offline restore verification; no catalogue writes."""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

TABLES = ("series", "catalog_series", "volumes", "stores", "store_listings", "price_history",
          "user_volume_collections", "wishlist_items", "price_alerts", "users", "user_sessions")


def fingerprint(connection) -> dict:
    """Counts + canonical row digests, never user rows or credentials in the report."""
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    result = {}
    for table in TABLES:
        if table not in tables:
            continue  # legacy backups may precede account migrations
        columns = list(connection.execute(f'PRAGMA table_info("{table}")'))
        pk = [r[1] for r in sorted(columns, key=lambda r: r[5]) if r[5]]
        order = ",".join('"' + key + '"' for key in pk) or "rowid"
        digest, count = hashlib.sha256(), 0
        for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}'):
            payload = json.dumps(list(row), ensure_ascii=False, separators=(",", ":"),
                                 default=lambda value: {"blob": value.hex()}).encode()
            digest.update(len(payload).to_bytes(8, "big")); digest.update(payload)
            count += 1
        result[table] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def inspect_file(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("Database file does not exist")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise RuntimeError("Backup quick_check failed")
        fk = connection.execute("PRAGMA foreign_key_check").fetchall()
        return {"tables": fingerprint(connection), "foreign_key_errors": len(fk)}


def copy_backup(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or not source.is_file():
        raise ValueError("Backup needs an existing source and a different destination")
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
        return inspect_file(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def rehearse_restore(backup: Path) -> dict:
    """Restore only into a newly created isolated directory, inspect it read-only."""
    expected = inspect_file(backup)
    with TemporaryDirectory(prefix="yomiba-restore-") as directory:
        actual = copy_backup(backup, Path(directory) / "restored.db")
    if actual != expected or actual["foreign_key_errors"]:
        raise RuntimeError("Restore rehearsal failed identity/FK verification")
    return {"verified": True, **actual}


def activation_backup(source: Path) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = source.with_name(f"{source.name}.p0-isbn-{stamp}-{uuid4().hex[:8]}.bak")
    copy_backup(source, backup)
    restored = rehearse_restore(backup)
    return {"backup": str(backup), "restore": restored}


def save_manifest(source: Path, report: dict) -> None:
    target = source.with_name(source.name + ".isbn-safety.json")
    temp = target.with_name(target.name + "." + uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(report, stream, ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
