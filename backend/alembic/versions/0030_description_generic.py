"""volumes.description_generic: a store text shared by several volumes of a
series (the series blurb BKM repeats on every volume), not the volume's own."""
from alembic import op
import sqlalchemy as sa

revision = "0030_description_generic"
down_revision = "0029_volume_descriptions"
branch_labels = depends_on = None


def upgrade():
    # Plain ADD COLUMN: a batch rebuild would drop the ISBN triggers (0018).
    op.add_column("volumes", sa.Column("description_generic", sa.Boolean))


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
