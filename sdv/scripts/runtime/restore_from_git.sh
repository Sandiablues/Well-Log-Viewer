#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${SEISMIC_VIEWER_PROJECT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BACKEND="$PROJECT/seismic-viewer-backend"
FRONTEND="$PROJECT/seismic-viewer-frontend"
BASE="http://127.0.0.1:8000"

cd "$BACKEND"
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cd "$FRONTEND"
npm ci
npm run build

rm -rf "$BACKEND/packaged_dist"
mkdir -p "$BACKEND/packaged_dist"
cp -R "$FRONTEND/dist/"* "$BACKEND/packaged_dist/"

cd "$BACKEND"
source venv/bin/activate
PIDS="$(lsof -tiTCP:8000 -sTCP:LISTEN || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS 2>/dev/null || true
  sleep 2
fi

nohup python -m uvicorn main:app --host 127.0.0.1 --port 8000 > backend_restore.log 2>&1 &
sleep 4

curl -s "$BASE/api/msi/health" | python -m json.tool

echo "RESTORE_FROM_GIT: PASS"
echo "Open: http://127.0.0.1:8000/"
