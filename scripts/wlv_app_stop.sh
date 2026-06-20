#!/usr/bin/env bash
set -euo pipefail

PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"

QUIET=0
for arg in "$@"; do
  case "$arg" in
    --quiet|--no-launcher) QUIET=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

"$PROJECT/scripts/wlv_service_stop.sh"

if [ "$QUIET" -ne 1 ]; then
  echo "WLV services stopped. Browser windows were not modified."
fi
