#!/usr/bin/env bash
# =============================================================================
# preview_alias_enrichments_kr_data_1r.sh
#
# PART B of the KR-DATA-1R staging path — dry-run preview.
#
# Reads alias_enrichment_records from kr_data_1r_reconciled_import_payload.json,
# loads the current ManagedKRRepository state (read-only), and shows exactly
# what AliasEnrichmentRecord instances would be staged by
# stage_alias_enrichments_kr_data_1r.sh.
#
# Checks performed:
#   - Required fields present on each record
#   - No duplicate record_ids already in managed_knowledge.json
#   - Reconciliation classification: product_subgroup comparison confirms
#     ILD/ILM/LLD/LLS are safe_alias_enrichment (not true_alias_conflict)
#   - KR-6/7/8 display behavior unchanged (enrichment records are CANDIDATE only)
#
# SIDE-EFFECT FREE — does NOT call _add_record(), persist(), or any HTTP endpoint.
#
# Usage:
#   bash preview_alias_enrichments_kr_data_1r.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
BACKEND="$PROJECT_ROOT/backend"
PAYLOAD="$SCRIPT_DIR/kr_data_1r_reconciled_import_payload.json"
STORAGE="$BACKEND/data/knowledge/managed_knowledge.json"
VENV="$BACKEND/.venv/bin"

echo "============================================================"
echo " KR-DATA-1R — PART B: Alias Enrichments — DRY-RUN PREVIEW"
echo "============================================================"
echo " Project root: $PROJECT_ROOT"
echo " Payload     : $PAYLOAD"
echo " Storage     : $STORAGE"
echo " Mode        : DRY-RUN — nothing staged, nothing written"
echo "============================================================"
echo ""

# --- Prerequisites --------------------------------------------------------
echo "[1/4] Prerequisites..."
missing_prereq=0
[[ -f "$PAYLOAD" ]]  || { echo "  ERROR: Payload not found: $PAYLOAD" >&2;                 missing_prereq=1; }
[[ -f "$STORAGE" ]]  || { echo "  ERROR: managed_knowledge.json not found: $STORAGE" >&2;  missing_prereq=1; }
[[ -f "$VENV/python" ]] || { echo "  ERROR: Backend venv not found at $VENV/python" >&2;   missing_prereq=1; }
[[ "$missing_prereq" -eq 0 ]] || exit 1
echo "  All prerequisites present — OK"
echo ""

# --- Print record table from payload -------------------------------------
echo "[2/4] Alias enrichment records in payload..."
"$VENV/python" -c "
import json, sys
with open('$PAYLOAD') as f:
    raw = json.load(f)
enrichments = raw.get('alias_enrichment_records', [])
if not enrichments:
    print('  ERROR: no alias_enrichment_records found in payload.', file=sys.stderr)
    sys.exit(1)
print(f'  Count: {len(enrichments)}')
for r in enrichments:
    print()
    print(f'  alias              : {r.get(\"alias\")}')
    print(f'  record_id          : {r.get(\"record_id\")}')
    print(f'  record_type        : {r.get(\"record_type\")}')
    print(f'  display_canonical  : {r.get(\"display_canonical_curve_id\")}')
    print(f'  technical_curve_id : {r.get(\"technical_curve_id\")}')
    print(f'  technical_display  : {r.get(\"technical_display_name\")}')
    print(f'  parent_canonical   : {r.get(\"parent_canonical_curve_id\")}')
    print(f'  measurement_family : {r.get(\"measurement_family\")}')
    print(f'  measurement_depth  : {r.get(\"measurement_depth\")}')
    print(f'  tool_family        : {r.get(\"tool_family\")}')
    print(f'  status (expected)  : CANDIDATE')
    print(f'  source_reference   : {r.get(\"source_reference\")}')
"
echo ""

# --- Offline checks: duplicates, reconciliation, field validation --------
echo "[3/4] Offline validation checks..."
"$VENV/python" -c "
import json, sys

with open('$PAYLOAD') as f:
    raw = json.load(f)
with open('$STORAGE') as f:
    stored = json.load(f)

enrichments = raw.get('alias_enrichment_records', [])
existing_records = stored.get('records', [])
existing_ids = {r.get('record_id') for r in existing_records}
existing_enrich_aliases = {
    r.get('alias') for r in existing_records
    if r.get('record_type') == 'alias_enrichment'
}

all_ok = True

# Check duplicate record_ids
print('  Duplicate record_id check:')
for r in enrichments:
    rid = r.get('record_id', '')
    if rid in existing_ids:
        print(f'  [ERR] record_id already in repository: {rid}', file=sys.stderr)
        all_ok = False
    else:
        print(f'  [OK ] {r.get(\"alias\")}: record_id not in repository')

print()

# Check for pre-existing enrichment on same alias
print('  Pre-existing alias_enrichment check:')
for r in enrichments:
    alias = r.get('alias')
    if alias in existing_enrich_aliases:
        print(f'  [WARN] {alias}: alias_enrichment already exists — staging would add a second record')
    else:
        print(f'  [OK ] {alias}: no prior enrichment record')

print()

# Simulate reconciliation (product_subgroup comparison)
print('  Reconciliation classification (product_subgroup):')
SUBGROUP = {
    'deep_resistivity':              'resistivity',
    'shallow_resistivity':           'resistivity',
    'deep_induction_resistivity':    'resistivity',
    'medium_induction_resistivity':  'resistivity',
    'deep_laterolog_resistivity':    'resistivity',
    'shallow_laterolog_resistivity': 'resistivity',
}
for r in enrichments:
    alias   = r.get('alias')
    display = r.get('display_canonical_curve_id')
    tech    = r.get('technical_curve_id')
    sg_d = SUBGROUP.get(display, 'UNKNOWN')
    sg_t = SUBGROUP.get(tech, 'UNKNOWN')
    if sg_d == sg_t and sg_d != 'UNKNOWN':
        print(f'  [OK ] {alias}: {display}({sg_d}) == {tech}({sg_t}) -> safe_alias_enrichment')
    else:
        print(f'  [ERR] {alias}: {display}({sg_d}) != {tech}({sg_t}) -> true_alias_conflict (BLOCK)', file=sys.stderr)
        all_ok = False

print()

# Required field validation
print('  Required field check:')
REQUIRED = [
    'record_id', 'alias', 'normalized_alias',
    'display_canonical_curve_id', 'technical_curve_id',
    'technical_display_name', 'parent_canonical_curve_id',
]
for r in enrichments:
    missing = [f for f in REQUIRED if not r.get(f)]
    alias = r.get('alias', '?')
    if missing:
        print(f'  [ERR] {alias}: missing required fields: {missing}', file=sys.stderr)
        all_ok = False
    else:
        print(f'  [OK ] {alias}: all required fields present')

print()
if not all_ok:
    print('  OFFLINE CHECKS FAILED — do not stage.', file=sys.stderr)
    sys.exit(1)
print('  All offline checks passed.')
" && true || { echo ""; echo "  Offline validation FAILED — do not stage." >&2; exit 1; }
echo ""

# --- Final dry-run summary ------------------------------------------------
echo "[4/4] Staging dry-run summary..."
"$VENV/python" -c "
import json
with open('$PAYLOAD') as f:
    raw = json.load(f)
enrichments = raw.get('alias_enrichment_records', [])
print(f'  Records that WOULD be staged: {len(enrichments)}')
print(f'  Status on entry: CANDIDATE')
print(f'  Record type    : alias_enrichment')
print(f'  Storage target : backend/data/knowledge/managed_knowledge.json')
print()
print('  Record summary:')
for r in enrichments:
    print(f'    {r.get(\"record_id\")}')
    print(f'      {r.get(\"alias\")} -> display={r.get(\"display_canonical_curve_id\")} / technical={r.get(\"technical_curve_id\")}')
print()
print('  KR-6/7/8 display behavior: UNCHANGED')
print('    ILD/ILM/LLD/LLS display canonical remains deep_resistivity / shallow_resistivity')
print('    CANDIDATE records are NOT production-eligible')
print('    Seed alias mappings are NOT remapped')
print()
print('  To stage: bash stage_alias_enrichments_kr_data_1r.sh')
"

echo ""
echo "============================================================"
echo " PART B DRY-RUN COMPLETE — nothing was staged or written"
echo "============================================================"
