# Mangakol'suz keşif ve ISBN kaynakları araştırması (16 Ekim 2026)

Amaç: Mangakol kapanırsa ya da erişimimizi kısıtlarsa site takılmasın. Yeni seri ve ciltleri, ISBN'leri ve künyeleri kendi kaynaklarımızdan bulalım. Ayrıca GitHub'daki ISBN doğrulama sisteminin (PR #4–#10) neden işe yaramadığını ölçelim.

## Kısa sonuç

- **Mevcut doğrulama sistemi Railway'de hiçbir cildi doğrulayamıyor.** 40 ciltlik örneklemde Kitapyurdu kapalıyken (Railway'deki durum) sonuç 0 `VERIFIED`, 39 `INSUFFICIENT_EVIDENCE`. Sebep kodda: BKM her aramada hata sayılıyor, aramalar romaji adla yapılıyor, Pandora ve D&R hep 403.
- **Mangakol'un ISBN'leri de hatalı olabiliyor.** Kayıp Kıta serilerinde bir cilt kayma hatası bulundu (aşağıda). İki kaynağın uyuştuğu bir sistem bunu yakalar.
- **Mangakol'suz keşif mümkün.** Bugün taradığımız 9 mağaza Mangakol'daki çıkmış ciltlerin %92'sini zaten listeliyor. Bora Dağıtım ve idefix eklenince son 90 günde çıkan ciltlerin %94'ü kapsanıyor, ve yeni ciltler çıkış gününde ya da daha önce görünüyor.
- **Mangakol'un yerini tam tutamayan tek şey "Yakında" duyuruları.** Haftalar önceden gelen duyuruların otomatik bir kaynağı bulunamadı (Athica hariç). JP/TR yayın durumu ve orijinal ad için AniList kullanılabilir.
- **Öneri:** ISBN kontrolü ile keşfi aynı mekanizmada birleştirmek. Yayınevi ve dağıtımcı listelerini düzenli tarayıp `ISBN → (yayınevi, başlık, cilt, tarih)` haritası tutmak. Bu harita hem yeni ciltleri buldurur hem de kataloğun ISBN'lerini toplu kontrol eder. Cilt cilt arama yapan şimdiki denetim tam katalogda ~20 saat sürüyor; liste taraması dakikalar sürer.

## Nasıl ölçüldü

- Mangakol'un tamamı çekildi: 475 seri, 2.326 çıkmış cilt, 46 "Yakında". Her serinin son 3 cildi için ISBN ve çıkış tarihi alındı. Son 90 günde çıkan 139 cilt "yeni çıkanlar" örneklemi oldu.
- Her aday kaynağın manga kategorisi baştan sona tarandı. Ürünler başlık, cilt numarası ve yayınevine göre Mangakol cilt listesiyle eşlendi (yaklaşık bir eşleştirici; uzun adlı birkaç seri kaçabilir).
- GitHub `origin/main` üzerindeki ISBN denetim kodu (`isbn_sources.py`, `isbn_identity.py`) aynen çalıştırıldı: Mangakol'dan rastgele 40 cilt, gerçek kaynaklar.
- **Sınır:** Testler bu bilgisayarın ağından yapıldı. Kitapyurdu buradan açılıyor ama Railway'e 403 dönüyor (1 Ekim erişim testi). Diğer kaynaklar da üretime almadan önce admin panelindeki erişim testiyle Railway'den doğrulanmalı.

## 1. Mevcut ISBN doğrulama sistemi neden işe yaramıyor

40 cilt, ortalama 31 saniye/cilt (tam katalog ≈ 20 saat):

| Durum | Bu makineden (Kitapyurdu açık) | Railway gibi (Kitapyurdu yok) |
|---|---|---|
| VERIFIED | 14 | **0** |
| INSUFFICIENT_EVIDENCE | 24 | 39 |
| CONFLICT | 2 | 0 |
| SOURCE_ERROR | 0 | 1 |

Kaynak bazında:

| Kaynak | Sonuç (40 cilt) | Sebep |
|---|---|---|
| BKM | 40 ERROR | BKM araması her zaman sonuç sınırına ulaşıyor (ISBN ile arayınca bile alakasız 48 ürün dönüyor). Kod `max_results` / `no_new_items` durumunu "arama eksik" sayıyor. **BKM hiç oy veremiyor.** |
| Kitap Sepeti | 37 NO_RESULT, 3 ERROR | Arama sorgusu Mangakol slug'ından üretiliyor: "hori san to miyamura kun 15", "kaguya sama wa kokurasetai…". Mağaza Türkçe adla satıyor. |
| Kitapyurdu | 21 MATCH, 18 NO_RESULT | Aynı romaji sorgu sorunu. Railway'den zaten 403. |
| Bora | 25 MATCH, 12 ERROR | 24'ten fazla sonuç dönen her arama "sayfalama doğrulanamadı" hatası oluyor. |
| Pandora, D&R | 40 ERROR | 403. Sistemde sadece hata üretiyorlar. |

Sonuç olarak Railway'de pratikte tek oy veren kaynak Bora, iki bağımsız kaynak şartı da hiç sağlanmıyor. "Kuyruk işe yaramıyor" gözleminin tam açıklaması bu.

Ek gerilemeler (P0 kilidi canlıda):

- Katalog senkronu yeni ciltlerin ISBN'ini okuyup yazmıyor; mağaza ISBN'i de yazılmıyor. 14 Ekim'den beri eklenen ciltler sadece başlık eşleşmesiyle fiyat alıyor.
- Trigger'lar ilan ve fiyat geçmişi silmeyi tamamen engelliyor. Admin'in "yanlış eşleşmeyi kaldır" düğmesi ve kalkan ürün temizliği çalışmıyor.

## 2. Mangakol ISBN'leri: bir cilt kayma hatası

Kaynaklar Mangakol'la ayrıştığında Bora barkod sayfasıyla doğrulandı:

| Cilt | Mangakol ISBN'i | Bu barkod Bora'da | Doğru ISBN |
|---|---|---|---|
| Skip and Loafer 4 | 9786259667294 | Skip and Loafer **3** (Aralık 2025) | 9786259324036 (Haziran 2026) |
| Huzurlu Kamp 3 | 9786259727080 | Huzurlu Kamp **2** (Haziran 2025) | 9786259324067 (Haziran 2026) |
| Happiness 6 | 9786259360492 | Happiness **5** (Nisan 2026) | 9786259324050; Kitapyurdu da aynısını veriyor |

Üçü de Kayıp Kıta. Mangakol, yeni cilde bir önceki cildin ISBN'ini kopyalamış. Bizde bu iki cilt aynı ISBN'i istediği için "ISBN çakışması" olarak görünür ve yeni cildin fiyatları eski cilde düşebilir.

Diğer farkların çoğu meşru: Blue Lock 29 ve Solo Leveling 5–7 normal/varyant baskı farkı, omnibus numaralandırması (Dragon Ball "9 ve 10", Oldboy) ya da yabancı baskı (VIZ). Blue Lock 29'da Komik Şeyler ile Kitapseç 9786258630633'te uyuşuyor, Mangakol 9786258630626 diyor. Bora'da ikisi de yok; elle bakılmalı.

## 3. Kaynakların kapsaması

Mangakol'daki çıkmış ciltlere göre. "Son cilt": serinin en son çıkmış cildi. "Son 90 gün": son 90 günde çıkan 139 cilt.

| Kaynak | Ürün | ISBN'li | Seri | Cilt | Son cilt | Son 90 gün |
|---|---|---|---|---|---|---|
| Büyülü Dükkan | 2.288 | 474 | %80 | %86 | %70 | %54 |
| Gerekli Şeyler (mağaza) | 9.407 | 494 | %68 | %78 | %64 | **%81** |
| Kitap Sepeti | 4.755 | – | %63 | %56 | %40 | %25 |
| **Bora Dağıtım** | 7.270 | 7.051 | %45 | %61 | %44 | %54 |
| idefix | 957 | – | %53 | %35 | %37 | %48 |
| Kitapbulan | 513 | – | %27 | %20 | %8 | %1 |
| BKM (kategori) | 1.576 | 1.576 | %12 | %19 | %4 | %0 |
| Kitapseç (kategori) | 524 | 503 | %12 | %4 | %7 | %13 |
| Komik Şeyler (API) | 823 | 362 | %8 | %7 | %8 | %11 |
| Destek Dükkan (ilk sayfa + ön sipariş) | 49 | 49 | %5 | %1 | %4 | %22 |

Birlikte:

| Kombinasyon | Cilt | Son cilt | Son 90 gün |
|---|---|---|---|
| Bugünkü 9 mağaza | %92 | %86 | %87 |
| + Bora | %93 | %88 | %92 |
| + Bora + idefix | %93 | %89 | %94 |
| Sadece Bora + idefix | %79 | %68 | %87 |

Kalan boşluklar küçük yayınevleri (Hayalperest Çocuk, Doğan Egmont, Aba, Yordam) ve eşleştiricinin kaçırdığı çok uzun adlar (Tokyo Manga'nın "Her Şeyi Savuştur…" serisi).

## 4. Hız: yeni çıkan cilt nerede ne zaman görünüyor

16 Ekim'deki tarama, Mangakol çıkış tarihine göre:

| Çıkış | Cilt | Görüldüğü kaynaklar |
|---|---|---|
| 22 Ekim (gelecek) | Dorohedoro 5 | Kitapseç |
| 20 Ekim (gelecek) | Berserk (Athica) 20 | Destek Dükkan (ön sipariş), Büyülü Dükkan |
| 15 Ekim | Mashle 8, Kaiju No. 8 9, Mavi Kutu 5, Vatansever Moriarty 6 | Bora, Gerekli Şeyler |
| 15 Ekim | Kötülerin Kaderi Yok Olmaktır 5, Elden Ring 2 | idefix (+ Destek Dükkan) |
| 14 Ekim | Dük ile İlk Gecem 2–3, Kuzey Yıldızı'nın Yumruğu 1 | Bora (+ idefix) |
| 13 Ekim | One Piece 62, Naruto 62, Haikyu!! 22, Kahramanlık Akademim 33, Dandadan 8, Nana 7 | Bora ve Gerekli Şeyler'de hepsi; Büyülü Dükkan, Kitap Sepeti ve Kitapseç'te çoğu |

Bora ve Gerekli Şeyler çıkış gününde listeliyor. Mangakol bundan haftalar önce "Yakında" gösterebiliyor; bu farkı kapatan otomatik bir kaynak bulunamadı.

## 5. Kaynak profilleri

### Bora Dağıtım (boradagitim.com) — en değerli yeni kaynak
- Yayınevlerinin dağıtımcısı. Künye yayınevinden geliyor: barkod (ISBN), yayınevi, dil, sayfa sayısı, kapak ve kağıt türü (2. hamur / kuşe), basım tarihi (ay/yıl), baskı sayısı, liste fiyatı, stok.
- Dağıttığı manga yayınevleri: Gerekli Şeyler (1.001 ürün), Marmara Çizgi (766), Akılçelen (516), Kayıp Kıta (154), Beta Byou (118), Kurukafa (101), Tokyo Manga (47), Satori (29), Uykulu Kahve (21), İthaki Yuki (13), Senpai (9). Artemis ve Everest genel yayınevi; mangaları binlerce kitabın içinde.
- **Dağıtmadıkları:** Athica (kataloğun en büyük yayınevi, 94 seri), Komik Şeyler (52 seri).
- Erişim: yayınevi listesi `Istem/Urun/YayinEvi/Detay.aspx?index=N&Id=…`, sayfada 24 ürün. Yeni çıkanlar `ListeleYeni.aspx?tip=1` (636 ürün, tüm kategoriler). Barkodla doğrudan ürün sayfası: `Detay.aspx?Barcode=…`. robots.txt yok (404), tümü izinli.
- Not: Arama sayfası 24'ten fazla sonucu sayfalamıyor; doğrulayıcının "eksik arama" hatası buradan geliyor. Yayınevi listesi ve barkod sayfası bu sorunu yaşamıyor.

### idefix (manga kategorisi)
- 957 ürün, `__NEXT_DATA__` JSON'u. "Son Eklenen" sıralaması (`siralama=desc_added`) var, yani yeni ürün akışı olarak kullanılabilir. Satıcı (D&R, BKM), stok ve 30 günün en düşük fiyatı da geliyor.
- ISBN liste sayfasında yok, ürün sayfasında (JSON-LD `gtin13`).
- 1 Ekim'de Railway'den erişilebilir bulunmuştu. Athica ve Bora'da olmayan diğer yayınevlerini yakalıyor.

### Destek Dükkan (destekdukkan.com) — Athica'nın kendi mağazası
- Athica'nın bağlı olduğu Destek Grubu'nun mağazası. `/magaza/oznitelik/yayinevi/athica-books` sayfasında toplam 508 ürün, en yenileri üstte. ISBN kapak dosyasının adında (`9786258858280-front-cover.jpg`).
- `/on-siparis` sayfası çıkmamış kitapları gösteriyor (bugün Berserk 20 ve iki Athica serisi daha). Athica için "Yakında" kaynağı olabilir.
- Sayfalama düz adresle çalışmadı (JavaScript ile yükleniyor gibi). Keşif için ilk sayfa ve ön siparişler yeterli; tam liste için sitemap (`static.destekdukkan.com/cache/sitemap/sitemap-index.xml`) ya da sayfalamanın çözülmesi gerekir. Sitemap adresi bu ağdan çözülemedi.

### Komik Şeyler (WooCommerce API)
- `wp-json/wc/store/v1/products`: 823 ürün, 211'i manga, `sku` çoğu zaman ISBN.
- **Risk:** Ana sayfa şu an 503 veriyor ve "Yeni sitemiz çok yakında" yazıyor. Yeni site açılınca API ve mevcut scraper kırılabilir.

### Gerekli Şeyler ve Büyülü Dükkan (IdeaSoft)
- Kategori sayfaları mevcut kart ayrıştırıcısıyla okunuyor. Gerekli Şeyler'in "manga" kategorisi 9.407 ürün (çoğu figür ve yabancı baskı); Büyülü Dükkan 2.288.
- Gerekli Şeyler yayınevi olarak kendi kitaplarını çıkış gününde listeliyor.
- robots.txt `crawl-delay: 30` istiyor; günlük bir tarama için sorun değil.

### Kitapseç
- Kategori sayfasında ISBN (`sku`) var, çıkmamış kitapları da listeliyor (Dorohedoro 5). Kategori küçük (524 ürün); çoğu manga kategoride değil, aramayla bulunuyor.

### BKM, Kitap Sepeti, Kitapbulan
- BKM kategori sayfası her ürünün ISBN'ini veriyor ama manga kategorisi ayrı değil; çizgi romanla karışık ve sınırlı.
- Kitap Sepeti ve Kitapbulan'da ISBN listede yok.

### Kitapyurdu
- En iyi künye kaynaklarından biri, ama Railway'e 403. Sadece bu makineden çalışıyor; üretimde kullanılamaz.

### Resmi kaynaklar
- Kültür ve Turizm Bakanlığı bandrol sistemi ve ISBN Türkiye Ajansı için herkese açık bir "yeni kitaplar" listesi bulunamadı. Bandrol sorgusu e-Devlet üzerinden ve sadece eser sahibine açık ([TRT Haber](https://www.trthaber.com/haber/kultur-sanat/bandrol-satislari-e-devletten-sorgulanabilecek-310449.html)). ISBN ajansı başvuru odaklı ([ekygm.gov.tr](https://ekygm.gov.tr)).
- Milli Kütüphane'nin derleme kayıtları ISBN doğrulamada işe yarayabilir ama aylar gecikmeli; keşif için uygun değil.

### Yayınevi siteleri
- Kayıp Kıta, Akılçelen, Kurukafa, Satori, Tokyo Manga ve Beta Byou için çalışan bir satış sitesi bulunamadı. Bu yayınevlerinin verisi en temiz haliyle Bora'da.
- Marmara Çizgi'nin sitesi (marmaracizgi.com.tr) açık, ama sayfada ISBN yok.

## 6. Mangakol'dan aldığımız her alanın yedeği

| Alan | Mangakol'suz kaynak | Durum |
|---|---|---|
| Yeni cilt (var olan seride) | Bora, Gerekli Şeyler, idefix, Destek Dükkan, Komik Şeyler API, mevcut mağazalar | ✓ Çıkış gününde |
| Yeni seri | Aynı kaynaklar (seri adı ve yayınevi ürün başlığından) | ✓ Ama gürültülü: figür, yabancı baskı, roman ayıklanmalı |
| ISBN | Bora (yayınevi künyesi), Destek Dükkan, Komik Şeyler `sku`, Kitapseç, BKM | ✓ Mangakol'dan daha güvenilir |
| Sayfa sayısı, kağıt/kapak türü | Bora | ✓ |
| Çıkış tarihi | Bora (ay/yıl), ilk görüldüğü gün | ~ Gün hassasiyeti yok |
| Kapak görseli | Mağaza ve Bora ürün görselleri | ✓ |
| Yazar / çizer | Bora, idefix (`authorName`, `artistName`) | ✓ |
| "Yakında" duyuruları | Sadece Athica (Destek ön sipariş) ve Kitapseç'teki ön satışlar | ✗ Kısmen |
| JP/TR yayın durumu, orijinal ad | AniList (1 Ekim araştırması) | ~ Eşleştirme gerekir |
| Baskı sekmeleri (varyant, bez cilt) | Ürün başlıkları ve Bora'daki kağıt/kapak türü | ~ Kurallarla |

## 7. Önerilen yön

1. **Kendi kataloğumuz doğruluk kaynağı olur; Mangakol beslemelerden biri olarak kalır.** Mangakol kapanırsa sadece "Yakında" ve yayın durumu zayıflar.
2. **Tek bir "künye haritası" tutulur.** Bora yayınevi listeleri, Destek Dükkan, Komik Şeyler API, idefix son eklenenler ve mağaza kategori sayfaları her gün taranır. Her ürün `ISBN → yayınevi, başlık, cilt, tarih, kaynak, ilk/son görülme` olarak kaydedilir.
3. **Aynı harita iki işi yapar:**
   - *Keşif:* Haritada olup katalogda olmayan ISBN'ler yeni cilt ya da yeni seri adayıdır. Kararımıza göre otomatik eklenir.
   - *ISBN kontrolü:* Katalogdaki her cildin ISBN'i harita ile karşılaştırılır. Yayınevi künyesi (Bora, Destek, Komik Şeyler) ya da iki kaynak uyuşursa doğru sayılır. Çelişki varsa kuyruğa düşer. Mangakol'un kayma hatası da böyle yakalanır.
4. **Cilt cilt arama yapan şimdiki denetim emekliye ayrılır** ya da sadece kuyruktaki tek tük kayıt için ikinci görüş olarak kalır.

## 8. Karar verilmesi gerekenler

- "Her şey otomatik" kuralı yeni seriler için nasıl uygulanacak? Yeni seri adayı için asgari kanıt ne olmalı (ör. Bora'da ya da yayınevinin kendi mağazasında, Türkçe, ISBN'li)? Yanlış eklenen seri için admin'de "son eklenenler / geri al" listesi yeterli mi?
- "Yakında" duyuruları için ne yapılacak: Mangakol çalıştıkça ondan almak, elle eklemek, ya da Yakında'yı tamamen bırakmak.
- Hangi kaynakla başlanacak: Bora ilk sırada önerilir (en temiz künye, 11 yayınevi, çıkış gününde). Sonra Destek Dükkan (Athica) ve idefix.
- Komik Şeyler'in site değişikliği takip edilmeli.

## 9. Taramasız yollar (ek araştırma, 16 Ekim)

Kullanıcının iki kaygısı vardı: taramaya bağımlılık (siteler değişince kırılır) ve veri kalitesi. Bu yüzden üç yol daha incelendi.

### 9.1 Bibliyografik API'ler — işe yaramıyor

30 ISBN ile test edildi: 15'i son çıkan, 15'i rastgele eski cilt.

| Kaynak | Sonuç |
|---|---|
| Open Library | 0/30 |
| Wikidata | Türkiye önekli (978-605 / 978-625) ISBN'e sahip toplam **155** baskı kaydı var; pratikte boş |
| Google Books | Anahtarsız kota dolu (429), ölçülemedi. Ücretsiz bir API anahtarıyla tekrar denenebilir; 1 Ekim'de de aynı durumdaydı |
| ISBNdb | Ücretli, 7 günlük deneme var. Türkçe kapsamına dair kanıt bulunamadı ([Wikipedia](https://en.wikipedia.org/wiki/ISBNdb.com)). Kitapları ancak satışa çıktıktan sonra eklediği belirtiliyor; "Yakında" için işe yaramaz |

Uluslararası veritabanları Türk mangasını bilmiyor. Bu yol en fazla Google Books anahtarıyla bir kez daha ölçülmeye değer.

### 9.2 Resmi ürün beslemeleri — ancak anlaşmayla

- Ortaklık ağlarında (Admitad, Gelir Ortakları, ReklamAction) kitapçıların ürün beslemesi verdiğine dair doğrulanmış bir kaynak bulunamadı. Admitad Türkiye'de çalışıyor ama D&R/idefix ile ilişkisi görünmüyor ([Webrazzi](https://webrazzi.com/2020/06/11/admitad-bcnmonetize-affiliate-marketing/)).
- Mağazaların robots.txt dosyalarında sadece sitemap var. Cimri ve Akakçe için üretilen XML beslemeleri herkese açık değil.
- **En gerçekçi yol doğrudan istemek:**
  - **Bora Dağıtım** bir B2B dağıtımcı. Sitede "Kurumsal Üye" ve bayilik girişi var; bayilere künye ve stok listesi (Excel/XML) vermeleri olağan. Yomiba bayi değil, ama "fiyat karşılaştırma sitesi, satışınızı artırırız" gerekçesiyle künye listesi istenebilir.
  - **Yayınevleri** (Athica/Destek, Gerekli Şeyler, Komik Şeyler, Kayıp Kıta, Akılçelen): yeni çıkan ve yakında listesi istenebilir. Bazıları zaten basın bülteni gönderiyordur.
  - Bu yol hem taramaya bağımlılığı hem de kalite sorununu en iyi çözer, ama kullanıcının e-posta ile iletişime geçmesini gerektirir ve sonucu belirsizdir.

### 9.3 Yayınevi duyuruları + yapay zekâ — "Yakında" için tek ciddi aday

- Yayınevleri yeni seri ve cilt duyurularını Instagram'da yapıyor; Mangakol'un "Yakında" bilgisi de muhtemelen buradan geliyor. JJK 21'in Mangakol kaydında Japon cildin alt başlığı var, yani elle girilmiş bir duyuru.
- **Instagram'ı kazımak** kullanım koşullarına aykırı ve sık kırılır; önerilmez.
- **Resmi yol: Instagram Graph API "Business Discovery".** Kendi Instagram profesyonel hesabımızla başka profesyonel hesapların (yayınevleri) gönderilerini okuyabiliyoruz ([Meta belgesi](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-facebook-login/business-discovery.md)).
  - Gerekenler: bir Facebook uygulaması, Facebook Sayfasına bağlı bir Instagram profesyonel hesabı (Yomiba'nın Instagram hesabı zaten planlanıyordu), `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement` izinleri.
  - **Belirsiz olan:** Business Discovery sayfası örneklerde sadece beğeni ve yorum sayısını gösteriyor. Medya referansı `caption` alanını herkese açık alan olarak listeliyor ([Meta media reference](https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media)). Açıklama metni ve görselin gelip gelmediği küçük bir denemeyle doğrulanmalı. Uygulama incelemesi (app review) gerekip gerekmediği de belgede yazmıyor; kendi hesabımızla geliştirme modunda denenebilir.
- **Yapay zekâ ne yapar:** Her yeni gönderinin açıklaması ve görseli Claude'a verilir. Claude "seri, cilt, baskı türü, tarih, yakında mı / çıktı mı" bilgisini yapılandırılmış olarak çıkarır. Bu bir **öneri** olur; ürün ISBN'iyle bir kaynakta görünene kadar "Yakında" olarak kalır. Böylece yapay zekânın hatası ISBN'e ya da fiyata hiç dokunmaz.
- Hacim küçük: ~15 yayınevi, günde birkaç gönderi. Maliyeti düşük, kesin rakam kurulumda hesaplanır.

### 9.4 Güncellenmiş öneri

Fiyatlar zaten mağaza taramasından geliyor; anlaşma olmadan taramadan tamamen kurtulmak mümkün değil. Hedef **tek bir kırılma noktası olmaması**:

1. **Künye haritası birden fazla kaynakla beslenir.** Hiçbir kaynak tek başına zorunlu değildir. Bir kaynak kırılırsa diğerleri kapsamayı sürdürür. Bölüm 3'teki tabloya göre en az üç kaynağın her biri yeni çıkanların büyük kısmını görüyor.
2. **Kaynaklar güven sırasıyla değerlendirilir:** anlaşmalı besleme > dağıtımcı/yayınevi künyesi (Bora, Destek, Komik Şeyler) > iki mağaza uyuşması > tek mağaza > Mangakol. Kalite bu sıralamadan gelir.
3. **"Yakında" duyuruları Instagram + Claude ile alınır**, Mangakol yedek kalır, admin elle de ekleyebilir.
4. **Her kaynağın sağlığı izlenir.** Admin panelinde "son başarılı okuma, son 7 günde getirdiği ürün sayısı" gösterilir; bir kaynak sustuğunda haber verilir.
5. **Paralel olarak Bora ve büyük yayınevlerine e-posta atılır.** Olumlu dönen kaynak taramanın yerini alır.

## Ham veri

Ölçüm betikleri ve ham JSON'lar bu makinede `%LOCALAPPDATA%\Temp\yomiba-research` klasöründe (`mk_catalog.json`, `src/*.json`, `audit_sample.json`, `analyze.py`). Git'e eklenmedi.
