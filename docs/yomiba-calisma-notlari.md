# Yomiba çalışma notları

Son güncelleme: 1 Ekim 2026. Son push: bu günkü "Slug URLs, search dialog" commit'i (main); öncesi `a906b8e`.

## Sistem nasıl çalışıyor

- **Katalog kaynağı Mangakol.** Katalog senkronu seri, cilt, kapak, ISBN, sayfa sayısı, yerel çıkış tarihi, yazar/çizer ve JP/TR yayın durumunu okur. Arama sadece Mangakol kataloğundaki serileri gösterir.
- **Fiyatlar mağazalardan gelir.** BKM, Kitapseç, Kitap Sepeti, Kitapbulan, Gerekli Şeyler, Edessa ve diğerleri taranır. Ürünler önce ISBN ile, olmazsa başlık ve yayınevi ile ciltlere eşlenir. ISBN her zaman başlıktan önce gelir.
- **Kapaklar bizde.** Mangakol'dan bir kez indirilip Railway volume'da WebP olarak saklanır ve `/api/covers/...` üzerinden sunulur. İleride R2'ye taşınabilecek şekilde yazıldı.
- **Deploy.** Backend Railway'de (SQLite, `/data` volume). Veritabanı güncellemeleri açılışta yedek alınarak otomatik çalışır. Frontend Vercel'de.

## Çalışma düzeni

- Her değişiklikten sonra testleri çalıştırıyorum. Özet Türkçe veriliyor ve push ancak senin onayınla yapılıyor.
- Backend testleri:
  - Komut: `cd backend && .venv/Scripts/python.exe -m pytest -q --ignore=tests/test_task2_identity.py`
  - `test_task2_identity.py` gerçek bir veritabanı istediği için yerelde her zaman hata verir; bu bir regresyon değil.
- Frontend kontrolleri: `cd frontend && npx tsc --noEmit -p . && npx eslint .`
- `test_rate_limit_keeps_per_store_interval` Windows'ta ara sıra zamanlama yüzünden düşüyor; eskiden beri var.
- Fiyatsız seriler raporu (`fiyatsızlar.txt`): Mağaza bazındaki sebep sayıları, sorgunun döndürdüğü tüm ürünler üzerinden toplanıyor. Örneğin BKM'de büyük bir `publisher_conflict` sayısı genelde "bu mağaza o seriyi satmıyor" demektir.

## Son günlerde yapılanlar

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

## Sıradaki adımlar (30 Eylül push'undan sonra)

1. Railway deploy'unun bitmesini bekle.
2. **Katalog güncellemesi:** JP/TR durumları dolar ve One Shot sekmesi görünür. Varyantlar kendi ISBN'lerini alır.
3. **Katalog güncellemesi, ikinci kez:** Normal ciltler kendi ISBN'lerini okur (Soichi → …101).
4. **Fiyat güncellemesi:** Yanlış yerdeki bez cilt fiyatları varyantlara taşınır.
5. **Kontrol:**
   - Normal Soichi sayfasında Kitapseç'in 385 TL'lik bez cilt fiyatı gitmiş olmalı; Soichi (Bez Cilt) fiyat almalı.
   - Fiyatsız seriler panelinde varyantlar yeni açıklamalarla görünmeli.

## Açık fikirler / belki sonra

- Seri sayfalarında "diğer baskılar" bağlantısı (Soichi ↔ Soichi (Bez Cilt)).
- One shot'ların tamamını listeleyen bir sayfa. Ana sayfada şu an en fazla 8 tane gösteriliyor.
- Kapakları Railway volume yerine R2'ye taşımak. Kod buna hazır; Mangakol yedek kaynak olarak duruyor.
- Fiyatsız seriler raporunu yeniden çekip kalanlara bakmak.
