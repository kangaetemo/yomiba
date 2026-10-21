""""Hatalı içerik bildir": a visitor's report reaches the admin list, and
the form's abuse guards drop or refuse what they should."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import ContentReport, Store, Volume
from app.services import analytics, content_reports
from app.services.series_slugs import slug_for
from tests.test_import_service import seed_catalog_series

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    monkeypatch.setattr(content_reports, "_burst", content_reports.SlidingLimiter(3, 600))
    monkeypatch.setattr(content_reports, "_daily", content_reports.SlidingLimiter(10, 86_400))
    monkeypatch.setattr(content_reports, "_site", content_reports.SlidingLimiter(300, 86_400))
    monkeypatch.setattr(analytics, "_salt_cache", {})


def anon_client(client, ip="203.0.113.7"):
    return TestClient(client.app, base_url="https://testserver",
                      headers={"Origin": "http://localhost:3000", "User-Agent": UA, "X-Forwarded-For": ip})


@pytest.fixture()
def page(db_session):
    series = seed_catalog_series(db_session, "Berserk", "Gerekli Şeyler", volumes=(1, 2))
    volume = db_session.scalar(select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 2))
    db_session.add(Store(code="dr-test", name="D&R Test"))
    db_session.commit()
    return series, volume, f"/series/{slug_for(db_session, series.id)}/cilt-2"


def report(c, path, **extra):
    body = {"category": "price", "message": "Fiyat 250 TL değil, mağazada 320 TL yazıyor.",
            "path": path, "filled_ms": 8000, "website": ""}
    body.update(extra)
    return c.post("/hata-bildir", json=body)


def reports(db):
    return list(db.scalars(select(ContentReport).order_by(ContentReport.id)))


def test_anonymous_report_reaches_the_admin_list(client, db_session, page):
    series, volume, path = page
    with anon_client(client) as anon:
        assert report(anon, path, store="D&R Test").status_code == 204
    [row] = reports(db_session)
    assert (row.series_id, row.volume_id, row.status, row.user_id) == (series.id, volume.id, "new", None)
    assert len(row.reporter) == 16 and "203.0.113.7" not in row.reporter

    listing = client.get("/admin/reports").json()
    assert listing["counts"] == {"new": 1, "resolved": 0, "dismissed": 0}
    [item] = listing["items"]
    assert (item["path"], item["series"], item["volume_number"], item["store"]) == (path, "Berserk", 2, "D&R Test")
    assert item["category_label"] == "Fiyat yanlış"
    assert client.get("/admin/reports/count").json() == {"new": 1}

    assert client.patch(f"/admin/reports/{row.id}", json={"status": "resolved"}).status_code == 200
    assert client.get("/admin/reports").json()["items"] == []
    assert client.get("/admin/reports?status=resolved").json()["items"][0]["resolved_at"]


def test_admin_endpoints_need_an_admin(client, page):
    with anon_client(client) as anon:
        assert anon.get("/admin/reports").status_code == 401
        assert anon.patch("/admin/reports/1", json={"status": "resolved"}).status_code == 401


def test_bot_traps_are_dropped_silently(client, db_session, page):
    _, _, path = page
    with anon_client(client) as anon:
        assert report(anon, path, website="http://spam.example").status_code == 204
        assert report(anon, path, filled_ms=400).status_code == 204
        assert report(anon, path, message="Ucuz ilaç http://a.example http://b.example http://c.example").status_code == 204
        assert report(anon, path).status_code == 204
        assert report(anon, path).status_code == 204  # same text again: a duplicate
    assert len(reports(db_session)) == 1


def test_people_are_told_what_is_wrong(client, page):
    _, _, path = page
    with anon_client(client) as anon:
        assert report(anon, path, message="kötü").status_code == 422
        assert report(anon, path, message="x" * 1001).status_code == 422
        assert report(anon, "/admin").status_code == 422
        assert report(anon, "/series/olmayan-seri").status_code == 422


def test_one_sender_is_rate_limited_but_others_are_not(client, db_session, page):
    _, _, path = page
    with anon_client(client) as anon:
        for i in range(3):
            assert report(anon, path, message=f"Stok bilgisi yanlış, deneme {i}").status_code == 204
        refused = report(anon, path, message="Dördüncü bildirim burada")
        assert refused.status_code == 429 and "Çok fazla" in refused.json()["detail"]
    with anon_client(client, ip="198.51.100.9") as other:
        assert report(other, path, message="Başka birinden gelen bildirim").status_code == 204
    assert len(reports(db_session)) == 4


def test_open_list_has_a_ceiling(client, db_session, page, monkeypatch):
    _, _, path = page
    monkeypatch.setattr(content_reports, "MAX_OPEN", 1)
    with anon_client(client) as anon:
        assert report(anon, path).status_code == 204
        assert report(anon, path, message="Bir bildirim daha gönderiyorum").status_code == 429


def test_message_is_kept_as_plain_text(client, db_session, page):
    _, _, path = page
    with anon_client(client) as anon:
        report(anon, path, message="<script>alert(1)</script>\r\n\r\n\r\n\r\nikinci   satır\x00")
    [row] = reports(db_session)
    assert row.message == "<script>alert(1)</script>\n\nikinci satır"
