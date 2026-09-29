"""Phase 19: DB-first search with automatic background import.

Covers the required scenarios (catalog-only policy: a background import is
scheduled ONLY for queries the catalog matches — an import for anything
else could never produce visible results, so it must not run at all):

 1. DB hit with fresh data        -> no import
 2. DB hit with stale data        -> background import triggered
 3. DB miss                       -> NO import, honest "idle" (not-in-catalog)
 4. concurrent identical queries  -> only one import
 5. normalized equivalent queries -> same import key
 6. scraper failure               -> existing data kept
 7. partial scraper success       -> retained
 8. fresh results                 -> returned without waiting for scraper
 9. import status                 -> represented correctly
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.models import CatalogSeries, ImportRecord, Series, StoreListing
from app.services import search_service
from app.services.background_import import (
    BackgroundImportRunner,
    normalized_query_key,
)
from app.services.import_service import ImportService
from app.utils import utcnow
from tests.helpers import RecordingScraper
from tests.test_import_service import make_result, do_import


# -- fixtures -------------------------------------------------------------------

@pytest.fixture()
def sessions(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def runner_factory(sessions):
    def make(scrapers: list, **kwargs) -> BackgroundImportRunner:
        def factory(store_ids=None):
            return list(scrapers)

        return BackgroundImportRunner(sessions, scraper_factory=factory, **kwargs)

    return make


def seed_catalog(sessions, *results):
    """Register the series behind ``results`` in the catalog manifest
    (rows created directly — standing in for the mangakol sync), THEN run a
    synchronous import (bypassing the runner) so volumes/listings exist.
    Seeded data stands in for the tracked (mangakol) catalog, which is what
    search serves. The catalog-only import would skip the products on a
    bare DB, so the catalog rows must exist first."""
    from app.normalization import normalize_text, parse_volume_title
    from app.models import Publisher, Volume

    session = sessions()
    try:
        pub = Publisher(name="Seed Publisher", normalized_name="seed publisher")
        session.add(pub)
        session.flush()
        for r in results:
            parsed = parse_volume_title(r.title)
            key = normalize_text(parsed.base_title or r.title)
            exists = session.scalar(
                select(Series).where(
                    Series.publisher_id == pub.id,
                    Series.normalized_title == key,
                )
            )
            if exists is None:
                series = Series(
                    publisher_id=pub.id,
                    title=(parsed.base_title or r.title),
                    normalized_title=key,
                    slug=key.replace(" ", "-"),
                )
                session.add(series)
                session.flush()
                session.add(
                    CatalogSeries(series_id=series.id, mangakol_slug=f"seed-{series.id}")
                )
                exists = series
            number = parsed.volume_number or 1
            if session.scalar(select(Volume.id).where(Volume.series_id == exists.id, Volume.volume_number == number)) is None:
                session.add(Volume(series_id=exists.id, volume_number=number))
                session.flush()
        session.commit()
    finally:
        session.close()

    session = sessions()
    try:
        store_ids = sorted({r.store_id for r in results})
        scrapers = [
            RecordingScraper(
                store_id=sid,
                store_name="X",
                results=[r for r in results if r.store_id == sid],
            )
            for sid in store_ids
        ]
        ImportService(session, scrapers=scrapers).run_import(results[0].title)
    finally:
        session.close()


def set_fresh(sessions, key: str, minutes_ago: float = 0.0) -> None:
    """Write an ImportRecord whose last success is ``minutes_ago`` minutes old."""
    session = sessions()
    try:
        when = utcnow() - timedelta(minutes=minutes_ago)
        record = session.scalar(
            select(ImportRecord).where(ImportRecord.normalized_query == key)
        )
        if record is None:
            record = ImportRecord(normalized_query=key)
            session.add(record)
        record.status = "success"
        record.last_attempt_at = when
        record.last_success_at = when
        record.results_found = 1
        record.stores_ok = 1
        session.commit()
    finally:
        session.close()


# -- 1. fresh data -> no import ---------------------------------------------------

def test_fresh_db_hit_no_import(sessions, runner_factory):
    seed_catalog(sessions, make_result("bkm", "Berserk 1", "182", isbn="9786256335424"))
    key = normalized_query_key("berserk")
    set_fresh(sessions, key, minutes_ago=5)

    scraper = RecordingScraper(results=[make_result("bkm", "Berserk 20", "182")])
    runner = runner_factory([scraper])

    session = sessions()
    try:
        outcome = search_service.search_with_auto_import(session, "berserk", runner)
    finally:
        session.close()

    assert len(outcome.matches) == 1
    assert outcome.import_status.state == "fresh"
    assert scraper.calls == []  # scraper never touched
    assert not runner.is_running(key)


# -- 2. stale data -> background import triggered ----------------------------------

def test_stale_db_hit_triggers_background_import(sessions, runner_factory):
    seed_catalog(sessions, make_result("bkm", "Berserk 1", "182", isbn="9786256335424"))
    key = normalized_query_key("berserk")
    set_fresh(sessions, key, minutes_ago=120)  # older than the 60 min TTL

    scraper = RecordingScraper(delay=0.3)
    runner = runner_factory([scraper])

    session = sessions()
    try:
        outcome = search_service.search_with_auto_import(session, "berserk", runner)
    finally:
        session.close()

    assert len(outcome.matches) == 1  # existing data returned immediately
    assert outcome.import_status.state == "refreshing"
    assert runner.is_running(key)
    assert runner.wait_for(key)
    assert scraper.calls == ["berserk"]
    record = runner.get_record(key)
    assert record.status == "success"


# -- 3. DB miss -> NO import (catalog-only policy) ---------------------------------

def test_db_miss_no_import_catalog_only(sessions, runner_factory):
    """A query the catalog does not match must NOT start a background
    import: the import could never produce visible (catalog) results, so
    the search answers the honest "idle" / not-in-catalog state instantly.
    """
    scraper = RecordingScraper(results=[make_result("bkm", "Naruto 1", "150")])
    runner = runner_factory([scraper])

    session = sessions()
    try:
        outcome = search_service.search_with_auto_import(session, "naruto", runner)
    finally:
        session.close()

    assert outcome.matches == []
    assert outcome.import_status.state == "idle"
    assert scraper.calls == []  # no store was ever contacted
    assert runner.get_record("naruto") is None  # nothing recorded either

    session = sessions()
    try:
        assert session.scalar(select(func.count(Series.id))) == 0
        outcome = search_service.search_with_auto_import(session, "naruto", runner)
    finally:
        session.close()
    assert len(outcome.matches) == 0
    assert outcome.import_status.state == "idle"
    assert not runner.is_running("naruto")


def test_db_miss_with_old_failed_record_stays_idle(sessions, runner_factory):
    """A non-matching query with an old failed record (pre-policy) must
    still report the honest "idle" state — never "failed", never a job."""
    runner = runner_factory([])
    session = sessions()
    try:
        session.add(
            ImportRecord(
                normalized_query="dante",
                last_query="dante",
                status="failed",
                last_attempt_at=utcnow() - timedelta(hours=2),
                error="boom",
            )
        )
        session.commit()
        outcome = search_service.search_with_auto_import(session, "dante", runner)
    finally:
        session.close()
    assert outcome.matches == []
    assert outcome.import_status.state == "idle"
    assert not runner.is_running("dante")


# -- 4. concurrent identical queries -> one import -----------------------------------

def test_concurrent_identical_queries_single_import(sessions, runner_factory):
    scraper = RecordingScraper(delay=0.4)
    runner = runner_factory([scraper])
    key = normalized_query_key("berserk")

    assert runner.submit(key, "berserk") is True
    assert runner.submit(key, "BERSERK") is False  # same normalized key
    session = sessions()
    try:
        # A search while a job for the same key runs must not start
        # another one. ("berserk" is not in the catalog here, so the search
        # itself answers "idle" — the dedup check is the assertion.)
        outcome = search_service.search_with_auto_import(session, "berserk", runner)
    finally:
        session.close()
    assert outcome.import_status.state == "idle"

    assert runner.wait_for(key)
    assert scraper.calls == ["berserk"]  # exactly one import


# -- 5. normalized equivalent queries -> same import key --------------------------------

def test_normalized_equivalent_queries_same_key(sessions, runner_factory):
    assert (
        normalized_query_key("Berserk")
        == normalized_query_key("BERSERK")
        == normalized_query_key("berserk")
    )

    scraper = RecordingScraper(delay=0.3)
    runner = runner_factory([scraper])

    assert runner.submit(normalized_query_key("BERSERK"), "BERSERK") is True
    assert runner.submit(normalized_query_key("berserk"), "berserk") is False
    assert runner.wait_for(normalized_query_key("berserk"))
    assert scraper.calls == ["BERSERK"]  # one job under one key


# -- 6. scraper failure does not remove existing data ----------------------------------

def test_scraper_failure_keeps_existing_data(sessions, runner_factory):
    seed_catalog(
        sessions,
        make_result("bkm", "Berserk 1", "182", isbn="9786256335424"),
        make_result("bkm", "Berserk 2", "182"),
    )
    listings_before = None
    session = sessions()
    try:
        listings_before = session.scalar(select(func.count(StoreListing.id)))
    finally:
        session.close()
    assert listings_before == 2

    runner = runner_factory(
        [
            RecordingScraper(store_id="bkm", fail="boom"),
            RecordingScraper(store_id="amazon", fail="robot-checked (HTTP 503)"),
            RecordingScraper(store_id="dr", fail="blocked (HTTP 403)"),
        ]
    )

    session = sessions()
    try:
        outcome = search_service.search_with_auto_import(session, "berserk", runner)
    finally:
        session.close()
    assert outcome.import_status.state == "refreshing"  # data served, job started
    assert runner.wait_for("berserk")

    session = sessions()
    try:
        assert session.scalar(select(func.count(StoreListing.id))) == listings_before
        assert session.scalar(select(func.count(Series.id))) == 1
        outcome = search_service.search_with_auto_import(session, "berserk", runner)
    finally:
        session.close()
    record = runner.get_record("berserk")
    assert record.status == "failed"
    assert "boom" in record.error
    assert record.last_success_at is None
    assert len(outcome.matches) == 1  # data still served
    # Inside the failure retry window: no second attempt is scheduled.
    assert outcome.import_status.state == "stale"
    assert not runner.is_running("berserk")


# -- 7. partial scraper success is retained ---------------------------------------------

def test_partial_scraper_success_retained(sessions, runner_factory):
    seed_catalog(sessions, make_result("bkm", "Frieren 1", "200"))
    from app.models import Volume
    with sessions() as session:
        series = session.scalar(select(Series))
        session.add(Volume(series_id=series.id, volume_number=2))
        session.commit()
    set_fresh(sessions, normalized_query_key("frieren"), minutes_ago=120)

    runner = runner_factory(
        [
            RecordingScraper(
                store_id="bkm",
                results=[
                    make_result("bkm", "Frieren 1", "200"),
                    make_result("bkm", "Frieren 2", "200"),
                ],
            ),
            RecordingScraper(store_id="amazon", fail="robot-checked (HTTP 503)"),
        ]
    )

    session = sessions()
    try:
        outcome = search_service.search_with_auto_import(session, "frieren", runner)
    finally:
        session.close()
    assert outcome.import_status.state == "refreshing"  # catalog hit, job started
    assert runner.wait_for("frieren")

    record = runner.get_record("frieren")
    assert record.status == "partial"
    assert record.stores_ok == 1
    assert record.stores_failed == 1
    assert record.last_success_at is not None  # partial counts as a successful refresh
    assert record.created == 1  # the new Frieren 2 listing
    assert record.updated == 1  # the existing Frieren 1 listing

    session = sessions()
    try:
        outcome = search_service.search_with_auto_import(session, "frieren", runner)
        # BKM data is retained in the DB despite Amazon failing.
        assert session.scalar(select(func.count(StoreListing.id))) == 2
    finally:
        session.close()
    assert len(outcome.matches) == 1
    assert outcome.import_status.state == "fresh"


# -- 8. fresh results returned without waiting for the scraper ---------------------------

def test_fresh_results_return_without_waiting(sessions, runner_factory):
    import time

    seed_catalog(
        sessions,
        make_result("bkm", "Berserk 1", "182", isbn="9786256335424"),
        make_result("bkm", "Berserk 2", "182"),
        make_result("bkm", "Berserk 3", "182"),
    )
    set_fresh(sessions, normalized_query_key("berserk"), minutes_ago=120)

    slow_scraper = RecordingScraper(
        delay=0.8, results=[make_result("bkm", "Berserk 4", "182")]
    )
    runner = runner_factory([slow_scraper])

    session = sessions()
    started = time.monotonic()
    try:
        outcome = search_service.search_with_auto_import(session, "berserk", runner)
    finally:
        session.close()
    elapsed = time.monotonic() - started

    assert elapsed < 0.5  # did NOT wait for the 0.8s scraper
    assert outcome.import_status.state == "refreshing"
    assert outcome.matches[0].volume_count == 3  # old data served immediately

    assert runner.wait_for("berserk")
    session = sessions()
    try:
        outcome = search_service.search_with_auto_import(session, "berserk", runner)
    finally:
        session.close()
    assert outcome.matches[0].volume_count == 3  # store refresh cannot extend the catalog


# -- 9. import status represented correctly ----------------------------------------------

def test_import_status_represented_correctly(sessions, runner_factory):
    seed_catalog(sessions, make_result("bkm", "Chainsaw Man 1", "160"))
    set_fresh(sessions, normalized_query_key("chainsaw man"), minutes_ago=120)

    runner = runner_factory(
        [RecordingScraper(results=[make_result("bkm", "Chainsaw Man 1", "160")])]
    )

    session = sessions()
    try:
        search_service.search_with_auto_import(session, "chainsaw man", runner)
    finally:
        session.close()
    assert runner.wait_for("chainsaw man")

    record = runner.get_record("chainsaw man")
    assert record.status == "success"
    assert record.stores_ok == 1
    assert record.stores_failed == 0
    assert record.results_found == 1
    assert record.created == 0  # already imported by the seed
    assert record.updated == 1
    assert record.last_attempt_at is not None
    assert record.last_success_at is not None
    assert record.error is None

    session = sessions()
    try:
        outcome = search_service.search_with_auto_import(session, "Chainsaw Man", runner)
    finally:
        session.close()
    # The import is recorded and fresh: the catalog hit serves "fresh" and
    # the record summary is exposed in the detail.
    assert len(outcome.matches) == 1
    assert outcome.import_status.state == "fresh"
    assert outcome.import_status.last_success_at is not None
    assert "1 güncellendi" in outcome.import_status.detail


# -- 10. a job that dies BEFORE it starts must leave a visible failed record ----

class _FailFirstScalarSession:
    """Session wrapper whose FIRST scalar() raises — simulates a job whose
    first database operation fails (e.g. a pool checkout timeout). Every
    later call works, so the failure bookkeeping itself can succeed."""

    def __new__(cls, session_factory, **kwargs):  # noqa: N805
        session = session_factory(**kwargs)
        state = {"first": True}
        original_scalar = session.scalar

        def scalar(*args, **kw):
            if state["first"]:
                state["first"] = False
                raise RuntimeError("simulated pool checkout timeout")
            return original_scalar(*args, **kw)

        session.scalar = scalar  # type: ignore[method-assign]
        return session


def test_startup_db_failure_leaves_visible_failed_record(sessions, engine):
    session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    runner = BackgroundImportRunner(
        lambda: _FailFirstScalarSession(
            session_factory,
            autoflush=False,
            expire_on_commit=False,
        ),
        scraper_factory=lambda store_ids=None: [],
    )

    assert runner.submit("broken query", "Broken Query") is True
    assert runner.wait_for("broken query", timeout=10)

    session = sessions()
    try:
        record = session.scalar(
            select(ImportRecord).where(
                ImportRecord.normalized_query == "broken query"
            )
        )
    finally:
        session.close()
    assert record is not None, "job died pre-startup but left no trace"
    assert record.status == "failed"
    assert "içe aktarma başlatılamadı" in record.error


# -- 11. a subtitled catalog title that matched nothing retries shorter ---------

class _HeadOnlyScraper(RecordingScraper):
    """Store search that finds nothing for the full subtitled title."""

    def search(self, query: str) -> list:
        self.calls.append(query)
        return list(self.results) if query == "Kamisama Kiss" else []


def test_fallback_queries_head_and_original(db_session):
    from app.services.background_import import fallback_queries
    from tests.test_import_service import seed_catalog_series

    seed_catalog_series(db_session, "Tokyo Gül - Yeniden", "P", original="tokyo ghoul re")
    db_session.commit()
    assert fallback_queries(db_session, "Kamisama Kiss -Tanrılık Görevine Başladım") == [
        "Kamisama Kiss"
    ]
    assert fallback_queries(db_session, "Tokyo Gül - Yeniden") == ["Tokyo Gül", "tokyo ghoul re"]
    assert fallback_queries(db_session, "Berserk") == []
    assert fallback_queries(db_session, "Zom 100: Ölülerin Yapılacaklar Listesi") == ["Zom 100"]
    assert fallback_queries(db_session, "Avatar: The Last Airbender - Uçurum") == [
        "Avatar: The Last Airbender", "Avatar",
    ]


def test_zero_match_import_retries_main_title(sessions, runner_factory):
    from tests.test_import_service import seed_catalog_series

    session = sessions()
    try:
        seed_catalog_series(session, "Kamisama Kiss -Tanrılık Görevine Başladım",
                            "Komik Şeyler", volumes=range(1, 10))
        session.commit()
    finally:
        session.close()

    scraper = _HeadOnlyScraper(results=[
        make_result("bkm", "Kamisama Kiss Cilt 07", "100", publisher="Komikşeyler Yayıncılık"),
    ])
    runner = runner_factory([scraper])
    title = "Kamisama Kiss -Tanrılık Görevine Başladım"
    key = normalized_query_key(title)
    assert runner.submit(key, title)
    assert runner.wait_for(key)

    assert scraper.calls == [title, "Kamisama Kiss"]
    record = runner.get_record(key)
    assert record.status == "success"
    assert record.stores_ok == 1  # one store, counted once across both queries
    assert record.results_found == 1
    assert record.created == 1
    session = sessions()
    try:
        assert session.scalar(select(func.count(StoreListing.id))) == 1
    finally:
        session.close()


class _QueryScraper(RecordingScraper):
    """Store search whose results depend on the query."""

    def __init__(self, by_query, store_id="bkm", store_name="BKM Kitap"):
        super().__init__(store_id=store_id, store_name=store_name, results=[])
        self.by_query = by_query

    def search(self, query: str) -> list:
        self.calls.append(query)
        return list(self.by_query.get(query, []))


def test_fallback_runs_when_query_only_priced_another_series(sessions, runner_factory):
    """"Oşi No Ko: Seçtiğim Yıldız" matched products of ANOTHER catalog
    series, so the old "nothing matched" condition never retried the head
    query and the series stayed unpriced ("başka seriyle eşleşti")."""
    from tests.test_import_service import seed_catalog_series

    session = sessions()
    try:
        seed_catalog_series(session, "Oşi No Ko: Seçtiğim Yıldız", "Gerekli Şeyler",
                            volumes=range(1, 13))
        seed_catalog_series(session, "Berserk", "Gerekli Şeyler", volumes=(1,))
        session.commit()
    finally:
        session.close()

    title = "Oşi No Ko: Seçtiğim Yıldız"
    pub = "Gerekli Şeyler Yayıncılık"
    scraper = _QueryScraper({
        title: [make_result("bkm", "Berserk 1", "100", publisher=pub)],
        "Oşi No Ko": [make_result("bkm", "Oşi No Ko 4. Cilt", "100", publisher=pub)],
    })
    runner = runner_factory([scraper])
    key = normalized_query_key(title)
    assert runner.submit(key, title)
    assert runner.wait_for(key)

    assert scraper.calls == [title, "Oşi No Ko"]
    session = sessions()
    try:
        from app.services.background_import import catalog_series_unpriced

        assert not catalog_series_unpriced(session, title)
    finally:
        session.close()


def test_fallback_is_per_store_once_another_store_priced_the_series(sessions, runner_factory):
    """Zom 100: BKM's fuzzy search finds "Zom 100 Cilt 10" for the full
    subtitled title; a strict all-words store returns nothing for it. The
    series is priced (by BKM), yet the strict store must still be asked for
    "Zom 100" — and BKM must not be searched twice."""
    from tests.test_import_service import seed_catalog_series

    session = sessions()
    try:
        seed_catalog_series(session, "Zom 100: Ölülerin Yapılacaklar Listesi",
                            "Marmara Çizgi", volumes=range(1, 11))
        session.commit()
    finally:
        session.close()

    title = "Zom 100: Ölülerin Yapılacaklar Listesi"
    fuzzy = _QueryScraper({
        title: [make_result("bkm", "Zom 100 Cilt 10", "100", publisher="Marmara Çizgi")],
    })
    strict = _QueryScraper({
        "Zom 100": [make_result("dr", "Zom 100 Cilt 10", "95", publisher="Marmara Çizgi")],
    }, store_id="dr", store_name="D&R")
    runner = runner_factory([fuzzy, strict])
    key = normalized_query_key(title)
    assert runner.submit(key, title)
    assert runner.wait_for(key)

    assert fuzzy.calls == [title]
    assert strict.calls == [title, "Zom 100"]
    session = sessions()
    try:
        stores = {
            listing.store.code
            for listing in session.scalars(select(StoreListing))
        }
    finally:
        session.close()
    assert stores == {"bkm", "dr"}


def test_store_with_unrelated_results_is_not_retried_when_series_priced(sessions, runner_factory):
    """Bounded cost: a store that answered the full title with other
    products (and the series is priced elsewhere) gets no extra query."""
    from tests.test_import_service import seed_catalog_series

    session = sessions()
    try:
        seed_catalog_series(session, "Zom 100: Ölülerin Yapılacaklar Listesi",
                            "Marmara Çizgi", volumes=range(1, 11))
        session.commit()
    finally:
        session.close()

    title = "Zom 100: Ölülerin Yapılacaklar Listesi"
    fuzzy = _QueryScraper({
        title: [make_result("bkm", "Zom 100 Cilt 10", "100", publisher="Marmara Çizgi")],
    })
    other = _QueryScraper({
        title: [make_result("dr", "Başka Bir Kitap", "50", publisher="X Yayınları")],
    }, store_id="dr", store_name="D&R")
    runner = runner_factory([fuzzy, other])
    key = normalized_query_key(title)
    assert runner.submit(key, title)
    assert runner.wait_for(key)

    assert other.calls == [title]


class _HidingStore(RecordingScraper):
    """Kitapseç-like store: the sold-out product is gone from search, but
    its product page still answers."""

    verifies_unseen_listings = True

    def __init__(self, pages):
        super().__init__(store_id="kitapsec", store_name="Kitapsec", results=[])
        self.pages = pages
        self.checked: list[str] = []

    def check_listing(self, url):
        self.checked.append(url)
        return self.pages.get(url)


def test_background_job_rechecks_listing_missing_from_search(sessions, runner_factory):
    from app.models import Store, Volume
    from app.scrapers.base import ListingCheck
    from tests.test_import_service import seed_catalog_series

    url = "https://www.kitapsec.com/Products/Tokyo-Gul-Yeniden-8.html"
    session = sessions()
    try:
        series = seed_catalog_series(session, "Tokyo Gül - Yeniden", "Gerekli Şeyler", volumes=(8,))
        store = Store(code="kitapsec", name="Kitapsec")
        session.add(store)
        session.flush()
        vol = session.scalar(select(Volume).where(Volume.series_id == series.id))
        session.add(StoreListing(volume_id=vol.id, store_id=store.id, product_url=url, price=20000,
                                 in_stock=True, last_checked=utcnow() - timedelta(hours=20)))
        session.commit()
    finally:
        session.close()

    scraper = _HidingStore({url: ListingCheck(in_stock=False)})
    runner = runner_factory([scraper])
    title = "Tokyo Gül - Yeniden"
    key = normalized_query_key(title)
    assert runner.submit(key, title)
    assert runner.wait_for(key)

    assert scraper.checked == [url]
    session = sessions()
    try:
        listing = session.scalar(select(StoreListing))
        assert listing.in_stock is False
        assert listing.price == 20000  # page gave no price: keep the last one
    finally:
        session.close()
