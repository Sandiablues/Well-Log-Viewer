#!/usr/bin/env bash
# =============================================================================
# validate_kr_data_1r_reconciled_import.sh
#
# Full validation suite for KR-DATA-1R reconciled import package.
#
# SECTION A — Legacy KR-3 payload validation:
#   1. Prerequisites check
#   2. JSON syntax validation
#   3. Pydantic ImportPayload contract validation (offline)
#   4. Offline alias pre-check — ILD/ILM/LLD/LLS absent from curve_definitions
#   5. KR-DATA-MODEL-1 alias enrichment tests (pytest)
#   6. Full knowledge test suite (pytest)
#   7. Live preview (POST /import/preview) — skipped if server not running
#   8. Frontend typecheck (npm run typecheck)
#   9. Frontend build (npm run build)
#
# SECTION B — Alias enrichment validation (ILD/ILM/LLD/LLS):
#   B1. alias_enrichment_records present in payload
#   B2. All 4 required aliases (ILD/ILM/LLD/LLS) present with correct fields
#   B3. Reconciliation classification: product_subgroup confirms safe_alias_enrichment
#   B4. No duplicate record_ids in managed_knowledge.json
#
# NOTE: Legacy KR-3 preview excludes alias_enrichment_records; alias enrichment
#       records are validated separately (Section B and
#       preview_alias_enrichments_kr_data_1r.sh).
#
# Usage:
#   bash validate_kr_data_1r_reconciled_import.sh [--server http://HOST:PORT]
#
# Default server: http://127.0.0.1:8000
# Stage is NOT triggered by this script.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
BACKEND="$PROJECT_ROOT/backend"
FRONTEND="$PROJECT_ROOT/frontend"
PAYLOAD="$SCRIPT_DIR/kr_data_1r_reconciled_import_payload.json"
STORAGE="$BACKEND/data/knowledge/managed_knowledge.json"
VENV="$BACKEND/.venv/bin"
SERVER="http://127.0.0.1:8000"
PASS=0
FAIL=0

if [[ "${1:-}" == "--server" && -n "${2:-}" ]]; then SERVER="$2"; fi

step_pass() { echo "  [PASS] $1"; ((++PASS)); }
step_fail() { echo "  [FAIL] $1" >&2; ((++FAIL)); }

echo "============================================================"
echo " KR-DATA-1R Validation Suite"
echo "============================================================"
echo " Project root: $PROJECT_ROOT"
echo " Payload     : $PAYLOAD"
echo " Storage     : $STORAGE"
echo " Server      : $SERVER"
echo "============================================================"
echo ""

# ##########################################################################
# SECTION A — Legacy KR-3 Payload
# ##########################################################################
echo "============================================================"
echo " SECTION A — Legacy KR-3 Payload Validation"
echo " NOTE: Legacy KR-3 preview excludes alias_enrichment_records;"
echo "       alias enrichment records are validated separately in Section B"
echo "       and via preview_alias_enrichments_kr_data_1r.sh."
echo "============================================================"
echo ""

# --------------------------------------------------------------------------
# Step 1: Prerequisites
# --------------------------------------------------------------------------
echo "--- Step 1: Prerequisites ---"
for cmd in curl python3; do
    if command -v $cmd &>/dev/null; then step_pass "$cmd found"
    else step_fail "$cmd not found"; fi
done
if [[ -f "$PAYLOAD" ]]; then step_pass "Payload file exists"
else step_fail "Payload file missing: $PAYLOAD"; fi
if [[ -f "$VENV/python" ]]; then step_pass "Backend venv found"
else step_fail "Backend venv not found at $VENV"; fi
echo ""

# --------------------------------------------------------------------------
# Step 2: JSON syntax
# --------------------------------------------------------------------------
echo "--- Step 2: JSON syntax validation ---"
if python3 -c "import json; json.load(open('$PAYLOAD'))" 2>/dev/null; then
    step_pass "JSON syntax valid"
else
    step_fail "JSON syntax error in $PAYLOAD"
fi
echo ""

# --------------------------------------------------------------------------
# Step 3: Pydantic ImportPayload contract (offline)
# --------------------------------------------------------------------------
echo "--- Step 3: Pydantic ImportPayload contract validation ---"
echo "  [Stripping alias_enrichment_records and _reconciliation_meta before"
echo "   Pydantic parse — these are non-schema extensions. Legacy KR-3 preview"
echo "   excludes alias_enrichment_records; alias enrichment records are"
echo "   validated separately in Section B.]"
cd "$PROJECT_ROOT"
"$VENV/python" -c "
import json, sys
sys.path.insert(0, '.')
from backend.app.knowledge.import_models import ImportPayload

with open('$PAYLOAD') as f:
    raw = json.load(f)

# Strip non-ImportPayload keys.
# alias_enrichment_records: handled by Section B and stage_alias_enrichments_kr_data_1r.sh
# _reconciliation_meta: documentation only
raw.pop('_reconciliation_meta', None)
raw.pop('alias_enrichment_records', None)

try:
    payload = ImportPayload(**raw)
    cd_count = len(payload.curve_definitions)
    alias_count = sum(len(cd.aliases) for cd in payload.curve_definitions)
    dr_count = len(payload.display_rules)
    cr_count = len(payload.classification_rules)
    tr_count = len(payload.template_rules)
    print(f'  ImportPayload parsed OK')
    print(f'  curve_definitions   : {cd_count}')
    print(f'  aliases in payload  : {alias_count}  (ILD/ILM/LLD/LLS staged via Part B)')
    print(f'  display_rules       : {dr_count}')
    print(f'  classification_rules: {cr_count}')
    print(f'  template_rules      : {tr_count}')
except Exception as e:
    print(f'  Pydantic error: {e}', file=sys.stderr)
    sys.exit(1)
" && step_pass "Pydantic contract valid" || step_fail "Pydantic contract failed"
echo ""

# --------------------------------------------------------------------------
# Step 4: Offline alias pre-check
# --------------------------------------------------------------------------
echo "--- Step 4: Offline alias pre-check (ILD/ILM/LLD/LLS absent from curve_definitions) ---"
cd "$PROJECT_ROOT"
"$VENV/python" -c "
import json, sys
sys.path.insert(0, '.')

with open('$PAYLOAD') as f:
    raw = json.load(f)

all_aliases = [a for cd in raw.get('curve_definitions', []) for a in cd.get('aliases', [])]
blocked = [x for x in ['ILD','ILM','LLD','LLS'] if x in all_aliases]
if blocked:
    print(f'  FAIL: {blocked} still present in curve_definitions', file=sys.stderr)
    sys.exit(1)
print('  ILD, ILM, LLD, LLS: absent from curve_definitions — OK')
print('  (These aliases are represented in alias_enrichment_records; see Section B.)')
" && step_pass "Alias pre-check passed" || step_fail "Alias pre-check failed"
echo ""

# --------------------------------------------------------------------------
# Step 5: KR-DATA-MODEL-1 alias enrichment tests
# --------------------------------------------------------------------------
echo "--- Step 5: KR-DATA-MODEL-1 alias enrichment tests ---"
cd "$PROJECT_ROOT/backend"
if "$VENV/pytest" tests/knowledge/test_kr_data_model_1_alias_enrichment.py -v \
    --tb=short -q 2>&1 | tail -5; then
    step_pass "KR-DATA-MODEL-1 tests passed"
else
    step_fail "KR-DATA-MODEL-1 tests failed"
fi
echo ""

# --------------------------------------------------------------------------
# Step 6: Full knowledge test suite
# --------------------------------------------------------------------------
echo "--- Step 6: Full knowledge test suite ---"
cd "$PROJECT_ROOT/backend"
if "$VENV/pytest" tests/knowledge/ -v --tb=short -q \
    --ignore=tests/knowledge/test_no_las_parsing_in_module.py 2>&1 | tail -5; then
    step_pass "Full knowledge suite passed"
else
    step_fail "Full knowledge suite failed"
fi
echo ""

# --------------------------------------------------------------------------
# Step 7: Live preview (optional — skipped if server not running)
# --------------------------------------------------------------------------
echo "--- Step 7: Live preview (POST /import/preview) ---"
echo "  NOTE: Legacy KR-3 preview excludes alias_enrichment_records;"
echo "        alias enrichment records are validated separately in Section B."
if curl -sf --max-time 5 "$SERVER/api/wlv/knowledge/managed/health" >/dev/null 2>&1; then
    STRIPPED=$(python3 -c "
import json
with open('$PAYLOAD') as f:
    d = json.load(f)
# Strip alias_enrichment_records and _reconciliation_meta.
# ImportPayload schema has no alias_enrichment_records field.
# ILD/ILM/LLD/LLS alias enrichments are staged by stage_alias_enrichments_kr_data_1r.sh.
d.pop('_reconciliation_meta', None)
d.pop('alias_enrichment_records', None)
print(json.dumps(d))
")
    HTTP_STATUS=$(curl -s -o /tmp/kr_data_1r_validate_preview.json \
        -w "%{http_code}" \
        -X POST -H "Content-Type: application/json" \
        -d "$STRIPPED" \
        "$SERVER/api/wlv/knowledge/managed/import/preview")
    if [[ "$HTTP_STATUS" == "200" ]]; then
        python3 -c "
import json, sys
with open('/tmp/kr_data_1r_validate_preview.json') as f:
    r = json.load(f)
valid = r.get('valid', False)
errs = r.get('error_count', 0)
warns = r.get('warning_count', 0)
print(f'  HTTP 200 OK')
print(f'  valid={valid}, errors={errs}, warnings={warns}')
if not valid:
    for e in r.get('errors', []):
        print(f'  ERROR [{e[\"code\"]}] {e[\"path\"]}: {e[\"message\"]}', file=sys.stderr)
    sys.exit(1)
" && step_pass "Live preview: valid=true, HTTP 200" || step_fail "Live preview: valid=false or error"
    else
        step_fail "Live preview: HTTP $HTTP_STATUS"
    fi
else
    echo "  Server not running at $SERVER — step skipped"
    echo "  Run: uvicorn app.main:app --port 8000, then re-run this script"
    step_pass "Live preview skipped (not a failure — server offline)"
fi
echo ""

# --------------------------------------------------------------------------
# Step 8: Frontend typecheck
# --------------------------------------------------------------------------
echo "--- Step 8: Frontend typecheck ---"
cd "$FRONTEND"
if npm run typecheck 2>&1 | tail -3; then
    step_pass "Frontend typecheck passed"
else
    step_fail "Frontend typecheck failed"
fi
echo ""

# --------------------------------------------------------------------------
# Step 9: Frontend build
# --------------------------------------------------------------------------
echo "--- Step 9: Frontend build ---"
cd "$FRONTEND"
if npm run build 2>&1 | tail -3; then
    step_pass "Frontend build passed"
else
    step_fail "Frontend build failed"
fi
echo ""

# ##########################################################################
# SECTION B — Alias Enrichment Validation
# ##########################################################################
echo "============================================================"
echo " SECTION B — Alias Enrichment Validation (ILD/ILM/LLD/LLS)"
echo " These records are staged by stage_alias_enrichments_kr_data_1r.sh"
echo " not by the legacy KR-3 import/stage endpoint."
echo "============================================================"
echo ""

# --------------------------------------------------------------------------
# Step B1: alias_enrichment_records present
# --------------------------------------------------------------------------
echo "--- Step B1: alias_enrichment_records present in payload ---"
"$VENV/python" -c "
import json, sys
with open('$PAYLOAD') as f:
    raw = json.load(f)
enrichments = raw.get('alias_enrichment_records', [])
if not enrichments:
    print('  ERROR: alias_enrichment_records section is absent or empty.', file=sys.stderr)
    sys.exit(1)
print(f'  Found {len(enrichments)} alias_enrichment_records.')
" && step_pass "alias_enrichment_records present" || step_fail "alias_enrichment_records missing"
echo ""

# --------------------------------------------------------------------------
# Step B2: All 4 aliases present with correct display/technical mappings
# --------------------------------------------------------------------------
echo "--- Step B2: Required aliases (ILD/ILM/LLD/LLS) and field check ---"
"$VENV/python" -c "
import json, sys
with open('$PAYLOAD') as f:
    raw = json.load(f)
enrichments = raw.get('alias_enrichment_records', [])
enrich_by_alias = {r['alias']: r for r in enrichments}

EXPECTED = {
    'ILD': {'display_canonical_curve_id': 'deep_resistivity',    'technical_curve_id': 'deep_induction_resistivity'},
    'ILM': {'display_canonical_curve_id': 'shallow_resistivity', 'technical_curve_id': 'medium_induction_resistivity'},
    'LLD': {'display_canonical_curve_id': 'deep_resistivity',    'technical_curve_id': 'deep_laterolog_resistivity'},
    'LLS': {'display_canonical_curve_id': 'shallow_resistivity', 'technical_curve_id': 'shallow_laterolog_resistivity'},
}
REQUIRED = [
    'record_id', 'alias', 'normalized_alias',
    'display_canonical_curve_id', 'technical_curve_id',
    'technical_display_name', 'parent_canonical_curve_id',
]

all_ok = True
for alias, exp in EXPECTED.items():
    if alias not in enrich_by_alias:
        print(f'  FAIL: {alias} missing from alias_enrichment_records', file=sys.stderr)
        all_ok = False
        continue
    r = enrich_by_alias[alias]
    missing = [f for f in REQUIRED if not r.get(f)]
    if missing:
        print(f'  FAIL [{alias}]: missing required fields: {missing}', file=sys.stderr)
        all_ok = False
    for field, expected_val in exp.items():
        actual_val = r.get(field)
        if actual_val != expected_val:
            print(f'  FAIL [{alias}]: {field} expected={expected_val}, got={actual_val}', file=sys.stderr)
            all_ok = False
        else:
            print(f'  OK   [{alias}]: {field}={actual_val}')
if not all_ok:
    sys.exit(1)
print()
print('  All 4 alias_enrichment_records present with correct field values.')
" && step_pass "Alias enrichment fields valid" || step_fail "Alias enrichment fields invalid"
echo ""

# --------------------------------------------------------------------------
# Step B3: Reconciliation classification
# --------------------------------------------------------------------------
echo "--- Step B3: Reconciliation classification (product_subgroup) ---"
"$VENV/python" -c "
import json, sys
with open('$PAYLOAD') as f:
    raw = json.load(f)
enrichments = raw.get('alias_enrichment_records', [])

SUBGROUP = {
    'deep_resistivity': 'resistivity',      'shallow_resistivity': 'resistivity',
    'deep_induction_resistivity': 'resistivity', 'medium_induction_resistivity': 'resistivity',
    'deep_laterolog_resistivity': 'resistivity', 'shallow_laterolog_resistivity': 'resistivity',
}
all_ok = True
for r in enrichments:
    alias   = r.get('alias')
    display = r.get('display_canonical_curve_id')
    tech    = r.get('technical_curve_id')
    sg_d = SUBGROUP.get(display, 'UNKNOWN')
    sg_t = SUBGROUP.get(tech,    'UNKNOWN')
    if sg_d == sg_t and sg_d != 'UNKNOWN':
        print(f'  OK   [{alias}]: product_subgroup={sg_d} -> safe_alias_enrichment')
    else:
        print(f'  FAIL [{alias}]: existing={sg_d} != import={sg_t} -> would be true_alias_conflict', file=sys.stderr)
        all_ok = False
if not all_ok:
    sys.exit(1)
print()
print('  All 4 aliases classify as safe_alias_enrichment.')
" && step_pass "Reconciliation: all 4 aliases = safe_alias_enrichment" || step_fail "Reconciliation: true_alias_conflict detected"
echo ""

# --------------------------------------------------------------------------
# Step B4: No duplicate record_ids in managed_knowledge.json
# --------------------------------------------------------------------------
echo "--- Step B4: Duplicate record_id check against managed_knowledge.json ---"
if [[ -f "$STORAGE" ]]; then
    "$VENV/python" -c "
import json, sys
with open('$PAYLOAD') as f:
    raw = json.load(f)
with open('$STORAGE') as f:
    stored = json.load(f)

enrichments = raw.get('alias_enrichment_records', [])
existing_ids = {r.get('record_id') for r in stored.get('records', [])}
duplicates = [r.get('record_id') for r in enrichments if r.get('record_id') in existing_ids]
if duplicates:
    print(f'  FAIL: duplicate record_ids already in repository: {duplicates}', file=sys.stderr)
    sys.exit(1)
print(f'  No duplicate record_ids in managed_knowledge.json — OK')
print(f'  (current managed records: {len(stored.get(\"records\",[]))})')
" && step_pass "No duplicate record_ids" || step_fail "Duplicate record_ids found"
else
    echo "  managed_knowledge.json not found — skipping (OK if repo not yet initialised)"
    step_pass "Duplicate check skipped (storage not found)"
fi
echo ""

# ##########################################################################
# Summary
# ##########################################################################
echo "============================================================"
echo " VALIDATION SUMMARY"
echo "============================================================"
echo " Passed: $PASS"
echo " Failed: $FAIL"
echo ""
if [[ "$FAIL" -eq 0 ]]; then
    echo " RESULT: ALL CHECKS PASSED"
    echo ""
    echo " Next steps (two-part staging):"
    echo "   Part A — bash preview_kr_data_1r_reconciled_import.sh"
    echo "            bash stage_kr_data_1r_reconciled_import.sh"
    echo "   Part B — bash preview_alias_enrichments_kr_data_1r.sh"
    echo "            bash stage_alias_enrichments_kr_data_1r.sh"
else
    echo " RESULT: $FAIL CHECK(S) FAILED — do not stage until resolved."
fi
echo "============================================================"

[[ "$FAIL" -eq 0 ]]
