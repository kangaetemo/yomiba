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


def test_series_lists_other_editions(client, db_session):
    """The plain edition and its "~clothbound" variant point at each other;
    an unrelated series has no editions."""
    from sqlalchemy import select

    from app.models import CatalogSeries

    plain = seed_catalog_series(db_session, "Soichi", "Gerekli Şeyler", volumes=(1,))
    cloth = seed_catalog_series(db_session, "Soichi (Bez Cilt)", "Gerekli Şeyler", volumes=(1, 2))
    other = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1,))
    for series, slug in ((plain, "soichi"), (cloth, "soichi~clothbound")):
        row = db_session.scalar(select(CatalogSeries).where(CatalogSeries.series_id == series.id))
        row.mangakol_slug = slug
    db_session.commit()

    from_plain = client.get(f"/series/{series_slugs.slug_for(db_session, plain.id)}").json()["editions"]
    assert [e["title"] for e in from_plain] == ["Soichi (Bez Cilt)"]
    assert from_plain[0]["volume_count"] == 2 and from_plain[0]["slug"]
    from_cloth = client.get(f"/series/{series_slugs.slug_for(db_session, cloth.id)}").json()["editions"]
    assert [e["title"] for e in from_cloth] == ["Soichi"]
    assert client.get(f"/series/{series_slugs.slug_for(db_session, other.id)}").json()["editions"] == []


def test_all_one_shots_lists_beyond_the_home_shelf(client, db_session):
    for i in range(12):
        s = seed_catalog_series(db_session, f"Tek {i:02d}", "Gerekli Şeyler", volumes=(1,))
        s.jp_status = s.tr_status = "completed"
    db_session.commit()
    assert len(client.get("/home").json()["one_shots"]) == 8
    assert len(client.get("/one-shots").json()["one_shots"]) == 12
