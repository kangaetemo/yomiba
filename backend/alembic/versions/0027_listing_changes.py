"""listing_changes: per-listing change log of imports (price refresh view)."""
from alembic import op
import sqlalchemy as sa

revision = "0027_listing_changes"
down_revision = "0026_provisional_covers"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "listing_changes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("note", sa.String(32)),
        sa.Column("old_price", sa.Integer),
        sa.Column("new_price", sa.Integer),
        sa.Column("old_in_stock", sa.Boolean),
        sa.Column("new_in_stock", sa.Boolean),
        sa.Column("product_url", sa.String(2000)),
    )
    op.create_index("ix_listing_changes_created", "listing_changes", ["created_at"])
    op.create_index("ix_listing_changes_volume_id", "listing_changes", ["volume_id"])


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
