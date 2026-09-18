#!/bin/bash
set -euo pipefail

PID_FILE="/Users/donarcher/Applications/MultiViewer/seismic_viewer_project/run/backend.pid"
BACKEND_LOG="/Users/donarcher/Applications/MultiViewer/seismic_viewer_project/logs/backend.log"

echo "=== MultiViewer Runtime Status ==="

if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" >/dev/null 2>&1; then
  echo "Backend: running, PID $(cat "$PID_FILE")"
else
  echo "Backend: not running"
fi

echo ""
echo "Project:"
echo "/Users/donarcher/Applications/MultiViewer/seismic_viewer_project"

echo ""
echo "Port 8000 listeners:"
lsof -nP -iTCP:8000 -sTCP:LISTEN || true

echo ""
echo "Recent backend log:"
tail -60 "$BACKEND_LOG" 2>/dev/null || true
