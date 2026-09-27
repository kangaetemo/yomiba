"""Regression tests for the 2026-09-26 QA audit fixes (H1, M2, M3, M4, M6, M7, M8, M9, lows)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.models import PriceHistory, Store, StoreListing, Volume
from app.services.import_service import ImportAction, ImportService
from app.utils import utcnow
from tests.helpers import RecordingScraper
from tests.test_import_service import make_result, seed_catalog_series


def _phantom(db_session, series, *, isbn="9786258237559", with_listing=True):
    phantom = Volume(series_id=series.id, volume_number=-1, isbn=isbn)
    db_session.add(phantom)
    db_session.flush()
    if with_listing:
        store = db_session.scalar(select(Store).where(Store.code == "kitapsec"))
        if store is None:
            store = Store(code="kitapsec", name="Kitapsec")
            db_session.add(store)
            db_session.flush()
        listing = StoreListing(volume_id=phantom.id, store_id=store.id,
                               product_url="https://kitapsec.example/old", price=14880)
        db_session.add(listing)
        db_session.flush()
        db_session.add(PriceHistory(listing_id=listing.id, price=15990, checked_at=utcnow() - timedelta(hours=3)))
        db_session.add(PriceHistory(listing_id=listing.id, price=14880, checked_at=utcnow() - timedelta(hours=1)))
    db_session.commit()
    return phantom


# ---------------------------------------------------------------- H1 -------
def test_h1_legacy_phantom_hidden_from_public_reads(client, db_session):
    series = seed_catalog_series(db_session, "Elveda Eri", "Gerekli Şeyler")
    real = series.volumes[0]
    phantom = _phantom(db_session, series)

    detail = client.get(f"/series/{series.id}").json()
    assert [v["id"] for v in detail["volumes"]] == [real.id]
    search = client.get("/search", params={"q": "Elveda"}).json()["results"]
    assert search[0]["volume_count"] == 1

    vol = client.get(f"/volume/{phantom.id}")
    assert vol.status_code == 200  # user rows may still point at it
    assert vol.json()["unverified"] is True
    assert vol.json()["stores"] == []
    assert client.get(f"/volume/{phantom.id}/price-history").json()["listings"] == []
    assert client.get("/price-drops", params={"hours": 24}).json()["drops"] == []
    assert client.get(f"/volume/{real.id}").json()["unverified"] is False
    # Data is untouched: no cleanup without an approved merge.
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == 1


def test_h1_catalog_owned_unnumbered_volume_stays_visible(client, db_session):
    """A -1 row WITHOUT ISBN/listings is a catalog (Mangakol) unnumbered item."""
    series = seed_catalog_series(db_session, "Kutu Manga", "Yayinci", volumes=(1, 2))
    _phantom(db_session, series, isbn=None, with_listing=False)
    numbers = [v["number"] for v in client.get(f"/series/{series.id}").json()["volumes"]]
    assert numbers == [1, 2, None]


def test_h1_phantom_isbn_multi_volume_uses_parsed_number(db_session, import_service):
    series = seed_catalog_series(db_session, "Gantz", "Kurukafa", volumes=range(1, 6))
    phantom = _phantom(db_session, series, isbn="9786050000033", with_listing=False)
    result = make_result("bkm", "Gantz 3", "120", isbn="9786050000033", publisher="Kurukafa")
    assert import_service.import_result(result) == ImportAction.CREATED
    db_session.commit()
    listing = db_session.scalar(select(StoreListing))
    assert listing.volume.volume_number == 3
    assert listing.volume.isbn is None  # the ISBN is not moved off the phantom
    assert db_session.get(Volume, phantom.id).isbn == "9786050000033"
    # Numberless product in a multi-volume series is still rejected.
    assert import_service.import_result(make_result("dr", "Gantz", "120", isbn="9786050000033")) == ImportAction.SKIPPED


# ---------------------------------------------------------------- M2 -------
def _run(db_session, *results):
    return ImportService(db_session, scrapers=[RecordingScraper("bkm", "BKM Kitap", list(results))]).run_import("q")


def _history(db_session):
    return [p for (p,) in db_session.execute(select(PriceHistory.price).order_by(PriceHistory.id))]


def test_m2_other_product_cannot_flip_listing_between_runs(db_session):
    seed_catalog_series(db_session, "Jujutsu Kaisen", "Gerekli Şeyler", volumes=(0, 1, 2))
    a = make_result("bkm", "Jujutsu Kaisen 0", "196.80", publisher="Gerekli Şeyler")
    b = make_result("bkm", "Jujutsu Kaisen Cilt 0", "472.24", publisher="Gerekli Şeyler")
    for results in ([a], [b], [a], [b], [a]):
        _run(db_session, *results)
    assert _history(db_session) == [19680]
    listing = db_session.scalar(select(StoreListing))
    assert listing.product_url == a.product_url and listing.price == 19680
    report = _run(db_session, b)
    assert report.stores[0].reasons.get("other_product") == 1


def test_m2_cheaper_or_stale_or_restocked_product_may_replace(db_session):
    seed_catalog_series(db_session, "Jujutsu Kaisen", "Gerekli Şeyler", volumes=(0,))
    expensive = make_result("bkm", "Jujutsu Kaisen Cilt 0", "472.24", publisher="Gerekli Şeyler")
    cheap = make_result("bkm", "Jujutsu Kaisen 0", "196.80", publisher="Gerekli Şeyler")
    _run(db_session, expensive)
    _run(db_session, cheap)  # cheaper printing wins
    listing = db_session.scalar(select(StoreListing))
    assert listing.product_url == cheap.product_url

    # Current product not seen for longer than the switch window -> replaceable.
    listing.last_checked = utcnow() - timedelta(hours=49)
    db_session.commit()
    _run(db_session, expensive)
    assert db_session.scalar(select(StoreListing)).product_url == expensive.product_url

    # Out-of-stock current product -> an in-stock alternative may replace it.
    listing = db_session.scalar(select(StoreListing))
    listing.in_stock = False
    listing.product_url = "https://example.com/bkm/sold-out"
    db_session.commit()
    _run(db_session, expensive)
    assert db_session.scalar(select(StoreListing)).product_url == expensive.product_url


def test_m2_same_product_price_changes_still_recorded(db_session):
    seed_catalog_series(db_session, "Gantz", "Kurukafa", volumes=(1,))
    _run(db_session, make_result("bkm", "Gantz 1", "100", publisher="Kurukafa"))
    _run(db_session, make_result("bkm", "Gantz 1", "100", publisher="Kurukafa"))
    _run(db_session, make_result("bkm", "Gantz 1", "90", publisher="Kurukafa"))
    assert _history(db_session) == [10000, 9000]


# ---------------------------------------------------------------- M3 -------
import pytest  # noqa: E402


@pytest.mark.parametrize("catalog_title,publisher,volumes,product,expected", [
    ("Kaiju No: 8 - 8 No'lu Canavar", "Kurukafa", range(1, 9), "Kaiju No: 8 - 8 No'lu Canavar 3", 3),
    ("Kaiju No: 8 - 8 No'lu Canavar", "Kurukafa", range(1, 9), "Kaiju No: 8 - 8 No'lu Canavar Cilt 3", 3),
    ("Mob Psycho 100", "İthaki Çocuk Yayınları", (1, 2, 3), "Mob Psycho 100 Cilt 2", 2),
    ("Mob Psycho 100", "İthaki Çocuk Yayınları", (1, 2, 3), "Mob Psycho 100 2", 2),
    ("Dövüş Sınıfı 3", "Yayinci", (1, 2), "Dövüş Sınıfı 3 Cilt 2", 2),
    ("Disney Manga - 6 Süper Kahraman", "Yayinci", (1,), "Disney Manga - 6 Süper Kahraman", 1),
])
def test_m3_catalog_titles_with_numbers_match(db_session, import_service, catalog_title, publisher, volumes, product, expected):
    seed_catalog_series(db_session, catalog_title, publisher, volumes=volumes)
    before = db_session.scalar(select(func.count()).select_from(Volume))
    action = import_service.import_result(make_result("bkm", product, "100", publisher=publisher))
    assert action == ImportAction.CREATED, import_service.last_reason
    db_session.commit()
    assert db_session.scalar(select(StoreListing)).volume.volume_number == expected
    assert db_session.scalar(select(func.count()).select_from(Volume)) == before


@pytest.mark.parametrize("product,reason", [
    ("Kaiju No: 8 - 8 No'lu Canavar 1-3 Kutu Set", "box_set"),
    ("Kaiju No: 8 - 8 No'lu Canavar 9", "volume_not_found"),
    ("Kaiju No: 8 - 8 No'lu Canavar Artbook", "publisher_conflict"),
    ("Kaiju No: 8 - 8 No'lu Canavar", "no_volume_number"),
])
def test_m3_prefix_fallback_stays_strict(db_session, import_service, product, reason):
    seed_catalog_series(db_session, "Kaiju No: 8 - 8 No'lu Canavar", "Kurukafa", volumes=range(1, 9))
    assert import_service.import_result(make_result("bkm", product, "100", publisher="Kurukafa")) == ImportAction.SKIPPED
    assert import_service.last_reason == reason


def test_m3_fallback_respects_publisher_and_edition(db_session, import_service):
    seed_catalog_series(db_session, "Mob Psycho 100", "Publisher A", volumes=(1, 2))
    seed_catalog_series(db_session, "Mob Psycho 100", "Publisher B", volumes=(1, 2))
    # unknown publisher -> no guess
    assert import_service.import_result(make_result("bkm", "Mob Psycho 100 Cilt 2", "100", publisher="Başka")) == ImportAction.SKIPPED
    # no publisher + two editions -> no guess
    assert import_service.import_result(make_result("bkm", "Mob Psycho 100 Cilt 2", "100")) == ImportAction.SKIPPED
    assert import_service.import_result(make_result("bkm", "Mob Psycho 100 Cilt 2", "100", publisher="Publisher B")) == ImportAction.CREATED


def test_l8_ambiguous_title_reports_ambiguous_reason(db_session, import_service):
    seed_catalog_series(db_session, "Gantz", "Kurukafa", volumes=(1, 2))
    assert import_service.import_result(make_result("bkm", "Bilinmeyen 100 Cilt 2", "100", publisher="Kurukafa")) == ImportAction.SKIPPED
    assert import_service.last_reason == "ambiguous_volume"


# ---------------------------------------------------------------- M4 -------
def test_m4_announced_sync_intent_prevents_gate_starvation(engine, monkeypatch):
    import threading
    import time
    from sqlalchemy.orm import sessionmaker
    from app.services.background_import import BackgroundImportRunner, SYNC_GATE_KEY

    runner = BackgroundImportRunner(sessionmaker(bind=engine), max_concurrent=2, queue_capacity=16)
    monkeypatch.setattr(runner, "_execute", lambda key, query: time.sleep(0.1))
    stop = threading.Event()
    counter = [0]

    def feeder():  # a price-refresh cycle that keeps the queue full
        while not stop.is_set():
            if runner.available_slots() > 0:
                runner.submit(f"q{counter[0]}", f"q{counter[0]}")
                counter[0] += 1
            time.sleep(0.005)

    threading.Thread(target=feeder, daemon=True).start()
    try:
        time.sleep(0.3)
        assert not runner.acquire_import_lock(SYNC_GATE_KEY, "catalog", timeout=0)
        runner.lock.set_exclusive_intent(SYNC_GATE_KEY, True)
        acquired = False
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not acquired:
            acquired = runner.acquire_import_lock(SYNC_GATE_KEY, "catalog", timeout=0)
            time.sleep(0.02)
        runner.lock.set_exclusive_intent(SYNC_GATE_KEY, False)
        assert acquired, "catalog sync must get the gate once intent is announced"
        runner.release_import_lock(SYNC_GATE_KEY, "catalog")
        # store imports resume afterwards
        started = counter[0]
        time.sleep(0.5)
        assert counter[0] > started
    finally:
        stop.set()
        runner.shutdown(timeout=2)


def test_m4_scheduler_announces_and_withdraws_intent():
    from app.services.catalog_scheduler import CatalogSyncScheduler

    results = iter(["gate_held", "gate_held", "started"])
    events: list[bool] = []
    sched = CatalogSyncScheduler(lambda: next(results), interval_seconds=60,
                                 gate_wait_seconds=5, poll_seconds=0.01,
                                 announce_intent=events.append)
    assert sched._try_start_with_gate_wait() == "started"
    assert events == [True, False]


# ---------------------------------------------------------------- M6 / L2 / L7 -
PW = "correct horse battery staple"


def test_m6_trusted_device_can_log_in_while_account_is_locked(client, db_session):
    from app.login_rate_limit import DEVICE_COOKIE_NAME
    from app.auth import COOKIE_NAME

    client.cookies.clear()
    assert client.post("/auth/register", json={"email": "victim@example.com", "password": PW, "display_name": "V"}).status_code == 201
    owner_device = client.cookies.get(DEVICE_COOKIE_NAME)
    assert owner_device
    client.cookies.clear()
    assert client.post("/auth/register", json={"email": "other@example.com", "password": PW, "display_name": "O"}).status_code == 201
    other_device = client.cookies.get(DEVICE_COOKIE_NAME)

    client.cookies.clear()
    for _ in range(10):  # attacker locks the account
        assert client.post("/auth/login", json={"email": "victim@example.com", "password": "nope"}).status_code == 401
    ok = {"email": "victim@example.com", "password": PW}
    assert client.post("/auth/login", json=ok).status_code == 429  # no device
    client.cookies.set(DEVICE_COOKIE_NAME, owner_device[:-4] + "0000")
    assert client.post("/auth/login", json=ok).status_code == 429  # forged
    client.cookies.clear(); client.cookies.set(DEVICE_COOKIE_NAME, other_device)
    assert client.post("/auth/login", json=ok).status_code == 429  # other account's device
    client.cookies.clear(); client.cookies.set(DEVICE_COOKIE_NAME, owner_device)
    assert client.post("/auth/login", json=ok).status_code == 200  # the real owner
    assert client.cookies.get(COOKIE_NAME)


def test_m6_trusted_device_is_itself_rate_limited(client, db_session):
    from app.login_rate_limit import DEVICE_COOKIE_NAME

    client.cookies.clear()
    client.post("/auth/register", json={"email": "d@example.com", "password": PW, "display_name": "D"})
    device = client.cookies.get(DEVICE_COOKIE_NAME)
    client.cookies.clear()
    for _ in range(10):
        client.post("/auth/login", json={"email": "d@example.com", "password": "nope"})
    client.cookies.set(DEVICE_COOKIE_NAME, device)
    codes = [client.post("/auth/login", json={"email": "d@example.com", "password": "nope"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_m6_successful_logins_do_not_consume_attempts(client, db_session):
    client.cookies.clear()
    client.post("/auth/register", json={"email": "s@example.com", "password": PW, "display_name": "S"})
    for _ in range(12):
        client.cookies.clear()
        assert client.post("/auth/login", json={"email": "s@example.com", "password": PW}).status_code == 200


def test_l2_logout_cookie_deletion_keeps_security_attributes(client, db_session):
    client.cookies.clear()
    client.post("/auth/register", json={"email": "lo@example.com", "password": PW, "display_name": "L"})
    header = client.post("/auth/logout").headers["set-cookie"].lower()
    assert "max-age=0" in header and "httponly" in header and "secure" in header and "samesite=lax" in header


def test_l7_login_purges_expired_and_revoked_sessions(client, db_session):
    from app.models import User, UserSession

    client.cookies.clear()
    client.post("/auth/register", json={"email": "p@example.com", "password": PW, "display_name": "P"})
    client.post("/auth/logout")  # revoked row
    user = db_session.scalar(select(User).where(User.email == "p@example.com"))
    db_session.add(UserSession(user_id=user.id, token_hash="x" * 64, expires_at=utcnow() - timedelta(days=1)))
    db_session.commit()
    assert client.post("/auth/login", json={"email": "p@example.com", "password": PW}).status_code == 200
    db_session.expire_all()
    rows = db_session.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()
    assert len(rows) == 1 and rows[0].revoked_at is None


# ---------------------------------------------------------------- M7 -------
def test_m7_backup_written_only_when_schema_is_behind(tmp_path):
    import sqlite3

    from app.database import backup_before_migration

    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE alembic_version(version_num TEXT)")
        c.execute("INSERT INTO alembic_version VALUES ('0004_catalog_exclusion')")
        c.execute("CREATE TABLE series(id INTEGER PRIMARY KEY, title TEXT)")
        c.execute("INSERT INTO series VALUES (1, 'Kept')")
    before = db.read_bytes()
    backup = backup_before_migration(f"sqlite:///{db}", "0006_publisher_alias_by_name")
    assert backup is not None and backup.name.startswith("old.db.pre-migration-0004_catalog_exclusion-")
    with sqlite3.connect(backup) as c:
        assert c.execute("SELECT title FROM series").fetchone() == ("Kept",)
    assert db.read_bytes() == before  # source untouched
    # at head / empty file / missing file -> nothing to do
    assert backup_before_migration(f"sqlite:///{db}", "0004_catalog_exclusion") is None
    empty = tmp_path / "empty.db"; empty.touch()
    assert backup_before_migration(f"sqlite:///{empty}", "0006_publisher_alias_by_name") is None
    assert backup_before_migration(f"sqlite:///{tmp_path / 'missing.db'}", "0006_publisher_alias_by_name") is None


def test_m7_real_startup_backs_up_before_migrating(monkeypatch, tmp_path):
    from dataclasses import replace

    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app import config as config_mod, database
    import app.main as main_mod

    db = tmp_path / "startup.db"
    url = f"sqlite:///{db}"
    settings = replace(config_mod.get_settings(), database_url=url, app_env="production",
                       price_refresh_enabled=False, catalog_sync_enabled=False)
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(database, "get_settings", lambda: settings)
    monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
    backend = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    db.touch()
    command.upgrade(cfg, "0004_catalog_exclusion")  # an older real schema
    engine = database.build_engine(url)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    try:
        with TestClient(main_mod.create_app(auto_init=True)) as c:
            assert c.get("/ready").status_code == 200
        backups = list(tmp_path.glob("startup.db.pre-migration-0004_catalog_exclusion-*.bak"))
        assert len(backups) == 1
        with TestClient(main_mod.create_app(auto_init=True)) as c:  # already at head
            assert c.get("/ready").status_code == 200
        assert len(list(tmp_path.glob("startup.db.pre-migration-*.bak"))) == 1
    finally:
        engine.dispose()


# ---------------------------------------------------------------- M9 / L1 --
def test_m9_me_lists_are_per_user_and_ordered(client, db_session):
    from app.auth import COOKIE_NAME

    series = seed_catalog_series(db_session, "Liste Manga", "Liste Yayin", volumes=(0, 1, 2))
    v0, v1, v2 = sorted(series.volumes, key=lambda v: v.volume_number)
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store); db_session.flush()
    db_session.add(StoreListing(volume_id=v1.id, store_id=store.id, product_url="https://x/1", price=12345))
    db_session.commit()

    def register(email):
        client.cookies.clear()
        client.post("/auth/register", json={"email": email, "password": PW, "display_name": "x"})
        return client.cookies.get(COOKIE_NAME)

    a, b = register("la@example.com"), register("lb@example.com")
    client.cookies.clear(); client.cookies.set(COOKIE_NAME, a)
    client.patch(f"/volume/{v2.id}/collection-status", json={"status": "wanted"})
    client.patch(f"/volume/{v0.id}/collection-status", json={"status": "owned"})
    client.post(f"/volume/{v1.id}/wishlist")
    client.put(f"/volume/{v1.id}/price-alert", json={"threshold_price": 10000})

    col = client.get("/me/collection")
    assert "no-store" in col.headers["cache-control"]
    assert [(i["volume_number"], i["status"]) for i in col.json()] == [(0, "owned"), (2, "wanted")]
    wl = client.get("/me/wishlist").json()
    assert [(i["volume_id"], i["best_price"]) for i in wl] == [(v1.id, 123.45)]
    assert client.get("/me/price-alerts").json()[0]["threshold_price"] == 10000

    client.cookies.clear(); client.cookies.set(COOKIE_NAME, b)
    assert client.get("/me/collection").json() == []
    assert client.get("/me/wishlist").json() == []
    assert client.get("/me/price-alerts").json() == []
    client.cookies.clear()
    assert client.get("/me/collection").status_code == 401


def test_l1_huge_threshold_is_422_not_500(client, db_session):
    series = seed_catalog_series(db_session, "Big Manga", "Big Pub", volumes=(1,))
    r = client.put(f"/volume/{series.volumes[0].id}/price-alert", json={"threshold_price": 2 ** 70})
    assert r.status_code == 422


# ------------------------------------------ NEW-1: titles ending in s/c/no ---
@pytest.mark.parametrize("title,base,number", [
    ("Happiness 8", "Happiness", 8),
    ("Made in Abyss 11", "Made in Abyss", 11),
    ("Beastars 20. Cilt", "Beastars", 20),
    ("Tokyo Revengers 12", "Tokyo Revengers", 12),
    ("One Piece S. 3", "One Piece", 3),
    ("One Piece No: 5", "One Piece", 5),
    ("Berserk C. 4", "Berserk", 4),
])
def test_new1_marker_words_must_be_whole_words(title, base, number):
    from app.normalization import parse_volume_title

    parsed = parse_volume_title(title)
    assert (parsed.base_title, parsed.volume_number) == (base, number)


def test_new1_title_ending_in_s_matches_catalog(db_session, import_service):
    seed_catalog_series(db_session, "Made in Abyss", "Yayinci", volumes=range(1, 12))
    assert import_service.import_result(make_result("bkm", "Made in Abyss 11", "100", publisher="Yayinci")) == ImportAction.CREATED


def test_m3_collection_word_inside_catalog_title(db_session, import_service):
    seed_catalog_series(db_session, "Mavi Kutu", "Yayinci", volumes=range(1, 6))
    assert import_service.import_result(make_result("bkm", "Mavi Kutu 4", "100", publisher="Yayinci")) == ImportAction.CREATED
    assert import_service.import_result(make_result("bkm", "Mavi Kutu 1-3 Set", "100", publisher="Yayinci")) == ImportAction.SKIPPED
    assert import_service.last_reason == "box_set"


def test_m7_backup_targets_the_database_alembic_migrates(monkeypatch, tmp_path):
    """Regression: the backup must follow the URL Alembic uses (config
    module), never another default file such as backend/yomiba.db."""
    import sqlite3
    from dataclasses import replace

    from app import config as config_mod, database

    def old_db(path):
        with sqlite3.connect(path) as c:
            c.execute("CREATE TABLE alembic_version(version_num TEXT)")
            c.execute("INSERT INTO alembic_version VALUES ('0004_catalog_exclusion')")

    target, bystander = tmp_path / "target.db", tmp_path / "bystander.db"
    old_db(bystander)
    target.touch()  # empty: Alembic creates the schema, no backup needed
    migrate = replace(config_mod.get_settings(), database_url=f"sqlite:///{target}", app_env="development")
    other = replace(config_mod.get_settings(), database_url=f"sqlite:///{bystander}", app_env="development")
    monkeypatch.setattr(config_mod, "get_settings", lambda: migrate)
    monkeypatch.setattr(database, "get_settings", lambda: other)
    database.init_db()
    assert list(tmp_path.glob("*.bak")) == []


# ------------------------------------ BKM real titles (2026-09-27 staging) ---
def test_kaiju_real_bkm_titles_survive_scraper_and_match(db_session, import_service):
    """Real BKM titles use a curly apostrophe and "8 - 8" (not a range)."""
    from app.normalization import parse_volume_title

    seed_catalog_series(db_session, "Kaiju No: 8 - 8 No'lu Canavar", "Kurukafa", volumes=range(1, 9))
    for title, number in [("Kaiju No: 8 - 8 No\u2019lu Canavar 6", 6), ("Kaiju No: 8 - 8 No`lu Canavar 7", 7)]:
        assert not parse_volume_title(title).is_collection  # scrapers drop collections
        assert import_service.import_result(make_result("bkm", title, "160", publisher="Kurukafa")) == ImportAction.CREATED
        db_session.commit()
    nums = sorted(l.volume.volume_number for l in db_session.scalars(select(StoreListing)))
    assert nums == [6, 7]


@pytest.mark.parametrize("holder_title,holder_number,expected", [
    ("One Piece", 55, ImportAction.CREATED),   # legacy same-work duplicate
    ("One Piece", -1, ImportAction.CREATED),
    ("One Piece", 12, ImportAction.SKIPPED),   # ISBN says another volume
    ("Outside", 55, ImportAction.SKIPPED),     # ISBN belongs to another work
])
def test_isbn_on_legacy_non_catalog_duplicate(db_session, import_service, holder_title, holder_number, expected):
    from sqlalchemy import delete
    from app.models import CatalogSeries

    catalog = seed_catalog_series(db_session, "One Piece", "Gerekli Şeyler", volumes=range(1, 63))
    legacy = seed_catalog_series(db_session, holder_title, "Gerekli Şeyler Yayıncılık", volumes=(holder_number,))
    legacy.volumes[0].isbn = "9786256031791"
    db_session.execute(delete(CatalogSeries).where(CatalogSeries.series_id == legacy.id))
    db_session.commit()
    result = make_result("bkm", "One Piece 55. Cilt", "180", isbn="9786256031791", publisher="Gerekli Şeyler")
    assert import_service.import_result(result) == expected
    db_session.commit()
    listing = db_session.scalar(select(StoreListing))
    if expected is ImportAction.CREATED:
        assert listing.volume.series_id == catalog.id and listing.volume.volume_number == 55
        assert listing.volume.isbn is None  # ISBN stays on the legacy row
    else:
        assert listing is None and import_service.last_reason == "non_catalog_volume"
