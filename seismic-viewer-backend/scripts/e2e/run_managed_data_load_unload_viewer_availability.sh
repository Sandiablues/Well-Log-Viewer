#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${SEISMIC_VIEWER_PROJECT:-$HOME/Applications/MultiViewer/seismic_viewer_project}"
BACKEND="$PROJECT/seismic-viewer-backend"
BASE="${SEISMIC_VIEWER_BASE_URL:-http://127.0.0.1:8000}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$HOME/Downloads/e2e_4_managed_data_load_unload_${STAMP}"
ZIP="$OUTDIR.zip"
PY="$BACKEND/venv/bin/python"

if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

mkdir -p "$OUTDIR"

{
  echo "E2E-4 — Managed Data Load / Unload / Viewer Availability"
  echo "Timestamp: $(date)"
  echo "Project: $PROJECT"
  echo "Backend: $BACKEND"
  echo "Base URL: $BASE"
  echo
  echo "---- backend health ----"
  curl -sS "$BASE/api/msi/health" | "$PY" -m json.tool
  echo
  echo "---- run harness ----"
  "$PY" "$BACKEND/scripts/e2e/test_managed_data_load_unload_viewer_availability.py" --base-url "$BASE" --outdir "$OUTDIR"
  echo
  echo "---- frontend bundle verification ----"
  "$PY" - "$PROJECT" "$BASE" <<'PY'
import re
import sys
import urllib.request
from pathlib import Path
project = Path(sys.argv[1])
base = sys.argv[2].rstrip('/')
pattern = re.compile(r'assets/index-[^"\\']+\\.js')
def from_file(path: Path) -> str:
    if not path.exists():
        return ''
    match = pattern.search(path.read_text(encoding='utf-8', errors='replace'))
    return match.group(0) if match else ''
def from_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as response:
        text = response.read().decode('utf-8', errors='replace')
    match = pattern.search(text)
    return match.group(0) if match else ''
front = from_file(project / 'seismic-viewer-frontend' / 'dist' / 'index.html')
pack = from_file(project / 'seismic-viewer-backend' / 'packaged_dist' / 'index.html')
served = from_url(base + '/')
print(f'frontend: {front}')
print(f'packaged: {pack}')
print(f'served: {served}')
if not front or front != pack or pack != served:
    print('BUNDLE CHECK: FAIL')
    raise SystemExit(1)
print('BUNDLE CHECK: PASS')
PY
} 2>&1 | tee "$OUTDIR/run_log.txt"

cd "$HOME/Downloads"
zip -qr "$ZIP" "$(basename "$OUTDIR")"

echo
echo "Created:"
echo "$ZIP"
echo
echo "Upload this zip after running the manual browser checklist."
echo
