#!/usr/bin/env bash
# rollback_kr1_patch.sh — WLV KR-1 Knowledge Repository rollback
#
# Reverses KR-1 changes:
#   - Removes new KR-1 backend files
#   - Restores backend/app/main.py (removes knowledge router lines)
#   - Restores frontend TrackLayoutPrototype.tsx (removes KR types/functions,
#     restores OPEN_HOLE_SUBGROUP_ORDER, OPEN_HOLE_FALLBACK_SUBGROUP_LABELS,
#     and openHoleSubgroups())
#
# Usage:
#   bash rollback_kr1_patch.sh
#
# Run from the Well-Log-Viewer repository root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== WLV KR-1 Knowledge Repository — Rollback Script ==="
echo "Repo: ${REPO_ROOT}"
echo ""

# ---------------------------------------------------------------------------
# Strategy: prefer backup created by apply_kr1_patch.sh; fall back to Python
# surgical removal.
# ---------------------------------------------------------------------------

BACKUP_FILE="${REPO_ROOT}/.wlv_kr1_last_backup"

if [[ -f "${BACKUP_FILE}" ]]; then
  BACKUP_DIR="$(cat "${BACKUP_FILE}")"
  if [[ -d "${BACKUP_DIR}" ]]; then
    echo "[1/3] Restoring from backup: ${BACKUP_DIR}"

    cp "${BACKUP_DIR}/backend/app/main.py" \
       "${REPO_ROOT}/backend/app/main.py"
    echo "  Restored backend/app/main.py"

    cp "${BACKUP_DIR}/frontend/src/wells/prototype/TrackLayoutPrototype.tsx" \
       "${REPO_ROOT}/frontend/src/wells/prototype/TrackLayoutPrototype.tsx"
    echo "  Restored frontend/src/wells/prototype/TrackLayoutPrototype.tsx"
  else
    echo "  Backup directory not found at ${BACKUP_DIR}. Falling back to surgical rollback."
    _do_surgical_rollback
  fi
else
  echo "[1/3] No backup record found. Performing surgical rollback via Python..."
  _do_surgical_rollback() {
    python3 - << 'PYEOF'
import re, pathlib

REPO = pathlib.Path(__file__).parent if '__file__' in dir() else pathlib.Path(".")

# --- Rollback main.py: remove knowledge router lines ---
main_py = REPO / "backend/app/main.py"
src = main_py.read_text()
src = src.replace(
    "from .knowledge.api_knowledge import router as knowledge_router\n",
    ""
)
src = src.replace(
    "app.include_router(knowledge_router)\n",
    ""
)
main_py.write_text(src)
print("  Rolled back backend/app/main.py")

# --- Rollback TrackLayoutPrototype.tsx: restore frontend KR-truth constants ---
tsx = REPO / "frontend/src/wells/prototype/TrackLayoutPrototype.tsx"
src = tsx.read_text()

OLD_KR_BLOCK = """// KR-1: Backend-owned Knowledge Repository contracts.
// The frontend renders these; it must not own subgroup order or label truth.
type KrSubgroup = {
  key: string;
  label: string;
  order: number;
};

type KrProductGroup = {
  key: string;
  label: string;
  order: number;
  subgroups: KrSubgroup[];
};

type KrProductGroupsPayload = {
  version: string;
  groups: KrProductGroup[];
};

function normalizedProductSubgroupKey(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

/**
 * Group product items using backend-provided subgroup order and labels.
 * Items whose key is not in the KR list fall into the last subgroup
 * (conventionally the "other/review" bucket) if one exists.
 * The frontend does not infer or re-order subgroups — it renders the
 * backend-provided order and labels only.
 */
function groupProductItemsByKrSubgroups(
  items: ManagedProductGroupItem[],
  krSubgroups: KrSubgroup[],
): WmdpProductSubgroup[] {
  if (krSubgroups.length === 0) return [];

  const sortedSubgroups = [...krSubgroups].sort((a, b) => a.order - b.order);
  const subgroupByKey = new Map<string, WmdpProductSubgroup>(
    sortedSubgroups.map((s) => [s.key, { subgroupKey: s.key, subgroupLabel: s.label, items: [] }]),
  );

  // Last subgroup absorbs unrecognised keys (typically the "other/review" bucket).
  const fallbackKey = sortedSubgroups[sortedSubgroups.length - 1].key;

  for (const item of items) {
    const rawKey = item.product_subgroup_key || item.curve_family || '';
    const normKey = normalizedProductSubgroupKey(rawKey);
    const targetKey = subgroupByKey.has(normKey) ? normKey : fallbackKey;
    subgroupByKey.get(targetKey)?.items.push(item);
  }

  return sortedSubgroups
    .map((s) => subgroupByKey.get(s.key)!)
    .filter((s) => s.items.length > 0);
}"""

NEW_KR_BLOCK = """const OPEN_HOLE_SUBGROUP_ORDER = [
  'gamma_ray',
  'resistivity',
  'sonic_acoustic',
  'density_neutron_porosity',
  'nmr',
  'borehole_geometry_imaging',
  'sp_electrochemical',
  'dip_directional',
  'formation_pressure_sampling',
  'petrophysical_interpretation',
  'other_open_hole_review',
];

const OPEN_HOLE_FALLBACK_SUBGROUP_LABELS: Record<string, string> = {
  gamma_ray: 'Gamma Ray',
  resistivity: 'Resistivity',
  sonic_acoustic: 'Sonic / Acoustic',
  density_neutron_porosity: 'Density / Neutron / Porosity',
  nmr: 'NMR',
  borehole_geometry_imaging: 'Borehole Geometry / Imaging',
  sp_electrochemical: 'SP / Electrochemical',
  dip_directional: 'Dip / Directional',
  formation_pressure_sampling: 'Formation Pressure / Sampling',
  petrophysical_interpretation: 'Petrophysical Interpretation',
  other_open_hole_review: 'Other Open-hole / Review',
};

function normalizedProductSubgroupKey(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'other_open_hole_review';
}

function openHoleSubgroups(items: ManagedProductGroupItem[]): WmdpProductSubgroup[] {
  const grouped = new Map<string, WmdpProductSubgroup>();
  for (const item of items) {
    const rawKey = item.product_subgroup_key || item.curve_family || 'other_open_hole_review';
    const subgroupKey = normalizedProductSubgroupKey(rawKey);
    const canonicalKey = OPEN_HOLE_FALLBACK_SUBGROUP_LABELS[subgroupKey] ? subgroupKey : 'other_open_hole_review';
    const subgroupLabel = item.product_subgroup_label || OPEN_HOLE_FALLBACK_SUBGROUP_LABELS[canonicalKey] || 'Other Open-hole / Review';
    if (!grouped.has(canonicalKey)) {
      grouped.set(canonicalKey, { subgroupKey: canonicalKey, subgroupLabel, items: [] });
    }
    grouped.get(canonicalKey)?.items.push(item);
  }

  return [...grouped.values()].sort((left, right) => {
    const leftIndex = OPEN_HOLE_SUBGROUP_ORDER.indexOf(left.subgroupKey);
    const rightIndex = OPEN_HOLE_SUBGROUP_ORDER.indexOf(right.subgroupKey);
    const safeLeft = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
    const safeRight = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
    return safeLeft - safeRight || left.subgroupLabel.localeCompare(right.subgroupLabel);
  });
}"""

if OLD_KR_BLOCK in src:
    src = src.replace(OLD_KR_BLOCK, NEW_KR_BLOCK)
    print("  Rolled back KR-1 types/functions in TrackLayoutPrototype.tsx")
else:
    print("  WARNING: KR-1 block not found verbatim in TrackLayoutPrototype.tsx")
    print("  Manual rollback may be required for TrackLayoutPrototype.tsx")

# Remove krProductGroups state line
src = src.replace(
    "  // KR-1: backend-owned product groups fetched once on mount.\n"
    "  // If unavailable the page degrades safely (subgroups not shown).\n"
    "  const [krProductGroups, setKrProductGroups] = useState<KrProductGroup[]>([]);\n",
    ""
)

# Remove KR fetch from loadInventory
src = src.replace(
    "\n    // KR-1: Fetch backend-owned product groups in parallel with inventory.\n"
    "    // A KR failure is non-fatal — the page degrades gracefully (no subgrouping).\n"
    "    fetchWlvJson<KrProductGroupsPayload>('/api/wlv/knowledge/product-groups')\n"
    "      .then((payload) => setKrProductGroups(payload.groups ?? []))\n"
    "      .catch(() => { /* KR unavailable — subgroup rendering degrades safely */ });\n",
    ""
)

tsx.write_text(src)
print("  Rolled back krProductGroups state and KR fetch")
print("  NOTE: The categoryExpanded render block was also changed.")
print("  If automatic rollback is incomplete, restore from a backup or git stash.")
PYEOF
  }
  _do_surgical_rollback
fi

# ---------------------------------------------------------------------------
# 2. Remove new KR-1 files
# ---------------------------------------------------------------------------
echo ""
echo "[2/3] Removing KR-1 new files..."

KR1_NEW_FILES=(
  "backend/app/knowledge/models.py"
  "backend/app/knowledge/repository.py"
  "backend/app/knowledge/api_knowledge.py"
  "backend/tests/knowledge/test_kr1_knowledge_repository.py"
  "apply_kr1_patch.sh"
  "rollback_kr1_patch.sh"
  "validate_kr1.sh"
  "KR1_IMPLEMENTATION_REPORT.md"
)

for f in "${KR1_NEW_FILES[@]}"; do
  if [[ -f "${REPO_ROOT}/${f}" ]]; then
    rm "${REPO_ROOT}/${f}"
    echo "  Removed ${f}"
  else
    echo "  Already absent: ${f}"
  fi
done

# ---------------------------------------------------------------------------
# 3. Result
# ---------------------------------------------------------------------------
echo ""
echo "[3/3] KR-1 rollback complete."
echo "  Verify with: cd frontend && npm run typecheck"
echo "  Verify with: cd backend && pytest"
