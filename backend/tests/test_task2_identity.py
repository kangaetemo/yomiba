"""Kimlik regresyon testleri — Görev 2 veri temizliğinin SONRASı durumu.

2026-09-14 hibrit-merge temizliği (docs/reports/task2-dry-run.md, onaylı)
gerçek yomiba.db üzerinde uygulandı. Bu testler, temizlenmiş gerçek DB'nin
kopiyası üzerinde kimlik değişmezliklerini (invariant'ları) korur:

* her iş tek bir seri altında (hibrit seri satırları yok),
* catalog slug'ları veri serilerine işaret ediyor,
* liste/price-history kaybı yok,
* dokunulmaması gereken seriler (roman/İngilizce/ayrı kitap) hâlâ ayrı.

DB 2.5 MB: session başında tmp'ye kopyalanır, testler salt-okur çalışır.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

REAL_DB = Path(__file__).resolve().parent.parent / "yomiba.db"


@pytest.fixture(scope="module")
def db() -> sqlite3.Connection:
    assert REAL_DB.exists(), "gerçek yomiba.db bulunamadı"
    tmp = Path(__file__).resolve().parent / "fixtures" / "_task2_identity_copy.db"
    shutil.copyfile(REAL_DB, tmp)
    con = sqlite3.connect(tmp)
    con.row_factory = sqlite3.Row
    yield con
    con.close()
    tmp.unlink(missing_ok=True)


def series_ids(con: sqlite3.Connection, names: list[int]) -> set[int]:
    ph = ",".join("?" * len(names))
    return {r[0] for r in con.execute(
        f"SELECT id FROM series WHERE id IN ({ph})", names
    )}


def missing(con: sqlite3.Connection, ids: list[int]) -> None:
    assert not series_ids(con, ids), f"silinecek seriler hâlâ var: {ids}"


def identity_gone(con: sqlite3.Connection, norm_title: str, norm_publisher: str) -> None:
    """A deleted series' IDENTITY (normalized title + normalized publisher)
    must never reappear.

    Rowid-based ``missing()`` is NOT safe for tombstones: the series table
    has no AUTOINCREMENT, so the import engine reuses deleted rowids for
    unrelated new series (e.g. after the 2026-09-14 warmup, rowids 2389 and
    2357 hold the brand-new "Sunya" and "Ojeni" series).
    """
    row = con.execute(
        """SELECT s.id FROM series s
           JOIN publishers p ON p.id = s.publisher_id
           WHERE s.normalized_title = ? AND p.normalized_name = ?""",
        (norm_title, norm_publisher),
    ).fetchone()
    assert row is None, (
        f"silinecek kimlik geri geldi: {norm_title!r} + {norm_publisher!r} "
        f"(seri {row[0]})"
    )


# ---------------- Jujutsu Kaisen ----------------

def test_jjk_single_series_with_all_volumes(db):
    # Import sonraki ciltler EKELEYEBİLİR (örn. vol 8) — invariant: birleşen
    # 18 cilt hep seri 4'te olmalı, hibrit seriler bir daha var olmamalı.
    vols = {r[0] for r in db.execute(
        "SELECT volume_number FROM volumes WHERE series_id=4")}
    assert vols >= {0, 1, 2, 3, 4, 5, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19}, vols
    missing(db, [5, 14, 15, 90])


def test_jjk_merged_volume_isbns(db):
    got = {
        r[0]: r[1]
        for r in db.execute(
            "SELECT volume_number, isbn FROM volumes"
            " WHERE series_id=4 AND volume_number IN (0, 1, 9)"
        )
    }
    assert got == {0: "9786257590303", 1: "9786257590341", 9: "9786258237979"}


def test_jjk_merged_listing_survived(db):
    # vol 9'un BKM listing'i (eski seri 5) hâlâ seri 4'ün vol 9'unda
    n = db.execute(
        "SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
        " WHERE v.series_id=4 AND v.volume_number=9 AND l.store_id=2"
    ).fetchone()[0]
    assert n == 1


def test_jjk_catalog_slug_points_to_data_series(db):
    row = db.execute(
        "SELECT series_id FROM catalog_series WHERE mangakol_slug='jujutsu-kaisen'"
    ).fetchone()
    assert row is not None and row[0] == 4


# ---------------- Naruto ----------------

def test_naruto_vol28_29_in_main_series_with_isbns(db):
    got = {
        r[0]: r[1]
        for r in db.execute(
            "SELECT volume_number, isbn FROM volumes"
            " WHERE series_id=6 AND volume_number IN (28, 29)"
        )
    }
    assert got == {28: "9786059141574", 29: "9786059141796"}
    # birleşen 3 mağazanın listing'i (BKM, Kitapsepeti, Kitapsec) hep olmalı
    for vnum in (28, 29):
        vid = db.execute(
            "SELECT id FROM volumes WHERE series_id=6 AND volume_number=?", (vnum,)
        ).fetchone()[0]
        stores = {
            r[0] for r in db.execute(
                "SELECT store_id FROM store_listings WHERE volume_id=?", (vid,)
            )
        }
        assert stores >= {2, 4, 8}, f"Naruto vol {vnum} stores {stores}"
    missing(db, [19, 20])


def test_naruto_felsefesi_is_a_separate_book(db):
    # "Naruto Felsefesi" (Teras Kitap) Naruto mangası DEĞİLDİ — kitap olarak
    # ayrı bir seri idi. Görev 4 ("katalogda kal") kapsamı gereği manga
    # olmayan kitap 21 silindi; Naruto mangası (971) ayrı durmaya devam ediyor.
    missing(db, [21])
    row = db.execute(
        "SELECT title FROM series WHERE id=6"
    ).fetchone()
    assert row is not None and row[0] == "Naruto"


# ---------------- Kara Meşale ----------------

def test_kara_mesale_single_series(db):
    row = db.execute("SELECT title FROM series WHERE id=2145").fetchone()
    assert row[0] == "Kara Meşale"
    slug = db.execute(
        "SELECT series_id FROM catalog_series WHERE mangakol_slug='black-torch'"
    ).fetchone()
    assert slug is not None and slug[0] == 2145
    missing(db, [343])
    # vol 1'in BKM listing'i korundu
    n = db.execute(
        "SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
        " WHERE v.series_id=2145 AND v.volume_number=1 AND l.store_id=2"
    ).fetchone()[0]
    assert n == 1


# ---------------- Vinland Saga (TR) ----------------

def test_vinland_single_tr_series(db):
    row = db.execute("SELECT title FROM series WHERE id=2157").fetchone()
    assert row[0] == "Vinland Destanı"
    slug = db.execute(
        "SELECT series_id FROM catalog_series WHERE mangakol_slug='vinland-saga'"
    ).fetchone()
    assert slug is not None and slug[0] == 2157
    missing(db, [106])
    n = db.execute(
        "SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
        " WHERE v.series_id=2157"
    ).fetchone()[0]
    assert n >= 55, n  # 55 birleşen listing kaybolamaz (import ilavesi yapabilir)
    # Kodansha (İngilizce) baskılar mangakol kataloğunda yok — görev 4
    # kapsamı ("sadece katalogda bağlı seriler") gereği silindiler.
    missing(db, [2158, 2159])


# ---------------- Orange (TR) ----------------

def test_orange_single_tr_series(db):
    slug = db.execute(
        "SELECT series_id FROM catalog_series WHERE mangakol_slug='orange'"
    ).fetchone()
    assert slug is not None and slug[0] == 1851
    missing(db, [150, 1874, 1886])

    v1 = db.execute(
        "SELECT id, isbn FROM volumes WHERE series_id=1851 AND volume_number=1"
    ).fetchone()
    assert v1[1] == "9786052115442"  # 1886'dan backfill
    stores = {
        r[0] for r in db.execute(
            "SELECT store_id FROM store_listings WHERE volume_id=?", (v1[0],)
        )
    }
    # Kitapbulan + Gerekli Şeyler (1874'ten) + Komikşeyler (1886'dan)
    assert stores >= {5, 6, 9}, stores

    v4 = db.execute(
        "SELECT id FROM volumes WHERE series_id=1851 AND volume_number=4"
    ).fetchone()
    stores4 = {
        r[0] for r in db.execute(
            "SELECT store_id FROM store_listings WHERE volume_id=?", (v4[0],)
        )
    }
    assert stores4 >= {2, 4, 5, 8, 9, 6}, stores4  # 5 eski + Gerekli Şeyler (1874'ten)

    total = db.execute(
        "SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
        " WHERE v.series_id=1851"
    ).fetchone()[0]
    assert total >= 37, total


def test_orange_related_but_distinct_series_preserved(db):
    # roman + İngilizce baskılar + spin-off ayrı serilerdi; hiçbiri mangakol
    # kataloğunda değil → görev 4 kapsamıyla silindiler.
    missing(db, [1853, 1875, 1879])


# ---------------- import-doğumlu duplikatlar (takip temizliği) ----------------

def test_import_born_duplicates_merged(db):
    # Doğrulama arama-tetikli import dalgası (2026-09-14) yayıncı-yazım
    # varyantı yüzünden 3 duplikat açmıştı; hepsi birleştirildi.
    # Kimlik (başlık + yayıncı) bazlı kontrol: rowid'ler yeniden kullanılabilir
    # (2026-09-14 warmup'ı 2389/2357 rowid'lerine "Sunya"/"Ojeni" serilerini
    # yazdı — id tabanlı kontrol yanlış pozitif verirdi).
    identity_gone(db, "jujutsu kaisen", "gerekli seyler")
    identity_gone(db, "orange", "komik seyler")
    identity_gone(db, "kara kahya", "gerekli seyler")


def test_jjk_gerekliseyler_listings_in_series4(db):
    for vn in (0, 1, 2, 4, 5, 6, 7, 8):
        vid = db.execute(
            "SELECT id FROM volumes WHERE series_id=4 AND volume_number=?", (vn,)
        ).fetchone()[0]
        stores = {
            r[0] for r in db.execute(
                "SELECT store_id FROM store_listings WHERE volume_id=?", (vid,)
            )
        }
        assert 6 in stores, f"seri 4 vol {vn} store 6 eksik: {stores}"


def test_orange_merged_history_preserved(db):
    # 2389'dan taşınan price-history satırları 1851'in store-6
    # listing'lerinde (her ciltte orijinal + en az 1 taşınan)
    for vn in (1, 4):
        lid = db.execute(
            "SELECT l.id FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
            " WHERE v.series_id=1851 AND v.volume_number=? AND l.store_id=6", (vn,)
        ).fetchone()[0]
        n = db.execute(
            "SELECT COUNT(*) FROM price_history WHERE listing_id=?", (lid,)
        ).fetchone()[0]
        assert n >= 2, f"orange vol {vn} history {n}"


def test_kara_kahya_vol20_24_have_listings(db):
    for vn in (20, 21, 22, 23, 24):
        assert db.execute(
            "SELECT 1 FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
            " WHERE v.series_id=151 AND v.volume_number=? AND l.store_id=6", (vn,)
        ).fetchone(), f"151 vol {vn} store 6 eksik"


# ---------------- Paradise Kiss ----------------

def test_paradise_kiss_publisher_attributed(db):
    # Görev 4: 1593 (katalog-dışı) silindi. Mangakol sync'i Paradise Kiss'ı
    # yeniden açarsa yayıncısı yine Komikşeyler Yayıncılık olmalı.
    missing(db, [1593])
    rows = db.execute(
        "SELECT p.name FROM series s JOIN publishers p ON p.id=s.publisher_id"
        " WHERE s.normalized_title = 'paradise kiss'"
    ).fetchall()
    for row in rows:
        assert row[0] == "Komikşeyler Yayıncılık", row


# ---------------- global bütünlük ----------------

def test_no_orphan_listings_or_fk_violations(db):
    orphans = db.execute(
        "SELECT COUNT(*) FROM store_listings l LEFT JOIN volumes v ON v.id=l.volume_id"
        " WHERE v.id IS NULL"
    ).fetchone()[0]
    assert orphans == 0
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_no_duplicate_series_volume_pairs(db):
    dups = db.execute(
        "SELECT series_id, volume_number, COUNT(*) c FROM volumes"
        " GROUP BY series_id, volume_number HAVING c > 1"
    ).fetchall()
    assert dups == []


def test_total_listing_and_history_counts(db):
    # Kayıp-koruması: görev 4 ("sadece katalogda bağlı seriler", onaylı)
    # sonrasındaki site geneli sayılar (yedek yomiba.db.bak-task4) alt
    # sınırıdır — sync/import ilave edebilir, kayıp asla olmaz.
    listings = db.execute("SELECT COUNT(*) FROM store_listings").fetchone()[0]
    history = db.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    assert listings >= 1031, listings
    assert history >= 1034, history
