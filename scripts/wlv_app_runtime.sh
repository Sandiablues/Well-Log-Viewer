#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

wlv_service_mkdirs
RUNTIME_LOG="$WLV_LOG_DIR/wlv_app_launcher_$(date +%Y%m%d_%H%M%S).log"

{
  echo "==== Well Log Viewer app launcher ===="
  echo "Timestamp: $(date)"
  echo "Project: $WLV_PROJECT"
  echo "Launcher owns no backend, frontend, or browser lifecycle."

  "$WLV_PROJECT/scripts/wlv_service_start.sh"
  "$WLV_PROJECT/scripts/wlv_app_open.sh"

  echo "Launcher completed. WLV services remain supervised by launchd."
} 2>&1 | tee -a "$RUNTIME_LOG"
