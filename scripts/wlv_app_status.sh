#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
RUNTIME_DIR="$PROJECT/.wlv_runtime"
BACKEND_URL="http://127.0.0.1:8001"
FRONTEND_URL="http://127.0.0.1:5173"
PROFILE_DIR="$RUNTIME_DIR/chrome-profile"

cd "$PROJECT"
echo "WLV app runtime status"
echo "Project: $PROJECT"
echo "Backend:  $BACKEND_URL"
echo "Frontend: $FRONTEND_URL"

echo
echo "---- git ----"
git status --short || true
git log --oneline --decorate -5 || true

echo
echo "---- PID files ----"
for f in "$RUNTIME_DIR/backend.pid" "$RUNTIME_DIR/frontend.pid" "$RUNTIME_DIR/launcher.pid" "$PROJECT/.wlv_backend.pid" "$PROJECT/.wlv_frontend.pid"; do
  if [ -f "$f" ]; then
    pid="$(cat "$f" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "$f -> $pid RUNNING"
    else
      echo "$f -> ${pid:-empty} NOT RUNNING"
    fi
  else
    echo "$f -> missing"
  fi
done

echo
echo "---- WLV ports and possible conflicts ----"
for port in 8001 5173 8000 5174 5175; do
  echo "### port $port"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || echo "no listener"
done

echo
echo "---- WLV Chrome profile processes ----"
ps aux | grep -F "$PROFILE_DIR" | grep -v grep || echo "no WLV Chrome profile process"

echo
echo "---- health ----"
if curl -fsS "$BACKEND_URL/api/wlv/source-intake/health" >/dev/null 2>&1; then
  echo "Backend source-intake: OK"
else
  echo "Backend source-intake: FAIL"
fi
if curl -fsS "$BACKEND_URL/api/wlv/wdv/templates" >/dev/null 2>&1; then
  echo "Backend WDV templates: OK"
else
  echo "Backend WDV templates: FAIL"
fi
if curl -fsS "$FRONTEND_URL" >/dev/null 2>&1; then
  echo "Frontend: OK"
else
  echo "Frontend: FAIL"
fi
