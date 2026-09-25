"""2026-09-21 kullanıcı onaylı (sadece manga kapsamı) — katalogdaki
18 kitap benzeri girişin TEK SEFERLİK güvenli temizliği.

Karar (kullanıcı: "sadece ve sadece mangakol db'deki [manga] ürünleri
istiyorum"): mangakol kataloğundaki edebiyat/roman uyarlamaları, oyun
romanları ve eğitim kitapları katalogdan çıkarılır, BLOK LİSTESİ'ne
alınır → 12 saatlik senkron bir daha asla geri ekleyemez.

Kapsam (18 slug):
  Edebiyat/felsefe uyarlamaları: shin-shihonron, kyousantou-sengen,
    shu-no-kigen, sensou-to-heiwa, shinkyoku, kanikousen, waga-tousou,
    olum-tinisi, psy-comm
  Oyun/roman uyarlamaları: warcraft-legends, warcraft-the-sunwell-trilogy,
    starcraft-frontline, twilight
  Eğitim ("Manga de Wakaru") kitapları: manga-de-wakaru-denki,
    manga-de-wakaru-butsuri-rikigaku-hen, manga-de-wakaru-soutaisei-riron,
    manga-de-wakaru-bunshi-seibutsugaku, manga-de-wakaru-bibun-sekibun

Yapılanlar (--apply):
  * Önce yedek (yomiba.db.bak-nonmanga).
  * catalog_exclusions tablosu yoksa oluşturulur (migration 0004 ile aynı
    şema; uygulama başlarken otomatik oluşur ama script kendi kendine
    yeter).
  * TEK transaction:
      - 18 slug'in catalog_series satırları silinir (manifest kapısı kapanır;
        arama / indirim şeridi / warmup / zamanlayıcılar onları bir daha
        işlemez),
      - 18 slug catalog_exclusions'a yazılır (senkron kalıcı olarak atlar),
      - bu seriye ait import_records silinir (24h fiyat döngüsü boşuna
        mağaza taramasın).
  * ZERO LOSS: serilere ait volume / listing / price_history satırları
    DOKUNULMAZ (id kümesi + checksum pre/post karşılaştırması ile kanıtlanır).
  * Dry-run varsayılandır; yazma için --apply GEREKLİ.

Çalıştırma (backend dizininde):
  .venv/bin/python apply_nonmanga_exclusions.py            # dry-run (güvenli)
  .venv/bin/python apply_nonmanga_exclusions.py --apply    # uygula (yedek alır)
  Windows: .venv/Scripts/python apply_nonmanga_exclusions.py --apply
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB = "yomiba.db"
BAK = "yomiba.db.bak-nonmanga"

SLUGS: list[tuple[str, str]] = [
    ("shin-shihonron", "edebiyat uyarlaması (Kapital manga)"),
    ("kyousantou-sengen", "edebiyat uyarlaması (Komünist Manifesto)"),
    ("shu-no-kigen", "edebiyat uyarlaması (Türlerin Kökeni)"),
    ("sensou-to-heiwa", "edebiyat uyarlaması (Savaş ve Barış)"),
    ("shinkyoku", "edebiyat uyarlaması (İlahi Komedya)"),
    ("kanikousen", "edebiyat uyarlaması (Yengeç Gemisi)"),
    ("waga-tousou", "edebiyat uyarlaması (Kavgam)"),
    ("olum-tinisi", "edebiyat uyarlaması (Ölüm Tınısı)"),
    ("psy-comm", "edebiyat uyarlaması (Psi-Kom)"),
    ("warcraft-legends", "oyun romanı uyarlaması (Warcraft: Efsaneler)"),
    ("warcraft-the-sunwell-trilogy", "oyun romanı uyarlaması (Sunwell Üçlemesi)"),
    ("starcraft-frontline", "oyun romanı uyarlaması (Starcraft: Öncephe)"),
    ("twilight", "roman uyarlaması (Alacakaranlık)"),
    ("manga-de-wakaru-denki", "eğitim kitabı (Elektrik)"),
    ("manga-de-wakaru-butsuri-rikigaku-hen", "eğitim kitabı (Fizik)"),
    ("manga-de-wakaru-soutaisei-riron", "eğitim kitabı (Görelilik)"),
    ("manga-de-wakaru-bunshi-seibutsugaku", "eğitim kitabı (Moleküler Biyoloji)"),
    ("manga-de-wakaru-bibun-sekibun", "eğitim kitabı (Matematik)"),
]
SLUG_LIST = [s for s, _ in SLUGS]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_affected(con: sqlite3.Connection, series_ids: list[int]) -> dict[str, tuple[int, str]]:
    """Etkilenen serilerin volume/listing/history kümelerinin özeti
    (satır sayısı + içerik checksum) — zero-loss kanıtı için.

    NOT: sabit series_id kümesiyle sorgular — catalog_series satırları
    silindikten SONRA da aynı kümeyi ölçer (manifeste bağımlı alt sorgu
    kullanılmaz; o, silme sonrası boş döner ve yanıltır)."""
    out: dict[str, tuple[int, str]] = {}
    if not series_ids:
        return out
    idq = ",".join("?" * len(series_ids))
    for table in ("volumes", "store_listings", "price_history"):
        if table == "volumes":
            sql = ("SELECT id, series_id, volume_number, isbn FROM volumes v"
                   f" WHERE v.series_id IN ({idq}) ORDER BY id")
        elif table == "store_listings":
            sql = ("SELECT l.id, l.volume_id, l.store_id, l.price, l.product_url"
                   " FROM store_listings l JOIN volumes v ON v.id = l.volume_id"
                   f" WHERE v.series_id IN ({idq}) ORDER BY l.id")
        else:
            sql = ("SELECT h.id, h.listing_id, h.price, h.checked_at"
                   " FROM price_history h JOIN store_listings l ON l.id = h.listing_id"
                   " JOIN volumes v ON v.id = l.volume_id"
                   f" WHERE v.series_id IN ({idq}) ORDER BY h.id")
        rows = con.execute(sql, series_ids).fetchall()
        out[table] = (len(rows), hashlib.sha256(repr(rows).encode()).hexdigest())
    return out


def q() -> str:
    return ",".join("?" * len(SLUG_LIST))


def main() -> int:
    apply = "--apply" in sys.argv
    if not Path(DB).exists():
        print(f"HATA: {DB} bulunamadı — backend dizininden çalıştır.")
        return 1

    con = sqlite3.connect(DB)
    try:
        # --- Durum saptama ---
        total_before = con.execute("SELECT COUNT(*) FROM catalog_series").fetchone()[0]
        present = {
            r[0]
            for r in con.execute(
                f"SELECT mangakol_slug FROM catalog_series WHERE mangakol_slug IN ({q()})",
                SLUG_LIST,
            )
        }
        missing = [s for s in SLUG_LIST if s not in present]

        print(f"Katalog toplamı: {total_before}")
        print(f"Kapsamdaki slug'lar: {len(SLUG_LIST)} — DB'de mevcut: {len(present)}")
        if missing:
            print(f"  (DB'de bulunamadı, atlanacak: {missing})")

        print("\n=== KURBAN LİSTESİ (katalogdan çıkacak) ===")
        rows = con.execute(
            f"SELECT cs.mangakol_slug, s.title, p.name,"
            f" (SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
            f"  WHERE v.series_id=s.id) AS listings"
            " FROM catalog_series cs JOIN series s ON s.id=cs.series_id"
            " LEFT JOIN publishers p ON p.id=s.publisher_id"
            f" WHERE cs.mangakol_slug IN ({q()}) ORDER BY s.title",
            SLUG_LIST,
        ).fetchall()
        total_listings = 0
        for slug, title, pub, n_list in rows:
            total_listings += n_list
            reason = next(r for s, r in SLUGS if s == slug)
            print(f"  {slug:<40} {title}  [{pub or '-'}] — {n_list} listing KORUNUR ({reason})")
        print(f"\nToplam korunacak listing: {total_listings} (veri SİLİNMEZ, manifest kapanır)")

        # İlgili import kayıtları (24h döngü için) — anahtar, app'in kendi
        # normalize_text() fonksiyonuyla üretilen Series.title anahtarıdır
        # (warmup'un kullandığı anahtar).
        from app.normalization.text import normalize_text

        titles = [
            r[0]
            for r in con.execute(
                "SELECT s.title FROM series s"
                f" WHERE s.id IN (SELECT series_id FROM catalog_series WHERE mangakol_slug IN ({q()}))",
                SLUG_LIST,
            )
        ]
        norm_queries = {normalize_text(t) for t in titles if normalize_text(t)}
        rec_count = con.execute(
            f"SELECT COUNT(*) FROM import_records WHERE normalized_query IN ({q()})",
            list(norm_queries),
        ).fetchone()[0]
        print(f"Ilgili import_records (silinecek, işlem geçmişi): {rec_count}")

        affected_ids = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT series_id FROM catalog_series"
                f" WHERE mangakol_slug IN ({q()})",
                SLUG_LIST,
            )
        ]
        snap_before = snapshot_affected(con, affected_ids)
        for t, (n, _) in snap_before.items():
            print(f"Pre  {t:<15} {n} satır")

        if not apply:
            print("\nDRY-RUN: hiçbir şey yazılmadı. Uygulamak için: --apply")
            return 0

        # --- Uygula ---
        if not Path(BAK).exists():
            shutil.copy2(DB, BAK)
            print(f"\nYedek alındı: {BAK}")
        else:
            print(f"\nYedek zaten var: {BAK} (üzerine yazılmadı)")

        con.execute(
            "CREATE TABLE IF NOT EXISTS catalog_exclusions ("
            " mangakol_slug VARCHAR(200) PRIMARY KEY,"
            " reason VARCHAR(300),"
            " added_at DATETIME NOT NULL)"
        )
        con.executemany(
            "INSERT OR IGNORE INTO catalog_exclusions (mangakol_slug, reason, added_at)"
            " VALUES (?, ?, ?)",
            [(s, r, now_iso()) for s, r in SLUGS],
        )
        cur = con.execute(
            f"DELETE FROM catalog_series WHERE mangakol_slug IN ({q()})", SLUG_LIST
        )
        deleted = cur.rowcount
        cur2 = con.execute(
            f"DELETE FROM import_records WHERE normalized_query IN ({q()})",
            list(norm_queries),
        )
        deleted_records = cur2.rowcount
        con.commit()

        # --- Assert ---
        excl = con.execute("SELECT COUNT(*) FROM catalog_exclusions").fetchone()[0]
        left = con.execute(
            f"SELECT COUNT(*) FROM catalog_series WHERE mangakol_slug IN ({q()})",
            SLUG_LIST,
        ).fetchone()[0]
        total_after = con.execute("SELECT COUNT(*) FROM catalog_series").fetchone()[0]
        snap_after = snapshot_affected(con, affected_ids)

        ok = True
        for t in snap_before:
            before, after = snap_before[t], snap_after[t]
            status = "OK" if before == after else "!!! EŞİT DEĞİL"
            if before != after:
                ok = False
            print(f"Post {t:<15} {after[0]} satır  ({status})")
        print(
            f"Assert: exclusions={excl} (>=18 {'OK' if excl >= 18 else 'FAIL'}), "
            f"manifest kalanı={left} (0 {'OK' if left == 0 else 'FAIL'}), "
            f"katalog {total_before}->{total_after} "
            f"({deleted} satır silindi {'OK' if deleted == len(present) else 'NOTES'})"
        )
        print(f"Silinen import_records: {deleted_records}")
        if not ok:
            print("ZERO-LOSS KONTROLÜ BAŞARISIZ — roll back önerilir (yedek: %s)" % BAK)
            return 2
        print("\nTAMAM — katalog artık %d seri; 18 giriş bloklendi ve veri korundu." % total_after)
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
