#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
HOST="${WLV_BACKEND_HOST:-127.0.0.1}"
PORT="${WLV_BACKEND_PORT:-8010}"
RUNTIME_DIR="$PROJECT/backend/runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/wlv_backend.pid"
LOG_FILE="$LOG_DIR/wlv_backend_$(date +%Y%m%d_%H%M%S).log"
PYTHON="$PROJECT/backend/.venv/bin/python"

mkdir -p "$LOG_DIR"
cd "$PROJECT"

if [ ! -x "$PYTHON" ]; then
  echo "ERROR: Backend venv not found at $PYTHON"
  echo "Run scripts/wlv_backend_validate.sh to create/repair the backend environment."
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "WLV backend already running with PID $OLD_PID"
    echo "URL: http://$HOST:$PORT"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if command -v lsof >/dev/null 2>&1; then
  PORT_PID="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  if [ -n "$PORT_PID" ]; then
    echo "ERROR: Port $PORT is already in use by PID $PORT_PID"
    exit 1
  fi
fi

export PYTHONPATH="$PROJECT"
export WLV_BACKEND_HOST="$HOST"
export WLV_BACKEND_PORT="$PORT"

nohup "$PYTHON" -m uvicorn backend.app.main:app --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
PID="$!"
echo "$PID" > "$PID_FILE"

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    echo "WLV backend started"
    echo "PID: $PID"
    echo "URL: http://$HOST:$PORT"
    echo "Log: $LOG_FILE"
    exit 0
  fi
  sleep 0.5
done

echo "ERROR: WLV backend did not pass health check"
echo "PID: $PID"
echo "Log: $LOG_FILE"
exit 1
