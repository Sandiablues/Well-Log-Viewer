#!/usr/bin/env bash
# rollback_kr5_persistent_storage.sh
# Rollback KR-5 Persistent Managed Knowledge Storage changes.
#
# This script reverts the KR-5 implementation to the KR-4 baseline state.
# Run from the project root.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "======================================================================"
echo "  WLV KR-5 Rollback"
echo "======================================================================"
echo ""
echo "  Reverting to KR-4 baseline via git..."
echo ""

cd "$SCRIPT_DIR"

# Show what will be reverted
echo "Files added in KR-5:"
echo "  backend/app/knowledge/managed_storage.py"
echo "  backend/tests/knowledge/test_kr5_persistent_storage.py"
echo "  backend/tests/knowledge/conftest.py"
echo "  backend/data/knowledge/managed_knowledge.json"
echo "  validate_kr5_persistent_storage.sh"
echo "  rollback_kr5_persistent_storage.sh"
echo ""
echo "Files modified in KR-5:"
echo "  backend/app/knowledge/managed_repository.py"
echo "  backend/app/knowledge/governance_service.py"
echo "  backend/app/knowledge/managed_models.py"
echo "  backend/app/knowledge/api_managed_knowledge.py"
echo ""

read -p "Proceed with rollback? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

# Restore modified files from git
echo "Restoring modified files from git HEAD..."
git checkout HEAD -- \
    backend/app/knowledge/managed_repository.py \
    backend/app/knowledge/governance_service.py \
    backend/app/knowledge/managed_models.py \
    backend/app/knowledge/api_managed_knowledge.py

# Remove KR-5-added files
echo "Removing KR-5-added files..."
rm -f backend/app/knowledge/managed_storage.py
rm -f backend/tests/knowledge/test_kr5_persistent_storage.py
rm -f backend/tests/knowledge/conftest.py
rm -f backend/data/knowledge/managed_knowledge.json
rm -f validate_kr5_persistent_storage.sh
rm -f rollback_kr5_persistent_storage.sh

# Remove empty data directory if created by KR-5
rmdir backend/data/knowledge 2>/dev/null || true

echo ""
echo "Rollback complete. Run the KR-4 test suite to verify:"
echo "  cd $BACKEND_DIR"
echo "  .venv/bin/pytest tests/knowledge/test_kr4_governance_review.py -v"
