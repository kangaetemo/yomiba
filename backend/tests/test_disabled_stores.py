"""Stores that block the production host are skipped by default imports."""

from dataclasses import replace

from app.config import get_settings
from app.scrapers import registry


def _with(monkeypatch, disabled):
    settings = replace(get_settings(), disabled_stores=tuple(disabled))
    monkeypatch.setattr(registry, "get_settings", lambda: settings)


def test_default_disables_blocked_stores():
    import os
    if "DISABLED_STORES" not in os.environ:
        assert get_settings().disabled_stores == ("amazon", "dr", "cizman")


def test_get_scrapers_skips_disabled_by_default(monkeypatch):
    _with(monkeypatch, ["amazon", "dr", "cizman"])
    ids = [s.store_id for s in registry.get_scrapers()]
    assert ids == ["bkm", "kitapsepeti", "kitapbulan", "gerekliseyler", "kitapsec", "komikseyler"]
    assert registry.enabled_store_ids() == ids


def test_explicit_store_ids_still_run_disabled_store(monkeypatch):
    _with(monkeypatch, ["cizman"])
    assert [s.store_id for s in registry.get_scrapers(["cizman"])] == ["cizman"]


def test_empty_setting_enables_all(monkeypatch):
    _with(monkeypatch, [])
    assert len(registry.get_scrapers()) == 9
