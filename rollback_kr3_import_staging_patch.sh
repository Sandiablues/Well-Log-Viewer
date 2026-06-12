#!/usr/bin/env bash
# =============================================================================
# rollback_kr3_import_staging_patch.sh
# WLV-KR-3: Definition Import and Staging Contract — ROLLBACK
#
# Removes all KR-3 new files and restores the KR-2 originals of any
# modified files.  Call this from the project root:
#
#   cd /path/to/Well-Log-Viewer
#   bash rollback_kr3_import_staging_patch.sh
#
# SAFETY: This script will NOT run if KR-3 changes have already been
# committed to git.  Rollback only applies to working-tree changes.
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

info()  { echo -e "${GREEN}[KR-3 ROLLBACK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[KR-3 WARN]    ${NC} $*"; }
error() { echo -e "${RED}[KR-3 ERROR]   ${NC} $*"; }

cd "$PROJECT_ROOT"

info "Checking git working tree..."
# Safety: ensure KR-3 changes are not committed
if git log --oneline -5 | grep -q "KR-3"; then
    warn "A KR-3 commit appears to exist in git history."
    warn "This rollback script is for working-tree changes only."
    warn "To roll back a committed KR-3, use: git revert HEAD (if KR-3 is the last commit)"
    read -r -p "Continue anyway? [y/N] " CONFIRM
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        info "Rollback aborted."
        exit 0
    fi
fi

# ------------------------------------------------------------------
# 1. Remove KR-3 new files
# ------------------------------------------------------------------
KR3_NEW_FILES=(
    "$KNOWLEDGE/import_models.py"
    "$KNOWLEDGE/import_validation_service.py"
    "$KNOWLEDGE/import_staging_service.py"
    "$TESTS/test_kr3_import_staging.py"
)

for f in "${KR3_NEW_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        rm -f "$f"
        info "Removed: $(basename "$f")"
    else
        warn "Not found (already removed?): $(basename "$f")"
    fi
done

# ------------------------------------------------------------------
# 2. Restore KR-2 originals of modified files
# ------------------------------------------------------------------
info "Restoring api_managed_knowledge.py to KR-2 state..."
git checkout HEAD -- backend/app/knowledge/api_managed_knowledge.py 2>/dev/null \
    || warn "git checkout failed — api_managed_knowledge.py may need manual restore"

info "Restoring managed_models.py to KR-2 state..."
git checkout HEAD -- backend/app/knowledge/managed_models.py 2>/dev/null \
    || warn "git checkout failed — managed_models.py may need manual restore"

# ------------------------------------------------------------------
# 3. Clean up patch/validate scripts (optional — comment out to keep)
# ------------------------------------------------------------------
# rm -f "$PROJECT_ROOT/apply_kr3_import_staging_patch.sh"
# rm -f "$PROJECT_ROOT/rollback_kr3_import_staging_patch.sh"
# rm -f "$PROJECT_ROOT/validate_kr3_import_staging.sh"
# rm -f "$PROJECT_ROOT/KR3_IMPORT_STAGING_REPORT.md"

info "Git status after rollback:"
git status --short backend/

echo ""
info "KR-3 rollback complete."
info "Run: cd backend && .venv/bin/pytest tests/knowledge/ -v"
info "to verify KR-2 baseline tests still pass."
