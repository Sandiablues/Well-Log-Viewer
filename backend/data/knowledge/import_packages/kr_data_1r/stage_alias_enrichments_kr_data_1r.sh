#!/usr/bin/env bash
# =============================================================================
# stage_alias_enrichments_kr_data_1r.sh
#
# PART B of the KR-DATA-1R staging path.
#
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# WARNING: This script stages 4 AliasEnrichmentRecord CANDIDATE records into
#          managed_knowledge.json via the backend managed repository.
#
#          Do NOT run unless:
#            1. preview_alias_enrichments_kr_data_1r.sh has been reviewed
#            2. stage_kr_data_1r_reconciled_import.sh (Part A) has completed
#          Rollback: bash rollback_kr_data_1r_staging.sh --surgical
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#
# This script uses the backend Python modules directly (not the HTTP import
# endpoint) because the ImportPayload schema does not have an
# alias_enrichment_records field.  The backend API endpoint
# POST /import/stage only handles ImportPayload records.
#
# Staging mechanism:
#   - Loads AliasEnrichmentRecord from backend.app.knowledge.alias_enrichment_models
#   - Constructs each record from alias_enrichment_records in the payload JSON
#   - Calls repository._add_record() for each record
#   - _add_record() adds to _managed_records and calls persist() to write JSON
#   - All records enter as status=CANDIDATE (default)
#   - CANDIDATE records are NOT production-eligible; KR-6/7/8 is UNCHANGED
#
# Usage:
#   bash stage_alias_enrichments_kr_data_1r.sh [--yes]
#
# Without --yes you will be prompted to confirm before any mutation occurs.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
BACKEND="$PROJECT_ROOT/backend"
PAYLOAD="$SCRIPT_DIR/kr_data_1r_reconciled_import_payload.json"
STORAGE="$BACKEND/data/knowledge/managed_knowledge.json"
VENV="$BACKEND/.venv/bin"
CONFIRM="no"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) CONFIRM="yes"; shift ;;
        *)     echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

BACKUP="$STORAGE.before_kr_data_1r_enrich_$(date +%Y%m%d_%H%M%S)"

echo "============================================================"
echo " KR-DATA-1R — PART B: Alias Enrichments — STAGE"
echo "============================================================"
echo " Project root  : $PROJECT_ROOT"
echo " Payload       : $PAYLOAD"
echo " Storage       : $STORAGE"
echo " Backup target : $BACKUP"
echo ""
echo " !!! WARNING: This will mutate managed_knowledge.json !!!"
echo " Ensure preview_alias_enrichments_kr_data_1r.sh has been reviewed."
echo " All records enter as status=CANDIDATE."
echo " CANDIDATE records do NOT affect KR-6/7/8 display behavior."
echo " Seed alias mappings are NOT remapped."
echo "============================================================"
echo ""

# --- Confirmation ---------------------------------------------------------
if [[ "$CONFIRM" != "yes" ]]; then
    read -r -p "Type 'stage' to confirm alias enrichment staging, or Ctrl-C to abort: " REPLY
    if [[ "$REPLY" != "stage" ]]; then
        echo "Aborted." ; exit 0
    fi
fi

# --- Prerequisites --------------------------------------------------------
echo "[1/5] Prerequisites..."
missing_prereq=0
[[ -f "$PAYLOAD" ]]     || { echo "  ERROR: Payload not found: $PAYLOAD" >&2;               missing_prereq=1; }
[[ -f "$STORAGE" ]]     || { echo "  ERROR: managed_knowledge.json not found" >&2;           missing_prereq=1; }
[[ -f "$VENV/python" ]] || { echo "  ERROR: Backend venv not found at $VENV/python" >&2;    missing_prereq=1; }
[[ "$missing_prereq" -eq 0 ]] || exit 1
echo "  All prerequisites present — OK"
echo ""

# --- Pre-stage dry-run validation ----------------------------------------
echo "[2/5] Pre-stage offline validation (duplicate check, field check)..."
"$VENV/python" -c "
import json, sys

with open('$PAYLOAD') as f:
    raw = json.load(f)
with open('$STORAGE') as f:
    stored = json.load(f)

enrichments = raw.get('alias_enrichment_records', [])
if not enrichments:
    print('ERROR: no alias_enrichment_records in payload', file=sys.stderr)
    sys.exit(1)

existing_ids = {r.get('record_id') for r in stored.get('records', [])}
REQUIRED = [
    'record_id', 'alias', 'normalized_alias',
    'display_canonical_curve_id', 'technical_curve_id',
    'technical_display_name', 'parent_canonical_curve_id',
]
all_ok = True
for r in enrichments:
    alias = r.get('alias', '?')
    rid = r.get('record_id', '')
    if rid in existing_ids:
        print(f'  ERROR: duplicate record_id already in repository: {rid}', file=sys.stderr)
        all_ok = False
    missing = [f for f in REQUIRED if not r.get(f)]
    if missing:
        print(f'  ERROR [{alias}]: missing required fields: {missing}', file=sys.stderr)
        all_ok = False
    if all_ok:
        print(f'  {alias}: validation OK (record_id={rid})')
if not all_ok:
    print('Pre-stage validation FAILED — aborting.', file=sys.stderr)
    sys.exit(1)
print(f'  {len(enrichments)} records validated — proceeding to backup.')
" || exit 1
echo ""

# --- Backup ---------------------------------------------------------------
echo "[3/5] Backing up managed_knowledge.json..."
cp "$STORAGE" "$BACKUP"
echo "  Backup: $BACKUP"
echo ""

# --- Stage via ManagedKRRepository._add_record() -------------------------
echo "[4/5] Staging alias enrichment records..."
cd "$PROJECT_ROOT"
"$VENV/python" -c "
import json, sys
sys.path.insert(0, '$PROJECT_ROOT')

from backend.app.knowledge.alias_enrichment_models import AliasEnrichmentRecord
from backend.app.knowledge.governance import GovernanceStatus

# Import ManagedKRRepository.  Pass the storage path explicitly so the script
# works from any working directory.
from pathlib import Path
from backend.app.knowledge.managed_repository import ManagedKRRepository

PAYLOAD  = '$PAYLOAD'
STORAGE  = '$STORAGE'

with open(PAYLOAD) as f:
    raw = json.load(f)

enrichments_data = raw.get('alias_enrichment_records', [])

# Initialise the repository pointing at the production storage file.
# ManagedKRRepository loads seed records from managed_seed.py automatically.
repo = ManagedKRRepository(storage_path=Path(STORAGE))

staged_ids = []
for r in enrichments_data:
    record = AliasEnrichmentRecord(
        record_id=r['record_id'],
        alias=r['alias'],
        normalized_alias=r['normalized_alias'],
        display_canonical_curve_id=r['display_canonical_curve_id'],
        technical_curve_id=r['technical_curve_id'],
        technical_display_name=r['technical_display_name'],
        parent_canonical_curve_id=r['parent_canonical_curve_id'],
        status=GovernanceStatus.CANDIDATE,
        measurement_family=r.get('measurement_family'),
        measurement_depth=r.get('measurement_depth'),
        tool_family=r.get('tool_family'),
        selection_priority=r.get('selection_priority'),
        confidence=float(r.get('confidence', 1.0)),
        source_reference=r.get('source_reference'),
        review_notes=r.get('review_notes'),
    )
    repo._add_record(record)
    staged_ids.append(record.record_id)
    print(f'  STAGED: {record.alias} -> record_id={record.record_id}, status={record.status}')

print()
print(f'  Total staged: {len(staged_ids)}')
print(f'  Persisted to: $STORAGE')
" || {
    echo ""
    echo "  ERROR: staging failed — restoring backup." >&2
    cp "$BACKUP" "$STORAGE"
    echo "  Backup restored from $BACKUP" >&2
    exit 1
}
echo ""

# --- Post-stage verification ----------------------------------------------
echo "[5/5] Post-stage verification..."
"$VENV/python" -c "
import json, sys

with open('$STORAGE') as f:
    stored = json.load(f)

enrichment_records = [
    r for r in stored.get('records', [])
    if r.get('record_type') == 'alias_enrichment'
    and r.get('record_id', '').startswith('kr_data_1r_')
]

if not enrichment_records:
    print('  ERROR: no kr_data_1r alias_enrichment records found after staging.', file=sys.stderr)
    sys.exit(1)

print(f'  {len(enrichment_records)} kr_data_1r alias_enrichment record(s) found in storage:')
for r in enrichment_records:
    status = r.get('status', '?')
    if status != 'CANDIDATE':
        print(f'  WARNING: {r.get(\"record_id\")} has status={status}, expected CANDIDATE')
    else:
        print(f'  OK: {r.get(\"record_id\")} -> status={status}')
print()
print('  KR-6/7/8 check: CANDIDATE records are not production-eligible.')
print('  Seed alias mappings are unchanged.')
" || {
    echo "  Post-stage verification failed — check managed_knowledge.json manually." >&2
    exit 1
}
echo ""

echo "============================================================"
echo " PART B STAGE COMPLETE"
echo "============================================================"
echo ""
echo "  4 AliasEnrichmentRecord instances staged as CANDIDATE."
echo "  ILD/ILM/LLD/LLS display canonical: UNCHANGED."
echo "  KR-6/7/8 display behavior: UNCHANGED."
echo ""
echo "  Backup: $BACKUP"
echo "  To rollback: bash rollback_kr_data_1r_staging.sh --surgical"
echo "  To rollback to pre-stage state:"
echo "    bash rollback_kr_data_1r_staging.sh --backup $BACKUP"
echo ""
echo "  Review candidates:"
echo "    GET /api/wlv/knowledge/managed/records?status=CANDIDATE"
echo ""
echo "============================================================"
