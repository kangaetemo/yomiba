"""Real store title shapes seen on BKM (2026-09-27) that the catalog-title
fallback must resolve — or keep rejecting — without guessing. Temp DB only."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import StoreListing
from app.services.import_service import ImportAction
from tests.test_import_service import make_result, seed_catalog_series

AKIL = "Akıl Çelen Kitaplar"  # what BKM sends; catalog says "Akılçelen"


@pytest.fixture
def rosario(db_session):
    s1 = seed_catalog_series(db_session, "Tılsımlı Kolye ve Vampir", "Akılçelen",
                             original="rosario vampire rosario to vampire", volumes=range(1, 11))
    s2 = seed_catalog_series(db_session, "Tılsımlı Kolye ve Vampir Sezon 2", "Akılçelen",
                             original="rosario vampire season 2", volumes=range(1, 15))
    db_session.commit()
    return s1, s2


def _target(db_session):
    v = db_session.scalar(select(StoreListing)).volume
    return v.series_id, v.volume_number


@pytest.mark.parametrize("title,season,number", [
    ("Rosario + Vampire - Tılsımlı Kolye ve Vampir 8", 1, 8),
    ("Rosario Vampire - Tılsımlı Kolye ve Vampir 10", 1, 10),
    ("Rosario + Vampire - Tılsımlı Kolye ve Vampir Sezon: 2 11", 2, 11),
    ("Rosario + Vampire - Tılsımlı Kolye ve Vampir - Sezon 2 Cilt 2", 2, 2),
    ("Rosario+Vampire - Tılsımlı Kolye ve Vampir Sezon 2 Cilt 14", 2, 14),
    ("Rosario ve Vampire Sezon 2 Cilt 7 - Tılsımlı Kolye ve Vampir Sezon 2 Cilt 7", 2, 7),
    ("Rosario & Vampire Sezon 2 Cilt 9- Tılsımlı Kolye ve Vampir Sezon 2 Cilt 9", 2, 9),
])
def test_original_title_before_dash(db_session, import_service, rosario, title, season, number):
    r = make_result("bkm", title, "100", publisher=AKIL)
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _target(db_session) == (rosario[season - 1].id, number)


def test_number_before_dash_must_agree(db_session, import_service, rosario):
    r = make_result("bkm", "Rosario Sezon 2 Cilt 3 - Tılsımlı Kolye ve Vampir Sezon 2 Cilt 7", "100",
                    publisher=AKIL)
    assert import_service.import_result(r) == ImportAction.SKIPPED


def test_dash_part_needs_same_publisher(db_session, import_service, rosario):
    r = make_result("bkm", "Arkadaşım Mumya - Tılsımlı Kolye ve Vampir 3", "100",
                    publisher="Epsilon Yayınevi")
    assert import_service.import_result(r) == ImportAction.SKIPPED


def test_missing_volume_is_not_forced(db_session, import_service, rosario):
    r = make_result("bkm", "Rosario + Vampire - Tılsımlı Kolye ve Vampir Cilt 13", "100", publisher=AKIL)
    assert import_service.import_result(r) == ImportAction.SKIPPED


@pytest.fixture
def ragnarok(db_session):
    main = seed_catalog_series(db_session, "Ragnarok Valkürleri", "Komik Şeyler", volumes=range(1, 9))
    spin = seed_catalog_series(db_session, "Ragnarok Valkürleri - Tuhaf Öykü - Lü Bu Fengxian",
                               "Komik Şeyler", volumes=(1, 2, 3))
    db_session.commit()
    return main, spin


@pytest.mark.parametrize("title,number", [
    ("Ragnarok Valkürleri – Tuhaf Öykü Cilt 3", 3),
    ("Ragnarok Valkürleri - Tuhaf Öykü Cilt 2", 2),
])
def test_store_title_without_catalog_subtitle(db_session, import_service, ragnarok, title, number):
    r = make_result("bkm", title, "100", publisher="Komikşeyler Yayıncılık")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _target(db_session) == (ragnarok[1].id, number)


def test_main_series_still_matches_directly(db_session, import_service, ragnarok):
    r = make_result("bkm", "Ragnarok Valkürleri Cilt 6", "100", publisher="Komikşeyler Yayıncılık")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _target(db_session) == (ragnarok[0].id, 6)


def test_subtitle_only_volume_without_number_skipped(db_session, import_service, ragnarok):
    r = make_result("bkm", "Ragnarok Valkürleri - Tuhaf Öykü - Lü Bu Fengxian - Uçan General", "100",
                    publisher="Komikşeyler Yayıncılık")
    assert import_service.import_result(r) == ImportAction.SKIPPED


def test_kamisama_kiss_without_subtitle(db_session, import_service):
    s = seed_catalog_series(db_session, "Kamisama Kiss -Tanrılık Görevine Başladım", "Komik Şeyler",
                            volumes=range(1, 10))
    db_session.commit()
    r = make_result("bkm", "Kamisama Kiss Cilt 07", "100", publisher="Komikşeyler Yayıncılık")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert _target(db_session) == (s.id, 7)


def test_head_rule_refuses_two_candidates(db_session, import_service):
    seed_catalog_series(db_session, "Deneme - Birinci Yol", "Komik Şeyler", volumes=(1, 2))
    seed_catalog_series(db_session, "Deneme - İkinci Yol", "Komik Şeyler", volumes=(1, 2))
    db_session.commit()
    r = make_result("bkm", "Deneme Cilt 2", "100", publisher="Komik Şeyler")
    assert import_service.import_result(r) == ImportAction.SKIPPED


def test_head_rule_needs_publisher(db_session, import_service):
    seed_catalog_series(db_session, "Deneme - Birinci Yol", "Komik Şeyler", volumes=(1, 2))
    db_session.commit()
    r = make_result("bkm", "Deneme Cilt 2", "100", publisher="Başka Yayınevi")
    assert import_service.import_result(r) == ImportAction.SKIPPED


def test_hyphenated_word_is_not_a_separator(db_session, import_service):
    seed_catalog_series(db_session, "Kun Hikayesi", "Komik Şeyler", volumes=(1, 2))
    db_session.commit()
    r = make_result("bkm", "Tamon-Kun Hikayesi 2", "100", publisher="Komik Şeyler")
    assert import_service.import_result(r) == ImportAction.SKIPPED
