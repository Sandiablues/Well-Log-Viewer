import { type Dispatch, type ReactNode, type SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { curveCatalog } from '../prototype/realLasTrackLayoutData';
import { WellLogPropertiesPanelSlot } from '../prototype/WellLogPropertiesPanelSlot';
import { loadBackendViewerPackageWithFallback, type BackendViewerPackageLoadResult } from '../prototype/backendViewerPackageAdapter';
import { buildWdvPackageState, emptyWdvPackageState, type WdvLoadedCurveItem, type WdvPackageState } from '../prototype/wdvPackageState';
import { indexManagedCurveSamples, parseManagedCurveSamples, resolveManagedCurveContract, type ManagedCurveSampleContractsByCurveId, type ManagedCurveSampleLoadResult, type ManagedCurveSamplesByCurveId, type ManagedCurveSamplesPayload } from '../prototype/managedCurveSamples';
import type { CoreTrackAppearance, CompletionTrackAppearance, CurveAssignment, CurveCatalogItem, DragCurvePayload, MacroCoreImageConfig, SelectionRef, TextOverlayConfig, WellLogTrack } from '../prototype/trackLayoutModel';
import { makeCurveAssignment, orderedCurves } from '../prototype/trackLayoutModel';
import { managedWellIdentityFromPayload, sameManagedWellIdentity, type ManagedWellIdentity } from '../identity/managedWellIdentity';
import { parseWdvIdentityMetadataContract, type WdvIdentityMetadataContract } from '../contracts/wdvIdentityMetadataContract';
import { listWbvOverlayPackages, previewWbvPackageUpdate, previewWdvPublication, publishWdvAsNewWbvPackage, updateExistingWbvPackage, type WbvOverlayPackage } from '../wbv/publicationApi';
import {
    buildCurveIdentityIndex,
    canonicalizeCurveIdentitySet,
    canonicalizeCurveUsageCounts,
    resolveAssignmentCanonicalCurveKey,
} from '../identity/curveIdentityIndex';
import { planAddBlankTrack, planAssignmentReorder, planTrackReorder } from './canvasCompositionControl';
import { planTrackRelationshipCleanup } from './trackRelationshipCleanupControl';
import { AddTrackDraft, GLOBAL_DEPTH_LATTICE_INCREMENT, CURVE_TRACK_MAX_WIDTH, CURVE_TRACK_MIN_WIDTH, CurveInventory, CurveInventoryWellContext, DepthViewRange, DEFAULT_FORMATION_TOP_OVERLAY_STYLE, FormationTopDataset, FormationTopMarker, FormationTopOverlayStyle, LithologyIntervalDataset, LithologyIntervalRecord, CoreImageInventoryItem, CompletionComponentRecord, CORE_PHOTO_THRESHOLD_PIXELS_PER_MD, CORE_PHOTO_THRESHOLD_WIDTH_PX, IntervalSelectionState, RightPanel, Toolbar, TrackBackdropMode, TrackCanvas, WdvCanonicalTemplateApplySession, WdvRecommendedCurve, WdvTemplateRecommendationItem, WdvTemplateRecommendationModal, WdvWorkspaceLoadedWell, buildWdvTemplateRecommendationRequest, clampCurveTrackWidth, clampValue, fetchWlvJson, makeMockCurveSamples, sortTracks } from './WdvPresentationPrimitives';
import type { SavedCanvasToolbarItem } from './SavedCanvasToolbarControl';
import { useWdvLayoutSource } from './useWdvLayoutSource';
import type { CanonicalLayoutResult } from './useWdvLayoutSource';
import { buildCompleteLasLoadRequest, buildCompleteLasLoadUrl } from './completeLasWorkflow';
import { openQuickViewFile, sendQuickViewFileToWsi, isQuickViewFile, type QuickViewCurve, type QuickViewPackage, type QuickViewMetadataValue } from './quickViewWorkflow';
import { QuickViewCanvas } from './QuickViewCanvas';
import {
    applyCurveFillGeometryDeltaV2,
    createCurveFillRuleV2,
    fetchCurveFillFeatureStatusV2,
    hydrateCurveFillV2,
    removeCurveFillRuleV2,
    updateCurveFillRuleV2,
    reorderCurveFillRulesV2,
    type CanonicalCurveFillRuleV2,
    type CurveFillGeometryV2,
    type CurveFillWorkflowResultV2,
    WDV_CURVE_SAMPLE_LIMIT,
} from './curveFillV2';
import { buildWellOwnedTrackRenderBundles, renderBundleForTrack, type WellOwnedOverlayRenderState } from './wellOwnedRenderBundles';
import { beginWdvDiagnosticOperation, installWdvDiagnosticErrorHooks, recordWdvDiagnosticEvent } from './wdvDiagnostics';
import { useViewerViewportComposition } from './useViewerViewportComposition';
import { isSelectedViewportTrackEligible } from './viewportSelectionAuthority';
import { useCanonicalSessionMutationController } from './useCanonicalSessionMutationController';
import { useCanonicalSessionApplicationController } from './useCanonicalSessionApplicationController';
import { useCanvasCompositionMutationController } from './useCanvasCompositionMutationController';
import { useViewPersistenceLifecycleController } from './useViewPersistenceLifecycleController';
import { useTrackAssignmentMutationController } from './useTrackAssignmentMutationController';
import { recoveryAuthorityWellUid, recoveryTargetWellUids, shouldArmRecoveryAutosave, shouldAttemptUnifiedRecoveryHydration, shouldRetryStartupHydration, shouldScheduleRecoveryAutosave, UNIFIED_WDV_RECOVERY_RESTORE_KEY, WDV_RECOVERY_AUTOSAVE_DELAY_MS, WDV_STARTUP_HYDRATION_RETRY_DELAY_MS } from './recoveryPersistenceControl';
import { buildPersistedTrackViewports, buildPersistedViewportTieGroups, restorePersistedTrackViewports, restorePersistedViewportTieGroups, restorePersistedViewportTieSuspensions } from './viewportPersistenceContract';
import { shouldScheduleCommittedViewportCommit } from './viewportCommitControl';
import { useViewportRelationshipState } from './useViewportRelationshipState';
import type { DragPanState } from './useDragPanExecution';


function isCurveFillRevisionConflict(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return /^409(?:\s|$)/.test(error.message)
    || /409 Conflict/.test(error.message)
    || /Expected revision \d+, found \d+/.test(error.message);
}


function fullRenderableDepthRangeFromValues(
    values: number[],
    fallback: DepthViewRange,
): DepthViewRange {
    const finite = values.filter((value) => Number.isFinite(value));
    if (finite.length === 0) return { ...fallback };
    const min = Math.min(...finite);
    const max = Math.max(...finite);
    return max > min ? { min, max } : { ...fallback };
}

type WellInfoSessionMetadataValue = {
    value: string;
    unit?: string;
    source?: string;
    sourceReference?: string;
    notes?: string;
};

type WellInfoSessionMetadata = Record<string, WellInfoSessionMetadataValue>;

const CURVE_OVERLAY_PERSISTENCE_KEY = 'wlv.wdv.curveOverlaysByWell.v1';
const CURVE_OVERLAY_TRACK_STYLE_PERSISTENCE_KEY = 'wlv.wdv.formationTopOverlayStylesByTrack.v1';

// WDV_COMPLETION_SELECTION_RELOAD_PERSISTENCE_V1_0_0
// Completion component selection is well-owned durable viewer state, alongside
// the existing well-owned Formation Top and lithology selection records.
type PersistedCurveOverlayWellState = {
    selectedFormationTopIds: string[];
    selectedLithologyIntervalIds: string[];
    selectedCompletionComponentIds: string[];
    stylesByTrackId: Record<string, FormationTopOverlayStyle>;
};

type PersistedCurveOverlayState = Record<string, PersistedCurveOverlayWellState>;

function readPersistedCurveOverlayState(): PersistedCurveOverlayState {
    if (typeof window === 'undefined') return {};
    try {
        const raw = window.localStorage.getItem(CURVE_OVERLAY_PERSISTENCE_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw) as unknown;
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
        return parsed as PersistedCurveOverlayState;
    } catch {
        return {};
    }
}

function readPersistedCurveOverlayWellState(
    managedWellId: string | null | undefined,
): PersistedCurveOverlayWellState | null {
    if (!managedWellId) return null;
    const candidate = readPersistedCurveOverlayState()[managedWellId];
    if (!candidate || typeof candidate !== 'object') return null;

    const selectedFormationTopIds = Array.isArray(candidate.selectedFormationTopIds)
        ? candidate.selectedFormationTopIds.filter((value): value is string => typeof value === 'string')
        : [];

    const selectedLithologyIntervalIds = Array.isArray(candidate.selectedLithologyIntervalIds)
        ? candidate.selectedLithologyIntervalIds.filter((value): value is string => typeof value === 'string')
        : [];

    const selectedCompletionComponentIds = Array.isArray(candidate.selectedCompletionComponentIds)
        ? candidate.selectedCompletionComponentIds.filter((value): value is string => typeof value === 'string')
        : [];

    const stylesByTrackId =
        candidate.stylesByTrackId &&
        typeof candidate.stylesByTrackId === 'object' &&
        !Array.isArray(candidate.stylesByTrackId)
            ? candidate.stylesByTrackId
            : {};

    return {
        selectedFormationTopIds,
        selectedLithologyIntervalIds,
        selectedCompletionComponentIds,
        stylesByTrackId,
    };
}

function writePersistedCurveOverlayWellState(
    managedWellId: string | null | undefined,
    state: PersistedCurveOverlayWellState,
): void {
    if (typeof window === 'undefined' || !managedWellId) return;
    const current = readPersistedCurveOverlayState();
    current[managedWellId] = state;
    window.localStorage.setItem(CURVE_OVERLAY_PERSISTENCE_KEY, JSON.stringify(current));
}

function readPersistedCurveOverlayTrackStyles(): Record<string, FormationTopOverlayStyle> {
    if (typeof window === 'undefined') return {};
    try {
        const raw = window.localStorage.getItem(CURVE_OVERLAY_TRACK_STYLE_PERSISTENCE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw) as unknown;
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                return parsed as Record<string, FormationTopOverlayStyle>;
            }
        }
    } catch {
        // Fall through to legacy migration below.
    }

    // WDV_OVERLAY_TRACK_CANVAS_STYLE_AUTHORITY_V1_0_0
    // One-time compatibility fallback: older builds stored track presentation
    // styles inside well-owned overlay records. Merge those track-keyed values
    // only as a migration seed; subsequent writes use the canvas/track store.
    const migrated: Record<string, FormationTopOverlayStyle> = {};
    for (const wellState of Object.values(readPersistedCurveOverlayState())) {
        if (!wellState || typeof wellState !== 'object') continue;
        const styles = wellState.stylesByTrackId;
        if (!styles || typeof styles !== 'object' || Array.isArray(styles)) continue;
        Object.assign(migrated, styles);
    }
    return migrated;
}

function writePersistedCurveOverlayTrackStyles(
    stylesByTrackId: Record<string, FormationTopOverlayStyle>,
): void {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(
        CURVE_OVERLAY_TRACK_STYLE_PERSISTENCE_KEY,
        JSON.stringify(stylesByTrackId),
    );
}

const WDV_INTERVAL_STORAGE_KEYS = [
    'wlv.intervalTrack.builder.v2',
    'wlv.intervalTrack.formation.v1',
    'wlv.intervalTrack.depth.v1',
    'wlv.intervalTrack.descriptions.v2',
] as const;

function readDurableIntervalStorageState(): Record<string, string> {
    if (typeof window === 'undefined') return {};
    const state: Record<string, string> = {};
    for (const key of WDV_INTERVAL_STORAGE_KEYS) {
        try {
            const value = window.localStorage.getItem(key);
            if (value !== null) state[key] = value;
        } catch {
            // Backend recovery remains usable even when browser storage is unavailable.
        }
    }
    return state;
}

function applyDurableIntervalStorageState(state: Record<string, string> | undefined): void {
    if (typeof window === 'undefined' || !state) return;
    for (const key of WDV_INTERVAL_STORAGE_KEYS) {
        const value = state[key];
        if (typeof value !== 'string') continue;
        try {
            window.localStorage.setItem(key, value);
        } catch {
            // Rendering can still proceed from current in-memory state.
        }
    }
    window.dispatchEvent(new CustomEvent('wlv:interval-formation-config-changed'));
    window.dispatchEvent(new CustomEvent('wlv:interval-depth-config-changed'));
    window.dispatchEvent(new CustomEvent('wlv:interval-description-config-changed'));
    // Same-document localStorage writes do not fire the browser "storage" event.
    // Explicitly rehydrate semantic Tie-in configuration after restart recovery.
    window.dispatchEvent(new CustomEvent('wlv:interval-tie-in-config-changed'));
}

function overlayWellInfoSessionMetadata(
    contract: WdvIdentityMetadataContract | null,
    supplementalMetadata: WellInfoSessionMetadata,
): WdvIdentityMetadataContract | null {
    if (!contract || Object.keys(supplementalMetadata).length === 0) return contract;

    return {
        ...contract,
        sections: contract.sections.map((section) => {
            if (section.key !== 'well') return section;
            return {
                ...section,
                values: section.values.map((item) => {
                    const supplemental = supplementalMetadata[item.key];
                    const value = supplemental?.value?.trim();
                    if (!value) return item;
                    return {
                        ...item,
                        value,
                        unit: supplemental.unit?.trim() || item.unit,
                        source: supplemental.source?.trim() || 'Well Info session',
                    };
                }),
            };
        }),
    };
}

type WdvTemplateRecommendationEnvelope = {
    service: string;
    contract_version: string;
    source: string;
    available_curve_count: number;
    classified_curve_count: number;
    unresolved_curve_count: number;
    unresolved_curves?: WdvRecommendedCurve[];
    recommendation_count: number;
    recommendations: WdvTemplateRecommendationItem[];
    knowledge_policy?: Record<string, unknown>;
};

type TrackResizeState = {
    trackId: string;
    startX: number;
    startWidth: number;
};

// Transient empty-canvas state only. Loaded-well depth authority comes from
// the backend viewer package and is never replaced by a frontend default.
const EMPTY_DEPTH_RANGE: DepthViewRange = { min: 0, max: 0 };

const CURVE_TRACK_RESET_WIDTH = 220;

// Go-to navigation is an inspection command, not just a pan command.
// 200 m gives enough context to review the target while making the selected
// MD / formation top the visual focus of the canvas.
const GO_TO_REVIEW_WINDOW_M = 200;

// Detailed log inspection must be able to resolve short intervals. This is
// expressed in the active display unit so metres and feet behave consistently.
const MIN_DEPTH_VIEW_SPAN = 0.10;

const METRES_PER_FOOT = 0.3048;

function convertDepthUnitValue(value: number, fromUnit: 'm' | 'ft', toUnit: 'm' | 'ft'): number {
    if (fromUnit === toUnit) return value;
    return fromUnit === 'm' ? value / METRES_PER_FOOT : value * METRES_PER_FOOT;
}

function convertDepthUnitRange(range: DepthViewRange, fromUnit: 'm' | 'ft', toUnit: 'm' | 'ft'): DepthViewRange {
    return {
        min: convertDepthUnitValue(range.min, fromUnit, toUnit),
        max: convertDepthUnitValue(range.max, fromUnit, toUnit),
    };
}

function clampDepthRange(range: DepthViewRange, fullRange: DepthViewRange): DepthViewRange {
    const span = Math.max(MIN_DEPTH_VIEW_SPAN, range.max - range.min);
    let min = range.min;
    let max = range.max;
    if (min < fullRange.min) {
        min = fullRange.min;
        max = Math.min(fullRange.max, min + span);
    }
    if (max > fullRange.max) {
        max = fullRange.max;
        min = Math.max(fullRange.min, max - span);
    }
    if (min >= max) {
        return { ...fullRange };
    }
    return {
        min: Number(min.toFixed(6)),
        max: Number(max.toFixed(6)),
    };
}

function makeDepthTicks(range: DepthViewRange): number[] {
    const increment = GLOBAL_DEPTH_LATTICE_INCREMENT;
    const start = Math.ceil(range.min / increment) * increment;
    const ticks: number[] = [];
    const maximumTicks = 5000;
    for (
        let depth = start;
        depth <= range.max + increment * 1e-6 && ticks.length < maximumTicks;
        depth += increment
    ) {
        ticks.push(Number(depth.toFixed(6)));
    }
    return ticks;
}

function isAbortError(error: unknown): boolean {
    return error instanceof DOMException && error.name === 'AbortError';
}



async function evaluateWdvTemplateRecommendations(loadedCurveItems: WdvLoadedCurveItem[], signal?: AbortSignal): Promise<WdvTemplateRecommendationEnvelope> {
    return fetchWlvJson<WdvTemplateRecommendationEnvelope>('/api/wlv/wdv/templates/recommendations/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildWdvTemplateRecommendationRequest(loadedCurveItems)),
        signal,
    });
}

function rangesEqual(a: DepthViewRange, b: DepthViewRange): boolean {
    return a.min === b.min && a.max === b.max;
}

function parseInventoryDepthRange(value: string | null | undefined): DepthViewRange | null {
    if (!value) return null;
    const values = value
        .replace(/,/g, '')
        .match(/[-+]?\d+(?:\.\d+)?/g)
        ?.map((token) => Number(token))
        .filter((token) => Number.isFinite(token)) ?? [];

    if (values.length < 2) return null;
    const min = values[0];
    const max = values[1];
    return max > min ? { min, max } : null;
}

function depthRangeSpan(range: DepthViewRange): number {
    return range.max - range.min;
}

export function unionDepthRanges(ranges: DepthViewRange[], fallback: DepthViewRange = EMPTY_DEPTH_RANGE): DepthViewRange {
    const valid = ranges.filter((range) => Number.isFinite(range.min) && Number.isFinite(range.max) && range.max > range.min);
    if (valid.length === 0) return { ...fallback };
    return {
        min: Math.min(...valid.map((range) => range.min)),
        max: Math.max(...valid.map((range) => range.max)),
    };
}

export function preserveCanonicalTrackOrder(current: WellLogTrack[], incoming: WellLogTrack[]): WellLogTrack[] {
    const incomingById = new Map(incoming.map((track) => [track.trackId, track]));
    const preserved = current
        .map((track) => incomingById.get(track.trackId))
        .filter((track): track is WellLogTrack => Boolean(track));
    const preservedIds = new Set(preserved.map((track) => track.trackId));
    const appended = incoming.filter((track) => !preservedIds.has(track.trackId));
    return reindexTracksInCurrentOrder([...preserved, ...appended]);
}

export function preserveSelectionAcrossCanonicalRefresh(
    current: SelectionRef,
    incoming: WellLogTrack[],
    backendSelectedTrackUid: string | null,
): SelectionRef {
    const selectedTrack = incoming.find((track) => track.trackId === current.trackId);
    if (selectedTrack) {
        if (
            current.kind === 'curve'
            && selectedTrack.trackType === 'curve'
            && selectedTrack.curves.some((assignment) => assignment.assignmentId === current.assignmentId)
        ) {
            return current;
        }
        return { kind: 'track', trackId: selectedTrack.trackId };
    }

    if (backendSelectedTrackUid) {
        const backendTrack = incoming.find((track) => track.trackId === backendSelectedTrackUid);
        if (backendTrack) return { kind: 'track', trackId: backendTrack.trackId };
    }

    return { kind: 'track', trackId: incoming[0]?.trackId ?? '' };
}

function reindexTracksInCurrentOrder(tracks: WellLogTrack[]): WellLogTrack[] {
    return tracks.map((track, index) => ({ ...track, trackIndex: index }));
}


// WLV-WDV-CURVE-INVENTORY-RESIZE-1
// Keep the current WDV curve inventory width as the minimum/default and allow
// the user to widen it to the right without changing backend/session state.
const CURVE_INVENTORY_DEFAULT_WIDTH_PX = 300;

const CURVE_INVENTORY_MIN_WIDTH_PX = CURVE_INVENTORY_DEFAULT_WIDTH_PX;

const CURVE_INVENTORY_MAX_WIDTH_PX = 680;

type CurveInventoryResizeState = {
    startX: number;
    startWidth: number;
};

type CompleteLasPlanCurve = {
    managed_curve_uid: string;
    mnemonic: string;
    display_name: string;
    unit?: string | null;
    source_curve_position: number;
    review_required: boolean;
    selectable: boolean;
    loaded_to_wdv: boolean;
};

type CompleteLasPlan = {
    contract_kind: 'wdv_complete_las_reconstruction_plan';
    managed_well_uid: string;
    source_id: string;
    original_filename: string;
    curve_count: number;
    eligible_curve_count: number;
    review_curve_count: number;
    curves: CompleteLasPlanCurve[];
    warnings: string[];
};

type CompleteLasLoadResponse = {
    plan: CompleteLasPlan;
    loaded_product_ids: string[];
    added_managed_curve_uids: string[];
    skipped_existing_managed_curve_uids: string[];
    session: RawCanonicalSession;
};

type CompleteLasSourceOption = {
    sourceId: string;
    label: string;
    curveCount: number;
    assetAvailable?: boolean;
};

type CompleteLasSourceListResponse = {
    managed_well_uid: string;
    sources: Array<{
        source_id: string;
        label: string;
        original_filename: string;
        curve_count: number;
        asset_available: boolean;
    }>;
};

type LogImageSourceOption = {
    sourceId: string;
    label: string;
    fileFormat?: string | null;
};

type LogImageSourceListResponse = {
    managed_well_uid: string;
    sources: Array<{
        source_id: string;
        label: string;
        original_filename: string;
        file_format?: string | null;
    }>;
};

type ManagedFormationTopItem = {
    product_id?: string;
    display_name?: string;
    product_subgroup_key?: string;
    curve_type?: string;
    provenance?: {
        dataset_status?: string;
        formation_tops?: Array<{
            group?: string;
            marker_name?: string;
            marker_type?: string;
            md_m_rt?: number;
            pick_status?: string;
        }>;
    };
};

type ManagedWellFormationTopResponse = {
    managed_well_id?: string;
    product_groups?: Array<{
        items?: Array<ManagedFormationTopItem & {
            product_id?: string;
            display_name?: string;
            product_subgroup_key?: string;
            run_interval?: string;
            run_number?: string;
            depth_start?: number;
            depth_end?: number;
            depth_units?: string;
            provenance?: ManagedFormationTopItem['provenance'] & {
                image_type?: string;
                description_intervals?: Array<unknown>;
                source_label?: string;
                completion_components?: Array<{
                    component_id?: string;
                    canonical_id?: string;
                    canonical_component_key?: string;
                    kr_instruction_id?: string;
                    kr_version?: string;
                    component_type?: string;
                    label?: string;
                    top_md?: number;
                    base_md?: number | null;
                    depth_unit?: string;
                    diameter?: number | null;
                    status?: string | null;
                    source_document?: string | null;
                    source_reference?: string | null;
                    confidence?: string | null;
                    notes?: string | null;
                }>;
            };
        }>;
    }>;
};

type ManagedLithologyItem = {
    product_id?: string;
    display_name?: string;
    product_subgroup_key?: string;
    curve_type?: string;
    provenance?: {
        dataset_status?: string;
        lithology_intervals?: Array<{
            lithology?: string; canonical_lithology?: string;
            top_md?: number; base_md?: number;
            depth_unit?: string; depth_reference?: string;
            pattern_id?: string; background_color?: string; pattern_color?: string;
            description?: string; confidence?: string;
        }>;
    };
};


const COMPLETION_CANONICAL_IDS = new Set<CompletionComponentRecord['canonicalId']>([
    'completion.tubing',
    'completion.casing',
    'completion.liner',
    'completion.screen',
    'completion.open_hole',
    'completion.perforations',
    'completion.packer',
    'completion.safety_valve',
    'completion.downhole_valve',
    'completion.sliding_sleeve',
    'completion.gas_lift',
    'completion.icd_aicd',
    'completion.bridge_plug',
    'completion.retainer',
    'completion.cement_barrier',
]);

function resolveCompletionCanonicalId(raw: {
    canonical_id?: string;
    canonical_component_key?: string;
    component_type?: string;
    label?: string;
}): CompletionComponentRecord['canonicalId'] | null {
    const explicit = String(raw.canonical_id || '').trim() as CompletionComponentRecord['canonicalId'];
    if (COMPLETION_CANONICAL_IDS.has(explicit)) return explicit;

    // Read-only migration compatibility for datasets published before KR canonical
    // identity became authoritative. New publication no longer writes component_type.
    const legacyType = String(raw.component_type || '').trim().toLowerCase();
    const label = String(raw.label || '').trim().toLowerCase();
    if (legacyType === 'tubing') return 'completion.tubing';
    if (legacyType === 'open_hole') return 'completion.open_hole';
    if (legacyType === 'perforations') return 'completion.perforations';
    if (legacyType === 'packer') return 'completion.packer';
    if (legacyType === 'liner_screen') return /screen/.test(label) ? 'completion.screen' : 'completion.liner';
    if (legacyType === 'valve') {
        if (/safety|sssv|scssv|dhsv/.test(label)) return 'completion.safety_valve';
        if (/sliding|sleeve|\bssd\b/.test(label)) return 'completion.sliding_sleeve';
        if (/gas.?lift/.test(label)) return 'completion.gas_lift';
        if (/\baicd\b|\bicd\b|inflow.?control/.test(label)) return 'completion.icd_aicd';
        return 'completion.downhole_valve';
    }
    if (legacyType === 'plug') {
        return /retainer|ezsv/.test(label) ? 'completion.retainer' : 'completion.bridge_plug';
    }
    if (legacyType === 'other') {
        if (/cement/.test(label)) return 'completion.cement_barrier';
        if (/casing/.test(label)) return 'completion.casing';
    }
    return null;
}

type ParsedManagedWellOverlayDatasets = {
    formationTopDatasets: FormationTopDataset[];
    lithologyIntervalDatasets: LithologyIntervalDataset[];
    coreImageItems: CoreImageInventoryItem[];
    completionComponents: CompletionComponentRecord[];
};

function parseManagedWellOverlayDatasets(record: ManagedWellFormationTopResponse): ParsedManagedWellOverlayDatasets {
    const formationTopDatasets: FormationTopDataset[] = [];
    for (const group of record.product_groups ?? []) {
        for (const item of group.items ?? []) {
            if (item.product_subgroup_key !== 'formation_tops') continue;
            const datasetId = item.product_id || item.display_name || `formation-tops-${formationTopDatasets.length + 1}`;
            const markers = (item.provenance?.formation_tops ?? [])
                .filter((marker) => typeof marker.md_m_rt === 'number' && Boolean(marker.marker_name))
                .map((marker, index): FormationTopMarker => ({
                    markerId: `${datasetId}:${index}:${String(marker.marker_name)}`,
                    datasetId,
                    datasetLabel: item.display_name || 'Formation Tops',
                    group: marker.group || '',
                    markerName: marker.marker_name || `Marker ${index + 1}`,
                    markerType: marker.marker_type || 'Formation top',
                    md: Number(marker.md_m_rt),
                    pickStatus: marker.pick_status || item.provenance?.dataset_status || item.curve_type || 'Unknown',
                }))
                .sort((left, right) => left.md - right.md || left.markerName.localeCompare(right.markerName));
            if (markers.length === 0) continue;
            formationTopDatasets.push({
                datasetId,
                datasetLabel: item.display_name || 'Formation Tops',
                status: item.provenance?.dataset_status || item.curve_type || 'Unknown',
                markers,
            });
        }
    }

    const lithologyIntervalDatasets: LithologyIntervalDataset[] = [];
    for (const group of record.product_groups ?? []) {
        for (const rawItem of group.items ?? []) {
            const item = rawItem as unknown as ManagedLithologyItem;
            if (item.product_subgroup_key !== 'lithology_intervals') continue;
            const datasetId = item.product_id || item.display_name || `lithology-${lithologyIntervalDatasets.length + 1}`;
            const intervals = (item.provenance?.lithology_intervals ?? [])
                .filter((interval) => typeof interval.top_md === 'number' && typeof interval.base_md === 'number' && Boolean(interval.lithology))
                .map((interval, index): LithologyIntervalRecord => ({
                    intervalId: `${datasetId}:${index}:${interval.top_md}:${interval.base_md}`,
                    datasetId,
                    datasetLabel: item.display_name || 'Lithology Intervals',
                    lithology: interval.lithology || `Lithology ${index + 1}`,
                    canonicalLithology: interval.canonical_lithology || '',
                    topMd: Number(interval.top_md),
                    baseMd: Number(interval.base_md),
                    depthUnit: interval.depth_unit || 'm',
                    depthReference: interval.depth_reference || 'MD',
                    // Published KR swatches are authoritative. Prefer the canonical
                    // catalogue entry and retain pattern_id only for legacy records.
                    patternId: interval.canonical_lithology || interval.pattern_id || '',
                    // Preserve published interval metadata without inventing colours.
                    // Rendering resolves foreground/background from the KR entry.
                    backgroundColor: interval.background_color || '',
                    patternColor: interval.pattern_color || '',
                    description: interval.description || '',
                    confidence: interval.confidence || '',
                }))
                .sort((left, right) => left.topMd - right.topMd || left.baseMd - right.baseMd);
            if (intervals.length === 0) continue;
            lithologyIntervalDatasets.push({
                datasetId,
                datasetLabel: item.display_name || 'Lithology Intervals',
                status: item.provenance?.dataset_status || item.curve_type || 'Reviewed',
                intervals,
            });
        }
    }

    const coreImageItems: CoreImageInventoryItem[] = [];
    for (const group of record.product_groups ?? []) {
        for (const item of group.items ?? []) {
            if (item.product_subgroup_key !== 'compound_core_segment') continue;
            if (!item.product_id || typeof item.depth_start !== 'number' || typeof item.depth_end !== 'number') continue;
            const managedWellId = record.managed_well_id || '';
            coreImageItems.push({
                productId: item.product_id,
                managedWellId,
                label: item.display_name || item.run_number || 'Core Image',
                topMd: Number(item.depth_start),
                baseMd: Number(item.depth_end),
                depthUnit: item.depth_units || 'm',
                imageType: item.provenance?.image_type || 'core image',
                descriptionCount: Array.isArray(item.provenance?.description_intervals) ? item.provenance.description_intervals.length : 0,
                descriptions: (Array.isArray(item.provenance?.description_intervals)
                    ? item.provenance.description_intervals
                    : []
                ).flatMap((rawDescription, index) => {
                    if (!rawDescription || typeof rawDescription !== 'object') return [];
                    const raw = rawDescription as Record<string, unknown>;
                    const md = Number(
                        raw.top_depth
                        ?? raw.top_md
                        ?? raw.depth_md
                    );
                    const text = String(raw.text ?? '').trim();
                    if (!Number.isFinite(md) || !text) return [];
                    return [{
                        descriptionId: String(
                            raw.description_id
                            ?? `${item.product_id}:description:${index}`
                        ),
                        md,
                        text,
                        category: String(
                            raw.category ?? 'core_description'
                        ),
                    }];
                }),
                runNumber: item.run_number || null,
                sourceLabel: item.provenance?.source_label || 'Core Image Manager',
                imageUrl: `/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}/core-segment-image?product_id=${encodeURIComponent(item.product_id)}`,
                chunkManifestUrl: `/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}/core-segment-display-chunks?product_id=${encodeURIComponent(item.product_id)}`,
            });
        }
    }
    coreImageItems.sort((a, b) => a.topMd - b.topMd || a.baseMd - b.baseMd || a.label.localeCompare(b.label));

    const completionComponents: CompletionComponentRecord[] = [];
    for (const group of record.product_groups ?? []) {
        for (const item of group.items ?? []) {
            if (item.product_subgroup_key !== 'completion_components') continue;
            const datasetId = item.product_id || 'completion-components';
            const datasetLabel = item.display_name || 'Completion Components';
            for (const [index, raw] of (item.provenance?.completion_components ?? []).entries()) {
                const canonicalId = resolveCompletionCanonicalId(raw);
                const label = String(raw.label || '').trim();
                const topMd = Number(raw.top_md);
                const baseCandidate = raw.base_md;
                const baseMd = baseCandidate === null || baseCandidate === undefined
                    ? null
                    : Number(baseCandidate);
                if (!canonicalId || !label || !Number.isFinite(topMd)) continue;
                const componentKey = String(raw.canonical_component_key || canonicalId.replace('completion.', '')).trim();
                completionComponents.push({
                    componentId: String(raw.component_id || `${datasetId}:${index}:${canonicalId}:${topMd}`),
                    datasetId,
                    datasetLabel,
                    canonicalId,
                    componentKey,
                    krInstructionId: raw.kr_instruction_id ? String(raw.kr_instruction_id) : null,
                    krVersion: raw.kr_version ? String(raw.kr_version) : null,
                    label,
                    topMd,
                    baseMd: baseMd !== null && Number.isFinite(baseMd) ? baseMd : null,
                    depthUnit: String(raw.depth_unit || item.depth_units || 'm'),
                    diameter: typeof raw.diameter === 'number' && Number.isFinite(raw.diameter) ? raw.diameter : null,
                    status: raw.status ? String(raw.status) : null,
                    sourceDocument: raw.source_document ? String(raw.source_document) : null,
                    sourceReference: raw.source_reference ? String(raw.source_reference) : null,
                    confidence: raw.confidence ? String(raw.confidence) : null,
                    notes: raw.notes ? String(raw.notes) : null,
                });
            }
        }
    }
    completionComponents.sort((a, b) => a.topMd - b.topMd || (a.baseMd ?? a.topMd) - (b.baseMd ?? b.topMd) || a.label.localeCompare(b.label));
    return { formationTopDatasets, lithologyIntervalDatasets, coreImageItems, completionComponents };
}

function reconcilePersistedLithologySelectionIds(
    persistedIds: Iterable<string>,
    intervals: LithologyIntervalRecord[],
): Set<string> {
    const persisted = Array.from(persistedIds);
    if (persisted.length === 0 || intervals.length === 0) return new Set<string>();

    const exactIds = new Set(intervals.map((interval) => interval.intervalId));
    const currentByGeometry = new Map<string, string>();
    const currentByDataset = new Map<string, LithologyIntervalRecord[]>();

    for (const interval of intervals) {
        currentByGeometry.set(
            `${interval.datasetId}:${interval.topMd}:${interval.baseMd}`,
            interval.intervalId,
        );
        const bucket = currentByDataset.get(interval.datasetId) ?? [];
        bucket.push(interval);
        currentByDataset.set(interval.datasetId, bucket);
    }

    const resolved = new Set<string>();
    const legacyByDataset = new Map<string, Array<{ index: number; top: string; base: string }>>();

    for (const persistedId of persisted) {
        if (exactIds.has(persistedId)) resolved.add(persistedId);

        const match = persistedId.match(/^(.*):(\d+):([^:]+):([^:]+)$/);
        if (!match) continue;
        const [, datasetId, rawIndex, top, base] = match;
        const index = Number(rawIndex);
        if (!Number.isInteger(index) || index < 0) continue;

        const bucket = legacyByDataset.get(datasetId) ?? [];
        bucket.push({ index, top, base });
        legacyByDataset.set(datasetId, bucket);

        const remapped = currentByGeometry.get(`${datasetId}:${top}:${base}`);
        if (remapped) resolved.add(remapped);
    }

    for (const [datasetId, legacy] of legacyByDataset.entries()) {
        const current = currentByDataset.get(datasetId) ?? [];
        if (legacy.length === 0 || current.length === 0) continue;

        const uniqueIndices = Array.from(new Set(legacy.map((entry) => entry.index))).sort((a, b) => a - b);
        const representedEntireLegacyDataset =
            uniqueIndices.length === legacy.length
            && uniqueIndices[0] === 0
            && uniqueIndices.every((value, index) => value === index);

        if (representedEntireLegacyDataset) {
            for (const interval of current) resolved.add(interval.intervalId);
        }
    }

    return resolved;
}

type WdvWorkspaceState = {
    workspace_id: string;
    revision: number;
    active_managed_well_id?: string | null;
    active_managed_well_uid?: string | null;
    common_depth_unit: 'm' | 'ft';
    loaded_wells: WdvWorkspaceLoadedWell[];
    updated_at?: string | null;
};

function clampCurveInventoryWidth(widthPx: number): number {
    return Math.max(CURVE_INVENTORY_MIN_WIDTH_PX, Math.min(CURVE_INVENTORY_MAX_WIDTH_PX, Math.round(widthPx)));
}

// ---------------------------------------------------------------------------
// Canonical session raw types and conversion helpers (C2 Defect B)
//
// These types mirror the backend WdvCanonicalSession / WdvCanonicalTrack /
// WdvCanonicalAssignment shapes as returned by the canonical GET and command
// endpoints.  They are intentionally minimal — only the fields consumed by
// frontendTracksFromCanonicalSession.
//
// Using the raw JSON shape (snake_case) avoids requiring the full V21 parse
// pipeline (which requires CurveCatalogItemV21[] for assignment validation)
// and works directly with the legacy CurveCatalogItem catalog that is already
// available inside WdvPageBoundary.
// ---------------------------------------------------------------------------

/** @internal exported for unit tests */
export interface RawCanonicalAssignment {
  assignment_uid: string;
  managed_curve_uid: string;
  managed_product_uid: string;
  managed_well_uid: string;
  managed_source_uid: string;
  observed_mnemonic: string;
  normalized_mnemonic?: string | null;
  display_name: string;
  curve_family?: string | null;
  stack_index: number;
  visible: boolean;
  scale_min: number | null;
  scale_max: number | null;
  scale_min_label?: string | null;
  scale_max_label?: string | null;
  scale_ticks?: Array<{
    value: number;
    label: string;
    normalized_position: number;
  }>;
  scale_type: string | null;
  scale_direction: string | null;
  color: string | null;
  line_visible?: boolean | null;
  line_width?: number | null;
  line_style?: 'solid' | 'dash' | 'dot' | null;
  line_opacity?: number | null;
  unit: string | null;
  clip_to_track?: boolean | null;
  display_policy_source:
    | 'curve'
    | 'family'
    | 'system_default'
    | 'user_override'
    | null;
  display_review_required: boolean;
  display_warning_code: string | null;
  display_warning_message: string | null;
  range_override_mode?: 'governed' | 'manual' | 'fit_to_curve' | 'fit_to_curve_p05_p95' | 'fit_to_curve_p01_p99';
  manual_scale_min?: number | null;
  manual_scale_max?: number | null;
  effective_range_source?: 'governed' | 'manual' | 'fit_to_curve' | 'fit_to_curve_p05_p95' | 'fit_to_curve_p01_p99';
  override_warning_code?: string | null;
  override_warning_message?: string | null;
  range_edit_step?: number;
  range_edit_precision?: number;
}

/** @internal exported for unit tests */
export interface RawCanonicalTrack {
  track_uid: string;
  managed_well_uid: string;
  track_key?: string | null;
  track_name: string;
  track_type: string;
  width_px?: number | null;
  lattice?: string | null;
  lattice_source?: string | null;
  lattice_override?: boolean | null;
  scale_mode?: string | null;
  depth_basis?: string | null;
  renderer_type?: string | null;
  track_role?: string | null;
  core_base_color?: string | null;
  core_brightness?: number | null;
  core_shading_mode?: 'flat' | 'cylindrical' | null;
  core_shading_strength?: number | null;
  core_description_overlay_enabled?: boolean | null;
  core_description_overlay_position?: 'left' | 'right' | null;
  core_description_overlay_width_pct?: number | null;
  core_description_overlay_font_size?: number | null;
  core_description_overlay_show_md?: boolean | null;
  completion_schematic_position?: 'left' | 'center' | 'right' | null;
  completion_schematic_width_px?: number | null;
  completion_symbol_scale?: number | null;
  completion_line_weight?: number | null;
  completion_show_labels?: boolean | null;
  completion_label_position?: 'left' | 'right' | 'auto' | null;
  completion_label_font_size?: number | null;
  completion_label_offset_px?: number | null;
  completion_label_vertical_offset_px?: number | null;
  completion_label_max_width_px?: number | null;
  completion_label_collision_mode?: 'auto' | 'off' | null;
  completion_label_wrap?: boolean | null;
  depth_range_locator_enabled?: boolean | null;
  depth_range_locator_source_track_uid?: string | null;
  depth_range_locator_mode?: 'content_extent' | 'viewport_extent' | 'auto' | null;
  depth_range_locator_presentation?: 'edge_arrows' | 'wall_bar' | 'data_bar' | null;
  depth_range_locator_side?: 'auto' | 'left' | 'right' | null;
  macro_core_image_enabled?: boolean | null;
  macro_core_image_top_md?: number | null;
  macro_core_image_base_md?: number | null;
  macro_core_image_placement?: 'left' | 'center' | 'right' | null;
  macro_core_image_horizontal_offset_px?: number | null;
  text_overlays?: Array<{
    overlay_uid: string;
    text?: string | null;
    content_html?: string | null;
    md: number;
    horizontal_anchor: 'left' | 'center' | 'right';
    horizontal_offset: number;
    vertical_offset: number;
    width_percent?: number | null;
    font_size: number;
    color: string;
    background: 'none' | 'light';
    text_align?: 'left' | 'center' | 'right' | null;
  }> | null;
  assignments: RawCanonicalAssignment[];
}

/** @internal exported for unit tests */
export interface RawCanonicalSession {
  revision: number;
  state_status: 'empty' | 'active' | 'cleared';
  selected_track_uid: string | null;
  tracks: RawCanonicalTrack[];
  curve_fills?: CanonicalCurveFillRuleV2[];
}

const COMPLETE_LAS_CANONICAL_PALETTE = [
  '#2f80ed',
  '#27ae60',
  '#f2994a',
  '#eb5757',
  '#9b51e0',
  '#00a6a6',
  '#f2c94c',
] as const;

function completeLasFallbackColor(track: RawCanonicalTrack): string | null {
  if (track.track_role !== 'las_source_curve') return null;
  const match = /^las:[^:]+:(\d+)$/.exec(track.track_key ?? '');
  if (!match) return null;
  const sourcePosition = Number.parseInt(match[1], 10);
  if (!Number.isFinite(sourcePosition) || sourcePosition < 1) return null;
  return COMPLETE_LAS_CANONICAL_PALETTE[(sourcePosition - 1) % COMPLETE_LAS_CANONICAL_PALETTE.length];
}

/** Regex matching any variant-4 UUID (v4/v5/v7, etc.) — used to gate
 *  canonical commands to tracks/assignments that carry server-issued UUIDs.
 * @internal exported for unit tests */
const _UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** @internal exported for unit tests */
export function looksLikeUuid(value: string): boolean {
  return _UUID_RE.test(value);
}

/**
 * Build the payload for a canonical session mutation.
 *
 * command_id is intentionally omitted. The backend accepts it as optional,
 * but when supplied it must be a canonical UUIDv7. The previous frontend
 * timestamp/random token was not a UUID and caused every canonical delete
 * and assignment toggle command to fail request validation.
 */
export function canonicalAssignmentUpdateCommandBody(
  assignment: CurveAssignment,
  patch: Partial<CurveAssignment>,
): Record<string, unknown> | null {
  const body: Record<string, unknown> = {};

  if (patch.scaleDirection !== undefined) {
    body.scale_direction = patch.scaleDirection === 'reverse' ? 'reversed' : 'normal';
  }
  if (patch.scaleType !== undefined) {
    body.scale_type = patch.scaleType === 'log' ? 'logarithmic' : 'linear';
  }

  const directFields: Array<
    [keyof CurveAssignment, string]
  > = [
    ['color', 'color'],
    ['lineVisible', 'line_visible'],
    ['lineStyle', 'line_style'],
    ['lineWidth', 'line_width'],
    ['lineOpacity', 'line_opacity'],
    ['positionAnchor', 'position_anchor'],
    ['horizontalOffsetPct', 'horizontal_offset_pct'],
    ['clipToTrack', 'clip_to_track'],
    ['fillSide', 'fill_side'],
    ['fillColor', 'fill_color'],
    ['fillOpacity', 'fill_opacity'],
    ['infillSource', 'infill_source'],
    ['infillPattern', 'infill_pattern'],
    ['infillIntervalColumn', 'infill_interval_column'],
    ['displayPriority', 'display_priority'],
    ['showQaqcWarnings', 'show_qaqc_warnings'],
    ['showNullGaps', 'show_null_gaps'],
    ['showOutOfRange', 'show_out_of_range'],
  ];

  directFields.forEach(([frontendKey, backendKey]) => {
    const value = patch[frontendKey];
    if (value !== undefined) {
      body[backendKey] = value;
    }
  });

  if (patch.pairedCurveId !== undefined) {
    if (patch.pairedCurveId) {
      body.paired_managed_curve_uid = patch.pairedCurveId;
      body.clear_paired_managed_curve_uid = false;
    } else {
      body.clear_paired_managed_curve_uid = true;
    }
  }

  const hasRangeIntent =
    patch.rangeOverrideMode !== undefined
    || patch.manualScaleMin !== undefined
    || patch.manualScaleMax !== undefined
    || patch.scaleMin !== undefined
    || patch.scaleMax !== undefined;

  if (!hasRangeIntent) {
    return Object.keys(body).length > 0 ? body : null;
  }

  const scaleChanged =
    patch.scaleMin !== undefined || patch.scaleMax !== undefined;
  const rangeOverrideMode =
    patch.rangeOverrideMode
    ?? (scaleChanged ? 'manual' : assignment.rangeOverrideMode ?? 'governed');

  if (rangeOverrideMode !== 'manual') {
    body.range_override_mode = rangeOverrideMode;
    return body;
  }

  const manualScaleMin =
    patch.manualScaleMin
    ?? patch.scaleMin
    ?? assignment.manualScaleMin
    ?? assignment.scaleMin;
  const manualScaleMax =
    patch.manualScaleMax
    ?? patch.scaleMax
    ?? assignment.manualScaleMax
    ?? assignment.scaleMax;

  if (
    !Number.isFinite(manualScaleMin)
    || !Number.isFinite(manualScaleMax)
    || manualScaleMin === manualScaleMax
  ) {
    throw new Error('Manual curve range requires two distinct finite bounds.');
  }

  body.range_override_mode = 'manual';
  body.manual_scale_min = manualScaleMin;
  body.manual_scale_max = manualScaleMax;
  return body;
}

// Backward-compatible export for existing tests and callers.
export const canonicalRangeOverrideCommandBody =
  canonicalAssignmentUpdateCommandBody;

export { canonicalCommandRequestBody } from './canonicalSessionCommandOrchestrator';

/**
 * Convert a raw canonical session response to the legacy WellLogTrack[] shape
 * that the rest of WdvPageBoundary renders.
 *
 * After this conversion:
 *   track.trackId  === track_uid  (canonical UUID — usable in RemoveTrackCommand)
 *   assignment.assignmentId === assignment_uid  (UUID — usable in RemoveCurveAssignmentCommand)
 *   assignment.curveId      === managed_curve_uid
 *
 * Assignments whose managed_curve_uid cannot be found in the active catalog
 * are silently skipped (the canonical session may reference curves not yet
 * loaded into this viewer session).
 */
function escapeTextBoxLegacyText(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
}

/** @internal exported for unit tests */
export // WDV_CANONICAL_CURVE_LINE_STYLE_PROJECTION_V1_0_1
// Backend-owned curve line-style values are declared in RawCanonicalAssignment
// and projected back into CurveAssignment so canonical reconciliation preserves
// intentional false/zero-style values such as line_visible=false.
function frontendTracksFromCanonicalSession(
  rawSession: RawCanonicalSession,
  catalog: CurveCatalogItem[],
): WellLogTrack[] {
  const result: WellLogTrack[] = [];
  rawSession.tracks.forEach((rawTrack, index) => {
    const trackId = rawTrack.track_uid;
    const trackType = rawTrack.track_type;
    const title = rawTrack.track_name || `Track ${index + 1}`;
    const widthPx =
      typeof rawTrack.width_px === 'number' && rawTrack.width_px > 0
        ? rawTrack.width_px
        : trackType === 'depth' ? 65 : CURVE_TRACK_RESET_WIDTH;
    const depthRangeLocator = rawTrack.depth_range_locator_source_track_uid
      ? {
          enabled: rawTrack.depth_range_locator_enabled === true,
          sourceTrackId: rawTrack.depth_range_locator_source_track_uid,
          mode: rawTrack.depth_range_locator_mode ?? 'auto',
          presentation: rawTrack.depth_range_locator_presentation ?? 'edge_arrows',
          side: rawTrack.depth_range_locator_side ?? 'auto',
        }
      : undefined;
    const depthRangeLocatorFields = depthRangeLocator ? { depthRangeLocator } : {};
    const macroCoreImage = rawTrack.macro_core_image_top_md != null && rawTrack.macro_core_image_base_md != null
      ? {
          enabled: rawTrack.macro_core_image_enabled === true,
          topMd: rawTrack.macro_core_image_top_md,
          baseMd: rawTrack.macro_core_image_base_md,
          placement: rawTrack.macro_core_image_placement ?? 'center',
          horizontalOffsetPx: rawTrack.macro_core_image_horizontal_offset_px ?? 0,
        }
      : undefined;
    const macroCoreImageFields = macroCoreImage ? { macroCoreImage } : {};
    const textOverlays: TextOverlayConfig[] = (rawTrack.text_overlays ?? []).map((item) => ({
      overlayUid: item.overlay_uid,
      contentHtml: item.content_html
        ?? `<div>${escapeTextBoxLegacyText(item.text ?? "Text")}</div>`,
      md: item.md,
      horizontalAnchor: item.horizontal_anchor,
      horizontalOffset: item.horizontal_offset,
      verticalOffset: item.vertical_offset,
      widthPercent: item.width_percent ?? 70,
      fontSize: item.font_size,
      color: item.color,
      background: item.background,
      textAlign: item.text_align ?? "left",
    }));
    const textOverlayFields = textOverlays.length ? { textOverlays } : {};

    if (trackType === 'depth') {
      const db = rawTrack.depth_basis;
      result.push({
        trackId,
        managedWellUid: rawTrack.managed_well_uid,
        ...depthRangeLocatorFields,
        ...macroCoreImageFields,
        ...textOverlayFields,
        trackIndex: index,
        trackType: 'depth',
        title,
        depthBasis: db === 'TVD' || db === 'TVDSS' ? db : 'MD',
        unit: 'm',
        widthPx,
        visible: true,
      });
      return;
    }

    if (
      trackType === 'annotation'
      && rawTrack.renderer_type === 'completion_components'
    ) {
      result.push({
        trackId,
        managedWellUid: rawTrack.managed_well_uid,
        ...depthRangeLocatorFields,
        ...macroCoreImageFields,
        ...textOverlayFields,
        trackIndex: index,
        trackType: 'completion',
        title: rawTrack.track_name || 'Completion',
        widthPx,
        visible: true,
        reservedReason: 'Reviewed MWD Completion Components track',
        rendererType: 'completion_components',
        trackRole: rawTrack.track_role || 'completion_components',
        completionAppearance: {
          schematicPosition:
            rawTrack.completion_schematic_position === 'left'
            || rawTrack.completion_schematic_position === 'right'
              ? rawTrack.completion_schematic_position
              : 'center',
          schematicWidthPx:
            typeof rawTrack.completion_schematic_width_px === 'number'
              ? rawTrack.completion_schematic_width_px
              : 44,
          symbolScale:
            typeof rawTrack.completion_symbol_scale === 'number'
              ? rawTrack.completion_symbol_scale
              : 1,
          lineWeight:
            typeof rawTrack.completion_line_weight === 'number'
              ? rawTrack.completion_line_weight
              : 2,
          showLabels:
            typeof rawTrack.completion_show_labels === 'boolean'
              ? rawTrack.completion_show_labels
              : true,
          labelPosition:
            rawTrack.completion_label_position === 'left'
            || rawTrack.completion_label_position === 'auto'
              ? rawTrack.completion_label_position
              : 'right',
          labelFontSize:
            typeof rawTrack.completion_label_font_size === 'number'
              ? rawTrack.completion_label_font_size
              : 10,
          labelOffsetPx:
            typeof rawTrack.completion_label_offset_px === 'number'
              ? rawTrack.completion_label_offset_px
              : 12,
          labelVerticalOffsetPx:
            typeof rawTrack.completion_label_vertical_offset_px === 'number'
              ? rawTrack.completion_label_vertical_offset_px
              : 0,
          labelMaxWidthPx:
            typeof rawTrack.completion_label_max_width_px === 'number'
              ? rawTrack.completion_label_max_width_px
              : 140,
          labelCollisionMode:
            rawTrack.completion_label_collision_mode === 'off'
              ? 'off'
              : 'auto',
          labelWrap:
            typeof rawTrack.completion_label_wrap === 'boolean'
              ? rawTrack.completion_label_wrap
              : false,
        },
      });
      return;
    }

    if (trackType === 'annotation' && typeof rawTrack.renderer_type === 'string' && rawTrack.renderer_type.startsWith('interval_')) {
      const isDepthInterval=rawTrack.renderer_type==='interval_depth';
      const isCoreDescription=rawTrack.renderer_type==='interval_core_description';
      const isBlankInterval=rawTrack.renderer_type==='interval_blank';
      result.push({
        trackId,
        managedWellUid: rawTrack.managed_well_uid,
        ...depthRangeLocatorFields,
        ...macroCoreImageFields,
        ...textOverlayFields,
        trackIndex:index,
        title:rawTrack.track_name || (
          isDepthInterval
            ? 'MD'
            : isCoreDescription
              ? 'Core Description'
              : isBlankInterval
                ? 'Interval'
                : 'Formation'
        ),
        widthPx,
        visible:true,
        trackType:'interval',
        reservedReason:
          isDepthInterval
            ? 'Interval depth track'
            : isCoreDescription
              ? 'Core Description depth-marker track'
              : isBlankInterval
                ? 'Blank interval track'
                : 'Formation Tops interval track',
        rendererType:rawTrack.renderer_type,
        trackRole:rawTrack.track_role || (
          isDepthInterval
            ? 'interval_depth'
            : isCoreDescription
              ? 'core_description'
              : isBlankInterval
                ? 'interval_blank'
                : 'geological_interval'
        ),
      });
      return;
    }
    if (
      trackType === 'image'
      && rawTrack.renderer_type === 'core_image'
    ) {
      result.push({
        trackId,
        managedWellUid: rawTrack.managed_well_uid,
        ...depthRangeLocatorFields,
        ...macroCoreImageFields,
        ...textOverlayFields,
        trackIndex: index,
        trackType: 'core',
        title: rawTrack.track_name || 'Core',
        widthPx,
        visible: true,
        reservedReason: 'Core image track',
        rendererType: 'core_image',
        trackRole: rawTrack.track_role || 'core_image',
        coreAppearance: {
          baseColor: rawTrack.core_base_color || '#d7d9dd',
          brightness: typeof rawTrack.core_brightness === 'number' ? rawTrack.core_brightness : 1,
          shadingMode: rawTrack.core_shading_mode === 'cylindrical' ? 'cylindrical' : 'flat',
          shadingStrength: typeof rawTrack.core_shading_strength === 'number' ? rawTrack.core_shading_strength : 0.38,
          descriptionPresentationMode:
            rawTrack.core_description_overlay_enabled === true
              ? rawTrack.core_description_overlay_position === 'left'
                ? 'description_left_core_right'
                : 'core_left_description_right'
              : 'core_centered',
          descriptionOverlayWidthPct: typeof rawTrack.core_description_overlay_width_pct === 'number' ? rawTrack.core_description_overlay_width_pct : 42,
          descriptionOverlayFontSize: typeof rawTrack.core_description_overlay_font_size === 'number' ? rawTrack.core_description_overlay_font_size : 10,
          descriptionOverlayShowMd: rawTrack.core_description_overlay_show_md !== false,
        },
      });
      return;
    }

    if (trackType !== 'curve') return;

    const lattice = rawTrack.lattice === 'logarithmic' ? 'logarithmic' : 'linear';
    const ls = rawTrack.lattice_source ?? 'front_curve_default';
    const latticeSource =
      ls === 'user_override' || ls === 'template' ? ls : 'front_curve_default';

    const assignments: CurveAssignment[] = rawTrack.assignments
      .sort((a, b) => a.stack_index - b.stack_index)
      .flatMap((raw, assignIndex) => {
        const exactCurve = catalog.find(
          (item) => item.curveUid === raw.managed_curve_uid,
        );
        const normalizedMnemonic = (
          raw.normalized_mnemonic
          ?? raw.observed_mnemonic
          ?? ''
        ).trim().toUpperCase();
        const semanticCurve = normalizedMnemonic
          ? catalog.find((item) => (
              item.recognised
              && (
                (item.normalizedMnemonic ?? item.observedMnemonic ?? item.mnemonic)
                  .trim()
                  .toUpperCase()
                === normalizedMnemonic
              )
            ))
          : undefined;
        const curve = exactCurve?.recognised
          ? exactCurve
          : semanticCurve ?? exactCurve;

        const fallback = makeCurveAssignment(
          curve ?? {
            curveId: raw.managed_curve_uid,
            curveUid: raw.managed_curve_uid,
            managedWellUid: raw.managed_well_uid,
            managedProductUid: raw.managed_product_uid,
            managedSourceUid: raw.managed_source_uid,
            observedMnemonic: raw.observed_mnemonic,
            normalizedMnemonic: raw.normalized_mnemonic ?? raw.observed_mnemonic,
            mnemonic: raw.observed_mnemonic,
            description: raw.display_name,
            unit: raw.unit ?? '',
            curveClass: 'unknown',
            defaultLattice: raw.scale_type === 'log' || raw.scale_type === 'logarithmic' ? 'logarithmic' : 'linear',
            defaultMin: typeof raw.scale_min === 'number' ? raw.scale_min : 0,
            defaultMax: typeof raw.scale_max === 'number' ? raw.scale_max : 1,
            defaultColor: raw.color ?? '#000000',
            recognised: false,
          },
          assignIndex,
          raw.assignment_uid,
        );
        const sd = raw.scale_direction;
        const st = raw.scale_type;

        if (
          typeof raw.scale_min !== 'number'
          || !Number.isFinite(raw.scale_min)
          || typeof raw.scale_max !== 'number'
          || !Number.isFinite(raw.scale_max)
          || raw.scale_min === raw.scale_max
        ) {
          throw new Error(
            `Canonical WDV assignment ${raw.assignment_uid} for curve `
            + `${raw.managed_curve_uid} is missing a valid backend scale range.`,
          );
        }

        const scaleType =
          st === 'log' || st === 'logarithmic'
            ? 'log'
            : st === 'linear'
              ? 'linear'
              : null;
        if (scaleType === null) {
          throw new Error(
            `Canonical WDV assignment ${raw.assignment_uid} for curve `
            + `${raw.managed_curve_uid} has invalid backend scale type: ${String(st)}.`,
          );
        }

        const scaleDirection =
          sd === 'reverse' || sd === 'reversed'
            ? 'reverse'
            : sd === 'normal'
              ? 'normal'
              : null;
        if (scaleDirection === null) {
          throw new Error(
            `Canonical WDV assignment ${raw.assignment_uid} for curve `
            + `${raw.managed_curve_uid} has invalid backend scale direction: ${String(sd)}.`,
          );
        }

        if (
          scaleType === 'log'
          && (raw.scale_min <= 0 || raw.scale_max <= 0)
        ) {
          throw new Error(
            `Canonical WDV assignment ${raw.assignment_uid} for curve `
            + `${raw.managed_curve_uid} has a non-positive logarithmic backend scale.`,
          );
        }

        const assignment: CurveAssignment = {
          ...fallback,
          assignmentId: raw.assignment_uid,
          curveUid: raw.managed_curve_uid,
          managedWellUid: raw.managed_well_uid,
          managedProductUid: raw.managed_product_uid,
          managedSourceUid: raw.managed_source_uid,
          observedMnemonic: raw.observed_mnemonic,
          normalizedMnemonic: raw.normalized_mnemonic ?? null,
          displayName: raw.display_name,
          curveFamily: raw.curve_family ?? null,
          stackIndex: raw.stack_index,
          visible: raw.visible,
          scaleMin: raw.scale_min,
          scaleMax: raw.scale_max,
          scaleMinLabel: raw.scale_min_label ?? null,
          scaleMaxLabel: raw.scale_max_label ?? null,
          scaleTicks: (raw.scale_ticks ?? []).map((tick) => ({
            value: tick.value,
            label: tick.label,
            normalizedPosition: tick.normalized_position,
          })),
          scaleType,
          scaleDirection,
          color: raw.color ?? completeLasFallbackColor(rawTrack) ?? fallback.color,
          lineVisible:
            typeof raw.line_visible === 'boolean'
              ? raw.line_visible
              : fallback.lineVisible,
          lineWidth:
            typeof raw.line_width === 'number' && Number.isFinite(raw.line_width)
              ? raw.line_width
              : fallback.lineWidth,
          lineStyle:
            raw.line_style === 'solid' ||
            raw.line_style === 'dash' ||
            raw.line_style === 'dot'
              ? raw.line_style
              : fallback.lineStyle,
          lineOpacity:
            typeof raw.line_opacity === 'number' && Number.isFinite(raw.line_opacity)
              ? raw.line_opacity
              : fallback.lineOpacity,
          unit: raw.unit,
          clipToTrack: raw.clip_to_track ?? fallback.clipToTrack,
          displayPolicySource:
            raw.display_policy_source === 'user_override'
              ? null
              : raw.display_policy_source,
          displayReviewRequired: raw.display_review_required,
          displayWarningCode: raw.display_warning_code,
          displayWarningMessage: raw.display_warning_message,
          rangeOverrideMode:
            raw.range_override_mode === 'manual'
            || raw.range_override_mode === 'fit_to_curve'
            || raw.range_override_mode === 'fit_to_curve_p05_p95'
            || raw.range_override_mode === 'fit_to_curve_p01_p99'
              ? raw.range_override_mode
              : 'governed',
          manualScaleMin: raw.manual_scale_min ?? null,
          manualScaleMax: raw.manual_scale_max ?? null,
          effectiveRangeSource:
            raw.effective_range_source === 'manual'
            || raw.effective_range_source === 'fit_to_curve'
            || raw.effective_range_source === 'fit_to_curve_p05_p95'
            || raw.effective_range_source === 'fit_to_curve_p01_p99'
              ? raw.effective_range_source
              : 'governed',
          overrideWarningCode: raw.override_warning_code ?? null,
          overrideWarningMessage: raw.override_warning_message ?? null,
          rangeEditStep:
            typeof raw.range_edit_step === 'number' && raw.range_edit_step > 0
              ? raw.range_edit_step
              : 1,
          rangeEditPrecision:
            typeof raw.range_edit_precision === 'number'
              ? raw.range_edit_precision
              : 0,
        };
        return [assignment];
      });

    result.push({
      trackId,
      managedWellUid: rawTrack.managed_well_uid,
      ...depthRangeLocatorFields,
      ...macroCoreImageFields,
      ...textOverlayFields,
      trackIndex: index,
      trackType: 'curve',
      title:
        assignments.length > 0
          ? assignments
              .map((a) => catalog.find((c) => c.curveUid === a.curveUid)?.mnemonic ?? a.curveId)
              .join(' / ')
          : title,
      widthPx,
      visible: true,
      lattice,
      latticeSource,
      latticeOverride: rawTrack.lattice_override ?? false,
      scaleMode:
        rawTrack.scale_mode === 'shared' ||
        rawTrack.scale_mode === 'dual' ||
        rawTrack.scale_mode === 'normalized'
          ? rawTrack.scale_mode
          : 'per_curve',
      curves: assignments,
    });
  });
  return result;
}

/**
 * Resolve the well that owns a canvas selection. The shared depth ruler is
 * deliberately canvas-owned and never changes the active Curve Inventory well.
 */
export function managedWellUidForCanvasSelection(
  tracks: WellLogTrack[],
  selection: SelectionRef,
): string | null {
  const track = tracks.find((item) => item.trackId === selection.trackId);
  if (!track || track.trackType === 'depth') return null;
  if (selection.kind === 'curve' && track.trackType === 'curve') {
    const assignment = track.curves.find((item) => item.assignmentId === selection.assignmentId);
    return assignment?.managedWellUid ?? track.managedWellUid ?? null;
  }
  return track.managedWellUid ?? null;
}

export interface WdvPageBoundaryProps {
  managedViewerWell: ManagedWellIdentity | null;
  setManagedViewerWell: Dispatch<SetStateAction<ManagedWellIdentity | null>>;
  onOpenWellbore3D(): void;
  supplementalWellInfoMetadata?: WellInfoSessionMetadata;
}




const WDV_QV_SHARED_HEADER_TEXT_STYLE = {
    margin: 0,
    color: '#dfe6f1',
    fontSize: 11,
    fontWeight: 720,
    letterSpacing: '0.115em',
    lineHeight: 1,
    textTransform: 'uppercase' as const,
};

const QUICK_VIEW_INVENTORY_COLORS = [
  '#7CFC00',
  '#45D6FF',
  '#FF4FD8',
  '#FFD84D',
  '#FF9F43',
  '#C084FC',
  '#7EE7C1',
  '#FF7A7A',
  '#5EA2FF',
  '#B9E769',
] as const;





function cleanQuickViewCurveDescription(raw: string | null | undefined): string {
    return String(raw || '')
        .replace(/\s*\{\s*[A-Z]\d+(?:\.\d+)?\s*\}\s*/gi, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function quickViewScaleStatus(curve: QuickViewCurve): string {
    const catalogue = String((curve as any).catalogue_status || '').trim();
    const decision = String((curve as any).scale_decision || '').trim();
    if (catalogue && decision) return `${catalogue} · ${decision}`;
    const scaleSource = String((curve as any).scale_source || '').toLowerCase();
    if (scaleSource.includes('managed_knowledge_curve_rule') || scaleSource.includes('governed')) return 'KR exact · Governed';
    if (scaleSource.includes('resistivity_log')) return 'Unit domain · Unit-log fallback';
    if (scaleSource.includes('fallback_unit_domain')) return 'Unit domain · Unit-linear fallback';
    return 'Unknown · Generic fallback';
}

function quickViewInventoryDescription(curve: QuickViewCurve, fallback: string): string {
    const cleaned = cleanQuickViewCurveDescription(curve.description || fallback || curve.mnemonic);
    return `${cleaned || curve.mnemonic} · ${quickViewScaleStatus(curve)}`;
}


function quickViewMetaDisplay(value: QuickViewMetadataValue | undefined | null, fallback = 'Not supplied'): string {
    if (!value || value.value === null || value.value === undefined || value.value === '') return fallback;
    const rendered = typeof value.value === 'boolean' ? (value.value ? 'Yes' : 'No') : String(value.value);
    return value.unit ? `${rendered} ${value.unit}` : rendered;
}

const QUICK_VIEW_HEADER_PLACEHOLDERS = new Set([
    'WELL',
    'FIELD',
    'COMPANY',
    'COUNTRY',
    'STATE',
    'COUNTY',
    'COUNTRY / STATE / COUNTY',
    'UNIQUE WELL ID / API NUMBER',
    'UNIQUE WELL ID',
    'API NUMBER',
]);

function quickViewIsHeaderPlaceholder(value: string): boolean {
    const normalized = value.trim().replace(/\s+/g, ' ').toUpperCase();
    return QUICK_VIEW_HEADER_PLACEHOLDERS.has(normalized);
}

function quickViewWellMetaDisplay(value: QuickViewMetadataValue | undefined | null): string {
    const rendered = quickViewMetaDisplay(value, 'Not available');
    if (rendered === 'Not supplied') return 'Not available';
    return quickViewIsHeaderPlaceholder(rendered) ? 'Not available' : rendered;
}

function quickViewCompactRange(pkg: QuickViewPackage): string {
    const index = pkg.quick_view_metadata?.curve_info.index;
    if (!index) {
        const unit = pkg.depth_unit_label ? ` ${pkg.depth_unit_label}` : '';
        return `${pkg.depth_min.toFixed(0)} – ${pkg.depth_max.toFixed(0)}${unit}`;
    }
    return `${quickViewMetaDisplay(index.start, '—')} – ${quickViewMetaDisplay(index.stop, '—')}`;
}

function quickViewNormalizeEmpty(value: string): string {
    const cleaned = value.trim();
    return cleaned.length ? cleaned : 'Not supplied';
}

function quickViewStatusTone(value: string): 'neutral' | 'ok' | 'warning' | 'error' {
    const normalized = value.toLowerCase();
    if (normalized.includes('error') || normalized.includes('failed')) return 'error';
    if (normalized.includes('warning') || normalized.includes('mismatch')) return 'warning';
    if (normalized.includes('parsed') || normalized.includes('governed')) return 'ok';
    return 'neutral';
}

function quickViewToneColor(tone: 'neutral' | 'ok' | 'warning' | 'error'): string {
    if (tone === 'error') return '#ff9a9a';
    return '#cbd4e1';
}

function QuickViewMetadataRow({ label, value, tone = 'neutral' }: { label: string; value: string; tone?: 'neutral' | 'ok' | 'warning' | 'error' }) {
    return <div
        className="wlv-qv-metadata-row"
        style={{
            display: 'grid',
            gridTemplateColumns: '118px minmax(0, 1fr)',
            columnGap: 8,
            alignItems: 'baseline',
            padding: '2px 0',
            borderBottom: '1px solid rgba(116, 132, 158, 0.09)',
        }}
    >
        <dt style={{ margin: 0, color: '#8f98a8', fontSize: 9.5, fontWeight: 650, letterSpacing: '0.055em', textTransform: 'uppercase' }}>{label}</dt>
        <dd
            className={`wlv-qv-metadata-value wlv-qv-metadata-${tone}`}
            style={{ margin: 0, minWidth: 0, color: quickViewToneColor(tone), fontSize: 10.5, fontWeight: 520, lineHeight: 1.22, overflowWrap: 'anywhere' }}
        >
            {quickViewNormalizeEmpty(value)}
        </dd>
    </div>;
}

function QuickViewMetadataSection({ title, children, meta }: { title: string; children: ReactNode; meta?: string }) {
    return <section
        className="wlv-property-section wlv-qv-metadata-card"
        style={{
            margin: '0 0 7px',
            padding: '8px 10px',
            border: '1px solid rgba(116, 132, 158, 0.24)',
            borderRadius: 7,
            background: 'rgba(12, 15, 20, 0.64)',
        }}
    >
        <div className="wlv-qv-metadata-card-heading" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
            <h3 style={{ margin: 0, color: '#dfe6f1', fontSize: 11, fontWeight: 720, letterSpacing: '0.095em', textTransform: 'uppercase' }}>{title}</h3>
            {meta ? <span style={{ color: quickViewStatusTone(meta) === 'warning' ? '#d8b957' : '#9aa6b8', fontSize: 9.5, fontWeight: 650, letterSpacing: '0.055em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{meta.replace(/_/g, ' ')}</span> : null}
        </div>
        {children}
    </section>;
}

function QuickViewMetadataList({ children }: { children: ReactNode }) {
    return <dl className="wlv-qv-metadata-list" style={{ margin: 0, padding: 0 }}>{children}</dl>;
}

function QuickViewNotice({ children }: { children: ReactNode }) {
    return <div
        className="wlv-property-note wlv-qv-metadata-notice"
        style={{ marginTop: 6, padding: '5px 7px', border: '1px dashed rgba(116, 132, 158, 0.30)', borderRadius: 7, color: '#aeb7c6', fontSize: 10.5, fontWeight: 500, lineHeight: 1.28 }}
    >
        {children}
    </div>;
}

function QuickViewSummaryPill({ label, value, tone = 'neutral' }: { label: string; value: number | string; tone?: 'neutral' | 'ok' | 'warning' | 'error' }) {
    return <span
        className={`wlv-qv-summary-pill wlv-qv-summary-${tone}`}
        style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            gap: 4,
            minWidth: 0,
            padding: '3px 6px',
            border: '1px solid rgba(116, 132, 158, 0.20)',
            borderRadius: 5,
            background: 'rgba(18, 23, 31, 0.54)',
        }}
    >
        <span style={{ color: '#9aa6b8', fontSize: 9.5, fontWeight: 640, letterSpacing: '0.04em', textTransform: 'uppercase', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
        <b style={{ color: quickViewToneColor(tone), fontSize: 10.5, fontWeight: 680 }}>{value}</b>
    </span>;
}

function QuickViewSummaryGroup({ title, children }: { title: string; children: ReactNode }) {
    return <div style={{ marginTop: 6 }}>
        <div style={{ color: '#8f98a8', fontSize: 9.5, fontWeight: 680, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>{title}</div>
        <div className="wlv-qv-summary-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 4 }}>{children}</div>
    </div>;
}

function QuickViewInfoToggle({ collapsed, onToggleCollapsed }: { collapsed: boolean; onToggleCollapsed: () => void }) {
    return <button
        type="button"
        className="wlv-curve-inventory-collapse-toggle wlv-qv-info-collapse-toggle"
        onClick={onToggleCollapsed}
        aria-expanded={!collapsed}
        aria-label={collapsed ? 'Expand Info panel' : 'Collapse Info panel'}
        title={collapsed ? 'Expand Info panel' : 'Collapse Info panel'}
        style={{ position: 'static', width: 28, height: 28, minWidth: 28, minHeight: 28, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0, margin: 0 }}
    >
        {collapsed ? '‹' : '›'}
    </button>;
}

function QuickViewPanelHeaderTitle({ children }: { children: ReactNode }) {
    return <h2
        className="wlv-qv-panel-header-title wlv-qv-shared-header-text"
        style={WDV_QV_SHARED_HEADER_TEXT_STYLE}
    >
        {children}
    </h2>;
}

function QuickViewInfoHeading({ collapsed, onToggleCollapsed }: { collapsed: boolean; onToggleCollapsed: () => void }) {
    if (collapsed) {
        return <div className="wlv-panel-heading wlv-qv-info-heading-collapsed" style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', minHeight: 42, padding: '6px 5px' }}>
            <QuickViewInfoToggle collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />
        </div>;
    }
    return <div className="wlv-panel-heading wlv-qv-info-heading" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, minHeight: 42, padding: '0 10px' }}>
        <QuickViewPanelHeaderTitle>INFO</QuickViewPanelHeaderTitle>
        <QuickViewInfoToggle collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />
    </div>;
}

function QuickViewMetadataPanel({ pkg, collapsed = false, onToggleCollapsed = () => {} }: { pkg: QuickViewPackage; collapsed?: boolean; onToggleCollapsed?: () => void }) {
    const metadata = pkg.quick_view_metadata;
    const totalCurves = pkg.tracks.reduce((count, track) => count + track.curves.length, 0);
    if (!metadata) {
        return <aside className="wlv-right-panel wlv-ready-properties-panel" aria-label="Quick View information" style={{ overflow: 'hidden' }}>
            <QuickViewInfoHeading collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />
            {collapsed ? null : <div className="wlv-ready-properties-copy wlv-qv-metadata-panel" style={{ padding: 8, overflowY: 'auto' }}>
              <QuickViewMetadataSection title="File Info">
                <p className="wlv-qv-source-name" style={{ margin: '0 0 6px', color: '#cbd4e1', fontSize: 10.5, fontWeight: 540, lineHeight: 1.25, overflowWrap: 'anywhere' }}>{pkg.filename}</p>
                <QuickViewMetadataList>
                    <QuickViewMetadataRow label="Type" value={pkg.source_format} />
                    <QuickViewMetadataRow label="Curves" value={`${totalCurves} renderable curves`} />
                </QuickViewMetadataList>
                <QuickViewNotice>Temporary display only. Nothing was added to WSI or WMD.</QuickViewNotice>
              </QuickViewMetadataSection>
            </div>}
          </aside>;
    }
    const file = metadata.file_info;
    const well = metadata.well_info;
    const curve = metadata.curve_info;
    const index = curve.index;
    const fileType = quickViewMetaDisplay(file.file_type, pkg.source_format);
    const fileVersion = quickViewMetaDisplay(file.format_version, '');
    const locationParts = [quickViewWellMetaDisplay(well.country), quickViewWellMetaDisplay(well.state_province), quickViewWellMetaDisplay(well.county_area)].filter((part) => part !== 'Not available');
    const location = locationParts.length ? locationParts.join(' / ') : 'Not available';
    const uwiApiParts = [quickViewWellMetaDisplay(well.uwi), quickViewWellMetaDisplay(well.api)].filter((part) => part !== 'Not available');
    const uwiApi = uwiApiParts.length ? uwiApiParts.join(' / ') : 'Not available';
    const technicalFlags = metadata.early_qaqc.flags.filter((flag) => /wrap|technical|section|encoding|parser/i.test(`${flag.code} ${flag.message}`));
    const qaqcFlags = metadata.early_qaqc.flags.filter((flag) => !technicalFlags.includes(flag));
    return <aside className="wlv-right-panel wlv-ready-properties-panel" aria-label="Quick View information" style={{ overflow: 'hidden' }}>
        <QuickViewInfoHeading collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />
        {collapsed ? null : <div className="wlv-ready-properties-copy wlv-qv-metadata-panel" style={{ padding: 8, overflowY: 'auto' }}>
            <QuickViewMetadataSection title="File Info">
                <p className="wlv-qv-source-name" style={{ margin: '0 0 6px', color: '#cbd4e1', fontSize: 10.5, fontWeight: 540, lineHeight: 1.25, overflowWrap: 'anywhere' }}>{quickViewMetaDisplay(file.source_file_name, pkg.filename)}</p>
                <QuickViewMetadataList>
                    <QuickViewMetadataRow label="Type" value={`${fileType}${fileVersion ? ` ${fileVersion}` : ''}`} />
                    <QuickViewMetadataRow label="Curves" value={`${curve.curve_counts.renderable_curves} rendered / ${curve.curve_counts.total_curves} total`} />
                </QuickViewMetadataList>
                <QuickViewNotice>Temporary display only. Nothing was added to WSI or WMD.</QuickViewNotice>
            </QuickViewMetadataSection>
            <QuickViewMetadataSection title="Well Info">
                <QuickViewMetadataList>
                    <QuickViewMetadataRow label="Well" value={quickViewWellMetaDisplay(well.well_name)} />
                    <QuickViewMetadataRow label="UWI/API" value={uwiApi} />
                    <QuickViewMetadataRow label="Field" value={quickViewWellMetaDisplay(well.field)} />
                    <QuickViewMetadataRow label="Operator" value={quickViewWellMetaDisplay(well.operator)} />
                    <QuickViewMetadataRow label="Location" value={location} />
                </QuickViewMetadataList>
            </QuickViewMetadataSection>
            <QuickViewMetadataSection title="Curve Info">
                <QuickViewMetadataList>
                    <QuickViewMetadataRow label="Index" value={`${quickViewMetaDisplay(index.source_mnemonic, 'Index')} ${quickViewMetaDisplay(index.resolved_unit, '')}`.trim()} />
                    <QuickViewMetadataRow label="Range" value={quickViewCompactRange(pkg)} />
                    <QuickViewMetadataRow label="Step / samples" value={`${quickViewMetaDisplay(index.step, '—')} / ${quickViewMetaDisplay(index.sample_count, '—')}`} />
                    <QuickViewMetadataRow label="Missing units" value={String(curve.curve_counts.curves_missing_units)} tone={curve.curve_counts.curves_missing_units ? 'warning' : 'ok'} />
                </QuickViewMetadataList>
                <QuickViewSummaryGroup title="Recognition">
                    <QuickViewSummaryPill label="Exact" value={curve.recognition_summary.kr_exact} tone="ok" />
                    <QuickViewSummaryPill label="Alias" value={curve.recognition_summary.kr_alias} />
                    <QuickViewSummaryPill label="Family" value={curve.recognition_summary.kr_family} />
                    <QuickViewSummaryPill label="Unit only" value={curve.recognition_summary.unit_domain} />
                    <QuickViewSummaryPill label="Unknown" value={curve.recognition_summary.unknown} tone={curve.recognition_summary.unknown ? 'warning' : 'ok'} />
                </QuickViewSummaryGroup>
                <QuickViewSummaryGroup title="Scaling">
                    <QuickViewSummaryPill label="Governed" value={curve.scaling_summary.governed} tone="ok" />
                    <QuickViewSummaryPill label="KR fallback" value={curve.scaling_summary.kr_known_fallback} />
                    <QuickViewSummaryPill label="Unit fallback" value={curve.scaling_summary.unit_domain_fallback} />
                    <QuickViewSummaryPill label="Generic" value={curve.scaling_summary.generic_fallback} tone={curve.scaling_summary.generic_fallback ? 'warning' : 'ok'} />
                    <QuickViewSummaryPill label="Mismatch" value={curve.scaling_summary.unit_mismatch} tone={curve.scaling_summary.unit_mismatch ? 'warning' : 'ok'} />
                </QuickViewSummaryGroup>
            </QuickViewMetadataSection>
            <QuickViewMetadataSection title="Early QAQC" meta={metadata.early_qaqc.severity.toUpperCase()}>
                {qaqcFlags.length === 0 ? <QuickViewNotice>No QAQC warnings.</QuickViewNotice> : <div className="wlv-qv-qaqc-list" style={{ display: 'grid', gap: 4, marginTop: 2 }}>{qaqcFlags.slice(0, 6).map((flag) => <p key={`${flag.code}:${flag.message}`} className={`wlv-qv-qaqc-flag wlv-qv-qaqc-${flag.severity}`} style={{ margin: 0, padding: '4px 6px', borderRadius: 4, border: '1px solid rgba(116, 132, 158, 0.16)', background: 'rgba(18, 23, 31, 0.42)', color: '#b7c1d0', fontSize: 10.25, fontWeight: 500, lineHeight: 1.22 }}>{flag.message}</p>)}</div>}
                {technicalFlags.length ? <details className="wlv-qv-technical-flags" style={{ marginTop: 6, color: '#9aa6b8', fontSize: 10.25, fontWeight: 500 }}>
                    <summary>Technical parse flags</summary>
                    {technicalFlags.map((flag) => <p style={{ margin: '5px 0 0' }} key={`${flag.code}:${flag.source ?? ''}:${flag.message}`}>{flag.message}</p>)}
                </details> : null}
            </QuickViewMetadataSection>
        </div>}
      </aside>;
}

function QuickViewCurveInventory({ pkg }: { pkg: QuickViewPackage }) {
    const curves = pkg.tracks.flatMap((track, trackIndex) => track.curves.map((curve, curveIndex) => ({
        curve,
        trackTitle: track.title,
        key: `${track.track_id}:${curve.curve_id}:${trackIndex}:${curveIndex}`,
        color: QUICK_VIEW_INVENTORY_COLORS[(trackIndex + curveIndex) % QUICK_VIEW_INVENTORY_COLORS.length],
    })));
    const count = curves.length;

    return (<aside className="wlv-curve-inventory wlv-qv-curve-inventory wlv-qv-curve-inventory-compact">
      <div className="wlv-inventory-control-stack">
        <section className="wlv-inventory-control-section wlv-curve-inventory-section">
          <button type="button" className="wlv-inventory-section-toggle" aria-expanded="true" style={{ minHeight: 42, alignItems: 'center' }}>
            <span className="wlv-qv-shared-header-text" style={WDV_QV_SHARED_HEADER_TEXT_STYLE}>CURVE INVENTORY</span>
            <span className="wlv-inventory-section-toggle-meta">{count}<b>▾</b></span>
          </button>
          <div className="wlv-inventory-section-body wlv-curve-inventory-body">
            <div className="wlv-inventory-list wlv-qv-curve-list-compact">
              {curves.map(({ curve, trackTitle, key, color }) => {
                  const description = quickViewInventoryDescription(curve, trackTitle);
                  return (<div key={key} className="wlv-qv-curve-row-compact" title={description}>
                    <strong style={{ color }}>{curve.mnemonic}</strong>
                    <span>{description}</span>
                  </div>);
              })}
            </div>
          </div>
        </section>
      </div>
    </aside>);
}

export function WdvPageBoundary({ managedViewerWell, setManagedViewerWell, supplementalWellInfoMetadata = {} }: WdvPageBoundaryProps) {
  useEffect(() => installWdvDiagnosticErrorHooks(), []);
  const managedViewerWellId = managedViewerWell?.managedWellId ?? null;
  const managedViewerWellUid = managedViewerWell?.managedWellUid ?? null;
  const activeView = 'log-viewer' as const;
  const [wdvWorkspace, setWdvWorkspace] = useState<WdvWorkspaceState | null>(null);
  const [wdvWorkspaceError, setWdvWorkspaceError] = useState<string | null>(null);
  const [, setViewerPackageLoad] = useState<BackendViewerPackageLoadResult | null>(null);
  const [wdvPackageState, setWdvPackageState] = useState<WdvPackageState>(() => emptyWdvPackageState());
  // Last-good viewer packages are retained per well so changing active well is
  // a focus change, not a destructive canvas rehydration event.
  const viewerPackageStateByWellUidRef = useRef<Record<string, WdvPackageState>>({});
  const [viewerPackageCacheRevision, setViewerPackageCacheRevision] = useState(0);
  const [wdvIdentityMetadata, setWdvIdentityMetadata] = useState<WdvIdentityMetadataContract | null>(null);
  const [wdvIdentityMetadataError, setWdvIdentityMetadataError] = useState<string | null>(null);
  const effectiveWdvIdentityMetadata = useMemo(
    () => overlayWellInfoSessionMetadata(wdvIdentityMetadata, supplementalWellInfoMetadata),
    [wdvIdentityMetadata, supplementalWellInfoMetadata],
  );
  const [managedSamplesByCurveId, setManagedSamplesByCurveId] = useState<ManagedCurveSamplesByCurveId>({});
  const [managedSampleContractsByCurveId, setManagedSampleContractsByCurveId] = useState<ManagedCurveSampleContractsByCurveId>({});
  const [managedSampleErrorsByCurveId, setManagedSampleErrorsByCurveId] = useState<Record<string, string>>({});
  const [managedSamplesLoading, setManagedSamplesLoading] = useState(false);
  const [rightPropertiesCollapsed, setRightPropertiesCollapsed] = useState(false);
  const [wbvPublishBusy, setWbvPublishBusy] = useState(false);
  const [wbvPublishMessage, setWbvPublishMessage] = useState<string | null>(null);
  const [wbvPublishPanelOpen, setWbvPublishPanelOpen] = useState(false);
  const [wbvPublishedPackages, setWbvPublishedPackages] = useState<WbvOverlayPackage[]>([]);
  const [recommendationRefreshRevision, setRecommendationRefreshRevision] = useState(0);
  const [viewerPackageRefreshRevision, setViewerPackageRefreshRevision] = useState(0);
  const viewerPackageAbortRef = useRef<AbortController | null>(null);
  const viewerPackageGenerationRef = useRef(0);
  const sampleCacheRef = useRef<Map<string, ManagedCurveSampleLoadResult>>(new Map());
  const sampleInflightRef = useRef<Map<string, Promise<ManagedCurveSampleLoadResult>>>(new Map());
  const requiredSampleKeysRef = useRef<Set<string>>(new Set());
  const sampleDepthUnitRef = useRef<string | null>(null);
  const recommendationAbortRef = useRef<AbortController | null>(null);
  const recommendationGenerationRef = useRef(0);
  const activeWellSwitchAbortRef = useRef<AbortController | null>(null);
  const activeWellSwitchTargetRef = useRef<string | null>(null);
  // WLV-WDV-REBUILD-1: WMDP load creates WDV availability only.
  // It must not auto-populate visible well-log tracks.
  useEffect(() => {
      viewerPackageAbortRef.current?.abort();
      const controller = new AbortController();
      viewerPackageAbortRef.current = controller;
      const generation = viewerPackageGenerationRef.current + 1;
      viewerPackageGenerationRef.current = generation;
      if (activeView !== 'log-viewer') {
          return () => controller.abort();
      }
      if (!managedViewerWellId) {
          setViewerPackageLoad({
              source: 'prototype_fallback',
              package: null,
              warning: 'No managed well is currently loaded to the Well Data Viewer',
          });
          setWdvPackageState(emptyWdvPackageState());
          return () => controller.abort();
      }

      // WDV_ACTIVE_WELL_FOCUS_SWITCH_STABILIZATION_V1_0_0
      // Never blank a valid viewer package merely because focus moved to a
      // different well. Reuse that well's last-good package immediately while
      // the backend refresh runs, then atomically replace it on success. If this
      // well has not been seen yet, leave the last-good canvas render intact
      // rather than publishing a transient empty package into shared render
      // derivations.
      const cachedPackage = managedViewerWellUid
          ? viewerPackageStateByWellUidRef.current[managedViewerWellUid]
          : undefined;
      if (cachedPackage) setWdvPackageState(cachedPackage);

      void loadBackendViewerPackageWithFallback(managedViewerWellId, { signal: controller.signal })
          .then((result) => {
          if (controller.signal.aborted || viewerPackageGenerationRef.current !== generation)
              return;
          const nextPackageState = buildWdvPackageState(result.package);
          setViewerPackageLoad(result);
          if (managedViewerWellUid) {
              viewerPackageStateByWellUidRef.current = {
                  ...viewerPackageStateByWellUidRef.current,
                  [managedViewerWellUid]: nextPackageState,
              };
              setViewerPackageCacheRevision((current) => current + 1);
          }
          setWdvPackageState(nextPackageState);
      })
          .catch((error) => {
          if (controller.signal.aborted || viewerPackageGenerationRef.current !== generation || isAbortError(error))
              return;
          setViewerPackageLoad({
              source: 'prototype_fallback',
              package: null,
              warning: error instanceof Error ? error.message : 'Viewer package unavailable',
          });
          // Preserve the last-good render package on refresh failure. The
          // warning belongs to the active inventory context; valid background
          // tracks must not be de-hydrated because a focus refresh failed.
      });
      return () => {
          controller.abort();
          if (viewerPackageAbortRef.current === controller)
              viewerPackageAbortRef.current = null;
      };
  }, [activeView, managedViewerWellId, managedViewerWellUid, viewerPackageRefreshRevision]);
  useEffect(() => {
      if (!managedViewerWellUid) {
          setWdvIdentityMetadata(null);
          setWdvIdentityMetadataError(null);
          return undefined;
      }
      const controller = new AbortController();
      setWdvIdentityMetadata(null);
      setWdvIdentityMetadataError(null);
      void fetchWlvJson<unknown>(
          `/api/wlv/v2/viewer-packages/${encodeURIComponent(managedViewerWellUid)}/metadata`,
          { signal: controller.signal },
      )
          .then((payload) => parseWdvIdentityMetadataContract(payload, managedViewerWellUid))
          .then((contract) => {
              if (!controller.signal.aborted) setWdvIdentityMetadata(contract);
          })
          .catch((error) => {
              if (controller.signal.aborted || isAbortError(error)) return;
              setWdvIdentityMetadata(null);
              setWdvIdentityMetadataError(
                  error instanceof Error ? error.message : 'Backend WDV metadata unavailable',
              );
          });
      return () => controller.abort();
  }, [managedViewerWellUid, viewerPackageRefreshRevision]);
  const [tracks, setTracks] = useState<WellLogTrack[]>([]);
  const tracksRef = useRef<WellLogTrack[]>([]);
  useEffect(() => { tracksRef.current = tracks; }, [tracks]);
  const [selection, setSelection] = useState<SelectionRef>({ kind: 'track', trackId: 'track-gr-sp' });
  const selectionRef = useRef<SelectionRef>(selection);
  useEffect(() => { selectionRef.current = selection; }, [selection]);
  const [addTrackCurveSelectionMode, setAddTrackCurveSelectionMode] = useState(false);
  const [pendingAddTrackCurveIds, setPendingAddTrackCurveIds] = useState<string[]>([]);
  const [openCurveMenu, setOpenCurveMenu] = useState<{
      trackId: string;
      assignmentId: string;
  } | null>(null);
  const [curveEditRequest, setCurveEditRequest] = useState<{
    trackId: string;
    assignmentId: string;
    requestId: number;
  } | null>(null);

  const [fullDepthRangesByWellUid, setFullDepthRangesByWellUid] = useState<Record<string, DepthViewRange>>({});
  const {
    viewDepthRange,
    setViewDepthRange,
    combinationActiveTrackIds,
    setCombinationActiveTrackIds,
    combinationLockedTrackIds,
    setCombinationLockedTrackIds,
    multiHighlightedTrackIds,
    setMultiHighlightedTrackIds,
    trackDepthRangesById,
    setTrackDepthRangesById,
    combinationGroupViewRange,
    setCombinationGroupViewRange,
    setCombinationGroupHistory,
    viewportTieGroups,
    setViewportTieGroups,
    viewportTieSuspendedTrackIds,
    setViewportTieSuspendedTrackIds,
    viewportTieHistoryByGroupId,
    setViewportTieHistoryByGroupId,
  } = useViewportRelationshipState(EMPTY_DEPTH_RANGE);
  const restoredSavedWorkspaceKeysRef = useRef<Set<string>>(new Set());
  const [recoveryHydratedWellUid, setRecoveryHydratedWellUid] = useState<string | null>(null);
  const [recoveryAutosaveArmed, setRecoveryAutosaveArmed] = useState(false);

  /*
   * WDV_CANVAS_GLOBAL_INTERVAL_PERSISTENCE_FIX_V1_0_0
   *
   * Interval/Tie-in persistence belongs to the unified WDV canvas. Selecting a
   * different track may change the active inventory well for contextual tools,
   * but it must never re-apply another well's recovery payload over the live
   * canvas.
   */
  const canvasRecoveryHydratedRef = useRef(false);

  /*
   * WDV_DURABLE_RESTART_INVARIANTS_V1_0_0
   *
   * A persisted identifier is not the same thing as a hydrated/renderable
   * client object. Track owners, Core inventory, overlay state and Curve Fill
   * geometry must be reconstructed before the recovery writer is allowed to
   * persist another view-state snapshot.
   */
  const [representedContentHydratedWellUids, setRepresentedContentHydratedWellUids] =
      useState<Set<string>>(() => new Set());
  const [startupHydrationRetryTick, setStartupHydrationRetryTick] = useState(0);
  const [intervalStorageCommitRevision, setIntervalStorageCommitRevision] = useState(0);
  const recoverySaveTimerRef = useRef<number | null>(null);
  const previousCanvasFullDepthRangeRef = useRef<DepthViewRange | null>(null);
  const [, setViewHistory] = useState<DepthViewRange[]>([]);
  const [goToDepthValue, setGoToDepthValue] = useState('');
  const [goToDepthMarker, setGoToDepthMarker] = useState<number | null>(null);
  const [displayGoToSelectionLine, setDisplayGoToSelectionLine] = useState(true);
  const [goToDepthPickActive, setGoToDepthPickActive] = useState(false);
  const [intervalZoomActive, setIntervalZoomActive] = useState(false);
  const [intervalSelection, setIntervalSelection] = useState<IntervalSelectionState | null>(null);
  const [dragPanState, setDragPanState] = useState<DragPanState | null>(null);
  const [trackResizeState, setTrackResizeState] = useState<TrackResizeState | null>(null);
  const [curveInventoryWidthPx, setCurveInventoryWidthPx] = useState(CURVE_INVENTORY_DEFAULT_WIDTH_PX);
  const [curveInventoryCollapsed, setCurveInventoryCollapsed] = useState(false);
  const [quickViewInfoCollapsed, setQuickViewInfoCollapsed] = useState(false);
  const [curveInventoryResizeState, setCurveInventoryResizeState] = useState<CurveInventoryResizeState | null>(null);
  // Tracks the current canonical session revision for revision-guarded commands.
  // -1 means the canonical session has not been initialised yet (canonical GET
  // returned empty or was unreachable).  ≥ 0 means the session is live and
  // canonical commands can be dispatched.
  const canonicalRevisionRef = useRef<number>(-1);

  // Durable viewport commits have their own serialized lane. This lane is
  // deliberately separate from canonical content mutations: pointer/drag
  // preview stays local, and only settled committed viewport state is sent.
  const committedViewportCommitTimerRef = useRef<number | null>(null);

  const [canonicalSession, setCanonicalSession] = useState<RawCanonicalSession | null>(null);
  const [curveFillFeatureEnabled, setCurveFillFeatureEnabled] = useState(false);
  const [curveFillGeometryByRuleUid, setCurveFillGeometryByRuleUid] = useState<Map<string, CurveFillGeometryV2>>(() => new Map());
  const [curveFillPending, setCurveFillPending] = useState(false);
  const [curveFillError, setCurveFillError] = useState<string | null>(null);
  const curveFillHydrationKeyRef = useRef<string | null>(null);
  const backgroundCurveFillHydrationKeysRef = useRef<Set<string>>(new Set());
  const completedCurveFillHydrationKeysRef = useRef<Set<string>>(new Set());
  const curveSelectionPendingKeysRef = useRef<Set<string>>(new Set());
  const [curveSelectionOptimisticByKey, setCurveSelectionOptimisticByKey] = useState<Record<string, boolean>>({});
  const hasLoadedViewerWell = Boolean(managedViewerWellId);
  const [trackBackdropMode, setTrackBackdropMode] = useState<TrackBackdropMode>('light');
  const [trackHeadersCollapsed, setTrackHeadersCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem('wlv.wdv.trackHeaders.v1') === 'collapsed';
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(
        'wlv.wdv.trackHeaders.v1',
        trackHeadersCollapsed ? 'collapsed' : 'expanded',
      );
    } catch {
      // Header display remains session-local when storage is unavailable.
    }
  }, [trackHeadersCollapsed]);
  const [wdvTemplateRecommendations, setWdvTemplateRecommendations] = useState<WdvTemplateRecommendationItem[]>([]);
  const [wdvTemplateRecommendationsLoading, setWdvTemplateRecommendationsLoading] = useState(false);
  const [wdvTemplateRecommendationsError, setWdvTemplateRecommendationsError] = useState<string | null>(null);
  const [selectedWdvTemplateKey, setSelectedWdvTemplateKey] = useState('');
  const [wdvTemplateModalOpen, setWdvTemplateModalOpen] = useState(false);
  const [completeLasSourceId, setCompleteLasSourceId] = useState('');
  const [completeLasSourceOptions, setCompleteLasSourceOptions] = useState<CompleteLasSourceOption[]>([]);
  const [, setCompleteLasSourcesLoading] = useState(false);
  const [completeLasIncludeReview, setCompleteLasIncludeReview] = useState(false);
  const [completeLasPending, setCompleteLasPending] = useState(false);
  const [completeLasError, setCompleteLasError] = useState<string | null>(null);
  const [completeLasResult, setCompleteLasResult] = useState<string | null>(null);

const [quickViewPackage, setQuickViewPackage] = useState<QuickViewPackage | null>(null);
const [quickViewSourceFile, setQuickViewSourceFile] = useState<File | null>(null);
const [quickViewElevatePending, setQuickViewElevatePending] = useState(false);
const [quickViewElevateMessage, setQuickViewElevateMessage] = useState<string | null>(null);
const [quickViewDragActive, setQuickViewDragActive] = useState(false);
const [quickViewPending, setQuickViewPending] = useState(false);
const [quickViewError, setQuickViewError] = useState<string | null>(null);
const [quickViewDepthUnit, setQuickViewDepthUnit] = useState<'m' | 'ft'>('m');
const [quickViewRange, setQuickViewRange] = useState<DepthViewRange>(EMPTY_DEPTH_RANGE);
const [, setQuickViewHistory] = useState<DepthViewRange[]>([]);
const [quickViewIntervalZoomActive, setQuickViewIntervalZoomActive] = useState(false);
const [quickViewGoToDepthValue, setQuickViewGoToDepthValue] = useState('');
const [quickViewSelectedDepth, setQuickViewSelectedDepth] = useState<number | null>(null);
const handleQuickViewDrop = useCallback(async (file: File) => {
  if (!isQuickViewFile(file)) { setQuickViewError('Quick View accepts LAS or DLIS files.'); return; }
  setQuickViewPending(true); setQuickViewError(null);
  try {
    const pkg = await openQuickViewFile(file);
    const unit = pkg.depth_unit_label?.toLowerCase() === 'ft' ? 'ft' : 'm';
    const factor = pkg.depth_unit_label?.toLowerCase() === 'ft' && unit === 'm' ? 1 / 3.280839895013123 : 1;
    setCurveInventoryCollapsed(false);
    setQuickViewPackage(pkg);
    setQuickViewSourceFile(file);
    setQuickViewDepthUnit(unit);
    setQuickViewRange({ min: pkg.depth_min * factor, max: pkg.depth_max * factor });
    setQuickViewHistory([]);
    setQuickViewIntervalZoomActive(false);
    setQuickViewGoToDepthValue('');
    setQuickViewSelectedDepth(null);
    setQuickViewElevateMessage(null);
  }
  catch (error) { setQuickViewError(error instanceof Error ? error.message : 'Unable to display file'); }
  finally { setQuickViewPending(false); }
}, []);

const handleQuickViewElevate = useCallback(async () => {
  if (!quickViewSourceFile) return;
  setQuickViewElevatePending(true);
  setQuickViewElevateMessage(null);
  try {
    const result = await sendQuickViewFileToWsi(quickViewSourceFile);
    setQuickViewElevateMessage(result.message);
  } catch (error) {
    setQuickViewElevateMessage(error instanceof Error ? error.message : 'Unable to send file to WSI');
  } finally {
    setQuickViewElevatePending(false);
  }
}, [quickViewSourceFile]);

const quickViewSourceUnit = quickViewPackage?.depth_unit_label?.toLowerCase() === 'ft' ? 'ft'
  : quickViewPackage?.depth_unit_label?.toLowerCase() === 'm' ? 'm'
  : null;
const quickViewFullRange = useMemo<DepthViewRange>(() => {
  if (!quickViewPackage) return EMPTY_DEPTH_RANGE;
  const convert = (value: number): number => {
    if (!quickViewSourceUnit || quickViewSourceUnit === quickViewDepthUnit) return value;
    return quickViewSourceUnit === 'm' ? value * 3.280839895013123 : value / 3.280839895013123;
  };
  return { min: convert(quickViewPackage.depth_min), max: convert(quickViewPackage.depth_max) };
}, [quickViewPackage, quickViewSourceUnit, quickViewDepthUnit]);
const setQuickViewDepthWindow = useCallback((range: DepthViewRange, remember = true) => {
  if (!quickViewPackage) return;
  const min = Math.max(quickViewFullRange.min, Math.min(range.min, range.max));
  const max = Math.min(quickViewFullRange.max, Math.max(range.min, range.max));
  if (!(max > min)) return;
  if (remember) setQuickViewHistory((history) => [...history, quickViewRange]);
  setQuickViewRange({ min, max });
}, [quickViewPackage, quickViewFullRange.min, quickViewFullRange.max, quickViewRange]);
const changeQuickViewDepthUnit = useCallback((unit: 'm' | 'ft') => {
  if (!quickViewSourceUnit || unit === quickViewDepthUnit) return;
  const factor = quickViewDepthUnit === 'm' ? 3.280839895013123 : 1 / 3.280839895013123;
  setQuickViewDepthUnit(unit);
  setQuickViewRange((range) => ({ min: range.min * factor, max: range.max * factor }));
  setQuickViewHistory((history) => history.map((range) => ({ min: range.min * factor, max: range.max * factor })));
  setQuickViewSelectedDepth((depth) => depth === null ? null : depth * factor);
  setQuickViewGoToDepthValue('');
}, [quickViewSourceUnit, quickViewDepthUnit]);
const zoomQuickView = useCallback((factor: number) => {
  const center = (quickViewRange.min + quickViewRange.max) / 2;
  const half = (quickViewRange.max - quickViewRange.min) * factor / 2;
  setQuickViewDepthWindow({ min: center - half, max: center + half });
}, [quickViewRange, setQuickViewDepthWindow]);
const previousQuickView = useCallback(() => {
  setQuickViewHistory((history) => {
    if (!history.length) return history;
    const previous = history[history.length - 1];
    setQuickViewRange(previous);
    return history.slice(0, -1);
  });
}, []);
const goToQuickViewDepth = useCallback(() => {
  const depth = Number.parseFloat(quickViewGoToDepthValue);
  if (!Number.isFinite(depth)) return;
  if (depth < quickViewFullRange.min || depth > quickViewFullRange.max) {
    setQuickViewError(`Measured depth must be between ${quickViewFullRange.min} and ${quickViewFullRange.max}.`);
    return;
  }

  const currentSpan = quickViewRange.max - quickViewRange.min;
  const reviewWindow = quickViewDepthUnit === 'ft'
    ? GO_TO_REVIEW_WINDOW_M * 3.280839895013123
    : GO_TO_REVIEW_WINDOW_M;
  const requestedSpan = Math.min(currentSpan, reviewWindow);
  const fullSpan = quickViewFullRange.max - quickViewFullRange.min;
  const span = Math.min(requestedSpan, fullSpan);

  let min = depth - span / 2;
  let max = depth + span / 2;
  if (min < quickViewFullRange.min) {
    max += quickViewFullRange.min - min;
    min = quickViewFullRange.min;
  }
  if (max > quickViewFullRange.max) {
    min -= max - quickViewFullRange.max;
    max = quickViewFullRange.max;
  }

  setQuickViewSelectedDepth(depth);
  setQuickViewDepthWindow({ min, max });
  setQuickViewError(null);
}, [quickViewGoToDepthValue, quickViewRange, quickViewFullRange, quickViewDepthUnit, setQuickViewDepthWindow]);

const closeQuickView = useCallback(() => {
  setQuickViewPackage(null);
  setQuickViewSourceFile(null);
  setQuickViewHistory([]);
  setQuickViewIntervalZoomActive(false);
  setQuickViewGoToDepthValue('');
  setQuickViewSelectedDepth(null);
  setQuickViewElevateMessage(null);
}, []);

useEffect(() => {
  if (activeView !== 'log-viewer') return undefined;

  const containsFile = (transfer: DataTransfer | null): boolean => {
    if (!transfer) return false;
    if (transfer.files.length > 0) return true;
    return Array.from(transfer.items).some((item) => item.kind === 'file');
  };

  const onWindowDragOver = (event: globalThis.DragEvent): void => {
    if (!containsFile(event.dataTransfer)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    setQuickViewDragActive(true);
  };

  const onWindowDragLeave = (event: globalThis.DragEvent): void => {
    if (event.relatedTarget === null) setQuickViewDragActive(false);
  };

  const onWindowDrop = (event: globalThis.DragEvent): void => {
    if (!containsFile(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    setQuickViewDragActive(false);
    const files = Array.from(event.dataTransfer?.files ?? []);
    if (files.length !== 1) {
      setQuickViewError('Drop one LAS or DLIS file at a time.');
      return;
    }
    void handleQuickViewDrop(files[0]);
  };

  window.addEventListener('dragover', onWindowDragOver, true);
  window.addEventListener('dragleave', onWindowDragLeave, true);
  window.addEventListener('drop', onWindowDrop, true);
  return () => {
    window.removeEventListener('dragover', onWindowDragOver, true);
    window.removeEventListener('dragleave', onWindowDragLeave, true);
    window.removeEventListener('drop', onWindowDrop, true);
  };
}, [activeView, handleQuickViewDrop]);

  const [logImageSourceOptions, setLogImageSourceOptions] = useState<LogImageSourceOption[]>([]);
  const [selectedLogImageSourceId, setSelectedLogImageSourceId] = useState('');
  useEffect(() => {
      if (activeView !== 'log-viewer') return;
      let cancelled = false;
      let retryTimer: number | null = null;
      let attempt = 0;

      const probe = async (): Promise<void> => {
          try {
              const status = await fetchCurveFillFeatureStatusV2();
              if (!cancelled) setCurveFillFeatureEnabled(status.enabled);
          } catch {
              attempt += 1;
              if (!cancelled && attempt < 4) {
                  retryTimer = window.setTimeout(() => { void probe(); }, attempt * 500);
              } else if (!cancelled) {
                  setCurveFillFeatureEnabled(false);
              }
          }
      };

      void probe();
      return () => {
          cancelled = true;
          if (retryTimer !== null) window.clearTimeout(retryTimer);
      };
  }, [activeView]);

  useEffect(() => {
      // Geometry is well-owned and retained for every represented well. Only the
      // active well's hydration key changes; existing geometry remains available
      // to its owning tracks on the shared canvas.
      curveFillHydrationKeyRef.current = null;
  }, [managedViewerWellUid]);

  useEffect(() => {
      const commonDepthUnit = wdvWorkspace?.common_depth_unit;
      if (!commonDepthUnit) return;
      setTracks((current) => {
          let changed = false;
          const next = current.map((track) => {
              if (track.trackType !== 'depth' || track.unit === commonDepthUnit) return track;
              changed = true;
              return { ...track, unit: commonDepthUnit };
          });
          return changed ? next : current;
      });
  }, [wdvWorkspace?.common_depth_unit]);

  const selectedTrackForDepth = tracks.find((track) => track.trackId === selection.trackId) ?? null;
  const representedWellUids = useMemo(() => Array.from(new Set(
      tracks.map((track) => track.managedWellUid).filter((value): value is string => Boolean(value)),
  )), [tracks]);
  const canvasFullDepthRange = useMemo(() => {
      const representedRanges = representedWellUids
          .map((wellUid) => fullDepthRangesByWellUid[wellUid])
          .filter((range): range is DepthViewRange => Boolean(range));
      if (representedRanges.length > 0) {
          return unionDepthRanges(representedRanges, wdvPackageState.depthRange ?? EMPTY_DEPTH_RANGE);
      }
      return wdvPackageState.depthRange
          ? { ...wdvPackageState.depthRange }
          : { ...EMPTY_DEPTH_RANGE };
  }, [fullDepthRangesByWellUid, representedWellUids, wdvPackageState.depthRange]);
  const visibleCurveTracksFullExtent = useMemo(() => {
      const inventoryRangesByCurveId = new Map<string, DepthViewRange>();

      for (const item of wdvPackageState.loadedCurveItems) {
          const inventoryRange = parseInventoryDepthRange(item.runInterval);
          if (!inventoryRange) continue;
          if (item.curveUid) inventoryRangesByCurveId.set(item.curveUid, inventoryRange);
          if (item.curveId) inventoryRangesByCurveId.set(item.curveId, inventoryRange);
      }

      const trackRanges: DepthViewRange[] = [];

      for (const track of tracks) {
          if (track.trackType !== 'curve') continue;

          const assignedCurveRanges: DepthViewRange[] = [];

          for (const assignment of track.curves) {
              // Managed sample contracts are returned in the active workspace
              // depth unit and therefore are the authoritative display range.
              // Inventory run intervals remain source metadata and can retain
              // their original numeric unit after a workspace unit change.
              const contract = resolveManagedCurveContract(
                  managedSampleContractsByCurveId,
                  {
                      managedWellUid: assignment.managedWellUid ?? null,
                      curveUid: assignment.curveUid ?? null,
                      curveId: assignment.curveId,
                  },
              );
              const min = contract?.depth_min;
              const max = contract?.depth_max;

              if (
                  typeof min === 'number'
                  && Number.isFinite(min)
                  && typeof max === 'number'
                  && Number.isFinite(max)
                  && max > min
              ) {
                  assignedCurveRanges.push({ min, max });
                  continue;
              }

              const inventoryRange =
                  inventoryRangesByCurveId.get(assignment.curveUid ?? '')
                  ?? inventoryRangesByCurveId.get(assignment.curveId);

              if (inventoryRange) {
                  assignedCurveRanges.push(inventoryRange);
              }
          }

          if (assignedCurveRanges.length > 0) {
              trackRanges.push(
                  unionDepthRanges(assignedCurveRanges, canvasFullDepthRange),
              );
          }
      }

      if (trackRanges.length === 0) return canvasFullDepthRange;

      return trackRanges.reduce((longest, candidate) =>
          depthRangeSpan(candidate) > depthRangeSpan(longest)
              ? candidate
              : longest
      );
  }, [
      canvasFullDepthRange,
      managedSampleContractsByCurveId,
      tracks,
      wdvPackageState.loadedCurveItems,
  ]);

  const canvasAssignedCurveDepthRange = visibleCurveTracksFullExtent;
  const visibleDepthTicks = useMemo(() => makeDepthTicks(viewDepthRange), [viewDepthRange]);
  useEffect(() => {
      const previousFull = previousCanvasFullDepthRangeRef.current;
      setViewDepthRange((current) => {
          if (previousFull === null || rangesEqual(current, previousFull)) {
              return { ...canvasAssignedCurveDepthRange };
          }
          return clampDepthRange(current, canvasAssignedCurveDepthRange);
      });
      previousCanvasFullDepthRangeRef.current = { ...canvasAssignedCurveDepthRange };
  }, [canvasAssignedCurveDepthRange]);
  useEffect(() => {
      if (!managedViewerWellUid || !wdvPackageState.depthRange) return;
      const packageRange = { ...wdvPackageState.depthRange };
      setFullDepthRangesByWellUid((current) => ({ ...current, [managedViewerWellUid]: packageRange }));
  }, [managedViewerWellUid, wdvPackageState.depthRange]);
  useEffect(() => {
      if (!trackResizeState)
          return undefined;
      const handleMouseMove = (event: MouseEvent) => {
          const delta = event.clientX - trackResizeState.startX;
          const nextWidth = clampCurveTrackWidth(trackResizeState.startWidth + delta);
          setTracks((current) => current.map((track) => (
              track.trackId === trackResizeState.trackId
              && (
                  track.trackType === 'curve'
                  || track.trackType === 'core'
                  || track.trackType === 'interval'
                  || track.trackType === 'completion'
              )
                  ? { ...track, widthPx: nextWidth }
                  : track
          )));
      };
      const handleMouseUp = () => {
          const resizedTrack = tracksRef.current.find(
              (track) => track.trackId === trackResizeState.trackId,
          );
          if (resizedTrack) {
              window.dispatchEvent(new CustomEvent(
                  'wlv:track-width-commit',
                  { detail: { trackId: resizedTrack.trackId, widthPx: resizedTrack.widthPx } },
              ));
          }
          setTrackResizeState(null);
      };
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
          window.removeEventListener('mousemove', handleMouseMove);
          window.removeEventListener('mouseup', handleMouseUp);
      };
  }, [trackResizeState]);
  useEffect(() => {
      if (!curveInventoryResizeState)
          return undefined;
      const previousCursor = document.body.style.cursor;
      const previousUserSelect = document.body.style.userSelect;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      const handleMouseMove = (event: MouseEvent) => {
          const delta = event.clientX - curveInventoryResizeState.startX;
          setCurveInventoryWidthPx(clampCurveInventoryWidth(curveInventoryResizeState.startWidth + delta));
      };
      const handleMouseUp = () => {
          setCurveInventoryResizeState(null);
      };
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
          window.removeEventListener('mousemove', handleMouseMove);
          window.removeEventListener('mouseup', handleMouseUp);
          document.body.style.cursor = previousCursor;
          document.body.style.userSelect = previousUserSelect;
      };
  }, [curveInventoryResizeState]);
  useEffect(() => {
      const handleKeyDown = (event: KeyboardEvent) => {
          if (event.key !== 'Escape')
              return;
          setIntervalZoomActive(false);
          setIntervalSelection(null);
          setDragPanState(null);
          setTrackResizeState(null);
          setCurveInventoryResizeState(null);
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);
  const selectedTrack = selectedTrackForDepth;
  const orderedTracks = useMemo(() => sortTracks(tracks), [tracks]);
  const selectedTrackIndex = selectedTrack
      ? orderedTracks.findIndex((track) => track.trackId === selectedTrack.trackId)
      : -1;
  const canMoveSelectedTrackLeft = selectedTrackIndex > 0;
  const canMoveSelectedTrackRight = selectedTrackIndex >= 0 && selectedTrackIndex < orderedTracks.length - 1;
  const selectedResizableTrack =
      selectedTrack?.trackType === 'curve'
      || selectedTrack?.trackType === 'core'
      || selectedTrack?.trackType === 'interval'
      || selectedTrack?.trackType === 'completion'
          ? selectedTrack
          : null;

  const canAdjustSelectedCurveTrackWidthDown = Boolean(
      selectedResizableTrack
      && selectedResizableTrack.widthPx > CURVE_TRACK_MIN_WIDTH
  );

  const canAdjustSelectedCurveTrackWidthUp = Boolean(
      selectedResizableTrack
      && selectedResizableTrack.widthPx < CURVE_TRACK_MAX_WIDTH
  );
  const activeViewerCurves = useMemo(() => wdvPackageState.availableCurves, [wdvPackageState]);
  const curveIdentityIndex = useMemo(() => buildCurveIdentityIndex(activeViewerCurves), [activeViewerCurves]);
  const activeWorkspaceWell = useMemo(() => wdvWorkspace?.loaded_wells.find((well) => well.managed_well_id === managedViewerWellId) ?? null, [managedViewerWellId, wdvWorkspace]);
  const [formationTopDatasets, setFormationTopDatasets] = useState<FormationTopDataset[]>([]);
  const [selectedFormationTopIds, setSelectedFormationTopIds] = useState<Set<string>>(() => {
      const persisted = readPersistedCurveOverlayWellState(managedViewerWellId);
      return new Set(persisted?.selectedFormationTopIds ?? []);
  });
  const [lithologyIntervalDatasets, setLithologyIntervalDatasets] = useState<LithologyIntervalDataset[]>([]);
  const [coreImageItems, setCoreImageItems] = useState<CoreImageInventoryItem[]>([]);
  const [selectedCoreImageIds, setSelectedCoreImageIds] = useState<Set<string>>(() => new Set());

  // Core render data is well-owned on a multi-well canvas. The active inventory
  // well can change without rebinding or clearing Core/Core Description tracks
  // that already belong to another well.
  const [coreImageItemsByWellUid, setCoreImageItemsByWellUid] =
      useState<Record<string, CoreImageInventoryItem[]>>({});
  const [completionComponentsByWellUid, setCompletionComponentsByWellUid] =
      useState<Record<string, CompletionComponentRecord[]>>({});
  const [selectedCompletionComponentIds, setSelectedCompletionComponentIds] =
      useState<Set<string>>(() => new Set());
  const [selectedCompletionComponentIdsByWellUid, setSelectedCompletionComponentIdsByWellUid] =
      useState<Record<string, Set<string>>>({});
  const [selectedCoreImageIdsByWellUid, setSelectedCoreImageIdsByWellUid] =
      useState<Record<string, Set<string>>>({});

  const [selectedLithologyIntervalIds, setSelectedLithologyIntervalIds] = useState<Set<string>>(() => {
      const persisted = readPersistedCurveOverlayWellState(managedViewerWellId);
      return new Set(persisted?.selectedLithologyIntervalIds ?? []);
  });
  const [formationTopOverlayStylesByTrackId, setFormationTopOverlayStylesByTrackId] = useState<Record<string, FormationTopOverlayStyle>>(() =>
      readPersistedCurveOverlayTrackStyles(),
  );
  const [hydratedManagedOverlayWellId, setHydratedManagedOverlayWellId] = useState<string | null>(null);
  const [overlayRenderStateByWellUid, setOverlayRenderStateByWellUid] = useState<Record<string, WellOwnedOverlayRenderState>>({});
  const activeInventoryWell = useMemo<CurveInventoryWellContext | null>(() => activeWorkspaceWell ? { managedWellId: activeWorkspaceWell.managed_well_id, wellName: activeWorkspaceWell.well_name } : null, [activeWorkspaceWell]);
  const curveOverlayHydrationPendingRef = useRef(false);
  const selectedCoreImageIdsOwnerWellUidRef = useRef<string | null>(
      managedViewerWellUid ?? null,
  );
  const selectedCompletionComponentIdsOwnerWellUidRef = useRef<string | null>(
      managedViewerWellUid ?? null,
  );

  useEffect(() => {
      if (!managedViewerWellUid) return;
      if (selectedCompletionComponentIdsOwnerWellUidRef.current !== managedViewerWellUid) return;
      setSelectedCompletionComponentIdsByWellUid((current) => {
          const previous = current[managedViewerWellUid] ?? new Set<string>();
          const next = new Set(selectedCompletionComponentIds);
          if (
              previous.size === next.size
              && [...previous].every((id) => next.has(id))
          ) return current;
          return { ...current, [managedViewerWellUid]: next };
      });
  }, [managedViewerWellUid, selectedCompletionComponentIds]);

  useEffect(() => {
      if (!managedViewerWellUid) return;

      // During a well switch, selectedCoreImageIds still contains the previous
      // well's selection until the new well finishes hydration. Do not write
      // those old IDs under the new well UID.
      if (selectedCoreImageIdsOwnerWellUidRef.current !== managedViewerWellUid) {
          return;
      }

      setSelectedCoreImageIdsByWellUid((current) => {
          const previous = current[managedViewerWellUid] ?? new Set<string>();
          const next = new Set(selectedCoreImageIds);

          if (
              previous.size === next.size
              && [...previous].every((id) => next.has(id))
          ) {
              return current;
          }

          return {
              ...current,
              [managedViewerWellUid]: next,
          };
      });
  }, [managedViewerWellUid, selectedCoreImageIds]);

  useEffect(() => {
      let cancelled = false;
      curveOverlayHydrationPendingRef.current = true;
      setHydratedManagedOverlayWellId(null);
      const persistedOverlayState = readPersistedCurveOverlayWellState(managedViewerWellId);
      setFormationTopDatasets([]);
      setLithologyIntervalDatasets([]);
      setSelectedFormationTopIds(new Set(persistedOverlayState?.selectedFormationTopIds ?? []));
      setSelectedLithologyIntervalIds(new Set(persistedOverlayState?.selectedLithologyIntervalIds ?? []));

      /*
       * Completion selection must enter React state in the same synchronous
       * hydration phase as Formation Tops and lithology. If it remains empty
       * until the asynchronous well-data fetch resolves, a subsequent
       * persistence effect can overwrite the durable Completion selection with
       * an empty set during startup/well-switch scheduling.
       *
       * The async fetch below still reconciles these persisted IDs against the
       * Completion components actually available for the well.
       */
      selectedCompletionComponentIdsOwnerWellUidRef.current =
          managedViewerWellUid ?? null;
      setSelectedCompletionComponentIds(
          new Set(persistedOverlayState?.selectedCompletionComponentIds ?? []),
      );

      if (!managedViewerWellId) return () => { cancelled = true; };

      void fetchWlvJson<ManagedWellFormationTopResponse>(
          `/api/wlv/inventory/wells/${encodeURIComponent(managedViewerWellId)}`,
      ).then((record) => {
          if (cancelled) return;
          const parsed = parseManagedWellOverlayDatasets(record);
          setFormationTopDatasets(parsed.formationTopDatasets);
          setLithologyIntervalDatasets(parsed.lithologyIntervalDatasets);
          const allParsedLithology = parsed.lithologyIntervalDatasets.flatMap((dataset) => dataset.intervals);
          setSelectedLithologyIntervalIds(
              reconcilePersistedLithologySelectionIds(
                  persistedOverlayState?.selectedLithologyIntervalIds ?? [],
                  allParsedLithology,
              ),
          );
          setCoreImageItems(parsed.coreImageItems);

          if (managedViewerWellUid) {
              setCoreImageItemsByWellUid((current) => ({
                  ...current,
                  [managedViewerWellUid]: parsed.coreImageItems,
              }));
              setCompletionComponentsByWellUid((current) => ({
                  ...current,
                  [managedViewerWellUid]: parsed.completionComponents,
              }));
              selectedCompletionComponentIdsOwnerWellUidRef.current = managedViewerWellUid;
              setSelectedCompletionComponentIds((current) => {
                  const available = new Set(
                      parsed.completionComponents.map((item) => item.componentId),
                  );
                  const inMemoryForWell =
                      selectedCompletionComponentIdsByWellUid[managedViewerWellUid];
                  const persistedIds =
                      persistedOverlayState?.selectedCompletionComponentIds ?? [];
                  const source =
                      inMemoryForWell ??
                      (persistedIds.length > 0 ? new Set(persistedIds) : current);
                  return new Set([...source].filter((id) => available.has(id)));
              });

              if (parsed.completionComponents.length > 0) {
                  const completionDepths = parsed.completionComponents.flatMap(
                      (component) => [component.topMd, component.baseMd ?? component.topMd],
                  );
                  const completionRange = {
                      min: Math.min(...completionDepths),
                      max: Math.max(...completionDepths),
                  };
                  if (
                      Number.isFinite(completionRange.min)
                      && Number.isFinite(completionRange.max)
                      && completionRange.max >= completionRange.min
                  ) {
                      setFullDepthRangesByWellUid((current) => {
                          const existingRange = current[managedViewerWellUid];
                          return {
                              ...current,
                              [managedViewerWellUid]: existingRange
                                  ? unionDepthRanges([existingRange, completionRange], existingRange)
                                  : completionRange,
                          };
                      });
                  }
              }
          }

          selectedCoreImageIdsOwnerWellUidRef.current =
              managedViewerWellUid ?? null;

          setSelectedCoreImageIds((current) => {
              const available = new Set(
                  parsed.coreImageItems.map((item) => item.productId),
              );
              const persistedForWell = managedViewerWellUid
                  ? selectedCoreImageIdsByWellUid[managedViewerWellUid]
                  : undefined;
              const source = persistedForWell ?? current;
              return new Set([...source].filter((id) => available.has(id)));
          });
          setHydratedManagedOverlayWellId(managedViewerWellId);
      }).catch(() => {
          if (!cancelled) {
              setFormationTopDatasets([]);
              setLithologyIntervalDatasets([]);
          }
      });

      return () => {
          cancelled = true;
      };
  }, [
      managedViewerWellId,
      managedViewerWellUid,
      wdvWorkspace?.loaded_wells,
  ]);

  useEffect(() => {
      if (!managedViewerWellId) return;
      if (curveOverlayHydrationPendingRef.current) {
          curveOverlayHydrationPendingRef.current = false;
          return;
      }
      const persistedForWell = readPersistedCurveOverlayWellState(managedViewerWellId);
      writePersistedCurveOverlayWellState(managedViewerWellId, {
          selectedFormationTopIds: Array.from(selectedFormationTopIds),
          selectedLithologyIntervalIds: Array.from(selectedLithologyIntervalIds),
          selectedCompletionComponentIds: Array.from(selectedCompletionComponentIds),
          // Legacy field retained for storage compatibility only. Track presentation
          // authority now lives in CURVE_OVERLAY_TRACK_STYLE_PERSISTENCE_KEY.
          stylesByTrackId: persistedForWell?.stylesByTrackId ?? {},
      });
  }, [
      managedViewerWellId,
      selectedFormationTopIds,
      selectedLithologyIntervalIds,
      selectedCompletionComponentIds,
  ]);

  const selectedFormationTops = useMemo(
      () => formationTopDatasets
          .flatMap((dataset) => dataset.markers)
          .filter((marker) => selectedFormationTopIds.has(marker.markerId)),
      [formationTopDatasets, selectedFormationTopIds],
  );
  const allFormationTops = useMemo(
      () => formationTopDatasets.flatMap((dataset) => dataset.markers),
      [formationTopDatasets],
  );
  const allLoadedLithologyIntervals = useMemo(
      () => lithologyIntervalDatasets.flatMap((dataset) => dataset.intervals),
      [lithologyIntervalDatasets],
  );
  const selectedLithologyIntervals = useMemo(
      () => allLoadedLithologyIntervals
          .filter((interval) => selectedLithologyIntervalIds.has(interval.intervalId)),
      [allLoadedLithologyIntervals, selectedLithologyIntervalIds],
  );

  // Geological overlay records remain canonical in storage. Formation Tops and
  // saved specified-interval infills are canonical metres; lithology intervals
  // retain their declared source unit. Project only the values supplied to the
  // canvas/editor into the active workspace display unit.
  const overlayDisplayDepthUnit = wdvWorkspace?.common_depth_unit ?? 'm';
  const displayFormationTops = useMemo(
      () => selectedFormationTops.map((marker) => ({
          ...marker,
          md: convertDepthUnitValue(marker.md, 'm', overlayDisplayDepthUnit),
      })),
      [overlayDisplayDepthUnit, selectedFormationTops],
  );
  const displayAllFormationTops = useMemo(
      () => allFormationTops.map((marker) => ({
          ...marker,
          md: convertDepthUnitValue(marker.md, 'm', overlayDisplayDepthUnit),
      })),
      [allFormationTops, overlayDisplayDepthUnit],
  );
  const projectLithologyInterval = useCallback((interval: LithologyIntervalRecord): LithologyIntervalRecord => {
      const sourceUnit = interval.depthUnit === 'ft' ? 'ft' : 'm';
      return {
          ...interval,
          topMd: convertDepthUnitValue(interval.topMd, sourceUnit, overlayDisplayDepthUnit),
          baseMd: convertDepthUnitValue(interval.baseMd, sourceUnit, overlayDisplayDepthUnit),
          depthUnit: overlayDisplayDepthUnit,
      };
  }, [overlayDisplayDepthUnit]);
  const displayAllLoadedLithologyIntervals = useMemo(
      () => allLoadedLithologyIntervals.map(projectLithologyInterval),
      [allLoadedLithologyIntervals, projectLithologyInterval],
  );
  const displaySelectedLithologyIntervals = useMemo(
      () => selectedLithologyIntervals.map(projectLithologyInterval),
      [projectLithologyInterval, selectedLithologyIntervals],
  );
  const projectOverlayStylesToDisplayUnit = useCallback(
      (styles: Record<string, FormationTopOverlayStyle>): Record<string, FormationTopOverlayStyle> => {
          const projected: Record<string, FormationTopOverlayStyle> = {};
          for (const [trackId, style] of Object.entries(styles)) {
              const fillZones: FormationTopOverlayStyle['fillZones'] = (style.fillZones ?? []).map((zone) => {
                  if (zone.depthExtent !== 'specified_interval') return zone;
                  return {
                      ...zone,
                      intervalFromMd: typeof zone.intervalFromMd === 'number'
                          ? convertDepthUnitValue(zone.intervalFromMd, 'm', overlayDisplayDepthUnit)
                          : zone.intervalFromMd,
                      intervalToMd: typeof zone.intervalToMd === 'number'
                          ? convertDepthUnitValue(zone.intervalToMd, 'm', overlayDisplayDepthUnit)
                          : zone.intervalToMd,
                  };
              });
              projected[trackId] = { ...style, fillZones };
          }
          return projected;
      },
      [overlayDisplayDepthUnit],
  );
  const normalizeOverlayStylesToCanonicalMetres = useCallback(
      (styles: Record<string, FormationTopOverlayStyle>): Record<string, FormationTopOverlayStyle> => {
          const normalized: Record<string, FormationTopOverlayStyle> = {};
          for (const [trackId, style] of Object.entries(styles)) {
              const fillZones: FormationTopOverlayStyle['fillZones'] = (style.fillZones ?? []).map((zone) => {
                  if (zone.depthExtent !== 'specified_interval') return zone;
                  return {
                      ...zone,
                      intervalFromMd: typeof zone.intervalFromMd === 'number'
                          ? convertDepthUnitValue(zone.intervalFromMd, overlayDisplayDepthUnit, 'm')
                          : zone.intervalFromMd,
                      intervalToMd: typeof zone.intervalToMd === 'number'
                          ? convertDepthUnitValue(zone.intervalToMd, overlayDisplayDepthUnit, 'm')
                          : zone.intervalToMd,
                  };
              });
              normalized[trackId] = { ...style, fillZones };
          }
          return normalized;
      },
      [overlayDisplayDepthUnit],
  );
  const displayFormationTopOverlayStylesByTrackId = useMemo(
      () => projectOverlayStylesToDisplayUnit(formationTopOverlayStylesByTrackId),
      [formationTopOverlayStylesByTrackId, projectOverlayStylesToDisplayUnit],
  );


  const representedOverlayWells = useMemo(
      () => (wdvWorkspace?.loaded_wells ?? []).filter((well) => representedWellUids.includes(well.managed_well_uid)),
      [representedWellUids, wdvWorkspace?.loaded_wells],
  );

  useEffect(() => {
      let cancelled = false;
      const load = async (): Promise<void> => {
          const entries = await Promise.all(representedOverlayWells.map(async (well) => {
              try {
                  const record = await fetchWlvJson<ManagedWellFormationTopResponse>(
                      `/api/wlv/inventory/wells/${encodeURIComponent(well.managed_well_id)}`,
                  );
                  const parsed = parseManagedWellOverlayDatasets(record);
                  const persisted = readPersistedCurveOverlayWellState(well.managed_well_id);
                  const selectedTopIds = new Set(persisted?.selectedFormationTopIds ?? []);
                  const allTops = parsed.formationTopDatasets.flatMap((dataset) => dataset.markers);
                  const allLithology = parsed.lithologyIntervalDatasets.flatMap((dataset) => dataset.intervals);
                  const selectedLithologyIds = reconcilePersistedLithologySelectionIds(
                      persisted?.selectedLithologyIntervalIds ?? [],
                      allLithology,
                  );
                  const availableCompletionIds = new Set(
                      parsed.completionComponents.map((component) => component.componentId),
                  );
                  const selectedCompletionIds = new Set(
                      (persisted?.selectedCompletionComponentIds ?? [])
                          .filter((componentId) => availableCompletionIds.has(componentId)),
                  );
                  const state: WellOwnedOverlayRenderState = {
                      formationTops: allTops
                          .filter((marker) => selectedTopIds.has(marker.markerId))
                          .map((marker) => ({ ...marker, md: convertDepthUnitValue(marker.md, 'm', overlayDisplayDepthUnit) })),
                      allFormationTops: allTops
                          .map((marker) => ({ ...marker, md: convertDepthUnitValue(marker.md, 'm', overlayDisplayDepthUnit) })),
                      lithologyIntervals: allLithology
                          .filter((interval) => selectedLithologyIds.has(interval.intervalId))
                          .map(projectLithologyInterval),
                      loadedLithologyIntervals: allLithology.map(projectLithologyInterval),
                      formationTopOverlayStylesByTrackId: projectOverlayStylesToDisplayUnit(readPersistedCurveOverlayTrackStyles()),
                  };
                  return {
                      wellUid: well.managed_well_uid,
                      overlayState: state,
                      coreItems: parsed.coreImageItems,
                      completionComponents: parsed.completionComponents,
                      selectedCompletionIds,
                  };
              } catch {
                  return null;
              }
          }));
          if (cancelled) return;

          setRepresentedContentHydratedWellUids((current) => {
              const next = new Set(current);
              let changed = false;
              for (const entry of entries) {
                  if (!entry) continue;
                  if (next.has(entry.wellUid)) continue;
                  next.add(entry.wellUid);
                  changed = true;
              }
              return changed ? next : current;
          });

          /*
           * WDV_STARTUP_CONTENT_REHYDRATION_RECOVERY_V1_0_0
           *
           * Multi-well Core/Core Description content is track-owner data.
           * Rehydrate Core inventory for EVERY represented well, not only the
           * currently active inventory well. Otherwise a full restart leaves
           * background Core/Core Description tracks structurally present but
           * empty until that well happens to become active.
           */
          setCoreImageItemsByWellUid((current) => {
              const next = { ...current };
              for (const well of representedOverlayWells) {
                  const loaded = entries.find((entry) => entry?.wellUid === well.managed_well_uid);
                  if (loaded) next[well.managed_well_uid] = loaded.coreItems;
              }
              return next;
          });

          setCompletionComponentsByWellUid((current) => {
              const next = { ...current };
              for (const well of representedOverlayWells) {
                  const loaded = entries.find((entry) => entry?.wellUid === well.managed_well_uid);
                  if (loaded) next[well.managed_well_uid] = loaded.completionComponents;
              }
              return next;
          });

          setSelectedCompletionComponentIdsByWellUid((current) => {
              const next = { ...current };
              for (const well of representedOverlayWells) {
                  const loaded = entries.find((entry) => entry?.wellUid === well.managed_well_uid);
                  if (loaded) next[well.managed_well_uid] = loaded.selectedCompletionIds;
              }
              return next;
          });

          setOverlayRenderStateByWellUid((current) => {
              const next: Record<string, WellOwnedOverlayRenderState> = {};
              for (const well of representedOverlayWells) {
                  const loaded = entries.find((entry) => entry?.wellUid === well.managed_well_uid);
                  const state = loaded?.overlayState ?? current[well.managed_well_uid];
                  if (state) next[well.managed_well_uid] = state;
              }
              return next;
          });
      };
      void load();
      return () => { cancelled = true; };
  }, [
      overlayDisplayDepthUnit,
      projectLithologyInterval,
      projectOverlayStylesToDisplayUnit,
      representedOverlayWells,
      startupHydrationRetryTick,
  ]);

  /*
   * Recovery selection is stored durably as product IDs. Once every represented
   * well's Core inventory is available, partition those IDs back to the owning
   * wells so Core and Core Description tracks can render independently of which
   * inventory well is active.
   */
  useEffect(() => {
      if (selectedCoreImageIds.size === 0) return;
      setSelectedCoreImageIdsByWellUid((current) => {
          let changed = false;
          const next = { ...current };
          for (const [wellUid, items] of Object.entries(coreImageItemsByWellUid)) {
              const available = new Set(items.map((item) => item.productId));
              const selectedForWell = new Set(
                  [...selectedCoreImageIds].filter((productId) => available.has(productId)),
              );
              if (selectedForWell.size === 0) continue;
              const previous = current[wellUid] ?? new Set<string>();
              if (
                  previous.size === selectedForWell.size
                  && [...previous].every((productId) => selectedForWell.has(productId))
              ) {
                  continue;
              }
              next[wellUid] = selectedForWell;
              changed = true;
          }
          return changed ? next : current;
      });
  }, [coreImageItemsByWellUid, selectedCoreImageIds]);

  useEffect(() => {
      if (!managedViewerWellUid || !managedViewerWellId) return;
      if (hydratedManagedOverlayWellId !== managedViewerWellId) return;
      setOverlayRenderStateByWellUid((current) => ({
          ...current,
          [managedViewerWellUid]: {
              formationTops: displayFormationTops,
              allFormationTops: displayAllFormationTops,
              lithologyIntervals: displaySelectedLithologyIntervals,
              loadedLithologyIntervals: displayAllLoadedLithologyIntervals,
              formationTopOverlayStylesByTrackId: displayFormationTopOverlayStylesByTrackId,
          },
      }));
  }, [
      displayAllFormationTops,
      displayAllLoadedLithologyIntervals,
      displayFormationTopOverlayStylesByTrackId,
      displayFormationTops,
      displaySelectedLithologyIntervals,
      hydratedManagedOverlayWellId,
      managedViewerWellId,
      managedViewerWellUid,
  ]);

  const activeCurveFillTrackUids = useMemo(
      () => new Set(tracks.map((track) => track.trackId)),
      [tracks],
  );
  const renderBundlesByWellUid = useMemo(() => buildWellOwnedTrackRenderBundles(
      overlayRenderStateByWellUid,
      curveFillFeatureEnabled ? curveFillGeometryByRuleUid : new Map(),
      tracks,
  ), [curveFillFeatureEnabled, curveFillGeometryByRuleUid, overlayRenderStateByWellUid, tracks]);

  /*
   * WDV_TIE_IN_FORMATION_CORRELATION_V2_0_0
   *
   * Formation Top Tie-ins consume exactly the same selected/rendered marker set
   * as the visible Formation Top overlays for each owning well. This prevents
   * a broader/stale loaded dataset from supplying plausible names with unrelated
   * MD values.
   */
  const formationTopMarkersByWellUid = useMemo<Record<string, FormationTopMarker[]>>(
      () => Object.fromEntries(
          Object.entries(overlayRenderStateByWellUid).map(([wellUid, state]) => [
              wellUid,
              state.formationTops ?? [],
          ]),
      ),
      [overlayRenderStateByWellUid],
  );

  /*
   * Durable startup barrier.
   *
   * Recovery autosave is forbidden until every represented well has completed
   * owner-data hydration, every selected Core product can be resolved to an
   * owner inventory item, and every enabled Curve Fill has hydrated geometry.
   * This prevents a partially hydrated startup frame from becoming the next
   * durable recovery snapshot.
   */
  const startupSemanticHydrationReady = useMemo(() => {
      if (representedWellUids.some((wellUid) => !representedContentHydratedWellUids.has(wellUid))) {
          return false;
      }

      if (selectedCoreImageIds.size > 0) {
          const availableCoreProductIds = new Set<string>();
          for (const items of Object.values(coreImageItemsByWellUid)) {
              for (const item of items) availableCoreProductIds.add(item.productId);
          }
          for (const productId of selectedCoreImageIds) {
              if (!availableCoreProductIds.has(productId)) return false;
          }
      }

      if (curveFillFeatureEnabled) {
          for (const rule of canonicalSession?.curve_fills ?? []) {
              if (!rule.enabled) continue;
              if (!curveFillGeometryByRuleUid.has(rule.rule_uid)) return false;
          }
      }

      return true;
  }, [
      canonicalSession?.curve_fills,
      coreImageItemsByWellUid,
      curveFillFeatureEnabled,
      curveFillGeometryByRuleUid,
      representedContentHydratedWellUids,
      representedWellUids,
      selectedCoreImageIds,
  ]);

  const lastStartupHydrationDiagnosticRef = useRef<string>('');
  useEffect(() => {
      const enabledFillRuleUids = (canonicalSession?.curve_fills ?? [])
          .filter((rule) => rule.enabled)
          .map((rule) => rule.rule_uid)
          .sort();
      const missingFillRuleUids = enabledFillRuleUids
          .filter((ruleUid) => !curveFillGeometryByRuleUid.has(ruleUid));
      const availableCoreProductIds = new Set(
          Object.values(coreImageItemsByWellUid)
              .flatMap((items) => items.map((item) => item.productId)),
      );
      const missingSelectedCoreProductIds = [...selectedCoreImageIds]
          .filter((productId) => !availableCoreProductIds.has(productId))
          .sort();
      const missingOwnerWellUids = representedWellUids
          .filter((wellUid) => !representedContentHydratedWellUids.has(wellUid))
          .sort();

      const signature = JSON.stringify({
          ready: startupSemanticHydrationReady,
          missingOwnerWellUids,
          missingSelectedCoreProductIds,
          missingFillRuleUids,
      });
      if (signature === lastStartupHydrationDiagnosticRef.current) return;
      lastStartupHydrationDiagnosticRef.current = signature;
      recordWdvDiagnosticEvent('startup-hydration', startupSemanticHydrationReady ? 'ready' : 'blocked', {
          missingOwnerWellUids,
          missingSelectedCoreProductIds,
          missingFillRuleUids,
      });
  }, [
      canonicalSession?.curve_fills,
      coreImageItemsByWellUid,
      curveFillGeometryByRuleUid,
      representedContentHydratedWellUids,
      representedWellUids,
      selectedCoreImageIds,
      startupSemanticHydrationReady,
  ]);

  const lastRenderBundleDiagnosticSignatureRef = useRef<string>('');
  useEffect(() => {
      const ruleByUid = new Map(
          (canonicalSession?.curve_fills ?? []).map((rule) => [rule.rule_uid, rule] as const),
      );
      const geometryEntries = curveFillFeatureEnabled
          ? [...curveFillGeometryByRuleUid.entries()]
              .filter(([, geometry]) => activeCurveFillTrackUids.has(geometry.track_uid))
              .map(([ruleUid, geometry]) => {
                  const rule = ruleByUid.get(ruleUid);
                  return {
                      ruleUid,
                      managedWellUid: geometry.managed_well_uid ?? null,
                      trackUid: geometry.track_uid ?? null,
                      assignmentUid: rule?.curve_a_assignment_uid ?? null,
                      secondAssignmentUid: rule?.curve_b_assignment_uid ?? null,
                      ruleType: rule?.rule_type ?? null,
                      comparison: rule?.comparison ?? null,
                      boundary: rule?.boundary ?? null,
                      enabled: rule?.enabled ?? null,
                      style: rule?.style ?? null,
                      depthExtent: rule?.depth_extent ?? null,
                      intervalFromMd: rule?.interval_from_md ?? null,
                      intervalToMd: rule?.interval_to_md ?? null,
                  };
              }).sort((left, right) => left.ruleUid.localeCompare(right.ruleUid))
          : [];
      const signature = JSON.stringify({
          wellUids: [...renderBundlesByWellUid.keys()].sort(),
          overlayWellUids: Object.keys(overlayRenderStateByWellUid).sort(),
          geometryEntries,
      });
      if (signature === lastRenderBundleDiagnosticSignatureRef.current) return;
      lastRenderBundleDiagnosticSignatureRef.current = signature;
      recordWdvDiagnosticEvent('render-bundles', 'state-changed', {
          wellCount: renderBundlesByWellUid.size,
          overlayWellCount: Object.keys(overlayRenderStateByWellUid).length,
          curveFillGeometryCount: geometryEntries.length,
          geometryEntries,
      });
  }, [activeCurveFillTrackUids, canonicalSession?.curve_fills, curveFillFeatureEnabled, curveFillGeometryByRuleUid, overlayRenderStateByWellUid, renderBundlesByWellUid]);

  const ownerWellNames = useMemo(
      () => new Map((wdvWorkspace?.loaded_wells ?? []).map((well) => [well.managed_well_uid, well.well_name])),
      [wdvWorkspace?.loaded_wells],
  );
  const activeCurveRunMetadata = useMemo(() => {
      const metadata = new Map<string, {
          runInterval?: string | null;
          runNumber?: string | null;
      }>();
      wdvPackageState.loadedCurveItems.forEach((item) => {
          const value = { runInterval: item.runInterval, runNumber: item.runNumber };
          metadata.set(item.curveUid, value);
          metadata.set(item.curveId, value);
      });
      return metadata;
  }, [wdvPackageState.loadedCurveItems]);
  const completeLasSources = completeLasSourceOptions;

  useEffect(() => {
      if (!managedViewerWellUid) {
          setCompleteLasSourceOptions([]);
          return;
      }
      const controller = new AbortController();
      setCompleteLasSourcesLoading(true);
      void fetchWlvJson<CompleteLasSourceListResponse>(
          `/api/wlv/v2/wdv/las/${encodeURIComponent(managedViewerWellUid)}/sources`,
          { signal: controller.signal },
      ).then((payload) => {
          if (controller.signal.aborted) return;
          setCompleteLasSourceOptions(payload.sources.map((source) => ({
              sourceId: source.source_id,
              label: source.label || source.original_filename || source.source_id,
              curveCount: source.curve_count,
              assetAvailable: source.asset_available,
          })));
      }).catch((error) => {
          if (controller.signal.aborted || isAbortError(error)) return;
          setCompleteLasSourceOptions([]);
          setCompleteLasError(error instanceof Error ? error.message : 'Unable to list managed LAS sources');
      }).finally(() => {
          if (!controller.signal.aborted) setCompleteLasSourcesLoading(false);
      });
      return () => controller.abort();
  }, [managedViewerWellUid, viewerPackageRefreshRevision]);

  useEffect(() => {
      if (!managedViewerWellUid) {
          setLogImageSourceOptions([]);
          setSelectedLogImageSourceId('');
          return;
      }
      const controller = new AbortController();
      void fetchWlvJson<LogImageSourceListResponse>(
          `/api/wlv/v2/wdv/las/${encodeURIComponent(managedViewerWellUid)}/log-images`,
          { signal: controller.signal },
      ).then((payload) => {
          if (controller.signal.aborted) return;
          const options = payload.sources.map((source) => ({
              sourceId: source.source_id,
              label: source.label || source.original_filename || source.source_id,
              fileFormat: source.file_format,
          }));
          setLogImageSourceOptions(options);
          setSelectedLogImageSourceId((current) => options.some((item) => item.sourceId === current) ? current : (options[0]?.sourceId ?? ''));
      }).catch((error) => {
          if (controller.signal.aborted || isAbortError(error)) return;
          setLogImageSourceOptions([]);
      });
      return () => controller.abort();
  }, [managedViewerWellUid, viewerPackageRefreshRevision]);

  useEffect(() => {
      if (completeLasSources.some((source) => source.sourceId === completeLasSourceId)) return;
      setCompleteLasSourceId(completeLasSources[0]?.sourceId ?? '');
      setCompleteLasError(null);
      setCompleteLasResult(null);
  }, [completeLasSourceId, completeLasSources]);

  const activeCurveCatalog = useMemo(() => {
      const merged = [...curveCatalog];
      const identityKey = (curve: CurveCatalogItem): string => {
          const owner = curve.managedWellUid ?? curve.wellUid ?? '';
          const identity = curve.curveUid ?? curve.curveId;
          return `${owner || 'unowned'}:${identity}`;
      };
      const existingCurveKeys = new Set(merged.map(identityKey));

      // Preserve catalog identities for every well still represented on the
      // canvas. Active-well focus only controls inventory foregrounding; it no
      // longer removes the catalog records required by background tracks.
      const representedViewerCurves = representedWellUids.flatMap(
          (wellUid) => viewerPackageStateByWellUidRef.current[wellUid]?.availableCurves ?? [],
      );
      [...representedViewerCurves, ...activeViewerCurves].forEach((curve) => {
          if (!curve.curveId) return;
          const key = identityKey(curve);
          if (existingCurveKeys.has(key)) return;
          merged.push(curve);
          existingCurveKeys.add(key);
      });

      tracks.forEach((track) => {
          if (track.trackType !== 'curve') return;
          track.curves.forEach((assignment) => {
              const assignmentKey = `${assignment.managedWellUid ?? 'unowned'}:${assignment.curveUid ?? assignment.curveId}`;
              if (existingCurveKeys.has(assignmentKey)) return;
              merged.push({
                  curveId: assignment.curveId,
                  curveUid: assignment.curveUid,
                  managedWellUid: assignment.managedWellUid ?? null,
                  managedProductUid: assignment.managedProductUid ?? null,
                  managedSourceUid: assignment.managedSourceUid ?? null,
                  observedMnemonic: assignment.observedMnemonic ?? assignment.curveId,
                  normalizedMnemonic: assignment.normalizedMnemonic ?? assignment.observedMnemonic ?? assignment.curveId,
                  mnemonic: assignment.observedMnemonic ?? assignment.displayName ?? assignment.curveId,
                  description: assignment.displayName ?? assignment.observedMnemonic ?? assignment.curveId,
                  unit: assignment.unit ?? '',
                  curveClass: 'unknown',
                  defaultLattice: assignment.scaleType === 'log' ? 'logarithmic' : 'linear',
                  defaultMin: assignment.scaleMin,
                  defaultMax: assignment.scaleMax,
                  defaultColor: assignment.color,
                  recognised: false,
              });
              existingCurveKeys.add(assignmentKey);
          });
      });
      return merged;
  }, [activeViewerCurves, curveCatalog, representedWellUids, tracks, viewerPackageCacheRevision]);

  // Full is track-owned, not a synonym for the global canvas range.
  // This is intentionally declared only after every dependency below exists.
  const trackFullDepthRangesById = useMemo<Record<string, DepthViewRange>>(() => {
      const orderedTracks = sortTracks(tracks);
      const ranges: Record<string, DepthViewRange> = {};

      const fullRangeForTrack = (track: WellLogTrack): DepthViewRange => {
          const renderBundle = renderBundleForTrack(track, renderBundlesByWellUid);
          const trackCoreImageItems: CoreImageInventoryItem[] = track.managedWellUid
              ? coreImageItemsByWellUid[track.managedWellUid] ?? []
              : coreImageItems;
          const trackSelectedCoreImageIds = track.managedWellUid
              ? selectedCoreImageIdsByWellUid[track.managedWellUid] ?? new Set<string>()
              : selectedCoreImageIds;

          if (track.trackType === 'curve') {
              return fullRenderableDepthRangeFromValues(
                  orderedCurves(track).flatMap((assignment, index) => {
                      const curve = activeCurveCatalog.find(
                          (candidate) => candidate.curveId === assignment.curveId,
                      );
                      return curve
                          ? makeMockCurveSamples(
                              curve,
                              assignment,
                              index,
                              managedSamplesByCurveId,
                          ).map((sample) => sample.depth)
                          : [];
                  }),
                  canvasAssignedCurveDepthRange,
              );
          }

          if (track.trackType === 'completion') {
              const trackCompletionComponents = track.managedWellUid
                  ? completionComponentsByWellUid[track.managedWellUid] ?? []
                  : [];
              const trackSelectedCompletionIds = track.managedWellUid
                  ? selectedCompletionComponentIdsByWellUid[track.managedWellUid] ?? new Set<string>()
                  : selectedCompletionComponentIds;
              const selectedComponents = trackCompletionComponents.filter(
                  (component) => trackSelectedCompletionIds.has(component.componentId),
              );
              const rangeItems = selectedComponents.length > 0
                  ? selectedComponents
                  : trackCompletionComponents;
              return fullRenderableDepthRangeFromValues(
                  rangeItems.flatMap((component) => [
                      component.topMd,
                      component.baseMd ?? component.topMd,
                  ]),
                  canvasAssignedCurveDepthRange,
              );
          }

          if (track.trackType === 'core') {
              const selectedItems = trackCoreImageItems.filter(
                  (item) => trackSelectedCoreImageIds.has(item.productId),
              );
              const rangeItems = selectedItems.length > 0
                  ? selectedItems
                  : trackCoreImageItems;
              return fullRenderableDepthRangeFromValues(
                  rangeItems.flatMap((item) => [item.topMd, item.baseMd]),
                  canvasAssignedCurveDepthRange,
              );
          }

          if (
              track.trackType === 'interval'
              && track.rendererType === 'interval_core_description'
          ) {
              return fullRenderableDepthRangeFromValues(
                  trackCoreImageItems.flatMap((item) => [item.topMd, item.baseMd]),
                  canvasAssignedCurveDepthRange,
              );
          }

          if (
              track.trackType === 'interval'
              && track.rendererType === 'interval_depth'
          ) {
              return trackCoreImageItems.length > 0
                  ? fullRenderableDepthRangeFromValues(
                      trackCoreImageItems.flatMap((item) => [item.topMd, item.baseMd]),
                      canvasAssignedCurveDepthRange,
                  )
                  : { ...canvasAssignedCurveDepthRange };
          }

          if (
              track.trackType === 'interval'
              && track.rendererType === 'interval_formation'
          ) {
              return fullRenderableDepthRangeFromValues(
                  renderBundle.allFormationTops.map((marker) => marker.md),
                  canvasAssignedCurveDepthRange,
              );
          }

          if (renderBundle.loadedLithologyIntervals.length > 0) {
              return fullRenderableDepthRangeFromValues(
                  renderBundle.loadedLithologyIntervals.flatMap(
                      (interval) => [interval.topMd, interval.baseMd],
                  ),
                  canvasAssignedCurveDepthRange,
              );
          }

          return { ...canvasAssignedCurveDepthRange };
      };

      for (let index = 0; index < orderedTracks.length; index += 1) {
          const track = orderedTracks[index];

          if (track.trackType !== 'depth') {
              ranges[track.trackId] = fullRangeForTrack(track);
              continue;
          }

          // Existing WDV Depth/MD convention: follow the nearest non-depth
          // track to the right for authoritative displayed extent.
          const rightTrack = orderedTracks
              .slice(index + 1)
              .find((candidate) => candidate.trackType !== 'depth') ?? null;
          ranges[track.trackId] = rightTrack
              ? fullRangeForTrack(rightTrack)
              : { ...canvasAssignedCurveDepthRange };
      }

      return ranges;
  }, [
      activeCurveCatalog,
      canvasAssignedCurveDepthRange,
      completionComponentsByWellUid,
      coreImageItems,
      coreImageItemsByWellUid,
      managedSamplesByCurveId,
      renderBundlesByWellUid,
      selectedCoreImageIds,
      selectedCoreImageIdsByWellUid,
      selectedCompletionComponentIds,
      selectedCompletionComponentIdsByWellUid,
      tracks,
  ]);
  /*
   * Authoritative canvas navigation domain: union of every represented
   * track's full renderable domain. This deliberately includes Core,
   * Interval, Raster/future renderers, and Curve tracks. It is not a
   * replacement for independent track viewports.
   */
  const canvasAllTrackDepthRange = useMemo<DepthViewRange>(() => {
      const ranges = Object.values(trackFullDepthRangesById);
      if (ranges.length === 0) return { ...canvasAssignedCurveDepthRange };
      return ranges.reduce(
          (combined, candidate) => unionDepthRanges([combined, candidate], combined),
          { ...canvasAssignedCurveDepthRange },
      );
  }, [canvasAssignedCurveDepthRange, trackFullDepthRangesById]);


  /*
   * Navigation authority is deliberately broader than content authority.
   *
   * trackFullDepthRangesById remains the track-owned content extent used by
   * Full/magnification semantics. Drag-pan must not use that range as a hard
   * clamp for Curve tracks: a curve can end before the well ends, and the
   * viewport must still be able to move into valid blank MD space.
   *
   * Prefer the owning well's backend viewer-package depth range. Legacy Curve
   * tracks can recover ownership from their canonical assignments. If owner
   * depth authority is unavailable, use the union canvas navigation domain.
   */
  const trackNavigableDepthRangesById = useMemo<Record<string, DepthViewRange>>(() => {
      const ranges: Record<string, DepthViewRange> = {};
      for (const track of tracks) {
          const assignmentOwnerWellUid = track.trackType === 'curve'
              ? track.curves.find((assignment) => Boolean(assignment.managedWellUid))?.managedWellUid ?? null
              : null;
          const ownerWellUid = track.managedWellUid ?? assignmentOwnerWellUid;
          const ownerRange = ownerWellUid ? fullDepthRangesByWellUid[ownerWellUid] : null;
          ranges[track.trackId] = ownerRange && ownerRange.max > ownerRange.min
              ? { ...ownerRange }
              : { ...canvasAllTrackDepthRange };
      }
      return ranges;
  }, [canvasAllTrackDepthRange, fullDepthRangesByWellUid, tracks]);

  useEffect(() => {
      const depthUnit = wdvWorkspace?.common_depth_unit ?? 'm';
      const requests = tracks.flatMap((track) =>
          track.trackType === 'curve'
              ? track.curves.flatMap((assignment) =>
                  assignment.managedWellUid && assignment.curveUid
                      ? [{
                            assignment,
                            managedWellUid: assignment.managedWellUid,
                            managedCurveUid: assignment.curveUid,
                            cacheKey: `${assignment.managedWellUid}:${assignment.curveUid}:${depthUnit}`,
                        }]
                      : [],
                )
              : [],
      );

      const unique = Array.from(
          new Map(requests.map((item) => [item.cacheKey, item])).values(),
      );
      requiredSampleKeysRef.current = new Set(unique.map((item) => item.cacheKey));

      if (sampleDepthUnitRef.current !== depthUnit) {
          sampleDepthUnitRef.current = depthUnit;
          sampleCacheRef.current.clear();
          sampleInflightRef.current.clear();
          setManagedSamplesByCurveId({});
          setManagedSampleContractsByCurveId({});
          setManagedSampleErrorsByCurveId({});
      }

      if (activeView !== 'log-viewer' || unique.length === 0) {
          setManagedSamplesByCurveId({});
          setManagedSampleContractsByCurveId({});
          setManagedSampleErrorsByCurveId({});
          setManagedSamplesLoading(false);
          return undefined;
      }

      const cachedResults = unique
          .map((item) => sampleCacheRef.current.get(item.cacheKey))
          .filter((result): result is ManagedCurveSampleLoadResult => Boolean(result));
      const cachedIndexed = indexManagedCurveSamples(cachedResults);
      setManagedSamplesByCurveId(cachedIndexed.samplesByCurveId);
      setManagedSampleContractsByCurveId(cachedIndexed.contractsByCurveId);
      setManagedSampleErrorsByCurveId(cachedIndexed.errorsByCurveId);

      const mergeVisibleResult = (cacheKey: string, result: ManagedCurveSampleLoadResult) => {
          if (!requiredSampleKeysRef.current.has(cacheKey)) return;
          const responseWellUid = result.contract?.managed_well_uid ?? null;
          const responseCurveUid = result.contract?.managed_curve_uid ?? null;
          if (
              (responseWellUid && responseWellUid !== result.request.managedWellId)
              || (responseCurveUid && responseCurveUid !== (result.request.managedCurveUid ?? result.request.curveUid))
          ) {
              recordWdvDiagnosticEvent('curve-hydration', 'owner-mismatch-rejected', {
                  requestedWellUid: result.request.managedWellId,
                  responseWellUid,
                  requestedCurveUid: result.request.managedCurveUid ?? result.request.curveUid,
                  responseCurveUid,
              });
              return;
          }
          const indexed = indexManagedCurveSamples([result]);
          setManagedSamplesByCurveId((current) => ({ ...current, ...indexed.samplesByCurveId }));
          setManagedSampleContractsByCurveId((current) => ({ ...current, ...indexed.contractsByCurveId }));
          setManagedSampleErrorsByCurveId((current) => {
              const next = { ...current };
              for (const key of Object.keys(indexed.samplesByCurveId)) delete next[key];
              return { ...next, ...indexed.errorsByCurveId };
          });

          if (result.samples.length > 0) {
              const depths = result.samples.map((sample) => sample.depth);
              const sampledRange = { min: Math.min(...depths), max: Math.max(...depths) };
              if (Number.isFinite(sampledRange.min) && Number.isFinite(sampledRange.max) && sampledRange.max > sampledRange.min) {
                  setFullDepthRangesByWellUid((current) => {
                      const existingRange = current[result.request.managedWellId];
                      return {
                          ...current,
                          [result.request.managedWellId]: existingRange
                              ? unionDepthRanges([existingRange, sampledRange], existingRange)
                              : sampledRange,
                      };
                  });
              }
          }
      };

      for (const item of unique) {
          const cached = sampleCacheRef.current.get(item.cacheKey);
          if (cached) continue;

          const existingInflight = sampleInflightRef.current.get(item.cacheKey);
          if (existingInflight) {
              void existingInflight.then((result) => mergeVisibleResult(item.cacheKey, result));
              continue;
          }

          const { assignment, managedWellUid, managedCurveUid, cacheKey } = item;
          const request = {
              managedWellId: managedWellUid,
              curveId: assignment.curveId,
              curveUid: assignment.curveUid ?? managedCurveUid,
              managedCurveUid,
              productId: assignment.managedProductUid ?? managedCurveUid,
              samplesUrl: '/api/wlv/v2/curve-samples',
          };

          const load = (async (): Promise<ManagedCurveSampleLoadResult> => {
              try {
                  const payload = await fetchWlvJson<ManagedCurveSamplesPayload>(
                      '/api/wlv/v2/curve-samples',
                      {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                              managed_well_uid: managedWellUid,
                              managed_curve_uid: managedCurveUid,
                              target_depth_unit: depthUnit,
                              max_samples: WDV_CURVE_SAMPLE_LIMIT,
                          }),
                      },
                  );
                  const samples = parseManagedCurveSamples(payload);
                  return {
                      request,
                      contract: payload,
                      samples,
                      error: samples.length ? null : `No usable samples returned for ${assignment.curveId}`,
                  };
              } catch (error) {
                  return {
                      request,
                      contract: null,
                      samples: [],
                      error: error instanceof Error ? error.message : `Unable to load ${assignment.curveId}`,
                  };
              }
          })();

          sampleInflightRef.current.set(cacheKey, load);
          setManagedSamplesLoading(true);
          void load.then((result) => {
              sampleCacheRef.current.set(cacheKey, result);
              mergeVisibleResult(cacheKey, result);
          }).finally(() => {
              sampleInflightRef.current.delete(cacheKey);
              if (sampleInflightRef.current.size === 0) setManagedSamplesLoading(false);
          });
      }

      if (unique.every((item) => sampleCacheRef.current.has(item.cacheKey))) {
          setManagedSamplesLoading(false);
      }
      return undefined;
  }, [activeView, tracks, wdvWorkspace?.common_depth_unit]);

  const wdvSessionKey = useMemo(() => {
      if (!managedViewerWellId)
          return null;
      const productKey = wdvPackageState.loadedCurveItems.map((item) => item.productId || item.curveId).join('|');
      return `${managedViewerWellId}:${productKey}`;
  }, [managedViewerWellId, wdvPackageState.loadedCurveItems]);

  // ---------------------------------------------------------------------------
  // Canonical-only startup restore
  // ---------------------------------------------------------------------------

  const projectCanonicalTracks = useCallback(
    (session: RawCanonicalSession): WellLogTrack[] => (
      frontendTracksFromCanonicalSession(session, activeCurveCatalog).map((track) => ({
        ...track,
        ownerWellName: track.managedWellUid ? ownerWellNames.get(track.managedWellUid) : undefined,
      }))
    ),
    [activeCurveCatalog, ownerWellNames],
  );

  // WDV_STARTUP_LAYOUT_REPLAY_GUARD_V1_0_0
  // These callbacks are startup-layout dependencies. Keep them referentially
  // stable so canonical mutations do not recreate applyCanonicalStartupLayout
  // and accidentally replay stale startup tracks over live canonical state.
  const canonicalTrackUid = useCallback(
    (track: WellLogTrack): string => track.trackId,
    [],
  );
  const buildCanonicalTrackSelection = useCallback(
    (trackId: string): SelectionRef => ({ kind: 'track', trackId }),
    [],
  );

  const {
    prepareCanonicalStartupSession,
    applyCanonicalStartupLayout,
    applyCanonicalSession,
  } = useCanonicalSessionApplicationController<RawCanonicalSession, WellLogTrack, SelectionRef>({
    canonicalRevisionRef,
    setCanonicalSession,
    setTracks,
    setSelection,
    currentSelection: () => selectionRef.current,
    projectTracks: projectCanonicalTracks,
    reindexTracks: reindexTracksInCurrentOrder,
    trackUid: canonicalTrackUid,
    buildTrackSelection: buildCanonicalTrackSelection,
    backendSelection: (selectedTrackUid): SelectionRef => ({ kind: 'track', trackId: selectedTrackUid ?? '' }),
    preserveSelection: preserveSelectionAcrossCanonicalRefresh,
    recordDiagnostic: (detail) => recordWdvDiagnosticEvent('canonical-session', 'apply', detail),
  });

  const loadCanonicalLayout = useCallback(
    async (signal: AbortSignal): Promise<CanonicalLayoutResult | null> => {
      if (!managedViewerWellUid || !wdvSessionKey || wdvPackageState.loadedCurveItems.length === 0) {
        return null;
      }
      const canonicalSession = await fetchWlvJson<RawCanonicalSession>(
        `/api/wlv/v2/wdv/sessions/${encodeURIComponent(managedViewerWellUid)}`,
        { signal },
      );
      const startup = prepareCanonicalStartupSession(canonicalSession);
      return {
        tracks: startup.tracks,
        selectedTrackId: startup.selectedTrackUid,
        hydratedSessionKey: wdvSessionKey,
      };
    },
    [managedViewerWellUid, prepareCanonicalStartupSession, wdvPackageState.loadedCurveItems.length, wdvSessionKey],
  );

  const layoutSource = useWdvLayoutSource({
    managedWellUid: managedViewerWellUid,
    canonicalLoadKey: wdvSessionKey ?? '',
    loadCanonicalLayout,
  });

  // ---------------------------------------------------------------------------
  // Canonical session command helpers (C2 Defect B)
  // ---------------------------------------------------------------------------

  const {
    executeCanonicalCommand: executeWdvCanonicalCommand,
    refreshCanonicalSession,
    runSerializedCanonicalMutation: runSerializedWdvCanonicalMutation,
    runSerializedCanonicalTask,
  } = useCanonicalSessionMutationController<RawCanonicalSession>({
    managedWellUid: managedViewerWellUid,
    canonicalRevisionRef,
    applyCanonicalSession,
    fetchJson: fetchWlvJson,
    beginDiagnostic: beginWdvDiagnosticOperation,
  });

  const {
    configureBlankTrack: runConfigureBlankTrack,
    clearCanvas: runClearCanonicalCanvas,
    reorderTracks: runReorderTracks,
    configureTrack: runConfigureTrack,
    moveAssignment: runMoveAssignment,
    reorderAssignments: runReorderAssignments,
    removeAssignment: runRemoveAssignment,
  } = useCanvasCompositionMutationController<RawCanonicalSession>({
    managedWellUid: managedViewerWellUid,
    canonicalRevisionRef,
    applyCanonicalSession,
    executeCanonicalCommand: executeWdvCanonicalCommand,
    refreshCanonicalSession,
    runSerializedCanonicalMutation: runSerializedWdvCanonicalMutation,
  });

  const {
    commitTrackWidth,
    updateAssignment: runUpdateAssignment,
    commitAssignmentLineStyle,
    assignCurveToTrack,
    removeCurveAssignment: runRemoveCurveAssignmentWithReconcile,
  } = useTrackAssignmentMutationController<RawCanonicalSession>({
    runSerializedCanonicalMutation: runSerializedWdvCanonicalMutation,
    refreshCanonicalSession,
  });

  useEffect(() => {
      const handleWidthCommit = (event: Event) => {
          const detail = (event as CustomEvent<{ trackId?: string; widthPx?: number }>).detail;
          if (
              !detail?.trackId
              || typeof detail.widthPx !== 'number'
              || !Number.isFinite(detail.widthPx)
              || !managedViewerWellUid
              || canonicalRevisionRef.current < 0
          ) {
              return;
          }
          void commitTrackWidth(
              detail.trackId,
              clampCurveTrackWidth(detail.widthPx),
          ).catch((error) => {
              console.error('[WdvPageBoundary] canonical track width commit failed:', error);
          });
      };
      window.addEventListener('wlv:track-width-commit', handleWidthCommit as EventListener);
      return () => window.removeEventListener(
          'wlv:track-width-commit',
          handleWidthCommit as EventListener,
      );
  }, [commitTrackWidth, managedViewerWellUid]);

  const coreAppearanceCommitTimerRef = useRef<number | null>(null);
  const pendingCoreAppearanceCommitRef = useRef<{
      trackId: string;
      appearance: CoreTrackAppearance;
  } | null>(null);

  useEffect(() => {
      const handleCompletionAppearanceCommit = (event: Event) => {
          const detail = (event as CustomEvent<{
              trackId?: string;
              managedWellUid?: string | null;
              appearance?: CompletionTrackAppearance;
              resolve?: () => void;
              reject?: (error: unknown) => void;
          }>).detail;
          const trackId = detail?.trackId;
          const ownerWellUid = detail?.managedWellUid;
          const appearance = detail?.appearance;
          const resolve = detail?.resolve;
          const reject = detail?.reject;
          if (
              !trackId
              || !ownerWellUid
              || !appearance
              || !looksLikeUuid(trackId)
              || canonicalRevisionRef.current < 0
          ) {
              reject?.(new Error("Completion appearance commit target is not canonical"));
              return;
          }

          void runSerializedCanonicalTask(async () => {
              const commitAtCurrentRevision = async (attempt: 1 | 2): Promise<void> => {
                  try {
                      const session = await fetchWlvJson<RawCanonicalSession>(
                          `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(ownerWellUid)}/tracks/update`,
                          {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                  expected_revision: canonicalRevisionRef.current,
                                  track_uid: trackId,
                                  completion_schematic_position: appearance.schematicPosition,
                                  completion_schematic_width_px: appearance.schematicWidthPx,
                                  completion_symbol_scale: appearance.symbolScale,
                                  completion_line_weight: appearance.lineWeight,
                                  completion_show_labels: appearance.showLabels,
                                  completion_label_position: appearance.labelPosition,
                                  completion_label_font_size: appearance.labelFontSize,
                                  completion_label_offset_px: appearance.labelOffsetPx,
                                  completion_label_vertical_offset_px: appearance.labelVerticalOffsetPx,
                                  completion_label_max_width_px: appearance.labelMaxWidthPx,
                                  completion_label_collision_mode: appearance.labelCollisionMode,
                                  completion_label_wrap: appearance.labelWrap,
                              }),
                          },
                      );
                      applyCanonicalSession(session, { preserveInteraction: true });
                      resolve?.();
                  } catch (error) {
                      if (
                          attempt === 1
                          && error instanceof Error
                          && error.message.startsWith('409 ')
                      ) {
                          await refreshCanonicalSession({ preserveInteraction: true });
                          await commitAtCurrentRevision(2);
                          return;
                      }
                      console.error('[WdvPageBoundary] canonical Completion appearance commit failed:', error);
                      reject?.(error);
                  }
              };
              await commitAtCurrentRevision(1);
          }).catch((error) => {
              console.error('[WdvPageBoundary] serialized Completion appearance commit failed:', error);
              reject?.(error);
          });
      };

      window.addEventListener(
          'wlv:completion-appearance-commit',
          handleCompletionAppearanceCommit as EventListener,
      );
      return () => window.removeEventListener(
          'wlv:completion-appearance-commit',
          handleCompletionAppearanceCommit as EventListener,
      );
  }, [applyCanonicalSession, refreshCanonicalSession, runSerializedCanonicalTask]);

  useEffect(() => {
      const flushCoreAppearanceCommit = async () => {
          const pending = pendingCoreAppearanceCommitRef.current;
          if (coreAppearanceCommitTimerRef.current !== null) {
              window.clearTimeout(coreAppearanceCommitTimerRef.current);
              coreAppearanceCommitTimerRef.current = null;
          }
          pendingCoreAppearanceCommitRef.current = null;
          if (
              !pending
              || !managedViewerWellUid
              || canonicalRevisionRef.current < 0
              || !looksLikeUuid(pending.trackId)
          ) return;

          // Core appearance is canonical track state. It must share the same
          // serialized mutation lane as Curve/track commands; otherwise a Curve
          // edit can advance the revision while this appearance write is in
          // flight, causing the 409 recovery refresh to erase the just-applied
          // Core appearance.
          await runSerializedCanonicalTask(async () => {
              const commitAtCurrentRevision = async (attempt: 1 | 2): Promise<void> => {
                  const commandBody = {
                      expected_revision: canonicalRevisionRef.current,
                      track_uid: pending.trackId,
                      core_base_color: pending.appearance.baseColor,
                      core_brightness: pending.appearance.brightness,
                      core_shading_mode: pending.appearance.shadingMode,
                      core_shading_strength: pending.appearance.shadingStrength,
                      core_description_overlay_enabled:
                        pending.appearance.descriptionPresentationMode !== 'core_centered',
                      core_description_overlay_position:
                        pending.appearance.descriptionPresentationMode === 'description_left_core_right'
                          ? 'left'
                          : 'right',
                      core_description_overlay_width_pct: pending.appearance.descriptionOverlayWidthPct,
                      core_description_overlay_font_size: pending.appearance.descriptionOverlayFontSize,
                      core_description_overlay_show_md: pending.appearance.descriptionOverlayShowMd,
                  };

                  try {
                      const session = await fetchWlvJson<RawCanonicalSession>(
                          `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(managedViewerWellUid)}/tracks/update`,
                          {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify(commandBody),
                          },
                      );
                      applyCanonicalSession(session, { preserveInteraction: true });
                  } catch (error) {
                      if (
                          attempt === 1
                          && error instanceof Error
                          && error.message.startsWith('409 ')
                      ) {
                          await refreshCanonicalSession({ preserveInteraction: true });
                          // Retry the user's appearance against the refreshed
                          // revision. A conflict refresh alone would lose the
                          // user's already-Applied Core styling.
                          await commitAtCurrentRevision(2);
                          return;
                      }
                      console.error('[WdvPageBoundary] canonical Core appearance commit failed:', error);
                  }
              };

              await commitAtCurrentRevision(1);
          });
      };

      const handleCoreAppearanceCommit = (event: Event) => {
          const detail = (event as CustomEvent<{
              trackId?: string;
              appearance?: CoreTrackAppearance;
              immediate?: boolean;
          }>).detail;
          if (!detail?.trackId || !detail.appearance) return;
          pendingCoreAppearanceCommitRef.current = {
              trackId: detail.trackId,
              appearance: { ...detail.appearance },
          };
          if (coreAppearanceCommitTimerRef.current !== null) {
              window.clearTimeout(coreAppearanceCommitTimerRef.current);
          }
          if (detail.immediate) {
              void flushCoreAppearanceCommit();
              return;
          }
          coreAppearanceCommitTimerRef.current = window.setTimeout(
              () => { void flushCoreAppearanceCommit(); },
              140,
          );
      };

      window.addEventListener('wlv:core-appearance-commit', handleCoreAppearanceCommit as EventListener);
      return () => {
          window.removeEventListener('wlv:core-appearance-commit', handleCoreAppearanceCommit as EventListener);
          if (coreAppearanceCommitTimerRef.current !== null) {
              window.clearTimeout(coreAppearanceCommitTimerRef.current);
              coreAppearanceCommitTimerRef.current = null;
          }
      };
  }, [applyCanonicalSession, managedViewerWellUid, refreshCanonicalSession, runSerializedCanonicalTask]);

  useEffect(() => {
      const handleDepthRangeLocatorCommit = (event: Event) => {
          const detail = (event as CustomEvent<{
              trackId?: string;
              config?: WellLogTrack['depthRangeLocator'];
          }>).detail;
          const trackId = detail?.trackId;
          const config = detail?.config;
          if (
              !trackId
              || !config
              || !managedViewerWellUid
              || canonicalRevisionRef.current < 0
              || !looksLikeUuid(trackId)
          ) return;

          void runSerializedCanonicalTask(async () => {
              const commitAtCurrentRevision = async (attempt: 1 | 2): Promise<void> => {
                  try {
                      const session = await fetchWlvJson<RawCanonicalSession>(
                          `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(managedViewerWellUid)}/tracks/update`,
                          {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                  expected_revision: canonicalRevisionRef.current,
                                  track_uid: trackId,
                                  depth_range_locator_enabled: config.enabled,
                                  depth_range_locator_source_track_uid: config.sourceTrackId || undefined,
                                  depth_range_locator_mode: config.mode,
                                  depth_range_locator_presentation: config.presentation,
                                  depth_range_locator_side: config.side,
                              }),
                          },
                      );
                      applyCanonicalSession(session, { preserveInteraction: true });
                  } catch (error) {
                      if (attempt === 1 && error instanceof Error && error.message.startsWith('409 ')) {
                          await refreshCanonicalSession({ preserveInteraction: true });
                          await commitAtCurrentRevision(2);
                          return;
                      }
                      console.error('[WdvPageBoundary] canonical Depth Range Locator commit failed:', error);
                  }
              };
              await commitAtCurrentRevision(1);
          });
      };
      window.addEventListener('wlv:depth-range-locator-commit', handleDepthRangeLocatorCommit as EventListener);
      return () => window.removeEventListener('wlv:depth-range-locator-commit', handleDepthRangeLocatorCommit as EventListener);
  }, [applyCanonicalSession, managedViewerWellUid, refreshCanonicalSession, runSerializedCanonicalTask]);

  useEffect(() => {
      const handleMacroCoreImageCommit = (event: Event) => {
          const detail = (event as CustomEvent<{
              trackId?: string;
              managedWellUid?: string | null;
              config?: MacroCoreImageConfig;
              resolve?: () => void;
              reject?: (error: unknown) => void;
          }>).detail;
          const trackId = detail?.trackId;
          const ownerWellUid = detail?.managedWellUid;
          const config = detail?.config;
          const resolve = detail?.resolve;
          const reject = detail?.reject;
          if (!trackId || !ownerWellUid || !config || !looksLikeUuid(trackId) || canonicalRevisionRef.current < 0) {
              reject?.(new Error("Macro Core Image commit target is not canonical"));
              return;
          }
          if (!Number.isFinite(config.topMd) || !Number.isFinite(config.baseMd) || config.baseMd <= config.topMd) {
              reject?.(new Error("Macro Core Image Base MD must be greater than Top MD"));
              return;
          }

          void runSerializedCanonicalTask(async () => {
              const commitAtCurrentRevision = async (attempt: 1 | 2): Promise<void> => {
                  try {
                      const session = await fetchWlvJson<RawCanonicalSession>(
                          `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(ownerWellUid)}/tracks/update`,
                          {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                  expected_revision: canonicalRevisionRef.current,
                                  track_uid: trackId,
                                  macro_core_image_enabled: config.enabled,
                                  macro_core_image_top_md: config.topMd,
                                  macro_core_image_base_md: config.baseMd,
                                  macro_core_image_placement: config.placement,
                                  macro_core_image_horizontal_offset_px: config.horizontalOffsetPx,
                              }),
                          },
                      );
                      applyCanonicalSession(session, { preserveInteraction: true });
                      resolve?.();
                  } catch (error) {
                      if (attempt === 1 && error instanceof Error && error.message.startsWith('409 ')) {
                          await refreshCanonicalSession({ preserveInteraction: true });
                          await commitAtCurrentRevision(2);
                          return;
                      }
                      console.error('[WdvPageBoundary] canonical Macro Core Image commit failed:', error);
                      reject?.(error);
                  }
              };
              await commitAtCurrentRevision(1);
          });
      };
      window.addEventListener('wlv:macro-core-image-commit', handleMacroCoreImageCommit as EventListener);
      return () => window.removeEventListener('wlv:macro-core-image-commit', handleMacroCoreImageCommit as EventListener);
  }, [applyCanonicalSession, refreshCanonicalSession, runSerializedCanonicalTask]);

  useEffect(() => {
      const handleTextOverlaysCommit = (event: Event) => {
          const detail = (event as CustomEvent<{
              trackId?: string;
              managedWellUid?: string | null;
              textOverlays?: TextOverlayConfig[];
              resolve?: () => void;
              reject?: (error: unknown) => void;
          }>).detail;
          const trackId = detail?.trackId;
          const ownerWellUid = detail?.managedWellUid;
          const textOverlays = detail?.textOverlays;
          const resolve = detail?.resolve;
          const reject = detail?.reject;
          if (!trackId || !ownerWellUid || !looksLikeUuid(trackId) || canonicalRevisionRef.current < 0 || !Array.isArray(textOverlays)) {
              reject?.(new Error("Text Box commit target is not canonical"));
              return;
          }

          void runSerializedCanonicalTask(async () => {
              const commitAtCurrentRevision = async (attempt: 1 | 2): Promise<void> => {
                  try {
                      const session = await fetchWlvJson<RawCanonicalSession>(
                          `/api/wlv/inventory/wdv/session/${encodeURIComponent(ownerWellUid)}/tracks/${encodeURIComponent(trackId)}/text-overlays`,
                          {
                              method: 'PUT',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                  expected_revision: canonicalRevisionRef.current,
                                  text_overlays: textOverlays.map((item) => ({
                                      overlay_uid: item.overlayUid,
                                      content_html: item.contentHtml,
                                      md: item.md,
                                      horizontal_anchor: item.horizontalAnchor,
                                      horizontal_offset: item.horizontalOffset,
                                      vertical_offset: item.verticalOffset,
                                      width_percent: item.widthPercent,
                                      font_size: item.fontSize,
                                      color: item.color,
                                      background: item.background,
                                      text_align: item.textAlign,
                                  })),
                              }),
                          },
                      );
                      applyCanonicalSession(session, { preserveInteraction: true });
                      resolve?.();
                  } catch (error) {
                      if (attempt === 1 && error instanceof Error && error.message.startsWith('409 ')) {
                          await refreshCanonicalSession({ preserveInteraction: true });
                          await commitAtCurrentRevision(2);
                          return;
                      }
                      console.error('[WdvPageBoundary] canonical Text Box Overlay commit failed:', error);
                      reject?.(error);
                  }
              };
              await commitAtCurrentRevision(1);
          }).catch((error) => {
              console.error('[WdvPageBoundary] serialized Text Box Overlay commit failed:', error);
              reject?.(error);
          });
      };
      window.addEventListener('wlv:text-overlays-commit', handleTextOverlaysCommit as EventListener);
      return () => window.removeEventListener('wlv:text-overlays-commit', handleTextOverlaysCommit as EventListener);
  }, [applyCanonicalSession, refreshCanonicalSession, runSerializedCanonicalTask]);

  const applyCurveFillWorkflowResult = useCallback((result: CurveFillWorkflowResultV2<RawCanonicalSession>): void => {
      setCurveFillGeometryByRuleUid((current) => applyCurveFillGeometryDeltaV2(current, result.geometry_delta));
      applyCanonicalSession(result.session, { preserveInteraction: true });
  }, [applyCanonicalSession]);

  const createCurveFillRule = useCallback(async (
      body: Readonly<Record<string, unknown>>,
  ): Promise<string | null> => {
      if (
          !managedViewerWellUid
          || !curveFillFeatureEnabled
          || canonicalRevisionRef.current < 0
      ) return null;

      const existingRuleUids = new Set(
          (canonicalSession?.curve_fills ?? []).map((rule) => rule.rule_uid),
      );

      setCurveFillPending(true);
      setCurveFillError(null);

      const executeCreate = async (attempt: 1 | 2): Promise<string | null> => {
          const expectedRevision = canonicalRevisionRef.current;
          recordWdvDiagnosticEvent('curve-fill', attempt === 1 ? 'create:start' : 'create:retry', {
              managedWellUid: managedViewerWellUid,
              revision: expectedRevision,
              attempt,
              body,
          });

          const result = await createCurveFillRuleV2<RawCanonicalSession>(
              managedViewerWellUid,
              {
                  ...body,
                  expected_revision: expectedRevision,
              },
          );
          applyCurveFillWorkflowResult(result);

          const createdRule = [...(result.session.curve_fills ?? [])]
              .reverse()
              .find((rule) => (
                  !existingRuleUids.has(rule.rule_uid)
                  && rule.track_uid === body.track_uid
                  && rule.curve_a_assignment_uid === body.curve_a_assignment_uid
                  && (body.curve_b_assignment_uid == null
                      || rule.curve_b_assignment_uid === body.curve_b_assignment_uid)
              ));

          recordWdvDiagnosticEvent('curve-fill', 'create:end', {
              outcome: 'success',
              attempt,
              responseRevision: result.session.revision,
              ruleUid: createdRule?.rule_uid ?? null,
              trackUid: createdRule?.track_uid ?? body.track_uid ?? null,
              assignmentUid: createdRule?.curve_a_assignment_uid ?? body.curve_a_assignment_uid ?? null,
              secondAssignmentUid: createdRule?.curve_b_assignment_uid ?? body.curve_b_assignment_uid ?? null,
              ruleType: createdRule?.rule_type ?? body.rule_type ?? null,
              comparison: createdRule?.comparison ?? body.comparison ?? null,
              boundary: createdRule?.boundary ?? body.boundary ?? null,
              style: createdRule?.style ?? body.style ?? null,
              depthExtent: createdRule?.depth_extent ?? body.depth_extent ?? null,
          });
          return createdRule?.rule_uid ?? null;
      };

      try {
          return await executeCreate(1);
      } catch (firstError) {
          if (isCurveFillRevisionConflict(firstError)) {
              recordWdvDiagnosticEvent('curve-fill', 'create:conflict', {
                  managedWellUid: managedViewerWellUid,
                  failedRevision: canonicalRevisionRef.current,
                  error: firstError instanceof Error ? firstError.message : String(firstError),
                  trackUid: body.track_uid ?? null,
                  assignmentUid: body.curve_a_assignment_uid ?? null,
                  secondAssignmentUid: body.curve_b_assignment_uid ?? null,
              });
              await refreshCanonicalSession({ preserveInteraction: true });
              try {
                  return await executeCreate(2);
              } catch (retryError) {
                  recordWdvDiagnosticEvent('curve-fill', 'create:end', {
                      outcome: 'error',
                      attempt: 2,
                      error: retryError instanceof Error ? retryError.message : String(retryError),
                  });
                  setCurveFillError(retryError instanceof Error ? retryError.message : 'Curve Fill command failed');
                  return null;
              }
          }

          recordWdvDiagnosticEvent('curve-fill', 'create:end', {
              outcome: 'error',
              attempt: 1,
              error: firstError instanceof Error ? firstError.message : String(firstError),
          });
          setCurveFillError(firstError instanceof Error ? firstError.message : 'Curve Fill command failed');
          return null;
      } finally {
          setCurveFillPending(false);
      }
  }, [
      applyCurveFillWorkflowResult,
      canonicalSession,
      curveFillFeatureEnabled,
      managedViewerWellUid,
      refreshCanonicalSession,
  ]);

  const removeCurveFillRule = useCallback(async (ruleUid: string): Promise<void> => {
      if (!managedViewerWellUid || !curveFillFeatureEnabled || canonicalRevisionRef.current < 0) return;
      setCurveFillPending(true); setCurveFillError(null);
      recordWdvDiagnosticEvent('curve-fill', 'remove:start', {
          managedWellUid: managedViewerWellUid,
          revision: canonicalRevisionRef.current,
          ruleUid,
      });
      try {
          const result = await removeCurveFillRuleV2<RawCanonicalSession>(managedViewerWellUid, canonicalRevisionRef.current, ruleUid);
          applyCurveFillWorkflowResult(result);
          recordWdvDiagnosticEvent('curve-fill', 'remove:end', {
              outcome: 'success',
              responseRevision: result.session.revision,
              ruleUid,
          });
      } catch (error) {
          recordWdvDiagnosticEvent('curve-fill', 'remove:end', {
              outcome: 'error',
              ruleUid,
              error: error instanceof Error ? error.message : String(error),
          });
          setCurveFillError(error instanceof Error ? error.message : 'Curve Fill delete failed');
          await refreshCanonicalSession({ preserveInteraction: true });
      } finally { setCurveFillPending(false); }
  }, [applyCurveFillWorkflowResult, curveFillFeatureEnabled, managedViewerWellUid, refreshCanonicalSession]);

  const updateCurveFillRule = useCallback(async (ruleUid: string, patch: Readonly<Record<string, unknown>>): Promise<void> => {
      if (!managedViewerWellUid || !curveFillFeatureEnabled || canonicalRevisionRef.current < 0) return;
      setCurveFillPending(true); setCurveFillError(null);
      recordWdvDiagnosticEvent('curve-fill', 'update:start', {
          managedWellUid: managedViewerWellUid,
          revision: canonicalRevisionRef.current,
          ruleUid,
          patch,
      });
      try {
          const result = await updateCurveFillRuleV2<RawCanonicalSession>(managedViewerWellUid, {
              expected_revision: canonicalRevisionRef.current,
              rule_uid: ruleUid,
              ...patch,
          });
          applyCurveFillWorkflowResult(result);
          const updatedRule = (result.session.curve_fills ?? []).find((rule) => rule.rule_uid === ruleUid);
          recordWdvDiagnosticEvent('curve-fill', 'update:end', {
              outcome: 'success',
              responseRevision: result.session.revision,
              ruleUid,
              trackUid: updatedRule?.track_uid ?? null,
              assignmentUid: updatedRule?.curve_a_assignment_uid ?? null,
              secondAssignmentUid: updatedRule?.curve_b_assignment_uid ?? null,
              ruleType: updatedRule?.rule_type ?? null,
              comparison: updatedRule?.comparison ?? null,
              boundary: updatedRule?.boundary ?? null,
              style: updatedRule?.style ?? null,
              depthExtent: updatedRule?.depth_extent ?? null,
          });
      } catch (error) {
          recordWdvDiagnosticEvent('curve-fill', 'update:end', {
              outcome: 'error',
              ruleUid,
              error: error instanceof Error ? error.message : String(error),
          });
          setCurveFillError(error instanceof Error ? error.message : 'Curve Fill update failed');
          await refreshCanonicalSession({ preserveInteraction: true });
      } finally { setCurveFillPending(false); }
  }, [applyCurveFillWorkflowResult, curveFillFeatureEnabled, managedViewerWellUid, refreshCanonicalSession]);

  const reorderCurveFillRules = useCallback(async (trackUid: string, ruleUids: readonly string[]): Promise<void> => {
      if (!managedViewerWellUid || !curveFillFeatureEnabled || canonicalRevisionRef.current < 0) return;
      setCurveFillPending(true); setCurveFillError(null);
      recordWdvDiagnosticEvent('curve-fill', 'reorder:start', {
          managedWellUid: managedViewerWellUid,
          revision: canonicalRevisionRef.current,
          trackUid,
          ruleUids,
      });
      try {
          const result = await reorderCurveFillRulesV2<RawCanonicalSession>(managedViewerWellUid, {
              expected_revision: canonicalRevisionRef.current,
              track_uid: trackUid,
              rule_uids: ruleUids,
          });
          applyCurveFillWorkflowResult(result);
          recordWdvDiagnosticEvent('curve-fill', 'reorder:end', {
              outcome: 'success',
              responseRevision: result.session.revision,
              trackUid,
              ruleUids,
          });
      } catch (error) {
          recordWdvDiagnosticEvent('curve-fill', 'reorder:end', {
              outcome: 'error',
              trackUid,
              ruleUids,
              error: error instanceof Error ? error.message : String(error),
          });
          setCurveFillError(error instanceof Error ? error.message : 'Curve Fill reorder failed');
          await refreshCanonicalSession({ preserveInteraction: true });
      } finally { setCurveFillPending(false); }
  }, [applyCurveFillWorkflowResult, curveFillFeatureEnabled, managedViewerWellUid, refreshCanonicalSession]);

  useEffect(() => {
      if (!managedViewerWellUid || canonicalSession === null || curveFillPending) return;
      const enabledRules = (canonicalSession.curve_fills ?? []).filter(
          (rule) => rule.enabled && rule.managed_well_uid === managedViewerWellUid,
      );
      if (!curveFillFeatureEnabled && enabledRules.length === 0) return;
      const missingRules = enabledRules.filter(
          (rule) => rule.state !== 'resolved' || !curveFillGeometryByRuleUid.has(rule.rule_uid),
      );
      if (missingRules.length === 0) {
          // A completed hydration must not permanently suppress recovery. Zoom,
          // refresh, or render-bundle reconstruction can later drop only the
          // client geometry while the canonical rule remains enabled.
          curveFillHydrationKeyRef.current = '';
          return;
      }

      // Hydration mutates canonical rule state and therefore advances the session
      // revision. A revision-based key re-triggered hydration after every response,
      // creating a continuous background writer that starved interactive commands.
      // The signature below changes only when the material rule definition changes.
      const ruleSignature = enabledRules.map((rule) => JSON.stringify({
          rule_uid: rule.rule_uid,
          track_uid: rule.track_uid,
          curve_a_assignment_uid: rule.curve_a_assignment_uid,
          curve_b_assignment_uid: rule.curve_b_assignment_uid,
          order: rule.order,
          enabled: rule.enabled,
          rule_type: rule.rule_type,
          comparison: rule.comparison,
          boundary: rule.boundary,
          overlay_policy_uid: rule.overlay_policy_uid,
          overlay_policy_revision: rule.overlay_policy_revision,
          deadband: rule.deadband,
          minimum_interval: rule.minimum_interval,
          depth_extent: rule.depth_extent,
          interval_from_md: rule.interval_from_md,
          interval_to_md: rule.interval_to_md,
          style: rule.style,
      })).join('|');
      const missingRuleSignature = missingRules
          .map((rule) => rule.rule_uid)
          .sort()
          .join(',');
      const key = `${managedViewerWellUid}:${ruleSignature}:missing=${missingRuleSignature}`;
      if (curveFillHydrationKeyRef.current === key) return;
      curveFillHydrationKeyRef.current = key;
      setCurveFillPending(true);
      setCurveFillError(null);

      const hydrate = async (): Promise<void> => {
          try {
              const result = await hydrateCurveFillV2<RawCanonicalSession>(
                  managedViewerWellUid,
                  canonicalRevisionRef.current,
              );
              applyCurveFillWorkflowResult(result);
          } catch (error) {
              setCurveFillError(error instanceof Error ? error.message : 'Curve Fill hydration failed');
              if (error instanceof Error && error.message.startsWith('409 ')) {
                  await refreshCanonicalSession({ preserveInteraction: true });
              }
          } finally {
              setCurveFillPending(false);
          }
      };

      // Hydration shares the same revision-sensitive lane as interactive WDV
      // mutations. It can no longer race a curve checkbox command.
      void runSerializedCanonicalTask(hydrate);
  }, [
      applyCurveFillWorkflowResult,
      canonicalSession,
      curveFillFeatureEnabled,
      curveFillGeometryByRuleUid,
      curveFillPending,
      managedViewerWellUid,
      refreshCanonicalSession,
      runSerializedCanonicalTask,
  ]);


  /*
   * Do not discover Curve Fill work by scanning every represented well.
   * The unified canonical session is the durable canvas authority. Hydrating
   * per-well sessions that are not represented by enabled canonical rules
   * creates revision writers unrelated to the visible canvas and can starve
   * the rule that actually needs geometry after Saved Canvas restore.
   */

  /*
   * Durable Curve Fill recovery must hydrate against the rule OWNER well.
   * The unified canvas session can contain rules from background wells, so
   * using the currently active well UID can leave a valid canonical fill rule
   * with no client geometry after restart.
   */
  useEffect(() => {
      if (!curveFillFeatureEnabled) return;
      const missingByOwner = new Map<string, CanonicalCurveFillRuleV2[]>();
      for (const rule of canonicalSession?.curve_fills ?? []) {
          if (!rule.enabled || curveFillGeometryByRuleUid.has(rule.rule_uid)) continue;
          const ownerWellUid = rule.managed_well_uid;
          if (!ownerWellUid) continue;
          const current = missingByOwner.get(ownerWellUid) ?? [];
          current.push(rule);
          missingByOwner.set(ownerWellUid, current);
      }
      if (missingByOwner.size === 0) return;

      let cancelled = false;
      const hydrateOwners = async (): Promise<void> => {
          for (const [ownerWellUid, rules] of missingByOwner) {
              if (cancelled) return;
              const materialSignature = rules
                  .map((rule) => JSON.stringify({
                      rule_uid: rule.rule_uid,
                      track_uid: rule.track_uid,
                      curve_a_assignment_uid: rule.curve_a_assignment_uid,
                      curve_b_assignment_uid: rule.curve_b_assignment_uid,
                      order: rule.order,
                      enabled: rule.enabled,
                      rule_type: rule.rule_type,
                      comparison: rule.comparison,
                      boundary: rule.boundary,
                      overlay_policy_uid: rule.overlay_policy_uid,
                      overlay_policy_revision: rule.overlay_policy_revision,
                      deadband: rule.deadband,
                      minimum_interval: rule.minimum_interval,
                      depth_extent: rule.depth_extent,
                      interval_from_md: rule.interval_from_md,
                      interval_to_md: rule.interval_to_md,
                      style: rule.style,
                  }))
                  .sort()
                  .join('|');
              const key = `owner-recovery:${ownerWellUid}:${materialSignature}`;
              if (
                  backgroundCurveFillHydrationKeysRef.current.has(key)
                  || completedCurveFillHydrationKeysRef.current.has(key)
              ) {
                  continue;
              }
              backgroundCurveFillHydrationKeysRef.current.add(key);
              try {
                  const session = await fetchWlvJson<RawCanonicalSession>(
                      `/api/wlv/v2/wdv/sessions/${encodeURIComponent(ownerWellUid)}`,
                  );
                  if (cancelled) return;
                  const result = await hydrateCurveFillV2<RawCanonicalSession>(
                      ownerWellUid,
                      session.revision,
                  );
                  if (cancelled) return;
                  setCurveFillGeometryByRuleUid((current) =>
                      applyCurveFillGeometryDeltaV2(current, result.geometry_delta));
                  completedCurveFillHydrationKeysRef.current.add(key);
              } catch {
                  // A later semantic hydration pass may retry from fresh canonical authority.
              } finally {
                  backgroundCurveFillHydrationKeysRef.current.delete(key);
              }
          }
      };
      void hydrateOwners();

      return () => { cancelled = true; };
  }, [
      canonicalSession?.curve_fills,
      curveFillFeatureEnabled,
      curveFillGeometryByRuleUid,
      startupHydrationRetryTick,
  ]);

  const loadCompleteLas = useCallback(async (): Promise<void> => {
      if (!managedViewerWellUid || !completeLasSourceId || canonicalRevisionRef.current < 0) return;
      setCompleteLasPending(true);
      setCompleteLasError(null);
      setCompleteLasResult(null);
      try {
          const response = await fetchWlvJson<CompleteLasLoadResponse>(
              buildCompleteLasLoadUrl(managedViewerWellUid),
              {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(buildCompleteLasLoadRequest({
                      expectedRevision: canonicalRevisionRef.current,
                      sourceId: completeLasSourceId,
                      placement: 'append_tracks',
                      includeReviewRequired: completeLasIncludeReview,
                  })),
              },
          );
          applyCanonicalSession(response.session);
          setViewerPackageRefreshRevision((current) => current + 1);
          setCompleteLasResult(`${response.added_managed_curve_uids.length} LAS curve track(s) appended; ${response.skipped_existing_managed_curve_uids.length} existing assignment(s) skipped.`);
      } catch (error) {
          if (error instanceof Error && /409|revision/i.test(error.message)) {
              await refreshCanonicalSession();
          }
          setCompleteLasError(error instanceof Error ? error.message : 'Unable to load complete LAS');
      } finally {
          setCompleteLasPending(false);
      }
  }, [applyCanonicalSession, completeLasIncludeReview, completeLasSourceId, managedViewerWellUid, refreshCanonicalSession]);

  const changeCommonDepthUnit = useCallback(async (commonDepthUnit: 'm' | 'ft'): Promise<void> => {
      const currentDepthUnit = wdvWorkspace?.common_depth_unit ?? 'm';
      if (commonDepthUnit === currentDepthUnit) return;

      try {
          const workspace = await fetchWlvJson<WdvWorkspaceState>('/api/wlv/inventory/wdv-workspace/common-depth-unit', {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ common_depth_unit: commonDepthUnit }),
          });

          // Viewport state is expressed in the active display unit. Convert it
          // before the new-unit sample ranges arrive, so the full-range effect
          // never clamps old-unit viewport numbers against new-unit bounds.
          setViewDepthRange((range) => convertDepthUnitRange(range, currentDepthUnit, commonDepthUnit));
          setViewHistory((history) => history.map((range) => convertDepthUnitRange(range, currentDepthUnit, commonDepthUnit)));
          setCombinationGroupViewRange((range) => range === null
              ? null
              : convertDepthUnitRange(range, currentDepthUnit, commonDepthUnit));
          setCombinationGroupHistory((history) => history.map(
              (range) => convertDepthUnitRange(range, currentDepthUnit, commonDepthUnit),
          ));
          setTrackDepthRangesById((ranges) => Object.fromEntries(
              Object.entries(ranges).map(([trackId, range]) => [
                  trackId,
                  convertDepthUnitRange(range, currentDepthUnit, commonDepthUnit),
              ]),
          ));
          setGoToDepthMarker((depth) => depth === null
              ? null
              : convertDepthUnitValue(depth, currentDepthUnit, commonDepthUnit));
          setGoToDepthValue((value) => {
              const depth = Number.parseFloat(value);
              if (!Number.isFinite(depth)) return value;
              const converted = convertDepthUnitValue(depth, currentDepthUnit, commonDepthUnit);
              return String(Number(converted.toFixed(6)));
          });
          setIntervalSelection((selection) => selection === null
              ? null
              : {
                  ...selection,
                  startDepth: convertDepthUnitValue(selection.startDepth, currentDepthUnit, commonDepthUnit),
                  currentDepth: convertDepthUnitValue(selection.currentDepth, currentDepthUnit, commonDepthUnit),
              });
          setDragPanState((state) => state === null
              ? null
              : {
                  ...state,
                  startRange: convertDepthUnitRange(state.startRange, currentDepthUnit, commonDepthUnit),
              });
          setFullDepthRangesByWellUid((ranges) => Object.fromEntries(
              Object.entries(ranges).map(([wellUid, range]) => [
                  wellUid,
                  convertDepthUnitRange(range, currentDepthUnit, commonDepthUnit),
              ]),
          ));

          // Keep the existing rendered curves and their authoritative contracts
          // in the same unit as the converted viewport while the backend reloads
          // the target-unit sample payloads. Without this synchronous conversion,
          // the full-range effect can immediately replace the converted viewport
          // with stale source-unit contract numbers (for example 176-5330 m
          // relabelled as ft), which places the actual feet samples off-screen.
          setManagedSamplesByCurveId((samplesByCurveId) => Object.fromEntries(
              Object.entries(samplesByCurveId).map(([curveId, samples]) => [
                  curveId,
                  samples.map((sample) => ({
                      ...sample,
                      depth: convertDepthUnitValue(sample.depth, currentDepthUnit, commonDepthUnit),
                  })),
              ]),
          ));
          setManagedSampleContractsByCurveId((contractsByCurveId) => Object.fromEntries(
              Object.entries(contractsByCurveId).map(([curveId, contract]) => [
                  curveId,
                  {
                      ...contract,
                      depth_unit: commonDepthUnit,
                      depth_min: typeof contract.depth_min === 'number' && Number.isFinite(contract.depth_min)
                          ? convertDepthUnitValue(contract.depth_min, currentDepthUnit, commonDepthUnit)
                          : contract.depth_min,
                      depth_max: typeof contract.depth_max === 'number' && Number.isFinite(contract.depth_max)
                          ? convertDepthUnitValue(contract.depth_max, currentDepthUnit, commonDepthUnit)
                          : contract.depth_max,
                  },
              ]),
          ));
          if (previousCanvasFullDepthRangeRef.current !== null) {
              previousCanvasFullDepthRangeRef.current = convertDepthUnitRange(
                  previousCanvasFullDepthRangeRef.current,
                  currentDepthUnit,
                  commonDepthUnit,
              );
          }

          // Curve-fill geometry is returned in the workspace common depth unit.
          // Discard the old-unit geometry and force a fresh hydration so fills
          // remain aligned with curves after switching metres/feet.
          setCurveFillGeometryByRuleUid(new Map());
          curveFillHydrationKeyRef.current = null;
          backgroundCurveFillHydrationKeysRef.current.clear();
          completedCurveFillHydrationKeysRef.current.clear();

          setWdvWorkspace(workspace);
          setWdvWorkspaceError(null);
      } catch (error) {
          setWdvWorkspaceError(error instanceof Error ? error.message : 'Unable to change Common Depth Unit');
      }
  }, [wdvWorkspace?.common_depth_unit]);

  const refreshWdvWorkspace = async () => {
      try {
          const workspace = await fetchWlvJson<WdvWorkspaceState>('/api/wlv/inventory/wdv-workspace');
          setWdvWorkspace(workspace);
          setWdvWorkspaceError(null);
          const loadedIdentities = workspace.loaded_wells.map(managedWellIdentityFromPayload);
          const activeIdentity = workspace.active_managed_well_id && workspace.active_managed_well_uid
              ? managedWellIdentityFromPayload({
                  managed_well_id: workspace.active_managed_well_id,
                  managed_well_uid: workspace.active_managed_well_uid,
              })
              : loadedIdentities[0] ?? null;
          setManagedViewerWell((current) => {
              const currentIsLoaded = loadedIdentities.some((identity) => sameManagedWellIdentity(identity, current));
              return currentIsLoaded ? current : activeIdentity;
          });
          return workspace;
      }
      catch (error) {
          setWdvWorkspaceError(error instanceof Error ? error.message : 'WDV workspace unavailable');
          return null;
      }
  };
  useEffect(() => {
      if (activeView !== 'log-viewer')
          return undefined;
      let cancelled = false;
      void refreshWdvWorkspace().then((workspace) => {
          if (cancelled || !workspace)
              return;
          const activeWell = workspace.active_managed_well_id && workspace.active_managed_well_uid
              ? managedWellIdentityFromPayload({
                  managed_well_id: workspace.active_managed_well_id,
                  managed_well_uid: workspace.active_managed_well_uid,
              })
              : workspace.loaded_wells[0]
                  ? managedWellIdentityFromPayload(workspace.loaded_wells[0])
                  : null;
          if (activeWell)
              setManagedViewerWell(activeWell);
      });
      const handleFocus = () => { void refreshWdvWorkspace(); };
      window.addEventListener('focus', handleFocus);
      return () => {
          cancelled = true;
          window.removeEventListener('focus', handleFocus);
      };
  }, [activeView]);
  const changeActiveWdvWell = async (identity: ManagedWellIdentity) => {
      const managedWellId = identity.managedWellId;
      if (!managedWellId || wdvWorkspace?.active_managed_well_id === managedWellId || activeWellSwitchTargetRef.current === managedWellId)
          return;
      activeWellSwitchAbortRef.current?.abort();
      const controller = new AbortController();
      activeWellSwitchAbortRef.current = controller;
      activeWellSwitchTargetRef.current = managedWellId;
      try {
          const workspace = await fetchWlvJson<WdvWorkspaceState>('/api/wlv/inventory/wdv-workspace/active-well', {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ managed_well_id: identity.managedWellId, managed_well_uid: identity.managedWellUid }),
              signal: controller.signal,
          });
          if (controller.signal.aborted || activeWellSwitchTargetRef.current !== managedWellId)
              return;
          setWdvWorkspace(workspace);
          setWdvWorkspaceError(null);
          if (!workspace.active_managed_well_id || !workspace.active_managed_well_uid) {
              throw new Error('Backend WDV workspace did not return the active managed-well identity pair.');
          }
          setManagedViewerWell(managedWellIdentityFromPayload({
              managed_well_id: workspace.active_managed_well_id,
              managed_well_uid: workspace.active_managed_well_uid,
          }));
          setPendingAddTrackCurveIds([]);
          setAddTrackCurveSelectionMode(false);
      }
      catch (error) {
          if (!controller.signal.aborted && !isAbortError(error)) {
              setWdvWorkspaceError(error instanceof Error ? error.message : 'Unable to switch active WDV well');
          }
      }
      finally {
          if (activeWellSwitchAbortRef.current === controller)
              activeWellSwitchAbortRef.current = null;
          if (activeWellSwitchTargetRef.current === managedWellId)
              activeWellSwitchTargetRef.current = null;
      }
  };
  const activateCanvasSelectionWell = (nextSelection: SelectionRef) => {
      /*
       * Selection may switch the active inventory well for properties/catalogs,
       * but unified-canvas persistence stays independent of that context.
       */
      setSelection(nextSelection);
      const ownerWellUid = managedWellUidForCanvasSelection(tracksRef.current, nextSelection);
      if (!ownerWellUid || ownerWellUid === managedViewerWellUid)
          return;
      const ownerWell = wdvWorkspace?.loaded_wells.find((well) => well.managed_well_uid === ownerWellUid);
      if (!ownerWell) {
          setWdvWorkspaceError('Selected canvas item belongs to a well that is not present in the backend WDV workspace.');
          return;
      }
      void changeActiveWdvWell(managedWellIdentityFromPayload(ownerWell)).catch((error) => {
          setWdvWorkspaceError(error instanceof Error ? error.message : 'Unable to activate selected canvas well');
      });
  };
  const selectCanvasTrack = (trackId: string, additive = false) => {
      // Selection/highlighting is orthogonal to viewport state. A header/body
      // click must never normalize, reset, replace, or otherwise mutate any
      // track/group zoom state.
      const currentTrackId = selectionRef.current.trackId;

      if (additive) {
          /*
           * WDV_OVERLAY_SELECTED_TRACKS_PRIMARY_SELECTION_V1_0_0
           *
           * Additive (⌘-click) selection builds a target set without moving the
           * primary active track. This lets the Properties/standalone inspector
           * remain anchored to the source track while additional tracks are
           * selected for multi-track actions such as Formation Tops Extend.
           */
          const base =
              multiHighlightedTrackIds.length > 0
                  ? multiHighlightedTrackIds
                  : currentTrackId
                      ? [currentTrackId]
                      : [];

          const removing = base.includes(trackId);
          const next = removing
              ? base.filter((id) => id !== trackId)
              : [...base, trackId];

          setMultiHighlightedTrackIds(next);

          if (!currentTrackId && !removing) {
              activateCanvasSelectionWell({ kind: 'track', trackId });
          }
          return;
      }

      setMultiHighlightedTrackIds([]);

      // Plain MB1 is a true toggle.
      if (
          selectionRef.current.kind === 'track'
          && currentTrackId === trackId
      ) {
          setSelection({ kind: 'track', trackId: '' });
          return;
      }

      activateCanvasSelectionWell({ kind: 'track', trackId });
  };
  const selectCanvasCurve = (trackId: string, assignmentId: string) => {
      activateCanvasSelectionWell({ kind: 'curve', trackId, assignmentId });
  };

  useEffect(() => {
      if (!managedViewerWellId || !wdvWorkspace)
          return;
      if (wdvWorkspace.active_managed_well_id === managedViewerWellId)
          return;
      if (managedViewerWell)
          void changeActiveWdvWell(managedViewerWell);
  }, [managedViewerWellId, managedViewerWellUid, wdvWorkspace?.active_managed_well_id, wdvWorkspace?.active_managed_well_uid]);

  /*
   * WDV_UNIFIED_CANVAS_ACTIVE_WELL_SELECTION_ISOLATION_V1_0_0
   *
   * Canonical startup layout is a true startup action for the mounted unified
   * canvas. Canvas selection may legitimately change the active inventory well
   * (properties/catalog context), which changes `wdvSessionKey`. That context
   * switch must NOT be interpreted as a new canvas startup/hydration event,
   * otherwise backend `selected_track_uid: null` can reapply startup selection
   * and force the first canonical track (T1 / Measured Depth).
   *
   * Apply startup layout once per mounted WDV canvas. A real page/restart remount
   * naturally gets a fresh ref and hydrates again.
   */
  const canonicalStartupAppliedRef = useRef(false);

  useEffect(() => {
    if (layoutSource.mode !== 'ready') return;
    if (layoutSource.managedWellUid !== managedViewerWellUid) return;
    if (canonicalStartupAppliedRef.current) return;

    applyCanonicalStartupLayout(layoutSource.tracks, layoutSource.selectedTrackId);
    canonicalStartupAppliedRef.current = true;
  }, [
    applyCanonicalStartupLayout,
    layoutSource,
    managedViewerWellUid,
  ]);
  useEffect(() => {
      recommendationAbortRef.current?.abort();
      const controller = new AbortController();
      recommendationAbortRef.current = controller;
      const generation = recommendationGenerationRef.current + 1;
      recommendationGenerationRef.current = generation;
      if (!hasLoadedViewerWell || wdvPackageState.loadedCurveItems.length === 0 || managedSamplesLoading) {
          setWdvTemplateRecommendations([]);
          setWdvTemplateRecommendationsError(null);
          setSelectedWdvTemplateKey('');
          setWdvTemplateModalOpen(false);
          setWdvTemplateRecommendationsLoading(false);
          return () => controller.abort();
      }
      setWdvTemplateRecommendationsLoading(true);
      setWdvTemplateRecommendationsError(null);
      void evaluateWdvTemplateRecommendations(wdvPackageState.loadedCurveItems, controller.signal)
          .then((result) => {
          if (controller.signal.aborted || recommendationGenerationRef.current !== generation)
              return;
          const recommendations = [...(result.recommendations ?? [])].sort((a, b) => a.rank - b.rank);
          setWdvTemplateRecommendations(recommendations);
          setSelectedWdvTemplateKey((current) => (current && recommendations.some((item) => item.template_key === current) ? current : ''));
      })
          .catch((error) => {
          if (controller.signal.aborted || recommendationGenerationRef.current !== generation || isAbortError(error))
              return;
          setWdvTemplateRecommendations([]);
          setSelectedWdvTemplateKey('');
          setWdvTemplateModalOpen(false);
          setWdvTemplateRecommendationsError(error instanceof Error ? error.message : 'Template recommendation service unavailable');
      })
          .finally(() => {
          if (!controller.signal.aborted && recommendationGenerationRef.current === generation) {
              setWdvTemplateRecommendationsLoading(false);
          }
      });
      return () => {
          controller.abort();
          if (recommendationAbortRef.current === controller)
              recommendationAbortRef.current = null;
      };
  }, [hasLoadedViewerWell, managedSamplesLoading, recommendationRefreshRevision, wdvPackageState.loadedCurveItems]);
  const selectedWdvTemplateRecommendation = useMemo(() => wdvTemplateRecommendations.find((item) => item.template_key === selectedWdvTemplateKey) ?? null, [selectedWdvTemplateKey, wdvTemplateRecommendations]);
  const handleLayoutRecommendationChange = (templateKey: string) => {
      setSelectedWdvTemplateKey(templateKey);
      setWdvTemplateModalOpen(Boolean(templateKey));
  };
  const refreshWdvTemplateRecommendations = () => {
      setRecommendationRefreshRevision((revision) => revision + 1);
  };
  const handleWdvTemplateApplied = (session: WdvCanonicalTemplateApplySession) => {
      applyCanonicalSession(session as RawCanonicalSession);
      setWdvTemplateModalOpen(false);
  };
  const curveUsageCounts = useMemo(
      () => canonicalizeCurveUsageCounts(curveIdentityIndex, wdvPackageState.curveUsageCounts),
      [curveIdentityIndex, wdvPackageState.curveUsageCounts],
  );
  const selectedTrackCurveIds = useMemo(() => {
      if (!selectedTrack || selectedTrack.trackType !== 'curve')
          return new Set<string>();
      const selected = new Set(
          selectedTrack.curves
              .map((assignment) => resolveAssignmentCanonicalCurveKey(curveIdentityIndex, assignment))
              .filter((identity): identity is string => Boolean(identity)),
      );
      for (const curve of activeCurveCatalog) {
          const canonicalId = curve.curveUid ?? curve.curveId;
          if (!canonicalId) continue;
          const pendingKey = `${selectedTrack.trackId}:${curve.curveUid ?? canonicalId}`;
          const optimistic = curveSelectionOptimisticByKey[pendingKey];
          if (optimistic === true) selected.add(canonicalId);
          if (optimistic === false) selected.delete(canonicalId);
      }
      return selected;
  }, [activeCurveCatalog, curveIdentityIndex, curveSelectionOptimisticByKey, selectedTrack]);
  // WLV-WDV-REBUILD-1B-EMPTY-STATE-CLEANUP:
  // Selected inventory reflects curves assigned to visible tracks only.
  // WMDP-loaded availability remains separate under Loaded Curves.
  const visibleTrackCurveIds = useMemo(() => {
      const ids = new Set<string>();
      tracks.forEach((track) => {
          if (track.trackType !== 'curve')
              return;
          track.curves.forEach((assignment) => {
              const canonical = resolveAssignmentCanonicalCurveKey(curveIdentityIndex, assignment);
              if (canonical) ids.add(canonical);
          });
      });
      return ids;
  }, [curveIdentityIndex, tracks]);
  const pendingAddTrackCanonicalIds = useMemo(
      () => canonicalizeCurveIdentitySet(curveIdentityIndex, pendingAddTrackCurveIds),
      [curveIdentityIndex, pendingAddTrackCurveIds],
  );
  const updateTrack = (trackId: string, patch: Partial<WellLogTrack>) => {
      setTracks((current) => current.map((track) => (track.trackId === trackId ? { ...track, ...patch } as WellLogTrack : track)));
  };
  const updateCurveAssignment = (
      trackId: string,
      assignmentId: string,
      patch: Partial<CurveAssignment>,
      options: Readonly<{ persist?: boolean }> = {},
  ) => {
      const track = tracks.find((item) => item.trackId === trackId && item.trackType === 'curve');
      const assignment =
          track && track.trackType === 'curve'
              ? track.curves.find((item) => item.assignmentId === assignmentId)
              : undefined;
      const assignmentCommandBody = assignment
          ? canonicalAssignmentUpdateCommandBody(assignment, patch)
          : null;

      if (options.persist === false) {
          setTracks((current) => current.map((item) => {
              if (item.trackId !== trackId || item.trackType !== 'curve')
                  return item;
              return {
                  ...item,
                  curves: item.curves.map((currentAssignment) => (
                      currentAssignment.assignmentId === assignmentId
                          ? { ...currentAssignment, ...patch }
                          : currentAssignment
                  )),
              };
          }));
          return;
      }

      if (assignmentCommandBody !== null) {
          if (
              !managedViewerWellUid
              || canonicalRevisionRef.current < 0
              || !looksLikeUuid(trackId)
              || !looksLikeUuid(assignmentId)
          ) {
              console.error(
                  '[WdvPageBoundary] canonical assignment update blocked because canonical identity or revision is unavailable.',
              );
              return;
          }

          // Keep controlled Edit Track fields responsive while the canonical
          // mutation is queued. The backend-returned canonical session remains
          // authoritative and will reconcile this optimistic assignment.
          setTracks((current) => current.map((item) => {
              if (item.trackId !== trackId || item.trackType !== 'curve')
                  return item;
              return {
                  ...item,
                  curves: item.curves.map((currentAssignment) => (
                      currentAssignment.assignmentId === assignmentId
                          ? { ...currentAssignment, ...patch }
                          : currentAssignment
                  )),
              };
          }));

          void runUpdateAssignment(
              assignmentId,
              assignmentCommandBody,
          ).catch((error) => {
              console.error(
                  '[WdvPageBoundary] updateCurveAssignment canonical command failed:',
                  error,
              );
          });
          return;
      }

      setTracks((current) => current.map((item) => {
          if (item.trackId !== trackId || item.trackType !== 'curve')
              return item;
          return {
              ...item,
              curves: item.curves.map((currentAssignment) => (
                  currentAssignment.assignmentId === assignmentId
                      ? { ...currentAssignment, ...patch }
                      : currentAssignment
              )),
          };
      }));
  };
  const previewCurveLineStyle = (
      trackId: string,
      assignmentId: string,
      value: CurveLineStyleValue,
  ) => {
      setTracks((current) => current.map((item) => {
          if (item.trackId !== trackId || item.trackType !== 'curve') return item;
          return {
              ...item,
              curves: item.curves.map((assignment) => (
                  assignment.assignmentId === assignmentId
                      ? {
                          ...assignment,
                          lineVisible: value.visible,
                          color: value.color,
                          lineWidth: value.width,
                          lineStyle: value.style,
                          lineOpacity: value.opacity,
                      }
                      : assignment
              )),
          };
      }));
  };

  const commitCurveLineStyle = (
      trackId: string,
      assignmentId: string,
      value: CurveLineStyleValue,
  ) => {
      if (
          !managedViewerWellUid
          || canonicalRevisionRef.current < 0
          || !looksLikeUuid(trackId)
          || !looksLikeUuid(assignmentId)
      ) {
          console.error(
              '[WdvPageBoundary] curve line style commit blocked because canonical identity is unavailable.',
          );
          return;
      }

      previewCurveLineStyle(trackId, assignmentId, value);

      void commitAssignmentLineStyle(assignmentId, {
          line_visible: value.visible,
          color: value.color,
          line_width: value.width,
          line_style: value.style,
          line_opacity: value.opacity,
      }).catch((error) => {
          console.error('[WdvPageBoundary] curve line style commit failed:', error);
      });
  };

  const configureIntervalTrack = useCallback(async (
    trackId: string,
    config: {
      trackName: string;
      rendererType: string;
      trackRole: string;
      widthPx: number;
    },
  ) => {
    if (!managedViewerWellUid || canonicalRevisionRef.current < 0) return;
    try {
      await runConfigureTrack(trackId, config);
    } catch (error) {
      console.error('[WdvPageBoundary] configureIntervalTrack failed:', error);
    }
  }, [
    managedViewerWellUid,
    runConfigureTrack,
  ]);

  const addTrack = (draft: AddTrackDraft) => {
      if (!managedViewerWellUid || canonicalRevisionRef.current < 0) return;
      const selected = orderedTracks.find((track) => track.trackId === selection.trackId) ?? null;
      const initialCurveUids = draft.trackType === 'curve' && draft.curveSource === 'selected'
          ? pendingAddTrackCurveIds
              .map((curveId) => activeCurveCatalog.find((curve) => curve.curveId === curveId || curve.curveUid === curveId)?.curveUid)
              .filter((curveUid): curveUid is string => Boolean(curveUid && looksLikeUuid(curveUid)))
          : [];
      const compositionPlan = planAddBlankTrack({
          trackType: draft.trackType,
          depthBasis: draft.depthBasis,
          latticeMode: draft.latticeMode,
          scaleMode: draft.scaleMode,
          insertMode: draft.insertMode,
          referenceTrackId: draft.referenceTrackId && looksLikeUuid(draft.referenceTrackId) ? draft.referenceTrackId : null,
          selectedTrackId: selected?.trackId && looksLikeUuid(selected.trackId) ? selected.trackId : null,
          initialManagedCurveUids: initialCurveUids,
      });
      if (!compositionPlan.ok) {
          setWdvWorkspaceError(
              `Add Track aborted: the active track could not be resolved for ${
                  draft.insertMode === 'before_selected' ? 'Before active track' : 'After active track'
              }. No track was added.`,
          );
          return;
      }

      void (async () => {
          try {
              await runConfigureBlankTrack(compositionPlan.command);
              setPendingAddTrackCurveIds([]);
              setAddTrackCurveSelectionMode(false);
          } catch (error) {
              if (error instanceof Error && error.message.startsWith('409 ')) await refreshCanonicalSession();
              else console.error('[WdvPageBoundary] addTrack failed:', error);
          }
      })();
  };
  const deleteSelectedTrack = () => {
      if (!selectedTrack || canonicalRevisionRef.current < 0 || !looksLikeUuid(selectedTrack.trackId)) return;

      const removedTrackId = selectedTrack.trackId;
      const ownerWellUid = selectedTrack.managedWellUid;

      if (!ownerWellUid || !looksLikeUuid(ownerWellUid)) {
          setWdvWorkspaceError(
              `Delete failed: selected track ${removedTrackId} has no canonical managed-well owner.`,
          );
          return;
      }

      const cleanupPlan = planTrackRelationshipCleanup({
          removedTrackId,
          combinationActiveTrackIds,
          combinationLockedTrackIds,
          multiHighlightedTrackIds,
          trackDepthRangesById,
          viewportTieGroups,
          viewportTieSuspendedTrackIds,
          viewportTieHistoryByGroupId,
      });

      void (async () => {
          /*
           * WDV_TRACK_DELETE_OWNER_AUTHORITY_V1_0_1
           *
           * Unified WDV tracks are well-owned. Route RemoveTrack through the
           * selected track's own managedWellUid rather than the viewer's current
           * managedViewerWellUid. Use the backend command contract directly:
           * expected_revision + track_uid, with no optional command_id envelope.
           */
          const executeDeleteAtCurrentRevision = async (): Promise<RawCanonicalSession> =>
              fetchWlvJson<RawCanonicalSession>(
                  `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(ownerWellUid)}/tracks/remove`,
                  {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                          expected_revision: canonicalRevisionRef.current,
                          track_uid: removedTrackId,
                      }),
                  },
              );

          try {
              let session: RawCanonicalSession;
              try {
                  session = await executeDeleteAtCurrentRevision();
              } catch (error) {
                  if (!(error instanceof Error) || !error.message.startsWith('409 ')) {
                      throw error;
                  }
                  await refreshCanonicalSession({ preserveInteraction: true });
                  session = await executeDeleteAtCurrentRevision();
              }

              applyCanonicalSession(session, { preserveInteraction: true });

              setCombinationActiveTrackIds(cleanupPlan.combinationActiveTrackIds);
              setCombinationLockedTrackIds(cleanupPlan.combinationLockedTrackIds);
              setMultiHighlightedTrackIds(cleanupPlan.multiHighlightedTrackIds);
              setTrackDepthRangesById(cleanupPlan.trackDepthRangesById);
              setViewportTieGroups(cleanupPlan.viewportTieGroups);
              setViewportTieSuspendedTrackIds(cleanupPlan.viewportTieSuspendedTrackIds);
              setViewportTieHistoryByGroupId(cleanupPlan.viewportTieHistoryByGroupId);
              setWdvWorkspaceError(null);
          } catch (error) {
              const message =
                  error instanceof Error
                      ? error.message
                      : 'Unable to delete the selected WDV track.';
              setWdvWorkspaceError(message);
              console.error('[WdvPageBoundary] deleteSelectedTrack failed:', {
                  error,
                  removedTrackId,
                  ownerWellUid,
                  viewerManagedWellUid: managedViewerWellUid,
                  canonicalRevision: canonicalRevisionRef.current,
              });
          }
      })();
  };
  const clearCanvas = () => {
      if (!managedViewerWellUid) return;
      void (async () => {
          try {
              await runClearCanonicalCanvas();
              setOpenCurveMenu(null);
              setPendingAddTrackCurveIds([]);
              setAddTrackCurveSelectionMode(false);
          } catch (error) {
              const message = error instanceof Error ? error.message : 'Unable to clear the WDV canvas.';
              setWdvWorkspaceError(message);
              console.error('[WdvPageBoundary] clearCanvas failed:', error);
          }
      })();
  };
  const moveSelectedTrack = (direction: -1 | 1) => {
      const trackId = selection.trackId;
      if (!trackId) return;
      const plan = planTrackReorder(tracksRef.current, trackId, direction);
      if (!plan) return;
      setTracks(plan.nextTracks);
      setSelection((current) => (
          current.trackId === trackId ? current : { kind: 'track', trackId }
      ));

      if (!managedViewerWellUid || canonicalRevisionRef.current < 0) return;
      void runReorderTracks(plan.orderedTrackIds).catch((error) => {
          console.error('[WdvPageBoundary] canonical track reorder failed:', error);
      });
  };
  const adjustCurveTrackWidth = (trackId: string, delta: number) => {
      let committedWidth: number | null = null;
      setTracks((current) => current.map((track) => {
          if (
              track.trackId !== trackId
              || (
                  track.trackType !== 'curve'
                  && track.trackType !== 'core'
                  && track.trackType !== 'interval'
                  && track.trackType !== 'completion'
              )
          ) {
              return track;
          }
          committedWidth = clampCurveTrackWidth(track.widthPx + delta);
          return { ...track, widthPx: committedWidth };
      }));
      if (committedWidth !== null) {
          window.dispatchEvent(new CustomEvent(
              'wlv:track-width-commit',
              { detail: { trackId, widthPx: committedWidth } },
          ));
      }
  };

  const adjustSelectedCurveTrackWidth = (delta: number) => {
      if (!selectedResizableTrack)
          return;

      adjustCurveTrackWidth(
          selectedResizableTrack.trackId,
          delta,
      );
  };

  const resetCurveTrackWidths = () => {
      const resettable = tracksRef.current.filter(
          (track) => track.trackType === 'curve'
              || track.trackType === 'core'
              || track.trackType === 'interval'
              || track.trackType === 'completion',
      );
      setTracks((current) => current.map((track) => (
          track.trackType === 'curve'
          || track.trackType === 'core'
          || track.trackType === 'interval'
          || track.trackType === 'completion'
              ? { ...track, widthPx: CURVE_TRACK_RESET_WIDTH }
              : track
      )));
      for (const track of resettable) {
          window.dispatchEvent(new CustomEvent(
              'wlv:track-width-commit',
              { detail: { trackId: track.trackId, widthPx: CURVE_TRACK_RESET_WIDTH } },
          ));
      }
  };
  const startCurveTrackResize = (trackId: string, startX: number, startWidth: number) => {
      setOpenCurveMenu(null);
      setDragPanState(null);
      setIntervalZoomActive(false);
      setIntervalSelection(null);
      setTrackResizeState({ trackId, startX, startWidth: clampCurveTrackWidth(startWidth) });
  };
  /*
   * One top-level viewport composition hook now owns semantic derivation,
   * presentation projection, and controller hookup. WdvPageBoundary supplies
   * raw state/setters and consumes the resulting viewer/controller surface.
   */
  const combinationLockActionTrackIds = multiHighlightedTrackIds.length > 0
      ? multiHighlightedTrackIds
      : selectedTrack
          ? [selectedTrack.trackId]
          : [];
  const {
      viewportSemantics,
      viewerPresentationModel,
      toggleCombinationTrack,
      createViewportTie,
      untieSelectedViewportTracks,
      lockSelectedCombinationTracks,
      unlockSelectedCombinationTracks,
      applyCombinationRange,
      zoomDepth,
      beginDragPan,
      updateDragPan,
      endDragPan,
      previousDepthView,
      fitDepth,
      resetDepthView,
      centerGoToDepthTarget,
      goToDepth,
  } = useViewerViewportComposition({
      semanticInput: {
          tracks: tracks.map((track) => ({ trackId: track.trackId, trackIndex: track.trackIndex })),
          selection,
          selectedTrackId: selectedTrack?.trackId ?? null,
          combinationActiveTrackIds,
          combinationLockedTrackIds,
          multiHighlightedTrackIds,
          trackDepthRangesById,
          trackFullDepthRangesById,
          combinationGroupViewRange,
          viewDepthRange,
          viewportTieGroups,
          viewportTieSuspendedTrackIds,
          fullDepthRange: canvasAllTrackDepthRange,
          dragPanActive: Boolean(dragPanState),
          quickView: Boolean(quickViewPackage),
          combinationLockActionTrackIds,
      },
      commandInput: {
          viewDepthRange,
          setViewDepthRange,
          combinationActiveTrackIds,
          setCombinationActiveTrackIds,
          combinationLockedTrackIds,
          setCombinationLockedTrackIds,
          trackDepthRangesById,
          setTrackDepthRangesById,
          setCombinationGroupViewRange,
          setCombinationGroupHistory,
          viewportTieGroups,
          setViewportTieGroups,
          viewportTieSuspendedTrackIds,
          setViewportTieSuspendedTrackIds,
          viewportTieHistoryByGroupId,
          setViewportTieHistoryByGroupId,
          setViewHistory,
          minSpan: MIN_DEPTH_VIEW_SPAN,
          zoomOuterRange: canvasAllTrackDepthRange,
          combinationLockActionTrackIds,
          rangesEqual,
      },
      dragInput: {
          dragPanState,
          setDragPanState,
          combinationLockedTrackIdSet: new Set(combinationLockedTrackIds),
          viewportTieGroups,
          setViewportTieGroups,
          setViewportTieSuspendedTrackIds,
          setViewportTieHistoryByGroupId,
          viewDepthRange,
          setViewDepthRange,
          setViewHistory,
          trackFullDepthRangesById: trackNavigableDepthRangesById,
          canvasAllTrackDepthRange,
          blankSpacePanTrackIds: new Set(
              tracks
                  .filter((track) => track.trackType === 'curve')
                  .map((track) => track.trackId),
          ),
          setTrackDepthRangesById,
          setCombinationGroupViewRange,
          minSpan: MIN_DEPTH_VIEW_SPAN,
      },
      navigationInput: {
          viewDepthRange,
          setViewDepthRange,
          setViewHistory,
          setViewportTieGroups,
          setViewportTieHistoryByGroupId,
          setCombinationGroupHistory,
          setCombinationGroupViewRange,
          trackIds: tracks.map((track) => track.trackId),
          trackFullDepthRangesById,
          canvasAssignedCurveDepthRange,
          setTrackDepthRangesById,
          setIntervalZoomActive,
          setIntervalSelection,
          setDragPanState,
          setGoToDepthMarker,
          goToDepthValue,
          setGoToDepthValue,
          rangesEqual,
          minSpan: MIN_DEPTH_VIEW_SPAN,
          goToReviewWindow: GO_TO_REVIEW_WINDOW_M,
      },
  });
  const {
      activeCombinationTrackIds,
      lockedCombinationTrackIds,
      selectedViewportTieGroup,
      groupActionTrackIds,
      activeGroupViewRange,
      combinationTrackStateById,
  } = viewportSemantics;
  const multiHighlightedTrackIdSet = new Set(multiHighlightedTrackIds);
  const combinationStateForTrack = (trackId: string) => combinationTrackStateById[trackId] ?? 'normal';
  const groupActionTrackIdSet = new Set(groupActionTrackIds);
  const trackCanvasRenderModel = viewerPresentationModel.canvas;
  const trackSelectionPresentationModel = viewerPresentationModel.selection;
  const trackHeaderPresentationById = viewerPresentationModel.headerByTrackId;
  const viewportToolbarPresentation = viewerPresentationModel.toolbar;

  useEffect(() => {
      const liveTrackIds = new Set(tracks.map((track) => track.trackId));
      setViewportTieGroups((groups) => groups.flatMap((group) => {
          const survivingMembers = group.memberTrackIds.filter((trackId) => liveTrackIds.has(trackId));
          if (!liveTrackIds.has(group.leaderTrackId) || survivingMembers.length < 2) {
              if (survivingMembers.length > 0) {
                  setTrackDepthRangesById((current) => {
                      const next = { ...current };
                      for (const trackId of survivingMembers) next[trackId] = { ...group.viewport };
                      return next;
                  });
              }
              return [];
          }
          if (survivingMembers.length === group.memberTrackIds.length) return [group];
          return [{ ...group, memberTrackIds: survivingMembers }];
      }));
      setViewportTieSuspendedTrackIds((ids) => ids.filter((trackId) => liveTrackIds.has(trackId)));
  }, [tracks]);

  type SavedWdvViewState = {
      depth_unit: 'm' | 'ft';
      global_viewport: DepthViewRange;
      group_viewport: DepthViewRange | null;
      active_track_uids: string[];
      highlighted_track_uids: string[];
      locked_track_uids: string[];
      locked_viewports_by_track_uid: Record<string, DepthViewRange>;
      track_viewports_by_track_uid?: Record<string, DepthViewRange>;
      viewport_tie_groups?: Array<{
          group_id: string;
          leader_track_uid: string;
          member_track_uids: string[];
          viewport: DepthViewRange;
      }>;
      viewport_tie_suspended_track_uids?: string[];
      presentation_state?: {
          selected_formation_top_ids?: string[];
          selected_lithology_interval_ids?: string[];
          formation_top_overlay_styles_by_track_id?: Record<string, FormationTopOverlayStyle>;
          selected_core_image_ids?: string[];
          track_backdrop_mode?: TrackBackdropMode;
          track_headers_collapsed?: boolean;
          go_to_depth_marker?: number | null;
          display_go_to_selection_line?: boolean;
          track_order_uids?: string[];
          track_widths_by_uid?: Record<string, number>;
          interval_storage_state?: Record<string, string>;
          viewport_tie_groups?: Array<{
              group_id: string;
              leader_track_uid: string;
              member_track_uids: string[];
              viewport: DepthViewRange;
          }>;
          viewport_tie_suspended_track_uids?: string[];
      };
  };



  type SavedCanvasRestoreResponse = {
      saved_canvas_uid: string;
      workspace_id: string;
      name: string;
      restored_at: string;
      session: RawCanonicalSession;
      view_revision: number;
      view_state: SavedWdvViewState;
  };

  const [savedCanvases, setSavedCanvases] = useState<SavedCanvasToolbarItem[]>([]);
  const [savedCanvasSaving, setSavedCanvasSaving] = useState(false);
  const [savedCanvasBusyUid, setSavedCanvasBusyUid] = useState<string | null>(null);
  const [savedCanvasError, setSavedCanvasError] = useState<string | null>(null);

  const buildSavedViewState = (): SavedWdvViewState => {
      const lockedViewports: Record<string, DepthViewRange> = {};
      for (const trackId of lockedCombinationTrackIds) {
          lockedViewports[trackId] =
              trackDepthRangesById[trackId] ?? viewDepthRange;
      }
      return {
          depth_unit: wdvWorkspace?.common_depth_unit ?? 'm',
          global_viewport: { ...viewDepthRange },
          group_viewport: !selectedViewportTieGroup && activeGroupViewRange
              ? { ...activeGroupViewRange }
              : combinationGroupViewRange
                  ? { ...combinationGroupViewRange }
                  : null,
          active_track_uids: [...activeCombinationTrackIds],
          highlighted_track_uids: tracks
              .filter((track) => multiHighlightedTrackIdSet.has(track.trackId))
              .map((track) => track.trackId),
          locked_track_uids: [...lockedCombinationTrackIds],
          locked_viewports_by_track_uid: lockedViewports,
          track_viewports_by_track_uid: buildPersistedTrackViewports(
              tracks.map((track) => track.trackId),
              trackDepthRangesById,
          ),
          viewport_tie_groups: buildPersistedViewportTieGroups(viewportTieGroups),
          viewport_tie_suspended_track_uids: [...viewportTieSuspendedTrackIds],
          presentation_state: {
              selected_formation_top_ids: Array.from(selectedFormationTopIds),
              selected_lithology_interval_ids: Array.from(selectedLithologyIntervalIds),
              formation_top_overlay_styles_by_track_id: formationTopOverlayStylesByTrackId,
              selected_core_image_ids: Array.from(selectedCoreImageIds),
              track_backdrop_mode: trackBackdropMode,
              track_headers_collapsed: trackHeadersCollapsed,
              go_to_depth_marker: goToDepthMarker,
              display_go_to_selection_line: displayGoToSelectionLine,
              track_order_uids: sortTracks(tracks).map((track) => track.trackId),
              track_widths_by_uid: Object.fromEntries(
                  tracks.map((track) => [track.trackId, track.widthPx]),
              ),
              interval_storage_state: readDurableIntervalStorageState(),
          },
      };
  };


  const {
      commitCurrentViewState,
      loadStartupView,
      saveCommittedRecoverySnapshots,
  } = useViewPersistenceLifecycleController<SavedWdvViewState, RawCanonicalSession>({
      managedWellUid: managedViewerWellUid,
      canonicalRevisionRef,
      fetchJson: fetchWlvJson,
  });


  /*
   * Slice 7 durable viewport commit boundary.
   *
   * High-frequency interaction remains local. During drag-pan, the viewport
   * setters continue updating React/canvas state directly. Once the gesture is
   * no longer active (or a discrete zoom/range/lock/tie operation settles),
   * this effect queues one backend commit. The backend independently guards
   * both canonical session revision and monotonic view revision.
   */
  useEffect(() => {
      if (!shouldScheduleCommittedViewportCommit({
          managedWellUid: managedViewerWellUid,
          canonicalRevision: canonicalRevisionRef.current,
          hasCanonicalSession: Boolean(canonicalSession),
          recoveryHydrated: canvasRecoveryHydratedRef.current,
          recoveryAutosaveArmed,
          startupSemanticHydrationReady,
          dragPanActive: dragPanState !== null,
      })) {
          return;
      }

      if (committedViewportCommitTimerRef.current !== null) {
          window.clearTimeout(committedViewportCommitTimerRef.current);
      }

      committedViewportCommitTimerRef.current = window.setTimeout(() => {
          committedViewportCommitTimerRef.current = null;
          const viewState = buildSavedViewState();
          void commitCurrentViewState(viewState).catch((error) => {
              // A 409 means a newer canonical/view commit won. Never force
              // local convergence from this write path. The next settled
              // interaction re-reads backend view revision.
              if (!isCurveFillRevisionConflict(error)) {
                  console.error(
                      '[WdvPageBoundary] committed viewport write failed:',
                      error,
                  );
              }
          });
      }, 180);

      return () => {
          if (committedViewportCommitTimerRef.current !== null) {
              window.clearTimeout(committedViewportCommitTimerRef.current);
              committedViewportCommitTimerRef.current = null;
          }
      };
  }, [
      managedViewerWellUid,
      canonicalSession?.revision,
      recoveryAutosaveArmed,
      startupSemanticHydrationReady,
      dragPanState,
      viewDepthRange,
      combinationGroupViewRange,
      activeCombinationTrackIds,
      multiHighlightedTrackIds,
      lockedCombinationTrackIds,
      trackDepthRangesById,
      viewportTieGroups,
      viewportTieSuspendedTrackIds,
      tracks,
  ]);

  const waitForSavedCanvasTrackComposition = async (
      viewState: SavedWdvViewState,
  ): Promise<void> => {
      const requiredTrackIds = new Set<string>();

      /*
       * Large Saved Canvases hydrate in several React passes. Tie restoration
       * must wait for the complete persisted canvas composition, not for an
       * arbitrary number of animation frames.
       */
      for (const trackId of viewState.presentation_state?.track_order_uids ?? []) {
          requiredTrackIds.add(trackId);
      }
      for (const trackId of Object.keys(viewState.track_viewports_by_track_uid ?? {})) {
          requiredTrackIds.add(trackId);
      }
      for (const group of viewState.viewport_tie_groups ?? []) {
          requiredTrackIds.add(group.leader_track_uid);
          for (const trackId of group.member_track_uids) requiredTrackIds.add(trackId);
      }
      if (requiredTrackIds.size === 0) return;

      const deadline = Date.now() + 5000;
      while (Date.now() < deadline) {
          const liveTrackIds = new Set(
              tracksRef.current.map((track) => track.trackId),
          );
          if (
              Array.from(requiredTrackIds).every((trackId) =>
                  liveTrackIds.has(trackId))
          ) {
              return;
          }
          await new Promise<void>((resolve) => {
              window.setTimeout(resolve, 25);
          });
      }

      const liveTrackIds = new Set(
          tracksRef.current.map((track) => track.trackId),
      );
      const missingTrackIds = Array.from(requiredTrackIds).filter(
          (trackId) => !liveTrackIds.has(trackId),
      );
      throw new Error(
          `Saved Canvas track composition did not stabilize before Tie restore; missing: ${missingTrackIds.join(', ')}`,
      );
  };

  const applySavedViewState = async (viewState: SavedWdvViewState): Promise<void> => {
      const currentUnit = wdvWorkspace?.common_depth_unit ?? 'm';
      if (viewState.depth_unit !== currentUnit) {
          await changeCommonDepthUnit(viewState.depth_unit);
      }

      setViewDepthRange({ ...viewState.global_viewport });
      setViewHistory([]);
      setCombinationActiveTrackIds([...viewState.active_track_uids]);
      setMultiHighlightedTrackIds([...viewState.highlighted_track_uids]);
      setCombinationLockedTrackIds([...viewState.locked_track_uids]);
      setCombinationGroupViewRange(
          viewState.group_viewport
              ? { ...viewState.group_viewport }
              : null,
      );
      setCombinationGroupHistory([]);

      const restoredTrackViewports = restorePersistedTrackViewports(
          viewState,
          viewState.locked_track_uids,
          viewState.locked_viewports_by_track_uid,
      );
      setTrackDepthRangesById(restoredTrackViewports);

      const persistedTrackIds = new Set<string>(
          tracksRef.current.map((track) => track.trackId),
      );
      for (const trackId of viewState.presentation_state?.track_order_uids ?? []) {
          persistedTrackIds.add(trackId);
      }
      for (const trackId of Object.keys(viewState.track_viewports_by_track_uid ?? {})) {
          persistedTrackIds.add(trackId);
      }
      for (const group of viewState.viewport_tie_groups ?? []) {
          persistedTrackIds.add(group.leader_track_uid);
          for (const trackId of group.member_track_uids) persistedTrackIds.add(trackId);
      }

      const restoredTieGroups = restorePersistedViewportTieGroups(
          viewState,
          Array.from(persistedTrackIds),
      );
      setViewportTieGroups(restoredTieGroups);
      setViewportTieSuspendedTrackIds(
          restorePersistedViewportTieSuspensions(viewState, restoredTieGroups),
      );
      setViewportTieHistoryByGroupId(
          Object.fromEntries(restoredTieGroups.map((group) => [group.groupId, []])),
      );

      const presentation = viewState.presentation_state;
      if (presentation) {
          if (
              Array.isArray(presentation.track_order_uids)
              || presentation.track_widths_by_uid
          ) {
              setTracks((current) => {
                  const currentById = new Map(current.map((track) => [track.trackId, track]));
                  const orderedIds = Array.isArray(presentation.track_order_uids)
                      ? presentation.track_order_uids.filter((trackId) => currentById.has(trackId))
                      : sortTracks(current).map((track) => track.trackId);
                  const seen = new Set(orderedIds);
                  const missing = sortTracks(current)
                      .map((track) => track.trackId)
                      .filter((trackId) => !seen.has(trackId));
                  return [...orderedIds, ...missing].map((trackId, index) => {
                      const track = currentById.get(trackId)!;
                      const savedWidth = presentation.track_widths_by_uid?.[trackId];
                      return {
                          ...track,
                          trackIndex: index,
                          widthPx: typeof savedWidth === 'number' && Number.isFinite(savedWidth)
                              ? clampCurveTrackWidth(savedWidth)
                              : track.widthPx,
                      };
                  });
              });
          }
          applyDurableIntervalStorageState(presentation.interval_storage_state);
          if (Array.isArray(presentation.selected_formation_top_ids)) {
              setSelectedFormationTopIds(
                  new Set(presentation.selected_formation_top_ids),
              );
          }
          if (Array.isArray(presentation.selected_lithology_interval_ids)) {
              setSelectedLithologyIntervalIds(
                  new Set(presentation.selected_lithology_interval_ids),
              );
          }
          if (presentation.formation_top_overlay_styles_by_track_id) {
              setFormationTopOverlayStylesByTrackId(
                  presentation.formation_top_overlay_styles_by_track_id,
              );
              writePersistedCurveOverlayTrackStyles(
                  presentation.formation_top_overlay_styles_by_track_id,
              );
          }
          if (Array.isArray(presentation.selected_core_image_ids)) {
              setSelectedCoreImageIds(
                  new Set(presentation.selected_core_image_ids),
              );
          }
          if (presentation.track_backdrop_mode) {
              setTrackBackdropMode(presentation.track_backdrop_mode);
          }
          if (typeof presentation.track_headers_collapsed === 'boolean') {
              setTrackHeadersCollapsed(presentation.track_headers_collapsed);
          }
          setGoToDepthMarker(
              typeof presentation.go_to_depth_marker === 'number'
                  ? presentation.go_to_depth_marker
                  : null,
          );
          if (typeof presentation.display_go_to_selection_line === 'boolean') {
              setDisplayGoToSelectionLine(
                  presentation.display_go_to_selection_line,
              );
          }
      } else {
          setGoToDepthMarker(null);
      }

      setIntervalZoomActive(false);
      setIntervalSelection(null);
      setDragPanState(null);
  };

  const refreshSavedCanvases = useCallback(async (): Promise<void> => {
      if (!wdvWorkspace?.workspace_id) {
          setSavedCanvases([]);
          return;
      }
      try {
          const items = await fetchWlvJson<SavedCanvasToolbarItem[]>(
              `/api/wlv/inventory/wdv-workspace/${encodeURIComponent(wdvWorkspace.workspace_id)}/saved-canvases`,
          );
          setSavedCanvases(items);
          setSavedCanvasError(null);
      } catch (error) {
          setSavedCanvasError(error instanceof Error ? error.message : 'Unable to list Saved Canvases');
      }
  }, [wdvWorkspace?.workspace_id]);

  useEffect(() => {
      if (activeView !== 'log-viewer' || quickViewPackage || !wdvWorkspace?.workspace_id) return;
      void refreshSavedCanvases();
  }, [activeView, quickViewPackage, refreshSavedCanvases, wdvWorkspace?.workspace_id]);

  const saveCurrentCanvas = async (name: string): Promise<void> => {
      if (!wdvWorkspace || canonicalRevisionRef.current < 0 || quickViewPackage) return;
      if (curveFillPending) {
          setSavedCanvasError('Canvas infill is still committing. Save Canvas is temporarily unavailable.');
          return;
      }

      // Snapshot the user-visible Tie/Lock/view state before any awaited refresh.
      const savedViewStateSnapshot = buildSavedViewState();

      setSavedCanvasSaving(true);
      setSavedCanvasError(null);
      try {
          await runSerializedCanonicalTask(async () => {
              // Save Canvas must sit behind every earlier canonical mutation in
              // the same lane. This prevents a visible Curve Fill from being
              // saved before its canonical rule has actually committed.
              const currentWorkspace = await refreshWdvWorkspace();
              if (!currentWorkspace) {
                  throw new Error('Unable to refresh WDV workspace before Save Canvas');
              }
              await refreshCanonicalSession({ preserveInteraction: true });
              await fetchWlvJson<unknown>(
                  `/api/wlv/inventory/wdv-workspace/${encodeURIComponent(currentWorkspace.workspace_id)}/saved-canvases`,
                  {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                          name,
                          view_state: savedViewStateSnapshot,
                      }),
                  },
              );
          });
          await refreshSavedCanvases();
      } catch (error) {
          setSavedCanvasError(error instanceof Error ? error.message : 'Unable to save canvas');
      } finally {
          setSavedCanvasSaving(false);
      }
  };

  const saveActiveCanvas = async (savedCanvasUid: string): Promise<void> => {
      if (!wdvWorkspace || canonicalRevisionRef.current < 0 || quickViewPackage) return;
      if (curveFillPending) {
          setSavedCanvasError('Canvas infill is still committing. Save Changes is temporarily unavailable.');
          return;
      }

      // Snapshot the user-visible Tie/Lock/view state before any awaited refresh.
      const savedViewStateSnapshot = buildSavedViewState();

      setSavedCanvasSaving(true);
      setSavedCanvasError(null);
      try {
          await runSerializedCanonicalTask(async () => {
              const currentWorkspace = await refreshWdvWorkspace();
              if (!currentWorkspace) throw new Error('Unable to refresh WDV workspace before Save Changes');
              await refreshCanonicalSession({ preserveInteraction: true });
              await fetchWlvJson<unknown>(
                  `/api/wlv/inventory/wdv-workspace/${encodeURIComponent(currentWorkspace.workspace_id)}/saved-canvases/${encodeURIComponent(savedCanvasUid)}`,
                  {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ view_state: savedViewStateSnapshot }),
                  },
              );
          });
          await refreshSavedCanvases();
      } catch (error) {
          setSavedCanvasError(error instanceof Error ? error.message : 'Unable to save changes to active canvas');
      } finally {
          setSavedCanvasSaving(false);
      }
  };

  const loadSavedCanvas = async (savedCanvasUid: string): Promise<void> => {
      if (!wdvWorkspace || !canonicalSession || quickViewPackage || savedCanvasBusyUid) return;
      setSavedCanvasBusyUid(savedCanvasUid);
      setSavedCanvasError(null);

      // Saved Canvas restore is an explicit workspace transaction. Disarm the
      // ordinary settled-view/recovery lane before the request, not after it.
      // Also cancel any already-scheduled viewport commit synchronously so a
      // stale commit cannot advance canonical revision while restore is in flight.
      if (committedViewportCommitTimerRef.current !== null) {
          window.clearTimeout(committedViewportCommitTimerRef.current);
          committedViewportCommitTimerRef.current = null;
      }
      setRecoveryAutosaveArmed(false);
      setRecoveryHydratedWellUid(null);

      try {
          await runSerializedCanonicalTask(async () => {
              // Saved Canvas restore is backend-authoritative. Once this
              // serialized lane is acquired, do not make a historical restore
              // depend on frontend-held workspace/session revisions.
              const currentWorkspace = await refreshWdvWorkspace();
              if (!currentWorkspace) {
                  throw new Error('Unable to refresh WDV workspace before Saved Canvas restore');
              }

              const response = await fetchWlvJson<SavedCanvasRestoreResponse>(
                  `/api/wlv/inventory/wdv-workspace/${encodeURIComponent(currentWorkspace.workspace_id)}/saved-canvases/${encodeURIComponent(savedCanvasUid)}/restore`,
                  {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({}),
                  },
              );

              // Saved Canvas restores canonical Curve Fill rules as part of the
              // historical session. Curve Fill geometry is derived client state.
              // Invalidate stale geometry and hydration suppression before applying
              // the restored session so restored rules rehydrate by owner well.
              setCurveFillGeometryByRuleUid(new Map());
              curveFillHydrationKeyRef.current = null;
              backgroundCurveFillHydrationKeysRef.current.clear();
              completedCurveFillHydrationKeysRef.current.clear();

              applyCanonicalSession(response.session);
              await waitForSavedCanvasTrackComposition(response.view_state);
              await applySavedViewState(response.view_state);
              setStartupHydrationRetryTick((current) => current + 1);
              canvasRecoveryHydratedRef.current = true;
              const authorityWellUid = recoveryAuthorityWellUid(managedViewerWellUid);
              if (authorityWellUid) {
                  window.requestAnimationFrame(() => {
                      setRecoveryHydratedWellUid(authorityWellUid);
                  });
              }
          });
          await refreshSavedCanvases();
      } catch (error) {
          // Restore failed before mutation or the backend rejected the expected
          // revision. Re-arm ordinary recovery for the unchanged live canvas.
          canvasRecoveryHydratedRef.current = true;
          const authorityWellUid = recoveryAuthorityWellUid(managedViewerWellUid);
          if (authorityWellUid) {
              window.requestAnimationFrame(() => {
                  setRecoveryHydratedWellUid(authorityWellUid);
              });
          }
          setSavedCanvasError(error instanceof Error ? error.message : 'Unable to load Saved Canvas');
      } finally {
          setSavedCanvasBusyUid(null);
      }
  };

  const deleteSavedCanvas = async (savedCanvasUid: string): Promise<void> => {
      if (!wdvWorkspace || quickViewPackage || savedCanvasBusyUid) return;
      setSavedCanvasBusyUid(savedCanvasUid);
      setSavedCanvasError(null);
      try {
          await fetchWlvJson<unknown>(
              `/api/wlv/inventory/wdv-workspace/${encodeURIComponent(wdvWorkspace.workspace_id)}/saved-canvases/${encodeURIComponent(savedCanvasUid)}`,
              { method: 'DELETE' },
          );
          setSavedCanvases((current) => current.filter((item) => item.saved_canvas_uid !== savedCanvasUid));
      } catch (error) {
          setSavedCanvasError(error instanceof Error ? error.message : 'Unable to delete Saved Canvas');
      } finally {
          setSavedCanvasBusyUid(null);
      }
  };

  useEffect(() => {
      /*
       * Active-well changes are selection/context changes only.
       * Never de-hydrate the unified canvas because a different track owner
       * became active.
       */
      if (!canvasRecoveryHydratedRef.current) {
          setRecoveryAutosaveArmed(false);
          setRecoveryHydratedWellUid(null);
      }
  }, [managedViewerWellUid]);

  useEffect(() => {
      const handleIntervalStorageCommitted = () => setIntervalStorageCommitRevision((current) => current + 1);
      window.addEventListener('wlv:interval-storage-committed', handleIntervalStorageCommitted);
      return () => window.removeEventListener('wlv:interval-storage-committed', handleIntervalStorageCommitted);
  }, []);

  useEffect(() => {
      if (!shouldAttemptUnifiedRecoveryHydration({
          managedViewerWellUid,
          canonicalRevision: canonicalRevisionRef.current,
          hasCanonicalSession: Boolean(canonicalSession),
          canvasRecoveryHydrated: canvasRecoveryHydratedRef.current,
      })) {
          return;
      }

      const restoreKey = UNIFIED_WDV_RECOVERY_RESTORE_KEY;
      if (restoredSavedWorkspaceKeysRef.current.has(restoreKey)) return;
      restoredSavedWorkspaceKeysRef.current.add(restoreKey);

      const recoveryAuthorityUid = recoveryAuthorityWellUid(managedViewerWellUid);
      if (!recoveryAuthorityUid) return;
      const expectedSessionRevision = canonicalRevisionRef.current;

      void (async () => {
          try {
              const startupView = await loadStartupView(
                  recoveryAuthorityUid,
                  expectedSessionRevision,
              );
              if (startupView.status === 'aborted') {
                  restoredSavedWorkspaceKeysRef.current.delete(restoreKey);
                  return;
              }
              if (startupView.status === 'committed' || startupView.status === 'recovery') {
                  await applySavedViewState(startupView.viewState);
              }

              canvasRecoveryHydratedRef.current = true;
              setRecoveryHydratedWellUid(recoveryAuthorityUid);
              setRecoveryAutosaveArmed(false);
          } catch {
              restoredSavedWorkspaceKeysRef.current.delete(restoreKey);
              canvasRecoveryHydratedRef.current = false;
              setRecoveryAutosaveArmed(false);
          }
      })();
  }, [managedViewerWellUid, canonicalSession?.revision]);

  useEffect(() => {
      if (!shouldArmRecoveryAutosave({
          managedViewerWellUid,
          canvasRecoveryHydrated: canvasRecoveryHydratedRef.current,
          recoveryHydratedWellUid,
          startupSemanticHydrationReady,
      })) {
          setRecoveryAutosaveArmed(false);
          return;
      }

      let cancelled = false;
      const frameOne = window.requestAnimationFrame(() => {
          const frameTwo = window.requestAnimationFrame(() => {
              if (!cancelled) setRecoveryAutosaveArmed(true);
          });
          if (cancelled) window.cancelAnimationFrame(frameTwo);
      });

      return () => {
          cancelled = true;
          window.cancelAnimationFrame(frameOne);
      };
  }, [
      managedViewerWellUid,
      recoveryHydratedWellUid,
      startupSemanticHydrationReady,
  ]);

  /*
   * Self-healing startup watchdog.
   *
   * If any represented owner inventory or Curve Fill geometry failed to hydrate,
   * retry the same authoritative owner-based hydration path. Autosave remains
   * blocked during retries, so an incomplete canvas cannot overwrite a good
   * recovery snapshot.
   */
  useEffect(() => {
      if (!shouldRetryStartupHydration({
          managedViewerWellUid,
          canvasRecoveryHydrated: canvasRecoveryHydratedRef.current,
          recoveryHydratedWellUid,
          startupSemanticHydrationReady,
      })) {
          return;
      }

      const retryTimer = window.setTimeout(() => {
          setStartupHydrationRetryTick((current) => current + 1);
      }, WDV_STARTUP_HYDRATION_RETRY_DELAY_MS);

      return () => window.clearTimeout(retryTimer);
  }, [
      managedViewerWellUid,
      recoveryHydratedWellUid,
      startupHydrationRetryTick,
      startupSemanticHydrationReady,
  ]);

  useEffect(() => {
      if (!shouldScheduleRecoveryAutosave({
          managedViewerWellUid,
          recoveryAutosaveArmed,
          canvasRecoveryHydrated: canvasRecoveryHydratedRef.current,
          recoveryHydratedWellUid,
          startupSemanticHydrationReady,
          canonicalRevision: canonicalRevisionRef.current,
          hasCanonicalSession: Boolean(canonicalSession),
      })) {
          return;
      }

      if (recoverySaveTimerRef.current !== null) {
          window.clearTimeout(recoverySaveTimerRef.current);
      }
      recoverySaveTimerRef.current = window.setTimeout(() => {
          recoverySaveTimerRef.current = null;

          void (async () => {
              const recoveryWellUids = recoveryTargetWellUids(
                  wdvWorkspace?.loaded_wells ?? [],
                  managedViewerWellUid,
              );

              /*
               * Recovery is now a backend copy of the exact committed view
               * revision. It cannot author a separate frontend view payload.
               */
              const results = await saveCommittedRecoverySnapshots(
                  recoveryWellUids,
                  buildSavedViewState(),
              );
              if (!results) return;
              results.forEach((result, index) => {
                  if (result.status === 'fulfilled') return;
                  const error = result.reason;
                  if (!isCurveFillRevisionConflict(error)) {
                      console.error(
                          '[WdvPageBoundary] durable recovery save failed:',
                          recoveryWellUids[index],
                          error,
                      );
                  }
              });
          })().catch((error) => {
              if (!isCurveFillRevisionConflict(error)) {
                  console.error('[WdvPageBoundary] durable recovery commit failed:', error);
              }
          });
      }, WDV_RECOVERY_AUTOSAVE_DELAY_MS);

      return () => {
          if (recoverySaveTimerRef.current !== null) {
              window.clearTimeout(recoverySaveTimerRef.current);
              recoverySaveTimerRef.current = null;
          }
      };
  }, [
      managedViewerWellUid,
      recoveryHydratedWellUid,
      recoveryAutosaveArmed,
      startupSemanticHydrationReady,
      canonicalSession?.revision,
      viewDepthRange,
      activeGroupViewRange,
      combinationGroupViewRange,
      activeCombinationTrackIds,
      multiHighlightedTrackIds,
      lockedCombinationTrackIds,
      trackDepthRangesById,
      viewportTieGroups,
      viewportTieSuspendedTrackIds,
      selectedFormationTopIds,
      selectedLithologyIntervalIds,
      formationTopOverlayStylesByTrackId,
      selectedCoreImageIds,
      trackBackdropMode,
      trackHeadersCollapsed,
      goToDepthMarker,
      displayGoToSelectionLine,
      tracks,
      intervalStorageCommitRevision,
      wdvWorkspace?.loaded_wells,
  ]);

  const zoomToCoreThreshold = () => {
      if (selectedTrack?.trackType !== 'core') return;

      const selectedItems = coreImageItems.filter(
          (item) => selectedCoreImageIds.has(item.productId),
      );

      const candidates =
          selectedItems.length > 0
              ? selectedItems
              : coreImageItems;

      if (candidates.length === 0) return;

      const selectedCoreRange =
          selectedTrack && groupActionTrackIdSet.has(selectedTrack.trackId)
              ? (activeGroupViewRange ?? viewDepthRange)
              : selectedTrack && combinationStateForTrack(selectedTrack.trackId) === 'locked'
                  ? (trackDepthRangesById[selectedTrack.trackId] ?? viewDepthRange)
                  : viewDepthRange;

      const currentCenter =
          (selectedCoreRange.min + selectedCoreRange.max) / 2;

      /*
       * Navigation priority:
       *
       * 1. explicit focus MD from Go to MD or Pick on Track;
       * 2. otherwise the center of the current WDV viewport.
       */
      const focusDepth =
          goToDepthMarker ?? currentCenter;

      const distanceToItem = (item: CoreImageInventoryItem) => {
          if (focusDepth < item.topMd) {
              return item.topMd - focusDepth;
          }
          if (focusDepth > item.baseMd) {
              return focusDepth - item.baseMd;
          }
          return 0;
      };

      const targetItem = [...candidates].sort(
          (left, right) =>
              distanceToItem(left) - distanceToItem(right),
      )[0];

      if (!targetItem) return;

      void (async () => {
          let requiredPixelsPerMd =
              CORE_PHOTO_THRESHOLD_PIXELS_PER_MD;

          try {
              const manifest = await fetchWlvJson<{
                  chunks?: Array<{
                      top_depth: number;
                      base_depth: number;
                      pixel_width?: number;
                      pixel_height?: number;
                  }>;
              }>(targetItem.chunkManifestUrl);

              const samples = (manifest.chunks ?? []).flatMap(
                  (chunk) => {
                      const width = Number(chunk.pixel_width);
                      const height = Number(chunk.pixel_height);
                      const mdSpan =
                          Number(chunk.base_depth)
                          - Number(chunk.top_depth);

                      if (
                          !Number.isFinite(width)
                          || !Number.isFinite(height)
                          || !Number.isFinite(mdSpan)
                          || width <= 0
                          || height <= 0
                          || mdSpan <= 0
                      ) {
                          return [];
                      }

                      return [{
                          width,
                          pixelsPerMd: height / mdSpan,
                      }];
                  },
              );

              if (samples.length > 0) {
                  const median = (values: number[]) => {
                      const ordered = [...values].sort(
                          (left, right) => left - right,
                      );
                      const middle =
                          Math.floor(ordered.length / 2);

                      return ordered.length % 2 === 0
                          ? (
                              ordered[middle - 1]
                              + ordered[middle]
                          ) / 2
                          : ordered[middle];
                  };

                  const nativeWidth = median(
                      samples.map((sample) => sample.width),
                  );

                  const nativePixelsPerMd = median(
                      samples.map(
                          (sample) => sample.pixelsPerMd,
                      ),
                  );

                  /*
                   * Width requirement converted back into the vertical
                   * pixels-per-MD needed to preserve aspect ratio.
                   */
                  const widthDrivenPixelsPerMd =
                      CORE_PHOTO_THRESHOLD_WIDTH_PX
                      * nativePixelsPerMd
                      / nativeWidth;

                  requiredPixelsPerMd = Math.max(
                      CORE_PHOTO_THRESHOLD_PIXELS_PER_MD,
                      widthDrivenPixelsPerMd,
                  );
              }
          } catch {
              /*
               * The manifest is an optimization for a precise threshold.
               * Falling back to the vertical Core threshold still produces
               * a valid navigation result.
               */
          }

          const activeCoreBody =
              document.querySelector<HTMLElement>(
                  '.wlv-track.core.selected .wlv-track-body',
              )
              ?? document.querySelector<HTMLElement>(
                  '.wlv-track.core .wlv-track-body',
              );

          const bodyHeightPx =
              activeCoreBody?.getBoundingClientRect().height ?? 0;

          if (
              !Number.isFinite(bodyHeightPx)
              || bodyHeightPx <= 0
              || !Number.isFinite(requiredPixelsPerMd)
              || requiredPixelsPerMd <= 0
          ) {
              return;
          }

          const thresholdSpan = Math.max(
              MIN_DEPTH_VIEW_SPAN,
              bodyHeightPx / requiredPixelsPerMd,
          );

          const currentSpan =
              selectedCoreRange.max - selectedCoreRange.min;

          /*
           * Core Threshold must never zoom the interpreter back out.
           */
          if (currentSpan <= thresholdSpan) {
              return;
          }

          /*
           * If focus is already inside Core, preserve that exact MD.
           * If it lies between Core runs, center on the nearest point
           * of the nearest Core interval rather than jumping to the
           * interval midpoint.
           */
          const targetCenter = clampValue(
              focusDepth,
              targetItem.topMd,
              targetItem.baseMd,
          );

          if (selectedTrack && combinationStateForTrack(selectedTrack.trackId) === 'locked') return;
          applyCombinationRange({
              min: targetCenter - thresholdSpan / 2,
              max: targetCenter + thresholdSpan / 2,
          });
      })();
  };



  const goToFormationTop = (marker: FormationTopMarker) => {
      const centeredTarget = centerGoToDepthTarget(marker.md);

      setGoToDepthValue(
          String(Number(centeredTarget.toFixed(6))),
      );
      setGoToDepthPickActive(false);
  };

  const startGoToDepthPick = () => {
      setOpenCurveMenu(null);
      setIntervalZoomActive(false);
      setIntervalSelection(null);
      setDragPanState(null);
      setGoToDepthPickActive(true);
  };

  const pickGoToDepth = (depth: number) => {
      const clampedDepth = clampValue(
          depth,
          canvasAssignedCurveDepthRange.min,
          canvasAssignedCurveDepthRange.max,
      );

      /*
       * Mouse picking establishes focus only.
       * It intentionally does NOT alter the current zoom.
       *
       * Core Threshold can then use this focus to perform the
       * interpretation-scale navigation.
       */
      setGoToDepthMarker(clampedDepth);
      setGoToDepthValue(
          String(Number(clampedDepth.toFixed(6))),
      );
      setGoToDepthPickActive(false);
  };

  const startDragPan = (startY: number, sourceTrackId: string | null) => {
      setOpenCurveMenu(null);
      setIntervalZoomActive(false);
      setIntervalSelection(null);
      beginDragPan(startY, sourceTrackId);
  };

  const startIntervalSelection = (depth: number, y: number, sourceTrackId: string | null) => {
      setDragPanState(null);
      setOpenCurveMenu(null);

      // Drag Zoom uses the same selected-track authority as toolbar Zoom.
      // The gesture must begin on an explicitly selected/highlighted unlocked
      // track. Only a selected Tie principal expands to its followers.
      if (!isSelectedViewportTrackEligible({
          sourceTrackId,
          selectedTrackId: selectedTrack?.trackId ?? null,
          multiHighlightedTrackIds,
          lockedTrackIds: new Set(combinationLockedTrackIds),
      })) return;

      setIntervalSelection({
          startDepth: depth,
          currentDepth: depth,
          startY: y,
          currentY: y,
          dragging: true,
          sourceTrackId,
      });
  };
  const updateIntervalSelection = (depth: number, y: number) => {
      setIntervalSelection((current) => current
          ? { ...current, currentDepth: depth, currentY: y }
          : current);
  };
  const completeIntervalSelection = (depth: number) => {
      if (!intervalSelection)
          return;
      const nextMin = Math.min(intervalSelection.startDepth, depth);
      const nextMax = Math.max(intervalSelection.startDepth, depth);

      const sourceTrackId = intervalSelection.sourceTrackId;
      setIntervalSelection(null);

      // Drag Zoom remains armed for repeated gestures. Revalidate the source
      // at completion so Lock/selection changes during the gesture cannot
      // mutate an ineligible viewport.
      if (nextMax <= nextMin)
          return;
      if (!isSelectedViewportTrackEligible({
          sourceTrackId,
          selectedTrackId: selectedTrack?.trackId ?? null,
          multiHighlightedTrackIds,
          lockedTrackIds: new Set(combinationLockedTrackIds),
      })) return;

      applyCombinationRange({ min: nextMin, max: nextMax });
  };
  const toggleCurveForSelectedTrack = (curveId: string, checked: boolean) => {
      const operation = beginWdvDiagnosticOperation('curve-selection', checked ? 'assign' : 'remove', {
          curveId,
          checked,
          activeManagedWellUid: managedViewerWellUid,
          selectedTrackId: selectedTrack?.trackId ?? null,
          selectedTrackOwnerWellUid: selectedTrack?.managedWellUid ?? null,
          selectedTrackType: selectedTrack?.trackType ?? null,
          currentTrackCount: tracksRef.current.length,
      });
      if (!selectedTrack || selectedTrack.trackType !== 'curve') {
          operation.end({ outcome: 'ignored', reason: 'no-selected-curve-track' });
          return;
      }
      if (canonicalRevisionRef.current < 0 || !looksLikeUuid(selectedTrack.trackId)) {
          operation.end({ outcome: 'ignored', reason: 'invalid-canonical-track', revision: canonicalRevisionRef.current });
          return;
      }
      const curveLookupStartedAt = performance.now();
      const curve = activeCurveCatalog.find((item) => item.curveId === curveId || item.curveUid === curveId);
      const managedCurveUid = curve?.curveUid ?? null;
      recordWdvDiagnosticEvent('curve-selection', 'catalog-lookup', {
          operationId: operation.id,
          durationMs: performance.now() - curveLookupStartedAt,
          catalogSize: activeCurveCatalog.length,
          managedCurveUid,
      });
      if (!managedCurveUid || !looksLikeUuid(managedCurveUid)) {
          operation.end({ outcome: 'ignored', reason: 'managed-curve-not-resolved' });
          return;
      }

      const pendingKey = `${selectedTrack.trackId}:${managedCurveUid}`;
      if (curveSelectionPendingKeysRef.current.has(pendingKey)) {
          operation.end({ outcome: 'ignored', reason: 'duplicate-pending-intent', pendingKey });
          return;
      }
      curveSelectionPendingKeysRef.current.add(pendingKey);
      setCurveSelectionOptimisticByKey((current) => ({ ...current, [pendingKey]: checked }));
      setOpenCurveMenu(null);

      void (async () => {
          try {
              if (checked) {
                  const rawSession = await assignCurveToTrack(
                      selectedTrack.trackId,
                      managedCurveUid,
                  );
                  operation.end({
                      outcome: 'success',
                      responseRevision: rawSession.revision,
                      responseTrackCount: rawSession.tracks?.length ?? 0,
                  });
                  return;
              }

              const matching = selectedTrack.curves.filter((assignment) =>
                  assignment.curveUid === managedCurveUid && looksLikeUuid(assignment.assignmentId));
              for (const assignment of matching) {
                  await runRemoveCurveAssignmentWithReconcile(
                      assignment.assignmentId,
                  );
              }
              operation.end({ outcome: 'success', removedAssignmentCount: matching.length });
          } catch (error) {
              operation.end({ outcome: 'error', error: error instanceof Error ? error.message : String(error) });
              if (!(error instanceof Error && error.message.startsWith('409 '))) {
                  console.error('[WdvPageBoundary] toggleCurveForSelectedTrack failed:', error);
              }
          } finally {
              curveSelectionPendingKeysRef.current.delete(pendingKey);
              setCurveSelectionOptimisticByKey((current) => {
                  const next = { ...current };
                  delete next[pendingKey];
                  return next;
              });
          }
      })();
  };
  const lastTrackStateDiagnosticSignatureRef = useRef<string>('');
  useEffect(() => {
      const state = {
          activeManagedWellUid: managedViewerWellUid,
          trackCount: tracks.length,
          curveAssignmentCount: tracks.reduce((total, track) => total + (track.trackType === 'curve' ? track.curves.length : 0), 0),
          renderBundleCount: renderBundlesByWellUid.size,
          selectedTrackId: selectedTrack?.trackId ?? null,
      };
      const signature = JSON.stringify(state);
      if (signature === lastTrackStateDiagnosticSignatureRef.current) return;
      lastTrackStateDiagnosticSignatureRef.current = signature;
      recordWdvDiagnosticEvent('react-commit', 'track-state', state);
  }, [managedViewerWellUid, renderBundlesByWellUid, selectedTrack?.trackId, tracks]);

  const refreshWbvPublishedPackages = useCallback(async () => {
    if (!managedViewerWellUid) {
      setWbvPublishedPackages([]);
      return [] as WbvOverlayPackage[];
    }
    const response = await listWbvOverlayPackages(managedViewerWellUid);
    setWbvPublishedPackages(response.packages);
    return response.packages;
  }, [managedViewerWellUid]);

  const openWbvPublishPanel = useCallback(async () => {
    if (!managedViewerWellUid || wbvPublishBusy) return;
    setWbvPublishMessage(null);
    setWbvPublishPanelOpen((open) => !open);
    if (!wbvPublishPanelOpen) {
      try {
        await refreshWbvPublishedPackages();
      } catch (error) {
        setWbvPublishMessage(error instanceof Error ? error.message : 'Unable to read WBV publications');
      }
    }
  }, [managedViewerWellUid, refreshWbvPublishedPackages, wbvPublishBusy, wbvPublishPanelOpen]);

  const publishCurrentWdvAsNewWbvPackage = useCallback(async () => {
    if (!managedViewerWellUid || wbvPublishBusy) return;
    setWbvPublishBusy(true);
    setWbvPublishMessage(null);
    try {
      const packageName = `WDV ${managedViewerWellId ?? managedViewerWellUid} ${new Date().toISOString().slice(0, 16).replace('T', ' ')}`;
      const preview = await previewWdvPublication(managedViewerWellUid, packageName);
      if (!preview.publishable) {
        throw new Error(preview.warnings.join('; ') || 'The current WDV session is not publishable.');
      }
      const published = await publishWdvAsNewWbvPackage(managedViewerWellUid, packageName);
      await refreshWbvPublishedPackages();
      setWbvPublishPanelOpen(false);
      setWbvPublishMessage(`Published new WBV package · revision ${published.package_revision} · WDV ${published.source_wdv_revision}`);
    } catch (error) {
      setWbvPublishMessage(error instanceof Error ? error.message : 'Unable to publish WDV content to WBV');
    } finally {
      setWbvPublishBusy(false);
    }
  }, [managedViewerWellId, managedViewerWellUid, refreshWbvPublishedPackages, wbvPublishBusy]);

  const updateExistingWbvPublication = useCallback(async (target: WbvOverlayPackage) => {
    if (!managedViewerWellUid || wbvPublishBusy) return;
    setWbvPublishBusy(true);
    setWbvPublishMessage(null);
    try {
      const preview = await previewWbvPackageUpdate(managedViewerWellUid, target.package_uid);
      if (!preview.publishable) {
        throw new Error(preview.warnings.join('; ') || 'The current WDV session cannot update this WBV package.');
      }
      if (!preview.update_available) {
        setWbvPublishPanelOpen(false);
        setWbvPublishMessage(`WBV package is already current · WDV revision ${preview.source_revision}`);
        return;
      }
      const result = await updateExistingWbvPackage(
        managedViewerWellUid,
        target.package_uid,
        preview.package_revision,
      );
      await refreshWbvPublishedPackages();
      setWbvPublishPanelOpen(false);
      const changeCount =
        result.changes.tracks_added.length + result.changes.tracks_removed.length + result.changes.tracks_changed.length
        + result.changes.assignments_added.length + result.changes.assignments_removed.length + result.changes.assignments_changed.length
        + result.changes.fills_added.length + result.changes.fills_removed.length + result.changes.fills_changed.length;
      setWbvPublishMessage(`Updated WBV package · revision ${result.package.package_revision} · ${changeCount} source change${changeCount === 1 ? '' : 's'}`);
    } catch (error) {
      setWbvPublishMessage(error instanceof Error ? error.message : 'Unable to update the WBV package');
    } finally {
      setWbvPublishBusy(false);
    }
  }, [managedViewerWellUid, refreshWbvPublishedPackages, wbvPublishBusy]);

  const activeWbvPublishedPackage = wbvPublishedPackages.find((item) => item.status === 'active') ?? wbvPublishedPackages[0] ?? null;

  const wbvPublishAction = (
    <span className="wlv-wdv-wbv-publish-actions" style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {wbvPublishMessage ? <span role="status" style={{ fontSize: 11, opacity: 0.78 }}>{wbvPublishMessage}</span> : null}
      <button
        type="button"
        className="wlv-inline-wbv-publish-button wlv-send-to-wbv-button wlv-go-to-depth-button ready"
        style={{
          alignItems: 'center',
          background: 'rgba(94, 203, 255, 0.07)',
          border: '1px solid rgba(94, 203, 255, 0.78)',
          borderRadius: 4,
          boxSizing: 'border-box',
          color: '#5ecbff',
          cursor: (!managedViewerWellUid || wbvPublishBusy || tracks.length === 0) ? 'not-allowed' : 'pointer',
          display: 'inline-flex',
          fontSize: 14,
          fontWeight: 400,
          height: 28,
          justifyContent: 'center',
          letterSpacing: 0,
          lineHeight: '26px',
          margin: 0,
          minWidth: 0,
          padding: '0 14px',
          textTransform: 'none',
          whiteSpace: 'nowrap',
          width: 'auto',
        }}
        disabled={!managedViewerWellUid || wbvPublishBusy || tracks.length === 0}
        onClick={() => void openWbvPublishPanel()}
        title="Publish or update backend-owned WDV content in WBV"
        aria-expanded={wbvPublishPanelOpen}
        aria-haspopup="dialog"
      >
        {wbvPublishBusy ? 'Working…' : 'Send to WBV'}
      </button>
      {wbvPublishPanelOpen ? createPortal(
        <div
          role="dialog"
          aria-label="Send WDV content to WBV"
          style={{
            position: 'fixed',
            right: 24,
            top: 88,
            zIndex: 2147483000,
            minWidth: 300,
            maxWidth: 380,
            padding: 10,
            border: '1px solid #566171',
            borderRadius: 6,
            background: '#171b20',
            color: '#eef2f6',
            boxShadow: '0 12px 32px rgba(0,0,0,0.58)',
            display: 'grid',
            gap: 8,
            fontFamily: 'inherit',
            fontSize: 12,
          }}
        >
          <div style={{ display: 'grid', gap: 3 }}>
            <strong style={{ color: '#f3f6f9', fontSize: 13, lineHeight: 1.2 }}>
              Send WDV content to WBV
            </strong>
            <span style={{ color: '#b9c2ce', fontSize: 11, lineHeight: 1.35 }}>
              WBV retains each published package independently until you explicitly update it.
            </span>
          </div>
          {activeWbvPublishedPackage ? (
            <div style={{ display: 'grid', gap: 3, padding: 7, border: '1px solid #3e4855', borderRadius: 4, background: '#11151a' }}>
              <span style={{ color: '#9ea9b7', fontSize: 11 }}>Current retained package</span>
              <strong style={{ color: '#eef2f6', fontSize: 12 }}>{activeWbvPublishedPackage.package_name}</strong>
              <span style={{ color: '#9ea9b7', fontSize: 11 }}>
                Package revision {activeWbvPublishedPackage.package_revision} · source WDV revision {activeWbvPublishedPackage.source_wdv_revision}
              </span>
            </div>
          ) : (
            <span style={{ color: '#b9c2ce', fontSize: 11 }}>
              No retained WBV package exists for this well.
            </span>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button
              type="button"
              onClick={() => setWbvPublishPanelOpen(false)}
              disabled={wbvPublishBusy}
              style={{
                height: 28,
                padding: '0 10px',
                border: '1px solid #5d6978',
                borderRadius: 5,
                background: '#20262d',
                color: '#eef2f6',
                font: 'inherit',
                fontSize: 12,
                fontWeight: 700,
                lineHeight: 1,
                cursor: wbvPublishBusy ? 'default' : 'pointer',
                opacity: wbvPublishBusy ? 0.55 : 1,
              }}
            >
              Cancel
            </button>
            {activeWbvPublishedPackage ? (
              <button
                type="button"
                onClick={() => void updateExistingWbvPublication(activeWbvPublishedPackage)}
                disabled={wbvPublishBusy}
                style={{
                  height: 28,
                  padding: '0 10px',
                  border: '1px solid #20d98b',
                  borderRadius: 5,
                  background: '#174b3a',
                  color: '#55efaf',
                  font: 'inherit',
                  fontSize: 12,
                  fontWeight: 700,
                  lineHeight: 1,
                  cursor: wbvPublishBusy ? 'default' : 'pointer',
                  opacity: wbvPublishBusy ? 0.55 : 1,
                }}
              >
                Update existing
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void publishCurrentWdvAsNewWbvPackage()}
              disabled={wbvPublishBusy}
              style={{
                height: 28,
                padding: '0 10px',
                border: '1px solid #20d98b',
                borderRadius: 5,
                background: '#174b3a',
                color: '#55efaf',
                font: 'inherit',
                fontSize: 12,
                fontWeight: 700,
                lineHeight: 1,
                cursor: wbvPublishBusy ? 'default' : 'pointer',
                opacity: wbvPublishBusy ? 0.55 : 1,
              }}
            >
              Publish as new
            </button>
          </div>
        </div>,
        document.body,
      ) : null}
    </span>
  );

  const moveCurveToTrack = (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => {
      if (!payload.assignmentId || !looksLikeUuid(payload.assignmentId) || !looksLikeUuid(toTrackId)) return;
      const assignmentId = payload.assignmentId;
      void (async () => {
          try {
              await runMoveAssignment(
                  assignmentId,
                  toTrackId,
                  typeof toIndex === 'number' ? toIndex : 0,
              );
          } catch (error) {
              if (error instanceof Error && error.message.startsWith('409 ')) await refreshCanonicalSession();
              else console.error('[WdvPageBoundary] moveCurveToTrack failed:', error);
          }
      })();
  };
  const reorderCurve = (trackId: string, assignmentId: string, toIndex: number) => {
      const track = tracks.find((item) => item.trackId === trackId && item.trackType === 'curve');
      if (!track || track.trackType !== 'curve' || !looksLikeUuid(trackId)) return;
      const ordered = orderedCurves(track);
      const assignmentUids = planAssignmentReorder(
          ordered.map((assignment) => assignment.assignmentId),
          assignmentId,
          toIndex,
      );
      if (!assignmentUids || !assignmentUids.every(looksLikeUuid)) return;
      void (async () => {
          try {
              await runReorderAssignments(trackId, assignmentUids);
          } catch (error) {
              if (error instanceof Error && error.message.startsWith('409 ')) await refreshCanonicalSession();
              else console.error('[WdvPageBoundary] reorderCurve failed:', error);
          }
      })();
  };
  const removeCurveFromTrack = (_trackId: string, assignmentId: string) => {
      if (!looksLikeUuid(assignmentId)) return;
      setOpenCurveMenu(null);
      void (async () => {
          try {
              await runRemoveAssignment(assignmentId);
          } catch (error) {
              if (error instanceof Error && error.message.startsWith('409 ')) await refreshCanonicalSession();
              else console.error('[WdvPageBoundary] removeCurveFromTrack failed:', error);
          }
      })();
  };
  return <div className="wlv-prototype-root">
      <header className="wlv-app-header">
        <div className="wlv-app-title">
          <strong>Well Log Viewer</strong>
        </div>
      </header>

      {!hasLoadedViewerWell && !quickViewPackage && (<section className="wlv-empty-viewer-top-banner" aria-label="Well Data Viewer empty state">
          <strong>No data loaded in the Well Data Viewer</strong>
          <span>
            The WDV is ready. Load a managed well or selected products from the WMDP using Bulk Action → Load selected to Data Viewer.
          </span>
        </section>)}



      <Toolbar commonDepthUnit={quickViewPackage ? quickViewDepthUnit : (wdvWorkspace?.common_depth_unit ?? 'm')} onCommonDepthUnitChange={(unit) => quickViewPackage ? changeQuickViewDepthUnit(unit) : void changeCommonDepthUnit(unit)} managedLayoutDisabled={Boolean(quickViewPackage)} depthUnitDisabled={Boolean(quickViewPackage && !quickViewSourceUnit)} selectedTrack={quickViewPackage ? null : selectedTrack} tracks={tracks} intervalTracks={tracks.filter((track) => track.trackType === 'interval')} pendingAddTrackCurveCount={pendingAddTrackCurveIds.length} viewDepthRange={quickViewPackage ? quickViewRange : viewDepthRange} fullDepthRange={quickViewPackage ? quickViewFullRange : canvasAllTrackDepthRange} viewDepthReadoutEnabled={quickViewPackage ? true : tracks.length > 0} intervalZoomActive={quickViewPackage ? quickViewIntervalZoomActive : intervalZoomActive} goToDepthValue={quickViewPackage ? quickViewGoToDepthValue : goToDepthValue} onGoToDepthValueChange={quickViewPackage ? setQuickViewGoToDepthValue : setGoToDepthValue} trackBackdropMode={trackBackdropMode} onTrackBackdropModeChange={setTrackBackdropMode} trackHeadersCollapsed={trackHeadersCollapsed} onTrackHeadersCollapsedChange={setTrackHeadersCollapsed} onAddTrack={addTrack} onConfigureIntervalTrack={configureIntervalTrack} onDeleteTrack={deleteSelectedTrack} onClearCanvas={clearCanvas} onMoveSelectedTrack={moveSelectedTrack} canMoveSelectedTrackLeft={canMoveSelectedTrackLeft} canMoveSelectedTrackRight={canMoveSelectedTrackRight} canAdjustSelectedCurveTrackWidthDown={canAdjustSelectedCurveTrackWidthDown} canAdjustSelectedCurveTrackWidthUp={canAdjustSelectedCurveTrackWidthUp} onAdjustSelectedCurveTrackWidth={adjustSelectedCurveTrackWidth} onResetCurveTrackWidths={resetCurveTrackWidths} onZoomIn={() => quickViewPackage ? zoomQuickView(0.75) : zoomDepth(1 / 1.1)} onZoomOut={() => quickViewPackage ? zoomQuickView(1.33) : zoomDepth(1.1)} viewportToolbarPresentation={viewportToolbarPresentation} onLockSelectedTracks={lockSelectedCombinationTracks} onUnlockSelectedTracks={unlockSelectedCombinationTracks} onCreateViewportTie={createViewportTie} onUntieSelectedViewportTracks={untieSelectedViewportTracks} onPreviousView={quickViewPackage ? previousQuickView : previousDepthView} onFitDepth={() => quickViewPackage ? setQuickViewDepthWindow(quickViewFullRange) : fitDepth()} onSpecifyDepthRange={(range) => {
        if (quickViewPackage) {
            setQuickViewIntervalZoomActive(false);
            setQuickViewDepthWindow(range);
            return;
        }
        setOpenCurveMenu(null);
        setIntervalZoomActive(false);
        setIntervalSelection(null);
        setDragPanState(null);
        applyCombinationRange(range);
    }} onResetView={() => {
        if (quickViewPackage) {
            setQuickViewHistory([]);
            setQuickViewRange(quickViewFullRange);
            setQuickViewIntervalZoomActive(false);
            setQuickViewGoToDepthValue('');
            setQuickViewSelectedDepth(null);
            return;
        }
        resetDepthView();
    }} canvasRightInsetPx={quickViewPackage ? (quickViewInfoCollapsed ? 38 : 330) : (rightPropertiesCollapsed ? 38 : 330)} savedCanvases={savedCanvases} savedCanvasDisabled={Boolean(quickViewPackage) || !wdvWorkspace || !canonicalSession || curveFillPending} savedCanvasSaving={savedCanvasSaving} savedCanvasBusyUid={savedCanvasBusyUid} savedCanvasError={savedCanvasError} onSaveCanvas={saveCurrentCanvas} onSaveActiveCanvas={saveActiveCanvas} onLoadSavedCanvas={loadSavedCanvas} onDeleteSavedCanvas={deleteSavedCanvas} onToggleIntervalZoom={() => {
        if (quickViewPackage) {
            setQuickViewIntervalZoomActive((active) => !active);
            return;
        }
        setOpenCurveMenu(null);
        setIntervalSelection(null);
        setDragPanState(null);
        setIntervalZoomActive((active) => !active);
    }} onGoToDepth={quickViewPackage ? goToQuickViewDepth : goToDepth} coreThresholdAvailable={Boolean(!quickViewPackage && selectedTrack?.trackType === 'core')} onCoreThreshold={zoomToCoreThreshold} goToDepthPickActive={goToDepthPickActive} onStartGoToDepthPick={startGoToDepthPick} displayGoToSelectionLine={displayGoToSelectionLine} onDisplayGoToSelectionLineChange={setDisplayGoToSelectionLine} onAddTrackCurveSelectionModeChange={(active) => {
        setAddTrackCurveSelectionMode(active);
        if (active) {
            setPendingAddTrackCurveIds([]);
        }
    }} formationTopDatasets={formationTopDatasets} formationTopMarkersByWellUid={formationTopMarkersByWellUid} coreImageItems={coreImageItems} navigationFormationTops={displayAllFormationTops} onGoToFormationTop={goToFormationTop} selectedFormationTopIds={selectedFormationTopIds} wbvPublishAction={wbvPublishAction} layoutRecommendations={wdvTemplateRecommendations} layoutRecommendationsLoading={wdvTemplateRecommendationsLoading} layoutRecommendationsError={wdvTemplateRecommendationsError} selectedLayoutRecommendationKey={selectedWdvTemplateKey} onLayoutRecommendationChange={handleLayoutRecommendationChange} onRefreshLayoutRecommendations={refreshWdvTemplateRecommendations}/>

      {wdvTemplateModalOpen && selectedWdvTemplateRecommendation ? (<WdvTemplateRecommendationModal recommendation={selectedWdvTemplateRecommendation} loadedCurveItems={wdvPackageState.loadedCurveItems} managedWellId={managedViewerWellId} managedWellUid={managedViewerWellUid} getCanonicalRevision={() => canonicalRevisionRef.current} onClose={() => setWdvTemplateModalOpen(false)} onApplied={handleWdvTemplateApplied}/>) : null}

      <div className={`wlv-prototype-workspace wlv-track-backdrop-${trackBackdropMode} ${curveInventoryResizeState ? 'curve-inventory-resize-active' : ''} ${curveInventoryCollapsed ? 'curve-inventory-collapsed' : ''}`} style={{ gridTemplateColumns: `${curveInventoryCollapsed ? 38 : curveInventoryWidthPx}px minmax(0, 1fr) ${quickViewPackage ? (quickViewInfoCollapsed ? 38 : 330) : (rightPropertiesCollapsed ? 38 : 330)}px` }}>
        {(quickViewDragActive || quickViewPending) && <div className="wlv-qv-drop-overlay"><strong>{quickViewPending ? 'Reading file…' : 'Drop LAS or DLIS to view'}</strong></div>}
        {quickViewError && <div className="wlv-qv-status-message" role="status">{quickViewError}</div>}
        <div className={`wlv-curve-inventory-shell ${curveInventoryCollapsed ? 'collapsed' : ''}`} style={{ width: curveInventoryCollapsed ? 38 : curveInventoryWidthPx }}>
        <button type="button" className="wlv-curve-inventory-collapse-toggle" onClick={() => setCurveInventoryCollapsed((collapsed) => !collapsed)} aria-expanded={!curveInventoryCollapsed} aria-label={curveInventoryCollapsed ? 'Expand Curve Inventory' : 'Collapse Curve Inventory'} title={curveInventoryCollapsed ? 'Expand Curve Inventory' : 'Collapse Curve Inventory'}>
          {curveInventoryCollapsed ? '›' : '‹'}
        </button>
        {curveInventoryCollapsed ? (<div className="wlv-curve-inventory-collapsed-label" aria-hidden="true">Curves</div>) : (<>
        {quickViewPackage ? (<QuickViewCurveInventory pkg={quickViewPackage}/>) : (<>
        {wdvWorkspaceError && <div className="wlv-workspace-error">{wdvWorkspaceError}</div>}
        <CurveInventory availableCurves={activeViewerCurves} curveUsageCounts={curveUsageCounts} visibleTrackCurveIds={visibleTrackCurveIds} selectedTrackCurveIds={addTrackCurveSelectionMode ? pendingAddTrackCanonicalIds : selectedTrackCurveIds} selectedCurveIds={visibleTrackCurveIds} assignmentEnabled={addTrackCurveSelectionMode || selectedTrack?.trackType === 'curve'} preferredInventoryTab={tracks.length > 0 ? 'selected' : 'all'} loadedWells={wdvWorkspace?.loaded_wells ?? []} activeWell={activeInventoryWell} curveRunMetadata={activeCurveRunMetadata} lasSources={completeLasSources} selectedLasSourceId={completeLasSourceId} lasPending={completeLasPending} lasIncludeReviewRequired={completeLasIncludeReview} lasMessage={completeLasError ?? completeLasResult} onLasSourceChange={(sourceId) => { setCompleteLasSourceId(sourceId); setCompleteLasError(null); setCompleteLasResult(null); }} onLasIncludeReviewRequiredChange={setCompleteLasIncludeReview} onAddCompleteLas={() => void loadCompleteLas()} formationTopDatasets={formationTopDatasets} selectedFormationTopIds={selectedFormationTopIds} lithologyIntervalDatasets={lithologyIntervalDatasets} selectedLithologyIntervalIds={selectedLithologyIntervalIds} coreImageItems={coreImageItems} selectedCoreImageIds={selectedCoreImageIds} onToggleCoreImage={(productId, checked) => setSelectedCoreImageIds((current) => { const next = new Set(current); checked ? next.add(productId) : next.delete(productId); return next; })} onToggleAllCoreImages={(checked) => setSelectedCoreImageIds(checked ? new Set(coreImageItems.map((item) => item.productId)) : new Set())} completionComponents={managedViewerWellUid ? (completionComponentsByWellUid[managedViewerWellUid] ?? []) : []} selectedCompletionComponentIds={selectedCompletionComponentIds} onToggleCompletionComponent={(componentId, checked) => setSelectedCompletionComponentIds((current) => { const next = new Set(current); checked ? next.add(componentId) : next.delete(componentId); return next; })} onToggleAllCompletionComponents={(checked) => { const activeItems = managedViewerWellUid ? (completionComponentsByWellUid[managedViewerWellUid] ?? []) : []; setSelectedCompletionComponentIds(checked ? new Set(activeItems.map((item) => item.componentId)) : new Set()); }} onToggleLithologyInterval={(intervalId, checked) => {
            setSelectedLithologyIntervalIds((current) => { const next = new Set(current); checked ? next.add(intervalId) : next.delete(intervalId); return next; });
        }} onToggleAllLithologyIntervals={(datasetId, checked) => {
            setSelectedLithologyIntervalIds((current) => {
                const next = new Set(current);
                for (const interval of lithologyIntervalDatasets.find((item) => item.datasetId === datasetId)?.intervals ?? []) checked ? next.add(interval.intervalId) : next.delete(interval.intervalId);
                return next;
            });
        }} onToggleFormationTop={(markerId, checked) => {
            setSelectedFormationTopIds((current) => {
                const next = new Set(current);
                if (checked) next.add(markerId);
                else next.delete(markerId);
                return next;
            });
        }} onToggleAllFormationTops={(datasetId, checked) => {
            setSelectedFormationTopIds((current) => {
                const next = new Set(current);
                const dataset = formationTopDatasets.find((item) => item.datasetId === datasetId);
                for (const marker of dataset?.markers ?? []) {
                    if (checked) next.add(marker.markerId);
                    else next.delete(marker.markerId);
                }
                return next;
            });
        }} logImageSources={logImageSourceOptions} selectedLogImageSourceId={selectedLogImageSourceId} onLogImageSourceChange={setSelectedLogImageSourceId} onActiveWellChange={(managedWellId) => {
            recordWdvDiagnosticEvent('active-well', 'change-requested', {
                fromManagedWellId: managedViewerWellId,
                fromManagedWellUid: managedViewerWellUid,
                toManagedWellId: managedWellId,
                trackCount: tracksRef.current.length,
            });
            const selectedIdentityPayload = wdvWorkspace?.loaded_wells.find(
                (well) => well.managed_well_id === managedWellId,
            );
            if (!selectedIdentityPayload) {
                setWdvWorkspaceError('Selected well is not present in the backend WDV workspace.');
                return;
            }
            void changeActiveWdvWell(managedWellIdentityFromPayload(selectedIdentityPayload)).catch((error) => {
                setWdvWorkspaceError(error instanceof Error ? error.message : 'Unable to activate selected well');
            });
        }} onToggleCurveInSelectedTrack={(curveId, checked) => {
            if (addTrackCurveSelectionMode) {
                setPendingAddTrackCurveIds((current) => (checked
                    ? Array.from(new Set([...current, curveId]))
                    : current.filter((item) => item !== curveId)));
                return;
            }
            toggleCurveForSelectedTrack(curveId, checked);
        }} onSelectCurve={(curveId) => {
            setOpenCurveMenu(null);
            const containingTrack = selectedTrack?.trackType === 'curve' && selectedTrack.curves.some((assignment) => assignment.curveId === curveId)
                ? selectedTrack
                : tracks.find((track) => (track.trackType === 'curve' && track.curves.some((assignment) => assignment.curveId === curveId)));
            if (containingTrack?.trackType === 'curve') {
                const assignment = containingTrack.curves.find((item) => item.curveId === curveId);
                if (assignment)
                    setSelection({ kind: 'curve', trackId: containingTrack.trackId, assignmentId: assignment.assignmentId });
            }
        }}/>
        </>)}
        </>)}
        {!curveInventoryCollapsed && (<button type="button" className="wlv-curve-inventory-resize-handle" aria-label="Resize curve inventory panel" title="Drag to widen Curve Inventory" onMouseDown={(event) => {
            event.preventDefault();
            setCurveInventoryResizeState({ startX: event.clientX, startWidth: curveInventoryWidthPx });
        }} onDoubleClick={() => setCurveInventoryWidthPx(CURVE_INVENTORY_DEFAULT_WIDTH_PX)}/>)}
        </div>
        {quickViewPackage ? (<QuickViewCanvas pkg={quickViewPackage} onClose={closeQuickView} onElevate={handleQuickViewElevate} elevatePending={quickViewElevatePending} elevateMessage={quickViewElevateMessage} viewDepthRange={quickViewRange} displayDepthUnit={quickViewDepthUnit} selectedDepth={quickViewSelectedDepth} intervalZoomActive={quickViewIntervalZoomActive} onIntervalSelected={(range) => { setQuickViewIntervalZoomActive(false); setQuickViewDepthWindow(range); }} />) : (<>
        {tracks.length === 0 ? (hasLoadedViewerWell ? (<section className="wlv-loaded-curves-ready-state" aria-label="Loaded curves ready">
              <div className="wlv-loaded-curves-ready-card">
                <h2>Loaded curves are ready</h2>
                <p>
                  {wdvWorkspace?.loaded_wells.length ?? 0} well{(wdvWorkspace?.loaded_wells.length ?? 0) === 1 ? '' : 's'} loaded in the WDV workspace.
                  {activeInventoryWell ? ` Active well: ${activeInventoryWell.wellName}.` : ''}
                </p>
                <p>
                  {activeWorkspaceWell?.displayable_curve_count ?? 0} displayable curve{(activeWorkspaceWell?.displayable_curve_count ?? 0) === 1 ? '' : 's'} available for the active well.
                </p>
                <p className="wlv-empty-viewer-note">
                  Select loaded curves and use Add Track, or drag curves into a manually created curve track.
                  WMDP Load does not automatically populate well-log tracks.
                </p>
                {wdvPackageState.unsupportedProductCount > 0 && (<p className="wlv-empty-viewer-note">
                    {wdvPackageState.unsupportedProductCount} unsupported product{wdvPackageState.unsupportedProductCount === 1 ? '' : 's'}
                    {' '}were excluded from renderable Loaded Curves.
                  </p>)}
              </div>
            </section>) : (<section className="wlv-track-canvas wlv-track-canvas-empty-active" aria-label="Blank Well Data Viewer track canvas">
              <div className="wlv-track-strip" aria-hidden="true"/>
            </section>)) : (<TrackCanvas trackHeadersCollapsed={trackHeadersCollapsed} tracks={tracks} trackHeaderPresentationById={trackHeaderPresentationById} viewportTieGroups={viewportTieGroups} trackDepthRangesById={trackCanvasRenderModel.trackDepthRangesById} trackContentDepthRangesById={trackFullDepthRangesById} fullDepthRangesByWellUid={fullDepthRangesByWellUid} fullDepthRange={trackCanvasRenderModel.fullDepthRange} onToggleCombinationTrack={toggleCombinationTrack} trackHighlightedById={trackSelectionPresentationModel.highlightedByTrackId} selectedAssignmentIdByTrackId={trackSelectionPresentationModel.selectedAssignmentIdByTrackId} openCurveMenu={openCurveMenu} depthTicks={visibleDepthTicks} viewDepthRange={trackCanvasRenderModel.viewDepthRange} goToDepthMarker={goToDepthMarker} goToSelectionTrackIds={groupActionTrackIds} displayGoToSelectionLine={displayGoToSelectionLine} goToDepthPickActive={goToDepthPickActive} onPickGoToDepth={pickGoToDepth} renderBundlesByWellUid={renderBundlesByWellUid} liveFormationTopOverlayStylesByTrackId={displayFormationTopOverlayStylesByTrackId} coreImageItems={coreImageItems} coreImageItemsByWellUid={coreImageItemsByWellUid} completionComponentsByWellUid={completionComponentsByWellUid} selectedCompletionComponentIds={selectedCompletionComponentIds} selectedCompletionComponentIdsByWellUid={selectedCompletionComponentIdsByWellUid} activeWellName={activeInventoryWell?.wellName ?? ''} selectedCoreImageIds={selectedCoreImageIds} selectedCoreImageIdsByWellUid={selectedCoreImageIdsByWellUid} intervalZoomActive={intervalZoomActive} intervalSelection={intervalSelection} dragPanActive={trackCanvasRenderModel.dragPanActive} onSelectTrack={selectCanvasTrack} onSelectCurve={selectCanvasCurve}
          onEditCurve={(trackId, assignmentId) => {
            selectCanvasCurve(trackId, assignmentId);
            setOpenCurveMenu(null);
            setRightPropertiesCollapsed(false);
            setCurveEditRequest((current) => ({
              trackId,
              assignmentId,
              requestId: (current?.requestId ?? 0) + 1,
            }));
          }} onReorderCurve={reorderCurve} onMoveCurveToTrack={moveCurveToTrack} onOpenCurveMenu={(trackId, assignmentId) => setOpenCurveMenu({ trackId, assignmentId })} onCloseCurveMenu={() => setOpenCurveMenu(null)} onRemoveCurveFromTrack={removeCurveFromTrack} onStartIntervalSelection={startIntervalSelection} onUpdateIntervalSelection={updateIntervalSelection} onCompleteIntervalSelection={completeIntervalSelection} onStartDragPan={startDragPan} onUpdateDragPan={updateDragPan} onEndDragPan={endDragPan} onStartCurveTrackResize={startCurveTrackResize} resizingTrackId={trackResizeState?.trackId ?? null} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={activeCurveCatalog}/>)}
        </>)}
        {quickViewPackage ? (<QuickViewMetadataPanel pkg={quickViewPackage} collapsed={quickViewInfoCollapsed} onToggleCollapsed={() => setQuickViewInfoCollapsed((collapsed) => !collapsed)} />) : (tracks.length === 0 ? (<aside className="wlv-right-panel wlv-ready-properties-panel" aria-label="Track properties unavailable">
            <div className="wlv-panel-heading">
              <h2>Track Properties</h2>
            </div>
            <div className="wlv-ready-properties-copy">
              Create or select a visible track to edit display properties.
            </div>
          </aside>) : (<WellLogPropertiesPanelSlot
          tracks={tracks}
          selection={selection}
          selectedTrackIds={Array.from(new Set([
            ...(selection.trackId ? [selection.trackId] : []),
            ...multiHighlightedTrackIds,
          ]))}
          completionComponentsByWellUid={completionComponentsByWellUid}
          selectedCompletionComponentIdsByWellUid={selectedCompletionComponentIdsByWellUid}
          coreImageItemsByWellUid={coreImageItemsByWellUid}
          selectedCoreImageIdsByWellUid={selectedCoreImageIdsByWellUid}
          curveCatalogItems={activeCurveCatalog} managedSampleContractsByCurveId={managedSampleContractsByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} wdvIdentityMetadata={effectiveWdvIdentityMetadata} wdvIdentityMetadataError={wdvIdentityMetadataError} wellNameByManagedWellUid={Object.fromEntries(ownerWellNames)} updateTrack={updateTrack} updateCurveAssignment={updateCurveAssignment} previewCurveLineStyle={previewCurveLineStyle} commitCurveLineStyle={commitCurveLineStyle}
          curveEditRequest={curveEditRequest} formationTops={displayFormationTops} loadedFormationTops={displayAllFormationTops} lithologyIntervals={displayAllLoadedLithologyIntervals} depthUnit={overlayDisplayDepthUnit} formationTopOverlayStylesByTrackId={displayFormationTopOverlayStylesByTrackId} updateFormationTopOverlayStyle={(trackId, patch) => {
            // WDV_FORMATION_TOPS_SELECTED_TRACKS_LIVE_PREVIEW_V1_0_1
            // Overlay editing is a live-preview transaction. Keep the canonical
            // track-style map and already-rendered per-well presentation state
            // synchronized immediately; Apply remains the persistence boundary
            // and Cancel restores through the existing editor snapshot.
            const nextDisplayStyle = {
              ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
              ...(displayFormationTopOverlayStylesByTrackId[trackId] ??
                DEFAULT_FORMATION_TOP_OVERLAY_STYLE),
              ...patch,
            };

            setFormationTopOverlayStylesByTrackId((current) => {
              const displayCurrent = projectOverlayStylesToDisplayUnit(current);
              const nextDisplay = {
                ...displayCurrent,
                [trackId]: {
                  ...(displayCurrent[trackId] ?? DEFAULT_FORMATION_TOP_OVERLAY_STYLE),
                  ...patch,
                },
              };
              return normalizeOverlayStylesToCanonicalMetres(nextDisplay);
            });

            const targetTrack = tracks.find(
              (candidate) => candidate.trackId === trackId,
            );
            if (targetTrack?.managedWellUid) {
              setOverlayRenderStateByWellUid((current) => {
                const ownerState = current[targetTrack.managedWellUid!];
                if (!ownerState) return current;
                return {
                  ...current,
                  [targetTrack.managedWellUid!]: {
                    ...ownerState,
                    formationTopOverlayStylesByTrackId: {
                      ...ownerState.formationTopOverlayStylesByTrackId,
                      [trackId]: {
                        ...nextDisplayStyle,
                        fillZones: [
                          ...(nextDisplayStyle.fillZones ?? []),
                        ],
                      },
                    },
                  },
                };
              });
            }
          }} commitFormationTopOverlayStyles={(stylesByTrackId, touchedTrackIds) => {
            // The editor works in the active display unit; durable overlay state
            // remains canonical metres so m↔ft switching never mutates or drifts it.
            const canonicalStyles = normalizeOverlayStylesToCanonicalMetres(stylesByTrackId);
            setFormationTopOverlayStylesByTrackId(canonicalStyles);

            // WDV_OVERLAY_TRACK_CANVAS_STYLE_AUTHORITY_V1_0_0
            // Formation-top selections/data are well-owned. Presentation styles
            // are track/canvas-owned and must never be replaced by active-well
            // hydration. Extend therefore commits the complete track-style map to
            // one canvas authority; each target menu reads the copied value by
            // trackId after activation, refresh, and restart.
            writePersistedCurveOverlayTrackStyles(canonicalStyles);

            const touched = new Set(touchedTrackIds);

            // Update already-rendered background wells immediately. The copied
            // styles therefore remain visible before and after well activation.
            setOverlayRenderStateByWellUid((current) => {
              let changed = false;
              const next = { ...current };
              for (const track of tracks) {
                if (!touched.has(track.trackId) || !track.managedWellUid) continue;
                const style = canonicalStyles[track.trackId];
                const ownerState = next[track.managedWellUid];
                if (!style || !ownerState) continue;
                next[track.managedWellUid] = {
                  ...ownerState,
                  formationTopOverlayStylesByTrackId: {
                    ...ownerState.formationTopOverlayStylesByTrackId,
                    [track.trackId]: projectOverlayStylesToDisplayUnit({
                      [track.trackId]: style,
                    })[track.trackId],
                  },
                };
                changed = true;
              }
              return changed ? next : current;
            });
          }} collapsed={rightPropertiesCollapsed} onToggleCollapsed={() => setRightPropertiesCollapsed((collapsed) => !collapsed)} curveFillV2={{ enabled: curveFillFeatureEnabled, managedWellUid: managedViewerWellUid, revision: canonicalSession?.revision ?? canonicalRevisionRef.current, rules: canonicalSession?.curve_fills ?? [], pending: curveFillPending, error: curveFillError, onCreateRule: createCurveFillRule, onUpdateRule: updateCurveFillRule, onRemoveRule: removeCurveFillRule, onReorderRules: reorderCurveFillRules }} legacyPanel={(<RightPanel tracks={tracks} selection={selection} curveCatalogItems={activeCurveCatalog} updateTrack={updateTrack} updateCurveAssignment={updateCurveAssignment}/>)}/>))}
      </div>


      <footer className="wlv-status-footer">
        <span>Backend-managed WDV workspace</span>
        <span>Backend-owned depth and curve contracts</span>
        <span>Portable local and enterprise deployment</span>
      </footer>
        </div>;
}
import type { CurveLineStyleValue } from "../prototype/CurveLineStyleControl";
