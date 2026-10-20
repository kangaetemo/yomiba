#!/usr/bin/env bash
# Yomiba — GitHub'daki son sürümü sunucuya al ve yeniden başlat.
#   /srv/yomiba/app/deploy/guncelle.sh
# GitHub Actions da main'e push'ta (testler geçince) ve haftada bir SSH ile
# bunu çalıştırır (.github/workflows/deploy.yml); o anahtar yalnızca bu
# betiği çalıştırabilir.
set -euo pipefail
cd "$(dirname "$0")"
SELF="$PWD/$(basename "$0")"

if [ "${1:-}" != "--cekildi" ]; then
  # Aynı anda iki deploy olmasın; kilit exec sonrasında da tutulur.
  exec 9>/var/lock/yomiba-deploy.lock
  flock 9
  git -C .. pull --ff-only
  # Bash betiği okurken çalıştırır: yeni sürümüyle baştan devam et.
  exec "$SELF" --cekildi
fi

echo "sürüm: $(git -C .. log -1 --format='%h %s')"
docker compose build --pull
docker compose up -d --wait --wait-timeout 300
docker image prune -f >/dev/null
domain="$(sed -n 's/^SITE_DOMAIN=//p' .env)"
curl -fsS -o /dev/null --max-time 20 "https://${domain:-yomiba.net}/" \
  || { echo "HATA: site cevap vermiyor"; docker compose ps; exit 1; }
docker compose ps
echo "deploy tamam"
