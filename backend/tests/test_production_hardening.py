"""Production safety checks use only temporary files and databases."""

from dataclasses import replace
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import Settings, validate_database_settings, validate_runtime_settings
from app.database import build_engine, enable_sqlite_wal
from app.login_rate_limit import LoginRateLimiter
from tests.test_import_service import seed_catalog_series


def test_production_requires_absolute_sqlite_path(tmp_path):
    with pytest.raises(ValueError, match="absolute"):
        validate_database_settings(Settings(app_env="production", database_url="sqlite:///./yomiba.db"))
    with pytest.raises(ValueError, match="absolute"):
        validate_database_settings(Settings(app_env="production", database_url="sqlite:///:memory:"))
    validate_database_settings(Settings(app_env="development", database_url="sqlite:///./yomiba.db"))
    with pytest.raises(ValueError, match="already exist"):
        validate_database_settings(Settings(app_env="production", database_url=f"sqlite:///{tmp_path / 'data.db'}"))
    (tmp_path / "data.db").touch()
    validate_database_settings(Settings(app_env="production", database_url=f"sqlite:///{tmp_path / 'data.db'}"))
    with pytest.raises(ValueError, match="AUTH_COOKIE_SECURE"):
        validate_runtime_settings(Settings(app_env="production", database_url=f"sqlite:///{tmp_path / 'data.db'}", auth_cookie_secure=False))


def test_sqlite_connections_enforce_fk_timeout_and_wal(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'runtime.db'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"))
        enable_sqlite_wal(engine)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 2  # FULL
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO child (parent_id) VALUES (999)"))
        engine.dispose()
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
    finally:
        engine.dispose()


def test_registration_cannot_escalate_and_login_is_limited(client, db_session):
    client.cookies.clear()
    response = client.post("/auth/register", json={
        "email": "role@example.com", "password": "correct horse battery staple",
        "display_name": "Role", "role": "ADMIN", "ROLE": "ADMIN", "is_admin": True,
        "is_active": False, "id": 42,
    })
    assert response.status_code == 201
    assert response.json()["role"] == "USER"
    assert response.json()["id"] != 42
    assert client.get("/import/records").status_code == 403
    client.cookies.clear()
    client.app.state.login_limiter = LoginRateLimiter(limit=2, window_seconds=60)
    for index in range(2):
        assert client.post("/auth/login", headers={"X-Forwarded-For": f"1.2.3.{index}"}, json={
            "email": "role@example.com", "password": "wrong",
        }).status_code == 401
    limited = client.post("/auth/login", headers={"X-Forwarded-For": "9.9.9.9"}, json={
        "email": "role@example.com", "password": "wrong",
    })
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
    assert client.post("/auth/login", json={
        "email": "different@example.com", "password": "wrong",
    }).status_code == 401
    client.app.state.login_limiter = LoginRateLimiter(limit=2, window_seconds=60)
    assert client.post("/auth/login", json={
        "email": "role@example.com", "password": "correct horse battery staple",
    }).status_code == 200


def test_personal_responses_are_not_shared_cached(client, db_session):
    series = seed_catalog_series(db_session, "Cache Manga", "Cache Publisher", volumes=(1,))
    volume_id = series.volumes[0].id
    client.cookies.clear()
    anonymous = client.get(f"/volume/{volume_id}")
    assert anonymous.json()["collection_status"] is None
    assert "Cookie" in anonymous.headers["Vary"]
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503  # fixture skips production startup
    client.post("/auth/register", json={"email": "cache-a@example.com", "password": "correct horse battery staple", "display_name": "A"})
    client.patch(f"/volume/{volume_id}/collection-status", json={"status": "owned"})
    personal = client.get(f"/volume/{volume_id}")
    assert personal.json()["collection_status"] == "owned"
    assert personal.headers["Cache-Control"] == "private, no-store"
    assert "Cookie" in personal.headers["Vary"]
    client.cookies.clear()
    assert client.get(f"/volume/{volume_id}").json()["collection_status"] is None


def test_readiness_fails_when_database_check_fails(client, monkeypatch):
    import app.main as main_mod

    client.app.state.ready = True
    def unavailable(_engine):
        raise OSError("temporary test DB unavailable")
    monkeypatch.setattr(main_mod, "check_database_ready", unavailable)
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200


def _wired_startup(monkeypatch, engine, events, *, fail_at=None):
    from app import database, seed as seed_mod
    import app.main as main_mod
    import app.routes.catalog as catalog_route
    import app.services.background_import as background_mod
    import app.services.catalog_scheduler as catalog_mod
    import app.services.price_refresh_scheduler as price_mod

    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)

    def step(name):
        events.append(name)
        if name == fail_at:
            raise RuntimeError(name)

    monkeypatch.setattr(database, "init_db", lambda: step("migration"))
    monkeypatch.setattr(database, "enable_sqlite_wal", lambda _engine: step("wal"))
    monkeypatch.setattr(seed_mod, "seed_stores", lambda _session: step("seed"))
    monkeypatch.setattr(main_mod, "check_database_ready", lambda _engine, **_kwargs: step("readiness"))
    monkeypatch.setattr(main_mod, "get_settings", lambda: replace(
        Settings(), database_url=str(engine.url), app_env="development", price_refresh_enabled=True, catalog_sync_enabled=True,
    ))
    monkeypatch.setattr(catalog_route, "wait_for_active_sync", lambda timeout: True)

    class Runner:
        worker_count = 2
        queue_capacity = 16
        active_count = 0
        queued_count = 0

        def __init__(self, *_args): step("runner")
        def shutdown(self, timeout): events.append("runner_stop")

    class Price:
        is_running = False
        def __init__(self, *_args): pass
        def start(self): step("price_start")
        def stop(self, timeout): events.append("price_stop")

    class Catalog:
        is_running = False
        def __init__(self, *_args, **_kwargs): pass
        def start(self): step("catalog_start")
        def stop(self, timeout): events.append("catalog_stop")

    monkeypatch.setattr(background_mod, "BackgroundImportRunner", Runner)
    monkeypatch.setattr(price_mod, "PriceRefreshScheduler", Price)
    monkeypatch.setattr(catalog_mod, "CatalogSyncScheduler", Catalog)
    return main_mod.create_app(auto_init=True)


def test_startup_order_and_shutdown(monkeypatch, engine):
    events = []
    app = _wired_startup(monkeypatch, engine, events)
    with TestClient(app) as client:
        assert app.state.ready
        assert client.get("/ready").status_code == 200
    assert events[:7] == ["migration", "wal", "seed", "readiness", "runner", "price_start", "catalog_start"]
    assert events[-3:] == ["price_stop", "catalog_stop", "runner_stop"]


def test_real_startup_migrates_only_temporary_database(monkeypatch, tmp_path):
    from app import config as config_mod, database
    import app.main as main_mod

    url = f"sqlite:///{tmp_path / 'startup.db'}"
    (tmp_path / "startup.db").touch()
    settings = replace(config_mod.get_settings(), database_url=url,
                       app_env="production", price_refresh_enabled=False,
                       catalog_sync_enabled=False)
    engine = database.build_engine(url)
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    try:
        with TestClient(main_mod.create_app(auto_init=True)) as client:
            assert client.get("/ready").status_code == 200
            with engine.connect() as connection:
                assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
                assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
                assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0009_catalog_details"
    finally:
        engine.dispose()


@pytest.mark.parametrize("fail_at", ["migration", "seed", "readiness"])
def test_failed_startup_never_starts_workers(monkeypatch, engine, fail_at):
    events = []
    app = _wired_startup(monkeypatch, engine, events, fail_at=fail_at)
    with pytest.raises(RuntimeError, match=fail_at):
        with TestClient(app):
            pass
    assert "runner" not in events
    assert "price_start" not in events
    assert "catalog_start" not in events
    assert not app.state.ready


def test_startup_rejects_engine_config_mismatch(monkeypatch, engine):
    import app.main as main_mod

    events = []
    _wired_startup(monkeypatch, engine, events)
    monkeypatch.setattr(main_mod, "get_settings", lambda: replace(
        Settings(), database_url="sqlite:///some-other-relative.db",
        app_env="development", price_refresh_enabled=False, catalog_sync_enabled=False,
    ))
    app = main_mod.create_app(auto_init=True)
    with pytest.raises(RuntimeError, match="differ"):
        with TestClient(app):
            pass
    assert events == []


def _tiny_yomiba_db(path):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version(version_num TEXT)")
        connection.execute("INSERT INTO alembic_version VALUES ('0006_publisher_alias_by_name')")
        connection.execute("CREATE TABLE series(id INTEGER PRIMARY KEY, title TEXT)")
        connection.execute("INSERT INTO series VALUES (1, 'Example')")
        connection.execute("CREATE TABLE catalog_series(series_id INTEGER)")
        connection.execute("INSERT INTO catalog_series VALUES (1)")
        for table in ("volumes", "store_listings", "price_history"):
            connection.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY)")


def test_online_backup_and_restore_check(tmp_path):
    from db_backup import backup_database, inspect_database
    source, output = tmp_path / "source.db", tmp_path / "backup.db"
    _tiny_yomiba_db(source)
    with sqlite3.connect(source) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("INSERT INTO series VALUES (2, 'Latest committed')")
    report = backup_database(source, output)
    assert report["counts"]["series"] == 2
    assert inspect_database(output) == report
    with pytest.raises(ValueError, match="differ"):
        backup_database(source, source)
    with pytest.raises(FileExistsError):
        backup_database(source, output)
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        inspect_database(corrupt)


def test_runner_shutdown_discards_queue_and_times_out_safely(engine, caplog):
    from app.services.background_import import BackgroundImportRunner

    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    runner = BackgroundImportRunner(sessions, max_concurrent=1, queue_capacity=1)
    entered, release = threading.Event(), threading.Event()

    def blocked(_key, _query):
        entered.set()
        release.wait(2)

    runner._guarded = blocked
    assert runner.submit("active", "active")
    assert entered.wait(2)
    assert runner.submit("queued", "queued")
    assert not runner.submit("rejected", "rejected")
    assert "queue full" in caplog.text
    runner.shutdown(timeout=0.01)
    assert runner.queued_count == 0
    assert runner.active_count == 1
    assert not runner.submit("later", "later")
    assert "timed out" in caplog.text
    release.set()
    assert runner.wait_for("active", 2)
    runner.shutdown(timeout=2)


def test_catalog_sync_shutdown_wait_is_bounded(monkeypatch):
    import app.routes.catalog as catalog_route

    release = threading.Event()
    thread = threading.Thread(target=lambda: release.wait(2), daemon=True)
    thread.start()
    monkeypatch.setattr(catalog_route, "_sync_thread", thread)
    assert not catalog_route.wait_for_active_sync(timeout=0.01)
    release.set()
    assert catalog_route.wait_for_active_sync(timeout=2)
