#!/usr/bin/env bash
# Yomiba — Railway'deki canlı DB'yi ve kapakları bu sunucuya taşır.
#
#   /srv/yomiba/app/deploy/railway-tasima.sh
#
# Railway volume'una hiçbir şey yazmaz (volume dolunca site çöküyor): çevrimiçi
# yedek ve kapak arşivi konteynerin geçici /tmp'sinde hazırlanır, base64 ile
# `railway ssh` üzerinden çekilir, sha256 ile doğrulanır ve /tmp temizlenir.
# Sunucuda var olan bir yomiba.db'nin üzerine asla yazmaz.
#
# Gerekenler: railway CLI, LINK_DIR'de (varsayılan /root) `railway link`,
# Railway hesabına eklenmiş SSH anahtarı, backend durdurulmuş olmalı.
set -euo pipefail

LINK_DIR="${LINK_DIR:-/root}"
WORK="${WORK:-/root/tasima}"
RAILWAY_DB="${RAILWAY_DB:-/data/yomiba-staging.db}"
DATA="${DATA:-/srv/yomiba/data}"
DEPLOY="$(cd "$(dirname "$0")" && pwd)"

die() { echo "HATA: $*" >&2; exit 1; }
remote() { (cd "$LINK_DIR" && railway ssh -- sh -c "$1"); }
# railway ssh çıktısı TTY'den geçebilir (\r) ve başına bilgi satırı ekler;
# yalnızca işaretler arasındaki base64'ü al.
extract() { tr -d '\r' < "$1" | sed -n '/^==BASLA==$/,/^==BITTI==$/p' | sed '1d;$d' | base64 -d > "$2"; }
remote_sha() { tr -d '\r' < "$1" | sed -n 's/^SHA \([0-9a-f]\{64\}\).*/\1/p'; }

command -v railway >/dev/null || die "railway CLI bulunamadı"
[ ! -e "$DATA/yomiba.db" ] || die "$DATA/yomiba.db zaten var; üzerine yazılmaz"
# Yeniden başlatma döngüsündeki bir backend, DB yerleşirken açılabilir.
if [ -n "$(cd "$DEPLOY" && docker compose ps -a -q backend 2>/dev/null)" ]; then
  die "backend konteyneri var; önce: cd $DEPLOY && docker compose down"
fi
mkdir -p "$WORK"
cd "$WORK"

# Uygulama dizinini bul (Railpack: /app), boş yer kontrolü, yedek + doğrulama,
# kapaklar ve DB'nin yanındaki durum dosyaları için arşiv.
PREP='set -e
cd /app 2>/dev/null || true
[ -f db_backup.py ] || cd "$(dirname "$(find / -xdev -name db_backup.py 2>/dev/null | head -1)")"
rm -f /tmp/tasima.db /tmp/kapak.tar
avail=$(python -c "import shutil; print(shutil.disk_usage(\"/tmp\").free // 1024)")
echo "tmp bos alan: ${avail} KB"
[ "$avail" -gt 450000 ] || { echo "YETERSIZ_ALAN"; exit 3; }
python db_backup.py --source "'"$RAILWAY_DB"'" --output /tmp/tasima.db
python restore_check.py --db /tmp/tasima.db
cd "$(dirname "'"$RAILWAY_DB"'")"
db="$(basename "'"$RAILWAY_DB"'")"
python - "$db" /tmp/kapak.tar <<PY
import sys, tarfile
from pathlib import Path
db, out = sys.argv[1], sys.argv[2]
with tarfile.open(out, "w") as tar:
    tar.add("covers")
    for name in (db + ".catalog-state.json", db + ".isbn-safety.json"):
        if Path(name).is_file():
            tar.add(name)
PY
ls -l /tmp/tasima.db /tmp/kapak.tar
echo HAZIR'

echo "[1/5] Railway'de yedek alınıyor (yalnızca /tmp)..."
remote "$PREP" | tee hazirlik.log
tr -d '\r' < hazirlik.log | grep -qx HAZIR || die "Railway tarafında hazırlık başarısız (hazirlik.log)"

for pair in "tasima.db:yomiba.db" "kapak.tar:kapak.tar"; do
  src="${pair%%:*}"; dst="${pair##*:}"
  echo "[2/5] /tmp/$src indiriliyor..."
  remote "echo ==BASLA==; base64 /tmp/$src; echo ==BITTI==; echo SHA \$(sha256sum /tmp/$src)" > "$dst.b64"
  extract "$dst.b64" "$dst"
  want="$(remote_sha "$dst.b64")"
  got="$(sha256sum "$dst" | cut -d' ' -f1)"
  [ -n "$want" ] && [ "$want" = "$got" ] || die "$dst sha256 uyuşmuyor (Railway: ${want:-yok}, burada: $got)"
  echo "      sha256 tamam: $got"
  rm -f "$dst.b64"
done

echo "[3/5] Railway /tmp temizleniyor..."
remote 'rm -f /tmp/tasima.db /tmp/kapak.tar; echo temiz' | tail -1

echo "[4/5] dosyalar $DATA altına yerleştiriliyor..."
src_db="$(basename "$RAILWAY_DB")"
staging="$WORK/acilan"
rm -rf "$staging"; mkdir -p "$staging"
tar xf kapak.tar -C "$staging"
[ ! -e "$DATA/covers" ] || die "$DATA/covers zaten var"
mv "$staging/covers" "$DATA/covers"
for suffix in catalog-state.json isbn-safety.json; do
  [ -f "$staging/$src_db.$suffix" ] && mv "$staging/$src_db.$suffix" "$DATA/yomiba.db.$suffix"
done
install -m 0600 yomiba.db "$DATA/yomiba.db"
chown -R 10001:10001 "$DATA"

echo "[5/5] sunucuda bütünlük kontrolü..."
(cd "$DEPLOY" && docker compose run --rm --no-deps -T backend python restore_check.py --db /data/yomiba.db)

cat <<EOF

Taşıma bitti. $WORK altındaki yomiba.db ve kapak.tar yerel kopya olarak kalır.
Başlatmak için:  cd $DEPLOY && docker compose up -d && docker compose logs -f backend
EOF
