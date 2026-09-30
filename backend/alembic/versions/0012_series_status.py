"""Publication status from Mangakol: series.jp_status / tr_status.

The series page shows "JP Tamamlandı · TR Devam Ediyor"; the sync stores
the status key of each ("completed", "ongoing", ...). Nullable: unknown
stays NULL. The home page's one-shot shelf reads them.

Revision ID: 0012_series_status
Revises: 0011_listing_exclusions
Create Date: 2026-09-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0012_series_status"
down_revision: str = "0011_listing_exclusions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("series")}
    with op.batch_alter_table("series") as batch:
        for name in ("jp_status", "tr_status"):
            if name not in existing:
                batch.add_column(sa.Column(name, sa.String(20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("series") as batch:
        batch.drop_column("tr_status")
        batch.drop_column("jp_status")
