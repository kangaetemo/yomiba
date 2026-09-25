# TASK 4 — Legacy Temizlik + Mangakol 12saat Sync — UYGULANDI

**Durum: UYGULANDI + DOĞRULANDI (2026-09-14).** Yedekler:
`backend/yomiba.db.bak-task4` (temizlik öncesi), `yomiba.db.bak-task4b`
(duplikat onarımı öncesi).

## 1. Kapsam kararı

İnce kırımlı sınıflandırma (ilk dry run: 755 KEEP / 35 REVIEW / 1253 SİL)
kullanıcı tarafından revize edildi. **Son karar (2026-09-14, option
"katalog-sadece"):** yalnızca mangakol kataloğuyla bağlı seriler kalsın;
katalogdaki 14 yanlış eşleşme de temizlensin. "Diğer ne varsa boşverelim."

## 2. Temizlik (tek transaction, `apply_task4_cleanup.py`)

| İşlem | Adet |
|---|---:|
| Silinen seri (katalog-dışı) | 1636 |
| Silinen seri (14 katalog yanlış eşleşmesi, 0 listing) | 14 |
| **Toplam silinen** | **1650** |
| **Kalan seri = kalan katalog satırı** | **455** |

Silinenlerin içinde (onaylı kapsam): 61 wave serisi (28 Karakarga, JJK Viz 6,
Batman 2, Guardian 3, Komikşeyler 4, Winx…), 4 held (2287 Karanlığın Kızı,
2394/2404/2407 Kara X), 1253 eski SİL + 314 katalog-dışı manga (Athica 97,
Gerekli Şeyler 84, Tokyo Manga 37, Presstij 31, Viz 24, Seven Seas 22…).
Geri istenirse `bak-task4`'ten alınır.

**Doğrulama:** post = series 455 / vols 2306 / listings 1031 / history 1034 /
catalog 455; orphan 0; **zero-loss** (KAL setindeki 1031 listing + 1034
history, id+price+checked_at birebir; SİL kalıntısı 0); FK temiz;
testler 384/384 (5 task-2 identity testi yeni kapsama göre güncellendi).

## 3. Mangakol 12 saatte bir kontrol

Mevcut P26 altyapısı yeterli çıktı: `CatalogSyncService` (additif, idempotent,
hata-izole) + `CatalogSyncScheduler` (daemon thread). **API
`CATALOG_SYNC_INTERVAL_HOURS=12` ile 09:35'te başlatıldı:**
log `catalog scheduler started (first run in 12.0h, then every 12.0h)`.
Manuel tetik `POST /catalog/sync` · durum `GET /catalog/sync/status`.

### İlk sync + yakalanan hata + onarım

**09:22 manuel sync (eski kodla):** 465 manga, 0 hata, 71 seri açıldı.
Doğrulama sırasında **61'inin duplikat** olduğu bulundu:
* 51 × yayıncı varyantı: mangakol "Komik Şeyler" (iç boşluk) → fuzzy eşleşme
  "Komikşeyler Yayıncılık"ı bulamadı → 716 twin satırı + 51 twin seri.
* 10 × başlık farkı: "Jujutsu Kaisen - Lanet Savaşları" / "Jujutsu Kaisen",
  "Orange - Portakal" / "Orange", "Tougen Anki: …" / "Tougen Anki - …",
  "Kara Meşale" (eski satırın normalize hatalı yazımı: 'kara mesele').
* 14 × mangakol'un katalogda manga olarak listeliği kitaplar (aşağıda).

**Onarım (`fix_task4_sync_duplicates.py`):** 61 duplikat slug-grubu bazında
keeper'a (listing'li seri) eritildi (volume add-only, 243 çakışık volume
atıldı), 61 catalog satırı silindi, 716 yayıncı silindi. Post: series 465 =
catalog 465 = benzersiz slug 465; zero-loss.

**Kod düzeltmeleri (`app/services/catalog_sync.py`, 3 katman):**
1. **Slug-first kimlik** — `_merge_manga`: slug manifestte varsa (hangi
   yayıncı/başlık varyantı olursa olsun) O seriye merge; twin açılamaz.
2. **Alias tablosu** — `_resolve_publisher` artık `publisher_aliases`'e
   bakar (ImportService ile aynı mekanizma; 'komik seyler'→204 alias'ı
   task 3'ten beri var, catalog sync göremiyordu).
3. **Boşluk-kör yayıncı eşleşmesi** — `_names_related`: iç boşluklu Türkçe
   bileşikler için boşluksuz önek karşılaştırma (≥6 karakter + harf
   sınırı; "athica"/"athica2x" hâlâ eşleşmez).

**3 yeni test** (test_catalog_sync.py) eklendi.

### Doğrulama sync (09:35, yeni kod)

`465 manga · 0 hata · 0 seri açıldı · 465 merge · 3 yeni cilt · 5 yayıncı
satırı konsolide` — aynı katalog ikinci kez sıfır duplikat üretti.

## 4. Son DB durumu

| Metrik | Değer |
|---|---:|
| series | **465** (= mangakol kataloğu 1:1) |
| catalog_series (benzersiz slug) | 465 |
| volumes | 2330 |
| store_listings | 1031 |
| price_history | 1034 |
| publishers | 627 (537 legacy yayınevi referans olarak duruyor) |
| orfan seri | 0 |

## 5. Notlar / kalan işler

* **14 "kitap" sayfası:** mangakol, İlahi Komedya, Kapital, Savaş ve Barış,
  Türlerin Kökeni, Komünist Manifesto, Kavgam (Mein Kampf), Alacakaranlık
  (Twilight), Warcraft ×2, Starcraft, Yengeç Gemisi, Psi-Kom, Gannibal, Ölüm
  Tınısı başlıklarını KENDİ kataloğunda manga olarak listeliyor; sync bu
  kaynak sadakatiyle açtı (0 listing, yalnızca mangakol ciltleri).
  "mangakol = tek kaynak" kuralına göre **kaldılar**; istenirse sync'e
  slug-bloklaması eklenip silinebilir (1 satırlık karar).
* Scheduler process restart'ında sıfırlanır (tur aralığı [12h, 24h)
  garantili). Servisler env reset'inde düşer → yeniden başlat:
  API `CATALOG_SYNC_INTERVAL_HOURS=12 python3 -m uvicorn app.main:app
  --host 0.0.0.0 --port 8000` (backend/), Web `npx next dev -H 0.0.0.0
  -p 3000` (frontend/).
* Store import hâlâ katalog-dışı seri üretebilir (spec: ImportService
  değişmez); bunlar aramada görünmez (manifest tasarımı) ama DB'de birikir
  → ileride "katalog-dışı serileri periyodik sil" adayı.
* Sonic kümesi dedup'ı, R6 SEO, E2E doğrulama, Amazon/English manga: parked.
