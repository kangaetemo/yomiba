"""First-party analytics: the beacon records, attributes and filters
events; the admin report adds them up."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AnalyticsEvent, AnalyticsSalt, Store, StoreListing, Volume
from app.services import analytics
from app.services.series_slugs import slug_for
from tests.test_import_service import seed_catalog_series

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    monkeypatch.setattr(analytics, "_limiter", analytics.RateLimiter())
    monkeypatch.setattr(analytics, "_salt_cache", {})
    monkeypatch.setattr(analytics, "_last_prune", [""])


@pytest.fixture()
def visitor(client):
    """An anonymous browser on the same app (the default client is admin)."""
    anon = TestClient(client.app, base_url="https://testserver",
                      headers={"Origin": "http://localhost:3000", "User-Agent": UA,
                               "X-Forwarded-For": "203.0.113.7, 172.18.0.5"})
    with anon:
        yield anon


def send(c, **payload):
    payload.setdefault("s", "sess-abc-123")
    response = c.post("/olay", content=__import__("json").dumps(payload), headers={"Content-Type": "text/plain"})
    assert response.status_code == 204
    return response


@pytest.fixture()
def catalog(db_session):
    series = seed_catalog_series(db_session, "Berserk", "Gerekli Şeyler", volumes=(1, 2))
    volumes = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id))}
    store = Store(code="dr-test", name="D&R Test")
    db_session.add(store)
    db_session.flush()
    listing = StoreListing(volume_id=volumes[2].id, store_id=store.id, product_url="https://www.dr.com.tr/kitap/berserk-2",
                           price=25000, in_stock=True, last_checked=datetime.now(timezone.utc))
    db_session.add(listing)
    db_session.commit()
    return series, volumes, store, listing


def events(db):
    return list(db.scalars(select(AnalyticsEvent).order_by(AnalyticsEvent.id)))


def test_pageview_is_attributed_and_anonymous(visitor, db_session, catalog):
    series, volumes, _, _ = catalog
    slug = slug_for(db_session, series.id)
    send(visitor, k="pageview", u=f"/series/{slug}/cilt-2?utm_source=instagram&utm_campaign=ekim",
         r="https://www.google.com/search?q=berserk", w=390, n=True)
    [event] = events(db_session)
    assert (event.path, event.series_id, event.volume_id) == (f"/series/{slug}/cilt-2", series.id, volumes[2].id)
    assert (event.referrer_host, event.utm_source, event.utm_campaign) == ("google.com", "instagram", "ekim")
    assert (event.device, event.browser, event.os, event.is_returning, event.logged_in) == ("mobile", "Safari", "iOS", True, False)
    assert len(event.visitor) == 16 and "203.0.113.7" not in event.visitor
    # Same browser, same day: same visitor; the salt is stored for restarts.
    send(visitor, k="pageview", u=f"/series/{slug}")
    assert len({e.visitor for e in events(db_session)}) == 1
    assert db_session.scalar(select(AnalyticsSalt.day)) == event.day


def test_outbound_click_finds_the_listing_through_utm_tags(visitor, db_session, catalog):
    series, volumes, store, listing = catalog
    send(visitor, k="outbound", u="/", t="https://www.dr.com.tr/kitap/berserk-2?utm_source=yomiba&utm_medium=referral")
    [event] = events(db_session)
    assert (event.listing_id, event.store_id, event.volume_id, event.series_id) == (listing.id, store.id, volumes[2].id, series.id)
    assert event.target_url == "https://www.dr.com.tr/kitap/berserk-2"
    # A store page that is not a listing still counts for the store.
    send(visitor, k="outbound", u="/", t="https://www.dr.com.tr/kampanya")
    assert events(db_session)[-1].store_id == store.id and events(db_session)[-1].listing_id is None


def test_strip_utm_keeps_other_parameters():
    assert analytics.strip_utm("https://a.tr/x?vid=abc&utm_source=yomiba&utm_medium=referral") == "https://a.tr/x?vid=abc"
    assert analytics.strip_utm("https://a.tr/x?utm_source=yomiba#top") == "https://a.tr/x#top"


def test_bots_admins_and_junk_are_dropped(client, visitor, db_session):
    send(client, k="pageview", u="/")                                   # admin cookie
    send(visitor, k="pageview", u="/", s="x")                           # bad session id
    send(visitor, k="nope", u="/")
    send(visitor, k="outbound", u="/", t="javascript:alert(1)")
    bot = TestClient(client.app, base_url="https://testserver",
                     headers={"Origin": "http://localhost:3000", "User-Agent": "Googlebot/2.1"})
    send(bot, k="pageview", u="/")
    assert events(db_session) == []
    assert visitor.post("/olay", content="not json").status_code == 204


def test_cross_origin_beacon_is_refused(visitor):
    assert visitor.post("/olay", content="{}", headers={"Origin": "https://evil.example"}).status_code == 403


def test_rate_limit(visitor, db_session, monkeypatch):
    monkeypatch.setattr(analytics, "_limiter", analytics.RateLimiter(limit=3))
    for _ in range(5):
        send(visitor, k="pageview", u="/")
    assert len(events(db_session)) == 3


def test_report(client, visitor, db_session, catalog):
    series, volumes, store, listing = catalog
    slug = slug_for(db_session, series.id)
    send(visitor, k="pageview", u="/", r="https://t.co/x")
    send(visitor, k="search", u="/", q="  Berserk ", v=1)
    send(visitor, k="search", u="/", q="vagabond", v=0)
    send(visitor, k="pageview", u=f"/series/{slug}/cilt-2")
    send(visitor, k="engage", u=f"/series/{slug}/cilt-2", v=42)
    send(visitor, k="outbound", u=f"/series/{slug}/cilt-2", t=listing.product_url + "?utm_source=yomiba")
    send(visitor, k="pageview", u="/", s="sess-other-999")             # a bounce

    r = client.get("/admin/analytics?days=7").json()
    t = r["totals"]
    assert (t["sessions"], t["pageviews"], t["outbound"], t["searches"], t["zero_result_searches"]) == (2, 3, 1, 2, 1)
    assert t["bounce_rate"] == 0.5 and t["click_rate"] == 0.5 and t["avg_session_seconds"] == 21
    assert r["stores"][0]["name"] == "D&R Test" and r["stores"][0]["clicks"] == 1 and sum(r["stores"][0]["trend"]) == 1
    assert r["top_volumes"][0]["volume_id"] == volumes[2].id
    assert r["top_volumes"][0]["click_rate"] == 1.0 and r["top_volumes"][0]["path"] == f"/series/{slug}/cilt-2"
    assert r["top_series"][0]["title"] == "Berserk"
    assert r["zero_searches"][0]["query"] == "vagabond" and {s["query"] for s in r["searches"]} == {"berserk", "vagabond"}
    assert r["search_click_rate"] == 1.0
    assert {x["name"] for x in r["referrers"]} == {"t.co", None}
    assert r["funnel"] == {"sessions": 2, "viewed_volume": 1, "clicked_store": 1}
    assert len(r["series"]) == 7 and sum(p["pageviews"] for p in r["series"]) == 3
    assert r["live"]["sessions"] == 2
    assert sum(map(sum, r["heatmap"])) == 3
    assert len(client.get("/admin/analytics?days=1").json()["series"]) == 24


def test_report_requires_admin(visitor):
    assert visitor.get("/admin/analytics").status_code == 401


def test_old_events_are_pruned(db_session):
    old = datetime.now(timezone.utc) - timedelta(days=analytics.RETENTION_DAYS + 5)
    db_session.add(AnalyticsEvent(ts=old, day=analytics.local_now(old).date().isoformat(), hour=1, kind="pageview",
                                  path="/", visitor="v", session="s" * 8, is_returning=False, logged_in=False,
                                  device="desktop", browser="Chrome", os="Windows"))
    db_session.commit()
    analytics._prune(db_session, analytics.local_now().date())
    assert events(db_session) == []


def test_user_agent_parsing():
    assert analytics.parse_user_agent(UA) == ("mobile", "Safari", "iOS")
    assert analytics.parse_user_agent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0") == ("desktop", "Edge", "Windows")
    assert analytics.parse_user_agent("Mozilla/5.0 (Linux; Android 14; SM-T870) Chrome/130.0 Safari/537.36")[0] == "tablet"
