# Cilt sayısı araştırması — 13 Ekim 2026

## Kapsam ve yöntem

Canlı Yomiba'nın herkese açık `/api/home?hero=true`, `/api/series/<slug>` ve seçili `/api/volume/<id>` yanıtları salt okunur olarak incelendi. En uzun seriler ağırlıklı 14 seri örneklemi kullanıldı; bütün veritabanının kaynakla bire bir doğrulandığı iddia edilmiyor.

Mangakol Fairy Tail sayfası bu çalışma ortamında HTTP 403 verdi. Kullanıcının kaynakta gördüğü 22 cilt bilgisi önemli bir karşılaştırma; güncel kaynak listesinin tamamı bu ortamdan bağımsız doğrulanamadı. Aşağıdaki tarih yokluğu tek başına yanlış kayıt kanıtı değildir.

## Canlı bulgular

| Seri | Yomiba kayıt sayısı | En büyük cilt numarası | Yerel çıkış tarihi olan | Tarihsiz | Tarihsiz ve mağaza kaydı olmayan |
|---|---:|---:|---:|---:|---:|
| One Piece | 62 | 62 | 61 | 1 | 1 |
| Naruto | 62 | 62 | 61 | 1 | 1 |
| Fairy Tail | 52 | 63 | 21 | 31 | 17 |
| Bleach | 48 | 48 | 48 | 0 | 0 |
| Titana Saldırı | 34 | 34 | 34 | 0 | 0 |
| Kıyamet Meleği | 34 | 34 | 34 | 0 | 0 |
| Kahramanlık Akademim | 33 | 33 | 32 | 1 | 1 |
| Tek Yumruk | 30 | 30 | 30 | 0 | 0 |
| Blue Lock | 30 | 30 | 30 | 0 | 0 |
| Yedi Ölümcül Günah | 30 | 30 | 30 | 0 | 0 |
| Yalnız Kurt ve Yavrusu | 28 | 28 | 28 | 0 | 0 |
| Metal Simyacı | 27 | 27 | 27 | 0 | 0 |
| Gecenin Çağrısı | 7 | 7 | 6 | 1 | 1 |
| Akame, Keser! | 14 | 14 | 14 | 0 | 0 |

Fairy Tail'da 52 kayıt var, numaralar 63'e kadar çıkıyor. Bunların 31'inde yerel çıkış tarihi yok. 22 ve 23'te ISBN ve fiyat yok; 62'de ISBN/tarih yok ve eski Kitapbulan teklifi stok belirsiz. Bu teklif yabancı baskı olduğuna dair tek başına kesin kanıt değildir. Fairy Tail 19 ise ISBN 9786255606402 ile, Kitapbulan 144 TL ve dört başka mağaza 180 TL olarak doğrulandı.

## Kodda doğrulanan sorunlar ve çözüm

1. Kaynak parser'ı “Yakında” bilgisini `CatalogVolume.released=False` olarak okuyordu; senkron bu bilgiyi veritabanına taşımıyordu. Artık `Volume.catalog_released` alanına taşınıyor.
2. Senkron sadece cilt ekliyor, kaynak listesinden çıkan eski ciltleri kamuya açık listelerde bırakıyordu. Tam, boş olmayan ve tek kaynak kimliğine sahip başarılı bir kaynak görüntüsü geldikten sonra artık bu kayıtlar pasif işaretleniyor. Veritabanı satırları ve kullanıcı koleksiyonları silinmiyor.
3. Fragment isteği başarısızsa veya sayfalama bütçesi tükenirse görüntü eksik sayılır. Bu durumda görülmeyen eski ciltler pasif yapılmaz.
4. Tarihi belli olan duyurular yayın takviminde ve ilgili sayfalarda erişilebilir kalır. Tarihsiz “Yakında”/kaynak dışı kayıtlar normal katalog cilt sayısını şişirmez.
5. Eski, henüz doğrulanmamış satırlar yalnızca ISBN/fiyat/tarih yok diye tahminen gizlenmez. Durumları sonraki başarılı kaynak senkronunda güncellenir. Mağaza importer'ı kaynakta pasif işaretlenmiş cilde yeni teklif yazmaz.

## Canlıda kalan doğrulama

Yeni şema ve kod yayımlandıktan sonra başarılı bir katalog güncellemesi gereklidir. Ardından Fairy Tail ve örneklemdeki diğer serilerin cilt sayıları kaynakla tekrar karşılaştırılmalıdır. Bu çalışma sırasında canlı veritabanı doğrudan değiştirilmedi; 22 cilt sabiti veya elle silme uygulanmadı.
