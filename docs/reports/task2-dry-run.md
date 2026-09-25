# Görev 2 — Veri kalitesi denetimi: DRY-RUN raporu

Tarih: 2026-09-14 · Durum: **UYGULANDI** (aşağıda sonuç; plan bölümleri
dry-run'daki orijinal hâliyle korunuyor).

## UYGULAMA SONUCU (2026-09-14, onay sonrası)

* **Yedekler:** `yomiba.db.bak-task2` (merge öncesi), `yomiba.db.bak-task2b`
  (takip temizliği öncesi).
* **Ana merge** (`apply_task2_merges.py`, tek transaction):
  * Pre/post assertion'ların tamamı geçti (263 listing + 263 price-history
    kümelerde kayıpsız; 11 seri silindi; 4 slug taşındı; FK temiz).
  * Rehearsal, kopya DB üzerinde 3 kez çalıştırıldı; her seferinde
    yakalanan bir IntegrityError düzeltildi (UNIQUE(series_id,volume_number)
    sentinel çakışması, UNIQUE(isbn) sıralama, ON DELETE CASCADE sıralama).
* **Eksra (raporda işaretlendi, uygulandı):** mevcut FK yetimi katalog satırı
  (series 310, `yamada-kun-to-lv999-no-koi-wo-suru`) silindi — referansı
  olmayan 1 satır.
* **Takip merge** (`apply_task2_followup.py`, tek transaction):
  * Doğrulama için attığım arama curl'leri arama-tetikli background import
    başlattı (import_records 24/25/26). Yayınca-yazım varyantı yüzünden 3
    YENİ duplikat doğdu ve hepsi birleştirildi:
    * `2212` "Jujutsu Kaisen" (Gerekli Şeyler) → seri 4 (vol 6 cilt + 7 listing)
    * `2389` "Orange" (Komik Şeyler) → seri 1851 (2 birebir-duplike listing
      atıldı; price-history kayıpsız taşındı)
    * `2357` "Kara Kâhya" (Gerekli Şeyler) → seri 151 (vol 20-24, 5 listing)
* **Kimlik regresyon testleri:** `tests/test_task2_identity.py` — 18 test
  (gerçek DB kopyası üzerinde; import-tolerant invariant'lar).
* **Tam dizi: 377/377 yeşil.**
* **Canlı API:** `jujutsu`/`vinland`/`orange` aramaları tek seri döndürüyor;
  seri 4 cilt 0/1/9 görünür; import, JJK vol 8'i yeni seri 4'e doğru yerleştirdi
  (merge canlı akışta da doğrulandı).

## Yöntem

Kimlik kanıtı hiyerarşisi: **ISBN > yayınevi + seri adı + cilt no > başlık**.
Bir seri "hibrit" sayıldı: (a) asıl seriyle aynı işi taşıyan ama cilt alt-başlığı /
İngilizce önek yüzünden ayrı seri satırı oluşturulmuş, (b) katalog iskeleti
(mangakol slug'ı) ile data serisi ayrı kalmış.

**Hayatta kalan (survivor) kuralı:** verisi (cilt + listing) olan seri hayatta
kalır; boş katalog iskeletleri silinir ve `catalog_series` slug'ı veri serisine
taşınır. Neden: listing/price-history hareketi riskli, boş satır hareketi değil;
katalog senkronu slug→series_id haritasından çalıştığı için slug taşınması
yeterli.

**Güvenlik:** Her birleşim için (store_id, product_url) örtüşmesi kontrol edildi —
**9/9 temiz** (hiçbir listing iki kez eklenmeyecek). `series_id`'ye yalnızca
`volumes` ve `catalog_series` referans verir — kaynak seriler güvenle silinebilir.

## Küme 1 — Jujutsu Kaisen (Gerekli Şeyler)

| Seri | Başlık | Durum | Kanıt |
|---|---|---|---|
| **4** (survivor) | Jujutsu Kaisen | 15 cilt (2-7,10-19), 19 listing | asıl seri |
| 5 | Jujutsu Kaisen Vakitsiz Ölüm | vol 9, ISBN **9786258237979**, BKM 180,00 | hibrit (cilt 9 alt-başlığı); ISBN, serinin 9786258237xxx bandında (vol 5 …7030, vol 7 …7436) |
| 14 | Jujutsu Kaisen 1 - Lanet Savaşları | vol 1, ISBN **9786257590341**, BKM 180,00 | hibrit (cilt 1 alt-başlığı); ISBN bandı 9786257590xxx (vol 2 …0501, vol 3 …0709) |
| 15 | Jujutsu Kaisen 0 - Göz Kamaştıran Karanlık | vol 0, ISBN **9786257590303**, BKM 180,00 | **cilt 0 (prequel)**; ISBN sıralaması 0303 → 0341 → 0501 → 0709 = aynı yayıncının 0,1,2,3 bandı |
| 90 | Jujutsu Kaisen - Lanet Savaşları | 22 BOŞ cilt (0-21), 0 listing, slug `jujutsu-kaisen` | boş katalog iskeleti |

**İşlem:** vol 0, 1, 9 (listing'leriyle) seri 4'e taşınır; 5, 14, 15 silinir;
slug `jujutsu-kaisen` 90 → 4; 90 silinir.
**Güven:** YÜKSEK (3/3 ISBN bandı + yayıncı eşleşmesi).
**Sonuç:** seri 4 = 18 cilt, 22 listing, 22 price-history.

## Küme 2 — Naruto (Gerekli Şeyler)

| Seri | Başlık | Durum | Kanıt |
|---|---|---|---|
| **6** (survivor) | Naruto | 62 cilt, slug `naruto`, cilt 28/29 BOŞ (ISBN'siz) | asıl seri |
| 19 | Naruto - Naruto'nun Dönüşü | vol 28, ISBN **9786059141574**, 3 listing (BKM/Kitapsepeti/Kitapsec) | hibrit (cilt 28 alt-başlığı); ISBN, serinin 9786059141xxx bandında (vol 20-27) |
| 20 | Naruto - Kakaşi İtaçi`ye Karşı | vol 29, ISBN **9786059141796**, 3 listing | hibrit (cilt 29 alt-başlığı); aynı bant |
| 21 | Naruto Felsefesi (Teras Kitap) | vol -1, ISBN 9786259983516, 2 listing | **AYRI KİTAP** — farklı yayıncı, farklı ISBN bandı → **dokunulmaz** |

**İşlem:** vol 28 ve 29 (listing'leriyle) seri 6'nın boş cilt 28/29 slotlarına
taşınır, ISBN'ler 6'ya backfill; 19, 20 silinir.
**Güven:** YÜKSEK. **Sonuç:** seri 6 = 64 cilt, 148 listing, 148 history.

## Küme 3 — Kara Meşale (Athica)

| Seri | Başlık | Durum |
|---|---|---|
| 343 | Kara Meşale | 3 BOŞ cilt, slug `black-torch` |
| **2145** (survivor) | Black Torch - Kara Meşale | vol 1, ISBN 9786258502725, BKM 162,50 |

**İşlem:** slug `black-torch` 343 → 2145; 2145 başlığı **"Kara Meşale"**; 343 silinir.
(Hiçbir listing hareketi yok — veri zaten 2145'te.) **Güven:** YÜKSEK.

## Küme 4 — Vinland Saga TR (Kurukafa)

| Seri | Başlık | Durum |
|---|---|---|
| 106 | Vinland Destanı | 11 BOŞ cilt, slug `vinland-saga` |
| **2157** (survivor) | Vinland Saga - Vinland Destanı | 11 cilt (ISBN'li), **55 listing**, 55 history |
| 2158 | Vinland Saga (Kodansha) | **İngilizce baskı — dokunulmaz** |
| 2159 | Vinland Saga, Book (Kodansha) | **İngilizce baskı — dokunulmaz** |

**İşlem:** slug `vinland-saga` 106 → 2157; 2157 başlığı **"Vinland Destanı"**;
106 silinir (11 boş cilt satırı). **Güven:** YÜKSEK (yayıncı aynı: "Kurukafa"
v. "Kurukafa Yayınevi" — bilinen yazım varyantı; cilt sayıları birebir örtüşüyor).

## Küme 5 — Orange TR (Komikşeyler)

| Seri | Başlık | Durum |
|---|---|---|
| 150 | Orange - Portakal | 7 BOŞ cilt, slug `orange` |
| **1851** (survivor) | Orange | 7 cilt (vol 1 ISBN'siz), 34 listing |
| 1874 | Orange (Komik Şeyler) | vol 1 (GS 224,00) + vol 4 (GS 224,00), ISBN'siz |
| 1886 | Orange (Bilinmiyor) | vol 1, ISBN **9786052115442**, Komikşeyler 196,00 |
| 1853 | Orange Novel | **roman — dokunulmaz** (ISBN bandı 97862564493xx, manga 9786052115xxx) |
| 1875 | Orange - To You, Dear One (Seven Seas) | **İngilizce — dokunulmaz** |
| 1879 | Orange: Future (Seven Seas) | **farklı seri (spin-off), İngilizce — dokunulmaz** |

**İşlem:** 1874'ün vol 1 + vol 4 listing'leri ve 1886'nın vol 1 listing'i
1851'in aynı ciltlerine eklenir (store'lar farklı: 1851 vol 1'de yalnız GS
yoktu → 3 yeni listing); 1851 vol 1 ISBN'i ← **9786052115442**;
slug `orange` 150 → 1851; 150, 1874, 1886 silinir.
**Örtüşme kontrolü:** (store, url) bazında 3/3 temiz. **Güven:** YÜKSEK
(tüm ISBN'ler 9786052115xxx = Komikşeyler bandı: 5442, 5480, 5541 sıralı).

## Küme 6 — Paradise Kiss (1593)

2 cilt (ISBN 9786052115947/5886), 2 listing, yayıncı **Bilinmiyor**.
DB'de başka Paradise Kiss serisi **yok** → birleşecek hedef yok, **dokunulmaz**.
İsteğe bağlı (onay bekliyor): ISBN bandı 9786052115xxx Komikşeyler'e ait
(Orange vol 1/2/3 aynı bantta) → yayıncı **Komikşeyler Yayıncılık** atanabilir.

## Toplam etki (GERÇEK — uygulama sonrası ölçüldü)

Üç anlık kesit (yedek dosyalarından):

| | bak-task2<br>(merge öncesi) | bak-task2b<br>(import sonrası, takip öncesi) | şimdi |
|---|---|---|---|
| Seri | 2063 | 2279 | **2276** |
| Cilt | 4182 | 4399 | **4385** |
| Listing | 3080 | 3424 | **3422** |
| Price history | 3119 | 3468 | **3468** |
| catalog_series | 470 | 469 | **469** |

Satır satır izleme:
* **Ana merge** (bak-task2 → sonraki an): seri −11 (5,14,15,90,19,20,343,106,
  150,1874,1886); listing **kayıpsız** (3080); history **kayıpsız** (3119);
  1 yetim catalog satırı silindi (470 → 469); 4 slug taşındı.
* **Import dalgası** (doğrulama curl'leri): seri +227, listing +344,
  history +349, 3 duplikat seri doğdu. (Bknz. "Kapsam dışı gözlemler".)
* **Takip merge** (bak-task2b → şimdi): seri −3 (2212,2389,2357);
  listing **−2** (yalnızca 2389'daki 2 BİREBİR duplike); history **kayıpsız**
  (3468).

**Net veri kaybı: SIFIR** (listing'lerdeki tek düşüş, aynı mağaza+URL+fiyatla
iki kez sayılan duplike satırların birleştirilmesidir).

## Kapsam dışı gözlemler (gelecek geçişin kapsamı — onay: "sonraki geçiş")

### 1) Doğrulama import dalgası (2026-09-14, YENİ)

Doğrulama arama-tetikli import'lar (import_records 24/25/26) **227 yeni seri**
açtı (id 2207-2433). Çoğu `kara` önek sorgusunun BKM'den çektiği **manga
dışı kitap** (KPSS/MEB soru bankaları, motivasyon, çocuk kitabı, genel
edebiyat) — bunlar app amacının dışında. Manga/manga-benzeri olanlar
(Karakarga Türk çizgi romanları, Miraculous Chibi, Spider-Man Noir,
Batman, Low, İmge Vinland baskısı 2207, Viz JJK 2208/2209, guidebook/roman
2210/2211/2213, Yan Karakter 2215/2216/2218) ayrı değerlendirilmeli.

**Kök neden (bilinen, ertelenen sorun):** yayıncı yazım varyantları —
`Gerekli Şeyler` v. `Gerekli Şeyler Yayıncılık`, `Komik Şeyler` v.
`Komikşeyler Yayıncılık`, `Kurukafa` v. `Kurukafa Yayınevi` — import
eşleştirmesini kaçırıyor, yeni seri + yeni yayıncı satırı açıyor. Bu, aynı
sınıftaki varyantların (Akılçelen 668/633/670) birleşimini de gerektirir.

**Önerilen sonraki geçiş:** (a) 227 serinin sınıflandırılması
(manga/manga-benzeri = kal, manga-dışı = sil — listing'leriyle birlikte,
kullanıcı onaylı listeyle); (b) yayıncı varyantlarının birleştirilmesi
(matching'in kök nedenini kapatır).

### 2) Önceki taramanın duplikat kümeleri (onaylı kapsam DIŞINDAKİLER)

Genel tarama başka duplikat kümeleri de gösterdi; bunlara **bu işlemden
dokunulmayacak**:

- Manga benzeri adaylar: `buyucu kiz madoka magica` (156/2102),
  `buyucu kiz madoka magica bir isyan oykusu` (287/2100),
  `buyucu kiz madoka magica hayaletlerin ayaklanisi` (210/2101),
  `frieren beyond journey s end` (619/642), `kizil sacli pamuk prenses`
  (452/831), `blue lock` (103/2149), `berserk` (1/22/326), `one piece`
  (2/1040), `naruto` (6/932 — 932 Viz İngilizce, muhtemelen ayrı kalsın),
  `beyblade` (241/524, 0 listing), `tomie` (132/292, 0 listing)
- Çoğunluk manga DEĞİL kitap (Sherlock Holmes varyantları, romantik roman,
  soru bankası, "la vache orange" vb.) — bunlar için ayrı bir politika
  kararı gerekir (manga uygulamasında neden varlar?).
