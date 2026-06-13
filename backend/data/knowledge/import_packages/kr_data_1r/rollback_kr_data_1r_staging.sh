#!/usr/bin/env bash
# =============================================================================
# rollback_kr_data_1r_staging.sh
#
# Rollback KR-DATA-1R staged records from managed_knowledge.json.
#
# Covers BOTH parts of the KR-DATA-1R staging path:
#   Part A: Legacy KR-3 ImportPayload candidate records
#           (CurveDefinition, DisplayRule, ClassificationRule, TemplateRule)
#   Part B: AliasEnrichmentRecord candidates for ILD/ILM/LLD/LLS
#           (record_type="alias_enrichment", record_id prefix "kr_data_1r_")
#
# Two modes:
#
#   1. Backup-file restore (fast, preferred — reverts to exact pre-stage state):
#      bash rollback_kr_data_1r_staging.sh --backup /path/to/backup.json
#
#   2. Surgical removal (removes only KR-DATA-1R records, preserving all other
#      records including seed and other import packages):
#      bash rollback_kr_data_1r_staging.sh --surgical
#
# Surgical identification criteria:
#   - record_id starts with 'kr_data_1r_'   (covers Part A and Part B)
#   - source_reference == 'kr_data_1r_reconciled_import_20260613'
#   - evidence_refs contains 'kr_data_1r_reconciled_import_20260613'
#
# NEVER modifies seed records or records from other import packages.
# NEVER deletes source catalogue files.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
STORAGE="$PROJECT_ROOT/backend/data/knowledge/managed_knowledge.json"
MODE=""
BACKUP_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup)   MODE="backup";   BACKUP_FILE="$2"; shift 2 ;;
        --surgical) MODE="surgical"; shift ;;
        *)          echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$MODE" ]]; then
    echo "Usage:"
    echo "  $0 --backup /path/to/managed_knowledge.json.before_kr_data_1r_TIMESTAMP"
    echo "  $0 --surgical"
    echo ""
    echo "Surgical mode removes ALL kr_data_1r records (Part A and Part B)."
    exit 1
fi

echo "============================================================"
echo " KR-DATA-1R Rollback — mode=$MODE"
echo " Covers: Part A (legacy KR-3 candidates) AND"
echo "         Part B (alias_enrichment candidates: ILD/ILM/LLD/LLS)"
echo "============================================================"
echo " Storage: $STORAGE"
echo ""

if [[ ! -f "$STORAGE" ]]; then
    echo "ERROR: managed_knowledge.json not found: $STORAGE" >&2
    exit 1
fi

if [[ "$MODE" == "backup" ]]; then
    if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
        echo "ERROR: Backup file not found: ${BACKUP_FILE:-<none>}" >&2
        exit 1
    fi
    echo "Restoring from backup: $BACKUP_FILE"
    cp "$BACKUP_FILE" "$STORAGE"
    echo "Rollback complete (backup restore)."

elif [[ "$MODE" == "surgical" ]]; then
    echo "Running surgical removal of KR-DATA-1R records (Part A + Part B)..."
    python3 -c "
import json, sys

STORAGE = '$STORAGE'
KR_DATA_1R_SOURCE_REF  = 'kr_data_1r_reconciled_import_20260613'
KR_DATA_1R_ID_PREFIX   = 'kr_data_1r_'

with open(STORAGE) as f:
    data = json.load(f)

original_count    = len(data.get('records', []))
original_evidence = len(data.get('evidence_records', []))

def is_kr_data_1r_record(r):
    record_id = r.get('record_id', '')
    # Part A and Part B: both use kr_data_1r_ prefix
    if record_id.startswith(KR_DATA_1R_ID_PREFIX):
        return True
    # Match by source_reference (Part A import batch)
    if r.get('source_reference') == KR_DATA_1R_SOURCE_REF:
        return True
    # Match via evidence_refs chain
    if any(KR_DATA_1R_SOURCE_REF in str(ref) for ref in r.get('evidence_refs', [])):
        return True
    return False

def is_kr_data_1r_evidence(e):
    return e.get('source_reference') == KR_DATA_1R_SOURCE_REF

kept_records    = [r for r in data.get('records', [])          if not is_kr_data_1r_record(r)]
removed_records = [r for r in data.get('records', [])          if     is_kr_data_1r_record(r)]
kept_evidence   = [e for e in data.get('evidence_records', []) if not is_kr_data_1r_evidence(e)]
removed_evidence = [e for e in data.get('evidence_records', []) if    is_kr_data_1r_evidence(e)]

# Classify removed records by part
part_a_types = {'curve_definition', 'display_rule', 'classification_rule', 'template_rule'}
part_a = [r for r in removed_records if r.get('record_type') in part_a_types]
part_b = [r for r in removed_records if r.get('record_type') == 'alias_enrichment']
other  = [r for r in removed_records if r not in part_a and r not in part_b]

data['records']          = kept_records
data['evidence_records'] = kept_evidence

with open(STORAGE, 'w') as f:
    json.dump(data, f, indent=2, default=str)

print(f'  Records before  : {original_count}')
print(f'  Records removed : {len(removed_records)}')
print(f'    Part A (legacy KR-3 candidates)   : {len(part_a)}')
print(f'    Part B (alias_enrichment CANDIDATE): {len(part_b)}')
if other:
    print(f'    Other (unexpected)               : {len(other)}')
print(f'  Records after   : {len(kept_records)}')
print(f'  Evidence removed: {len(removed_evidence)}')
if removed_records:
    print()
    print('  Removed record IDs:')
    for r in removed_records:
        record_type = r.get('record_type', '?')
        status      = r.get('status', '?')
        part_label  = 'B' if record_type == 'alias_enrichment' else 'A'
        print(f'    [Part {part_label}] {r.get(\"record_id\",\"?\")} ({record_type}, status={status})')
"
    echo "Surgical rollback complete."
fi

echo ""
echo "============================================================"
echo " ROLLBACK COMPLETE"
echo "============================================================"
