"""Price alerts fire once per crossing and their mails go through the outbox."""
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import EmailOutbox, PriceAlert, Store, StoreListing, User, Volume
from app.services import mailer, price_alerts_service
from app.services.price_alert_checker import check_alerts, store_link
from tests.test_import_service import seed_catalog_series


def _setup(db_session, price=19000, threshold=20000, in_stock=True):
    series = seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=(29,))
    volume = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()
    listing = StoreListing(volume_id=volume.id, store_id=store.id, product_url="https://bkm.example/blue-lock-29",
                           price=price, in_stock=in_stock, last_checked=datetime.now(timezone.utc))
    user = db_session.scalar(select(User))
    alert = PriceAlert(user_id=user.id, volume_id=volume.id, threshold_price=threshold, is_active=True)
    db_session.add_all([listing, alert])
    db_session.commit()
    return volume, listing, alert


def _mails(db_session):
    return list(db_session.scalars(select(EmailOutbox).order_by(EmailOutbox.id)))


def test_alert_fires_once_per_crossing(db_session):
    volume, listing, alert = _setup(db_session)
    assert check_alerts(db_session, [volume.id])["fired"] == 1
    assert check_alerts(db_session, [volume.id])["fired"] == 0  # next refresh: no repeat
    mails = _mails(db_session)
    assert len(mails) == 1
    assert mails[0].to_email == "test-admin@example.com"
    assert mails[0].subject == "Fiyat alarmı: Blue Lock · Cilt 29 190 TL"
    assert "https://bkm.example/blue-lock-29?utm_source=yomiba&utm_medium=email" in mails[0].body_text
    assert "/series/blue-lock/cilt-29" in mails[0].body_text
    assert (alert.triggered_price, alert.triggered_at is not None) == (19000, True)

    listing.price = 25000  # back above the threshold: re-armed
    db_session.commit()
    assert check_alerts(db_session, [volume.id])["rearmed"] == 1
    listing.price = 18000
    db_session.commit()
    assert check_alerts(db_session, [volume.id])["fired"] == 1
    assert len(_mails(db_session)) == 2


def test_sold_out_neither_fires_nor_rearms(db_session):
    volume, listing, alert = _setup(db_session)
    check_alerts(db_session, [volume.id])
    listing.in_stock = False
    db_session.commit()
    assert check_alerts(db_session, [volume.id]) == {"fired": 0, "rearmed": 0}
    listing.in_stock = True  # back in stock at the same low price
    db_session.commit()
    assert check_alerts(db_session, [volume.id])["fired"] == 0
    assert len(_mails(db_session)) == 1


def test_out_of_stock_offer_never_fires(db_session):
    volume, _, _ = _setup(db_session, in_stock=False)
    assert check_alerts(db_session, [volume.id])["fired"] == 0
    assert _mails(db_session) == []


def test_new_threshold_rearms_and_paused_alert_is_ignored(db_session):
    volume, _, alert = _setup(db_session)
    check_alerts(db_session, [volume.id])
    price_alerts_service.upsert_price_alert(db_session, volume.id, alert.user_id, threshold_price=19500)
    assert alert.triggered_at is None
    price_alerts_service.upsert_price_alert(db_session, volume.id, alert.user_id, is_active=False)
    assert check_alerts(db_session, [volume.id])["fired"] == 0
    price_alerts_service.upsert_price_alert(db_session, volume.id, alert.user_id, is_active=True)
    assert check_alerts(db_session, [volume.id])["fired"] == 1


def test_mail_waits_without_smtp_and_is_sent_once_configured(db_session, monkeypatch):
    volume, _, _ = _setup(db_session)
    check_alerts(db_session, [volume.id])
    base = mailer.get_settings()
    monkeypatch.setattr(mailer, "get_settings", lambda: replace(base, smtp_host=""))
    assert mailer.send_pending(db_session) == {"sent": 0, "failed": 0}
    assert _mails(db_session)[0].sent_at is None

    sent = []

    class FakeSMTP:
        def send_message(self, msg):
            sent.append((msg["To"], msg["Subject"], msg.get_body(("plain",)).get_content()))

        def quit(self):
            pass

    monkeypatch.setattr(mailer, "get_settings", lambda: replace(base, smtp_host="smtp.example"))
    assert mailer.send_pending(db_session, connect=lambda s: FakeSMTP()) == {"sent": 1, "failed": 0}
    assert sent[0][:2] == ("test-admin@example.com", "Fiyat alarmı: Blue Lock · Cilt 29 190 TL")
    assert _mails(db_session)[0].sent_at is not None
    assert mailer.send_pending(db_session, connect=lambda s: FakeSMTP()) == {"sent": 0, "failed": 0}


def test_smtp_failure_is_retried_later(db_session, monkeypatch):
    volume, _, _ = _setup(db_session)
    check_alerts(db_session, [volume.id])
    base = mailer.get_settings()
    monkeypatch.setattr(mailer, "get_settings", lambda: replace(base, smtp_host="smtp.example"))

    def down(settings):
        raise OSError("connection refused")

    assert mailer.send_pending(db_session, connect=down)["failed"] == 1
    row = _mails(db_session)[0]
    assert (row.attempts, row.sent_at) == (1, None) and "connection refused" in row.last_error
    # Not due yet: the retry waits.
    assert mailer.send_pending(db_session, connect=down) == {"sent": 0, "failed": 0}


def test_price_refresh_checks_the_series_alerts(db_session):
    from app.services.background_import import BackgroundImportRunner

    volume, _, _ = _setup(db_session)
    BackgroundImportRunner._check_price_alerts(db_session, "Blue Lock")
    assert len(_mails(db_session)) == 1


def test_store_link_tags_without_touching_the_store_query():
    assert store_link("https://edessakitabevi.com/frieren-cilt-6?vid=a%20b#x") == \
        "https://edessakitabevi.com/frieren-cilt-6?vid=a%20b&utm_source=yomiba&utm_medium=email#x"
    assert store_link("https://x.example/p?utm_source=other") == "https://x.example/p?utm_source=other"
    assert store_link("not a url") == "not a url"
