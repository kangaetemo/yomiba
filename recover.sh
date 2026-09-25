#!/usr/bin/env bash
# Yomiba — tek komutlu reset kurtarma betiği.
#
# Sandbox environment reset'lerinden sonra (venv + node_modules + süreçler
# silindi; yomiba.db SAĞLAM kalır) her şeyi geri koyar:
#   1) backend venv + requirements
#   2) frontend node_modules
#   3) API (:8000, env 12h katalog / 24h fiyat / 8 paralel) + web (:3000)
#   4) katalog warmup'ını yeniden kuyruğa alır (dedup-güvenli, fresh kayıtlar
#      60 dk içindeyse anında atlanır)
#
# Kullanım:  bash recover.sh
# Loglar:    /tmp/yomiba-api.log  /tmp/yomiba-web.log
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/4] backend venv..."
(cd backend && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt)

echo "[2/4] frontend deps..."
(cd frontend && npm install --no-audit --no-fund >/dev/null)

echo "eski süreçleri durduruluyor..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
sleep 2

echo "[3/4] API + web başlatılıyor..."
(cd backend && CATALOG_SYNC_INTERVAL_HOURS=12 PRICE_REFRESH_INTERVAL_HOURS=24 \
  IMPORT_MAX_CONCURRENT_JOBS=8 \
  nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --log-level info > /tmp/yomiba-api.log 2>&1 &)
(cd frontend && nohup npm run dev > /tmp/yomiba-web.log 2>&1 &)

for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -sf http://127.0.0.1:8000/health >/dev/null || {
  echo "API hazır olmadı — /tmp/yomiba-api.log'a bakın"; exit 1; }

echo "[4/4] warmup yeniden kuyruğa alınıyor..."
curl -s -X POST http://127.0.0.1:8000/import/warmup
echo
echo "Kurtarma tamam. API :8000 · Web :3000 · /admin'den izlenebilir."
