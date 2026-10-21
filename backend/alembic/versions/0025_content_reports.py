"""content_reports: visitors' "hatalı içerik" reports."""
from alembic import op
import sqlalchemy as sa

revision = "0025_content_reports"
down_revision = "0024_analytics"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "content_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("series_id", sa.Integer),
        sa.Column("volume_id", sa.Integer),
        sa.Column("store_id", sa.Integer),
        sa.Column("user_id", sa.Integer),
        sa.Column("reporter", sa.String(16), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_content_reports_status_created", "content_reports", ["status", "created_at"])


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
