# Task 5 — Aramada beklememe: katalog-sadece içe aktarma + fiyat tazeleme

**Tarih:** 2026-09-14 · **Durum:** UYGULANDI + KANITLANDI (402/402 test; canlı doğrulama aşağıda)

## 1. Sorun

Kullanıcı şikâyeti: *"ne ararsam senkronize etmesini bekliyorum mecbur."*

Kök neden analizi (kod okuma):

1. **Katalogu ıskalayan sorgular ölüm döngüsüne giriyordu.** `/search` DB'den
   anında cevap veriyordu ama katalogda eşleşme yoksa `search_service` bir
   arka plan içe aktarması başlatıyordu ve API `"importing"` state'i
   döndürüyordu. Frontend bu durumda **"Katalog hazırlanıyor…"** ekranını
   gösterip 8 sn'de bir tekrar soruyordu. Ama arama **katalog-sadece**
   olduğundan (sonuçlar yalnızca `catalog_series` manifestinde olan serileri
   gösterir), bu içe aktarma **asla görünür sonuç üretemiyordu** — birkaç
   dakikalık bekleme hep boşlukla bitiyordu.
2. **TTL (60 dk) etkisi:** katalogu vuran bir arama bile, son içe aktarma
   60 dk'dan eskiyse arka plan yenileme tetikliyordu; fiyatlar 1–5 dk içinde
   geliyordu (sonuç görünürdü ama "güncelleniyor" banner'ı durmadan
   yeniden tetikleniyordu).

## 2. Çözümler (3 parça)

### 2.1 Katalog-sadece içe aktarma politikası — `app/services/search_service.py`

- Arka plan içe aktarması **yalnızca sorgu katalogda eşleşme bulduysa**
  başlatılıyor (`if matches and not fresh and not running ...`).
- Katalogu ıskalayan sorgu → `"idle"`: dürüst "katalogda yok" durumu, **hiç
  iş yok, hiç scraping yok, hiç kayıt yok**.
- `_state()` basitleştirildi: `idle` (eşleşme yok) / `refreshing`
  (eşleşme + iş çalışıyor/yeni başlatıldı) / `fresh` / `stale`.
  `"importing"` ve `"failed"` state'leri artık emit edilmiyor (API
  uyumluluğu için enum'da ve frontend'de korundu, ama catalog-sadece
  politika altında ulaşılmaz).

**Etkisi:** "Katalog hazırlanıyor…" ekranı fiilen ortadan kalktı. Arama ya
anında sonuç gösterir (fiyat eskiyse arka planda tazeleyerek) ya da anında
"Katalogda bulunamadı" der.

### 2.2 Tüm katalog sıcak başlatma — `POST /import/warmup` (`app/routes/import_.py`)

- Tüm `catalog_series` serilerinin başlığı için arka plan fiyat içe
  aktarması kuyruğa alır (runner'ın sorgu-bazlı dedup'u tekrar çağrıya karşı
  güvenli).
- Yanıt: `{"total": 461, "queued": 461}` (465 serinin 461 benzersiz başlığı).
- Amacı: warmup bitince **herhangi bir katalog mangası aranır anında fiyat
  listesi bulur** — ilk tarama beklemez.

### 2.3 Fiyat tazeleme zamanlayıcısı — `app/services/price_refresh_scheduler.py` (YENİ)

- `CatalogSyncScheduler` aynısı: daemon thread, ilk tur işlem başlangıcından
  **1 tam interval sonra** (catch-up yok), her interval'da `tick()`.
- `tick()`: tüm `ImportRecord` satırlarına bakar; son başarılı içe aktarma
  `import_freshness_ttl_minutes` (60 dk)'dan eskiyse sorguyu mevcut
  `BackgroundImportRunner`'a yeniden gönderir.
- Anti-dövme kuralları değişmez: çalışanda tekrar gönderme (runner dedup),
  son denemesi `import_failure_retry_minutes` (5 dk) penceresinde olanı
  atla, sınırlı eşzamanlılık (semaphore), katalog yazı kilidi gate'i.
- Warmup'tan sonra 461+ sorgu kaydının tümü bu zamanlayıcının kapsamına
  girer → **6 saatte bir tam tur**: fiyatlar sürekli taze kalır, arama
  istek anında scraping tetiklemek durumunda neredeyse hiç kalmaz.

### 2.4 Yapılandırma — `app/config.py`

| Env | Varsayılan | Açıklama |
|---|---|---|
| `PRICE_REFRESH_ENABLED` | `1` | fiyat tazeleme zamanlayıcısını aç/kapat |
| `PRICE_REFRESH_INTERVAL_HOURS` | `6` | tazeleme turu aralığı |
| `IMPORT_MAX_CONCURRENT_JOBS` | (mevcut, 2→**4** env ile) | eşzamanlı içe aktarma işi |

### 2.5 Frontend — `components/SearchSection.tsx`

- Boş sonuç metni dürüst hale getirildi: "Katalogda bulunamadı" +
  "Katalog yalnızca mangakol.com'dan beslenir ve her 12 saatte bir
  güncellenir — yeni seriler bir sonraki senkronda eklenir."
- Eski "importing"/"failed" boş durum dalları savunmacı olarak korundu
  (API artık emit etmiyor).

## 3. Testler

**Suite: 402/402** (önceki 387 + 15 yeni; 4 test yeni politikaya göre
güncellendi).

Yeni testler:
- `tests/test_price_refresh_scheduler.py` (15): taze kayıt atlanır; eski
  kayıt saklanan `last_query` metniyle yeniden gönderilir; retry penceresi
  içindeki deneme atlanır; dışındaki yeniden gönderilir; hiç denenmemiş
  kayıt gönderilir; çalışandaki key tekrar gönderilmez; boş tablo no-op;
  ilk interval'dan önce tur yok; döngü tur çökmesine karşı dayanıklı;
  `start()` idempotent; lifespan bağlantı testleri (auto_init=True →
  çalışır + temiz kapanır, flag kapalı → None, auto_init=False → asla
  kurulmaz).
- `tests/test_api.py::test_import_warmup_queues_every_catalog_series`
  (2 katalog serisi → total=2, queued=2, işler biter),
  `test_import_warmup_empty_catalog` (boş → 0/0, hata yok).
- `tests/test_auto_import.py::test_db_miss_no_import_catalog_only`
  (eşleşmesiz sorgu: iş yok, scraper çağrılmadı, kayıt yok, `idle`),
  `test_db_miss_with_old_failed_record_stays_idle` (eski failed kayıt bile
  `idle` — asla `failed`, asla iş).

Güncellenen testler (politika değişimi):
- `test_db_miss_triggers_import` → `test_db_miss_no_import_catalog_only`
- `test_concurrent_identical_queries_single_import` (state `importing`→`idle`;
  dedup kontrolü aynı)
- `test_partial_scraper_success_retained` (katalog seed'li: `refreshing` →
  partial kayıt → `fresh`; 2 listing korunur)
- `test_import_status_represented_correctly` (katalog seed'li: `fresh` +
  "1 güncellendi" detail)
- `test_api.py::test_search_no_results_reports_importing` →
  `test_search_no_results_reports_idle`
- `test_import_lock.py::test_manual_import_409_while_background_running`
  (arka plan işi artık `runner.submit` ile başlatılır — search
  endpoint'i katalog-sadece olduğu için)

## 4. Canlı doğrulama (2026-09-14 ~10:55)

API yeniden başlatıldı (`api-server-fb47b9db`, env:
`CATALOG_SYNC_INTERVAL_HOURS=12`, `PRICE_REFRESH_INTERVAL_HOURS=6`,
`IMPORT_MAX_CONCURRENT_JOBS=4`):

```
yomiba.catalog.scheduler: catalog scheduler started (first run in 12.0h, then every 12.0h)
yomiba.price_refresh:     price refresh scheduler started (first run in 6.0h, then every 6.0h)
```

| Kontrol | Sonuç |
|---|---|
| `POST /import/warmup` | `{"total": 461, "queued": 461}` |
| `GET /search?q=nonexistent-manga-xyz` | **anında** `{"results":[],"status":{"state":"idle"}}` — iş yok, kayıt yok, scraping yok |
| `GET /search?q=Berserk` (via :3000 proxy) | anında 3 seri (19+4+3 cilt), state `refreshing` (warmup işi çalışıyordu) |
| `GET /search?q=frieren` (via :3000 proxy) | anında sonuç, state **`fresh`**, detail "18 yeni, 27 güncellendi; 2 mağazaya ulaşılamadı" — warmup işi tamamlanmış |
| Warmup ilerlemesi (40 dk) | 27 iş bitti; 7–8/9 mağaza başarılı (beklenen tek hata: D&R 403 bot duvarı) |

Web sunucusu yeniden ayağa kaldırıldı (`website-c952538f`, :3000; env reset
node_modules'u silmişti, `npm install` ile yeniden kuruldu).

## 5. İşletme notları

- **Warmup bir seferlik çalıştırıldı ve ~1,5–2 saate yayıldı** (461 iş × ~50
  sn / 4 paralel). Tamamlanınca her katalog araması hazır veri bulur.
- **6 saatte bir tazeleme** artık otomatik: aynı iş havuzundan, aynı
  kilidelerden; katalog senkronuyla çarpışmaz (write gate + 409 mantığı
  değişmedi).
- İstemci tarayıcıda: arama yap → ya kartlar anında (fiyatlar taze) ya
  kartlar + ince "Katalog güncelleniyor" banner'ı. **"Katalog hazırlanıyor…"
  ekranı katalog dışı sorgularda bir daha gelmez** — yerine dürüst
  "Katalogda bulunamadı".
- Manuel tetiklemek istersen: `curl -X POST http://127.0.0.1:8000/import/warmup`
  (dedup güvenli; koşanları atlar).
- İlerleme: `sqlite3 yomiba.db "SELECT status, COUNT(*) FROM import_records
  WHERE last_attempt_at > datetime('now','-1 hour') GROUP BY status"`.

## 6. Bilinen sınırlar (kasıtlı, kapsam dışı)

- Katalogdaki serinin **orijinal adıyla** arama, yalnızca o ad
  `original_title` alanında ise eşleşir (mangakol'un eklediği orijinal
  başlık — ör. "Tokyo Ghoul" → "Tokyo Gül" çalışır; Japonca/İngilizce
  varyasyonlar da `original_title`'a girerse çalışır).
- 12 saatlik katalog senkronu ile arada çıkan **yeni** bir mangakol mangası
  aranırsa "Katalogda bulunamadı" der; bir sonraki senkronla eklenir
  (dürüst davranış, artık bekleme döngüsü yok).

## 7. ImportService → catalog-only (task 5, ikinci parça — kullanıcı onaylı 9 maddelik plan)

### Neden
İlk warmup (461 seri) eski ImportService davranışıyla katalogda OLMAYAN
mağaza ürünleri için ~1600 yeni Series + 300 Publisher satırı yarattı
(DB: 465 → 2079 seri). Bu, task 4'te silinen türün geri gelmesiydi.
Karar: **import hiçbir zaman yeni Series/Publisher oluşturamaz**; katalog
serilerini bulamadığı sonucu **skip** eder.

### Değişiklikler — `app/services/import_service.py`
* `_resolve_publisher` → **`_find_publisher` (sadece-okunur)**: mevcut
  satırı (normalize ad) veya `publisher_aliases` üzerinden canonical
  satırı bulur; bulamazsa `None` döner — **yayıncı satırı oluşturulmaz**.
* `_resolve_series` ikiye bölündü, ikisi de **katalog manifestiyle
  filtreli** (`Series.id IN (SELECT series_id FROM catalog_series)`) ve
  `None` dönebilir:
  * `_resolve_series_for_publisher` — (yayıncı, normalize başlık)
    edisyon kimliği → çift dilli köprü → None.
  * `_resolve_series_no_publisher` — tek açık katalog adayı → köprü → None.
* **Bilinmeyen yayıncı iddiası** (sattır "Dark Horse" diyor ama o satır
  yok): yalnızca **çift dilli köprü** (başlık-tabanlı, belirsiz kimlik)
  denenir; düz başlık eşleşmesi farklı bir edisyona birleştirme YAPMAZ
  (edison kimliği korunur).
* `_create_series` / `_unique_slug` **kaldırıldı** (import artık seri
  oluşturamaz).
* ISBN yolu: ISBN bir cilde çözülenürse, o cildin serisi **katalogda
  olmalı**; değilse skip (ISBN kimlik mantığı değişmedi).
* **Değişmeyenler:** ISBN > edisyon > başlık önceliği, cilt oluşturma
  (katalog serisinin yeni cildi listelenmeye devam eder), listing upsert,
  PriceHistory, katalog senkronu (kendi `_create_series`'ini kullanır).

### Doğrulama (regression testler)
* Mağaza katalog-dışı ürün döndürür → **0 yeni series, 0 yeni publisher**,
  aksiyon `SKIPPED` (`test_non_catalog_product_creates_nothing`).
* Katalogdaki Berserk + mağaza listing'i → cilt + listing oluşur
  (`test_catalog_berserk_gets_listing`, `test_catalog_new_volume_is_added`).
* Farklı publisher/edition → identity kuralları: bilinmeyen edisyon skip
  (`test_unknown_publisher_edition_is_skipped`), ISBN yayıncı iddiasına
  kazanır, çift edisyon asla birleşmez (`test_identity_dedup` B/C).
* Çift dilli köprü katalog serisine çalışmaya devam eder
  (`test_bilingual_title_bridges_to_catalog_series`); belirsiz köprü
  reddedilir → skip.
* Suite: **408/408** (önceki 405 + 3 yeni catalog-only test; 20+ test yeni
  politikaya göre seed'i katalog öncesi olacak şekilde güncellendi).

## 8. Tek seferlik katalog-dışı temizlik (`apply_task5_cleanup.py`)

Güvenlik modeli task 2/3/4 ile aynı: önce yedek (`yomiba.db.bak-task5`),
`--dry-run` modu, TEK transaction, pre/post assert, patlamada tam
rollback, zero-loss checksum.

| Metrik | Sonuç |
|---|---|
| Silinen katalog-dışı seri | 1614 |
| Silinen cilt / listing / history | 1973 / 2231 / 2259 |
| Silinen yayıncı (YALNIZCA warmup yetimi; bak-task4b'de olmayan + alias hedefi olmayan) | 324 |
| Korunan referans yayıncı (task 3/4 onaylı küme) | 585 |
| **Son seri** | **465 == katalog manifesti (birebir doğrulandı)** |
| Son yayıncı | 629 |
| Katalog volume/listing/history | zero-loss (sha256 pre/post) |

## 9. Warmup yeniden başlatıldı (katalog-only kodla)

`POST /import/warmup` → 461 seri kuyruğa. İlk ~10 dk:

* **series: 465 (sabit) — 0 yeni seri**
* **publishers: 629 (sabit) — 0 yeni yayıncı**
* Örnek tamamlanan işler: Gantz → 93 yeni listing; Tomie → 88 güncelleme;
  katalog dışı eşleşmeler skip (results_found > created+updated).
* Katalog listing sayısı 1031 → 3242'ye yükseldi ve yükseliyor.

## 10. Son durum / işletme

* API: `api-server-b3d36a97` (:8000), env `CATALOG_SYNC_INTERVAL_HOURS=12
  PRICE_REFRESH_INTERVAL_HOURS=6 IMPORT_MAX_CONCURRENT_JOBS=4`.
* Warmup arka planda (~1-2 saat); bitince her katalog araması hazır veri
  bulur. 6 saatte bir tazeleme zamanlayıcısı fiyatları taze tutar; artık
  hiçbir tur çöp seri üretmez.
* Yedekler: `yomiba.db.bak-task5` (temizlik öncesi, 2079 seri),
  `yomiba.db.bak-task4`/`.bak-task4b` (önceki görevler).

## 11. Isletme notu — hızlandırma (2026-09-14 12:25)

* Warmup 4 paralelde ~1 iş/dk gidiyordu (7 canlı store + detail enrichment
  + 2 kalıcı bloklu store: D&R 403, Amazon 503). `IMPORT_MAX_CONCURRENT_JOBS=8`
  ile **~8-9 iş/dk** (86/461 @ 12:25, tahmini bitiş ~13:15).
* 8 paralel yazar için `build_engine`'e SQLite `connect_args["timeout"]=30`
  eklendi (varsayılan 5 sn; test motoruyla aynı değer) — "database is locked"
  yerine yazan taraf 30 sn'ye kadar bekler.
* Environment reset'leri (venv/node_modules/süreç kaybı) 2 kez yaşandı;
  her seferinde venv + node_modules yeniden kuruldu, API/web yeniden
  başlatıldı, warmup yeniden kuyruğa alındı (dedup güvenli). DB dosyası
  hiç etkilenmedi.

## 12. Pool-exhaustion olayı + kalıcı düzeltme (2026-09-14 13:00-13:25)

Env reset #5 (venv + node_modules + süreçler silindi; DB sağlam) sonrası
warmup yeniden kuyruğa alındı ve ilk dalga 10 dk boyunca **sessizce çöktü**:
tüm 461 iş, ilk DB işleminde `QueuePool limit of size 5 overflow 10 reached,
connection timed out` ile öldü — üstelik hata kaydına bile ulaşamadan
(fresh-check'ın sessiz except'i), o yüzden DB'de iz kalmadı.

Kök neden tek başına kesinleştirilemedi (tam uygulama + gerçek scraper'larla
3 tekrar denemesinde pool 682/682 checkout/checkin ile tamamen dengeli kaldı),
ama olay 3 gerçek zayıflığı ortaya çıkardı ve hepsi düzeltildi:

1. **Sızıntı** — `BackgroundImportRunner._execute`'in fresh-skip yolu
   session'ı `close()`'lamadan `return` ediyordu (GC'ye emanet connection).
   Tek `try/finally: session.close()` ile kapatıldı.
2. **Pool headroom** — `build_engine`'e dosya tabanlı SQLite için
   `pool_size=10, max_overflow=20` eklendi (8 paralel import job'u +
   request/scheduler thread'leri için; `:memory:` test motorları etkilenmez).
3. **Sessiz ölüm** — fresh-check başarısız olan iş artık en azından
   best-effort `failed` kaydı bırakıyor ("içe aktarma başlatılamadı
   (DB hatası)"); iş kayıtsızca buharlaşamaz. Regresyon testi eklendi
   (`test_auto_import.py::test_startup_db_failure_leaves_visible_failed_record`,
   suite 408 → **409/409**).

## 13. Çalışma periyotları — nihai (kullanıcı kararı, 2026-09-14)

| Döngü | Periyot | Not |
|---|---|---|
| Mangakol katalog senkronu | **12 saat** | `CATALOG_SYNC_INTERVAL_HOURS=12`; yalnızca mangakol.com, mağaza yok |
| Mağaza fiyat tazelemesi | **24 saat** | `PRICE_REFRESH_INTERVAL_HOURS=24`; her tick'te ~461 başlık ≈ ~1 saat arka plan scraping |
| Kullanıcı araması | anlık | TTL (60 dk) geçmişse o başlık o an arka planda tazelenir; 5 dk anti-hammering |

Aktif süreçler: API `api-server-4d2ebd57` (:8000, env 12h/24h/8 job),
web `website-53fcd1b6` (:3000). Warmup (3. yeniden kuyruklama) 13:24 başlatıldı.
