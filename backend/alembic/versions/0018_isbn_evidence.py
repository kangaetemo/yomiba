"""Lift the P0 trigger freeze; ISBN evidence, provenance and change log.

* Drops every ``isbn*`` trigger (P0 identity guards, approval permits,
  audit-history immutability). Writes are governed by the application's
  ISBN resolver and logged in ``isbn_changes`` instead.
* ``volumes.catalog_isbn``: what the catalog source (Mangakol) lists, kept
  apart from ``volumes.isbn`` (what we decided) so a source error never
  overwrites a decision. ``volumes.isbn_source`` records where the current
  ISBN came from ("legacy" for rows set before this revision).
* ``shared_isbns``: other editions of the same work that carry an ISBN
  owned by another volume (publishers print limited/variant books under
  the regular ISBN).
* ``store_observations``: every store product seen by an import, with the
  volume its title points to, the volume its ISBN points to and the rule
  that attached it (or why not). Evidence for the resolver and admins.
* ``isbn_issues``: contradictions the resolver did not settle.

The pre-migration backup (database.backup_before_migration) runs first.
Catalog ISBNs are re-read: ``details_checked_at`` is cleared for released
volumes so the next syncs fill ``catalog_isbn``.
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_isbn_evidence"
down_revision = "0017_isbn_approval"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        names = [r[0] for r in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'isbn%'")]
        for name in names:
            bind.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{name}"')

    # Plain ALTER TABLE ADD COLUMN: never recreate ``volumes`` (its
    # dependents cascade on delete).
    op.add_column("volumes", sa.Column("catalog_isbn", sa.String(20), nullable=True))
    op.add_column("volumes", sa.Column("isbn_source", sa.String(20), nullable=True))
    op.create_index("ix_volumes_catalog_isbn", "volumes", ["catalog_isbn"])
    bind.exec_driver_sql("UPDATE volumes SET isbn_source='legacy' WHERE isbn IS NOT NULL")
    bind.exec_driver_sql(
        "UPDATE volumes SET details_checked_at=NULL WHERE catalog_released IS NOT 0 AND volume_number >= 0")

    op.create_table(
        "isbn_changes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("volume_id", sa.Integer, nullable=False, index=True),
        sa.Column("old_isbn", sa.String(20)),
        sa.Column("new_isbn", sa.String(20)),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("user_id", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "shared_isbns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("isbn", sa.String(20), nullable=False, index=True),
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("isbn", "volume_id", name="uq_shared_isbn_volume"),
    )
    op.create_table(
        "store_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_url", sa.String(2000), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("isbn", sa.String(20)),
        sa.Column("publisher", sa.String(300)),
        sa.Column("price", sa.Integer),
        sa.Column("in_stock", sa.Boolean),
        sa.Column("title_volume_id", sa.Integer, index=True),
        sa.Column("isbn_volume_id", sa.Integer, index=True),
        sa.Column("volume_id", sa.Integer, index=True),
        sa.Column("rule", sa.String(40)),
        sa.Column("reason", sa.String(60)),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("store_id", "product_url", name="uq_observation_store_url"),
    )
    op.create_table(
        "isbn_issues",
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("detail", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    # Like 0015-0017: no in-place downgrade. The evidence tables and the
    # change log are the record of every ISBN decision; roll back by
    # restoring the pre-migration backup instead.
    raise RuntimeError("ISBN protection: evidence and change log must not be discarded by downgrade; "
                       "restore the pre-migration backup")
