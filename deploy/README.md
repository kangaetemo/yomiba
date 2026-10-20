# Yomiba — VDS kurulumu (yomiba.net)

Sunucu: Hephosting TRX-8G, Ubuntu 24.04. Yapı: Docker Compose; önde Caddy
(otomatik HTTPS), arkada Next.js (`frontend`) ve FastAPI (`backend`). Dışarı
yalnızca 80/443 açık; backend'e tarayıcı Next'in `/api` yönlendirmesiyle ulaşır.

| Dosya | Görev |
| --- | --- |
| `docker-compose.yml` | Üç servis, log sınırı, `/srv/yomiba/data` → `/data` |
| `Caddyfile` | `yomiba.net` → frontend, `www` → kök alan adına yönlendirme |
| `.env.example` | Sunucudaki `deploy/.env` şablonu (sırlar repoya girmez) |
| `kurulum.sh` | Yeni sunucunun tek seferlik kurulumu |
| `guncelle.sh` | GitHub'daki son sürümü çekip yeniden başlatır |
| `yedekle.sh` | Gece DB yedeği + doğrulama (son 7 yedek) |

Sunucudaki dizinler: `/srv/yomiba/app` (repo), `/srv/yomiba/data` (`yomiba.db`,
`-wal`/`-shm`, `covers/`; sahibi uid 10001), `/srv/yomiba/backups`.

## 1. DNS (Cloudflare)

1. Cloudflare'de `yomiba.net` sitesini ekle (Free), verdiği iki nameserver'ı
   alan adını aldığın firmanın panelinde gir.
2. Kayıtlar, ikisi de **DNS only (gri bulut)**; sertifika alındıktan sonra
   istenirse turuncuya çevrilir (SSL modu *Full (strict)*):
   - `A  yomiba.net  → <sunucu IPv4>`
   - `A  www         → <sunucu IPv4>`
3. Kontrol: `nslookup yomiba.net 1.1.1.1` sunucu IP'sini döndürmeli.

## 2. Sunucuyu hazırla

```sh
ssh root@<sunucu IP>
curl -fsSL https://raw.githubusercontent.com/kangaetemo/yomiba/main/deploy/kurulum.sh -o kurulum.sh
bash kurulum.sh
```

Ardından `/srv/yomiba/app/deploy/.env` dosyasını doldur:
`AUTH_DEVICE_SECRET` (`openssl rand -hex 32`), Google ve SMTP değerleri.
Zamanlayıcılar (`CATALOG_SYNC_ENABLED`, `PRICE_REFRESH_ENABLED`) DB doğrulanana
kadar `0` kalır.

## 3. Mağaza erişim testi (DB'den önce)

Türkiye IP'sinden hangi mağazaların açıldığını görmek için, DB gerekmeden:

```sh
cd /srv/yomiba/app/deploy
docker compose build backend
docker compose run --rm --no-deps -e APP_ENV=development backend python outbound_smoke.py
```

`BLOCKED` çıkmayan mağazalar `DISABLED_STORES` listesinden çıkarılabilir
(Railway'de Amazon, D&R ve Cizman engelliydi).

## 4. DB ve kapakları Railway'den taşı

Sunucuda bir kez: Railway CLI (`curl -fsSL https://railway.com/install.sh | sh`),
`railway login --browserless`, `/root` içinde `railway link` (canlı backend
servisi) ve `ssh-keygen -t ed25519` (ilk `railway ssh` anahtarı hesaba ekler).
Sonra backend durdurulmuşken:

```sh
cd /srv/yomiba/app/deploy && docker compose down
./railway-tasima.sh
```

Betik Railway volume'una hiçbir şey yazmaz (volume dolunca site çöküyor):
çevrimiçi yedeği ve kapak arşivini konteynerin `/tmp`'sinde hazırlar, base64
ile çeker, sha256 ile karşılaştırır, `/tmp`'yi temizler. DB `yomiba.db` adıyla
yerleşir; yanındaki `catalog-state.json` / `isbn-safety.json` da yeniden
adlandırılır. Sunucuda var olan bir `yomiba.db` veya `covers/` varsa durur.

Son aktarımdan önce Railway'deki zamanlayıcılar kapatılırsa aradaki fiyat
yazımları kaybolmaz; hesap/koleksiyon değişikliği yapılmamalı.

## 5. Başlat ve doğrula

```sh
cd /srv/yomiba/app/deploy
docker compose up -d --build
docker compose ps                 # backend: healthy
docker compose logs -f backend    # DB hedefi /data/yomiba.db, migration head, ready
curl -I https://yomiba.net        # 200, geçerli sertifika
```

Tarayıcıda: arama, seri/cilt sayfası, kapaklar, giriş/çıkış, Google ile giriş
(Google Cloud'da `https://yomiba.net` origin olarak eklenmeli), koleksiyon.
Sorun yoksa `.env` içinde zamanlayıcıları `1` yap ve
`docker compose up -d backend` çalıştır. İlk haftalarda Railway ve Vercel
kapatılmaz; geçiş oturunca `yomiba.vercel.app` → `yomiba.net` yönlendirilir.

## Günlük işler

- Güncelleme: `/srv/yomiba/app/deploy/guncelle.sh`
- Elle yedek: `/srv/yomiba/app/deploy/yedekle.sh` (log: `/var/log/yomiba-yedek.log`)
- Geri yükleme provası: `gunzip -k` ile açılan yedekte
  `python restore_check.py --db <dosya> --rehearse`
- Loglar: `docker compose logs --tail 200 backend`

## Henüz yok (sıradaki adımlar)

- Sunucu dışı sürekli yedek: Litestream → Cloudflare R2 (DB), kapaklar için
  gece senkronu.
- Push'ta GitHub Actions ile otomatik deploy; haftalık imaj yenileme.
- Erişilebilirlik takibi (ör. UptimeRobot) ve Umami.
- Filminibul'un aynı sunucuya alınması (Caddyfile'a ikinci site bloğu).
- `requirements.txt` sürümleri sabit değil; imaj için kilitli liste
  (`PRODUCTION.md`, "Dependencies").
