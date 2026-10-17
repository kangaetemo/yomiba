"""Görev 4 (revize kapsam) — "katalogda kal, gerisi sil" (KARAR: 2026-09-14 onaylı).

Dry-run raporu: docs/reports/task4-legacy-cleanup.md
Kullanıcı kararı (ask_user, option "katalog-sadece"):
  * Son durum = mangakol kataloğuyla bağlı seriler YALNIZCA.
  * 1636 katalog-dışı seri silinir (içinde 61 wave serisi ve 4 held dahil —
    kullanıcı tarafından bu onayda kapsandı).
  * 14 yanlış eşleşme (katalogda ama manga olmayan: Dante, Kapital,
    Mein Kampf, Warcraft ×2, Starcraft, Twilight romanı, Yengeç Gemisi,
    Psi-Kom, Gannibal figürü…) + katalog satırları da temizlenir.
  * Sonuç: 455 seri / 455 katalog satırı.

Güvenlik modeli (Görev 2/3 ile aynı):
  * Önce yedek (yomiba.db.bak-task4).
  * TEK transaction; pre/post assert; patlamada tam roll back.
  * Zero-loss: backup'a göre, KAL setindeki her volume/listing/history
    birebir korunur; SİL setindeki her satır gider; üçüncü durum yok.

Yayıncı satırlarına DOKUNULMAZ (referans verisi; task 3 modeli).
"""

from __future__ import annotations

import shutil
import sqlite3

DB = "yomiba.db"
BAK = "yomiba.db.bak-task4"

# Katalogda var ama manga OLMAYAN 14 yanlış eşleşme (başlık+slug doğrulandı).
FALSE_14 = [342, 463, 468, 477, 478, 486, 492, 495, 508, 518, 525, 528, 535, 536]
HELD = (2287, 2394, 2404, 2407)  # onayla birlikte silinme kapsamına girdi


def chunks(ids, n=500):
    for i in range(0, len(ids), n):
        yield ids[i : i + n]


def main() -> None:
    # 0) yedek ----------------------------------------------------------------
    shutil.copy2(DB, BAK)

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")

    # 1) pre ------------------------------------------------------------------
    cat_ids = [r[0] for r in con.execute(
        "SELECT DISTINCT series_id FROM catalog_series")]
    cat_rows = con.execute("SELECT COUNT(*) FROM catalog_series").fetchone()[0]
    assert cat_rows == 469 and len(cat_ids) == 469, (cat_rows, len(cat_ids))

    non_cat: list[int] = []
    for c in chunks(cat_ids):
        ph = ",".join("?" * len(c))
        non_cat += [r[0] for r in con.execute(
            f"SELECT id FROM series WHERE id NOT IN ({ph})", c)]
    assert len(non_cat) == 1636, len(non_cat)

    fset = set(FALSE_14)
    assert fset <= set(cat_ids), "FALSE_14 katalogda değil"
    assert not (fset & set(non_cat))
    assert set(HELD) <= set(non_cat), "held artık silme kapsamı (onaylı)"
    assert len(set(non_cat)) == 1636

    keep_ids = [i for i in cat_ids if i not in fset]
    assert len(keep_ids) == 455

    # FALSE_14'te hiç listing olmasın (veri kaybı olmamalı)
    for c in chunks(sorted(fset)):
        ph = ",".join("?" * len(c))
        n = con.execute(
            f"SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
            f" WHERE v.series_id IN ({ph})", c).fetchone()[0]
        assert n == 0, f"FALSE_14 listing taşıyor: {n}"

    def count_sql(table_join: str) -> str:
        return f"SELECT COUNT(*) FROM {table_join}"

    exp_vols = exp_lists = exp_hist = 0
    for c in chunks(keep_ids):
        ph = ",".join("?" * len(c))
        exp_vols += con.execute(
            f"SELECT COUNT(*) FROM volumes v WHERE v.series_id IN ({ph})", c).fetchone()[0]
        exp_lists += con.execute(
            f"SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
            f" WHERE v.series_id IN ({ph})", c).fetchone()[0]
        exp_hist += con.execute(
            f"SELECT COUNT(*) FROM price_history h JOIN store_listings l ON l.id=h.listing_id"
            f" JOIN volumes v ON v.id=l.volume_id WHERE v.series_id IN ({ph})", c).fetchone()[0]

    pre = {
        "series": con.execute("SELECT COUNT(*) FROM series").fetchone()[0],
        "vols": con.execute("SELECT COUNT(*) FROM volumes").fetchone()[0],
        "lists": con.execute("SELECT COUNT(*) FROM store_listings").fetchone()[0],
        "hist": con.execute("SELECT COUNT(*) FROM price_history").fetchone()[0],
    }
    print("PRE:", pre, "| beklenen kalan: vols", exp_vols, "lists", exp_lists,
          "hist", exp_hist)

    # 2) silme (tek transaction) ---------------------------------------------
    try:
        cur = con.cursor()
        cur.execute("BEGIN")
        for c in chunks(sorted(fset)):
            ph = ",".join("?" * len(c))
            cur.execute(f"DELETE FROM catalog_series WHERE series_id IN ({ph})", c)
        delete_ids = non_cat + sorted(fset)
        assert len(delete_ids) == 1650
        for c in chunks(delete_ids):
            ph = ",".join("?" * len(c))
            cur.execute(f"DELETE FROM series WHERE id IN ({ph})", c)
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        assert fk == [], fk
        con.commit()
    except Exception:
        con.rollback()
        raise

    # 3) post -----------------------------------------------------------------
    post = {
        "series": con.execute("SELECT COUNT(*) FROM series").fetchone()[0],
        "vols": con.execute("SELECT COUNT(*) FROM volumes").fetchone()[0],
        "lists": con.execute("SELECT COUNT(*) FROM store_listings").fetchone()[0],
        "hist": con.execute("SELECT COUNT(*) FROM price_history").fetchone()[0],
        "cat": con.execute("SELECT COUNT(*) FROM catalog_series").fetchone()[0],
    }
    assert post["series"] == 455, post
    assert post["cat"] == 455, post
    assert post["vols"] == exp_vols, (post, exp_vols)
    assert post["lists"] == exp_lists, (post, exp_lists)
    assert post["hist"] == exp_hist, (post, exp_hist)
    orphan = con.execute("""SELECT COUNT(*) FROM series s
        WHERE s.id NOT IN (SELECT series_id FROM catalog_series)""").fetchone()[0]
    assert orphan == 0, orphan
    assert con.execute(
        "SELECT COUNT(*) FROM series WHERE id IN (2287,2394,2404,2407)").fetchone()[0] == 0
    assert con.execute(
        "SELECT COUNT(*) FROM series WHERE id >= 2207").fetchone()[0] == 1  # 2245 Kara Paradoks
    print("POST:", post)

    # 4) zero-loss (backup'a karşı) -------------------------------------------
    bak = sqlite3.connect(f"file:{BAK}?mode=ro", uri=True)

    def series_set(db, ids):
        s = set()
        for c in chunks(ids):
            ph = ",".join("?" * len(c))
            s |= {r[0] for r in db.execute(f"SELECT id FROM series WHERE id IN ({ph})", c)}
        return s

    keep_series = series_set(con, keep_ids)
    del_series = series_set(bak, delete_ids)
    bak_series_all = {r[0] for r in bak.execute("SELECT id FROM series")}
    assert keep_series | del_series == bak_series_all, "bölünme tam değil"

    # volumes: KAL'dakiler birebir, SİL'dekiler gitti
    for label, db, ids in (("KAL", con, keep_ids), ("SİL", bak, delete_ids)):
        have = set()
        for c in chunks(ids):
            ph = ",".join("?" * len(c))
            have |= {r[0] for r in db.execute(
                f"SELECT id FROM volumes WHERE series_id IN ({ph})", c)}
        if label == "KAL":
            in_bak = set()
            for c in chunks(ids):
                ph = ",".join("?" * len(c))
                in_bak |= {r[0] for r in bak.execute(
                    f"SELECT id FROM volumes WHERE series_id IN ({ph})", c)}
            assert have == in_bak, f"volume kaybı/ek: {len(have)} vs {len(in_bak)}"
        else:
            live_left = set()
            for c in chunks(ids):
                ph = ",".join("?" * len(c))
                live_left |= {r[0] for r in con.execute(
                    f"SELECT id FROM volumes WHERE series_id IN ({ph})", c)}
            assert live_left == set(), f"SİL volume kaldı: {len(live_left)}"

    # listings + history: KAL'daki fiyatlar birebir (id, price)
    def list_pairs(db, ids, table):
        out = set()
        for c in chunks(ids):
            ph = ",".join("?" * len(c))
            out |= {(r[0], r[1]) for r in db.execute(
                f"SELECT l.id, l.price FROM {table} l JOIN volumes v ON v.id=l.volume_id"
                f" WHERE v.series_id IN ({ph})", c)}
        return out

    a = list_pairs(bak, keep_ids, "store_listings")
    b = list_pairs(con, keep_ids, "store_listings")
    assert a == b, f"listing fark: {len(a ^ b)}"

    def hist_pairs(db, ids):
        out = set()
        for c in chunks(ids):
            ph = ",".join("?" * len(c))
            out |= {(r[0], r[1], r[2]) for r in db.execute(
                "SELECT h.id, h.price, h.checked_at FROM price_history h"
                " JOIN store_listings l ON l.id=h.listing_id"
                " JOIN volumes v ON v.id=l.volume_id"
                f" WHERE v.series_id IN ({ph})", c)}
        return out

    a = hist_pairs(bak, keep_ids)
    b = hist_pairs(con, keep_ids)
    assert a == b, f"history fark: {len(a ^ b)}"
    print(f"ZERO-LOSS OK: keep listings {len(list_pairs(con, keep_ids, 'store_listings'))},"
          f" history {len(hist_pairs(con, keep_ids))}")

    # silinenlerin listing/history'nin gittiği teyidi (post sayıları üstte doğrulandı)
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    assert fk == [], fk
    con.close()
    bak.close()
    print("UYGULANDI: 1650 seri silindi, 455 manga kaldı. Yedek:", BAK)


if __name__ == "__main__":
    main()
