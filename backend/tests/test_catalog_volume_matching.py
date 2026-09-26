"""Controlled fixtures, not a replay of Railway's unavailable 153 results."""
import pytest
from sqlalchemy import select, func

from app.models import Volume, StoreListing, PriceHistory
from app.normalization import parse_volume_title
from app.services.import_service import ImportAction, ImportService
from tests.helpers import RecordingScraper
from tests.test_import_service import seed_catalog_series, make_result


FORMATS = ["One Piece 1", "One Piece 1. Cilt", "One Piece Cilt 1",
           "One Piece Cilt: 1", "One Piece - 1", "One Piece 01",
           "One Piece Cilt 01", "One Piece Manga 1", "One Piece 61. Cilt", "One Piece 62"]


@pytest.mark.parametrize("title,number", list(zip(FORMATS, [1]*8 + [61, 62])))
def test_one_piece_formats(db_session, import_service, title, number):
    series = seed_catalog_series(db_session, "One Piece", "Gerekli Şeyler", volumes=range(1, 63))
    assert parse_volume_title(title).volume_number == number
    assert import_service.import_result(make_result("bkm", title, "100", publisher="Gerekli Şeyler")) == ImportAction.CREATED
    listing = db_session.scalar(select(StoreListing))
    assert listing.volume.series_id == series.id
    assert listing.volume.volume_number == number


@pytest.mark.parametrize("title", ["One Piece 2024", "One Piece ISBN 9786258237559",
    "One Piece 99.90 TL", "One Piece Edition 2", "978-605-360072-5", "One Piece Cilt 1 Cilt 2"])
def test_numeric_metadata_is_not_volume(title):
    assert parse_volume_title(title).volume_number is None


def test_elveda_eri_single_fallback_and_history(db_session, import_service):
    series = seed_catalog_series(db_session, "Elveda Eri", "Gerekli Şeyler")
    result = make_result("bkm", "Elveda Eri", "120", isbn="9786258237559", publisher="Gerekli Şeyler")
    assert import_service.import_result(result) == ImportAction.CREATED
    db_session.commit()
    assert import_service.import_result(result) == ImportAction.UPDATED
    db_session.commit()
    volume = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    assert volume.volume_number == 1 and volume.isbn == result.isbn
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 1
    assert db_session.scalar(select(func.count()).select_from(PriceHistory)) == 1


@pytest.mark.parametrize("title", ["One Piece", "One Piece Kutu Seti", "One Piece Bundle", "One Piece 63"])
def test_multivolume_unknown_and_box_rejected(db_session, import_service, title):
    seed_catalog_series(db_session, "One Piece", "Gerekli Şeyler", volumes=range(1, 63))
    assert import_service.import_result(make_result("bkm", title, "100")) == ImportAction.SKIPPED
    assert db_session.scalar(select(func.count()).select_from(Volume)) == 62


def test_isbn_priority_and_conflict(db_session, import_service):
    seed_catalog_series(db_session, "Elveda Eri", "Publisher A")
    first = make_result("bkm", "Elveda Eri", "100", isbn="9786258237559")
    import_service.import_result(first)
    db_session.commit()
    exact = make_result("dr", "Incorrect title 2", "120", isbn=first.isbn, publisher="Publisher B")
    assert import_service.import_result(exact) == ImportAction.CREATED
    conflict = make_result("amazon", "Elveda Eri", "90", isbn="9786051234567")
    assert import_service.import_result(conflict) == ImportAction.SKIPPED
    assert import_service.last_reason == "isbn_conflict"


def test_single_fallback_rejects_unknown_publisher_and_edition(db_session, import_service):
    seed_catalog_series(db_session, "Elveda Eri", "Publisher A")
    assert import_service.import_result(make_result("bkm", "Elveda Eri", "100", publisher="Publisher B")) == ImportAction.SKIPPED
    result = make_result("bkm", "Elveda Eri Hardcover Edition", "100").model_copy(update={"series_title": "Elveda Eri"})
    assert import_service.import_result(result) == ImportAction.SKIPPED


def test_synthetic_153_results_all_resolve_or_deduplicate(db_session):
    seed_catalog_series(db_session, "One Piece", "Gerekli Şeyler", volumes=range(1, 63))
    results = [make_result("bkm", f"One Piece Cilt: {i % 62 + 1:02d}", "100") for i in range(153)]
    report = ImportService(db_session, scrapers=[RecordingScraper("bkm", "BKM Kitap", results)]).run_import("One Piece")
    assert report.stores[0].results_found == 153
    assert report.total_created == 62
    assert report.stores[0].reasons == {"duplicate": 91}
    assert report.total_errors == 0
