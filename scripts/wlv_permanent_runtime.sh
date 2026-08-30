#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
RUNTIME_DIR="$PROJECT/.wlv_runtime"
LOG_DIR="$RUNTIME_DIR/logs"
LOCK_DIR="$RUNTIME_DIR/permanent_launcher.lock"

BACKEND_HOST="${WLV_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${WLV_BACKEND_PORT:-8001}"
FRONTEND_HOST="${WLV_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${WLV_FRONTEND_PORT:-5173}"

BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}"

BACKEND_LABEL="com.multiviewer.wlv.backend.permanent"
FRONTEND_LABEL="com.multiviewer.wlv.frontend.permanent"
LEGACY_LABELS=(
  "com.multiviewer.wlv.backend"
  "com.multiviewer.wlv.frontend"
)

BACKEND_PLIST="$HOME/Library/LaunchAgents/${BACKEND_LABEL}.plist"
FRONTEND_PLIST="$HOME/Library/LaunchAgents/${FRONTEND_LABEL}.plist"
DOMAIN="gui/$(id -u)"
CONTROL_LOG="$LOG_DIR/wlv_permanent_launcher.log"

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"
touch "$CONTROL_LOG"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$CONTROL_LOG"
}

fail() {
  log "ERROR: $*"
  exit 1
}

command_for_pid() {
  /bin/ps -p "$1" -o command= 2>/dev/null || true
}

cwd_for_pid() {
  /usr/sbin/lsof -a -p "$1" -d cwd -Fn 2>/dev/null |
    /usr/bin/awk 'BEGIN{cwd=""} /^n/{cwd=substr($0,2)} END{print cwd}'
}

listener_pids() {
  /usr/sbin/lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

pid_running() {
  local pid="${1:-}"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

backend_process_matches_project() {
  local pid="$1" cmd cwd
  cmd="$(command_for_pid "$pid")"
  cwd="$(cwd_for_pid "$pid")"
  [[ "$cwd" == "$PROJECT/backend" ]] || return 1
  case "$cmd" in
    *uvicorn*"app.main:app"*"--port $BACKEND_PORT"*) return 0 ;;
    *) return 1 ;;
  esac
}

frontend_process_matches_project() {
  local pid="$1" cmd cwd
  cmd="$(command_for_pid "$pid")"
  cwd="$(cwd_for_pid "$pid")"
  [[ "$cwd" == "$PROJECT/frontend" ]] || return 1
  case "$cmd" in
    *vite*"--port $FRONTEND_PORT"*) return 0 ;;
    *node*"$PROJECT/frontend/node_modules/vite/bin/vite.js"*"$FRONTEND_PORT"*) return 0 ;;
    *) return 1 ;;
  esac
}

stop_pid() {
  local pid="$1" label="$2"
  pid_running "$pid" || return 0
  log "Stopping $label PID $pid"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8; do
    pid_running "$pid" || return 0
    sleep 0.25
  done
  log "Force-stopping $label PID $pid"
  kill -KILL "$pid" 2>/dev/null || true
}

job_loaded() {
  /bin/launchctl print "$DOMAIN/$1" >/dev/null 2>&1
}

bootout_job() {
  local label="$1"
  /bin/launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
}

unload_legacy_jobs() {
  local label
  for label in "${LEGACY_LABELS[@]}"; do
    bootout_job "$label"
  done
}

health_ok() {
  local url="$1"
  /usr/bin/curl --max-time 2 -fsS "$url" >/dev/null 2>&1
}


open_frontend_window() {
  local url="$1"
  if [[ -d "/Applications/Google Chrome.app" ]]; then
    /usr/bin/osascript >/dev/null 2>&1 <<APPLESCRIPT || /usr/bin/open "$url"
tell application "Google Chrome"
  make new window
  set URL of active tab of front window to "$url"
  activate
end tell
APPLESCRIPT
  else
    /usr/bin/osascript >/dev/null 2>&1 <<APPLESCRIPT || /usr/bin/open "$url"
tell application "Safari"
  make new document with properties {URL:"$url"}
  activate
end tell
APPLESCRIPT
  fi
}

wait_health() {
  local url="$1" label="$2" attempts="${3:-80}"
  local i
  for ((i=1; i<=attempts; i++)); do
    if health_ok "$url"; then
      log "$label healthy: $url"
      return 0
    fi
    sleep 0.25
  done
  log "$label failed health check: $url"
  return 1
}

validate_prerequisites() {
  [[ -d "$PROJECT" ]] || fail "Project directory not found: $PROJECT"
  [[ -x "$PROJECT/backend/.venv/bin/python" ]] || fail "Backend Python missing: $PROJECT/backend/.venv/bin/python"
  [[ -f "$PROJECT/frontend/node_modules/vite/bin/vite.js" ]] || fail "Vite runtime missing: $PROJECT/frontend/node_modules/vite/bin/vite.js"
  [[ -x "$PROJECT/scripts/wlv_runtime_backend_service.sh" ]] || fail "Backend service script missing"
  [[ -x "$PROJECT/scripts/wlv_runtime_frontend_service.sh" ]] || fail "Frontend service script missing"
  [[ -f "$BACKEND_PLIST" ]] || fail "Backend LaunchAgent missing: $BACKEND_PLIST"
  [[ -f "$FRONTEND_PLIST" ]] || fail "Frontend LaunchAgent missing: $FRONTEND_PLIST"
}

reclaim_port() {
  local port="$1" kind="$2" pid cmd
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    if [[ "$kind" == "backend" ]] && backend_process_matches_project "$pid"; then
      stop_pid "$pid" "same-project orphaned backend"
    elif [[ "$kind" == "frontend" ]] && frontend_process_matches_project "$pid"; then
      stop_pid "$pid" "same-project orphaned frontend"
    else
      cmd="$(command_for_pid "$pid")"
      fail "Port $port is occupied by an unrelated process: PID $pid :: $cmd"
    fi
  done < <(listener_pids "$port")
}

runtime_healthy() {
  job_loaded "$BACKEND_LABEL" &&
  job_loaded "$FRONTEND_LABEL" &&
  health_ok "$BACKEND_URL/health" &&
  health_ok "$FRONTEND_URL"
}

bootstrap_job() {
  local label="$1" plist="$2"
  if job_loaded "$label"; then
    return 0
  fi
  /bin/launchctl bootstrap "$DOMAIN" "$plist" ||
    fail "Unable to bootstrap $label"
}

start_runtime() {
  validate_prerequisites
  unload_legacy_jobs

  if runtime_healthy; then
    log "WLV runtime already healthy; no duplicate services started."
    open_frontend_window "$FRONTEND_URL"
    return 0
  fi

  bootout_job "$FRONTEND_LABEL"
  bootout_job "$BACKEND_LABEL"
  reclaim_port "$FRONTEND_PORT" frontend
  reclaim_port "$BACKEND_PORT" backend

  bootstrap_job "$BACKEND_LABEL" "$BACKEND_PLIST"
  /bin/launchctl kickstart -k "$DOMAIN/$BACKEND_LABEL" >/dev/null
  if ! wait_health "$BACKEND_URL/health" "Backend" 120; then
    tail -120 "$LOG_DIR/wlv_backend.err.log" 2>/dev/null || true
    bootout_job "$BACKEND_LABEL"
    fail "Backend did not become healthy."
  fi

  bootstrap_job "$FRONTEND_LABEL" "$FRONTEND_PLIST"
  /bin/launchctl kickstart -k "$DOMAIN/$FRONTEND_LABEL" >/dev/null
  if ! wait_health "$FRONTEND_URL" "Frontend" 120; then
    tail -120 "$LOG_DIR/wlv_frontend.err.log" 2>/dev/null || true
    bootout_job "$FRONTEND_LABEL"
    bootout_job "$BACKEND_LABEL"
    fail "Frontend did not become healthy."
  fi

  log "WLV permanent runtime started successfully."
  open_frontend_window "$FRONTEND_URL"
}

stop_runtime() {
  unload_legacy_jobs
  bootout_job "$FRONTEND_LABEL"
  bootout_job "$BACKEND_LABEL"

  # Reclaim only processes proven to belong to this exact project.
  local pid
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && frontend_process_matches_project "$pid" &&
      stop_pid "$pid" "same-project frontend"
  done < <(listener_pids "$FRONTEND_PORT")
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && backend_process_matches_project "$pid" &&
      stop_pid "$pid" "same-project backend"
  done < <(listener_pids "$BACKEND_PORT")

  log "WLV runtime stopped."
}

status_runtime() {
  echo "WLV permanent runtime"
  echo "Project:  $PROJECT"
  echo "Backend:  $BACKEND_URL"
  echo "Frontend: $FRONTEND_URL"
  echo "Backend LaunchAgent: $([[ $(job_loaded "$BACKEND_LABEL"; echo $?) -eq 0 ]] && echo loaded || echo stopped)"
  echo "Frontend LaunchAgent: $([[ $(job_loaded "$FRONTEND_LABEL"; echo $?) -eq 0 ]] && echo loaded || echo stopped)"
  if runtime_healthy; then
    echo "Status: healthy"
    return 0
  fi
  echo "Status: stopped or unhealthy"
  return 1
}

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    echo $$ > "$LOCK_DIR/pid"
    trap 'rm -rf "$LOCK_DIR"' EXIT
    return 0
  fi

  local lock_pid=""
  [[ -f "$LOCK_DIR/pid" ]] && lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if pid_running "$lock_pid"; then
    fail "Another WLV launcher operation is already running."
  fi

  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" || fail "Unable to create launcher lock."
  echo $$ > "$LOCK_DIR/pid"
  trap 'rm -rf "$LOCK_DIR"' EXIT
}

COMMAND="${1:-start}"
case "$COMMAND" in
  start|open)
    acquire_lock
    start_runtime
    ;;
  stop)
    acquire_lock
    stop_runtime
    ;;
  restart)
    acquire_lock
    validate_prerequisites
    stop_runtime
    start_runtime
    ;;
  status)
    status_runtime
    ;;
  repair)
    acquire_lock
    stop_runtime
    start_runtime
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|repair}"
    exit 2
    ;;
esac
