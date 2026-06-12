#!/usr/bin/env bash
# rollback_kr4_governance_review_patch.sh
# ---------------------------------------------------------------------------
# Rolls back the KR-4 Governance Review patch.
#
# Removes:
#   - backend/app/knowledge/governance_service.py
#   - backend/tests/knowledge/test_kr4_governance_review.py
#
# Restores from git (if available) or reports manual steps for:
#   - backend/app/knowledge/managed_models.py
#   - backend/app/knowledge/api_managed_knowledge.py
#   - backend/tests/knowledge/test_kr3_import_staging.py
#
# Usage:
#   bash rollback_kr4_governance_review_patch.sh
# ---------------------------------------------------------------------------
set -euo pipefail

PROJECT_ROOT="$HOME/Applications/MultiViewer/Well-Log-Viewer"
BACKEND="$PROJECT_ROOT/backend"

echo "=== KR-4 Governance Review: rollback ==="

# ---- Remove KR-4-only new files ----
KR4_FILES=(
    "$BACKEND/app/knowledge/governance_service.py"
    "$BACKEND/tests/knowledge/test_kr4_governance_review.py"
)

for f in "${KR4_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        rm "$f"
        echo "Removed: $f"
    else
        echo "Already absent: $f"
    fi
done

# ---- Restore edited files from git if possible ----
cd "$PROJECT_ROOT"

if git rev-parse --git-dir > /dev/null 2>&1; then
    echo ""
    echo "Git repository detected. Checking for KR-4 changes to revert..."

    EDITED=(
        "backend/app/knowledge/managed_models.py"
        "backend/app/knowledge/api_managed_knowledge.py"
        "backend/tests/knowledge/test_kr3_import_staging.py"
    )

    for rel in "${EDITED[@]}"; do
        if git diff --name-only HEAD -- "$rel" | grep -q .; then
            git checkout HEAD -- "$rel"
            echo "Restored from git HEAD: $rel"
        else
            echo "No unstaged changes detected in git for: $rel"
        fi
    done
else
    echo ""
    echo "WARNING: Not a git repository."
    echo "The following files were edited by KR-4 and must be reverted manually:"
    echo "  backend/app/knowledge/managed_models.py"
    echo "    - Remove governance_history field from all 5 governed record types"
    echo "    - Remove KR4_VERSION = 'kr-4' constant"
    echo "  backend/app/knowledge/api_managed_knowledge.py"
    echo "    - Remove KR-4 imports (governance_service, KR4_VERSION)"
    echo "    - Remove get_governance_service dependency"
    echo "    - Remove KR-4 response models"
    echo "    - Remove KR-4 route handlers (/records, /production-eligible)"
    echo "  backend/tests/knowledge/test_kr3_import_staging.py"
    echo "    - Revert TestNoApprovalEndpoint.test_no_approve_endpoint_exists"
    echo "      to its original KR-3 form"
fi

echo ""
echo "=== KR-4 rollback complete ==="
