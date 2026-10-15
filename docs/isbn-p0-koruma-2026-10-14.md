# ISBN P0 koruma paketi — 14 Ekim 2026

## 15 Ekim: kullanıcı onayıyla canlıya alındı

PR #4, `a4272598061abe583205f62aec3602b36b8c567a` olarak main'e birleştirildi.
Railway `20fba45b-78b9-4c21-b3f7-44f952d74f45` SUCCESS, tek replica Online;
uyarı/kritik hata veya bekleyen altyapı değişikliği yok. Startup logu yeni
pre-migration yedeğini, gerçek 0014→0015 geçişini, DB readiness başarısını
ve normal scheduler başlangıcını doğruladı. Migration içindeki yedek,
restore, korunan tüm satırlarda önce/sonra eşitlik ve guard tanımı kontrolleri
başarısız olsaydı startup tamamlanmayacaktı; gerçek startup/healthcheck geçti.

Canlı `/ready`, `/home`, `/search?q=fairy` 200; yöneticiye özel koruma bilgisi
anonim erişimde 401. Readiness `isbn_writes_paused: true`; frontend 200.
Yayın öncesi güncel online yedek restore doğrulamasından geçti; şifreli ikinci
kopyası DPAPI decrypt/hash round-trip ile doğrulandı, ara plaintext silindi.

Ek bağımsız SSH audit'i (özel manifestin ayrıca okunması ve yayın öncesi yedekle
eski kimlik/geçmiş satırlarının karşılaştırılması) tekrarlanan bağlantı ve DNS
zaman aşımından dolayı **henüz tamamlanmadı**. Bu nedenle P0.4'ün bu son
operasyonel kontrolü açık tutuluyor. Canlı koruma aktif; mevcut ISBN farkları
ve bağımsız A/B/C admin sistemi bu çalışmada uygulanmadı.


## 15 Ekim: uygulama akışı, Linux regresyonu ve ikinci yedek doğrulandı

Sonraki bağlantı başarılı oldu. Aynı paket üzerinde Linux'ta üç sentetik
regresyon kontrolü geçti: aktivasyon yedeği/restore/owner-only izinleri,
restore hatasında durma ve bağlantı nesneleri hayatta tutulduğunda bütün
SQLite bağlantılarının kapatılması. Bunların ikisi Windows'ta dışlanan
testlerdir; üçüncüsü yerel test kümesinde de çalışmıştı. 936 yerel + iki ayrı
Linux vakasıyla 938 farklı kod testi başarılı; 18 tarihsel snapshot testi
bu sonuca dahil değildir.

Gerçek yedekten ikinci geçici DB oluşturuldu. Ayrı Python alt sürecinde tam
uygulama lifespan/startup çalıştı; katalog/fiyat/kapak scheduler'ları kapalı
tutuldu. `/ready`, `/home`, `/search?q=fairy` 200, özel `/catalog/isbn-safety`
anonim kullanıcı için 401 döndü; readiness `isbn_writes_paused: true` verdi.
Startup ve HTTP okumaları sonrasında 11 korunan tablonun özetleri aynıydı.
Bu kontrol bağımsız Railway environment oluşturmaz; mevcut konteynerde
izole DB ve alt süreç kullanan bir uygulama provasıdır.

Onaylanan 8.196.096 baytlık yedek Railway volume'u dışına alındı. SHA-256
eşitliği doğrulandı, yerel Windows kullanıcısına özel erişimli dizinde
Windows DPAPI CurrentUser ile şifrelendi ve decrypt/hash round-trip kontrolü
geçti. Doğrulanan şifreli kopya tutuldu; ara plaintext kopya kaldırıldı.
Şifreli kopya bu Windows hesabına bağlıdır; parola, token veya kullanıcı
satırları kaynak paketine/GitHub'a eklenmedi. Özel operasyon kaydı yerel
`work/private` dizininde tutuluyor.

Canlı DB hâlâ değiştirilmedi; henüz deployment yapılmadı. Üretim geçişi için
güncel ön yedek/boş alan kontrolü, eski yazıcı süreçlerin kontrollü durması,
tek worker ile 0015 aktivasyonu ve canlı readiness/admin manifest kontrolü
gerekir. Ayrı staging environment oluşturulmadığı açıkça korunuyor.


## 15 Ekim: gerçek yedek üzerinde 0015 provası başarılı

Yerel operatörün `capture_output` kullanımı, komut tamamlanana kadar bütün
çıktıyı gizliyordu. Başlatıcı artık hemen durum gösteriyor; SSH port erişimini
12 saniyeyle sınırlıyor ve Railway/uzak prova çıktısını anında ekrana yazıyor.
Bekleyen süreçte 10 saniyede bir ilerleme bilgisi gösteriliyor; toplam süre
sınırında yalnız kendi alt süreç ağacı kapatılıyor.

Düzeltilmiş operatör gerçek Railway Linux konteynerine bağlanıp belirtilen
online yedeği `/tmp` altında özel bir kopyaya geri yükledi ve gerçek Alembic
0014 → 0015 geçişini tamamladı. **24 DB kilidi doğrulandı; 11 korunan tablonun
satır sayıları ve tam satır özetleri aynı kaldı.** Kaynak yedeğin bayt hash'i
aynı; geçici DB, manifest ve yedeklerin owner-only dosya izinleri doğrulandı.
Readiness'in gerçek şema/trigger denetimi geçti. Kaynak yedek 8.196.096 bayt,
quick_check sonucu `ok`, şema 0014 olarak ayrıca okundu.

Bu, canlı konteynerde izole dosya ve migration provasıdır; ayrı Railway
environment veya uygulamanın tüm startup/HTTP akışı testi değildir.
Canlı DB, deployment ve ISBN'ler değiştirilmedi. Sonraki sentetik Linux
regresyonu / uygulama smoke testi ve ikinci kopya indirme denemeleri tekrar
bağlantı kesilmesi/zaman aşımına takıldı; başarılı sayılmadı. Volume dışı
ikinci yedek bu sohbet tarafından henüz oluşturulmadı.

Bekleyenler: bağımsız staging uygulama doğrulaması, ikinci özel yedek,
kontrollü üretim geçişi ve canlı sonrası kontrol. 936 yerel kod testi sonucu
geçerli; Windows'ta dışlanan iki POSIX regresyon vakası ayrıca çalıştırılmadı.
Gerçek provanın başarılı izin kontrolü bu iki testin çalıştırıldığı iddiası
değildir. A/B/C ve ISBN düzeltmeleri hâlâ sonraki aşamadadır.


## 15 Ekim 2026: yerel sohbete devir ve prova hazırlığı

Son yerel doğrulama: **936 test geçti, 2 Linux dosya izin vakası Windows'ta
dışarıda bırakıldı**. Tarihsel gerçek DB kopyası isteyen 18 kontrol ayrıca
çalıştırılmadı. Derleme, paket hash/içerik kontrolü ve diff kontrolü geçti.
Bu sayılar gerçek Railway provası veya canlı aktivasyon sonucu değildir.

Kaynak temel `main / 69a3e80a58973eb6308de21a53bee48e2b18ff31`.
Önceki uzak sohbette push edilmemiş P0 değişiklikleri, kayıtlı dosya diff'leri
ve incelenen düzenleme adımları üzerinden ayrı yerel checkout'a devralındı.
Bu bir uzak Git commit'inin birebir hash doğrulaması değildir; devralınan
kaynak yeniden derlendi ve test edildi.

Kullanıcının paylaştığı operatör çıktısı online yedek ve restore doğrulamasını
başarılı bildiriyor: kaynak şema 0014, 11 korunan tablo, sıfır FK hatası,
komut kaynak kataloğu değiştirmemiş. Tam dosya yolu ve kimlik özetleri özel
operasyon kaydında tutuluyor. Bu sohbet aynı yedeğe bağımsız dosya erişimini
henüz doğrulayamadı.

Railway yönetim bağlantısı canlı servisin SUCCESS olduğunu, ayrı staging
bulunmadığını ve bekleyen altyapı değişikliği olmadığını doğruladı. Yerel CLI
oturumu açık. SSH port 22 bağlantısı iki denemede zaman aşımına uğradı.
Canlı migration, deploy, restore veya ISBN düzeltmesi çalıştırılmadı.

Ek düzeltme: sqlite3 bağlantı context manager'ı bağlantıyı kapatmıyordu;
backup/restore incelemesi artık bağlantıları açıkça kapatıyor. Böylece
Windows'ta geçici restore dosyaları anında temizlenebiliyor. Bunu bağlantı
nesnelerini bilerek hayatta tutan regresyon testi de doğruluyor.
Prova Linux'ta geçici veri/manifest/yedek dosyalarının owner-only izinlerini
ayrıca kontrol ediyor; bu kontrol başarısızsa prova duruyor.

Tek dosyalık `p0_rehearsal_operator.py`, paketlenmiş kaynağı standart SSH
girdisiyle `/tmp` altında yeni, özel bir dizine aktarır. Onaylanan yedeği
salt okunur açar; bir kopyasında gerçek 0015 Alembic geçişini, tüm korunan
satır özetlerini ve readiness kilit tanımlarını sınar. Kaynak yedeğin
bayt hash'ini önce/sonra karşılaştırır. API, scraper veya scheduler başlatmaz;
canlı DB'ye restore veya migration yapmaz. Kimlik bilgisi pakete gömülmez.

P0.1/P0.4 gerçek ortam provası, volume dışı ikinci özel yedek ve kontrollü
üretim aktivasyonu tamamlanana kadar açık. A/B/C ve kalan ISBN farklarının
incelemesi henüz uygulanmadı. Aşağıdaki 14 Ekim kaydı tarihsel paket notudur.


**Durum:** Kod ve izole regresyon tamamlandı; GitHub'a push, gerçek Railway
staging restore testi ve üretim aktivasyonu yapılmadı. Canlı ISBN, cilt,
ilan, kullanıcı kaydı veya geçmişi bu çalışma kapsamında değiştirilmedi.
A/B/C bağımsız doğrulama ve admin onay sistemi henüz uygulanmadı.

Kaynak sürüm: `main` / `69a3e80a58973eb6308de21a53bee48e2b18ff31`.
Kod, önceki çalışma alanındaki değişikliklere dokunmayan ayrı bir checkout'ta
hazırlandı. [Onaylı şartname](isbn-dogrulama-teknik-sartname-2026-10-14.md)
ve [yazma yolları denetimi](isbn-yazma-yollari-denetimi-2026-10-14.md)
P0 kapsamının temelidir.

## Hazırlanan davranış

| Yol | P0 davranışı |
| --- | --- |
| Mangakol katalog/startup/scheduler | Yeni seri ve NULL ISBN'li cilt keşfi; güvenli kapak/künye/yayın görünürlüğü güncellemeleri devam eder. ISBN önerileri raporlanır; doldurma, temizleme, özel baskılar arası taşıma yok. |
| Mağaza importer | Mevcut katalogda fiyat/stok güncellemeleri devam eder. Tek mağaza ISBN'yi dolduramaz. Başka ciltteki aynı ürün ilanı otomatik silinmez veya taşınmaz. |
| Phantom, ISBN fix, yabancı baskı temizliği | Önizleme okunabilir; eski apply yardımcıları ve admin/CLI yazma girişleri açıkça engellenir. |
| Publisher/series merge | Alias/seri/cilt kimlikleri otomatik birleştirilmez. Eski merge yardımcıları engellenir. |
| İlan silme / kaldırılmış mağaza ürünü | Admin silme geçici olarak 409 döner. Mağazanın kaldırdığı ürünün satırı tutulur, stok dışına alınır; değişen stok için yeni gözlem eklenir. Geçmiş silinmez. |
| Tarihsel bakım betikleri | Task2 merge/followup, task3/4/5 cleanup ve task4 duplicate fix, DB açmadan engellenir. Orphan cleanup `--apply` ve demo `--fresh` de engellenir. |
| ORM / bulk SQL / sqlite3 | Migration 0015 ile 24 SQLite trigger kurulur. ISBN/Volume kimliği, bağımlı seri/yayınevi/mağaza kimlikleri, ilan/geçmiş kimlikleri ve kişisel satırların yeniden bağlanması korunur. |

ISBN eşsizliği kaldırılmadı. P0 hiçbir ISBN onayı vermiyor; hiçbir bypass
bayrağı yok. Kullanıcının kendi koleksiyon durumunu değiştirmesi, wishlist
ve alarmını kaldırması gibi normal kişisel işlemler devam eder.

Fiyat geçmişinin eski fiyat, stok, tarih, satır ve ilan kimliği değiştirilemez.
Bir istisna, eski NULL `product_url` alanını **ilanın hâlen bağlı olduğu
URL ile** doldurmaktır; bu, meşru aynı-cilt ürün geçişinden önce eski gözleme
ürün kimliğini kazandırır. Yeni ürünün fiyatı ayrı gözlem olarak eklenir.
Bu işlem başka cilde ilan/geçmiş taşıma yetkisi vermez.

`isbns_deferred` tüm ertelenen kaynak adaylarını, `isbn_conflicts` dolu ISBN
veya başka ISBN sahibiyle çatışanları sayar. Bu kaynak adayları bağımsız
kanıt veya VERIFIED kararı değildir; mevcut bütçeli künye okuması Aşama A'nın
tüm yayımlanmış kataloğu kapsayan taramasının yerine geçmez.

## Yedek ve değişmezlik

- `0014_catalog_membership` şemasındaki mevcut dosyada, 0015 aktivasyonu
  SQLite yazma kilidi altında korunacak tabloların sayım ve SHA-256 özetini
  çıkarır. Online backup API ile aynı DB'nin özel yedeğini oluşturur.
- Yedek yeni, UUID içeren ada ve `0600` iznine sahiptir; var olan dosyanın
  üzerine yazılmaz. `AUTO_MIGRATION_BACKUP=0`, P0 aktivasyon yedeğini kapatamaz.
- Yedek yalnız yeni, izole bir geçici dizine geri yüklenir; bütün korunan
  satır özetleri ve yabancı anahtar kontrolü karşılaştırılır. Bu kopyada
  CRUD/merge deneyi yapılmaz. Sonrasında geçici kopya kaldırılır.
- Trigger kurulumu öncesi/sonrası tam satır özetleri aynı olmak zorundadır.
  Seri, manifest, Volume, mağaza, ilan, PriceHistory, koleksiyon, wishlist,
  alarm, kullanıcı ve oturum tabloları özetlenir. Rapor ham kullanıcı veya
  kimlik bilgisi içermez.
- Önceki şemalardan yükseltmelerin genel açılış yedeği de özel dosya ve
  izole restore kontrolü kullanır. Eski migration'ların kendi veri dönüşümleri
  0015'in salt koruma kurulumundan ayrı değerlendirilir.
- Yedek, restore veya özet kontrolü başarısızsa başlangıç başarısız olur;
  uygulama/scheduler hazır ilan edilmez. Mevcut 0014 DB'de koruma kurulumu
  katalog satırlarını değiştirmez.

Aktivasyon manifesti DB'nin yanında `*.isbn-safety.json` adıyla, atomik ve
özel izinlerle yazılır. Migration başarısının tek kanıtı manifest değildir:
readiness gerçek migration head ve trigger SQL tanımlarını doğrular.

## İzole doğrulama

Komut:

```sh
cd backend
python -m pytest -q --ignore=tests/test_task2_identity.py
```

**Sonuç: 933 geçti.** Bunların **51'i yeni P0 testidir**.
Python derleme kontrolü ve `git diff --check` başarılı. Frontend değişmedi.
Mevcut bağımlılıklarda deprecation uyarıları var; başarısız kod testi yok.

Yeni testler gerçek migration zinciriyle geçici 0014 DB kurup yalnız sentetik
veriyle 0015'e geçer: ISBN/Volume ilişkileri, ilan, geçmiş ve kişisel kayıtlar
aktivasyon öncesi/sonrası tam olarak eşittir; özel yedek/restore doğrulanır.
Ham SQL'de FK ve recursive trigger ayarları kapatılsa bile doldurma, `None`
temizleme, kimlik değişimi, delete ve PK/unique-slot `INSERT OR REPLACE`
engellenir. ORM/bulk update, scheduler, helper, eski bakım CLI'si, admin 409,
Yakında/pasif mağaza aktarımı, meşru fiyat/stock akışı, yedek hatasında durma
ve trigger tahrifatında readiness 503 ayrıca sınanır.

`test_task2_identity.py` içindeki **18 tarihsel veri kontrolü çalıştırılmış
sayılmaz**: eski gerçek `backend/yomiba.db` snapshot'ını gerektirir. Dosya bu
checkout'a alınmadı; testlerin beklentileri değiştirilmedi. Çalışma notlarında
zaten belgelenmiş olan kod-test komutu kullanıldı. Üretim verisiyle CRUD
testi veya otomatik temizleme yapılmadı.

## Gerçek staging ve kontrollü aktivasyon

Bu bölüm henüz uygulanmadı. Bu oturumda Railway DB/SSH veya staging yönetim
erişimi yok; izole test sonucu gerçek Railway restore sonucu olarak sunulmaz.

1. Ayrı kaynak branch/commit'i incelensin. Üretim `main` push'unun Railway
   dağıtımını tetiklediği unutulmasın. Önce staging; kaynak pakete `.db`, WAL,
   yedek veya özel manifest eklenmesin.
2. Yetkili operatör canlı DB'nin online yedeğini `db_backup.py` ile yeni ve
   özel bir hedefe alsın; revision, satır özetleri ve restore sonucu özel
   operasyon kaydında saklansın. Yedek/rapor kamuya veya Git'e yüklenmesin.
3. Yedek ayrı staging volume'una, `/data/yomiba-staging.db` hedefine restore
   edilsin. [Railway staging runbook](../backend/RAILWAY_STAGING.md) izlenerek
   `APP_ENV=staging`, güvenli cookie/HTTPS ayarları doğrulansın. İlk kontrolde
   katalog, fiyat ve kapak scheduler'ları kapalı olsun. Üretim dosyası staging
   hedefi olarak kullanılmasın.
4. Yeni kodun başlangıcı, 0015 geçişi, özel yedek/restore ve manifestin
   `before == after == restore.tables` sonuçları doğrulansın. `/ready` gerçek
   kilitleri kontrol edip 200 ve `isbn_writes_paused: true` vermeli.
   `/catalog/isbn-safety` admin oturumuyla okunmalı; sıradan/anonim kullanıcı
   özel özete erişememeli.
5. Katalog görünümü ve mevcut doğru ilanlarda fiyat/stok akışı staging'de
   kontrol edilsin. ISBN, Volume ID, kişisel bağlantılar ve eski geçmişin
   değişmediği ayrıca karşılaştırılsın. Eski apply girişleri 409 vermeli.
6. Staging başarılıysa üretim geçişi ayrı uygulanır: eski worker/scheduler
   süreçleri durdurulsun, güncel online yedek ve özel operasyon kaydı tutulsun;
   tek replica/worker ile guarded kod başlatılsın. Eski ve yeni sürüm aynı
   SQLite dosyasında eşzamanlı çalıştırılmasın. Kilitli yazma lease'i aktivasyon
   esnasında eşzamanlı DML'i durdurur; eski süreçlerin guard hatasıyla çalışmaya
   devam etmesi operasyon planının yerine geçmez.
7. Gerçek startup ve admin manifest sonuçları doğrulandıktan sonra P0 canlı
   durumunu işaretle; ardından A/B/C çalışmasına geç. Kalan 16 fark bu sırada
   otomatik düzeltilmez.

Örnek operatör kontrolü (hedef mevcut olmamalı):

```sh
cd backend
python db_backup.py --source /data/yomiba.db --output /data/yomiba-p0-manual-20261014-unique.bak
python restore_check.py --db /data/yomiba-p0-manual-20261014-unique.bak --rehearse
```

## Saklama ve geri dönüş

P0 yedeklerinde otomatik silme yok. Dağıtım öncesi ve aktivasyon yedeği, geçiş
doğrulanıp saklama kararı ayrıca verilene kadar korunur. Volume dışı ikinci
şifreli özel kopya, yetkili operasyon sürecinde tutulmalı; yalnız aynı disk
üzerindeki yedek disk/volume kaybına dayanıklılık sağlamaz. Disk alanı, yedek
başarısı ve dosya izinleri operatör tarafından kontrol edilmeli.

Bir uygulama hatasında tercih, **0015 şemasını ve kilitleri koruyan ileri
düzeltmedir**. `alembic downgrade` korumayı kaldıramaz. Eski 0014 bekleyen
uygulama ikilisini doğrudan 0015 DB'ye geri döndürmek readiness'i başarısız
yapar; rollback guard tanımlarını bilen kodla hazırlanmalı.

DB restore gerçekten gerekirse bütün yazıcılar durdurulmalı; mevcut DB/WAL
dosyaları korunmalı. Seçilen yedek önce yeni, karantina hedefe geri yüklenip
özet/FK kontrolünden geçmeli; guarded kod bu hedefte 0015'i kurmadan servis
açılmamalı. Canlı hedefin değiştirilmesi ayrıca açık bir operasyon kararıdır.
Yedek tarihinden sonraki hesap/fiyat/katalog hareketleri kaybolabilir; bunların
koruma/uzlaştırma planı olmadan eski yedeği otomatik olarak canlıya koyma.
Aktif SQLite dosyasını veya WAL'ı dosya kopyalayarak değiştirme.

Kilitler normal DML, ORM, bulk SQL, bakım CLI ve mevcut eski yazıcıları
kapsar. DB dosyasını değiştirme veya `DROP TRIGGER` gibi yetkili DDL, SQLite'ta
ayrı bir güven sınırıdır; dosya erişim yetkisini ortadan kaldırmaz. Tanım
tahrifatı bir sonraki readiness kontrolünde 503 verir. Bu paket PostgreSQL
koruması iddia etmez; migration SQLite dışındaki backend'de durur.

## Tamamlanmamış işler

P0.1'in gerçek canlı yedek/staging restore/ikinci kopya kaydı ve P0.4'ün gerçek
üretim doğrulaması bekliyor. P0.2/3 yazma korumaları kodda ve izole testte
kanıtlandı, üretimde henüz aktif değil. A/B/C kanıt tabloları, checksum/
ISBN-10 eşdeğerliği, bağımsız kaynak erişimi, tüm katalog denetimi, admin
karar geçmişi ve tek yetkili uygulama servisi sonraki aşamadır.
