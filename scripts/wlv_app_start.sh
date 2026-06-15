#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_runtime_lib.sh"

wlv_mkdirs
START_LOG="$WLV_LOG_DIR/wlv_app_start_$(date +%Y%m%d_%H%M%S).log"
exec >> "$START_LOG" 2>&1

fail() {
  local message="$1"
  wlv_log "ERROR: $message"
  wlv_notify_error "$message\n\nLog:\n$START_LOG"
  exit 1
}

wlv_log "==== WLV runtime start ===="
wlv_log "Timestamp: $(date)"
wlv_log "Project: $WLV_PROJECT"
wlv_log "Backend: $WLV_BACKEND_URL"
wlv_log "Frontend: $WLV_FRONTEND_URL"
wlv_log "Log: $START_LOG"
wlv_log "Shell arch: $(uname -m 2>/dev/null || echo unknown)"
wlv_log "Native runtime mode: $(wlv_native_mode_label)"

wlv_assert_project_ready || fail "Project runtime requirements are not available."
cd "$WLV_PROJECT"

assert_port_free_or_owned_cleanup() {
  local port="$1"
  local pid=""
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if wlv_pid_is_wlv_owned "$pid"; then
      wlv_stop_pid_if_owned "$pid" "listener on port $port" 0
    else
      wlv_log "Port $port is occupied:"
      lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
      fail "Port $port is already in use by a non-WLV process. WLV will not kill SDV/SBLT/other apps."
    fi
  done < <(wlv_listener_pids_on_port "$port")

  sleep 1
  if [ -n "$(wlv_listener_pids_on_port "$port")" ]; then
    fail "Port $port is still occupied after WLV-owned cleanup."
  fi
}

assert_port_free_or_owned_cleanup "$WLV_BACKEND_PORT"
assert_port_free_or_owned_cleanup "$WLV_FRONTEND_PORT"

for legacy_port in 8000 5174 5175; do
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if wlv_pid_is_wlv_owned "$pid"; then
      wlv_stop_pid_if_owned "$pid" "legacy WLV listener on port $legacy_port" 0
    else
      wlv_log "Non-WLV listener on legacy port $legacy_port left untouched: PID $pid $(wlv_process_command "$pid")"
    fi
  done < <(wlv_listener_pids_on_port "$legacy_port")
done

rm -f "$WLV_BACKEND_PID_FILE" "$WLV_FRONTEND_PID_FILE"

wlv_log "---- backend Python architecture preflight ----"
cd "$WLV_PROJECT"
if ! PYTHONPATH="$WLV_PROJECT" wlv_run_native "$WLV_PROJECT/backend/.venv/bin/python" -c 'import platform; import pydantic_core; print("python_arch=" + platform.machine()); print("pydantic_core=ok")'; then
  fail "Backend Python architecture/dependency preflight failed. See $START_LOG."
fi

wlv_log "---- start backend ----"
cd "$WLV_PROJECT"
PYTHONPATH="$WLV_PROJECT" wlv_run_native "$WLV_PROJECT/backend/.venv/bin/python" -m uvicorn backend.app.main:app \
  --host "$WLV_BACKEND_HOST" \
  --port "$WLV_BACKEND_PORT" \
  > "$WLV_LOG_DIR/wlv_backend.log" 2>&1 &
echo $! > "$WLV_BACKEND_PID_FILE"

if ! wlv_wait_for_url "$WLV_BACKEND_URL/api/wlv/source-intake/health" "Backend source-intake health" 30; then
  tail -160 "$WLV_LOG_DIR/wlv_backend.log" || true
  fail "Backend did not pass source-intake health check on $WLV_BACKEND_URL."
fi

if ! wlv_wait_for_url "$WLV_BACKEND_URL/api/wlv/wdv/templates" "Backend WDV templates" 30; then
  tail -160 "$WLV_LOG_DIR/wlv_backend.log" || true
  fail "Backend did not pass WDV template check on $WLV_BACKEND_URL."
fi

wlv_log "---- start frontend ----"
cd "$WLV_PROJECT/frontend"
wlv_run_native npm run dev -- --host "$WLV_FRONTEND_HOST" --port "$WLV_FRONTEND_PORT" --strictPort \
  > "$WLV_LOG_DIR/wlv_frontend.log" 2>&1 &
echo $! > "$WLV_FRONTEND_PID_FILE"

if ! wlv_wait_for_url "$WLV_FRONTEND_URL" "Frontend" 35; then
  tail -160 "$WLV_LOG_DIR/wlv_frontend.log" || true
  fail "Frontend did not start on fixed port $WLV_FRONTEND_URL."
fi

for drift_port in 5174 5175; do
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if wlv_pid_is_wlv_owned "$pid"; then
      fail "WLV unexpectedly has a frontend listener on drift port $drift_port."
    fi
  done < <(wlv_listener_pids_on_port "$drift_port")
done

wlv_log "WLV runtime start completed."
