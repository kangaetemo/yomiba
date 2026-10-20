#!/usr/bin/env bash
# Yomiba — DB'nin çevrimiçi yedeği (SQLite backup API) + doğrulama.
# Cron her gece çalıştırır; son KEEP yedek /srv/yomiba/backups altında kalır.
# r2.env doluysa yedek ve kapaklar R2'ye de kopyalanır (R2'de 30 gün).
# DB'nin sürekli kopyası ayrıca Litestream'de (docker-compose.yml).
set -euo pipefail
cd "$(dirname "$0")"

ROOT=/srv/yomiba
KEEP="${KEEP:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="yomiba-$STAMP.db"

docker compose exec -T backend python db_backup.py \
  --source /data/yomiba.db --output "/data/backups/$NAME"
docker compose exec -T backend python restore_check.py --db "/data/backups/$NAME"

mv "$ROOT/data/backups/$NAME" "$ROOT/backups/$NAME"
gzip -f "$ROOT/backups/$NAME"
ls -1t "$ROOT"/backups/yomiba-*.db.gz | tail -n +"$((KEEP + 1))" | xargs -r rm --
echo "$(date -u +%FT%TZ) yedek tamam: $ROOT/backups/$NAME.gz"

if [ -f r2.env ] && grep -q '^RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=.' r2.env; then
  BUCKET="$(sed -n 's/^R2_BUCKET=//p' r2.env)"
  [ -n "$BUCKET" ] || { echo "r2.env: R2_BUCKET boş"; exit 1; }
  rclone() { docker compose run --rm -T rclone "$@"; }
  rclone copy /backups "r2:$BUCKET/gunluk" --include 'yomiba-*.db.gz'
  rclone delete "r2:$BUCKET/gunluk" --min-age 30d
  # copy, not sync: a deleted local cover never removes the off-site copy.
  rclone copy /covers "r2:$BUCKET/covers"
  echo "$(date -u +%FT%TZ) R2 kopyası tamam: $BUCKET"
else
  echo "UYARI: r2.env yok ya da boş; sunucu dışı kopya alınmadı"
fi
