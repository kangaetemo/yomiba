"""Store bestseller ranks per catalog series (home "Popüler seriler")."""
from alembic import op
import sqlalchemy as sa

revision = "0021_series_popularity"
down_revision = "0020_collection_two_states"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "series_popularity",
        sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        #: Sum over store bestseller lists of (1 - rank / list length).
        sa.Column("bestseller_score", sa.Float, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
