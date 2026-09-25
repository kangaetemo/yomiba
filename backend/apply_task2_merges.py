"""Görev 2 — hibrit/katkı küme birleştirmeleri (KARAR: 2026-09-14 onaylı).

Dry-run raporu: docs/reports/task2-dry-run.md

Güvenlik modeli:
* Önce yedek (dışarıdan alınır: yomiba.db.bak-task2).
* TEK transaction; her adımda pre/post assert.
* Bir assert patlarsa TAMAM roll back edilir ve DB değişmeden kalır.

İşlemler:
  JJK:      vol 0 (seri 15), vol 1 (seri 14), vol 9 (seri 5) -> seri 4'a
            (cilt satırıyla birlikte); 5, 14, 15 silinir; slug 90 -> 4; 90 silinir.
  Naruto:   seri 19 vol 28 + seri 20 vol 29 listing'leri -> seri 6'nın
            mevcut boş vol 28/29 slotlarına; ISBN backfill; 19, 20 silinir.
  Kara Meşale: slug 343 -> 2145; 2145 başlığı "Kara Meşale"; 343 + 3 boş cilt silinir.
  Vinland:  slug 106 -> 2157; 2157 başlığı "Vinland Destanı"; 106 + 11 boş cilt silinir.
  Orange:   1874 vol 1/4 + 1886 vol 1 listing'leri -> 1851 vol 1/4; vol 1 ISBN
            9786052115442 backfill; slug 150 -> 1851; 150, 1874, 1886 silinir.
  Paradise Kiss: seri 1593 publisher_id -> 204 (Komikşeyler Yayıncılık).
"""

from __future__ import annotations

import sqlite3
import sys

DB = "yomiba.db"


def fail(con: sqlite3.Connection, msg: str) -> None:
    con.rollback()
    print(f"ROLLBACK — {msg}")
    sys.exit(1)


def vol(con: sqlite3.Connection, series_id: int, volume_number: int) -> int:
    row = con.execute(
        "SELECT id FROM volumes WHERE series_id=? AND volume_number=?",
        (series_id, volume_number),
    ).fetchone()
    if row is None:
        raise AssertionError(f"volume yok: seri={series_id} vol={volume_number}")
    return row[0]


def n_listings(con: sqlite3.Connection, series_id: int) -> int:
    return con.execute(
        "SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
        " WHERE v.series_id=?", (series_id,),
    ).fetchone()[0]


def main() -> None:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")

    # ---------------- PRE ASSERTIONS ----------------
    cluster_series = [4, 5, 14, 15, 90, 6, 19, 20, 343, 2145, 106, 2157,
                      150, 1851, 1874, 1886]
    placeholders = ",".join("?" * len(cluster_series))
    pre_listings = con.execute(
        f"SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
        f" WHERE v.series_id IN ({placeholders})", cluster_series,
    ).fetchone()[0]
    pre_history = con.execute(
        f"SELECT COUNT(*) FROM price_history ph JOIN store_listings l ON l.id=ph.listing_id"
        f" JOIN volumes v ON v.id=l.volume_id WHERE v.series_id IN ({placeholders})",
        cluster_series,
    ).fetchone()[0]
    if (pre_listings, pre_history) != (263, 263):
        print(f"PRE-ASSERT HATA: beklenen (263, 263), bulunan ({pre_listings}, {pre_history})")
        sys.exit(1)

    # (store, product_url) örtüşmeleri olmasın
    overlaps = con.execute(
        """
        SELECT COUNT(*) FROM store_listings a
        JOIN volumes va ON va.id=a.volume_id
        JOIN store_listings b ON b.store_id=a.store_id AND b.product_url=a.product_url
        JOIN volumes vb ON vb.id=b.volume_id
        WHERE (va.series_id, va.volume_number, vb.series_id, vb.volume_number) IN (
            (5,9,4,9),(14,-1,4,1),(15,-1,4,0),
            (19,28,6,28),(20,29,6,29),
            (1874,1,1851,1),(1874,4,1851,4),(1886,1,1851,1)
        )
        """
    ).fetchone()[0]
    if overlaps:
        print(f"PRE-ASSERT HATA: {overlaps} (store,url) örtüşmesi")
        sys.exit(1)

    # hedef slotların mevcut listing sayıları (taşınmadan önce)
    for series_id, vnum, expected in ((6, 28, 0), (6, 29, 0), (1851, 1, 1), (1851, 4, 5)):
        vid = vol(con, series_id, vnum)
        cnt = con.execute(
            "SELECT COUNT(*) FROM store_listings WHERE volume_id=?", (vid,)
        ).fetchone()[0]
        if cnt != expected:
            print(f"PRE-ASSERT HATA: seri {series_id} vol {vnum} -> {cnt} listing (beklenen {expected})")
            sys.exit(1)
    # JJK 4'te vol 0/1/9 OLMAMALI (cilt satırı taşınacak)
    for missing in ((4, 0), (4, 1), (4, 9)):
        row = con.execute(
            "SELECT id FROM volumes WHERE series_id=? AND volume_number=?", missing
        ).fetchone()
        if row is not None:
            print(f"PRE-ASSERT HATA: seri 4'te vol {missing[1]} zaten var")
            sys.exit(1)
    # silinecek iskeletler BOŞ olmalı (listing'siz ciltler)
    for skel in (90, 343, 106, 150):
        if n_listings(con, skel) != 0:
            print(f"PRE-ASSERT HATA: iskelet seri {skel} listing içeriyor!")
            sys.exit(1)
    # silinecek cilt satırlarına wishlist/price_alert referansı yok (NO ACTION FK)
    bad_refs = con.execute(
        """
        SELECT (SELECT COUNT(*) FROM wishlist_items WHERE volume_id IN
            (SELECT id FROM volumes WHERE (series_id, volume_number) IN
              ((19,28),(20,29),(1874,1),(1874,4),(1886,1)) OR series_id IN (90,343,106,150))),
               (SELECT COUNT(*) FROM price_alerts WHERE volume_id IN
            (SELECT id FROM volumes WHERE (series_id, volume_number) IN
              ((19,28),(20,29),(1874,1),(1874,4),(1886,1)) OR series_id IN (90,343,106,150)))
        """
    ).fetchone()
    if bad_refs != (0, 0):
        print(f"PRE-ASSERT HATA: silinecek ciltlere referans var: {bad_refs}")
        sys.exit(1)
    # ÖNCEDEN VAR olan tek FK yetimi: series 310 silinmiş, catalog satırı kalmış.
    # Beklenti: tam olarak bu satır (fazlası sürpriz = dur).
    pre_fk = con.execute("PRAGMA foreign_key_check").fetchall()
    if pre_fk != [("catalog_series", 236, "series", 0)]:
        print(f"PRE-ASSERT HATA: beklenmeyen mevcut FK ihlali: {pre_fk}")
        sys.exit(1)
    if con.execute("SELECT 1 FROM series WHERE id=310").fetchone() is not None:
        print("PRE-ASSERT HATA: seri 310 yeniden var — yetim analizi geçersiz")
        sys.exit(1)
    # ISBN kontrolü
    isbn_check = {
        vol(con, 5, 9): "9786258237979",
        vol(con, 14, -1): "9786257590341",
        vol(con, 15, -1): "9786257590303",
        vol(con, 19, 28): "9786059141574",
        vol(con, 20, 29): "9786059141796",
        vol(con, 1886, 1): "9786052115442",
    }
    for vid, expected_isbn in isbn_check.items():
        actual = con.execute("SELECT isbn FROM volumes WHERE id=?", (vid,)).fetchone()[0]
        if actual != expected_isbn:
            print(f"PRE-ASSERT HATA: vol {vid} isbn {actual!r} != {expected_isbn!r}")
            sys.exit(1)
    print(f"PRE OK: {pre_listings} listing, {pre_history} price-history, 0 örtüşme")

    # ---------------- TRANSACTION ----------------
    # Sıra kuralları (bunlar olmasa IntegrityError):
    # * catalog_series.series_id -> series.id ON DELETE CASCADE: slug taşıma
    #   silinen serinin DELETE'inden ÖNCE yapılmalı.
    # * volumes.isbn UNIQUE: ISBN backfill, kaynağı ISBN taşıyan satır
    #   silindikten SONRA yapılmalı.
    # * series UNIQUE(publisher_id, normalized_title): aynı yayıncının aynı
    #   normalize başlıklı iki satırı aynı anda yaşayamaz -> yeniden adlandırma,
    #   eski başlığı taşıyan seri silindikten SONRA.
    con.execute("BEGIN")
    try:
        # --- JJK: slug önce, sonra cilt satırları seri 4'e, en sonda silme ---
        con.execute("UPDATE catalog_series SET series_id=4 WHERE series_id=90")
        # 14/15'teki satırlar -1 (numarasız sentinel) taşınırken gerçek cilt
        # numarasını alır: "JJK 1 - Lanet Savaşları" -> vol 1, "JJK 0 - ..." -> vol 0.
        for src_series, vnum, tgt_vol in ((5, 9, 9), (14, -1, 1), (15, -1, 0)):
            vid = vol(con, src_series, vnum)
            con.execute(
                "UPDATE volumes SET series_id=4, volume_number=? WHERE id=?",
                (tgt_vol, vid),
            )
        con.execute("DELETE FROM series WHERE id IN (5, 14, 15, 90)")

        # --- Naruto: listing'leri seri 6'nın boş slotlarına ---
        for src_series, vnum, tgt_series in ((19, 28, 6), (20, 29, 6)):
            src_vid = vol(con, src_series, vnum)
            tgt_vid = vol(con, tgt_series, vnum)
            con.execute(
                "UPDATE store_listings SET volume_id=? WHERE volume_id=?",
                (tgt_vid, src_vid),
            )
            src_isbn = con.execute("SELECT isbn FROM volumes WHERE id=?", (src_vid,)).fetchone()[0]
            con.execute("DELETE FROM volumes WHERE id=?", (src_vid,))
            con.execute("UPDATE volumes SET isbn=? WHERE id=?", (src_isbn, tgt_vid))
        con.execute("DELETE FROM series WHERE id IN (19, 20)")

        # --- Kara Meşale: slug taşı -> iskelet sil -> survivor'ı yeniden adlandır ---
        con.execute("UPDATE catalog_series SET series_id=2145 WHERE series_id=343")
        con.execute("DELETE FROM volumes WHERE series_id=343")
        con.execute("DELETE FROM series WHERE id=343")
        con.execute(
            "UPDATE series SET title='Kara Meşale', normalized_title='kara mesele' WHERE id=2145"
        )

        # --- Vinland: slug taşı -> iskelet sil -> survivor'ı yeniden adlandır ---
        con.execute("UPDATE catalog_series SET series_id=2157 WHERE series_id=106")
        con.execute("DELETE FROM volumes WHERE series_id=106")
        con.execute("DELETE FROM series WHERE id=106")
        con.execute(
            "UPDATE series SET title='Vinland Destanı', normalized_title='vinland destani' WHERE id=2157"
        )

        # --- Orange: listing'leri 1851'e, ISBN backfill, sonra silmeler ---
        for src_series, vnum in ((1874, 1), (1874, 4), (1886, 1)):
            src_vid = vol(con, src_series, vnum)
            tgt_vid = vol(con, 1851, vnum)
            con.execute(
                "UPDATE store_listings SET volume_id=? WHERE volume_id=?",
                (tgt_vid, src_vid),
            )
            con.execute("DELETE FROM volumes WHERE id=?", (src_vid,))
        con.execute("UPDATE volumes SET isbn='9786052115442' WHERE id=?", (vol(con, 1851, 1),))
        con.execute("UPDATE catalog_series SET series_id=1851 WHERE series_id=150")
        con.execute("DELETE FROM volumes WHERE series_id=150")
        con.execute("DELETE FROM series WHERE id IN (150, 1874, 1886)")

        # --- Paradise Kiss: yayıncı ataması ---
        con.execute("UPDATE series SET publisher_id=204 WHERE id=1593")

        # --- EKSRA (raporda işaretli): mevcut FK yetimi katalog satırı ---
        # series 310 çoktan silinmiş; bu satır hem FK ihlali yaratıyor hem
        # gelecek katalog senkronunda aynı slug'ın iki satırıyla sonuçlanmasına
        # yol açabilir. Referansı olmayan 1 satır, sıfır veri kaybı.
        con.execute(
            "DELETE FROM catalog_series WHERE series_id=310"
            " AND mangakol_slug='yamada-kun-to-lv999-no-koi-wo-suru'"
        )

        # ---------------- POST ASSERTIONS (commit ÖNCESI — hata = rollback) ---
        # 1) sıfır kayıp: küme listing + history korunmuş
        survivors = [4, 6, 2145, 2157, 1851]
        ph = ",".join("?" * len(survivors))
        post_listings = con.execute(
            f"SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
            f" WHERE v.series_id IN ({ph})", survivors,
        ).fetchone()[0]
        post_history = con.execute(
            f"SELECT COUNT(*) FROM price_history ph JOIN store_listings l ON l.id=ph.listing_id"
            f" JOIN volumes v ON v.id=l.volume_id WHERE v.series_id IN ({ph})",
            survivors,
        ).fetchone()[0]
        assert (post_listings, post_history) == (263, 263), \
            f"kayıp! ({post_listings}, {post_history}) != (263, 263)"

        # 2) JJK 4: 18 cilt, ISBN'ler yerinde
        vols = {r[0] for r in con.execute(
            "SELECT volume_number FROM volumes WHERE series_id=4")}
        assert vols == {0, 1, 2, 3, 4, 5, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19}, vols
        for vnum, isbn in ((0, "9786257590303"), (1, "9786257590341"), (9, "9786258237979")):
            got = con.execute(
                "SELECT isbn FROM volumes WHERE series_id=4 AND volume_number=?", (vnum,)
            ).fetchone()[0]
            assert got == isbn, f"JJK vol {vnum} isbn {got!r}"
        assert n_listings(con, 4) == 22, n_listings(con, 4)

        # 3) Naruto 6: vol 28/29 ISBN'li + 3'er listing
        for vnum, isbn in ((28, "9786059141574"), (29, "9786059141796")):
            got = con.execute(
                "SELECT isbn FROM volumes WHERE series_id=6 AND volume_number=?", (vnum,)
            ).fetchone()[0]
            assert got == isbn, f"Naruto vol {vnum} isbn {got!r}"
            vid = vol(con, 6, vnum)
            cnt = con.execute(
                "SELECT COUNT(*) FROM store_listings WHERE volume_id=?", (vid,)
            ).fetchone()[0]
            assert cnt == 3, f"Naruto vol {vnum} listing {cnt}"
        assert n_listings(con, 6) == 148, n_listings(con, 6)

        # 4) Kara Meşale / Vinland başlık + slug
        assert con.execute("SELECT title FROM series WHERE id=2145").fetchone()[0] == "Kara Meşale"
        assert con.execute("SELECT title FROM series WHERE id=2157").fetchone()[0] == "Vinland Destanı"
        slug_map = {
            r[0]: r[1] for r in con.execute(
                "SELECT mangakol_slug, series_id FROM catalog_series"
                " WHERE mangakol_slug IN ('jujutsu-kaisen','black-torch','vinland-saga','orange','naruto')")
        }
        assert slug_map == {
            "jujutsu-kaisen": 4, "black-torch": 2145,
            "vinland-saga": 2157, "orange": 1851, "naruto": 6,
        }, slug_map
        assert n_listings(con, 2145) == 1 and n_listings(con, 2157) == 55

        # 5) Orange 1851: vol 1 = 3 listing (stores 5,6,9) + ISBN; vol 4 = 6 listing
        v1 = vol(con, 1851, 1)
        stores_v1 = {r[0] for r in con.execute(
            "SELECT store_id FROM store_listings WHERE volume_id=?", (v1,))}
        assert stores_v1 == {5, 6, 9}, stores_v1
        assert con.execute(
            "SELECT isbn FROM volumes WHERE id=?", (v1,)
        ).fetchone()[0] == "9786052115442"
        v4 = vol(con, 1851, 4)
        assert con.execute(
            "SELECT COUNT(*) FROM store_listings WHERE volume_id=?", (v4,)
        ).fetchone()[0] == 6
        assert n_listings(con, 1851) == 37, n_listings(con, 1851)

        # 6) silinen seriler yok; dokunulmayanlar var
        gone = con.execute(
            "SELECT id FROM series WHERE id IN (5,14,15,90,19,20,343,106,150,1874,1886)"
        ).fetchall()
        assert not gone, f"silinecekler hâlâ var: {gone}"
        for keep in (21, 1853, 1875, 1879, 2158, 2159, 1593):
            assert con.execute("SELECT 1 FROM series WHERE id=?", (keep,)).fetchone(), keep
        assert con.execute(
            "SELECT publisher_id FROM series WHERE id=1593"
        ).fetchone()[0] == 204

        # 7) FK bütünlüğü: yetim listing/price-history yok
        orphans = con.execute(
            "SELECT COUNT(*) FROM store_listings l LEFT JOIN volumes v ON v.id=l.volume_id"
            " WHERE v.id IS NULL"
        ).fetchone()[0]
        assert orphans == 0, f"{orphans} yetim listing"
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        assert not fk, f"FK ihlali: {fk[:5]}"
        print("POST ASSERT (commit öncesi) TAMAMI OK")

        con.commit()
    except AssertionError as exc:
        fail(con, f"POST-ASSERT: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        fail(con, f"{type(exc).__name__}: {exc}")
        return

    print("POST OK: 263 listing + 263 price-history korunmuş, 11 seri silindi, 4 slug taşındı")
    print("TAMAM — commit edildi.")


if __name__ == "__main__":
    main()
