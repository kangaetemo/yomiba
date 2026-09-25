#!/usr/bin/env bash
# Yomiba — yerel kurulum (macOS / Linux)
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================"
echo "  YOMIBA - yerel kurulum"
echo "============================================"
echo

# ---------- [0/4] Sistem kontrolu ----------
echo "[0/4] Sistem kontrolu..."
PY="$(command -v python3.12 || command -v python3.11 || command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "HATA: python3 bulunamadi. Python 3.11+ kurulmustur."
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null; then
  echo "HATA: Python 3.11+ gerekiyor ($($PY --version) bulundu)."
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "HATA: Node.js bulunamadi. Node 18+ (LTS) kur."
  exit 1
fi
echo "  $("$PY" --version) ve $(node --version) OK."
echo

# ---------- [1/4] Backend ----------
echo "[1/4] Backend sanal ortami (ilk calistirmada ~1 dk)..."
if [ ! -d backend/.venv ]; then
  (cd backend && "$PY" -m venv .venv && .venv/bin/pip install -q -r requirements.txt)
fi
echo "  Backend hazir."
echo

# ---------- [2/4] Frontend ----------
echo "[2/4] Frontend bagimlilari (ilk calistirmada ~1 dk)..."
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi
echo "  Frontend hazir."
echo

# ---------- [3/4] Ilk is DB yedegi ----------
if [ ! -f backend/yomiba.db.bak-first ]; then
  cp backend/yomiba.db backend/yomiba.db.bak-first
  echo "  DB yedeklendi: backend/yomiba.db.bak-first"
fi

# ---------- [4/4] Hizmetler ----------
echo "[4/4] Hizmetler baslatiliyor..."
(cd backend && CATALOG_SYNC_INTERVAL_HOURS=12 PRICE_REFRESH_INTERVAL_HOURS=24 \
  IMPORT_MAX_CONCURRENT_JOBS=8 \
  nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info \
  > /tmp/yomiba-api.log 2>&1 &
 echo "  API  -> http://127.0.0.1:8000   (log: /tmp/yomiba-api.log)")
(cd frontend && nohup npm run dev > /tmp/yomiba-web.log 2>&1 &
 echo "  Web  -> http://localhost:3000   (log: /tmp/yomiba-web.log)")

sleep 6
echo
echo "============================================"
echo "  HAZIR!"
echo "  Web    : http://localhost:3000"
echo "  Admin  : http://localhost:3000/admin"
echo "============================================"
echo
echo "  Ilk is: admin sayfasinda \"Tum katalogu isit\" butonuna bas (1 kere)."
echo
echo "  Kapatmak:  pkill -f 'uvicorn app.main' && pkill -f 'next dev'"
