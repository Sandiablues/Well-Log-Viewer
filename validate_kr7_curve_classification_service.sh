#!/usr/bin/env bash
# validate_kr7_curve_classification_service.sh
# ---------------------------------------------------------------------------
# WLV KR-7 Validation Script — Backend Curve Classification Service
#
# Runs:
#   1. KR-7 classification service tests (focused)
#   2. Full knowledge test suite (regression: KR-1 through KR-7)
#   3. Frontend typecheck
#   4. Frontend build
#
# Exit code 0 = all checks passed.  Non-zero = one or more checks failed.
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

PASS=0
FAIL=0

_section() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

_ok() {
    echo "  ✓ $1"
    PASS=$((PASS + 1))
}

_fail() {
    echo "  ✗ $1"
    FAIL=$((FAIL + 1))
}

# ---------------------------------------------------------------------------
# 1. KR-7 focused test run
# ---------------------------------------------------------------------------
_section "1 / 4 — KR-7 classification service tests"

cd "$BACKEND_DIR"

if .venv/bin/pytest tests/knowledge/test_kr7_curve_classification_service.py -v; then
    _ok "KR-7 classification service tests passed"
else
    _fail "KR-7 classification service tests FAILED"
fi

# ---------------------------------------------------------------------------
# 2. Full knowledge test suite (regression)
# ---------------------------------------------------------------------------
_section "2 / 4 — Full knowledge test suite (KR-1 through KR-7)"

if .venv/bin/pytest tests/knowledge/ -v; then
    _ok "Full knowledge test suite passed"
else
    _fail "Full knowledge test suite FAILED"
fi

# ---------------------------------------------------------------------------
# 3. Frontend typecheck
# ---------------------------------------------------------------------------
_section "3 / 4 — Frontend typecheck"

cd "$FRONTEND_DIR"

if npm run typecheck; then
    _ok "Frontend typecheck passed"
else
    _fail "Frontend typecheck FAILED"
fi

# ---------------------------------------------------------------------------
# 4. Frontend build
# ---------------------------------------------------------------------------
_section "4 / 4 — Frontend build"

if npm run build; then
    _ok "Frontend build passed"
else
    _fail "Frontend build FAILED"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  KR-7 Validation Summary"
echo "============================================================"
echo "  Passed : $PASS"
echo "  Failed : $FAIL"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "  RESULT: FAILED — $FAIL check(s) did not pass."
    exit 1
else
    echo "  RESULT: ALL CHECKS PASSED."
    exit 0
fi
