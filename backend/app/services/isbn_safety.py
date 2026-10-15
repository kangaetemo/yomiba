"""Temporary P0 freeze. No override exists before the reviewed approval service."""
from __future__ import annotations

MESSAGE = "ISBN ve kayıt taşıma işlemleri inceleme sistemi hazır olana kadar kilitli; mevcut kayıtlar korundu."


class MutationPaused(RuntimeError):
    pass


def reject_legacy_write() -> None:
    raise MutationPaused(MESSAGE)


# Database enforcement also covers sqlite3, bulk SQL and old deployed workers.
# Discovery inserts with a NULL ISBN and ordinary prices/stock updates remain legal.
GUARDS = {
    "isbn_p0_volume_insert": ("volumes", "INSERT", "NEW.isbn IS NOT NULL OR EXISTS (SELECT 1 FROM volumes WHERE id=NEW.id OR (series_id=NEW.series_id AND volume_number=NEW.volume_number))"),
    "isbn_p0_series_insert": ("series", "INSERT", "EXISTS (SELECT 1 FROM series WHERE id=NEW.id OR (publisher_id=NEW.publisher_id AND normalized_title=NEW.normalized_title))"),
    "isbn_p0_publisher_insert": ("publishers", "INSERT", "EXISTS (SELECT 1 FROM publishers WHERE id=NEW.id OR normalized_name=NEW.normalized_name)"),
    "isbn_p0_listing_insert": ("store_listings", "INSERT", "EXISTS (SELECT 1 FROM store_listings WHERE id=NEW.id OR (volume_id=NEW.volume_id AND store_id=NEW.store_id))"),
    "isbn_p0_history_insert": ("price_history", "INSERT", "EXISTS (SELECT 1 FROM price_history WHERE id=NEW.id)"),
    "isbn_p0_volume_update": ("volumes", "UPDATE", "NEW.isbn IS NOT OLD.isbn OR NEW.id IS NOT OLD.id OR NEW.series_id IS NOT OLD.series_id OR NEW.volume_number IS NOT OLD.volume_number"),
    "isbn_p0_volume_delete": ("volumes", "DELETE", "1"),
    "isbn_p0_series_update": ("series", "UPDATE", "(NEW.id IS NOT OLD.id OR NEW.publisher_id IS NOT OLD.publisher_id) AND EXISTS (SELECT 1 FROM volumes WHERE series_id=OLD.id)"),
    "isbn_p0_series_delete": ("series", "DELETE", "EXISTS (SELECT 1 FROM volumes WHERE series_id=OLD.id)"),
    "isbn_p0_publisher_update": ("publishers", "UPDATE", "NEW.id IS NOT OLD.id AND EXISTS (SELECT 1 FROM series s JOIN volumes v ON v.series_id=s.id WHERE s.publisher_id=OLD.id)"),
    "isbn_p0_publisher_delete": ("publishers", "DELETE", "EXISTS (SELECT 1 FROM series s JOIN volumes v ON v.series_id=s.id WHERE s.publisher_id=OLD.id)"),
    "isbn_p0_listing_update": ("store_listings", "UPDATE", "NEW.id IS NOT OLD.id OR NEW.volume_id IS NOT OLD.volume_id OR NEW.store_id IS NOT OLD.store_id"),
    "isbn_p0_listing_delete": ("store_listings", "DELETE", "1"),
    "isbn_p0_history_update": ("price_history", "UPDATE", "NEW.id IS NOT OLD.id OR NEW.listing_id IS NOT OLD.listing_id OR NEW.price IS NOT OLD.price OR NEW.in_stock IS NOT OLD.in_stock OR NEW.checked_at IS NOT OLD.checked_at OR (NEW.product_url IS NOT OLD.product_url AND NOT (OLD.product_url IS NULL AND NEW.product_url IS NOT NULL AND NEW.product_url IS (SELECT product_url FROM store_listings WHERE id=OLD.listing_id)))"),
    "isbn_p0_history_delete": ("price_history", "DELETE", "1"),
    "isbn_p0_store_insert": ("stores", "INSERT", "EXISTS (SELECT 1 FROM stores WHERE id=NEW.id OR code=NEW.code)"),
    "isbn_p0_store_update": ("stores", "UPDATE", "NEW.id IS NOT OLD.id AND EXISTS (SELECT 1 FROM store_listings WHERE store_id=OLD.id)"),
    "isbn_p0_store_delete": ("stores", "DELETE", "EXISTS (SELECT 1 FROM store_listings WHERE store_id=OLD.id)"),
    **{f"isbn_p0_{table}_insert": (table, "INSERT", f"EXISTS (SELECT 1 FROM {table} WHERE id=NEW.id OR (user_id=NEW.user_id AND volume_id=NEW.volume_id))")
       for table in ("user_volume_collections", "wishlist_items", "price_alerts")},
    **{f"isbn_p0_{table}_identity": (table, "UPDATE", "NEW.id IS NOT OLD.id OR NEW.volume_id IS NOT OLD.volume_id OR NEW.user_id IS NOT OLD.user_id")
       for table in ("user_volume_collections", "wishlist_items", "price_alerts")},
}


def definition(name: str) -> str:
    table, event, condition = GUARDS[name]
    return f"CREATE TRIGGER {name} BEFORE {event} ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT, 'isbn_p0_write_paused'); END"


def install_guards(connection) -> None:
    for name in GUARDS:
        connection.execute(definition(name))


def check_guards(connection) -> None:
    found = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
    if any(found.get(name) != definition(name) for name in GUARDS):
        raise RuntimeError("ISBN P0 database guards are incomplete")
