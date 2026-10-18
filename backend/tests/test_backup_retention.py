"""Pre-migration backups never pile up on the volume (19 Oct 2026: seven
full copies filled Railway's volume and the app refused to start)."""
import os
import sqlite3
from collections import namedtuple

import pytest

from app import database
from app.database import backup_before_migration, db_backups


def _db(tmp_path, revision="0022_google_accounts"):
    db = tmp_path / "yomiba.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE alembic_version(version_num TEXT)")
        c.execute(f"INSERT INTO alembic_version VALUES ('{revision}')")
    return db


def _old(tmp_path, name, age):
    path = tmp_path / name
    path.write_bytes(b"x" * 10)
    stamp = 1_700_000_000 - age
    os.utime(path, (stamp, stamp))
    return path


def test_only_the_newest_older_backup_survives_a_new_one(tmp_path):
    db = _db(tmp_path)
    oldest = _old(tmp_path, "yomiba.db.pre-migration-0017-a.bak", 300)
    p0 = _old(tmp_path, "yomiba.db.p0-isbn-b.bak", 200)
    fix = _old(tmp_path, "yomiba.db.bak-isbn-fix-c", 150)
    newest = _old(tmp_path, "yomiba.db.pre-migration-0021-d.bak", 100)
    sidecars = [_old(tmp_path, n, 0) for n in ("yomiba.db-wal", "yomiba.db.catalog-state.json", "yomiba.db.isbn-safety.json", "other.db.pre-migration-x.bak")]
    backup = backup_before_migration(f"sqlite:///{db}", "0023_listing_seen_in_search")
    assert {p.name for p in db_backups(db)} == {newest.name, backup.name}
    assert not any(p.exists() for p in (oldest, p0, fix))
    assert all(p.exists() for p in sidecars) and db.exists()


def test_a_full_disk_is_reported_before_anything_is_written(tmp_path, monkeypatch):
    db = _db(tmp_path)
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr("shutil.disk_usage", lambda path: Usage(10, 10, 1024))
    with pytest.raises(RuntimeError, match="Not enough disk"):
        backup_before_migration(f"sqlite:///{db}", "0023_listing_seen_in_search")
    assert db_backups(db) == []
    assert database.BACKUP_KEEP == 2
