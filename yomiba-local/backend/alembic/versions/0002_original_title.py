"""series.original_title: original (foreign) title search key.

Column added by the original-title search feature (backfilled from the
mangakol detail-page h2). The production database already received it via a
one-off ALTER, so this migration is guarded and safe to run against both
fresh and un-stamped legacy databases.

Revision ID: 0002_original_title
Revises: 0001_baseline
Create Date: 2026-09-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_original_title"
down_revision: str = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("series")}
    with op.batch_alter_table("series", schema=None) as batch_op:
        if "original_title" not in columns:
            batch_op.add_column(
                sa.Column("original_title", sa.String(length=300), nullable=True)
            )
        batch_op.create_index(
            batch_op.f("ix_series_original_title"),
            ["original_title"],
            unique=False,
            if_not_exists=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("series", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_series_original_title"))
        batch_op.drop_column("original_title")
