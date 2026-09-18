#!/bin/bash
set -euo pipefail

echo "=== Restart Seismic Viewer backend ==="

PROJECT_ROOT="$HOME/Applications/MultiViewer/seismic_viewer_project"
BACKEND_DIR="$PROJECT_ROOT/seismic-viewer-backend"

cd "$BACKEND_DIR"

echo "Backend dir:"
pwd

if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
else
  echo "ERROR: No backend virtual environment found at venv/ or .venv/"
  exit 1
fi

echo "Python:"
which python

echo "Stopping existing backend on port 8000, if any..."
lsof -ti tcp:8000 -sTCP:LISTEN | xargs kill -9 2>/dev/null || true

echo "Finding FastAPI entrypoint..."

ENTRYPOINT=""

if [ -f "main.py" ] && grep -q "FastAPI(" main.py; then
  ENTRYPOINT="main:app"
elif [ -f "app.py" ] && grep -q "FastAPI(" app.py; then
  ENTRYPOINT="app:app"
elif [ -f "server.py" ] && grep -q "FastAPI(" server.py; then
  ENTRYPOINT="server:app"
elif [ -f "app/main.py" ] && grep -q "FastAPI(" app/main.py; then
  ENTRYPOINT="app.main:app"
elif [ -f "app/__init__.py" ] && grep -q "FastAPI(" app/__init__.py; then
  ENTRYPOINT="app:app"
else
  echo "ERROR: Could not find FastAPI app entrypoint."
  echo ""
  echo "FastAPI references found:"
  grep -R "FastAPI(" . -n \
    --exclude-dir=venv \
    --exclude-dir=.venv \
    --exclude-dir=__pycache__ || true
  exit 1
fi

echo "Using entrypoint: $ENTRYPOINT"
echo ""
echo "Backend starting at:"
echo "http://localhost:8000"
echo ""

uvicorn "$ENTRYPOINT" --reload --host 0.0.0.0 --port 8000
