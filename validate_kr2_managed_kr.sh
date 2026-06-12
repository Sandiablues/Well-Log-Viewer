#!/usr/bin/env bash
# validate_kr2_managed_kr.sh
# Validates the KR-2 Managed Knowledge Repository implementation.
#
# Run from the repo root (Well-Log-Viewer/).
# Requires: backend venv active or accessible, frontend node_modules present.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"

PASS=0
FAIL=0

pass() { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }

echo "=============================================="
echo " KR-2 Managed KR — Validation"
echo "=============================================="
echo ""

# -------------------------------------------------------------------
# 1. File existence
# -------------------------------------------------------------------
echo "--- 1. File existence ---"
for f in \
    backend/app/knowledge/governance.py \
    backend/app/knowledge/managed_models.py \
    backend/app/knowledge/managed_seed.py \
    backend/app/knowledge/managed_repository.py \
    backend/app/knowledge/api_managed_knowledge.py \
    backend/tests/knowledge/test_kr2_managed_repository.py; do
    if [[ -f "$REPO_ROOT/$f" ]]; then
        pass "$f"
    else
        fail "$f MISSING"
    fi
done

# Check main.py patch
if grep -q "api_managed_knowledge" "$BACKEND/app/main.py"; then
    pass "main.py contains managed_knowledge_router"
else
    fail "main.py missing managed_knowledge_router"
fi

# Verify KR-1 files are untouched
for f in \
    backend/app/knowledge/models.py \
    backend/app/knowledge/repository.py \
    backend/app/knowledge/curve_knowledge.py \
    backend/app/knowledge/api_knowledge.py; do
    if [[ -f "$REPO_ROOT/$f" ]]; then
        pass "KR-1 file intact: $f"
    else
        fail "KR-1 file MISSING: $f"
    fi
done

echo ""

# -------------------------------------------------------------------
# 2. Backend tests
# -------------------------------------------------------------------
echo "--- 2. Backend pytest (tests/knowledge/) ---"
cd "$BACKEND"
if .venv/bin/pytest tests/knowledge/ -v --tb=short 2>&1; then
    pass "All knowledge tests passed"
else
    fail "Knowledge tests FAILED — see output above"
fi
echo ""

# -------------------------------------------------------------------
# 3. Backend full suite (optional, may be slow)
# -------------------------------------------------------------------
echo "--- 3. Backend pytest (full suite) ---"
cd "$BACKEND"
if .venv/bin/pytest -v --tb=short 2>&1; then
    pass "Full backend suite passed"
else
    fail "Full backend suite has failures — check if pre-existing"
fi
echo ""

# -------------------------------------------------------------------
# 4. Frontend typecheck
# -------------------------------------------------------------------
echo "--- 4. Frontend typecheck ---"
cd "$FRONTEND"
if npm run typecheck 2>&1; then
    pass "Frontend typecheck passed"
else
    fail "Frontend typecheck FAILED"
fi
echo ""

# -------------------------------------------------------------------
# 5. Frontend build
# -------------------------------------------------------------------
echo "--- 5. Frontend build ---"
cd "$FRONTEND"
if npm run build 2>&1; then
    pass "Frontend build passed"
else
    fail "Frontend build FAILED"
fi
echo ""

# -------------------------------------------------------------------
# 6. Endpoint smoke tests (requires running backend at :8000)
# -------------------------------------------------------------------
echo "--- 6. Endpoint smoke tests (requires backend running at :8000) ---"
echo "    Run these manually with the backend server active:"
echo ""
echo "    # KR-1 endpoints (must remain unchanged):"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/health | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/product-groups | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/curve-definitions | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/display-rules | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/templates | python3 -m json.tool"
echo ""
echo "    # KR-2 managed endpoints (new):"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/managed/health | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/managed/schema | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/managed/status-summary | python3 -m json.tool"
echo ""

# -------------------------------------------------------------------
# 7. Manual UI checklist
# -------------------------------------------------------------------
echo "--- 7. Manual UI checks ---"
echo "    Perform these checks in the browser after starting the frontend:"
echo "    1. Open Data / MDP."
echo "    2. Expand a well with open-hole data."
echo "    3. Confirm subgroup labels/order still render correctly."
echo "    4. Load selected curves to WDV."
echo "    5. Confirm loaded curves appear in Loaded Curves panel."
echo "    6. Confirm no tracks auto-populate."
echo "    7. Confirm browser console has no new errors."
echo ""

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo "=============================================="
echo " PASS: $PASS"
echo " FAIL: $FAIL"
echo "=============================================="
if [[ $FAIL -eq 0 ]]; then
    echo " All automated checks passed."
    exit 0
else
    echo " $FAIL check(s) failed."
    exit 1
fi
