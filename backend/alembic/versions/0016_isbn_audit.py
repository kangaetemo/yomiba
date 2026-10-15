"""Durable, read-only ISBN audit queue. No catalogue mutation permission."""
from alembic import op
import sqlalchemy as sa

revision = "0016_isbn_audit"
down_revision = "0015_isbn_safety"
branch_labels = depends_on = None


def upgrade():
    op.create_table("isbn_audit_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requested_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("processed", sa.Integer, nullable=False),
        sa.Column("errors", sa.Integer, nullable=False),
        sa.Column("lease", sa.String(40)), sa.Column("lease_until", sa.DateTime),
        sa.Column("error", sa.Text))
    op.create_index("isbn_one_open_run", "isbn_audit_runs", ["status"], unique=True,
                    sqlite_where=sa.text("status='RUNNING'"))
    op.create_table("isbn_audit_items",
        sa.Column("run_id", sa.Integer, sa.ForeignKey("isbn_audit_runs.id"), primary_key=True),
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id"), primary_key=True),
        sa.Column("completed", sa.Boolean, nullable=False))
    op.create_table("isbn_audit_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("isbn_audit_runs.id"), nullable=False),
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id"), nullable=False),
        sa.Column("checked_at", sa.DateTime, nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("proposed_isbn", sa.String(13)), sa.Column("reason", sa.Text, nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("run_id", "volume_id"))
    op.create_index("ix_isbn_audit_results_volume_id", "isbn_audit_results", ["volume_id"])
    op.create_index("ix_isbn_audit_results_run_id", "isbn_audit_results", ["run_id"])
    op.create_table("isbn_reviews",
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id"), primary_key=True),
        sa.Column("result_id", sa.Integer, sa.ForeignKey("isbn_audit_results.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("workflow", sa.String(30), nullable=False),
        sa.Column("next_check_at", sa.DateTime, nullable=False))
    op.create_index("ix_isbn_reviews_workflow", "isbn_reviews", ["workflow"])
    op.create_index("ix_isbn_reviews_next_check_at", "isbn_reviews", ["next_check_at"])
    op.create_table("isbn_decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("volume_id", sa.Integer, sa.ForeignKey("volumes.id"), nullable=False),
        sa.Column("result_id", sa.Integer, sa.ForeignKey("isbn_audit_results.id"), nullable=False),
        sa.Column("review_version", sa.Integer, nullable=False),
        sa.Column("admin_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("old_isbn", sa.String(20)), sa.Column("new_isbn", sa.String(13)),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("decided_at", sa.DateTime, nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False))
    op.create_index("ix_isbn_decisions_volume_id", "isbn_decisions", ["volume_id"])
    for table in ("isbn_audit_results", "isbn_decisions"):
        for event in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER {table}_{event.lower()} BEFORE {event} ON {table} "
                       "BEGIN SELECT RAISE(ABORT, 'isbn_history_immutable'); END")
        unique = " OR (run_id=NEW.run_id AND volume_id=NEW.volume_id)" if table == "isbn_audit_results" else ""
        op.execute(f"CREATE TRIGGER {table}_replace BEFORE INSERT ON {table} "
                   f"WHEN EXISTS(SELECT 1 FROM {table} WHERE id=NEW.id{unique}) "
                   "BEGIN SELECT RAISE(ABORT, 'isbn_history_immutable'); END")


def downgrade():
    raise RuntimeError("ISBN evidence and admin history must be preserved")
