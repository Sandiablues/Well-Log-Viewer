#!/usr/bin/env bash
# apply_kr1_patch.sh — WLV KR-1 Knowledge Repository patch
#
# KR-1 changes are applied directly to the repository by Claude.
# This script:
#   1. Creates a timestamped backup of the files modified by KR-1.
#   2. Verifies all KR-1 deliverable files are present.
#   3. Reports any missing files.
#
# Usage:
#   bash apply_kr1_patch.sh
#
# Run from the Well-Log-Viewer repository root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${REPO_ROOT}/.wlv_kr1_backup_${TIMESTAMP}"

echo "=== WLV KR-1 Knowledge Repository — Apply Script ==="
echo "Repo: ${REPO_ROOT}"
echo "Backup dir: ${BACKUP_DIR}"
echo ""

# ---------------------------------------------------------------------------
# 1. Back up the two modified files (pre-apply baseline for rollback)
# ---------------------------------------------------------------------------
echo "[1/3] Creating pre-apply backup..."
mkdir -p "${BACKUP_DIR}/backend/app"
mkdir -p "${BACKUP_DIR}/frontend/src/wells/prototype"

cp "${REPO_ROOT}/backend/app/main.py" \
   "${BACKUP_DIR}/backend/app/main.py"

cp "${REPO_ROOT}/frontend/src/wells/prototype/TrackLayoutPrototype.tsx" \
   "${BACKUP_DIR}/frontend/src/wells/prototype/TrackLayoutPrototype.tsx"

echo "  Backed up backend/app/main.py"
echo "  Backed up frontend/src/wells/prototype/TrackLayoutPrototype.tsx"

# Record the backup location for rollback
echo "${BACKUP_DIR}" > "${REPO_ROOT}/.wlv_kr1_last_backup"
echo "  Backup path written to .wlv_kr1_last_backup"

# ---------------------------------------------------------------------------
# 2. Verify KR-1 deliverable files are present
# ---------------------------------------------------------------------------
echo ""
echo "[2/3] Verifying KR-1 files..."

KR1_FILES=(
  "backend/app/knowledge/models.py"
  "backend/app/knowledge/repository.py"
  "backend/app/knowledge/api_knowledge.py"
  "backend/tests/knowledge/test_kr1_knowledge_repository.py"
)

ALL_PRESENT=true
for f in "${KR1_FILES[@]}"; do
  if [[ -f "${REPO_ROOT}/${f}" ]]; then
    echo "  PRESENT  ${f}"
  else
    echo "  MISSING  ${f}  ← KR-1 file not found"
    ALL_PRESENT=false
  fi
done

# Verify main.py has knowledge router
if grep -q "from .knowledge.api_knowledge import router as knowledge_router" \
   "${REPO_ROOT}/backend/app/main.py"; then
  echo "  PRESENT  backend/app/main.py (knowledge router registered)"
else
  echo "  MISSING  backend/app/main.py knowledge router registration"
  ALL_PRESENT=false
fi

# Verify frontend has KR types (not the old constants)
if grep -q "KrProductGroup" \
   "${REPO_ROOT}/frontend/src/wells/prototype/TrackLayoutPrototype.tsx"; then
  echo "  PRESENT  frontend TrackLayoutPrototype.tsx (KR types present)"
else
  echo "  MISSING  frontend KR types in TrackLayoutPrototype.tsx"
  ALL_PRESENT=false
fi

if grep -q "OPEN_HOLE_SUBGROUP_ORDER" \
   "${REPO_ROOT}/frontend/src/wells/prototype/TrackLayoutPrototype.tsx"; then
  echo "  WARNING  OPEN_HOLE_SUBGROUP_ORDER still present in frontend — not fully removed"
  ALL_PRESENT=false
else
  echo "  REMOVED  OPEN_HOLE_SUBGROUP_ORDER (frontend no longer owns subgroup order)"
fi

# ---------------------------------------------------------------------------
# 3. Result
# ---------------------------------------------------------------------------
echo ""
echo "[3/3] Result"
if [[ "${ALL_PRESENT}" == "true" ]]; then
  echo "  KR-1 patch is fully applied."
  echo ""
  echo "  Next: validate with:  bash validate_kr1.sh"
else
  echo "  Some KR-1 files are missing or checks failed. Review output above."
  exit 1
fi
