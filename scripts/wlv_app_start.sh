#!/usr/bin/env bash
set -euo pipefail
PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
exec "$PROJECT/scripts/wlv_service_start.sh"
