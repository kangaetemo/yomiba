"""Price alerts are evaluated and mailed.

* ``price_alerts.triggered_at`` / ``triggered_price``: when (and at which
  best price, cents) the alert last fired. Cleared when the best price goes
  back above the threshold or the threshold changes, so one mail is sent per
  crossing, never on every price refresh.
* ``email_outbox``: mails are queued in the same transaction as the
  decision and sent by a separate step, so an SMTP outage loses nothing.
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_price_alert_mail"
down_revision = "0018_isbn_evidence"
branch_labels = depends_on = None


def upgrade():
    # ALTER TABLE ADD COLUMN only: price_alerts is never recreated.
    op.add_column("price_alerts", sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("price_alerts", sa.Column("triggered_price", sa.Integer, nullable=True))
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body_text", sa.Text, nullable=False),
        sa.Column("body_html", sa.Text, nullable=True),
        sa.Column("kind", sa.String(40), nullable=False),
        #: e.g. "price_alert:<alert id>:<triggered at>" — one mail per event.
        sa.Column("ref", sa.String(120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
    )
    op.create_index("ix_email_outbox_pending", "email_outbox", ["sent_at", "next_attempt_at"])


def downgrade():
    # The chain below (0015-0018) refuses downgrades; failing here too keeps
    # the database at one consistent revision. Roll back from the backup.
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
