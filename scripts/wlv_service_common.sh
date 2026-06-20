#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

WLV_PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
WLV_RUNTIME_DIR="$WLV_PROJECT/.wlv_runtime"
WLV_LOG_DIR="$WLV_RUNTIME_DIR/logs"
WLV_BACKEND_HOST="127.0.0.1"
WLV_BACKEND_PORT="8001"
WLV_FRONTEND_HOST="127.0.0.1"
WLV_FRONTEND_PORT="5173"
WLV_BACKEND_URL="http://${WLV_BACKEND_HOST}:${WLV_BACKEND_PORT}"
WLV_FRONTEND_URL="http://${WLV_FRONTEND_HOST}:${WLV_FRONTEND_PORT}"
WLV_BACKEND_LABEL="com.multiviewer.wlv.backend"
WLV_FRONTEND_LABEL="com.multiviewer.wlv.frontend"
WLV_GUI_DOMAIN="gui/$(id -u)"
WLV_BACKEND_PLIST="$HOME/Library/LaunchAgents/${WLV_BACKEND_LABEL}.plist"
WLV_FRONTEND_PLIST="$HOME/Library/LaunchAgents/${WLV_FRONTEND_LABEL}.plist"

wlv_service_mkdirs() {
  mkdir -p "$WLV_RUNTIME_DIR" "$WLV_LOG_DIR" "$HOME/Library/LaunchAgents"
}

wlv_service_assert_project() {
  [ -d "$WLV_PROJECT/.git" ] || {
    echo "ERROR: WLV project not found: $WLV_PROJECT" >&2
    return 1
  }
  [ -x "$WLV_PROJECT/backend/.venv/bin/python" ] || {
    echo "ERROR: backend Python missing: $WLV_PROJECT/backend/.venv/bin/python" >&2
    return 1
  }
  [ -x "/opt/homebrew/bin/node" ] || {
    echo "ERROR: native Node missing: /opt/homebrew/bin/node" >&2
    return 1
  }
  [ -f "$WLV_PROJECT/frontend/node_modules/vite/bin/vite.js" ] || {
    echo "ERROR: Vite runtime missing. Run npm install in frontend." >&2
    return 1
  }
}

wlv_launchd_loaded() {
  local label="$1"
  launchctl print "$WLV_GUI_DOMAIN/$label" >/dev/null 2>&1
}

wlv_wait_url() {
  local url="$1"
  local seconds="$2"
  local label="$3"
  local i
  for ((i=1; i<=seconds; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label: OK"
      return 0
    fi
    sleep 1
  done
  echo "$label: FAIL ($url)" >&2
  return 1
}

wlv_listener_pid() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

wlv_print_service_logs() {
  local service="$1"
  echo
  echo "---- $service stdout ----"
  tail -120 "$WLV_LOG_DIR/${service}_launchd.log" 2>/dev/null || true
  echo
  echo "---- $service stderr ----"
  tail -120 "$WLV_LOG_DIR/${service}_launchd.err.log" 2>/dev/null || true
}
