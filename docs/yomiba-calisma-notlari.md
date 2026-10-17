# Yomiba çalışma notları

Son güncelleme: 17 Ekim 2026 (fiyat alarmları, ana sayfa, koleksiyon, fiyat geçmişi, popüler seriler).

Bu dosya ve [yapılacaklar.md](../yapılacaklar.md) GitHub'da tutulur; birden fazla cihazdan çalışıldığı için yerel kopya yerine her zaman main'deki sürüm esastır.

## Sistem nasıl çalışıyor

- **Katalog kaynağı Mangakol.** Katalog senkronu seri, cilt, kapak, sayfa sayısı, yerel çıkış tarihi, yazar/çizer ve JP/TR yayın durumunu okur. Mangakol'un ISBN'i `catalog_isbn` olarak saklanır; cildin ISBN'ine ISBN çözücü karar verir (`services/isbn_resolver.py`). Arama sadece Mangakol kataloğundaki serileri gösterir.
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
  - Windows'ta `tzdata` paketi gerekir (Europe/Istanbul saat dilimi); yoksa ~47 test `ModuleNotFoundError: tzdata` ile düşer. Venv'de pip yok: `uv pip install --python .venv/Scripts/python.exe -r requirements.txt`.
- Frontend kontrolleri: `cd frontend && npx tsc --noEmit -p . && npx eslint .`
- `test_rate_limit_keeps_per_store_interval` Windows'ta ara sıra zamanlama yüzünden düşüyor; eskiden beri var.
- Fiyatsız seriler raporu (`fiyatsızlar.txt`): Mağaza bazındaki sebep sayıları, sorgunun döndürdüğü tüm ürünler üzerinden toplanıyor. Örneğin BKM'de büyük bir `publisher_conflict` sayısı genelde "bu mağaza o seriyi satmıyor" demektir.

## Son günlerde yapılanlar

### 17 Ekim gecesi: canlı ISBN raporunun ikinci turu

- Senkron panelindeki 16 çelişki, senkronun bittiği andaki görüntü. Fiyat taramasından sonra 9'u kendiliğinden çözüldü: Blue Lock 29, Happiness 6, Huzurlu Kamp 3, Skip and Loafer 4, Vampir Şövalye 6, ORV 3/4 ve Yıldızların Sesi/Canım Kızım.
- Mağazalarla doğrulanan yanlış ISBN'ler (admin panelinden girilecek):
  - Solo Leveling 2 (#859) → 9786256449671. Bizdeki …459, Novel Cilt 2'nin ISBN'i.
  - Solo Leveling 7 (#2471) → 9786258630510.
  - Komünist Manifesto (#2245) → 9786055541583. Bizdeki …801, düz metin cep kitabı.
  - Kapital 2 (#2311) → 9789944122962. Bizdeki …781, asıl Kapital kitabı.
  - Kapital 1 (#2310) → …917 aynı kalır; admin onayı çelişkiyi kapatır.
  - Alacakaranlık (#2275) → …633. Önce kapakla doğrulanacak.
- **Ders:** Yanlış ISBN, aynı adlı manga olmayan kitapların (roman, düz metin) fiyatını mangaya bağlıyor. Doğru ISBN girilince bu ürünler `isbn_conflict` ile reddediliyor ve eski ilanlar 48 saatte bayatlayıp düşüyor.
- **Çözücü değişikliği:** Mangakol, bizdeki ISBN ve mağazalardan biri aynı ISBN'i gösteriyorsa, başka bir baskının ISBN'i artık "mağazalar anlaşamıyor" çelişkisi açmıyor (Soichi, Kara Paradoks, Çöküşten Önce…). 913 test geçti.

### 17 Ekim gecesi: alarmlar, ana sayfa, koleksiyon, fiyat geçmişi, popüler seriler

- **Fiyat alarmları** (migration `0019_price_alert_mail`): Her fiyat güncellemesinden sonra alarmlar kontrol ediliyor (`services/price_alert_checker.py`). Eşik geçilince bir kez e-posta `email_outbox` kuyruğuna giriyor. Stoklu en düşük fiyat eşiğin üstüne çıkınca alarm yeniden kuruluyor. Teklif yoksa hiçbir şey değişmiyor. `services/mailer.py` kuyruğu SMTP ile gönderiyor, hata olursa artan aralıklarla en fazla 8 kez deniyor.
  - **Sınırlama:** Railway Hobby SMTP'yi engelliyor. Alan adı alınınca Resend API'ye geçilecek ([yapılacaklar](../yapılacaklar.md)). O zamana kadar mailler kuyrukta bekliyor.
- **Ana sayfa:**
  - Slogan “Aynı cilt, en uygun fiyat.” oldu.
  - İstatistik alanı ve alt bilgideki mağaza listesi kaldırıldı.
  - Yeni çıkanlardaki mobil taşma düzeltildi.
  - Takvim küçültüldü; geniş ekranda yanda sabit duruyor.
- **Popüler seriler** (migration `0021_series_popularity`, `services/popularity.py`):
  - Her katalog senkronundan sonra idefix manga “Çok satanlar” (3 sayfa) ve BKM çok satan çizgi roman (4 sayfa) okunuyor. Her ürün serisine `1 - sıra/liste uzunluğu` puan veriyor.
  - Sıralama: çok satan puanı, son 60 günde cilt çıktıysa +0,5 ve okur ilgisi (en fazla +1). Eşitlikte cilt başına stoklu teklif sayısı kullanılıyor.
  - Liste okunamazsa eski puanlar korunuyor.
  - Gerçek listelerle ölçüm (17 Ekim): idefix 72 üründen 65'i (%90), BKM 48 üründen 42'si (%87) eşleşti. Eşleşmeyenler setler, hediyeli paketler, katalog dışı kitaplar ve belirsiz “Tokyo 9. Cilt”. İlk sıralar: Blue Lock, Gençlik Yolculuğu, Titana Saldırı, Tokyo Gul, Kahramanlık Akademim.
- **Koleksiyon** (migration `0020_collection_two_states`):
  - Durumlar artık yalnız “Bende var” / “Bende yok”. Eski “İstediğim” kayıtları istek listesine taşındı.
  - Cilt kartlarında yer imi istek listesini, tik “Bende var”ı açıp kapatıyor. “Eksiklerimi istek listeme ekle” düğmesi istek listesine ekliyor.
  - Seri sayfasında “İstek listemde” filtresi var; eski `?status=wanted` bağlantıları da buna yönleniyor.
- **Fiyat geçmişi:**
  - Grafik tek çizgi: stokta olan mağazalar arasındaki en düşük fiyat, basamak biçiminde (`lowest`, `catalog_service.lowest_price_steps`).
  - Üstte üç değer var: şu an, aralığın en düşüğü ve tipik fiyat (zamana göre ağırlıklı ortanca).
  - 30/90 gün/Tümü aralıkları var. Üzerine gelince ya da dokununca tarih, fiyat ve mağaza görünüyor.
- **Doğrulama:** 912 backend testinden 911'i geçti; yalnız bilinen zamanlama testi düştü, o da tek başına çalıştırınca geçiyor. `tsc`, `eslint` ve `npm run build` temiz. Popülerlik yenilemesi senkron kilidinin dışında çalışıyor; testlerde ağa çıkmıyor (`conftest.no_popularity_network`).

### 17 Ekim akşamı: "yanlış fiyat, eksik fiyattan kötü" kuralı kaldırıldı

- Kullanıcı kararı: fiyatlar gösterilsin, hata görülürse üzerine gidilsin.
- Başlık ve ISBN farklı ciltleri gösterdiğinde ürün artık reddedilmiyor; **mağazanın başlığına göre** bağlanıyor (kural `title_over_isbn`) ve sağlık raporundaki "Başlığı bir cildi, ISBN'i başka cildi gösteren ürünler" bölümünde listeleniyor. Yubooh Uyurken'de her ürün kendi başlığındaki cilde gidiyor; katalog ISBN'leri değişmiyor (uzlaşı kuralları aynı).
- Sadece başlıkla eşleşen yüksek fiyatlı ürünün reddi kaldırıldı; fiyat aykırılıkları raporda.
- Reddedilen ürünün mevcut ilanı sadece yabancı baskı kanıtlanınca kaldırılıyor (Monster 9 VIZ). Cildin kendi ISBN'i farklıyken başka ISBN'li ürünün bağlanmaması (`isbn_conflict`, eskiden beri var) duruyor ama mevcut ilan silinmiyor.

### 17 Ekim: ISBN kanıt sistemi (P0 kilidi kalktı)

Kullanıcının asıl derdi: Mangakol'un aynı ISBN'i iki cilde vermesi (Blue Lock 28/29 → …626) ve yayınevlerinin özel baskıyı normal baskıyla aynı ISBN'le basması. Beş adım tek seferde yapıldı (`0018_isbn_evidence`).

- **P0 kalktı:** Bütün `isbn*` trigger'ları düşürüldü; readiness kontrolü, açılıştaki denetim işçisi, Codex'in inceleme merkezi ve dış kaynak adaptörleri (`isbn_audit/decisions/sources/identity/triage`) kaldırıldı. Migration'ların ihtiyaç duyduğu `isbn_safety.py`, `isbn_approval_guards.py`, `safety_backup.py` duruyor. Bakım araçları (yabancı baskı temizliği, hayalet cilt birleştirme, `isbn_conflict_fix`, `apply_task*`) P0 öncesi haline döndü. Yanlış eşleşme kaldırma geri geldi. Kalkan ürünler silinmiyor, "stokta yok" işaretleniyor (P0'dan kalan, daha iyi davranış). Yayınevi/seri bulanık birleştirmesi kapalı kaldı (artık gereksiz). 0018'in downgrade'i de reddediyor; geri dönüş yedekten.
- **Kaynak ve karar ayrı:** `volumes.catalog_isbn` (Mangakol ne diyor) ve `volumes.isbn` (ne kararlaştırdık) + `isbn_source` (catalog / stores / admin / legacy). Her değişiklik `isbn_changes`'e gerekçesiyle. Migration, çıkmış ciltlerin Mangakol sayfalarını yeniden okunacak diye işaretledi (senkron başına 600 sayfa → ~4 senkron).
- **Çözücü kuralları** (`isbn_resolver.py`, her senkron sonunda tüm katalog, her fiyat taramasından sonra dokunulan ciltler):
  1. Admin kararı hiç ezilmez ("otomatiğe bırak" ile kaldırılır).
  2. Mağaza uzlaşısı: başlığı bu cildi gösteren en az 2 bağımsız mağaza aynı ISBN'i gösteriyorsa ve Mangakol'un kullanılabilir farklı bir ISBN'i yoksa. Gerekli Şeyler + Büyülü Dükkan ve Kitap Sepeti + İstanbul Kitapçısı tek oy (aynı yanlış stok kodları / aynı sayfalar).
  3. Mangakol: geçerli, Türk, kaynakta tekrar etmeyen ISBN boş alanı doldurur. Mevcut geçersiz (yabancı/barkod/checksum) ISBN boş sayılır.
  4. Kaynakta tekrar: Mangakol aynı ISBN'i farklı numaralı ya da başka bir kitaba vermişse hiçbirine yazılmaz; diğer cildin farklı geçerli ISBN'i varsa tekrar "açıklanmış" sayılır (Blue Lock 29 …633 olunca 28 …626 alır; Happiness 6'nın …324050'si 5'e …360492'yi bırakır).
  5. Başka ciltteki ISBN: aynı kitabın başka baskısıysa ve iki sayfa da aynı ISBN'i gösteriyorsa ortak (`shared_isbns`); sayfalar farklıysa her baskı kendi ISBN'ini alır (Soichi); hayalet/katalog dışı kayıttan alınır; gerçek bir katalog cildinden sadece mağaza uzlaşısıyla ve o cildin lehine oy yoksa taşınır. Gerisi `isbn_issues`.
- **Eşleştirme** (`import_service._resolve_target`): başlık (ISBN yok sayılarak) ve ISBN ayrı çözülür. Aynı cilt → bağla; başlık aynı kitabın başka baskısı → baskı kelimesi, "Ana Kapak", fiyat aralığı (±1,5×); farklı cilt → `isbn_title_conflict`, bağlanmaz ve mevcut ilan kaldırılır. (Akşam güncellemesi: çelişkide başlık kazanıyor, fiyat reddi kaldırıldı; aşağıya bakın.)
- **Gözlem kaydı** (`store_observations`): her ürün için başlık, ISBN, fiyat, başlığın ve ISBN'in gösterdiği cilt, bağlandığı cilt, kural/ret nedeni. Okunan ISBN aynı URL + aynı başlıkla tekrar kullanılıyor (mağazalar sayfaları başka cilde çeviriyor). Gerekli Şeyler/Büyülü Dükkan detay kotası (15) artık sadece ISBN'i bilinmeyen ürünlere.
- **Admin:** cilt sayfasında "ISBN ve eşleşmeler" paneli (Mangakol / bizim ISBN, oylar, çelişki, her ürün için "neden burada", geçmiş, elle ISBN / ortak / taşı / otomatiğe bırak; `GET/POST /admin/isbn/volumes/{id}`). Sağlık raporu: çözülemeyen çelişkiler, Mangakol tekrarları, başlık-ISBN çelişkili ürünler, Mangakol'dan farklı ciltler, fiyat aykırılıkları, son değişiklikler. Gürültülü adres kontrolü kaldırıldı.
- **Testler:** Backend 898 test geçti; yeni `test_isbn_evidence.py` canlı vakaları birebir kuruyor (Blue Lock, Yubooh, Happiness, Monster, Solo Leveling fiyat aralığı, admin kararları). TypeScript, ESLint ve üretim derlemesi başarılı.
- **Sınırlar:** Etki canlıda kademeli: Mangakol ISBN'leri ~4 senkronda, mağaza oyları fiyat taramalarıyla (her seri günde bir) birikir. Mağaza grupları gözleme dayanıyor; başka ortak beslemeler bulunursa `VOTE_GROUPS`'a eklenmeli.

### 17 Ekim: ISBN sağlık raporunun canlı sonucu

- Canlı rapor (08:42 UTC): 2.359 çıkmış ciltten **27'si ISBN'siz** (%1), ilanı olan 8. Bunların 4'ü bu hafta çıkan ciltler (Mashle 8, Vatansever Moriarty 6, Mavi Kutu 5, Kaiju No. 8 9); Mangakol ISBN'leri "güvenle yazılabilir", P0 yüzünden yazılmamış. Baskı karışması (seriye göre fiyat aykırılığı) **0**.
- **Happiness 6 canlıda doğru** (…324050); Mangakol şimdi 5. cildin barkodunu öneriyor, P0 ezilmesini önlemiş.
- **Adresi başka cildi gösteren 30 ilan** canlı ürün sayfalarıyla kontrol edildi; çoğu yanlış alarm: mağazalar eski ürünü düzenleyip yeni cilde çeviriyor, adres eski kalıyor ("naruto-18-cilt-kopya" → Naruto 54; "derin-tarih-…-sayi-153" → Vinland 6, ISBN aynı). Gerçek yanlış eşleşmeler:
  - **Yubooh Uyurken 1↔2:** Gerekli Şeyler ve Büyülü Dükkan stok kodlarını karıştırmış ("Cilt 2" ürününde …431). Bora, Mangakol ve bizim DB …431 = Cilt 1. ISBN başlığı ezdiği için ürünler ters ciltlere düşmüş.
  - **Akame Keser 3** ← Kitapseç'in "Akame Keser 2" ürünü (mağazanın ISBN'i 3. cildin).
  - Kamisama Kiss 8 (Komikşeyler) doğrulanamadı: site 503.
- **Yüksek fiyat aykırılıkları:** Monster 9'a Gerekli Şeyler'in **İngilizce VIZ Perfect Edition**'ı (1.265 TL) bağlanmış: kartta ISBN yok, başlık "MONSTER 09" ile eşleşmiş, yabancı ISBN detay sayfasında. Komünist Manifesto'ya başka yayınevinin baskısı başlıkla bağlanmış. Madoka Magica 1 (Kitapbulan 502 TL) ISBN'i doğru.
- **Düşük fiyat aykırılıkları** çoğunlukla gerçek indirim (BKM'de Beta Byou kitapları 99 TL); otomatik gizlenmemeli.
- 4 özel baskıda ISBN yerine mağaza barkodu duruyor (Solo Leveling Limitli/Varyant, Titana Saldırı: Kayıp Kızlar Limitli). Yıldızların Sesi (5 mağaza) ve Komünist Manifesto ilanları ayrıca eski kopya ciltlere (2439, 2451) de bağlı.
- **Sonuç:** Canlıda en çok zarar veren iki yol: (1) mağazanın yanlış ISBN'i başlıktaki cilt numarasını eziyor; (2) ISBN'siz mağaza kartı sadece başlıkla eşleşiyor, yabancı/başka yayınevi baskısı sızıyor. Adres kontrolü gürültülü; mağaza başlığı saklanınca onunla değiştirilmeli.

### 17 Ekim: ISBN sağlık raporu (salt okunur)

- Admin paneline **ISBN Sağlık Raporu** eklendi (`/admin/isbn/saglik`, API `GET /admin/isbn/health`). Hiçbir kaydı değiştirmez.
- Kontroller: kayma şüphesi (Mangakol'un önerdiği ISBN komşu ciltte), adresi başka cildi gösteren ilanlar, serinin diğer ciltlerinden çok farklı fiyatlı ciltler (baskı karışması), diğer mağazalardan çok farklı fiyatlı ilanlar, Mangakol'un önerip yazılmayan ISBN'leri (son senkron), ISBN'siz çıkmış ciltler, geçersiz ISBN'ler, birden fazla ciltte duran ürün.
- "Raporu indir (JSON)" düğmesi var; kullanıcı canlıda açıp dosyayı paylaşacak, düzeltmelerin önceliği buna göre belirlenecek.
- `tzdata` gereksinimlere eklendi (Windows'ta testler için). Backend 1.088 test geçti; TypeScript, ESLint ve üretim derlemesi başarılı.

### 16–17 Ekim: ISBN sisteminin ölçümü ve keşif kaynakları araştırması

- Kod değişmedi; sadece ölçüm ve araştırma. [Ayrıntılı rapor](kesif-kaynaklari-arastirmasi-2026-10-16.md).
- **ISBN doğrulama sistemi (PR #4–#10) pratikte çalışmıyor.** GitHub'daki denetim kodu 40 rastgele ciltte gerçek kaynaklarla çalıştırıldı. Railway koşullarında (Kitapyurdu 403) **0 doğrulandı**, 39 "yetersiz kanıt". Sebepler: BKM araması her zaman sonuç sınırına ulaştığı için hep `ERROR` sayılıyor; arama sorgusu Mangakol slug'ının romaji adıyla yapılıyor ("hori san to miyamura kun 15"); Pandora ve D&R hep 403; Bora 24'ten fazla sonuçta hata veriyor. Bir cilt ~31 sn, tam katalog ~20 saat.
- **P0 kilidinin yan etkileri:** Katalog senkronu ve mağaza aktarımı yeni ciltlere ISBN yazmıyor (14 Ekim'den beri yeni ciltler sadece başlıkla eşleşiyor); trigger'lar ilan silmeyi engellediği için admin'in "yanlış eşleşmeyi kaldır" düğmesi çalışmıyor.
- **Mangakol ISBN'leri bir cilt kayabiliyor:** Skip and Loafer 4, Huzurlu Kamp 3 ve Happiness 6'da (Kayıp Kıta) Mangakol önceki cildin barkodunu vermiş; Bora barkod sayfası ve Kitapyurdu ile doğrulandı.
- **Kapsama:** Bugün taranan 9 mağaza Mangakol'daki çıkmış ciltlerin %92'sini, son 90 günde çıkanların %87'sini listeliyor.
- **Kullanıcı kararları:** Mangakol'a bağımlılık bitirilecek, Mangakol tek bir besleme olarak kalacak. ISBN çelişki yoksa otomatik yazılacak; trigger'lı P0 kilidi yerine hafif değişiklik kaydı + yedek; admin gerekçeyle ISBN girebilecek; keşfedilenler otomatik eklenecek. Cilt cilt arayan eski denetim kaldırılacak. "Yakında" için Mangakol + elle giriş.
- **Sırada:** Tüm sistemin ISBN ve eşleştirme açısından taranması ve düzeltme planı (kullanıcı 17 Ekim'de istedi). Bora/Instagram/e-posta yolları şimdilik beklemede.

### 1–2 Ekim: stok kuralı, baskılar, hız (özet)

- **Stok kuralı:** Ziyaretçiye stokta olmayan teklif gösterilmez; cilt ya "N mağazada stokta" ya "Stokta yok" (`a72d8fa`). Kitapseç adı düzeltildi.
- **Yeni mağazalar:** Büyülü Dükkan ve İstanbul Kitapçısı (`244453c`); admin mağaza erişim testi (`3730b8d`).
- **T-Soft stok okuması** (İstanbul Kitapçısı, Kitap Sepeti) ürün sayfasından, 60 ürüne kadar (`f1ba8eb`). Cilt araması ("one piece 47"), koleksiyon sayfası.
- **Paralel tarama:** Bir serinin mağazaları aynı anda taranıyor; tam güncelleme ~2 saatten ~1 saat 20 dk'ya indi (`df52800`).
- **Baskılar:** Mangakol'daki her sekme ayrı seri (`<slug>~clothbound`). Solo Leveling için ortak ISBN `SHARED_ISBN_OWNERS` ile varyanta verildi, ISBN'siz ürünler başlıktaki etiket kelimesinden eşleniyor. Afro Samuray: normal sayfası da aynı ISBN'i gösteriyorsa ISBN normal baskıda kalır (`26e46fb`, `bc3074b`, `10e6d47`).
- **Derin arama:** Gerekli Şeyler, Kitapbulan ve Büyülü Dükkan sonuç sınırları uzun seriler için artırıldı (One Piece 51).
- **Diğer:** One shot yönlendirmesi, seri seri koleksiyon, admin "kaydı olmayan mağazalar" kutusu, tüm saatler Türkiye saati, hero kapakları ve puantiye arka plan.

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

## Sıradaki adımlar

Bekleyen işler [yapılacaklar.md](../yapılacaklar.md) dosyasında.

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
