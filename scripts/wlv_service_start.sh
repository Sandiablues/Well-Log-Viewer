#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

wlv_service_mkdirs
wlv_service_assert_project

BACKEND_HEALTH="$WLV_BACKEND_URL/api/wlv/source-intake/health"
FRONTEND_HEALTH="$WLV_FRONTEND_URL"

backend_loaded=0
frontend_loaded=0
wlv_launchd_loaded "$WLV_BACKEND_LABEL" && backend_loaded=1
wlv_launchd_loaded "$WLV_FRONTEND_LABEL" && frontend_loaded=1

if [ "$backend_loaded" -ne 1 ] || [ "$frontend_loaded" -ne 1 ]; then
  "$WLV_PROJECT/scripts/install_wlv_launch_agents.sh"
else
  if ! curl -fsS "$BACKEND_HEALTH" >/dev/null 2>&1; then
    echo "Backend LaunchAgent is loaded but unhealthy; restarting backend only."
    launchctl kickstart -k "$WLV_GUI_DOMAIN/$WLV_BACKEND_LABEL"
  else
    echo "Backend already healthy; leaving PID unchanged."
  fi

  if ! curl -fsS "$FRONTEND_HEALTH" >/dev/null 2>&1; then
    echo "Frontend LaunchAgent is loaded but unhealthy; restarting frontend only."
    launchctl kickstart -k "$WLV_GUI_DOMAIN/$WLV_FRONTEND_LABEL"
  else
    echo "Frontend already healthy; leaving PID unchanged."
  fi
fi

if ! wlv_wait_url "$BACKEND_HEALTH" 40 "Backend source-intake"; then
  wlv_print_service_logs "wlv_backend"
  exit 1
fi
if ! wlv_wait_url "$WLV_BACKEND_URL/api/wlv/wdv/templates" 40 "Backend WDV templates"; then
  wlv_print_service_logs "wlv_backend"
  exit 1
fi
if ! wlv_wait_url "$FRONTEND_HEALTH" 40 "Frontend"; then
  wlv_print_service_logs "wlv_frontend"
  exit 1
fi

echo "WLV services are healthy."
