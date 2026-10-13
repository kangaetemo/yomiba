"""Stock/product context for observed prices; release evidence for volumes."""
from alembic import op
import sqlalchemy as sa

revision = "0013_offer_evidence"
down_revision = "0012_series_status"
branch_labels = None
depends_on = None


def upgrade():
    for table, columns in (
        ("price_history", [sa.Column("in_stock", sa.Boolean(), nullable=True),
                           sa.Column("product_url", sa.String(2000), nullable=True)]),
        ("volumes", [sa.Column("catalog_released", sa.Boolean(), nullable=True)]),
    ):
        existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for column in columns:
                if column.name not in existing:
                    batch.add_column(column)


def downgrade():
    with op.batch_alter_table("volumes") as batch:
        batch.drop_column("catalog_released")
    with op.batch_alter_table("price_history") as batch:
        batch.drop_column("product_url")
        batch.drop_column("in_stock")
