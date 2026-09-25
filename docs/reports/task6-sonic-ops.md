# Task 6 — Sonic dedup incelemesi + admin "Raf kapsaması" paneli (2026-09-16)

## 1. Sonic dedup: SONUÇ — GEREK KALMADI (kalem kapandı)

Inceleme (canlı DB + canlı mangakol):

* `series` / `catalog_series` / `publishers` / `store_listings` tablolarında
  "sonic" geçen **hiç kayıt yok** (title, normalized_title, slug, publisher —
  tüm kolonlar tarandı).
* Canlı mangakol.com katalog taraması (22 sayfa, 501 slug): **"sonic" geçen
  hiç manga yok.**
* Tek çoklu giriş örneği bilinen meşru vaka: iki "Berserk" serisi
  (id 1 = **Athica Yayınları** / slug `berserk-athica`,
  id 326 = **Gerekli Şeyler Yayıncılık** / slug `berserk-gerekli-seyler`).
  İki farklı yayınevinden basılmış baskılar — kullanıcı teyidi
  (2026-09-16): "normal, sıkıntı etme." Seri kimliği = yayıncı + başlık
  kuralı gereği bu ikili asla birleştirilmez; işlem gerekmez.

**Neden gerek kalmadı:** "Sonic dedup" kalemi, katalog-öncesi (task 2
denetimi) devirde farklı mağazalardan gelen Sonic ürünlerinin farklı
seriler olarak birikmesi sorununu işaret ediyordu. Task 4'ün katalog-sadece
kapsam kararında tüm katalog dışı veri silindi; Sonic mangakol kataloğunda
olmadığı için bu DB'de var olamaz. **Yapılacak hiçbir şey yok.**

## 2. Bonus: admin sayfasına "Raf kapsaması" paneli

`/admin` sayfası zaten vardı (katalog senkronu + mağaza içe aktarma + son 20
kayıt). Eksik olan: ısıtmanın/kapsamanın canlı özeti ve reset sonrası
kullanıcının kendi kendini ısıtabilmesi.

### Backend
* `GET /import/coverage` (`app/routes/import_.py`) — salt okunur özet:
  `catalog_series`, `series_with_listings`, `listings_total`,
  `records_total`, `records_by_status`, `fresh_records`,
  `freshness_ttl_minutes`. Herhangi bir scraping tetiklemez.
* Test: `tests/test_import_coverage.py` (3 test: boş DB, dolu raf +
  durum kırılımı, listeliksiz seri sayılmaz). **Suite: 409 → 412/412.**

### Frontend
* `types/index.ts`: `ImportCoverage` + `ImportRecord.status`'a `"skipped"`.
* `services/admin.ts`: `getImportCoverage()`, `warmupCatalog()`.
* `components/admin/AdminControls.tsx`: `CoveragePanel` — ilerleme çubuğu
  (fiyatlı seri/katalog), toplam listing, taze kayıt sayacı, durum kırılımı;
  iş çalışırken 20 sn'de bir otomatik tazelenir; **"Tüm katalogu ısıt"**
  butonu (POST /import/warmup, dedup-güvenli).
* Doğrulama: `tsc --noEmit` temiz; `/admin` SSR 200;
  `:3000/api/import/coverage` proxy'si uçtan uca çalışıyor.

## 3. O anki canlı durum (18:40)

* `catalog_series: 465`, `series_with_listings: 219 (47%)`,
  `listings_total: 4256`, taze kayıt: 47, çalışan iş: 8.
* Warmup, sandbox reset'leri yüzünden birden çok dalga halinde birikiyor;
  ilerleme DB'de kalıcı (her dalga ~40-100 seri tamamlıyor).
* API `api-server-fb649f33` (:8000, env 12h/24h/8 job),
  web `website-1275de05` (:3000).
