"""Collection keeps two states: "Bende var" (owned) / "Bende yok" (missing).

The third state "wanted" ("İstediğim" / "Takip et") duplicated the separate
wishlist. Each wanted row becomes a wishlist item (unless already there) and
leaves the collection. The CHECK constraint is left as is: changing it would
recreate the table on SQLite; the API accepts only the two states.
"""
from alembic import op

revision = "0020_collection_two_states"
down_revision = "0019_price_alert_mail"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        "INSERT INTO wishlist_items (user_id, volume_id, created_at) "
        "SELECT c.user_id, c.volume_id, c.updated_at FROM user_volume_collections c "
        "WHERE c.status = 'wanted' AND NOT EXISTS (SELECT 1 FROM wishlist_items w "
        "WHERE w.user_id = c.user_id AND w.volume_id = c.volume_id)"
    )
    bind.exec_driver_sql("DELETE FROM user_volume_collections WHERE status = 'wanted'")


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
