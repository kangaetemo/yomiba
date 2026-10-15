"""Narrow, one-use admin approval permission. Existing P0 identity guards stay."""
from alembic import op
import sqlalchemy as sa

revision = "0017_isbn_approval"
down_revision = "0016_isbn_audit"
branch_labels = depends_on = None


def upgrade():
    from app.services.isbn_approval_guards import definitions
    from app.services.isbn_safety import check_guards
    from app.services.safety_backup import fingerprint

    connection = op.get_bind().connection.driver_connection
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    check_guards(connection)
    before = fingerprint(connection)
    op.create_table("isbn_approval_permits",
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id"), primary_key=True),
        sa.Column("decision_id", sa.Integer, sa.ForeignKey("isbn_decisions.id"), unique=True, nullable=False),
        sa.Column("old_isbn", sa.String(20)),
        sa.Column("new_isbn", sa.String(13), nullable=False),
        sa.Column("token", sa.String(64), nullable=False))
    connection.execute("DROP TRIGGER isbn_p0_volume_update")
    for sql in definitions().values():
        connection.execute(sql)
    check_guards(connection)
    if fingerprint(connection) != before:
        raise RuntimeError("Approval migration changed catalogue or user data")


def downgrade():
    raise RuntimeError("ISBN protection and admin decisions must be preserved; use the documented forward rollback")
