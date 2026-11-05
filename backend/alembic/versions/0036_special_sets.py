"""Special sets: box sets / bundles an admin adds by store product URL and
links to catalog series (special_sets, special_set_series)."""
from alembic import op
import sqlalchemy as sa

revision = "0036_special_sets"
down_revision = "0035_restocks"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "special_sets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_url", sa.String(2000), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("image_url", sa.String(1000)),
        sa.Column("price", sa.Integer),
        sa.Column("in_stock", sa.Boolean),
        sa.Column("preorder", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("last_checked", sa.DateTime(timezone=True)),
        sa.Column("check_error", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("store_id", "product_url", name="uq_special_set_store_url"),
    )
    op.create_table(
        "special_set_series",
        sa.Column("set_id", sa.Integer, sa.ForeignKey("special_sets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_special_set_series_series_id", "special_set_series", ["series_id"])


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
