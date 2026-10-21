"""users.email_verified_at + email_tokens: e-mail ownership before a Google
account may take over a password account.

Accounts already linked to Google count as verified; password-only accounts
start unverified (nobody ever proved they read the mailbox)."""
from alembic import op
import sqlalchemy as sa

revision = "0027_email_verification"
down_revision = "0026_provisional_covers"
branch_labels = depends_on = None


def upgrade():
    # Plain ADD COLUMN: a batch rebuild would drop the ISBN triggers (0018).
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE users SET email_verified_at = updated_at WHERE google_sub IS NOT NULL")
    op.create_table(
        "email_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("google_sub", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
