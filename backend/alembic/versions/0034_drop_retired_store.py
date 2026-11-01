"""Remove a retired store and every row that came from it.

The store's scraper and seed entry are gone. This deletes its listings,
price history, change log, exclusions, ISBN observations, outbound-click
events, the store row itself, its part of import errors and rejection
counts, and covers taken from it (the cover worker fetches those volumes
again from the remaining sources). Volumes keep their catalog data.
"""
import json
import logging

from alembic import op
import sqlalchemy as sa

revision = "0034_drop_retired_store"
down_revision = "0033_cover_error"
branch_labels = depends_on = None

CODE = "amazon"
#: Image and product hosts of the store (covers and clicked links).
HOST_PATTERNS = ("%amazon.%", "%media-amazon%", "%ssl-images-amazon%")

logger = logging.getLogger("alembic.0034")


def _matches(column: str) -> str:
    return "(" + " OR ".join(f"{column} LIKE :p{i}" for i in range(len(HOST_PATTERNS))) + ")"


def upgrade():
    bind = op.get_bind()
    run = lambda sql, **kw: bind.execute(sa.text(sql), {**{f"p{i}": p for i, p in enumerate(HOST_PATTERNS)}, **kw})  # noqa: E731

    # Covers taken from the store: forget them, delete their files below.
    cover_from_store = f"(cover_source = 'store:{CODE}' OR {_matches('cover_origin_url')})"
    keys = {k for (k,) in run(f"SELECT cover_key FROM volumes WHERE cover_key IS NOT NULL AND {cover_from_store}")}
    run(f"UPDATE volumes SET cover_key = NULL, cover_source = NULL, cover_origin_url = NULL, "
        f"cover_provisional = NULL, cover_checked_at = NULL WHERE {cover_from_store}")
    run(f"UPDATE volumes SET cover_url = NULL WHERE {_matches('cover_url')}")
    run("UPDATE volumes SET description = NULL, description_source = NULL, description_checked_at = NULL "
        "WHERE description_source = :code", code=CODE)

    run(f"DELETE FROM analytics_events WHERE {_matches('target_url')}")
    store_id = run("SELECT id FROM stores WHERE code = :code", code=CODE).scalar()
    if store_id is not None:
        listings = "SELECT id FROM store_listings WHERE store_id = :sid"
        run(f"DELETE FROM price_history WHERE listing_id IN ({listings})", sid=store_id)
        for table in ("store_listings", "listing_changes", "listing_exclusions", "store_observations",
                      "analytics_events"):
            run(f"DELETE FROM {table} WHERE store_id = :sid", sid=store_id)
        run("UPDATE content_reports SET store_id = NULL WHERE store_id = :sid", sid=store_id)
        run("DELETE FROM stores WHERE id = :sid", sid=store_id)

    # Import records: "amazon: <err> | dr: <err>" and {"amazon": {...}}.
    for rid, error, reasons in run("SELECT id, error, reasons FROM import_records "
                                   "WHERE error LIKE :e OR reasons LIKE :r", e=f"%{CODE}:%", r=f'%"{CODE}"%').all():
        parts = [p for p in (error or "").split(" | ") if p and not p.startswith(f"{CODE}:")]
        data = json.loads(reasons) if isinstance(reasons, str) else reasons
        if isinstance(data, dict):
            data.pop(CODE, None)
        run("UPDATE import_records SET error = :error, reasons = :reasons WHERE id = :id", id=rid,
            error=" | ".join(parts) or None, reasons=json.dumps(data) if data else None)

    # Cover files no volume uses any more (keys are content hashes, so
    # another volume may share one).
    still_used = {k for (k,) in run("SELECT DISTINCT cover_key FROM volumes WHERE cover_key IS NOT NULL")}
    if keys - still_used:
        try:
            from app.config import get_settings
            from app.services.covers import get_cover_store

            store = get_cover_store(get_settings())
            for key in keys - still_used:
                path = store.local_path(key)
                if path is not None:
                    path.unlink()
        except Exception:  # noqa: BLE001 - a leftover file must not stop the upgrade
            logger.exception("could not delete the store's cover files")


def downgrade():
    raise RuntimeError("ISBN protection: no in-place downgrade past 0018; restore the pre-migration backup")
