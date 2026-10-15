# ISBN İnceleme Merkezi · 15 Ekim 2026

## Ürün akışı

`/admin` içindeki **ISBN Doğrulama / İnceleme Merkezi** bağlantısı
`/admin/isbn` ekranını açar. İlk taramayı yönetici başlatır. İlerleme,
duraklatma/sürdürme, sonuç ve iş akışı filtreleri, seri araması, sayfalama,
ürün kanıtları ve karar geçmişi aynı ekrandadır.

Tarama yalnız yeni denetim tablolarına yazar. Etkin katalogdaki tüm ciltler
kalıcı çalışma listesine alınır; backfill bütçesi kullanılmaz. Yayımlandığı
doğrulanmayan veya gelecekte tarihli ciltler dış kaynak sorgulanmadan atlanır.
Tarihin geçmesi `catalog_released` değerini değiştirmez. Pasif kayıtlar
kuyruk ve özetlerden çıkarılır; eski kanıt ve kararları saklanır.

İki ayrı kaynak grubu aynı fiziksel baskı ve aynı geçerli ISBN üzerinde
uyuşursa dolu ve aynı ISBN `VERIFIED` olur. Boş veya farklı ISBN yönetici
onayı bekler. Üçüncü kaynaktaki geçerli çelişki onayı engeller; erişim hatası
yokluk veya farklı ISBN diye yorumlanmaz. MangaKol bilgisi ayrıca gösterilir
ve bağımsız kaynak sayılmaz.

**Mevcut ISBN’yi koru**, **Önerilen ISBN’yi kabul et**, **Manuel ISBN gir** ve
**İncelemeyi ertele** kararlarının hepsi gerekçe ister. Manuel giriş de iki
taze bağımsız kanıt kuralına tabidir. ISBN boşaltma, iki kayıt arasında ISBN
transferi, cilt/seri birleştirme ve ilan taşıma bu ekranda açılmamıştır.
Benzersiz ISBN indeksi korunur; ortak ISBN iddiası başka cilde uygulanmaz.

## Kaynak erişimi ve sınırlar

15 Ekim'de salt okunur gerçek ürün denemesi:

| Kaynak | Sonuç |
|---|---|
| Kitapyurdu | Ürün başlığı, yayınevi, Türkçe dil, karton kapak ve ISBN okundu. |
| BKM | Mevcut arama adaptörü ve BKM'nin kendi ürün sayfasından aynı künye okundu. |
| Pandora | robots.txt / ürün erişimi HTTP 403; koruma aşılmadı, `ERROR`. |
| D&R | robots.txt HTTP 403; koruma aşılmadı, `ERROR`. |

İki çalışan adaptörün aynı ürünü doğruladığı örnek ISBN **9786256449305**:
[Kitapyurdu](https://www.kitapyurdu.com/kitap/solo-leveling-novel-cilt-1/667345.html),
[BKM](https://www.bkmkitap.com/solo-leveling-novel-cilt-1).
Bu örnek katalogda bir düzeltme veya tam üretim taraması yapıldığı anlamına gelmez.

Pandora'nın erişilebilir GET arama formu bulunamazsa adaptör açık kaynak
hatası döndürür; canlı ürün ayrıştırması engel nedeniyle doğrulanamadı.
D&R mevcut adaptörü yeniden kullanılır. Şablon tanınmaması, eksik sayfalama,
403/429 ve bağlantı hataları `NO_RESULT` yapılmaz. Aynı kaynaktaki başarısız
ürün, o kaynağın daha önce okunan çelişkili ürün kanıtını silmez.

Kaynaklara robots kontrolü, en az bir saniye aralık, izinli HTTPS alan adları,
yönlendirme kontrolü ve artan hata bekleme süresi uygulanır. Kaynak grupları
`kitapyurdu`, `bkm`, `pandora`, `dr` şeklindedir. BKM'nin WAW araması ile BKM
ürün sayfası **tek** kaynaktır. Bilinen ortak upstream bilgisi oluşursa
`ISBN_SOURCE_GROUPS` JSON ayarıyla ilgili sağlayıcılar aynı gruba alınır;
ayar değişikliği eski kanıtla onay verilmesini engeller. Ayrı perakendeci
ürün kayıtları kullanılması, tüm yayıncı veri akışlarının bağımsızlığına dair
bir garanti olarak sunulmaz.

## Kalıcılık ve onay kapısı

`0016_isbn_audit`: çalışma, çalışma öğesi, değişmez kanıt/sonuç, cilt başına
tek inceleme ve değişmez karar tabloları. Aynı şüphe için kuyruk çoğalmaz.
ISBN/kimlik anlık görüntüsü ile kanıt özeti ve inceleme sürümü saklanır.
Anlamlı kanıt değişikliği yoksa önceki yönetici kararı yeniden açılmaz.

`0017_isbn_approval`: eski P0 kimlik/silme/replace kilitleri korunur.
Yalnız `isbn_p0_volume_update` tanımı, **aynı transaction içinde** tüketilen
tek kullanımlık yönetici kararı iznine daraltılır. Normal bağlantının
`isbn_approval_token()` işlevi `NULL` döner. Yalnız karar servisi bağlantıya
geçici yetki verir, kararı ve izin satırını ekler, sadece `Volume.isbn`
alanını günceller ve izni tüketir. Yetki `finally` içinde sıfırlanır.
İzin satırı başka bağlantıya görünür halde commit edilmez.

Yazma kilidi altında aktif admin, güncel inceleme sürümü, kaynak grupları,
güncel ISBN, katalog üyeliği ve baskı alanları, kanıt bütünlüğü, kaynak ürün
URL'leri, en çok 24 saatlik kanıt ve ISBN-10/13 eşdeğer benzersizlik yeniden
kontrol edilir. Başarısız işlem kararı/izni/ISBN'yi birlikte geri alır.
Admin onayı cilt ID'si, ilan, fiyat geçmişi veya kişisel ilişki değiştirmez.

DB sahibinin trigger silme / Python bağlantısına özel işlev kaydetme yetkisi
güven sınırıdır; P0'da olduğu gibi DB root erişimine karşı bir güvenlik
ürünü iddiası yoktur. Normal ham SQLite, ORM, bulk update ve eski bakım
betikleri kapıyı atlayamaz. Kanıt/karar `UPDATE`, `DELETE` ve `REPLACE`
işlemleri ayrıca engellenir. Readiness yeni tabloları, 34 trigger tanımını
ve kalmış izin bulunmamasını doğrular.

## Zamanlama ve yeniden başlatma

İlk tamamlanan yönetici taramasından sonra günlük çözülmeyen/ertelenen
kayıtlar ve haftalık doğrulanan kayıtlar taranır. Yeni ciltler sonraki
periyodik çalışmaya eklenir. Onay uygulandıktan sonra o cildin yeniden
denetimi geciktirilmez. Yakında durumu günlük yeniden değerlendirilir,
fakat yayın kanıtı gelmeden ISBN alarmı açılmaz.

İş listesi ve her tamamlanan cildin sonucu DB'dedir. HTTP sırasında yazma
transaction'ı tutulmaz. Çalışma sahibi için 30 saniyede yenilenen 10 dakikalık
kira bulunur. Süreç ölürse kira dolunca başka süreç kayıtlı ilerlemeden
sürdürür. Duraklatma devam eden kaynak isteği bittiğinde etkili olur.
Bir açık tarama varken ikinci tarama başlatılmaz.

## Doğrulama ve yayın

Sentetik testler checksum/ISBN-10 eşdeğerliği, yanlış cilt, novel/webtoon,
normal/limitli/varyant, omnibus, kağıt ve kapak türü, `-1`, Yakında, kaynak
hataları, aynı gruptan iki oy, sürüm/kimlik eskimesi, benzersizlik,
eşzamanlı onay, ham SQL/ORM/replace/izin sahteciliği ve ilişkilerin
korunmasını kapsar. Yeni HTTP onay akışı gerçek migration zinciri ve
korumalarıyla geçici DB üzerinde çalıştırıldı.

Tarayıcıda geçici test yöneticisiyle tarama → kuyruk → iki ürün kanıtı →
gerekçeli ISBN onayı → kuyruktan çıkış → karar geçmişi → yeniden `VERIFIED`
akışı kontrol edildi. Hiçbir test üretim DB'sinde CRUD işlemi yapmaz.
18 tarihsel snapshot testi, takip edilmeyen eski DB dosyası istediği için
güncel test komutundan ayrıdır. GitHub Actions Linux'ta gerçek POSIX dosya
izinleri dahil arka uç testlerini, ön yüzde lint ve üretim derlemesini çalıştırır.

Yayın hazırlığındaki kesin test sonuçları ve CI bağlantısı PR açıklamasındadır.
Üretim yayını ve ilk tam canlı katalog taraması ayrı doğrulama adımıdır;
bu geliştirme sırasında canlı ISBN uygulanmamıştır. Önce güncel yedek ve
restore provası, sonra backend migration/readiness, ardından frontend,
en son admin oturumuyla salt okunur ilk tarama yapılır.

Geri dönüşte trigger veya tarihçe tabloları silinmez. ISBN onay uçları
kapatılarak P0'nun katı `volume_update` tanımı ileri düzeltme transaction'ı
ile geri konabilir; veriler korunur. `alembic downgrade` bilerek reddedilir.
Uygulama kodunu 0015'e tek başına geri almak readiness'i bozacağından
kontrollü ileri düzeltme veya doğrulanmış yedek planı kullanılmalıdır.
