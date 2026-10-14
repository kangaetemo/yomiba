"""Distinguish announcements from source-absent retained volume rows."""
from alembic import op
import sqlalchemy as sa

revision = "0014_catalog_membership"
down_revision = "0013_offer_evidence"
branch_labels = None
depends_on = None


def upgrade():
    names = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("volumes")}
    if "catalog_present" not in names:
        with op.batch_alter_table("volumes") as batch:
            batch.add_column(sa.Column("catalog_present", sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table("volumes") as batch:
        batch.drop_column("catalog_present")
