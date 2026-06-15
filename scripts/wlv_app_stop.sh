#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
RUNTIME_DIR="$PROJECT/.wlv_runtime"
PROFILE_DIR="$RUNTIME_DIR/chrome-profile"
QUIET=0
for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    *) echo "Unknown argument: $arg"; exit 2 ;;
  esac
done

log() {
  if [ "$QUIET" -ne 1 ]; then
    echo "$@"
  fi
}

process_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null || true
}

is_wlv_owned_pid() {
  local pid="$1"
  local cmd
  cmd="$(process_command "$pid")"
  case "$cmd" in
    *"$PROJECT"*|*"$PROFILE_DIR"*) return 0 ;;
    *) return 1 ;;
  esac
}

stop_pid_if_wlv_owned() {
  local pid="$1"
  local label="$2"
  if [ -z "${pid:-}" ] || ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  if is_wlv_owned_pid "$pid"; then
    log "Stopping WLV-owned $label PID $pid"
    kill "$pid" 2>/dev/null || true
  else
    log "Leaving non-WLV $label PID $pid: $(process_command "$pid")"
  fi
}

cd "$PROJECT"
log "WLV app runtime stop"
log "Project: $PROJECT"

for pid_file in \
  "$RUNTIME_DIR/backend.pid" \
  "$RUNTIME_DIR/frontend.pid" \
  "$RUNTIME_DIR/launcher.pid" \
  "$PROJECT/.wlv_backend.pid" \
  "$PROJECT/.wlv_frontend.pid"
do
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    stop_pid_if_wlv_owned "$pid" "$(basename "$pid_file")"
  fi
done

# Stop dedicated WLV Chrome profile processes only. This does not touch normal
# Chrome, SDV, or SBLT browser sessions.
ps aux | grep -F "$PROFILE_DIR" | grep -v grep | awk '{print $2}' | while IFS= read -r pid; do
  stop_pid_if_wlv_owned "$pid" "Chrome profile"
done

sleep 1

# Clear only WLV-owned listeners. Non-WLV listeners are reported and left alone.
for port in 8001 5173 8000 5174 5175; do
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    stop_pid_if_wlv_owned "$pid" "listener on port $port"
  done
done

sleep 2

for port in 8001 5173 8000 5174 5175; do
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if is_wlv_owned_pid "$pid"; then
      log "Force-stopping WLV-owned listener on port $port PID $pid"
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
done

rm -f "$RUNTIME_DIR/backend.pid" "$RUNTIME_DIR/frontend.pid" "$RUNTIME_DIR/launcher.pid"
rm -f "$PROJECT/.wlv_backend.pid" "$PROJECT/.wlv_frontend.pid"
rm -rf "$RUNTIME_DIR/launcher.lock" 2>/dev/null || true

log "WLV app runtime stopped."
