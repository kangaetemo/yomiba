"""Catalog details from Mangakol: credits, page count, local release date.

series.author / series.illustrator come from the series page ("Yazar",
"Çizer"); volumes.page_count / release_date from each volume page ("Sayfa
Sayısı", "Yayın Tarihi (Yerel)"), read together with the ISBN.
volumes.details_checked_at records when a volume page was last read. All
columns are nullable: unknown stays NULL, nothing is guessed.

Revision ID: 0009_catalog_details
Revises: 0008_volume_covers_range
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0009_catalog_details"
down_revision: str = "0008_volume_covers_range"
branch_labels = None
depends_on = None


def _add(table: str, columns: list[sa.Column]) -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    with op.batch_alter_table(table) as batch:
        for column in columns:
            if column.name not in existing:
                batch.add_column(column)


def upgrade() -> None:
    """Upgrade schema."""
    _add("series", [
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("illustrator", sa.String(200), nullable=True),
    ])
    _add("volumes", [
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("details_checked_at", sa.DateTime(timezone=True), nullable=True),
    ])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("volumes") as batch:
        batch.drop_column("details_checked_at")
        batch.drop_column("release_date")
        batch.drop_column("page_count")
    with op.batch_alter_table("series") as batch:
        batch.drop_column("illustrator")
        batch.drop_column("author")
