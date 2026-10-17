"""Admins remove a wrongly matched store listing; the product never returns.

Real case (2026-09-29): Kitapseç's novel "İtiraf" (Dokuz Yayınları, ISBN
9786054737994) was attached by title to the manga "İtiraf Cilt 1" before
the catalog had the manga's ISBN.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import ListingExclusion, PriceHistory, Store, StoreListing, Volume
from app.services.import_service import ImportAction
from tests.test_import_service import make_result, seed_catalog_series

URL = "https://www.kitapsec.com/Products/Itiraf-Dokuz-Yayinlari-215902.html"


def _wrong_listing(db_session):
    series = seed_catalog_series(db_session, "İtiraf", "Komik Şeyler", volumes=(1,))
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    store = Store(code="kitapsec", name="Kitapsec")
    db_session.add(store)
    db_session.flush()
    listing = StoreListing(volume_id=vol.id, store_id=store.id, product_url=URL, price=12000)
    db_session.add(listing)
    db_session.flush()
    db_session.add(PriceHistory(listing_id=listing.id, price=12000))
    db_session.commit()
    return vol, listing


def test_admin_removes_listing_and_blocks_product(client, db_session):
    vol, listing = _wrong_listing(db_session)
    body = client.get(f"/volume/{vol.id}").json()
    assert body["stores"][0]["id"] == listing.id

    res = client.delete(f"/volume/{vol.id}/listings/{listing.id}?reason=roman, manga değil")
    assert res.status_code == 200
    assert db_session.get(StoreListing, listing.id) is None
    assert db_session.scalar(select(PriceHistory)) is None
    ex = db_session.scalar(select(ListingExclusion))
    assert (ex.product_url, ex.volume_id, ex.reason) == (URL, vol.id, "roman, manga değil")


def test_excluded_product_is_never_imported_again(db_session, import_service):
    vol, listing = _wrong_listing(db_session)
    db_session.add(ListingExclusion(store_id=listing.store_id, product_url=URL, volume_id=vol.id))
    db_session.delete(listing)
    db_session.commit()

    r = make_result("bkm", "İtiraf", "120", isbn=None)
    r = r.model_copy(update={"store_id": "kitapsec", "store_name": "Kitapsec", "product_url": URL})
    assert import_service.import_result(r) == ImportAction.SKIPPED
    assert import_service.last_reason == "excluded"


def test_only_admins_can_remove(client, db_session):
    vol, listing = _wrong_listing(db_session)
    client.cookies.clear()
    assert client.delete(f"/volume/{vol.id}/listings/{listing.id}").status_code == 401
    assert client.delete(f"/volume/{vol.id + 999}/listings/{listing.id}").status_code in (401, 404)
