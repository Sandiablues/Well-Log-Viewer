#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
HOST="${WLV_BACKEND_HOST:-127.0.0.1}"
PORT="${WLV_BACKEND_PORT:-8010}"
PYTHON="$PROJECT/backend/.venv/bin/python"
SCRIPT_DIR="$PROJECT/scripts"

cd "$PROJECT"

if [ ! -x "$PYTHON" ]; then
  python3 -m venv "$PROJECT/backend/.venv"
fi

"$PYTHON" -m pip install --upgrade pip setuptools wheel >/dev/null
(cd "$PROJECT/backend" && "$PYTHON" -m pip install -e ".[dev]" >/dev/null)
rm -rf "$PROJECT/backend/well_log_viewer_backend.egg-info"

export PYTHONPATH="$PROJECT"
"$PYTHON" -m pytest backend/tests

"$SCRIPT_DIR/wlv_backend_restart.sh"
trap '"$SCRIPT_DIR/wlv_backend_stop.sh" >/dev/null 2>&1 || true' EXIT

for endpoint in \
  "/health" \
  "/api/wlv/health" \
  "/api/wlv/system/status" \
  "/api/wlv/wells" \
  "/api/wlv/wells/forge-21-31" \
  "/api/wlv/wells/forge-21-31/curves" \
  "/api/wlv/wells/forge-21-31/interval-columns" \
  "/api/wlv/wells/forge-21-31/viewer-package"
do
  code="$(curl -s -o /tmp/wlv_backend_validate_response.json -w '%{http_code}' "http://$HOST:$PORT$endpoint")"
  echo "$endpoint $code"
  if [ "$code" != "200" ]; then
    cat /tmp/wlv_backend_validate_response.json || true
    exit 1
  fi
done

echo "WLV backend runtime validation passed."
