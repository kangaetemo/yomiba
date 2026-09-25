# Yomiba — "Son indirimler" özelliği + çoklu baskı düzeltmesi

Bu paket 2 şey içerir:

1. **🔥 Son indirimler** — ana ekranda son 24 saatte *gözlenen* fiyat
   düşüşleri (kapak + mağaza + eski→yeni fiyat + % + "2 saat önce").
2. **Çoklu baskı düzeltmesi (öncelemeli!)** — bazı kitapçılar aynı cildi
   farklı ISBN'li iki baskı olarak satıyor (örn. BKM'de "Titana Saldırısı:
   Çöküşten Önce 3" → 201,60 ₺ ve 180,00 ₺). Eski kod her kontrolde fiyatı
   bu iki değer arasında sallandırıp **sahte fiyat geçmişi ve sahte indirim**
   üretiyordu. Artık her (cilt × mağaza) için **en ucuz baskı kazanır**;
   fiyatlar kararlıdır ve indirim şeridi gerçek düşüşleri gösterir.

## Kurulum (2 dakika)

1. Bu zip'i PC'ndeki `C:\yomiba` klasörünün **üstüne** çıkar (dosyalar
   mevcut dosyaların üzerine yazılsın — 3 dosya güncelleniyor, 4 dosya yeni).
2. **Yomiba API** penceresini kapat, aynı pencerede tekrar başlat:
   ```
   cd C:\yomiba\backend
   set CATALOG_SYNC_INTERVAL_HOURS=12
   set PRICE_REFRESH_INTERVAL_HOURS=24
   set IMPORT_MAX_CONCURRENT_JOBS=8
   .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
   ```
   (veya `run-local.bat`'i yeniden çalıştır — yeni dosyaları fark etmez,
   sadece iki servis penceresini kapatıp yeniden başlatman yeterli)
3. **Yomiba Web** penceresini kapatıp aç (`npm run dev`) — veya sadece
   tarayıcıdan yenile (Next.js dev, dosya değişikliklerini otomatik alır).

Bitir. Ana sayfada arama kutusunun altında "🔥 Son indirimler" görünür.

## Doğrulama (isteğe bağlı)

- API penceresinde "keeping the cheapest" satırı → çoklu baskı koruması
  devrededir demektir.
- `http://127.0.0.1:8000/price-drops?hours=168` → ham indirim listesi.
- Test (Python + venv hazırsa): `cd backend && .venv\Scripts\python -m pytest -q`
  → **424/424** geçmeli.

## Not: eski sahte indirimler

Düzeltmeden önceki ısıtmalarda oluşmuş sahte fiyat geçmişi (201,60↔180,00
sallanmaları) veritabanında durmaya devam eder; indirim şeridi 24 saatlik
pencere kullandığı için bu eski sahte kayıtlar **en geç 24 saat içinde
kendi kendine kaybolur**. Bundan sonra yenisinin oluşması engellendi.
(Dilediğin gün bunları tarihsel olarak da temizleriz — ayrı onay ister.)
