#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_runtime_lib.sh"

wlv_mkdirs
OPEN_LOG="$WLV_LOG_DIR/wlv_app_open_$(date +%Y%m%d_%H%M%S).log"
exec >> "$OPEN_LOG" 2>&1

fail() {
  local message="$1"
  wlv_log "ERROR: $message"
  wlv_notify_error "$message\n\nLog:\n$OPEN_LOG"
  exit 1
}

wlv_log "==== WLV app open ===="
wlv_log "Timestamp: $(date)"
wlv_log "Frontend: $WLV_FRONTEND_URL"
wlv_log "Profile: $WLV_PROFILE_DIR"
wlv_log "Log: $OPEN_LOG"

if ! wlv_wait_for_url "$WLV_FRONTEND_URL" "Frontend" 15; then
  fail "Frontend is not available at $WLV_FRONTEND_URL. Start WLV runtime before opening the app window."
fi

rm -f "$WLV_PROFILE_DIR"/SingletonLock "$WLV_PROFILE_DIR"/SingletonSocket "$WLV_PROFILE_DIR"/SingletonCookie 2>/dev/null || true

if ! command -v open >/dev/null 2>&1; then
  fail "macOS open command is not available."
fi

open -na "Google Chrome" --args \
  --user-data-dir="$WLV_PROFILE_DIR" \
  --app="$WLV_FRONTEND_URL" \
  --no-first-run \
  --disable-features=Translate >/dev/null 2>&1 || fail "Unable to open Google Chrome for WLV."

for _ in $(seq 1 30); do
  if wlv_chrome_has_window; then
    wlv_log "Chrome WLV app window detected."
    exit 0
  fi
  if [ -n "$(wlv_chrome_profile_pids)" ]; then
    wlv_log "Chrome WLV profile detected."
    exit 0
  fi
  sleep 1
done

fail "Google Chrome did not open the WLV app profile/window."
