"""Back in stock ("Tekrar stokta"): restock events, stock alerts, wishlist
mails and the public lists."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.models import (
    EmailOutbox,
    PriceHistory,
    RestockEvent,
    StockAlert,
    Store,
    StoreListing,
    User,
    UserVolumeCollection,
    Volume,
    WishlistItem,
)
from app.services import restocks, stock_alerts_service
from tests.test_import_service import seed_catalog_series

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _setup(db_session, *, in_stock=True, release=date(2025, 1, 10), volumes=(29,)):
    series = seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=volumes)
    vols = list(db_session.scalars(select(Volume).where(Volume.series_id == series.id).order_by(Volume.volume_number)))
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()
    listings = []
    for v in vols:
        v.release_date = release
        listing = StoreListing(volume_id=v.id, store_id=store.id, product_url=f"https://bkm.example/blue-lock-{v.volume_number}",
                               price=19000, in_stock=in_stock, last_checked=T0)
        db_session.add(listing)
        db_session.flush()
        db_session.add(PriceHistory(listing_id=listing.id, price=19000, in_stock=in_stock, checked_at=T0))
        listings.append(listing)
    db_session.commit()
    return vols, listings


def _check(db_session, volumes, at):
    return restocks.process(db_session, [v.id for v in volumes], now=at)


def _events(db_session):
    return list(db_session.scalars(select(RestockEvent).order_by(RestockEvent.id)))


def _mails(db_session):
    return list(db_session.scalars(select(EmailOutbox).order_by(EmailOutbox.id)))


def test_back_after_a_week_is_a_restock(db_session):
    vols, (listing,) = _setup(db_session)
    _check(db_session, vols, T0)  # first check: state only
    listing.in_stock = False
    db_session.commit()
    _check(db_session, vols, T0 + timedelta(days=1))
    assert _events(db_session) == []
    listing.in_stock = True
    db_session.commit()
    counts = _check(db_session, vols, T0 + timedelta(days=9))
    assert counts["restocked"] == 1
    (event,) = _events(db_session)
    assert restocks.out_days(event) == 9 and event.price == 19000
    assert _check(db_session, vols, T0 + timedelta(days=10))["restocked"] == 0  # still in stock: once


def test_short_gap_and_first_check_write_nothing(db_session):
    vols, (listing,) = _setup(db_session)
    _check(db_session, vols, T0)
    listing.in_stock = False
    db_session.commit()
    _check(db_session, vols, T0 + timedelta(hours=12))
    listing.in_stock = True
    db_session.commit()
    assert _check(db_session, vols, T0 + timedelta(days=3))["restocked"] == 0

    # A volume never checked before only records its state.
    vols[0].stock_checked_at = vols[0].last_in_stock_at = None
    vols[0].last_in_stock_at = T0 - timedelta(days=60)
    db_session.commit()
    assert _check(db_session, vols, T0 + timedelta(days=4))["restocked"] == 0
    assert _events(db_session) == []


def test_old_volume_never_seen_in_stock_counts_new_release_does_not(db_session):
    vols, (listing,) = _setup(db_session, in_stock=False)
    _check(db_session, vols, T0)
    listing.in_stock = True
    db_session.commit()
    _check(db_session, vols, T0 + timedelta(days=10))
    (event,) = _events(db_session)
    assert event.out_since is None and restocks.out_days(event) is None

    db_session.delete(event)
    db_session.commit()
    vols[0].release_date = date(2026, 10, 5)  # came out days ago: a new release
    vols[0].last_in_stock_at = None
    vols[0].stock_checked_at = T0
    db_session.commit()
    assert _check(db_session, vols, T0 + timedelta(days=11))["restocked"] == 0


def test_stale_listing_does_not_count_as_stock(db_session):
    vols, listings = _setup(db_session, volumes=(28, 29))
    # The store's other product was refreshed 3 days later; this one was not seen.
    listings[1].last_checked = T0 + timedelta(days=3)
    db_session.commit()
    assert set(restocks.best_offers(db_session, [v.id for v in vols])) == {vols[1].id}


def test_stock_alert_fires_once_without_gap_and_can_be_set_again(db_session):
    vols, (listing,) = _setup(db_session, in_stock=False)
    user = db_session.scalar(select(User))
    _check(db_session, vols, T0)
    alert = stock_alerts_service.set_stock_alert(db_session, vols[0].id, user.id)
    assert _check(db_session, vols, T0 + timedelta(hours=6))["alerts"] == 0  # still sold out
    listing.in_stock = True
    db_session.commit()
    counts = _check(db_session, vols, T0 + timedelta(hours=12))
    assert (counts["alerts"], counts["mails"]) == (1, 1)
    assert alert.triggered_at is not None
    (mail,) = _mails(db_session)
    assert mail.subject == "Stokta: Blue Lock · Cilt 29"
    assert mail.kind == "restock" and mail.to_email == "test-admin@example.com"
    assert "https://bkm.example/blue-lock-29?utm_source=yomiba&utm_medium=email" in mail.body_text
    assert "/series/blue-lock/cilt-29" in mail.body_text
    assert "Stok alarmı bir kez çalar" in mail.body_text
    assert _check(db_session, vols, T0 + timedelta(days=1))["alerts"] == 0
    stock_alerts_service.set_stock_alert(db_session, vols[0].id, user.id)
    assert alert.triggered_at is None


def _wishlister(db_session, email, volume, *, verified=True, restock_mail=True):
    user = User(email=email, display_name=email.split("@")[0], role="USER", is_active=True,
                email_verified_at=T0 if verified else None, restock_mail=restock_mail)
    db_session.add(user)
    db_session.flush()
    db_session.add(WishlistItem(user_id=user.id, volume_id=volume.id))
    db_session.commit()
    return user


def _restock(db_session, vols, listings, while_out=None):
    _check(db_session, vols, T0)
    for listing in listings:
        listing.in_stock = False
    db_session.commit()
    _check(db_session, vols, T0 + timedelta(days=1))
    if while_out:
        while_out()
    for listing in listings:
        listing.in_stock = True
    db_session.commit()
    return _check(db_session, vols, T0 + timedelta(days=9))


def test_wishlist_mail_only_to_verified_opted_in_non_owners(db_session):
    vols, listings = _setup(db_session, volumes=(28, 29))
    yes = _wishlister(db_session, "yes@example.com", vols[1])
    _wishlister(db_session, "unverified@example.com", vols[1], verified=False)
    _wishlister(db_session, "off@example.com", vols[1], restock_mail=False)
    owner = _wishlister(db_session, "owner@example.com", vols[1])
    db_session.add(UserVolumeCollection(user_id=owner.id, volume_id=vols[1].id, status="owned"))
    db_session.add(WishlistItem(user_id=yes.id, volume_id=vols[0].id))
    db_session.commit()

    counts = _restock(db_session, vols, listings)
    assert counts["restocked"] == 2
    (mail,) = _mails(db_session)
    assert mail.to_email == "yes@example.com"
    assert mail.subject == "Stokta: Blue Lock · Cilt 28 ve 1 cilt daha"
    assert "Beklediğin 2 cilt yeniden satışta." in mail.body_text
    assert "Hesabım sayfasından kapatabilirsin" in mail.body_text


def test_alert_and_wishlist_share_one_mail(db_session):
    vols, listings = _setup(db_session)
    user = _wishlister(db_session, "both@example.com", vols[0])
    _restock(db_session, vols, listings,
             while_out=lambda: stock_alerts_service.set_stock_alert(db_session, vols[0].id, user.id))
    mails = [m for m in _mails(db_session) if m.to_email == "both@example.com"]
    assert len(mails) == 1
    assert "Stok alarmı bir kez çalar" in mails[0].body_text


def test_public_list_badges_and_endpoints(db_session, client):
    vols, (listing,) = _setup(db_session)
    _restock(db_session, vols, [listing])
    # Events are dated in the past (T0 + 9 days); the API looks back from now.
    for event in _events(db_session):
        event.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        event.out_since = event.created_at - timedelta(days=8)
    db_session.commit()

    body = client.get("/restocks?days=7").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert (item["series_slug"], item["volume_number"], item["out_days"], item["price"]) == ("blue-lock", 29, 8, 190.0)
    assert item["store_name"] == "BKM Kitap" and item["in_stock_count"] == 1

    series = client.get("/series/blue-lock").json()
    assert series["volumes"][0]["restocked_at"] is not None
    volume = client.get(f"/volume/{vols[0].id}").json()
    assert volume["restocked_at"] is not None and volume["restock_out_days"] == 8

    insta = client.get("/admin/instagram/restocks?days=7").json()
    assert insta["volumes"][0]["number"] == 29 and insta["volumes"][0]["out_days"] == 8

    listing.in_stock = False  # sold out again: off the list
    db_session.commit()
    assert client.get("/restocks?days=7").json()["total"] == 0


def test_stock_alert_endpoints_and_account_setting(db_session, client):
    vols, _ = _setup(db_session, in_stock=False)
    vid = vols[0].id
    assert client.get(f"/volume/{vid}/stock-alert").json() == {"volume_id": vid, "alert": None}
    alert = client.put(f"/volume/{vid}/stock-alert").json()["alert"]
    assert alert["triggered_at"] is None
    (mine,) = client.get("/me/stock-alerts").json()
    assert (mine["volume_id"], mine["series_title"]) == (vid, "Blue Lock")
    assert client.delete(f"/volume/{vid}/stock-alert").json()["alert"] is None
    assert client.get("/me/stock-alerts").json() == []

    assert client.get("/auth/me").json()["restock_mail"] is True
    me = client.patch("/auth/me", json={"restock_mail": False}).json()
    assert me["restock_mail"] is False and me["display_name"] == "Test admin"
    assert client.patch("/auth/me", json={"display_name": "Yeni"}).json()["restock_mail"] is False


def test_price_refresh_runs_the_restock_check(db_session):
    from app.services.background_import import BackgroundImportRunner

    vols, (listing,) = _setup(db_session, in_stock=False)
    user = db_session.scalar(select(User))
    db_session.add(StockAlert(user_id=user.id, volume_id=vols[0].id, created_at=T0))
    listing.in_stock = True
    db_session.commit()
    BackgroundImportRunner._check_price_alerts(db_session, "Blue Lock")
    assert [m.kind for m in _mails(db_session)] == ["restock"]
    assert db_session.get(Volume, vols[0].id).stock_checked_at is not None
