#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$HOME/Applications/MultiViewer/seismic_viewer_project"
FRONTEND="$PROJECT_ROOT/seismic-viewer-frontend"
BACKEND="$PROJECT_ROOT/seismic-viewer-backend"

echo "=== Rebuild frontend ==="
cd "$FRONTEND"
npm run build

echo
echo "=== Restart backend on port 8000 ==="
lsof -ti :8000 | xargs kill -9 2>/dev/null || true

cd "$BACKEND"
source venv/bin/activate 2>/dev/null || true

echo
echo "Backend starting at http://localhost:8000"
exec uvicorn main:app --reload --host 0.0.0.0 --port 8000
