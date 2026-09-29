"""Self-hosted covers: volumes.cover_key / cover_source / cover_checked_at.

Covers used to be hot-linked from Mangakol. They are now downloaded once
(store product images first), resized to WebP and served from our own
storage; ``cover_key`` is the storage key of that copy. ``cover_url`` keeps
the external source candidate only.

Revision ID: 0010_self_hosted_covers
Revises: 0009_catalog_details
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0010_self_hosted_covers"
down_revision: str = "0009_catalog_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("volumes")}
    with op.batch_alter_table("volumes") as batch:
        for column in (
            sa.Column("cover_key", sa.String(200), nullable=True),
            sa.Column("cover_source", sa.String(40), nullable=True),
            sa.Column("cover_checked_at", sa.DateTime(timezone=True), nullable=True),
        ):
            if column.name not in existing:
                batch.add_column(column)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("volumes") as batch:
        batch.drop_column("cover_checked_at")
        batch.drop_column("cover_source")
        batch.drop_column("cover_key")
