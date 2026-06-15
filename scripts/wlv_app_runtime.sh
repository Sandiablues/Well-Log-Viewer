#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_runtime_lib.sh"

wlv_mkdirs
RUNTIME_LOG="$WLV_LOG_DIR/wlv_app_launcher_$(date +%Y%m%d_%H%M%S).log"
exec >> "$RUNTIME_LOG" 2>&1

fail() {
  local message="$1"
  wlv_log "ERROR: $message"
  wlv_notify_error "$message\n\nLog:\n$RUNTIME_LOG"
  exit 1
}

cleanup() {
  local rc=$?
  rm -rf "$WLV_LOCK_DIR" 2>/dev/null || true
  if [ "$rc" -ne 0 ]; then
    wlv_log "Launcher exiting with failure code $rc; stopping WLV-owned runtime."
    "$WLV_PROJECT/scripts/wlv_app_stop.sh" --quiet --no-launcher >/dev/null 2>&1 || true
  fi
  rm -f "$WLV_LAUNCHER_PID_FILE" 2>/dev/null || true
}
trap cleanup EXIT

wlv_log "==== Well Log Viewer app launcher ===="
wlv_log "Timestamp: $(date)"
wlv_log "Project: $WLV_PROJECT"
wlv_log "Backend: $WLV_BACKEND_URL"
wlv_log "Frontend: $WLV_FRONTEND_URL"
wlv_log "Log: $RUNTIME_LOG"

wlv_assert_project_ready || fail "Project runtime requirements are not available."

if ! mkdir "$WLV_LOCK_DIR" 2>/dev/null; then
  existing="$(wlv_read_pid_file "$WLV_LAUNCHER_PID_FILE" 2>/dev/null || true)"
  if [ -n "$existing" ] && wlv_pid_running "$existing"; then
    wlv_log "WLV launcher already running as PID $existing."
    exit 0
  fi
  rm -rf "$WLV_LOCK_DIR" 2>/dev/null || true
  mkdir "$WLV_LOCK_DIR" || fail "Unable to acquire launcher lock."
fi

echo $$ > "$WLV_LAUNCHER_PID_FILE"

wlv_log "---- stop previous WLV runtime without killing current launcher ----"
"$WLV_PROJECT/scripts/wlv_app_stop.sh" --quiet --no-launcher || true

wlv_log "---- start backend/frontend ----"
"$WLV_PROJECT/scripts/wlv_app_start.sh" || fail "Backend/frontend startup failed."

wlv_log "---- open WLV browser window ----"
"$WLV_PROJECT/scripts/wlv_app_open.sh" || fail "Browser open failed."

monitor_mode="profile"
for _ in $(seq 1 20); do
  if wlv_chrome_has_window; then
    monitor_mode="window"
    break
  fi
  if [ -n "$(wlv_chrome_profile_pids)" ]; then
    monitor_mode="profile"
    break
  fi
  sleep 1
done

wlv_log "Monitor mode: $monitor_mode"

if [ "$monitor_mode" = "window" ]; then
  while wlv_chrome_has_window; do
    sleep 2
  done
else
  while [ -n "$(wlv_chrome_profile_pids)" ]; do
    sleep 2
  done
fi

wlv_log "WLV app window/profile closed; stopping WLV-owned runtime."
"$WLV_PROJECT/scripts/wlv_app_stop.sh" --quiet --no-launcher || true
rm -rf "$WLV_LOCK_DIR" 2>/dev/null || true
rm -f "$WLV_LAUNCHER_PID_FILE" 2>/dev/null || true
trap - EXIT
exit 0
