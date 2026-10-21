#!/usr/bin/env bash
# Yomiba — backend neden işlemci yiyor? Canlı ölçüm, hiçbir şeyi değiştirmez.
#   sudo /srv/yomiba/app/deploy/cpu-teshis.sh            # ekrana
#   sudo /srv/yomiba/app/deploy/cpu-teshis.sh > rapor.txt 2>&1
#
# py-spy, sunucuya kurulmadan geçici bir konteynerde çalışır (--pid=host):
# backend'in o an hangi Python satırlarında durduğunu gösterir. Backend'i
# durdurmaz, yeniden başlatmaz; yalnızca birkaç saniye örnekler.
set -uo pipefail
cd "$(dirname "$0")"

SURE="${SURE:-60}"   # py-spy örnekleme süresi (saniye)
DATA="$(sed -n 's/^DATA_DIR=//p' .env 2>/dev/null)"
DATA="${DATA:-/srv/yomiba/data}"
cid="$(docker compose ps -q backend)"
[ -n "$cid" ] || { echo "backend konteyneri çalışmıyor"; exit 1; }
pid="$(docker inspect -f '{{.State.Pid}}' "$cid")"

baslik() { printf '\n===== %s =====\n' "$1"; }

baslik "docker stats"
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'

baslik "backend açık kalma süresi / yeniden başlama"
docker inspect -f 'başladı={{.State.StartedAt}} yeniden_başlama={{.RestartCount}} sağlık={{.State.Health.Status}}' "$cid"

baslik "backend iş parçacıkları (en çok CPU)"
top -H -b -n 1 -p "$pid" | sed -n '7,22p'

baslik "veritabanı dosyaları (büyük bir -wal checkpoint yapılamadığını gösterir)"
ls -la "$DATA" | grep -E 'yomiba\.db|litestream' || true

baslik "son 10 dakikada en çok log yazan kaynaklar"
docker compose logs --since 10m --no-color backend 2>/dev/null \
  | sed -nE 's/.* (INFO|WARNING|ERROR) ([^:]+):.*/\1 \2/p' | sort | uniq -c | sort -rn | head -15

baslik "son 10 dakikada en çok istenen adresler"
docker compose logs --since 10m --no-color backend 2>/dev/null \
  | sed -nE 's/.*"(GET|POST|PUT|DELETE|PATCH) ([^ ?"]+).*/\1 \2/p' | sort | uniq -c | sort -rn | head -15

baslik "son 10 dakikada biten içe aktarmalar"
docker compose logs --since 10m --no-color backend 2>/dev/null | grep -c 'background import for .* finished' || true

baslik "py-spy dump (o anki yığınlar, 3 kez)"
spy() {
  docker run --rm --pid=host --cap-add SYS_PTRACE -v /tmp/yomiba-cpu:/out \
    python:3.12-slim sh -c "pip install -q --root-user-action=ignore py-spy >/dev/null 2>&1 && $1"
}
mkdir -p /tmp/yomiba-cpu
spy "py-spy dump --pid $pid; sleep 5; echo ---; py-spy dump --pid $pid; sleep 5; echo ---; py-spy dump --pid $pid"

baslik "py-spy record ${SURE} sn (en sık görülen 25 yığın)"
spy "py-spy record --pid $pid --duration $SURE --rate 50 --nonblocking --format raw --output /out/profil.txt >/dev/null 2>&1"
if [ -s /tmp/yomiba-cpu/profil.txt ]; then
  # Satır: "çerçeve;çerçeve;... sayı" — en çok örneklenen yığınlar, son 4 çerçeve.
  awk '{n=$NF; $NF=""; k=split($0,f,";"); s=""; for(i=(k>4?k-3:1);i<=k;i++) s=s (s?" > ":"") f[i]; print n"\t"s}' /tmp/yomiba-cpu/profil.txt \
    | sort -rn | head -25
  echo "(tam profil: /tmp/yomiba-cpu/profil.txt)"
else
  echo "py-spy record çıktı vermedi"
fi
