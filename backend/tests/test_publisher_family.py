"""Publisher spelling variants ("Gerekli Şeyler" vs "Gerekli Şeyler
Yayıncılık") must not starve catalog series, without merging distinct
publishers or guessing between editions. Temp DB only."""
from __future__ import annotations

import logging

import pytest
from sqlalchemy import select

from app.models import Publisher, PublisherAlias, StoreListing
from app.normalization import normalize_publisher, publisher_family_key
from app.services.import_service import ImportAction, ImportService
from tests.helpers import RecordingScraper
from tests.test_import_service import make_result, seed_catalog_series


@pytest.mark.parametrize("a,b", [
    ("Gerekli Şeyler", "Gerekli Şeyler Yayıncılık"),
    ("Kurukafa", "Kurukafa Yayınevi"),
    ("Komik Şeyler", "Komikşeyler Yayıncılık"),
    ("Kara Karga Yayınları", "Karakarga"),
    ("Presstij", "Presstij Kitap"),
    ("Akıl Çelen Kitaplar", "Akılçelen"),
])
def test_family_key_same_publisher(a, b):
    assert publisher_family_key(a) == publisher_family_key(b) != ""


@pytest.mark.parametrize("a,b", [
    ("Timaş Çocuk", "Timaş Yayınları"),
    ("İthaki Çocuk Yayınları", "İthaki Yayınları"),
    ("Kayıp Kıta", "Kayıp"),
])
def test_family_key_keeps_distinct_publishers_apart(a, b):
    assert publisher_family_key(a) != publisher_family_key(b)


def test_family_key_never_empty_match():
    assert publisher_family_key("Yayınları") == ""
    assert publisher_family_key(None) == ""


def _listing_volume(db_session):
    listing = db_session.scalar(select(StoreListing))
    return listing.volume if listing else None


def test_catalog_short_name_store_long_name_one_piece(db_session, import_service):
    """Live shape: catalog publisher "Gerekli Şeyler", BKM sends
    "Gerekli Şeyler Yayıncılık" -> was publisher_conflict for every volume."""
    s = seed_catalog_series(db_session, "One Piece", "Gerekli Şeyler", volumes=range(1, 63))
    r = make_result("bkm", "One Piece 5", "150", publisher="Gerekli Şeyler Yayıncılık")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    v = _listing_volume(db_session)
    assert (v.series_id, v.volume_number) == (s.id, 5)


def test_catalog_long_name_store_short_name_without_alias(db_session, import_service):
    s = seed_catalog_series(db_session, "Berserk", "Gerekli Şeyler Yayıncılık", volumes=(1, 2, 3))
    assert db_session.scalar(select(PublisherAlias)) is None
    r = make_result("dr", "Berserk 3", "150", publisher="Gerekli Şeyler")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _listing_volume(db_session).series_id == s.id


def test_distinct_publisher_family_still_conflicts(db_session, import_service):
    seed_catalog_series(db_session, "Deneme Serisi", "Timaş Çocuk", volumes=(1,))
    r = make_result("bkm", "Deneme Serisi 1", "100", publisher="Timaş Yayınları")
    assert import_service.import_result(r) == ImportAction.SKIPPED
    assert import_service.last_reason == "publisher_conflict"


def test_two_editions_same_family_is_not_guessed(db_session, import_service):
    seed_catalog_series(db_session, "Berserk", "Arkadaş Yayınevi", volumes=(1,))
    seed_catalog_series(db_session, "Berserk", "Arkadaş Yayınları", volumes=(1,))
    r = make_result("bkm", "Berserk 1", "100", publisher="Arkadaş")
    assert import_service.import_result(r) == ImportAction.SKIPPED
    assert db_session.scalar(select(StoreListing)) is None


def test_exact_publisher_edition_wins_over_family(db_session, import_service):
    exact = seed_catalog_series(db_session, "Berserk", "Arkadaş Yayınları", volumes=(1,))
    seed_catalog_series(db_session, "Berserk", "Arkadaş Yayınevi", volumes=(1,))
    r = make_result("bkm", "Berserk 1", "100", publisher="Arkadaş Yayınları")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _listing_volume(db_session).series_id == exact.id


def test_prefix_fallback_accepts_family_publisher(db_session, import_service):
    """Kaiju-style titles go through the catalog-title prefix fallback,
    which must use the same publisher-family tolerance."""
    s = seed_catalog_series(db_session, "Kaiju No: 8 - 8 No'lu Canavar", "Gerekli Şeyler",
                            volumes=range(1, 9))
    r = make_result("bkm", "Kaiju No: 8 - 8 No'lu Canavar 3", "100",
                    publisher="Gerekli Şeyler Yayıncılık")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    v = _listing_volume(db_session)
    assert (v.series_id, v.volume_number) == (s.id, 3)


def test_wrong_alias_does_not_block_family_match(db_session, import_service):
    """An id-seeded alias pointing at an unrelated publisher (Railway shape
    before migration 0006) must not starve the real edition."""
    other = Publisher(name="Başka Yayınevi", normalized_name=normalize_publisher("Başka Yayınevi"))
    db_session.add(other)
    db_session.flush()
    db_session.add(PublisherAlias(normalized_alias="komik seyler", publisher_id=other.id))
    s = seed_catalog_series(db_session, "Deneme", "Komikşeyler Yayıncılık", volumes=(1, 2))
    db_session.commit()
    r = make_result("bkm", "Deneme 2", "100", publisher="Komik Şeyler")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _listing_volume(db_session).series_id == s.id


def test_unknown_publisher_family_still_rejected(db_session, import_service):
    seed_catalog_series(db_session, "One Piece", "Gerekli Şeyler", volumes=(1,))
    r = make_result("bkm", "One Piece 1", "100", publisher="Korsan Yayınları")
    assert import_service.import_result(r) == ImportAction.SKIPPED
    assert import_service.last_reason == "publisher_conflict"


def test_summary_logs_conflicting_publishers(db_session, caplog):
    seed_catalog_series(db_session, "One Piece", "Gerekli Şeyler", volumes=(1, 2))
    results = [make_result("bkm", f"One Piece {n}", "100", publisher="Korsan Yayınları")
               for n in (1, 2)]
    with caplog.at_level(logging.INFO, logger="yomiba.import"):
        ImportService(db_session, scrapers=[RecordingScraper("bkm", "BKM Kitap", results)]).run_import("One Piece")
    line = next(r.getMessage() for r in caplog.records if "publisher conflicts" in r.getMessage())
    assert "Korsan Yayınları" in line and "2" in line
