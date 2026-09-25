# Yomiba — Yerel Kurulum (Kendi Bilgisayarında Çalıştır)

Manga fiyat karşılaştırma uygulamasının **tamamını kendi bilgisayarında**
çalıştırmak için her şey bu klasörde. Sandbox/hosting gerekmez.

## Gereksinimler (ikisi de ücretsiz)

| Yazılım | Sürüm | Nereden |
|---|---|---|
| Python | **3.11 veya 3.12** | https://python.org (Windows kurulumunda **"Add Python to PATH"** kutusunu işaretle!) |
| Node.js | **18+ (LTS önerilir)** | https://nodejs.org |

Kurduğunu doğrulamak için terminalde:
```
python --version   # Python 3.11.x / 3.12.x
node --version     # v18.x ve üzeri
```

## Kurulum (2 adım)

### Windows
1. Bu klasörü bilgisayarında bir yere aç (ör. `C:\yomiba`)
2. **`run-local.bat`** dosyasına çift tıkla
3. İlk çalıştırmada bağımlılıklar kurulur (~2 dk). İki yeni pencere açılır:
   "Yomiba API" ve "Yomiba Web"

### macOS / Linux
```bash
cd /klasor/un/yeri
bash run-local.sh
```
Aynı şeyi yapar; servisler arka planda çalışır, loglar `/tmp/yomiba-api.log`
ve `/tmp/yomiba-web.log`.

## Kullanım

- **Uygulama:** http://localhost:3000
- **Admin (kapsama + ısıtma butonu):** http://localhost:3000/admin
- **Telefondan (aynı WiFi):** tarayıcıya `http://<bilgisayarın-LAN-IP>:3000`
  - Windows: `ipconfig` → "IPv4 Address"
  - Mac/Linux: `ip addr`

### İlk iş (bir kez)
Admin sayfasında **"Tüm katalogu ısıt"** butonuna bas. ~45 dakika arka
planda 461 serinin fiyatları toplanır; bu sırada uygulamayı kullanmaya
devam edebilirsin. Buton tekrar basılsa da zararsız (çalışan işler
yenilenecek kadar "taze"se anında atlanır).

## Günlük çalışma

- Bilgisayar açıkken:
  - **12 saatte bir** mangakol.com katalog senkronu (yeni manga/ad kontrolü)
  - **24 saatte bir** tüm katalog fiyat tazelemesi (~1 saat arka plan)
  - Her aramanda: veri 60 dakikadan eskiyse o seri o an arka planda tazelenir
- Bilgisayar kapalıyken hiçbir şey çalışmaz; açınca kaldığı yerden devam
  eder (veriler diskte, hiçbir şey kaybolmaz).

## Durdurma

- **Windows:** "Yomiba API" ve "Yomiba Web" pencerelerini kapat
- **macOS/Linux:** `pkill -f 'uvicorn app.main' && pkill -f 'next dev'`

## Veri ve yedek

- Tek veri dosyası: **`backend/yomiba.db`** (~3 MB) — tüm seriler,
  listelemeler, fiyat geçmişi, import kayıtları
- Kurulum scripti ilk çalıştırmada otomatik `yomiba.db.bak-first` yedeği alır
- Öneri: ayda bir `backend/yomiba.db`'i kopyalayıp ayrı bir yere at
  (ya da bulut diske)

## Sık sorular

**"D&R ve Amazon sonuçları neden yok?"**
Bu iki mağaza bazı IP adreslerinden (özellikle veri merkezi IP'leri) erişimi
blokluyor. Ev IP'nden çalışınca açılabilir de, açılmayabilir de; uygulama
diğer 7 mağaza ile tam çalışır.

**"Sandbox'taki halinden farkı ne?"**
Hiçbir şey eksik değil: aynı kod, aynı veriler (219+ serinin fiyatları
dahil). Farkı şu: artık günlük reset yok, zamanlayıcılar gerçekten 12/24
saat döngülerini tamamlar, warmup tek seferde biter.

**"Kodu değiştirmek istersen?"**
`backend/app/...` ve `frontend/app/...` klasörlerinde düz Python/TypeScript
kodu var; normal bir editörle açıp değiştirebilirsin. Backend'de test
çalıştırmak: `cd backend && .venv/bin/python -m pytest -q` (veya Windows'ta
`.venv\Scripts\python -m pytest -q`).
