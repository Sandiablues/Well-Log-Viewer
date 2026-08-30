#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

is_wlv_listener() {
  local port="$1"
  local cmd="$2"

  case "$port:$cmd" in
    "$WLV_BACKEND_PORT:"*"$WLV_PROJECT"*) return 0 ;;
    "$WLV_BACKEND_PORT:"*"uvicorn app.main:app"*) return 0 ;;
    "$WLV_BACKEND_PORT:"*"uvicorn backend.app.main:app"*) return 0 ;;
    "$WLV_FRONTEND_PORT:"*"$WLV_PROJECT"*) return 0 ;;
    "$WLV_FRONTEND_PORT:"*"vite"*"--port $WLV_FRONTEND_PORT"*) return 0 ;;
    "$WLV_FRONTEND_PORT:"*"npm run dev"*) return 0 ;;
    *) return 1 ;;
  esac
}

for label in "$WLV_FRONTEND_LABEL" "$WLV_BACKEND_LABEL"; do
  launchctl bootout "$WLV_GUI_DOMAIN/$label" >/dev/null 2>&1 || true
done

sleep 1

for port in "$WLV_FRONTEND_PORT" "$WLV_BACKEND_PORT"; do
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if is_wlv_listener "$port" "$cmd"; then
      echo "Stopping WLV-owned listener on port $port: PID $pid"
      kill "$pid" 2>/dev/null || true
    else
      echo "Leaving non-WLV listener on port $port: PID $pid :: $cmd" >&2
    fi
  done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
done

sleep 2

for port in "$WLV_FRONTEND_PORT" "$WLV_BACKEND_PORT"; do
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if is_wlv_listener "$port" "$cmd"; then
      echo "Force-stopping WLV-owned listener on port $port: PID $pid"
      kill -9 "$pid" 2>/dev/null || true
    fi
  done < <(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
done

echo "WLV LaunchAgents and WLV-owned listeners stopped."
