#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${SEISMIC_VIEWER_PROJECT:-$HOME/Applications/MultiViewer/seismic_viewer_project}"
BACKEND="$PROJECT/seismic-viewer-backend"
HARNESS="$BACKEND/scripts/e2e/test_existing_managed_3d_viewer.py"
PY="$BACKEND/venv/bin/python"

if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

if [ ! -f "$HARNESS" ]; then
  echo "Missing harness: $HARNESS"
  exit 1
fi

"$PY" "$HARNESS" --zip
