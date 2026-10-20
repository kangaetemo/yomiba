#!/usr/bin/env bash
# Yomiba — DB'nin çevrimiçi yedeği (SQLite backup API) + doğrulama.
# Cron her gece çalıştırır; son KEEP yedek /srv/yomiba/backups altında kalır.
# Sunucu dışı kopya (R2/B2) ayrıca kurulacak; bu yedek tek başına disk
# kaybına karşı korumaz.
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
