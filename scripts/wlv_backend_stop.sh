#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
PORT="${WLV_BACKEND_PORT:-8010}"
PID_FILE="$PROJECT/backend/runtime/wlv_backend.pid"

STOPPED=0

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      if ! kill -0 "$PID" 2>/dev/null; then
        break
      fi
      sleep 0.3
    done
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" 2>/dev/null || true
    fi
    STOPPED=1
  fi
  rm -f "$PID_FILE"
fi

if command -v lsof >/dev/null 2>&1; then
  for PID in $(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true); do
    kill "$PID" 2>/dev/null || true
    STOPPED=1
  done
fi

if [ "$STOPPED" -eq 1 ]; then
  echo "WLV backend stopped."
else
  echo "WLV backend was not running."
fi
