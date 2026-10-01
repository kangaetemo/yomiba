"""Public series URLs use number-free slugs; old numeric links still resolve."""

from __future__ import annotations

from app.services import series_slugs
from tests.test_import_service import seed_catalog_series


def test_slug_resolves_series_and_legacy_id(client, db_session):
    berserk = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1,))
    db_session.commit()
    assert series_slugs.slug_for(db_session, berserk.id) == "berserk"
    assert client.get("/series/berserk").json()["slug"] == "berserk"
    assert client.get(f"/series/{berserk.id}").json()["slug"] == "berserk"
    assert client.get("/series/yok-boyle-bir-seri").status_code == 404


def test_same_title_at_two_publishers_gets_distinct_slugs(client, db_session):
    first = seed_catalog_series(db_session, "Akira", "Athica", volumes=(1,))
    second = seed_catalog_series(db_session, "Akira", "Marmara Çizgi", volumes=(1,))
    db_session.commit()
    a = series_slugs.slug_for(db_session, first.id)
    b = series_slugs.slug_for(db_session, second.id)
    assert a == "akira" and b != a and b.startswith("akira-")
    assert client.get(f"/series/{b}").json()["id"] == second.id
