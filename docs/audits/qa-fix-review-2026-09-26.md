# QA fix pass — bağımsız kontrol (2026-09-26)

Mevcut working tree incelendi. Uygulama kodu değiştirilmedi; commit/push/deploy, gerçek DB write/migration/cleanup yapılmadı. Aşağıdaki iki hata sadece bellekteki SQLite verisiyle yeniden üretildi.

## P1 — Catalog title fallback katalog sınırını atlıyor

Konum: `backend/app/services/import_service.py:414` ve `:607`.

Normal `_resolve_target` ISBN sahibinin CatalogSeries'e bağlı olduğunu kontrol ediyor. Ancak `parsed.is_collection` yolu doğrudan `_catalog_title_fallback` çağırıyor. Fallback negatif ISBN sahibini ayıklıyor; pozitif ISBN sahibinin katalogda olduğunu kontrol etmiyor. `_resolve_volume` da bulunan ISBN sahibini koşulsuz döndürüyor.

Tekrar üretim: katalogda Mavi Kutu 1–2, katalog dışında Disarida 1 oluşturuldu; dışarıdaki cilde ISBN 9786258237559 verildi. `Mavi Kutu 1` adlı ürün bu ISBN ile import edildi. Sonuç `ImportAction.CREATED`; listing katalogdaki Mavi Kutu yerine katalog dışındaki Volume 3'e yazıldı.

Öneri: Bütün ISBN çözümleme girişlerinde aynı catalog membership kontrolünü koru. ISBN önceliğini değiştirmek gerekmiyor. Erken collection/fallback yolu için katalog dışı pozitif ISBN regression testi gerekli.

## P2 — Stoksuz ucuz ürün A↔B fiyat geçmişi döngüsünü sürdürüyor

Konum: `backend/app/services/import_service.py:652`, özellikle fiyat karşılaştırması ve `:722` sonrası history yazımı.

`_may_switch_product`, daha ucuz ürünün stokta olmasını şart koşmuyor. Stokta A=100 TL → stokta olmayan B=90 TL fiyat gerekçesiyle kabul ediliyor. Sonraki A, mevcut B stoksuz olduğu için kabul ediliyor. Bu tekrar edebiliyor.

Tekrar üretim: aynı mağaza/cilt için A,B,A,B,A sıralaması. Sonuç CREATED, UPDATED, UPDATED, UPDATED, UPDATED; PriceHistory kuruş değerleri `[10000, 9000, 10000, 9000, 10000]`. Hiçbir ürünün kendi fiyatı değişmedi. Ara adımda mevcut stoklu teklif de görünmez oluyor.

Öneri: Stok/fiyat tercih sırasını tutarlı hale getir; stoklu alternatif varken ucuz stoksuz ürünün onu devralmasını önle. Karışık stok durumlu tekrar import regression testi ekle.

## WARNING — Auth fallback framework kontrol sinyalini logluyor

`frontend/services/auth.ts:21` içindeki genel catch, build sırasında Next.js'in `DYNAMIC_SERVER_USAGE` kontrol sinyalini de yakalayıp `currentUser failed` olarak yazıyor. Build exit code 0; rotalar dinamik olarak üretildi. Bu çalışmada gerçek runtime sayfa çökmesi gözlenmedi. Gerçek backend hatalarıyla framework kontrol sinyallerinin ayrılması önerilir.

## Bağımsız doğrulama sonuçları

- Backend full suite: **581 passed, 44 warnings**, 75.64 saniye. `DATABASE_URL=sqlite:///:memory:`; pytest fixture'ları geçici DB kullanıyor. Cache yazımı kapalı.
- Frontend typecheck: PASS (`tsc --noEmit --incremental false`).
- Frontend lint: PASS.
- Frontend production build: PASS; yukarıdaki log uyarıları mevcut.
- İki ilave bellek içi repro: yukarıdaki iki hatayı doğruladı; bunlar mevcut 581 testin kapsamadığı senaryolar.
- Canlı staging import / runtime smoke bu QA kontrolünde yeniden çalıştırılmadı.

Sonuç: Test sayısı ve build iddiası doğrulandı; iki correctness sorunu nedeniyle bu working tree için henüz deploy onayı önerilmiyor.
