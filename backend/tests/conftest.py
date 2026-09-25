"""Shared pytest fixtures.

Provides an isolated in-memory SQLite database and a fresh ``ImportService``
so import / API tests never touch the real ``yomiba.db``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401  (register models)
from app.database import Base


@pytest.fixture(autouse=True)
def fast_scraper_network(monkeypatch):
    """Zero out scraper retry backoff / request interval so tests never sleep.

    Applies to every test: ``BaseScraper`` reads settings at construction,
    so the scraper package's ``get_settings`` binding is patched.
    """
    from dataclasses import replace

    from app import scrapers
    from app.config import get_settings

    fast = replace(
        get_settings(),
        scraper_retry_backoff_seconds=0.0,
        scraper_min_request_interval_seconds=0.0,
    )
    monkeypatch.setattr(scrapers.base, "get_settings", lambda: fast)
    yield


@pytest.fixture()
def engine(tmp_path):
    # File-based SQLite: background import jobs open their own sessions, so
    # tests need a multi-connection database (the production shape), not a
    # single shared in-memory connection.
    engine = create_engine(
        f"sqlite:///{tmp_path}/test_yomiba.db",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(engine):
    from app.models import User
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    session.add(User(email="test-admin@example.com", password_hash=None,
                     display_name="Test admin", role="ADMIN", is_active=True))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def import_service(db_session):
    from app.services.import_service import ImportService

    return ImportService(db_session)


@pytest.fixture()
def client(engine, db_session, monkeypatch):
    """FastAPI TestClient wired to the test database, with NO real scrapers.

    Both import paths share the same recording fake scraper: the background
    runner via its factory, and the manual /import route via a patched
    ``get_scrapers``. API tests therefore never touch the real database or
    the network. Tests that need different scraper behaviour monkeypatch
    ``app.services.import_service.get_scrapers`` (applied later, wins).
    """
    from app.database import get_db
    from app.main import create_app
    from app.services import import_service as import_service_mod
    from app.services.background_import import BackgroundImportRunner
    from tests.helpers import RecordingScraper

    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    app = create_app(auto_init=False)

    def fake_scrapers(store_ids=None):
        return [RecordingScraper(store_id="bkm")]

    monkeypatch.setattr(import_service_mod, "get_scrapers", fake_scrapers)
    app.state.import_runner = BackgroundImportRunner(
        TestingSession, scraper_factory=fake_scrapers, max_concurrent=2
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    from app.auth import COOKIE_NAME, new_session
    from app.models import User

    # Existing API tests exercise authenticated behavior. New security tests
    # use a separate anonymous client or clear this cookie explicitly.
    admin = db_session.get(User, 1)
    token = new_session(db_session, admin)
    with TestClient(app, base_url="https://testserver", headers={"Origin": "http://localhost:3000"}) as test_client:
        test_client.cookies.set(COOKIE_NAME, token)
        yield test_client
