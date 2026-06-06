#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${SEISMIC_VIEWER_PROJECT:-$HOME/Applications/MultiViewer/seismic_viewer_project}"
FRONTEND="$PROJECT/seismic-viewer-frontend"
BACKEND="$PROJECT/seismic-viewer-backend"
BASE="${SEISMIC_VIEWER_BASE_URL:-http://127.0.0.1:8000}"
HOST="${SEISMIC_VIEWER_HOST:-127.0.0.1}"
PORT="${SEISMIC_VIEWER_PORT:-8000}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$BACKEND/backend_runtime_deploy_${STAMP}.log"
PACKAGED="$BACKEND/packaged_dist"
BACKUP="$PROJECT/_runtime_backup_packaged_dist_${STAMP}"

fail() {
  echo "DEPLOY_LOCAL_RUNTIME: FAIL"
  echo "$1"
  exit 1
}

bundle_from_index() {
  local file="$1"
  if [ -f "$file" ]; then
    grep -o 'assets/index-[^"]*\.js' "$file" | head -1 || true
  fi
}

echo "DEPLOY_LOCAL_RUNTIME"
echo "Timestamp: $(date)"
echo "Project: $PROJECT"
echo "Frontend: $FRONTEND"
echo "Backend: $BACKEND"
echo "Base URL: $BASE"
echo

echo "---- preflight ----"
[ -d "$PROJECT" ] || fail "Missing project directory: $PROJECT"
[ -d "$FRONTEND" ] || fail "Missing frontend directory: $FRONTEND"
[ -d "$BACKEND" ] || fail "Missing backend directory: $BACKEND"
[ -f "$FRONTEND/package.json" ] || fail "Missing frontend package.json"
[ -f "$BACKEND/main.py" ] || fail "Missing backend main.py"
[ -d "$BACKEND/venv" ] || fail "Missing backend venv"
echo "preflight: PASS"
echo

echo "---- build frontend ----"
cd "$FRONTEND"
npm run build
[ -f "$FRONTEND/dist/index.html" ] || fail "Frontend build did not produce dist/index.html"
FRONT_BUNDLE="$(bundle_from_index "$FRONTEND/dist/index.html")"
[ -n "$FRONT_BUNDLE" ] || fail "Could not determine frontend dist bundle"
echo "frontend bundle: $FRONT_BUNDLE"
echo

echo "---- publish frontend artifact ----"
mkdir -p "$BACKUP"
if [ -d "$PACKAGED" ]; then
  cp -R "$PACKAGED" "$BACKUP/packaged_dist"
fi
rm -rf "$PACKAGED"
mkdir -p "$PACKAGED"
cp -R "$FRONTEND/dist/"* "$PACKAGED/"
PACK_BUNDLE="$(bundle_from_index "$PACKAGED/index.html")"
[ -n "$PACK_BUNDLE" ] || fail "Could not determine packaged_dist bundle"
[ "$FRONT_BUNDLE" = "$PACK_BUNDLE" ] || fail "Built bundle and packaged bundle differ: $FRONT_BUNDLE vs $PACK_BUNDLE"
echo "packaged bundle: $PACK_BUNDLE"
echo "packaged backup: $BACKUP"
echo

echo "---- restart backend ----"
cd "$BACKEND"
source "$BACKEND/venv/bin/activate"

PIDS="$(lsof -tiTCP:${PORT} -sTCP:LISTEN || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS 2>/dev/null || true
  sleep 2
fi

nohup python -m uvicorn main:app --host "$HOST" --port "$PORT" > "$LOG" 2>&1 &
sleep 4

echo "backend log: $LOG"
echo

echo "---- backend health ----"
python - <<PY
import json
import sys
import urllib.request

url = "$BASE/api/msi/health"
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception as exc:
    print(f"backend health request failed: {exc}")
    sys.exit(1)

print(json.dumps(payload, indent=2, sort_keys=True))
if not payload.get("ok"):
    sys.exit(1)
PY
echo "backend health: PASS"
echo

echo "---- served bundle verification ----"
SERVED_BUNDLE="$(curl -s "$BASE/" | grep -o 'assets/index-[^"]*\.js' | head -1 || true)"
[ -n "$SERVED_BUNDLE" ] || fail "Could not determine served bundle"
echo "frontend dist:    $FRONT_BUNDLE"
echo "packaged_dist:    $PACK_BUNDLE"
echo "served:           $SERVED_BUNDLE"

if [ "$FRONT_BUNDLE" != "$SERVED_BUNDLE" ]; then
  fail "Served bundle mismatch: built=$FRONT_BUNDLE served=$SERVED_BUNDLE"
fi

echo
echo "DEPLOY_LOCAL_RUNTIME: PASS"
echo
echo "Open app:"
echo "open -na \"Google Chrome\" --args --new-window \"$BASE/\""
