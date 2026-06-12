#!/usr/bin/env bash
# rollback_kr7_curve_classification_service.sh
# ---------------------------------------------------------------------------
# WLV KR-7 Rollback Script — removes all KR-7 additions
#
# Removes:
#   backend/app/knowledge/classification_service.py
#   backend/tests/knowledge/test_kr7_curve_classification_service.py
#
# Reverts:
#   backend/app/knowledge/api_managed_knowledge.py  (KR-7 additions)
#
# Does NOT touch:
#   Any KR-1 through KR-6 files
#   backend/app/main.py  (KR-7 uses the existing resolve_router — no new router)
#   frontend/ files
#   backend/data/knowledge/managed_knowledge.json
#
# Usage:
#   bash rollback_kr7_curve_classification_service.sh [--dry-run]
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    echo "[DRY RUN] No files will be modified."
fi

_remove() {
    local path="$1"
    if [ -f "$path" ]; then
        if [ "$DRY_RUN" -eq 0 ]; then
            rm "$path"
            echo "  Removed: $path"
        else
            echo "  [dry-run] Would remove: $path"
        fi
    else
        echo "  (already absent): $path"
    fi
}

echo ""
echo "============================================================"
echo "  WLV KR-7 Rollback"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# 1. Remove new KR-7 files
# ---------------------------------------------------------------------------
echo "1. Removing KR-7 new files..."
_remove "$BACKEND_DIR/app/knowledge/classification_service.py"
_remove "$BACKEND_DIR/tests/knowledge/test_kr7_curve_classification_service.py"

# ---------------------------------------------------------------------------
# 2. Revert api_managed_knowledge.py
#    Strip everything from the KR-7 imports/models block onward.
#    The block begins with the line containing "KR-7 classification".
# ---------------------------------------------------------------------------
echo ""
echo "2. Reverting api_managed_knowledge.py (removing KR-7 additions)..."

API_FILE="$BACKEND_DIR/app/knowledge/api_managed_knowledge.py"

if [ -f "$API_FILE" ]; then
    if grep -q "KR-7 classification" "$API_FILE"; then
        if [ "$DRY_RUN" -eq 0 ]; then
            # Find the start of the KR-7 block
            CUTLINE=$(grep -n "KR-7 classification" "$API_FILE" | head -1 | cut -d: -f1)
            # Walk back to remove trailing blank lines before the KR-7 block
            CUTLINE=$((CUTLINE - 1))
            while [ "$CUTLINE" -gt 0 ]; do
                LINE_CONTENT=$(sed -n "${CUTLINE}p" "$API_FILE")
                if [ -z "$LINE_CONTENT" ]; then
                    CUTLINE=$((CUTLINE - 1))
                else
                    break
                fi
            done
            head -n "$CUTLINE" "$API_FILE" > "${API_FILE}.rollback_tmp"
            mv "${API_FILE}.rollback_tmp" "$API_FILE"
            # Restore module docstring to KR-6 form
            python3 - "$API_FILE" <<'PYEOF'
import sys, pathlib
path = pathlib.Path(sys.argv[1])
text = path.read_text()
text = text.replace(
    'WLV Managed Knowledge Repository API routes (KR-2 + KR-3 + KR-4 + KR-6 + KR-7).',
    'WLV Managed Knowledge Repository API routes (KR-2 + KR-3 + KR-4 + KR-6).',
)
text = text.replace(
    'KR-7 classification endpoint (new):\n  POST /api/wlv/knowledge/classify/curves\n\n',
    '',
)
text = text.replace(
    "KR-6 resolution endpoints (unchanged):",
    "KR-6 resolution endpoints (new):",
)
path.write_text(text)
PYEOF
            echo "  Reverted: $API_FILE"
        else
            echo "  [dry-run] Would revert: $API_FILE"
        fi
    else
        echo "  (KR-7 block not found — already clean): $API_FILE"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
if [ "$DRY_RUN" -eq 0 ]; then
    echo "  KR-7 rollback complete."
    echo "  Verify with: cd backend && .venv/bin/pytest tests/knowledge/ -v"
else
    echo "  [DRY RUN] No changes were made."
fi
echo "============================================================"
echo ""
