#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

for label in "$WLV_FRONTEND_LABEL" "$WLV_BACKEND_LABEL"; do
  launchctl bootout "$WLV_GUI_DOMAIN/$label" >/dev/null 2>&1 || true
done

sleep 1

for port in "$WLV_FRONTEND_PORT" "$WLV_BACKEND_PORT"; do
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    case "$cmd" in
      *"$WLV_PROJECT"*)
        kill "$pid" 2>/dev/null || true
        ;;
      *)
        echo "Leaving non-WLV listener on port $port: PID $pid :: $cmd" >&2
        ;;
    esac
  done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
done

echo "WLV LaunchAgents stopped."
