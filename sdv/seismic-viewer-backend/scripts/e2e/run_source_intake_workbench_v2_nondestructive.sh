#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT="${SEISMIC_VIEWER_PROJECT:-$HOME/Applications/MultiViewer/seismic_viewer_project}"
BACKEND="$PROJECT/seismic-viewer-backend"
BASE="${SEISMIC_VIEWER_BASE_URL:-http://127.0.0.1:8000}"
MODE="${SEISMIC_VIEWER_E2E_MODE:-3d}"
REPOSITORY_ID="${SEISMIC_VIEWER_E2E_REPOSITORY_ID:-}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="$HOME/Downloads/e2e_2_source_intake_workbench_v2_${STAMP}"
ZIP="$OUTDIR.zip"
PY="$BACKEND/venv/bin/python"

if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

mkdir -p "$OUTDIR"

{
  echo "E2E-2 Source Intake Workbench V2 non-destructive harness"
  echo "Timestamp: $(date)"
  echo "Project: $PROJECT"
  echo "Backend: $BACKEND"
  echo "Base URL: $BASE"
  echo "Mode: $MODE"
  echo "Repository ID override: ${REPOSITORY_ID:-<auto>}"
  echo
  echo "No upload/delete/convert/rebuild/load/unload is performed."
  echo "Only the backend-owned Workbench active set is modified, then restored."
  echo
} > "$OUTDIR/README.txt"

"$PY" "$BACKEND/scripts/e2e/test_source_intake_workbench_v2_nondestructive.py" \
  --base-url "$BASE" \
  --mode "$MODE" \
  ${REPOSITORY_ID:+--repository-id "$REPOSITORY_ID"} \
  --out-dir "$OUTDIR" \
  2>&1 | tee "$OUTDIR/harness_stdout_stderr.txt"

{
  echo "---- frontend bundle verification ----"
  echo "frontend:"
  grep -o 'assets/index-[^"]*\.js' "$PROJECT/seismic-viewer-frontend/dist/index.html" 2>/dev/null | head -1 || true
  echo "packaged:"
  grep -o 'assets/index-[^"]*\.js' "$BACKEND/packaged_dist/index.html" 2>/dev/null | head -1 || true
  echo "served:"
  curl -s "$BASE/" | grep -o 'assets/index-[^"]*\.js' | head -1 || true
} > "$OUTDIR/frontend_bundle_check.txt" 2>&1

cat > "$OUTDIR/manual_browser_checklist.txt" <<TXT
E2E-2 MANUAL CHECKLIST

Open app:
open -na "Google Chrome" --args --new-window "$BASE/"

Manual checks after backend harness PASS:
1. Go to Sources / Source Intake.
2. Select the tested mode/repository if needed.
3. Confirm Workbench / Selection and Conversion shows repository rows.
4. Press Refresh and confirm rows remain stable.
5. Do not run Convert, Rebuild, Delete, Upload, Load, or Unload during this check.

The backend harness already verified:
- Use in Workbench populates rows.
- Refresh preserves rows.
- Clear one removes exactly one row.
- Refresh does not resurrect the cleared row.
- Clear all empties rows.
- Refresh remains empty.
- Use in Workbench restores rows.
- Managed Data / Loaded / MSI datasets remain unchanged.
TXT

cd "$HOME/Downloads"
zip -qr "$ZIP" "$(basename "$OUTDIR")"

echo
echo "Created E2E-2 result bundle:"
echo "$ZIP"
echo
echo "Upload this zip into the chat."
