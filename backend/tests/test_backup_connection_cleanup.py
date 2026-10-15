"""Backup inspection must close handles even while references stay alive."""
from contextlib import closing
import sqlite3

import pytest

from app.services import safety_backup


def test_backup_and_restore_close_all_database_handles(tmp_path, monkeypatch):
    source = tmp_path / 'source.db'
    with closing(sqlite3.connect(source)) as db:
        db.executescript('CREATE TABLE volumes(id INTEGER PRIMARY KEY, isbn TEXT); '
                         "INSERT INTO volumes VALUES(1,'9786256335424');")
    real_connect = sqlite3.connect
    connections = []

    def tracked_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(safety_backup.sqlite3, 'connect', tracked_connect)
    backup = tmp_path / 'backup.db'
    safety_backup.copy_backup(source, backup)
    assert safety_backup.rehearse_restore(backup)['verified']
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            connection.execute('SELECT 1')
    backup.unlink()  # Also proves Windows can immediately remove the file.
