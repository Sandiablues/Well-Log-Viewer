#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_runtime_lib.sh"

QUIET=0
INCLUDE_LAUNCHER=1
for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --no-launcher) INCLUDE_LAUNCHER=0 ;;
    *) echo "Unknown argument: $arg"; exit 2 ;;
  esac
done

emit() {
  if [ "$QUIET" -ne 1 ]; then
    printf '%s\n' "$*"
  fi
}

wlv_mkdirs
cd "$WLV_PROJECT"
emit "WLV app runtime stop"
emit "Project: $WLV_PROJECT"

stop_from_pid_file() {
  local pid_file="$1"
  local label="$2"
  local pid=""
  pid="$(wlv_read_pid_file "$pid_file" 2>/dev/null || true)"
  [ -z "$pid" ] && return 0
  wlv_stop_pid_if_owned "$pid" "$label" "$QUIET"
}

stop_from_pid_file "$WLV_BACKEND_PID_FILE" "backend.pid"
stop_from_pid_file "$WLV_FRONTEND_PID_FILE" "frontend.pid"
stop_from_pid_file "$WLV_LEGACY_BACKEND_PID_FILE" ".wlv_backend.pid"
stop_from_pid_file "$WLV_LEGACY_FRONTEND_PID_FILE" ".wlv_frontend.pid"

if [ "$INCLUDE_LAUNCHER" -eq 1 ]; then
  launcher_pid="$(wlv_read_pid_file "$WLV_LAUNCHER_PID_FILE" 2>/dev/null || true)"
  if [ -n "$launcher_pid" ] && [ "$launcher_pid" != "$$" ]; then
    wlv_stop_pid_if_owned "$launcher_pid" "launcher.pid" "$QUIET"
  fi
fi

wlv_stop_chrome_profile "$QUIET"

sleep 1

for port in "$WLV_BACKEND_PORT" "$WLV_FRONTEND_PORT" 8000 5174 5175; do
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    wlv_stop_pid_if_owned "$pid" "listener on port $port" "$QUIET"
  done < <(wlv_listener_pids_on_port "$port")
done

sleep 2

for port in "$WLV_BACKEND_PORT" "$WLV_FRONTEND_PORT" 8000 5174 5175; do
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    wlv_force_stop_pid_if_owned "$pid" "listener on port $port" "$QUIET"
  done < <(wlv_listener_pids_on_port "$port")
done
wlv_force_stop_chrome_profile "$QUIET"

rm -f "$WLV_BACKEND_PID_FILE" "$WLV_FRONTEND_PID_FILE"
rm -f "$WLV_LEGACY_BACKEND_PID_FILE" "$WLV_LEGACY_FRONTEND_PID_FILE"
if [ "$INCLUDE_LAUNCHER" -eq 1 ]; then
  rm -f "$WLV_LAUNCHER_PID_FILE"
fi
rm -rf "$WLV_LOCK_DIR" 2>/dev/null || true

emit "WLV app runtime stopped."
