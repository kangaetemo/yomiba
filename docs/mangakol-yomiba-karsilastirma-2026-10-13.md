# Mangakol–Yomiba katalog karşılaştırması — 13 Ekim 2026

## Kapsam ve doğrulama

- Kaynak: kullanıcı tarafından indirilen `mangakol-yomiba-karsilastirma.json`; Yomiba sunucusundaki salt okunur karşılaştırma aracının çıktısı.
- Tarama: **13 Ekim 2026, 22:18:51–22:44:26 (Europe/Istanbul)**. DB görüntüsü başlangıçta alınmıştır; sonuçlar bu görüntüye aittir, sonraki canlı değişiklikleri temsil ettiği varsayılmaz.
- **473/473 ana seri**, 22 ek baskıyla **495 seri/baskı kaydı**, **2.399 cilt künyesi**. `complete=true`, liste tam, kaynak hatası 0, künye hatası 0, `applied=false`.
- Dizi uzunlukları, fark sayıları, kaynak ve DB katalog kimliklerinin eşitliği ayrıca yeniden hesaplanıp doğrulandı.
- Karşılaştırma kamuya açık Mangakol kataloğu ile Yomiba DB görüntüsü arasındadır; Mangakol sunucusunun ham SQL veritabanına erişildiği iddia edilmiyor.
- Ham rapor SHA-256: `8cad451c0f80d9d49d919c7306becebbd867cca0d9ab2ddf6fe6ab02333ef38f`. Kullanıcı hesapları/oturumları ve koleksiyon satırları rapora dahil değildir.

## Genel sonuç

| Ölçüt | Sonuç |
|---|---:|
| Kaynakta eşleşen seri/baskı | 495 |
| Eksik/fazla seri, belirsiz seri kimliği | 0 |
| Kaynakta olup DB’de eksik cilt | 0 |
| DB’de toplam korunan cilt satırı | 2.470 |
| DB görüntüsünde kamuya açık cilt | 2.456 |
| Kaynakta kayıtlı cilt | 2.399 |
| Kaynakta yayımlanmış cilt | 2.352 |
| Kaynakta “Yakında” cildi | 47 |
| Kaynakta olmayan, görünür fazla satır | 57 |
| Zaten gizli eski numarasız satır | 14 |
| ISBN farkı | 23 |
| Sayfa sayısı farkı | 7 |
| Yerel çıkış tarihi farkı | 7 |

Yayınevi, normalize seri adı ve omnibus kapsamı karşılaştırma ölçütlerinde ek fark raporlanmadı. Bu, sayılan ölçütler için bir sonuçtur; bütün olası katalog alanlarının doğrulandığı anlamına gelmez.

## Görünür fazla ciltler

| Seri | Yomiba’da görünür kayıt | Mangakol kaydı | Fazla kayıt | Fazla numaralar |
|---|---:|---:|---:|---|
| Fairy Tail | 52 | 22 | 30 | 23, 24, 25, 26, 27, 28, 38, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63 |
| Nana | 20 | 7 | 13 | 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 |
| Beastars | 20 | 8 | 12 | 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20 |
| Black Lagoon | 6 | 5 | 1 | 9 |
| City | 2 | 1 | 1 | Numarasız (-1) |

**Fairy Tail:** Kaynakta 1–21 yayımlanmış, 22 “Yakında”. Yomiba’da 52 görünür kayıt bulunuyor ve numaralar 63’e kadar çıkıyor. 23 ve sonrasındaki 30 fazla kayıt silinmeden katalog görünümünden ayrılmalı. Doğru sunum: **21 yayımlanmış + 1 yakında**.

Nana’nın DB’deki 21 satırının biri zaten gizli numarasız kayıttır; görünür sayı 20, fazla görünür sayı 13’tür. City’deki fazla satır da numarasızdır. 57 fazla satırın tamamında ISBN boş. ISBN boşluğu tek başına kaldırma kanıtı değildir; buradaki kanıt eksiksiz kaynak listesinde bulunmamalarıdır.

## Yayın durumları ve köken değerlendirmesi

- DB görüntüsündeki **2.470 satırın tamamında `catalog_released=None`**. Kaynakla eşleşen 2.399 cilt için rapor bu yüzden `release_unverified` yazıyor. Bu, 2.399 cildin yanlış olduğu anlamına gelmez; yeni durum alanının veriyle doldurulmadığını gösterir.
- “Yakında” görünen **47 cilt, 38 seriye** yayılıyor; hepsinin yerel çıkış tarihi de yok. Normal yayımlanmış cilt sayısından ayrılmaları gerekir. Tarihi belli duyuruların korunması kuralı bu 47 kaydı açıklamıyor.
- Salt okunur karşılaştırma bir senkron işlemi değildir; yayın durumlarını doldurmadı ve fazla kayıtları pasifleştirmedi.
- Kod incelemesi: güncel `ImportService._resolve_volume` bulunmayan bir cilt için yeni satır yaratmıyor, `volume_not_found` döndürüyor. Fazla satırlar eski aktarımla tutarlıdır; rapor bunları hangi mağazanın/hangi tarihte yarattığını kanıtlamaz.
- Güncel `_upsert_listing`, kaynakta `False` olan cilde teklif yazmıyor; `None` kalan eski satırların görünürlüğü başarılı katalog doğrulamasını bekliyor.
- Tam kaynaktan sonra mevcut senkron kodu olmayan ciltleri `False` yapabilir. Bu işlem uygulanmadan, kullanıcı satırları/fiyat geçmişi korunmalı ve kaynak ISBN çakışmalarının etkisi incelenmeli.

### “Yakında” olup görünür kalanlar

| Seri | Ciltler |
|---|---|
| Jujutsu Kaisen - Lanet Savaşları | 21 |
| Berserk | 20 |
| Testere Adam | 18 |
| Tokyo İntikamcıları | 19 |
| Gecenin Çağrısı | 7 |
| Sakamoto Günleri | 7 |
| Tuvalet Hayaleti Hanako-Kun | 16 |
| Parazit | 8 |
| Oşi No Ko: Seçtiğim Yıldız | 13 |
| Kaiju No: 8 - 8 No'lu Canavar | 9 |
| Happiness | 9 |
| Made in Abyss | 11 |
| Mashle | 8 |
| Vatansever Moriarty | 6 |
| Erased | 3 |
| Fairy Tail | 22 |
| Kobayaşi Hanesi'nin Hizmetçi Ejderhası | 3, 4 |
| Kuroko'nun Basketbolu | 23 |
| Pandora Hearts | 4 |
| Beni Ay'a Götür | 6 |
| Akira | 4 |
| Toradora! | 4 |
| ReLIFE | 3 |
| Kamisama Kiss -Tanrılık Görevine Başladım | 9 |
| Dr. Stone | 2 |
| Blend.S | 5 |
| Mavi Kutu | 5 |
| İlk Aşkım Sensin | 2 |
| Eternal Sabbath | 2 |
| Yeni Geçit | 7 |
| Maid-Sama: Başkan Aslında Bir Hizmetçi! | 3 |
| Kralın Oyunu: Başlangıç | 3, 4, 5, 6 |
| Minecraft: Dünyanın Sonu'na Yolculuk | 3 |
| Ormanda Perişan Hâlde Bulduğum Bir Genç Kıza Yaramazlık Dersleri Veriyorum: Güzel Yemekler Yedirip, Güzel Giysiler Giydirip, Onu Dünyanın En Mutlu Kızı Yapacağım! | 6 |
| Yubooh Uyurken | 3, 4, 5 |
| JoJo's Bizarre Adventure Part 1: Phantom Blood | 1, 2, 3 |
| Dük ile İlk Gecem | 2, 3 |
| Astra Uzak Gezegenlerde | 2 |

## ISBN farkları: otomatik ezme yapılmamalı

23 farkın **12’si DB’de boş olan ISBN**, **11’i iki farklı, dolu ISBN**. Bunlar aynı tür hata değildir.

Kaynak ISBN’lerinden **11 tanesi birden fazla cilt/baskıda** görünüyor. Bu tekrarlar 23 ISBN farkının **12’sini** etkiliyor. Aynı cilt numarasındaki özel baskılar ortak ISBN kullanabilir; farklı cilt numaraları veya farklı eserler arasındaki tekrarlar ayrıca doğrulanmalı. Bütün kaynak ISBN’lerinin kontrol basamağı geçerli; bu, hangi kitaba ait olduklarını kanıtlamaz.

Örnekler: Blue Lock 28/29, Happiness 5/6 ve Omniscient Reader’s Viewpoint 3/4 için kaynak aynı ISBN’i tekrar ediyor. Yıldızların Sesi ile Canım Kızım’da da aynı ISBN görünüyor. Kaynakta gördüğümüz her ISBN’i doğru kabul edip DB’ye kopyalamak fiyat eşleştirmesini bozabilir.

| Seri / cilt | Yomiba ISBN | Kaynak ISBN | Kaynak içi tekrar |
|---|---|---|---|
| One Piece · 62 | Boş | 9786258657531 | Yok |
| Naruto · 62 | Boş | 9786258657562 | Yok |
| Blue Lock · 29 | 9786258630633 | 9786258630626 | Var |
| Kahramanlık Akademim · 33 | Boş | 9786258657517 | Yok |
| Dandadan · 8 | Boş | 9786258657579 | Yok |
| Haikyu!! · 22 | Boş | 9786258657500 | Yok |
| Solo Leveling · 2 | 9786256449459 | 9786256449671 | Yok |
| Solo Leveling · 7 | Boş | 9786255607775 | Var |
| Solo Leveling (Limitli Baskı) · 5 | Boş | 9786255607782 | Var |
| Afro Samuray (Limitli Baskı) · 1 | Boş | 9786057144522 | Var |
| Happiness · 6 | 9786259324050 | 9786259360492 | Var |
| Nana · 7 | Boş | 9786256327740 | Yok |
| Omniscient Reader’s Viewpoint · 3 | 9786258630442 | 9786258630176 | Var |
| Omniscient Reader’s Viewpoint · 4 | 9786258630350 | 9786258630176 | Var |
| Omniscient Reader’s Viewpoint (Varyant Kapak) · 4 | Boş | 9786258630145 | Var |
| Skip and Loafer · 4 | 9786259324036 | 9786259667294 | Var |
| Huzurlu Kamp · 3 | 9786259324067 | 9786259727080 | Var |
| Vampir Şövalye · 6 | 9786055381448 | 9786055381431 | Var |
| Yıldızların Sesi · 1 | Boş | 9786255607850 | Var |
| İskelet Ejderin Küçük Kızı · 3 | Boş | 9786259087849 | Yok |
| Komünist Manifesto · 1 | 9789944122801 | 9786055541583 | Yok |
| Alacakaranlık · 1 | 9789944821094 | 9789944822633 | Yok |
| Kapital · 2 | 9786055541781 | 9789944122962 | Yok |

### Tekrarlanan kaynak ISBN’leri

| ISBN | Kaynak kayıtları |
|---|---|
| 9786258630626 | Blue Lock · 28; Blue Lock · 29 |
| 9786255607775 | Solo Leveling · 5; Solo Leveling · 7 |
| 9786255607782 | Solo Leveling (Limitli Baskı) · 5; Solo Leveling (Varyant Kapak) · 5 |
| 9786057144522 | Afro Samuray · 1; Afro Samuray (Limitli Baskı) · 1 |
| 9786259360492 | Happiness · 5; Happiness · 6 |
| 9786258630145 | Omniscient Reader’s Viewpoint · 1; Omniscient Reader’s Viewpoint (Varyant Kapak) · 4 |
| 9786258630176 | Omniscient Reader’s Viewpoint · 3; Omniscient Reader’s Viewpoint · 4; Omniscient Reader’s Viewpoint (Varyant Kapak) · 2 |
| 9786259667294 | Skip and Loafer · 3; Skip and Loafer · 4 |
| 9786259727080 | Huzurlu Kamp · 2; Huzurlu Kamp · 3 |
| 9786055381431 | Vampir Şövalye · 5; Vampir Şövalye · 6 |
| 9786255607850 | Yıldızların Sesi · 1; Canım Kızım · 1 |

## Yeni künye bilgileri

Sayfa sayısı ve tarih farklarının **yedisinde de DB alanları boş**; kaynak tarihi 13 Ekim 2026. Bunlar eski dolu tarihlerin değiştirilmesi değil, yeni yayımlanmış ciltlerin henüz işlenmemiş bilgileridir. Bu yedi kaydın kaynak ISBN’leri kaynak içinde tekil, başlangıç DB görüntüsünde başka cildin üzerinde bulunmuyor.

| Seri / cilt | ISBN | Sayfa | Yerel çıkış |
|---|---|---:|---|
| One Piece · 62 | 9786258657531 | 216 | 2026-10-13 |
| Naruto · 62 | 9786258657562 | 200 | 2026-10-13 |
| Kahramanlık Akademim · 33 | 9786258657517 | 192 | 2026-10-13 |
| Dandadan · 8 | 9786258657579 | 200 | 2026-10-13 |
| Haikyu!! · 22 | 9786258657500 | 192 | 2026-10-13 |
| Nana · 7 | 9786256327740 | 200 | 2026-10-13 |
| İskelet Ejderin Küçük Kızı · 3 | 9786259087849 | 176 | 2026-10-13 |

## 13 Ekim başlangıç uygulama planı

1. **Önce görünürlük:** 57 kaynak dışı kaydı ve 47 tarihsiz duyuruyu yayımlanmış cilt görünümünden ayır; satırları, fiyat geçmişini ve kişisel kayıtları koru. Jujutsu Kaisen 0 gibi gerçek cilt 0 kayıtlarını koru.
2. **Yayın durumu:** Kaynakla eşleşen 2.399 cilt için kaynak durumunu işle; `None` ile “Yakında” aynı şey değildir.
3. **Yeni bilgiler:** Yukarıdaki yedi yeni künyeyi ve çakışmasız boş alanları kontrollü doldur.
4. **ISBN incelemesi:** Dolu ISBN farklarını ve kaynakta tekrarlanan ISBN’leri yayınevi/ürün barkodu kanıtıyla ayır; körlemesine güncelleme yapma. Meşru ortak ISBN’li özel baskılar ayrı tutulmalı.
5. **Canlı doğrulama:** Fairy Tail 21 yayımlanmış + 1 yakında; Nana 7, Beastars 8 ve diğer düzeltilen serileri yeniden karşılaştır. Aynı eski satırlar mağaza taramasında yeniden görünür hale gelmemeli.

**13 Ekim rapor anındaki durum:** Tüm katalog karşılaştırması ve rapor analizi tamamlandı; bu salt okunur tarama veritabanı düzeltmesi uygulamadı.

## 14 Ekim uygulama sonucu

Koruyucu düzeltme yayımlandı ve güncel kaynakla senkron canlıda çalıştı. Başlangıç raporundaki 495 serinin yayımlanmış cilt sayıları tamamen eşleşiyor (2.352 cilt); 38 serideki 47 duyuru ayrı listede, fark yok. Fairy Tail 21 yayımlanmış + 22. cilt yakında; Nana 7, Beastars 8, Black Lagoon 5 ve City 1. Yedi yeni ISBN/sayfa/tarih künyesi tamamlandı. Eski satırlar silinmiyor; fiyat geçmişi ve kişisel referansların korunması DB regresyon testiyle doğrulandı.

Güncel kaynak listesine SEKIRO-Yan Hikâye: Ölümsüz Hanbei eklenmiş: 474 ana seri, 496 seri/baskı, 2.353 yayımlanmış cilt. Bu yeni kayıt, başlangıç raporundaki toplamların değişmesinin doğrulanmış sebebi.

23 başlangıç ISBN farkının yedisi giderildi; kalan 16 fark (canlıda dört boş, 12 dolu ve farklı ISBN) kanıt incelemesine açık. Ortak ISBN kullanan baskılar ve kaynakta yanlış tekrarlanan ISBN'ler otomatik hata sayılmadı. Uygulama, testler ve canlı doğrulamanın kapsamı [14 Ekim çalışma notlarında](yomiba-calisma-notlari.md); açık işler [yapılacaklar listesinde](../yapılacaklar.md).
