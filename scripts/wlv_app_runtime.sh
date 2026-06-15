#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
APP_NAME="Well Log Viewer"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8001"
FRONTEND_HOST="127.0.0.1"
FRONTEND_PORT="5173"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}"
RUNTIME_DIR="$PROJECT/.wlv_runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PROFILE_DIR="$RUNTIME_DIR/chrome-profile"
LOCK_DIR="$RUNTIME_DIR/launcher.lock"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
LAUNCHER_PID_FILE="$RUNTIME_DIR/launcher.pid"
STARTED_BACKEND=0
STARTED_FRONTEND=0

mkdir -p "$LOG_DIR" "$PROFILE_DIR"
LOG_FILE="$LOG_DIR/wlv_app_launcher_$(date +%Y%m%d_%H%M%S).log"
exec >> "$LOG_FILE" 2>&1

echo "==== Well Log Viewer app launcher ===="
echo "Timestamp: $(date)"
echo "Project: $PROJECT"
echo "Backend: $BACKEND_URL"
echo "Frontend: $FRONTEND_URL"
echo "Log: $LOG_FILE"

show_message() {
  local message="$1"
  if command -v osascript >/dev/null 2>&1; then
    local escaped_message escaped_title
    escaped_message="$(printf '%s' "$message" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    escaped_title="$(printf '%s' "$APP_NAME" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    osascript <<OSA >/dev/null 2>&1 || true
display dialog "$escaped_message" with title "$escaped_title" buttons {"OK"} default button "OK"
OSA
  fi
}

fail() {
  local message="$1"
  echo "ERROR: $message"
  show_message "$message\n\nLog:\n$LOG_FILE"
  exit 1
}

cleanup_on_failure() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "Launcher exiting with failure code $rc; stopping WLV-owned runtime."
    "$PROJECT/scripts/wlv_app_stop.sh" --quiet >/dev/null 2>&1 || true
  fi
  rm -rf "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup_on_failure EXIT

if [ ! -d "$PROJECT" ]; then
  fail "Project directory not found: $PROJECT"
fi
if [ ! -x "$PROJECT/backend/.venv/bin/python" ]; then
  fail "Backend Python venv not found at $PROJECT/backend/.venv/bin/python"
fi
if [ ! -d "$PROJECT/frontend" ]; then
  fail "Frontend directory not found: $PROJECT/frontend"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  existing=""
  [ -f "$LAUNCHER_PID_FILE" ] && existing="$(cat "$LAUNCHER_PID_FILE" 2>/dev/null || true)"
  if [ -n "$existing" ] && kill -0 "$existing" 2>/dev/null; then
    show_message "Well Log Viewer is already launching or running."
    exit 0
  fi
  rm -rf "$LOCK_DIR" 2>/dev/null || true
  mkdir "$LOCK_DIR" || fail "Unable to acquire launcher lock."
fi

echo $$ > "$LAUNCHER_PID_FILE"

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
    echo "Stopping WLV-owned $label PID $pid"
    kill "$pid" 2>/dev/null || true
  else
    echo "Leaving non-WLV $label PID $pid: $(process_command "$pid")"
  fi
}

stop_existing_wlv_runtime() {
  echo "---- stop existing WLV-owned runtime ----"
  "$PROJECT/scripts/wlv_app_stop.sh" --quiet || true
  sleep 1
}

assert_port_available_or_fail() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return 0
  fi
  echo "Port $port is occupied:"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if is_wlv_owned_pid "$pid"; then
      stop_pid_if_wlv_owned "$pid" "listener on port $port"
    else
      fail "Port $port is already in use by a non-WLV process. WLV will not kill SDV/SBLT/other apps. Stop that app or change WLV ports before launching."
    fi
  done <<< "$pids"
  sleep 1
  if lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    fail "Port $port is still occupied after WLV-owned cleanup."
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local seconds="$3"
  local i
  for ((i=1; i<=seconds; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label OK: $url"
      return 0
    fi
    sleep 1
  done
  return 1
}

chrome_profile_running() {
  ps aux | grep -F "$PROFILE_DIR" | grep -v grep >/dev/null 2>&1
}

chrome_has_wlv_window() {
  if ! command -v osascript >/dev/null 2>&1; then
    return 2
  fi
  local result
  result="$(osascript <<OSA 2>/dev/null || true
try
  tell application "Google Chrome"
    repeat with w in windows
      repeat with t in tabs of w
        if ((URL of t) as text) starts with "$FRONTEND_URL" then
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

stop_existing_wlv_runtime

# These are WLV-reserved ports. If another application owns either one, fail
# instead of killing it. This prevents SDV/SBLT conflicts.
assert_port_available_or_fail "$BACKEND_PORT"
assert_port_available_or_fail "$FRONTEND_PORT"

# Old WLV drift ports should not be used. Only kill them if they are clearly
# WLV-owned; otherwise leave them alone and report their presence in the log.
for legacy_port in 8000 5174 5175; do
  pids="$(lsof -tiTCP:"$legacy_port" -sTCP:LISTEN 2>/dev/null || true)"
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if is_wlv_owned_pid "$pid"; then
      stop_pid_if_wlv_owned "$pid" "legacy WLV listener on port $legacy_port"
    else
      echo "Non-WLV listener on legacy port $legacy_port left untouched: PID $pid $(process_command "$pid")"
    fi
  done <<< "$pids"
done

rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"

echo "---- start backend from project root ----"
cd "$PROJECT"
PYTHONPATH="$PROJECT" "$PROJECT/backend/.venv/bin/python" -m uvicorn backend.app.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  > "$LOG_DIR/wlv_backend.log" 2>&1 &
echo $! > "$BACKEND_PID_FILE"
STARTED_BACKEND=1

if ! wait_for_url "$BACKEND_URL/api/wlv/source-intake/health" "Backend source-intake health" 25; then
  tail -120 "$LOG_DIR/wlv_backend.log" || true
  fail "Backend did not pass source-intake health check on $BACKEND_URL."
fi
if ! wait_for_url "$BACKEND_URL/api/wlv/wdv/templates" "Backend WDV templates" 20; then
  tail -120 "$LOG_DIR/wlv_backend.log" || true
  fail "Backend did not pass WDV template check on $BACKEND_URL."
fi

echo "---- start frontend with strict port ----"
cd "$PROJECT/frontend"
npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort \
  > "$LOG_DIR/wlv_frontend.log" 2>&1 &
echo $! > "$FRONTEND_PID_FILE"
STARTED_FRONTEND=1

if ! wait_for_url "$FRONTEND_URL" "Frontend" 25; then
  tail -120 "$LOG_DIR/wlv_frontend.log" || true
  fail "Frontend did not start on fixed port $FRONTEND_URL."
fi

# Ensure Vite did not drift. strictPort should prevent this, but keep the guard.
for drift_port in 5174 5175; do
  pids="$(lsof -tiTCP:"$drift_port" -sTCP:LISTEN 2>/dev/null || true)"
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if is_wlv_owned_pid "$pid"; then
      fail "WLV unexpectedly started or left a frontend listener on drift port $drift_port."
    fi
  done <<< "$pids"
done

echo "---- open dedicated Chrome app window ----"
# Remove stale Chrome singleton files only inside the WLV-dedicated profile.
rm -f "$PROFILE_DIR"/SingletonLock "$PROFILE_DIR"/SingletonSocket "$PROFILE_DIR"/SingletonCookie 2>/dev/null || true
open -na "Google Chrome" --args \
  --user-data-dir="$PROFILE_DIR" \
  --app="$FRONTEND_URL" \
  --no-first-run \
  --disable-features=Translate >/dev/null 2>&1 || fail "Unable to open Google Chrome for WLV."

monitor_mode="profile"
for _ in $(seq 1 15); do
  if chrome_has_wlv_window; then
    monitor_mode="chrome-window"
    break
  fi
  if chrome_profile_running; then
    monitor_mode="profile"
    break
  fi
  sleep 1
done

echo "Monitor mode: $monitor_mode"
show_message "Well Log Viewer is running.\n\nClose the Well Log Viewer browser window to stop WLV backend/frontend."

if [ "$monitor_mode" = "chrome-window" ]; then
  while chrome_has_wlv_window; do
    sleep 2
  done
else
  while chrome_profile_running; do
    sleep 2
  done
fi

echo "WLV browser window/profile closed; stopping WLV-owned runtime."
"$PROJECT/scripts/wlv_app_stop.sh" --quiet || true
rm -rf "$LOCK_DIR" 2>/dev/null || true
rm -f "$LAUNCHER_PID_FILE" 2>/dev/null || true
trap - EXIT
exit 0
