# Yeni veri kaynakları araştırması (1 Ekim 2026)

Önceki araştırmalar: `new-store-candidates.md` (10 Eylül, mağazalar) ve `store-access-research.md` (Amazon / D&R). Bu belge onları güncelliyor ve iki yeni alan ekliyor: fiyat karşılaştırma siteleri ve seri bilgisi (metadata) kaynakları.

## Nasıl test edildi

- Her site için ana sayfa, `robots.txt`, arama sayfası ve bir ürün sayfası canlı olarak çekildi.
- Uygulamanın kendi tarayıcı kimliği (User-Agent) kullanıldı. Cookie, proxy, captcha çözme ya da bot korumasını aşma denenmedi. 403, captcha veya Cloudflare challenge görülen site "engelli" sayıldı.
- Ölçüt olarak arama sonucunda kaç farklı "Berserk N" (gerekirse Frieren) cildi çıktığı sayıldı. Ürün sayfasında ISBN, fiyat ve stok bilgisinin olup olmadığına bakıldı.

**Önemli uyarı:** Testler bu bilgisayarın ağından yapıldı, Railway sunucusundan değil. Cizman buradan açılıyor ama Railway'e Cloudflare 403 döndürüyor; bu yüzden kapatılmıştı. Aşağıdaki "erişilebilir" sonuçlar, üretimde kullanmadan önce **Railway'den tekrar doğrulanmalı**. Bu özellikle Kitapyurdu ve idefix için geçerli.

## 1. Fiyat kaynakları: yeni ve erişilebilir

| Kaynak | Arama | Ürün verisi | Not | Öncelik |
|---|---|---|---|---|
| **Kitapyurdu** | Sunucu tarafında oluşan arama sayfası (`index.php?route=product/search&filter_name=`), sayfada 20 ürün, `&page=N` ile sayfalama. Kartta fiyat, liste fiyatı, yayınevi, dil ve yayın tarihi var. | JSON-LD `Product` + `Book`: `gtin13` ve `isbn`, fiyat, stok, yayınevi, `inLanguage`, sayfa sayısı, `datePublished` | Türkiye'nin en büyük kitapçılarından. Berserk 1–19'un tamamını döndürdü. robots.txt tamamen açık. 10 Eylül'de Cloudflare challenge vardı, şimdi yok. | ⭐⭐⭐ |
| **idefix** (pazar yeri) | Arama WAF tarafından reddediliyor (HTTP 511). Ama manga kategorisi açık: `/manga-c-330731344?sayfa=N`, toplam 632 ürün, sayfada 24. | Kategori sayfasındaki `__NEXT_DATA__`: fiyat, stok adedi, satıcı (**D&R**, **BKM**), 30 günün en düşük fiyatı, satışta mı. Ürün sayfası JSON-LD: `gtin13`, fiyat, yayınevi, dil. | D&R'ın fiyatları dolaylı olarak buradan gelir; dr.com.tr ise bizi engelliyor. Arama yerine kategori taraması yapılır (~27 sayfa). | ⭐⭐⭐ |
| **Büyülü Dükkan** | `/arama/<terim>`, sayfalama `?tp=N`. IdeaSoft, yani Gerekli Şeyler ile aynı altyapı. 19 Berserk cildi döndü. | "Stok Kodu" alanı ISBN veriyor, Gerekli Şeyler'deki gibi. | Mevcut Gerekli Şeyler parser'ı örnek alınarak ucuza eklenir. | ⭐⭐ |
| **İstanbul Kitapçısı** | `/arama?q=`, T-Soft altyapısı (Kitap Sepeti ve Kitapbulan ile aynı aile). 12 Berserk cildi döndü. | JSON-LD: `isbn`, fiyat, liste fiyatı, stok | Mevcut Kitap Sepeti parser'ı örnek alınarak ucuza eklenir. | ⭐⭐ |
| **Ucuzkitapal** | `/?dispatch=products.search&q=…&search_performed=Y` (CS-Cart). 12 Berserk cildi döndü. | JSON-LD: `sku` alanı ISBN, fiyat, stok (`OutOfStock` dahil) | | ⭐⭐ |
| **Marmara Çizgi Dükkan** (yayınevinin kendi mağazası) | `/arama?q=` | JSON-LD: `isbn`, fiyat, liste fiyatı, stok | Sadece Marmara Çizgi kitapları var (katalogda 23 seri). Yayınevi fiyatı referans olarak işe yarar. | ⭐ |
| **Ekin Kitap** | `/arama?q=`, 15 Frieren sonucu | "Stok Kodu" ISBN veriyor; fiyat sayfada JavaScript ile oluşuyor (doğrulanmalı) | | ⭐ |
| **Arka Bahçe** | Arama sunucu tarafında oluşuyor, ürün adresinde ISBN var (`/urun/berserk-19-9786258858068`) | Ürün sayfası istemci tarafında çiziliyor (Nuxt); veriyi arama sayfasından almak gerekir | Kısmen kullanılabilir. | ⭐ |

## 2. Engelli ya da işe yaramayanlar

| Kaynak | Durum |
|---|---|
| Amazon TR | Boş 202 yanıtı (JavaScript duvarı). Resmi API yolu hâlâ "30 günde 10 satış" şartına bağlı. |
| D&R | Her adres 403. Fiyatları idefix üzerinden alınabilir. |
| Hepsiburada, Cimri | 403 |
| Trendyol, n11 | Ana sayfa açılıyor, arama 403 |
| Kitapsan | Cloudflare challenge |
| Akakçe | Arama Cloudflare challenge'a takılıyor |
| Kitsort | Hâlâ tek sayfalık uygulama (SPA), veri özel bir API'den geliyor. Ancak ortaklık yoluyla kullanılabilir. |
| Kitap Karşılaştır | Küçük, reklamla dönen bir site; arama sonuç vermedi |
| Pandora | robots.txt aramayı yasaklıyor, manga kategorisi bulunamadı |
| Paralel Evren (`paralelevren.istanbul`, yeni adresi) | Erişilebilir ama çoğunlukla İngilizce manga, çizgi roman ve Funko var. Türkçe katalog için değeri düşük. |
| Dünyada Kitap | Shopify'ın açık JSON'u ile ~1.040 manga, ISBN'ler SKU içinde. Ama fiyatlar **USD** ve Avrupa'ya satış yapıyor; Türkiye fiyatı değil. |
| Presstij, İstanbook, Akm Kitap, Yapada Dükkan | Açılıyorlar, ama arama adresi bulunamadı ya da sonuçlar JavaScript ile geliyor. Düşük öncelik. |
| Kitabı Nabak, Populus, Kitap Bulut | Bu ağdan bağlanılamadı; doğrulanamadı. |
| Cizman | Buradan açılıyor ama Railway'e Cloudflare 403 döndüğü için kapalı. Railway'den yeniden denenebilir. |

## 3. Seri bilgisi (metadata) kaynakları

| Kaynak | Ne veriyor | Erişim | Değer |
|---|---|---|---|
| **AniList** (GraphQL) | `format` (**ONE_SHOT** dahil), yayın durumu, cilt sayısı, türler, etiketler, puan, popülerlik, İngilizce özet, MAL id, kapak, yazar ve çizer | Ücretsiz, anahtar gerekmiyor, dakikada ~90 istek. Eşleştirme `original_title` ile yapılır. | ⭐⭐⭐ Tür ve etiket filtreleri, "benzer seriler", one shot'ı çapraz kontrol |
| **1000Kitap** | JSON-LD `Book`: **ISBN**, **Türkçe özet**, okur puanı (örnek: Berserk 4 için 146 oyla 9,1), yorum sayısı, çevirmen. Arama sunucu tarafında oluşuyor. | robots.txt açık. Eşleştirme ISBN ile yapılır. | ⭐⭐ Türkçe tanıtım yazısı ve okur puanı. Kullanım koşulları kontrol edilmeli; yorum metinleri kopyalanmamalı, puan gösterilip bağlantı verilmeli. |
| MangaUpdates API | Resmi ve ücretsiz. Yayın durumu, türler, öneriler. | Türk yayınevlerini bilmiyor (sadece İngilizce ve orijinal). Arama gürültülü: "Look Back" yanlış bir doujinshi ile eşleşti. | ⭐ |
| MyAnimeList (Jikan veya resmi API) | AniList'e benzer | Jikan test sırasında çöktü (504). Resmi API ücretsiz bir client ID istiyor. | ⭐ (AniList yeterli) |
| Google Books | ISBN ile arama | Anahtarsız günlük kota dolu (429). Ücretsiz anahtar gerekir; Türkçe manga kapsamı doğrulanamadı. | ? |
| Open Library | — | Test edilen ISBN'lerin hiçbiri yok | ✗ |

## Önerilen sıra

1. **Railway'den erişim testi.** Admin panele "mağaza erişim testi" düğmesi eklenir; her adayı Railway'den bir kez çekip durum kodunu ve duvar işaretini gösterir. Kitapyurdu ve idefix'i entegre etmeden önce bu şart.
2. **Kitapyurdu scraper'ı.** En büyük kapsam artışı. Arama kartı fiyat verir, ISBN ürün sayfasından okunur (BKM'deki zenginleştirme gibi).
3. **Ucuz eklemeler.** Büyülü Dükkan (Gerekli Şeyler deseni), İstanbul Kitapçısı (Kitap Sepeti deseni) ve Ucuzkitapal.
4. **idefix kategori taraması.** D&R ve BKM pazar yeri fiyatları gelir. Arama yerine sayfa sayfa tarama yapılır; ISBN ürün sayfasından ya da başlık ve yayınevinden bulunur.
5. **AniList zenginleştirmesi.** Tür, etiket, özet ve one shot doğrulaması.
6. **1000Kitap.** Türkçe özet ve okur puanı, kullanım koşulları kontrol edildikten sonra.
7. Marmara Çizgi Dükkan ve Ekin Kitap (niş).
