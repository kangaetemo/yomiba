# Yomiba — ISBN yazma yolları denetimi

**Tarih:** 14 Ekim 2026 · **Kapsam:** Teknik şartname öncesi zorunlu mevcut-kod incelemesi.

**İncelenen sürüm:** `main`, `33bfdc407bd26793a1ba1316aa395fec123d3dcb`.
**Dayanak:** [ISBN doğrulama ve admin onay teknik şartnamesi v1.0](isbn-dogrulama-teknik-sartname-2026-10-14.md).
**İşlem sınırı:** Uygulama kodu, migration veya canlı katalog değiştirilmedi. Bu rapor onay kapısını kurmaz; mevcut otomatik ISBN yazmaları hâlâ mevcut kodun davranışıdır.

## 1. Sonuç

**Mevcut sistem yeni şartnamedeki zorunlu ISBN onay sürecini uygulamıyor.** Yalnızca yeni bir doğrulama ekranı eklemek yeterli olmayacak: mevcut katalog senkronu ve mağaza aktarımı o ekranı kullanmadan ISBN yazmaya devam edebilir.

- **Yedi dosyada 18 doğrudan ISBN atama/güncelleme noktası** bulundu. ISBN silme, başka cilde taşıma ve boş alan doldurma bu sayıya dahildir. Kaynak cilt/seri satırını silen veya kimliğini taşıyan dolaylı yollar ayrıca listelendi.
- Mangakol boş ISBN doldurabiliyor, yabancı sayılan ISBN'yi değiştirebiliyor, normal/özel baskı arasında ISBN taşıyabiliyor ve eski numarasız satırı otomatik birleştirebiliyor.
- Mağaza aktarımı tek mağaza sonucuyla boş ISBN doldurabiliyor. **Yakında/pasif cilde ilan yazılması engellense bile ISBN daha önce yazılıp commit ediliyor.** Bu davranış izole DB'de doğrulandı.
- ISBN normalizasyonu kontrol basamağını doğrulamıyor. Hatalı kontrol basamağı olan bir ISBN'nin katalog ISBN'sine yazılması izole DB'de doğrulandı.
- Admin araçları giriş yetkisi, önizleme ve bazı uygulama kontrolleri içeriyor. Ancak yeni şartnamenin istediği ortak karar kaydı, iki bağımsız kanıt, kararın sonraki senkronlarda korunması ve bütün yazıcılara uygulanan onay kapısı yok.
- ISBN metnini korumak tek başına yeterli değil: bazı merge/delete yolları `Volume.id`, ilan bağlantısı ve fiyat geçmişini de etkileyebiliyor.

**Zorunlu ön inceleme tamamlandı.** Onay kapısının uygulanması, kaynak adaptörleri ve yeni doğrulama motoru henüz yapılmadı; A/B/C aşamaları açık kalıyor.

## 2. İnceleme yöntemi ve sınırlar

GitHub'daki sürümün tam dosya ağacı alındı; ağaç kesilmemişti. İncelenen yerel **254 kod/betik dosyasının** Git blob hash'leri bu sürümle tek tek eşleşti. Bunların 192'si Python; 122 Python dosyası test dizininin dışında. Ayrı `.sql` dosyası yok; doğrudan SQL bakım betiklerinin Python metinlerinde bulunuyor. Shell betiği ve frontend admin çağrıları da tarandı.

Tarama; `.isbn` atamalarını, SQLAlchemy `values(isbn=...)` yazmalarını, ham `UPDATE ... isbn`, cilt/seri silmelerini, kimlik taşıyan merge işlevlerini, bunların çağıranlarını ve commit noktalarını kapsadı. Scraper'ın `SearchResult.isbn` üretmesi ile gerçek `Volume.isbn` yazması ayrı değerlendirildi. Metin taraması Python AST taraması ve hedef işlevlerin okunmasıyla kontrol edildi.

Canlı DB açılmadı, dış ürün sayfası taraması veya canlı ISBN düzeltmesi çalıştırılmadı. Dört davranış deneyi `sqlite:///:memory:` üzerinde sahte mağaza sonuçlarıyla yapıldı. Testler kendi geçici DB'lerini kullandı.

Bu rapor depodaki bilinen girişleri kapsar; operatörün depodan bağımsız SQL çalıştırması veya DB dosyasını dışarıdan değiştirmesi hakkında garanti vermez. Canlıda bu yolların hangi kitapta ne zaman çalıştığını gösteren işlem geçmişi yeniden oluşturulmuş değildir.

## 3. Doğrudan ISBN yazma envanteri

Satır numaraları yukarıdaki sabit sürüme aittir. Aynı işlevin farklı dalları farklı onay atlama yollarıdır.

| Yol | Kaynak / satır | Mevcut davranış | Mevcut yetki veya kontrol | Yeni süreçte gerekli işlem |
|---|---|---|---|---|
| Mangakol boş alan doldurma | `backend/app/services/catalog_sync.py`, `_backfill_isbns`, 494–495 | Kaynak ISBN başka satırda tutulmuyorsa mevcut cilde yazar ve commit eder. | Kaynak okuması, bütçe, yayın durumu, bazı çakışma kontrolleri; cilt bazında admin kararı yok. | ISBN adayını ayrı kaydet; boş alan yalnız admin kararıyla dolsun. |
| Mangakol yabancı ISBN temizleme/değiştirme | Aynı dosya, 487–495 | Yabancı sayılan eski ISBN'yi `None` yapar; boşta olan kaynak ISBN'yi yazabilir. | Türkiye ISBN öneki sınıflandırması; iki dış kanıt veya kalıcı karar yok. | Temizleme de değişikliktir; mevcut değeri koru ve incelemeye gönder. |
| Özel baskıdan normal baskıya taşıma | Aynı dosya, 515–525 | Eski sahibin ISBN'sini siler, normal cilde verir. | Baskı ailesi ve farklı numara koruması; admin kararı yok. | Ortak ISBN/baskı incelemesi; otomatik sahip değiştirme olmasın. |
| Normal baskıdan varyanta taşıma | Aynı dosya, 530–546 | Ana cildin sayfası aynı ISBN'yi göstermiyorsa ISBN'yi varyanta taşıyabilir. | Ana sayfa okuması; okunamayan sayfa da `None` dönebilir. | `SOURCE_ERROR` ile gerçek olumsuz kanıt ayrılmalı; taşıma yalnız karar sonrası. |
| Sabit ortak-ISBN sahibine taşıma | Aynı dosya, 552–561 | `SHARED_ISBN_OWNERS` sahibine ISBN taşır. | Sabit kitap/baskı eşlemesi; yeni karar kaydı yok. | Meşru ortak baskıyı koruyan, açık ve kayıtlı karar gerektirir. |
| Mağaza aktarımında boş ISBN doldurma | `backend/app/services/import_service.py`, `_resolve_volume`, 1180–1181 | Seri/cilt eşleşmişse tek mağaza ISBN'sini boş cilde yazar. | Normalizasyon, katalog kimliği ve dolu-ISBN çakışma koruması; admin kararı yok. | Eşleştirme salt okunur olmalı; aday ayrı kaydedilmeli. |
| Numara belirsiz satırın ISBN'sini birleştirme | `backend/app/services/phantom_review.py`, `merge_volume_rows`, 102 ve 114–116 | Kaynak ISBN'yi temizler, hedef boşsa taşır; kaynak cildi siler. | Alt işlev karar/kişisel veri kontrolünü kendisi yapmıyor; çağıranın yapmasını varsayıyor. | ISBN kararı merge yetkisi sayılmamalı; bu görevin otomatik denetiminde çağrılmamalı. |
| Bilinen ISBN düzeltmesi | `backend/app/services/isbn_conflict_fix.py`, `apply_case`, 128–129 | Yanlış cildin ISBN'sini temizler, hedefe yazar. | API'de admin; CLI'da `--apply`; DB önkoşulları, yedek ve transaction. Ortak karar kaydı yok. | Admin/CLI aynı kalıcı karar ve onay uygulama servisini kullanmalı. |
| Yabancı baskı temizliği | `backend/app/services/foreign_editions.py`, `apply_plan`, 129–135 | Planın yabancı saydığı ISBN'leri `None` yapar; künye kontrol zamanını sıfırlar. | Admin önce tarayıp uygular; eski değer eşitliği kontrol edilir. | ISBN temizliği ayrı karar olarak kaydedilmeli; sonraki sync sessizce yeniden doldurmamalı. |
| Eski Task 2 SQL bakım yazmaları | `backend/apply_task2_merges.py`, 186 ve 214 | Naruto kaynak ISBN'sini hedefe kopyalar; Orange ISBN'sini sabit değerle yazar. | Tarihsel snapshot/önkoşullar ve transaction; normal admin akışını kullanmaz. | Canlı için emekliye ayrılmalı veya yeni karar sürecine geçirilmelidir. |
| Eski Task 3 SQL bakım yazmaları | `backend/apply_task3_cleanup.py`, 312 ve 372 | İki hedef ISBN'sini sabit değerlerle doldurur. | Tarihsel snapshot/önkoşullar ve transaction; ortak karar kaydı yok. | Aynı kural; tarihsel onay yorumu yeni sistem onayı değildir. |

İlk beş tablo satırı aynı dosyadaki sekiz `.isbn` atamasını kapsar. Toplam doğrudan yazıcı dosyaları: `catalog_sync`, `import_service`, `phantom_review`, `isbn_conflict_fix`, `foreign_editions`, `apply_task2_merges`, `apply_task3_cleanup`.

### Koruma var, fakat yeni onay süreci değil

Mangakol dalında dolu yerel ISBN farklıysa veya kaynak ISBN farklı numaralı bir ciltteyse mevcut kayıt korunuyor (`catalog_sync.py`, 443–480). Bu yararlı koruma boş ISBN yazmayı, aynı numaralı baskılar arasında sahip değiştirmeyi ve eski numarasız satır merge'ünü engellemiyor.

`trusted_isbn` adı bağımsız doğrulama anlamına gelmiyor: burada esasen ISBN'nin dolu ve yabancı sayılmaması kontrol ediliyor. Dolu ISBN'li ve daha önce kontrol edilmiş ciltler çoğunlukla tekrar okunmuyor. İlk tam bağımsız denetim bu mevcut backfill döngüsünü kullanarak bütün kataloğu doğrulamış sayılamaz.

## 4. Dolaylı kimlik, merge ve geçmiş etkileri

| Yol | Kanıt / çağrı | Etki ve değerlendirme |
|---|---|---|
| Otomatik eski numarasız cilt merge'ü | `catalog_sync.py`, 501–508; `phantom_review.merge_volume_rows` | Aynı seride ISBN'yi tutan negatif numaralı satırda kişisel veri yoksa senkron helper'ı doğrudan çağırıyor. Daha sıkı `plan_merge/apply_safe_merge` ürün kanıtı planından geçmiyor. Hedef ISBN, ilanlar ve history bağlantıları değişiyor; kaynak `Volume.id` siliniyor. |
| Manuel güvenli merge helper'ı | `phantom_review.py`, `apply_safe_merge`, 70–82 | Ürün başlığı/yayınevi/ISBN kanıtı ve kişisel veri koruması var; ayrı CLI/API yazma ucu bulunmadı. Ancak docstring'deki “çağıran açıkça onaylamalı” şartı kalıcı admin karar nesnesiyle uygulanmıyor. |
| Yayıncı/seri birleştirmesi | `catalog_sync.sync`, 198; `_merge_publisher_into`, 769–777; `_merge_series_into`, 814–902 | ISBN backfill'inden önce çalışabilir. Çakışmayan cilt başka seriye taşınır; numara çakışmasında kaynak cilt silinir. Hedefe kaynak ISBN'sini kopyalayan bir adım yok. Kişisel referanslar taşınabilir; aynı mağazadaki fazla ilan silindiğinde cascade ile geçmişi de silinebilir. Şartnamenin ID/geçmiş koruması bu yolu da kapsamalı. Canlıda kayıp yaşandığı iddia edilmiyor; bu kod dalının etkisidir. |
| ISBN'ye göre ilanı başka baskıya yerleştirme | `import_service.py`, 497–513 ve `_edition_named_in_title`, 1242–1284 | Aynı ISBN'yi paylaşan baskı için başlık kelimeleriyle kardeş cilt seçebilir; eski sahibin aynı ürün ilanını silebilir. ISBN değişmese de ilan ve geçmiş etkisi vardır. |
| Yanlış yerdeki ilanı serbest bırakma | `import_service.py`, `_release_misplaced_listings`, 1342–1362 | Mevcut cilt ISBN'si mağaza sonucuyla aynıysa aynı URL'li diğer cildin ilanını siler. History silinen ilana bağlıdır; yeni ilan eklenmesi eski history'nin taşındığı anlamına gelmez. |
| Admin yabancı baskı uygulaması | `foreign_editions.py`, 112–135 | İlan silme ve ISBN temizleme aynı uygulamada; ilan silme geçmişini de etkileyebilir. ISBN kararından otomatik ilan taşıma/silme yetkisi türetilmemeli. |
| Admin ilan kaldırma | `routes/volume.py`, 296–318 | ISBN yazmaz. Mevcut uç açıkça ilanı ve fiyat geçmişini siler; ürün için exclusion kaydeder. Yeni ISBN kabul işlemi bu ucu sessizce çağırmamalı. |

Geçmiş etkisinin dayanağı: `StoreListing.history` ilişkisi `cascade="all, delete-orphan"`; `PriceHistory.listing_id` yabancı anahtarında `ondelete="CASCADE"` var. Bütün merge yolları aynı değil: `merge_volume_rows` ile `isbn_conflict_fix` duplicate ilan history'sini hedefe yeniden bağlamaya çalışırken, yukarıdaki bazı diğer dallar ilanı doğrudan siliyor.

### Diğer bakım girişleri

- `apply_task2_followup.py` (107–147): doğrudan ISBN alanı yazmıyor; seri/cilt bağlantıları taşıyor ve kaynak satırlar siliyor.
- `fix_task4_sync_duplicates.py` (84–100): ciltleri başka seriye taşıyor veya çakışan kaynak cildi siliyor. ISBN sahipliği/satır yaşamı dolaylı etkilenebilir.
- `apply_task4_cleanup.py` (104–112), `apply_task5_cleanup.py` (170–181): seri silmeleri cascade ile ciltleri ve ISBN sahiplerini de kaldırabilir. Task 5'in `--dry-run` yolu salt okunur; uygulanması ayrıca incelenmeli.
- `cleanup_catalog_orphans.py`: varsayılan dry-run; `--apply` ile silmeden önce ISBN, koleksiyon, wishlist, alarm, ilan ve history verisini sert biçimde engelliyor. Koruma mevcut; ISBN yazıcısı değildir.
- `reconcile_live_catalog.py` ve `catalog_reconciliation.reconcile_snapshot`: manifest/başlık ve cilt üyeliği düzenler; `_merge_manga` kullanır, `_backfill_isbns` çağırmaz. Mevcut sürümde doğrudan ISBN yazıcısı değil; gelecekte kapsam genişletilirse yeniden kontrol edilmeli.
- `app.dev_data --fresh`: geliştirme komutu; katalog satırlarını topluca silebilir. Demo sonuçları gerçek `ImportService` yolunu kullanır. Üretimden kesin ayrılmalıdır.
- `recover.sh`: doğrudan ISBN SQL'i içermez; uygulamayı ve worker'ları başlatır, warmup isteği gönderir. Onaylı ISBN restore mekanizması değildir; mevcut yazıcıları tetikleyebilir.

Bu tarihsel betikler bu incelemede **çalıştırılmadı**. Bazılarında eski sabit ID/sayı önkoşulları var; bunlar gelecekte tekrar çalıştırmanın güvenli veya yeni şartnameye uygun olduğunu kanıtlamaz.

## 5. Tetikleyiciler ve gerçekten salt okunur yollar

| Giriş | Ulaştığı yol | Yeni katmanın dikkat etmesi gereken nokta |
|---|---|---|
| Uygulama başlangıcı ve katalog scheduler | `main.py`, 95–107; `routes.catalog.try_start_sync` → `CatalogSyncService.sync` | Zamanı gelen senkron admin ekranı açılmadan otomatik çalışabilir. |
| `POST /catalog/sync` | Aynı senkron | Router `require_admin` kullanır; bir senkron başlatmak her ISBN adayı için admin kararı değildir. |
| Fiyat scheduler, background runner, warmup ve manuel import | `background_import.py`, 618; `routes/import_.py`, 234–276 → `ImportService.run_import` | Fiyat toplama ISBN adayını doğrudan katalog alanına yazmamalı. |
| `POST /catalog/isbn-fix?apply=true` | `isbn_conflict_fix.run/apply_case` | Önizleme varsayılan, uygulama açık istekle. Frontend `window.confirm` içerir; kalıcı aday/karar kimliği yok. |
| `POST /catalog/foreign-editions/apply` | `ForeignEditionJob.apply/apply_plan` | Plan bellekte; uygulayan adminin karar geçmişi ve birleşik ISBN kapısı yok. |
| `fix_isbn_conflicts.py --apply [--case ...]` | Aynı SQL ISBN düzeltme servisi | CLI çağrısı HTTP admin kontrolünden geçmez; yeni onay servisine bağlanmalı veya yazma yetkisi kaldırılmalı. |

**Salt okunur olanlar:** `catalog_audit.snapshot/audit`, katalog/ISBN çıktı şemaları, scraper'ların `SearchResult`/künye üretimi, `anilist_audit` planları ve `audit_phantom_volumes` denetimi katalog ISBN'si yazmıyor. Alembic dosyalarında ISBN verisini doğrudan düzelten migration bulunmadı; baseline ISBN sütunu ve unique index oluşturuyor. `seed_stores` mağaza satırlarını güncelliyor, ISBN yazmıyor. `restore_check.py` kontrolü salt okunur; `db_backup.py` yedek çıktı üretir, bir ISBN karar/restore uygulayıcısı değildir.

**Önemli çağrı ayrımı:** `search_service.search_with_auto_import` eski arka plan import davranışını hâlâ içeriyor; incelenen uygulama kodunda çağıranı bulunmadı. Güncel `routes/search.py` doğrudan salt okunur `catalog_service` sorguları kullanıyor. “Public GET /search bugün ISBN yazar” sonucu çıkarılmamalı. Yeni denetimde mevcut `ImportService._resolve_target` bir salt okunur ürün eşleştirici gibi yeniden kullanılmamalı; ISBN/ilan yan etkileri var.

## 6. İzole DB'de doğrulanan davranışlar

Deneyler mevcut gerçek `ImportService.run_import`, test kataloğu ve sahte BKM sonuçlarıyla yapıldı. Her satır ayrı, boş `sqlite:///:memory:` veritabanıdır; cilt ID'si mevcut ve ISBN başlangıçta boştu. Ağ isteği veya admin kararı yoktu.

| Senaryo | Durum | Girdi ISBN | İşlem sonrası ISBN | İlan sayısı | Sonuç |
|---|---|---|---|---:|---|
| Yayımlanmış | present=true, released=true | 9786256335424 | 9786256335424 | 1 | Tek mağaza sonucuyla onaysız yazıldı. |
| Yakında | present=true, released=false | 9786256335424 | 9786256335424 | 0 | İlan engellendi ama ISBN yazıldı. |
| Kaynak dışı/pasif | present=false, released=false | 9786256335424 | 9786256335424 | 0 | Pasif ISBN alanı yine değişti. |
| Kontrol basamağı hatalı | present=true, released=true | 9786256335425 | 9786256335425 | 1 | Checksum hatası engellenmedi. |

**Yayın koruması neden geç kalıyor?** `_resolve_volume` ISBN'yi 1181'de değiştiriyor; `run_import` çözümlemenin hemen ardından 254'te commit ediyor. `_upsert_listing` yayın/kaynak korumasına 1368'de, daha sonraki ilan aşamasında geliyor. İlanın atlanması önceki ISBN commit'ini geri almıyor.

**ISBN teknik geçerliliği:** `normalization/isbn.py` uzunluk/karakter temizliği yapıyor; `book_isbn` 13 haneli kod için 978/979 önekini arıyor, kontrol basamağını doğrulamıyor. `9786256335425` kabul ediliyor; ayrıca 13 karakterli `978625633542X` de kabul ediliyor. ISBN-10/13 eşdeğerini tek kitap anahtarına dönüştüren adım bulunmadı. Yeni denetim geçerli ISBN-10'u uygun ISBN-13 karşılığıyla karşılaştırabilmeli; mevcut metadata/merchandise normalizasyonunun tüm kullanıcılarını körlemesine değiştirmemeli.

## 7. Diğer uygulanabilirlik açıkları

1. **Yetki, karar ve kilit farklı şeyler.** `require_admin` giriş yetkisini doğrular; cilt/ISBN için kaydedilmiş karar değildir. `SYNC_GATE_KEY` yarışmayı azaltır; onay vermez. `unique=True` bir değerin kopyasını engeller; doğru kitaba ait olduğunu kanıtlamaz.
2. **Raw SQL, yalnız ORM korumasını atlar.** `isbn_conflict_fix` ve eski bakım betikleri `sqlite3` ile yazıyor. Sadece model setter veya `before_flush` eklemek bütün yolları kapatmaz.
3. **Alt helper güvenlik sınırı değil.** `merge_volume_rows` doğrudan çağrılabilir; kendi içinde `has_personal_rows`, kanıt veya admin kararı denetlemez. Şartname ISBN kabulüyle otomatik merge'ü zaten yasaklıyor.
4. **Erişilememe, olumsuz kanıt olmamalı.** Ana baskı sayfasından ISBN alınamadığında varyant taşıma dalı ilerleyebilir. Yabancı-ISBN planı bazı ISBN'leri önekle seçer ve uygulamada temizler; kaynak hata sonuçlarının ayrı modellenmesi gerekir.
5. **Eski düzeltmede ilan kanıtı, ISBN değişikliğinin iki-kaynak doğrulaması değil.** `add_evidence` hangi ilanların taşınacağını belirler; `apply_case` ISBN'yi varsayılan/CLI vaka bilgisine göre yazar. İlanların hiçbiri taşınabilir olmasa da bu ISBN yazması yapılabilir.
6. **Uygulama sırasında daha kapsamlı karşılaştırma gerekebilir.** `isbn_conflict_fix.run` yazmadan önce DB durumunu ve ilan ID listesini yeniden denetliyor; kanıt URL'sinin değişmediğini aynı kapsamda karşılaştırmıyor. Yeni uygulama kararı mevcut ISBN, hedef cilt/baskı, kanıt tarihi/URL'si ve karar sürümüyle birlikte yeniden doğrulanmalı. Bu tespit statik incelemeye dayanır.
7. **Kalıcı karar yok.** İncelenen modeller arasında ISBN aday/kanıt/karar tabloları yok. `details_checked_at` veya son senkron raporu hangi adminin hangi ISBN'yi hangi kanıtla onayladığını göstermez.
8. **Aday kaynak, adaptör demek değil.** Registry'de BKM ve D&R gibi mevcut adaptörler var; Kitapyurdu yalnız erişim testi adayı olarak geçiyor, Kitapyurdu/Pandora doğrulama adaptörleri yok. Erişim testi iki bağımsız kitap kanıtı sağlamaz.

## 8. Uygulama için kesin geçiş listesi

Bu maddeler uygulama önerisidir; bu raporda kodlanmadı. [Şartnamedeki A/B/C sırası](isbn-dogrulama-teknik-sartname-2026-10-14.md) korunmalıdır.

### A — Salt okunur denetim

- Saf ISBN checksum/normalizasyon ve fiziksel kitap kimliği eşleştirmesi oluştur; yazma yan etkili importer resolver'ını kullanma.
- Geçerli bağımsız dış kanıtları topla; Mangakol karşılaştırma bilgisi olsun, iki dış kaynaktan biri sayılmasın.
- Yakında ve kaynak dışı ciltleri aday yazmadan ele al; tarih gelince yayın kanıtını yeniden değerlendir. Tarih tek başına released=true yapmasın.
- Snapshot'taki ISBN, kaynak/baskı kimliği ve kanıtları ayrı denetim kayıtlarına yaz; mevcut katalog/ilan/kullanıcı/history alanlarına dokunma. Snapshot sonrasında değişmiş katalog ISBN'sine eski öneriyi uygulama.
- Önce staging/test; ilk tam taramada yayımlanmış bütün katalog kapsansın. Mevcut backfill bütçesi/skip kuralları denetim kapsamını daraltmasın.

### B — Admin inceleme merkezi

- Mevcut ISBN'yi koru, öneriyi kabul et, manuel gir ve ertele kararlarını kalıcı kaydet; kim, ne zaman, eski/yeni değer, neden ve kanıtlar görünür olsun.
- İki kaynak aynı ve üçüncü geçerli kaynak farklıysa CONFLICT; üçüncü erişilemiyorsa SOURCE_ERROR kanıtı olarak ayrı tutulmalı. Kaynak hatası ISBN yokluğu sayılmasın.
- Boş ISBN için mutabakat bulunsa bile admin onayına kadar `Volume.isbn` değişmesin. Dolu ve aynı ISBN çelişkisiz doğrulanırsa yalnız VERIFIED durumu oluşsun.
- Ortak ISBN'li farklı baskılar ayrı kalsın; mevcut unique kısıt otomatik kaldırılmasın. Aynı değeri başka satırdan çalmak veya merge yapmak çözüm sayılmasın.

### C — Bütün yazıcılara ortak onay kapısı

- Mangakol, importer, eski admin düzeltmeleri ve CLI aday üretmeli; kalıcı ve geçerli kararı uygulayan tek mutation servisi dışındaki katalog ISBN yazmaları kaldırılmalı/engellenmeli.
- Temizleme (`isbn=None`) ve taşıma iki ayrı satırı etkileyen değişikliktir; onay denetimi yalnız “yeni ISBN ekle” dalında olmamalı.
- ISBN/yayın/baskı kontrolleri ilk ISBN veya ilan yan etkisinden **önce** çalışmalı; `_upsert_listing` son koruma olarak kalsın.
- ORM doğrudan ataması ve toplu SQLAlchemy güncellemesi için savunma kontrolü/testi ekle. Ham SQLite yollarını ortak uygulama servisine taşı veya canlı kullanımını açıkça engelle; eski bakım betiklerini sessiz açık kapı olarak bırakma.
- Karar uygulaması sırasında mevcut değer ve unique çakışması transaction içinde yeniden denetlensin. Onay sonrası senkron aday üretebilir, admin kararını ezemez.
- ISBN kabulü `Volume.id`, koleksiyon, wishlist, alarm veya ilan/history ilişkilerini kendiliğinden değiştirmesin. İlan düzeltmesi gerekiyorsa ayrı, ürün kanıtlı ve geçmiş koruyan karar olsun.
- Kontroller tamamlanmadan “bütün ISBN'ler artık admin onayında” diye ürün/sistem davranışı ilan edilmesin.

### Gerekli yeni regresyonlar

Şartnamedeki Blue Lock, Solo Leveling roman/webtoon, Afro Samuray ve ORV varyant vakalarına ek olarak: Yakında/pasif cilde import sırasında ISBN commit edilmemesi; hatalı ISBN-13 checksum ve ISBN-13 içinde X'in reddi; ISBN-10/13 eşdeğerliği; ana sayfa erişim hatasında varyant ISBN taşımasının engellenmesi; `isbn=None` temizlemesinin karar istemesi; raw SQL/CLI'nin onayı atlayamaması; aynı mağaza ilan çakışmasında history korunması; source cilt ID'sinin ISBN kabulüyle silinmemesi; doğrudan helper çağrısının korumayı geçememesi; admin kararını eski snapshot önerisinin ezememesi test edilmelidir.

## 9. Yapılan doğrulama

Mevcut davranışı ve ilgili korumaları kontrol eden **131 test geçti**. Testler yeni onay sisteminin varlığını kanıtlamaz; bazıları mevcut otomatik yazma/taşıma davranışını özellikle bekliyor. Yeni sözleşme uygulanırken bu beklentiler aday/karar sürecine göre yeniden düzenlenmeli.

Çalıştırılan kapsam:

```text
python -m pytest -q
  tests/test_catalog_isbn.py tests/test_catalog_variants.py
  tests/test_catalog_cleanup.py tests/test_catalog_release_visibility.py
  tests/test_import_service.py tests/test_fix_isbn_conflicts.py
  tests/test_foreign_editions.py tests/test_phantom_review.py
  tests/test_catalog_sync.py tests/test_catalog_reconciliation.py
  tests/test_auto_import.py
```

Komut yukarıdaki dosyalarla tek satır olarak çalıştırıldı. Dört izole davranış deneyi ve normalizer sınır kontrolü ayrıca çalıştırıldı. Uygulama/frontend kodu değiştirilmediğinden frontend build'i tekrarlanmadı; yeni denetim motoru veya canlı ISBN taraması başlatılmadı.

## 10. Kaynak bağlantıları

Sabit sürümdeki başlıca kanıtlar:

- [Mangakol ISBN yazma/taşıma dalları](https://github.com/kangaetemo/yomiba/blob/33bfdc407bd26793a1ba1316aa395fec123d3dcb/backend/app/services/catalog_sync.py#L410)
- [Importer boş ISBN yazması](https://github.com/kangaetemo/yomiba/blob/33bfdc407bd26793a1ba1316aa395fec123d3dcb/backend/app/services/import_service.py#L1133)
- [Importer erken commit](https://github.com/kangaetemo/yomiba/blob/33bfdc407bd26793a1ba1316aa395fec123d3dcb/backend/app/services/import_service.py#L244)
- [Numarasız cilt merge helper'ı](https://github.com/kangaetemo/yomiba/blob/33bfdc407bd26793a1ba1316aa395fec123d3dcb/backend/app/services/phantom_review.py#L93)
- [Admin/CLI ham SQL ISBN düzeltmesi](https://github.com/kangaetemo/yomiba/blob/33bfdc407bd26793a1ba1316aa395fec123d3dcb/backend/app/services/isbn_conflict_fix.py#L127)
- [Yabancı ISBN temizleme](https://github.com/kangaetemo/yomiba/blob/33bfdc407bd26793a1ba1316aa395fec123d3dcb/backend/app/services/foreign_editions.py#L101)
- [Seri birleştirmesindeki dolaylı etkiler](https://github.com/kangaetemo/yomiba/blob/33bfdc407bd26793a1ba1316aa395fec123d3dcb/backend/app/services/catalog_sync.py#L814)
- [Mevcut normalizasyon](https://github.com/kangaetemo/yomiba/blob/33bfdc407bd26793a1ba1316aa395fec123d3dcb/backend/app/normalization/isbn.py#L13)

**Tamamlanan iş:** Mevcut ISBN yazma yollarının ve ilgili dolaylı veri etkilerinin raporlanması. **Açık işler:** A/B/C uygulaması, kaynak adaptörleri, kalıcı onay kayıtları ve bütün yazma yollarının gerçekten kapatıldığını kanıtlayan yeni testler.
