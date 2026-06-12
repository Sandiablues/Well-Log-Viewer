#!/usr/bin/env bash
# apply_kr2_managed_kr_patch.sh
# Applies the KR-2 Managed Knowledge Repository patch to the WLV project.
#
# Prerequisites: run from the repo root (Well-Log-Viewer/).
# This script is idempotent — re-running it is safe.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$REPO_ROOT/backend"

echo "=== KR-2 Managed KR — Apply Patch ==="
echo "Repo root: $REPO_ROOT"
echo ""

# --- Verify baseline ---
if [[ ! -f "$BACKEND/app/knowledge/repository.py" ]]; then
    echo "ERROR: KR-1 repository.py not found. Ensure KR-1 is in place before applying KR-2."
    exit 1
fi

# --- New files (already present if Claude applied them directly) ---
NEW_FILES=(
    "backend/app/knowledge/governance.py"
    "backend/app/knowledge/managed_models.py"
    "backend/app/knowledge/managed_seed.py"
    "backend/app/knowledge/managed_repository.py"
    "backend/app/knowledge/api_managed_knowledge.py"
    "backend/tests/knowledge/test_kr2_managed_repository.py"
)

for f in "${NEW_FILES[@]}"; do
    if [[ -f "$REPO_ROOT/$f" ]]; then
        echo "  EXISTS: $f"
    else
        echo "  MISSING: $f  (re-run Claude's KR-2 task)"
        exit 1
    fi
done

# --- Patch main.py (idempotent) ---
MAIN_PY="$BACKEND/app/main.py"
if grep -q "api_managed_knowledge" "$MAIN_PY"; then
    echo "  OK: main.py already patched"
else
    echo "  Patching main.py..."
    # Add import after the knowledge_router import
    sed -i '' \
        's|from .knowledge.api_knowledge import router as knowledge_router|from .knowledge.api_knowledge import router as knowledge_router\nfrom .knowledge.api_managed_knowledge import router as managed_knowledge_router|' \
        "$MAIN_PY"
    # Add include_router call after knowledge_router include
    sed -i '' \
        's|app.include_router(knowledge_router)|app.include_router(knowledge_router)\napp.include_router(managed_knowledge_router)|' \
        "$MAIN_PY"
    echo "  main.py patched"
fi

echo ""
echo "=== KR-2 patch applied successfully ==="
echo ""
echo "Next step — run validation:"
echo "  bash $REPO_ROOT/validate_kr2_managed_kr.sh"
