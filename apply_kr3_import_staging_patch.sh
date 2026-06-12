#!/usr/bin/env bash
# =============================================================================
# apply_kr3_import_staging_patch.sh
# WLV-KR-3: Definition Import and Staging Contract
#
# Verifies all KR-3 files are present in the project, then stages them for
# commit.  Call this from the project root:
#
#   cd /path/to/Well-Log-Viewer
#   bash apply_kr3_import_staging_patch.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND="$PROJECT_ROOT/backend"
KNOWLEDGE="$BACKEND/app/knowledge"
TESTS="$BACKEND/tests/knowledge"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[KR-3 APPLY]${NC} $*"; }
warn()    { echo -e "${YELLOW}[KR-3 WARN] ${NC} $*"; }
error()   { echo -e "${RED}[KR-3 ERROR]${NC} $*"; }

info "Checking KR-3 file presence..."

REQUIRED_FILES=(
    "$KNOWLEDGE/import_models.py"
    "$KNOWLEDGE/import_validation_service.py"
    "$KNOWLEDGE/import_staging_service.py"
    "$KNOWLEDGE/api_managed_knowledge.py"
    "$KNOWLEDGE/managed_models.py"
    "$TESTS/test_kr3_import_staging.py"
)

MISSING=0
for f in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "$f" ]]; then
        error "Missing: $f"
        MISSING=1
    else
        info "Found: $(basename "$f")"
    fi
done

if [[ $MISSING -eq 1 ]]; then
    error "One or more KR-3 files are missing. Aborting."
    exit 1
fi

info "Verifying import endpoint presence in api_managed_knowledge.py..."
if ! grep -q "import/preview" "$KNOWLEDGE/api_managed_knowledge.py"; then
    error "import/preview endpoint not found in api_managed_knowledge.py"
    exit 1
fi
if ! grep -q "import/stage" "$KNOWLEDGE/api_managed_knowledge.py"; then
    error "import/stage endpoint not found in api_managed_knowledge.py"
    exit 1
fi
info "Endpoints verified."

info "Verifying KR3_VERSION in managed_models.py..."
if ! grep -q "KR3_VERSION" "$KNOWLEDGE/managed_models.py"; then
    error "KR3_VERSION not found in managed_models.py"
    exit 1
fi
info "KR3_VERSION verified."

info "Staging KR-3 files in git..."
cd "$PROJECT_ROOT"
git add \
    backend/app/knowledge/import_models.py \
    backend/app/knowledge/import_validation_service.py \
    backend/app/knowledge/import_staging_service.py \
    backend/app/knowledge/api_managed_knowledge.py \
    backend/app/knowledge/managed_models.py \
    backend/tests/knowledge/test_kr3_import_staging.py

info "Git status after staging:"
git status --short backend/

echo ""
info "KR-3 patch applied successfully."
info "Run validate_kr3_import_staging.sh to run the test suite."
info "Commit with: git commit -m 'WLV-KR-3: Definition Import and Staging Contract'"
