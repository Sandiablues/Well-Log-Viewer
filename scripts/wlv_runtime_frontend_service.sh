#!/usr/bin/env bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PROJECT="${WLV_PROJECT:-$HOME/Applications/MultiViewer/Well-Log-Viewer}"
NODE_BIN="${WLV_NODE_BIN:-/opt/homebrew/bin/node}"
[[ -x "$NODE_BIN" ]] || NODE_BIN="$(command -v node)"
cd "$PROJECT/frontend"
exec "$NODE_BIN" "$PROJECT/frontend/node_modules/vite/bin/vite.js" \
  --host "${WLV_FRONTEND_HOST:-127.0.0.1}" \
  --port "${WLV_FRONTEND_PORT:-5173}" \
  --strictPort
