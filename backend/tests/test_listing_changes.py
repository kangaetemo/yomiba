"""Price-refresh change log: imports record which volume changed at which
store (new listing, price, stock, product, removal), and the admin view
groups them by series and volume."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models import CatalogSeries, ListingChange, Publisher, Series, Store, StoreListing, Volume
from app.normalization import parse_volume_title
from app.normalization.text import normalize_publisher, normalize_text
from app.scrapers import SearchResult
from app.services import listing_changes
from app.services.import_service import ImportService
from app.utils import utcnow
from tests.helpers import RecordingScraper

STORES = {"bkm": "BKM Kitap", "kitapsec": "Kitapseç"}


def _seed(db_session, title="Berserk", numbers=(1, 2)) -> list[Volume]:
    publisher = Publisher(name="Gerekli Şeyler", normalized_name=normalize_publisher("Gerekli Şeyler"))
    db_session.add(publisher)
    db_session.flush()
    slug = title.lower().replace(" ", "-")
    series = Series(publisher_id=publisher.id, title=title, slug=slug, normalized_title=normalize_text(title))
    db_session.add(series)
    db_session.flush()
    db_session.add(CatalogSeries(series_id=series.id, mangakol_slug=slug))
    volumes = [Volume(series_id=series.id, volume_number=n) for n in numbers]
    db_session.add_all(volumes)
    for code, name in STORES.items():
        if db_session.scalar(select(Store).where(Store.code == code)) is None:
            db_session.add(Store(code=code, name=name))
    db_session.commit()
    return volumes


def _result(title, *, price, store="bkm", in_stock=True, url=None) -> SearchResult:
    parsed = parse_volume_title(title)
    return SearchResult(
        store_id=store, store_name=STORES[store], title=title,
        product_url=url or f"https://{store}.example/{title.replace(' ', '-').lower()}",
        series_title=parsed.base_title or None, volume_number=parsed.volume_number,
        price=Decimal(price) if price is not None else None, currency="TRY", in_stock=in_stock,
    )


def _run(db_session, results, store="bkm", gone=()):
    scraper = RecordingScraper(store_id=store, store_name=STORES[store], results=results)
    if gone:
        original = scraper.search

        def search(query):
            found = original(query)
            scraper.gone_urls = set(gone)
            return found
        scraper.search = search
    return ImportService(db_session, scrapers=[scraper]).run_import("berserk")


def _changes(db_session):
    return db_session.scalars(select(ListingChange).order_by(ListingChange.id)).all()


def test_new_listings_mark_the_first_store_of_a_volume(db_session):
    _seed(db_session)
    _run(db_session, [_result("Berserk 1", price="150")])
    _run(db_session, [_result("Berserk 1", price="160", store="kitapsec")], store="kitapsec")
    first, second = _changes(db_session)
    assert (first.kind, first.note, first.new_price, first.new_in_stock) == ("new", "first", 15000, True)
    assert (second.kind, second.note) == ("new", None)


def test_unchanged_recheck_writes_nothing_and_changes_are_recorded(db_session):
    _seed(db_session)
    _run(db_session, [_result("Berserk 1", price="150")])
    _run(db_session, [_result("Berserk 1", price="150")])
    assert len(_changes(db_session)) == 1

    _run(db_session, [_result("Berserk 1", price="135", in_stock=False)])
    change = _changes(db_session)[-1]
    assert change.kind == "update"
    assert (change.old_price, change.new_price) == (15000, 13500)
    assert (change.old_in_stock, change.new_in_stock) == (True, False)


def test_store_removed_product_is_a_stock_change(db_session):
    _seed(db_session)
    _run(db_session, [_result("Berserk 1", price="150")])
    url = db_session.scalar(select(StoreListing.product_url))
    _run(db_session, [], gone=[url])
    change = _changes(db_session)[-1]
    assert (change.kind, change.note, change.old_in_stock, change.new_in_stock) == ("update", "gone", True, False)


def test_admin_report_groups_series_and_volumes_and_filters(db_session):
    _seed(db_session)
    _run(db_session, [_result("Berserk 1", price="150"), _result("Berserk 2", price="150")])
    _run(db_session, [_result("Berserk 1", price="140"), _result("Berserk 2", price="150")])

    report = listing_changes.admin_report(db_session, utcnow() - timedelta(hours=1))
    assert report["counts"]["new"] == 2 and report["counts"]["first"] == 2
    assert report["counts"]["price"] == 1 and report["counts"]["stock"] == 0
    (serie,) = report["series"]
    assert serie["title"] == "Berserk" and serie["first_listings"] == 2
    assert [v["number"] for v in serie["volumes"]] == [2, 1]
    one = serie["volumes"][1]
    assert one["path"] == "/series/berserk/cilt-1"
    assert [c["kind"] for c in one["changes"]] == ["update", "new"]
    assert (one["changes"][0]["old_price"], one["changes"][0]["new_price"]) == (150.0, 140.0)

    priced = listing_changes.admin_report(db_session, utcnow() - timedelta(hours=1), kind="price")
    assert priced["shown"] == 1
    assert [v["number"] for v in priced["series"][0]["volumes"]] == [1]
    assert listing_changes.admin_report(db_session, utcnow() - timedelta(hours=1), store="kitapsec")["series"] == []


def test_prune_drops_rows_past_retention(db_session):
    (volume, _) = _seed(db_session)
    store = db_session.scalar(select(Store).where(Store.code == "bkm"))
    db_session.add_all([
        ListingChange(created_at=utcnow() - timedelta(days=40), volume_id=volume.id, store_id=store.id, kind="new"),
        ListingChange(created_at=utcnow(), volume_id=volume.id, store_id=store.id, kind="new"),
    ])
    db_session.commit()
    assert listing_changes.prune(db_session) == 1
    assert len(_changes(db_session)) == 1


def test_changes_endpoint(client, db_session):
    _seed(db_session)
    _run(db_session, [_result("Berserk 1", price="150")])
    body = client.get("/import/changes").json()
    assert body["window"] == "24h"  # no finished cycle since start
    assert body["series"][0]["volumes"][0]["changes"][0]["store"] == "BKM Kitap"
    assert client.get("/import/changes?window=7d&kind=removed").json()["series"] == []
