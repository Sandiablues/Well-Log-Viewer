#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

wlv_service_mkdirs
wlv_service_assert_project

cd "$WLV_PROJECT/frontend"

exec /usr/bin/arch -arm64 \
  /opt/homebrew/bin/node \
  "$WLV_PROJECT/frontend/node_modules/vite/bin/vite.js" \
  --host "$WLV_FRONTEND_HOST" \
  --port "$WLV_FRONTEND_PORT" \
  --strictPort
