#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

wlv_service_mkdirs

wlv_wait_url "$WLV_FRONTEND_URL" 15 "Frontend"

if [ ! -d "/Applications/Google Chrome.app" ] &&    [ ! -d "$HOME/Applications/Google Chrome.app" ]; then
  echo "ERROR: Google Chrome is not installed." >&2
  exit 1
fi

open -na "Google Chrome" --args --new-window "$WLV_FRONTEND_URL"

echo "Opened WLV in a new Chrome window."
