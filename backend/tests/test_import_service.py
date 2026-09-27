"""ImportService tests: dedup, resolution priority, upsert, price history.

Catalog-only policy (task 5): imports only enrich EXISTING catalog series
— a product with no catalog match is skipped (no Series/Publisher rows are
ever created by a store import). Tests that import products therefore seed
the catalog first (``seed_catalog_series``).

Includes the mandatory cross-store scenario:

    BKM:    Berserk 1  ISBN X  169 TRY
    D&R:    Berserk 1  ISBN X  260 TRY
    Amazon: Berserk 1  ISBN X  163.54 TRY
        -> one Volume with three listings, cheapest (Amazon) first.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import PriceHistory, Publisher, Series, Store, StoreListing, Volume
from app.normalization import parse_volume_title
from app.normalization.volume import UNNUMBERED_VOLUME
from app.scrapers import SearchResult
from app.scrapers.base import BaseScraper, ScraperError
from app.services.import_service import ImportAction, ImportService

STORE_NAMES = {"bkm": "BKM Kitap", "dr": "D&R", "amazon": "Amazon"}


def make_result(
    store: str,
    title: str,
    price: str | None,
    isbn: str | None = None,
    publisher: str | None = None,
    in_stock: bool = True,
    image: str | None = None,
):
    parsed = parse_volume_title(title)
    return SearchResult(
        store_id=store,
        store_name=STORE_NAMES[store],
        title=title,
        product_url=f"https://www.example.com/{store}/{title.lower().replace(' ', '-')}",
        series_title=parsed.base_title or None,
        volume_number=parsed.volume_number,
        isbn=isbn,
        publisher=publisher,
        price=Decimal(price) if price is not None else None,
        currency="TRY",
        in_stock=in_stock,
        image_url=image,
    )


def do_import(import_service, db_session, *results) -> list[ImportAction]:
    actions = []
    for result in results:
        actions.append(import_service.import_result(result))
        db_session.commit()
    return actions


def seed_catalog_series(
    db_session,
    title: str,
    publisher: str,
    original: str | None = None,
    volumes=(1,),
):
    """A catalog-shaped series (like the mangakol sync creates): registered
    in the catalog manifest, so the catalog-only import may enrich it
    (volumes / listings). Returns the Series row.
    """
    from app.models import CatalogSeries
    from app.normalization import normalize_publisher, normalize_text

    key = normalize_text(title)
    pub = db_session.scalar(
        select(Publisher).where(
            Publisher.normalized_name == normalize_publisher(publisher)
        )
    )
    if pub is None:
        pub = Publisher(
            name=publisher, normalized_name=normalize_publisher(publisher)
        )
        db_session.add(pub)
        db_session.flush()
    series = Series(
        publisher_id=pub.id,
        title=title,
        normalized_title=key,
        slug=key.replace(" ", "-"),
        original_title=normalize_text(original) if original else None,
    )
    db_session.add(series)
    db_session.flush()
    db_session.add(CatalogSeries(series_id=series.id, mangakol_slug=f"cat-{key}"))
    for n in volumes:
        db_session.add(Volume(series_id=series.id, volume_number=n))
    db_session.commit()
    return series


# ---------------------------------------------------------------------------
# Mandatory cross-store scenario
# ---------------------------------------------------------------------------
def test_three_stores_same_isbn_merge_into_one_volume(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    isbn = "9786051234567"
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn=isbn),
        make_result("dr", "Berserk 1", "260", isbn=isbn),
        make_result("amazon", "Berserk 1", "163.54", isbn=isbn),
    )

    volumes = db_session.scalars(select(Volume)).all()
    assert len(volumes) == 1
    volume = volumes[0]
    assert volume.isbn == isbn

    listings = db_session.scalars(
        select(StoreListing).where(StoreListing.volume_id == volume.id)
    ).all()
    assert len(listings) == 3
    prices = {l.store.code: l.price for l in listings}
    assert prices == {"bkm": 16900, "dr": 26000, "amazon": 16354}

    # First import created exactly one history point per listing.
    history = db_session.scalars(select(PriceHistory)).all()
    assert len(history) == 3
    assert sorted(h.price for h in history) == [16354, 16900, 26000]


def test_no_publisher_isbn_still_merges(import_service, db_session):
    """ISBN alone (no publisher info) resolves the correct volume."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    # give the seeded volume its ISBN so the second (no-publisher) result
    # resolves through the ISBN path
    from app.models import Volume as _V

    vol = db_session.scalar(select(_V).where(_V.volume_number == 1))
    vol.isbn = "9786051234567"
    db_session.commit()
    isbn = "9786051234567"
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn=isbn, publisher="Athica Yayınları"),
        make_result("amazon", "Berserk 1", "163.54", isbn=isbn),  # no publisher
    )
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    series = db_session.scalar(select(Series))
    assert series.publisher.name == "Athica Yayınları"


# ---------------------------------------------------------------------------
# Series / publisher resolution
# ---------------------------------------------------------------------------
def test_same_edition_no_duplicates(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk Cilt 1", "169", publisher="Athica Yayınları"),
        make_result("bkm", "BERSERK cilt 1", "175", publisher="athica yayinlari"),
    )
    assert db_session.scalar(select(func.count()).select_from(Series)) == 1
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == 1
    # Publisher deduplicated by normalized name.
    assert db_session.scalar(select(func.count()).select_from(Publisher)) == 1


def test_unknown_publisher_edition_is_skipped(import_service, db_session):
    """Catalog-only: a product whose edition (publisher, title) has no
    existing catalog series is skipped — no parallel series, no phantom
    publisher. The catalog edition keeps its own listing."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 1", "200", isbn="9786057654321", publisher="Dark Horse"),
    )
    assert actions == [ImportAction.CREATED, ImportAction.SKIPPED]
    assert db_session.scalar(select(func.count()).select_from(Series)) == 1
    assert db_session.scalar(select(func.count()).select_from(Publisher)) == 1  # no "Dark Horse" row
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    assert (
        db_session.scalar(select(func.count()).select_from(StoreListing)) == 1
    )  # only the BKM listing


def test_isbn_wins_over_publisher_claim(import_service, db_session):
    """Same ISBN = same physical book, even if the store claims another publisher."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn="9786051234567", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 1", "200", isbn="9786051234567", publisher="Dark Horse"),
    )
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    volume = db_session.scalar(select(Volume))
    series = db_session.get(Series, volume.series_id)
    assert series.publisher.name == "Athica Yayınları"


def test_no_publisher_single_candidate_merges(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1, 2))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn="9786051234567", publisher="Athica Yayınları"),
        # No ISBN, no publisher: "Berserk" has exactly one catalog edition -> merge.
        make_result("dr", "Berserk 2", "260"),
    )
    assert db_session.scalar(select(func.count()).select_from(Series)) == 1
    series = db_session.scalar(select(Series))
    assert series.publisher.name == "Athica Yayınları"
    vol2 = db_session.scalar(
        select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 2)
    )
    assert vol2 is not None
    assert db_session.scalar(
        select(func.count()).select_from(StoreListing).where(StoreListing.volume_id == vol2.id)
    ) == 1


def test_no_publisher_ambiguous_is_skipped(import_service, db_session):
    """Catalog-only: two catalog editions exist and the product has no
    identifiers -> never guess, never create a "Bilinmiyor" candidate:
    the product is skipped, the editions are untouched."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    seed_catalog_series(db_session, "Berserk", "Dark Horse", volumes=(1,))
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 1", "200", publisher="Dark Horse"),
        # Ambiguous: two catalog editions exist, no identifiers -> skip.
        make_result("amazon", "Berserk 3", "180"),
    )
    assert actions[2] is ImportAction.SKIPPED
    series = db_session.scalars(select(Series)).all()
    assert len(series) == 2  # the two seeded editions, nothing new
    # Each edition kept exactly its own seeded volume (no vol 3 anywhere).
    assert (
        db_session.scalar(
            select(func.count()).select_from(Volume)
        )
        == 2
    )


def test_collection_and_garbage_skipped(import_service, db_session):
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1-5 (Kutu)", "600"),
        make_result("bkm", "Berserk Deluxe", "900"),
    )
    assert all(a is ImportAction.SKIPPED for a in actions)
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 0


# ---------------------------------------------------------------------------
# Volume placement
# ---------------------------------------------------------------------------
def test_unnumbered_item_gets_sentinel_and_dedups(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk", "450", publisher="Athica Yayınları"),
        make_result("dr", "Berserk", "480", publisher="Athica Yayınları"),
    )
    volumes = db_session.scalars(select(Volume)).all()
    assert len(volumes) == 1
    assert volumes[0].volume_number == 1  # safe single-volume fallback
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == 2


# ---------------------------------------------------------------------------
# Listing upsert + price history
# ---------------------------------------------------------------------------
def test_listing_upsert_price_change_creates_history(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    isbn = "9786051234567"
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn=isbn),
        make_result("bkm", "Berserk 1", "163.54", isbn=isbn),  # price changed
        make_result("bkm", "Berserk 1", "163.54", isbn=isbn),  # unchanged
    )
    assert actions[0] is ImportAction.CREATED
    assert actions[1] is ImportAction.UPDATED
    assert actions[2] is ImportAction.UPDATED

    listing = db_session.scalar(select(StoreListing))
    assert listing.price == 16354

    points = db_session.scalars(
        select(PriceHistory).where(PriceHistory.listing_id == listing.id)
    ).all()
    assert [p.price for p in points] == [16900, 16354]  # no duplicate on unchanged


def test_missing_price_still_creates_listing_without_history(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    action = import_service.import_result(make_result("bkm", "Berserk 1", None))
    db_session.commit()
    assert action is ImportAction.CREATED
    listing = db_session.scalar(select(StoreListing))
    assert listing.price is None
    assert db_session.scalar(select(func.count()).select_from(PriceHistory)) == 0


def test_no_duplicate_listing_same_volume_store(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    isbn = "9786051234567"
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn=isbn),
        make_result("bkm", "Berserk 1", "170", isbn=isbn),
    )
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == 1

    # Database-level guard: a manual duplicate must be rejected.
    volume = db_session.scalar(select(Volume))
    store = db_session.scalar(select(Store))
    db_session.add(
        StoreListing(volume_id=volume.id, store_id=store.id, product_url="https://x", price=1)
    )
    try:
        db_session.flush()
        raise AssertionError("duplicate listing was accepted")
    except IntegrityError:
        db_session.rollback()


# ---------------------------------------------------------------------------
# Import run (scraper orchestration)
# ---------------------------------------------------------------------------
def _fake_scrapers(results_by_store: dict, failing: set) -> list[BaseScraper]:
    scrapers = []
    for store, results in results_by_store.items():

        def make_search(self, query, _results=results, _store=store, _failing=failing):
            if _store in _failing:
                raise ScraperError(f"{_store}: HTTP 403 blocked")
            return _results

        FakeScraper = type(
            f"FakeScraper_{store}",
            (BaseScraper,),
            {"store_id": store, "store_name": STORE_NAMES[store], "search": make_search},
        )
        scrapers.append(FakeScraper())
    return scrapers


def test_scraper_failure_isolated(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    scrapers = _fake_scrapers(
        {
            "bkm": [make_result("bkm", "Berserk 1", "169", isbn="9786051234567")],
            "dr": [],
        },
        failing={"dr"},
    )
    service = ImportService(db_session, scrapers=scrapers)
    report = service.run_import("berserk")

    bkm = next(s for s in report.stores if s.store_code == "bkm")
    dr = next(s for s in report.stores if s.store_code == "dr")
    assert bkm.results_found == 1
    assert bkm.created == 1
    assert dr.error is not None
    assert "403" in dr.error
    # Data from the healthy store still imported.
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1


def test_bad_result_does_not_stop_run(db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    good = make_result("bkm", "Berserk 1", "169", isbn="9786051234567")
    bad = SearchResult(
        store_id="bkm",
        store_name="BKM Kitap",
        title="Berserk 2",
        product_url="https://www.example.com/bkm/berserk-2",
        price=Decimal("170"),
    )
    # A "poison" result that raises inside import (simulate a data bug).
    import app.services.import_service as imp_mod

    original = imp_mod.ImportService._resolve_volume

    def boom(self, series, isbn, volume_number, result):
        if result.title == "Berserk 2":
            raise ValueError("simulated data bug")
        return original(self, series, isbn, volume_number, result)

    imp_mod.ImportService._resolve_volume = boom
    try:
        scrapers = _fake_scrapers({"bkm": [good, bad]}, failing=set())
        service = ImportService(db_session, scrapers=scrapers)
        report = service.run_import("berserk")
    finally:
        imp_mod.ImportService._resolve_volume = original

    bkm = next(s for s in report.stores if s.store_code == "bkm")
    assert bkm.created == 1
    assert bkm.errors == 1
    # Good result persisted despite the bad one.
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1


# -- bilingual bridge: "Original Title - Local Title" products -------------------

def _catalog_series(db_session, title, original, publisher, volumes=(1, 2, 3)):
    """A catalog-shaped series (like the mangakol sync produces) —
    registered in the catalog manifest so the catalog-only import may
    enrich it."""
    from app.models import CatalogSeries
    from app.normalization import normalize_publisher, normalize_text

    pub = Publisher(name=publisher, normalized_name=normalize_publisher(publisher))
    db_session.add(pub)
    db_session.flush()
    series = Series(
        publisher_id=pub.id,
        title=title,
        normalized_title=normalize_text(title),
        slug=normalize_text(title).replace(" ", "-"),
        original_title=original,
    )
    db_session.add(series)
    db_session.flush()
    db_session.add(
        CatalogSeries(series_id=series.id, mangakol_slug=f"cat-{normalize_text(title)}")
    )
    for n in volumes:
        db_session.add(Volume(series_id=series.id, volume_number=n))
    db_session.commit()
    return series


def test_bilingual_title_bridges_to_catalog_series(import_service, db_session):
    """'One Punch Man 3 - Tek Yumruk' carries BOTH titles of the catalog
    series 'Tek Yumruk' (original 'one punch man') -> must merge there,
    even though the store claims a differently-spelled publisher."""
    series = _catalog_series(db_session, "Tek Yumruk", "one punch man", "Akılçelen Kitaplar")
    do_import(
        import_service,
        db_session,
        make_result("bkm", "One Punch Man 3 - Tek Yumruk", "100", publisher="Akılçelen Kitaplar"),
    )
    assert db_session.scalar(select(func.count()).select_from(Series)) == 1
    vol3 = db_session.scalar(
        select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 3)
    )
    assert vol3 is not None
    assert db_session.scalar(
        select(func.count()).select_from(StoreListing).where(StoreListing.volume_id == vol3.id)
    ) == 1


def test_original_title_alone_bridges(import_service, db_session):
    """An English-only product title that equals the original title of
    exactly one series also bridges ('One Punch Man (Cilt 5)')."""
    series = _catalog_series(db_session, "Tek Yumruk", "one punch man", "Akılçelen Kitaplar",
                             volumes=(1, 5))
    do_import(
        import_service,
        db_session,
        make_result("dr", "One Punch Man (Cilt 5)", "90"),
    )
    assert db_session.scalar(select(func.count()).select_from(Series)) == 1
    vol5 = db_session.scalar(
        select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 5)
    )
    assert vol5 is not None
    assert db_session.scalar(
        select(func.count()).select_from(StoreListing).where(StoreListing.volume_id == vol5.id)
    ) == 1


def test_bilingual_bridge_never_merges_different_series(import_service, db_session):
    """'Tokyo Ghoul:re' is a different series: its key must NOT bridge into
    'Tokyo Gül' just because it starts with the same original title.
    Catalog-only: it is skipped (no new series)."""
    _catalog_series(db_session, "Tokyo Gül", "tokyo ghoul", "Gerekli Şeyler Yayıncılık")
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "Tokyo Ghoul:re Cilt 2", "120", publisher="Gerekli Şeyler"),
    )
    assert actions == [ImportAction.SKIPPED]
    series_list = db_session.scalars(select(Series)).all()
    assert len(series_list) == 1  # only the seeded catalog series
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 3


@pytest.mark.parametrize("publisher", [None, "Bilinmeyen Yayınevi"])
def test_bilingual_ambiguous_skips_bridge(import_service, db_session, publisher):
    """Two catalog editions sharing the same original+local pair and no
    publisher evidence that separates them: the bridge must refuse (never
    guess); catalog-only, the product is skipped."""
    _catalog_series(db_session, "Tek Yumruk", "one punch man", "Akılçelen Kitaplar")
    _catalog_series(db_session, "Tek Yumruk", "one punch man", "Diğer Yayınevi")
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "One Punch Man 3 - Tek Yumruk", "100", publisher=publisher),
    )
    assert actions == [ImportAction.SKIPPED]
    # only the two seeded catalog series — nothing created
    assert db_session.scalar(select(func.count()).select_from(Series)) == 2


def test_bilingual_two_editions_publisher_family_picks_one(import_service, db_session):
    """Same two editions, but the store names the publisher without its
    suffix ("Akılçelen" for "Akılçelen Kitaplar"): that identifies exactly
    one edition, so this is not a guess."""
    akil = _catalog_series(db_session, "Tek Yumruk", "one punch man", "Akılçelen Kitaplar")
    _catalog_series(db_session, "Tek Yumruk", "one punch man", "Diğer Yayınevi")
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "One Punch Man 3 - Tek Yumruk", "100", publisher="Akılçelen"),
    )
    assert actions == [ImportAction.CREATED]
    listing = db_session.scalar(select(StoreListing))
    assert listing.volume.series_id == akil.id
    assert db_session.scalar(select(func.count()).select_from(Series)) == 2


# ---------------------------------------------------------------------------
# Catalog-only policy (task 5) — the import must never create Series rows
# ---------------------------------------------------------------------------
def test_non_catalog_product_creates_nothing(import_service, db_session):
    """A store product with NO catalog match creates nothing: 0 series,
    0 publishers, 0 volumes, 0 listings — the result is skipped."""
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "Sunya 1", "120", publisher="İkinci Adam Yayınları"),
    )
    assert actions == [ImportAction.SKIPPED]
    assert db_session.scalar(select(func.count()).select_from(Series)) == 0
    assert db_session.scalar(select(func.count()).select_from(Publisher)) == 0
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 0
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == 0


def test_catalog_berserk_gets_listing(import_service, db_session):
    """A catalog series + a store product for it -> a volume + listing are
    created (the normal enrichment path still works)."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", publisher="Athica Yayınları"),
    )
    assert actions == [ImportAction.CREATED]
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    vol = db_session.scalar(select(Volume))
    assert vol.volume_number == 1
    assert (
        db_session.scalar(select(func.count()).select_from(StoreListing)) == 1
    )


def test_catalog_missing_volume_is_rejected(import_service, db_session):
    """A catalog series gets a brand-new volume from the store (how a new
    volume of a catalog manga becomes listed)."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 5", "182", publisher="Athica Yayınları"),
    )
    vols = {
        v.volume_number
        for v in db_session.scalars(select(Volume)).all()
    }
    assert vols == {1}
    assert import_service.last_reason == "volume_not_found"
