#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_runtime_lib.sh"

wlv_mkdirs
cd "$WLV_PROJECT"

echo "WLV app runtime status"
echo "Project: $WLV_PROJECT"
echo "Backend:  $WLV_BACKEND_URL"
echo "Frontend: $WLV_FRONTEND_URL"

echo
echo "---- git ----"
git status --short || true
git log --oneline --decorate -5 || true

echo
echo "---- PID files ----"
for f in "$WLV_BACKEND_PID_FILE" "$WLV_FRONTEND_PID_FILE" "$WLV_LAUNCHER_PID_FILE" "$WLV_LEGACY_BACKEND_PID_FILE" "$WLV_LEGACY_FRONTEND_PID_FILE"; do
  if [ -f "$f" ]; then
    pid="$(wlv_read_pid_file "$f" 2>/dev/null || true)"
    if [ -n "$pid" ] && wlv_pid_running "$pid"; then
      echo "$f -> $pid RUNNING :: $(wlv_process_command "$pid")"
    else
      echo "$f -> ${pid:-empty} NOT RUNNING"
    fi
  else
    echo "$f -> missing"
  fi
done

echo
echo "---- WLV ports and possible conflicts ----"
for port in "$WLV_BACKEND_PORT" "$WLV_FRONTEND_PORT" 8000 5174 5175; do
  echo "### port $port"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || echo "no listener"
done

echo
echo "---- WLV Chrome profile processes ----"
chrome_pids="$(wlv_chrome_profile_pids || true)"
if [ -n "$chrome_pids" ]; then
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    echo "$pid :: $(wlv_process_command "$pid")"
  done <<< "$chrome_pids"
else
  echo "no WLV Chrome profile process"
fi

echo
echo "---- health ----"
if curl -fsS "$WLV_BACKEND_URL/api/wlv/source-intake/health" >/dev/null 2>&1; then
  echo "Backend source-intake: OK"
else
  echo "Backend source-intake: FAIL"
fi
if curl -fsS "$WLV_BACKEND_URL/api/wlv/wdv/templates" >/dev/null 2>&1; then
  echo "Backend WDV templates: OK"
else
  echo "Backend WDV templates: FAIL"
fi
if curl -fsS "$WLV_FRONTEND_URL" >/dev/null 2>&1; then
  echo "Frontend: OK"
else
  echo "Frontend: FAIL"
fi
