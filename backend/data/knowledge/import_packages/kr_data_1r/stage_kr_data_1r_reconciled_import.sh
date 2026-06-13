#!/usr/bin/env bash
# =============================================================================
# stage_kr_data_1r_reconciled_import.sh
#
# PART A of the KR-DATA-1R staging path.
#
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# WARNING: This script stages legacy KR-3 candidate records into
#          managed_knowledge.json via the backend import/stage endpoint.
#
#          Do NOT run unless:
#            1. preview_kr_data_1r_reconciled_import.sh has been reviewed
#               and returned valid=true
#            2. You are explicitly authorised to stage this package
#
#          This is PART A only.  After this completes, run PART B:
#            bash stage_alias_enrichments_kr_data_1r.sh
#          Rollback: bash rollback_kr_data_1r_staging.sh --surgical
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#
# What this script stages (Part A — legacy KR-3 ImportPayload):
#   - 12 CurveDefinitionRecord candidates
#   - 12 DisplayRule candidates
#   - 27 ClassificationRule candidates
#   - 3  TemplateRule candidates
#   - NO alias_enrichment_records (those are staged by Part B)
#
# The alias_enrichment_records in the payload JSON are stripped before
# submission because the ImportPayload schema does not have that field.
# They are NOT silently dropped — they are the explicit responsibility of
# stage_alias_enrichments_kr_data_1r.sh.
#
# Usage:
#   bash stage_kr_data_1r_reconciled_import.sh [--server http://HOST:PORT] [--yes]
#
# Without --yes you will be prompted to confirm before staging.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
PAYLOAD="$SCRIPT_DIR/kr_data_1r_reconciled_import_payload.json"
STORAGE="$PROJECT_ROOT/backend/data/knowledge/managed_knowledge.json"
SERVER="http://127.0.0.1:8000"
CONFIRM="no"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server) SERVER="$2"; shift 2 ;;
        --yes)    CONFIRM="yes"; shift ;;
        *)        echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

ENDPOINT="$SERVER/api/wlv/knowledge/managed/import/stage"
BACKUP="$STORAGE.before_kr_data_1r_$(date +%Y%m%d_%H%M%S)"

echo "============================================================"
echo " KR-DATA-1R — PART A: Legacy KR-3 Import — STAGE"
echo "============================================================"
echo " Package  : kr_data_1r"
echo " Payload  : $PAYLOAD"
echo " Endpoint : $ENDPOINT"
echo " Storage  : $STORAGE"
echo " Backup   : $BACKUP"
echo ""
echo " !!! WARNING: This will mutate managed_knowledge.json !!!"
echo " Ensure preview_kr_data_1r_reconciled_import.sh returned valid=true."
echo ""
echo " PART B (alias enrichments) must be staged separately:"
echo "   bash stage_alias_enrichments_kr_data_1r.sh"
echo "============================================================"
echo ""

if [[ "$CONFIRM" != "yes" ]]; then
    read -r -p "Type 'stage' to confirm Part A staging, or Ctrl-C to abort: " REPLY
    if [[ "$REPLY" != "stage" ]]; then
        echo "Aborted." ; exit 0
    fi
fi

# --- Prerequisites --------------------------------------------------------
for cmd in curl python3; do
    command -v "$cmd" &>/dev/null || { echo "ERROR: $cmd is required." >&2; exit 1; }
done
[[ -f "$PAYLOAD" ]] || { echo "ERROR: Payload not found: $PAYLOAD" >&2; exit 1; }
[[ -f "$STORAGE" ]] || { echo "ERROR: managed_knowledge.json not found: $STORAGE" >&2; exit 1; }

# --- Backup ---------------------------------------------------------------
echo "[1/4] Backing up managed_knowledge.json..."
cp "$STORAGE" "$BACKUP"
echo "  Backup: $BACKUP"
echo ""

# --- Pre-stage preview validation ----------------------------------------
echo "[2/4] Pre-stage preview validation..."
STRIPPED_PAYLOAD=$(python3 -c "
import json
with open('$PAYLOAD') as f:
    d = json.load(f)
# alias_enrichment_records is not part of ImportPayload schema.
# These records are staged separately by stage_alias_enrichments_kr_data_1r.sh.
d.pop('_reconciliation_meta', None)
d.pop('alias_enrichment_records', None)
print(json.dumps(d))
")

PREVIEW_STATUS=$(curl -s -o /tmp/kr_data_1r_prestage_preview.json \
    -w "%{http_code}" \
    -X POST -H "Content-Type: application/json" \
    -d "$STRIPPED_PAYLOAD" \
    "$SERVER/api/wlv/knowledge/managed/import/preview")

if [[ "$PREVIEW_STATUS" != "200" ]]; then
    echo "ERROR: Preview returned HTTP $PREVIEW_STATUS. Aborting stage." >&2
    exit 1
fi

PREVIEW_VALID=$(python3 -c "
import json
with open('/tmp/kr_data_1r_prestage_preview.json') as f:
    r = json.load(f)
print(str(r.get('valid', False)))
")

if [[ "$PREVIEW_VALID" != "True" ]]; then
    echo "ERROR: Preview returned valid=false. Fix errors before staging." >&2
    cat /tmp/kr_data_1r_prestage_preview.json
    exit 1
fi
echo "  Pre-stage preview: valid=true — proceeding to stage."
echo ""

# --- POST to stage endpoint -----------------------------------------------
echo "[3/4] Posting to $ENDPOINT ..."
HTTP_STATUS=$(curl -s -o /tmp/kr_data_1r_stage_response.json \
    -w "%{http_code}" \
    -X POST -H "Content-Type: application/json" \
    -d "$STRIPPED_PAYLOAD" \
    "$ENDPOINT")

echo "  HTTP status: $HTTP_STATUS"

if [[ "$HTTP_STATUS" != "200" ]]; then
    echo "ERROR: Stage returned HTTP $HTTP_STATUS. Restoring backup." >&2
    cp "$BACKUP" "$STORAGE"
    exit 1
fi

python3 -c "
import json, sys
with open('/tmp/kr_data_1r_stage_response.json') as f:
    r = json.load(f)
print(f'  valid              : {r.get(\"valid\")}')
print(f'  staged             : {r.get(\"staged\")}')
print(f'  import_batch_id    : {r.get(\"import_batch_id\")}')
print(f'  candidate_records  : {r.get(\"candidate_record_count\")}')
print(f'  record_type_counts : {json.dumps(r.get(\"record_type_counts\",{}), indent=4)}')
if not r.get('staged'):
    print('ERROR: staged=false', file=sys.stderr)
    sys.exit(1)
" || {
    echo "ERROR: Stage response indicates failure. Restoring backup." >&2
    cp "$BACKUP" "$STORAGE"
    exit 1
}
echo ""

# --- Summary --------------------------------------------------------------
echo "[4/4] Part A complete."
echo ""
echo "  Backup: $BACKUP"
echo ""
echo "  ================================================================"
echo "  NEXT STEP — PART B: Stage alias enrichment records:"
echo "    bash preview_alias_enrichments_kr_data_1r.sh   (review first)"
echo "    bash stage_alias_enrichments_kr_data_1r.sh     (then stage)"
echo "  ================================================================"
echo ""
echo "  To rollback Part A: bash rollback_kr_data_1r_staging.sh --backup $BACKUP"
echo "  To rollback both:   bash rollback_kr_data_1r_staging.sh --surgical"
echo ""
echo "============================================================"
echo " PART A STAGE COMPLETE"
echo "============================================================"
