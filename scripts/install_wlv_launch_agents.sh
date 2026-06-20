#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
source "$PROJECT/scripts/wlv_service_common.sh"

wlv_service_mkdirs
wlv_service_assert_project

render_plist() {
  local template="$1"
  local target="$2"
  sed \
    -e "s|__PROJECT__|$WLV_PROJECT|g" \
    -e "s|__HOME__|$HOME|g" \
    "$template" > "$target"
  plutil -lint "$target" >/dev/null
}

render_plist \
  "$WLV_PROJECT/deploy/macos/com.multiviewer.wlv.backend.plist.template" \
  "$WLV_BACKEND_PLIST"
render_plist \
  "$WLV_PROJECT/deploy/macos/com.multiviewer.wlv.frontend.plist.template" \
  "$WLV_FRONTEND_PLIST"

for label in "$WLV_BACKEND_LABEL" "$WLV_FRONTEND_LABEL"; do
  launchctl bootout "$WLV_GUI_DOMAIN/$label" >/dev/null 2>&1 || true
done

launchctl bootstrap "$WLV_GUI_DOMAIN" "$WLV_BACKEND_PLIST"
launchctl bootstrap "$WLV_GUI_DOMAIN" "$WLV_FRONTEND_PLIST"
launchctl enable "$WLV_GUI_DOMAIN/$WLV_BACKEND_LABEL"
launchctl enable "$WLV_GUI_DOMAIN/$WLV_FRONTEND_LABEL"
launchctl kickstart -k "$WLV_GUI_DOMAIN/$WLV_BACKEND_LABEL"
launchctl kickstart -k "$WLV_GUI_DOMAIN/$WLV_FRONTEND_LABEL"

echo "Installed and started:"
echo "  $WLV_BACKEND_LABEL"
echo "  $WLV_FRONTEND_LABEL"
