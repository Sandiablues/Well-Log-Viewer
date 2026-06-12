#!/usr/bin/env bash
# rollback_kr2_managed_kr_patch.sh
# Removes all KR-2 Managed Knowledge Repository additions from the WLV project.
#
# Prerequisites: run from the repo root (Well-Log-Viewer/).
# WARNING: This permanently removes KR-2 source files. Commit KR-2 first if
#          you want to preserve it.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$REPO_ROOT/backend"

echo "=== KR-2 Managed KR — Rollback ==="
echo "Repo root: $REPO_ROOT"
echo ""
echo "WARNING: This will remove all KR-2 files."
read -rp "Continue? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

# --- Remove new KR-2 files ---
KR2_FILES=(
    "backend/app/knowledge/governance.py"
    "backend/app/knowledge/managed_models.py"
    "backend/app/knowledge/managed_seed.py"
    "backend/app/knowledge/managed_repository.py"
    "backend/app/knowledge/api_managed_knowledge.py"
    "backend/tests/knowledge/test_kr2_managed_repository.py"
)

for f in "${KR2_FILES[@]}"; do
    if [[ -f "$REPO_ROOT/$f" ]]; then
        rm "$REPO_ROOT/$f"
        echo "  REMOVED: $f"
    else
        echo "  SKIPPED (not found): $f"
    fi
done

# --- Restore main.py via git ---
MAIN_PY="$BACKEND/app/main.py"
if git -C "$REPO_ROOT" diff --name-only HEAD | grep -q "backend/app/main.py"; then
    git -C "$REPO_ROOT" checkout HEAD -- backend/app/main.py
    echo "  RESTORED: backend/app/main.py (via git checkout)"
elif grep -q "api_managed_knowledge" "$MAIN_PY"; then
    # Manual removal if git is not available
    sed -i '' '/api_managed_knowledge/d' "$MAIN_PY"
    echo "  PATCHED: backend/app/main.py (removed managed_knowledge_router lines)"
else
    echo "  OK: backend/app/main.py already clean"
fi

echo ""
echo "=== KR-2 rollback complete ==="
echo "KR-1 endpoints and seed data are unchanged."
