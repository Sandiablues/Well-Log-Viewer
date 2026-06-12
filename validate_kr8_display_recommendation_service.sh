#!/usr/bin/env bash
# validate_kr8_display_recommendation_service.sh
# Validates the KR-8 Display Recommendation Service implementation.
#
# Runs:
#   1. KR-8 unit + API tests
#   2. Full knowledge test suite
#   3. Frontend typecheck
#   4. Frontend build

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================================="
echo "KR-8 Display Recommendation Service — Validation Script"
echo "=========================================================="
echo ""

# ---------------------------------------------------------------------------
# 1. KR-8 tests
# ---------------------------------------------------------------------------
echo "----------------------------------------------------------"
echo "Step 1: KR-8 unit + API tests"
echo "----------------------------------------------------------"
cd "$SCRIPT_DIR/backend"
.venv/bin/pytest tests/knowledge/test_kr8_display_recommendation_service.py -v
echo ""

# ---------------------------------------------------------------------------
# 2. Full knowledge test suite
# ---------------------------------------------------------------------------
echo "----------------------------------------------------------"
echo "Step 2: Full knowledge test suite"
echo "----------------------------------------------------------"
.venv/bin/pytest tests/knowledge/ -v
echo ""

# ---------------------------------------------------------------------------
# 3. Frontend typecheck
# ---------------------------------------------------------------------------
echo "----------------------------------------------------------"
echo "Step 3: Frontend typecheck"
echo "----------------------------------------------------------"
cd "$SCRIPT_DIR/frontend"
npm run typecheck
echo ""

# ---------------------------------------------------------------------------
# 4. Frontend build
# ---------------------------------------------------------------------------
echo "----------------------------------------------------------"
echo "Step 4: Frontend build"
echo "----------------------------------------------------------"
npm run build
echo ""

echo "=========================================================="
echo "KR-8 Validation PASSED"
echo "=========================================================="
