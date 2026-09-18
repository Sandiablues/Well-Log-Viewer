#!/bin/bash
set -euo pipefail

PID_FILE="/Users/donarcher/Applications/MultiViewer/seismic_viewer_project/run/backend.pid"

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE")"

  if ps -p "$pid" >/dev/null 2>&1; then
    kill "$pid" 2>/dev/null || true
    sleep 1

    if ps -p "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi

  rm -f "$PID_FILE"
fi

echo "Stopped runtime backend. Browser windows were not touched."
