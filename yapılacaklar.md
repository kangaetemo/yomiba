# Yomiba — Yapılacaklar

Son güncelleme: 13 Ekim 2026

Bu liste, birlikte değerlendirilecek geliştirme ve düzeltme taleplerini içerir. Maddeler henüz tamamlanmış sayılmaz; uygulama ayrıntıları ve öncelikleri istişare sırasında netleştirilecek. Tamamlanan işler, kararlar ve doğrulama sonuçları [Yomiba çalışma notlarına](docs/yomiba-calisma-notlari.md) tarihli olarak yazılır.

## Ana sayfa ve tasarım

- [ ] **İndirim bölümünü yeniden düzenle.** Tasarımı, indirim oranlarının hesaplanmasını ve gösterimini gözden geçir. Özellikle masaüstündeki kötü görünümü düzelt.
  - Etiket/liste fiyatına göre indirim ile gözlemlenen satış fiyatı düşüşünün nasıl sunulacağını birlikte netleştir. Önceki satış fiyatını etiket fiyatı olarak adlandırma; sabit bir fiyat referansı kullanma.
  - Fiyat tekrar yükselmişse eski düşüşü güncel fırsat gibi gösterme; güncel stok ve fiyatı doğrula.
- [ ] **“Tüm indirimler” bağlantısı ve sayfası ekle.** Ana sayfadaki sınırlı seçkinin dışındaki indirimler de görülebilsin.
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
