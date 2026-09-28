"""import_records.reasons: per-store rejection counts of the last import.

The matching summary (``{store: {reason: count}}``, e.g. ``no_series_match``,
``publisher_conflict``, ``ambiguous_volume``) used to be logged only. Storing
it on the record lets the admin panel explain WHY a catalog series has no
price listings without replaying the import.

Revision ID: 0007_import_record_reasons
Revises: 0006_publisher_alias_by_name
Create Date: 2026-09-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0007_import_record_reasons"
down_revision: str = "0006_publisher_alias_by_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("import_records")}
    if "reasons" not in columns:
        with op.batch_alter_table("import_records") as batch:
            batch.add_column(sa.Column("reasons", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("import_records") as batch:
        batch.drop_column("reasons")
