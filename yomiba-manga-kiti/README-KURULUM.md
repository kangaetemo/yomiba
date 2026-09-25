# Yomiba — "Sadece Manga" Paketi (18 kitap benzeri girişin temizliği)

2026-09-21 kararı: katalogdaki 18 kitap benzeri giriş (edebiyat uyarlamaları,
oyun romanları, eğitim kitapları) katalogdan çıkarılıyor ve **blok listesine**
alınıyor → 12 saatlik mangakol senkronu bir daha asla geri ekleyemez.

Veri SİLİNMEZ: bu serilere ait cilt/listing/fiyat geçmişi DB'de durur;
yalnızca "katalog kapısı" kapanır (arama, indirim şeridi, warmup ve
zamanlayıcılar onları bir daha işlemez).

## Kurulum (3 adım)

1. Zip'i `C:\yomiba` klasörünün **üstüne** çıkar (8 dosya, 3'ü güncelleniyor).

2. **Yomiba API** penceresini kapat ve yeniden başlat:
   ```
   cd C:\yomiba\backend
   set CATALOG_SYNC_INTERVAL_HOURS=12
   set PRICE_REFRESH_INTERVAL_HOURS=24
   set IMPORT_MAX_CONCURRENT_JOBS=8
   .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
   ```
   (Başlangıçta yeni `catalog_exclusions` tablosu otomatik oluşur.)

3. Temizlik scriptini çalıştır — **önce dry-run** (hiçbir şey yazmaz):
   ```
   .venv\Scripts\python apply_nonmanga_exclusions.py
   ```
   Kravan listeyi ve "korunacak listing" sayılarını gösterir. Uygunsa uygula
   (otomatik yedek alır: `yomiba.db.bak-nonmanga`):
   ```
   .venv\Scripts\python apply_nonmanga_exclusions.py --apply
   ```
   "TAMAM — katalog artık 447 seri" yazmalı.

4. (İsteğe bağlı) Testler: `.venv\Scripts\python -m pytest -q` → **425/425**

Web penceresi değişmez (frontend dokunulmadı) — ama bir yenilemek
fark etmez.

## Kapsam (18 slug)

| Grup | Girişler |
|---|---|
| Edebiyat/felsefe uyarlamaları | Kapital, Komünist Manifesto, Türlerin Kökeni, Savaş ve Barış, İlahi Komedya, Yengeç Gemisi, Kavgam, Ölüm Tınısı, Psi-Kom |
| Oyun/roman uyarlamaları | Warcraft: Efsaneler, Warcraft: Sunwell Üçlemesi, Starcraft: Öncephe, Alacakaranlık |
| Eğitim ("Manga de Wakaru") | Elektrik, Fizik, Görelilik, Moleküler Biyoloji, Matematik |

Sonraki senkronlar bu slug'ları log'da `excluded (non-manga scope); skipped`
olarak atlar. İleride birini geri almak istersen:
`catalog_exclusions` tablosundan o satırı sil + catalog_series satırını geri
ekle (veri zaten DB'de duruyordur).
