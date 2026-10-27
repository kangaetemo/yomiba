"""volumes.cover_error: why the last cover pass stored nothing for a volume
(shown in the admin list of volumes without a self-hosted cover)."""
from alembic import op
import sqlalchemy as sa

revision = "0033_cover_error"
down_revision = "0032_description_dotted_i"
branch_labels = depends_on = None


def upgrade():
    # Plain ADD COLUMN: a batch rebuild would drop the ISBN triggers (0018).
    op.add_column("volumes", sa.Column("cover_error", sa.String(500)))


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
