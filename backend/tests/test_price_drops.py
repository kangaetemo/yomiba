"""Current selling-price opportunities, not retail-list-price discounts."""
from datetime import timedelta
from app.models import CatalogSeries, PriceHistory, Publisher, Series, Store, StoreListing, Volume
from app.utils import utcnow


def _seed(session, title="Manga", code="bkm", volume=None):
    store = Store(code=code, name=code.upper())
    session.add(store); session.flush()
    if volume is None:
        pub = Publisher(name=title, normalized_name=title.lower())
        session.add(pub); session.flush()
        series = Series(publisher_id=pub.id, title=title, normalized_title=title.lower(), slug=title.lower())
        session.add(series); session.flush()
        session.add(CatalogSeries(series_id=series.id, mangakol_slug=title.lower()))
        volume = Volume(series_id=series.id, volume_number=1)
        session.add(volume); session.flush()
    listing = StoreListing(volume_id=volume.id, store_id=store.id, product_url=f"https://{code}.example/1", price=18000)
    session.add(listing); session.commit()
    return listing


def _point(session, listing, price, hours, stock=None, product=None):
    session.add(PriceHistory(listing_id=listing.id, price=price, checked_at=utcnow() - timedelta(hours=hours),
                             in_stock=stock, product_url=product))
    listing.price = price
    session.commit()


def test_small_drop_is_visible_but_not_a_home_opportunity(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 14 * 24)
    _point(db_session, listing, 17000, 1)
    item = client.get("/price-drops").json()["drops"][0]
    assert (item["old_price"], item["new_price"], item["saving"], item["drop_pct"]) == (180, 170, 10, 5.6)
    assert item["reference_kind"] == "usual" and item["significant"] is False
    assert client.get("/price-drops?significant=true").json()["drops"] == []


def test_screenshot_offer_and_detail_use_same_reference(db_session, client):
    listing = _seed(db_session, "Fairy Tail")
    _point(db_session, listing, 18000, 14 * 24)
    _point(db_session, listing, 14400, 1)
    item = client.get("/price-drops?significant=true").json()["drops"][0]
    detail = client.get(f"/volume/{listing.volume_id}").json()["price_deal"]
    assert item["saving"] == detail["saving"] == 36
    assert item["drop_pct"] == detail["drop_pct"] == 20
    assert item["reference_kind"] == "usual"


def test_short_history_does_not_claim_a_normal_price(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 2)
    _point(db_session, listing, 14400, 1)
    item = client.get("/price-drops").json()["drops"][0]
    assert item["reference_kind"] == "previous"
    assert item["significant"] is False


def test_brief_price_increase_does_not_inflate_reference(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 20 * 24)
    _point(db_session, listing, 24000, 2)
    _point(db_session, listing, 18000, 1)
    assert client.get("/price-drops").json()["drops"] == []


def test_drop_after_brief_increase_uses_usual_selling_price(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 20 * 24)
    _point(db_session, listing, 24000, 2)
    _point(db_session, listing, 14400, 1)
    assert client.get("/price-drops").json()["drops"][0]["old_price"] == 180


def test_cheaper_competitor_prevents_a_false_opportunity(db_session, client):
    a = _seed(db_session)
    b = _seed(db_session, code="ks", volume=db_session.get(Volume, a.volume_id))
    _point(db_session, a, 20000, 14 * 24)
    _point(db_session, b, 17000, 14 * 24)
    _point(db_session, a, 18000, 1)
    assert client.get("/price-drops").json()["drops"] == []


def test_rebound_never_shows_expired_lower_price(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 14 * 24)
    _point(db_session, listing, 14400, 2)
    _point(db_session, listing, 19000, 1)
    assert client.get("/price-drops").json()["drops"] == []


def test_multiple_drops_only_show_current_price_once(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 14 * 24)
    _point(db_session, listing, 17000, 2)
    _point(db_session, listing, 14400, 1)
    items = client.get("/price-drops").json()["drops"]
    assert len(items) == 1 and items[0]["new_price"] == 144


def test_sold_out_stale_and_unreleased_are_not_offers(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 14 * 24)
    _point(db_session, listing, 14400, 1)
    listing.in_stock = False; db_session.commit()
    assert client.get("/price-drops").json()["drops"] == []
    listing.in_stock = True; listing.last_checked = utcnow() - timedelta(days=5); db_session.commit()
    assert client.get("/price-drops").json()["drops"] == []
    listing.last_checked = utcnow(); db_session.get(Volume, listing.volume_id).catalog_released = False; db_session.commit()
    assert client.get("/price-drops").json()["drops"] == []


def test_stock_and_product_evidence_do_not_fabricate_history(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 12, stock=False, product=listing.product_url)
    _point(db_session, listing, 14400, 1, stock=True, product=listing.product_url)
    assert client.get("/price-drops").json()["drops"] == []
    db_session.query(PriceHistory).delete()
    _point(db_session, listing, 24000, 12, product="https://old-product.example")
    _point(db_session, listing, 14400, 1, product=listing.product_url)
    assert client.get("/price-drops").json()["drops"] == []


def test_daily_fresh_observations_supply_weighted_coverage(db_session, client):
    listing = _seed(db_session)
    for day in range(14, 0, -1):
        _point(db_session, listing, 18000, day * 24, stock=True, product=listing.product_url)
    _point(db_session, listing, 14400, 1, stock=True, product=listing.product_url)
    item = client.get("/price-drops").json()["drops"][0]
    assert item["reference_kind"] == "usual" and item["significant"] is True


def test_expired_known_stock_does_not_claim_seven_days(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 18000, 14 * 24, stock=True, product=listing.product_url)
    _point(db_session, listing, 14400, 1, stock=True, product=listing.product_url)
    assert client.get("/price-drops").json()["drops"] == []


def test_window_sorting_and_pagination_apply_after_dedup(db_session, client):
    a = _seed(db_session, "A")
    b = _seed(db_session, "B", code="ks")
    for listing, value, hours in ((a, 17000, 2), (b, 14400, 1)):
        _point(db_session, listing, 18000, 14 * 24)
        _point(db_session, listing, value, hours)
    first = client.get("/price-drops?sort=saving&limit=1").json()
    second = client.get("/price-drops?sort=saving&limit=1&offset=1").json()
    assert first["total"] == 2 and first["drops"][0]["volume_id"] == b.volume_id
    assert second["drops"][0]["volume_id"] == a.volume_id
    assert client.get(f"/price-drops?volume_id={a.volume_id}").json()["total"] == 1
    assert client.get("/price-drops?sort=wrong").status_code == 422


def test_all_time_low_flag_looks_beyond_reference_window(db_session, client):
    listing = _seed(db_session)
    _point(db_session, listing, 9000, 45 * 24)
    _point(db_session, listing, 18000, 35 * 24)
    _point(db_session, listing, 14400, 1)
    assert client.get("/price-drops").json()["drops"][0]["lowest_ever"] is False
