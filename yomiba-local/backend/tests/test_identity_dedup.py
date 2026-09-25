"""Phase 21: identity & dedup regression suite.

Locks the identity/dedup contract end-to-end against the documented rules:

  * ISBN is the strongest cross-store identity (same ISBN -> one Volume).
  * Berserk/Athica and Berserk/Dark Horse are different Series and must
    NEVER be merged, even with identical title + volume number and no ISBN.
  * Within one edition, results merge without ISBN via
    publisher + series + volume (normalized), and via normalized
    series + volume only when there is a single unambiguous edition.
  * Catalog-only (task 5): products are imported only into EXISTING
    catalog series; ambiguous or non-catalog results are skipped —
    never guessed into a reserved "Bilinmiyor" edition, never created.
  * Duplicates are impossible at the database level (unique constraints).
  * PriceHistory: new listing -> 1 point, price changed -> 1 point,
    unchanged -> no point.
  * Re-importing the same data is idempotent (updates, no new rows).

The suite is self-contained: it exercises ``ImportService.import_result``
and ``ImportService.run_import`` (with fake scrapers) directly against a
test database. API-level contracts (cheapest-first sorting, price history
endpoint) are already covered in ``test_api.py``.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import PriceHistory, Publisher, Series, Store, StoreListing, Volume
from app.normalization.volume import UNNUMBERED_VOLUME
from app.scrapers import SearchResult
from app.services.import_service import ImportAction, ImportService
from tests.helpers import RecordingScraper
from tests.test_import_service import seed_catalog_series

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
    from app.normalization import parse_volume_title

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


def counts(db_session) -> dict:
    return {
        "publishers": db_session.scalar(select(func.count()).select_from(Publisher)),
        "series": db_session.scalar(select(func.count()).select_from(Series)),
        "volumes": db_session.scalar(select(func.count()).select_from(Volume)),
        "listings": db_session.scalar(select(func.count()).select_from(StoreListing)),
        "history": db_session.scalar(select(func.count()).select_from(PriceHistory)),
    }


# ---------------------------------------------------------------------------
# A — ISBN identity (strongest key)
# ---------------------------------------------------------------------------
def test_a_run_level_three_stores_same_isbn_one_volume(db_session):
    """The mandatory cross-store scenario at the full run_import level."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    isbn = "9786051234567"
    service = ImportService(
        db_session,
        scrapers=[
            RecordingScraper("bkm", STORE_NAMES["bkm"], [make_result("bkm", "Berserk 1", "169", isbn=isbn)]),
            RecordingScraper("dr", STORE_NAMES["dr"], [make_result("dr", "Berserk 1", "260", isbn=isbn)]),
            RecordingScraper("amazon", STORE_NAMES["amazon"], [make_result("amazon", "Berserk 1", "163.54", isbn=isbn)]),
        ],
    )
    report = service.run_import("berserk")

    assert all(s.error is None for s in report.stores)
    assert report.total_created == 3  # one listing per store
    assert report.total_errors == 0

    assert counts(db_session) == {
        "publishers": 1,  # reserved "Bilinmiyor" (no publisher info)
        "series": 1,
        "volumes": 1,
        "listings": 3,
        "history": 3,
    }
    volume = db_session.scalar(select(Volume))
    assert volume.isbn == isbn
    prices = {
        l.store.code: l.price
        for l in db_session.scalars(
            select(StoreListing).where(StoreListing.volume_id == volume.id)
        )
    }
    assert prices == {"bkm": 16900, "dr": 26000, "amazon": 16354}


def test_a_isbn_wins_over_publisher_claim(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn="9786051234567", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 1", "200", isbn="9786051234567", publisher="Dark Horse"),
    )
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    series = db_session.get(Series, db_session.scalar(select(Volume)).series_id)
    assert series.publisher.name == "Athica Yayınları"
    # no phantom "Dark Horse" publisher row (read-only resolution)
    assert db_session.scalar(select(func.count()).select_from(Publisher)) == 1


def test_a_isbn_enriches_existing_volume(import_service, db_session):
    """A no-ISBN volume found via series+number gains the ISBN later."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(2,))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 2", "169", publisher="Athica Yayınları"),
        make_result("dr", "Berserk Cilt 2", "200", isbn="9786059999999", publisher="Athica Yayınları"),
    )
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    assert db_session.scalar(select(Volume)).isbn == "9786059999999"


def test_a_isbn_conflict_keeps_existing_and_warns(import_service, db_session, caplog):
    """series+number match with a conflicting ISBN: keep the stored one."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(2,))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 2", "169", isbn="9786051111111", publisher="Athica Yayınları"),
    )
    with caplog.at_level(logging.WARNING, logger="yomiba.import"):
        action = import_service.import_result(
            make_result("dr", "Berserk 2", "200", isbn="9786052222222", publisher="Athica Yayınları")
        )
        db_session.commit()

    # The *listing* is new for D&R, but the *volume* is the existing one:
    # the stored ISBN survives the conflict.
    assert action is ImportAction.CREATED
    volume = db_session.scalar(select(Volume))
    assert volume.isbn == "9786051111111"  # not overwritten
    assert any("ISBN conflict" in r.message for r in caplog.records)
    assert (
        db_session.scalar(
            select(func.count()).select_from(StoreListing).where(StoreListing.volume_id == volume.id)
        )
        == 2  # bkm + dr listings on the same (single) volume
    )


@pytest.mark.parametrize(
    "first_publisher, second_publisher",
    [
        ("Athica Yayınları", "Dark Horse"),
        ("Dark Horse", "Athica Yayınları"),
    ],
)
def test_a_same_isbn_conflicting_publisher_no_phantom_series(
    import_service, db_session, first_publisher, second_publisher
):
    """Same ISBN, conflicting publisher — in BOTH import orders.

    The existing ISBN's Volume/Series identity wins; the second, conflicting
    publisher must not create a phantom Publisher/Series row.
    """
    seed_catalog_series(db_session, "Berserk", first_publisher, volumes=(1,))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn="9786051234567", publisher=first_publisher),
        make_result("dr", "Berserk 1", "200", isbn="9786051234567", publisher=second_publisher),
    )
    assert counts(db_session) == {
        "publishers": 1,
        "series": 1,
        "volumes": 1,
        "listings": 2,
        "history": 2,  # one point per new listing
    }
    series = db_session.scalar(select(Series))
    assert series.publisher.name == first_publisher  # identity of first import wins
    volume = db_session.scalar(select(Volume))
    assert volume.series_id == series.id
    assert {l.store.code for l in volume.listings} == {"bkm", "dr"}


@pytest.mark.parametrize(
    "first_publisher, second_publisher",
    [
        ("Athica Yayınları", "Dark Horse"),
        ("Dark Horse", "Athica Yayınları"),
    ],
)
def test_a_same_isbn_conflicting_series_title_no_phantom_series(
    import_service, db_session, first_publisher, second_publisher
):
    """Same ISBN, conflicting publisher AND series title — both orders."""
    seed_catalog_series(db_session, "Berserk", first_publisher, volumes=(1,))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn="9786051234567", publisher=first_publisher),
        make_result("dr", "Berserk Classic 1", "200", isbn="9786051234567", publisher=second_publisher),
    )
    assert counts(db_session) == {
        "publishers": 1,
        "series": 1,
        "volumes": 1,
        "listings": 2,
        "history": 2,  # one point per new listing
    }
    series = db_session.scalar(select(Series))
    assert series.title == "Berserk"  # the first import's identity wins
    assert series.publisher.name == first_publisher
    volume = db_session.scalar(select(Volume))
    assert volume.series_id == series.id
    assert {l.store.code for l in volume.listings} == {"bkm", "dr"}


# ---------------------------------------------------------------------------
# B — never merge across editions
# ---------------------------------------------------------------------------
def test_b_same_title_volume_different_publishers_no_isbn_stay_separate(import_service, db_session):
    """'Berserk 2' Athica and 'Berserk 2' Dark Horse: two volumes, no merge
    (both editions are catalog series, so the products land on their own)."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    seed_catalog_series(db_session, "Berserk", "Dark Horse")
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 2", "169", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 2", "200", publisher="Dark Horse"),
    )
    series = db_session.scalars(select(Series)).all()
    assert len(series) == 2
    assert {s.publisher.name for s in series} == {"Athica Yayınları", "Dark Horse"}

    by_publisher = {s.publisher.name: s for s in series}
    for name, series in by_publisher.items():
        volumes = db_session.scalars(
            select(Volume).where(Volume.series_id == series.id)
        ).all()
        assert len(volumes) == 1
        assert volumes[0].volume_number == 2
        listings = db_session.scalars(
            select(StoreListing).where(StoreListing.volume_id == volumes[0].id)
        ).all()
        assert len(listings) == 1  # each edition keeps its own store listing

    # Re-importing must not bridge the two editions either.
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 2", "175", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 2", "210", publisher="Dark Horse"),
    )
    assert counts(db_session) == {
        "publishers": 2,
        "series": 2,
        "volumes": 2,
        "listings": 2,
        "history": 4,  # 2 created + 2 price changes
    }


# ---------------------------------------------------------------------------
# C — within one edition: merge without ISBN
# ---------------------------------------------------------------------------
def test_c_cross_store_no_isbn_same_publisher_merges(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk Cilt 2", "169", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 2", "200", publisher="athica yayinlari"),
    )
    assert db_session.scalar(select(func.count()).select_from(Series)) == 1
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    volume = db_session.scalar(select(Volume))
    assert volume.isbn is None
    assert db_session.scalar(
        select(func.count()).select_from(StoreListing).where(StoreListing.volume_id == volume.id)
    ) == 2
    # The two surface forms of the publisher are one row.
    assert db_session.scalar(select(func.count()).select_from(Publisher)) == 1


def test_c_normalization_variants_merge(import_service, db_session):
    """Case / punctuation / whitespace / Turkish letters / volume formats."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    seed_catalog_series(db_session, "Çiçek", "Yeni Yayın")
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 2", "169", publisher="Athica Yayınları"),
        make_result("bkm", "BERSERK, Cilt 2", "170", publisher="ATHICA YAYINLARI"),
        make_result("dr", "berserk (2)", "171"),
        make_result("dr", "Berserk #2", "172"),
        # Turkish folding: ç/Ç and İ/i/ı/I must not split editions.
        make_result("bkm", "Çiçek 1", "100", publisher="Yeni Yayın"),
        make_result("dr", "ÇİÇEK (1)", "110", publisher="yeni yayın"),
    )
    assert db_session.scalar(select(func.count()).select_from(Series)) == 2
    berserk = db_session.scalar(
        select(Series).where(Series.publisher_id == (
            select(Publisher.id).where(Publisher.name == "Athica Yayınları").scalar_subquery()
        ))
    )
    assert (
        db_session.scalar(
            select(func.count()).select_from(Volume).where(Volume.series_id == berserk.id)
        )
        == 1
    )
    assert db_session.scalar(select(func.count()).select_from(Publisher)) == 2


def test_c_no_publisher_single_candidate_merges(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn="9786051234567", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 2", "260"),  # no ISBN, no publisher
    )
    assert db_session.scalar(select(func.count()).select_from(Series)) == 1
    series = db_session.scalar(select(Series))
    assert series.publisher.name == "Athica Yayınları"
    assert (
        db_session.scalar(
            select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 2)
        )
        is not None
    )


def test_c_no_publisher_ambiguous_never_guesses(import_service, db_session):
    """Catalog-only: two catalog editions exist and the product has no
    identifiers -> never guess; the product is skipped (no "Bilinmiyor"
    candidate series is created)."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    seed_catalog_series(db_session, "Berserk", "Dark Horse", volumes=(1,))
    actions = do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", publisher="Athica Yayınları"),
        make_result("dr", "Berserk 1", "200", publisher="Dark Horse"),
        make_result("amazon", "Berserk 3", "180"),  # ambiguous: two editions exist
    )
    assert actions[2] is ImportAction.SKIPPED
    series = db_session.scalars(select(Series)).all()
    assert len(series) == 2  # the two catalog editions, nothing created
    assert (
        db_session.scalar(select(func.count()).select_from(Volume)) == 2
    )  # each edition its own vol 1 — no vol 3 anywhere


def test_c_distinct_titles_never_over_merge(import_service, db_session):
    """Conservative keys: 'Berserk' and 'Berserk of Gluttony' stay apart."""
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    seed_catalog_series(db_session, "Berserk of Gluttony", "Athica Yayınları")
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", publisher="Athica Yayınları"),
        make_result("bkm", "Berserk of Gluttony 1", "175", publisher="Athica Yayınları"),
    )
    assert db_session.scalar(select(func.count()).select_from(Series)) == 2
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 2


# ---------------------------------------------------------------------------
# D — database constraints are the backstop (never silent duplicates)
# ---------------------------------------------------------------------------
def test_d_series_unique_publisher_normalized_title(db_session):
    publisher = Publisher(name="Athica Yayınları", normalized_name="athica yayinlari")
    db_session.add(publisher)
    db_session.flush()
    db_session.add(Series(publisher_id=publisher.id, title="Berserk", normalized_title="berserk", slug="berserk"))
    db_session.flush()
    db_session.add(Series(publisher_id=publisher.id, title="Berserk", normalized_title="berserk", slug="berserk-2"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_d_volume_unique_series_number(db_session):
    publisher = Publisher(name="Athica", normalized_name="athica")
    db_session.add(publisher)
    db_session.flush()
    series = Series(publisher_id=publisher.id, title="Berserk", normalized_title="berserk", slug="berserk")
    db_session.add(series)
    db_session.flush()
    db_session.add(Volume(series_id=series.id, volume_number=2))
    db_session.flush()
    db_session.add(Volume(series_id=series.id, volume_number=2))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_d_isbn_globally_unique_across_volumes(db_session):
    pub_a = Publisher(name="Athica", normalized_name="athica")
    pub_b = Publisher(name="Dark Horse", normalized_name="dark horse")
    db_session.add_all([pub_a, pub_b])
    db_session.flush()
    s_a = Series(publisher_id=pub_a.id, title="Berserk", normalized_title="berserk", slug="berserk")
    s_b = Series(publisher_id=pub_b.id, title="Berserk", normalized_title="berserk", slug="berserk")
    db_session.add_all([s_a, s_b])
    db_session.flush()
    db_session.add(Volume(series_id=s_a.id, volume_number=1, isbn="9786051234567"))
    db_session.flush()
    db_session.add(Volume(series_id=s_b.id, volume_number=1, isbn="9786051234567"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_d_listing_unique_volume_store(db_session):
    publisher = Publisher(name="Athica", normalized_name="athica")
    db_session.add(publisher)
    db_session.flush()
    series = Series(publisher_id=publisher.id, title="Berserk", normalized_title="berserk", slug="berserk")
    db_session.add(series)
    db_session.flush()
    volume = Volume(series_id=series.id, volume_number=1)
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add_all([volume, store])
    db_session.flush()
    db_session.add(StoreListing(volume_id=volume.id, store_id=store.id, product_url="https://x", price=1))
    db_session.flush()
    db_session.add(StoreListing(volume_id=volume.id, store_id=store.id, product_url="https://y", price=2))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ---------------------------------------------------------------------------
# E — price history invariants
# ---------------------------------------------------------------------------
def test_e_price_history_full_lifecycle(import_service, db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    isbn = "9786051234567"
    do_import(import_service, db_session, make_result("bkm", "Berserk 1", "169", isbn=isbn))
    listing = db_session.scalar(select(StoreListing))

    def points():
        return [
            p.price
            for p in db_session.scalars(
                select(PriceHistory).where(PriceHistory.listing_id == listing.id).order_by(PriceHistory.id)
            )
        ]

    assert points() == [16900]  # new listing -> exactly one point

    do_import(import_service, db_session, make_result("bkm", "Berserk 1", "169", isbn=isbn))
    assert points() == [16900]  # unchanged -> no point

    do_import(import_service, db_session, make_result("bkm", "Berserk 1", "163.54", isbn=isbn))
    assert points() == [16900, 16354]  # changed -> one new point

    do_import(import_service, db_session, make_result("bkm", "Berserk 1", None, isbn=isbn))
    assert points() == [16900, 16354]  # missing price -> no point
    assert db_session.scalar(select(StoreListing)).price == 16354  # last known kept

    do_import(import_service, db_session, make_result("bkm", "Berserk 1", "163.54", isbn=isbn))
    assert points() == [16900, 16354]  # back to the same price -> still no point

    do_import(import_service, db_session, make_result("bkm", "Berserk 1", "150", isbn=isbn))
    assert points() == [16900, 16354, 15000]


# ---------------------------------------------------------------------------
# F — idempotent re-imports
# ---------------------------------------------------------------------------
def _service_with(db_session, results_by_store: dict, price_by_store: dict) -> ImportService:
    scrapers = []
    for store, titles in results_by_store.items():
        scrapers.append(
            RecordingScraper(
                store,
                STORE_NAMES[store],
                [make_result(store, t, price_by_store.get(store, "169"), isbn="9786051234567") for t in titles],
            )
        )
    return ImportService(db_session, scrapers=scrapers)


def test_f_second_run_updates_only_no_new_rows(db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    before = counts(db_session)
    assert before == {"publishers": 1, "series": 1, "volumes": 0, "listings": 0, "history": 0}

    first = _service_with(db_session, {"bkm": ["Berserk 1"], "dr": ["Berserk 1"], "amazon": ["Berserk 1"]}, {})
    report1 = first.run_import("berserk")
    assert report1.total_created == 3
    assert report1.total_updated == 0
    after_first = counts(db_session)
    assert after_first == {"publishers": 1, "series": 1, "volumes": 1, "listings": 3, "history": 3}

    # Same data again, with one store's price changed.
    second = _service_with(db_session, {"bkm": ["Berserk 1"], "dr": ["Berserk 1"], "amazon": ["Berserk 1"]}, {"dr": "250"})
    report2 = second.run_import("berserk")
    assert report2.total_created == 0
    assert report2.total_updated == 3
    after_second = counts(db_session)
    assert after_second == {"publishers": 1, "series": 1, "volumes": 1, "listings": 3, "history": 4}

    dr_listing = db_session.scalar(
        select(StoreListing).join(Store).where(Store.code == "dr")
    )
    assert dr_listing.price == 25000
    assert (
        db_session.scalar(select(func.count()).select_from(PriceHistory)) == 4
    )  # the only new point is D&R's price change


def test_f_unnumbered_and_collection_items_stay_stable_across_runs(db_session):
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")
    titles = ["Berserk", "Berserk 1-5 (Kutu)"]  # unnumbered single + collection
    service = _service_with(db_session, {"bkm": titles}, {})
    r1 = service.run_import("berserk")
    assert r1.total_created == 1  # collection skipped
    assert r1.total_skipped == 1
    volume = db_session.scalar(select(Volume))
    assert volume.volume_number == UNNUMBERED_VOLUME

    r2 = _service_with(db_session, {"bkm": titles}, {}).run_import("berserk")
    assert r2.total_updated == 1
    assert r2.total_skipped == 1
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == 1
