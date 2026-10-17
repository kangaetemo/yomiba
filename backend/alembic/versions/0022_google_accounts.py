"""Google sign-in: the Google account id (``sub``) linked to a user."""
from alembic import op
import sqlalchemy as sa

revision = "0022_google_accounts"
down_revision = "0021_series_popularity"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("google_sub", sa.String(255), nullable=True))
    op.create_index("ux_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
