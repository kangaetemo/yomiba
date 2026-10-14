# Yomiba — ISBN Doğrulama ve Admin Onay Sistemi

**Teknik şartname:** v1.0 · **Karar tarihi:** 14 Ekim 2026 · **Durum:** Yalnızca planlandı; kodlama ve canlı DB değişikliği yapılmadı.

> **KODLAYACAK ASİSTANA ÖNEMLİ NOT — İLK ÖNCE BUNU OKU**
>
> Kod yazmadan **önce** mevcut sistemde ISBN yazabilen, değiştirebilen veya başka cilde taşıyabilen **bütün yolları** tara ve raporla: MangaKol katalog senkronizasyonu (`backend/app/services/catalog_sync.py`), mağaza ithalatı (`backend/app/services/import_service.py`), mevcut ISBN düzeltme uçları, admin işlemleri, bakım betikleri ve diğer dolaylı güncelleme yolları. Bu inceleme bitmeden denetim motorunu eklemeye başlama. **ISBN onay kapısını atlayabilecek tek bir yazma yolu kalmamalı.**
>
> **Önce test/staging ve salt okunur tarama.** Canlı veritabanında deney yapma, mevcut veriyi topluca değiştirme, otomatik merge/move/delete yapma. `Volume.id`, kullanıcı koleksiyonları, wishlist, fiyat geçmişi, mağaza ilanları ve yönetici kararları korunmalı. Mevcut işlevlere geriye dönük uyumluluk testleri yaz.

## 1. Amaç ve kesin kararlar

MangaKol entegrasyonu **kaldırılmayacak**. Yomiba'nın kendi kataloğunun ISBN kalitesi, 3–4 bağımsız ürün kaynağından kontrol edilecek; kaynakların ISBN ve ürün kimliği bilgileriyle çelişen veya eksik kayıtlar yönetici incelemesine düşecek.

**Kesinleşmiş ürün kararları:**

1. En az **iki bağımsız kaynak aynı ISBN'yi** ve aynı fiziksel Türkçe manga cildini doğrulamalı; diğer geçerli kaynaklarda **hiçbir çelişki** bulunmamalı.
2. İlk tarama **mevcut tüm yayımlanmış kataloğu** kapsayacak.
3. **Yomiba'da ISBN boşsa**, iki veya daha fazla kaynak eşleşse bile **her durumda admin onayı** gerekecek.
4. Yomiba'daki dolu ISBN farklıysa **otomatik değiştirme olmayacak**. İnceleme + admin onayı gerekecek.
5. Henüz çıkmamış, **Yakında** durumundaki ciltlere ISBN kontrolü veya ISBN eksik bildirimi yapılmayacak. Yayın tarihi geldiğinde durum yeniden değerlendirilip ISBN hâlâ boşsa kontrol başlatılacak. Tarih gelmesi tek başına `catalog_released` değerini otomatik `true` yapmayacak.
6. Zaten doğru olan dolu ISBN, iki bağımsız kanıtla ve çelişkisiz doğrulanırsa `VERIFIED` işaretlenecek; ISBN değişmeyecek ve admin müdahalesi gerekmeyecek.
7. İlk tam tarama ISBN / cilt / ilan / koleksiyon alanlarını **hiç değiştirmeyen salt okunur denetim** olacak; yalnızca denetim sonuçları, kanıt ve inceleme kuyruğu saklanabilir.

## 2. Mevcut kod ve mimariyle entegrasyon

Yomiba: FastAPI + SQLAlchemy + Alembic + Next.js.

Mevcut yapıdaki `Volume.isbn` benzersiz; `Volume.catalog_released`, `Volume.release_date` ve `catalog_present` yayın görünürlüğü için kullanılıyor. MangaKol senkronizasyonu bazı boş ISBN'leri doğrudan yazabiliyor. Mevcut mağaza tarayıcıları ortak `SearchResult` modeliyle ürün başlığı, ISBN, cilt numarası, yayınevi ve URL döndürüyor.

Yeni motor **ayrı bir manga ana kataloğu yaratmayacak**. Mevcut seri ve cilt ID'leriyle çalışacak. Mevcut admin katalog/audit araçları ve kaynak adaptörleri mümkün olduğunca yeniden kullanılacak.

`Volume.isbn` alanının mevcut benzersizlik kısıtı **varsayımsız kaldırılmayacak**. Aynı ISBN'yi paylaşan farklı baskılar (ör. Afro Samuray normal / limitli) ayrı ürünler olarak kalabilmeli, fakat onay öncesinde DB kısıtıyla ve fiyat eşleştirme davranışıyla güvenli biçimde ele alınmalı. ISBN, tek başına güvenilir ürün kimliği sayılmayacak.

## 3. Kaynaklar ve kanıt yapısı

İlk aday kaynaklar: **Kitapyurdu, Pandora, BKM Kitap**, dördüncü kaynak olarak **yayınevi resmî ürün kaydı** veya uygunsa **D&R / Komikşeyler / başka mevcut mağaza**. Bir kaynakta eser listelenmiyorsa orası başarısız sayılmasın; diğer kaynaklara bakılsın.

- Kod deposunda Kitapyurdu ve Pandora için henüz tarayıcı yok; gerekiyorsa yeni adaptör oluşturulmalı.
- BKM ve diğer mevcut mağaza adaptörlerini yeniden kullan; aynı tarama motorunu sıfırdan yazma.
- MangaKol'un verdiği ISBN karşılaştırma ekranında gösterilecek ama **iki bağımsız dış kanıtın biri sayılmayacak**.
- Aynı mağazanın iki sayfası iki ayrı oy değildir. Aynı upstream katalog akışını kullandığı bilinen kaynakların sözde bağımsızlığını sorgula.
- Her kanıt kaydında kaynak kodu, gerçek ürün URL'si, ham başlık, ISBN, seri/cilt, yayınevi, baskı/varyant, kontrol zamanı, erişim durumu ve varsa çelişki/hata gerekçesi yer almalı.
- Kullanım koşullarına ve erişim sınırlarına uy; bot engeli aşmak için koruma atlatma yöntemleri kurma.

## 4. Doğrulama algoritması

### 4.1 Teknik geçerlilik
- ISBN-10 / ISBN-13 normalizasyonu, **kontrol basamağı doğrulaması**.
- ISBN-13 yalnızca kitap ISBN öneki **978 / 979** olabilir; standart ISBN olmayan 13 haneli ürün barkodlarını ayır.
- Geçerli kontrol basamağı = doğru manga/cilt anlamına gelmez.

### 4.2 Ürün kimliği
- Seri başlığı, Türkçe baskı, gerçek **cilt numarası**, yayınevi, kapak/baskı türü, manga–roman ayrımı, omnibus/set ayrımı kontrol edilecek.
- Belirsiz veya yanlış ürüne ait ISBN'yi mutabakat hesabına katma.
- Seri adlarının yerelleştirilmiş/farklı yazılışları için mevcut normalizasyon kullanılsın.
- Kaynağın kendi sayfasında birbirini tutmayan ISBN'ler varsa o kaynak `MISMATCH` / belirsiz kanıt olarak işaretlensin.

### 4.3 Mutabakat örnekleri

| Dış kaynak sonuçları | Sonuç |
| --- | --- |
| A ve B aynı, C aynı; ürün eşleşiyor | `VERIFIED` (Yomiba ISBN de aynıysa) |
| A ve B aynı, C erişilemiyor; ürün eşleşiyor | Dolu ve aynı ISBN için `VERIFIED` |
| A ve B aynı, C farklı | `CONFLICT` → admin |
| A ve B farklı | `CONFLICT` → admin |
| Sadece A'da geçerli ürün eşleşmesi var | `INSUFFICIENT_EVIDENCE` |
| ISBN hiçbir yerde yok, cilt yayımlanmış | `MISSING_ISBN` / inceleme |
| Kaynakların hepsi bloklandı/erişilemedi | `SOURCE_ERROR`, kitapta ISBN yok varsayma |
| A ve B aynı ama yanlış cilt/roman/edisyon | `CONFLICT` / ürün kimliği incelemesi |
| Yomiba boş, A ve B doğru biçimde uyuşuyor | Admin onayına ISBN önerisi |
| Yomiba dolu ama A ve B başka ISBN'de uyuşuyor | Admin onayına düzeltme önerisi; eski değeri koru |

**Teknik kaynak erişim hatası ISBN uyuşmazlığı değildir.** Örneğin HTTP 403 / 429 veya zaman aşımı = `ERROR`; “ISBN yok” değildir. Bir kaynak kitap bulunmasına rağmen ISBN yazmıyorsa `NO_ISBN`, kitap hiç listelenmiyorsa `NO_RESULT`.

## 5. Yayın durumu (Yakında)

- Doğrulanmış `Yakında` ve gelecekte tarihli ciltleri `SKIPPED_UPCOMING` olarak atla; bunlar için admin alarmı açma.
- Yayın tarihi bilinmeyen fakat hâlâ Yakında olarak işaretli ciltleri de otomatik ISBN denetimine sokma.
- Yayın tarihi geldiğinde **denetimi yeniden değerlendir**; ancak ertelenmiş kitapları yanlışlıkla yayımlanmış sayma. Gerektiğinde mağaza listelenmesi veya `catalog_released` gibi ek yayın kanıtı bekle.
- Gerçekten yayımlandığı anlaşılmış ciltte ISBN boşsa dış kaynaklardan ara; bulunsa da bulunmasa da uygun inceleme durumu oluştur.
- Tarih tek başına katalog yayın durumunu değiştiremez.

## 6. Denetim durumları ve veri modeli

Cilt denetim sonuçları: `VERIFIED`, `CONFLICT`, `MISSING_ISBN`, `INSUFFICIENT_EVIDENCE`, `SOURCE_ERROR`, `SKIPPED_UPCOMING`. Yönetici iş akışı: `REVIEW_PENDING`, `REVIEWED`.

Kaynak denetimleri: `MATCH`, `MISMATCH`, `NO_RESULT`, `NO_ISBN`, `ERROR`.

Mevcut katalog alanlarından ayrı bir denetim modeli gerekir:

1. **Denetim çalışması:** ID, başlangıç/bitiş, sonuç, ilerleme, hata sayıları.
2. **Cilt denetimi:** `volume_id`, mevcut ISBN anlık değeri, öneri, sonuç, son kontrol tarihi.
3. **Kanıt:** sağlayıcı, URL, ham ürün künyesi, ISBN, ürün eşleşme sonucu, tarih, hata nedeni.
4. **Admin kararı:** kullanıcı, karar, eski/yeni ISBN, zaman, gerekçe ve dayanak kanıt.

Değişiklik geçmişi kalıcı olacak. Tarama durdurulup başlatıldığında ilerleme kaybolmayacak; aynı şüphe için tekrar tekrar inceleme kaydı oluşmayacak. Kullanıcının önceden verdiği karar sonraki senkronizasyonda ezilmeyecek; yeni çelişki yeni inceleme açabilir.

## 7. Admin paneli

Mevcut `/admin` içine **ISBN Doğrulama / İnceleme Merkezi** ekle.

Özet göstergeler: taranan, doğrulanan, eksik, çelişkili, kanıt yetersiz, admin bekleyen, kaynak hataları, son tarama.

İnceleme kartında: manga adı, cilt, baskı, Yomiba ISBN, MangaKol ISBN, her bağımsız kaynağın ISBN'si, ham ürün başlığı, tıklanabilir URL, kontrol tarihi ve gerekçe.

Yönetici seçenekleri:

- **Mevcut ISBN'yi koru**
- **Önerilen ISBN'yi kabul et**
- **Manuel ISBN gir**
- **İncelemeyi ertele**

Onay uygularken eşzamanlı değişiklik / ISBN benzersizliği / yanlış baskı kontrolleri yeniden yapılacak. `Volume.id` ve ilişkili kullanıcı verileri korunacak. Mağaza ilanları, yalnızca ürün kanıtıyla taşınabilir; sırf ISBN değişti diye otomatik taşınmaz.

## 8. Zamanlama ve dayanıklılık

Öneri (ilk ayarlar değiştirilebilir): yeni yayın / yeni ISBN tetiklemesi; eksik veya çelişkili kayıtlar için günlük; doğrulanmış eski kayıt için haftalık denetim. Gelecek tarihli Yakında ciltlerine ISBN kontrolü yok. Erişim hatası için hız sınırlama, backoff, tekrar deneme ve kaynak bazında hata gösterimi.

Kaynaklardan birinin çökmesi tüm denetimi durdurmayacak. Mağaza ithalatı ve katalog senkronizasyonuyla yarış koşulları/yazma çakışmaları önlenecek. Tekrarlı çalıştırma idempotent olmalı; admin uçları mevcut `require_admin` yetkilerini kullanmalı.

## 9. Uygulama aşamaları (önce test/staging)

**A. Salt okunur doğrulama:** Adaptörler, bibliyografik eşleşme, ISBN algoritması, denetim kayıtları, yayımlanmış tüm kataloğun toplu taraması ve raporu. Kataloğa otomatik yazma yok.

**B. Admin onayı:** İnceleme kuyruğu, kanıt bağlantıları, karar geçmişi, güvenli ve denetlenebilir ISBN uygulaması.

**C. Bütün ISBN yazma yollarında zorunlu onay kapısı:** MangaKol, mağaza ithalatı, mevcut admin düzeltmeleri, bakım betikleri dahil. Yeni ISBN adayı ayrı saklanır; kullanıcı onayı olmadan katalog ISBN'si değişemez. Yayın günü tetikleyicileri ve periyodik kontroller eklenir.

Her aşamada testler bitmeden sonraki aşamaya geçme. Üretim verisini test için kullanma.

## 10. Zorunlu regresyon vakaları

- Blue Lock 29: başka cildin ISBN'sini kabul etme.
- Solo Leveling 2: **novel** ile manga/webtoon baskısını karıştırma.
- Afro Samuray limitli: aynı ISBN ihtimalinde baskıları otomatik birleştirme.
- Yıldızların Sesi: hatalı karşı ürün ISBN'sini ayır; `-1` legacy numarasız cildi kontrolsüz taşıma.
- Omniscient Reader's Viewpoint: ana/varyant kapak ayrımını koru.
- Yakında ve gelecek tarihli boş ISBN: bildirim yok.
- Yayın tarihi gelmiş boş ISBN: yayın durumunu doğrula, gerektiğinde inceleme.
- İki kaynak uyuşuyor, üçüncü çelişiyor: admin.
- İki kaynak uyuşuyor, üçüncü hata veriyor: ürünü doğruluyorsa geçerli mutabakat.
- Tüm kaynaklar erişilemez: `SOURCE_ERROR`, katalog değişmesin.
- Yomiba boş, kaynaklar uyuşuyor: admin onayına kadar yazma yok.
- Önceden onaylanmış ISBN: sonraki sync üzerine yazamıyor.
- Kullanıcı koleksiyonu, wishlist, ilan/fiyat geçmişi ve `Volume.id` değişmiyor.

## 11. Kabul kriterleri ve kapsam dışı

Tamamlanma için: yayımlanmış tüm katalog denetlenebilmeli; minimum iki bağımsız kaynak kuralı ve doğru ürün kimliği uygulanmalı; çelişki ve boş ISBN admin onayına düşmeli; **hiçbir ISBN yazma yolu onay kontrolünü geçememeli**; kullanıcı ve fiyat verisi korunmalı; kanıtlar ve karar geçmişi görüntülenebilmeli; ilk üretim taraması katalogda veri değişikliği yapmamalı.

**Bu görevin kapsamında değil:** MangaKol bağlantısını kaldırmak; bandrolden yeni seri oluşturmak; bağımsız yeni manga keşif motoru; yayınevi isimlerini otomatik birleştirmek; fiyat motorunu baştan yazmak; varyantları topluca merge etmek.

**Nihai hedef:** MangaKol çalışmaya devam ederken ISBN'leri bağımsız doğrulayabilen, mevcut katalogu koruyan ve belirsizlikleri yalnızca yönetici kararıyla çözen kalite kontrol katmanı.
