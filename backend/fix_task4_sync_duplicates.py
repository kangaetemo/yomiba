"""Task 4 sonrasI — sync duplikasyon onarimi (61 seri).

2026-09-14 09:23 manuel mangakol sync'i, yayinci-variant ("Komik Seyler" vs
"Komiksleyler Yayinciligi") ve baslik-fark (JJK - Lanet Savaslari, Orange -
Portakal, Tougen Anki: vs -) nedeniyle 71 seri acmistI; bunlardan 14'u
meşru yeni katalog sayfasI, 61'i mevcut seriye aynI slug'u tasiyan
duplikat. Duplikatlar slug-grubu bazinda keeper'a (listing'li, yoksa en
kucuk id) eritilir:

  * volume'lar add-only: numara chakisma'da duplikat volume silinir
    (listing'leri keeper'a tasinir — bu kumede 0 listing), chakisma yoksa
    keeper'a re-point.
  * duplikatin catalog satiri silinir (slug benzersiz kalir).
  * duplikat seri silinir; 716 (Komik Seyler) bosaldiysa silinir.

Guvence: once yedek (bak-task4b); tek transaction; pre/post assert;
zero-loss (listing sayisi ve (id,price) kumesi birebir).
"""

from __future__ import annotations

import shutil
import sqlite3

DB = "yomiba.db"
BAK = "yomiba.db.bak-task4b"


def main() -> None:
    shutil.copy2(DB, BAK)
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")

    groups = con.execute(
        """SELECT mangakol_slug, series_id FROM catalog_series
           WHERE mangakol_slug IN (SELECT mangakol_slug FROM catalog_series
                                   GROUP BY mangakol_slug HAVING COUNT(*) > 1)
           ORDER BY mangakol_slug, series_id"""
    ).fetchall()
    by_slug: dict[str, list[int]] = {}
    for slug, sid in groups:
        by_slug.setdefault(slug, []).append(sid)
    n_groups = len(by_slug)

    dup_ids: list[int] = []
    for slug, sids in by_slug.items():
        info = con.execute(
            """SELECT c.series_id,
                (SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id
                 WHERE v.series_id = c.series_id)
               FROM catalog_series c WHERE c.series_id IN (%s)"""
            % ",".join("?" * len(sids)), sids
        ).fetchall()
        keeper = max(info, key=lambda r: (r[1], -r[0]))[0]
        for sid, nlist in info:
            if sid != keeper:
                dup_ids.append(sid)
    print(f"grup: {n_groups}, duplikat seri: {len(dup_ids)}")
    assert len(dup_ids) == 61, len(dup_ids)

    # duplikatlarda listing olmamali (veri kaybini onler)
    for c in [dup_ids[i:i + 500] for i in range(0, len(dup_ids), 500)]:
        ph = ",".join("?" * len(c))
        n = con.execute(
            f"SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
            f" WHERE v.series_id IN ({ph})", c).fetchone()[0]
        assert n == 0, f"duplikatta {n} listing var — dur"

    pre_lists = con.execute("SELECT COUNT(*) FROM store_listings").fetchone()[0]
    pre_hist = con.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    pre_vols = con.execute("SELECT COUNT(*) FROM volumes").fetchone()[0]

    try:
        cur = con.cursor()
        cur.execute("BEGIN")
        for dup in dup_ids:
            keeper = con.execute(
                "SELECT series_id FROM catalog_series c2 WHERE c2.mangakol_slug ="
                " (SELECT mangakol_slug FROM catalog_series WHERE series_id=?) "
                "ORDER BY (SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
                "          WHERE v.series_id=c2.series_id) DESC, c2.series_id LIMIT 1",
                (dup,)).fetchone()[0]
            # volumes add-only
            for vid, vno, cover in cur.execute(
                    "SELECT id, volume_number, cover_url FROM volumes WHERE series_id=?", (dup,)):
                k = cur.execute(
                    "SELECT id, cover_url FROM volumes WHERE series_id=? AND volume_number=?",
                    (keeper, vno)).fetchone()
                if k is not None:
                    if k[1] is None and cover:
                        cur.execute("UPDATE volumes SET cover_url=? WHERE id=?", (cover, k[0]))
                    moved = cur.execute(
                        "UPDATE store_listings SET volume_id=? WHERE volume_id=?", (k[0], vid)).rowcount
                    assert moved == 0, f"listing tasima beklenmedik: {moved}"
                    cur.execute("DELETE FROM volumes WHERE id=?", (vid,))
                else:
                    cur.execute("UPDATE volumes SET series_id=? WHERE id=?", (keeper, vid))
            # katalog satiri + seri
            cur.execute("DELETE FROM catalog_series WHERE series_id=?", (dup,))
            cur.execute("DELETE FROM series WHERE id=?", (dup,))
        # 716 bosaldiyiysa sil
        left = cur.execute("SELECT COUNT(*) FROM series WHERE publisher_id=716").fetchone()[0]
        if left == 0:
            cur.execute("DELETE FROM publishers WHERE id=716")
            print("yayinici 716 silindi")
        con.execute("PRAGMA foreign_key_check")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        assert fk == [], fk
        con.commit()
    except Exception:
        con.rollback()
        raise

    # post
    assert con.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 526 - 61
    assert con.execute("SELECT COUNT(*) FROM catalog_series").fetchone()[0] == 465
    d = con.execute("SELECT COUNT(*) FROM (SELECT mangakol_slug FROM catalog_series GROUP BY mangakol_slug HAVING COUNT(*)>1)").fetchone()[0]
    assert d == 0, d
    assert con.execute("SELECT COUNT(*) FROM series WHERE id NOT IN (SELECT series_id FROM catalog_series)").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM store_listings").fetchone()[0] == pre_lists == 1031
    assert con.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == pre_hist
    print("POST: series 465 | catalog 465 (slug benzersiz) | vols",
          con.execute("SELECT COUNT(*) FROM volumes").fetchone()[0],
          f"(pre {pre_vols}) | listings 1031 | history {pre_hist}")

    # zero-loss: listing (id,price) ve history (id,price,checked_at) birebir
    bak = sqlite3.connect(f"file:{BAK}?mode=ro", uri=True)
    a = {r for r in bak.execute("SELECT id, price FROM store_listings")}
    b = {r for r in con.execute("SELECT id, price FROM store_listings")}
    assert a == b, len(a ^ b)
    a = {r for r in bak.execute("SELECT id, price, checked_at FROM price_history")}
    b = {r for r in con.execute("SELECT id, price, checked_at FROM price_history")}
    assert a == b, len(a ^ b)
    print("ZERO-LOSS OK")
    con.close()
    bak.close()
    print("ONARIM TAMAM. Yedek:", BAK)


if __name__ == "__main__":
    main()
