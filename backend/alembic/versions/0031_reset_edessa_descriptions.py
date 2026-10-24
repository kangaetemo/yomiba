"""Re-read Edessa texts: its page state also holds the "Çok satanlar"
products, and the first description in it was sometimes one of those
(100 Kurşun's text on Haikyu 10)."""
from alembic import op

revision = "0031_reset_edessa_descriptions"
down_revision = "0030_description_generic"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        "UPDATE volumes SET description = NULL, description_source = NULL, "
        "description_checked_at = NULL, description_generic = NULL "
        "WHERE description_source = 'edessa'"
    )


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
