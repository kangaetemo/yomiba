# Yomiba — Yapılacaklar

Son güncelleme: 14 Ekim 2026

Bu liste, birlikte değerlendirilecek geliştirme ve düzeltme taleplerini içerir. Maddeler henüz tamamlanmış sayılmaz; uygulama ayrıntıları ve öncelikleri istişare sırasında netleştirilecek. Tamamlanan işler, kararlar ve doğrulama sonuçları [Yomiba çalışma notlarına](docs/yomiba-calisma-notlari.md) tarihli olarak yazılır.

## Öncelikli — Katalog düzeltmeleri

- [ ] **Karşılaştırmada bulunan katalog farklarını veriyi koruyarak düzelt ve canlıda doğrula.** En yüksek öncelik; 14 Ekim 2026'da uygulama başladı. Kaynakta bulunma ve yayın durumu ayrı tutuluyor; yeniden başlatmalarda senkron zamanı korunuyor. Canlı sonuç doğrulanınca alt işler tamamlandı olarak kaydedilecek.
  - 57 görünür kaynak dışı kayıt: Fairy Tail 30, Nana 13, Beastars 12, Black Lagoon 1 ve City 1 numarasız kayıt. Satırları, fiyat geçmişini ve kullanıcı koleksiyonlarını koruyarak katalog görünümünden ayır.
  - 38 serideki 47 tarihsiz “Yakında” cildini yayımlanmış cilt sayısından ayır. Fairy Tail için “21 yayımlanmış + 1 yakında” durumunu canlıda doğrula.
  - Kaynakla eşleşen 2.399 cildin yayın durumunu işle; rapor görüntüsündeki `catalog_released=None` durumu giderilsin. Kısmi/başarısız kaynak okuması kayıtları yanlışlıkla pasifleştirmemeli.
  - Yedi yeni yayımlanmış cildin boş ISBN/sayfa/çıkış bilgilerini ve diğer çakışmasız boş alanları kontrollü doldur.
  - 23 ISBN farkını ayrı incele: 12 boş alan, 11 dolu ISBN farkı. Kaynaktaki 11 tekrarlanan ISBN grubu nedeniyle her farkı Yomiba hatası varsayma; dolu ISBN'leri ürün/yayınevi kanıtı olmadan ezme. Meşru ortak ISBN'li özel baskıları koru.
  - Fazla satırların eski aktarım kökenini gerekirse ek kanıtla araştır; güncel mağaza importer'ı bulunmayan yeni cilt yaratmıyor. Pasif kayıtlar mağaza taramasında yeniden görünür hâle gelmemeli.
  - Tamamlanan düzeltmeleri çalışma notlarına ekle; eski “Yayımlama sonrası katalog doğrulaması” bu kapsamda devam ediyor.
- [x] **Mangakol kataloğu ile Yomiba veritabanını tüm seriler için karşılaştır ve farkları raporla.** 13 Ekim 2026'da tam tarama ve sonuç analizi tamamlandı: 473 ana seri / 495 seri-baskı / 2.399 cilt künyesi; kaynak hatası yok. [Ayrıntılı sonuçlar](docs/mangakol-yomiba-karsilastirma-2026-10-13.md) ve [çalışma notları](docs/yomiba-calisma-notlari.md).

## Ana sayfa ve tasarım

- [x] **İndirim bölümünü yeniden düzenle.** Eşit boyutlu kartlar, satış fiyatı geçmişine dayalı karşılaştırma, güncel stok/fiyat doğrulaması ve cilt başına tek fırsat uygulandı. Etiket fiyatı referans alınmıyor. Ana sayfa için en az 7 günlük geçmiş ve tipik en ucuz satış fiyatına göre en az %10 avantaj aranıyor. Küçük düşüşler ayrı sayfada görülebiliyor.
- [x] **“Tüm indirimler” bağlantısı ve sayfası ekle.** `/indirimler`: 7/14/30 gün, oran/TL farkı/fiyat/tarih sıralaması ve sayfalama.
- [x] **Fiyat avantajını cilt sayfasında göster.** Fiyat özeti ve ilgili mağaza satırında ortak düşüş bilgisi; yeterli geçmiş yoksa mevcut mağazalar arasındaki avantaj ayrı ifadeyle belirtiliyor.
- [x] **Fairy Tail ve diğer serilerdeki fazla cilt kayıtlarını araştır; genel koruma ekle.** 14 seri örneklemi incelendi. Kaynak yayın durumu ve tam kaynak görüntüsüne göre, kayıt silmeden genel görünürlük düzeltmesi hazırlandı. [Araştırma](docs/cilt-sayisi-arastirmasi-2026-10-13.md).
- [ ] **Yayın takvimini küçült.** Takvim alanı çok yer kaplıyor; daha az alan kaplayan bir düzen oluştur.
- [ ] **“Takip edilen mağazalar” bölümünü kaldır.** Bu ayrı bölüme ihtiyaç yok.
- [ ] **Ana sayfadaki istatistik alanını kaldır.** “Katalogdaki seri: 495”, “Takip edilen mağaza: 10” ve “Güncel fiyat: 13.314” göstergelerini içeren alana ihtiyaç yok. Sayılar, kaldırılacak alanı tanımlamak için mevcut görünümden örnektir.
- [ ] **Ana sloganı daha doğal bir dille yeniden yaz.** “Rafına eklenecek bir sonraki cilt, en uygun fiyatıyla.” sloganı yapay duruyor. Alanın genel fikri ve aşağıdaki açıklama beğeniliyor; yeni slogan birlikte değerlendirilecek.

  > Aynı cildin fiyatını Türkiye'deki kitapçılarda yan yana gör, stokta olanı tek bakışta bul. Koleksiyonunu tut, istek listeni oluştur, fiyat düşünce haberin olsun.

- [ ] **Popüler seriler bölümünü gözden geçir.** Bölümün sunumu ve hangi serilerin gösterileceği birlikte netleştirilecek.
- [ ] **Yeni çıkanlardaki mobil taşmayı düzelt.** Mobilde en soldaki cilt alanın dışına taşıyor.
- [ ] **Fiyat geçmişini yeniden düzenle.** Mevcut görünüm anlaşılır ve kullanışlı değil; grafik ve sunum biçimi gözden geçirilecek.

## Koleksiyon ve istek listesi

- [ ] **“Koleksiyonum” durumlarını ve görünümünü sadeleştir.**
  - “Sahibim” yerine “Bende var” gibi daha doğal bir ifade kullan.
  - “Eksik” yerine “Bende yok” gibi daha açık bir ifade kullan.
  - Ayrı bir istek listesi bulunduğu için koleksiyon durumlarındaki “İstediğim” seçeneğini kaldır.
  - Bir cildin kullanıcıda bulunmaması, onu istediği anlamına gelmez. “Bende yok” durumu cildi otomatik olarak istek listesine eklememeli.
  - Son etiketler ve düzen birlikte değerlendirilecek.

## Üyelik ve cihazlar arası kullanım

- [ ] **Üyelik sisteminin mevcut durumunu kontrol et ve eksikleri tamamla; Google ile giriş ekle.** Daha önce hangi parçaların yapıldığı doğrulanacak.
- [ ] **Koleksiyonların bulutta, kullanıcı hesabına bağlı olarak kaydedildiğini doğrula ve eksikleri tamamla.** Cihazlar arasında geçişte aynı koleksiyona erişilebilmeli; mevcut koleksiyonlar korunmalı.

## Fiyat alarmları

- [ ] **Çalışmayan fiyat alarmlarını araştır ve düzelt.** Kullanıcı bildirimine göre alarmlar şu an çalışmıyor. Alarm oluşturma, fiyat koşulunun kontrolü ve bildirimin kullanıcıya ulaşması uçtan uca incelenecek.
