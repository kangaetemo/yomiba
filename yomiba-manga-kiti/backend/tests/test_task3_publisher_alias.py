"""Task 3 — publisher alias resolution (root-cause fix for variant-spawned dups).

Covers:
* migration 0003: table creation + guarded/idempotent alias seeding;
* ``_find_publisher`` (read-only, catalog-only): exact match -> alias ->
  None (store imports never create Publisher rows);
* integration: an import carrying a variant publisher name reuses the
  canonical publisher AND the existing series (no phantom rows).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from sqlalchemy import create_engine, func, select, text

from app.models import Publisher, PublisherAlias, Series
from app.normalization import normalize_publisher, parse_volume_title
from app.normalization.text import normalize_text, slugify
from app.scrapers import SearchResult
from app.services.import_service import ImportService

SEED_COUNT = 11
SEED_TARGETS = (2, 11, 30, 133, 204, 239, 433, 633, 713)


@pytest.fixture()
def alembic_url(tmp_path, monkeypatch):
    """Scratch database URL wired into the alembic env (real yomiba.db safe)."""
    import app.config as config_mod

    scratch = tmp_path / "alembic_test.db"
    real = config_mod.get_settings()

    def fake_get_settings():
        from dataclasses import replace

        return replace(real, database_url=f"sqlite:///{scratch}")

    monkeypatch.setattr(config_mod, "get_settings", fake_get_settings)
    return scratch


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
def test_init_db_creates_alias_table_on_fresh_database(alembic_url):
    from app import database

    database.init_db()

    import sqlite3

    conn = sqlite3.connect(alembic_url)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "publisher_aliases" in tables
        assert conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "0004_catalog_exclusion"
        # No publisher rows on a fresh database -> no seeds.
        assert conn.execute(
            "SELECT COUNT(*) FROM publisher_aliases").fetchone()[0] == 0
    finally:
        conn.close()


def test_migration_seeds_aliases_when_publishers_present(alembic_url):
    """Production shape: publishers exist at 0002, 0003 seeds the variants."""
    from alembic import command
    from alembic.config import Config

    from app import database

    backend_dir = Path(__file__).resolve().parents[1]

    # Full schema at head first (no publishers yet -> no seeds).
    database.init_db()
    engine = create_engine(f"sqlite:///{alembic_url}",
                           connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM publisher_aliases"))
        for pid in SEED_TARGETS:
            conn.execute(
                text("INSERT INTO publishers (id, name, normalized_name) "
                     "VALUES (:pid, :name, :norm)"),
                {"pid": pid, "name": f"Yayin-{pid}", "norm": f"yayin {pid}"},
            )
    engine.dispose()

    # Re-run 0003 against a database that now has the target publishers.
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    command.downgrade(config, "0002_original_title")
    command.upgrade(config, "0003_publisher_alias")

    import sqlite3

    conn = sqlite3.connect(alembic_url)
    try:
        rows = conn.execute(
            "SELECT normalized_alias, publisher_id FROM publisher_aliases "
            "ORDER BY publisher_id, normalized_alias").fetchall()
        assert len(rows) == SEED_COUNT, rows
        assert (rows[0]) == ("gerekli seyler", 2)
        assert ("komik seyler", 204) in rows
        assert ("kara karga yayinlari", 713) in rows
        # Idempotent: running the migration again must not duplicate.
        command.upgrade(config, "head")
        assert conn.execute(
            "SELECT COUNT(*) FROM publisher_aliases").fetchone()[0] == SEED_COUNT
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# _resolve_publisher
# ---------------------------------------------------------------------------
def _add_publisher(db_session, name: str) -> Publisher:
    pub = Publisher(name=name, normalized_name=normalize_publisher(name))
    db_session.add(pub)
    db_session.flush()
    return pub


def test_find_publisher_exact_match_reuses_row(db_session, import_service):
    pub = _add_publisher(db_session, "Komikşeyler Yayıncılık")

    resolved = import_service._find_publisher("Komikşeyler Yayıncılık")

    assert resolved.id == pub.id
    assert db_session.scalar(
        select(func.count()).select_from(Publisher)) == 1


def test_find_publisher_alias_variant_reuses_canonical(db_session, import_service):
    canonical = _add_publisher(db_session, "Komikşeyler Yayıncılık")
    db_session.add(PublisherAlias(
        normalized_alias=normalize_publisher("Komik Şeyler"),
        publisher_id=canonical.id,
    ))
    db_session.flush()

    resolved = import_service._find_publisher("Komik Şeyler")

    assert resolved.id == canonical.id
    assert db_session.scalar(
        select(func.count()).select_from(Publisher)) == 1


def test_find_publisher_unknown_name_returns_none(db_session, import_service):
    """Catalog-only (task 5): an unknown publisher name is NOT created by a
    store import — the lookup is read-only and returns None."""
    _add_publisher(db_session, "Komikşeyler Yayıncılık")
    db_session.add(PublisherAlias(
        normalized_alias=normalize_publisher("Komik Şeyler"),
        publisher_id=1,
    ))
    db_session.flush()

    resolved = import_service._find_publisher("Bambaşka Yayınevi")

    assert resolved is None
    assert db_session.scalar(
        select(func.count()).select_from(Publisher)) == 1


def test_find_publisher_orphaned_alias_returns_none(db_session, import_service):
    # Defensive: an alias whose target publisher vanished (FK not enforced on
    # raw test connections) must not break resolution — it yields None.
    db_session.add(PublisherAlias(
        normalized_alias=normalize_publisher("Kayıp Yayınevi"),
        publisher_id=99999,
    ))
    db_session.flush()

    resolved = import_service._find_publisher("Kayıp Yayınevi")

    assert resolved is None


# ---------------------------------------------------------------------------
# Integration: variant publisher name must not spawn a parallel series
# ---------------------------------------------------------------------------
def _volume_result(store: str, title: str, price: str, isbn: str | None):
    parsed = parse_volume_title(title)
    return SearchResult(
        store_id=store,
        store_name="BKM Kitap",
        title=title,
        product_url=f"https://www.bkmkitap.example/{store}-{title.lower()}",
        series_title=parsed.base_title or None,
        volume_number=parsed.volume_number,
        isbn=isbn,
        publisher="Komik Şeyler",  # variant spelling
        price=Decimal(price),
        currency="TRY",
        in_stock=True,
        image_url=None,
    )


def test_variant_publisher_reuses_canonical_publisher_and_series(
    db_session, import_service
):
    canonical = _add_publisher(db_session, "Komikşeyler Yayıncılık")
    db_session.add(PublisherAlias(
        normalized_alias=normalize_publisher("Komik Şeyler"),
        publisher_id=canonical.id,
    ))
    series = Series(
        title="Kızıl Saçlı Pamuk Prenses",
        slug=slugify("Kızıl Saçlı Pamuk Prenses"),
        normalized_title=normalize_text("Kızıl Saçlı Pamuk Prenses"),
        publisher_id=canonical.id,
    )
    db_session.add(series)
    db_session.flush()
    # Catalog-only: register the series in the catalog manifest so the
    # store import may enrich it.
    from app.models import CatalogSeries, Volume

    db_session.add(
        CatalogSeries(
            series_id=series.id,
            mangakol_slug="cat-kizil-sacli-pamuk-prenses",
        )
    )


    volume1 = Volume(series_id=series.id, volume_number=1,
                     isbn="9786255607362")
    db_session.add(volume1)
    db_session.flush()

    import_service.import_result(
        _volume_result("bkm", "Kızıl Saçlı Pamuk Prenses 2", "150", None))
    db_session.commit()

    assert db_session.scalar(
        select(func.count()).select_from(Publisher)) == 1, "phantom publisher"
    assert db_session.scalar(
        select(func.count()).select_from(Series)) == 1, "parallel series"
    vols = db_session.scalars(
        select(Volume).where(Volume.series_id == series.id)
    ).all()
    assert {v.volume_number for v in vols} == {1, 2}
