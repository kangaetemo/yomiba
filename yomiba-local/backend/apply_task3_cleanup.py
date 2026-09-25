"""Görev 3 — sonraki geçiş temizliği (KARAR: 2026-09-14 onaylı).

Dry-run raporu: docs/reports/task3-dry-run.md
Onay tablosu: 8+1 yayıncı emişi, 11 seri birleşmesi, 160 silme,
4 şüpheli BEKLEME (2287, 2394, 2404, 2407), 28 Karakarga KAL,
kara-karga alias'ı doğrulanarak eklendi (634 -> 713).

Güvenlik modeli (Görev 2 ile aynı):
* Önce yedek (dışarıdan: yomiba.db.bak-task3).
* TEK transaction; her adımda pre/post assert.
* Bir assert patlarsa TAMAM roll back edilir, DB değişmeden kalır.

Sıra (bunlar olmasa IntegrityError):
1. Seri birleştirmeleri  — varyant yayıncılar HÂLÂ AYRI satırlarken
   (yoksa UNIQUE(publisher_id, normalized_title) çakışması).
2. Çift baş başa çakışma kontrolü (her yayıncı çifti için 0 olmalı).
3. Yayıncı yeniden işaretleme + varyant satır silme.
4. 160 seri silme (catalog/wishlist/alert referanssız — pre'de doğrulandı).

Kod tarafı (alias tablosu + migration 0003 + resolver) BU scriptten ÖNCE
uygulanmış ve test edilmiştir; bu script yalnızca veri operasyonlarıdır.
"""

from __future__ import annotations

import sqlite3
import sys

DB = "yomiba.db"

# ---------------------------------------------------------------------------
# Onaylı veri kümeleri
# ---------------------------------------------------------------------------
HOLD = (2287, 2394, 2404, 2407)  # 4 şüpheli — BEKLETİLİR (dokunulmaz)

# (varyant satır id, hedef id, seri sayısı) — onaylı 11 emiş
PUB_MERGES = [
    (671, 2, 0),    # Gerekli Şeyler -> Gerekli Şeyler Yayıncılık
    (7, 204, 57),   # Komik Şeyler -> Komikşeyler Yayıncılık
    (667, 30, 1),   # Kurukafa Yayınevi -> Kurukafa
    (670, 633, 0),  # Akılçelen -> Akılçelen Kitaplar
    (668, 633, 0),  # Akıl Çelen Kitaplar -> Akılçelen Kitaplar
    (677, 11, 1),   # Kayıp Kıta Yayınları -> Kayıp Kıta
    (716, 239, 2),  # Presstij -> Presstij Kitap
    (504, 239, 2),  # Prestij -> Presstij Kitap
    (714, 133, 2),  # Eksik Parça -> Eksik Parça Yayınları
    (695, 433, 1),  # Penguin Books -> Penguin Books UK
    (634, 713, 2),  # Kara Karga Yayınları -> Karakarga (doğrulandı)
]

# SİL — onaylı 160 (programatik doğrulandı; gruplar kesişimsiz)
SINAV = [2291, 2292, 2297, 2298, 2299, 2301, 2304, 2305, 2307, 2311, 2312,
         2313, 2314, 2315, 2316, 2317, 2319, 2320, 2321, 2329, 2330, 2332,
         2333, 2334, 2339, 2390, 2398, 2399, 2400, 2405, 2416, 2417, 2418,
         2419, 2420, 2421, 2422, 2423, 2424, 2425, 2426, 2427]
DIN = [2331, 2336, 2337, 2406, 2408, 2409, 2410, 2411]
COCUK = [2221, 2222, 2233, 2234, 2242, 2247, 2251, 2260, 2265, 2270, 2271,
         2272, 2285, 2286, 2289, 2296, 2300, 2303, 2323, 2338, 2340, 2341]
ROMAN = [2217, 2219, 2220, 2223, 2224, 2225, 2226, 2227, 2228, 2230, 2231,
         2232, 2236, 2237, 2238, 2239, 2240, 2241, 2243, 2244, 2246, 2248,
         2249, 2250, 2252, 2253, 2254, 2255, 2257, 2258, 2259, 2261, 2262,
         2263, 2264, 2266, 2267, 2269, 2273, 2274, 2275, 2276, 2277, 2278,
         2279, 2280, 2281, 2282, 2284, 2288, 2290, 2293, 2294, 2302, 2306,
         2308, 2309, 2310, 2318, 2322, 2325, 2326, 2327, 2328, 2335, 2342,
         2343, 2344, 2345, 2347, 2348, 2366, 2391, 2392, 2393, 2395, 2397,
         2401, 2402, 2403, 2412, 2413, 2414, 2415, 2428, 2430, 2431, 2433]
DELETE_160 = SINAV + DIN + COCUK + ROMAN
assert len(DELETE_160) == 160, len(DELETE_160)
assert len(set(DELETE_160)) == 160, "yinelenen id!"
assert not set(DELETE_160) & set(HOLD)

# Beklenen ön sayımlar (snapshot 2026-09-14, task2 sonrası)
PRE_SNAP = {
    "series": 2276, "volumes": 4385, "store_listings": 3422,
    "price_history": 3468, "publishers": 646, "catalog_series": 469,
}

# Beklenen POST sayımlar
POST_SNAP = {
    "series": 2276 - 11 - 160,          # 2105
    "volumes": 4385 - 14 - 160,         # 4211 (14 = birleşmede silinen cilt)
    "store_listings": 3422 - 170 - 2,   # 3250 (2 = M8/M9 duplike cizman)
    "price_history": 3468 - 171,        # 3297 (M8/M9 history TAŞINDI)
    "publishers": 646 - 11,             # 635
    "catalog_series": 469,              # değişmez (slug taşımaları UPDATE)
}


def die(msg: str) -> None:
    print(f"HATA (pre): {msg}")
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
    for table, expected in PRE_SNAP.items():
        actual = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if actual != expected:
            die(f"{table} = {actual}, beklenen {expected} (DB değişti mi?)")

    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        die(f"beklenmeyen mevcut FK ihlali: {fk[:5]}")

    # Alias tablosu + seed (migration 0003)
    aliases = {r[0]: r[1] for r in con.execute(
        "SELECT normalized_alias, publisher_id FROM publisher_aliases")}
    expected_aliases = {
        "gerekli seyler": 2, "komik seyler": 204, "kurukafa yayinevi": 30,
        "akilcelen": 633, "akil celen kitaplar": 633,
        "kayip kita yayinlari": 11, "presstij": 239, "prestij": 239,
        "eksik parca": 133, "penguin books": 433, "kara karga yayinlari": 713,
    }
    if aliases != expected_aliases:
        die(f"alias seti beklenmedik: {aliases}")

    # Varyant yayıncı satırları: id -> (normalized_name, seri sayısı)
    variant_norm = {
        671: "gerekli seyler", 7: "komik seyler", 667: "kurukafa yayinevi",
        670: "akilcelen", 668: "akil celen kitaplar", 677: "kayip kita yayinlari",
        716: "presstij", 504: "prestij", 714: "eksik parca",
        695: "penguin books", 634: "kara karga yayinlari",
    }
    for src, tgt, cnt in PUB_MERGES:
        row = con.execute(
            "SELECT normalized_name, (SELECT COUNT(*) FROM series"
            " WHERE publisher_id=p.id) FROM publishers p WHERE p.id=?", (src,)).fetchone()
        if row is None or row[0] != variant_norm[src] or row[1] != cnt:
            die(f"varyant {src}: {row}, beklenen norm={variant_norm[src]!r} cnt={cnt}")
        if con.execute("SELECT 1 FROM publishers WHERE id=?", (tgt,)).fetchone() is None:
            die(f"hedef yayıncı {tgt} yok")

    # --- Seri birleşme verisi ---
    # (kaynak, hedef, kaynak volume id'leri [empty ise], hedef slug'suz olmalı)
    slug_moves = {
        156: "mahou-shoujo-madokamagica",
        287: "gekijouban-mahou-shoujo-madokamagica-shinpen-hangyaku-no-monogatari",
        210: "mahou-shoujo-madokamagica-majuu-hen",
        103: "blue-lock",
        381: "tougen-anki",
        213: "black-paradox",
    }
    for src, slug in slug_moves.items():
        got = con.execute(
            "SELECT mangakol_slug FROM catalog_series WHERE series_id=?", (src,)
        ).fetchone()
        if got is None or got[0] != slug:
            die(f"seri {src} slug beklenen {slug!r}, bulunan {got}")
    for tgt in (2102, 2100, 2101, 2149, 2150, 2245):
        if con.execute("SELECT 1 FROM catalog_series WHERE series_id=?", (tgt,)).fetchone():
            die(f"hedef {tgt} zaten katalog slug'una sahip")
    if con.execute("SELECT 1 FROM catalog_series WHERE series_id=831").fetchone():
        die("831 katalog slug'una sahip olmamalı (452'de)")

    # M1: 831 vol2 (listing'li + ISBN) -> 452 vol2 (boş)
    v831 = vol(con, 831, 2)
    if con.execute("SELECT isbn, (SELECT COUNT(*) FROM store_listings"
                   " WHERE volume_id=?) FROM volumes WHERE id=?", (v831, v831)).fetchone() != \
            ("9786255607379", 4):
        die("831 vol2 beklenen (9786255607379, 4 listing)")
    v452 = vol(con, 452, 2)
    if con.execute("SELECT isbn, (SELECT COUNT(*) FROM store_listings"
                   " WHERE volume_id=?) FROM volumes WHERE id=?", (v452, v452)).fetchone() != \
            (None, 0):
        die("452 vol2 boş + ISBN'siz olmalı")
    if n_listings(con, 452) != 7:
        die(f"452 listing = {n_listings(con, 452)}, beklenen 7")

    # M2/M3/M4: kaynak ciltleri BOŞ olmalı
    for src, vols in ((156, [1, 2, 3]), (287, [1, 2, 3]), (210, [1, 2, 3])):
        for vnum in vols:
            vid = vol(con, src, vnum)
            if con.execute("SELECT COUNT(*) FROM store_listings WHERE volume_id=?",
                           (vid,)).fetchone()[0] != 0:
                die(f"{src} vol {vnum} boş olmalı")
    if n_listings(con, 2102) != 19 or n_listings(con, 2100) != 17 or n_listings(con, 2101) != 17:
        die("Madoka hedefleri beklenen listing sayısında değil")
    # 2101'de vol 1 OLMAMALI (boş slot taşınacak)
    if con.execute("SELECT 1 FROM volumes WHERE series_id=2101 AND volume_number=1").fetchone():
        die("2101 vol 1 zaten var")
    # 2101/2100'ün -1 ciltleri var (boş kalır)

    # M5/M6: kaynak ciltlerinin HEPSİ boş olmalı
    for v in con.execute("SELECT id FROM volumes WHERE series_id=103"):
        if con.execute("SELECT COUNT(*) FROM store_listings WHERE volume_id=?",
                       (v[0],)).fetchone()[0] != 0:
            die("103 ciltleri boş olmalı")
    for v in con.execute("SELECT id FROM volumes WHERE series_id=381"):
        if con.execute("SELECT COUNT(*) FROM store_listings WHERE volume_id=?",
                       (v[0],)).fetchone()[0] != 0:
            die("381 ciltleri boş olmalı")
    if len(con.execute("SELECT id FROM volumes WHERE series_id=103").fetchall()) != 30:
        die("103'te 30 cilt olmalı")
    if len(con.execute("SELECT id FROM volumes WHERE series_id=381").fetchall()) != 8:
        die("381'de 8 cilt olmalı")
    if n_listings(con, 2149) != 1 or n_listings(con, 2150) != 1:
        die("2149/2150 tek listing'li olmalı")

    # M7: 213 vol1 boş; 2245 vol -1 ISBN'li
    v213 = vol(con, 213, 1)
    if con.execute("SELECT COUNT(*) FROM store_listings WHERE volume_id=?",
                   (v213,)).fetchone()[0] != 0:
        die("213 vol1 boş olmalı")
    if n_listings(con, 2245) != 3:
        die("2245 3 listing'li olmalı")

    # M8/M9: (store,url) duplike — sadece beklenen iki satır
    for src, tgt, src_listing, tgt_listing, url_frag in (
        (1549, 982, 1783, 1115, "cilt-13-imparatorluk"),
        (1548, 994, 1782, 1114, "tangle-whisper"),
    ):
        row = con.execute(
            "SELECT l.product_url, l.price FROM store_listings l WHERE l.id=?",
            (src_listing,)).fetchone()
        if row is None or url_frag not in row[0]:
            die(f"listing {src_listing} beklenmedik: {row}")
        tgt_row = con.execute(
            "SELECT l.product_url, l.price FROM store_listings l WHERE l.id=?",
            (tgt_listing,)).fetchone()
        if row[0] != tgt_row[0] or row[1] != tgt_row[1]:
            die(f"M{8 if src == 1549 else 9}: kaynak/hedef (url,price) aynı olmalı")
        if con.execute("SELECT COUNT(*) FROM price_history WHERE listing_id=?",
                       (src_listing,)).fetchone()[0] != 1:
            die(f"listing {src_listing} tek history satırlı olmalı")
    if n_listings(con, 982) != 6 or n_listings(con, 994) != 6:
        die("982/994 6 listing'li olmalı")
    # Beklenmedik başka (store,url) çakışması yok
    for src, tgt in ((831, 452), (156, 2102), (287, 2100), (210, 2101),
                     (103, 2149), (381, 2150), (213, 2245),
                     (1549, 982), (1548, 994), (2349, 2145), (2396, 2324)):
        n = con.execute(
            """SELECT COUNT(*) FROM store_listings a
               JOIN volumes va ON va.id=a.volume_id
               JOIN store_listings b ON b.store_id=a.store_id AND b.product_url=a.product_url
               JOIN volumes vb ON vb.id=b.volume_id
               WHERE va.series_id=? AND vb.series_id=?""", (src, tgt)).fetchone()[0]
        expected = 1 if src in (1549, 1548) else 0
        if n != expected:
            die(f"{src}->{tgt} (store,url) çakışması = {n}, beklenen {expected}")

    # M10: 2349 vol2 (2l + ISBN) -> 2145 (sadece vol1)
    v2349 = vol(con, 2349, 2)
    if con.execute("SELECT isbn, (SELECT COUNT(*) FROM store_listings"
                   " WHERE volume_id=?) FROM volumes WHERE id=?", (v2349, v2349)).fetchone() != \
            ("9786258502909", 2):
        die("2349 vol2 beklenen (9786258502909, 2)")
    if len(con.execute("SELECT id FROM volumes WHERE series_id=2145").fetchall()) != 1:
        die("2145 tek ciltli olmalı")

    # M11: 2396 vol-1 (ISBN + 1l) -> 2324 vol-1 (ISBN'siz, 1l)
    v2396 = vol(con, 2396, -1)
    if con.execute("SELECT isbn, (SELECT COUNT(*) FROM store_listings"
                   " WHERE volume_id=?) FROM volumes WHERE id=?", (v2396, v2396)).fetchone() != \
            ("9786057865083", 1):
        die("2396 vol-1 beklenen (9786057865083, 1)")
    v2324 = vol(con, 2324, -1)
    if con.execute("SELECT isbn, (SELECT COUNT(*) FROM store_listings"
                   " WHERE volume_id=?) FROM volumes WHERE id=?", (v2324, v2324)).fetchone() != \
            (None, 1):
        die("2324 vol-1 beklenen (NULL, 1)")

    # --- 160 silme ön kontrolü ---
    ph = ",".join("?" * 160)
    for q, expect in (
        (f"SELECT COUNT(*) FROM catalog_series WHERE series_id IN ({ph})", 0),
        (f"SELECT COUNT(*) FROM wishlist_items WHERE volume_id IN"
         f" (SELECT id FROM volumes WHERE series_id IN ({ph}))", 0),
        (f"SELECT COUNT(*) FROM price_alerts WHERE volume_id IN"
         f" (SELECT id FROM volumes WHERE series_id IN ({ph}))", 0),
        (f"SELECT COUNT(*) FROM volumes WHERE series_id IN ({ph})", 160),
        (f"SELECT COUNT(*) FROM store_listings l JOIN volumes v ON v.id=l.volume_id"
         f" WHERE v.series_id IN ({ph})", 170),
        (f"SELECT COUNT(*) FROM price_history p JOIN store_listings l ON l.id=p.listing_id"
         f" JOIN volumes v ON v.id=l.volume_id WHERE v.series_id IN ({ph})", 171),
        (f"SELECT COUNT(*) FROM series WHERE id IN ({ph})", 160),
    ):
        if con.execute(q, DELETE_160).fetchone()[0] != expect:
            die(f"160-silme ön kontrolü: {q[:60]}... = {con.execute(q, DELETE_160).fetchone()[0]}, beklenen {expect}")
    for h in HOLD:
        if con.execute("SELECT 1 FROM series WHERE id=?", (h,)).fetchone() is None:
            die(f"HOLD {h} yok — veri değişti")

    print(f"PRE OK: snapshot {PRE_SNAP}, 11 merge + 11 emiş + 160 silme doğrulandı")

    # ---------------- TRANSACTION ----------------
    con.execute("BEGIN")
    try:
        # --- 1) Seri birleştirmeleri ---
        # M1: 831 -> 452 (listing + ISBN -> 452 vol2)
        con.execute("UPDATE store_listings SET volume_id=? WHERE volume_id=?", (v452, v831))
        con.execute("DELETE FROM volumes WHERE id=?", (v831,))
        con.execute("UPDATE volumes SET isbn='9786255607379' WHERE id=?", (v452,))
        con.execute("DELETE FROM series WHERE id=831")

        # M2/M3/M4: Madoka üçlüsü (slug taşı + boş ciltler)
        con.execute("UPDATE catalog_series SET series_id=2102 WHERE series_id=156")
        con.execute("DELETE FROM volumes WHERE series_id=156")
        con.execute("DELETE FROM series WHERE id=156")

        con.execute("UPDATE catalog_series SET series_id=2100 WHERE series_id=287")
        con.execute("DELETE FROM volumes WHERE series_id=287")
        con.execute("DELETE FROM series WHERE id=287")

        con.execute("UPDATE catalog_series SET series_id=2101 WHERE series_id=210")
        con.execute("UPDATE volumes SET series_id=2101 WHERE id=?", (vol(con, 210, 1),))
        con.execute("DELETE FROM volumes WHERE series_id=210")
        con.execute("DELETE FROM series WHERE id=210")

        # M5: 103 -> 2149 (29 boş slot taşınır; kaynak vol15 silinir)
        con.execute("UPDATE catalog_series SET series_id=2149 WHERE series_id=103")
        moved_103 = [r[0] for r in con.execute(
            "SELECT id FROM volumes WHERE series_id=103 AND volume_number != 15")]
        assert len(moved_103) == 29
        con.executemany("UPDATE volumes SET series_id=2149 WHERE id=?",
                        [(v,) for v in moved_103])
        con.execute("DELETE FROM volumes WHERE series_id=103")  # kalan: vol 15
        con.execute("DELETE FROM series WHERE id=103")

        # M6: 381 -> 2150 (7 boş slot; kaynak vol5 silinir)
        con.execute("UPDATE catalog_series SET series_id=2150 WHERE series_id=381")
        moved_381 = [r[0] for r in con.execute(
            "SELECT id FROM volumes WHERE series_id=381 AND volume_number != 5")]
        assert len(moved_381) == 7
        con.executemany("UPDATE volumes SET series_id=2150 WHERE id=?",
                        [(v,) for v in moved_381])
        con.execute("DELETE FROM volumes WHERE series_id=381")  # kalan: vol 5
        con.execute("DELETE FROM series WHERE id=381")

        # M7: 213 -> 2245 (boş vol1 slot taşınır)
        con.execute("UPDATE catalog_series SET series_id=2245 WHERE series_id=213")
        con.execute("UPDATE volumes SET series_id=2245 WHERE id=?", (v213,))
        con.execute("DELETE FROM series WHERE id=213")

        # M8/M9: Sonic — history taşı, duplike listing + cilt + seri sil
        con.execute("UPDATE price_history SET listing_id=1115 WHERE listing_id=1783")
        con.execute("DELETE FROM store_listings WHERE id=1783")
        con.execute("DELETE FROM volumes WHERE id=?", (vol(con, 1549, 13),))
        con.execute("DELETE FROM series WHERE id=1549")

        con.execute("UPDATE price_history SET listing_id=1114 WHERE listing_id=1782")
        con.execute("DELETE FROM store_listings WHERE id=1782")
        con.execute("DELETE FROM volumes WHERE id=?", (vol(con, 1548, -1),))
        con.execute("DELETE FROM series WHERE id=1548")

        # M10: 2349 vol2 -> 2145 (cilt satırıyla)
        con.execute("UPDATE volumes SET series_id=2145 WHERE id=?", (v2349,))
        con.execute("DELETE FROM series WHERE id=2349")

        # M11: 2396 -> 2324 (listing + ISBN)
        con.execute("UPDATE store_listings SET volume_id=? WHERE volume_id=?", (v2324, v2396))
        con.execute("DELETE FROM volumes WHERE id=?", (v2396,))
        con.execute("UPDATE volumes SET isbn='9786057865083' WHERE id=?", (v2324,))
        con.execute("DELETE FROM series WHERE id=2396")

        # --- 2) 160 silme (repoint ÖNCESİ: 2290/1868 'a clockwork orange'
        # çifti repoint sonrası 433/433 çakışması olurdu; 2290 silince gider) ---
        con.execute(f"DELETE FROM series WHERE id IN ({ph})", DELETE_160)

        # --- Çift baş başa çakışma kontrolü (repoint ÖNCESİ, silme SONRASI) ---
        for src, tgt, _ in PUB_MERGES:
            n = con.execute(
                "SELECT COUNT(*) FROM series a JOIN series b"
                " ON a.normalized_title=b.normalized_title"
                " WHERE a.publisher_id=? AND b.publisher_id=?", (src, tgt)).fetchone()[0]
            if n:
                raise AssertionError(f"{src}->{tgt}: {n} aynı normalize başlık!")

        # --- 3) Yayıncı emişleri ---
        for src, tgt, _ in PUB_MERGES:
            con.execute("UPDATE series SET publisher_id=? WHERE publisher_id=?", (tgt, src))
        con.execute("DELETE FROM publishers WHERE id IN (671,7,667,670,668,677,716,504,714,695,634)")

        # ---------------- POST ASSERTIONS (commit ÖNCESI) ----------------
        for table, expected in POST_SNAP.items():
            actual = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if actual != expected:
                raise AssertionError(f"POST {table} = {actual}, beklenen {expected}")

        # Sıfır kayıp: birleşme hedeflerinde beklenen listing'ler
        if n_listings(con, 452) != 11:   # 7 + 4 (831 vol2)
            raise AssertionError(f"452 = {n_listings(con, 452)}, beklenen 11")
        if n_listings(con, 2102) != 19 or n_listings(con, 2100) != 17 or n_listings(con, 2101) != 17:
            raise AssertionError("Madoka hedefleri listing kaybı")
        if n_listings(con, 2149) != 1 or n_listings(con, 2150) != 1:
            raise AssertionError("2149/2150 listing kaybı")
        if n_listings(con, 2245) != 3:
            raise AssertionError("2245 listing kaybı")
        if n_listings(con, 982) != 6 or n_listings(con, 994) != 6:
            raise AssertionError("Sonic 982/994 listing kaybı")
        if n_listings(con, 2145) != 4:   # vol1 2l + vol2 2l
            raise AssertionError(f"2145 = {n_listings(con, 2145)}, beklenen 4")
        if n_listings(con, 2324) != 2:   # 1l (store4) + 1l (store8)
            raise AssertionError(f"2324 = {n_listings(con, 2324)}, beklenen 2")

        # Cilt haritaları
        b1 = {r[0] for r in con.execute("SELECT volume_number FROM volumes WHERE series_id=2149")}
        if b1 != set(range(1, 31)):
            raise AssertionError(f"2149 ciltler: {sorted(b1)}")
        ta = {r[0] for r in con.execute("SELECT volume_number FROM volumes WHERE series_id=2150")}
        if ta != set(range(1, 9)):
            raise AssertionError(f"2150 ciltler: {sorted(ta)}")
        kp = {r[0] for r in con.execute("SELECT volume_number FROM volumes WHERE series_id=2245")}
        if kp != {-1, 1}:
            raise AssertionError(f"2245 ciltler: {sorted(kp)}")

        # ISBN'ler yerinde
        checks = {
            vol(con, 452, 2): "9786255607379",
            vol(con, 2145, 2): "9786258502909",
            vol(con, 2324, -1): "9786057865083",
        }
        for vid, isbn in checks.items():
            got = con.execute("SELECT isbn FROM volumes WHERE id=?", (vid,)).fetchone()[0]
            if got != isbn:
                raise AssertionError(f"vol {vid} isbn {got!r} != {isbn!r}")

        # History taşındı (M8/M9: hedefte 1 kendi + 1 taşınan = 2 satır)
        for lid in (1115, 1114):
            n = con.execute("SELECT COUNT(*) FROM price_history WHERE listing_id=?",
                            (lid,)).fetchone()[0]
            if n != 2:
                raise AssertionError(f"listing {lid} history = {n}, beklenen 2")
        # Kaynak listing'lerin history'si artık hedefte (kaynak silindi)
        if con.execute("SELECT COUNT(*) FROM store_listings WHERE id IN (1783,1782)").fetchone()[0] != 0:
            raise AssertionError("duplike cizman listing'leri hâlâ var")

        # Slug'lar hedefte
        slug_map = {r[0]: r[1] for r in con.execute(
            "SELECT mangakol_slug, series_id FROM catalog_series WHERE mangakol_slug IN"
            " ('mahou-shoujo-madokamagica',"
            " 'gekijouban-mahou-shoujo-madokamagica-shinpen-hangyaku-no-monogatari',"
            " 'mahou-shoujo-madokamagica-majuu-hen','blue-lock','tougen-anki',"
            " 'black-paradox','akagami-no-shirayukihime','black-torch')")}
        expected_slugs = {
            "mahou-shoujo-madokamagica": 2102,
            "gekijouban-mahou-shoujo-madokamagica-shinpen-hangyaku-no-monogatari": 2100,
            "mahou-shoujo-madokamagica-majuu-hen": 2101,
            "blue-lock": 2149, "tougen-anki": 2150, "black-paradox": 2245,
            "akagami-no-shirayukihime": 452, "black-torch": 2145,
        }
        if slug_map != expected_slugs:
            raise AssertionError(f"slug haritası: {slug_map}")

        # Yayıncı emişleri doğrula
        for src, tgt, _ in PUB_MERGES:
            if con.execute("SELECT 1 FROM publishers WHERE id=?", (src,)).fetchone():
                raise AssertionError(f"varyant yayıncı {src} hâlâ var")
        if con.execute("SELECT publisher_id FROM series WHERE id=2371").fetchone()[0] != 204:
            raise AssertionError("2371 (Komik Şeyler) 204'e işaretlenmemiş")
        if con.execute("SELECT publisher_id FROM series WHERE id=2011").fetchone()[0] != 713:
            raise AssertionError("2011 (Kara Karga Yayınları) 713'e işaretlenmemiş")
        if con.execute("SELECT publisher_id FROM series WHERE id=2324").fetchone()[0] != 713:
            raise AssertionError("2324 713'e işaretlenmemiş")

        # Silinenler yok, HOLD'lar var
        gone = con.execute(
            f"SELECT id FROM series WHERE id IN ({ph})", DELETE_160).fetchall()
        if gone:
            raise AssertionError(f"silinecekler hâlâ var: {gone[:5]}")
        for h in HOLD:
            if con.execute("SELECT 1 FROM series WHERE id=?", (h,)).fetchone() is None:
                raise AssertionError(f"HOLD {h} silinmiş!")
        for m in (831, 156, 287, 210, 103, 381, 213, 1549, 1548, 2349, 2396):
            if con.execute("SELECT 1 FROM series WHERE id=?", (m,)).fetchone():
                raise AssertionError(f"merge kaynağı {m} hâlâ var")

        # Alias'lar sağlam
        if len(con.execute("SELECT 1 FROM publisher_aliases").fetchall()) != 11:
            raise AssertionError("alias kayıpları var")

        # Bütünlük
        orphans = con.execute(
            "SELECT COUNT(*) FROM store_listings l LEFT JOIN volumes v ON v.id=l.volume_id"
            " WHERE v.id IS NULL").fetchone()[0]
        if orphans:
            raise AssertionError(f"{orphans} yetim listing")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            raise AssertionError(f"FK ihlali: {fk[:5]}")

        print("POST ASSERT (commit öncesi) TAMAMI OK")
        con.commit()
    except AssertionError as exc:
        con.rollback()
        print(f"ROLLBACK — POST-ASSERT: {exc}")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        con.rollback()
        print(f"ROLLBACK — {type(exc).__name__}: {exc}")
        sys.exit(1)

    con.close()
    print("POST OK:")
    print(f"  seri {2276} -> {POST_SNAP['series']} | cilt {4385} -> {POST_SNAP['volumes']}")
    print(f"  listing {3422} -> {POST_SNAP['store_listings']} | history {3468} -> {POST_SNAP['price_history']}")
    print(f"  yayıncı {646} -> {POST_SNAP['publishers']} | katalog {469} (değişmedi)")
    print("  11 seri merge, 11 yayıncı emişi, 160 silme, 4 HOLD — commit edildi.")


if __name__ == "__main__":
    main()
