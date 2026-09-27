# 75 REVIEW adayı — bağımsız kanıt incelemesi

Salt okunur staging audit; 2026-09-26. Hiçbir merge/delete/DB write uygulanmadı. Son audit çıktısı `APPLIED False`.

## Sonuç

İncelenen 75 REVIEW adayından **10 SAFE_MERGE_CANDIDATE, 65 REVIEW, 0 KEEP**. Bunlar uygulanmış birleşimler veya bütün kalan adayların güvensiz olduğuna dair karar değildir. Yeterli kanıt bulunmayanlar REVIEW kaldı.

AniList tek-cilt sinyali, mevcut tek pozitif katalog cildi (1), Mangakol seri/yayıncı kimliği ve mağaza ürünlerinin ISBN/yayıncı/başlık bilgileri birlikte kontrol edildi. 12 güçlü adayın 38 listing sayfası incelendi. Kaynak bazlı gözlemler `phantom-independent-evidence-2026-09-26.json` dosyasındadır. Aynı kitaba ait mağaza bilgilerinin ortak tedarikçiden gelme ihtimali vardır; yalnızca birden çok mağazada görünmek bağımsız baskı kanıtı sayılmadı.

| Phantom → katalog Volume | Seri | ISBN | Listing | History |
|---|---|---|---:|---:|
|2336 → 96|Elveda Eri|9786258237559|5|5|
|2338 → 145|Look Back|9786256031302|5|5|
|2359 → 1156|Nijigahara Holograf|9786257590594|3|3|
|2375 → 1263|Humanitas|9786259961347|4|4|
|2397 → 1334|Kara Paradoks|9786259324074|5|5|
|2418 → 1442|One Room Angel|9786256449282|2|2|
|2419 → 1446|Kelimeler Bahçesi|9786058033412|3|3|
|2420 → 1460|Tadımlık Otobüs Hikayeleri|9786057111593|3|3|
|2422 → 1496|Scientia|9786052656051|2|2|
|2452 → 2276|Karga ile Ayı|9786259617572|1|1|

Toplam **33 listing / 33 history**. İncelenen adaylarda kullanıcı ilişkisi saptanmadı; hedef cilt ISBN'leri boştu. Uygulama öncesi bütün ilişki ve çakışma kontrolleri yeni snapshot üzerinde tekrarlanmalıdır.

## REVIEW kalan iki güçlü aday

- **2428 Monoton Blue → 1800:** Mağaza başlığı Monotone Blue, katalog yerel başlığı Monoton Blue. Mangakol orijinal başlığı alias bağlantısını destekliyor; mevcut planner'ın tam başlık eşitliği şartı geçmiyor. 4 listing. Bu incelemede kural gevşetilmedi.
- **2451 Komünist Manifesto → 2245:** DB katalog yayıncısı Yordam; gerçek ürün ISBN 9786254180835, Kırmızı Kedi / Martin Rowson baskısı. Aynı başlık başka baskıyı kanıtlamıyor. 1 listing. Birleştirme önerilmiyor; REVIEW olarak korunmalı.

Diğer 63 aday bu güçlü tek-cilt grubunun dışında ve yeterli ek kanıt elde edilmedi; yeniden sınıflandırılmadı.

## Örnek çapraz kaynaklar

- Elveda Eri: [Mangakol](https://mangakol.com/manga/sayonara-eri), [yayıncı ürünü](https://www.gerekliseyler.com.tr/urun/elveda-eri).
- Look Back: [Mangakol](https://mangakol.com/manga/look-back), [yayıncı ürünü](https://www.gerekliseyler.com.tr/urun/look-back-1).
- One Room Angel: [Mangakol](https://mangakol.com/manga/one-room-angel), [yayıncı](https://komikseyler.com.tr/urun/one-room-angel/).
- Scientia: [Mangakol](https://mangakol.com/manga/scientia), [İthaki](https://www.ithakiyayingrubu.com/scientia).
- Komünist Manifesto baskı uyuşmazlığı: [Kırmızı Kedi](https://www.kirmizikedi.com/komunist-manifesto-p-6341).
- Karga ile Ayı: [Mangakol](https://mangakol.com/manga/kuma-to-karasu), [ürün](https://www.gerekliseyler.com.tr/urun/karga-ve-ayi).

## Snapshot ve sınırlar

Staging verisi inceleme sırasında başka çalışan süreçler nedeniyle değişmeye devam etti; Nijigahara Holograf ve Kara Paradoks'a gelen yeni listingler de ayrıca doğrulandı. Son salt okunur planner sonucu staging `/tmp/yomiba-independent-reviewed-v3.json` dosyasından Railway konsolunda görüldü: 10 SAFE_MERGE_CANDIDATE / 65 REVIEW / 0 KEEP, APPLIED False. Bu dosya yerel olarak indirilmiş değildir ve geçici dosya kalıcılığı garanti edilmez.

Bu sonuç başlangıçtaki 75 REVIEW kümesini ele alır; toplam 76 phantom'un tamamı için yeni toplam sınıflandırma iddiası değildir.

## Yeni QA koduyla ilişkisi / sonraki adım

Yeni yerel kod phantom ISBN'yi taşımadan başlık/cilt üzerinden pozitif Volume'a yeni listing bağlayabiliyor. Dolayısıyla 2336 ISBN'si eski koddaki gibi mutlak blocker değil. Ancak eski listing/history otomatik taşınmıyor ve yeni listingler sonradan merge çakışması yaratabilir. QA incelemesindeki katalog sınırı ve stok/fiyat geçişi sorunları ayrıca düzeltilmeli.

Öneri: Bu 10 aday için onaydan önce, yazıcılar kontrollü biçimde durdurulmuşken yeni bir salt okunur plan ve yedek doğrulaması üret; listing/history/kullanıcı ilişkilerini yeniden say. Onay verilmeden cleanup uygulama. Bu incelemede scheduler ayarları değiştirilmedi, import başlatılmadı, deploy yapılmadı.
