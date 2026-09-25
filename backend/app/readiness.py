"""Lightweight local database readiness checks; never call scrapers."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine


def expected_revision() -> str:
    backend_dir = Path(__file__).resolve().parent.parent
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("Alembic head is missing")
    return head


def check_database_ready(engine: Engine, *, check_foreign_keys: bool = False) -> None:
    """Raise on missing schema, stale migration or broken catalog reference."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != expected_revision():
            raise RuntimeError("Database Alembic revision is not at head")
        for table in ("series", "catalog_series", "volumes", "store_listings",
                      "price_history", "users", "user_sessions", "import_records"):
            connection.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        invalid = connection.execute(text(
            "SELECT cs.series_id FROM catalog_series cs "
            "LEFT JOIN series s ON s.id=cs.series_id "
            "WHERE s.id IS NULL LIMIT 1"
        )).first()
        if invalid is not None:
            raise RuntimeError("CatalogSeries references a missing Series")
        if check_foreign_keys and engine.url.get_backend_name() == "sqlite":
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise RuntimeError("SQLite foreign key integrity check failed")
