#!/usr/bin/env bash
# validate_kr4_governance_review.sh
# ---------------------------------------------------------------------------
# Validates the KR-4 Governance Review implementation.
#
# Runs:
#   1. KR-4 test suite
#   2. Full knowledge test suite (regression)
#   3. Frontend typecheck
#   4. Frontend build
#   5. Live endpoint curl checks (requires running backend on port 8000)
#
# Usage:
#   bash validate_kr4_governance_review.sh
#   bash validate_kr4_governance_review.sh --no-live   # skip curl checks
# ---------------------------------------------------------------------------
set -euo pipefail

PROJECT_ROOT="$HOME/Applications/MultiViewer/Well-Log-Viewer"
BACKEND="$PROJECT_ROOT/backend"
FRONTEND="$PROJECT_ROOT/frontend"

SKIP_LIVE=false
for arg in "$@"; do
    [[ "$arg" == "--no-live" ]] && SKIP_LIVE=true
done

PASS=0
FAIL=0

run_step() {
    local label="$1"
    shift
    echo ""
    echo "━━━ $label ━━━"
    if "$@"; then
        echo "✓ PASS: $label"
        ((PASS++))
    else
        echo "✗ FAIL: $label"
        ((FAIL++))
    fi
}

# ---------------------------------------------------------------------------
# 1. KR-4 tests
# ---------------------------------------------------------------------------
run_step "KR-4 governance tests" \
    bash -c "cd '$BACKEND' && .venv/bin/pytest tests/knowledge/test_kr4_governance_review.py -v --tb=short"

# ---------------------------------------------------------------------------
# 2. Full knowledge test suite
# ---------------------------------------------------------------------------
run_step "Full knowledge test suite" \
    bash -c "cd '$BACKEND' && .venv/bin/pytest tests/knowledge/ -v --tb=short"

# ---------------------------------------------------------------------------
# 3. Frontend typecheck
# ---------------------------------------------------------------------------
run_step "Frontend typecheck" \
    bash -c "cd '$FRONTEND' && npm run typecheck"

# ---------------------------------------------------------------------------
# 4. Frontend build
# ---------------------------------------------------------------------------
run_step "Frontend build" \
    bash -c "cd '$FRONTEND' && npm run build"

# ---------------------------------------------------------------------------
# 5. Live endpoint curl checks (optional)
# ---------------------------------------------------------------------------
if [[ "$SKIP_LIVE" == false ]]; then
    BASE="http://localhost:8000"

    echo ""
    echo "━━━ Live endpoint checks (backend must be running on $BASE) ━━━"

    curl_check() {
        local label="$1"
        local expected_status="$2"
        shift 2
        local url="$1"
        shift
        local status
        status=$(curl -s -o /dev/null -w "%{http_code}" "$@" "$url")
        if [[ "$status" == "$expected_status" ]]; then
            echo "  ✓ $label → HTTP $status"
            ((PASS++))
        else
            echo "  ✗ $label → HTTP $status (expected $expected_status)"
            ((FAIL++))
        fi
    }

    # KR-4 read endpoints
    curl_check "GET /managed/records"          "200" "$BASE/api/wlv/knowledge/managed/records"
    curl_check "GET /managed/records?status=seed" "200" "$BASE/api/wlv/knowledge/managed/records?status=seed"
    curl_check "GET /managed/records?status=candidate" "200" "$BASE/api/wlv/knowledge/managed/records?status=candidate"
    curl_check "GET /managed/production-eligible" "200" "$BASE/api/wlv/knowledge/managed/production-eligible"
    curl_check "GET /managed/records/nonexistent → 404" "404" "$BASE/api/wlv/knowledge/managed/records/nonexistent_kr4_record"

    # KR-4 action endpoints (expect 404 on unknown IDs, not 422/500)
    curl_check "POST approve unknown → 404" "404" \
        -X POST -H "Content-Type: application/json" \
        -d '{"actor":"test","reason":"test"}' \
        "$BASE/api/wlv/knowledge/managed/records/nonexistent/approve"

    curl_check "POST approve malformed → 422" "422" \
        -X POST -H "Content-Type: application/json" \
        -d '{"notes":"missing actor"}' \
        "$BASE/api/wlv/knowledge/managed/records/gamma_ray/approve"

    # KR-2 compatibility
    curl_check "GET /managed/health"           "200" "$BASE/api/wlv/knowledge/managed/health"
    curl_check "GET /managed/schema"           "200" "$BASE/api/wlv/knowledge/managed/schema"
    curl_check "GET /managed/status-summary"   "200" "$BASE/api/wlv/knowledge/managed/status-summary"

    # KR-1 compatibility
    curl_check "GET /knowledge/health"         "200" "$BASE/api/wlv/knowledge/health"
    curl_check "GET /knowledge/curve-definitions" "200" "$BASE/api/wlv/knowledge/curve-definitions"
    curl_check "GET /knowledge/product-groups" "200" "$BASE/api/wlv/knowledge/product-groups"
    curl_check "GET /knowledge/display-rules"  "200" "$BASE/api/wlv/knowledge/display-rules"
    curl_check "GET /knowledge/templates"      "200" "$BASE/api/wlv/knowledge/templates"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "KR-4 Validation Summary"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ "$FAIL" -gt 0 ]]; then
    echo "RESULT: FAIL — $FAIL step(s) failed"
    exit 1
else
    echo "RESULT: PASS — all steps passed"
fi
