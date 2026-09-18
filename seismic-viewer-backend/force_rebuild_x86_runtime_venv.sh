#!/bin/bash
set -euo pipefail

echo "=== Force rebuild runtime backend venv as x86_64 ==="

PROJECT_ROOT="$HOME/Applications/MultiViewer/seismic_viewer_project"
BACKEND_DIR="$PROJECT_ROOT/seismic-viewer-backend"

cd "$BACKEND_DIR"

echo ""
echo "Stopping runtime backend..."
if [ -f "$PROJECT_ROOT/run/backend.pid" ]; then
  pid="$(cat "$PROJECT_ROOT/run/backend.pid")"
  kill "$pid" 2>/dev/null || true
  sleep 1
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PROJECT_ROOT/run/backend.pid"
fi

echo ""
echo "System Python candidates:"
for PY in \
  /usr/local/bin/python3 \
  /opt/homebrew/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
  /usr/bin/python3 \
  python3
do
  if command -v "$PY" >/dev/null 2>&1 || [ -x "$PY" ]; then
    echo "--- $PY"
    "$PY" -c "import platform, sys; print(platform.machine()); print(sys.executable)" 2>/dev/null || true
    file "$("$PY" -c 'import sys; print(sys.executable)' 2>/dev/null)" 2>/dev/null || true
  fi
done

echo ""
echo "Removing runtime venv completely..."
rm -rf venv .venv

echo ""
echo "Creating x86_64 venv..."
arch -x86_64 python3 -m venv venv

source venv/bin/activate

echo ""
echo "Venv Python architecture:"
python -c "import platform, sys; print(platform.machine()); print(sys.executable)"
file "$(python -c 'import sys; print(sys.executable)')"

echo ""
echo "Installing dependencies cleanly..."
python -m pip install --upgrade pip setuptools wheel

if [ -f requirements.txt ]; then
  python -m pip install --no-cache-dir --force-reinstall -r requirements.txt
elif [ -f ../requirements.txt ]; then
  python -m pip install --no-cache-dir --force-reinstall -r ../requirements.txt
else
  python -m pip install --no-cache-dir --force-reinstall \
    fastapi uvicorn python-multipart numpy zarr segyio numcodecs pydantic
fi

echo ""
echo "Checking pydantic_core architecture..."
CORE_PATH="$(python - <<'PY'
import pydantic_core
print(pydantic_core.__file__)
PY
)"

echo "$CORE_PATH"
file "$CORE_PATH"

if file "$CORE_PATH" | grep -q "arm64"; then
  echo ""
  echo "ERROR: pydantic_core is still arm64. Runtime venv is not usable."
  exit 1
fi

if ! file "$CORE_PATH" | grep -q "x86_64"; then
  echo ""
  echo "ERROR: pydantic_core is not confirmed x86_64."
  exit 1
fi

echo ""
echo "Import check..."
python - <<'PY'
import platform
import fastapi
import uvicorn
import pydantic
import pydantic_core
import zarr
import segyio

print("Python arch:", platform.machine())
print("fastapi:", fastapi.__version__)
print("uvicorn:", uvicorn.__version__)
print("pydantic:", pydantic.__version__)
print("pydantic_core:", pydantic_core.__version__)
print("zarr:", zarr.__version__)
print("segyio: OK")
PY

echo ""
echo "Backend syntax check..."
python -m py_compile main.py app/api/endpoints.py

echo ""
echo "=== Runtime venv rebuilt successfully as x86_64 ==="
