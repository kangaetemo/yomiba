# Yomiba çalışma notları

Son güncelleme: 14 Ekim 2026 (katalog farklarını koruyarak düzeltme).

Önceki kayıttaki son kod push bilgisi: 1 Ekim, "Slug URLs, search dialog" (main); öncesi `a906b8e`. Bu bilgi tarihsel kayıttır; güncel branch durumunu ifade etmez.

## Sistem nasıl çalışıyor

- **Katalog kaynağı Mangakol.** Katalog senkronu seri, cilt, kapak, ISBN, sayfa sayısı, yerel çıkış tarihi, yazar/çizer ve JP/TR yayın durumunu okur. Arama sadece Mangakol kataloğundaki serileri gösterir.
- **Fiyatlar mağazalardan gelir.** BKM, Kitapseç, Kitap Sepeti, Kitapbulan, Gerekli Şeyler, Edessa ve diğerleri taranır. Ürünler önce ISBN ile, olmazsa başlık ve yayınevi ile ciltlere eşlenir. ISBN her zaman başlıktan önce gelir.
- **Kapaklar bizde.** Mangakol'dan bir kez indirilip Railway volume'da WebP olarak saklanır ve `/api/covers/...` üzerinden sunulur. İleride R2'ye taşınabilecek şekilde yazıldı.
- **Deploy.** Backend Railway'de (SQLite, `/data` volume). Veritabanı güncellemeleri açılışta yedek alınarak otomatik çalışır. Frontend Vercel'de.

## Çalışma düzeni

- **Dokümantasyon ayrımı:** Bekleyen talepler ve değerlendirilecek fikirler [yapılacaklar.md](../yapılacaklar.md) dosyasında tutulur. Tamamlanan işler, alınan kararlar, doğrulama sonuçları ve varsa kalan sınırlamalar bu çalışma notlarına tarihli olarak eklenir. İki dosya ayrı kalır; uzun açıklamalar kopyalanmak yerine ilgili kayda bağlantı verilir.
- Bir iş tamamlanınca yapılacaklar listesindeki maddesi işaretlenir ve buraya sonuç kaydı eklenir. Yalnızca konuşulan öneriler tamamlanmış iş gibi yazılmaz; kodda bulunması da tek başına canlıda test edildiği anlamına gelmez.
- Her değişiklikten sonra testleri çalıştırıyorum. Özet Türkçe veriliyor ve push ancak senin onayınla yapılıyor.
- Backend testleri:
  - Komut: `cd backend && .venv/Scripts/python.exe -m pytest -q --ignore=tests/test_task2_identity.py`
  - `test_task2_identity.py` gerçek bir veritabanı istediği için yerelde her zaman hata verir; bu bir regresyon değil.
- Frontend kontrolleri: `cd frontend && npx tsc --noEmit -p . && npx eslint .`
- `test_rate_limit_keeps_per_store_interval` Windows'ta ara sıra zamanlama yüzünden düşüyor; eskiden beri var.
- Fiyatsız seriler raporu (`fiyatsızlar.txt`): Mağaza bazındaki sebep sayıları, sorgunun döndürdüğü tüm ürünler üzerinden toplanıyor. Örneğin BKM'de büyük bir `publisher_conflict` sayısı genelde "bu mağaza o seriyi satmıyor" demektir.

## Son günlerde yapılanlar

### 14 Ekim: ISBN yazma yollarının zorunlu ön incelemesi

- Kullanıcının isteğiyle yeni ISBN doğrulama teknik şartnamesi için kod yazmadan önce mevcut yazıcılar denetlendi. İncelenen main sürümü `33bfdc407bd26793a1ba1316aa395fec123d3dcb`; 254 kod/betik dosyasının yerel Git blob hash'i sürümle eşleşti.
- [Ayrıntılı rapor](isbn-yazma-yollari-denetimi-2026-10-14.md): yedi dosyada 18 doğrudan ISBN yazma/temizleme/taşıma noktası; katalog senkronu, mağaza aktarımı, admin/CLI düzeltmeleri, numarasız cilt merge'ü, yabancı baskı temizliği, tarihsel SQL bakım yazmaları ve dolaylı kimlik/history etkileri.
- Dört izole bellek DB deneyinde tek mağaza sonucuyla boş ISBN doldurma; Yakında/pasif cilde ilan atlanırken ISBN'nin commit edilmesi; checksum hatalı ISBN'nin yazılması doğrulandı. İlgili mevcut 131 test geçti. Güncel public `/search` salt okunur; eski `search_with_auto_import` işlevinin varlığı bugünkü route'un yazıcı olduğu şeklinde yorumlanmadı.
- Uygulama kodu, migration ve canlı DB değiştirilmedi. Yeni doğrulama motoru çalıştırılmadı; ISBN kararları uygulanmadı. Yalnız rapor/dokümantasyon kaydedildi ve zorunlu ön inceleme checkbox'ı tamamlandı. **A/B/C aşamaları ve ortak onay kapısı hâlâ açık; sistemin ISBN'leri artık admin onayıyla değiştirdiği iddia edilmiyor.**

### 14 Ekim: katalog farklarının düzeltilmesi

- Kullanıcı, karşılaştırmada bulunan farkların en üst önceliğe alınmasını ve uygulanmasını istedi. Düzeltme eski raporu veritabanına kopyalamıyor; senkron sırasında güncel Mangakol görüntüsünü kullanıyor.
- `catalog_present` kaynak üyeliğini, `catalog_released` yayın durumunu temsil ediyor. Tam ve boş olmayan cilt listesinde bulunmayan eski satırlar görünür katalogdan ayrılıyor; cilt satırları, fiyat geçmişi ve kişisel referanslar korunuyor. Kısmi kaynak görüntüsü eksik görünen ciltleri pasifleştirmiyor.
- Seri ve arama cilt sayıları yalnızca yayımlanmış ciltleri sayıyor; gerçek duyurular ayrı `upcoming_volumes` / “Yakında” alanında gösteriliyor. Kaynak dışı, tarihli eski kayıtlar cilt sayfası ve takvimde de görünmüyor.
- Katalog senkronunun ilk çalışma zamanı her açılışta 24 saat ileri gidiyordu. Son başarılı çalışma ve son deneme zamanı SQLite'ın yanındaki kalıcı dosyada tutuluyor; açılışta geciken veya hiç doğrulanmamış senkron hemen çalışıyor, yarıda kalan/başarısız son deneme açılışta bir saatlik yeniden deneme aralığıyla hesaplanıyor. Bu dosya kişisel bilgi veya kimlik bilgisi içermiyor.
- Yeni yayımlanmış cildin eksik künyesi yeniden okunuyor; dolu sayfa/tarih alanları ezilmiyor. Kaynak ISBN'si başka numaralı ciltte tutuluyorsa veya cildin dolu yerel ISBN'siyle çelişiyorsa mevcut bilgiler korunup inceleme kaydı üretiliyor. Aynı cildin doğrulanmış özel baskı eşleştirmesi korunuyor.
- Kod `996784b` ile main'e yayımlandı; Vercel ve Railway yayın durumları başarılı. Canlı API kontrolü 14 Ekim 08:56–09:02 (Europe/Istanbul) aralığında yapıldı.
- Başlangıç raporundaki 495 seri/baskının tamamı, beş toplu arama isteğiyle yeniden karşılaştırıldı: yayımlanmış cilt sayılarında fark **0**, toplam **2.352**. 38 serinin duyuru listeleri ayrıca kontrol edildi: **47/47**, fark **0**. Jujutsu Kaisen 0 korunuyor (0–20: 21 yayımlanmış cilt, ayrıca 21. cilt yakında).
- Fairy Tail **21 yayımlanmış + 22. cilt yakında**; Nana **7**, Beastars **8**, Black Lagoon **5**, City **1**. Fairy Tail sayfasında “21 cilt”, “1 yakında” ve “Cilt 22” metinleri sunulan HTML'de doğrulandı. Beş fazla-kayıt grubundan birer eski cilt ID'si artık kamuya açık cilt API'sinde 404 veriyor; korunmuş satırlar için bu beklenen davranış.
- Yedi yeni cildin ISBN, sayfa ve çıkış tarihi alanları canlı cilt API'sinde kaynak değerleriyle eşleşiyor: One Piece 62, Naruto 62, Kahramanlık Akademim 33, Dandadan 8, Haikyu!! 22, Nana 7, İskelet Ejderin Küçük Kızı 3.
- Kaynak görüntüsü çalışırken güncellendi: tam ana seri listesi artık **474**; yeni `sekiro-gaiden-shinazu-hanbei` / “SEKIRO-Yan Hikâye: Ölümsüz Hanbei” için 1 yayımlanmış cilt var. Senkron bunu da ekledi. Canlı toplu arama **496 seri/baskı ve 2.353 yayımlanmış cilt** gösteriyor; eski raporun 495/2.352 toplamı yeni kayıtla karıştırılmamalı.
- 23 başlangıç ISBN farkının yedisi giderildi; **16 fark** kanıt incelemesi için açık. Bunların dördü hâlâ boş, 12'si dolu ve kaynakla farklı. ORV (Varyant Kapak) 4 başlangıçta boşken canlıda `9786258630367` olmuş; 14 Ekim'de kaynak sayfası hâlâ normal baskı 1. ciltte de kullanılan `9786258630145` gösteriyor. Dolu kayıt kaynakla ezilmedi; bu yeni dolu ISBN'nin kökeni salt okunur rapordan kanıtlanamıyor. Kaynaktaki tekrarlarla meşru ortak baskılar aynı hata gibi değerlendirilmedi.
- Özel admin oturumu tarayıcı koruması nedeniyle bu çalışmada okunamadı; canlı özel DB satır sayıları ve senkronun özel durum özeti doğrulanmış gibi sunulmuyor. Canlı kanıt kamuya açık API/HTML sonuçlarına, kişisel satır ve fiyat geçmişi koruması ise DB ile çalışan regresyon testlerine dayanıyor.
- Doğrulama: 881 backend testi geçti (`test_task2_identity.py` gerçek eski DB gerektirdiğinden kapsam dışı); son eklenen farklı numaralı özel baskı ISBN korumasıyla dört künye testi ayrıca geçti. TypeScript, ESLint ve Next.js üretim derlemesi başarılı. Tarihli kaynak dışı cildin seri/arama/cilt/takvimden ayrılırken koleksiyon, mağaza kaydı ve fiyat geçmişini koruduğu test edildi.
- Son değişikliklerden sonra katalog senkronu, kalıcı zaman, künye, yayın görünürlüğü, takvim ve audit kapsamındaki 42 test birlikte geçti. Senkron özetinin kalıcı dosyadan okunması ve geciken ilk çalışmanın hemen başlaması uygulandı; admin erişimi açıldığında yeni özel karşılaştırma raporu ayrıca alınabilir.

### 26–28 Eylül: eşleştirme ve fiyatsız seriler
- Katalog cilt eşleştirmesi düzeltildi. Engellenen mağazalar kapatıldı.
- Kaiju No. 8 ve One Piece eşleşmeleri düzeltildi.
- Yayınevi yazım farkları ve takma adları eşleniyor.
- Orijinal başlık öneki ve eksik alt başlıkla eşleşme eklendi.
- Fiyatsız serilerin nedenini gösteren admin paneli eklendi, "fiyatsızları yenile" düğmesiyle birlikte. Edessa mağazası eklendi.

### 29 Eylül: ISBN, tasarım, kapaklar
- **ISBN'ler:** Mangakol cilt sayfalarından katalog ISBN'leri alınıyor. Eşleşme artık ISBN öncelikli; "fiyatsız" sayısını en çok bu düşürdü.
- **Eski kayıtlar ve omnibus:**
  - Eski "Cilt -1" kayıtları doğru cilde birleştiriliyor.
  - ISBN çakışmaları admin panelinden düzeltilebiliyor.
  - 2'si 1 arada ciltler eşleniyor ("İki Cilt Bir Arada", "9&10").
- **Tasarım:** Ana sayfa ve cilt sayfası "editoryal manga kağıdı" temasıyla yeniden tasarlandı (Fraunces + Figtree fontları).
- **Popüler seriler:** Sıralama zamana göre ağırlıklı. Son 30 gündeki istek listesi ve koleksiyon hareketleri 3 kat sayılıyor, sonra cilt başına stok bakılıyor.
- **Kapaklar:** Artık kendi sunucumuzda.
- **Admin:** Yanlış eşleşen mağaza ürünü cilt sayfasından kaldırılabiliyor ve o ürün bir daha eşlenmiyor.

### 30 Eylül
- **BKM ve stok:** BKM'den kaldırılan ürünler siliniyor. Stokta olmayan fiyatlar daha sakin gösteriliyor, satılık ve tükenmiş ürünler ayrı listeleniyor.
- **Yabancı baskılar reddediliyor:**
  - Yabancı ISBN'li ya da dili Türkçe olmayan ürünler eşlenmiyor.
  - ISBN'i ve yayınevi olmayan, başlığında "Vol." ya da VIZ, Kodansha gibi yabancı yayınevi geçen ürünler eşlenmiyor.
  - Admin panelinde yabancı baskı taraması var.
- **Barkodlar:** 978/979 ile başlamayan kodlar mağaza barkodu sayılıyor; yabancı ISBN olarak değerlendirilmiyor.
- **Mavi Kutu (Blue Box):** "Box" ve "Kutu" artık sadece başlığın sonundaysa kutu set sayılıyor. Önceden "Blue Box – Mavi Kutu 4" kutu set sanılıp atılıyordu.
- **Arama sıralaması:**
  - Sıra: tam eşleşme, başlığın başında eşleşme, kelime başında eşleşme, sonra kelime içinde geçenler. Aynı seviyede stokta daha çok satıcısı olan önce gelir.
  - "one" yazınca One Piece, Dr. Stone'dan önce çıkıyor.
- **Özel baskılar / varyantlar:**
  - Mangakol'daki diğer baskı sekmeleri ("Bez Cilt", "3 Cilt 1 Arada") artık ayrı seri olarak ekleniyor, örneğin "Soichi (Bez Cilt)". Katalogdaki kimlikleri `<slug>~clothbound` biçiminde.
  - Mağazalar iki baskıyı da düz "Soichi" diye satıyor; ayrımı ISBN yapıyor.
  - ISBN, başka ciltte duran bir ürünün asıl yerini kanıtlarsa ürün oraya taşınıyor.
- **Varyant ISBN'i geri alma:**
  - Varyantlar gelmeden önce bez cildin ISBN'i başlık eşleşmesiyle normal cilde yazılmıştı (Soichi'de …118).
  - Artık varyantın Mangakol sayfası bu ISBN'i geri alıyor; normal cilt kendi ISBN'ini yeniden okuyor.
  - Admin panelinde varyantlar "başka seriyle eşleşti" yerine şu iki durumdan birini gösteriyor: "özel baskı: ISBN'i henüz okunmadı" ya da "özel baskı: mağazalarda bu ISBN yok".
- **One Shot sekmesi:**
  - Ana sayfadaki raf artık "Seriler" başlığı altında Popüler ve One shot sekmelerine ayrıldı.
  - One shot: Japonya'da ve Türkiye'de tamamlanmış, tek cildi olan seriler. Varyantlar hariç, stokta olanlar önce.
  - JP/TR durumu Mangakol'dan okunuyor (`0012_series_status` veritabanı güncellemesi).

### 1 Ekim: site düzeltmeleri
- **Geri tuşu:** Ana sayfa araması adres çubuğunda (`/?q=`) tutuluyor; seriye girip geri dönünce sonuçlar yerinde.
- **Arama penceresi:** Üstteki Ara düğmesi her sayfada modal arama açıyor (`SearchDialog`).
- **Hero:** `/home?popular=24` havuzundan, kapağı ve stokta fiyatı olan serilerden her yüklemede rastgele 3 kapak; kapaklar ve fiyat kartı tıklanabilir. "Popüler seriler" ilk 8'i gösteriyor.
- **One shot:** Sekme kalktı, "Yeni çıkanlar"ın altında ayrı bölüm.
- **Rakamsız URL'ler:** `/series/<slug>` ve `/series/<slug>/cilt-<n>` (`cilt-numarasiz`). Slug'lar `backend/app/services/series_slugs.py` ile çalışırken türetiliyor (DB'de saklanmıyor); aynı slug'ı paylaşan seride katalogdaki/ilk id düz adı alıyor, diğerine yayınevi ekleniyor. Eski `/series/<id>` ve `/volume/<id>` linkleri kalıcı yönlendiriliyor. API yanıtlarına `slug` / `series_slug` eklendi.

### 13 Ekim: yapılacaklar ve dokümantasyon düzeni

- **Tamamlanan:** Kullanıcının geliştirme ve düzeltme talepleri kökteki [yapılacaklar.md](../yapılacaklar.md) dosyasına 12 ana madde olarak eklendi ve main dalına kaydedildi (`4510146`).
- **Karar:** Yapılacaklar dosyası bekleyen işler için, bu dosya tamamlanan işler ve çalışma geçmişi için kullanılacak.
- **Kod incelemesi:** E-posta/parola üyeliği ve kullanıcı hesabına bağlı veritabanı koleksiyon kayıtları mevcut. Google girişi ve cihazlar arası canlı doğrulama yapılacak işlerdir.
- **Kod incelemesi:** Fiyat alarmları şu an yalnızca koşulu kaydediyor; fiyat koşulunu değerlendiren ve bildirim gönderen aşama henüz uygulanmamış.
- **Kod incelemesi:** İndirim akışı önceki mağaza satış fiyatına göre düşüşü hesaplıyor. Geçmiş düşüşün ardından yükselen fiyatın hâlâ eski fırsat gibi sunulmaması için güncel fiyat doğrulaması gerekiyor.
- **Yeni talep:** İndirim bölümüne “Tüm indirimler” bağlantısı ve tümünü gösteren bir sayfa eklenecek.
- **İstişare konusu — henüz uygulanmadı:** Etiket/liste fiyatına göre indirim ile gözlemlenen satış fiyatı düşüşü farklı ölçülerdir. Örnek: etiket 240 TL, önceki satış 180 TL, güncel satış 170 TL olduğunda etiket farkı yaklaşık %29,2; son satış fiyatındaki düşüş yaklaşık %5,6'dır. Hangi ölçünün ana rozet olacağı ve etiket fiyatının veri kaynağı birlikte netleştirilecek; 180 TL sabit bir referans değildir.

### 13 Ekim: satış fiyatı fırsatları, cilt sayfası ve katalog görünürlüğü

- **İndirim kararı:** Etiket/liste fiyatı ana referans olmayacak. Önceki etiket fiyatı önerisi istişarede geri çekildi; kitapların olağan çevrimiçi satış fiyatına göre gerçek avantaj gösterilecek.
- **Hesap:** Son 30 günlük gözlemlenen en ucuz piyasa satış fiyatlarının süreyle ağırlıklı medyanı kullanılıyor; en az 7 günlük kapsama gerekiyor. Kısa geçmişte sadece önceki gözlemlenen en ucuz fiyatla karşılaştırılıyor ve “tipik fiyat” iddiası yapılmıyor. Eski fiyat kayıtlarında stok bilgisi bulunmadığı için eski aralıklar fiyat geçmişi tahminidir; yeni gözlemler stok ve ürün kimliğini korur, 48 saatten sonra taze gözlem olmadan geçerli sayılmaz.
- **Ana sayfa:** Tipik satış fiyatına göre en az %10 avantaj sunan, güncel ve stoktaki ciltler eşit boyutlu kartlarda gösterilir. Mağaza bazında düşmüş fakat başka mağazada zaten daha ucuz olan teklifler öne çıkarılmaz. Fiyat yeniden yükseldiğinde eski düşük fiyat gösterilmez. Cilt başına tek kart vardır.
- **Tüm indirimler:** `/indirimler` sayfası, 7/14/30 gün seçimi, tarih/oran/TL farkı/güncel fiyat sıralaması ve 24 ciltlik sayfalama eklendi. Küçük düşüşler burada korunur.
- **Cilt sayfası:** Fiyat özetinde ve fırsatı sunan mağaza satırında aynı düşüş bilgisi gösterilir. Tarihsel fırsat bilgisi yoksa tek en ucuz mağazanın diğer mağazalara göre avantajı ayrı ifadeyle gösterilir; bu fark tarihsel indirim olarak adlandırılmaz.
- **Örnek:** Yeterli geçmişte 180 → 144 TL, “36 TL ucuzladı / %20 daha uygun”; 180 → 170 TL küçük düşüş olarak tüm indirimlerde kalır. 180 TL sabit referans değildir.
- **Veri:** `0013_offer_evidence` şema güncellemesi, fiyat geçmişine stok/ürün URL'si ve ciltlere kaynak yayın durumu ekler. Aynı fiyatın sık kontrolleri tekrar yazılmaz; başarılı kontrol gün içinde değişiklik yoksa en fazla günde bir gözlem bırakır. Baskı/ürün değişimi yeni geçmiş olarak ayrılır; eski ürün fiyatları yeni ürüne ait düşüş sayılmaz.
- **Cilt sayısı:** Kaynaktaki “Yakında” bilgisi daha önce okunuyor ama DB'ye taşınmıyordu. Artık taşınıyor. Yalnızca tam ve başarılı kaynak görüntüsünde kaynaktan çıkan ciltler pasif yapılır; kayıtlar, mağaza geçmişleri ve kullanıcı koleksiyonları silinmez. Eksik fragment veya sayfalama sınırı eski ciltleri yanlışlıkla pasif yapmaz. Tarihi belli duyurular erişilebilir kalır.
- **Araştırma:** [14 seri örneklemi ve Fairy Tail bulguları](cilt-sayisi-arastirmasi-2026-10-13.md). Canlı Fairy Tail 52 kayıt/63'e kadar numara içeriyor; 31 kayıtta yerel tarih yok. Bu çalışma ortamında Mangakol 403 döndüğünden, kaynakta güncel 22 cilt bilgisi bağımsız doğrulanamadı. Eksik metadata tek başına silme/gizleme ölçütü yapılmadı.
- **Kontroller:** Backend 867 test geçti (`test_task2_identity.py`, mevcut çalışma düzenindeki gerçek DB gereksinimi nedeniyle hariç). TypeScript, ESLint ve üretim derlemesi geçti. Yeni fırsat ve katalog görünürlüğü senaryoları ayrı regresyon testleriyle doğrulandı.
- **Arayüz doğrulaması:** İzole örnek veritabanıyla gerçek tarayıcıda ana sayfanın 6 kartı, tüm 26 fırsatın iki sayfaya yayılması, sıralama değişince sayfanın sıfırlanması ve cilt sayfasında 144 TL / 36 TL / %20 ortak gösterimi doğrulandı. 320 ve 393 px mobilde yeni sayfa ile cilt sayfasında yatay taşma ve tarayıcı sayfa hatası görülmedi.
- **Canlı adımı:** Kod ve şema yayımlandıktan sonra başarılı bir katalog senkronu gerekir. Şu anki araştırma canlı veritabanını doğrudan değiştirmedi; kaynakla son cilt sayısı kontrolü yapılacaklarda açık tutuluyor.

### 13 Ekim: otomatik Mangakol–Yomiba karşılaştırma aracı

- **Araç:** Yönetici paneline toplu katalog karşılaştırması eklendi. Mevcut Mangakol scraper'ı Yomiba sunucusunda çalışır; tarayıcıdan serileri tek tek incelemek gerekmez.
- **Veri güvenliği:** Başlangıçta sabit bir katalog görüntüsü alınır; işlem DB'ye yazmaz. Kaynak seri/baskı kimlikleri, cilt numaraları ve “Yakında” durumları karşılaştırılır. Kullanıcı hesapları, oturumları ve koleksiyonları rapora alınmaz.
- **Derin kontrol:** İsteğe bağlı ISBN/sayfa sayısı/yerel çıkış tarihi karşılaştırması her kaynak cilt sayfasını okur; seri taramasından daha uzun sürer. Hangi kapsamın çalıştırıldığı ve kaç künye okunduğu raporda belirtilir.
- **Eksik kaynak:** Liste sayfalaması tamamlanmamışsa eski seriler, cilt listesi kısmi ise fazla ciltler tahminen hatalı sayılmaz. Tekrarlayan kaynak hatası taramayı durdurur; sonuç “kısmi” olarak sunulur.
- **Yönetici uçları:** `/catalog/audit` (başlat), `/catalog/audit/status`, `/catalog/audit/snapshot`, `/catalog/audit/report`. Tümü mevcut ADMIN yetkisi gerektirir. Kaynak verisi ve önceki DB görüntüsü JSON raporundan indirilebilir.
- **Kontroller:** 874 backend testi geçti (gerçek yerel DB gerektiren `test_task2_identity.py` hariç); TypeScript, ESLint ve üretim derlemesi geçti. Yönetici yetkisi, salt okunur görüntü, kısmi kaynak ve özel baskı ayrımı test edildi.
- **Canlı sonuç:** İlk tam tarama ve rapor analizi aşağıda kayıtlı; veri düzeltmeleri henüz uygulanmadı.

### 13 Ekim: tam katalog karşılaştırmasının sonucu

- **Tamamlanan:** Kullanıcının indirdiği rapor incelendi ve fark sayıları bağımsız yeniden hesaplandı. Tarama 22:18:51–22:44:26 (İstanbul): 473/473 ana seri, özel baskılarla 495 kayıt, 2.399 cilt künyesi; kaynak hatası yok. [Ayrıntılı rapor](mangakol-yomiba-karsilastirma-2026-10-13.md).
- **Seriler:** Kaynak ve DB katalog kimlikleri eşleşiyor; eksik/fazla seri veya eksik kaynak cildi raporlanmadı.
- **Görünür fazla kayıtlar:** Toplam 57: Fairy Tail 30, Nana 13, Beastars 12, Black Lagoon 1, City 1 numarasız kayıt. Fairy Tail kaynakta 21 yayımlanmış + 22. cilt “Yakında”; Yomiba görüntüsünde 52 görünür kayıt/63'e kadar numara.
- **Duyurular:** 38 serideki 47 tarihsiz “Yakında” cildi normal katalogda görünür. Yayımlanmış ciltlerden ayrılmalı.
- **Durum alanı:** Başlangıç görüntüsünde 2.470 cilt satırının hepsinde `catalog_released=None`. Kaynakla eşleşen 2.399 satır bu yüzden “yayın durumu doğrulanmadı” olarak raporlanıyor; bu sayı yanlış cilt sayısı değildir. Önceki düzeltmenin veriyle işlenmesi henüz doğrulanmış değil; karşılaştırma bir senkron değildir.
- **ISBN:** 23 farkın 12'si boş alan, 11'i iki dolu ISBN farkı. Kaynakta 11 ISBN grubu tekrar ediyor ve 12 ISBN farkını etkiliyor. Aynı numaralı özel baskılar ortak ISBN kullanabilir; farklı cilt/eser tekrarları bağımsız ürün/yayınevi kanıtı gerektirir. Her fark Yomiba hatası kabul edilmedi.
- **Yeni yayınlar:** One Piece 62, Naruto 62, Kahramanlık Akademim 33, Dandadan 8, Haikyu!! 22, Nana 7 ve İskelet Ejderin Küçük Kızı 3 için kaynakta 13 Ekim çıkış tarihi ve künye var; DB alanları boş. Yedi tarih ve yedi sayfa sayısı farkı bunlardan geliyor.
- **Köken incelemesi:** Güncel mağaza importer'ı kaynakta bulunmayan yeni cilt yaratmıyor (`volume_not_found`); mevcut fazla kayıtların eski aktarım kalıntısı olmasıyla tutarlı. Rapordan hangi mağaza/hangi tarih kökeni kesin çıkarılamıyor. 14 eski numarasız kayıt zaten gizli ve korunuyor.
- **Uygulanmadı:** Ham raporda `applied=false`; bu çalışma da DB'yi değiştirmedi. Karşılaştırma tamamlandı olarak işaretlendi, görünürlük/künye/ISBN düzeltmeleri öncelikli açık iş olarak ayrıldı.

## Sıradaki adımlar (30 Eylül push'undan sonra)

1. Railway deploy'unun bitmesini bekle.
2. **Katalog güncellemesi:** JP/TR durumları dolar ve One Shot sekmesi görünür. Varyantlar kendi ISBN'lerini alır.
3. **Katalog güncellemesi, ikinci kez:** Normal ciltler kendi ISBN'lerini okur (Soichi → …101).
4. **Fiyat güncellemesi:** Yanlış yerdeki bez cilt fiyatları varyantlara taşınır.
5. **Kontrol:**
   - Normal Soichi sayfasında Kitapseç'in 385 TL'lik bez cilt fiyatı gitmiş olmalı; Soichi (Bez Cilt) fiyat almalı.
   - Fiyatsız seriler panelinde varyantlar yeni açıklamalarla görünmeli.

## Veri kaynakları araştırması (1 Ekim)

Ayrıntılar `docs/veri-kaynaklari-arastirmasi-2026-10-01.md` dosyasında.

- **En büyük yeni adaylar:**
  - **Kitapyurdu:** artık açık; arama sunucu tarafında oluşuyor ve ürün sayfasında tam JSON-LD var.
  - **idefix:** manga kategorisi taranabiliyor ve satıcılar arasında D&R ile BKM var.
- **Ucuz eklemeler:** Büyülü Dükkan (IdeaSoft), İstanbul Kitapçısı (T-Soft), Ucuzkitapal.
- **Metadata:**
  - **AniList:** tür, etiket ve ONE_SHOT bilgisi.
  - **1000Kitap:** Türkçe özet ve okur puanı.
- Testler bu ağdan yapıldı. Önce Railway'den erişim doğrulanmalı (Cizman örneği).

## Mağaza erişim testi ve yeni mağazalar (1 Ekim)

- **Erişim testi:** Admin paneline "Mağaza erişim testi" eklendi (`3730b8d`). Railway'den yapılan ilk testte:
  - Kitapyurdu **403**: sunucuya kapalı.
  - Amazon 200 döndü (tekrar test edilmeli).
  - D&R 404 döndü: erişim var, arama adresi değişmiş.
  - idefix ve küçük mağazalar açık.
- **Yeni mağazalar:**
  - **Büyülü Dükkan:** Gerekli Şeyler scraper'ının alt sınıfı (IdeaSoft).
  - **İstanbul Kitapçısı:** Kitap Sepeti scraper'ının alt sınıfı (T-Soft).
  - Üst sınıflardaki sabit adlar (`_limits()`, `cls.base_url`, `self.store_id`) genelleştirildi; davranış değişmedi.
- **Canlı uçtan uca deneme:** Büyülü Dükkan Berserk 1–19'u, İstanbul Kitapçısı 1–12'yi eşledi.
- **Ucuzkitapal eklenmedi:** Denenen tüm manga aramalarında (Berserk, One Piece, JJK, Chainsaw Man, Kaiju, Blue Lock, Naruto) her ürün "Stokta yok". Stok gelirse kolay eklenir: CS-Cart, kapak dosya adı ISBN, başlık "Ad - Yazar - Yayınevi" biçiminde.

## Açık fikirler / belki sonra

- Seri sayfalarında "diğer baskılar" bağlantısı (Soichi ↔ Soichi (Bez Cilt)).
- One shot'ların tamamını listeleyen bir sayfa. Ana sayfada şu an en fazla 8 tane gösteriliyor.
- Kapakları Railway volume yerine R2'ye taşımak. Kod buna hazır; Mangakol yedek kaynak olarak duruyor.
- Fiyatsız seriler raporunu yeniden çekip kalanlara bakmak.
