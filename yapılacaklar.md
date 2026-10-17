# Yomiba — Yapılacaklar

Son güncelleme: 17 Ekim 2026

Bu liste, birlikte değerlendirilecek geliştirme ve düzeltme taleplerini içerir. Maddeler henüz tamamlanmış sayılmaz; uygulama ayrıntıları ve öncelikleri istişare sırasında netleştirilecek. Tamamlanan işler, kararlar ve doğrulama sonuçları [Yomiba çalışma notlarına](docs/yomiba-calisma-notlari.md) tarihli olarak yazılır.

## Yeni yön (16–17 Ekim kararları) — aşağıdaki P0/A/B/C planının yerini alır

Ölçüm: Mevcut ISBN doğrulama sistemi Railway koşullarında 40 ciltten hiçbirini doğrulayamadı; P0 kilidi yeni ciltlere ISBN yazılmasını ve yanlış eşleşme kaldırmayı durdurdu. [Rapor](docs/kesif-kaynaklari-arastirmasi-2026-10-16.md).

- [x] **Sistemin genel taraması (17 Ekim):** Kök nedenler: (1) ISBN'in tek kaynağı Mangakol, kökeni kaydedilmiyor; (2) eşleştirmede ISBN başlıktaki cilt numarasını eziyor, yanlış ISBN iki sayfayı birden bozuyor (`import_service.py` ISBN yolu + `isbn_conflict`); (3) ISBN'siz ciltte baskılar karışıyor; (4) cilt başına tek, global benzersiz ISBN; (5) yanlış ilan taşınamıyor/silinemiyor; (6) ilan, ürünün başlığını/ISBN'ini ve eşleşme kuralını saklamıyor; (7) mağaza kanıtı kataloğu düzeltmek için kullanılmıyor.
  - **Kararlar:** Mağaza kanıtı katalog ISBN'ini sadece kesin durumlarda otomatik düzeltir (kayma hatası; en az 2 mağaza aynı başlık+ISBN, karşı kanıt yok), gerisi kuyruğa; her düzeltme kayıtlı ve geri alınabilir. ~~Şüpheli ilan ziyaretçiye gösterilmez.~~ 17 Ekim akşamı kaldırıldı: fiyatlar gösterilir, hatalar raporda görülüp üzerine gidilir.
- [x] **1. Salt okunur ISBN sağlık raporu (admin):** `/admin/isbn/saglik` (17 Ekim). Kullanıcı canlıda açıp JSON'u paylaşacak.
- [x] **ISBN kanıt sistemi (17 Ekim, `0018_isbn_evidence`):** P0 trigger kilidi kalktı; her ISBN değişikliği `isbn_changes`'e kaynağı ve gerekçesiyle yazılıyor. Ayrıntı: [çalışma notları](docs/yomiba-calisma-notlari.md).
  - [x] Mangakol ISBN'i ayrı alanda (`catalog_isbn`); Mangakol'un iki farklı kitaba verdiği ISBN hiçbirine kendiliğinden yazılmıyor (Blue Lock 28/29).
  - [x] Mağaza uzlaşısı: başlığı bu cildi gösteren en az 2 **bağımsız** mağaza aynı ISBN'i gösterirse ve Mangakol'un kullanılabilir farklı bir ISBN'i yoksa yazılıyor. Aynı veri kaynağını paylaşan mağazalar tek oy (Gerekli Şeyler + Büyülü Dükkan, Kitap Sepeti + İstanbul Kitapçısı).
  - [x] Aynı kitabın baskıları ortak ISBN taşıyabiliyor (`shared_isbns`); baskıyı başlıktaki kelime, yoksa fiyat aralığı seçiyor (Afro Samuray, Solo Leveling 5). `SHARED_ISBN_OWNERS` listesine gerek kalmadı.
  - [x] Eşleştirme: başlık ve ISBN farklı ciltleri gösteriyorsa ürün mağazanın başlığına göre bağlanıyor ve sağlık raporunda listeleniyor (Yubooh Uyurken, Akame Keser). Mevcut ilan sadece yabancı baskı kanıtlanınca kaldırılıyor.
  - [x] Gözlem kaydı (`store_observations`): her ürünün başlığı, ISBN'i, başlığın/ISBN'in gösterdiği cilt ve kural. Okunan ISBN aynı başlıkla tekrar kullanılıyor; Gerekli Şeyler/Büyülü Dükkan detay kotası ISBN'i bilinmeyen ürünlere harcanıyor (Monster 9 VIZ).
  - [x] Fiyat aykırılıkları gizlenmiyor; sağlık raporunda listeleniyor.
  - [x] Admin: cilt sayfasında "ISBN ve eşleşmeler" paneli (bu ilan neden burada, oylar, geçmiş, elle ISBN / ortak / taşı / otomatiğe bırak); yanlış eşleşme kaldırma geri açıldı; sağlık raporu yeni kontrollerle.
  - [x] Codex'in cilt cilt dış kaynak arayan denetimi ve inceleme merkezi kaldırıldı (`/admin/isbn` → sağlık raporu).
- [ ] **Canlıda doğrula (yayından sonra):** 4 senkron içinde Mangakol ISBN'leri okunmuş olacak (`catalog_isbn` sayacı raporda). Sonra sağlık raporunu tekrar al: Blue Lock 28/29, Yubooh, Monster 9, Happiness 6 ve "çözülemeyen çelişkiler" listesi.
- [x] **Özel baskılardaki mağaza barkodları:** 18 Ekim: dokunulmayacak. Yayınevi bazı özel varyantlara ISBN yerine barkod veriyor; mağazalar da aynı kodla satıyor, bu yüzden ürün doğru baskıya bağlanıyor. Solo Leveling Limitli/Varyant 1–3 ve Titana Saldırı: Kayıp Kızlar Limitli'de ISBN alanında barkod duruyor; raporda "geçersiz ISBN". Eşleşmeye etkisi yok (barkod hiçbir ürünü bağlamaz); admin panelinden temizlenebilir.
- [x] **Eski kopya ciltler:** Yıldızların Sesi (2439) ve Komünist Manifesto (2451) ilanları; ürünler bir sonraki taramada doğru cilde taşınıyor, eski satırlar kalıyor. 17 Ekim: #2439 bir sonraki katalog senkronunda #1847'ye birleşir. #2451 başka bir kitap (Kırmızı Kedi baskısı), gizli olarak kalır; Yordam mangasındaki kopya ilanı fiyat taramasında silinir.
- [ ] **Mangakol bağımlılığını bitir:** Mangakol bir besleme olarak kalsın; yeni cilt/seri keşfi kendi kaynaklarımızdan, otomatik. "Yakında" için Mangakol + admin elle giriş. Kaynak seçimi (Bora, Destek Dükkan, idefix, Instagram) şimdilik beklemede.

## P0 ve A/B/C ISBN onay planı (14–15 Ekim) — geçersiz

17 Ekim'de yerini yukarıdaki ISBN kanıt sistemi aldı. P0 kilidi canlıda yeni ciltlerin ISBN almasını ve yanlış eşleşme kaldırmayı durdurmuştu; A/B/C denetimi Railway'de hiçbir cildi doğrulayamadı (40/40 doğrulanamadı). Tarihsel belgeler: [P0 kaydı](docs/isbn-p0-koruma-2026-10-14.md), [şartname](docs/isbn-dogrulama-teknik-sartname-2026-10-14.md), [yazma yolları denetimi](docs/isbn-yazma-yollari-denetimi-2026-10-14.md), [inceleme merkezi](docs/isbn-inceleme-merkezi-2026-10-15.md).

## Öncelikli — Katalog düzeltmeleri

- [x] **57 fazla kayıt ile 47 duyuruyu yayımlanmış katalogdan ayır ve canlıda doğrula.** 14 Ekim: başlangıç raporundaki 495 serinin cilt sayıları tamamen eşleşti; Fairy Tail 21 yayımlanmış + 1 yakında. Satırlar ve kişisel referanslar korunuyor; importer pasif cildi yeniden görünür yapamıyor.
- [x] **Senkronun yeniden başlatmalarda ertelenmesini düzelt ve yeni künyeleri işle.** Kalıcı çalışma zamanıyla açılışta gecikmiş senkron çalışıyor; yedi yeni cildin ISBN/sayfa/tarih alanları canlıda doğrulandı. Kısmi kaynak görüntüsünde pasifleştirme yapılmıyor.
- [x] **Mangakol kataloğu ile Yomiba veritabanını tüm seriler için karşılaştır ve farkları raporla.** 13 Ekim 2026'da tam tarama ve sonuç analizi tamamlandı: 473 ana seri / 495 seri-baskı / 2.399 cilt künyesi; kaynak hatası yok. [Ayrıntılı sonuçlar](docs/mangakol-yomiba-karsilastirma-2026-10-13.md) ve [çalışma notları](docs/yomiba-calisma-notlari.md).

- [ ] **Yeni serilerin Türkçe kapak resimlerini ekle.** Yeni eklenen serilerde kapak görseli Türkçe baskıya ait olmalı; kapak yoksa veya yabancı baskıya aitse Türkçe baskının kapağı bulunup eklenecek. Acil değil.

## Ana sayfa ve tasarım

- [x] **İndirim bölümünü yeniden düzenle.** Eşit boyutlu kartlar, satış fiyatı geçmişine dayalı karşılaştırma, güncel stok/fiyat doğrulaması ve cilt başına tek fırsat uygulandı. Etiket fiyatı referans alınmıyor. Ana sayfa için en az 7 günlük geçmiş ve tipik en ucuz satış fiyatına göre en az %10 avantaj aranıyor. Küçük düşüşler ayrı sayfada görülebiliyor.
- [x] **“Tüm indirimler” bağlantısı ve sayfası ekle.** `/indirimler`: 7/14/30 gün, oran/TL farkı/fiyat/tarih sıralaması ve sayfalama.
- [x] **Fiyat avantajını cilt sayfasında göster.** Fiyat özeti ve ilgili mağaza satırında ortak düşüş bilgisi; yeterli geçmiş yoksa mevcut mağazalar arasındaki avantaj ayrı ifadeyle belirtiliyor.
- [x] **Fairy Tail ve diğer serilerdeki fazla cilt kayıtlarını araştır; genel koruma ekle.** 14 seri örneklemi incelendi. Kaynak yayın durumu ve tam kaynak görüntüsüne göre, kayıt silmeden genel görünürlük düzeltmesi hazırlandı. [Araştırma](docs/cilt-sayisi-arastirmasi-2026-10-13.md).
- [x] **Yayın takvimini küçült.** Takvim alanı çok yer kaplıyor; daha az alan kaplayan bir düzen oluştur. 17 Ekim: yapıldı ([çalışma notları](docs/yomiba-calisma-notlari.md)).
- [x] **“Takip edilen mağazalar” bölümünü kaldır.** Bu ayrı bölüme ihtiyaç yok. 17 Ekim: yapıldı ([çalışma notları](docs/yomiba-calisma-notlari.md)).
- [x] **Ana sayfadaki istatistik alanını kaldır.** “Katalogdaki seri: 495”, “Takip edilen mağaza: 10” ve “Güncel fiyat: 13.314” göstergelerini içeren alana ihtiyaç yok. Sayılar, kaldırılacak alanı tanımlamak için mevcut görünümden örnektir.
- [x] **Ana sloganı daha doğal bir dille yeniden yaz.** Yeni slogan: “Aynı cilt, en uygun fiyat.” “Rafına eklenecek bir sonraki cilt, en uygun fiyatıyla.” sloganı yapay duruyor. Alanın genel fikri ve aşağıdaki açıklama beğeniliyor; yeni slogan birlikte değerlendirilecek.

  > Aynı cildin fiyatını kitapçılarda yan yana gör, stokta olanı tek bakışta bul. Koleksiyonunu tut, istek listeni oluştur, fiyat düşünce haberin olsun.

- [x] **Popüler seriler bölümünü gözden geçir.** Bölümün sunumu ve hangi serilerin gösterileceği birlikte netleştirilecek. 17 Ekim: mağaza çok satan listeleri (idefix, BKM) + yeni cilt + okur ilgisi; yalnız stokta olan seriler.
- [x] **Yeni çıkanlardaki mobil taşmayı düzelt.** Mobilde en soldaki cilt alanın dışına taşıyor. 17 Ekim: yapıldı ([çalışma notları](docs/yomiba-calisma-notlari.md)).
- [x] **Fiyat geçmişini yeniden düzenle.** Mevcut görünüm anlaşılır ve kullanışlı değil; grafik ve sunum biçimi gözden geçirilecek. 17 Ekim: tek çizgi, en düşük stoklu fiyat.
- [x] **Koyu tema anahtarı.** Başlıkta ay/güneş düğmesi; seçim tarayıcıda hatırlanıyor, yoksa cihaz ayarı geçerli. 18 Ekim: yapıldı ([çalışma notları](docs/yomiba-calisma-notlari.md)).
- [x] **Mobil düzeltmeler (18 Ekim ekran görüntüleri).** Fiyat geçmişi değerleri, en düşük fiyat kutusu, istek listesi/koleksiyon kutusu, öne çıkan seri kartı, hero yazısı, seri sayfası araç çubuğu. 18 Ekim: yapıldı ([çalışma notları](docs/yomiba-calisma-notlari.md)).
- [x] **Tek ciltlik serilerde cilt seçme sayfası olmasın.** Seri sayfası doğrudan cildin fiyatlarını açıyor. 18 Ekim: yapıldı ([çalışma notları](docs/yomiba-calisma-notlari.md)).

## Koleksiyon ve istek listesi

- [x] **“Koleksiyonum” durumlarını ve görünümünü sadeleştir.** 17 Ekim: “Bende var” / “Bende yok”; istek listesi ayrı.
  - “Sahibim” yerine “Bende var” gibi daha doğal bir ifade kullan.
  - “Eksik” yerine “Bende yok” gibi daha açık bir ifade kullan.
  - Ayrı bir istek listesi bulunduğu için koleksiyon durumlarındaki “İstediğim” seçeneğini kaldır.
  - Bir cildin kullanıcıda bulunmaması, onu istediği anlamına gelmez. “Bende yok” durumu cildi otomatik olarak istek listesine eklememeli.
  - Son etiketler ve düzen birlikte değerlendirilecek.

## Üyelik ve cihazlar arası kullanım

- [ ] **Üyelik sisteminin mevcut durumunu kontrol et ve eksikleri tamamla; Google ile giriş ekle.** Daha önce hangi parçaların yapıldığı doğrulanacak.
- [ ] **Koleksiyonların bulutta, kullanıcı hesabına bağlı olarak kaydedildiğini doğrula ve eksikleri tamamla.** Cihazlar arasında geçişte aynı koleksiyona erişilebilmeli; mevcut koleksiyonlar korunmalı.

## Fiyat alarmları

- [x] **Çalışmayan fiyat alarmlarını araştır ve düzelt.** Kullanıcı bildirimine göre alarmlar şu an çalışmıyor. Alarm oluşturma, fiyat koşulunun kontrolü ve bildirimin kullanıcıya ulaşması uçtan uca incelenecek.
  - 17 Ekim: alarm kontrolü her fiyat güncellemesinden sonra çalışıyor; eşik geçilince bir kez e-posta kuyruğa giriyor (email_outbox), fiyat eşiğin üstüne çıkınca alarm yeniden kuruluyor. Gönderim şimdilik yalnız SMTP.
- [ ] **Alan adı alınınca alarm e-postalarını devreye al.** Railway Hobby planı SMTP portlarını (25/465/587/2525) engelliyor; bu yüzden gönderim HTTPS API'li bir servise geçirilecek. Öneri: Resend (ücretsiz: günde 100, ayda 3.000 mail). Brevo da olur (günde 300).
  - Alan adını al, Resend'de doğrula (DNS kayıtları).
  - Mailer'a Resend API gönderimini ekle; SMTP yolu Pro plan için kalsın.
  - Railway'e `RESEND_API_KEY`, `MAIL_FROM` (ör. `Yomiba <alarm@alanadi>`) ve `SITE_URL` ekle; deneme alarmıyla uçtan uca doğrula.
