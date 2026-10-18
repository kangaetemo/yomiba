"""store_listings.seen_in_search_at: when the store's SEARCH last returned the
product (``last_checked`` also moves on a product-page re-check)."""
from alembic import op
import sqlalchemy as sa

revision = "0023_listing_seen_in_search"
down_revision = "0022_google_accounts"
branch_labels = depends_on = None


def upgrade():
    op.add_column("store_listings", sa.Column("seen_in_search_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE store_listings SET seen_in_search_at = last_checked")


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
