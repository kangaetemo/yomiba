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

baslik "py-spy record ${SURE} sn"
spy "py-spy record --pid $pid --duration $SURE --rate 50 --nonblocking --format raw --output /out/profil.txt >/dev/null 2>&1"
P=/tmp/yomiba-cpu/profil.txt
if [ -s "$P" ]; then
  # Satır: "kök;...;yaprak sayı". py-spy bekleyen iş parçacıklarını da sayar
  # (_worker, ssl read, asyncio): gerçek iş en derin app/ çerçevesindedir.
  echo "-- en derin app/ çerçevesi --"
  awk '{c=$NF; $NF=""; n=split($0,f,";"); a="(app dışı)"; for(i=n;i>=1;i--) if (f[i] ~ /app\//) {a=f[i]; break}; s[a]+=c; t+=c} END {for (k in s) printf "%5.1f%%  %s\n", 100*s[k]/t, k}' "$P" | sort -rn | head -15
  echo "-- HTML ayrıştırma örnekleri, mağazaya göre --"
  awk '/bs4|lxml|soupsieve/ {c=$NF; m="?"; n=split($0,f,";"); for(i=n;i>=1;i--) if (match(f[i],/app\/scrapers\/[a-z_]+\.py/) && f[i] !~ /base\.py|common\.py/) {m=substr(f[i],RSTART+13,RLENGTH-16); break}; s[m]+=c} END{for(k in s) print s[k], k}' "$P" | sort -rn
  echo "(tam profil: $P)"
else
  echo "py-spy record çıktı vermedi"
fi

baslik "son 1 saatte mağaza başına arama / sayfa / duruş nedeni"
docker compose logs --since 1h --no-color backend 2>/dev/null | awk '/search stats for/ {match($0,/import: [a-z]+ search/); st=substr($0,RSTART+8,RLENGTH-15); p=0; if (match($0,/.pages_fetched.: [0-9]+/)) {split(substr($0,RSTART,RLENGTH),a,": "); p=a[2]}; r="?"; if (match($0,/.stop_reason.: .?[A-Za-z_]+/)) {r=substr($0,RSTART+15,RLENGTH-15); gsub(/[^A-Za-z_]/,"",r)}; n[st]++; pg[st]+=p; rs[st" "r]++} END {for(k in n) printf "%-16s arama=%d sayfa=%d\n", k, n[k], pg[k]; for(k in rs) print "   " k, rs[k]}' | sort
