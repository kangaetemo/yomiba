"""listing_exclusions: store products an admin removed from a volume.

The importer skips an excluded (store, product URL) for good, so a product
wrongly matched by title (e.g. Kitapseç's novel "İtiraf" on the manga
"İtiraf Cilt 1") cannot come back after it was removed.

Revision ID: 0011_listing_exclusions
Revises: 0010_self_hosted_covers
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0011_listing_exclusions"
down_revision: str = "0010_self_hosted_covers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    if "listing_exclusions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "listing_exclusions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_url", sa.String(2000), nullable=False),
        sa.Column("volume_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("store_id", "product_url", name="uq_listing_exclusion_store_url"),
    )
    op.create_index("ix_listing_exclusions_store_id", "listing_exclusions", ["store_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_listing_exclusions_store_id", table_name="listing_exclusions")
    op.drop_table("listing_exclusions")
