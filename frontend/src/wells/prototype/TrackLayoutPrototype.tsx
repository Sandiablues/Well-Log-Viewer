import { useEffect, useMemo, useState } from 'react';
import '../../styles/track-layout-prototype.css';
import '../../styles/kr-managed-instructions.css';
import { SourceIntakeWorkbench } from '../source-intake/SourceIntakeWorkbench';
import { KrManagedInstructionsWorkbench } from '../knowledge/KrManagedInstructionsWorkbench';
import { Wellbore3DPage } from '../wbv/Wellbore3DPage';
import { buildInventoryActionPayload, buildInventoryRemovalPayload } from '../identity/inventoryActionIdentity';
import { managedWellIdentityFromActiveWorkspace, managedWellIdentityFromPayload, type ManagedWellIdentity } from '../identity/managedWellIdentity';
import { fetchWlvJson } from '../wdv/WdvPresentationPrimitives';
import { flushMwdTransientData } from '../inventory/mwdTransientFlushApi';
import { WdvPageBoundary } from '../wdv/WdvPageBoundary';
import { fetchWmdDownstreamRecovery, rebuildWmdPayload, wmdRecoveryAction, wmdRecoveryLabel, type WmdDownstreamRecoveryStatus } from '../inventory/wmdRecoveryApi';

type DemoNavView = 'log-viewer' | 'data' | 'sources' | 'knowledge' | 'wellbore-3d' | 'info';

type ManagedInventorySourceReference = {
    source_id: string;
    source_kind?: string | null;
    display_name?: string | null;
    original_path?: string | null;
    file_name?: string | null;
    file_format?: string | null;
    checksum?: string | null;
    path?: string | null;
    uri?: string | null;
    status?: string | null;
};

type ManagedInventoryViewerPackageReference = {
    viewer_package_id: string;
    viewer_package_version?: string | null;
    package_kind?: string | null;
    display_name?: string | null;
    dataset_id?: string | null;
    representation_id?: string | null;
    endpoint?: string | null;
    status?: string | null;
};

type WmdpTrajectoryRecord = {
    trajectory_id: string;
    managed_trajectory_uid?: string | null;
    trajectory_name?: string | null;
    trajectory_type?: string | null;
    status?: string | null;
    wbv_eligible?: boolean | null;
    is_active?: boolean | null;
    is_canonical?: boolean | null;
    is_synthetic?: boolean | null;
    source_label?: string | null;
    station_count?: number | null;
    md_min?: number | null;
    md_max?: number | null;
    tvd_min?: number | null;
    tvd_max?: number | null;
    geometry_class?: string | null;
};

type ManagedProductGroupItem = {
    product_id: string;
    managed_product_uid?: string | null;
    managed_curve_uid?: string | null;
    display_name?: string | null;
    curve_name?: string | null;
    curve_type?: string | null;
    curve_family?: string | null;
    general_curve_family?: string | null;
    general_curve_family_key?: string | null;
    general_curve_family_projection_version?: string | null;
    product_subgroup_key?: string | null;
    product_subgroup_label?: string | null;
    classification_confidence?: string | null;
    classification_source?: string | null;
    classification_reasons?: string[] | null;
    review_required?: boolean | null;
    run_date?: string | null;
    run_interval?: string | null;
    run_number?: string | null;
    qa_flag?: string | null;
    selectable?: boolean;
    source_kind?: string | null;
    source_id?: string | null;
    viewer_package_id?: string | null;
    wmdp_state?: string | null;
    wdv_state?: string | null;
    product_category?: string | null;
    trajectory_id?: string | null;
    managed_trajectory_uid?: string | null;
    trajectory_status?: string | null;
    trajectory_role?: string | null;
    wbv_eligible?: boolean | null;
    source_label?: string | null;
    station_count?: number | null;
    md_min?: number | null;
    md_max?: number | null;
    tvd_min?: number | null;
    tvd_max?: number | null;
    is_active_trajectory?: boolean | null;
    is_synthetic_trajectory?: boolean | null;
};

type ManagedProductGroup = {
    group_key: string;
    group_label: string;
    collapsed_by_default?: boolean;
    items?: ManagedProductGroupItem[];
};

type ManagedInventoryWellRecord = {
    managed_well_id: string;
    managed_well_uid?: string | null;
    well_id: string;
    uwi?: string | null;
    well_name?: string | null;
    display_name?: string | null;
    wellbore_id?: string | null;
    wellbore_name?: string | null;
    operator?: string | null;
    field?: string | null;
    block?: string | null;
    country?: string | null;
    depth_unit?: string | null;
    top_depth?: number | null;
    base_depth?: number | null;
    status?: string | null;
    lifecycle_state?: string | null;
    source_references?: ManagedInventorySourceReference[];
    viewer_packages?: ManagedInventoryViewerPackageReference[];
    product_groups?: ManagedProductGroup[];
    loaded_product_count?: number;
    viewer_curve_count?: number;
    displayable_curve_count?: number;
    metadata?: {
        wbv_trajectory_records?: WmdpTrajectoryRecord[];
        active_trajectory_id?: string | null;
        active_trajectory_uid?: string | null;
        wellbore_geometry_status?: string | null;
    } | null;
    wmdp_state?: string | null;
    wdv_state?: string | null;
    tags?: string[];
    created_at?: string | null;
    updated_at?: string | null;
};

type ManagedInventoryStatusPayload = {
    ok: boolean;
    service: string;
    scope?: string | null;
    storage_backend?: string | null;
    schema_version?: string | null;
    managed_well_count: number;
    viewer_package_count: number;
    source_reference_count?: number;
    lifecycle_counts?: Record<string, number>;
    repository_path?: string | null;
    storage_path?: string | null;
    last_checked_at?: string | null;
};

function statusLabel(status?: string | null): string {
    return (status ?? 'unknown').replace(/_/g, ' ');
}

function safeText(value: string | number | null | undefined, fallback = '—'): string {
    if (value === null || value === undefined || value === '') {
        return fallback;
    }
    return String(value);
}

function wellDisplayName(well: ManagedInventoryWellRecord): string {
    return well.display_name || well.well_name || well.well_id || well.managed_well_id;
}

function wellStatus(well: ManagedInventoryWellRecord): string {
    return well.lifecycle_state || well.status || 'unknown';
}

function developmentSeedAlreadyRegistered(_wells: ManagedInventoryWellRecord[]): boolean {
    return false;
}

function wellTypeLabel(well: ManagedInventoryWellRecord): string {
    const record = well as ManagedInventoryWellRecord & {
        well_type?: string | null;
        type?: string | null;
        well_category?: string | null;
    };
    return statusLabel(record.well_type || record.type || record.well_category || '—');
}

function isFiniteNumber(value: unknown): value is number {
    return typeof value === 'number' && Number.isFinite(value);
}

function optionalDepthRangeLabel(min?: number | null, max?: number | null, unit = 'ft'): string {
    if (!isFiniteNumber(min) && !isFiniteNumber(max))
        return '—';
    const left = isFiniteNumber(min) ? min.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '—';
    const right = isFiniteNumber(max) ? max.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '—';
    return `${left}–${right} ${unit}`;
}

function wmdpWellboreGeometryGroup(well: ManagedInventoryWellRecord): ManagedProductGroup {
    const records = Array.isArray(well.metadata?.wbv_trajectory_records)
        ? well.metadata?.wbv_trajectory_records ?? []
        : [];
    const activeTrajectoryUid = well.metadata?.active_trajectory_uid
        ?? records.find((record) => record.is_active)?.managed_trajectory_uid
        ?? null;
    const activeTrajectoryId = well.metadata?.active_trajectory_id
        ?? records.find((record) => record.is_active)?.trajectory_id
        ?? null;
    const items: ManagedProductGroupItem[] = records.map((record) => {
        const isActive = Boolean(record.is_active
            || (activeTrajectoryUid
                && record.managed_trajectory_uid === activeTrajectoryUid)
            || (activeTrajectoryId
                && record.trajectory_id === activeTrajectoryId));
        const role = isActive ? 'Active trajectory' : record.is_canonical ? 'Canonical / available' : record.is_synthetic ? 'Demo / synthetic' : 'Available';
        return {
            product_id: record.trajectory_id,
            display_name: record.trajectory_name || record.trajectory_id,
            curve_name: record.trajectory_name || record.trajectory_id,
            curve_type: record.trajectory_type || 'Wellbore trajectory',
            curve_family: 'Wellbore Geometry',
            product_category: 'wellbore_geometry',
            product_subgroup_key: record.trajectory_type || 'trajectory',
            product_subgroup_label: statusLabel(record.trajectory_type || 'Trajectory'),
            classification_confidence: record.wbv_eligible ? 'high' : 'review',
            run_date: '—',
            run_interval: optionalDepthRangeLabel(record.md_min, record.md_max, well.depth_unit || 'ft'),
            run_number: role,
            qa_flag: record.status ? statusLabel(record.status) : 'unknown',
            selectable: Boolean(record.wbv_eligible),
            source_kind: 'wellbore_geometry',
            source_id: record.source_label || record.trajectory_id,
            wmdp_state: well.wmdp_state ?? null,
            wdv_state: well.wdv_state ?? null,
            trajectory_id: record.trajectory_id,
            managed_trajectory_uid: record.managed_trajectory_uid ?? null,
            trajectory_status: record.status ?? null,
            trajectory_role: role,
            wbv_eligible: Boolean(record.wbv_eligible),
            source_label: record.source_label ?? null,
            station_count: record.station_count ?? null,
            md_min: record.md_min ?? null,
            md_max: record.md_max ?? null,
            tvd_min: record.tvd_min ?? null,
            tvd_max: record.tvd_max ?? null,
            is_active_trajectory: isActive,
            is_synthetic_trajectory: Boolean(record.is_synthetic),
        };
    });
    return {
        group_key: 'wellbore_geometry',
        group_label: 'Wellbore Geometry',
        collapsed_by_default: false,
        items,
    };
}

function wmdpProductGroupsForWell(well: ManagedInventoryWellRecord): ManagedProductGroup[] {
    const groups = [...(well.product_groups ?? [])];
    const geometryGroup = wmdpWellboreGeometryGroup(well);
    const existingIndex = groups.findIndex((group) => group.group_key === 'wellbore_geometry');
    if (existingIndex >= 0) {
        groups[existingIndex] = geometryGroup;
    }
    else {
        groups.push(geometryGroup);
    }
    return groups;
}

function wellDisplayableCurveCount(well: ManagedInventoryWellRecord): number {
    if (Number.isFinite(well.viewer_curve_count)) {
        return Number(well.viewer_curve_count);
    }
    if (Number.isFinite(well.displayable_curve_count)) {
        return Number(well.displayable_curve_count);
    }
    return 0;
}


function wellRegisteredCurveCount(well: ManagedInventoryWellRecord): number {
    const registeredFromProducts = (well.product_groups ?? [])
        .filter((group) => group.group_key !== 'wellbore_geometry')
        .reduce((total, group) => {
            return total + (group.items ?? []).filter((item) => {
                const category = (item.product_category ?? '').toLowerCase();
                const role = (item.trajectory_role ?? '').toLowerCase();
                return category !== 'wellbore_geometry' && role !== 'wellbore_geometry';
            }).length;
        }, 0);

    if (registeredFromProducts > 0) {
        return registeredFromProducts;
    }

    if (Number.isFinite(well.displayable_curve_count)) {
        return Number(well.displayable_curve_count);
    }

    return 0;
}


type WmdpSortKey = 'wellName' | 'wellId' | 'field' | 'operator' | 'status' | 'updated';

type WmdpBulkAction = 'load' | 'unload' | 'remove';

type WmdpProductCategoryKey = string;

type WmdpProductSubgroup = {
    subgroupKey: string;
    subgroupLabel: string;
    items: ManagedProductGroupItem[];
};

// KR-1: Backend-owned Knowledge Repository contracts.
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
function groupCurveItemsByAuthoritativeGeneralFamily(items: ManagedProductGroupItem[]): WmdpProductSubgroup[] {
    const groupsByKey = new Map<string, WmdpProductSubgroup>();
    for (const item of items) {
        const familyKey = item.general_curve_family_key?.trim();
        const familyLabel = item.general_curve_family?.trim();
        if (!familyKey || !familyLabel) {
            continue;
        }
        const existing = groupsByKey.get(familyKey);
        if (existing) {
            existing.items.push(item);
        }
        else {
            groupsByKey.set(familyKey, {
                subgroupKey: familyKey,
                subgroupLabel: familyLabel,
                items: [item],
            });
        }
    }
    return [...groupsByKey.values()];
}

/**
 * Non-curve product groups continue to use their existing backend-provided
 * subgroup contract. This function is not curve-family authority.
 */
function groupProductItemsByKrSubgroups(items: ManagedProductGroupItem[], krSubgroups: KrSubgroup[]): WmdpProductSubgroup[] {
    if (krSubgroups.length === 0)
        return [];
    const sortedSubgroups = [...krSubgroups].sort((a, b) => a.order - b.order);
    const subgroupByKey = new Map<string, WmdpProductSubgroup>(sortedSubgroups.map((s) => [s.key, { subgroupKey: s.key, subgroupLabel: s.label, items: [] }]));
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
}

function productItemClassificationTitle(item: ManagedProductGroupItem): string | undefined {
    const parts = [
        item.product_subgroup_label ? `Subclass: ${item.product_subgroup_label}` : '',
        item.curve_family ? `Family: ${item.curve_family}` : '',
        item.classification_confidence ? `Confidence: ${item.classification_confidence}` : '',
    ].filter(Boolean);
    return parts.length > 0 ? parts.join(' | ') : undefined;
}

function productItemDisplayName(item: ManagedProductGroupItem): string {
    return item.curve_name || item.display_name || item.product_id;
}

function productItemRunDateDisplay(value: unknown): string {
    if (value === null || value === undefined) {
        return '—';
    }
    if (typeof value !== 'string' && typeof value !== 'number') {
        return '—';
    }
    const text = String(value).trim();
    if (!text) {
        return '—';
    }
    const normalized = text.replace(/[\s_-]+/g, ' ').trim().toUpperCase();
    const placeholders = new Set([
        'LOG DATE',
        'LOGDATE',
        'RUN DATE',
        'DATE',
        'N A',
        'NA',
        'N/A',
        'NONE',
        'NULL',
        'UNKNOWN',
        'UNAVAILABLE',
        '-',
        '—',
    ]);
    if (placeholders.has(normalized) || placeholders.has(text.toUpperCase())) {
        return '—';
    }
    return text;
}

function expandableProductName(value: string) {
    const text = safeText(value);
    const maxLength = 64;
    if (text.length <= maxLength) {
        return <>{text}</>;
    }
    return (<details className="wlv-wmdp-product-name-details">
      <summary title={text}>{text.slice(0, maxLength - 1)}…</summary>
      <span>{text}</span>
    </details>);
}

function WmdpProductItemRow({ item, selected, onToggle, managedWellId, onSetActiveTrajectory, trajectoryApplyingId, }: {
    item: ManagedProductGroupItem;
    selected: boolean;
    onToggle: () => void;
    managedWellId?: string;
    onSetActiveTrajectory?: (managedWellId: string, trajectoryId: string) => void;
    trajectoryApplyingId?: string | null;
}) {
    const isGeometry = item.product_category === 'wellbore_geometry' || item.source_kind === 'wellbore_geometry';
    const trajectoryReference = item.managed_trajectory_uid || item.trajectory_id;
    const canSetActive = Boolean(isGeometry
        && managedWellId
        && trajectoryReference
        && item.wbv_eligible
        && !item.is_active_trajectory);
    const applying = Boolean(trajectoryReference
        && trajectoryApplyingId === trajectoryReference);
    return (<label className={isGeometry ? 'wlv-wmdp-product-item wlv-wmdp-product-item-geometry' : 'wlv-wmdp-product-item'} key={item.product_id}>
      <input type="checkbox" checked={selected} disabled={item.selectable === false} onChange={onToggle} aria-label={`Select ${productItemDisplayName(item)}`}/>
      <span className="wlv-wmdp-product-item-summary">
        <span className="wlv-wmdp-product-item-code-wrap" title={productItemClassificationTitle(item)}>
          <strong className="wlv-wmdp-product-item-code">{productItemDisplayName(item)}</strong>
        </span>
        {isGeometry ? (<>
            <span className="wlv-wmdp-product-item-description" title={safeText(item.curve_type)}>
              <strong>Type:</strong> {statusLabel(item.curve_type)}
            </span>
            <span className="wlv-wmdp-product-item-name" title={safeText(item.source_label || item.source_id)}>
              <strong>Source:</strong> {expandableProductName(item.source_label || item.source_id || '—')}
            </span>
            <span className="wlv-wmdp-product-item-run-date" title={safeText(item.trajectory_role)}>
              <strong>Role:</strong> {safeText(item.trajectory_role)}
            </span>
            <span className="wlv-wmdp-product-item-run-interval" title={safeText(item.run_interval)}>
              <strong>MD Range:</strong> {safeText(item.run_interval)}
            </span>
            <span className="wlv-wmdp-product-item-run-number" title={safeText(item.station_count)}>
              <strong>Stations:</strong> {safeText(item.station_count)}
            </span>
            <span className="wlv-wmdp-product-item-qa-flag" title={safeText(item.qa_flag)}>
              <strong>Status:</strong> {safeText(item.qa_flag)}
            </span>
            {canSetActive ? (<button type="button" className="wlv-wmdp-product-item-action" disabled={applying} onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (managedWellId && trajectoryReference && onSetActiveTrajectory) {
                        onSetActiveTrajectory(managedWellId, trajectoryReference);
                    }
                }}>
                {applying ? 'Setting active…' : 'Set Active Trajectory'}
              </button>) : null}
          </>) : (<>
            <span className="wlv-wmdp-product-item-description" title={safeText(item.curve_type)}>
              <strong>Description:</strong> {safeText(item.curve_type)}
            </span>
            <span className="wlv-wmdp-product-item-name" title={safeText(item.display_name || productItemDisplayName(item))}>
              <strong>File Name:</strong> {expandableProductName(item.display_name || productItemDisplayName(item))}
            </span>
            <span className="wlv-wmdp-product-item-run-date" title={productItemRunDateDisplay(item.run_date)}>
              <strong>Run Date:</strong> {productItemRunDateDisplay(item.run_date)}
            </span>
            <span className="wlv-wmdp-product-item-run-interval" title={safeText(item.run_interval)}>
              <strong>Run Interval:</strong> {safeText(item.run_interval)}
            </span>
            <span className="wlv-wmdp-product-item-run-number" title={safeText(item.run_number)}>
              <strong>Run Number:</strong> {safeText(item.run_number)}
            </span>
            <span className="wlv-wmdp-product-item-qa-flag" title={[`QA Flag: ${safeText(item.qa_flag)}`, item.classification_source ? `Classification source: ${item.classification_source}` : '', ...(item.classification_reasons ?? [])].filter(Boolean).join('\n')}>
              <strong>QA Flag:</strong> {safeText(item.qa_flag)}
            </span>
          </>)}
      </span>
    </label>);
}

function ManagedWellInventoryPage({ onOpenLogViewer, onClearLogViewer, activeManagedWellId }: {
    onOpenLogViewer: (identity?: ManagedWellIdentity | null) => void;
    onClearLogViewer: () => void;
    activeManagedWellId: string | null;
}) {
    const [status, setStatus] = useState<ManagedInventoryStatusPayload | null>(null);
    const [wells, setWells] = useState<ManagedInventoryWellRecord[]>([]);
    const [selectedWellId, setSelectedWellId] = useState<string | null>(null);
    const [selectedWellIds, setSelectedWellIds] = useState<Set<string>>(new Set());
    const [expandedWellIds, setExpandedWellIds] = useState<Set<string>>(new Set());
    const [expandedProductGroupIds, setExpandedProductGroupIds] = useState<Set<string>>(new Set());
    const [selectedProductItemIds, setSelectedProductItemIds] = useState<Set<string>>(new Set());
    const [searchQuery, setSearchQuery] = useState('');
    const [sortKey, setSortKey] = useState<WmdpSortKey>('wellName');
    const [pageSize, setPageSize] = useState(25);
    const [currentPage, setCurrentPage] = useState(1);
    const [bulkAction, setBulkAction] = useState<WmdpBulkAction>('load');
    const [bulkApplying, setBulkApplying] = useState(false);
    const [flushApplying, setFlushApplying] = useState(false);
    const [trajectoryApplyingId, setTrajectoryApplyingId] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [registering, setRegistering] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [recoveryByWellId, setRecoveryByWellId] = useState<Map<string, WmdDownstreamRecoveryStatus>>(new Map());
    const [rebuildingWellId, setRebuildingWellId] = useState<string | null>(null);
    // KR-1: backend-owned product groups fetched once on mount.
    // If unavailable the page degrades safely (subgroups not shown).
    const [krProductGroups, setKrProductGroups] = useState<KrProductGroup[]>([]);
    const seedAlreadyRegistered = developmentSeedAlreadyRegistered(wells);
    const backendConnected = Boolean(status?.ok && !error);
    const filteredWells = useMemo(() => {
        const query = searchQuery.trim().toLowerCase();
        const matchesSearch = (well: ManagedInventoryWellRecord) => {
            if (!query)
                return true;
            return [
                wellDisplayName(well),
                well.managed_well_id,
                well.well_id,
                well.field,
                well.operator,
                well.country,
                wellStatus(well),
            ].some((value) => safeText(value, '').toLowerCase().includes(query));
        };
        const sortValue = (well: ManagedInventoryWellRecord): string => {
            if (sortKey === 'wellId')
                return safeText(well.well_id, '').toLowerCase();
            if (sortKey === 'field')
                return safeText(well.field, '').toLowerCase();
            if (sortKey === 'operator')
                return safeText(well.operator, '').toLowerCase();
            if (sortKey === 'status')
                return statusLabel(wellStatus(well)).toLowerCase();
            if (sortKey === 'updated')
                return safeText(well.updated_at ?? well.created_at, '').toLowerCase();
            return wellDisplayName(well).toLowerCase();
        };
        return wells.filter(matchesSearch).sort((a, b) => sortValue(a).localeCompare(sortValue(b)));
    }, [searchQuery, sortKey, wells]);
    const totalPages = Math.max(1, Math.ceil(filteredWells.length / pageSize));
    const safeCurrentPage = Math.min(currentPage, totalPages);
    const pageStartIndex = filteredWells.length === 0 ? 0 : (safeCurrentPage - 1) * pageSize;
    const pageEndIndex = Math.min(pageStartIndex + pageSize, filteredWells.length);
    const pagedWells = filteredWells.slice(pageStartIndex, pageEndIndex);
    const allVisibleSelected = pagedWells.length > 0 && pagedWells.every((well) => selectedWellIds.has(well.managed_well_id));
    const loadInventory = async () => {
        setLoading(true);
        setError(null);
        // KR-1: Fetch backend-owned product groups in parallel with inventory.
        // A KR failure is non-fatal — the page degrades gracefully (no subgrouping).
        fetchWlvJson<KrProductGroupsPayload>('/api/wlv/knowledge/product-groups')
            .then((payload) => setKrProductGroups(payload.groups ?? []))
            .catch(() => { });
        try {
            const [nextStatus, nextWells] = await Promise.all([
                fetchWlvJson<ManagedInventoryStatusPayload>('/api/wlv/inventory/status'),
                fetchWlvJson<ManagedInventoryWellRecord[]>('/api/wlv/inventory/wells'),
            ]);
            setStatus(nextStatus);
            setWells(nextWells);
            const recoveryResults = await Promise.all(nextWells.map(async (well) => {
                try {
                    return [well.managed_well_id, await fetchWmdDownstreamRecovery(well.managed_well_id)] as const;
                }
                catch {
                    return null;
                }
            }));
            setRecoveryByWellId(new Map(recoveryResults.filter((value): value is readonly [string, WmdDownstreamRecoveryStatus] => value !== null)));
            setSelectedWellId((current) => (current && nextWells.some((well) => well.managed_well_id === current)
                ? current
                : nextWells[0]?.managed_well_id ?? null));
            setSelectedWellIds((current) => {
                const validIds = new Set(nextWells.map((well) => well.managed_well_id));
                return new Set([...current].filter((id) => validIds.has(id)));
            });
            setExpandedWellIds((current) => {
                const validIds = new Set(nextWells.map((well) => well.managed_well_id));
                return new Set([...current].filter((id) => validIds.has(id)));
            });
            setExpandedProductGroupIds((current) => {
                const validPrefixes = nextWells.map((well) => `${well.managed_well_id}:`);
                return new Set([...current].filter((id) => validPrefixes.some((prefix) => id.startsWith(prefix))));
            });
            setSelectedProductItemIds(new Set());
        }
        catch (caught) {
            setError(caught instanceof Error ? caught.message : 'Unable to load managed well inventory');
            setStatus(null);
            setWells([]);
            setRecoveryByWellId(new Map());
            setSelectedWellId(null);
            setSelectedWellIds(new Set());
            setExpandedWellIds(new Set());
            setExpandedProductGroupIds(new Set());
            setSelectedProductItemIds(new Set());
        }
        finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        void loadInventory();
    }, []);
    useEffect(() => {
        setCurrentPage(1);
    }, [pageSize, searchQuery, sortKey, wells.length]);
    const registerSeedWell = async () => {
        if (seedAlreadyRegistered) {
            setError('Development seed well is already registered. Use Refresh to reload the managed inventory.');
            return;
        }
        setRegistering(true);
        setError(null);
        try {
            const result = await fetchWlvJson<{
                record: ManagedInventoryWellRecord;
            }>('/api/wlv/inventory/wells/register-seed', {
                method: 'POST',
            });
            await loadInventory();
            setSelectedWellId(result.record.managed_well_id);
            setExpandedWellIds((current) => new Set(current).add(result.record.managed_well_id));
        }
        catch (caught) {
            setError(caught instanceof Error ? caught.message : 'Unable to register development seed well');
        }
        finally {
            setRegistering(false);
        }
    };
    const toggleWellSelected = (managedWellId: string) => {
        setSelectedWellIds((current) => {
            const next = new Set(current);
            if (next.has(managedWellId)) {
                next.delete(managedWellId);
            }
            else {
                next.add(managedWellId);
            }
            return next;
        });
        setSelectedWellId(managedWellId);
    };
    const toggleVisibleSelection = () => {
        setSelectedWellIds((current) => {
            const next = new Set(current);
            if (allVisibleSelected) {
                pagedWells.forEach((well) => next.delete(well.managed_well_id));
            }
            else {
                pagedWells.forEach((well) => next.add(well.managed_well_id));
            }
            return next;
        });
    };
    const toggleWellExpanded = (managedWellId: string) => {
        setExpandedWellIds((current) => {
            const next = new Set(current);
            if (next.has(managedWellId)) {
                next.delete(managedWellId);
            }
            else {
                next.add(managedWellId);
            }
            return next;
        });
        setSelectedWellId(managedWellId);
    };
    const productGroupId = (managedWellId: string, categoryKey: WmdpProductCategoryKey): string => `${managedWellId}:${categoryKey}`;
    const toggleProductGroupExpanded = (managedWellId: string, categoryKey: WmdpProductCategoryKey) => {
        const groupId = productGroupId(managedWellId, categoryKey);
        setExpandedProductGroupIds((current) => {
            const next = new Set(current);
            if (next.has(groupId)) {
                next.delete(groupId);
            }
            else {
                next.add(groupId);
            }
            return next;
        });
        setSelectedWellId(managedWellId);
    };
    const toggleProductItemSelected = (itemId: string) => {
        setSelectedProductItemIds((current) => {
            const next = new Set(current);
            if (next.has(itemId)) {
                next.delete(itemId);
            }
            else {
                next.add(itemId);
            }
            return next;
        });
    };
    const toggleProductGroupItemsSelected = (items: ManagedProductGroupItem[]) => {
        setSelectedProductItemIds((current) => {
            const selectableIds = items
                .filter((item) => item.selectable !== false)
                .map((item) => item.product_id);
            const allSelected = selectableIds.length > 0 && selectableIds.every((id) => current.has(id));
            const next = new Set(current);
            selectableIds.forEach((id) => {
                if (allSelected) {
                    next.delete(id);
                }
                else {
                    next.add(id);
                }
            });
            return next;
        });
    };
    const selectedProductWellIds = useMemo(() => {
        const owners = new Set<string>();
        if (selectedProductItemIds.size === 0)
            return owners;
        wells.forEach((well) => {
            const ownsSelectedProduct = (well.product_groups ?? []).some((group) => (group.items ?? []).some((item) => selectedProductItemIds.has(item.product_id)));
            if (ownsSelectedProduct)
                owners.add(well.managed_well_id);
        });
        return owners;
    }, [selectedProductItemIds, wells]);
    const productOwnerById = useMemo(() => {
        const owners = new Map<string, string>();
        wells.forEach((well) => {
            (well.product_groups ?? []).forEach((group) => {
                (group.items ?? []).forEach((item) => {
                    owners.set(item.product_id, well.managed_well_id);
                });
            });
        });
        return owners;
    }, [wells]);
    const selectedProductItems = useMemo(() => (wells.flatMap((well) => (well.product_groups ?? []).flatMap((group) => group.items ?? []))
        .filter((item) => selectedProductItemIds.has(item.product_id))), [selectedProductItemIds, wells]);
    const selectedWellCount = selectedWellIds.size;
    const selectedProductCount = selectedProductItemIds.size;
    const hasSelection = selectedWellCount > 0 || selectedProductCount > 0;
    const selectedRecoveryWellIds = new Set([...selectedWellIds, ...selectedProductWellIds]);
    const recoveryBlocksLoad = bulkAction === 'load' && [...selectedRecoveryWellIds].some((wellId) => recoveryByWellId.get(wellId)?.wdv_load_allowed !== true);
    const canApplyBulkAction = hasSelection && !bulkApplying && !recoveryBlocksLoad;
    const rebuildWell = async (managedWellId: string) => {
        setRebuildingWellId(managedWellId);
        setError(null);
        try {
            await rebuildWmdPayload(managedWellId);
            await loadInventory();
        }
        catch (caught) {
            setError(caught instanceof Error ? caught.message : 'Unable to rebuild transient WMD payload');
        }
        finally {
            setRebuildingWellId(null);
        }
    };
    const applyBulkAction = async () => {
        if (!canApplyBulkAction)
            return;
        const productOwnerIds = [...selectedProductWellIds];
        if (bulkAction === 'remove') {
            const managedWellIds = [...selectedWellIds];
            setBulkApplying(true);
            setError(null);
            try {
                await fetchWlvJson('/api/wlv/inventory/remove-from-mdp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(buildInventoryRemovalPayload(wells.filter((well) => selectedWellIds.has(well.managed_well_id)), selectedProductItems)),
                });
                const removedActiveWell = activeManagedWellId !== null
                    && (managedWellIds.includes(activeManagedWellId) || productOwnerIds.includes(activeManagedWellId));
                setSelectedWellIds(new Set());
                setSelectedProductItemIds(new Set());
                await loadInventory();
                if (removedActiveWell) {
                    onClearLogViewer();
                }
            }
            catch (caught) {
                setError(caught instanceof Error ? caught.message : 'Unable to completely delete selected managed data from MWD');
            }
            finally {
                setBulkApplying(false);
            }
            return;
        }
        if (bulkAction !== 'load' && bulkAction !== 'unload')
            return;
        if (bulkAction === 'load') {
            const selectedWells = wells.filter((well) => selectedWellIds.has(well.managed_well_id));
            const selectedProductsByWell = new Map<string, string[]>();
            selectedProductItems.forEach((item) => {
                const ownerId = productOwnerById.get(item.product_id);
                if (!ownerId)
                    return;
                selectedProductsByWell.set(ownerId, [
                    ...(selectedProductsByWell.get(ownerId) ?? []),
                    item.product_id,
                ]);
            });
            const selectionIds = new Set<string>([
                ...selectedWells.map((well) => well.managed_well_id),
                ...selectedProductsByWell.keys(),
            ]);
            const selections = [...selectionIds].map((managedWellId) => ({
                managed_well_id: managedWellId,
                product_ids: selectedWellIds.has(managedWellId)
                    ? []
                    : selectedProductsByWell.get(managedWellId) ?? [],
            }));
            if (selections.length === 0) {
                setError('Select one or more managed wells or product rows to load to the Well Data Viewer.');
                return;
            }
            setBulkApplying(true);
            setError(null);
            try {
                const response = await fetchWlvJson<{
                    workspace?: {
                        active_managed_well_id?: string | null;
                        active_managed_well_uid?: string | null;
                    };
                }>('/api/wlv/inventory/wdv-workspace/wells/load', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ selections }),
                });
                await loadInventory();
                if (response.workspace?.active_managed_well_id && response.workspace.active_managed_well_uid) {
                    onOpenLogViewer(managedWellIdentityFromActiveWorkspace(response.workspace));
                } else {
                    throw new Error('Backend WDV workspace did not return the active managed-well identity pair.');
                }
            }
            catch (caught) {
                setError(caught instanceof Error ? caught.message : 'Unable to load selected managed wells into the Well Data Viewer');
            }
            finally {
                setBulkApplying(false);
            }
            return;
        }
        const unloadWellIds = Array.from(new Set([
            ...selectedWellIds,
            ...productOwnerIds,
            ...(selectedWellId ? [selectedWellId] : []),
        ])).filter(Boolean);
        if (unloadWellIds.length === 0) {
            setError('Select one or more managed wells or product rows to unload from the Well Data Viewer.');
            return;
        }
        const selections = unloadWellIds.map((managedWellId) => ({
            managed_well_id: managedWellId,
            product_ids: selectedProductItems
                .filter((item) => productOwnerById.get(item.product_id) === managedWellId)
                .map((item) => item.product_id),
        }));
        setBulkApplying(true);
        setError(null);
        try {
            const response = await fetchWlvJson<{
                workspace?: {
                    active_managed_well_id?: string | null;
                    active_managed_well_uid?: string | null;
                };
            }>('/api/wlv/inventory/wdv-workspace/wells/unload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selections }),
            });
            await loadInventory();
            const nextActive = response.workspace?.active_managed_well_id ?? null;
            if (!nextActive) {
                onClearLogViewer();
            } else if (activeManagedWellId && unloadWellIds.includes(activeManagedWellId)) {
                if (!response.workspace?.active_managed_well_uid) {
                    throw new Error('Backend WDV workspace did not return the active managed-well UID.');
                }
                onOpenLogViewer(managedWellIdentityFromActiveWorkspace(response.workspace));
            }
        }
        catch (caught) {
            setError(caught instanceof Error ? caught.message : 'Unable to unload selected managed data from the Well Data Viewer');
        }
        finally {
            setBulkApplying(false);
        }
    };
    const flushManagedData = async () => {
        if (flushApplying || loading || wells.length === 0)
            return;
        const confirmed = window.confirm(
            `Flush all transient MWD managed data? This will remove ${wells.length} managed well${wells.length === 1 ? '' : 's'} from MWD and clear their WDV workspace state. Original LAS/DLIS source files are not deleted.`,
        );
        if (!confirmed)
            return;
        setFlushApplying(true);
        setError(null);
        try {
            await flushMwdTransientData();
            onClearLogViewer();
            setSelectedWellIds(new Set());
            setSelectedProductItemIds(new Set());
            setExpandedWellIds(new Set());
            setExpandedProductGroupIds(new Set());
            await loadInventory();
        }
        catch (caught) {
            setError(caught instanceof Error ? caught.message : 'Unable to flush transient MWD managed data');
        }
        finally {
            setFlushApplying(false);
        }
    };
    const setActiveTrajectory = async (managedWellId: string, managedTrajectoryUid: string) => {
        setTrajectoryApplyingId(managedTrajectoryUid);
        setError(null);
        try {
            await fetchWlvJson(`/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/trajectories/active`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ managed_trajectory_uid: managedTrajectoryUid, requested_by: 'mdp' }),
            });
            await loadInventory();
        }
        catch (caught) {
            setError(caught instanceof Error ? caught.message : 'Unable to set active trajectory');
        }
        finally {
            setTrajectoryApplyingId(null);
        }
    };
    return (<section className="wlv-managed-inventory-page wlv-wmdp-page" aria-label="Managed Well Data">
      <header className="wlv-managed-inventory-header wlv-wmdp-page-header">
        <div>
          <span className="wlv-page-kicker">Data</span>
          <h1>Managed Data</h1>
          <p>Manage registered wells and data made available to the Well Data Viewer.</p>
        </div>
        <div className="wlv-wmdp-page-actions">
          <button type="button" className="wlv-wmdp-disposable-seed-button" onClick={registerSeedWell} disabled={loading || registering || seedAlreadyRegistered} title="Temporary development bootstrap action. Remove when intake workflow is complete.">
            {seedAlreadyRegistered ? '[disposable] Seed Registered' : registering ? '[disposable] Seeding…' : '[disposable] Seed Example Well'}
          </button>
        </div>
      </header>

      {error ? <div className="wlv-managed-inventory-error" role="alert">{error}</div> : null}
      {recoveryBlocksLoad ? <div className="wlv-wmd-recovery-banner" role="status">Selected data is not available to WDV. Restore the source or rebuild the transient WMD payload shown below.</div> : null}

      <section className="wlv-wmdp-panel" aria-label="Managed well data table">
        <header className="wlv-wmdp-panel-header">
          <div>
            <h2>Managed Well Data</h2>
            <p>{backendConnected ? 'Connected' : 'Backend unavailable'} · {safeText(status?.service, 'inventory')} · {wells.length} managed wells</p>
          </div>
          <div className="wlv-wmdp-panel-actions">
            <label className="wlv-wmdp-sort-control">
              <span>Sort by</span>
              <select value={sortKey} onChange={(event) => setSortKey(event.target.value as WmdpSortKey)}>
                <option value="wellName">Well name</option>
                <option value="wellId">Well ID</option>
                <option value="field">Field</option>
                <option value="operator">Operator</option>
                <option value="status">Status</option>
                <option value="updated">Updated</option>
              </select>
            </label>
            <button type="button" onClick={loadInventory} disabled={loading || flushApplying}>Refresh</button>
            <button type="button" onClick={() => setExpandedWellIds(new Set())} disabled={expandedWellIds.size === 0 || flushApplying}>Collapse</button>
            <button type="button" onClick={() => void flushManagedData()} disabled={loading || flushApplying || wells.length === 0} title="Flush all transient MWD managed data. Original LAS/DLIS source files are preserved.">{flushApplying ? 'Flushing MWD…' : 'Flush MWD'}</button>
          </div>
        </header>

        <div className="wlv-wmdp-control-band" aria-label="Managed data controls">
          <div className="wlv-wmdp-control-row wlv-wmdp-control-row-paging">
            <input type="search" placeholder="Search Managed Wells..." value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} aria-label="Search Managed Wells"/>
            <label className="wlv-wmdp-page-size-control">
              <span>Page size</span>
              <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
            <button type="button" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={safeCurrentPage <= 1}>Previous</button>
            <button type="button" onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))} disabled={safeCurrentPage >= totalPages}>Next</button>
            <span className="wlv-wmdp-page-readout">Showing {filteredWells.length === 0 ? '0' : `${pageStartIndex + 1}–${pageEndIndex}`} of {filteredWells.length}</span>
          </div>

          <div className="wlv-wmdp-control-row wlv-wmdp-control-row-bulk">
            <span className="wlv-wmdp-selected-readout">Selected wells {selectedWellCount} · products {selectedProductCount}</span>
            <label className="wlv-wmdp-action-control">
              <span>Action</span>
              <select value={bulkAction} onChange={(event) => setBulkAction(event.target.value as WmdpBulkAction)}>
                <option value="load">Load selected to Data Viewer</option>
                <option value="unload">Unload selected from Data Viewer</option>
                <option value="remove">Remove selected from MWD</option>
              </select>
            </label>
            <button type="button" onClick={applyBulkAction} disabled={!canApplyBulkAction}>{bulkApplying ? (bulkAction === 'remove' ? 'Removing…' : bulkAction === 'unload' ? 'Unloading…' : 'Loading…') : 'Apply'}</button>
          </div>
        </div>

        <div className="wlv-wmdp-table-wrap">
          <table className="wlv-wmdp-table">
            <thead>
              <tr>
                <th className="wlv-wmdp-col-select">
                  <input type="checkbox" checked={allVisibleSelected} disabled={pagedWells.length === 0} onChange={toggleVisibleSelection} aria-label="Select visible managed wells"/>
                </th>
                <th className="wlv-wmdp-col-expand" aria-label="Expand"/>
                <th>Well Name</th>
                <th>UWI</th>
                <th>Well Type</th>
                <th>Field</th>
                <th>Block</th>
                <th>Operator</th>
                <th className="wlv-wmdp-registered-curve-count-header"><span>Registered</span><span>Curves</span></th>
                <th className="wlv-wmdp-promoted-curve-count-header"><span>Promoted</span><span>Curves</span></th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (<tr><td colSpan={11} className="wlv-wmdp-empty-cell">Loading managed inventory from backend...</td></tr>) : pagedWells.length === 0 ? (<tr>
                  <td colSpan={11} className="wlv-wmdp-empty-cell">
                    {wells.length === 0 ? 'No managed wells registered.' : 'No managed wells match the current search.'}
                  </td>
                </tr>) : pagedWells.map((well) => {
            const expanded = expandedWellIds.has(well.managed_well_id);
            const rowSelected = selectedWellIds.has(well.managed_well_id);
            const productCategories = wmdpProductGroupsForWell(well);
            return (<>
                    <tr className={rowSelected || selectedWellId === well.managed_well_id ? 'is-selected' : ''} key={well.managed_well_id}>
                      <td className="wlv-wmdp-col-select">
                        <input type="checkbox" checked={rowSelected} onChange={() => toggleWellSelected(well.managed_well_id)} aria-label={`Select ${wellDisplayName(well)}`}/>
                      </td>
                      <td className="wlv-wmdp-col-expand">
                        <button type="button" className="wlv-wmdp-expand-btn" onClick={() => toggleWellExpanded(well.managed_well_id)} aria-label={`${expanded ? 'Collapse' : 'Expand'} ${wellDisplayName(well)}`} aria-expanded={expanded}>
                          {expanded ? '▾' : '▸'}
                        </button>
                      </td>
                      <td className="wlv-wmdp-name-cell">
                        <button type="button" onClick={() => setSelectedWellId(well.managed_well_id)}>
                          <strong>{wellDisplayName(well)}</strong>
                          <span>{well.managed_well_id}</span>
                        </button>
                      </td>
                      <td>{safeText(well.uwi)}</td>
                      <td>{wellTypeLabel(well)}</td>
                      <td>{safeText(well.field)}</td>
                      <td>{safeText(well.block)}</td>
                      <td>{safeText(well.operator)}</td>
                      <td className="wlv-wmdp-registered-curve-count-cell">{wellRegisteredCurveCount(well)}</td>
                      <td className="wlv-wmdp-promoted-curve-count-cell">{wellDisplayableCurveCount(well)}</td>
                      <td>
                        <div className="wlv-wmdp-row-actions">
                          {(() => {
                            const recovery = recoveryByWellId.get(well.managed_well_id);
                            const loadAllowed = recovery?.wdv_load_allowed === true;
                            const action = recovery ? wmdRecoveryAction(recovery) : null;
                            return <>
                              <button type="button" disabled={!loadAllowed} title={!loadAllowed ? recovery?.recovery_message || 'WMD payload unavailable' : 'Load managed well to WDV'} onClick={() => { setSelectedWellIds(new Set([well.managed_well_id])); void fetchWlvJson('/api/wlv/inventory/load-to-wdv', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildInventoryActionPayload(well, [])) }).then(() => loadInventory()).then(() => onOpenLogViewer(managedWellIdentityFromPayload(well))).catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load managed well to WDV')); }}>Load</button>
                              {action === 'rebuild' ? <button type="button" disabled={rebuildingWellId === well.managed_well_id} onClick={() => void rebuildWell(well.managed_well_id)}>{rebuildingWellId === well.managed_well_id ? 'Rebuilding…' : 'Rebuild'}</button> : null}
                              {action === 'restore-source' ? <button type="button" disabled title={recovery?.recovery_message || 'Restore the original unchanged source before rebuilding'}>Restore source</button> : null}
                            </>;
                          })()}
                          <button type="button" onClick={() => setSelectedWellId(well.managed_well_id)}>Info</button>
                          <button type="button" onClick={() => { setSelectedWellIds(new Set([well.managed_well_id])); setSelectedProductItemIds(new Set()); setBulkAction('remove'); }}>Remove</button>
                        </div>
                      </td>
                    </tr>
                    {expanded ? (<tr className="wlv-wmdp-expanded-row" key={`${well.managed_well_id}-expanded`}>
                        <td colSpan={11}>
                          <div className="wlv-wmdp-expanded-content wlv-wmdp-product-groups">
                            {productCategories.map((category) => {
                        const groupId = productGroupId(well.managed_well_id, category.group_key);
                        const categoryExpanded = expandedProductGroupIds.has(groupId);
                        const categoryItems = category.items ?? [];
                        const selectableCategoryItems = categoryItems.filter((item) => item.selectable !== false);
                        const categoryItemsAllSelected = selectableCategoryItems.length > 0
                            && selectableCategoryItems.every((item) => selectedProductItemIds.has(item.product_id));
                        return (<section className="wlv-wmdp-product-group" key={category.group_key}>
                                  <div className="wlv-wmdp-product-group-header">
                                    <input type="checkbox" className="wlv-wmdp-product-group-select" checked={categoryItemsAllSelected} disabled={selectableCategoryItems.length === 0} onChange={() => toggleProductGroupItemsSelected(categoryItems)} aria-label={`Select all ${category.group_label}`}/>
                                    <button type="button" className="wlv-wmdp-product-group-toggle" onClick={() => toggleProductGroupExpanded(well.managed_well_id, category.group_key)} aria-expanded={categoryExpanded}>
                                      <span className="wlv-wmdp-product-group-caret">{categoryExpanded ? '▾' : '▸'}</span>
                                      <span className="wlv-wmdp-product-group-title">{category.group_label}</span>
                                      <span className="wlv-wmdp-product-group-count">{categoryItems.length}</span>
                                    </button>
                                  </div>
                                  {categoryExpanded ? (() => {
                                const usesAuthoritativeCurveFamilyContract = categoryItems.length > 0
                                    && categoryItems.every((item) => Boolean(
                                        item.general_curve_family_key?.trim()
                                        && item.general_curve_family?.trim()
                                    ));
                                const krGroup = krProductGroups.find((g) => g.key === category.group_key);
                                const krSubgroups = krGroup?.subgroups ?? [];
                                const subgroupedItems = usesAuthoritativeCurveFamilyContract
                                    ? groupCurveItemsByAuthoritativeGeneralFamily(categoryItems)
                                    : krSubgroups.length > 0
                                        ? groupProductItemsByKrSubgroups(categoryItems, krSubgroups)
                                        : [];
                                return subgroupedItems.length > 0 ? (<div className="wlv-wmdp-product-subgroups">
                                        {categoryItems.length === 0 ? (<div className="wlv-wmdp-product-empty">No registered items.</div>) : subgroupedItems.map((subgroup) => (<section className="wlv-wmdp-product-subgroup" key={subgroup.subgroupKey}>
                                            <div className="wlv-wmdp-product-subgroup-header">
                                              <span className="wlv-wmdp-product-subgroup-caret">▾</span>
                                              <span className="wlv-wmdp-product-subgroup-title">{subgroup.subgroupLabel}</span>
                                              <span className="wlv-wmdp-product-subgroup-count">{subgroup.items.length}</span>
                                            </div>
                                            <div className="wlv-wmdp-product-items">
                                              {subgroup.items.map((item) => (<WmdpProductItemRow item={item} key={item.product_id} selected={selectedProductItemIds.has(item.product_id)} onToggle={() => toggleProductItemSelected(item.product_id)} managedWellId={well.managed_well_id} onSetActiveTrajectory={setActiveTrajectory} trajectoryApplyingId={trajectoryApplyingId}/>))}
                                            </div>
                                          </section>))}
                                      </div>) : (<div className="wlv-wmdp-product-items">
                                        {categoryItems.length === 0 ? (<div className="wlv-wmdp-product-empty">No registered items.</div>) : categoryItems.map((item) => (<WmdpProductItemRow item={item} key={item.product_id} selected={selectedProductItemIds.has(item.product_id)} onToggle={() => toggleProductItemSelected(item.product_id)} managedWellId={well.managed_well_id} onSetActiveTrajectory={setActiveTrajectory} trajectoryApplyingId={trajectoryApplyingId}/>))}
                                      </div>);
                            })() : null}
                                </section>);
                    })}
                          </div>
                        </td>
                      </tr>) : null}
                  </>);
        })}
            </tbody>
          </table>
        </div>
      </section>
    </section>);
}

type DemoNavIconKey = 'log-viewer' | 'data' | 'sources' | 'knowledge' | 'wellbore-3d' | 'info' | 'toolbox' | 'settings';

type DemoNavItem = {
    label: string;
    icon: DemoNavIconKey;
    view?: DemoNavView;
};

function DemoRailIcon({ icon }: {
    icon: DemoNavIconKey;
}) {
    const commonProps = {
        width: 22,
        height: 22,
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        strokeWidth: 2,
        strokeLinecap: 'round' as const,
        strokeLinejoin: 'round' as const,
        focusable: false,
    };
    if (icon === 'log-viewer') {
        return (<svg {...commonProps} aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2"/>
        <circle cx="8.5" cy="9" r="1.5"/>
        <path d="M21 15l-5-5L5 21"/>
      </svg>);
    }
    if (icon === 'data') {
        return (<svg {...commonProps} aria-hidden="true">
        <ellipse cx="12" cy="5" rx="9" ry="3"/>
        <path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/>
        <path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>
      </svg>);
    }
    if (icon === 'sources') {
        return (<svg {...commonProps} aria-hidden="true">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/>
        <line x1="12" y1="3" x2="12" y2="15"/>
      </svg>);
    }
    if (icon === 'knowledge') {
        return (<svg {...commonProps} aria-hidden="true">
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16z"/>
        <path d="M8 7h8"/>
        <path d="M8 11h8"/>
        <path d="M8 15h5"/>
        <path d="M4 5.5A2.5 2.5 0 0 0 6.5 8H20"/>
      </svg>);
    }
    if (icon === 'wellbore-3d') {
        return (<svg {...commonProps} aria-hidden="true">
        <path d="M12 3 20 7.5v9L12 21 4 16.5v-9L12 3z"/>
        <path d="M12 12 20 7.5"/>
        <path d="M12 12 4 7.5"/>
        <path d="M12 12v9"/>
        <path d="M8.4 16.1c1.2-1.3 1.7-2.8 1.6-4.6-.1-1.7.7-2.9 2.1-3.6 1.5-.7 2.9-.3 3.7.8"/>
        <circle cx="8.4" cy="16.1" r="0.85"/>
        <circle cx="15.8" cy="8.7" r="0.85"/>
      </svg>);
    }
    if (icon === 'info') {
        return (<svg {...commonProps} aria-hidden="true">
        <rect x="4" y="4" width="6" height="6" rx="1.2"/>
        <rect x="14" y="4" width="6" height="6" rx="1.2"/>
        <rect x="4" y="14" width="6" height="6" rx="1.2"/>
        <rect x="14" y="14" width="6" height="6" rx="1.2"/>
      </svg>);
    }
    if (icon === 'toolbox') {
        return (<svg {...commonProps} aria-hidden="true">
        <path d="M14.7 6.3a4 4 0 0 0-5.66 5.66L3.4 17.6a2 2 0 1 0 2.83 2.83l5.64-5.64a4 4 0 0 0 5.66-5.66l-2.83 2.83-2.83-2.83 2.83-2.83z"/>
      </svg>);
    }
    return (<svg {...commonProps} aria-hidden="true">
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>);
}

function DemoShellNavItem({ item, activeView, onNavigate, }: {
    item: DemoNavItem;
    activeView: DemoNavView;
    onNavigate: (view: DemoNavView) => void;
}) {
    const active = item.view === activeView;
    const navigable = Boolean(item.view);
    return (<button type="button" className={`wlv-demo-nav-item ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined} onClick={() => {
            if (item.view)
                onNavigate(item.view);
        }} disabled={!navigable} title={item.view === 'data' ? 'Open Managed Well Inventory' : item.view === 'sources' ? 'Open Source Intake' : item.view === 'knowledge' ? 'Open Knowledge Repository' : item.view === 'info' ? 'Open Info' : item.label}>
      <span className="wlv-demo-nav-icon" aria-hidden="true"><DemoRailIcon icon={item.icon}/></span>
      <span className="wlv-demo-nav-label">{item.label}</span>
    </button>);
}

function DemoShellRail({ activeView, onNavigate, }: {
    activeView: DemoNavView;
    onNavigate: (view: DemoNavView) => void;
}) {
    const topItems: DemoNavItem[] = [
        { label: 'Log Viewer', icon: 'log-viewer', view: 'log-viewer' },
        { label: '3D Wellbore', icon: 'wellbore-3d', view: 'wellbore-3d' },
        { label: 'Info', icon: 'info', view: 'info' },
        { label: 'Data', icon: 'data', view: 'data' },
        { label: 'Sources', icon: 'sources', view: 'sources' },
    ];
    const bottomItems: DemoNavItem[] = [
        { label: 'Knowledge', icon: 'knowledge', view: 'knowledge' },
        { label: 'Toolbox', icon: 'toolbox' },
        { label: 'Settings', icon: 'settings' },
    ];
    return (<aside className="wlv-demo-left-rail" aria-label="Well Log Viewer navigation">
      <div className="wlv-demo-rail-brand">
        <span>Well Log</span>
        <strong>Viewer</strong>
      </div>

      <div className="wlv-demo-nav-top">
        {topItems.map((item) => (<DemoShellNavItem key={item.label} item={item} activeView={activeView} onNavigate={onNavigate}/>))}
      </div>

      <div className="wlv-demo-nav-bottom">
        {bottomItems.map((item) => (<DemoShellNavItem key={item.label} item={item} activeView={activeView} onNavigate={onNavigate}/>))}
      </div>
    </aside>);
}

function WmdRecoveryBlockedView({ status, onReturnToData }: { status: WmdDownstreamRecoveryStatus; onReturnToData: () => void }) {
  const action = wmdRecoveryAction(status);
  return (<section className="wlv-prototype-root wlv-wmd-recovery-blocked-view" role="status">
    <header className="wlv-app-header">
      <div className="wlv-app-title">
        <strong>{wmdRecoveryLabel(status)}</strong>
        <span>{status.recovery_message || 'Transient WMD payload is unavailable.'}</span>
      </div>
    </header>
    <div className="wlv-wmd-recovery-blocked-body">
      <p>WDV, WBV, export, and saved-workspace resume are blocked by the backend recovery contract.</p>
      <p>{action === 'rebuild' ? 'Return to Managed Well Data and rebuild the transient payload.' : 'Restore the original unchanged source, then return to Managed Well Data and rebuild.'}</p>
      <button type="button" onClick={onReturnToData}>Open Managed Well Data</button>
    </div>
  </section>);
}

export function TrackLayoutPrototype() {
  const [activeView, setActiveView] = useState<DemoNavView>('log-viewer');
  const [managedViewerWell, setManagedViewerWell] = useState<ManagedWellIdentity | null>(null);
  const [activeRecovery, setActiveRecovery] = useState<WmdDownstreamRecoveryStatus | null>(null);
  const openManagedWellLogViewer = (identity?: ManagedWellIdentity | null) => {
    if (identity) setManagedViewerWell(identity);
    setActiveView('log-viewer');
  };
  const clearManagedWellLogViewer = () => {
    setManagedViewerWell(null);
    setActiveView('log-viewer');
  };
  const managedViewerWellId = managedViewerWell?.managedWellId ?? null;
  useEffect(() => {
    let cancelled = false;
    if (!managedViewerWellId) {
      setActiveRecovery(null);
      return () => { cancelled = true; };
    }
    void fetchWmdDownstreamRecovery(managedViewerWellId)
      .then((status) => { if (!cancelled) setActiveRecovery(status); })
      .catch(() => { if (!cancelled) setActiveRecovery(null); });
    return () => { cancelled = true; };
  }, [managedViewerWellId, activeView]);
  const downstreamBlocked = Boolean(activeRecovery && !activeRecovery.payload_available && (activeView === 'log-viewer' || activeView === 'wellbore-3d'));
  return (<div className="wlv-demo-shell">
        <DemoShellRail activeView={activeView} onNavigate={setActiveView}/>
        <main className="wlv-demo-main" aria-label="Well Log Viewer workspace">
          {downstreamBlocked && activeRecovery ? (<WmdRecoveryBlockedView status={activeRecovery} onReturnToData={() => setActiveView('data')}/>) : activeView === 'data' ? (<ManagedWellInventoryPage onOpenLogViewer={openManagedWellLogViewer} onClearLogViewer={clearManagedWellLogViewer} activeManagedWellId={managedViewerWellId}/>) : activeView === 'info' ? (<section className="wlv-prototype-root">
              <header className="wlv-app-header">
                <div className="wlv-app-title">
                  <strong>Info</strong>
                  <span>Well Log Viewer application information</span>
                </div>
              </header>
            </section>) : activeView === 'knowledge' ? (<div className="wlv-kr-page-shell">
              <KrManagedInstructionsWorkbench />
            </div>) : activeView === 'sources' ? (<SourceIntakeWorkbench />) : activeView === 'wellbore-3d' ? (<Wellbore3DPage onOpenLogViewer={() => setActiveView('log-viewer')}/>) : <WdvPageBoundary managedViewerWell={managedViewerWell} setManagedViewerWell={setManagedViewerWell} onOpenWellbore3D={() => setActiveView("wellbore-3d")}/>}
        </main>
      </div>);
}

export default TrackLayoutPrototype;
