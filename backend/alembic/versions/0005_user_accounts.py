"""Real accounts, sessions and per-user collection ownership.

Legacy personal rows remain owned by disabled users with no password. They
cannot be claimed by public registration or login.
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0005_user_accounts"
down_revision = "0004_catalog_exclusion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('USER', 'ADMIN')", name="ck_user_role"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "user_volume_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("volume_id", sa.Integer(), sa.ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "volume_id", name="uq_collection_user_volume"),
        sa.CheckConstraint("status IN ('owned', 'missing', 'wanted')", name="ck_collection_status"),
    )
    bind = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Preserve *all* legacy IDs present, not only ID 1. The old Volume field
    # has no owner metadata; it belongs to the historical implicit owner 1.
    ids = {row[0] for row in bind.execute(sa.text("SELECT DISTINCT user_id FROM wishlist_items"))}
    ids |= {row[0] for row in bind.execute(sa.text("SELECT DISTINCT user_id FROM price_alerts"))}
    if bind.scalar(sa.text("SELECT COUNT(*) FROM volumes WHERE collection_status IS NOT NULL")):
        ids.add(1)
    for user_id in ids:
        bind.execute(sa.text("INSERT INTO users (id,email,password_hash,display_name,role,is_active,created_at,updated_at) VALUES (:id,:email,NULL,:name,'USER',0,:now,:now)"), {
            "id": user_id, "email": f"legacy-{user_id}@yomiba.invalid", "name": f"Legacy owner {user_id}", "now": now,
        })
    bind.execute(sa.text("INSERT INTO user_volume_collections (user_id,volume_id,status,created_at,updated_at) SELECT 1,id,collection_status,:now,:now FROM volumes WHERE collection_status IS NOT NULL"), {"now": now})
    with op.batch_alter_table("wishlist_items") as batch:
        batch.create_foreign_key("fk_wishlist_user", "users", ["user_id"], ["id"], ondelete="CASCADE")
    with op.batch_alter_table("price_alerts") as batch:
        batch.create_foreign_key("fk_price_alert_user", "users", ["user_id"], ["id"], ondelete="CASCADE")
    with op.batch_alter_table("volumes") as batch:
        batch.drop_column("collection_status")


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade would discard multi-user ownership and sessions; "
        "restore a reviewed pre-upgrade backup instead."
    )
