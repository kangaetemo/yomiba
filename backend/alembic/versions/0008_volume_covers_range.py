"""volumes.covers_from / covers_to: original-volume span of omnibus books.

Mangakol marks 2-in-1 / 3-in-1 editions per volume (``TwoInOne``, label
"Dragon Ball 9&10") while stores title them by that span, so the catalog
volume number alone ("Cilt 5") cannot match "Dragon Ball 9&10". Both
columns stay NULL for regular single-volume books.

Revision ID: 0008_volume_covers_range
Revises: 0007_import_record_reasons
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0008_volume_covers_range"
down_revision: str = "0007_import_record_reasons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("volumes")}
    with op.batch_alter_table("volumes") as batch:
        if "covers_from" not in columns:
            batch.add_column(sa.Column("covers_from", sa.Integer(), nullable=True))
        if "covers_to" not in columns:
            batch.add_column(sa.Column("covers_to", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("volumes") as batch:
        batch.drop_column("covers_to")
        batch.drop_column("covers_from")
