#!/bin/bash
set -euo pipefail

PROJECT_ROOT="/Users/donarcher/Applications/MultiViewer/seismic_viewer_project"
BACKEND_DIR="$PROJECT_ROOT/seismic-viewer-backend"

RUNTIME_DIR="/Users/donarcher/Applications/MultiViewer"
RUNTIME_LOG_DIR="$RUNTIME_DIR/logs"

PROJECT_LOG_DIR="$PROJECT_ROOT/logs"
PROJECT_RUN_DIR="$PROJECT_ROOT/run"

mkdir -p "$RUNTIME_LOG_DIR" "$PROJECT_LOG_DIR" "$PROJECT_RUN_DIR"

APP_LOG="$RUNTIME_LOG_DIR/multiviewer_app_launch.log"
BACKEND_LOG="$PROJECT_LOG_DIR/backend.log"
BACKEND_PID="$PROJECT_RUN_DIR/backend.pid"

{
  echo "=== MultiViewer launch $(date) ==="
  echo "Project root: $PROJECT_ROOT"
  echo "Backend dir:  $BACKEND_DIR"

  backend_running=false

  # First trust the PID file if it points to a live process.
  if [ -f "$BACKEND_PID" ]; then
    pid="$(cat "$BACKEND_PID")"

    if ps -p "$pid" >/dev/null 2>&1; then
      backend_running=true
      echo "Backend already running from PID file, PID $pid"
    else
      echo "Removing stale backend PID file."
      rm -f "$BACKEND_PID"
    fi
  fi

  # Then guard against manually started or launcher-orphaned backends.
  # This prevents duplicate backend listeners serving stale code.
  if [ "$backend_running" = false ]; then
    port_pid="$(lsof -tiTCP:8000 -sTCP:LISTEN | head -1 || true)"
    if [ -n "$port_pid" ]; then
      backend_running=true
      echo "$port_pid" > "$BACKEND_PID"
      echo "Backend already listening on port 8000, PID $port_pid"
    fi
  fi

  if [ "$backend_running" = false ]; then
    echo "Starting backend hidden..."

    cd "$BACKEND_DIR"

    if [ -x "venv/bin/python" ]; then
      nohup arch -arm64 "venv/bin/python" -m uvicorn main:app --host 0.0.0.0 --port 8000 > "$BACKEND_LOG" 2>&1 &
    elif [ -x ".venv/bin/python" ]; then
      nohup arch -arm64 ".venv/bin/python" -m uvicorn main:app --host 0.0.0.0 --port 8000 > "$BACKEND_LOG" 2>&1 &
    else
      echo "ERROR: python not found in backend venv."
      exit 1
    fi

    echo $! > "$BACKEND_PID"

    sleep 2

    if ps -p "$(cat "$BACKEND_PID")" >/dev/null 2>&1; then
      echo "Backend started, PID $(cat "$BACKEND_PID")"
    else
      echo "ERROR: backend failed to start."
      tail -80 "$BACKEND_LOG" || true
      exit 1
    fi
  fi

  echo "Opening browser in sized new window..."

  # Launch profile: open MultiViewer wide enough for the left menu,
  # toolbars, and main page controls without requiring manual expansion.
  # Keep this launcher-level sizing here; do not solve first-open width
  # with page-by-page layout hacks.
  APP_URL="http://localhost:8000"
  WINDOW_BOUNDS="{80, 40, 1680, 1040}"

  if /usr/bin/osascript -e 'id of application "Google Chrome"' >/dev/null 2>&1; then
    /usr/bin/osascript <<OSA
set appUrl to "$APP_URL"
set desiredBounds to $WINDOW_BOUNDS

tell application "Google Chrome"
  activate
  make new window
  set bounds of front window to desiredBounds
  set URL of active tab of front window to appUrl
end tell
OSA
  else
    /usr/bin/open -na "Google Chrome" --args \
      --new-window \
      --window-size=1600,1000 \
      --window-position=80,40 \
      "$APP_URL"
  fi

  echo "Launch complete."
} >> "$APP_LOG" 2>&1
