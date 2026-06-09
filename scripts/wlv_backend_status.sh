#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
HOST="${WLV_BACKEND_HOST:-127.0.0.1}"
PORT="${WLV_BACKEND_PORT:-8010}"
PID_FILE="$PROJECT/backend/runtime/wlv_backend.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "PID: $PID"
  else
    echo "PID file exists but process is not running."
  fi
else
  echo "No WLV backend PID file."
fi

if curl -fsS "http://$HOST:$PORT/api/wlv/system/status" >/tmp/wlv_backend_status_payload.json 2>/dev/null; then
  echo "Status endpoint: OK"
  cat /tmp/wlv_backend_status_payload.json
  echo
else
  echo "Status endpoint: unavailable at http://$HOST:$PORT/api/wlv/system/status"
fi
