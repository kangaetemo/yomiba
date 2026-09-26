"""Catalog write boundary and cross-run product identity regressions."""

from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from app.models import CatalogSeries, PriceHistory, Publisher, Series, StoreListing, Volume
from app.services.import_service import ImportAction, ImportService
from app.utils import utcnow
from tests.helpers import RecordingScraper
from tests.test_import_service import make_result, seed_catalog_series


@pytest.mark.parametrize("title", ["Berserk", "Mavi Kutu"])
@pytest.mark.parametrize("holder_number", [-1, 1])
@pytest.mark.parametrize("batch", [False, True])
def test_non_catalog_isbn_never_falls_back(db_session, title, holder_number, batch):
    catalog = seed_catalog_series(db_session, title, "Yayinci", volumes=(1,))
    outside = seed_catalog_series(db_session, "Outside", "Other", volumes=(holder_number,))
    outside.volumes[0].isbn = "9786258237559"
    db_session.execute(delete(CatalogSeries).where(CatalogSeries.series_id == outside.id))
    db_session.commit()
    counts = lambda: tuple(db_session.scalar(select(func.count()).select_from(m))
                           for m in (Series, Publisher, Volume))
    before = counts()
    result = make_result("bkm", f"{title} 1", "100", isbn="9786258237559", publisher="Yayinci")
    service = ImportService(db_session, scrapers=[RecordingScraper("bkm", "BKM", [result])])
    if batch:
        report = service.run_import(title)
        assert report.stores[0].reasons == {"non_catalog_volume": 1}
        assert report.total_created == report.total_updated == 0
    else:
        assert service.import_result(result) == ImportAction.SKIPPED
        assert service.last_reason == "non_catalog_volume"
        db_session.commit()
    assert counts() == before
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == 0
    assert db_session.scalar(select(func.count()).select_from(PriceHistory)) == 0
    assert catalog.volumes[0].isbn is None
    assert outside.volumes[0].isbn == "9786258237559"


def _run(session, *results):
    return ImportService(session, scrapers=[RecordingScraper("bkm", "BKM", list(results))]).run_import("Berserk")


def _history(session):
    return list(session.scalars(select(PriceHistory.price).order_by(PriceHistory.id)))


def _products(session, current_stock=True, candidate_stock=True, candidate_price="90"):
    seed_catalog_series(session, "Berserk", "Yayinci", volumes=(1,))
    a = make_result("bkm", "Berserk 1", "100", publisher="Yayinci", in_stock=current_stock)
    b = make_result("bkm", "Berserk Cilt 1", candidate_price, publisher="Yayinci", in_stock=candidate_stock)
    _run(session, a)
    return a, b, session.scalar(select(StoreListing))


@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize("current_stock", [False, True])
def test_unavailable_other_product_never_switches(db_session, stale, current_stock):
    a, b, listing = _products(db_session, current_stock=current_stock, candidate_stock=False)
    if stale:
        listing.last_checked = utcnow() - timedelta(hours=49)
        db_session.commit()
    for _ in range(3):
        report = _run(db_session, b)
        assert report.stores[0].reasons == {"other_product": 1}
        assert listing.product_url == a.product_url
        assert listing.in_stock == current_stock
        _run(db_session, a)
    assert listing.price == 10000
    assert _history(db_session) == [10000]


@pytest.mark.parametrize("current_stock,candidate_price,stale", [
    (False, "110", False),  # restocked alternative
    (True, "90", False),   # cheaper available alternative
    (True, "110", True),   # stale identity, available alternative
])
def test_safe_switch_has_no_synthetic_price_change(db_session, current_stock, candidate_price, stale):
    a, b, listing = _products(db_session, current_stock=current_stock, candidate_price=candidate_price)
    if stale:
        listing.last_checked = utcnow() - timedelta(hours=49)
        db_session.commit()
    for _ in range(3):
        _run(db_session, b)
    assert listing.product_url == b.product_url
    assert listing.price == int(candidate_price) * 100
    assert listing.in_stock
    assert _history(db_session) == [10000]  # switch itself is not a price drop
    if candidate_price == "90":
        for _ in range(3):
            _run(db_session, a)
            _run(db_session, b)
        assert listing.product_url == b.product_url
        assert _history(db_session) == [10000]
    changed = make_result("bkm", "Berserk Cilt 1", "80", publisher="Yayinci")
    for _ in range(3):
        _run(db_session, changed)
    assert _history(db_session) == [10000, 8000]


def test_same_product_real_price_change_is_idempotent(db_session):
    a, _, listing = _products(db_session)
    cheaper = make_result("bkm", "Berserk 1", "90", publisher="Yayinci")
    for result in (a, cheaper, cheaper):
        _run(db_session, result)
    assert listing.product_url == a.product_url
    assert _history(db_session) == [10000, 9000]


def test_mixed_batch_does_not_hide_same_product_price_update(db_session):
    _, unavailable, listing = _products(db_session, candidate_stock=False, candidate_price="80")
    cheaper = make_result("bkm", "Berserk 1", "90", publisher="Yayinci")
    for results in ((unavailable, cheaper), (cheaper, unavailable)):
        _run(db_session, *results)
    assert listing.product_url == cheaper.product_url
    assert listing.in_stock and listing.price == 9000
    assert _history(db_session) == [10000, 9000]
