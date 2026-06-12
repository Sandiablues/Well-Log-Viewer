#!/usr/bin/env bash
# rollback_kr6_resolution_service.sh
# ---------------------------------------------------------------------------
# WLV KR-6 Rollback Script — removes all KR-6 additions
#
# Removes:
#   backend/app/knowledge/resolution_service.py
#   backend/tests/knowledge/test_kr6_resolution_service.py
#
# Reverts:
#   backend/app/knowledge/api_managed_knowledge.py  (KR-6 additions)
#   backend/app/main.py                             (resolve_router import/registration)
#
# Does NOT touch:
#   Any KR-1 through KR-5 files
#   frontend/ files
#   backend/data/knowledge/managed_knowledge.json
#
# Usage:
#   bash rollback_kr6_resolution_service.sh [--dry-run]
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
echo "  WLV KR-6 Rollback"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# 1. Remove new KR-6 files
# ---------------------------------------------------------------------------
echo "1. Removing KR-6 new files..."
_remove "$BACKEND_DIR/app/knowledge/resolution_service.py"
_remove "$BACKEND_DIR/tests/knowledge/test_kr6_resolution_service.py"

# ---------------------------------------------------------------------------
# 2. Revert api_managed_knowledge.py
#    Strip everything from the KR-6 resolve_router block onward.
#    The block begins with the line containing "# KR-6 resolution router".
# ---------------------------------------------------------------------------
echo ""
echo "2. Reverting api_managed_knowledge.py (removing KR-6 additions)..."

API_FILE="$BACKEND_DIR/app/knowledge/api_managed_knowledge.py"

if [ -f "$API_FILE" ]; then
    if grep -q "KR-6 resolution router" "$API_FILE"; then
        if [ "$DRY_RUN" -eq 0 ]; then
            # Strip from the KR-6 block start to EOF, and trim the preceding blank lines
            CUTLINE=$(grep -n "KR-6 resolution router" "$API_FILE" | head -1 | cut -d: -f1)
            # Walk back to remove trailing blank lines before the KR-6 block
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
            # Restore original docstring (remove KR-6 line from module docstring)
            python3 - <<'PYEOF'
import re, pathlib
path = pathlib.Path("$API_FILE")
text = path.read_text()
# Remove KR-6 docstring lines
text = re.sub(r'\nKR-6 resolution endpoints \(new\):\n  POST /api/wlv/knowledge/resolve/curve\n  POST /api/wlv/knowledge/resolve/curves\n', '', text)
# Fix module docstring title
text = text.replace(
    'WLV Managed Knowledge Repository API routes (KR-2 + KR-3 + KR-4 + KR-6).',
    'WLV Managed Knowledge Repository API routes (KR-2 + KR-3 + KR-4).',
)
text = text.replace(
    'KR-4 governance review endpoints (unchanged):',
    'KR-4 governance review endpoints (new):',
)
path.write_text(text)
PYEOF
            echo "  Reverted: $API_FILE"
        else
            echo "  [dry-run] Would revert: $API_FILE"
        fi
    else
        echo "  (KR-6 block not found — already clean): $API_FILE"
    fi
fi

# ---------------------------------------------------------------------------
# 3. Revert main.py
# ---------------------------------------------------------------------------
echo ""
echo "3. Reverting main.py (removing resolve_router import and registration)..."

MAIN_FILE="$BACKEND_DIR/app/main.py"

if [ -f "$MAIN_FILE" ]; then
    if grep -q "resolve_knowledge_router" "$MAIN_FILE"; then
        if [ "$DRY_RUN" -eq 0 ]; then
            python3 - "$MAIN_FILE" <<'PYEOF'
import sys, pathlib
path = pathlib.Path(sys.argv[1])
text = path.read_text()
# Remove resolve_router import line
text = text.replace(
    '\nfrom .knowledge.api_managed_knowledge import resolve_router as resolve_knowledge_router',
    '',
)
# Remove resolve_router registration line
text = text.replace(
    '\napp.include_router(resolve_knowledge_router)',
    '',
)
path.write_text(text)
PYEOF
            echo "  Reverted: $MAIN_FILE"
        else
            echo "  [dry-run] Would revert: $MAIN_FILE"
        fi
    else
        echo "  (resolve_knowledge_router not found — already clean): $MAIN_FILE"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
if [ "$DRY_RUN" -eq 0 ]; then
    echo "  KR-6 rollback complete."
    echo "  Verify with: cd backend && .venv/bin/pytest tests/knowledge/ -v"
else
    echo "  [DRY RUN] No changes were made."
fi
echo "============================================================"
echo ""
