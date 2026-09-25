# Görev 1 — Ortak manga/kitap ilgili-filtresi (merch filtresi)

Tarih: 2026-09-14 · Durum: **TAMAMLANDI, canlı doğrulandı**

## Amaç

Tüm mağaza scraper sonuçlarına **tek, ortak, kanıt-tabanlı** bir "bu ürün
manga/kitap mı?" filtresi eklemek: figür, oyuncak, TCG, blind box, poster,
kırtasiye, aksesuar vb. ürünleri sonuç listesinden düşürmek. Sadece başlık
kelimesine dayalı agresif filtreleme YAPILMADI; ISBN, kategori, ürün tipi ve
mağaza metaverisi birlikte değerlendirildi. İstenen 4 sorgu
(`naruto`, `one piece`, `berserk`, `jujutsu kaisen`) **canlı mağazalarda**
doğrulandı.

## Mimari

- **Yeni modül:** `app/scrapers/relevance.py`
  - `check_manga_relevance(title, publisher, isbn, category) -> RelevanceVerdict`
  - `filter_manga_results(results, stats=...)` — ortak uygulama fonksiyonu
- **Tüm 9 scraper'ın `search()` metoduna** entegre edildi (import hattının
  son halkası; mağaza-özel filter'ların ve koleksiyon/atıl filtrelerin SONRASI):
  `bkm, amazon, dr, kitapsepeti, kitapbulan, gerekliseyler, cizman, kitapsec,
  komikseyler`. Düşülen ürünler `stats["rejected"]["non_manga"]` altında
  sayılır (mevcut diagnostik sözleşmesi ile aynı).
- **ImportService ve catalog manifest mimarisine DOKUNULMADI.**

### Kanıt kuraları (skor tabanlı, eşik = 2)

| Kanıt | Güç |
|---|---|
| Güçlü ürün-tipi token'ı: `figür, figure, statue, blind box, grandista, funko, yumemirize, luminasta, xstellar, tcg, booster, playing cards, poster, oyuncak, plush, şapka, hat, lamp, bloknot, notebook, money bank, t shirt, keychain, piggy bank, …` | tek başına reddeder |
| Başlıkta santimetre ölçüsü (`16cm`, `25 cm`) — hiçbir gerçek kitap başlığında fiziksel ölçü yoktur | tek başına reddeder |
| Oyuncak yayınevi: Banpresto, Good Smile Company, MegaHouse, Kotobukiya, Prime 1, Max Factory, Medicom Toy, Bandai Spirits, Takara Tomy | tek başına reddeder |
| JP ürün kodu (45/49 önfillili, 978'siz 13 haneli) | tek başına reddeder |
| Mağaza kategorisi oyuncak (`oyuncak, hobi, figür, …`) | **anında** reddeder |
| Zayıf token'lar: `kart, puzzle, defter, kupa, maske, action, asorti, chibi, sega` | tek tek asla reddetmez; **bağımsız iki zayıf sinyal** (örn. `kupa` + Sega yayıncısı) reddeder |
| **Kitap kanıtı:** 978-/10 haneli ISBN **veya** kitap kategorisi (`Edebiyat Kitapları` gibi) | zayıf sinyalleri nötrler; **güçlü token'ı asla geçersiz kılmaz** |
| Şüpheli durumda | **ürün KALDIR** (yanlış red, kayıp kitaptan daha kötü) |

Kategori kuralının nedeni: BKM'de bir figürün "Edebiyat Kitapları"
kategorisinde yanlış etiketlendiği görülmüştü → kitap kategorisi "anında
kabul" değil, **kitap kanıtı** (sadece zayıf sinyali nötrler).

### Bilinçli yanlış-pozitif korumaları (gerçek kitaplar)

- `Ölüm Defteri 1/2` (Death Note TR), `Maske`, `Kart`, `Puzzle`,
  `Kupa Şampiyonu` — zayıf token tek başına reddetmez, 978 ISBN ile nötrlenir.
- `Hatsune Miku Songbook 1` — `hat` token'ı kelime-sınırına bağlıdır
  (`hatsune` ≠ `hat`).
- `Berserk of Gluttony (Manga) Vol. 8`, `BERSERK TP VOL 01 BLACK SWORDSMAN`,
  `Jujutsu Kaisen: The Official Anime Guide: Season 1`,
  `Jujutsu Kaisen: Thorny Road at Dawn (Novels)`, `One Piece: Güç Dersleri`,
  `Naruto 5 Düellocular`, `Savaşçının Açlığı 3` — spin-off/antoloji/guidebook
  kitaplar korunur.
- `Naruto Felsefesi` (Teras Kitap) — Naruto serisiyle aynı iş değil, korunur.

## Testler (359/359 yeşil)

| Dosya | Test | Açıklama |
|---|---|---|
| `tests/test_merch_filter.py` | **76** | 32 gerçek gözlenen merch (reddedilmeli) + 32 gerçek kitap (kabul edilmeli, tuzağa dahil) + 12 kanıt-birleşim kenar testi |
| 9 mağaza test dosyası | **9** | Her mağazaya "Grandista enjeksiyonu" wiring testi: mağaza yerel listesinde OLMAYAN güçlü ortak token ile üretilen sahte ürün, **sadece ortak katman** tarafından reddedilebildiği için wiring'i kanıtlar. Gerçek kitapların kaybolmadığı da ayrıca assert edilir. |
| geri kalan dizi | 274 | R4 öncesi baz, hiç dokunulmadı, aynı kalır |

Wiring testinin BKM varyantı ayrıca yeni kategori kuralını da kanıtlar:
`"One Piece 55. Cilt Grandista"` + `Edebiyat Kitapları` kategorisi → **red**
(kitap kategorisi güçlü token'ı kurtarmaz).

## Canlı doğrulama (canlı mağazalara 2 tur)

`backend/verify_live_merch_filter.py` — 9 mağaza × 4 sorgu, gerçek istek.

**Tur 1 (ilk sürüm):** 4 sorgunun sonuçlarında **11 gerçek sızıntı** bulundu:

- cizman: `Funko Pop … Kaido … 25cm`, `One Piece T-Shirt`
- gerekliseyler: `Straw Hat [Hasır Şapka]`, `Replica Hat`, `A5 Notebook`,
  `Lamp - Skull`, `Money Bank` + 7× `Luminasta`, `Yumemirize (SEGA)`,
  `XStellar` figür serileri
- kitapbulan/kitapsec/kitapsepeti: `Jujutsu Kaisen Bloknot`

→ Token listesi genişletildi (`funko, t shirt, şapka, hat, lamp, bloknot,
notebook, money bank, yumemirize, luminasta, xstellar` + cm ölçüsü kuralı +
Sega zayıf sinyali), her biri ünite testine **gerçek başlık olarak** eklendi.

**Tur 2 (son sürüm):** `TOTAL FLAGGED: 0` — 4 sorgunun **hepsinde**,
yanıt veren her mağazada (bkm, cizman, gerekliseyler, kitapbulan, kitapsec,
kitapsepeti) sonuç listeleri **yalnızca kitap** içerdi.

- cizman `one piece`: 3 sonuç → **1** (sadece `One Piece 107 (Japanese Edition)`);
  Funko Pop ve T-Shirt `non_manga: 2` olarak düştü.
- gerekliseyler `jujutsu kaisen`: 34 → **24** (10 figür serisi düştü);
  guidebook/roman kitaplar kaldı.
- `Berserk of Gluttony (Manga) Vol. 8`, `BERSERK TP VOL 01` vb. gerçek
  kitaplar **kaybolmadı** (Tur 1'de var olan her kitap Tur 2'de de var).
- amazon (503) ve D&R (403) hâlâ bot-çita ile engelli — bilinen durum,
  kapsam dışı (bypass reddedilmişti); bu iki mağazanın wiring'i fixture
  testleriyle kanıtlandı.

## Değişen dosyalar

- `app/scrapers/relevance.py` (YENİ)
- `app/scrapers/{bkm,amazon,dr,kitapsepeti,kitapbulan,gerekliseyler,cizman,kitapsec,komikseyler}.py` (9× `search()` içine 1-2 satır entegrasyon)
- `tests/test_merch_filter.py` (YENİ, 76 test)
- 9 mağaza test dosyasına wiring testi eklendi
- `backend/verify_live_merch_filter.py` (YENİ, canlı doğrulama betiği —
  tests/ dışıdır çünkü ağa gerçek istek atar)

## Bilinen sınırlar

- Filtre, scraper çıktısını daraltır; **veritabanındaki ESKİ** merch kayıtları
  bu görevin konusu değildir (Görev 2 kapsamı: hibrit/merch kayıtlarının
  denetimi ve temizliği).
- Mağaza yerel filter'ları (ör. cizman'ın `irrelevant` kapısı) değiştirilmedi;
  ortak filtre onların yanında, son katman olarak çalışır.
