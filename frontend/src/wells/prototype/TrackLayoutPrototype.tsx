import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import * as XLSX from 'xlsx';
import { strToU8, zipSync } from 'fflate';
import { parseManagedCurveSamples, type ManagedCurveSamplesPayload } from './managedCurveSamples';
import '../../styles/track-layout-prototype.css';
import '../../styles/mwd-selection-export-modal.css';
import '../../styles/kr-managed-instructions.css';
import { SourceIntakeWorkbench } from '../source-intake/SourceIntakeWorkbench';
import { KrManagedInstructionsWorkbench } from '../knowledge/KrManagedInstructionsWorkbench';
import { Wellbore3DPage } from '../wbv/Wellbore3DPage';
import { buildInventoryRemovalPayload } from '../identity/inventoryActionIdentity';
import { managedWellIdentityFromActiveWorkspace, type ManagedWellIdentity } from '../identity/managedWellIdentity';
import { fetchWlvJson, wlvApiBaseUrl } from '../wdv/WdvPresentationPrimitives';
import { flushMwdTransientData } from '../inventory/mwdTransientFlushApi';
import { WdvPageBoundary } from '../wdv/WdvPageBoundary';
import { fetchWmdDownstreamRecovery, wmdRecoveryAction, wmdRecoveryLabel, type WmdDownstreamRecoveryStatus } from '../inventory/wmdRecoveryApi';
import ToolboxPage from '../toolbox/ToolboxPage';

type DemoNavView = 'log-viewer' | 'data' | 'sources' | 'knowledge' | 'wellbore-3d' | 'info' | 'toolbox';

const LAST_PRIMARY_VIEW_STORAGE_KEY = 'wlv.shell.lastPrimaryView';
const RESTORABLE_PRIMARY_VIEWS = new Set<DemoNavView>([
  'log-viewer',
  'data',
  'sources',
  'knowledge',
  'wellbore-3d',
  'info',
  'toolbox',
]);

function readLastPrimaryView(): DemoNavView {
  try {
    const stored = window.localStorage.getItem(LAST_PRIMARY_VIEW_STORAGE_KEY);
    if (stored && RESTORABLE_PRIMARY_VIEWS.has(stored as DemoNavView)) {
      return stored as DemoNavView;
    }
  } catch {
    // Browser storage is optional; fall back to the canonical Log Viewer start page.
  }
  return 'log-viewer';
}

function persistLastPrimaryView(view: DemoNavView): void {
  try {
    window.localStorage.setItem(LAST_PRIMARY_VIEW_STORAGE_KEY, view);
  } catch {
    // Navigation remains usable if durable browser storage is unavailable.
  }
}

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
    datum?: string | null;
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



// WME_WELL_INFORMATION_INLINE_EDIT_V1_0_0
const WELL_INFO_SCHEMA_VERSION = '2.0.0';
const WELL_INFO_TEMPLATE_FILENAME_SUFFIX = `Well_Info_Template_V${WELL_INFO_SCHEMA_VERSION.replace(/\./g, '_')}`;
const LEGACY_WELL_INFO_FIELD_KEYS = new Set([
  'latitude_deg', 'longitude_deg', 'northing_m', 'easting_m',
  'rotary_table_elevation_msl_m', 'water_depth_m', 'wellhead_seabed_depth_m',
  'first_md_m', 'final_md_m', 'final_tvd_m', 'maximum_inclination_deg',
  'final_north_offset_m', 'final_east_offset_m',
]);

type WellInfoImportedValue = {
  value: string;
  unit?: string;
  source?: string;
  sourceReference?: string;
  notes?: string;
  authoredBy?: 'user' | 'import';
  userEditedAt?: string;
};

type WellInfoSupplementalMetadata = Record<string, WellInfoImportedValue>;

function mergeWellInfoPreservingUserAuthored(
  current: WellInfoSupplementalMetadata,
  incoming: WellInfoSupplementalMetadata,
): WellInfoSupplementalMetadata {
  const next: WellInfoSupplementalMetadata = { ...current };
  Object.entries(incoming).forEach(([key, value]) => {
    if (current[key]?.authoredBy === 'user') return;
    next[key] = value;
  });
  return next;
}

const WELL_INFO_METADATA_STORAGE_KEY = 'wlv.wellInfo.supplementalMetadataByWell';

function readPersistedWellInfoMetadata(): Record<string, WellInfoSupplementalMetadata> {
  try {
    const durable = window.localStorage.getItem(WELL_INFO_METADATA_STORAGE_KEY);
    if (durable) return JSON.parse(durable) as Record<string, WellInfoSupplementalMetadata>;

    // One-time migration from the former browser-session lifetime store.
    const legacy = window.sessionStorage.getItem(WELL_INFO_METADATA_STORAGE_KEY);
    if (!legacy) return {};
    const migrated = JSON.parse(legacy) as Record<string, WellInfoSupplementalMetadata>;
    window.localStorage.setItem(WELL_INFO_METADATA_STORAGE_KEY, JSON.stringify(migrated));
    window.sessionStorage.removeItem(WELL_INFO_METADATA_STORAGE_KEY);
    return migrated;
  } catch {
    return {};
  }
}

function persistWellInfoMetadata(metadataByWell: Record<string, WellInfoSupplementalMetadata>): void {
  try {
    if (Object.keys(metadataByWell).length === 0) {
      window.localStorage.removeItem(WELL_INFO_METADATA_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(WELL_INFO_METADATA_STORAGE_KEY, JSON.stringify(metadataByWell));
  } catch {
    // WI remains usable if durable browser storage is unavailable.
  }
}

function retainManagedWellMetadata(
  metadataByWell: Record<string, WellInfoSupplementalMetadata>,
  managedWellIds: readonly string[],
): Record<string, WellInfoSupplementalMetadata> {
  const validIds = new Set(managedWellIds);
  return Object.fromEntries(
    Object.entries(metadataByWell).filter(([managedWellId]) => validIds.has(managedWellId)),
  );
}

type WellInfoFieldDefinition = {
  section: string;
  label: string;
  key: string;
  unit?: string;
};

const WELL_INFO_FIELD_DEFINITIONS: WellInfoFieldDefinition[] = [
  { section: 'Identity', label: 'Well Name', key: 'well_name' },
  { section: 'Identity', label: 'Wellbore Name', key: 'wellbore_name' },
  { section: 'Identity', label: 'UWI / Local Identifier', key: 'uwi' },
  { section: 'Identity', label: 'Field', key: 'field' },
  { section: 'Identity', label: 'Site', key: 'site' },
  { section: 'Identity', label: 'Block', key: 'block' },
  { section: 'Identity', label: 'Operator', key: 'operator' },
  { section: 'Identity', label: 'Country', key: 'country' },
  { section: 'Identity', label: 'Well Status', key: 'well_status' },
  { section: 'Position / CRS', label: 'Latitude', key: 'latitude' },
  { section: 'Position / CRS', label: 'Longitude', key: 'longitude' },
  { section: 'Position / CRS', label: 'Northing', key: 'northing', unit: 'm' },
  { section: 'Position / CRS', label: 'Easting', key: 'easting', unit: 'm' },
  { section: 'Position / CRS', label: 'Coordinate System', key: 'coordinate_system' },
  { section: 'Position / CRS', label: 'UTM Zone', key: 'utm_zone' },
  { section: 'Position / CRS', label: 'Geodetic Datum', key: 'geodetic_datum' },
  { section: 'Position / CRS', label: 'EPSG Code', key: 'epsg_code' },
  { section: 'Position / CRS', label: 'North Reference', key: 'north_reference' },
  { section: 'Position / CRS', label: 'Grid Convergence', key: 'grid_convergence', unit: 'deg' },
  { section: 'Depth Reference', label: 'Depth Unit', key: 'depth_unit' },
  { section: 'Depth Reference', label: 'MD / TVD Reference', key: 'depth_reference' },
  { section: 'Depth Reference', label: 'Reference Elevation (relative to MSL)', key: 'reference_elevation', unit: 'm' },
  { section: 'Depth Reference', label: 'Ground / Seabed Elevation (relative to MSL)', key: 'surface_seabed_elevation', unit: 'm' },
  { section: 'Depth Reference', label: 'Water Depth', key: 'water_depth', unit: 'm' },
  { section: 'Depth Reference', label: 'Seabed Depth (below Reference)', key: 'seabed_depth_below_reference', unit: 'm' },
  { section: 'Depth Reference', label: 'Top of Wellhead Depth (below Reference)', key: 'wellhead_depth_below_reference', unit: 'm' },
  { section: 'Well Extent (from Reference)', label: 'Total Depth MD', key: 'total_depth_md', unit: 'm' },
  { section: 'Well Extent (from Reference)', label: 'Total Depth TVD', key: 'total_depth_tvd', unit: 'm' },
  { section: 'Survey Extent (from Reference)', label: 'Survey Start MD', key: 'survey_start_md', unit: 'm' },
  { section: 'Survey Extent (from Reference)', label: 'Survey End MD', key: 'survey_end_md', unit: 'm' },
  { section: 'Survey Extent (from Reference)', label: 'Survey Start TVD', key: 'survey_start_tvd', unit: 'm' },
  { section: 'Survey Extent (from Reference)', label: 'Survey End TVD', key: 'survey_end_tvd', unit: 'm' },
  { section: 'Data Coverage (from Reference)', label: 'Data Start MD', key: 'data_start_md', unit: 'm' },
  { section: 'Data Coverage (from Reference)', label: 'Data End MD', key: 'data_end_md', unit: 'm' },
  { section: 'Trajectory Summary', label: 'Trajectory Source', key: 'trajectory_source' },
  { section: 'Trajectory Summary', label: 'Survey Status', key: 'survey_status' },
  { section: 'Trajectory Summary', label: 'Survey Type', key: 'survey_type' },
  { section: 'Trajectory Summary', label: 'Calculation Method', key: 'calculation_method' },
  { section: 'Trajectory Summary', label: 'Station Count', key: 'station_count' },
  { section: 'Trajectory Summary', label: 'Maximum Inclination', key: 'maximum_inclination', unit: 'deg' },
  { section: 'Trajectory Summary', label: 'Final North Offset', key: 'final_north_offset', unit: 'm' },
  { section: 'Trajectory Summary', label: 'Final East Offset', key: 'final_east_offset', unit: 'm' },
];

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


type MwdExportProfile = 'multiviewer_roundtrip' | 'third_party_interchange';

type MwdExportDialogState = {
    wellId: string;
    profile: MwdExportProfile;
    includeSourceReferences: boolean;
};

function safeExportName(value: string): string {
    return value.trim().replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'managed-well';
}

function csvCell(value: unknown): string {
    if (value === null || value === undefined)
        return '';
    const rendered = typeof value === 'string' ? value : JSON.stringify(value);
    return /[",\n\r]/.test(rendered) ? `"${rendered.replace(/"/g, '""')}"` : rendered;
}

function recordsToCsv(records: readonly Record<string, unknown>[]): string {
    const headers = [...new Set(records.flatMap((record) => Object.keys(record)))];
    if (headers.length === 0)
        return '';
    return [
        headers.map(csvCell).join(','),
        ...records.map((record) => headers.map((header) => csvCell(record[header])).join(',')),
    ].join('\n');
}

function downloadBytes(filename: string, bytes: Uint8Array, mediaType: string): void {
    const ownedBytes = Uint8Array.from(bytes);
    const blob = new Blob([ownedBytes.buffer], { type: mediaType });
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
}

function productItemsForWell(well: ManagedInventoryWellRecord): ManagedProductGroupItem[] {
    return (well.product_groups ?? []).flatMap((group) => group.items ?? []);
}

function embeddedProductRecords(well: ManagedInventoryWellRecord, item: ManagedProductGroupItem): Record<string, unknown>[] {
    const metadata = (well.metadata ?? {}) as Record<string, unknown>;
    const subgroup = (item.product_subgroup_key ?? '').toLowerCase();
    const category = (item.product_category ?? '').toLowerCase();
    const candidates: unknown[] = [];
    if (subgroup.includes('formation') || category.includes('formation')) {
        const dataset = metadata.formation_tops_dataset as Record<string, unknown> | undefined;
        candidates.push(dataset?.tops, metadata.formation_tops, metadata.tops);
    }
    if (subgroup.includes('litholog') || category.includes('litholog')) {
        const dataset = metadata.lithology_intervals_dataset as Record<string, unknown> | undefined;
        candidates.push(dataset?.intervals, metadata.lithology_intervals, metadata.lithology);
    }
    if (subgroup.includes('completion')) {
        const dataset = metadata.completion_components_dataset as Record<string, unknown> | undefined;
        candidates.push(dataset?.completion_components, dataset?.components, metadata.completion_components);
    }
    if (subgroup.includes('deviation') || category.includes('trajectory') || item.trajectory_id)
        candidates.push(metadata.deviation_survey, metadata.trajectory_stations, metadata.survey_stations);
    for (const candidate of candidates) {
        if (Array.isArray(candidate))
            return candidate.filter((value): value is Record<string, unknown> => Boolean(value) && typeof value === 'object');
    }
    return [];
}

function preferredImportRoute(item: ManagedProductGroupItem): string {
    const discriminator = `${item.product_subgroup_key ?? ''} ${item.product_category ?? ''} ${item.display_name ?? ''}`.toLowerCase();
    if (discriminator.includes('formation top')) return 'FTM';
    if (discriminator.includes('litholog')) return 'LCM';
    if (discriminator.includes('completion')) return 'CDM';
    if (discriminator.includes('deviation') || discriminator.includes('trajectory')) return 'DSM';
    if (discriminator.includes('well info') || discriminator.includes('metadata')) return 'Well Info';
    return 'WSI';
}

function isDeviationSurveyExportItem(item: ManagedProductGroupItem): boolean {
    const discriminator = [
        item.product_category,
        item.product_subgroup_key,
        item.product_subgroup_label,
        item.curve_type,
        item.curve_family,
        item.display_name,
    ].filter(Boolean).join(' ').toLowerCase();
    return discriminator.includes('deviation_survey')
        || discriminator.includes('deviation survey')
        || discriminator.includes('directional survey')
        || discriminator.includes('trajectory');
}

async function fetchManagedProductSource(
    managedWellId: string,
    productId: string,
): Promise<{ bytes: Uint8Array; filename: string; mediaType: string }> {
    const response = await fetch(
        `${wlvApiBaseUrl()}/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}/products/${encodeURIComponent(productId)}/source-file`,
    );
    if (!response.ok) {
        let message = `${response.status} ${response.statusText}`;
        try {
            const detail = await response.json() as { detail?: string };
            if (detail.detail)
                message = detail.detail;
        } catch {
            // Preserve HTTP status text when the response is not JSON.
        }
        throw new Error(message);
    }
    const disposition = response.headers.get('content-disposition') ?? '';
    const filenameMatch = /filename="?([^";]+)"?/i.exec(disposition);
    const filename = filenameMatch?.[1] || 'deviation_survey.csv';
    const mediaType = response.headers.get('content-type') || 'application/octet-stream';
    if (mediaType.toLowerCase().includes('text/html'))
        throw new Error('Deviation survey export received the frontend HTML shell instead of the backend source file.');
    const bytes = new Uint8Array(await response.arrayBuffer());
    return {
        bytes,
        filename,
        mediaType,
    };
}

function isStructuredDatasetExportItem(item: ManagedProductGroupItem): boolean {
    const discriminator = [
        item.product_category,
        item.product_subgroup_key,
        item.product_subgroup_label,
        item.source_kind,
        item.display_name,
    ].filter(Boolean).join(' ').toLowerCase();

    return discriminator.includes('formation_tops')
        || discriminator.includes('formation tops')
        || discriminator.includes('stratigraphic_marker')
        || discriminator.includes('stratigraphic marker')
        || discriminator.includes('lithology_intervals')
        || discriminator.includes('lithology intervals')
        || discriminator.includes('lithology')
        || discriminator.includes('completion_components')
        || discriminator.includes('completion components')
        || discriminator.includes('completion data');
}

function isCurveExportItem(item: ManagedProductGroupItem): boolean {
    // MWD MANAGED PRODUCT EXPORT ROUTING V1.0.0:
    // Generic curve_name / curve_type / curve_family values are descriptive
    // metadata and must not route structured products through curve-samples.
    if (isDeviationSurveyExportItem(item) || isStructuredDatasetExportItem(item))
        return false;

    const discriminator = [
        item.product_category,
        item.product_subgroup_key,
        item.product_subgroup_label,
        item.source_kind,
    ].filter(Boolean).join(' ').toLowerCase();

    return Boolean(item.managed_curve_uid)
        || discriminator.includes('managed_curve')
        || discriminator.includes('managed curve')
        || discriminator.includes('curve_dataset')
        || discriminator.includes('curve dataset')
        || discriminator === 'curve'
        || discriminator.startsWith('curve ');
}

function lasText(well: ManagedInventoryWellRecord, item: ManagedProductGroupItem, payload: ManagedCurveSamplesPayload, samples: readonly { depth: number; value: number }[]): string {
    const mnemonic = (payload.normalized_mnemonic || payload.observed_mnemonic || item.curve_name || item.display_name || 'CURVE').trim();
    const depthUnit = (payload.depth_unit || well.depth_unit || 'm').trim();
    const valueUnit = (payload.value_unit || '').trim();
    const startDepth = samples[0]?.depth ?? 0;
    const stopDepth = samples[samples.length - 1]?.depth ?? startDepth;
    const steps = samples.slice(1).map((sample, index) => sample.depth - samples[index].depth).filter((step) => Number.isFinite(step) && step !== 0);
    const step = steps.length ? steps[Math.floor(steps.length / 2)] : 0;
    return ['~Version Information','VERS. 2.0 : CWLS LOG ASCII STANDARD','WRAP. NO : ONE LINE PER DEPTH STEP','~Well Information',`STRT.${depthUnit} ${startDepth} : START DEPTH`,`STOP.${depthUnit} ${stopDepth} : STOP DEPTH`,`STEP.${depthUnit} ${step} : STEP`,'NULL. -999.25 : NULL VALUE',`WELL. ${wellDisplayName(well)} : WELL`,`UWI. ${well.uwi ?? ''} : UNIQUE WELL IDENTIFIER`,'~Curve Information',`DEPT.${depthUnit} : DEPTH`,`${mnemonic}.${valueUnit} : ${item.display_name || item.curve_name || mnemonic}`,'~ASCII',...samples.map((sample) => `${sample.depth} ${sample.value}`),''].join('\n');
}

async function buildSelectedMwdExport(well: ManagedInventoryWellRecord, selectedItems: readonly ManagedProductGroupItem[], profile: MwdExportProfile, includeSourceReferences: boolean): Promise<void> {
    const exportedAt = new Date().toISOString();
    const wellFolder = safeExportName(wellDisplayName(well));
    const files: Record<string, Uint8Array> = {};
    const addText = (path: string, content: string) => { files[path] = strToU8(content); };
    const warnings: string[] = [];
    const items: Array<Record<string, unknown>> = [];

    const exportPath = (item: ManagedProductGroupItem, filename: string): string => {
        if (profile === 'third_party_interchange')
            return `${wellFolder}_${filename}`;
        const productGroup = safeExportName(item.product_subgroup_key || item.product_category || 'managed_product');
        return `${wellFolder}_${productGroup}_${filename}`;
    };

    for (const item of selectedItems) {
        const name = safeExportName(item.display_name || item.curve_name || item.product_id);
        const exportFiles: Array<Record<string, unknown>> = [];

        if (isDeviationSurveyExportItem(item)) {
            const source = await fetchManagedProductSource(well.managed_well_id, item.product_id);
            const sourceName = source.filename.toLowerCase().endsWith('.csv') ? `${name}.csv` : source.filename;
            const sourcePath = exportPath(item, sourceName);
            files[sourcePath] = source.bytes;
            exportFiles.push({
                path: sourcePath,
                role: profile === 'multiviewer_roundtrip' ? 'editable_derivative' : 'primary_transfer',
                format: source.filename.split('.').pop()?.toLowerCase() || 'binary',
            });

            if (profile === 'multiviewer_roundtrip') {
                const metadataPath = exportPath(item, `${name}.metadata.json`);
                addText(metadataPath, JSON.stringify({
                    schema: 'multiviewer.mwd.deviation-survey-export.v1',
                    managed_well_id: well.managed_well_id,
                    managed_product_uid: item.managed_product_uid ?? item.product_id,
                    product_id: item.product_id,
                    product: item,
                    preferred_import_route: 'DSM',
                    fallback_import_route: 'WSI',
                    exported_at: exportedAt,
                    source_filename: source.filename,
                }, null, 2));
                exportFiles.push({ path: metadataPath, role: 'metadata', format: 'json' });
            }
        } else if (isCurveExportItem(item)) {
            const samplesUrl = `/api/wlv/inventory/wells/${encodeURIComponent(well.managed_well_id)}/curve-samples?product_id=${encodeURIComponent(item.product_id)}&max_samples=100000`;
            const payload = await fetchWlvJson<ManagedCurveSamplesPayload>(samplesUrl);
            const samples = parseManagedCurveSamples(payload);
            if (!samples.length)
                throw new Error(`No usable samples were returned for ${item.display_name || item.curve_name || item.product_id} (well ${well.managed_well_id}, product ${item.product_id}).`);

            const lasPath = exportPath(item, `${name}.las`);
            const csvPath = exportPath(item, `${name}.csv`);
            addText(lasPath, lasText(well, item, payload, samples));
            addText(csvPath, recordsToCsv(samples.map((sample) => ({ depth: sample.depth, value: sample.value }))));
            exportFiles.push(
                { path: lasPath, role: 'primary_transfer', format: 'las' },
                { path: csvPath, role: 'editable_derivative', format: 'csv' },
            );

            if (profile === 'multiviewer_roundtrip') {
                const metadataPath = exportPath(item, `${name}.metadata.json`);
                addText(metadataPath, JSON.stringify({
                    schema: 'multiviewer.mwd.curve-export.v1',
                    managed_well_id: well.managed_well_id,
                    managed_well_uid: well.managed_well_uid,
                    managed_product_uid: item.managed_product_uid ?? item.product_id,
                    managed_curve_uid: item.managed_curve_uid,
                    product: item,
                    curve_contract: { ...payload, samples: undefined },
                    sample_count_exported: samples.length,
                    preferred_import_route: 'WSI',
                    exported_at: exportedAt,
                }, null, 2));
                exportFiles.push({ path: metadataPath, role: 'metadata', format: 'json' });
            }
        } else {
            const records = embeddedProductRecords(well, item);
            if (records.length) {
                const csvPath = exportPath(item, `${name}.csv`);
                addText(csvPath, recordsToCsv(records));
                exportFiles.push({ path: csvPath, role: 'editable_derivative', format: 'csv' });
            } else {
                warnings.push(`${item.display_name || item.curve_name || item.product_id}: no exportable data payload exposed.`);
            }

            if (profile === 'multiviewer_roundtrip') {
                const metadataPath = exportPath(item, `${name}.metadata.json`);
                addText(metadataPath, JSON.stringify({
                    schema: 'multiviewer.mwd.product-snapshot.v1',
                    managed_well_id: well.managed_well_id,
                    managed_product_uid: item.managed_product_uid ?? item.product_id,
                    product: item,
                    preferred_import_route: preferredImportRoute(item),
                    fallback_import_route: 'WSI',
                    exported_at: exportedAt,
                }, null, 2));
                exportFiles.push({ path: metadataPath, role: 'metadata', format: 'json' });
            }
        }

        items.push({
            managed_product_uid: item.managed_product_uid ?? item.product_id,
            product_id: item.product_id,
            managed_well_id: well.managed_well_id,
            display_name: item.display_name ?? item.curve_name ?? item.product_id,
            product_type: item.product_category ?? 'managed_product',
            product_subtype: item.product_subgroup_key ?? null,
            export_files: exportFiles,
        });
    }

    const sourceReferences = includeSourceReferences
        ? (well.source_references ?? []).filter((source) => selectedItems.some((item) => !item.source_id || item.source_id === source.source_id))
        : [];
    const wellIdentity = {
        managed_well_id: well.managed_well_id,
        managed_well_uid: well.managed_well_uid ?? null,
        well_id: well.well_id,
        well_name: well.well_name ?? well.display_name ?? well.well_id,
        wellbore_id: well.wellbore_id ?? null,
        uwi: well.uwi ?? null,
        depth_unit: well.depth_unit ?? null,
    };
    const allSelectableItems = productItemsForWell(well).filter((item) => item.selectable !== false);
    const selection = {
        selection_mode: selectedItems.length === allSelectableItems.length ? 'well' : 'item',
        selected_well_ids: [well.managed_well_id],
        selected_item_ids: selectedItems.map((item) => item.product_id),
        all_items_selected: selectedItems.length === allSelectableItems.length,
    };

    if (profile === 'multiviewer_roundtrip') {
        const manifest = {
            schema: 'multiviewer.mwd.export.v1',
            export_profile: profile,
            exported_at: exportedAt,
            selection,
            wells: [wellIdentity],
            items,
            source_references: sourceReferences,
            warnings,
        };
        addText('manifest.json', JSON.stringify(manifest, null, 2));
        addText('well_snapshot.json', JSON.stringify({
            schema: 'multiviewer.mwd.well-snapshot.v1',
            exported_at: exportedAt,
            managed_well: wellIdentity,
            selected_products: selectedItems.map((item) => ({
                product_id: item.product_id,
                managed_product_uid: item.managed_product_uid ?? item.product_id,
                managed_curve_uid: item.managed_curve_uid ?? null,
                display_name: item.display_name ?? item.curve_name ?? item.product_id,
                product_category: item.product_category ?? null,
                product_subgroup_key: item.product_subgroup_key ?? null,
            })),
            source_references: sourceReferences,
        }, null, 2));
        addText('selection_snapshot.json', JSON.stringify(selection, null, 2));
        addText('README.txt', [
            'MultiViewer Managed Well Data round-trip export',
            '',
            `Well: ${wellDisplayName(well)}`,
            `Selected products: ${selectedItems.length}`,
            '',
            'This package is intended for editing and re-import through the appropriate Toolbox module or WSI.',
            'Export does not change or archive MWD data.',
            '',
            ...warnings.map((warning) => `WARNING: ${warning}`),
        ].join('\n'));
    } else {
        if (includeSourceReferences && sourceReferences.length > 0)
            addText('source_references.json', JSON.stringify(sourceReferences, null, 2));
        addText('README.txt', [
            'MultiViewer third-party interchange export',
            '',
            `Well: ${wellDisplayName(well)}`,
            `Selected products: ${selectedItems.length}`,
            '',
            'This package contains only selected transferable and editable data files.',
            'MultiViewer round-trip snapshots and lifecycle metadata are intentionally excluded.',
            '',
            ...warnings.map((warning) => `WARNING: ${warning}`),
        ].join('\n'));
    }

    const archive = zipSync(files, { level: 6 });
    const suffix = profile === 'multiviewer_roundtrip' ? 'MWD_ROUNDTRIP' : 'INTERCHANGE';
    downloadBytes(`${wellFolder}_${suffix}_${exportedAt.replace(/[:.]/g, '-')}.zip`, archive, 'application/zip');
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
            curve_type: statusLabel(record.trajectory_type || 'Wellbore trajectory'),
            curve_family: 'Wellbore Geometry',
            product_category: 'wellbore_geometry',
            product_subgroup_key: record.trajectory_type || 'trajectory',
            product_subgroup_label: statusLabel(record.trajectory_type || 'Trajectory'),
            classification_confidence: record.wbv_eligible ? 'high' : 'review',
            run_date: '—',
            run_interval: optionalDepthRangeLabel(record.md_min, record.md_max, well.depth_unit || 'ft'),
            run_number: String(record.station_count ?? '—'),
            qa_flag: record.source_label === 'DSM CSV' ? 'Reviewed' : (record.status ? statusLabel(record.status) : 'Unknown'),
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
            datum: 'RKB',
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
    const completionItems: ManagedProductGroupItem[] = [];
    const groups: ManagedProductGroup[] = (well.product_groups ?? []).map((group): ManagedProductGroup => {
        const retainedItems = (group.items ?? []).filter((item) => {
            const isCompletion = item.product_subgroup_key === 'completion_components'
                || item.product_subgroup_label === 'Completion Components';
            if (isCompletion) completionItems.push(item);
            return !isCompletion;
        });
        return { ...group, items: retainedItems };
    });
    if (completionItems.length > 0) {
        groups.push({
            group_key: 'completion_data',
            group_label: 'Completion Data',
            collapsed_by_default: false,
            items: completionItems,
        });
    }
    const metadataGeometryGroup = wmdpWellboreGeometryGroup(well);
    const existingIndex = groups.findIndex((group) => group.group_key === 'wellbore_geometry');

    if (existingIndex < 0) {
        groups.push(metadataGeometryGroup);
        return groups;
    }

    const backendGeometryGroup = groups[existingIndex];
    const mergedItems = [...(backendGeometryGroup.items ?? [])];
    const existingIds = new Set(mergedItems.map((item) => item.product_id));

    for (const item of metadataGeometryGroup.items ?? []) {
        const existingItemIndex = mergedItems.findIndex((candidate) => candidate.product_id === item.product_id);
        if (existingItemIndex >= 0) {
            mergedItems[existingItemIndex] = { ...mergedItems[existingItemIndex], ...item };
        } else {
            mergedItems.push(item);
            existingIds.add(item.product_id);
        }
    }

    groups[existingIndex] = {
        ...backendGeometryGroup,
        group_key: 'wellbore_geometry',
        group_label: 'Wellbore Geometry',
        collapsed_by_default: backendGeometryGroup.collapsed_by_default
            ?? metadataGeometryGroup.collapsed_by_default,
        items: mergedItems,
    };

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

type WmdpBulkAction = 'load' | 'unload' | 'remove' | 'info';

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

function compactDepthReference(
    value: string | number | null | undefined,
) {
    const text = safeText(value);
    if (text === '—') {
        return text;
    }
    return text
        .replace(/\s*;\s*/g, ' · ')
        .replace(/\bTVDSS\s+m\s+MSL\b/gi, 'TVDSS MSL')
        .replace(/\bTVD\s+m\s+RT\b/gi, 'TVD RT')
        .replace(/\bMD\s+m\s+RT\b/gi, 'MD RT')
        .replace(/\s{2,}/g, ' ')
        .trim();
}

function normalizedCoreImageFileName(item: ManagedProductGroupItem): string {
    const explicit = safeText(item.display_name);
    const genericName = safeText(item.curve_name);
    if (explicit !== '—' && explicit !== genericName && explicit.toLowerCase() !== 'core image') {
        return explicit;
    }
    const productIdText = safeText(item.product_id, '');
    const wellMatch = productIdText.match(/^cim-core-package:([^:]+):/);
    const intervalText = safeText(item.run_interval, '');
    const intervalMatch = intervalText.match(/([0-9]+(?:\.[0-9]+)?)\s*[–-]\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)/);
    if (wellMatch && intervalMatch) {
        const normalizeDepth = (value: string) => value.replace(/\.0+$/, '').replace(/(\.[1-9]*)0+$/, '$1');
        const wellId = wellMatch[1];
        const top = normalizeDepth(intervalMatch[1]);
        const base = normalizeDepth(intervalMatch[2]);
        const unit = intervalMatch[3];
        return `${wellId}_Cont_Core_${top}-${base}${unit}`;
    }
    return explicit !== '—' ? explicit : genericName || 'Core Image';
}

function coreImageDescription(): string {
    return 'Continuous core from segments';
}

function coreImageSourceLabel(item: ManagedProductGroupItem): string {
    const text = safeText(item.source_label || item.source_id);
    if (text === '—') {
        return 'Core Image Manager';
    }
    if (text === 'core-image-manager') {
        return 'Core Image Manager';
    }
    return text;
}

function coreImageDepthReference(item: ManagedProductGroupItem): string {
    const explicit = compactDepthReference(item.depth_reference as string | number | null | undefined);
    return explicit === '—' ? 'MD' : explicit;
}

function completionDataDescription(): string {
    return 'Reviewed visualization-focused completion landmarks and intervals';
}

function completionDataSourceLabel(item: ManagedProductGroupItem): string {
    const text = safeText(item.source_label || item.source_id);
    if (text === '—' || text === 'completion-data-manager') {
        return 'Completion Data Manager';
    }
    return text;
}

function completionDataDepthReference(): string {
    // CDM v1 contract is explicitly measured-depth based.
    return 'MD';
}

function markerProductDescription(
    isFormationTops: boolean,
    isLithologyIntervals: boolean,
): string {
    if (isFormationTops) {
        return 'Stratigraphic formation-top picks and measured-depth markers';
    }
    if (isLithologyIntervals) {
        return 'Interpreted lithological column with depth-bounded rock-type intervals';
    }
    return '—';
}

function markerProductSource(
    isFormationTops: boolean,
    isLithologyIntervals: boolean,
): string {
    if (isFormationTops) {
        return 'Formation Tops Manager';
    }
    if (isLithologyIntervals) {
        return 'Lithology Column Manager';
    }
    return '—';
}

function expandableProductName(value: string, maxLength = 64) {
    const text = safeText(value);
    if (text.length <= maxLength) {
        return <>{text}</>;
    }
    return (<details className="wlv-wmdp-product-name-details">
      <summary title={text}>{text.slice(0, maxLength - 1)}…</summary>
      <span>{text}</span>
    </details>);
}


function expandableGeometryName(value: string, maxLength = 32) {
    const text = safeText(value);
    if (text.length <= maxLength) {
        return <>{text}</>;
    }
    return (<details className="wlv-wmdp-geometry-inline-name-details">
      <summary title={text}>
        <span className="wlv-wmdp-geometry-inline-name-collapsed">{text.slice(0, maxLength - 1)}…</span>
        <span className="wlv-wmdp-geometry-inline-name-expanded">{text}</span>
      </summary>
    </details>);
}

function WmdpGeometryColumnHeaders() {
    return (<div className="wlv-wmdp-geometry-column-header" role="row" aria-label="Deviation survey metadata columns">
      <span className="wlv-wmdp-geometry-column-header-checkbox" aria-hidden="true"/>
      <span className="wlv-wmdp-product-item-summary wlv-wmdp-product-item-summary-geometry wlv-wmdp-geometry-column-header-grid">
        <span>Name</span>
        <span>Status</span>
        <span>Type</span>
        <span>Active</span>
        <span>MD Range</span>
        <span>Stations</span>
        <span>Datum</span>
        <span>Source</span>
        <span>Action</span>
      </span>
    </div>);
}

function WmdpProductItemRow({ item, selected, onToggle, managedWellId, onSetActiveTrajectory, trajectoryApplyingId, }: {
    item: ManagedProductGroupItem;
    selected: boolean;
    onToggle: () => void;
    managedWellId?: string;
    onSetActiveTrajectory?: (managedWellId: string, trajectoryId: string) => void;
    trajectoryApplyingId?: string | null;
}) {
    const isCompletionComponents = item.product_subgroup_key === 'completion_components'
        || item.product_subgroup_label === 'Completion Components';
    const isGeometry = !isCompletionComponents
        && (item.product_category === 'wellbore_geometry' || item.source_kind === 'wellbore_geometry');
    const isFormationTops = item.product_subgroup_key === 'formation_tops' || item.display_layer_type === 'formation_tops_dataset';
    const isLithologyIntervals = item.product_subgroup_key === 'lithology_intervals';
    // MWD-CORE-IMAGE-DISPLAY-REPAIR-V1-0-2
    const isCoreImage = item.product_subgroup_key === 'compound_core_segment' || item.display_layer_type === 'compound_core_segment' || safeText(item.curve_name) === 'Core Image' || safeText(item.curve_type) === 'Continuous core from segments';
    const isStructuredMarkerRow = isFormationTops || isLithologyIntervals || isCoreImage || isCompletionComponents;
    const trajectoryReference = item.managed_trajectory_uid || item.trajectory_id;
    const canSetActive = Boolean(isGeometry
        && managedWellId
        && trajectoryReference
        && item.wbv_eligible
        && !item.is_active_trajectory);
    const applying = Boolean(trajectoryReference
        && trajectoryApplyingId === trajectoryReference);
    // WLV-MWD-GEOMETRY-ROW-TRUNCATE-REMOVE-STATUS-FIX-V2\n    // WLV-MWD-GEOMETRY-ROW-EXACT-GRID-FIX:
    // Geometry uses a dedicated semantic grid instead of the generic product row.
    return (<label className={isGeometry ? 'wlv-wmdp-product-item wlv-wmdp-product-item-geometry' : 'wlv-wmdp-product-item'} key={item.product_id}>
      <input type="checkbox" checked={selected} disabled={item.selectable === false} onChange={onToggle} aria-label={`Select ${productItemDisplayName(item)}`}/>
      <span
        className={isGeometry
          ? 'wlv-wmdp-product-item-summary wlv-wmdp-product-item-summary-geometry'
          : isFormationTops
            ? 'wlv-wmdp-product-item-summary wlv-wmdp-product-item-summary-marker-standard wlv-wmdp-product-item-summary-formation-tops'
            : isLithologyIntervals
              ? 'wlv-wmdp-product-item-summary wlv-wmdp-product-item-summary-marker-standard wlv-wmdp-product-item-summary-lithology-intervals'
              : isCoreImage || isCompletionComponents
                ? 'wlv-wmdp-product-item-summary wlv-wmdp-product-item-summary-marker-standard'
                : 'wlv-wmdp-product-item-summary'}
      >
        {isGeometry ? (<>
            <span className="wlv-wmdp-geometry-name" title={safeText(item.display_name)}>
              <strong className="wlv-wmdp-product-item-code">{expandableGeometryName(productItemDisplayName(item), 32)}</strong>
            </span>
            <span className="wlv-wmdp-geometry-status" title={safeText(item.qa_flag)}>{statusLabel(item.qa_flag)}</span>
            <span className="wlv-wmdp-geometry-type" title={safeText(item.curve_type)}>{statusLabel(item.curve_type)}</span>
            <span className="wlv-wmdp-geometry-active-state">{item.is_active_trajectory ? 'Yes' : 'No'}</span>
            <span className="wlv-wmdp-geometry-md-range" title={safeText(item.run_interval)}>{safeText(item.run_interval)}</span>
            <span className="wlv-wmdp-geometry-stations" title={safeText(item.station_count)}>{safeText(item.station_count)}</span>
            <span className="wlv-wmdp-geometry-datum" title={safeText(item.datum)}>{safeText(item.datum)}</span>
            <span className="wlv-wmdp-geometry-source" title={safeText(item.source_label)}>{safeText(item.source_label)}</span>
            <span className="wlv-wmdp-geometry-active">
              {item.is_active_trajectory ? (<strong>Active</strong>) : canSetActive ? (<button type="button" className="wlv-wmdp-product-item-action" disabled={applying} onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (managedWellId && trajectoryReference && onSetActiveTrajectory) onSetActiveTrajectory(managedWellId, trajectoryReference);
                }}>{applying ? 'Making active…' : 'Make active'}</button>) : (<span>—</span>)}
            </span>
          </>) : isStructuredMarkerRow ? (<>
            <span
              className="wlv-wmdp-product-item-code-wrap"
              title={productItemClassificationTitle(item)}
            >
              <strong className="wlv-wmdp-product-item-code">
                {expandableProductName(productItemDisplayName(item))}
              </strong>
            </span>
            <span
              className="wlv-wmdp-product-item-description"
              title={isCompletionComponents ? completionDataDescription() : isCoreImage ? coreImageDescription() : markerProductDescription(isFormationTops, isLithologyIntervals)}
            >
              <strong>Description:</strong>{' '}
              {isCompletionComponents ? completionDataDescription() : isCoreImage ? coreImageDescription() : markerProductDescription(isFormationTops, isLithologyIntervals)}
            </span>
            <span
              className={`wlv-wmdp-product-item-name${isCompletionComponents ? ' wlv-wmdp-completion-components-cell' : ''}`}
              title={isCompletionComponents ? safeText(item.run_number) : isCoreImage ? normalizedCoreImageFileName(item) : safeText(item.display_name || productItemDisplayName(item))}
            >
              <strong>{isCompletionComponents ? 'Components:' : 'File Name:'}</strong>{' '}
              {isCompletionComponents
                ? safeText(item.run_number)
                : expandableProductName(isCoreImage ? normalizedCoreImageFileName(item) : (item.display_name || productItemDisplayName(item)))}
            </span>
            <span
              className="wlv-wmdp-product-item-run-date"
              title={safeText(item.run_interval)}
            >
              <strong>MD Range:</strong> {safeText(item.run_interval)}
            </span>
            <span
              className="wlv-wmdp-product-item-run-interval"
              title={safeText(item.depth_reference)}
            >
              <strong>Depth Reference:</strong>{' '}
              {isCompletionComponents ? completionDataDepthReference() : isCoreImage ? coreImageDepthReference(item) : compactDepthReference(item.depth_reference)}
            </span>
            <span
              className="wlv-wmdp-product-item-run-number"
              title={isCompletionComponents ? completionDataSourceLabel(item) : isCoreImage ? coreImageSourceLabel(item) : markerProductSource(isFormationTops, isLithologyIntervals)}
            >
              <strong>Source:</strong>{' '}
              {isCompletionComponents ? completionDataSourceLabel(item) : isCoreImage ? coreImageSourceLabel(item) : markerProductSource(isFormationTops, isLithologyIntervals)}
            </span>
            <span
              className="wlv-wmdp-product-item-qa-flag"
              title={`QA: ${safeText(item.qa_flag)}`}
            >
              <strong>QA:</strong> {safeText(item.qa_flag)}
            </span>
          </>) : (<>
            <span className="wlv-wmdp-product-item-code-wrap" title={productItemClassificationTitle(item)}>
              <strong className="wlv-wmdp-product-item-code">{productItemDisplayName(item)}</strong>
            </span>
            <span className="wlv-wmdp-product-item-description" title={safeText(item.curve_type)}>
              <strong>Description:</strong> {safeText(item.curve_type)}
            </span>
            <span className="wlv-wmdp-product-item-name" title={isCoreImage ? normalizedCoreImageFileName(item) : safeText(item.display_name || productItemDisplayName(item))}>
              <strong>File Name:</strong> {expandableProductName(isCoreImage ? normalizedCoreImageFileName(item) : (item.display_name || productItemDisplayName(item)))}
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

function ManagedWellInventoryPage({ onOpenLogViewer, onOpenInfo, onClearLogViewer, onManagedWellIdsChange, activeManagedWellId }: {
    onOpenLogViewer: (identity?: ManagedWellIdentity | null) => void;
    onOpenInfo: (well: ManagedInventoryWellRecord) => void;
    onClearLogViewer: () => void;
    onManagedWellIdsChange: (managedWellIds: string[]) => void;
    activeManagedWellId: string | null;
}) {
    const [status, setStatus] = useState<ManagedInventoryStatusPayload | null>(null);
    const [wells, setWells] = useState<ManagedInventoryWellRecord[]>([]);
    const [selectedWellId, setSelectedWellId] = useState<string | null>(null);
    const [selectedWellIds, setSelectedWellIds] = useState<Set<string>>(new Set());
    const [expandedWellIds, setExpandedWellIds] = useState<Set<string>>(new Set());
    const [expandedProductGroupIds, setExpandedProductGroupIds] = useState<Set<string>>(new Set());
    const [selectedProductItemIds, setSelectedProductItemIds] = useState<Set<string>>(new Set());
    const [exportDialog, setExportDialog] = useState<MwdExportDialogState | null>(null);
    const [exportInProgress, setExportInProgress] = useState(false);
    const [exportError, setExportError] = useState<string | null>(null);
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
            onManagedWellIdsChange(nextWells.map((well) => well.managed_well_id));
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
        let refreshTimer: number | null = null;

        const requestRefresh = () => {
            if (refreshTimer !== null)
                window.clearTimeout(refreshTimer);
            refreshTimer = window.setTimeout(() => {
                refreshTimer = null;
                void loadInventory();
            }, 80);
        };

        const handleCustomRefresh = () => requestRefresh();
        const handleStorageRefresh = (event: StorageEvent) => {
            if (event.key === 'wlv:mwd-inventory-refresh')
                requestRefresh();
        };

        window.addEventListener('wlv:mwd-inventory-changed', handleCustomRefresh);
        window.addEventListener('storage', handleStorageRefresh);

        let channel: BroadcastChannel | null = null;
        try {
            channel = new BroadcastChannel('wlv:mwd-inventory');
            channel.addEventListener('message', requestRefresh);
        } catch {
            channel = null;
        }

        return () => {
            if (refreshTimer !== null)
                window.clearTimeout(refreshTimer);
            window.removeEventListener('wlv:mwd-inventory-changed', handleCustomRefresh);
            window.removeEventListener('storage', handleStorageRefresh);
            channel?.removeEventListener('message', requestRefresh);
            channel?.close();
        };
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
    const infoSelectionValid = bulkAction !== 'info' || (selectedWellCount === 1 && selectedProductCount === 0);
    const canApplyBulkAction = hasSelection && !bulkApplying && !recoveryBlocksLoad && infoSelectionValid;
    const applyBulkAction = async () => {
        if (!canApplyBulkAction)
            return;
        const productOwnerIds = [...selectedProductWellIds];
        if (bulkAction === 'info') {
            const selectedWell = wells.find((well) => selectedWellIds.has(well.managed_well_id));
            if (!selectedWell) {
                setError('Select exactly one managed well to open Well Information.');
                return;
            }
            onOpenInfo(selectedWell);
            return;
        }
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
    const exportWell = exportDialog ? wells.find((well) => well.managed_well_id === exportDialog.wellId) ?? null : null;
    const exportWellItems = exportWell ? productItemsForWell(exportWell).filter((item) => item.selectable !== false) : [];
    const selectedExportItems = exportWell
        ? (selectedWellIds.has(exportWell.managed_well_id)
            ? exportWellItems
            : exportWellItems.filter((item) => selectedProductItemIds.has(item.product_id)))
        : [];
    const runExport = async () => {
        if (!exportDialog || !exportWell || selectedExportItems.length === 0 || exportInProgress)
            return;
        setExportInProgress(true);
        setExportError(null);
        setError(null);
        try {
            await buildSelectedMwdExport(exportWell, selectedExportItems, exportDialog.profile, exportDialog.includeSourceReferences);
            setExportDialog(null);
        } catch (caught) {
            const message = caught instanceof Error ? caught.message : 'Unable to export selected managed data';
            setExportError(message);
            setError(message);
        } finally {
            setExportInProgress(false);
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
                <option value="info">Open Well Information</option>
                <option value="remove">Remove selected from MWD</option>
              </select>
            </label>
            <button type="button" onClick={applyBulkAction} disabled={!canApplyBulkAction}>{bulkApplying ? (bulkAction === 'remove' ? 'Removing…' : bulkAction === 'unload' ? 'Unloading…' : 'Loading…') : 'Apply'}</button>
            {bulkAction === 'info' && !infoSelectionValid ? <span className="wlv-wmdp-action-hint">Select one well only.</span> : null}
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
                          <button type="button" onClick={() => { setSelectedWellId(well.managed_well_id); onOpenInfo(well); }}>Info</button>
                          <button type="button" onClick={() => { setExportError(null); setExportDialog({ wellId: well.managed_well_id, profile: 'multiviewer_roundtrip', includeSourceReferences: true }); }}>Export</button>
                          <button type="button" onClick={() => { setSelectedWellIds(new Set([well.managed_well_id])); setSelectedProductItemIds(new Set()); setBulkAction('remove'); }}>Archive</button>
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
                                const subgroupedItems = category.group_key === 'completion_data'
                                    ? []
                                    : usesAuthoritativeCurveFamilyContract
                                        ? groupCurveItemsByAuthoritativeGeneralFamily(categoryItems)
                                        : krSubgroups.length > 0
                                            ? groupProductItemsByKrSubgroups(categoryItems, krSubgroups)
                                            : [];
                                return subgroupedItems.length > 0 ? (<div className="wlv-wmdp-product-subgroups">
                                        {category.group_key === 'wellbore_geometry' ? <WmdpGeometryColumnHeaders/> : null}
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
                                      </div>) : category.group_key === 'completion_data' ? (
                                      <div className="wlv-wmdp-product-subgroups">
                                        <section className="wlv-wmdp-product-subgroup">
                                          <div className="wlv-wmdp-product-items">
                                            {categoryItems.length === 0 ? (<div className="wlv-wmdp-product-empty">No registered items.</div>) : categoryItems.map((item) => (<WmdpProductItemRow item={item} key={item.product_id} selected={selectedProductItemIds.has(item.product_id)} onToggle={() => toggleProductItemSelected(item.product_id)} managedWellId={well.managed_well_id} onSetActiveTrajectory={setActiveTrajectory} trajectoryApplyingId={trajectoryApplyingId}/>))}
                                          </div>
                                        </section>
                                      </div>) : (<div className="wlv-wmdp-product-items">
                                        {category.group_key === 'wellbore_geometry' && categoryItems.length > 0 ? <WmdpGeometryColumnHeaders/> : null}
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

      {exportDialog && exportWell ? (
        <div className="wlv-mwd-export-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) { setExportError(null); setExportDialog(null); } }}>
          <section className="wlv-mwd-export-modal" role="dialog" aria-modal="true" aria-labelledby="mwd-export-title">
            <header>
              <div>
                <h3 id="mwd-export-title">Export selected managed data</h3>
                <p>{wellDisplayName(exportWell)} · {selectedExportItems.length} selected item{selectedExportItems.length === 1 ? '' : 's'}</p>
              </div>
              <button type="button" className="wlv-mwd-export-close" aria-label="Close export" onClick={() => { setExportError(null); setExportDialog(null); }}>×</button>
            </header>

            <div className="wlv-mwd-export-body">
              <label>
                <span>Export purpose</span>
                <select value={exportDialog.profile} onChange={(event) => setExportDialog((current) => current ? { ...current, profile: event.target.value as MwdExportProfile } : current)}>
                  <option value="multiviewer_roundtrip">Edit and re-import into MultiViewer</option>
                  <option value="third_party_interchange">Use in another application</option>
                </select>
              </label>

              <label>
                <input type="checkbox" checked={exportDialog.includeSourceReferences} onChange={(event) => setExportDialog((current) => current ? { ...current, includeSourceReferences: event.target.checked } : current)}/>
                <span>Include selected source references and checksums</span>
              </label>

              <div>
                <strong>Included products</strong>
                <ul>{selectedExportItems.map((item) => <li key={item.product_id}>{item.display_name || item.curve_name || item.product_id}</li>)}</ul>
              </div>

              {selectedExportItems.length === 0 ? <p className="is-error">Select one or more items under this well, or select the well to export everything.</p> : null}
              {exportError ? <p className="is-error" role="alert">{exportError}</p> : null}
              <p>The ZIP is saved through the browser to the configured download location. Export does not change or archive MWD data.</p>
            </div>

            <footer>
              <button type="button" onClick={() => { setExportError(null); setExportDialog(null); }}>Cancel</button>
              <button type="button" disabled={selectedExportItems.length === 0 || exportInProgress} onClick={() => void runExport()}>{exportInProgress ? 'Exporting…' : 'Export ZIP'}</button>
            </footer>
          </section>
        </div>
      ) : null}
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
    ];
    const bottomItems: DemoNavItem[] = [
        { label: 'Sources', icon: 'sources', view: 'sources' },
        { label: 'Toolbox', icon: 'toolbox', view: 'toolbox' },
        { label: 'Knowledge', icon: 'knowledge', view: 'knowledge' },
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


type WellInfoFieldProps = {
  fieldKey: string;
  label: string;
  value: string;
  editValue?: string;
  source?: string;
  armed: boolean;
  editing: boolean;
  draftValue: string;
  validationError?: string;
  onArm: (fieldKey: string) => void;
  onBeginEdit: (fieldKey: string, value: string) => void;
  onDraftChange: (value: string) => void;
  onSave: (fieldKey: string, value: string, source: string) => void;
  onCancel: () => void;
};

function WellInfoField({
  fieldKey, label, value, editValue, source = 'Loaded data',
  armed, editing, draftValue, validationError,
  onArm, onBeginEdit, onDraftChange, onSave, onCancel,
}: WellInfoFieldProps) {
  const editableValue = editValue ?? value;
  return (
    <article
      className={['wlv-well-info-field', armed ? 'is-armed' : '', editing ? 'is-editing' : ''].filter(Boolean).join(' ')}
      data-well-info-field={fieldKey}
      onClick={() => { if (!editing) onArm(fieldKey); }}
    >
      <span className="wlv-well-info-field__label">{label}</span>
      <div className="wlv-well-info-field__value-row">
        {editing ? (
          <input
            className="wlv-well-info-field__input"
            value={draftValue}
            autoFocus
            list={fieldKey === 'depth_reference' ? 'wlv-depth-reference-options' : undefined}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                onSave(fieldKey, draftValue, source);
              } else if (event.key === 'Escape') {
                event.preventDefault();
                onCancel();
              }
            }}
          />
        ) : (
          <strong className={value === '—' ? 'is-missing' : ''}>{value}</strong>
        )}
        {armed ? (
          <button
            type="button"
            className="wlv-well-info-field__edit-button"
            onClick={(event) => {
              event.stopPropagation();
              if (editing) onSave(fieldKey, draftValue, source);
              else onBeginEdit(fieldKey, editableValue === '—' ? '' : editableValue);
            }}
          >
            {editing ? 'Save' : 'Edit'}
          </button>
        ) : null}
      </div>
      {validationError ? <span className="wlv-well-info-field__validation">{validationError}</span> : null}
      <small>{source}</small>
    </article>
  );
}

function WellInfoSummaryPanel({ title, rows }: { title: string; rows: Array<{ label: string; value: string }> }) {
  return (<article className="wlv-well-info-summary-panel">
    <h4>{title}</h4>
    <dl>{rows.map((row) => <div key={`${title}-${row.label}`}><dt>{row.label}</dt><dd className={row.value === '—' ? 'is-missing' : ''}>{row.value}</dd></div>)}</dl>
  </article>);
}

function WellInfoPage({ well, supplementalMetadata, onSupplementalMetadataChange, onReturnToData, onSendToWme }: {
  well: ManagedInventoryWellRecord | null;
  supplementalMetadata: WellInfoSupplementalMetadata;
  onSupplementalMetadataChange: (metadata: WellInfoSupplementalMetadata) => void;
  onReturnToData: () => void;
  onSendToWme: (context: { fileName: string; workbookBase64: string }) => void;
}) {
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [transferMessage, setTransferMessage] = useState<string>('');
  const [transferError, setTransferError] = useState<string>('');
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [pendingImportFile, setPendingImportFile] = useState<File | null>(null);
  const [importDragActive, setImportDragActive] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [armedFieldKey, setArmedFieldKey] = useState<string | null>(null);
  const [editingFieldKey, setEditingFieldKey] = useState<string | null>(null);
  const [fieldDraftValue, setFieldDraftValue] = useState('');
  const [fieldValidationError, setFieldValidationError] = useState('');

  useEffect(() => {
    if (!armedFieldKey || editingFieldKey) return;
    const dismiss = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest(`[data-well-info-field="${armedFieldKey}"]`)) return;
      setArmedFieldKey(null);
      setFieldValidationError('');
    };
    document.addEventListener('pointerdown', dismiss, true);
    return () => document.removeEventListener('pointerdown', dismiss, true);
  }, [armedFieldKey, editingFieldKey]);

  if (!well) {
    return (<section className="wlv-well-info-page">
      <header className="wlv-well-info-topbar"><h1>Well Information</h1></header>
      <div className="wlv-well-info-empty">
        <strong>No managed well selected</strong>
        <span>Select a well in Managed Data, then choose Action → Open Well Information.</span>
        <button type="button" onClick={onReturnToData}>Open Managed Data</button>
      </div>
    </section>);
  }

  const imported = (key: string): WellInfoImportedValue | undefined => supplementalMetadata[key];
  const resolved = (key: string, nativeValue?: string | number | null, nativeSource = 'Loaded data') => {
    const supplied = imported(key);
    const suppliedText = supplied?.value?.trim() || '—';

    if (suppliedText !== '—') {
      return {
        value: suppliedText,
        source: supplied?.authoredBy === 'user'
          ? (supplied.source || 'Manual edit')
          : `${supplied?.source || 'Spreadsheet'} · imported`,
      };
    }

    const nativeText = safeText(nativeValue);
    if (nativeText !== '—') {
      return { value: nativeText, source: nativeSource };
    }

    return { value: '—', source: 'Not loaded' };
  };

  const numericWellInfoKeys = new Set([
    'latitude', 'longitude', 'northing', 'easting', 'grid_convergence',
    'reference_elevation', 'surface_seabed_elevation', 'water_depth',
    'seabed_depth_below_reference', 'wellhead_depth_below_reference',
    'total_depth_md', 'total_depth_tvd', 'survey_start_md', 'survey_end_md',
    'survey_start_tvd', 'survey_end_tvd', 'data_start_md', 'data_end_md',
    'station_count', 'maximum_inclination', 'final_north_offset', 'final_east_offset',
  ]);

  const validateInlineWellInfoValue = (fieldKey: string, rawValue: string): string | null => {
    const value = rawValue.trim();
    if (!value) return 'Enter a value before saving.';
    if (numericWellInfoKeys.has(fieldKey)) {
      const numeric = Number(value.replace(/,/g, ''));
      if (!Number.isFinite(numeric)) return 'Enter a valid numeric value.';
      if (fieldKey === 'latitude' && (numeric < -90 || numeric > 90)) return 'Latitude must be between -90 and 90.';
      if (fieldKey === 'longitude' && (numeric < -180 || numeric > 180)) return 'Longitude must be between -180 and 180.';
      if (fieldKey === 'station_count' && (!Number.isInteger(numeric) || numeric < 0)) return 'Station count must be a non-negative whole number.';
    }
    return null;
  };

  const beginInlineFieldEdit = (fieldKey: string, value: string) => {
    setArmedFieldKey(fieldKey);
    setEditingFieldKey(fieldKey);
    setFieldDraftValue(value);
    setFieldValidationError('');
  };

  const cancelInlineFieldEdit = () => {
    setEditingFieldKey(null);
    setArmedFieldKey(null);
    setFieldDraftValue('');
    setFieldValidationError('');
  };

  const saveInlineFieldEdit = (fieldKey: string, rawValue: string, displayedSource: string) => {
    const validation = validateInlineWellInfoValue(fieldKey, rawValue);
    if (validation) {
      setFieldValidationError(validation);
      return;
    }
    const existing = supplementalMetadata[fieldKey];
    const fieldDefinition = WELL_INFO_FIELD_DEFINITIONS.find((field) => field.key === fieldKey);
    onSupplementalMetadataChange({
      ...supplementalMetadata,
      [fieldKey]: {
        ...existing,
        value: rawValue.trim(),
        unit: existing?.unit ?? fieldDefinition?.unit,
        source: existing?.source || displayedSource,
        sourceReference: existing?.sourceReference,
        notes: existing?.notes,
        authoredBy: 'user',
        userEditedAt: new Date().toISOString(),
      },
    });
    setEditingFieldKey(null);
    setArmedFieldKey(null);
    setFieldDraftValue('');
    setFieldValidationError('');
  };

  const trajectories = well.metadata?.wbv_trajectory_records ?? [];
  const activeTrajectory = trajectories.find((item) => item.is_active) ?? trajectories[0] ?? null;
  const sources = well.source_references ?? [];
  const packages = well.viewer_packages ?? [];
  const productGroups = well.product_groups ?? [];
  const productCount = productGroups.reduce((sum, group) => sum + (group.items?.length ?? 0), 0);
  const depthUnit = resolved('depth_unit', well.depth_unit, 'Managed well');
  const depthReference = resolved('depth_reference');
  const displayDepth = (entry: { value: string; source: string }) => entry.value === '—' ? '—' : `${entry.value}${depthUnit.value === '—' ? '' : ` ${depthUnit.value}`}`;
  const displaySummaryDepth = (entry: { value: string; source: string }) => {
    if (entry.value === '—') return '—';

    const normalized = entry.value.replace(/,/g, '').replace(/\s+/g, ' ').trim();
    const match = normalized.match(/[-+]?\d+(?:\.\d+)?/);
    if (!match) return displayDepth(entry);

    const numeric = Number(match[0]);
    if (!Number.isFinite(numeric)) return displayDepth(entry);

    const formatted = numeric
      .toFixed(2)
      .replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

    return `${formatted}${depthUnit.value === '—' ? '' : ` ${depthUnit.value}`}`;
  };

  const deterministicExportValues: Record<string, { value: string; source: string }> = {
    well_name: resolved('well_name', wellDisplayName(well), 'Managed well'),
    wellbore_name: resolved('wellbore_name', well.wellbore_name, 'Managed well'),
    uwi: resolved('uwi', well.uwi, 'Managed well'), field: resolved('field', well.field, 'Managed well'),
    block: resolved('block', well.block, 'Managed well'), operator: resolved('operator', well.operator, 'Managed well'),
    country: resolved('country', well.country, 'Managed well'),
    well_status: resolved('well_status', statusLabel(wellStatus(well)), 'Managed well'),
    depth_unit: depthUnit,
    depth_reference: resolved('depth_reference'), reference_elevation: resolved('reference_elevation'),
    surface_seabed_elevation: resolved('surface_seabed_elevation'), water_depth: resolved('water_depth'),
    seabed_depth_below_reference: resolved('seabed_depth_below_reference'),
    wellhead_depth_below_reference: resolved('wellhead_depth_below_reference'),
    total_depth_md: resolved('total_depth_md'), total_depth_tvd: resolved('total_depth_tvd'),
    survey_start_md: resolved('survey_start_md', activeTrajectory?.md_min, 'Deviation'),
    survey_end_md: resolved('survey_end_md', activeTrajectory?.md_max, 'Deviation'),
    survey_start_tvd: resolved('survey_start_tvd', activeTrajectory?.tvd_min, 'Deviation'),
    survey_end_tvd: resolved('survey_end_tvd', activeTrajectory?.tvd_max, 'Deviation'),
    data_start_md: resolved('data_start_md', well.top_depth, 'Managed log coverage'),
    data_end_md: resolved('data_end_md', well.base_depth, 'Managed log coverage'),
    trajectory_source: resolved('trajectory_source', activeTrajectory?.source_label || activeTrajectory?.trajectory_name, 'Deviation'),
    survey_status: resolved('survey_status', activeTrajectory?.status ? statusLabel(activeTrajectory.status) : null, 'Deviation'),
    survey_type: resolved('survey_type', activeTrajectory?.trajectory_type, 'Deviation'),
    station_count: resolved('station_count', activeTrajectory?.station_count, 'Deviation'),
  };

  const summaryPanels = [
    { title: 'Identity', rows: [
      { label: 'Managed well', value: resolved('well_name', wellDisplayName(well), 'Managed well').value },
      { label: 'Wellbore', value: resolved('wellbore_name', well.wellbore_name).value },
      { label: 'Field', value: resolved('field', well.field).value },
      { label: 'Operator', value: resolved('operator', well.operator).value },
    ] },
    { title: 'Position / CRS', rows: [
      { label: 'Latitude', value: resolved('latitude').value },
      { label: 'Longitude', value: resolved('longitude').value },
      { label: 'Northing', value: resolved('northing').value },
      { label: 'CRS', value: resolved('coordinate_system').value },
    ] },
    { title: 'Depth reference', rows: [
      { label: 'Depth unit', value: depthUnit.value },
      { label: 'Depth reference', value: resolved('depth_reference').value },
      { label: 'Reference elevation', value: displaySummaryDepth(resolved('reference_elevation')) },
      { label: 'Surface / seabed elevation', value: displaySummaryDepth(resolved('surface_seabed_elevation')) },
    ] },
    { title: 'Well extent', rows: [
      { label: 'Total depth MD', value: displaySummaryDepth(resolved('total_depth_md')) },
      { label: 'Total depth TVD', value: displaySummaryDepth(resolved('total_depth_tvd')) },
      { label: 'Survey end MD', value: displaySummaryDepth(resolved('survey_end_md', activeTrajectory?.md_max, 'Deviation')) },
      { label: 'Data end MD', value: displaySummaryDepth(resolved('data_end_md', well.base_depth, 'Managed log coverage')) },
    ] },
    { title: 'Evidence', rows: [
      { label: 'Source files', value: String(sources.length) },
      { label: 'Viewer packages', value: String(packages.length) },
      { label: 'Trajectories', value: String(trajectories.length) },
      { label: 'Managed products', value: String(productCount) },
    ] },
  ];


  const importWellMetadataFile = async (file: File): Promise<boolean> => {
    setTransferMessage('');
    setTransferError('');

    try {
      const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' });
      const sheet = workbook.Sheets['Well Info'];
      if (!sheet) throw new Error('The workbook does not contain a Well Info sheet.');

      const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
      const acceptedKeys = new Set(WELL_INFO_FIELD_DEFINITIONS.map((field) => field.key));
      const next: WellInfoSupplementalMetadata = { ...supplementalMetadata };
      let importedCount = 0;

      for (const row of rows) {
        const key = String(row['Field Key'] ?? row['field_key'] ?? '').trim();
        const value = String(row['Value'] ?? row['value'] ?? '').trim();
        if (LEGACY_WELL_INFO_FIELD_KEYS.has(key)) {
          throw new Error(
            `Legacy Well Info field key "${key}" is not supported. Export a new Version ${WELL_INFO_SCHEMA_VERSION} template from Well Information and transfer the values into it.`,
          );
        }
        if (!key || !acceptedKeys.has(key) || !value) continue;

        if (next[key]?.authoredBy === 'user') continue;

        next[key] = {
          value,
          unit: String(row['Unit'] ?? '').trim() || undefined,
          source: String(row['Source'] ?? '').trim() || 'Spreadsheet',
          sourceReference: String(row['Source Reference'] ?? '').trim() || undefined,
          notes: String(row['Notes'] ?? '').trim() || undefined,
          authoredBy: 'import',
        };
        importedCount += 1;
      }

      const importedWellName = next.well_name?.value?.trim();
      const selectedNames = [
        wellDisplayName(well),
        well.well_name,
        well.wellbore_name,
        well.uwi,
      ]
        .filter(Boolean)
        .map((value) => String(value).trim().toLowerCase());

      if (importedWellName && !selectedNames.includes(importedWellName.toLowerCase())) {
        throw new Error(
          `Workbook well_name "${importedWellName}" does not match the selected well "${wellDisplayName(well)}".`,
        );
      }

      if (importedCount === 0) {
        throw new Error('No populated supported metadata values were found.');
      }

      onSupplementalMetadataChange(next);
      setTransferMessage(
        `Imported ${importedCount} transient metadata value${importedCount === 1 ? '' : 's'} from ${file.name}.`,
      );
      return true;
    } catch (error) {
      setTransferError(error instanceof Error ? error.message : 'Metadata import failed.');
      return false;
    }
  };

  const chooseImportFile = (file: File | null) => {
    if (!file) return;

    if (!/\.xlsx$/i.test(file.name)) {
      setPendingImportFile(null);
      setTransferError('Select an exported Well Info .xlsx workbook.');
      return;
    }

    setTransferError('');
    setPendingImportFile(file);
  };

  const handleImportInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    chooseImportFile(event.target.files?.[0] ?? null);
    event.target.value = '';
  };

  const confirmMetadataImport = async () => {
    if (!pendingImportFile || importBusy) return;

    setImportBusy(true);
    const imported = await importWellMetadataFile(pendingImportFile);
    setImportBusy(false);

    if (imported) {
      setImportModalOpen(false);
      setPendingImportFile(null);
      setImportDragActive(false);
    }
  };

  const closeMetadataImport = () => {
    if (importBusy) return;
    setImportModalOpen(false);
    setPendingImportFile(null);
    setImportDragActive(false);
    setTransferError('');
  };

  const buildContextWorkbook = () => {
    const rows = WELL_INFO_FIELD_DEFINITIONS.map((field) => {
      const deterministic = deterministicExportValues[field.key];
      const supplied = supplementalMetadata[field.key];
      const selected = deterministic?.value && deterministic.value !== '—' ? deterministic : supplied;
      return {
        Section: field.section,
        Field: field.label,
        'Field Key': field.key,
        Value: selected?.value ?? '',
        Unit: supplied?.unit ?? field.unit ?? '',
        Source: deterministic?.value && deterministic.value !== '—' ? deterministic.source : supplied?.source ?? '',
        'Source Reference': supplied?.sourceReference ?? '',
        Notes: supplied?.notes ?? '',
        'Schema Version': WELL_INFO_SCHEMA_VERSION,
        'AI Recommended Value': '',
        'AI Unit': '',
        'AI Source': '',
        'AI Source Reference': '',
        'AI Evidence': '',
        'AI Confidence': '',
        'AI Status': '',
      };
    });
    const contextWorkbook = XLSX.utils.book_new();
    const sheet = XLSX.utils.json_to_sheet(rows, { header: ['Section', 'Field', 'Field Key', 'Value', 'Unit', 'Source', 'Source Reference', 'Notes', 'Schema Version', 'AI Recommended Value', 'AI Unit', 'AI Source', 'AI Source Reference', 'AI Evidence', 'AI Confidence', 'AI Status'] });
    sheet['!cols'] = [{ wch: 22 }, { wch: 28 }, { wch: 28 }, { wch: 24 }, { wch: 12 }, { wch: 22 }, { wch: 34 }, { wch: 38 }, { wch: 16 }, { wch: 28 }, { wch: 12 }, { wch: 28 }, { wch: 34 }, { wch: 48 }, { wch: 14 }, { wch: 14 }];
    XLSX.utils.book_append_sheet(contextWorkbook, sheet, 'Well Info');
    const instructions = XLSX.utils.aoa_to_sheet([
      [`MultiViewer WME AI Context Workbook v${WELL_INFO_SCHEMA_VERSION}`],
      ['Populate only the AI-prefixed columns. Do not change Field Key, Value, or known-source columns.'],
      ['Every recommendation requires a source document, source reference/page, and evidence.'],
      ['Use AI Status values: proposed, unresolved, or conflict.'],
      [`Schema version: ${WELL_INFO_SCHEMA_VERSION}`],
    ]);
    XLSX.utils.book_append_sheet(contextWorkbook, instructions, 'AI Instructions');
    return contextWorkbook;
  };

  const sendToWme = () => {
    setTransferMessage('');
    setTransferError('');
    try {
      const contextWorkbook = buildContextWorkbook();
      const bytes = XLSX.write(contextWorkbook, { bookType: 'xlsx', type: 'array', compression: true }) as ArrayBuffer;
      const binary = Array.from(new Uint8Array(bytes), (value) => String.fromCharCode(value)).join('');
      const safeName = wellDisplayName(well).replace(/[^a-z0-9_-]+/gi, '_').replace(/^_+|_+$/g, '') || 'well';
      onSendToWme({ fileName: `${safeName}_${WELL_INFO_TEMPLATE_FILENAME_SUFFIX}.xlsx`, workbookBase64: btoa(binary) });
    } catch (error) {
      setTransferError(error instanceof Error ? error.message : 'Unable to send context to WME.');
    }
  };

  const handleExport = () => {
    setTransferMessage('');
    setTransferError('');
    try {
      const rows = WELL_INFO_FIELD_DEFINITIONS.map((field) => {
        const deterministic = deterministicExportValues[field.key];
        const supplied = supplementalMetadata[field.key];
        const selected = deterministic?.value && deterministic.value !== '—' ? deterministic : supplied;
        return {
          Section: field.section,
          Field: field.label,
          'Field Key': field.key,
          Value: selected?.value ?? '',
          Unit: supplied?.unit ?? field.unit ?? '',
          Source: deterministic?.value && deterministic.value !== '—' ? deterministic.source : supplied?.source ?? '',
          'Source Reference': supplied?.sourceReference ?? '',
          Notes: supplied?.notes ?? '',
          'Schema Version': WELL_INFO_SCHEMA_VERSION,
        };
      });
      const workbook = XLSX.utils.book_new();
      const sheet = XLSX.utils.json_to_sheet(rows, { header: ['Section', 'Field', 'Field Key', 'Value', 'Unit', 'Source', 'Source Reference', 'Notes', 'Schema Version'] });
      sheet['!cols'] = [{ wch: 22 }, { wch: 28 }, { wch: 28 }, { wch: 24 }, { wch: 12 }, { wch: 22 }, { wch: 34 }, { wch: 38 }, { wch: 16 }];
      XLSX.utils.book_append_sheet(workbook, sheet, 'Well Info');
      const instructions = XLSX.utils.aoa_to_sheet([
        [`MultiViewer WLV — Well Information Template v${WELL_INFO_SCHEMA_VERSION}`],
        ['This file contains the current transient well context. Imported values are flushed with MWD unless explicitly saved as custom information.'],
        ['Use only the canonical Field Key values in the Well Info sheet. Unit names must remain in the Unit column and must not be appended to Field Key values.'],
        [`Schema version: ${WELL_INFO_SCHEMA_VERSION}`],
        ['Legacy unit-suffixed keys such as latitude_deg, northing_m, and final_md_m are rejected.'],
      ]);
      XLSX.utils.book_append_sheet(workbook, instructions, 'Instructions');
      const safeName = wellDisplayName(well).replace(/[^a-z0-9_-]+/gi, '_').replace(/^_+|_+$/g, '') || 'well';
      XLSX.writeFile(workbook, `${safeName}_${WELL_INFO_TEMPLATE_FILENAME_SUFFIX}.xlsx`, { compression: true });
      setTransferMessage('Exported the current transient well context.');
    } catch (error) {
      setTransferError(error instanceof Error ? error.message : 'Metadata export failed.');
    }
  };

  const inlineFieldProps = (fieldKey: string, editValue?: string) => ({
    fieldKey,
    editValue,
    armed: armedFieldKey === fieldKey,
    editing: editingFieldKey === fieldKey,
    draftValue: editingFieldKey === fieldKey ? fieldDraftValue : '',
    validationError: editingFieldKey === fieldKey ? fieldValidationError : '',
    onArm: (key: string) => {
      if (editingFieldKey && editingFieldKey !== key) return;
      setArmedFieldKey(key);
      setFieldValidationError('');
    },
    onBeginEdit: beginInlineFieldEdit,
    onDraftChange: (value: string) => {
      setFieldDraftValue(value);
      setFieldValidationError('');
    },
    onSave: saveInlineFieldEdit,
    onCancel: cancelInlineFieldEdit,
  });

  const positionFields: Array<[string, string]> = [
    ['Latitude','latitude'], ['Longitude','longitude'], ['Northing','northing'], ['Easting','easting'],
    ['Coordinate System','coordinate_system'], ['UTM Zone','utm_zone'], ['Geodetic Datum','geodetic_datum'], ['EPSG Code','epsg_code'],
    ['North Reference','north_reference'], ['Grid Convergence','grid_convergence'],
  ];

  return (<section className="wlv-well-info-page" aria-label={`Well Information for ${wellDisplayName(well)}`}>
    <header className="wlv-well-info-topbar">
      <div className="wlv-well-info-topbar__title"><span className="wlv-well-info-db-icon">▣</span><h1>Well Information</h1></div>
      <div className="wlv-well-info-topbar__actions"><button type="button" onClick={onReturnToData}>‹ Managed Data</button></div>
    </header>
    <datalist id="wlv-depth-reference-options">
      <option value="RT" />
      <option value="RKB" />
      <option value="KB" />
      <option value="RC" />
      <option value="MSL" />
    </datalist>
    <div className="wlv-well-info-body">
      <section className="wlv-well-info-hero">
        <div><h2>{resolved('well_name', wellDisplayName(well), 'Managed well').value}</h2><p>{[well.field, well.wellbore_name, wellStatus(well)].filter(Boolean).join(' · ') || 'Managed well'}</p></div>
        <div className="wlv-well-info-context"><span>Transient well context</span><small>Source-derived and imported information is cleared with MWD.</small></div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Metadata Summary</h3><span>Consolidated identity, position, vertical reference, and evidence status.</span></div>
        <div className="wlv-well-info-summary-grid">{summaryPanels.map((panel) => <WellInfoSummaryPanel key={panel.title} title={panel.title} rows={panel.rows} />)}</div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Identity</h3></div>
        <div className="wlv-well-info-field-grid">
          <WellInfoField {...inlineFieldProps('well_name', resolved('well_name', wellDisplayName(well), 'Managed well').value)} label="Well Name" {...resolved('well_name', wellDisplayName(well), 'Managed well')} />
          <WellInfoField {...inlineFieldProps('wellbore_name', resolved('wellbore_name', well.wellbore_name, 'Managed well').value)} label="Wellbore" {...resolved('wellbore_name', well.wellbore_name, 'Managed well')} />
          <WellInfoField {...inlineFieldProps('uwi', resolved('uwi', well.uwi, 'Managed well').value)} label="UWI" {...resolved('uwi', well.uwi, 'Managed well')} />
          <WellInfoField {...inlineFieldProps('field', resolved('field', well.field, 'Managed well').value)} label="Field" {...resolved('field', well.field, 'Managed well')} />
          <WellInfoField {...inlineFieldProps('site', resolved('site').value)} label="Site" {...resolved('site')} />
          <WellInfoField {...inlineFieldProps('block', resolved('block', well.block, 'Managed well').value)} label="Block" {...resolved('block', well.block, 'Managed well')} />
          <WellInfoField {...inlineFieldProps('operator', resolved('operator', well.operator, 'Managed well').value)} label="Operator" {...resolved('operator', well.operator, 'Managed well')} />
          <WellInfoField {...inlineFieldProps('country', resolved('country', well.country, 'Managed well').value)} label="Country" {...resolved('country', well.country, 'Managed well')} />
          <WellInfoField {...inlineFieldProps('well_status', resolved('well_status', statusLabel(wellStatus(well)), 'Managed well').value)} label="Status" {...resolved('well_status', statusLabel(wellStatus(well)), 'Managed well')} />
        </div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Position / CRS</h3></div>
        <div className="wlv-well-info-field-grid">
          {positionFields.map(([label,key]) => <WellInfoField key={key} {...inlineFieldProps(key, resolved(key).value)} label={label} {...resolved(key)} />)}
        </div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Depth Reference</h3></div>
        <div className="wlv-well-info-field-grid">
          <WellInfoField {...inlineFieldProps('depth_unit', depthUnit.value)} label="Depth Unit" {...depthUnit} />
          <WellInfoField {...inlineFieldProps('depth_reference', depthReference.value)} label="MD / TVD Reference" {...depthReference} />
          <WellInfoField {...inlineFieldProps('reference_elevation', resolved('reference_elevation').value)} label="Reference Elevation (relative to MSL)" value={displayDepth(resolved('reference_elevation'))} source={resolved('reference_elevation').source} />
          <WellInfoField {...inlineFieldProps('surface_seabed_elevation', resolved('surface_seabed_elevation').value)} label="Ground / Seabed Elevation (relative to MSL)" value={displayDepth(resolved('surface_seabed_elevation'))} source={resolved('surface_seabed_elevation').source} />
          <WellInfoField {...inlineFieldProps('water_depth', resolved('water_depth').value)} label="Water Depth (below MSL)" value={displayDepth(resolved('water_depth'))} source={resolved('water_depth').source} />
          <WellInfoField {...inlineFieldProps('seabed_depth_below_reference', resolved('seabed_depth_below_reference').value)} label="Seabed Depth (below Reference)" value={displayDepth(resolved('seabed_depth_below_reference'))} source={resolved('seabed_depth_below_reference').source} />
          <WellInfoField {...inlineFieldProps('wellhead_depth_below_reference', resolved('wellhead_depth_below_reference').value)} label="Top of Wellhead Depth (below Reference)" value={displayDepth(resolved('wellhead_depth_below_reference'))} source={resolved('wellhead_depth_below_reference').source} />
        </div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Well Extent (from Reference)</h3></div>
        <div className="wlv-well-info-field-grid">
          <WellInfoField {...inlineFieldProps('total_depth_md', resolved('total_depth_md').value)} label="Total Depth MD" value={displayDepth(resolved('total_depth_md'))} source={resolved('total_depth_md').source} />
          <WellInfoField {...inlineFieldProps('total_depth_tvd', resolved('total_depth_tvd').value)} label="Total Depth TVD" value={displayDepth(resolved('total_depth_tvd'))} source={resolved('total_depth_tvd').source} />
        </div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Survey Extent (from Reference)</h3></div>
        <div className="wlv-well-info-field-grid">
          <WellInfoField {...inlineFieldProps('survey_start_md', resolved('survey_start_md', activeTrajectory?.md_min, 'Deviation').value)} label="Survey Start MD" value={displayDepth(resolved('survey_start_md', activeTrajectory?.md_min, 'Deviation'))} source={resolved('survey_start_md', activeTrajectory?.md_min, 'Deviation').source} />
          <WellInfoField {...inlineFieldProps('survey_end_md', resolved('survey_end_md', activeTrajectory?.md_max, 'Deviation').value)} label="Survey End MD" value={displayDepth(resolved('survey_end_md', activeTrajectory?.md_max, 'Deviation'))} source={resolved('survey_end_md', activeTrajectory?.md_max, 'Deviation').source} />
          <WellInfoField {...inlineFieldProps('survey_start_tvd', resolved('survey_start_tvd', activeTrajectory?.tvd_min, 'Deviation').value)} label="Survey Start TVD" value={displayDepth(resolved('survey_start_tvd', activeTrajectory?.tvd_min, 'Deviation'))} source={resolved('survey_start_tvd', activeTrajectory?.tvd_min, 'Deviation').source} />
          <WellInfoField {...inlineFieldProps('survey_end_tvd', resolved('survey_end_tvd', activeTrajectory?.tvd_max, 'Deviation').value)} label="Survey End TVD" value={displayDepth(resolved('survey_end_tvd', activeTrajectory?.tvd_max, 'Deviation'))} source={resolved('survey_end_tvd', activeTrajectory?.tvd_max, 'Deviation').source} />
        </div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Data Coverage (from Reference)</h3></div>
        <div className="wlv-well-info-field-grid">
          <WellInfoField {...inlineFieldProps('data_start_md', resolved('data_start_md', well.top_depth, 'Managed log coverage').value)} label="Data Start MD" value={displayDepth(resolved('data_start_md', well.top_depth, 'Managed log coverage'))} source={resolved('data_start_md', well.top_depth, 'Managed log coverage').source} />
          <WellInfoField {...inlineFieldProps('data_end_md', resolved('data_end_md', well.base_depth, 'Managed log coverage').value)} label="Data End MD" value={displayDepth(resolved('data_end_md', well.base_depth, 'Managed log coverage'))} source={resolved('data_end_md', well.base_depth, 'Managed log coverage').source} />
        </div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Trajectory Summary</h3></div>
        <div className="wlv-well-info-field-grid">
          <WellInfoField {...inlineFieldProps('trajectory_source', resolved('trajectory_source', activeTrajectory?.source_label || activeTrajectory?.trajectory_name, 'Deviation').value)} label="Trajectory Source" {...resolved('trajectory_source', activeTrajectory?.source_label || activeTrajectory?.trajectory_name, 'Deviation')} />
          <WellInfoField {...inlineFieldProps('survey_status', resolved('survey_status', activeTrajectory?.status ? statusLabel(activeTrajectory.status) : null, 'Deviation').value)} label="Survey Status" {...resolved('survey_status', activeTrajectory?.status ? statusLabel(activeTrajectory.status) : null, 'Deviation')} />
          <WellInfoField {...inlineFieldProps('survey_type', resolved('survey_type', activeTrajectory?.trajectory_type, 'Deviation').value)} label="Survey Type" {...resolved('survey_type', activeTrajectory?.trajectory_type, 'Deviation')} />
          <WellInfoField {...inlineFieldProps('calculation_method', resolved('calculation_method').value)} label="Calculation Method" {...resolved('calculation_method')} />
          <WellInfoField {...inlineFieldProps('station_count', resolved('station_count').value)} label="Station Count" {...resolved('station_count', activeTrajectory?.station_count, 'Deviation')} />
          <WellInfoField {...inlineFieldProps('maximum_inclination', resolved('maximum_inclination').value)} label="Maximum Inclination" {...resolved('maximum_inclination')} />
          <WellInfoField {...inlineFieldProps('final_north_offset', resolved('final_north_offset').value)} label="Final North Offset" {...resolved('final_north_offset')} />
          <WellInfoField {...inlineFieldProps('final_east_offset', resolved('final_east_offset').value)} label="Final East Offset" {...resolved('final_east_offset')} />
        </div>
      </section>

      <section className="wlv-well-info-section">
        <div className="wlv-well-info-section-heading"><h3>Loaded Data</h3><span>Current transient data attached to this managed well.</span></div>
        <div className="wlv-well-info-loaded-grid">
          <article><strong>{sources.length}</strong><span>Source files</span></article>
          <article><strong>{packages.length}</strong><span>Viewer packages</span></article>
          <article><strong>{trajectories.length}</strong><span>Trajectories</span></article>
          <article><strong>{productCount}</strong><span>Managed products</span></article>
        </div>
      </section>

      <div className="wlv-well-info-footer-actions">
        <input
          ref={importInputRef}
          className="wlv-well-info-file-input"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={handleImportInputChange}
        />
        <button
          type="button"
          onClick={() => {
            setTransferError('');
            setPendingImportFile(null);
            setImportModalOpen(true);
          }}
        >
          Import Well Metadata
        </button>
        <button type="button" onClick={sendToWme}>Send to WME</button>
        <button type="button" onClick={handleExport}>Export Well Context</button>
        {(transferMessage || transferError) ? <span className={transferError ? 'is-error' : 'is-success'}>{transferError || transferMessage}</span> : <span>Source-derived and imported information remains transient and is removed when MWD is flushed.</span>}
      </div>

      {importModalOpen ? (
        <div
          className="wlv-well-info-import-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) closeMetadataImport();
          }}
        >
          <section
            className="wlv-well-info-import-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="wlv-well-info-import-title"
          >
            <header>
              <div>
                <h3 id="wlv-well-info-import-title">Import Well Metadata</h3>
                <p>Import an exported Well Info workbook into the current transient well context.</p>
              </div>
              <button
                type="button"
                className="wlv-well-info-import-close"
                aria-label="Close metadata import"
                disabled={importBusy}
                onClick={closeMetadataImport}
              >
                ×
              </button>
            </header>

            <div
              className={`wlv-well-info-import-dropzone ${importDragActive ? 'is-dragging' : ''}`}
              onDragEnter={(event) => {
                event.preventDefault();
                event.stopPropagation();
                setImportDragActive(true);
              }}
              onDragOver={(event) => {
                event.preventDefault();
                event.stopPropagation();
                event.dataTransfer.dropEffect = 'copy';
                setImportDragActive(true);
              }}
              onDragLeave={(event) => {
                event.preventDefault();
                event.stopPropagation();
                if (event.currentTarget === event.target) setImportDragActive(false);
              }}
              onDrop={(event) => {
                event.preventDefault();
                event.stopPropagation();
                setImportDragActive(false);
                chooseImportFile(event.dataTransfer.files?.[0] ?? null);
              }}
            >
              <strong>
                {pendingImportFile ? pendingImportFile.name : 'Drop exported Well Info .xlsx here'}
              </strong>
              <span>
                {pendingImportFile
                  ? `${Math.max(1, Math.round(pendingImportFile.size / 1024))} KB selected`
                  : 'The workbook is validated against the selected managed well before import.'}
              </span>
              <button
                type="button"
                disabled={importBusy}
                onClick={() => importInputRef.current?.click()}
              >
                Browse
              </button>
            </div>

            {transferError ? (
              <div className="wlv-well-info-import-error" role="alert">{transferError}</div>
            ) : null}

            <footer>
              <button type="button" disabled={importBusy} onClick={closeMetadataImport}>
                Cancel
              </button>
              <button
                type="button"
                disabled={!pendingImportFile || importBusy}
                onClick={() => void confirmMetadataImport()}
              >
                {importBusy ? 'Importing…' : 'Import'}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </div>
  </section>);
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
  const [activeView, setActiveView] = useState<DemoNavView>(readLastPrimaryView);
  const [managedViewerWell, setManagedViewerWell] = useState<ManagedWellIdentity | null>(null);
  const [infoWell, setInfoWell] = useState<ManagedInventoryWellRecord | null>(null);
  const [supplementalMetadataByWell, setSupplementalMetadataByWell] = useState<Record<string, WellInfoSupplementalMetadata>>(
    readPersistedWellInfoMetadata,
  );
  const [activeRecovery, setActiveRecovery] = useState<WmdDownstreamRecoveryStatus | null>(null);
  const [wmeDirectContext, setWmeDirectContext] = useState<{ fileName: string; workbookBase64: string } | null>(null);

  useEffect(() => {
    persistWellInfoMetadata(supplementalMetadataByWell);
  }, [supplementalMetadataByWell]);

  useEffect(() => {
    persistLastPrimaryView(activeView);
  }, [activeView]);

  const reconcileSupplementalMetadataWithMwd = (managedWellIds: string[]) => {
    setSupplementalMetadataByWell((current) => {
      const retained = retainManagedWellMetadata(current, managedWellIds);
      return Object.keys(retained).length === Object.keys(current).length ? current : retained;
    });
    setInfoWell((current) => current && managedWellIds.includes(current.managed_well_id) ? current : null);
  };
  const openManagedWellLogViewer = (identity?: ManagedWellIdentity | null) => {
    if (identity) setManagedViewerWell(identity);
    setActiveView('log-viewer');
  };
  const openWellInfo = (well: ManagedInventoryWellRecord) => {
    setInfoWell(well);
    setActiveView('info');
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
          {downstreamBlocked && activeRecovery ? (<WmdRecoveryBlockedView status={activeRecovery} onReturnToData={() => setActiveView('data')}/>) : activeView === 'data' ? (<ManagedWellInventoryPage onOpenLogViewer={openManagedWellLogViewer} onOpenInfo={openWellInfo} onClearLogViewer={clearManagedWellLogViewer} onManagedWellIdsChange={reconcileSupplementalMetadataWithMwd} activeManagedWellId={managedViewerWellId}/>) : activeView === 'info' ? (<WellInfoPage well={infoWell} supplementalMetadata={infoWell ? supplementalMetadataByWell[infoWell.managed_well_id] ?? {} : {}} onSupplementalMetadataChange={(metadata) => { if (infoWell) setSupplementalMetadataByWell((current) => ({ ...current, [infoWell.managed_well_id]: metadata })); }} onReturnToData={() => setActiveView('data')} onSendToWme={(context) => { setWmeDirectContext(context); setActiveView('toolbox'); }} />) : activeView === 'toolbox' ? (<ToolboxPage initialContext={wmeDirectContext} onApplyToWellInfo={(values) => { if (!infoWell) return; setSupplementalMetadataByWell((current) => ({ ...current, [infoWell.managed_well_id]: mergeWellInfoPreservingUserAuthored(current[infoWell.managed_well_id] ?? {}, values) })); setActiveView('info'); }} />) : activeView === 'knowledge' ? (<div className="wlv-kr-page-shell">
              <KrManagedInstructionsWorkbench />
            </div>) : activeView === 'sources' ? (<SourceIntakeWorkbench />) : activeView === 'wellbore-3d' ? (<Wellbore3DPage supplementalWellInfoMetadataByWell={supplementalMetadataByWell} onOpenLogViewer={() => setActiveView('log-viewer')}/>) : <WdvPageBoundary managedViewerWell={managedViewerWell} setManagedViewerWell={setManagedViewerWell} supplementalWellInfoMetadata={managedViewerWell ? supplementalMetadataByWell[managedViewerWell.managedWellId] ?? {} : {}} onOpenWellbore3D={() => setActiveView("wellbore-3d")}/>}
        </main>
      </div>);
}

export default TrackLayoutPrototype;
