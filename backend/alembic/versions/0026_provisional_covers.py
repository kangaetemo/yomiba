"""volumes.cover_provisional + cover_origin_url: covers stored before a
volume was out (usually the Japanese original) are replaced once it is."""
from alembic import op
import sqlalchemy as sa

revision = "0026_provisional_covers"
down_revision = "0025_content_reports"
branch_labels = depends_on = None


def upgrade():
    # Plain ADD COLUMN: a batch rebuild would drop the ISBN triggers (0018).
    op.add_column("volumes", sa.Column("cover_provisional", sa.Boolean))
    op.add_column("volumes", sa.Column("cover_origin_url", sa.String(1000)))


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
