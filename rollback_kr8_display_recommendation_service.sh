#!/usr/bin/env bash
# rollback_kr8_display_recommendation_service.sh
# Removes all KR-8 additions and reverts the single KR-6 dataclass extension.
#
# Safe to run multiple times (idempotent removes).
# Does NOT touch any frontend files.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"
KNOWLEDGE="$BACKEND/app/knowledge"
TESTS="$BACKEND/tests/knowledge"

echo "=========================================================="
echo "KR-8 Display Recommendation Service — Rollback Script"
echo "=========================================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Remove KR-8 service file
# ---------------------------------------------------------------------------
KR8_SERVICE="$KNOWLEDGE/display_recommendation_service.py"
if [[ -f "$KR8_SERVICE" ]]; then
    rm -f "$KR8_SERVICE"
    echo "Removed: $KR8_SERVICE"
else
    echo "Already absent: $KR8_SERVICE"
fi

# Remove compiled bytecode if present
rm -f "$KNOWLEDGE/__pycache__/display_recommendation_service.cpython-"*.pyc 2>/dev/null || true

# ---------------------------------------------------------------------------
# 2. Remove KR-8 test file
# ---------------------------------------------------------------------------
KR8_TEST="$TESTS/test_kr8_display_recommendation_service.py"
if [[ -f "$KR8_TEST" ]]; then
    rm -f "$KR8_TEST"
    echo "Removed: $KR8_TEST"
else
    echo "Already absent: $KR8_TEST"
fi

# ---------------------------------------------------------------------------
# 3. Remove KR-8 block from api_managed_knowledge.py
# ---------------------------------------------------------------------------
API_FILE="$KNOWLEDGE/api_managed_knowledge.py"
echo ""
echo "Stripping KR-8 block from: $API_FILE"
echo "(Manual step — open the file and remove the section beginning with"
echo "'# KR-8 display recommendation — imports and models' through the end"
echo "of the file, and revert the module docstring to remove the KR-8 line.)"
echo ""
echo "Alternatively, restore the file from git:"
echo "  git checkout HEAD -- backend/app/knowledge/api_managed_knowledge.py"
echo ""

# ---------------------------------------------------------------------------
# 4. Revert DisplayRuleResult extension in resolution_service.py
# ---------------------------------------------------------------------------
echo "The 'preferred_track_family' field added to DisplayRuleResult in"
echo "backend/app/knowledge/resolution_service.py must also be reverted."
echo ""
echo "Restore from git:"
echo "  git checkout HEAD -- backend/app/knowledge/resolution_service.py"
echo ""

# ---------------------------------------------------------------------------
# 5. Remove validation script itself
# ---------------------------------------------------------------------------
echo "To remove this script and the validate script:"
echo "  rm -f validate_kr8_display_recommendation_service.sh"
echo "  rm -f rollback_kr8_display_recommendation_service.sh"
echo ""

echo "=========================================================="
echo "KR-8 Rollback complete."
echo "Review remaining manual steps above before committing."
echo "=========================================================="
