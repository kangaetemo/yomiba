"""P0 freeze of ISBN/identity writes, with a private online backup/restore check."""
from pathlib import Path
from contextlib import closing
import sqlite3

from alembic import op

revision = "0015_isbn_safety"
down_revision = "0014_catalog_membership"
branch_labels = None
depends_on = None


def upgrade():
    from app.services.isbn_safety import check_guards, install_guards
    from app.services.safety_backup import activation_backup, fingerprint, save_manifest

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        raise RuntimeError("P0 ISBN database protection requires SQLite")
    connection = bind.connection.driver_connection
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    before = fingerprint(connection)
    report = {"before": before, "existing_guard_baseline": False}
    files = list(connection.execute("PRAGMA database_list"))
    path = Path(files[0][2]) if files and files[0][2] else None
    if path and path.is_file():
        # Only back up the committed prior production schema here. Earlier
        # migrations/fresh databases are covered by backup_before_migration.
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            row = source.execute("SELECT version_num FROM alembic_version").fetchone() if "alembic_version" in tables else None
        if row and row[0] == down_revision:
            report.update(activation_backup(path))
            report["existing_guard_baseline"] = True
            if report["restore"]["tables"] != before:
                raise RuntimeError("Guard activation backup differs from the locked source")
    install_guards(connection)
    check_guards(connection)
    after = fingerprint(connection)
    if after != before:
        raise RuntimeError("ISBN guard migration changed protected rows")
    report.update(after=after, protected_rows_unchanged=True, guards_installed=True)
    if path:
        save_manifest(path, report)


def downgrade():
    raise RuntimeError("ISBN protection must not be disabled by downgrade; review the rollback plan")
