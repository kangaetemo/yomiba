"""Rehearsal runs the actual migration on copies, never on its source."""
from pathlib import Path
import json
import os
import sqlite3

import pytest

from db_backup import inspect_database
from p0_rehearse import rehearse
from tests.test_isbn_safety import guarded  # real 0014 -> 0015 temporary fixture


def test_rehearsal_preserves_a_prior_revision_backup_and_is_idempotent(guarded, tmp_path, monkeypatch):
    path, _ = guarded
    manifest = json.loads(path.with_name(path.name + ".isbn-safety.json").read_text())
    source = Path(manifest["backup"])
    before_bytes = source.read_bytes()
    before = inspect_database(source)
    bystander = tmp_path / "must-not-open.db"
    original_url = f"sqlite:///{bystander}"
    monkeypatch.setenv("DATABASE_URL", original_url)
    monkeypatch.setenv("APP_ENV", "production")
    first, second = rehearse(source), rehearse(source)
    assert first == second
    assert first["verified"] and first["source_unchanged"] and first["protected_rows_unchanged"]
    assert first["source_revision"] == "0014_catalog_membership"
    assert first["restored_revision"] == "0015_isbn_safety"
    assert first["identity_summary"] == before["identity_summary"]
    assert source.read_bytes() == before_bytes
    assert inspect_database(source) == before
    assert os.environ["DATABASE_URL"] == original_url and os.environ["APP_ENV"] == "production"
    assert not bystander.exists()


def test_rehearsal_fails_closed_for_tampered_current_head_without_fixing_source(guarded):
    path, _ = guarded
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER isbn_p0_volume_update")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="incomplete"):
        rehearse(path)
    assert path.read_bytes() == before


def test_rehearsal_rejects_an_older_schema_without_touching_it(guarded):
    path, _ = guarded
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE alembic_version SET version_num='0004_catalog_exclusion'")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="0014"):
        rehearse(path)
    assert path.read_bytes() == before
