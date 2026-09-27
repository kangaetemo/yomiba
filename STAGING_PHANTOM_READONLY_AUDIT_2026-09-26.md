# Railway staging — salt okunur phantom audit
Tarih: 2026-09-26. Hedef: dynamic-purpose / serene-rejoicing; Railway ortam etiketi production, uygulama APP_ENV=staging. DB: /data/yomiba-staging.db.
Bu rapor uygulama kodunu veya DB'yi değiştirmez. Commit/push/deploy/cleanup/delete/merge yapılmadı. Önceden staged olan dosyalar yerinde bırakıldı.

## Yöntem ve sınırlar
SQLite mode=ro ve PRAGMA query_only=ON ile sorgulandı. Ana rapor verileri tek okuma transaction'ından alındı. Kişisel bağlantılar daha sonraki salt okunur sorguda sayıldı. Uygulama scheduler ayarları değiştirilmedi; rapor anlık gözlemdir.
Railway /tmp/yomiba-phantom-readonly.json dosyasına yalnızca katalog, listing, toplulaştırılmış history ve import bilgileri yazıldı; DB dosyasına yazılmadı. Bu geçici rapor, DB yedeği değildir.
Staging'de audit_phantom_volumes.py bulunmadığı için deploy yapılmadan doğrudan read-only sorgular kullanıldı. Mevcut plan_merge güvenlik koşulları koddan incelendi; merge fonksiyonu çalıştırılmadı.
Ham scraper ürün başlığı, ürün bazında import provenance ve Volume.created_at saklanmıyor. Güncel URL başlığı tek başına geçmiş ürünün aynı edition olduğunun kanıtı değildir.

## PHANTOM ROOT CAUSE
76 adet volume_number<1: 75 adet -1 ve 1 adet 0. Tümü catalog_series içindeki 76 farklı seriye bağlı ve tümünün ISBN'si var.
60 adayın serisinde yalnızca pozitif Volume 1 var; 15 adet -1 adayın serisinde birden fazla pozitif cilt var; gerçek 0. cildin serisinde 1–21 var.
Adaylarda 168 listing, 167 fiyat geçmişi noktası var. WishlistItem=0, PriceAlert=0, UserVolumeCollection=0.
Bu serilerde toplam 166 pozitif Volume var; 78'inin ISBN'si dolu. Bu sayı, temiz/manga olduğu kanıtlanmış pozitif cilt sayısı değildir.

### Zaman çizgisi (UTC)
- 2026-09-25 20:56:57.169: refresh başladı, 468 seri / 463 query.
- 20:58:49.427–21:26:03.958: 16 yeni -1 oluşturma logu.
- 21:39:12.550: bir sonraki refresh başlangıcı, 468 seri / 463 query.
- 21:40:09.953–23:19:30.886: 59 yeni -1 oluşturma logu.
- 23:20:10.689: son döngü bitti; catalog=468, submitted=383, skipped=82, success=386, failed=0, duration=6058.1s.
75 oluşturma logu mevcut 75 negatif adayın series_id değerleriyle eşleşiyor. Son döngüde yeni oluşan negatif aday sayısı 59; önceki dönemde 16. Kalan ID 1 gerçek sıfırıncı cilttir. İlk history zamanı 20:57:07.639106; bu onun oluşturulma zamanı değildir.
Son döngünün ilk yeni negatif kaydından sonra mevcut aday kümesinin 18 üyesi artık vardı (1 sıfırıncı + 17 negatif); ardından 58 negatif daha oluştu. Eski “18” ölçümünün tarihli ID listesi olmadığı için bu ölçümle birebir aynı snapshot olduğunu kanıtlayamıyoruz. Önceki catalog audit'teki 18 manifest dışı Series ise farklı bir metriktir.

### Kök neden
Deploy edilmiş eski ImportService, ürün/scraper cilt numarası bulamayınca UNNUMBERED_VOLUME=-1 kullanıyor; (series, -1) yoksa yeni Volume yaratıyor. Tek ciltli eserlerde mevcut Volume 1'e güvenli fallback yok.
Başlık çakışmaları başka eser/edition ürünlerini aynı seriye taşıyabiliyor. Aynı -1 kaydı altında farklı mağazalardan gelen ürünler toplanıyor; eski _resolve_volume farklı ISBN'yi her durumda red yerine mevcut ISBN'yi tutarak aynı Volume'a dönebiliyor.
Bu nedenle sorun yalnızca “eksik cilt numarası” değil; yanlış eser ve karışık listing riski de var. Katalogda olmayan ürünün mağazada kitap olması, doğru manga edition'ı olduğunu kanıtlamaz.
Yeni local kod _resolve_volume içinde yeni Volume oluşturmuyor; fakat mevcut negatif ISBN sahibini hedefe dönüştürmeden volume_not_found ile reddediyor.

### İçerik kanıtının seviyesi
- 1 doğrulanmış gerçek 0. cilt: Jujutsu Kaisen 0 / 9786257590303. KEEP.
- 4 doğrulanmış normal katalog ürün adayı: Elveda Eri, Kadın ve Kedisi, Scientia, Ada 1. Cilt. Pozitif hedefleri sırasıyla 96, 1358, 1496, 2071; dört hedefin ISBN'si boş.
- En az 10 adayın mevcut ISBN'si başka eser/edition'a ait: Parazit, Limit, Renksiz, Nana, Leviathan, Kehanet, Paranoya, City, Kavgam, Kapital. Manga cildine otomatik taşınmamalı.
- Kalan 61 için bütün listing/edition kanıtı tamamlanmadı. Bunların normal cilt, farklı baskı veya başka eser olduğu kesin sayıyla söylenemez.
- Doğrulanmış set/bundle sayısı 0; bu, hiç set olmadığı anlamına gelmez. Listing URL'lerinde seti/bundle/box/omnibus/kutu işareti görülmedi. URL üzerinden ürün türü kesinleştirilemez.

## SAFE_MERGE / REVIEW / KEEP
**SAFE_MERGE=0 / REVIEW=75 / KEEP=1.**
SAFE_MERGE=0, eşleştirilebilir hiçbir kitap olmadığı anlamına gelmez. Her listing için doğru eser, yayınevi, ISBN ve hedef kanıtı tamamlanmadan veri hareketine güvenli etiketi verilmedi.
K: gerçek 0. cilt, pozitif 1 ile birleştirilmez.
N: pozitif hedef için güçlü ürün kanıtı var; bütün listing kanıtı ve history konsolidasyon planı eksik.
X: mevcut ISBN başka eser/edition'a ait; katalog cildine merge uygun değil, karantina/yanlış listing incelemesi gerekir.
M: birden fazla pozitif cilt; hedef cilt kanıtlanmadı.
S: yalnızca pozitif Volume 1 var; tek başına edition/ISBN doğrulaması sayılmaz.

| Volume ID | Series | Karar | Neden |
|---|---|---|---|
| 1 | Jujutsu Kaisen - Lanet Savaşları | KEEP | K |
| 2336 | Elveda Eri | REVIEW | N |
| 2337 | Titana Saldırı Pişmanlık Yok | REVIEW | S |
| 2338 | Look Back | REVIEW | S |
| 2339 | Korku Dağı | REVIEW | S |
| 2340 | Mimi'nin Dehşet Öyküleri | REVIEW | S |
| 2341 | Parazit | REVIEW | X |
| 2342 | Sensör | REVIEW | S |
| 2343 | Pankreasını Yemek İstiyorum | REVIEW | S |
| 2344 | Limit | REVIEW | X |
| 2345 | Yıldız Bekçisi Köpek | REVIEW | S |
| 2346 | Mamiya'nın Düello Çağrısı | REVIEW | S |
| 2347 | Great Trailers | REVIEW | M |
| 2348 | Afro Samurai | REVIEW | S |
| 2349 | Ningyo | REVIEW | S |
| 2350 | GYO | REVIEW | S |
| 2351 | Solanin | REVIEW | S |
| 2352 | Death Note Short Stories - Kısa Öyküler | REVIEW | S |
| 2353 | Renksiz | REVIEW | X |
| 2354 | Sığınak | REVIEW | S |
| 2355 | Soichi | REVIEW | S |
| 2356 | Kyoto'nun Arka Yüzü | REVIEW | S |
| 2357 | Saniyede 5 Santimetre | REVIEW | S |
| 2358 | Nana | REVIEW | X |
| 2359 | Nijigahara Holograf | REVIEW | S |
| 2374 | Korku Kesitleri | REVIEW | S |
| 2375 | Humanitas | REVIEW | S |
| 2376 | Mezarlık | REVIEW | S |
| 2394 | Cehennem Yıldızı Remina | REVIEW | S |
| 2396 | Emanon'un Hatıraları | REVIEW | S |
| 2397 | Kara Paradoks | REVIEW | S |
| 2410 | Kadın ve Kedisi | REVIEW | N |
| 2411 | İlahi Yalan | REVIEW | S |
| 2412 | Yine Aynı Rüyayı Gördüm | REVIEW | S |
| 2413 | Şaman Kral | REVIEW | M |
| 2414 | Ölülerin Aşk Hastalığı | REVIEW | S |
| 2416 | Hayatımı Yıllık 10 Bin Yen'e Sattım | REVIEW | S |
| 2417 | Yumi ve Kurumi | REVIEW | S |
| 2418 | One Room Angel | REVIEW | S |
| 2419 | Kelimeler Bahçesi | REVIEW | S |
| 2420 | Tadımlık Otobüs Hikayeleri | REVIEW | S |
| 2421 | Vitamin | REVIEW | S |
| 2422 | Scientia | REVIEW | N |
| 2423 | Ateş Böceklerinin Işıldayan Ormanlarına | REVIEW | S |
| 2424 | Leviathan | REVIEW | X |
| 2425 | Suzume | REVIEW | S |
| 2426 | Kör Noktadaki Venüs | REVIEW | S |
| 2427 | Jizo | REVIEW | S |
| 2428 | Monoton Blue | REVIEW | S |
| 2429 | Disney Manga: Karmakarışık | REVIEW | S |
| 2430 | Disney Manga - Güzel ve Çirkin - Çirkin'in Hikayesi | REVIEW | S |
| 2431 | Disney Manga - Güzel ve Çirkin - Bella'nın Hikayesi | REVIEW | S |
| 2432 | Yeni Normal | REVIEW | M |
| 2433 | Disney Manga: Miriya ile Marie | REVIEW | S |
| 2434 | MANNEQUIN feat. Hatsune Miku | REVIEW | S |
| 2435 | Kehanet | REVIEW | X |
| 2436 | Cthulhu'nun Çağrısı | REVIEW | S |
| 2437 | Paranoya | REVIEW | X |
| 2438 | I Am a Hero | REVIEW | S |
| 2439 | Yıldızların Sesi | REVIEW | S |
| 2440 | Kıyamet Lunaparkı | REVIEW | S |
| 2441 | Disney Manga: Minik Perinin Günlüğü | REVIEW | S |
| 2442 | City | REVIEW | X |
| 2443 | Derslerini Verelim | REVIEW | M |
| 2444 | Moriwaki'nin Deprem Rehberi | REVIEW | M |
| 2445 | Ada | REVIEW | N |
| 2446 | Öpücüğe Uzanan Mesafe | REVIEW | S |
| 2447 | Gökteki Hayalet Gezileri | REVIEW | S |
| 2448 | Kavgam | REVIEW | X |
| 2449 | Orman Suyu | REVIEW | M |
| 2450 | İlahi Komedya | REVIEW | S |
| 2451 | Komünist Manifesto | REVIEW | S |
| 2452 | Karga ile Ayı | REVIEW | S |
| 2453 | İtiraf | REVIEW | S |
| 2454 | Kapital | REVIEW | X |
| 2455 | Denizin Derinliklerinde Hayatta Kalmak | REVIEW | S |

## ELVEDA ERİ BLOCKER
Series 6 / manifest slug sayonara-eri.
- Phantom 2336: volume_number=-1; ISBN 9786258237559; Gerekli Şeyler, Kitapseç, BKM olmak üzere 3 listing.
- Katalog Volume 96: volume_number=1, ISBN NULL.
- Yayınevinin ürün sayfası aynı ISBN'yi Elveda Eri olarak doğruluyor.
Yeni kodun sırası: ürün → ISBN lookup → Volume 2336 bulunur → volume_number<1 → volume_not_found → return.
Bu erken dönüş, Series/Publisher çözümlemesine ve tek cilt fallback'ine ulaşmayı engeller. Sonuçta 96 güncellenmez, ISBN ile zenginleşmez.
ISBN volumes tablosunda global unique olduğundan, eski sahibini korurken aynı ISBN'yi 96'ya yazmak constraint ihlali olur.
ISBN'siz gelen ve kalan kuralları geçen ürün 96'ya bağlanabilir; eski 2336 ve listing'leri yine yerinde kalır. Bu nedenle “her mağaza kesin reddedilir” denemez.

## OTHER BLOCKED SERIES
Tablodaki 76 ISBN sahibinin tamamı yeni <1 kontrolüne takılır (ön filtrelerden geçen ve o ISBN'yi taşıyan sonuçlar için).
Bu 76 doğru ürünün kaybı anlamına gelmez: yanlış eser ISBN'lerinin reddi doğrudur. Risk, doğru katalog edition'larının eski negatif sahibi nedeniyle reddedilmesidir.
Doğrulanmış diğer örnekler:
- Kadın ve Kedisi 2410 → katalog 1358 / 1; ISBN 9789757938071.
- Scientia 2422 → katalog 1496 / 1; ISBN 9786052656051.
- Ada 2445 → katalog 2071 / 1; ISBN 9786053049999; seride ayrıca cilt 2 var, otomatik tek cilt fallback uygun değil.
- Jujutsu Kaisen 0, ID 1 → ISBN 9786257590303; mevcut gerçek 0. cildin fiyat yenilemesi de reddedilir. Bu ürünün hedefi Volume 1 değildir.
One Piece bu 76 aday kümesinde yok. Bu tespit One Piece'in tüm listing/edition verisinin temiz olduğunu kanıtlamaz.

## DEPLOY ORDER
Öneri **C: küçük compatibility adımı + kontrollü deploy + ayrı onaylı veri düzeltmesi**. Zorunlu geniş schema migration önerilmiyor.
A (mevcut kodu olduğu gibi deploy, sonra cleanup): yeni -1 üretimini durdurur fakat doğru ISBN'li ürünlerde boşluk/stale fiyat ve gerçek 0. cilt regresyonu bırakır.
B (önce cleanup, sonra deploy): eski çalışan kod aynı hatalı kayıtları yeniden yaratabilir; 10 yanlış eser ISBN'sini hedefe taşımak ayrıca yanlıştır.
C: gerçek katalog cilt geçerliliğini yalnızca >0 ile tanımlamayan ve legacy ISBN sahipliğini açıkça ele alan küçük bir uyumluluk tasarımı hazırlanmalı. Bu raporda kod değişikliği yapılmadı.

## RISK
- ISBN'li doğru ürünler erken reddedilir; 168 eski listing silinmez ama bazı fiyatlar güncellenmez.
- ISBN'siz ürünler doğru pozitif ciltte yeni listing açarken eski negatif listing de kalabilir; shelf/detail davranışı ayrıca kontrol edilmeli.
- record_import_result, stores_ok>0 ise last_success_at günceller. Tüm ürünler eşleşme reddi alsa bile mağaza çağrıları başarılıysa query fresh görünebilir.
- Yanlış eserleri pozitif cilde toplu taşımak, catalog correctness ve price history anlamını bozar.
- 0. cildi -1 ile aynı politikaya sokmak mevcut gerçek ürünü devre dışı bırakır.
- Geçiş sırasında process-local kilitleri kullanmayan ayrı bir cleanup process'i çalışan importlarla yarışabilir.

## RECOMMENDATION
1. Bu salt okunur bulguları başlangıç baseline'ı olarak sakla; sonraki işlem öncesi yeniden ölç.
2. Önce geçerli 0. cilt ve legacy ISBN senaryoları için küçük uyumluluk davranışını tasarla ve geçici DB testleriyle doğrula. Belirsiz ISBN sahibini atlayarak title fallback yaptırma; otomatik ISBN taşıma/merge yapma.
3. Gerekirse ayrı, denetlenebilir source→target çözümleme planı kullan; yanlış eserleri alias olarak eşleme. Bu bir öneridir, uygulanmadı.
4. Bakım penceresinde aktif importların bitmesini bekle; backup ve restore kontrolü al; scheduler/import yazarlarını kontrollü biçimde durdur. Ayarları şu anda değiştirme.
5. Yeni -1 yaratımını engelleyen, 0. cildi koruyan sürümü aynı koordinasyon içinde deploy et. Önceki writer'ın yeniden phantom üretmesine fırsat bırakma.
6. Her ürün/listing için kanıt tamamlanınca SAFE_MERGE planını tekrar üret. 168 listing/167 history noktasını ve kullanıcı ilişkilerini yeniden say. Kişisel ilişki sayısı bugün 0, gelecekte yeniden kontrol şart.
7. Ayrı kullanıcı onayı olmadan veri düzeltmesi uygulama. Karışık/yanlış eserler toplu Volume 1 merge kapsamına alınmamalı.
8. Onaylı düzeltme sonrası Elveda Eri, gerçek 0. cilt, çok ciltli Ada ve One Piece ile kontrollü import doğrula; rejected reason/freshness/listing/history ve yeni negatif sayısını karşılaştır.
Bu rapordan sonra duruldu; hiçbir deploy/cleanup/import tetiklenmedi.

## Dış ürün kanıtları
- [Jujutsu Kaisen 0, ISBN 9786257590303](https://www.kitapyurdu.com/kitap/jujutsu-kaisen-0-cilt-goz-kamastiran-karanlik/619582.html)
- [Elveda Eri — yayınevi](https://www.gerekliseyler.com.tr/urun/elveda-eri)
- [Kadın ve Kedisi](https://www.illakitap.com/kadin-ve-kedisi)
- [Scientia — yayınevi](https://www.ithakiyayingrubu.com/scientia)
- [Ada Birinci Cilt — yayınevi](https://www.artemisyayinlari.com/kitap-detay.php?k=474633)
- [Parazit / Michel Serres](https://www.kitapyurdu.com/kitap/parazit/677397.html)
- [Limit / Frank Schatzing](https://www.sehadetkitap.com/urun/limit)
- [Renksiz / Muhammet Özkan](https://www.sehadetkitap.com/urun/renksiz)
- [Nana / Emile Zola — kütüphane kataloğu](https://katalog.mudanya.edu.tr/bib/2259)
- [Leviathan / Boris Akunin — yayınevi](https://www.alfayayinlari.com/kitap.php?id=388497)
- [Kehanet / Arthur Schnitzler](https://www.kitapyurdu.com/kitap/kehanet/751457.html)
- [Paranoya / Julio de Mattos](https://www.kitapyurdu.com/kitap/paranoya/675146.html)
- [City / Abi Hall](https://www.sanmin.com.tw/product/index/007405859)
- [Kavgam / Katip baskısı](https://www.sehadetkitap.com/urun/kavgam-18)
- [Kapital & Güncel Bir Yorum / Hakan Şakar — kütüphane listesi](https://www.agri.edu.tr/upload/kutuphanevedokumantasyondairebaskanligidetay261/2017%20ihalesi%20Kutuphane.pdf)


