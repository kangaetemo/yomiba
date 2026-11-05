"""Back-in-stock tracking ("Tekrar stokta"): volumes.last_in_stock_at /
stock_checked_at, restock_events, stock_alerts and users.restock_mail.

``last_in_stock_at`` is filled from the stock history so a volume sold out
for months does not look newly tracked: the last price point that was in
stock (or, for legacy points, not known to be sold out). ``stock_checked_at``
stays empty, so the first price refresh after the upgrade only records each
volume's state and writes no events."""
from alembic import op
import sqlalchemy as sa

revision = "0035_restocks"
down_revision = "0034_drop_retired_store"
branch_labels = depends_on = None


def upgrade():
    # Plain ADD COLUMN: a batch rebuild would drop the ISBN triggers (0018).
    op.add_column("volumes", sa.Column("last_in_stock_at", sa.DateTime(timezone=True)))
    op.add_column("volumes", sa.Column("stock_checked_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("restock_mail", sa.Boolean, nullable=False, server_default="1"))
    op.create_table(
        "restock_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("out_since", sa.DateTime(timezone=True)),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="SET NULL")),
        sa.Column("price", sa.Integer),
    )
    op.create_index("ix_restock_events_created", "restock_events", ["created_at"])
    op.create_index("ix_restock_events_volume_id", "restock_events", ["volume_id"])
    op.create_table(
        "stock_alerts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "volume_id", name="uq_stock_alert_user_volume"),
    )
    op.create_index("ix_stock_alerts_user_id", "stock_alerts", ["user_id"])
    op.create_index("ix_stock_alerts_volume_id", "stock_alerts", ["volume_id"])
    op.get_bind().execute(sa.text(
        "UPDATE volumes SET last_in_stock_at = ("
        " SELECT max(ph.checked_at) FROM price_history ph"
        " JOIN store_listings sl ON sl.id = ph.listing_id"
        " WHERE sl.volume_id = volumes.id AND ph.price > 0"
        " AND (ph.in_stock IS NULL OR ph.in_stock = :yes))"
    ), {"yes": True})


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
