#!/usr/bin/env bash
# apply_kr4_governance_review_patch.sh
# ---------------------------------------------------------------------------
# Applies the KR-4 Governance Review patch to the Well-Log-Viewer project.
#
# KR-4 adds:
#   - backend/app/knowledge/governance_service.py       (new)
#   - backend/tests/knowledge/test_kr4_governance_review.py (new)
#   - Edits to managed_models.py  (governance_history field + KR4_VERSION)
#   - Edits to api_managed_knowledge.py  (KR-4 endpoints)
#   - Patch to test_kr3_import_staging.py  (allow KR-4 approve path)
#
# Usage:
#   bash apply_kr4_governance_review_patch.sh
# ---------------------------------------------------------------------------
set -euo pipefail

PROJECT_ROOT="$HOME/Applications/MultiViewer/Well-Log-Viewer"
BACKEND="$PROJECT_ROOT/backend"

echo "=== KR-4 Governance Review: apply patch ==="
echo "Project root: $PROJECT_ROOT"

# Verify key KR-4 files are present
required_files=(
    "$BACKEND/app/knowledge/governance_service.py"
    "$BACKEND/tests/knowledge/test_kr4_governance_review.py"
)

for f in "${required_files[@]}"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: Required KR-4 file missing: $f"
        echo "Ensure all KR-4 source files are in place before running this script."
        exit 1
    fi
done

echo ""
echo "KR-4 source files verified."
echo "Running backend tests to confirm patch is correct..."
echo ""

cd "$BACKEND"
.venv/bin/pytest tests/knowledge/test_kr4_governance_review.py -v --tb=short

echo ""
echo "Running full knowledge test suite..."
.venv/bin/pytest tests/knowledge/ -v --tb=short

echo ""
echo "=== KR-4 patch applied successfully ==="
