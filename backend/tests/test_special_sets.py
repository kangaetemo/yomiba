"""Special sets: box sets an admin links to catalog series by product URL
(Komik Şeyler's JoJo Part 1 + Part 2 Bunkobon Kutulu Set)."""
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.models import SpecialSet
from app.scrapers.base import ProductInfo
from app.scrapers.komikseyler import KomikseylerScraper
from app.services import special_sets
from tests.helpers import mock_client
from tests.test_import_service import seed_catalog_series

URL = "https://komikseyler.com.tr/urun/jojo-part-1-part-2-bunkobon-sert-kapakli-kutulu-set/"


class FakeReader:
    """Stands in for the store scraper's product-page read."""

    def __init__(self, info):
        self.info = info
        self.calls = 0

    def read_product(self, url):
        self.calls += 1
        if isinstance(self.info, Exception):
            raise self.info
        return self.info

    def close(self):
        pass


@pytest.fixture()
def jojo(db_session):
    one = seed_catalog_series(db_session, "JoJo's Bizarre Adventure Part 1: Phantom Blood", "Komik Şeyler")
    two = seed_catalog_series(db_session, "JoJo's Bizarre Adventure Part 2: Battle Tendency", "Komik Şeyler")
    db_session.commit()
    return one, two


@pytest.fixture()
def reader(monkeypatch):
    fake = FakeReader(ProductInfo(title="JoJo Part 1 + Part 2 Bunkobon Sert Kapaklı Kutulu Set",
                                  in_stock=True, price=Decimal("3450.00"), image_url="https://img/jojo.jpg"))
    monkeypatch.setattr(KomikseylerScraper, "read_product", lambda self, url: fake.read_product(url))
    return fake


def test_admin_adds_set_and_both_series_show_it(client, db_session, jojo, reader):
    one, two = jojo
    res = client.post("/admin/special-sets", json={
        "product_url": URL, "series_ids": [one.id, two.id], "preorder": True})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["title"] == "JoJo Part 1 + Part 2 Bunkobon Sert Kapaklı Kutulu Set"
    assert body["store"] == "Komikşeyler" and body["price"] == 3450.0 and body["preorder"] is True

    for series, other in ((one, two), (two, one)):
        cards = client.get(f"/series/{series.id}").json()["special_sets"]
        assert len(cards) == 1
        card = cards[0]
        assert card["price"] == 3450.0 and card["in_stock"] is True and card["preorder"] is True
        assert card["product_url"] == URL and card["image_url"] == "https://img/jojo.jpg"
        assert [a["title"] for a in card["also"]] == [other.title]


def test_rejects_unknown_store_duplicates_and_non_catalog_series(client, jojo, reader):
    one, _ = jojo
    assert client.post("/admin/special-sets", json={
        "product_url": "https://example.com/urun/x", "series_ids": [one.id]}).status_code == 422
    assert client.post("/admin/special-sets", json={"product_url": URL, "series_ids": []}).status_code == 422
    assert client.post("/admin/special-sets", json={"product_url": URL, "series_ids": [999]}).status_code == 422
    assert client.post("/admin/special-sets", json={"product_url": URL, "series_ids": [one.id]}).status_code == 201
    assert client.post("/admin/special-sets", json={"product_url": URL, "series_ids": [one.id]}).status_code == 422


def test_hidden_or_unread_sets_stay_off_the_series_page(client, db_session, jojo, reader):
    one, _ = jojo
    created = client.post("/admin/special-sets", json={"product_url": URL, "series_ids": [one.id]}).json()
    client.patch(f"/admin/special-sets/{created['id']}", json={"active": False})
    assert client.get(f"/series/{one.id}").json()["special_sets"] == []
    reader.info = None  # product page unreadable
    other = URL.replace("kutulu-set", "kutulu-set-2")
    client.post("/admin/special-sets", json={"product_url": other, "series_ids": [one.id]})
    row = db_session.scalar(select(SpecialSet).where(SpecialSet.product_url == other))
    assert row.check_error == "ürün sayfası okunamadı"
    assert client.get(f"/series/{one.id}").json()["special_sets"] == []


def test_price_refresh_of_a_linked_series_updates_the_set(db_session, jojo, monkeypatch):
    one, two = jojo
    first = FakeReader(ProductInfo(title="Set", in_stock=True, price=Decimal("3450"), image_url=None))
    special = special_sets.create(db_session, URL, [one.id, two.id], scraper=first)
    db_session.commit()
    later = FakeReader(ProductInfo(title="Set", in_stock=False, price=Decimal("2999.90")))
    monkeypatch.setattr(KomikseylerScraper, "read_product", lambda self, url: later.read_product(url))
    assert special_sets.refresh_for_series(db_session, {two.id}) == 1
    assert special.price == 299990 and special.in_stock is False and later.calls == 1
    broken = FakeReader(RuntimeError("boom"))
    monkeypatch.setattr(KomikseylerScraper, "read_product", lambda self, url: broken.read_product(url))
    assert special_sets.refresh_for_series(db_session, {one.id}) == 0
    assert special.price == 299990 and special.check_error == "RuntimeError: boom"


def test_komikseyler_reads_a_set_by_its_slug():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["slug"] = request.url.params.get("slug")
        return httpx.Response(200, json=[{
            "id": 1, "name": "JoJo Part 1 &#038; Part 2 Kutulu Set", "is_in_stock": True,
            "prices": {"price": "345000", "currency_code": "TRY"},
            "images": [{"src": "https://img/set.jpg"}],
        }])

    info = KomikseylerScraper(client=mock_client(handler)).read_product(URL)
    assert seen["slug"] == "jojo-part-1-part-2-bunkobon-sert-kapakli-kutulu-set"
    assert info == ProductInfo(title="JoJo Part 1 & Part 2 Kutulu Set", in_stock=True,
                               price=Decimal("3450"), image_url="https://img/set.jpg")
