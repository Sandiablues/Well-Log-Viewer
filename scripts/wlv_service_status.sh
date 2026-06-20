#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

echo "WLV service status"
echo "Project: $WLV_PROJECT"

for label in "$WLV_BACKEND_LABEL" "$WLV_FRONTEND_LABEL"; do
  echo
  echo "---- $label ----"
  launchctl print "$WLV_GUI_DOMAIN/$label" 2>&1 | \
    grep -E 'state =|pid =|last exit code =|program =|path =' || true
done

echo
echo "---- listeners ----"
lsof -nP -iTCP:"$WLV_BACKEND_PORT" -sTCP:LISTEN 2>/dev/null || echo "backend: no listener"
lsof -nP -iTCP:"$WLV_FRONTEND_PORT" -sTCP:LISTEN 2>/dev/null || echo "frontend: no listener"

echo
echo "---- health ----"
curl -fsS "$WLV_BACKEND_URL/api/wlv/source-intake/health" >/dev/null 2>&1 \
  && echo "backend source-intake: OK" || echo "backend source-intake: FAIL"
curl -fsS "$WLV_BACKEND_URL/api/wlv/wdv/templates" >/dev/null 2>&1 \
  && echo "backend WDV templates: OK" || echo "backend WDV templates: FAIL"
curl -fsS "$WLV_FRONTEND_URL" >/dev/null 2>&1 \
  && echo "frontend: OK" || echo "frontend: FAIL"
