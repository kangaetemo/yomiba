"""Staging bootstrap and connectivity checks never use the real database."""

from dataclasses import replace
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import config as config_mod, database
from app.config import Settings, prepare_staging_database, validate_runtime_settings
from db_backup import backup_database, inspect_database
from outbound_smoke import probe


def _staging_settings(monkeypatch, tmp_path, *, opt_in=True):
    target = tmp_path / "yomiba-staging.db"
    monkeypatch.setattr(config_mod, "STAGING_DB_PATH", target)
    monkeypatch.setattr(config_mod, "_staging_volume_mounted", lambda path: path == tmp_path)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    settings = replace(Settings(), app_env="staging", database_url=f"sqlite:///{target}",
                       staging_db_bootstrap=opt_in, auth_cookie_secure=True,
                       backend_url="https://yomiba-staging.up.railway.app",
                       cors_origins=("https://yomiba-staging.up.railway.app",),
                       catalog_sync_enabled=False, price_refresh_enabled=False)
    return target, settings


def test_staging_bootstrap_is_explicit_and_volume_bound(monkeypatch, tmp_path):
    target, settings = _staging_settings(monkeypatch, tmp_path, opt_in=False)
    with pytest.raises(ValueError, match="STAGING_DB_BOOTSTRAP"):
        validate_runtime_settings(settings)
    assert not target.exists()
    enabled = replace(settings, staging_db_bootstrap=True)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path / "wrong"))
    with pytest.raises(ValueError, match="mounted Railway volume"):
        prepare_staging_database(enabled)
    assert not target.exists()
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    with pytest.raises(ValueError, match="dedicated"):
        validate_runtime_settings(replace(enabled, database_url=f"sqlite:///{tmp_path / 'other.db'}"))
    with pytest.raises(ValueError, match="AUTH_COOKIE_SECURE"):
        validate_runtime_settings(replace(enabled, auth_cookie_secure=False))
    with pytest.raises(ValueError, match="HTTPS"):
        validate_runtime_settings(replace(enabled, cors_origins=("http://localhost:3000",)))
    assert prepare_staging_database(enabled)
    assert target.is_file() and target.stat().st_size == 0
    assert not prepare_staging_database(settings)
    assert target.stat().st_size == 0


def test_staging_first_start_restart_and_backup_use_temporary_db(monkeypatch, tmp_path):
    import app.main as main_mod

    target, settings = _staging_settings(monkeypatch, tmp_path)
    engine = database.build_engine(settings.database_url)
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    try:
        with TestClient(main_mod.create_app()) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 200
            monkeypatch.setattr(config_mod, "_staging_volume_mounted", lambda _path: False)
            assert client.get("/ready").status_code == 503
            monkeypatch.setattr(config_mod, "_staging_volume_mounted", lambda path: path == tmp_path)
            response = client.post("/auth/register", headers={"Origin": settings.backend_url}, json={
                "email": "staging-marker@example.com", "password": "correct horse battery staple",
                "display_name": "Staging marker",
            })
            assert response.status_code == 201
            assert "Secure" in response.headers["set-cookie"]
        assert target.is_file()
        with sqlite3.connect(target) as connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0007_import_record_reasons",)
            assert connection.execute("SELECT COUNT(*) FROM stores").fetchone()[0] > 0
        backup = tmp_path / "staging-backup.db"
        assert backup_database(target, backup) == inspect_database(backup)
        monkeypatch.setattr(main_mod, "get_settings", lambda: replace(settings, staging_db_bootstrap=False))
        with TestClient(main_mod.create_app()) as client:
            assert client.get("/ready").status_code == 200
            assert client.post("/auth/login", headers={"Origin": settings.backend_url}, json={
                "email": "staging-marker@example.com", "password": "correct horse battery staple",
            }).status_code == 200
    finally:
        engine.dispose()


@pytest.mark.parametrize("code,expected", [(200, "PASS"), (302, "PASS"), (403, "BLOCKED"), (503, "BLOCKED"), (500, "ERROR")])
def test_outbound_probe_classifies_single_http_response(monkeypatch, code, expected):
    from outbound_smoke import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [(None,)])
    transport = httpx.MockTransport(lambda _request: httpx.Response(code))
    with httpx.Client(transport=transport) as client:
        result = probe("Example", "https://example.com/", client)
    assert result["dns"] == "ok"
    assert result["tcp_tls"] == "ok"
    assert result["http_status"] == code
    assert result["status"] == expected


def test_outbound_probe_detects_bounded_bot_wall(monkeypatch):
    from outbound_smoke import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [(None,)])
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text="<title>Just a moment</title>"))
    with httpx.Client(transport=transport) as client:
        assert probe("Example", "https://example.com/", client)["status"] == "BLOCKED"
