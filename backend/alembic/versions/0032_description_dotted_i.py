"""Stored texts with "Hi̇nata": a lowercased "İ" kept its dot as a separate
mark (clean_description drops it from now on)."""
from alembic import op

revision = "0032_description_dotted_i"
down_revision = "0031_reset_edessa_descriptions"
branch_labels = depends_on = None


def upgrade():
    for mark in (775, 183):  # U+0307 combining dot above, U+00B7 middle dot
        op.execute(
            f"UPDATE volumes SET description = REPLACE(description, 'i' || char({mark}), 'i') "
            f"WHERE instr(description, 'i' || char({mark})) > 0"
        )


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
