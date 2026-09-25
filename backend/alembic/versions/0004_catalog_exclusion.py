"""catalog_exclusions: mangakol entries that must never be tracked.

Adds the exclusion table used by ``CatalogSyncService.sync`` to skip
non-manga catalog entries (manga-format adaptations of literature /
novels, game novels, educational textbooks) that were removed from the
tracked catalog in the 2026-09-21 "manga only" scope decision.

Revision ID: 0004_catalog_exclusion
Revises: 0003_publisher_alias
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_catalog_exclusion"
down_revision: str = "0003_publisher_alias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "catalog_exclusions" not in inspector.get_table_names():
        op.create_table(
            "catalog_exclusions",
            sa.Column("mangakol_slug", sa.String(length=200), primary_key=True),
            sa.Column("reason", sa.String(length=300)),
            sa.Column(
                "added_at", sa.DateTime(timezone=True), nullable=False
            ),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("catalog_exclusions")
