#!/usr/bin/env bash
# Yomiba — GitHub'daki son sürümü sunucuya al ve yeniden başlat.
#   /srv/yomiba/app/deploy/guncelle.sh
set -euo pipefail
cd "$(dirname "$0")"

git -C .. pull --ff-only
docker compose build --pull
docker compose up -d
docker image prune -f >/dev/null
docker compose ps
