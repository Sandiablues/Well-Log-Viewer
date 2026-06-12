#!/usr/bin/env bash
# validate_kr5_persistent_storage.sh
# KR-5 Persistent Managed Knowledge Storage — Validation Script
#
# Runs:
#   1. KR-5 test suite (test_kr5_persistent_storage.py)
#   2. Full knowledge test suite (tests/knowledge/)
#   3. Frontend TypeScript typecheck
#   4. Frontend production build
#   5. Prints suggested live endpoint checks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "======================================================================"
echo "  WLV KR-5 Validation — Persistent Managed Knowledge Storage"
echo "======================================================================"
echo ""

# ----------------------------------------------------------------------
# 1. KR-5 test suite
# ----------------------------------------------------------------------
echo "----------------------------------------------------------------------"
echo "  1/4  KR-5 test suite"
echo "----------------------------------------------------------------------"
cd "$BACKEND_DIR"
.venv/bin/pytest tests/knowledge/test_kr5_persistent_storage.py -v
echo ""

# ----------------------------------------------------------------------
# 2. Full knowledge test suite
# ----------------------------------------------------------------------
echo "----------------------------------------------------------------------"
echo "  2/4  Full knowledge test suite"
echo "----------------------------------------------------------------------"
.venv/bin/pytest tests/knowledge/ -v
echo ""

# ----------------------------------------------------------------------
# 3. Frontend TypeScript typecheck
# ----------------------------------------------------------------------
echo "----------------------------------------------------------------------"
echo "  3/4  Frontend TypeScript typecheck"
echo "----------------------------------------------------------------------"
cd "$FRONTEND_DIR"
npm run typecheck
echo ""

# ----------------------------------------------------------------------
# 4. Frontend production build
# ----------------------------------------------------------------------
echo "----------------------------------------------------------------------"
echo "  4/4  Frontend production build"
echo "----------------------------------------------------------------------"
npm run build
echo ""

# ----------------------------------------------------------------------
# Live endpoint validation guide
# ----------------------------------------------------------------------
echo "======================================================================"
echo "  AUTOMATED TESTS PASSED"
echo "======================================================================"
echo ""
echo "  Next: live restart persistence validation"
echo ""
echo "  Start backend:"
echo "    cd $BACKEND_DIR"
echo "    .venv/bin/uvicorn app.main:app --reload --port 8000"
echo ""
echo "  1.  Stage a candidate:"
echo "      curl -s -X POST http://localhost:8000/api/wlv/knowledge/managed/import/stage \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{"
echo "          \"source\":{\"source_type\":\"manual_import\",\"source_label\":\"KR-5 Live Test\"},"
echo "          \"curve_definitions\":[{"
echo "            \"canonical_curve_id\":\"kr5_live_validation_curve\","
echo "            \"display_name\":\"KR-5 Live Validation\","
echo "            \"family\":\"test_family\","
echo "            \"product_group\":\"open_hole_logs\""
echo "          }]"
echo "        }' | python3 -m json.tool"
echo ""
echo "  2.  Approve the candidate (replace RECORD_ID with the curve_def record_id from step 1):"
echo "      curl -s -X POST http://localhost:8000/api/wlv/knowledge/managed/records/RECORD_ID/approve \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"actor\":\"live_test\",\"reason\":\"KR-5 live validation\"}' | python3 -m json.tool"
echo ""
echo "  3.  Confirm production-eligible:"
echo "      curl -s http://localhost:8000/api/wlv/knowledge/managed/production-eligible | python3 -m json.tool"
echo ""
echo "  4.  Restart backend. Then:"
echo "      curl -s http://localhost:8000/api/wlv/knowledge/managed/production-eligible | python3 -m json.tool"
echo "      (approved record must still appear)"
echo ""
echo "  5.  Stage another candidate, reject it, restart, confirm non-production:"
echo "      curl -s http://localhost:8000/api/wlv/knowledge/managed/records?status=rejected | python3 -m json.tool"
echo ""
echo "  6.  Deprecate an approved record, restart, confirm non-production:"
echo "      curl -s http://localhost:8000/api/wlv/knowledge/managed/records?status=deprecated | python3 -m json.tool"
echo ""
echo "  7.  Storage health:"
echo "      curl -s http://localhost:8000/api/wlv/knowledge/managed/storage/health | python3 -m json.tool"
echo ""
echo "  Storage file location:"
echo "    $BACKEND_DIR/data/knowledge/managed_knowledge.json"
echo ""
echo "======================================================================"
