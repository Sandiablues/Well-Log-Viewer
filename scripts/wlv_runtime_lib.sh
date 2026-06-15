#!/usr/bin/env bash

# Shared WLV local-runtime helpers.
# This file is sourced by WLV runtime scripts and must not execute actions at
# source time beyond defining constants/functions.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

WLV_PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
WLV_APP_NAME="Well Log Viewer"
WLV_BACKEND_HOST="127.0.0.1"
WLV_BACKEND_PORT="8001"
WLV_FRONTEND_HOST="127.0.0.1"
WLV_FRONTEND_PORT="5173"
WLV_BACKEND_URL="http://${WLV_BACKEND_HOST}:${WLV_BACKEND_PORT}"
WLV_FRONTEND_URL="http://${WLV_FRONTEND_HOST}:${WLV_FRONTEND_PORT}"
WLV_RUNTIME_DIR="$WLV_PROJECT/.wlv_runtime"
WLV_LOG_DIR="$WLV_RUNTIME_DIR/logs"
WLV_PROFILE_DIR="$WLV_RUNTIME_DIR/chrome-profile"
WLV_LOCK_DIR="$WLV_RUNTIME_DIR/launcher.lock"
WLV_BACKEND_PID_FILE="$WLV_RUNTIME_DIR/backend.pid"
WLV_FRONTEND_PID_FILE="$WLV_RUNTIME_DIR/frontend.pid"
WLV_LAUNCHER_PID_FILE="$WLV_RUNTIME_DIR/launcher.pid"
WLV_LEGACY_BACKEND_PID_FILE="$WLV_PROJECT/.wlv_backend.pid"
WLV_LEGACY_FRONTEND_PID_FILE="$WLV_PROJECT/.wlv_frontend.pid"

# Force child runtimes to native arm64 on Apple Silicon when available.
# This prevents Finder/LaunchServices/Rosetta-inherited x86_64 launches from
# loading an arm64 Python virtualenv as x86_64.
WLV_FORCE_ARM64="${WLV_FORCE_ARM64:-auto}"

wlv_host_supports_arm64() {
  [ "$(sysctl -in hw.optional.arm64 2>/dev/null || echo 0)" = "1" ]
}

wlv_should_run_arm64() {
  case "$WLV_FORCE_ARM64" in
    1|true|TRUE|yes|YES|arm64) wlv_host_supports_arm64 ;;
    0|false|FALSE|no|NO|off|OFF) return 1 ;;
    auto|AUTO|'') wlv_host_supports_arm64 ;;
    *) wlv_host_supports_arm64 ;;
  esac
}

wlv_run_native() {
  if wlv_should_run_arm64 && [ -x /usr/bin/arch ]; then
    /usr/bin/arch -arm64 "$@"
  else
    "$@"
  fi
}

wlv_native_mode_label() {
  if wlv_should_run_arm64 && [ -x /usr/bin/arch ]; then
    printf 'arm64-forced'
  else
    printf 'process-default'
  fi
}

wlv_mkdirs() {
  mkdir -p "$WLV_RUNTIME_DIR" "$WLV_LOG_DIR" "$WLV_PROFILE_DIR"
}

wlv_log() {
  printf '%s\n' "$*"
}

wlv_read_pid_file() {
  local pid_file="$1"
  local pid=""
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file" 2>/dev/null || true)"
  fi
  case "$pid" in
    ''|*[!0-9]*) return 1 ;;
    *) printf '%s\n' "$pid" ;;
  esac
}

wlv_process_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null || true
}

wlv_pid_running() {
  local pid="$1"
  [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null
}

wlv_command_is_wlv_owned() {
  local cmd="$1"
  case "$cmd" in
    *"$WLV_PROJECT"*) return 0 ;;
    *"$WLV_PROFILE_DIR"*) return 0 ;;
    *"backend.app.main:app"*"--host $WLV_BACKEND_HOST"*"--port $WLV_BACKEND_PORT"*) return 0 ;;
    *"vite"*"--host $WLV_FRONTEND_HOST"*"--port $WLV_FRONTEND_PORT"*) return 0 ;;
    *"npm"*"run"*"dev"*) return 0 ;;
    *"WellLogViewerLauncher"*) return 0 ;;
    *"wlv_app_runtime.sh"*) return 0 ;;
    *) return 1 ;;
  esac
}

wlv_pid_is_wlv_owned() {
  local pid="$1"
  local cmd=""
  if ! wlv_pid_running "$pid"; then
    return 1
  fi
  cmd="$(wlv_process_command "$pid")"
  wlv_command_is_wlv_owned "$cmd"
}

wlv_stop_pid_if_owned() {
  local pid="$1"
  local label="$2"
  local quiet="${3:-0}"
  if [ -z "${pid:-}" ] || ! wlv_pid_running "$pid"; then
    return 0
  fi
  if wlv_pid_is_wlv_owned "$pid"; then
    [ "$quiet" = "1" ] || wlv_log "Stopping WLV-owned $label PID $pid"
    kill "$pid" 2>/dev/null || true
  else
    [ "$quiet" = "1" ] || wlv_log "Leaving non-WLV $label PID $pid: $(wlv_process_command "$pid")"
  fi
}

wlv_force_stop_pid_if_owned() {
  local pid="$1"
  local label="$2"
  local quiet="${3:-0}"
  if [ -z "${pid:-}" ] || ! wlv_pid_running "$pid"; then
    return 0
  fi
  if wlv_pid_is_wlv_owned "$pid"; then
    [ "$quiet" = "1" ] || wlv_log "Force-stopping WLV-owned $label PID $pid"
    kill -9 "$pid" 2>/dev/null || true
  fi
}

wlv_listener_pids_on_port() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

wlv_chrome_profile_pids() {
  ps -axo pid=,command= | awk -v profile="$WLV_PROFILE_DIR" 'index($0, profile) {print $1}'
}

wlv_stop_chrome_profile() {
  local quiet="${1:-0}"
  local pid=""
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    wlv_stop_pid_if_owned "$pid" "Chrome profile" "$quiet"
  done < <(wlv_chrome_profile_pids)
}

wlv_force_stop_chrome_profile() {
  local quiet="${1:-0}"
  local pid=""
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    wlv_force_stop_pid_if_owned "$pid" "Chrome profile" "$quiet"
  done < <(wlv_chrome_profile_pids)
}

wlv_wait_for_url() {
  local url="$1"
  local label="$2"
  local seconds="$3"
  local i=0
  for ((i=1; i<=seconds; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      wlv_log "$label OK: $url"
      return 0
    fi
    sleep 1
  done
  return 1
}

wlv_notify_error() {
  local message="$1"
  if command -v osascript >/dev/null 2>&1; then
    local escaped_message escaped_title
    escaped_message="$(printf '%s' "$message" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    escaped_title="$(printf '%s' "$WLV_APP_NAME" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    osascript <<OSA >/dev/null 2>&1 || true
display dialog "$escaped_message" with title "$escaped_title" buttons {"OK"} default button "OK"
OSA
  fi
}

wlv_chrome_has_window() {
  if ! command -v osascript >/dev/null 2>&1; then
    return 2
  fi
  local result=""
  result="$(osascript <<OSA 2>/dev/null || true
try
  tell application "Google Chrome"
    repeat with w in windows
      repeat with t in tabs of w
        if ((URL of t) as text) starts with "$WLV_FRONTEND_URL" then
          return "yes"
        end if
      end repeat
    end repeat
  end tell
  return "no"
on error
  return "unknown"
end try
OSA
)"
  case "$result" in
    yes) return 0 ;;
    no) return 1 ;;
    *) return 2 ;;
  esac
}

wlv_assert_project_ready() {
  if [ ! -d "$WLV_PROJECT" ]; then
    wlv_log "ERROR: Project directory not found: $WLV_PROJECT"
    return 1
  fi
  if [ ! -x "$WLV_PROJECT/backend/.venv/bin/python" ]; then
    wlv_log "ERROR: Backend Python venv not found: $WLV_PROJECT/backend/.venv/bin/python"
    return 1
  fi
  if [ ! -d "$WLV_PROJECT/frontend" ]; then
    wlv_log "ERROR: Frontend directory not found: $WLV_PROJECT/frontend"
    return 1
  fi
}
