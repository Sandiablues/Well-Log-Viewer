#!/usr/bin/env bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PROJECT="${SEISMIC_VIEWER_PROJECT:-$HOME/Applications/MultiViewer/seismic_viewer_project}"
BACKEND="$PROJECT/seismic-viewer-backend"
PY="$BACKEND/venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi
cd "$BACKEND"
"$PY" scripts/e2e/test_source_intake_document_info_continuity.py
