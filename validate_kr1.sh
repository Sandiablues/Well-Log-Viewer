#!/usr/bin/env bash
# validate_kr1.sh — WLV KR-1 Knowledge Repository validation
#
# Runs static checks that can execute without a running server.
# Runtime/endpoint/browser checks are documented at the bottom of this
# script and MUST be executed externally.
#
# Usage:
#   bash validate_kr1.sh
#
# Run from the Well-Log-Viewer repository root.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS  $1"; ((PASS++)); }
fail() { echo "  FAIL  $1"; ((FAIL++)); }
info() { echo "  INFO  $1"; }

echo "=== WLV KR-1 Validation ==="
echo "Repo: ${REPO_ROOT}"
echo "Date: $(date)"
echo ""

# ---------------------------------------------------------------------------
# 1. Static: required files present
# ---------------------------------------------------------------------------
echo "--- File presence ---"

check_file() {
  local f="$1" label="$2"
  if [[ -f "${REPO_ROOT}/${f}" ]]; then
    pass "${f} (${label})"
  else
    fail "${f} MISSING — ${label}"
  fi
}

check_file "backend/app/knowledge/__init__.py"                           "KR package init"
check_file "backend/app/knowledge/models.py"                             "KR Pydantic models"
check_file "backend/app/knowledge/repository.py"                         "KR seed repository"
check_file "backend/app/knowledge/api_knowledge.py"                      "KR FastAPI router"
check_file "backend/tests/knowledge/test_kr1_knowledge_repository.py"   "KR-1 tests"

# ---------------------------------------------------------------------------
# 2. Static: Python syntax on all KR-1 backend files
# ---------------------------------------------------------------------------
echo ""
echo "--- Python syntax ---"

KR1_PY_FILES=(
  "backend/app/knowledge/models.py"
  "backend/app/knowledge/repository.py"
  "backend/app/knowledge/api_knowledge.py"
  "backend/tests/knowledge/test_kr1_knowledge_repository.py"
  "backend/app/main.py"
)

for f in "${KR1_PY_FILES[@]}"; do
  if python3 -c "import ast; ast.parse(open('${REPO_ROOT}/${f}').read())" 2>/dev/null; then
    pass "${f} — syntax OK"
  else
    fail "${f} — syntax ERROR"
  fi
done

# ---------------------------------------------------------------------------
# 3. Static: main.py has knowledge router
# ---------------------------------------------------------------------------
echo ""
echo "--- Route registration ---"

if grep -q "from .knowledge.api_knowledge import router as knowledge_router" \
   "${REPO_ROOT}/backend/app/main.py"; then
  pass "backend/app/main.py imports knowledge_router"
else
  fail "backend/app/main.py missing knowledge_router import"
fi

if grep -q "app.include_router(knowledge_router)" \
   "${REPO_ROOT}/backend/app/main.py"; then
  pass "backend/app/main.py registers knowledge_router"
else
  fail "backend/app/main.py does not register knowledge_router"
fi

# ---------------------------------------------------------------------------
# 4. Static: KR-1 content checks (requires project venv python with pydantic)
# ---------------------------------------------------------------------------
echo ""
echo "--- KR-1 backend content (requires project venv) ---"

# Detect whether the project venv python (with pydantic) is available.
VENV_PYTHON="${REPO_ROOT}/backend/.venv/bin/python"
if [[ ! -x "${VENV_PYTHON}" ]]; then
  info "Project venv not found at ${VENV_PYTHON}"
  info "Skipping import-level checks — run with project venv to validate."
  info "Expected: get_product_groups()=8, get_curve_definitions()>=10, get_templates()=0"
else
  KR_GROUPS=$("${VENV_PYTHON}" -c "
import sys; sys.path.insert(0, '${REPO_ROOT}/backend')
from app.knowledge.repository import KnowledgeRepository
kr = KnowledgeRepository(); resp = kr.get_product_groups(); print(len(resp.groups))
" 2>/dev/null || echo "ERROR")

  if [[ "${KR_GROUPS}" == "8" ]]; then
    pass "KnowledgeRepository.get_product_groups() returns 8 groups"
  else
    fail "KnowledgeRepository.get_product_groups() returned: ${KR_GROUPS} (expected 8)"
  fi

  KR_CURVE_COUNT=$("${VENV_PYTHON}" -c "
import sys; sys.path.insert(0, '${REPO_ROOT}/backend')
from app.knowledge.repository import KnowledgeRepository
kr = KnowledgeRepository(); resp = kr.get_curve_definitions(); print(len(resp.curve_definitions))
" 2>/dev/null || echo "ERROR")

  if [[ "${KR_CURVE_COUNT}" =~ ^[0-9]+$ ]] && [[ "${KR_CURVE_COUNT}" -ge 10 ]]; then
    pass "KnowledgeRepository.get_curve_definitions() returns ${KR_CURVE_COUNT} definitions"
  else
    fail "KnowledgeRepository.get_curve_definitions() returned: ${KR_CURVE_COUNT}"
  fi

  KR_TEMPLATES=$("${VENV_PYTHON}" -c "
import sys; sys.path.insert(0, '${REPO_ROOT}/backend')
from app.knowledge.repository import KnowledgeRepository
kr = KnowledgeRepository(); resp = kr.get_templates(); print(len(resp.templates))
" 2>/dev/null || echo "ERROR")

  if [[ "${KR_TEMPLATES}" == "0" ]]; then
    pass "KnowledgeRepository.get_templates() returns empty list (KR-1: correct)"
  else
    fail "KnowledgeRepository.get_templates() returned ${KR_TEMPLATES} (expected 0)"
  fi
fi

# ---------------------------------------------------------------------------
# 5. Static: frontend KR-1 checks
# ---------------------------------------------------------------------------
echo ""
echo "--- Frontend KR-1 content ---"

TSX="${REPO_ROOT}/frontend/src/wells/prototype/TrackLayoutPrototype.tsx"

check_tsx_present()  { grep -q "$1" "${TSX}" && pass "TSX contains: $2" || fail "TSX missing: $2"; }
check_tsx_absent()   { grep -q "$1" "${TSX}" && fail "TSX still has: $2" || pass "TSX removed: $2"; }

check_tsx_absent  "OPEN_HOLE_SUBGROUP_ORDER"       "OPEN_HOLE_SUBGROUP_ORDER (frontend KR-truth removed)"
check_tsx_absent  "OPEN_HOLE_FALLBACK_SUBGROUP_LABELS" "OPEN_HOLE_FALLBACK_SUBGROUP_LABELS (frontend KR-truth removed)"
check_tsx_absent  "openHoleSubgroups("             "openHoleSubgroups() (frontend KR-truth removed)"
check_tsx_present "KrProductGroup"                 "KrProductGroup type"
check_tsx_present "KrSubgroup"                     "KrSubgroup type"
check_tsx_present "groupProductItemsByKrSubgroups" "groupProductItemsByKrSubgroups function"
check_tsx_present "krProductGroups"                "krProductGroups state"
check_tsx_present "/api/wlv/knowledge/product-groups" "KR product-groups endpoint fetch"
check_tsx_present "KrProductGroupsPayload"         "KrProductGroupsPayload type"

# ---------------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Static validation summary ==="
echo "  Passed: ${PASS}"
echo "  Failed: ${FAIL}"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
  echo "  STATIC CHECKS FAILED — review output above."
else
  echo "  All static checks passed."
fi

# ---------------------------------------------------------------------------
# 7. EXTERNAL TESTING REQUIRED (do not run here — execute separately)
# ---------------------------------------------------------------------------
echo ""
echo "=== EXTERNAL TESTING REQUIRED ==="
echo "  The following checks MUST be run externally with the backend running."
echo "  All runtime/endpoint/browser validation is deferred per work-order §12."
echo ""
echo "  Backend endpoint checks (requires: uvicorn running on :8000):"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/health | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/product-groups | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/curve-definitions | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/display-rules | python3 -m json.tool"
echo "    curl -s http://127.0.0.1:8000/api/wlv/knowledge/templates | python3 -m json.tool"
echo ""
echo "  Frontend typecheck (requires: node/npm in frontend/):"
echo "    cd frontend && npm run typecheck"
echo "    cd frontend && npm run build"
echo ""
echo "  Backend tests (requires: pytest in backend venv):"
echo "    cd backend && .venv/bin/pytest tests/knowledge/ -v"
echo "    cd backend && .venv/bin/pytest -v"
echo ""
echo "  Manual MDP checks (requires: running app in browser):"
echo "    1. Open MDP (Data tab)"
echo "    2. Expand a well with open-hole logs"
echo "    3. Confirm open-hole subgroups render using backend-provided labels/order"
echo "    4. Confirm Gamma Ray, Resistivity, Sonic/Acoustic etc. appear correctly"
echo "    5. Confirm no JavaScript errors in browser console"
echo ""
echo "  Manual WDV checks:"
echo "    1. Load a well from MDP to WDV"
echo "    2. Confirm loaded curves appear in Loaded Curves panel"
echo "    3. Confirm curves do NOT auto-populate well tracks"
echo "    4. Confirm WDV renders normally"
echo ""
echo "  Expected pass criteria:"
echo "    - All 5 /api/wlv/knowledge/* endpoints return 200 with version=kr-1"
echo "    - /health returns product_group_count=8, template_count=0"
echo "    - /product-groups returns 8 groups, open_hole_logs has >= 10 subgroups"
echo "    - npm run typecheck exits 0 (or failures are pre-existing and documented)"
echo "    - MDP subgroup rendering unchanged or improved"
echo "    - WDV load behavior unchanged"

exit $([[ "${FAIL}" -gt 0 ]] && echo 1 || echo 0)
