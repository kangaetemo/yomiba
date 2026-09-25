# Yomiba — Yeni Store Adayları Araştırması (2026-09-10)

**Uygulamanın amacı (kullanıcıdan, 2026-09-10):** Sadece Berserk değil; Türkiye'de bulunabilen
**Türkçe + İngilizce mangaların seri bazında fiyat/stok takibi** (böyle bir site yok). Store
seçiminde kataloğun her iki dildi de kapsaması önemli.

**Kapsam:** BKM dışında fiyat karşılaştırılmasına uygun Türkçe kitap/manga store'u bulmak.
**Yöntem:** 17 aday, düz HTTP istemcisi (tek browser UA, cookie/stealth yok), canlı probe:
home + arama sayfası + ürün sayfası + platform API'leri + robots.txt. Hiçbir bot duvarı,
CAPTCHA veya erişim kontrolü aşılMADI; 403/503/CAPTCHA/JS-only durumlar "erişilemez"
olarak kaydedildi. Tüm sonuçlar 2026-09-10 itibarıyla geçerlidir.

## Sonuç Özeti

| Aday | Durum | Not |
|---|---|---|
| **kitapsepeti.com** | ✅ **KULLANILABİLİR** | SSR arama + ürün sayfasında JSON-LD (ISBN, fiyat, stok) |
| **gerekliseyler.com.tr** | ✅ **KULLANILABİLİR** | Manga-özel, SSR arama + ürün sayfaları, stok durumu kartta |
| **cizman.com** | ✅ **KULLANILABİLİR** | Ticimax; SSR arama (POST) + SSR kategori (57 sayfa) + ürün sayfası ISBN/JSON-LD |
| **kitapsec.com** | ✅ **KULLANILABİLİR** | SSR arama, **schema.org microdata** (name+sku=ISBN+fiyat+URL), sayfalama |
| **kitapbulan.com** | ✅ **KULLANILABİLİR** | Kitapsepeti ile **aynı CMS**: SSR arama kartları + ürün sayfası JSON-LD (ISBN/fiyat/stok); TR+EN manga (One Piece, JJK, Frieren); Berserk Cilt 1 stokta |
| **komikseyler.com.tr** | ✅ **KULLANILABİLİR (API)** | WooCommerce Store API **halka açık**, tamamen yapılandırılmış JSON |
| **edessakitabevi.com** | 🟡 KISMEN | Ürün sayfaları SSR+JSON-LD (ISBN/fiyat/stok ✓) ama arama JS-only, kategoride SSR'siz "devamı" |
| arkabahce.com.tr | 🟡 JS-only | Nuxt SPA; sonuçlar client-side, düz istemciyle alınmıyor |
| pandora.com.tr | 🟡 JS-only | Next.js; arama sonuçları JS ile yükleniyor (CF proxy ama challenge yok) |
| kidega.com | 🟡 JS-only + captcha işareti | sonuçlar server-side yok |
| trendyol.com | 🔴 JS-only + ağır koruma | 200 döner ama sonuçlar SPA; pratik değeri yok |
| kitapyurdu.com | 🔴 403 + CF **managed challenge** | JS+cookie challenge sayfası; www/apex/http/robots/sitemap/arama hepsi 403; m./static. NXDOMAIN, cdn. 403 (2026-09-10 iki kez doğrulandı) |
| hepsiburada.com | 🔴 403 captcha | "Güvenlik" duvarı |
| n11.com | 🔴 403 Cloudflare | bot duvarı |
| paralelevrencr.com | 💀 **bozuk** | SSL sertifika uyuşmazlığı (www ve apex) — TLS doğrulamalı istek imkânsız |
| papirazz.com.tr | 💀 **ölü** | NXDOMAIN — domain artık yok (DoH ile doğrulandı, sandbox sorunu değil) |
| vatankitap.com | 💀 **ölü** | SERVFAIL — küresel DNS hatası |
| pttkitap.com | 💀 **ölü** | SERVFAIL |
| idefix.com.tr | 💀 ölü | TLS hatası, site kapalı |
| marmaracizgi | ℹ️ **site değil** | Yayınevi; ürünleri komikseyler.com.tr + edessa gibi store'larda satılıyor |
| amazon.com.tr | 🔴 503 (biliniyor) | P24.5: Creators API → 10 nitelikli satış şartı |
| dr.com.tr | 🔴 403 (biliniyor) | P24.5: API yok, partnership gerekir |
| bkmkitap.com | ✅ (mevcut) | baseline doğrulaması: arama 200, 4 berserk hit |

## ✅ Kullanılabilir Kaynaklar — Detay

### 1) Kitap Sepeti (kitapsepeti.com) — **birinci aday**
- **Arama:** `GET /arama?q=<term>` → 200, **server-side rendered**, sayfa başına ~38 kart.
  Kartta: başlık ("Berserk 18"), yayınevi (Athica Yayınları), yazar (Kentaro Miura),
  liste fiyatı + indirimli fiyat ("280,00 TL" üstü çizili → "182,00 TL"), ürün URL'si
  (`/berserk-18`).
- **Ürün sayfası:** `GET /berserk-18` → 200; **JSON-LD `Product+Book`**:
  ```json
  {"@type":["Product","Book"], "name":"Berserk 18", "isbn":"9786258858051",
   "publisher":{"@type":"Organization","name":"Athica Yayınları"},
   "inLanguage":"Turkish", "numberOfPages":"244",
   "offers":{"@type":"Offer","priceCurrency":"TRY","price":"182.00",
             "priceSpecification":{"price":"280.00"},
             "availability":"https://schema.org/InStock"}}
  ```
  → **ISBN + fiyat + stok durumu tek yapılandırlanmış bloktan** alınır.
- Kapsam: Berserk (Athica) cilt 16-19 mevcut; `/berserk-1` 404 (rafta yok → listing
  oluşmaz, beklenen davranış).
- **robots.txt:** `User-agent: * Allow: /` (content-signal: search=yes). Dikkat:
  `User-agent: Python` ve `Wget` Disallow → scraper UA'sı varsayılan python UA **değil**,
  mevcut app UA kullanılmalı (zaten öyle). `/ajax.php`, `/SecCode.php*` disallowed —
  kullanmıyoruz.
- Açık uçlar (implementasyonda çözülecek): arama sayfalama parametresi (UI var,
  `?page=` denendi ama tek sayfaya sığan sorguda ayırt edilemedi), "stokta yok"
  kartlarının görünümü (stok durumu ürün sayfası JSON-LD'den doğrulanacak).

### 2) Gerekli Şeyler (gerekliseyler.com.tr) — **ikinci aday (manga-özel)**
- Komikşeyler grubunun (komikseyler.com.tr ile aynı grup) manga/çizgi roman mağazası.
- **Arama:** `GET /arama/<term>` → 200, **SSR**; kartlarda fiyat + **stok durumu**
  ("stokta yok"/"tükendi" işaretleri — berserk aramasında ~38 kartın 18'i tükendi).
  Sayfalama: `?tp=<n>` (`rel=next` ile doğrulandı).
- **Ürün:** `GET /urun/berserk-cilt-1` → 200, SSR; HTML'de **ISBN
  (9786256335424 = Berserk Cilt 1, BKM verimizle aynı ISBN!)** ve
  "Stok Durumu: **Yok**" alanı. Fiyat: 280,00 → 238,00 TL.
- Kapsam: tam Berserk serisi (cilt 1-18) listeleniyor.
- Platform: IdeaSoft/WAW (BKM ile aynı aile).
- **robots.txt:** `User-agent: * Allow: /` — tamamen açık.

### 3) Komikşeyler (komikseyler.com.tr) — **üçüncü aday (temiz API)**
- **WooCommerce Store API halka açık** (HTML parse gerektirmez):
  - `GET /wp-json/wc/store/v1/products?search=<term>&per_page=N` → JSON
  - `GET /wp-json/wc/store/v1/products?category=<id>&per_page=N`
  - `GET /wp-json/wc/store/v1/products/categories`
  - Ürün alanları: `name`, `sku`, `is_in_stock`, `permalink`, `images`,
    `prices: {price:"17500" (KURUŞ), regular_price, sale_price, currency_code:"TRY"}`
- Kapsam: manga-özel ama **niş** — Drifters, Vanitas, Tougen Anki, Kızıl Saçlı Pamuk
  Prenses, Beyblade…; **Berserk/One Piece/Naruto raflarında YOK** (search= ile
  doğrulandı). BKM ile **tamamlayıcı** kaynak.
- ISBN alanı Store API'de görünmüyor (`sku` içinde kodlanmış olabilir —
  implementasyonda doğrulanacak); eşleştirme ISBN yoksa "normalize edilmiş seri+cilt
  (tek aday)" kuralına düşer.
- **robots.txt:** yalnız wp-admin/log dosyaları disallow; ürünler ve wp-json açık.

### 4) Cizman (cizman.com) — **dördüncü aday (Ticimax, manga-özel)**
- **Arama:** sitedeki **halka açık arama formu** (ASP.NET, `POST /` + `ctl00$YeniHeader$txtbxArama`
  + sayfadan alınan `__RequestVerificationToken`) → 200, SSR sonuç. "berserk" → 107 kart;
  **Berserk 18 (₺224,00/₺280,00) ve Berserk 19 (₺208,00/₺260,00) stokta**, Frieren, Mushoku Tensei,
  Gachiakuta, Hotarunun Yolculuğu…
- **Kategori:** `/manga-turkce`, `/manga-yabanci`, `/manga-japonca` → SSR + **`?sayfa=N` (57 sayfa!)**
- **Kart:** `ItemOrj` içinde başlık (title attr), marka (`productMarka`), indirimli + liste fiyat
  (₺ virgüllü), `%indirim`, ürün slug'u (`/berserk-19`).
- **Ürün sayfası:** 200, SSR; HTML'de **ISBN** + JSON-LD `Product` (name, image, description).
- **robots.txt:** yalnız /Print/, /Handlers/, /Uploads/languages/, /Templates/ disallow —
  arama/ürün/kategori açık.
- Risk: arama POST + token istiyor (normal form davranışı; her istek öncesi ana sayfadan
  token alınması gerekebilir — implementasyonda doğrulanacak).

### 5) Kitapsec (kitapsec.com) — **beşinci aday (SSR microdata)**
- KPSS/sınav kitabı ağırlıklı bir store ama **manga kataloğu da var**: "berserk" araması
  → 113 hit; **Berserk Cilt 1-19 (Athica) tam seride**.
- **Arama:** `GET /Arama/index.php?a=<term>` → 200, SSR; sonuç satırları **schema.org
  microdata** ile işaretli:
  `itemtype=schema.org/Product` → `itemprop=name` ("Berserk Cilt 1 Athica Yayınları"),
  `itemprop=sku` (**ISBN** 9786256335424), `itemprop=url`, `itemprop=price` (196.00 TRY).
  Sayfalama: `arama=1-<N>-0a0-0-0-0-0-0` (1,2,3… sayfaları link olarak sayfada).
- Fiyat formatı: noktalı ("196.00").
- **robots.txt:** `User-Agent: * Allow: /` — tamamen açık.

### 6) Kitapbulan (kitapbulan.com) — **altıncı aday (kitapsepeti ile aynı CMS, TR+EN)**
- **Arama:** `GET /arama?q=<term>` → 200, SSR; kart yapısı kitapsepeti ile birebir aynı
  (`product-item` / `brand-title` yayınevi / `product-title` / `product-price` "221,20" TL),
  üstte "Fiyat Artan" sıralama + "Sadece Stoktakiler" filtresi.
- **Ürün sayfası:** `GET /berserk-1` → 200; JSON-LD `Product+Book`: `isbn: 9786256335424`
  (Berserk Cilt 1 — kitapsepeti'de YOKTU, burada **InStock**, 221.20 TRY), publisher,
  `priceValidUntil`. `/berserk-17` → ISBN 9786258502763, InStock.
- **Katalog dili:** Türkçe + ithal İngilizce manga/çizgi roman: "One Piece" → Vol. 99
  (İngilizce, Shueisha) + 36/14/13/12/11; "jujutsu kaisen" → 16/15/14/13/8/5 (karışık
  baskı); "frieren" → 2. Berserk: cilt 1,2,3,7,8,17 (6 sonuç).
- **Dikkat:** eşleşme olmayan sorgularda (watchmen, v_for_vendetta) sayfada **ilgisiz
  vitrin ürünleri** görünüyor → scraper'ın sonuç başlığında sorgu terimi kontrolü yapması
  gerekir (sahte "var" sonucu önlemek için). Sayfa başına 6 kart; `&page=` parametresi
  gözlenmedi (sayfalama JS `T.getLink` üzerinden — implementasyonda gerçek parametre
  doğrulanacak).
- **robots.txt:** kitapsepeti ile aynı (Allow: / + /ajax.php vb. disallow; python/wget
  UA kuralı muhtemelen aynı — app UA kullan).
- Değer: kitapsepeti'nin eksik bıraktığı basamakları (örn. Berserk 1-15) ve EN baskıları
  kapatabilir; aynı parser ailesiyle düşük entegrasyon maliyeti.

### 7) Edessa Kitabevi (edessakitabevi.com) — **kismen**
- Next.js (myikas CDN). **Ürün sayfaları SSR + JSON-LD** (mükemmel):
  `/frieren-cilt-6` → `sku/mpn = 9786256327726` (ISBN), brand "Marmara Çizgi",
  price 143.00 TRY, `availability: InStock`.
- **Ama:** arama `/search?query=*` JS-only (tüm sorgularda aynı 601KB RSC shell döner);
  kategori `/manga-ve-manhwa` SSR ama kategori başına ~16 ürün, sayfalama JS (page/sayfa
  parametresi SSR çıktısını değiştirmiyor).
- → Kategori crawl'ı kısıtlı; pratik kullanım için arama veya tam kategori listesi gerekir.
  Şimdilik düşük öncelik.

### Not — Marmara Çizgi
Bağımsız sitesi yok (marmaracizgi.com NXDOMAIN); **yayınevi**. Ürünleri komikseyler.com.tr
(`/yayinevi/marmara-cizgi/`), edessa ve cizman gibi store'larda satılıyor. Komikşeyler kartlarında
ISBN görünür (ör. "9786256327153 Frieren Cilt 02").

## 🏢 Resmi API Rotası (yalnızca ticari kayıtla — şu an kapsam dışı)
- **Kitsort (kitsort.com.tr) — yeni, en umut verici ortaklık adayı:** aktif kitap fiyat
  karşılaştırma platformu; 50+ store'dan fiyat yayınlıyor (**Kitapyurdu, D&R, Amazon,
  Hepsiburada, BKM, n11, Trendyol** dahil). AMA: SPA — sonuçlar server-side YOK
  (`/isbn/9786256335424` → 17KB shell; fiyatlar `api.kitsort.com.tr` özel API'sinden
  client-side yükleniyor; API kökü 530; endpoint keşfi = private-endpoint reverse
  engineering → kuralımız dışı). **Meşru yol: veri/API ortaklığı talebi**
  (destek: support@kitsort.com.tr — JSON-LD'de kamuya açık). Tek anlaşma ile
  kitapyurdu + D&R + Amazon birlikte gelebilir.
- **Kitapyurdu doğrudan veri akışı:** Türkiye'nin en büyük kitap perakendecilerinden;
  aggregator'lara ürün feed'i veriyor olabilir → doğrudan data-sharing/affiliate görüşmesi.
- **kitabinabak.com** (eski fiyat karşılaştırma sitesi): 💀 bağlantı zaman aşımı (http+https) — ölü.
- **Hepsiburada Developer API** — partner onboarding (şirket kaydı) gerekir.
- **Trendyol / N11 marketplace API** — satıcı/partner anlaşması gerekir.
- **Amazon Creators API** — 30 günde 10 nitelikli satış eşiği (P24.5'te araştırıldı).
- Solo proje için pratik değil; P24.5 raporu geçerli.
- Not: kitapyurdu OpenCart tabanlı (GitHub'daki eski scraper botları URL şemasını
  doğruluyor: `index.php?route=product/...`) — CF managed challenge **öncesi** scrape
  edilebiliyormuş; şu an tüm yüzeyde challenge var, bypass kurallar dışı.

## Entegrasyon Notları (UYGULANDI — 2026-09-10 güncel durum)
1. **Altı store da entegre edildi — her biri AYRI bir scraper** (aynı CMS olsa bile
   ortak parser/tek sınıf çıkarılmadı; her store kendi dosyasında, kendi fixture/test
   setiyle):
   - `kitapsepeti` + `kitapbulan` — "Ara Faz" (aynı T-Soft CMS, benzer ama AYRI
     scraper'lar: `app/scrapers/kitapsepeti.py`, `app/scrapers/kitapbulan.py`),
     canlı E2E doğrulandı (167/167 test, berserk → 3 store'ta listing).
   - `gerekliseyler` (WAW, `?tp=` sayfalama, "Stok Kodu" ISBN), `cizman` (ASP.NET
     form POST + token, tek sayfa), `kitapsec` (microdata, sadece arama),
     `komikseyler` (WooCommerce Store API, JSON) — P25.6, canlı E2E doğrulandı.
   Edessa (kismen) ve arkabahce/pandora (JS-only) eklenmedi (karar: düşük değer).
2. Mimari: `stores` tablosuna satır (`seed.py`), `BaseScraper` alt sınıfı
   (throttle ≥0.5s, backoff, bot-wall fail-fast), parse → `SearchResult` →
   `ImportService` (DB tek sınır). Mevcut çalışan kod bozulmadı.
3. Fiyat formatı: arama kartları TR ondalık virgüllü ("182,00"); ürün sayfaları
   (kitapsepeti JSON-LD) noktalı ("182.00") — her scraper kendi formatını normalize eder.
4. Risk: bu siteler bugün duvarsız; yarın Cloudflare/CAPTCHA ekleyebilir. Scraper
   mevcut "blocked" davranışıyla (fail-fast + log) zaten buna dayanıklı.
5. robots.txt uyumu: kitapsepeti'de python/wget UA kullanma (app UA kullan);
   diğer iki adayda kısıt yok.
