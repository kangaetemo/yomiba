"""Görev 5 (kullanıcı onaylı, 2026-09-14) — warmup'ın yarattığı katalog-dışı
serileri TEK SEFERLİK güvenli temizlik.

Karar (kullanıcı mesajı, 9 maddelik plan):
  * ImportService artık catalog-only (yeni Series/Publisher oluşturamaz).
  * Warmup sırasında eski ImportService davranışıyla yaratılan katalog-dışı
    seriler (1614 seri / 1973 cilt / 2231 listing / 2259 history) silinir.
  * Yayıncılar: YALNIZCA warmup tarafından yaratılmış ve katalog serisi
    OLMAYAN yetim satırlar silinir (bak-task4b'de var olan ~585 referans
    yayıncı KALIR — task 3/4 onaylı durumun parçası).
  * Katalog serilerindeki TÜM cilt/listing/history (warmup'un katalog
    serilerine ekledikleri dahil) KORUNUR.

Güvenlik modeli (Görev 2/3/4 ile aynı):
  * Önce yedek (yomiba.db.bak-task5).
  * --dry-run: yalnızca sayılar, hiçbir yazma.
  * TEK transaction; pre/post assert; patlamada tam roll back.
  * Zero-loss: katalog serilerine ait her volume/listing/history birebir
    korunur (id kümesi + checksum karşılaştırması).

Çalıştırma:
  .venv/bin/python apply_task5_cleanup.py --dry-run
  .venv/bin/python apply_task5_cleanup.py
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys

DB = "yomiba.db"
BAK = "yomiba.db.bak-task5"
BAK_OLD = "yomiba.db.bak-task4b"  # warmup öncesi referans yayınacı kümesi


def chunks(ids, n=500):
    for i in range(0, len(ids), n):
        yield ids[i : i + n]


def catalog_series_set(con: sqlite3.Connection) -> set[int]:
    return {r[0] for r in con.execute("SELECT DISTINCT series_id FROM catalog_series")}


def snapshot_catalog(con: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    """Katalog serilerine ait volume/listing/history kümesinin özeti
    (satır sayısı + içerik checksum'u; pre/post karşılaştırması için)."""
    out = {}
    for table in ("volumes", "store_listings", "price_history"):
        if table == "volumes":
            rows = con.execute(
                "SELECT id, series_id, volume_number, isbn FROM volumes v"
                " WHERE v.series_id IN (SELECT series_id FROM catalog_series) ORDER BY id"
            ).fetchall()
        elif table == "store_listings":
            rows = con.execute(
                "SELECT l.id, l.volume_id, l.store_id, l.price, l.product_url"
                " FROM store_listings l JOIN volumes v ON v.id = l.volume_id"
                " WHERE v.series_id IN (SELECT series_id FROM catalog_series) ORDER BY l.id"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT h.id, h.listing_id, h.price, h.checked_at"
                " FROM price_history h JOIN store_listings l ON l.id = h.listing_id"
                " JOIN volumes v ON v.id = l.volume_id"
                " WHERE v.series_id IN (SELECT series_id FROM catalog_series) ORDER BY h.id"
            ).fetchall()
        digest = hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()
        out[table] = (len(rows), digest)
    return out


def main() -> None:
    dry = "--dry-run" in sys.argv

    if not dry:
        shutil.copy2(DB, BAK)
        print(f"yedek alındı: {BAK}")

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    bak_old = sqlite3.connect(BAK_OLD)
    old_pub_names = {
        r[0] for r in bak_old.execute("SELECT normalized_name FROM publishers")
    }
    bak_old.close()

    cat_ids = catalog_series_set(con)
    assert len(cat_ids) == 465, len(cat_ids)
    n_series = con.execute("SELECT COUNT(*) FROM series").fetchone()[0]
    non_cat = n_series - len(cat_ids & {
        r[0] for r in con.execute("SELECT id FROM series")
    })

    # SİL seti: katalog manifestinde olmayan tüm seriler.
    del_series: list[int] = [
        r[0]
        for r in con.execute(
            "SELECT id FROM series WHERE id NOT IN (SELECT series_id FROM catalog_series)"
        )
    ]

    # Yayıncı: warmup çöpü = (a) non-catalog seri silinince yetim KALACAK,
    # (b) bak-task4b'de (warmup öncesi) var OLMAYAN, (c) hiçbir alias'ın
    # hedefi OLMAYAN. Bu üç koşulun kesiimi.
    alias_targets = {
        r[0]
        for r in con.execute(
            "SELECT p.normalized_name FROM publisher_aliases a"
            " JOIN publishers p ON p.id = a.publisher_id"
        )
    }
    del_pubs: list[int] = []
    for pub_id, name in con.execute("SELECT id, normalized_name FROM publishers"):
        has_catalog = con.execute(
            "SELECT 1 FROM series s WHERE s.publisher_id = ? AND s.id IN"
            " (SELECT series_id FROM catalog_series) LIMIT 1",
            (pub_id,),
        ).fetchone()
        if has_catalog is not None:
            continue
        if name in old_pub_names:
            continue  # referans veri (task 3/4 onaylı küme)
        if name in alias_targets:
            continue  # alias hedefi: koru
        del_pubs.append(pub_id)

    # Sayılar (dry-run çıktısı / rapor için).
    counts = {
        "series_total": n_series,
        "series_catalog": len(cat_ids),
        "series_delete": len(del_series),
        "volumes_delete": 0,
        "listings_delete": 0,
        "history_delete": 0,
        "publishers_total": con.execute("SELECT COUNT(*) FROM publishers").fetchone()[0],
        "publishers_delete": len(del_pubs),
    }
    for c in chunks(del_series):
        ph = ",".join("?" * len(c))
        counts["volumes_delete"] += con.execute(
            f"SELECT COUNT(*) FROM volumes WHERE series_id IN ({ph})", c
        ).fetchone()[0]
        counts["listings_delete"] += con.execute(
            f"SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id = l.volume_id"
            f" WHERE v.series_id IN ({ph})",
            c,
        ).fetchone()[0]
        counts["history_delete"] += con.execute(
            f"SELECT COUNT(*) FROM price_history h JOIN store_listings l ON l.id = h.listing_id"
            f" JOIN volumes v ON v.id = l.volume_id WHERE v.series_id IN ({ph})",
            c,
        ).fetchone()[0]

    print("=== TEMİZLİK KAPSAMI ===")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    assert counts["series_delete"] == non_cat

    pre = snapshot_catalog(con)

    if dry:
        print("\nDRY-RUN: hiçbir şey silinmedi.")
        con.close()
        return

    # --- APPLY: tek transaction -------------------------------------------
    cur = con.cursor()
    try:
        cur.execute("BEGIN")
        for c in chunks(del_series):
            ph = ",".join("?" * len(c))
            # FK CASCADE zinciri: series -> volumes -> store_listings ->
            # price_history (+ wishlist_items/price_alerts; non-catalog'da 0).
            cur.execute(f"DELETE FROM series WHERE id IN ({ph})", c)
        if del_pubs:
            for c in chunks(del_pubs):
                ph = ",".join("?" * len(c))
                cur.execute(f"DELETE FROM publishers WHERE id IN ({ph})", c)
    except Exception:
        con.rollback()
        print("ROLLBACK — DB değişmedi.")
        raise

    # --- POST ASSERT --------------------------------------------------------
    post = snapshot_catalog(con)
    assert post == pre, (pre, post)  # katalog verisi birebir korunur

    assert (
        con.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 465
    ), "seri sayısı 465 değil"
    post_series = {r[0] for r in con.execute("SELECT id FROM series")}
    assert post_series == cat_ids, "series kümesi katalog manifestiyle birebir eşleşmiyor"

    leftover_pubs = con.execute(
        "SELECT COUNT(*) FROM publishers"
    ).fetchone()[0]
    assert leftover_pubs == counts["publishers_total"] - counts["publishers_delete"]

    cur.execute("COMMIT")
    con.close()

    print("\n=== UYGULANDI ===")
    print(f"  silinen seri: {len(del_series)}")
    print(f"  silinen cilt: {counts['volumes_delete']}")
    print(f"  silinen listing: {counts['listings_delete']}")
    print(f"  silinen history: {counts['history_delete']}")
    print(f"  silinen yayıncı (warmup yetimi): {len(del_pubs)}")
    print(f"  kalan seri: 465 == katalog 465 (birebir)")
    print(f"  kalan yayıncı: {leftover_pubs}")
    print("  katalog volume/listing/history: zero-loss doğrulandı (sha256)")


if __name__ == "__main__":
    main()
