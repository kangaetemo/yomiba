# Yomiba — VDS kurulumu (yomiba.net)

Sunucu: Hephosting TRX-8G, Ubuntu 24.04. Yapı: Docker Compose ile Next.js
(`frontend`) ve FastAPI (`backend`); önde sunucunun kendi Caddy'si (otomatik
HTTPS, Filminibul ile ortak). Frontend yalnızca `127.0.0.1:3001`'de dinler,
backend'e tarayıcı Next'in `/api` yönlendirmesiyle ulaşır. Dışarı yalnızca
80/443 açık.

| Dosya | Görev |
| --- | --- |
| `docker-compose.yml` | backend + frontend, log sınırı, `/srv/yomiba/data` → `/data` |
| `yomiba.caddy` | Host Caddy için site bloğu: `yomiba.net` → `127.0.0.1:3001`, `www` → kök |
| `Caddyfile` | Yalnızca host Caddy'si olmayan bir sunucuda: `docker compose --profile caddy up -d` |
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

## 5. Host Caddy'ye Yomiba'yı ekle (bir kez)

```sh
grep -q yomiba.caddy /etc/caddy/Caddyfile || echo 'import /srv/yomiba/app/deploy/yomiba.caddy' >> /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && systemctl reload caddy
```

`validate` hata verirse `reload` çalışmaz; Filminibul etkilenmez. `yomiba.caddy`
değişince `git pull` sonrası yalnızca `systemctl reload caddy` yeterli.

## 6. Başlat ve doğrula

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

## 7. Sunucu dışı yedek (Cloudflare R2)

İki katman, ikisi de `yomiba-yedek` bucket'ına:

- **Litestream** (`litestream` servisi): DB değişikliklerini en geç 60 saniyede
  `litestream/` altına kopyalar; 7 gün geriye herhangi bir ana dönülebilir.
- **Gece kopyası** (`yedekle.sh` → `rclone`): doğrulanmış gece yedeği
  `gunluk/` altına (30 gün), kapaklar `covers/` altına. Kapaklarda `copy`
  kullanılır; sunucuda silinen kapak R2'den silinmez.

Kurulum (bir kez): Cloudflare'de R2'yi aç (ücretsiz katman için de ödeme
yöntemi istiyor), `yomiba-yedek` bucket'ını oluştur, yalnızca bu bucket için
*Object Read & Write* yetkili API token al. Sonra sunucuda:

```sh
cd /srv/yomiba/app/deploy
install -m 600 r2.env.example r2.env && nano r2.env      # endpoint + iki anahtar
grep -q '^COMPOSE_PROFILES=' .env && sed -i 's/^COMPOSE_PROFILES=.*/COMPOSE_PROFILES=r2/' .env || echo 'COMPOSE_PROFILES=r2' >> .env
docker compose up -d && docker compose logs --tail 30 litestream
./yedekle.sh
```

Litestream logunda `initialized db` ve `replicating to` satırları görünmeli,
`error` olmamalı. Ardından **geri yükleme provası** (ayda bir tekrarlanır):

```sh
docker compose run --rm --no-deps litestream restore -o /data/backups/prova.db /data/yomiba.db
docker compose run --rm --no-deps -T backend python restore_check.py --db /data/backups/prova.db
rm -f /srv/yomiba/data/backups/prova.db*
```

Sunucu tamamen kaybolursa: yeni sunucuda 2. ve 5. adımlar ve `r2.env`, sonra:

```sh
docker compose run --rm --no-deps litestream restore -o /data/yomiba.db /data/yomiba.db
docker compose run --rm -v /srv/yomiba/data/covers:/restore rclone copy r2:yomiba-yedek/covers /restore
chown -R 10001:10001 /srv/yomiba/data && docker compose up -d
```

## 8. Push'ta otomatik deploy (GitHub Actions)

`.github/workflows/deploy.yml`: main'e push'ta "Application checks" geçince,
her pazartesi 04:30'da (güncel taban imajlar ve paketler) ve elle (*Actions →
Deploy → Run workflow*) sunucuda `guncelle.sh` çalışır. GitHub'daki anahtar
sunucuda yalnızca bu betiğe kilitlidir; kabuk açamaz, port yönlendiremez.
`guncelle.sh` kilit alır (iki deploy aynı anda çalışmaz), siteyi açılınca
kontrol eder ve hata olursa iş akışı kırmızı biter.

Kurulum (bir kez, sunucuda):

```sh
cd /srv/yomiba/app && git pull --ff-only
ssh-keygen -t ed25519 -N "" -f /root/.ssh/github_deploy -C github-actions-deploy
echo "command=\"/srv/yomiba/app/deploy/guncelle.sh\",restrict $(cat /root/.ssh/github_deploy.pub)" >> /root/.ssh/authorized_keys
cat /root/.ssh/github_deploy                                     # -> DEPLOY_SSH_KEY
echo "45.74.243.61 $(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)"   # -> DEPLOY_KNOWN_HOSTS
```

GitHub → repo *Settings → Secrets and variables → Actions → New repository
secret*: `DEPLOY_SSH_KEY` (özel anahtarın tamamı, BEGIN/END satırları dahil),
`DEPLOY_KNOWN_HOSTS`, `DEPLOY_HOST` = `45.74.243.61`. Sonra sunucudaki özel
anahtarı sil: `rm /root/.ssh/github_deploy`. Sırlar yokken iş akışı uyarı verip
atlar.

## Günlük işler

- Güncelleme: main'e push yeterli (8. adım); elle: `/srv/yomiba/app/deploy/guncelle.sh`
- Elle yedek: `/srv/yomiba/app/deploy/yedekle.sh` (log: `/var/log/yomiba-yedek.log`)
- Geri yükleme provası: `gunzip -k` ile açılan yedekte
  `python restore_check.py --db <dosya> --rehearse`
- Loglar: `docker compose logs --tail 200 backend`
- R2 durumu: `docker compose logs --tail 50 litestream`; gece kopyası `/var/log/yomiba-yedek.log`
- Backend işlemci yiyorsa: `sudo /srv/yomiba/app/deploy/cpu-teshis.sh > /tmp/cpu.txt 2>&1`
  (docker stats, iş parçacıkları, WAL boyu, log/istek sayıları ve py-spy profili;
  hiçbir şeyi değiştirmez, ~80 sn sürer)

## Henüz yok (sıradaki adımlar)

- Erişilebilirlik takibi (ör. UptimeRobot) ve Umami.
- Filminibul aynı sunucuda, host Caddy'yi paylaşıyor (`/etc/caddy/site.caddy`, `api.caddy`); kendi kurulumu ayrı yürütülüyor.
- `requirements.txt` sürümleri sabit değil; imaj için kilitli liste
  (`PRODUCTION.md`, "Dependencies").
