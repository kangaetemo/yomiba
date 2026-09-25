"""Görev 2 — TAKİP: doğrulama curl'lerinin tetiklediği arama-içe-aktarma
dalgasının (import_records id 24/25/26) doğurduğu 3 YENİ duplikatın
birleştirilmesi.

Kök neden (bilinen ertelenen sorun): yayıncı yazım varyantları
("Gerekli Şeyler" v. "Gerekli Şeyler Yayıncılık", "Komik Şeyler" v.
"Komikşeyler Yayıncılık") — import eşleşmesi varyant yüzünden kaçırıyor
ve yeni seri açıyor.

İşlemler (tek transaction, pre/post assert):
  2212 "Jujutsu Kaisen" (Gerekli Şeyler)  -> seri 4:
       vol 6 cilt satırı taşınır; vol 0,1,2,4,5,7,8'in store-6
       listing'leri seri 4'ün aynı ciltlerine eklenir.
  2389 "Orange" (Komik Şeyler)            -> seri 1851:
       2 listing BİREBİR duplike (aynı store 6, aynı URL, aynı fiyat)
       -> listing'ler atılır; price-history satırları 1851'in aynı
       listing'lerine eklenir (sıfır history kaybı).
  2357 "Kara Kâhya" (Gerekli Şeyler)      -> seri 151 "Kara Kahya":
       vol 20-24'ün store-6 listing'leri 151'in aynı ciltlerine eklenir.
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


def listings_of(con: sqlite3.Connection, volume_id: int):
    return con.execute(
        "SELECT store_id, product_url FROM store_listings WHERE volume_id=?",
        (volume_id,),
    ).fetchall()


def main() -> None:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")

    # ---------------- PRE ----------------
    pre_L = con.execute("SELECT COUNT(*) FROM store_listings").fetchone()[0]
    pre_H = con.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]

    for src in (2212, 2389, 2357):
        if con.execute("SELECT 1 FROM series WHERE id=?", (src,)).fetchone() is None:
            print(f"PRE HATA: seri {src} zaten yok — script zaten çalıştı mı?")
            sys.exit(1)

    # 2212: 8 cilt, her biri tek store-6 listing; seri 4 ile (store,url) çakışması yok
    vols_2212 = con.execute(
        "SELECT volume_number FROM volumes WHERE series_id=2212 ORDER BY volume_number"
    ).fetchall()
    assert [v[0] for v in vols_2212] == [0, 1, 2, 4, 5, 6, 7, 8], vols_2212
    for (vn,) in vols_2212:
        src_l = listings_of(con, vol(con, 2212, vn))
        assert len(src_l) == 1 and src_l[0][0] == 6, f"2212 vol {vn}: {src_l}"
        tgt = vol(con, 4, vn) if con.execute(
            "SELECT 1 FROM volumes WHERE series_id=4 AND volume_number=?", (vn,)
        ).fetchone() else None
        if tgt is not None:
            overlap = set(src_l) & set(listings_of(con, tgt))
            assert not overlap, f"2212 vol {vn} örtüşme: {overlap}"
    assert con.execute(
        "SELECT 1 FROM volumes WHERE series_id=4 AND volume_number=6"
    ).fetchone() is None, "seri 4'te vol 6 zaten var"

    # 2389: tam duplike kontrolü — 1851'de aynı store+URL listing'ler var
    for vn in (1, 4):
        src_l = listings_of(con, vol(con, 2389, vn))
        tgt_l = listings_of(con, vol(con, 1851, vn))
        assert len(src_l) == 1 and src_l[0][0] == 6
        assert src_l[0] in tgt_l, f"2389 vol {vn} birebir duplike değil: {src_l}"

    # 2357: vol 20-24, her biri tek store-6; 151 ile çakışma yok
    vols_2357 = [v[0] for v in con.execute(
        "SELECT volume_number FROM volumes WHERE series_id=2357 ORDER BY volume_number")]
    assert vols_2357 == [20, 21, 22, 23, 24], vols_2357
    for vn in vols_2357:
        src_l = listings_of(con, vol(con, 2357, vn))
        assert len(src_l) == 1 and src_l[0][0] == 6, f"2357 vol {vn}: {src_l}"
        assert not (set(src_l) & set(listings_of(con, vol(con, 151, vn)))), \
            f"2357 vol {vn} örtüşme"
    print(f"PRE OK: {pre_L} listing, {pre_H} history, duplikeler teyit edildi")

    # ---------------- TRANSACTION ----------------
    con.execute("BEGIN")
    try:
        # --- 2212 -> seri 4 ---
        con.execute(
            "UPDATE volumes SET series_id=4 WHERE id=?", (vol(con, 2212, 6),)
        )
        for vn in (0, 1, 2, 4, 5, 7, 8):
            src_vid = vol(con, 2212, vn)
            tgt_vid = vol(con, 4, vn)
            con.execute(
                "UPDATE store_listings SET volume_id=? WHERE volume_id=?",
                (tgt_vid, src_vid),
            )
            con.execute("DELETE FROM volumes WHERE id=?", (src_vid,))
        con.execute("DELETE FROM series WHERE id=2212")

        # --- 2389 -> 1851 (duplike listing atılır, history taşınır) ---
        for vn in (1, 4):
            src_vid = vol(con, 2389, vn)
            src_l = con.execute(
                "SELECT id FROM store_listings WHERE volume_id=?", (src_vid,)
            ).fetchone()[0]
            tgt_l = con.execute(
                "SELECT l.id FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
                " WHERE v.series_id=1851 AND v.volume_number=? AND l.store_id=6",
                (vn,),
            ).fetchone()[0]
            con.execute(
                "UPDATE price_history SET listing_id=? WHERE listing_id=?",
                (tgt_l, src_l),
            )
            con.execute("DELETE FROM store_listings WHERE id=?", (src_l,))
            con.execute("DELETE FROM volumes WHERE id=?", (src_vid,))
        con.execute("DELETE FROM series WHERE id=2389")

        # --- 2357 -> 151 ---
        for vn in (20, 21, 22, 23, 24):
            src_vid = vol(con, 2357, vn)
            tgt_vid = vol(con, 151, vn)
            con.execute(
                "UPDATE store_listings SET volume_id=? WHERE volume_id=?",
                (tgt_vid, src_vid),
            )
            con.execute("DELETE FROM volumes WHERE id=?", (src_vid,))
        con.execute("DELETE FROM series WHERE id=2357")

        # --- POST (commit öncesi) ---
        post_L = con.execute("SELECT COUNT(*) FROM store_listings").fetchone()[0]
        post_H = con.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        # 2389'dan yalnızca 2 BİREBİR duplike listing atılır; history kayıpsız
        assert post_L == pre_L - 2, f"listing {pre_L}->{post_L}"
        assert post_H == pre_H, f"history {pre_H}->{post_H}"

        for vn in (0, 1, 2, 4, 5, 6, 7, 8):
            stores = {
                r[0] for r in con.execute(
                    "SELECT store_id FROM store_listings WHERE volume_id=?",
                    (vol(con, 4, vn),),
                )
            }
            assert 6 in stores, f"seri 4 vol {vn} store 6 eksik"
        for vn in (1, 4):
            stores = {
                r[0] for r in con.execute(
                    "SELECT store_id FROM store_listings WHERE volume_id=?",
                    (vol(con, 1851, vn),),
                )
            }
            assert stores >= {5, 6, 9} if vn == 1 else 6 in stores
        for vn in (20, 21, 22, 23, 24):
            assert con.execute(
                "SELECT 1 FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
                " WHERE v.series_id=151 AND v.volume_number=? AND l.store_id=6", (vn,)
            ).fetchone(), f"151 vol {vn} store 6 eksik"

        for gone in (2212, 2389, 2357):
            assert con.execute("SELECT 1 FROM series WHERE id=?", (gone,)).fetchone() is None
        assert con.execute(
            "SELECT COUNT(*) FROM store_listings l LEFT JOIN volumes v"
            " ON v.id=l.volume_id WHERE v.id IS NULL"
        ).fetchone()[0] == 0
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        print("POST ASSERT OK")

        con.commit()
    except AssertionError as exc:
        fail(con, f"POST-ASSERT: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        fail(con, f"{type(exc).__name__}: {exc}")
        return

    print(f"TAMAM: 3 duplikat birleşti; listing {pre_L}->{post_L} (2 duplike atıldı), "
          f"history {pre_H} (kayıpsız).")


if __name__ == "__main__":
    main()
