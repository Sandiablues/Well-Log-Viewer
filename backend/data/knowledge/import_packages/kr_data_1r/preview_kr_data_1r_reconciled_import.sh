#!/usr/bin/env bash
# =============================================================================
# preview_kr_data_1r_reconciled_import.sh
#
# Preview the KR-DATA-1R reconciled LEGACY KR-3 import payload against the
# live backend.  SIDE-EFFECT FREE — calls POST /import/preview only.
# Nothing is staged.
#
# NOTE: This script handles PART A of the KR-DATA-1R staging path.
#       The alias_enrichment_records (ILD/ILM/LLD/LLS) are intentionally
#       excluded from this preview because the ImportPayload schema does not
#       have an alias_enrichment_records field.  Those records are previewed
#       separately via preview_alias_enrichments_kr_data_1r.sh (PART B).
#
# Usage:
#   bash preview_kr_data_1r_reconciled_import.sh [--server http://HOST:PORT]
#
# Default server: http://127.0.0.1:8000
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
PAYLOAD="$SCRIPT_DIR/kr_data_1r_reconciled_import_payload.json"
SERVER="${1:-http://127.0.0.1:8000}"

# Accept --server flag
if [[ "${1:-}" == "--server" && -n "${2:-}" ]]; then
    SERVER="$2"
fi

ENDPOINT="$SERVER/api/wlv/knowledge/managed/import/preview"

echo "============================================================"
echo " KR-DATA-1R — PART A: Legacy KR-3 Import — PREVIEW"
echo "============================================================"
echo " Package : kr_data_1r"
echo " Payload : $PAYLOAD"
echo " Endpoint: $ENDPOINT"
echo " Mode    : PREVIEW (no staging)"
echo ""
echo " NOTE: alias_enrichment_records (ILD/ILM/LLD/LLS) are excluded"
echo " from this preview. They are not part of the ImportPayload"
echo " schema and must be previewed via:"
echo "   bash preview_alias_enrichments_kr_data_1r.sh"
echo "============================================================"
echo ""

# --- Prerequisites --------------------------------------------------------
if ! command -v curl &>/dev/null; then
    echo "ERROR: curl is required but not found." >&2
    exit 1
fi
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required but not found." >&2
    exit 1
fi
if [[ ! -f "$PAYLOAD" ]]; then
    echo "ERROR: Payload file not found: $PAYLOAD" >&2
    exit 1
fi

# --- Validate JSON syntax -------------------------------------------------
echo "[1/3] Validating JSON syntax..."
python3 -c "
import json, sys
try:
    with open('$PAYLOAD') as f:
        d = json.load(f)
    cd_count = len(d.get('curve_definitions', []))
    alias_count = sum(len(cd.get('aliases',[])) for cd in d.get('curve_definitions',[]))
    enrich_count = len(d.get('alias_enrichment_records', []))
    print(f'  JSON valid: OK')
    print(f'  curve_definitions : {cd_count}')
    print(f'  aliases in payload: {alias_count}  (ILD/ILM/LLD/LLS removed; staged via Part B)')
    print(f'  alias_enrichments : {enrich_count}  (ILD, ILM, LLD, LLS — Part B only)')
    # Confirm ILD/ILM/LLD/LLS absent from curve_definitions
    all_aliases = [a for cd in d.get('curve_definitions',[]) for a in cd.get('aliases',[])]
    blocked = [x for x in ['ILD','ILM','LLD','LLS'] if x in all_aliases]
    if blocked:
        print(f'  ERROR: {blocked} still present in curve_definitions — should be absent', file=sys.stderr)
        sys.exit(1)
    print('  ILD/ILM/LLD/LLS absent from curve_definitions: OK')
except Exception as e:
    print(f'  JSON ERROR: {e}', file=sys.stderr)
    sys.exit(1)
"
echo ""

# --- Check server reachability --------------------------------------------
echo "[2/3] Checking server reachability ($SERVER)..."
if ! curl -sf --max-time 5 "$SERVER/api/wlv/knowledge/managed/health" >/dev/null 2>&1; then
    echo "  WARNING: Server not reachable at $SERVER"
    echo "  Start the backend with: uvicorn app.main:app --port 8000"
    echo "  Skipping live preview."
    echo ""
    echo "============================================================"
    echo " PREVIEW SKIPPED — server not running"
    echo " Run this script after starting the backend."
    echo "============================================================"
    exit 0
fi
echo "  Server reachable: OK"
echo ""

# --- POST to preview endpoint --------------------------------------------
echo "[3/3] Posting to $ENDPOINT ..."
echo ""
echo "  [Legacy KR-3 preview excludes alias_enrichment_records;"
echo "   alias enrichment records are validated separately via"
echo "   preview_alias_enrichments_kr_data_1r.sh]"
echo ""

# Strip non-ImportPayload keys before submitting
STRIPPED_PAYLOAD=$(python3 -c "
import json, sys
with open('$PAYLOAD') as f:
    d = json.load(f)
# alias_enrichment_records and _reconciliation_meta are non-schema extensions.
# The import endpoint (ImportPayload Pydantic model) does not accept these fields.
# They are stripped here. ILD/ILM/LLD/LLS alias enrichment records are handled
# separately by preview_alias_enrichments_kr_data_1r.sh and
# stage_alias_enrichments_kr_data_1r.sh.
d.pop('_reconciliation_meta', None)
d.pop('alias_enrichment_records', None)
print(json.dumps(d))
")

HTTP_STATUS=$(curl -s -o /tmp/kr_data_1r_preview_response.json \
    -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$STRIPPED_PAYLOAD" \
    "$ENDPOINT")

echo "  HTTP status        : $HTTP_STATUS"

if [[ "$HTTP_STATUS" != "200" ]]; then
    echo ""
    echo "ERROR: Expected HTTP 200, got $HTTP_STATUS" >&2
    echo "Response body:"
    cat /tmp/kr_data_1r_preview_response.json
    exit 1
fi

python3 -c "
import json, sys
with open('/tmp/kr_data_1r_preview_response.json') as f:
    r = json.load(f)

print(f'  valid              : {r.get(\"valid\")}')
print(f'  error_count        : {r.get(\"error_count\")}')
print(f'  warning_count      : {r.get(\"warning_count\")}')
print(f'  candidate_record_count : {r.get(\"candidate_record_count\")}')
print(f'  record_type_counts : {json.dumps(r.get(\"record_type_counts\", {}), indent=4)}')

errors = r.get('errors', [])
if errors:
    print()
    print('  ERRORS:')
    for e in errors:
        print(f'    [{e[\"code\"]}] {e[\"path\"]}: {e[\"message\"]}')

warnings = r.get('warnings', [])
if warnings:
    print()
    print('  WARNINGS:')
    for w in warnings:
        print(f'    [{w[\"code\"]}] {w[\"path\"]}: {w[\"message\"]}')

print()
if r.get('valid'):
    print('RESULT: valid=true — legacy KR-3 payload is ready for staging.')
    print('  ILD/ILM/LLD/LLS are NOT present as alias conflicts.')
    print()
    print('  Next steps:')
    print('    bash preview_alias_enrichments_kr_data_1r.sh  (preview Part B)')
    print('    bash stage_kr_data_1r_reconciled_import.sh    (stage Part A — requires approval)')
    print('    bash stage_alias_enrichments_kr_data_1r.sh   (stage Part B — requires approval)')
else:
    print('RESULT: valid=false — resolve errors before staging.', file=sys.stderr)
    conflict_errors = [e for e in errors if e.get('code') == 'alias_conflicts_with_existing_record']
    if conflict_errors:
        blocked = [e['path'] for e in conflict_errors if any(m in e.get('message','') for m in ['ILD','ILM','LLD','LLS'])]
        if blocked:
            print(f'  ILD/ILM/LLD/LLS alias conflicts still present: {blocked}', file=sys.stderr)
            print('  These aliases must be absent from curve_definitions.', file=sys.stderr)
"

echo ""
echo "============================================================"
echo " PART A PREVIEW COMPLETE — no records staged"
echo " Run preview_alias_enrichments_kr_data_1r.sh for Part B."
echo "============================================================"
