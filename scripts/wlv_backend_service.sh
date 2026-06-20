#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

wlv_service_mkdirs
wlv_service_assert_project

cd "$WLV_PROJECT/backend"
export PYTHONPATH="$WLV_PROJECT/backend"
export WLV_BACKEND_HOST
export WLV_BACKEND_PORT

exec /usr/bin/arch -arm64 \
  "$WLV_PROJECT/backend/.venv/bin/python" \
  -m uvicorn app.main:app \
  --host "$WLV_BACKEND_HOST" \
  --port "$WLV_BACKEND_PORT"
