#!/usr/bin/env bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
cd "$PROJECT/backend"
exec "$PROJECT/backend/.venv/bin/python" -m uvicorn app.main:app \
  --host "${WLV_BACKEND_HOST:-127.0.0.1}" \
  --port "${WLV_BACKEND_PORT:-8001}"
