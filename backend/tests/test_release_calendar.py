"""Monthly releases must include the whole catalog month, not the home shelf."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models import CatalogSeries, Store, Volume
from tests.test_home_feed import _offer, _vol
from tests.test_import_service import seed_catalog_series


def test_month_has_every_release_and_correct_prices(client, db_session):
    series = seed_catalog_series(db_session, "Takvim Serisi", "Athica", volumes=tuple(range(16)))
    cheap, sold_out = Store(code="cheap", name="Ucuz"), Store(code="sold", name="Tükendi")
    db_session.add_all([cheap, sold_out])
    db_session.flush()
    for number in range(12):
        _vol(db_session, series, number).release_date = date(2024, 2, number + 1)
    # Calendar boundaries, including leap day and adjacent months.
    _vol(db_session, series, 12).release_date = date(2024, 2, 29)
    _vol(db_session, series, 13).release_date = date(2024, 1, 31)
    _vol(db_session, series, 14).release_date = date(2024, 3, 1)
    _offer(db_session, _vol(db_session, series, 0), cheap, 15000)
    _offer(db_session, _vol(db_session, series, 0), sold_out, 10000, in_stock=False)
    db_session.commit()
    client.cookies.clear()  # Public page; no login required.

    response = client.get("/releases?month=2024-02")
    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2024-02"
    assert len(body["volumes"]) == 13
    assert [v["number"] for v in body["volumes"]] == list(range(12, -1, -1))
    assert body["volumes"][0]["release_date"] == "2024-02-29"
    zero = body["volumes"][-1]
    assert zero["lowest_price"] == 150.0 and zero["in_stock_offers"] == 1
    assert zero["series_slug"] and zero["publisher"] == "Athica"
    assert body["volumes"][0]["lowest_price"] is None


def test_calendar_excludes_non_catalog_unresolved_and_unknown_dates(client, db_session):
    series = seed_catalog_series(db_session, "Katalog", "Athica", volumes=(1, -1, 2))
    outsider = seed_catalog_series(db_session, "Katalog Dışı", "Athica", volumes=(1,))
    manifest = db_session.scalar(select(CatalogSeries).where(CatalogSeries.series_id == outsider.id))
    db_session.delete(manifest)
    for volume in db_session.scalars(select(Volume)).all():
        volume.release_date = date(2024, 6, 10)
    _vol(db_session, series, 2).release_date = None
    db_session.commit()
    body = client.get("/releases?month=2024-06").json()
    assert [(v["series_title"], v["number"]) for v in body["volumes"]] == [("Katalog", 1)]


def test_calendar_includes_announced_releases_and_handles_empty_month(client, db_session):
    series = seed_catalog_series(db_session, "Duyuru", "Athica", volumes=(1, 2))
    _vol(db_session, series, 1).release_date = date(2024, 12, 31)
    _vol(db_session, series, 2).release_date = date(9999, 12, 31)
    db_session.commit()
    body = client.get("/releases?month=9999-12").json()
    assert body["volumes"][0]["number"] == 2
    assert body["volumes"][0]["release_date"] > body["today"]
    assert body["latest_month"] == "2024-12"
    assert client.get("/releases?month=2025-01").json()["volumes"] == []
    assert all(v["number"] != 2 for v in client.get("/home").json()["new_volumes"])


@pytest.mark.parametrize("month", [None, "2024-00", "2024-13", "0000-01", "2024-2", "oops"])
def test_calendar_rejects_invalid_month(client, month):
    params = {} if month is None else {"month": month}
    assert client.get("/releases", params=params).status_code == 422
