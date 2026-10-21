"""analytics_events + analytics_salts: first-party site analytics."""
from alembic import op
import sqlalchemy as sa

revision = "0024_analytics"
down_revision = "0023_listing_seen_in_search"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("hour", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("visitor", sa.String(16), nullable=False),
        sa.Column("session", sa.String(32), nullable=False),
        sa.Column("is_returning", sa.Boolean, nullable=False),
        sa.Column("logged_in", sa.Boolean, nullable=False),
        sa.Column("referrer_host", sa.String(200)),
        sa.Column("utm_source", sa.String(100)),
        sa.Column("utm_medium", sa.String(100)),
        sa.Column("utm_campaign", sa.String(100)),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("browser", sa.String(30), nullable=False),
        sa.Column("os", sa.String(30), nullable=False),
        sa.Column("country", sa.String(2)),
        sa.Column("series_id", sa.Integer),
        sa.Column("volume_id", sa.Integer),
        sa.Column("store_id", sa.Integer),
        sa.Column("listing_id", sa.Integer),
        sa.Column("target_url", sa.String(2000)),
        sa.Column("query", sa.String(200)),
        sa.Column("value", sa.Integer),
    )
    op.create_index("ix_analytics_events_ts", "analytics_events", ["ts"])
    op.create_index("ix_analytics_events_day_kind", "analytics_events", ["day", "kind"])
    op.create_index("ix_analytics_events_session", "analytics_events", ["session"])
    op.create_table(
        "analytics_salts",
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("salt", sa.String(64), nullable=False),
    )


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
