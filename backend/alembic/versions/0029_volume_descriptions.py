"""volumes.description (+ source, checked_at): back-cover text from store
product pages, shown on volume and series pages."""
from alembic import op
import sqlalchemy as sa

revision = "0029_volume_descriptions"
down_revision = "0028_email_verification"
branch_labels = depends_on = None


def upgrade():
    # Plain ADD COLUMN: a batch rebuild would drop the ISBN triggers (0018).
    op.add_column("volumes", sa.Column("description", sa.Text))
    op.add_column("volumes", sa.Column("description_source", sa.String(50)))
    op.add_column("volumes", sa.Column("description_checked_at", sa.DateTime(timezone=True)))


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
