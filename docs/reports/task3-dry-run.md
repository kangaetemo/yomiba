# Görev 3 — Sonraki Geçiş: Yayıncı Varyantları + Dalganın Temizliği
## DRY-RUN RAPORU → **UYGULANDI** (2026-09-14)

Tarih: 2026-09-14 · Durum: **KAPANDI** — onay tablosu uygulanıp doğrulandı.
Önceki aşamalar: [task1-merch-filter.md](task1-merch-filter.md) ·
[task2-dry-run.md](task2-dry-run.md)

**UYGULAMA SONUCU (GERÇEK — uygulama sonrası ölçüldü):**

| | dry-run (öngörü) | uygulama (gerçek) |
|---|---|---|
| Seri | ~2101* | **2105** (2276 − 11 merge − 160 silme; *öngörü 164 silme varsaymıştı, onayda 4 BEKLEME ile 160 oldu) |
| Cilt | — | **4211** (4385 − 14 merge − 160 silme) |
| Listing | ~3256 | **3250** (3422 − 170 silme − 2 duplike cizman) |
| Price-history | — | **3297** (3468 − 171; M8/M9'ların 2 history satırı TAŞINDI) |
| Yayıncı | ~706 | **635** (646 − 11; ayrıca 634→713 = 12 emişten 11 satır) |
| Katalog satırı | 469 | **469** (değişmedi; 6 slug UPDATE ile taşındı) |
| Migration | 0003 | **0003_publisher_alias** (head; 11 alias seed'li) |

**Sıfır kayıp doğrulaması (yedek `yomiba.db.bak-task3` karşılaştırması):**
listing farkı 170 anahtar (tam silme seti; 2 duplike aynı (store,url) olduğu
içer setten görünmez), history farkı 171 (tam silme seti), seri farkı 171
(160 + 11 merge kaynağı). Beklenmedik kayıp: YOK.

**Uygulama notları (dry-run'dan sapmalar):**
1. `kara karga yayinlari` alias'ı doğrulanarak eklendi: web kontrolü
   (hepsiburada/kitapsec marka sayfaları) "Kara Karga Yayınları" ile
   "Karakarga"nın aynı şirket olduğunu doğruladı (Destek Medya bünyesi;
   Kazazedeler/Erkek Bedeni/Sıradan Zaferler her iki yazımda listeli) →
   634 (2 seri) → 713 (26 seri) emildi, alias seed'lendi.
2. Alias anahtar düzeltmesi: 670 "Akılçelen" normalize hali `akilcelen`
   (tek kelime) — pre-assert yakaladı, seed + migration düzeltildi.
3. Sıra düzeltmesi: 160 silme, yayıncı repoint'ten ÖNCE yapıldı —
   2290 (Penguin Books) ile 1868 (Penguin Books UK) "a clockwork orange"
   repoint sonrası 433/433 çakışması yapacaktı; 2290 silince gider.
4. Yeni gözlem (aksiyon GEREKMEZ): 365 (Komik Şeyler→204) ↔ 307
   (Gerekli Şeyler Yayıncılık) "titana saldiri cokusten once" — farklı
   yayıncı = farklı baskı, politika gereği ayrı kalır.
5. Testler: **384/384** (377 + 7 yeni: migration seed/idempotency, resolver
   birebir/alias/yeni/yetim, varyant-yayıncı entegrasyon). API yeni kodla
   yeniden başlatıldı; canlı doğrulama: 2105 seri, 4 HOLD sağlam, 0 kalan
   varyant yayıncı, 11 alias, slug'lar hedeflerde (Madoka 2102/2100/2101,
   Blue Lock 2149 30 cilt, Kara Meşale 2145 2 cilt, Low 1 2324 → Karakarga).

**AÇIK MADDELER (sonraki geçiş):**
- 4 şüpheli BEKLEME: 2287 Karanlığın Kızı, 2394 Kara Alaz, 2404 Kara Atena,
  2407 Kara Kıtanın Talanı (karar: kullanıcı incelemesinde).
- Dalga-öncesi eski manga-dışı kitaplar (karar: sonraki geçiş).
- "Bilinmiyor" adlı yayıncı satırı (id 27) — unknown-publisher hedefi;
  birleşme adayı değil, not.

---

Kapsam: (A) yayıncı varyant emişleri, (B) kök-nedenin kod ayağı (alias
mekanizması), (C) 11 seri birleşmesi, (D) 224'lük içe aktarma dalgasının
sınıflandırması (58 kal / 2 birleş / 164 sil → 160 sil + 4 bekletildi).

---

## A) Yayıncı varyant emişleri (veri ayağı)

`ImportService._resolve_publisher` isme BİREBİR göre çalışır; eşleşmeyen
yayıncı adı için **yeni satır + yeni seri** açar — 227'lik dalganın kök
nedeni. Bilinen varyant çiftleri:

| Hayatta kalan (hedef) | Serisi | Emilecek varyant | Serisi |
|---|---|---|---|
| 2 `Gerekli Şeyler Yayıncılık` | 85 | 671 `Gerekli Şeyler` | 0 |
| 204 `Komikşeyler Yayıncılık` | 13 | 7 `Komik Şeyler` | 57 |
| 30 `Kurukafa` | 7 | 667 `Kurukafa Yayınevi` | 1 |
| 633 `Akılçelen Kitaplar` | 23 | 670 `Akılçelen`, 668 `Akıl Çelen Kitaplar` | 0 + 0 |
| 11 `Kayıp Kıta` | 43 | 677 `Kayıp Kıta Yayınları` | 1 |
| 239 `Presstij Kitap` | 31 | 716 `Presstij`, 504 `Prestij` | 2 + 2 |
| 133 `Eksik Parça Yayınları` | 4 | 714 `Eksik Parça` | 2 |
| 433 `Penguin Books UK` | 4 | 695 `Penguin Books` | 1 |

**8 yayıncı, 11 varyant satırı.** Emilirken seri satırları hedef yayıncıya
yeniden işaretlenir; varyant satırları silinir.

> ⚠️ **Yalnızca veri emişi YETMEZ:** sonraki içe aktarmada mağaza başlığı
> yine "Gerekli Şeyler" / "Komik Şeyler" diye gelecek, birebir eşleşme yine
> kaçar, yeni yayıncı + yeni seri yine doğar. Kalıcı çözüm **B)** maddesi.

## B) Kök nedenin kod ayağı: `publisher_aliases` (ONAY İSTENİYOR)

- **Yeni tablo:** `publisher_aliases(normalized_alias TEXT PRIMARY KEY,
  publisher_id INTEGER NOT NULL REFERENCES publishers(id) ON DELETE CASCADE)`
  — Alembic migration `0003_publisher_alias` (R4 iş akışına uygun).
- **`_resolve_publisher` sırası:** birebir eşleşme → **alias eşleşmesi** →
  yeni satır (mevcut davranış). Kodda HARDCODE eşleme YOK; alias'lar veridir
  ("publisher mapping asla hardcode edilmez" kuralına uygun).
- **Seed alias'lar (11):** `gerekli seyler→2`, `komik seyler→204`,
  `kurukafa yayinevi→30`, `akil celen→633`, `akil celen kitaplar→633`,
  `kayip kita yayinlari→11`, `presstij→239`, `prestij→239`,
  `eksik parca→133`, `penguin books→433`, `kara karga yayinlari→(Low'un
  yayıncı kimliği belirlenince)` — 10 hazır + 1 açık.
- **Testler:** resolution (birebir/alias/yeni), migration testi, "alias'lı
  içe aktarma yeni seri açmaz" entegrasyon testi.
- ImportService'in **yazma/manifest davranışı değişmez**; yalnızca yayıncı
  çözümleme genişler. (Görev 1'in "ImportService'e dokunma" sınırı o
  görevin kapsamındaydı; bu madde ayrı onaylı.)

## C) Seri birleştirmeleri (11 — hepsi yüksek güven)

A emişleri bu çiftleri "aynı yayıncı" yapar; sonra seri birleşir
(survivor = verisi olan; slug verili seriye taşınır; (store,url)
çakışmaları uygulama öncesi yeniden doğrulanır):

| # | Kaynak | → Hedef | Kanıt / not |
|---|---|---|---|
| 1 | 831 Pamuk Prenses (1c/4l) | 452 (3c/7l, slug) | aynı iş; ISBN bandı aynı |
| 2 | 156 Madoka Magica (3c/0l, slug) | 2102 (4c/19l) | slug `mahou-shoujo-madokamagica` |
| 3 | 287 Madoka - Bir İsyan Öyküsü (3c/0l, slug) | 2100 (4c/17l) | slug `gekijouban-…-hangyaku-no-monogatari` |
| 4 | 210 Madoka - Hayaletlerin Ayaklanması (3c/0l, slug) | 2101 (3c/17l) | slug `…-majuu-hen` |
| 5 | 103 Blue Lock (30c/0l, slug) | 2149 (1c/1l) | slug `blue-lock` |
| 6 | 381 Tougen Anki: (8c/0l, slug) | 2150 (1c/1l) | slug `tougen-anki` |
| 7 | 213 Kara Paradoks (1c/0l, slug) | 2245 (1c/3l, ISBN 9786259324074) | slug `black-paradox` |
| 8 | 1549 Sonic: İmparatorluk İçin Savaş (1c/1l) | 982 (1c/6l, ISBN 9786256033986) | duplike listing kontrolü |
| 9 | 1548 Sonic: Tangle Whisper (1c/1l) | 994 (1c/6l, ISBN 9786256033993) | duplike listing kontrolü |
| 10 | 2349 Black Torch-Kara Meşale (vol 2, ISBN 9786258502909, 2l) | 2145 Kara Meşale (vol 1, ISBN …2725) | **Görev 2 kümesinin dalgada doğan vol 2'si** |
| 11 | 2396 Low 1: Umut Hezeyanı Kara (1l, ISBN 9786057865083) | 2324 Low 1: Umut Hezeyanı (1l) | aynı cilt; ISBN hedefe backfill + 2. mağaza |

**FARKLI BASKI = AYRI SERİ (birleşTİRİLMEZ — bilinçli karar):**
Batman 2235 (…8229) / 2353 (…8236) · Clockwork Orange 1868 / 2290 ·
Kara Paradoks 2245 (…074) / 2429 (…098; kitapsec URL'leri farklı:
942168/942129) · Beyblade 241 / 524 · Tomie 132 / 292 · Berserk 1 / 22 /
326 · One Piece 2 / 1040.

## D) 224 dalganın sınıflandırılması (2207–2433; 2212/2357/2389 zaten işlendi)

### KAL — manga / manga-benzeri (58)
| id | başlık | yayıncı | not |
|---|---|---|---|
| 2207 | Vinland Sagaları | İmge | TR baskı (Kurukafa'dan ayrı) |
| 2208, 2209, 2210, 2211, 2213, 2214 (+2214'un Bilinmoins kaydı) | Jujutsu Kaisen (Viz seti, 7 seri) | Viz Media | EN manga + guidebook/roman |
| 2215, 2216, 2218 | Yan Karakter (3 varyant) | Guardian | TR çizgi roman |
| 2229 | Spider-Man Noir: Karanlık Kökenler | Marmara Çizgi | |
| 2235, 2353 | Batman: Kara Ayna (karton + sert kapak) | JBC | 2 baskı, ikisi de kalır |
| 2245, 2429 | Kara Paradoks (+ 2. baskı) | Kayıp Kıta / Bilinmiyor | 2 baskı, ikisi de kalır |
| 2256, 2268, 2371, 2372 | Mucize: Uğur Böceği Chibi 1–4 | Komikşeyler / Komik Şeyler | 4 ayrı kitap |
| 2283 | Tetrasia – Kara Alev ile Safir Gölge | Odessa | |
| 2295 | Green Lantern – Karanlık | Arka Bahçe | DC çizgi |
| 2324 (+2396 birleşir) | Low 1: Umut Hezeyanı | Kara Karga | manga (Mitsuru Adachi) |
| 2346 | Kara Ada – Tenten'in Maceraları | Alfa | çizgi roman |
| 2350, 2351, 2352, 2354, 2355, 2356, 2358, 2359, 2360, 2361, 2362, 2363, 2364, 2365, 2367, 2369, 2370, 2374, 2377, 2378, 2379, 2380, 2382, 2383, 2385, 2386, 2387, 2388 | Pervane, Göl Kenarındaki Hoş Ev, Kara Büyü (çizgi), Anzu, Blast, Zamanya, Tüy Yumağı, Yol (+Ciltli), İnsanını Nasıl Eğitirsin?, Kanat İle Tayga, Kazazedeler, Genç Mustafa, ECE, Karikatürler, KAI, Bela Lugosi, Erkek Bedeni, Worldtr33, Parker, Ayışığında Kadınlar, Yojimbot, Brodeck Raporu, Sıradan Zaferler, Stillwater, Aristo, Yağmur (Joe Hill) | **Karakarga** (28) | TR çizgi roman yayıncısı — hepsi kalır (istisna işaretlenebilir) |
| 2368 | Kötü Karakterin Yükselişi, Clz | Bilinmiyor | "Clz" = çizgi |
| 2373 | Canavar Adası Okulu – Karaya Vuranlar | Büyülü Fener | çocuk çizgi *(İNCELE)* |
| 2375, 2381 | Karadut Ekspres 1–2 | Presstij | |
| 2376 | Bloodborne Karanlık Diyar | Eksik Parça | |
| 2384 | En Kahraman Rıdvan – Bay Karanlık | Marmara Çizgi | |
| 2432 | Winx Club – Karanlığın Esiri (vol 5) | Bilinmiyor | çocuk çizgi *(İNCELE)* |

### BİRLEŞ (2) — 2349 → 2145, 2396 → 2324 (tablo C #10–11).

### SİL — manga-dışı (164)
Tümü dalganın bugünkü ürünleridir; her biri 1 listing taşır (liste
programatik üretilip tek tek gözden geçirildi):

**Sınav/ders (42):** 2291, 2292, 2297, 2298, 2299, 2301, 2304, 2305, 2307,
2311, 2312, 2313, 2314, 2315, 2316, 2317, 2319, 2320, 2321, 2329, 2330,
2332, 2333, 2334, 2339, 2390, 2398, 2399, 2400, 2405, 2416, 2417, 2418,
2419, 2420, 2421, 2422, 2423, 2424, 2425, 2426, 2427
**Din/akademik (8):** 2331, 2336, 2337, 2406, 2408, 2409, 2410, 2411
**Çocuk/çıkartma/renkli (22):** 2221, 2222, 2233, 2234, 2242, 2247, 2251,
2260, 2265, 2270, 2271, 2272, 2285, 2286, 2289, 2296, 2300, 2303, 2323,
2338, 2340, 2341
**Roman/öykü/genel (92):** 2217, 2219, 2220, 2223, 2224, 2225, 2226, 2227,
2228, 2230, 2231, 2232, 2236, 2237, 2238, 2239, 2240, 2241, 2243, 2244,
2246, 2248, 2249, 2250, 2252, 2253, 2254, 2255, 2257, 2258, 2259, 2261,
2262, 2263, 2264, 2266, 2267, 2269, 2273, 2274, 2275, 2276, 2277, 2278,
2279, 2280, 2281, 2282, 2284, 2287, 2288, 2290, 2293, 2294, 2302, 2306,
2308, 2309, 2310, 2318, 2322, 2325, 2326, 2327, 2328, 2335, 2342, 2343,
2344, 2345, 2347, 2348, 2366, 2391, 2392, 2393, 2394, 2395, 2397, 2401,
2402, 2403, 2404, 2407, 2412, 2413, 2414, 2415, 2428, 2430, 2431, 2433

Toplam: 42 + 8 + 22 + 92 = **164** (programatik doğrulandı, gruplar
kesişimsiz, 224'ün tam bölünmesi).

> "Roman/öykü/genel" grubundaki birkaçı İNCELE (varsayılan SİL):
> **2287** Karanlığın Kızı (Eksik Parça — çizgi de olabilir), **2394** Kara
> Alaz, **2404** Kara Atena, **2407** Kara Kıtanın Talanı. Kullanıcı
> listeye bakarken bunları "kal"a çekerse onayda belirtir.

**Silme etkisi:** seri + cilt + listing + price-history birlikte gider;
yedek `yomiba.db.bak-task2b`'de kalır.

## E) Beklenen etki (tahmin — uygulama sonrası doğrulanacak)

| | şimdi | sonra |
|---|---|---|
| Yayıncı | ~717 | ~706 (−11) |
| Seri | 2276 | **2101** (−11 birleşme kaynağı −164 silme) |
| Listing | 3422 | ~3256 (−164 silme) |
| Migration | 0002 | **0003_publisher_alias** |

Uygulama sırası (tek transaction + pre/post assert, önce yedek):
1. Yayıncı emişleri (seriler yeniden işaretlenir, varyant satırları silinir)
2. 11 seri birleşmesi (slug taşımaları, listing taşımaları, ISBN backfill)
3. 164 silme
4. Alias seed satırları (son — emilen adlar artık alias)
5. Migration + kod + testler (ayrı adım, ayrı onay gerektirmez; B onayıyla gelir)

## F) ONAY İSTENEN KARARLAR

1. **D tablosu:** 164 silme + 58 kal + 4 "incele" (varsayılan sil) —
   onaylı mı? İstisna varsa id'lerini yazın.
2. **B maddesi:** `publisher_aliases` tablosu + migration +
   `_resolve_publisher` alias adımı — onaylı mı? (kalıcı kök-neden düzeltmesi)
3. **Karakarga (28 seri):** TR çizgi roman yayıncısı — hepsi kalsın mı?
4. **Dalga-ÖNCESİ eski manga-dışı kitaplar** (Sherlock Holmes kümeleri,
   romantik romanlar, eski soru bankaları vb.): (a) dokunma, (b) sonraki
   geçişte aynı sınıflandırmayla temizlik, (c) şimdi bu işe ekle.
