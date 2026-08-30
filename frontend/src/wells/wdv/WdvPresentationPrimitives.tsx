import { resolvedCurveFillPaintV2, type CurveFillGeometryV2 } from './curveFillV2';
import { renderBundleForTrack, type WellOwnedTrackRenderBundle } from './wellOwnedRenderBundles';
// WLV WDV presentation primitives.
// WLV-TRACK-CONTENT-RENDER-ORDER-AND-PAIRED-FILL-V1
// Extracted from TrackLayoutPrototype.

import { Fragment, createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import * as THREE from 'three';
import type { MouseEvent as ReactMouseEvent, ReactNode } from 'react';
import { depthUnitLabel, realCurveSamplesByCurveId, wellHeader } from '../prototype/realLasTrackLayoutData';
import { lithologyIntervals21_31, lithologySource } from '../prototype/lithologyTrackData';
import type { WdvLoadedCurveItem } from '../prototype/wdvPackageState';
import { resolveManagedCurveError, resolveManagedCurveSamples, type ManagedCurveSamplesByCurveId } from '../prototype/managedCurveSamples';
import { useTrackBodyGeometry } from '../prototype/useTrackBodyGeometry';
import type { ActiveTrackType, CompletionTrackAppearance, CoreTrackAppearance, CurveAssignment, CurveCatalogItem, CurveTrack, DepthBasis, DepthTrack, DragCurvePayload, FillSide, LineStyle, LithologyTrack, ScaleMode, SelectionRef, WellLogTrack } from '../prototype/trackLayoutModel';
import { DEFAULT_COMPLETION_TRACK_APPEARANCE, DEFAULT_CORE_TRACK_APPEARANCE, orderedCurves, parseDragPayload, resolveTrackLattice } from '../prototype/trackLayoutModel';
import { canonicalCurveKey } from '../identity/curveIdentityIndex';
import { CurveLineStyleControl, type CurveLineStyleValue } from '../prototype/CurveLineStyleControl';
import { SharedInfillEditor } from '../prototype/SharedInfillEditor';
import { KrLithologyPatternPicker } from '../prototype/KrLithologyPatternPicker';
import type { ViewportToolbarPresentation } from './viewportToolbarPresentationModel';
import { standardizedMagnificationLabel } from './magnificationScale';
import { SavedCanvasToolbarControl, type SavedCanvasToolbarItem } from './SavedCanvasToolbarControl';

export type CoreDescriptionInventoryRecord = {
    descriptionId: string;
    md: number;
    text: string;
    category: string;
};

export type CoreImageInventoryItem = {
    productId: string;
    managedWellId: string;
    label: string;
    topMd: number;
    baseMd: number;
    depthUnit: string;
    imageType: string;
    descriptionCount: number;
    descriptions?: CoreDescriptionInventoryRecord[];
    runNumber?: string | null;
    sourceLabel?: string | null;

    // V1 fallback.
    imageUrl: string;

    // V2 continuous-core publication.
    chunkManifestUrl: string;
};

type CoreImageDisplayChunk = {
    chunk_id: string;
    sequence_index: number;
    top_depth: number;
    base_depth: number;
    depth_unit: string;
    image_filename: string;
    mime_type: string;
    image_sha256?: string | null;
};

type CoreImageChunkManifest = {
    product_id: string;
    segment_id?: string | null;
    segment_name?: string | null;
    top_depth?: number | null;
    base_depth?: number | null;
    depth_unit?: string | null;
    display_contract_version?: string | null;
    schema_version?: string | null;
    chunks: CoreImageDisplayChunk[];
};

export type DepthViewRange = {
    min: number;
    max: number;
};
export type WdvSessionLayoutCurveState = {
    assignment_id?: string;
    assignmentId?: string;
    curve_uid?: string | null;
    curveUid?: string | null;
    well_uid?: string | null;
    wellUid?: string | null;
    source_uid?: string | null;
    sourceUid?: string | null;
    kr_curve_type_id?: string | null;
    krCurveTypeId?: string | null;
    observed_mnemonic?: string | null;
    observedMnemonic?: string | null;
    normalized_mnemonic?: string | null;
    normalizedMnemonic?: string | null;
    curve_id?: string;
    curveId?: string;
    product_id?: string | null;
    productId?: string | null;
    mnemonic?: string | null;
    display_curve_id?: string | null;
    displayCurveId?: string | null;
    display_name?: string | null;
    displayName?: string | null;
    curve_family?: string | null;
    curveFamily?: string | null;
    unit?: string | null;
    stack_index?: number;
    stackIndex?: number;
    visible?: boolean;
    scale_min?: number | null;
    scaleMin?: number | null;
    scale_max?: number | null;
    scaleMax?: number | null;
    scale_min_label?: string | null;
    scale_max_label?: string | null;
    scale_type?: string | null;
    scaleType?: string | null;
    scale_direction?: string | null;
    scaleDirection?: string | null;
    color?: string | null;
};
export type WdvSessionLayoutTrackState = {
    track_id?: string;
    trackId?: string;
    track_number?: number | null;
    trackNumber?: number | null;
    track_name?: string;
    trackName?: string;
    track_type?: string;
    trackType?: string;
    width_px?: number | null;
    widthPx?: number | null;
    lattice?: string | null;
    lattice_source?: string | null;
    latticeSource?: string | null;
    curves?: WdvSessionLayoutCurveState[];
};
export type WdvSessionLayoutResponse = {
    state_status?: 'empty' | 'active' | 'cleared';
    active_curve_ids?: string[];
    activeCurveIds?: string[];
    active_product_ids?: string[];
    activeProductIds?: string[];
    active_display_curve_ids?: string[];
    activeDisplayCurveIds?: string[];
    active_curve_mnemonics?: string[];
    activeCurveMnemonics?: string[];
    curve_assignments?: Array<Record<string, unknown>>;
    curveAssignments?: Array<Record<string, unknown>>;
    selected_track_id?: string | null;
    selectedTrackId?: string | null;
    tracks?: WdvSessionLayoutTrackState[];
    revision?: number;
};
export type WdvTemplateRecommendationLoadedCurvePayload = {
    product_id?: string | null;
    curve_uid?: string | null;
    well_uid?: string | null;
    source_uid?: string | null;
    kr_curve_type_id?: string | null;
    observed_mnemonic?: string | null;
    normalized_mnemonic?: string | null;
    curve_id?: string | null;
    display_curve_id?: string | null;
    canonical_curve_id?: string | null;
    original_mnemonic?: string | null;
    mnemonic?: string | null;
    normalized_name?: string | null;
    display_name?: string | null;
    curve_family?: string | null;
    track_family?: string | null;
    unit?: string | null;
    is_renderable?: boolean | null;
    support_status?: string | null;
    source_id?: string | null;
};
export type WdvTemplateRecommendationRequestPayload = {
    loaded_curve_items: WdvTemplateRecommendationLoadedCurvePayload[];
    workflow_context?: string | null;
    selected_product_ids?: string[];
    include_ineligible?: boolean;
};
export type WdvRecommendedCurve = {
    product_id?: string | null;
    curve_id?: string | null;
    mnemonic?: string | null;
    display_name?: string | null;
    unit?: string | null;
    curve_family?: string | null;
    raw_curve_family?: string | null;
    canonical_curve_id?: string | null;
    depth_role?: string | null;
    selection_reason?: string | null;
};
export type WdvTemplateRequirementCoverage = {
    available_families?: string[];
    missing_families?: string[];
    coverage_ratio?: number;
};
export type WdvTemplateRecommendationTrack = {
    track_id?: string | null;
    track_key?: string | null;
    track_number?: number | null;
    track_name?: string | null;
    track_role?: string | null;
    renderer_type?: string | null;
    required_renderer_capability?: string | null;
    selected_curves?: WdvRecommendedCurve[];
    alternate_curves?: WdvRecommendedCurve[];
    missing_curve_families?: string[];
    scale_defaults?: Array<Record<string, unknown>>;
};
export type WdvTemplateRecommendationItem = {
    template_key: string;
    template_label: string;
    workflow_context?: string | null;
    template_priority?: number | null;
    is_eligible: boolean;
    rank: number;
    score: number;
    required_coverage?: WdvTemplateRequirementCoverage;
    preferred_coverage?: WdvTemplateRequirementCoverage;
    optional_coverage?: WdvTemplateRequirementCoverage;
    missing_required_families?: string[];
    missing_preferred_families?: string[];
    selected_curve_count?: number;
    alternate_curve_count?: number;
    excluded_curve_count?: number;
    selected_curves?: WdvRecommendedCurve[];
    alternate_curves?: WdvRecommendedCurve[];
    excluded_curves?: WdvRecommendedCurve[];
    tracks?: WdvTemplateRecommendationTrack[];
    renderer_requirements?: string[];
    reason_codes?: string[];
};
export type WdvTemplateApplicationPlanTrack = WdvTemplateRecommendationTrack & {
    planned_action?: string | null;
};
export type WdvTemplateApplicationPlan = {
    application_plan_id: string;
    plan_status: string;
    template_key: string;
    template_label: string;
    workflow_context?: string | null;
    source_recommendation_rank?: number | null;
    source_recommendation_score?: number | null;
    apply_eligible: boolean;
    apply_mode?: string | null;
    blocking_issues?: string[];
    warnings?: string[];
    selected_curve_count?: number;
    alternate_curve_count?: number;
    excluded_curve_count?: number;
    selected_curves?: WdvRecommendedCurve[];
    alternate_curves?: WdvRecommendedCurve[];
    excluded_curves?: WdvRecommendedCurve[];
    tracks?: WdvTemplateApplicationPlanTrack[];
    renderer_requirements?: string[];
    missing_required_families?: string[];
    missing_preferred_families?: string[];
    reason_codes?: string[];
};
export type WdvTemplateApplicationPlanEnvelope = {
    service: string;
    contract_version: string;
    mutation_performed: boolean;
    plan: WdvTemplateApplicationPlan;
    knowledge_policy?: Record<string, unknown>;
};
export type WdvTemplateApplicationApplyEnvelope = {
    service: string;
    contract_version: string;
    mutation_performed: boolean;
    managed_well_id: string;
    template_key: string;
    application_plan_id: string;
    layout: WdvSessionLayoutResponse;
    apply_summary?: {
        track_count?: number;
        curve_assignment_count?: number;
        warnings?: string[];
    };
    knowledge_policy?: Record<string, unknown>;
};
export type IntervalSelectionState = {
    startDepth: number;
    currentDepth: number;
    startY: number;
    currentY: number;
    dragging: boolean;
    sourceTrackId: string | null;
};
export const CURVE_TRACK_MIN_WIDTH = 1;
export const CURVE_TRACK_MAX_WIDTH = 420;
export const CURVE_TRACK_WIDTH_STEP = 24;
export function formatDepthLabelValue(value: number): string {
    if (!Number.isFinite(value)) return '';
    const rounded = Math.round(value * 100) / 100;
    return rounded.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
}

export function depthRangeLabel(range: DepthViewRange, unit: 'm' | 'ft' = depthUnitLabel as 'm' | 'ft'): string {
    return `${formatDepthLabelValue(range.min)}–${formatDepthLabelValue(range.max)} ${unit} MD`;
}
export function wlvApiBaseUrl(): string {
    // WLV-MDP-API-PORT-8001-1:
    // The active WLV backend runs on 8001. Keep runtime override support,
    // use relative paths when served by the backend, and send Vite/dev
    // frontend calls to the backend inventory/source-intake API on 8001.
    const runtimeConfig = window as unknown as {
        __WLV_API_BASE_URL__?: string;
    };
    if (runtimeConfig.__WLV_API_BASE_URL__) {
        return runtimeConfig.__WLV_API_BASE_URL__.replace(/\/$/, '');
    }
    const protocol = window.location.protocol || 'http:';
    const hostname = window.location.hostname || '127.0.0.1';
    const port = window.location.port;
    const backendPort = '8001';
    if (port === backendPort) {
        return '';
    }
    if (port === '5173' || port === '5174' || port === '5175') {
        return `${protocol}//${hostname}:${backendPort}`;
    }
    return `http://127.0.0.1:${backendPort}`;
}
export async function fetchWlvJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${wlvApiBaseUrl()}${path}`, {
        ...init,
        headers: {
            Accept: 'application/json',
            ...(init?.headers ?? {}),
        },
    });
    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<T>;
}
export function curveInventoryIdentityKey(curve: CurveCatalogItem): string {
    return canonicalCurveKey(curve);
}

export function curveInventoryRowsForTab(
    tab: CurveInventoryTab,
    availableCurves: CurveCatalogItem[],
    visibleTrackCurveIds: Set<string>,
): CurveCatalogItem[] {
    if (tab === 'aliases')
        return [];
    if (tab === 'selected') {
        return availableCurves.filter((curve) =>
            visibleTrackCurveIds.has(curveInventoryIdentityKey(curve)),
        );
    }
    // Loaded is the backend-provided curve inventory. Track usage must not
    // determine whether a loaded backend curve record is visible.
    return availableCurves;
}

export function loadedMnemonicRows(curves: CurveCatalogItem[]): CurveCatalogItem[] {
    // Duplicate mnemonics from distinct backend curve identities remain
    // separate rows. The frontend must not collapse authoritative records.
    return curves;
}
export function resolveCurveAssignmentCatalogItem(catalog: CurveCatalogItem[], assignment: CurveAssignment): CurveCatalogItem | null {
    const identityCandidates = [
        assignment.curveId,
        assignment.curveUid,
        assignment.krCurveTypeId,
    ].map((value) => String(value || '').trim()).filter(Boolean);
    const exactOwner = (curve: CurveCatalogItem): boolean => (
        Boolean(assignment.managedWellUid)
        && curve.managedWellUid === assignment.managedWellUid
    );
    const compatibleOwner = (curve: CurveCatalogItem): boolean => (
        !assignment.managedWellUid
        || !curve.managedWellUid
        || curve.managedWellUid === assignment.managedWellUid
    );
    const exactUidMatch = catalog.find((curve) => exactOwner(curve) && Boolean(curve.curveUid) && identityCandidates.includes(String(curve.curveUid)));
    if (exactUidMatch)
        return exactUidMatch;
    const exactDirectMatch = catalog.find((curve) => exactOwner(curve) && identityCandidates.includes(String(curve.curveId)));
    if (exactDirectMatch)
        return exactDirectMatch;
    const uidMatch = catalog.find((curve) => compatibleOwner(curve) && Boolean(curve.curveUid) && identityCandidates.includes(String(curve.curveUid)));
    if (uidMatch)
        return uidMatch;
    const directMatch = catalog.find((curve) => compatibleOwner(curve) && identityCandidates.includes(String(curve.curveId)));
    if (directMatch)
        return directMatch;
    const mnemonicCandidates = [
        assignment.normalizedMnemonic,
        assignment.observedMnemonic,
    ].map((value) => String(value || '').trim().toLowerCase()).filter(Boolean);
    const mnemonicMatch = mnemonicCandidates.length > 0
        ? catalog.find((curve) => {
            if (!compatibleOwner(curve)) return false;
            const curveMnemonics = [
                curve.mnemonic,
                curve.normalizedMnemonic,
                curve.observedMnemonic,
            ].map((value) => String(value || '').trim().toLowerCase()).filter(Boolean);
            return curveMnemonics.some((value) => mnemonicCandidates.includes(value));
        })
        : undefined;
    if (mnemonicMatch) return mnemonicMatch;

    /*
     * WDV_BACKGROUND_CURVE_OWNER_RESOLUTION_V1_0_0
     *
     * The shared canvas can contain Curve tracks owned by wells other than the
     * currently active Curve Inventory well. Canonical assignments already carry
     * the complete display identity required by the renderer. Never suppress a
     * background curve merely because its owner catalog is not the active catalog.
     */
    const mnemonic = String(
        assignment.normalizedMnemonic
        ?? assignment.observedMnemonic
        ?? assignment.displayName
        ?? assignment.curveId,
    ).trim() || assignment.curveId;
    return {
        curveId: assignment.curveId,
        curveUid: assignment.curveUid ?? assignment.curveId,
        krCurveTypeId: assignment.krCurveTypeId ?? null,
        wellUid: assignment.wellUid ?? null,
        managedWellUid: assignment.managedWellUid ?? null,
        managedProductUid: assignment.managedProductUid ?? null,
        sourceUid: assignment.sourceUid ?? null,
        managedSourceUid: assignment.managedSourceUid ?? null,
        observedMnemonic: assignment.observedMnemonic ?? mnemonic,
        normalizedMnemonic: assignment.normalizedMnemonic ?? mnemonic,
        mnemonic,
        description: assignment.displayName ?? mnemonic,
        unit: assignment.unit ?? '',
        curveClass: 'unknown',
        backendCurveFamily: assignment.curveFamily ?? null,
        defaultLattice: assignment.scaleType === 'log' ? 'logarithmic' : 'linear',
        defaultMin: assignment.scaleMin,
        defaultMax: assignment.scaleMax,
        defaultScaleDirection: assignment.scaleDirection,
        defaultColor: assignment.color,
        recognised: false,
    };
}
export function recommendationCurveFamily(item: WdvLoadedCurveItem): string | null {
    if (item.trackFamily)
        return item.trackFamily;
    switch (item.curveFamily) {
        case 'gamma': return 'gamma_ray';
        case 'borehole': return 'caliper';
        case 'neutron': return 'neutron_porosity';
        case 'sonic': return 'sonic_slowness';
        default: return item.curveFamily || null;
    }
}
export function buildWdvTemplateRecommendationRequest(loadedCurveItems: WdvLoadedCurveItem[]): WdvTemplateRecommendationRequestPayload {
    return {
        workflow_context: 'open_hole',
        include_ineligible: true,
        selected_product_ids: [],
        loaded_curve_items: loadedCurveItems.map((item) => ({
            product_id: item.productId,
            curve_id: item.curveId,
            display_curve_id: item.displayCurveId,
            canonical_curve_id: item.canonicalCurveId ?? null,
            original_mnemonic: item.originalMnemonic,
            mnemonic: item.originalMnemonic,
            normalized_name: item.displayName,
            display_name: item.displayName,
            curve_family: recommendationCurveFamily(item),
            track_family: item.trackFamily ?? null,
            unit: item.unit,
            is_renderable: true,
            support_status: item.supportStatus ?? null,
            source_id: item.sourceId ?? null,
        })),
    };
}
export async function buildWdvTemplateApplicationPlan(templateKey: string, loadedCurveItems: WdvLoadedCurveItem[], managedWellId?: string | null): Promise<WdvTemplateApplicationPlanEnvelope> {
    const recommendationPayload = buildWdvTemplateRecommendationRequest(loadedCurveItems);
    return fetchWlvJson<WdvTemplateApplicationPlanEnvelope>('/api/wlv/wdv/templates/application-plans/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            managed_well_id: managedWellId || 'wdv_current_viewer_session',
            template_key: templateKey,
            workflow_context: recommendationPayload.workflow_context,
            loaded_curve_items: recommendationPayload.loaded_curve_items,
        }),
    });
}
export interface WdvCanonicalTemplateApplySession {
    revision: number;
    state_status: 'empty' | 'active' | 'cleared';
    selected_track_uid: string | null;
    tracks: Array<{
        track_uid: string;
        track_name: string;
        track_type: string;
        width_px?: number | null;
        lattice?: string | null;
        lattice_source?: string | null;
        lattice_override?: boolean | null;
        scale_mode?: string | null;
        depth_basis?: string | null;
        assignments: Array<{
            assignment_uid: string;
            managed_curve_uid: string;
            stack_index: number;
            visible: boolean;
            scale_min: number | null;
            scale_max: number | null;
            scale_type: string | null;
            scale_direction: string | null;
            color: string | null;
        }>;
    }>;
}

export async function applyCanonicalWdvTemplate(
    managedWellUid: string,
    expectedRevision: number,
    templateKey: string,
    workflowContext = 'open_hole',
): Promise<WdvCanonicalTemplateApplySession> {
    if (!managedWellUid.trim()) {
        throw new Error('Canonical template apply requires managed well UID.');
    }
    if (expectedRevision < 0) {
        throw new Error('Canonical WDV session is not ready for template application.');
    }
    return fetchWlvJson<WdvCanonicalTemplateApplySession>(
        `/api/wlv/v2/wdv/template-commands/${encodeURIComponent(managedWellUid)}/apply`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                expected_revision: expectedRevision,
                template_key: templateKey,
                workflow_context: workflowContext,
            }),
        },
    );
}
export function compactFamilyList(values?: string[], fallback = 'None'): string {
    if (!values || values.length === 0)
        return fallback;
    return values.slice(0, 6).join(', ') + (values.length > 6 ? ` +${values.length - 6}` : '');
}
export function compactRendererList(values?: string[], fallback = 'None'): string {
    if (!values || values.length === 0)
        return fallback;
    return values.map((value) => value.replace(/_/g, ' ')).slice(0, 5).join(', ') + (values.length > 5 ? ` +${values.length - 5}` : '');
}
export function formatPlanStatus(value?: string | null): string {
    return (value || 'pending').replace(/_/g, ' ');
}
export function formatTemplateMatch(value?: number | null): string {
    if (typeof value !== 'number' || Number.isNaN(value))
        return 'Pending';
    if (value >= 85)
        return 'Strong';
    if (value >= 70)
        return 'Good';
    if (value >= 50)
        return 'Partial';
    return 'Weak';
}
export function curveVisibleIdentity(curve: WdvRecommendedCurve): string {
    const visibleName = curve.mnemonic || curve.display_name || curve.curve_id || curve.product_id || '';
    const visibleFamily = curve.curve_family || curve.raw_curve_family || '';
    return `${visibleName}`.trim().toLowerCase().replace(/[\s\-/]+/g, '_') + '::' + `${visibleFamily}`.trim().toLowerCase().replace(/[\s\-/]+/g, '_');
}
export function uniqueVisibleRecommendedCurves(curves: WdvRecommendedCurve[]): WdvRecommendedCurve[] {
    const seen = new Set<string>();
    const unique: WdvRecommendedCurve[] = [];
    for (const curve of curves) {
        const identity = curveVisibleIdentity(curve);
        if (seen.has(identity))
            continue;
        seen.add(identity);
        unique.push(curve);
    }
    return unique;
}
export function scaleSummary(scaleDefaults?: Array<Record<string, unknown>>): string {
    if (!scaleDefaults || scaleDefaults.length === 0)
        return 'scale defaults pending';
    return scaleDefaults.slice(0, 3).map((scale) => {
        const family = typeof scale.curve_family === 'string' ? scale.curve_family.replace(/_/g, ' ') : 'curve';
        const scaleType = typeof scale.scale_type === 'string' ? scale.scale_type : 'scale';
        const min = scale.scale_min;
        const max = scale.scale_max;
        const range = (typeof min === 'number' || typeof max === 'number') ? ` ${String(min ?? '—')}–${String(max ?? '—')}` : '';
        return `${family}: ${scaleType}${range}`;
    }).join('; ');
}
export function sortTracks(tracks: WellLogTrack[]): WellLogTrack[] {
    return [...tracks].sort((a, b) => a.trackIndex - b.trackIndex);
}
export const TRACK_STRIP_PADDING_PX = 10;
export const TRACK_HEADER_HEIGHT_PX = 108;
export const TRACK_BODY_HEIGHT_PX = 900;
export const TRACK_BODY_MIN_HEIGHT_PX = 320;
export const TRACK_BODY_MAX_HEIGHT_PX = 12000;
export const TRACK_FOOTER_CLEARANCE_PX = 48;
export const TRACK_HEADER_TITLE_HEIGHT_PX = 24;
export const TRACK_HEADER_WELL_OWNER_HEIGHT_PX = 24;
export const TRACK_HEADER_COLLAPSED_HEIGHT_PX = 52;
export const TRACK_HEADER_SUBTITLE_HEIGHT_PX = 28;
export const TRACK_CURVE_HEADER_ROW_HEIGHT_PX = 38;
export const TRACK_HEADER_BOTTOM_PADDING_PX = 8;
export const CURVE_VIEW_PADDING_X = 10;
export type MockCurveSample = {
    depth: number;
    value: number;
};
export function depthToY(depth: number, viewRange: DepthViewRange, bodyHeightPx = TRACK_BODY_HEIGHT_PX): number {
    const span = Math.max(1e-9, viewRange.max - viewRange.min);
    const t = (depth - viewRange.min) / span;
    return clampValue(t, 0, 1) * bodyHeightPx;
}

/*
 * Core photographic geometry requires the complete source interval to remain
 * geometrically intact even when most of that interval is outside the current
 * viewport.
 *
 * Example:
 *   source chunk = 3925–3930 m
 *   viewport     = 3928.90–3929.00 m
 *
 * The source image must be positioned at its full 5 m display scale and the
 * Core track viewport clips the invisible portions. Clamping its endpoints
 * before calculating image geometry would compress the entire 5 m photograph
 * into the 0.10 m viewport and distort it.
 */
export function depthToYUnclamped(
    depth: number,
    viewRange: DepthViewRange,
    bodyHeightPx = TRACK_BODY_HEIGHT_PX,
): number {
    const span = Math.max(1e-9, viewRange.max - viewRange.min);
    const t = (depth - viewRange.min) / span;
    return t * bodyHeightPx;
}
export function yToDepth(y: number, viewRange: DepthViewRange, bodyHeight = TRACK_BODY_HEIGHT_PX): number {
    const ratio = bodyHeight <= 0 ? 0 : clampValue(y / bodyHeight, 0, 1);
    return viewRange.min + (viewRange.max - viewRange.min) * ratio;
}
export function depthTicksForRange(range: DepthViewRange, count = 11): number[] {
    const safeCount = Math.max(2, count);
    const step = (range.max - range.min) / (safeCount - 1);
    return Array.from({ length: safeCount }, (_, index) => Math.round(range.min + step * index));
}
export const GLOBAL_DEPTH_LATTICE_INCREMENT = 50;

export function depthTicksForIncrement(range: DepthViewRange, increment: number): number[] {
    if (!Number.isFinite(increment) || increment <= 0) return depthTicksForRange(range);
    const start = Math.ceil(range.min / increment) * increment;
    const ticks: number[] = [];
    const maximumTicks = 2000;
    for (let depth = start; depth <= range.max + increment * 1e-6 && ticks.length < maximumTicks; depth += increment) {
        ticks.push(Number(depth.toFixed(6)));
    }
    return ticks;
}

export type AdaptiveDepthTick = { depth: number; labelled: boolean; major: boolean };

function niceDepthStepAtLeast(value: number): number {
    if (!Number.isFinite(value) || value <= 0) return 1;
    const exponent = Math.floor(Math.log10(value));
    const magnitude = 10 ** exponent;
    const normalized = value / magnitude;
    const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return nice * magnitude;
}

export function adaptiveDepthTicks(
    range: DepthViewRange,
    configuredIncrement: number,
    bodyHeightPx: number,
    minimumLabelSpacingPx = 20,
): AdaptiveDepthTick[] {
    const minorTicks = depthTicksForIncrement(range, configuredIncrement);
    const span = Math.max(1e-9, range.max - range.min);
    const minimumLabelStep = (span / Math.max(1, bodyHeightPx)) * minimumLabelSpacingPx;
    const labelStep = niceDepthStepAtLeast(Math.max(configuredIncrement, minimumLabelStep));
    const tolerance = Math.max(1e-6, configuredIncrement * 1e-6);
    return minorTicks.map((depth) => {
        const nearestMajor = Math.round(depth / labelStep) * labelStep;
        const major = Math.abs(depth - nearestMajor) <= tolerance;
        return { depth, labelled: major, major };
    });
}
export function viewDepthRangeForTrack(
    track: WellLogTrack,
    viewDepthRangesByWellUid: Record<string, DepthViewRange>,
    fallback: DepthViewRange,
): DepthViewRange {
    return track.managedWellUid ? viewDepthRangesByWellUid[track.managedWellUid] ?? fallback : fallback;
}
export function clampValue(value: number, min: number, max: number): number {
    return Math.max(min, Math.min(max, value));
}
export function clampCurveTrackWidth(width: number): number {
    return Math.round(clampValue(width, CURVE_TRACK_MIN_WIDTH, CURVE_TRACK_MAX_WIDTH));
}
export function sharedTrackHeaderHeightPx(tracks: WellLogTrack[]): number {
    const curveTracks = tracks.filter((track): track is CurveTrack => track.trackType === 'curve');
    const maxCurveRows = curveTracks.reduce(
        (maxRows, track) => Math.max(maxRows, orderedCurves(track).length),
        0,
    );
    const hasManagedWellOwnerRow = curveTracks.some((track) => Boolean(track.managedWellUid));
    const requiredCurveHeaderHeight = TRACK_HEADER_TITLE_HEIGHT_PX +
        (hasManagedWellOwnerRow ? TRACK_HEADER_WELL_OWNER_HEIGHT_PX : 0) +
        TRACK_HEADER_SUBTITLE_HEIGHT_PX +
        maxCurveRows * TRACK_CURVE_HEADER_ROW_HEIGHT_PX +
        TRACK_HEADER_BOTTOM_PADDING_PX;
    return Math.max(TRACK_HEADER_HEIGHT_PX, requiredCurveHeaderHeight);
}
export function displayTitleForTrack(track: WellLogTrack, catalog: CurveCatalogItem[]): string {
    if (track.trackType !== 'curve')
        return track.title;
    const mnemonics = orderedCurves(track)
        .map((assignment) => resolveCurveAssignmentCatalogItem(catalog, assignment)?.mnemonic ?? assignment.observedMnemonic ?? assignment.curveId)
        .map((value) => String(value || '').trim())
        .filter(Boolean);
    if (mnemonics.length === 0)
        return track.title || 'Curve Track';
    return mnemonics.join(' / ');
}
export function valueToX(value: number, assignment: CurveAssignment, lattice: CurveTrack['lattice'], trackWidth: number): number {
    const safeTrackWidth = Math.max(CURVE_TRACK_MIN_WIDTH, trackWidth);
    const drawableWidth = safeTrackWidth - CURVE_VIEW_PADDING_X * 2;
    const rawLeft = assignment.scaleMin;
    const rawRight = assignment.scaleMax;
    const scaleType = assignment.scaleType ?? (lattice === 'logarithmic' ? 'log' : 'linear');
    const clipToTrack = assignment.clipToTrack ?? true;
    const leftEndpoint = assignment.scaleDirection === 'reverse' && rawLeft < rawRight ? rawRight : rawLeft;
    const rightEndpoint = assignment.scaleDirection === 'reverse' && rawLeft < rawRight ? rawLeft : rawRight;
    let t = 0.5;
    if (scaleType === 'log' && leftEndpoint > 0 && rightEndpoint > 0 && rightEndpoint !== leftEndpoint) {
        const low = Math.min(leftEndpoint, rightEndpoint);
        const high = Math.max(leftEndpoint, rightEndpoint);
        const logLeft = Math.log10(leftEndpoint);
        const logRight = Math.log10(rightEndpoint);
        const boundedValue = clipToTrack
            ? clampValue(value, low, high)
            : Math.max(value, Number.MIN_VALUE);
        t = (Math.log10(boundedValue) - logLeft) / (logRight - logLeft);
    }
    else {
        const denominator = rightEndpoint - leftEndpoint;
        if (denominator === 0)
            return safeTrackWidth / 2;
        const boundedValue = clipToTrack
            ? clampValue(value, Math.min(leftEndpoint, rightEndpoint), Math.max(leftEndpoint, rightEndpoint))
            : value;
        t = (boundedValue - leftEndpoint) / denominator;
    }
    const anchorBias = assignment.positionAnchor === 'left'
        ? -0.18
        : assignment.positionAnchor === 'right'
            ? 0.18
            : 0;
    const offset = ((assignment.horizontalOffsetPct ?? 0) / 100) * drawableWidth;
    const scaledT = clipToTrack ? clampValue(t, 0, 1) : t;
    const x = CURVE_VIEW_PADDING_X + scaledT * drawableWidth + anchorBias * drawableWidth + offset;
    return clipToTrack
        ? clampValue(x, CURVE_VIEW_PADDING_X, safeTrackWidth - CURVE_VIEW_PADDING_X)
        : x;
}

/**
 * Return the true rendered X coordinate without pinning an off-scale value to
 * the track edge. This is intentionally separate from valueToX(), because
 * existing fill/grid callers still depend on the bounded transform.
 *
 * When "Clip to track" is enabled, curve stroke rendering uses this raw
 * coordinate and clips each segment geometrically at the scale limits. That
 * prevents consecutive off-scale samples from becoming a false vertical rail.
 */
export function valueToUnclippedCurveX(
    value: number,
    assignment: CurveAssignment,
    lattice: CurveTrack['lattice'],
    trackWidth: number,
): number {
    const safeTrackWidth = Math.max(CURVE_TRACK_MIN_WIDTH, trackWidth);
    const drawableWidth = safeTrackWidth - CURVE_VIEW_PADDING_X * 2;
    const rawLeft = assignment.scaleMin;
    const rawRight = assignment.scaleMax;
    const scaleType = assignment.scaleType ?? (lattice === 'logarithmic' ? 'log' : 'linear');
    const leftEndpoint = assignment.scaleDirection === 'reverse' && rawLeft < rawRight ? rawRight : rawLeft;
    const rightEndpoint = assignment.scaleDirection === 'reverse' && rawLeft < rawRight ? rawLeft : rawRight;
    let t = 0.5;
    if (scaleType === 'log' && leftEndpoint > 0 && rightEndpoint > 0 && rightEndpoint !== leftEndpoint) {
        if (value <= 0) return Number.NaN;
        t = (Math.log10(value) - Math.log10(leftEndpoint))
            / (Math.log10(rightEndpoint) - Math.log10(leftEndpoint));
    } else {
        const denominator = rightEndpoint - leftEndpoint;
        if (denominator === 0) return safeTrackWidth / 2;
        t = (value - leftEndpoint) / denominator;
    }
    const anchorBias = assignment.positionAnchor === 'left'
        ? -0.18
        : assignment.positionAnchor === 'right'
            ? 0.18
            : 0;
    const offset = ((assignment.horizontalOffsetPct ?? 0) / 100) * drawableWidth;
    return CURVE_VIEW_PADDING_X + t * drawableWidth + anchorBias * drawableWidth + offset;
}

export type LogGridLine = {
    value: number;
    x: number;
    major: boolean;
    powerOfTen: boolean;
};
export function nearlyEqual(a: number, b: number): boolean {
    return Math.abs(a - b) <= Math.max(1e-9, Math.abs(b) * 1e-9);
}
export function logValueToX(value: number, scaleMin: number, scaleMax: number, trackWidth: number): number {
    const safeTrackWidth = Math.max(CURVE_TRACK_MIN_WIDTH, trackWidth);
    const drawableWidth = safeTrackWidth - CURVE_VIEW_PADDING_X * 2;
    const safeValue = clampValue(value, Math.min(scaleMin, scaleMax), Math.max(scaleMin, scaleMax));
    const logMin = Math.log10(scaleMin);
    const logMax = Math.log10(scaleMax);
    const t = (Math.log10(safeValue) - logMin) / (logMax - logMin);
    return CURVE_VIEW_PADDING_X + clampValue(t, 0, 1) * drawableWidth;
}
export function logGridRangeForTrack(track: CurveTrack): {
    min: number;
    max: number;
} | null {
    const positiveAssignments = orderedCurves(track).filter((assignment) => assignment.scaleMin !== null && assignment.scaleMax !== null && assignment.scaleMin > 0 && assignment.scaleMax > 0 && assignment.scaleMin !== assignment.scaleMax);
    if (positiveAssignments.length === 0)
        return null;
    const min = Math.min(...positiveAssignments.map((assignment) => Math.min(assignment.scaleMin, assignment.scaleMax)));
    const max = Math.max(...positiveAssignments.map((assignment) => Math.max(assignment.scaleMin, assignment.scaleMax)));
    if (!Number.isFinite(min) || !Number.isFinite(max) || min <= 0 || max <= min)
        return null;
    return { min, max };
}
export function logGridMajorValues(scaleMin: number, scaleMax: number): number[] {
    const values: number[] = [];
    let value = scaleMin;
    let guard = 0;
    while (value <= scaleMax * (1 + 1e-9) && guard < 12) {
        values.push(value);
        value *= 10;
        guard += 1;
    }
    if (!values.some((candidate) => nearlyEqual(candidate, scaleMax))) {
        values.push(scaleMax);
    }
    return values;
}
export function logGridLines(scaleMin: number, scaleMax: number, trackWidth: number): LogGridLine[] {
    const majorValues = logGridMajorValues(scaleMin, scaleMax);
    const startPower = Math.floor(Math.log10(scaleMin)) - 1;
    const endPower = Math.ceil(Math.log10(scaleMax)) + 1;
    const lines = new Map<string, LogGridLine>();
    const addLine = (value: number, major: boolean, powerOfTen: boolean) => {
        if (value < scaleMin * (1 - 1e-9) || value > scaleMax * (1 + 1e-9))
            return;
        const roundedKey = value.toPrecision(12);
        const existing = lines.get(roundedKey);
        const x = logValueToX(value, scaleMin, scaleMax, trackWidth);
        lines.set(roundedKey, {
            value,
            x,
            major: major || existing?.major || false,
            powerOfTen: powerOfTen || existing?.powerOfTen || false,
        });
    };
    majorValues.forEach((value) => addLine(value, true, false));
    for (let power = startPower; power <= endPower; power += 1) {
        const decade = 10 ** power;
        for (let multiplier = 1; multiplier < 10; multiplier += 1) {
            const value = multiplier * decade;
            const isPowerOfTen = multiplier === 1;
            const isMajor = majorValues.some((majorValue) => nearlyEqual(majorValue, value));
            addLine(value, isMajor, isPowerOfTen);
        }
    }
    return [...lines.values()].sort((a, b) => a.value - b.value);
}
export function renderLogarithmicGrid(track: CurveTrack, trackWidth: number, bodyHeightPx: number) {
    const range = logGridRangeForTrack(track);
    if (!range)
        return null;
    const lines = logGridLines(range.min, range.max, trackWidth);
    return (<g className="wlv-log-grid" aria-hidden="true">
      {lines.map((line) => (<line key={`log-grid-${track.trackId}-${line.value}`} className={`wlv-log-grid-line ${line.major ? 'major' : line.powerOfTen ? 'power' : 'minor'}`} x1={line.x} x2={line.x} y1="0" y2={bodyHeightPx} vectorEffect="non-scaling-stroke"/>))}
    </g>);
}
export const PROTOTYPE_SAMPLE_ALIASES_BY_MNEMONIC: Record<string, string[]> = {
    RXO: ['RXOZ', 'RXO8'],
};
export function sampleKeysForCurve(curve: CurveCatalogItem): string[] {
    const keys = [curve.curveId, curve.mnemonic];
    const aliases = PROTOTYPE_SAMPLE_ALIASES_BY_MNEMONIC[String(curve.mnemonic || '').toUpperCase()] ?? [];
    return [...keys, ...aliases].filter((key, index, allKeys) => Boolean(key) && allKeys.indexOf(key) === index);
}
export function makeMockCurveSamples(curve: CurveCatalogItem, assignment: CurveAssignment, _trackPosition: number, managedSamplesByCurveId: ManagedCurveSamplesByCurveId): MockCurveSample[] {
    const managedSamples = resolveManagedCurveSamples(managedSamplesByCurveId, {
        managedWellUid: assignment.managedWellUid ?? null,
        curveUid: assignment.curveUid ?? null,
        curveId: assignment.curveId,
    });
    // Managed assignments never fall through to generic prototype samples.
    // Doing so would let another well's GR (or other repeated mnemonic) render
    // inside this track while its owner-qualified hydration is pending.
    const samples = managedSamples ?? (assignment.managedWellUid
        ? []
        : sampleKeysForCurve(curve)
            .map((key) => realCurveSamplesByCurveId[key])
            .find((candidate) => candidate?.length) ?? []);
    const output: MockCurveSample[] = [];
    for (const sample of samples as unknown[]) {
        let depthValue: unknown;
        let curveValue: unknown;
        if (Array.isArray(sample)) {
            depthValue = sample[0];
            curveValue = sample[1];
        }
        else if (sample && typeof sample === 'object') {
            const sampleRecord = sample as {
                depth?: unknown;
                value?: unknown;
                values?: Record<string, unknown>;
            };
            depthValue =
                sampleRecord.depth ??
                    sampleRecord.values?.DEPT ??
                    sampleRecord.values?.DEPTH ??
                    sampleRecord.values?.MD ??
                    sampleRecord.values?.TDEP;
            curveValue = sampleRecord.value ?? sampleRecord.values?.[curve.curveId] ?? sampleRecord.values?.[curve.mnemonic];
        }
        if (typeof depthValue === 'number' &&
            Number.isFinite(depthValue) &&
            typeof curveValue === 'number' &&
            Number.isFinite(curveValue)) {
            output.push({
                depth: depthValue,
                value: curveValue,
            });
        }
    }
    return output;
}
export function visibleCurveSamples(curve: CurveCatalogItem, assignment: CurveAssignment, trackPosition: number, viewRange: DepthViewRange, managedSamplesByCurveId: ManagedCurveSamplesByCurveId): MockCurveSample[] {
    const padding = Math.max(10, (viewRange.max - viewRange.min) * 0.03);
    return makeMockCurveSamples(curve, assignment, trackPosition, managedSamplesByCurveId).filter((sample) => (sample.depth >= viewRange.min - padding && sample.depth <= viewRange.max + padding));
}
export type CurveRenderPoint = {
    depth: number;
    x: number;
    y: number;
};
export function curveRenderPoints(curve: CurveCatalogItem, assignment: CurveAssignment, trackPosition: number, viewRange: DepthViewRange, lattice: CurveTrack['lattice'], trackWidth: number, bodyHeightPx: number, managedSamplesByCurveId: ManagedCurveSamplesByCurveId): CurveRenderPoint[] {
    // A well-log curve is single-valued against depth for rendering purposes.
    // Hydration/re-log payloads are not guaranteed to arrive in monotonic depth
    // order and may contain duplicate depth rows. Feeding that raw sequence into
    // one SVG polyline creates false return traces and hard rectangular bridges.
    // Normalize only the render copy; authoritative samples remain untouched.
    const samples = visibleCurveSamples(curve, assignment, trackPosition, viewRange, managedSamplesByCurveId)
        .filter((sample) => Number.isFinite(sample.depth) && Number.isFinite(sample.value))
        .sort((left, right) => left.depth - right.depth);
    const uniqueSamples: MockCurveSample[] = [];
    for (const sample of samples) {
        const previous = uniqueSamples[uniqueSamples.length - 1];
        if (previous && Math.abs(previous.depth - sample.depth) <= 1e-9) {
            // Deterministic last-value wins for duplicate depth rows. This avoids
            // drawing horizontal connectors between multiple values at one MD.
            uniqueSamples[uniqueSamples.length - 1] = sample;
        } else {
            uniqueSamples.push(sample);
        }
    }
    return uniqueSamples.map((sample) => ({
        depth: sample.depth,
        x: valueToX(sample.value, assignment, lattice, trackWidth),
        y: depthToY(sample.depth, viewRange, bodyHeightPx),
    }));
}

export function curveRenderPointsUnclipped(
    curve: CurveCatalogItem,
    assignment: CurveAssignment,
    trackPosition: number,
    viewRange: DepthViewRange,
    lattice: CurveTrack['lattice'],
    trackWidth: number,
    bodyHeightPx: number,
    managedSamplesByCurveId: ManagedCurveSamplesByCurveId,
): CurveRenderPoint[] {
    const samples = visibleCurveSamples(
        curve,
        assignment,
        trackPosition,
        viewRange,
        managedSamplesByCurveId,
    )
        .filter((sample) => Number.isFinite(sample.depth) && Number.isFinite(sample.value))
        .sort((left, right) => left.depth - right.depth);
    const uniqueSamples: MockCurveSample[] = [];
    for (const sample of samples) {
        const previous = uniqueSamples[uniqueSamples.length - 1];
        if (previous && Math.abs(previous.depth - sample.depth) <= 1e-9) {
            uniqueSamples[uniqueSamples.length - 1] = sample;
        } else {
            uniqueSamples.push(sample);
        }
    }
    return uniqueSamples
        .map((sample) => ({
            depth: sample.depth,
            x: valueToUnclippedCurveX(sample.value, assignment, lattice, trackWidth),
            y: depthToY(sample.depth, viewRange, bodyHeightPx),
        }))
        .filter((point) => Number.isFinite(point.x));
}

function interpolateCurveRenderPoint(
    left: CurveRenderPoint,
    right: CurveRenderPoint,
    t: number,
): CurveRenderPoint {
    return {
        depth: left.depth + (right.depth - left.depth) * t,
        x: left.x + (right.x - left.x) * t,
        y: left.y + (right.y - left.y) * t,
    };
}

function clipCurveSegmentToXBounds(
    left: CurveRenderPoint,
    right: CurveRenderPoint,
    minimumX: number,
    maximumX: number,
): [CurveRenderPoint, CurveRenderPoint] | null {
    const minX = Math.min(minimumX, maximumX);
    const maxX = Math.max(minimumX, maximumX);
    const dx = right.x - left.x;
    let t0 = 0;
    let t1 = 1;

    if (Math.abs(dx) <= 1e-12) {
        if (left.x < minX || left.x > maxX) return null;
    } else {
        const atMin = (minX - left.x) / dx;
        const atMax = (maxX - left.x) / dx;
        const entering = Math.min(atMin, atMax);
        const leaving = Math.max(atMin, atMax);
        t0 = Math.max(t0, entering);
        t1 = Math.min(t1, leaving);
        if (t0 > t1) return null;
    }

    return [
        interpolateCurveRenderPoint(left, right, t0),
        interpolateCurveRenderPoint(left, right, t1),
    ];
}

function curveRenderGapThreshold(points: CurveRenderPoint[]): number {
    const spacings = points
        .slice(1)
        .map((point, index) => point.depth - points[index].depth)
        .filter((spacing) => Number.isFinite(spacing) && spacing > 0)
        .sort((left, right) => left - right);
    const medianSpacing = spacings.length > 0
        ? spacings[Math.floor(spacings.length / 2)]
        : 0;
    return Math.max(1, medianSpacing * 20);
}

/**
 * Build a path by clipping each true curve segment against the scale window.
 *
 * Both points outside on the same side -> no stroke.
 * Inside -> outside -> stroke ends at the exact edge intersection.
 * Outside -> inside -> stroke resumes at the exact edge intersection.
 * Outside left -> outside right -> only the crossing section is drawn.
 *
 * A fully outside run explicitly breaks the SVG subpath, so the renderer never
 * joins exit/re-entry points with a vertical edge-riding segment.
 */
export function pathFromGeometricallyClippedCurvePoints(
    points: CurveRenderPoint[],
    minimumX: number,
    maximumX: number,
): string {
    if (points.length < 2) return '';
    const gapThreshold = curveRenderGapThreshold(points);
    const commands: string[] = [];
    let previousEnd: CurveRenderPoint | null = null;
    let penDown = false;

    for (let index = 1; index < points.length; index += 1) {
        const left = points[index - 1];
        const right = points[index];
        const depthGap = right.depth - left.depth;
        if (
            !Number.isFinite(depthGap)
            || depthGap <= 0
            || depthGap > gapThreshold
        ) {
            penDown = false;
            previousEnd = null;
            continue;
        }

        const clipped = clipCurveSegmentToXBounds(
            left,
            right,
            minimumX,
            maximumX,
        );
        if (!clipped) {
            penDown = false;
            previousEnd = null;
            continue;
        }

        const [start, end] = clipped;
        const continuesPrevious =
            penDown
            && previousEnd !== null
            && Math.abs(previousEnd.x - start.x) <= 1e-6
            && Math.abs(previousEnd.y - start.y) <= 1e-6;

        if (!continuesPrevious) {
            commands.push(`M${start.x.toFixed(1)} ${start.y.toFixed(1)}`);
        }
        commands.push(`L${end.x.toFixed(1)} ${end.y.toFixed(1)}`);
        previousEnd = end;
        penDown = true;
    }

    return commands.join(' ');
}

export function pathFromCurvePoints(points: CurveRenderPoint[]): string {
    if (points.length === 0) return '';
    if (points.length === 1) return `M${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;

    const spacings = points
        .slice(1)
        .map((point, index) => point.depth - points[index].depth)
        .filter((spacing) => Number.isFinite(spacing) && spacing > 0)
        .sort((left, right) => left - right);
    const medianSpacing = spacings.length > 0
        ? spacings[Math.floor(spacings.length / 2)]
        : 0;
    // Never bridge a genuine sampling gap. 20x the normal sample spacing is
    // deliberately conservative; the 1 m floor prevents hypersensitive breaks
    // on very dense curves.
    const gapThreshold = Math.max(1, medianSpacing * 20);

    return points.map((point, index) => {
        const previous = index > 0 ? points[index - 1] : null;
        const startsSegment = index === 0
            || !previous
            || point.depth <= previous.depth
            || (point.depth - previous.depth) > gapThreshold;
        return `${startsSegment ? 'M' : 'L'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    }).join(' ');
}
export function polygonToAnchor(points: CurveRenderPoint[], anchorX: number): string {
    if (points.length < 2)
        return '';
    const first = points[0];
    const last = points[points.length - 1];
    return `${pathFromCurvePoints(points)} L ${anchorX.toFixed(1)} ${last.y.toFixed(1)} L ${anchorX.toFixed(1)} ${first.y.toFixed(1)} Z`;
}
export function polygonThresholdToAnchor(
    points: CurveRenderPoint[],
    thresholdX: number,
    fillAnchorX: number,
    comparison: string | null | undefined,
    scaleDirection: string | null | undefined,
): string {
    if (points.length < 2) return '';
    const reverse = scaleDirection === 'reverse';
    const greaterThan = comparison !== 'less_than';
    const qualifies = (x: number): boolean =>
        greaterThan ? (reverse ? x < thresholdX : x > thresholdX) : (reverse ? x > thresholdX : x < thresholdX);
    const crossing = (left: CurveRenderPoint, right: CurveRenderPoint): CurveRenderPoint => {
        const dx = right.x - left.x;
        const t = Math.abs(dx) <= 1e-12 ? 0 : (thresholdX - left.x) / dx;
        const clamped = Math.max(0, Math.min(1, t));
        return {
            depth: left.depth + (right.depth - left.depth) * clamped,
            x: thresholdX,
            y: left.y + (right.y - left.y) * clamped,
        };
    };
    const segments: CurveRenderPoint[][] = [];
    let current: CurveRenderPoint[] = [];
    for (let index = 0; index < points.length - 1; index += 1) {
        const left = points[index];
        const right = points[index + 1];
        const leftIn = qualifies(left.x);
        const rightIn = qualifies(right.x);
        if (leftIn && current.length === 0) current.push(left);
        if (leftIn && rightIn) {
            current.push(right);
            continue;
        }
        if (leftIn && !rightIn) {
            current.push(crossing(left, right));
            if (current.length >= 2) segments.push(current);
            current = [];
            continue;
        }
        if (!leftIn && rightIn) current = [crossing(left, right), right];
    }
    if (current.length >= 2) segments.push(current);
    return segments.map((segment) => polygonToAnchor(segment, fillAnchorX)).filter(Boolean).join(' ');
}
export function interpolatePointAtDepth(points: CurveRenderPoint[], depth: number): CurveRenderPoint | null {
    if (points.length === 0)
        return null;
    for (let index = 1; index < points.length; index += 1) {
        const previous = points[index - 1];
        const current = points[index];
        const minDepth = Math.min(previous.depth, current.depth);
        const maxDepth = Math.max(previous.depth, current.depth);
        if (depth >= minDepth && depth <= maxDepth) {
            const denominator = current.depth - previous.depth;
            const t = denominator === 0 ? 0 : (depth - previous.depth) / denominator;
            return {
                depth,
                x: previous.x + (current.x - previous.x) * t,
                y: previous.y + (current.y - previous.y) * t,
            };
        }
    }
    const nearest = points.reduce((best, point) => (Math.abs(point.depth - depth) < Math.abs(best.depth - depth) ? point : best), points[0]);
    return Math.abs(nearest.depth - depth) <= 1 ? nearest : null;
}
export function polygonBetweenCurves(primaryPoints: CurveRenderPoint[], pairedPoints: CurveRenderPoint[]): string {
    if (primaryPoints.length < 2 || pairedPoints.length < 2)
        return '';

    const pairedSorted = [...pairedPoints].sort((left, right) => left.depth - right.depth);
    const primarySorted = [...primaryPoints].sort((left, right) => left.depth - right.depth);
    const pairedMinimumDepth = pairedSorted[0].depth;
    const pairedMaximumDepth = pairedSorted[pairedSorted.length - 1].depth;
    const primarySpacings = primarySorted
        .slice(1)
        .map((point, index) => Math.abs(point.depth - primarySorted[index].depth))
        .filter((spacing) => Number.isFinite(spacing) && spacing > 0)
        .sort((left, right) => left - right);
    const medianSpacing = primarySpacings.length > 0
        ? primarySpacings[Math.floor(primarySpacings.length / 2)]
        : 0;
    const maximumContinuousGap = medianSpacing > 0 ? medianSpacing * 4 : Number.POSITIVE_INFINITY;

    const segments: Array<Array<{ primary: CurveRenderPoint; paired: CurveRenderPoint }>> = [];
    let current: Array<{ primary: CurveRenderPoint; paired: CurveRenderPoint }> = [];

    for (const primary of primarySorted) {
        const outsidePairedDomain = primary.depth < pairedMinimumDepth || primary.depth > pairedMaximumDepth;
        const paired = outsidePairedDomain ? null : interpolatePointAtDepth(pairedSorted, primary.depth);
        const previous = current[current.length - 1];
        const depthGap = previous ? Math.abs(primary.depth - previous.primary.depth) : 0;
        if (!paired || depthGap > maximumContinuousGap) {
            if (current.length >= 2) segments.push(current);
            current = [];
        }
        if (paired) current.push({ primary, paired });
    }
    if (current.length >= 2) segments.push(current);

    return segments.map((segment) => {
        const primaryPath = pathFromCurvePoints(segment.map((pair) => pair.primary));
        const pairedPath = [...segment]
            .reverse()
            .map((pair) => `L${pair.paired.x.toFixed(1)} ${pair.paired.y.toFixed(1)}`)
            .join(' ');
        return `${primaryPath} ${pairedPath} Z`;
    }).join(' ');
}

export function polygonToExtremeCurveAnchor(
    primaryPoints: CurveRenderPoint[],
    pairedPoints: CurveRenderPoint[],
    anchorX: number,
    extreme: 'leftmost' | 'rightmost',
): string {
    if (primaryPoints.length < 2 || pairedPoints.length < 2)
        return '';

    const primarySorted = [...primaryPoints].sort((left, right) => left.depth - right.depth);
    const pairedSorted = [...pairedPoints].sort((left, right) => left.depth - right.depth);
    const minimumDepth = Math.max(primarySorted[0].depth, pairedSorted[0].depth);
    const maximumDepth = Math.min(
        primarySorted[primarySorted.length - 1].depth,
        pairedSorted[pairedSorted.length - 1].depth,
    );
    if (minimumDepth >= maximumDepth)
        return '';

    const depths = Array.from(new Set([
        ...primarySorted.map((point) => point.depth),
        ...pairedSorted.map((point) => point.depth),
    ])).filter((depth) => depth >= minimumDepth && depth <= maximumDepth)
      .sort((left, right) => left - right);

    const primarySpacings = primarySorted
        .slice(1)
        .map((point, index) => Math.abs(point.depth - primarySorted[index].depth))
        .filter((spacing) => Number.isFinite(spacing) && spacing > 0)
        .sort((left, right) => left - right);
    const pairedSpacings = pairedSorted
        .slice(1)
        .map((point, index) => Math.abs(point.depth - pairedSorted[index].depth))
        .filter((spacing) => Number.isFinite(spacing) && spacing > 0)
        .sort((left, right) => left - right);
    const spacingCandidates = [...primarySpacings, ...pairedSpacings].sort((left, right) => left - right);
    const medianSpacing = spacingCandidates.length > 0
        ? spacingCandidates[Math.floor(spacingCandidates.length / 2)]
        : 0;
    const maximumContinuousGap = medianSpacing > 0 ? medianSpacing * 4 : Number.POSITIVE_INFINITY;

    const segments: CurveRenderPoint[][] = [];
    let current: CurveRenderPoint[] = [];
    let previousDepth: number | null = null;

    for (const depth of depths) {
        const primary = interpolatePointAtDepth(primarySorted, depth);
        const paired = interpolatePointAtDepth(pairedSorted, depth);
        const depthGap = previousDepth == null ? 0 : Math.abs(depth - previousDepth);
        if (!primary || !paired || depthGap > maximumContinuousGap) {
            if (current.length >= 2)
                segments.push(current);
            current = [];
            previousDepth = null;
        }
        if (!primary || !paired)
            continue;
        current.push({
            depth,
            x: extreme === 'leftmost'
                ? Math.min(primary.x, paired.x)
                : Math.max(primary.x, paired.x),
            y: primary.y,
        });
        previousDepth = depth;
    }
    if (current.length >= 2)
        segments.push(current);

    return segments.map((segment) => polygonToAnchor(segment, anchorX)).filter(Boolean).join(' ');
}

export function fillAnchorForAssignment(assignment: CurveAssignment, trackWidth: number): number {
    if (assignment.fillSide === 'left')
        return CURVE_VIEW_PADDING_X;
    if (assignment.fillSide === 'right')
        return trackWidth - CURVE_VIEW_PADDING_X;
    return trackWidth / 2;
}
export function svgFillForAssignment(assignment: CurveAssignment, intervalColor: string | null, trackId: string): string {
    if (assignment.infillSource === 'interval-column' && intervalColor)
        return intervalColor;
    if (assignment.infillSource === 'pattern') {
        if (assignment.infillPattern === 'dots')
            return `url(#infill-dots-${trackId})`;
        if (assignment.infillPattern === 'hatch')
            return `url(#infill-hatch-${trackId})`;
    }
    return assignment.fillColor;
}
export function fillOpacityForAssignment(assignment: CurveAssignment): number {
    return clampValue((assignment.fillOpacity ?? 55) / 100, 0.1, 1);
}
export function curvePriorityWeight(assignment: CurveAssignment): number {
    if (assignment.displayPriority === 'back')
        return 0;
    if (assignment.displayPriority === 'front')
        return 2;
    return 1;
}
export function lineOpacityForAssignment(assignment: CurveAssignment): number {
    const baseOpacity = assignment.visible ? 1 : 0.2;
    return baseOpacity * clampValue((assignment.lineOpacity ?? 100) / 100, 0, 1);
}
export function serialiseCurveDrag(payload: DragCurvePayload): string {
    return JSON.stringify(payload);
}
export function lithologyPattern(unit: string): string {
    switch (unit) {
        case 'QTs':
            return 'radial-gradient(rgba(80, 55, 20, 0.16) 18%, transparent 19%) 0 0 / 8px 8px';
        case 'Tba':
            return 'repeating-linear-gradient(135deg, rgba(32, 74, 44, 0.20) 0 4px, transparent 4px 9px)';
        case 'Trd':
            return 'repeating-linear-gradient(45deg, rgba(95, 50, 98, 0.18) 0 3px, transparent 3px 8px), repeating-linear-gradient(-45deg, rgba(95, 50, 98, 0.10) 0 3px, transparent 3px 8px)';
        case 'Mza':
            return 'repeating-linear-gradient(135deg, rgba(20, 63, 50, 0.26) 0 5px, transparent 5px 10px)';
        case 'Mzr':
            return 'repeating-linear-gradient(0deg, rgba(86, 61, 130, 0.15) 0 2px, transparent 2px 7px), repeating-linear-gradient(90deg, rgba(86, 61, 130, 0.10) 0 2px, transparent 2px 9px)';
        case 'Mzp':
            return 'repeating-linear-gradient(0deg, rgba(56, 76, 104, 0.22) 0 2px, transparent 2px 6px)';
        case 'Mzq':
            return 'repeating-linear-gradient(90deg, rgba(130, 112, 40, 0.18) 0 3px, transparent 3px 11px), repeating-linear-gradient(0deg, rgba(130, 112, 40, 0.12) 0 3px, transparent 3px 11px)';
        default:
            return 'none';
    }
}
export type CurveInventoryTab = 'all' | 'selected' | 'aliases';
export type WdvWorkspaceLoadedWell = {
    managed_well_id: string;
    managed_well_uid: string;
    well_name: string;
    loaded_product_ids: string[];
    loaded_product_count: number;
    viewer_curve_count: number;
    displayable_curve_count: number;
    loaded_curve_count: number;
    viewer_package_endpoint?: string | null;
};
export type CurveInventoryWellContext = {
    managedWellId: string;
    wellName: string;
};

export type FormationTopMarker = {
    markerId: string;
    datasetId: string;
    datasetLabel: string;
    group: string;
    markerName: string;
    markerType: string;
    md: number;
    pickStatus: string;
};

export type FormationTopDataset = {
    datasetId: string;
    datasetLabel: string;
    status: string;
    markers: FormationTopMarker[];
};


type FormationTopTieMatchStatus = 'Exact' | 'Suggested' | 'Choose';
type FormationTopTieRow = {
    markerA: FormationTopMarker;
    suggestedMarkerB: FormationTopMarker | null;
    score: number;
    status: FormationTopTieMatchStatus;
};

function normalizeFormationTopTieName(value: string): string {
    return value
        .toLowerCase()
        .replace(/[_\-./]+/g, ' ')
        .replace(/\b(formation|fm|top|marker)\b/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function formationTopTieSimilarity(leftName: string, rightName: string): number {
    const left = normalizeFormationTopTieName(leftName);
    const right = normalizeFormationTopTieName(rightName);
    if (!left || !right) return 0;
    if (left === right) return 1;
    if ((left.includes(right) || right.includes(left)) && Math.min(left.length, right.length) >= 4) return 0.86;
    const leftTokens = new Set(left.split(' ').filter(Boolean));
    const rightTokens = new Set(right.split(' ').filter(Boolean));
    const intersection = [...leftTokens].filter((token) => rightTokens.has(token)).length;
    const union = new Set([...leftTokens, ...rightTokens]).size;
    return union > 0 ? intersection / union : 0;
}

export type LithologyIntervalRecord = {
    intervalId: string; datasetId: string; datasetLabel: string; lithology: string;
    canonicalLithology: string; topMd: number; baseMd: number; depthUnit: string;
    depthReference: string; patternId: string; backgroundColor: string; patternColor: string;
    description: string; confidence: string;
};
export type LithologyIntervalDataset = {
    datasetId: string; datasetLabel: string; status: string; intervals: LithologyIntervalRecord[];
};

type TieInLithologyBoundaryAuthority = 'measured' | 'derived-tie-in';
type TieInLithologyBoundaryPair = {
    mdA: number;
    mdB: number;
    authorityA: TieInLithologyBoundaryAuthority;
    authorityB: TieInLithologyBoundaryAuthority;
};

function uniqueLithologyBoundaryDepths(
    intervals: LithologyIntervalRecord[],
): number[] {
    const depths = intervals.flatMap((interval) => [interval.topMd, interval.baseMd])
        .filter(Number.isFinite)
        .sort((left, right) => left - right);
    return depths.reduce<number[]>((unique, depth) => {
        const previous = unique[unique.length - 1];
        if (previous === undefined || Math.abs(previous - depth) > 1e-6) unique.push(depth);
        return unique;
    }, []);
}

function normalizeLithologyIntervalsForRendering(
    intervals: LithologyIntervalRecord[],
): LithologyIntervalRecord[] {
    const sorted = intervals
        .filter((interval) => (
            Number.isFinite(interval.topMd)
            && Number.isFinite(interval.baseMd)
            && interval.baseMd > interval.topMd
        ))
        .map((interval, sourceIndex) => ({ interval, sourceIndex }))
        .sort((left, right) => (
            left.interval.topMd - right.interval.topMd
            || left.sourceIndex - right.sourceIndex
        ));

    return sorted.map(({ interval }, index) => {
        const next = sorted[index + 1]?.interval ?? null;
        if (!next || !(next.topMd > interval.topMd + 1e-6)) return interval;

        /*
         * Display continuity invariant:
         * adjacent lithologies meet at exactly one boundary.
         *
         * - overlap: truncate the upper interval to the next top;
         * - internal gap: extend the upper interval to the next top;
         * - first top / final base are never extended.
         *
         * Presentation only: canonical measured intervals are not mutated.
         */
        return { ...interval, baseMd: next.topMd };
    });
}

function lithologyIntervalAtDepth(
    intervals: LithologyIntervalRecord[],
    depth: number,
): LithologyIntervalRecord | null {
    return intervals.find((interval) => (
        Number.isFinite(interval.topMd)
        && Number.isFinite(interval.baseMd)
        && interval.baseMd > interval.topMd
        && depth >= interval.topMd - 1e-6
        && depth < interval.baseMd - 1e-6
    )) ?? null;
}

function tieInLithologyIdentity(interval: LithologyIntervalRecord | null): string {
    if (!interval) return '';
    return (interval.canonicalLithology || interval.lithology || '')
        .trim()
        .toLowerCase()
        .replace(/\s+/g, ' ');
}

export type FormationTopOverlayLineStyle = 'solid' | 'dash' | 'dot';
export type FormationTopLabelPosition = 'left' | 'center' | 'right';
export type FormationTopFillMode = 'off' | 'interval';
export type FormationTopFillPattern = 'solid' | 'diagonal' | 'dots';
export type FormationTopFillSource = 'solid' | 'pattern' | 'raster' | 'lithology' | 'lithology-column';
export type FormationTopFillDepthExtent =
    | 'entire_track'
    | 'specified_interval'
    | 'top_boundaries';
export type FormationTopFillConstraint =
    | 'track'
    | 'left-of-curve'
    | 'right-of-curve'
    | 'between-curves'
    | 'left-of-leftmost-curves'
    | 'right-of-rightmost-curves';
export type FormationTopFillZone = {
    zoneId: string;
    enabled: boolean;
    depthExtent?: FormationTopFillDepthExtent;
    intervalFromMd?: number;
    intervalToMd?: number;
    topMarkerId?: string;
    baseMarkerId?: string;
    source: FormationTopFillSource;
    color: string;
    opacity: number;
    pattern: FormationTopFillPattern;
    patternScale?: number;
    rasterUrl?: string;
    rasterFit: 'stretch' | 'cover';
    lithologyId?: string;
    constraint: FormationTopFillConstraint;
    /** Core-only horizontal scope. Kept orthogonal to Curve constraints for rollback compatibility. */
    coreObjectOnly?: boolean;
    /** Interval-track overlay option: conform overlay polygons to saved Tie-In geometry. */
    honorTieInGeometry?: boolean;
    /** Tie-In lithology mismatch standard: center of the unresolved facies-transition band (0-100%). */
    tieInFaciesTransitionCenterPct?: number;
    /** Tie-In lithology mismatch standard: width of the unresolved facies-transition band (0-100%). */
    tieInFaciesTransitionWidthPct?: number;
    curveAId?: string;
    curveBId?: string;
};
export type FormationTopOverlayStyle = {
    displayOnTrack: boolean;
    topColor: string;
    baseColor: string;
    topWidth: number;
    baseWidth: number;
    topLineStyle: FormationTopOverlayLineStyle;
    baseLineStyle: FormationTopOverlayLineStyle;
    opacity: number;
    trackLeftInsetPct: number;
    trackRightInsetPct: number;
    showLabels: boolean;
    labelPosition: FormationTopLabelPosition;
    labelOffsetX: number;
    labelOffsetY: number;
    labelFontSize: number;
    labelTextColor: string;
    labelBackground: boolean;
    labelBackgroundColor: string;
    labelBackgroundOpacity: number;
    fillMode: FormationTopFillMode;
    fillTopMarkerId?: string;
    fillBaseMarkerId?: string;
    fillSource: FormationTopFillSource;
    fillColor: string;
    fillOpacity: number;
    fillPattern: FormationTopFillPattern;
    fillRasterUrl?: string;
    fillRasterFit: 'stretch' | 'cover';
    fillConstraint: FormationTopFillConstraint;
    fillCurveAId?: string;
    fillCurveBId?: string;
    fillZones: FormationTopFillZone[];
};
export const DEFAULT_FORMATION_TOP_OVERLAY_STYLE: FormationTopOverlayStyle = {
    displayOnTrack: true,
    topColor: '#f5b93f',
    baseColor: '#ff975c',
    topWidth: 1,
    baseWidth: 2,
    topLineStyle: 'dash',
    baseLineStyle: 'dash',
    opacity: 0.92,
    trackLeftInsetPct: 0,
    trackRightInsetPct: 0,
    showLabels: true,
    labelPosition: 'left',
    labelOffsetX: 8,
    labelOffsetY: -17,
    labelFontSize: 10,
    labelTextColor: '#f2d89b',
    labelBackground: true,
    labelBackgroundColor: '#0f1216',
    labelBackgroundOpacity: 0.9,
    fillMode: 'off',
    fillTopMarkerId: undefined,
    fillBaseMarkerId: undefined,
    fillSource: 'solid',
    fillColor: '#f5b93f',
    fillOpacity: 0.12,
    fillPattern: 'solid',
    fillRasterUrl: undefined,
    fillRasterFit: 'stretch',
    fillConstraint: 'track',
    fillCurveAId: undefined,
    fillCurveBId: undefined,
    fillZones: [],
};

type InventorySectionExpansionState = {
    well: boolean;
    las: boolean;
    curve: boolean;
    formationTops: boolean;
    logImage: boolean;
    coreImage: boolean;
    completion: boolean;
};

// Runtime-only state: survives WDV component remounts and canvas/session changes,
// but resets when the frontend application is restarted or reloaded.
const inventorySectionExpansionState: InventorySectionExpansionState = {
    well: false,
    las: false,
    curve: false,
    formationTops: false,
    logImage: false,
    coreImage: false,
    completion: false,
};
export function CurveInventory({ availableCurves, curveUsageCounts, visibleTrackCurveIds, selectedTrackCurveIds, selectedCurveIds, assignmentEnabled, preferredInventoryTab, loadedWells, activeWell, curveRunMetadata, lasSources, selectedLasSourceId, lasPending, lasIncludeReviewRequired, lasMessage, onLasSourceChange, onLasIncludeReviewRequiredChange, onAddCompleteLas, formationTopDatasets, selectedFormationTopIds, lithologyIntervalDatasets, selectedLithologyIntervalIds, onToggleLithologyInterval, onToggleAllLithologyIntervals, onToggleFormationTop, onToggleAllFormationTops, coreImageItems, selectedCoreImageIds, onToggleCoreImage, onToggleAllCoreImages, completionComponents, selectedCompletionComponentIds, onToggleCompletionComponent, onToggleAllCompletionComponents, logImageSources, selectedLogImageSourceId, onLogImageSourceChange, onActiveWellChange, onSelectCurve, onToggleCurveInSelectedTrack, }: {
    availableCurves: CurveCatalogItem[];
    curveUsageCounts: Map<string, number>;
    visibleTrackCurveIds: Set<string>;
    selectedTrackCurveIds: Set<string>;
    selectedCurveIds: Set<string>;
    assignmentEnabled: boolean;
    preferredInventoryTab: CurveInventoryTab;
    loadedWells: WdvWorkspaceLoadedWell[];
    activeWell: CurveInventoryWellContext | null;
    curveRunMetadata: Map<string, {
        runInterval?: string | null;
        runNumber?: string | null;
    }>;
    lasSources: Array<{ sourceId: string; label: string; curveCount: number; assetAvailable?: boolean }>;
    selectedLasSourceId: string;
    lasPending: boolean;
    lasIncludeReviewRequired: boolean;
    lasMessage: string | null;
    onLasSourceChange: (sourceId: string) => void;
    onLasIncludeReviewRequiredChange: (checked: boolean) => void;
    onAddCompleteLas: () => void;
    formationTopDatasets: FormationTopDataset[];
    selectedFormationTopIds: Set<string>;
    lithologyIntervalDatasets: LithologyIntervalDataset[];
    selectedLithologyIntervalIds: Set<string>;
    onToggleLithologyInterval: (intervalId: string, checked: boolean) => void;
    onToggleAllLithologyIntervals: (datasetId: string, checked: boolean) => void;
    onToggleFormationTop: (markerId: string, checked: boolean) => void;
    onToggleAllFormationTops: (datasetId: string, checked: boolean) => void;
    coreImageItems: CoreImageInventoryItem[];
    selectedCoreImageIds: Set<string>;
    onToggleCoreImage: (productId: string, checked: boolean) => void;
    onToggleAllCoreImages: (checked: boolean) => void;
    completionComponents: CompletionComponentRecord[];
    selectedCompletionComponentIds: Set<string>;
    onToggleCompletionComponent: (componentId: string, checked: boolean) => void;
    onToggleAllCompletionComponents: (checked: boolean) => void;
    logImageSources: Array<{ sourceId: string; label: string; fileFormat?: string | null }>;
    selectedLogImageSourceId: string;
    onLogImageSourceChange: (sourceId: string) => void;
    onActiveWellChange: (managedWellId: string) => void;
    onSelectCurve: (curveId: string) => void;
    onToggleCurveInSelectedTrack: (curveId: string, checked: boolean) => void;
}) {
    const [activeInventoryTab, setActiveInventoryTab] = useState<CurveInventoryTab>(preferredInventoryTab);
    const [wellSectionExpanded, setWellSectionExpanded] = useState(() => inventorySectionExpansionState.well);
    const [lasSectionExpanded, setLasSectionExpanded] = useState(() => inventorySectionExpansionState.las);
    const [curveSectionExpanded, setCurveSectionExpanded] = useState(() => inventorySectionExpansionState.curve);
    const [formationTopsSectionExpanded, setFormationTopsSectionExpanded] = useState(() => inventorySectionExpansionState.formationTops);
    const [lithologySectionExpanded, setLithologySectionExpanded] = useState(false);
    const [logImageSectionExpanded, setLogImageSectionExpanded] = useState(() => inventorySectionExpansionState.logImage);
    const [coreImageSectionExpanded, setCoreImageSectionExpanded] = useState(() => inventorySectionExpansionState.coreImage);
    const [completionSectionExpanded, setCompletionSectionExpanded] = useState(() => inventorySectionExpansionState.completion);
    useEffect(() => {
        setActiveInventoryTab(preferredInventoryTab);
    }, [preferredInventoryTab]);
    useEffect(() => {
        inventorySectionExpansionState.well = wellSectionExpanded;
    }, [wellSectionExpanded]);
    useEffect(() => {
        inventorySectionExpansionState.las = lasSectionExpanded;
    }, [lasSectionExpanded]);
    useEffect(() => {
        inventorySectionExpansionState.curve = curveSectionExpanded;
    }, [curveSectionExpanded]);
    useEffect(() => {
        inventorySectionExpansionState.logImage = logImageSectionExpanded;
    }, [logImageSectionExpanded]);
    useEffect(() => {
        inventorySectionExpansionState.coreImage = coreImageSectionExpanded;
    }, [coreImageSectionExpanded]);
    useEffect(() => {
        inventorySectionExpansionState.completion = completionSectionExpanded;
    }, [completionSectionExpanded]);
    const displayedCurves = useMemo(
        () => curveInventoryRowsForTab(activeInventoryTab, availableCurves, visibleTrackCurveIds),
        [activeInventoryTab, availableCurves, visibleTrackCurveIds],
    );
    const groups = useMemo(
        () => Array.from(new Set(displayedCurves.map((curve) => curve.backendCurveFamily || 'Unclassified'))),
        [displayedCurves],
    );
    const curvesByGroupAndMnemonic = useMemo(() => {
        const grouped = new Map<string, Map<string, CurveCatalogItem[]>>();
        displayedCurves.forEach((curve) => {
            const classKey = curve.backendCurveFamily || 'Unclassified';
            const mnemonicKey = curve.mnemonic || curve.curveId;
            const classGroup = grouped.get(classKey) ?? new Map<string, CurveCatalogItem[]>();
            const mnemonicGroup = classGroup.get(mnemonicKey) ?? [];
            mnemonicGroup.push(curve);
            mnemonicGroup.sort((left, right) => {
                const leftDescription = `${left.description || ''} ${left.unit || ''}`;
                const rightDescription = `${right.description || ''} ${right.unit || ''}`;
                return leftDescription.localeCompare(rightDescription);
            });
            classGroup.set(mnemonicKey, mnemonicGroup);
            grouped.set(classKey, classGroup);
        });
        return grouped;
    }, [displayedCurves]);
    const selectedCurveCount = useMemo(() => availableCurves.filter((curve) => visibleTrackCurveIds.has(curveInventoryIdentityKey(curve))).length, [availableCurves, visibleTrackCurveIds]);
    const loadedProductCount = useMemo(() => Array.from(curveUsageCounts.values()).reduce((total, count) => total + count, 0), [curveUsageCounts]);
    const inventoryCount = loadedProductCount;
    const renderCurveRow = (curve: CurveCatalogItem, options?: {
        duplicateInstance?: boolean;
    }) => {
        const curveIdentityKey = curveInventoryIdentityKey(curve);
        const usageCount = curveUsageCounts.get(curveInventoryIdentityKey(curve)) ?? 0;
        const usedAnywhere = visibleTrackCurveIds.has(curveIdentityKey);
        const checkedInSelectedTrack = selectedTrackCurveIds.has(curveIdentityKey);
        const highlightAsSelected = activeInventoryTab === 'selected' || selectedCurveIds.has(curveIdentityKey) || usedAnywhere;
        return (<div key={curve.curveId} role="button" tabIndex={0} className={`wlv-curve-row ${options?.duplicateInstance ? 'duplicate-instance' : ''} ${usedAnywhere ? 'assigned' : ''} ${checkedInSelectedTrack ? 'checked-in-track' : ''} ${highlightAsSelected ? 'inventory-selected' : ''} ${curve.recognised ? '' : 'unrecognised'}`} draggable onClick={() => onSelectCurve(curve.curveId)} onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onSelectCurve(curve.curveId);
                }
            }} onDragStart={(event) => {
                event.dataTransfer.setData('application/json', serialiseCurveDrag({ dragType: 'curve', curveId: curve.curveId }));
                event.dataTransfer.effectAllowed = 'move';
            }}>
        <button type="button" className={`wlv-checkbox ${checkedInSelectedTrack ? 'checked' : ''}`} disabled={!assignmentEnabled} aria-label={`${checkedInSelectedTrack ? 'Remove' : 'Add'} ${curve.mnemonic} ${checkedInSelectedTrack ? 'from' : 'to'} selected track`} title={assignmentEnabled ? 'Assign/remove curve for selected track' : 'Select a curve track to assign curves'} onClick={(event) => {
                event.stopPropagation();
                if (!assignmentEnabled)
                    return;
                onToggleCurveInSelectedTrack(curve.curveId, !checkedInSelectedTrack);
            }}>
          {checkedInSelectedTrack ? '✓' : ''}
        </button>
        <strong>{curve.mnemonic}</strong>
        {activeInventoryTab === 'selected' ? (<span className="wlv-selected-curve-metadata">
            <span className="wlv-selected-curve-well" title={activeWell?.wellName ?? ''}>{activeWell?.wellName ?? 'Unknown well'}</span>
            {(curveRunMetadata.get(curveIdentityKey)?.runInterval || curveRunMetadata.get(curve.curveId)?.runInterval) && (<span className="wlv-selected-curve-interval">
                {curveRunMetadata.get(curveIdentityKey)?.runInterval || curveRunMetadata.get(curve.curveId)?.runInterval}
              </span>)}
          </span>) : (<span title={curve.description}>{curve.description}</span>)}
        <em>{curve.unit}</em>
        {activeInventoryTab !== 'all' && usageCount > 1 && <span className="wlv-curve-count" title="Curve is used in multiple tracks">{usageCount}</span>}
      </div>);
    };
    const renderLoadedMnemonicGroup = (_group: string, _mnemonic: string, curves: CurveCatalogItem[]) =>
        loadedMnemonicRows(curves).map((curve) => renderCurveRow(curve));
    const sectionHeader = (label: string, expanded: boolean, onToggle: () => void, count?: number) => (
      <button type="button" className="wlv-inventory-section-toggle" aria-expanded={expanded} onClick={onToggle}>
        <span>{label}</span>
        <span className="wlv-inventory-section-toggle-meta">{count === undefined ? '' : count}<b>{expanded ? '▾' : '▸'}</b></span>
      </button>
    );
    return (<aside className="wlv-curve-inventory">
      <div className="wlv-panel-heading">
        <h2>Well Data Inventory</h2>
      </div>
      <div className="wlv-inventory-control-stack">
        <section className="wlv-inventory-control-section">
          {sectionHeader('Well Selection', wellSectionExpanded, () => setWellSectionExpanded((value) => !value))}
          {wellSectionExpanded && (<div className="wlv-inventory-section-body">
            <select id="wlv-loaded-well-select" aria-label="Well selection" value={activeWell?.managedWellId ?? ''} disabled={loadedWells.length === 0} onChange={(event) => onActiveWellChange(event.target.value)}>
              {loadedWells.length === 0 ? (<option value="">No wells loaded</option>) : loadedWells.map((well) => (<option key={well.managed_well_id} value={well.managed_well_id}>
                  {well.well_name} · {well.displayable_curve_count}
                </option>))}
            </select>
          </div>)}
        </section>
        {lasSources.length > 0 && (<section className="wlv-inventory-control-section">
          {sectionHeader('LAS Inventory', lasSectionExpanded, () => setLasSectionExpanded((value) => !value), lasSources.length)}
          {lasSectionExpanded && (<div className="wlv-inventory-section-body">
            <div className="wlv-las-inventory-row">
              <select aria-label="LAS file selection" value={selectedLasSourceId} disabled={lasPending} onChange={(event) => onLasSourceChange(event.target.value)}>
                {lasSources.map((source) => (
                  <option key={source.sourceId} value={source.sourceId}>{source.label} · {source.curveCount + 1} channels</option>
                ))}
              </select>
              <button type="button" className="wlv-las-add-compact" disabled={lasPending || !selectedLasSourceId} onClick={onAddCompleteLas} title="Add selected LAS to the shared canvas" aria-label="Add selected LAS to canvas">
                {lasPending ? '…' : '+ LAS'}
              </button>
            </div>
            <label className="wlv-inventory-inline-toggle">
              <input type="checkbox" checked={lasIncludeReviewRequired} disabled={lasPending} onChange={(event) => onLasIncludeReviewRequiredChange(event.target.checked)}/>
              Include review-required curves
            </label>
            {lasMessage ? <div className="wlv-inventory-status">{lasMessage}</div> : null}
          </div>)}
        </section>)}
      </div>
      <section className="wlv-inventory-control-section wlv-curve-inventory-section">
        {sectionHeader('Curve Inventory', curveSectionExpanded, () => setCurveSectionExpanded((value) => !value), inventoryCount)}
        {curveSectionExpanded && (<div className="wlv-inventory-section-body wlv-curve-inventory-body">
          <div className="wlv-search-row">
            <input aria-label="Search curves" placeholder="Search curves..."/>
            <button type="button" title="Filter curves">Filter</button>
          </div>
          <div className="wlv-inventory-tabs">
            <button type="button" className={activeInventoryTab === 'all' ? 'active' : ''} onClick={() => setActiveInventoryTab('all')}>Loaded</button>
            <button type="button" className={activeInventoryTab === 'selected' ? 'active' : ''} onClick={() => setActiveInventoryTab('selected')}>Selected <span className="wlv-tab-count">{selectedCurveCount}</span></button>
            <button type="button" className={activeInventoryTab === 'aliases' ? 'active' : ''} onClick={() => setActiveInventoryTab('aliases')}>Aliases</button>
          </div>
          {activeInventoryTab === 'selected' && selectedCurveCount === 0 && (<div className="wlv-curve-assignment-hint">No curves are currently assigned to visible tracks.</div>)}
          {activeInventoryTab === 'aliases' && (<div className="wlv-curve-assignment-hint">Alias grouping is not available in this prototype fixture yet.</div>)}
          <div className="wlv-inventory-list">
            {groups.map((group) => {
                const mnemonicGroups = curvesByGroupAndMnemonic.get(group) ?? new Map<string, CurveCatalogItem[]>();
                return (<section key={group} className="wlv-curve-group">
                  <div className="wlv-curve-group-title">{group}</div>
                  {Array.from(mnemonicGroups.entries()).map(([mnemonic, curves]) => renderLoadedMnemonicGroup(group, mnemonic, curves))}
                </section>);
            })}
          </div>
        </div>)}
      </section>
      {lithologyIntervalDatasets.length > 0 && (<section className="wlv-inventory-control-section wlv-lithology-inventory">
        {sectionHeader('Lithology Intervals', lithologySectionExpanded, () => setLithologySectionExpanded((value) => !value), lithologyIntervalDatasets.length)}
        {lithologySectionExpanded && (<div className="wlv-inventory-section-body wlv-lithology-inventory-body">
          {lithologyIntervalDatasets.map((dataset) => {
            const selectedCount = dataset.intervals.filter((interval) => selectedLithologyIntervalIds.has(interval.intervalId)).length;
            const allSelected = dataset.intervals.length > 0 && selectedCount === dataset.intervals.length;
            return (<section key={dataset.datasetId} className="wlv-lithology-dataset">
              <div className="wlv-lithology-dataset-heading"><strong>{dataset.datasetLabel}</strong><span>{dataset.status} · {dataset.intervals.length} intervals</span></div>
              <label className="wlv-lithology-select-all"><input type="checkbox" checked={allSelected} onChange={(event) => onToggleAllLithologyIntervals(dataset.datasetId, event.target.checked)} /> Display all</label>
              <div className="wlv-lithology-interval-list">{dataset.intervals.map((interval) => {
                const patternUrl = interval.patternId ? lithologyPatternUrl(interval.patternId) : '';
                return (<label key={interval.intervalId} className="wlv-lithology-interval-option">
                  <input type="checkbox" checked={selectedLithologyIntervalIds.has(interval.intervalId)} onChange={(event) => onToggleLithologyInterval(interval.intervalId, event.target.checked)} />
                  <span className="wlv-lithology-inventory-swatch" style={{ backgroundImage: patternUrl ? `url("${patternUrl}")` : undefined }} />
                  <span><strong>{interval.lithology}</strong><small>{interval.topMd.toLocaleString()}–{interval.baseMd.toLocaleString()} {interval.depthUnit} · {interval.confidence || 'unrated'}</small></span>
                </label>);
              })}</div>
            </section>);
          })}
        </div>)}
      </section>)}

      {(<section className="wlv-inventory-control-section wlv-core-image-inventory">
        {sectionHeader('Core Image Inventory', coreImageSectionExpanded, () => setCoreImageSectionExpanded((value) => !value), coreImageItems.length)}
        {coreImageSectionExpanded && (<div className="wlv-inventory-section-body wlv-core-image-inventory-body">
          <label className="wlv-core-image-select-all">
            <input
              type="checkbox"
              checked={coreImageItems.length > 0 && coreImageItems.every((item) => selectedCoreImageIds.has(item.productId))}
              onChange={(event) => onToggleAllCoreImages(event.target.checked)}
            />
            <span>Display all</span>
          </label>
          <div className="wlv-core-image-list">
            {coreImageItems.map((item) => (
              <label key={item.productId} className="wlv-core-image-row">
                <input type="checkbox" checked={selectedCoreImageIds.has(item.productId)} onChange={(event) => onToggleCoreImage(item.productId, event.target.checked)}/>
                <span className="wlv-core-image-row-text">
                  <strong>{item.label}</strong>
                  <small>{item.topMd.toLocaleString()}–{item.baseMd.toLocaleString()} {item.depthUnit} MD · {item.imageType} · {item.descriptionCount} description{item.descriptionCount === 1 ? '' : 's'}</small>
                </span>
              </label>
            ))}
          </div>
        </div>)}
      </section>)}
      {completionComponents.length > 0 && (<section className="wlv-inventory-control-section wlv-completion-inventory">
        {sectionHeader('Completion Components', completionSectionExpanded, () => setCompletionSectionExpanded((value) => !value), completionComponents.length)}
        {completionSectionExpanded && (<div className="wlv-inventory-section-body wlv-completion-inventory-body">
          <label className="wlv-core-image-select-all">
            <input
              type="checkbox"
              checked={completionComponents.length > 0 && completionComponents.every((item) => selectedCompletionComponentIds.has(item.componentId))}
              onChange={(event) => onToggleAllCompletionComponents(event.target.checked)}
            />
            <span>Display all</span>
          </label>
          <div className="wlv-core-image-list">
            {completionComponents.map((item) => (
              <label key={item.componentId} className="wlv-core-image-row">
                <input
                  type="checkbox"
                  checked={selectedCompletionComponentIds.has(item.componentId)}
                  onChange={(event) => onToggleCompletionComponent(item.componentId, event.target.checked)}
                />
                <span className="wlv-core-image-row-text">
                  <strong>{item.label}</strong>
                  <small>
                    {item.topMd.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                    {item.baseMd !== null ? `–${item.baseMd.toLocaleString(undefined, { maximumFractionDigits: 1 })}` : ''}
                    {' '}{item.depthUnit} MD · {item.canonicalId.replace('completion.', '').replace(/_/g, ' ')}
                  </small>
                </span>
              </label>
            ))}
          </div>
        </div>)}
      </section>)}
      {formationTopDatasets.length > 0 && (<section className="wlv-inventory-control-section wlv-formation-tops-inventory">
        {sectionHeader('Formation Tops Inventory', formationTopsSectionExpanded, () => setFormationTopsSectionExpanded((value) => !value), formationTopDatasets.length)}
        {formationTopsSectionExpanded && (<div className="wlv-inventory-section-body wlv-formation-tops-inventory-body">
          {formationTopDatasets.map((dataset) => {
            const selectedCount = dataset.markers.filter((marker) => selectedFormationTopIds.has(marker.markerId)).length;
            const allSelected = dataset.markers.length > 0 && selectedCount === dataset.markers.length;
            const partiallySelected = selectedCount > 0 && !allSelected;
            return (<section key={dataset.datasetId} className="wlv-formation-tops-dataset">
              <div className="wlv-formation-tops-dataset-heading">
                <strong>{dataset.datasetLabel}</strong>
                <span>{dataset.status} · {dataset.markers.length} markers</span>
              </div>
              <label className="wlv-formation-top-select-all">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(node) => {
                    if (node) node.indeterminate = partiallySelected;
                  }}
                  onChange={(event) => onToggleAllFormationTops(dataset.datasetId, event.target.checked)}
                />
                <span>Select all</span>
              </label>
              <div className="wlv-formation-top-list">
                {dataset.markers.map((marker) => (
                  <label key={marker.markerId} className="wlv-formation-top-row">
                    <input
                      type="checkbox"
                      checked={selectedFormationTopIds.has(marker.markerId)}
                      onChange={(event) => onToggleFormationTop(marker.markerId, event.target.checked)}
                    />
                    <span className="wlv-formation-top-name">{marker.markerName}</span>
                    <span className="wlv-formation-top-depth">{marker.md.toLocaleString(undefined, { maximumFractionDigits: 1 })} m MD</span>
                  </label>
                ))}
              </div>
            </section>);
          })}
        </div>)}
      </section>)}
      {activeInventoryTab === 'all' && (<section className="wlv-inventory-control-section wlv-log-image-inventory">
        {sectionHeader('Log Image Inventory', logImageSectionExpanded, () => setLogImageSectionExpanded((value) => !value), logImageSources.length)}
        {logImageSectionExpanded && (<div className="wlv-inventory-section-body">
          <select aria-label="Log image selection" value={selectedLogImageSourceId} disabled={logImageSources.length === 0} onChange={(event) => onLogImageSourceChange(event.target.value)}>
            {logImageSources.length === 0 ? <option value="">No managed log images</option> : logImageSources.map((source) => (
              <option key={source.sourceId} value={source.sourceId}>{source.label}{source.fileFormat ? ` · ${source.fileFormat}` : ''}</option>
            ))}
          </select>
          <button type="button" disabled title="Original log-image track rendering is not implemented yet">Add Original Image Track</button>
        </div>)}
      </section>)}
      <div className="wlv-drop-help">LAS files, individual curves, and log images share the same WDV canvas.</div>
    </aside>);
}
export function WdvTemplateRecommendationModal({ recommendation, loadedCurveItems, managedWellId, managedWellUid, getCanonicalRevision, onClose, onApplied, }: {
    recommendation: WdvTemplateRecommendationItem;
    loadedCurveItems: WdvLoadedCurveItem[];
    managedWellId?: string | null;
    managedWellUid?: string | null;
    getCanonicalRevision: () => number;
    onClose: () => void;
    onApplied: (session: WdvCanonicalTemplateApplySession) => void;
}) {
    const [applicationPlanEnvelope, setApplicationPlanEnvelope] = useState<WdvTemplateApplicationPlanEnvelope | null>(null);
    const [applicationPlanLoading, setApplicationPlanLoading] = useState(false);
    const [applicationPlanError, setApplicationPlanError] = useState<string | null>(null);
    const [applicationApplying, setApplicationApplying] = useState(false);
    const [applicationApplyError, setApplicationApplyError] = useState<string | null>(null);
    useEffect(() => {
        let cancelled = false;
        setApplicationPlanLoading(true);
        setApplicationPlanError(null);
        setApplicationPlanEnvelope(null);
        void buildWdvTemplateApplicationPlan(recommendation.template_key, loadedCurveItems, managedWellId)
            .then((result) => {
            if (!cancelled) {
                setApplicationPlanEnvelope(result);
            }
        })
            .catch((error) => {
            if (!cancelled) {
                setApplicationPlanError(error instanceof Error ? error.message : 'Application plan service unavailable');
            }
        })
            .finally(() => {
            if (!cancelled) {
                setApplicationPlanLoading(false);
            }
        });
        return () => {
            cancelled = true;
        };
    }, [recommendation.template_key, loadedCurveItems, managedWellId]);
    const plan = applicationPlanEnvelope?.plan ?? null;
    const selectedCurves = uniqueVisibleRecommendedCurves(plan?.selected_curves ?? recommendation.selected_curves ?? []);
    const alternateCurves = uniqueVisibleRecommendedCurves(plan?.alternate_curves ?? recommendation.alternate_curves ?? []);
    const tracks = plan?.tracks ?? recommendation.tracks ?? [];
    const missingRequiredFamilies = plan?.missing_required_families ?? recommendation.missing_required_families ?? [];
    const missingPreferredFamilies = plan?.missing_preferred_families ?? recommendation.missing_preferred_families ?? [];
    const rendererRequirements = plan?.renderer_requirements ?? recommendation.renderer_requirements ?? [];
    const blockingIssues = plan?.blocking_issues ?? [];
    const planWarnings = plan?.warnings ?? [];
    const planStatus = plan?.plan_status ?? (applicationPlanLoading ? 'building_plan' : 'recommendation_only');
    const applyEligible = plan?.apply_eligible ?? false;
    const mutationPerformed = applicationPlanEnvelope?.mutation_performed ?? false;
    const canApply = Boolean(managedWellId && managedWellUid && plan && applyEligible && !applicationPlanLoading && !applicationApplying);
    const handleApply = () => {
        if (!managedWellId || !managedWellUid || !plan || !applyEligible)
            return;
        setApplicationApplying(true);
        setApplicationApplyError(null);
        void applyCanonicalWdvTemplate(
            managedWellUid,
            getCanonicalRevision(),
            recommendation.template_key,
            'open_hole',
        )
            .then((session) => {
            onApplied(session);
        })
            .catch((error) => {
            setApplicationApplyError(error instanceof Error ? error.message : 'Template apply service unavailable');
        })
            .finally(() => setApplicationApplying(false));
    };
    return createPortal(<div className="wlv-template-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="wlv-template-modal" role="dialog" aria-modal="true" aria-label="WDV template application plan" onMouseDown={(event) => event.stopPropagation()}>
        <header className="wlv-template-modal-header">
          <div>
            <span>Backend KR application plan</span>
            <h2>{plan?.template_label ?? recommendation.template_label}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close template application plan">×</button>
        </header>

        <div className="wlv-template-plan-banner">
          <strong>{applicationPlanLoading ? 'Building backend-owned staged plan…' : formatPlanStatus(planStatus)}</strong>
          <span>
            {applicationPlanError
            ? applicationPlanError
            : applicationApplyError
                ? applicationApplyError
                : mutationPerformed
                    ? 'Unexpected mutation reported by backend during preview.'
                    : applyEligible
                        ? 'Backend plan is applyable. Apply writes active WDV layout state.'
                        : 'Backend plan is blocked pending review; tracks are not populated.'}
          </span>
        </div>

        <div className="wlv-template-modal-summary">
          <div><strong>Template match</strong><span>{formatTemplateMatch(plan?.source_recommendation_score ?? recommendation.score)}</span></div>
          <div><strong>Plan</strong><span>{applyEligible ? 'Ready for review' : 'Review required'}</span></div>
          <div><strong>Curves</strong><span>{selectedCurves.length} selected</span></div>
          <div><strong>Missing required</strong><span>{missingRequiredFamilies.length ? missingRequiredFamilies.length : 'None'}</span></div>
        </div>

        <section className="wlv-template-modal-section">
          <h3>Backend plan status</h3>
          <dl className="wlv-template-modal-dl">
            <dt>Plan status</dt>
            <dd>{formatPlanStatus(planStatus)}</dd>
            <dt>Apply mode</dt>
            <dd>{formatPlanStatus(plan?.apply_mode ?? 'backend_apply_available_after_review')}</dd>
            <dt>Blocking issues</dt>
            <dd>{compactFamilyList(blockingIssues, 'None')}</dd>
            <dt>Warnings</dt>
            <dd>{compactFamilyList(planWarnings, 'None')}</dd>
          </dl>
        </section>

        <section className="wlv-template-modal-section">
          <h3>Coverage</h3>
          <dl className="wlv-template-modal-dl">
            <dt>Available families</dt>
            <dd>{compactFamilyList(recommendation.required_coverage?.available_families, 'No matching required families')}</dd>
            <dt>Missing required</dt>
            <dd>{compactFamilyList(missingRequiredFamilies, 'None')}</dd>
            <dt>Missing preferred</dt>
            <dd>{compactFamilyList(missingPreferredFamilies, 'None')}</dd>
            <dt>Renderers</dt>
            <dd>{compactRendererList(rendererRequirements)}</dd>
          </dl>
        </section>

        <section className="wlv-template-modal-section">
          <h3>Selected representative curves</h3>
          {selectedCurves.length > 0 ? (<div className="wlv-template-curve-list">
              {selectedCurves.slice(0, 12).map((curve, index) => (<div key={`${curve.product_id ?? curve.curve_id ?? curve.mnemonic ?? 'curve'}-${index}`} className="wlv-template-curve-row">
                  <strong>{curve.mnemonic || curve.display_name || curve.curve_id || 'Curve'}</strong>
                  <span>{curve.curve_family || curve.raw_curve_family || 'unclassified'}</span>
                  <em>{curve.selection_reason || 'backend selected'}</em>
                </div>))}
            </div>) : (<p className="wlv-template-empty-note">No representative curves selected by the backend for this template.</p>)}
        </section>

        <section className="wlv-template-modal-section">
          <h3>Alternates</h3>
          {alternateCurves.length > 0 ? (<div className="wlv-template-curve-list">
              {alternateCurves.slice(0, 8).map((curve, index) => (<div key={`${curve.product_id ?? curve.curve_id ?? curve.mnemonic ?? 'alternate'}-${index}`} className="wlv-template-curve-row">
                  <strong>{curve.mnemonic || curve.display_name || curve.curve_id || 'Curve'}</strong>
                  <span>{curve.curve_family || curve.raw_curve_family || 'unclassified'}</span>
                  <em>{curve.selection_reason || 'alternate'}</em>
                </div>))}
            </div>) : (<p className="wlv-template-empty-note">No alternate curves returned by the backend for this plan.</p>)}
        </section>

        <section className="wlv-template-modal-section">
          <h3>Track plan</h3>
          <div className="wlv-template-track-plan">
            {tracks.slice(0, 10).map((track) => (<div key={track.track_key || track.track_id || track.track_name || String(track.track_number)} className="wlv-template-track-row">
                <strong>{track.track_number ?? '—'}. {track.track_name || track.track_key || 'Track'}</strong>
                <span>{track.renderer_type || 'renderer pending'}</span>
                <small>
                  {(track.selected_curves ?? []).map((curve) => curve.mnemonic || curve.display_name || curve.curve_id).filter(Boolean).join(', ') || 'no selected curves'} · {scaleSummary(track.scale_defaults)}
                </small>
              </div>))}
          </div>
        </section>

        <footer className="wlv-template-modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="button" disabled={!canApply} onClick={handleApply} title={canApply ? 'Apply backend-owned template plan to WDV layout' : compactFamilyList(blockingIssues, 'Backend plan is not applyable yet')}>
            {applicationApplying ? 'Applying…' : 'Apply'}
          </button>
        </footer>
      </section>
    </div>, document.body);
}
export type IntervalTieInField = 'upperA' | 'upperB' | 'lowerA' | 'lowerB';
export type IntervalTieInConfig = {
  enabled:boolean;
  upperA:number|null; upperB:number|null; lowerA:number|null; lowerB:number|null;
  line:CurveLineStyleValue;
  fillEnabled:boolean;
  fillDepthExtent:'correlation'|'specified_interval'|'formation_tops';
  fillUpperA:number|null; fillUpperB:number|null; fillLowerA:number|null; fillLowerB:number|null;
  fillTopMarkerAId:string; fillTopMarkerBId:string; fillBaseMarkerAId:string; fillBaseMarkerBId:string;
  fillAppearance:'solid'|'pattern'|'raster';
  fillPattern:'diagonal'|'dots'|'kr-lithology'|'lithology-column';
  fillLithologyId:string;
  fillPatternScale:number;
  fillColor:string;
  fillOpacity:number;
  fillRasterUrl:string;
  fillRasterFit:'stretch'|'cover';
};
export type IntervalTieInLayer = IntervalTieInConfig & {
  layerId:string;
  name:string;
};
export type IntervalTieInLayerState = {
  selectedLayerId:string|null;
  layers:IntervalTieInLayer[];
};
const INTERVAL_TIE_IN_DEFAULTS:IntervalTieInConfig={
  enabled:false,
  upperA:null,upperB:null,lowerA:null,lowerB:null,
  line:{visible:true,color:'#4b5563',width:1.5,style:'solid',opacity:100},
  fillEnabled:true,fillDepthExtent:'correlation',
  fillUpperA:null,fillUpperB:null,fillLowerA:null,fillLowerB:null,
  fillTopMarkerAId:'',fillTopMarkerBId:'',fillBaseMarkerAId:'',fillBaseMarkerBId:'',
  fillAppearance:'solid',fillPattern:'diagonal',fillLithologyId:'',fillPatternScale:1,
  fillColor:'#94a3b8',fillOpacity:.25,fillRasterUrl:'',fillRasterFit:'stretch',
};
const newIntervalTieInLayer=(ordinal:number,source?:Partial<IntervalTieInConfig>):IntervalTieInLayer=>({
  ...INTERVAL_TIE_IN_DEFAULTS,
  ...(source??{}),
  line:{...INTERVAL_TIE_IN_DEFAULTS.line,...(source?.line??{})},
  layerId:`tie-in-${Date.now()}-${Math.random().toString(36).slice(2,8)}`,
  name:`Tie-in ${ordinal}`,
});
type IntervalBuilderTab=IntervalBuilderColumnKey|'tie_in';
const INTERVAL_TIE_IN_CONFIG_CHANGED_EVENT='wlv:interval-tie-in-config-changed';
const INTERVAL_TIE_IN_PREVIEW_EVENT='wlv:interval-tie-in-preview';
const INTERVAL_TIE_IN_PREVIEW_END_EVENT='wlv:interval-tie-in-preview-end';
const INTERVAL_STORAGE_COMMITTED_EVENT='wlv:interval-storage-committed';

export type IntervalBuilderColumnKey = 'formation' | 'lithology' | 'depth' | 'thickness' | 'uncertainty' | 'notes' | 'color_band' | 'descriptions';
export type IntervalBuilderColumn = { key: IntervalBuilderColumnKey; label: string; enabled: boolean; width: number; title: string };
export type IntervalFormationSourceMode = 'loaded' | 'manual';
export type IntervalFormationManualTop = { id: string; name: string; md: string; group: string };
export type IntervalFormationConfig = {
 sourceMode: IntervalFormationSourceMode;
 selectionMode: 'all' | 'selected';
 selectedMarkerIds: string[];
 manualTops: IntervalFormationManualTop[];
 showLabels: boolean;
 fontSize: number;
 fontColor: string;
 fontWeight: 'regular' | 'bold';
 labelAlignment: 'left' | 'center' | 'right';
 showBoundaryLines: boolean;
 boundaryColor: string;
 boundaryWidth: number;
 boundaryStyle: 'solid' | 'dashed' | 'dotted';
 boundaryOpacity: number;
 boundaryExtent: 'column' | 'interval_columns';
 showBoxFill: boolean;
 boxFillColor: string;
 boxFillOpacity: number;
 showBoxBorder: boolean;
 boxBorderColor: string;
 boxBorderWidth: number;
};
const INTERVAL_FORMATION_DEFAULTS: IntervalFormationConfig = {
 sourceMode:'loaded',
 selectionMode:'all',
 selectedMarkerIds:[],
 manualTops:[],
 showLabels:true,
 fontSize:11,
 fontColor:'#111827',
 fontWeight:'regular',
 labelAlignment:'center',
 showBoundaryLines:true,
 boundaryColor:'#4b5563',
 boundaryWidth:1,
 boundaryStyle:'solid',
 boundaryOpacity:100,
 boundaryExtent:'column',
 showBoxFill:true,
 boxFillColor:'#d7dce2',
 boxFillOpacity:25,
 showBoxBorder:false,
 boxBorderColor:'#6b7280',
 boxBorderWidth:1,
};

export type IntervalDescriptionType = 'core_description';

export type IntervalDescriptionDensity =
  | 'auto'
  | 'all'
  | 'sparse';

export type IntervalDescriptionConfig = {
  descriptionType: IntervalDescriptionType;
  coreProductId: string;

  showMarkerLine: boolean;
  markerColor: string;
  markerWidth: number;
  markerStyle: 'solid' | 'dashed' | 'dotted';
  markerOpacity: number;

  showMd: boolean;
  depthFontSize: number;
  depthFontColor: string;
  depthFontWeight: 'regular' | 'bold';
  depthOpacity: number;

  showText: boolean;
  fontSize: number;
  fontColor: string;
  fontWeight: 'regular' | 'bold';
  descriptionOpacity: number;
  textAlignment: 'left' | 'center' | 'right';
  wrapText: boolean;

  depthRelativeToLine: 'above' | 'on' | 'below';
  descriptionRelativeToLine: 'above' | 'on' | 'below';
  depthDescriptionOrder:
    | 'depth_before'
    | 'description_before'
    | 'depth_above'
    | 'description_above';

  depthHorizontalOffset: number;
  depthVerticalOffset: number;
  descriptionHorizontalOffset: number;
  descriptionVerticalOffset: number;

  density: IntervalDescriptionDensity;
};

const INTERVAL_DESCRIPTION_DEFAULTS: IntervalDescriptionConfig = {
  descriptionType: 'core_description',
  coreProductId: '',

  showMarkerLine: true,
  markerColor: '#66717f',
  markerWidth: 1,
  markerStyle: 'solid',
  markerOpacity: 70,

  showMd: false,
  depthFontSize: 10,
  depthFontColor: '#1e2935',
  depthFontWeight: 'regular',
  depthOpacity: 100,

  showText: true,
  fontSize: 10,
  fontColor: '#1e2935',
  fontWeight: 'regular',
  descriptionOpacity: 100,
  textAlignment: 'left',
  wrapText: true,

  depthRelativeToLine: 'on',
  descriptionRelativeToLine: 'below',
  depthDescriptionOrder: 'depth_before',

  depthHorizontalOffset: 0,
  depthVerticalOffset: 0,
  descriptionHorizontalOffset: 6,
  descriptionVerticalOffset: 0,

  density: 'auto',
};

const INTERVAL_DESCRIPTION_STORAGE_KEY_V1 =
  'wlv.intervalTrack.descriptions.v1';

const INTERVAL_DESCRIPTION_STORAGE_KEY =
  'wlv.intervalTrack.descriptions.v2';

type IntervalDescriptionPreviewDetail = {
  config: IntervalDescriptionConfig;
  column: IntervalBuilderColumn;
};

const INTERVAL_DESCRIPTION_PREVIEW_EVENT =
  'wlv:interval-description-config-preview';

const INTERVAL_DESCRIPTION_PREVIEW_END_EVENT =
  'wlv:interval-description-config-preview-end';

function loadIntervalDescriptionConfig(): IntervalDescriptionConfig {
  try {
    const raw =
      window.localStorage.getItem(
        INTERVAL_DESCRIPTION_STORAGE_KEY,
      )
      ?? window.localStorage.getItem(
        INTERVAL_DESCRIPTION_STORAGE_KEY_V1,
      );

    if (raw) {
      const parsed =
        JSON.parse(raw) as Partial<IntervalDescriptionConfig>;

      return {
        ...INTERVAL_DESCRIPTION_DEFAULTS,
        ...parsed,
        descriptionType: 'core_description',
      };
    }
  } catch {
    // Use defaults.
  }

  return { ...INTERVAL_DESCRIPTION_DEFAULTS };
}

const INTERVAL_FORMATION_STORAGE_KEY='wlv.intervalTrack.formation.v1';
function loadIntervalFormationConfig(): IntervalFormationConfig {
 try {
  const raw=window.localStorage.getItem(INTERVAL_FORMATION_STORAGE_KEY);
  if(raw){
   const parsed=JSON.parse(raw) as Partial<IntervalFormationConfig>;
   return {
    ...INTERVAL_FORMATION_DEFAULTS,
    ...parsed,
    manualTops:Array.isArray(parsed.manualTops)?parsed.manualTops:[],
    selectedMarkerIds:Array.isArray(parsed.selectedMarkerIds)?parsed.selectedMarkerIds:[],
   };
  }
 } catch{}
 return {...INTERVAL_FORMATION_DEFAULTS,manualTops:[],selectedMarkerIds:[]};
}

export type IntervalDepthReference = 'MD' | 'TVD_RT' | 'TVD_MSL';
export type IntervalDepthTieMode = 'independent' | 'boundaries';
export type IntervalDepthLineMode = 'source' | 'draw' | 'none';
export type IntervalDepthLineExtent = 'full' | 'left_tick' | 'right_tick';
export type IntervalDepthValuePosition = 'on' | 'above' | 'below';
export type IntervalDepthHorizontalPosition = 'left' | 'center' | 'right';
export type IntervalDepthLineColorMode = 'adjacent' | 'custom';
export type IntervalDepthConfig = {
 reference: IntervalDepthReference;
 decimalPlaces: 0 | 1 | 2;
 tieMode: IntervalDepthTieMode;
 tiedColumnKey: string;
 showUnitInHeader: boolean;
 showUnitBesideValues: boolean;
 lineMode: IntervalDepthLineMode;
 lineExtent: IntervalDepthLineExtent;
 lineColorMode: IntervalDepthLineColorMode;
 customLineColor: string;
 lineWidth: number;
 lineStyle: 'solid' | 'dashed' | 'dotted';
 lineOpacity: number;
 valuePosition: IntervalDepthValuePosition;
 horizontalPosition: IntervalDepthHorizontalPosition;
 valueOffset: number;
};
const INTERVAL_DEPTH_DEFAULTS: IntervalDepthConfig = {
 reference:'MD',
 decimalPlaces:1,
 tieMode:'independent',
 tiedColumnKey:'formation',
 showUnitInHeader:true,
 showUnitBesideValues:false,
 lineMode:'source',
 lineExtent:'full',
 lineColorMode:'adjacent',
 customLineColor:'#4b5563',
 lineWidth:1,
 lineStyle:'solid',
 lineOpacity:100,
 valuePosition:'on',
 horizontalPosition:'center',
 valueOffset:3,
};
const INTERVAL_DEPTH_STORAGE_KEY='wlv.intervalTrack.depth.v1';
function loadIntervalDepthConfig(): IntervalDepthConfig {
 try {
  const raw=window.localStorage.getItem(INTERVAL_DEPTH_STORAGE_KEY);
  if(raw){
   const parsed=JSON.parse(raw) as Partial<IntervalDepthConfig>;
   return {...INTERVAL_DEPTH_DEFAULTS,...parsed};
  }
 } catch{}
 return {...INTERVAL_DEPTH_DEFAULTS};
}

function loadConfiguredDescriptionColumn(): IntervalBuilderColumn {
  try {
    const raw = window.localStorage.getItem(
      INTERVAL_BUILDER_STORAGE_KEY,
    );

    if (raw) {
      const configured =
        JSON.parse(raw) as IntervalBuilderColumn[];

      const descriptionColumn = configured.find(
        column => column.key === 'descriptions',
      );

      if (descriptionColumn) return descriptionColumn;
    }
  } catch {
    // Use defaults.
  }

  return INTERVAL_BUILDER_DEFAULTS.find(
    column => column.key === 'descriptions',
  ) ?? {
    key: 'descriptions',
    label: 'Descriptions',
    enabled: true,
    width: 260,
    title: 'Core Description',
  };
}

function loadConfiguredDepthColumn(): IntervalBuilderColumn {
 try {
  const raw=window.localStorage.getItem(INTERVAL_BUILDER_STORAGE_KEY);
  if(raw){
   const configured=JSON.parse(raw) as IntervalBuilderColumn[];
   const depth=configured.find((column)=>column.key==='depth');
   if(depth)return depth;
  }
 } catch{}
 return INTERVAL_BUILDER_DEFAULTS.find((column)=>column.key==='depth') ?? {
  key:'depth',
  label:'Depth',
  enabled:true,
  width:58,
  title:'MD',
 };
}
const INTERVAL_BUILDER_DEFAULTS: IntervalBuilderColumn[] = [
 { key:'formation',label:'Formation Tops',enabled:true,width:160,title:'Formation' },
 { key:'lithology',label:'Lithology',enabled:true,width:36,title:'Lithology' },
 { key:'depth',label:'Depth',enabled:true,width:58,title:'MD' },
 { key:'thickness',label:'Thickness',enabled:false,width:52,title:'Thickness' },
 { key:'uncertainty',label:'Uncertainty',enabled:false,width:48,title:'± m' },
 { key:'notes',label:'Notes',enabled:false,width:120,title:'Notes' },
 { key:'color_band',label:'Colour Band',enabled:false,width:28,title:'Band' },
 { key:'descriptions',label:'Descriptions',enabled:false,width:260,title:'Core Description' },
];
const INTERVAL_BUILDER_STORAGE_KEY='wlv.intervalTrack.builder.v2';
type IntervalBuilderPersistedPayload={
  columns:IntervalBuilderColumn[];
  tieInByTrackId:Record<string,IntervalTieInLayerState>;
};
function normalizeIntervalTieInConfig(value:Partial<IntervalTieInConfig>|undefined):IntervalTieInConfig{
  return {...INTERVAL_TIE_IN_DEFAULTS,...(value??{}),line:{...INTERVAL_TIE_IN_DEFAULTS.line,...(value?.line??{})}};
}
function normalizeIntervalTieInLayer(
  value:(Partial<IntervalTieInLayer>&{layerId?:string;name?:string})|undefined,
  ordinal:number,
):IntervalTieInLayer{
  const config=normalizeIntervalTieInConfig(value);
  return {
    ...config,
    layerId:value?.layerId||`tie-in-migrated-${ordinal}`,
    name:(value?.name||`Tie-in ${ordinal}`).trim()||`Tie-in ${ordinal}`,
  };
}
function normalizeIntervalTieInLayerState(
  value:IntervalTieInLayerState|Partial<IntervalTieInConfig>|undefined,
):IntervalTieInLayerState{
  if(value&&typeof value==='object'&&'layers' in value&&Array.isArray(value.layers)){
    const layers=value.layers.map((layer,index)=>normalizeIntervalTieInLayer(layer,index+1));
    const selectedLayerId=
      typeof value.selectedLayerId==='string'&&layers.some(layer=>layer.layerId===value.selectedLayerId)
        ? value.selectedLayerId
        : layers[0]?.layerId??null;
    return {selectedLayerId,layers};
  }
  if(value&&typeof value==='object'){
    // Backward-compatible migration: the former single Tie-in becomes Layer 1.
    const legacy=normalizeIntervalTieInLayer({...value,layerId:'tie-in-legacy-1',name:'Tie-in 1'},1);
    return {selectedLayerId:legacy.layerId,layers:[legacy]};
  }
  return {selectedLayerId:null,layers:[]};
}
function readIntervalBuilderPersistedPayload():IntervalBuilderPersistedPayload{
  let columns=INTERVAL_BUILDER_DEFAULTS.map(column=>({...column}));
  let tieInByTrackId:Record<string,IntervalTieInLayerState>={};
  try{
    const raw=window.localStorage.getItem(INTERVAL_BUILDER_STORAGE_KEY);
    if(raw){
      const parsed=JSON.parse(raw) as IntervalBuilderColumn[]|{columns?:IntervalBuilderColumn[];tieInByTrackId?:Record<string,IntervalTieInLayerState|Partial<IntervalTieInConfig>>};
      const savedColumns=Array.isArray(parsed)?parsed:parsed.columns;
      if(Array.isArray(savedColumns)&&savedColumns.length){
        const savedByKey=new Map(savedColumns.map(column=>[column.key,column]));
        columns=INTERVAL_BUILDER_DEFAULTS.map(defaultColumn=>({...defaultColumn,...(savedByKey.get(defaultColumn.key)??{})}));
      }
      if(!Array.isArray(parsed)&&parsed.tieInByTrackId){
        tieInByTrackId=Object.fromEntries(
          Object.entries(parsed.tieInByTrackId).map(([trackId,state])=>[trackId,normalizeIntervalTieInLayerState(state)]),
        );
      }
    }
  }catch{}
  return {columns,tieInByTrackId};
}
function loadIntervalBuilderColumns():IntervalBuilderColumn[]{return readIntervalBuilderPersistedPayload().columns;}
function loadIntervalTieInByTrackId():Record<string,IntervalTieInLayerState>{return readIntervalBuilderPersistedPayload().tieInByTrackId;}
function loadIntervalTieInLayerState(trackId:string):IntervalTieInLayerState{return normalizeIntervalTieInLayerState(loadIntervalTieInByTrackId()[trackId]);}
function intervalTieInRenderableLayers(value:IntervalTieInLayerState|IntervalTieInConfig|undefined):IntervalTieInLayer[]{
  return normalizeIntervalTieInLayerState(value).layers;
}
function persistIntervalBuilderState(columns:IntervalBuilderColumn[],tieInByTrackId:Record<string,IntervalTieInLayerState>):void{
  window.localStorage.setItem(INTERVAL_BUILDER_STORAGE_KEY,JSON.stringify({columns,tieInByTrackId}));
}

export type CompletionCanonicalId =
    | 'completion.tubing'
    | 'completion.casing'
    | 'completion.liner'
    | 'completion.screen'
    | 'completion.open_hole'
    | 'completion.perforations'
    | 'completion.packer'
    | 'completion.safety_valve'
    | 'completion.downhole_valve'
    | 'completion.sliding_sleeve'
    | 'completion.gas_lift'
    | 'completion.icd_aicd'
    | 'completion.bridge_plug'
    | 'completion.retainer'
    | 'completion.cement_barrier';

export type CompletionComponentRecord = {
    componentId: string;
    datasetId: string;
    datasetLabel: string;
    canonicalId: CompletionCanonicalId;
    componentKey: string;
    krInstructionId: string | null;
    krVersion: string | null;
    label: string;
    topMd: number;
    baseMd: number | null;
    depthUnit: string;
    diameter: number | null;
    status: string | null;
    sourceDocument: string | null;
    sourceReference: string | null;
    confidence: string | null;
    notes: string | null;
};

export type AddTrackDraft = {
    trackType: ActiveTrackType;
    depthBasis: DepthBasis;
    insertMode: 'before_selected' | 'after_selected' | 'far_right';
    referenceTrackId?: string | null;
    curveSource: 'empty' | 'selected';
    latticeMode: 'auto' | 'linear' | 'logarithmic';
    scaleMode: ScaleMode;
};
export const defaultAddTrackDraft: AddTrackDraft = {
    trackType: 'curve',
    depthBasis: 'MD',
    insertMode: 'after_selected',
    referenceTrackId: null,
    curveSource: 'empty',
    latticeMode: 'auto',
    scaleMode: 'per_curve',
};
export const CORE_PHOTO_THRESHOLD_PIXELS_PER_MD = 225;
export const CORE_PHOTO_THRESHOLD_WIDTH_PX = 13.5;

export type TrackBackdropMode = 'light' | 'dark';
type CombinationTrackState = 'normal' | 'active' | 'locked';

type ViewportTieHeaderStatus = {
    role: 'leader' | 'member';
    leaderLabel: string;
    memberLabels: string[];
};

type CombinationZoomContextValue = {
    presentationByTrackId: Record<string, { state: CombinationTrackState; selected: boolean; tied: boolean; title: string; ariaLabel: string }>;
    tieStatusByTrackId: Record<string, ViewportTieHeaderStatus>;
    onToggleTrack?: (trackId: string, additive?: boolean) => void;
};

const CombinationZoomContext = createContext<CombinationZoomContextValue>({
    presentationByTrackId: {},
    tieStatusByTrackId: {},
});

function TrackPlacementSelector({ track }: { track: WellLogTrack }) {
    const combinationZoom = useContext(CombinationZoomContext);
    const buttonRef = useRef<HTMLButtonElement | null>(null);
    const [tieStatusOpen, setTieStatusOpen] = useState(false);
    const [tieStatusPosition, setTieStatusPosition] = useState({ left: 0, top: 0 });
    const presentation = combinationZoom.presentationByTrackId[track.trackId] ?? {
        state: 'normal' as const,
        selected: false,
        tied: false,
        title: `T${track.trackIndex + 1}`,
        ariaLabel: `Track T${track.trackIndex + 1}: unlocked, untied`,
    };
    const { state, selected, tied, title, ariaLabel } = presentation;
    const tieStatus = combinationZoom.tieStatusByTrackId[track.trackId];
    const trackLabel = `T${track.trackIndex + 1}`;

    useEffect(() => {
        if (!tieStatusOpen || !tieStatus) return;
        const updatePosition = () => {
            const rect = buttonRef.current?.getBoundingClientRect();
            if (!rect) return;
            setTieStatusPosition({
                left: Math.round(rect.left),
                top: Math.round(rect.bottom + 6),
            });
        };
        const close = (event: PointerEvent) => {
            const target = event.target;
            if (target instanceof Node && buttonRef.current?.contains(target)) return;
            setTieStatusOpen(false);
        };
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setTieStatusOpen(false);
        };
        updatePosition();
        window.addEventListener('resize', updatePosition);
        window.addEventListener('scroll', updatePosition, true);
        document.addEventListener('pointerdown', close, true);
        document.addEventListener('keydown', closeOnEscape, true);
        return () => {
            window.removeEventListener('resize', updatePosition);
            window.removeEventListener('scroll', updatePosition, true);
            document.removeEventListener('pointerdown', close, true);
            document.removeEventListener('keydown', closeOnEscape, true);
        };
    }, [tieStatusOpen, tieStatus]);

    return <>
      <button
        ref={buttonRef}
        type="button"
        className="wlv-track-placement-selector"
        data-combination-track-id={track.trackId}
        data-combination-track-state={state}
        data-combination-track-selected={selected ? 'true' : 'false'}
        data-viewport-tied={tied ? 'true' : 'false'}
        data-viewport-tie-role={tieStatus?.role ?? 'none'}
        aria-pressed={selected}
        aria-expanded={tieStatus ? tieStatusOpen : undefined}
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (tieStatus) {
                setTieStatusOpen((open) => !open);
                return;
            }
            combinationZoom.onToggleTrack?.(track.trackId, true);
        }}
        title={tieStatus?.role === 'leader'
            ? `${trackLabel} · Tie principal`
            : tieStatus
              ? `${trackLabel} · Synced to ${tieStatus.leaderLabel}`
              : title}
        aria-label={tieStatus?.role === 'leader'
            ? `${ariaLabel}. Tie principal.`
            : tieStatus
              ? `${ariaLabel}. Synced to ${tieStatus.leaderLabel}.`
              : ariaLabel}
      >{trackLabel}</button>
      {tieStatus && tieStatusOpen ? createPortal(
        <div
          role="status"
          className="wlv-track-tie-status-popover"
          style={{
              top: tieStatusPosition.top,
              left: tieStatusPosition.left,
          }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          {tieStatus.role === 'leader' ? <>
            <strong className="wlv-track-tie-status-title">{trackLabel} · Tie principal</strong>
            <span className="wlv-track-tie-status-body">Synced tracks: {tieStatus.memberLabels.filter((label) => label !== trackLabel).join(', ') || 'None'}</span>
          </> : <>
            <strong className="wlv-track-tie-status-title">{trackLabel}</strong>
            <span className="wlv-track-tie-status-body">Synced to {tieStatus.leaderLabel}</span>
          </>}
        </div>,
        document.body,
      ) : null}
    </>;
}

type ToolbarZoneProps = {
    id: string;
    title: string;
    children: ReactNode;
    defaultExpanded?: boolean;
    className?: string;
};

const TOOLBAR_ZONE_STORAGE_PREFIX = 'wlv.wdv.toolbar-zone.';

function ToolbarZone({ id, title, children, defaultExpanded = true, className = '' }: ToolbarZoneProps) {
    const storageKey = `${TOOLBAR_ZONE_STORAGE_PREFIX}${id}`;
    const [expanded, setExpanded] = useState<boolean>(() => {
        if (typeof window === 'undefined')
            return defaultExpanded;
        try {
            const stored = window.localStorage.getItem(storageKey);
            return stored === null ? defaultExpanded : stored === 'expanded';
        }
        catch {
            return defaultExpanded;
        }
    });

    const toggleExpanded = () => {
        setExpanded((current) => {
            const next = !current;
            if (typeof window !== 'undefined') {
                try {
                    window.localStorage.setItem(storageKey, next ? 'expanded' : 'collapsed');
                }
                catch {
                    // Storage can be unavailable in restricted browser contexts.
                }
            }
            return next;
        });
    };

    return (<section className={`wlv-toolbar-group wlv-toolbar-zone ${className} ${expanded ? 'is-expanded' : 'is-collapsed'}`.trim()} data-toolbar-zone={id}>
      <button type="button" className="wlv-toolbar-zone-header" aria-expanded={expanded} aria-controls={`wlv-toolbar-zone-body-${id}`} onClick={toggleExpanded}>
        <span className="wlv-toolbar-zone-triangle" aria-hidden="true">{expanded ? '▼' : '▶'}</span>
        <span>{title}</span>
      </button>
      {expanded ? <div id={`wlv-toolbar-zone-body-${id}`} className="wlv-toolbar-actions wlv-toolbar-zone-body">{children}</div> : null}
    </section>);
}

export function Toolbar({ commonDepthUnit, onCommonDepthUnitChange, managedLayoutDisabled = false, depthUnitDisabled = false, selectedTrack, tracks, intervalTracks, pendingAddTrackCurveCount, viewDepthRange, fullDepthRange, viewDepthReadoutEnabled, intervalZoomActive, goToDepthValue, onGoToDepthValueChange, trackBackdropMode, onTrackBackdropModeChange, trackHeadersCollapsed, onTrackHeadersCollapsedChange, onAddTrack, onConfigureIntervalTrack, onDeleteTrack, onClearCanvas, onMoveSelectedTrack, canMoveSelectedTrackLeft, canMoveSelectedTrackRight, canAdjustSelectedCurveTrackWidthDown, canAdjustSelectedCurveTrackWidthUp, onAdjustSelectedCurveTrackWidth, onResetCurveTrackWidths, onZoomIn, onZoomOut, viewportToolbarPresentation, onLockSelectedTracks, onUnlockSelectedTracks, onCreateViewportTie, onUntieSelectedViewportTracks, onPreviousView, onFitDepth, onSpecifyDepthRange, onResetView, onToggleIntervalZoom, onGoToDepth, savedCanvases = [], savedCanvasDisabled = false, savedCanvasSaving = false, savedCanvasBusyUid = null, savedCanvasError = null, onSaveCanvas, onSaveActiveCanvas, onLoadSavedCanvas, onDeleteSavedCanvas, canvasRightInsetPx = 330,
    navigationFormationTops = [],
    onGoToFormationTop, goToDepthPickActive = false, onStartGoToDepthPick, displayGoToSelectionLine = true, onDisplayGoToSelectionLineChange, coreThresholdAvailable = false, onCoreThreshold, onAddTrackCurveSelectionModeChange, formationTopDatasets, formationTopMarkersByWellUid = {}, selectedFormationTopIds, coreImageItems, layoutRecommendations, layoutRecommendationsLoading, layoutRecommendationsError, selectedLayoutRecommendationKey, onLayoutRecommendationChange, onRefreshLayoutRecommendations, wbvPublishAction, }: {
    commonDepthUnit: 'm' | 'ft';
    onCommonDepthUnitChange: (unit: 'm' | 'ft') => void;
    managedLayoutDisabled?: boolean;
    depthUnitDisabled?: boolean;
    selectedTrack: WellLogTrack | null;
    tracks: WellLogTrack[];
    intervalTracks: WellLogTrack[];
    pendingAddTrackCurveCount: number;
    viewDepthRange: DepthViewRange;
    fullDepthRange: DepthViewRange;
    viewDepthReadoutEnabled: boolean;
    intervalZoomActive: boolean;
    goToDepthValue: string;
    onGoToDepthValueChange: (value: string) => void;
    trackBackdropMode: TrackBackdropMode;
    onTrackBackdropModeChange: (mode: TrackBackdropMode) => void;
    trackHeadersCollapsed: boolean;
    onTrackHeadersCollapsedChange: (collapsed: boolean) => void;
    onAddTrack: (draft: AddTrackDraft) => void;
    onConfigureIntervalTrack?: (
        trackId: string,
        config: {
            trackName: string;
            rendererType: string;
            trackRole: string;
            widthPx: number;
        },
    ) => void | Promise<void>;
    onDeleteTrack: () => void;
    onClearCanvas: () => void;
    onMoveSelectedTrack: (direction: -1 | 1) => void;
    canMoveSelectedTrackLeft: boolean;
    canMoveSelectedTrackRight: boolean;
    canAdjustSelectedCurveTrackWidthDown: boolean;
    canAdjustSelectedCurveTrackWidthUp: boolean;
    onAdjustSelectedCurveTrackWidth: (delta: number) => void;
    onResetCurveTrackWidths: () => void;
    onZoomIn: () => void;
    onZoomOut: () => void;
    viewportToolbarPresentation: ViewportToolbarPresentation;
    onLockSelectedTracks?: () => void;
    onUnlockSelectedTracks?: () => void;
    onCreateViewportTie?: (leaderTrackId: string) => void;
    onUntieSelectedViewportTracks?: () => void;
    onPreviousView: () => void;
    onFitDepth: () => void;
    onSpecifyDepthRange: (range: DepthViewRange) => void;
    onResetView: () => void;
    savedCanvases?: SavedCanvasToolbarItem[];
    savedCanvasDisabled?: boolean;
    savedCanvasSaving?: boolean;
    savedCanvasBusyUid?: string | null;
    savedCanvasError?: string | null;
    onSaveCanvas?: (name: string) => void | Promise<void>;
    onSaveActiveCanvas?: (savedCanvasUid: string) => void | Promise<void>;
    onLoadSavedCanvas?: (savedCanvasUid: string) => void | Promise<void>;
    onDeleteSavedCanvas?: (savedCanvasUid: string) => void | Promise<void>;
    canvasRightInsetPx?: number;
    onToggleIntervalZoom: () => void;
    onGoToDepth: () => void;
    navigationFormationTops: FormationTopMarker[];
    onGoToFormationTop: (marker: FormationTopMarker) => void;
    goToDepthPickActive?: boolean;
    onStartGoToDepthPick?: () => void;
    displayGoToSelectionLine?: boolean;
    onDisplayGoToSelectionLineChange?: (visible: boolean) => void;
    coreThresholdAvailable?: boolean;
    onCoreThreshold?: () => void;
    onAddTrackCurveSelectionModeChange: (active: boolean) => void;
    formationTopDatasets: FormationTopDataset[];
    formationTopMarkersByWellUid?: Record<string, FormationTopMarker[]>;
    selectedFormationTopIds: Set<string>;
    coreImageItems: CoreImageInventoryItem[];
    layoutRecommendations: WdvTemplateRecommendationItem[];
    layoutRecommendationsLoading: boolean;
    layoutRecommendationsError: string | null;
    selectedLayoutRecommendationKey: string;
    onLayoutRecommendationChange: (templateKey: string) => void;
    onRefreshLayoutRecommendations: () => void;
    wbvPublishAction?: ReactNode;
}) {
    const [builderOpen, setBuilderOpen] = useState(false);
    const [draft, setDraft] = useState<AddTrackDraft>(defaultAddTrackDraft);
    const [intervalBuilderOpen,setIntervalBuilderOpen]=useState(false);
    const [intervalBuilderPortalTarget,setIntervalBuilderPortalTarget]=useState<HTMLElement|null>(null);
    const [intervalBuilderEmbedded,setIntervalBuilderEmbedded]=useState(false);
    const [intervalBuilderMode,setIntervalBuilderMode]=useState<'create'|'edit'>('create');
    const [intervalBuilderTab,setIntervalBuilderTab]=useState<IntervalBuilderTab>('formation');
    const [intervalBuilderColumns,setIntervalBuilderColumns]=useState<IntervalBuilderColumn[]>(()=>loadIntervalBuilderColumns());
    const [intervalTieInByTrackId,setIntervalTieInByTrackId]=useState<Record<string,IntervalTieInLayerState>>(()=>loadIntervalTieInByTrackId());
    const [intervalTieInSelectedLayerId,setIntervalTieInSelectedLayerId]=useState<string|null>(null);
    const [intervalTieInDraft,setIntervalTieInDraft]=useState<IntervalTieInLayer>(()=>newIntervalTieInLayer(1));
    const [intervalTieInDraftMode,setIntervalTieInDraftMode]=useState<'new'|'style'|null>(null);
    const [intervalTieInCreationMethod,setIntervalTieInCreationMethod]=useState<'manual'|'formation_tops'>('manual');
    const [intervalTieInTopSelection,setIntervalTieInTopSelection]=useState<Set<string>>(()=>new Set());
    const intervalTieInTopSelectionRef=useRef<Set<string>>(new Set());
    const [intervalTieInTopMatchByMarkerId,setIntervalTieInTopMatchByMarkerId]=useState<Record<string,string>>({});
    const intervalTieInTopMatchByMarkerIdRef=useRef<Record<string,string>>({});
    const [intervalTieInExpandedLayerIds,setIntervalTieInExpandedLayerIds]=useState<Set<string>>(()=>new Set());
    const [intervalTieInHostTrackId,setIntervalTieInHostTrackId]=useState<string|null>(null);
    const [intervalTieInPickField,setIntervalTieInPickField]=useState<IntervalTieInField|null>(null);
    const [intervalTieInPickError,setIntervalTieInPickError]=useState<string|null>(null);
    const intervalTieInPickTokenRef=useRef(`tie-in-${Math.random().toString(36).slice(2)}`);
    const [intervalFormationConfig,setIntervalFormationConfig]=useState<IntervalFormationConfig>(()=>loadIntervalFormationConfig());
    const [intervalDepthConfig,setIntervalDepthConfig]=useState<IntervalDepthConfig>(()=>loadIntervalDepthConfig());
    const [intervalDescriptionConfig,setIntervalDescriptionConfig]=useState<IntervalDescriptionConfig>(()=>loadIntervalDescriptionConfig());
    const [manualTopName,setManualTopName]=useState('');
    const [manualTopMd,setManualTopMd]=useState('');
    const [manualTopGroup,setManualTopGroup]=useState('');
    const [intervalBuilderPosition,setIntervalBuilderPosition]=useState({top:72,left:160});
    const intervalBuilderDragRef=useRef<{
        startClientX:number;
        startClientY:number;
        startLeft:number;
        startTop:number;
    }|null>(null);
    const [panelPosition, setPanelPosition] = useState({ top: 128, left: 360 });
    const [rangeEditorOpen, setRangeEditorOpen] = useState(false);
    const [viewportTiePickerOpen, setViewportTiePickerOpen] = useState(false);
    const viewportTieButtonRef = useRef<HTMLButtonElement | null>(null);
    const viewportTiePopoverRef = useRef<HTMLDivElement | null>(null);
    const [viewportTiePopoverPosition, setViewportTiePopoverPosition] = useState({ top: 0, left: 0 });
    const [rangeTopValue, setRangeTopValue] = useState(String(Math.round(viewDepthRange.min)));
    const [rangeBaseValue, setRangeBaseValue] = useState(String(Math.round(viewDepthRange.max)));
    const specifyRangeButtonRef = useRef<HTMLButtonElement | null>(null);
    const specifyRangePopoverRef = useRef<HTMLDivElement | null>(null);
    const [rangePopoverPosition, setRangePopoverPosition] = useState({ top: 0, left: 0 });
    const [goToEditorOpen, setGoToEditorOpen] = useState(false);
    const goToDepthButtonRef = useRef<HTMLButtonElement | null>(null);
    const goToDepthPopoverRef = useRef<HTMLDivElement | null>(null);
    const [goToDepthPopoverPosition, setGoToDepthPopoverPosition] = useState({ top: 0, left: 0 });
    const [selectedGoToFormationTopId, setSelectedGoToFormationTopId] = useState('');
    const dragStateRef = useRef<{
        startClientX: number;
        startClientY: number;
        startLeft: number;
        startTop: number;
    } | null>(null);
    useEffect(() => {
        if (viewportToolbarPresentation.tie.action !== 'tie') {
            setViewportTiePickerOpen(false);
        }
    }, [viewportToolbarPresentation.tie.action]);

    useEffect(() => {
        if (!viewportTiePickerOpen)
            return undefined;
        const updatePosition = () => updateViewportTiePopoverPosition();
        const onPointerDown = (event: PointerEvent) => {
            const target = event.target as Node | null;
            if (!target)
                return;
            if (viewportTiePopoverRef.current?.contains(target))
                return;
            if (viewportTieButtonRef.current?.contains(target))
                return;
            setViewportTiePickerOpen(false);
        };
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                setViewportTiePickerOpen(false);
            }
        };
        updatePosition();
        window.addEventListener('resize', updatePosition, true);
        window.addEventListener('scroll', updatePosition, true);
        document.addEventListener('pointerdown', onPointerDown, true);
        document.addEventListener('keydown', onKeyDown, true);
        return () => {
            window.removeEventListener('resize', updatePosition, true);
            window.removeEventListener('scroll', updatePosition, true);
            document.removeEventListener('pointerdown', onPointerDown, true);
            document.removeEventListener('keydown', onKeyDown, true);
        };
    }, [viewportTiePickerOpen]);

    useEffect(() => {
        if (rangeEditorOpen)
            return;
        setRangeTopValue(String(Math.round(viewDepthRange.min)));
        setRangeBaseValue(String(Math.round(viewDepthRange.max)));
    }, [rangeEditorOpen, viewDepthRange.min, viewDepthRange.max]);
    useEffect(() => {
        if (!goToEditorOpen)
            return;
        const reposition = () => updateGoToDepthPopoverPosition();
        window.addEventListener('resize', reposition);
        window.addEventListener('scroll', reposition, true);
        return () => {
            window.removeEventListener('resize', reposition);
            window.removeEventListener('scroll', reposition, true);
        };
    }, [goToEditorOpen]);

    const updateViewportTiePopoverPosition = () => {
        const button = viewportTieButtonRef.current;
        if (!button)
            return;
        const rect = button.getBoundingClientRect();
        const popoverWidth = 128;
        const margin = 12;
        const maxLeft = Math.max(margin, window.innerWidth - popoverWidth - margin);
        setViewportTiePopoverPosition({
            top: rect.bottom + 10,
            left: clampValue(rect.left, margin, maxLeft),
        });
    };
    const updateGoToDepthPopoverPosition = () => {
        const button = goToDepthButtonRef.current;
        if (!button)
            return;
        const rect = button.getBoundingClientRect();
        const popoverWidth = 420;
        const margin = 12;
        const maxLeft = Math.max(margin, window.innerWidth - popoverWidth - margin);
        setGoToDepthPopoverPosition({
            top: rect.bottom + 10,
            left: clampValue(rect.left, margin, maxLeft),
        });
    };
    const openGoToDepthEditor = () => {
        updateGoToDepthPopoverPosition();
        setGoToEditorOpen(true);
    };
    const applyGoToDepth = () => {
        onGoToDepth();
        setGoToEditorOpen(false);
    };

    /*
     * Navigation Formation Tops are supplied by WdvPageBoundary from the
     * currently active WDV well only.
     */
    const goToFormationTopOptions = useMemo(
        () => [...navigationFormationTops]
            .filter((marker) => Number.isFinite(marker.md))
            .sort(
                (left, right) =>
                    left.md - right.md
                    || left.markerName.localeCompare(right.markerName),
            ),
        [navigationFormationTops],
    );

    useEffect(() => {
        if (
            selectedGoToFormationTopId
            && !goToFormationTopOptions.some(
                (marker) =>
                    marker.markerId === selectedGoToFormationTopId,
            )
        ) {
            setSelectedGoToFormationTopId('');
        }
    }, [
        goToFormationTopOptions,
        selectedGoToFormationTopId,
    ]);

    const applyGoToFormationTop = () => {
        const marker = goToFormationTopOptions.find(
            (candidate) =>
                candidate.markerId === selectedGoToFormationTopId,
        );

        if (!marker) return;

        onGoToFormationTop(marker);
        setGoToEditorOpen(false);
    };
    const updateSpecifiedRangePopoverPosition = () => {
        const button = specifyRangeButtonRef.current;
        if (!button)
            return;
        const rect = button.getBoundingClientRect();
        const popoverWidth = 560;
        const margin = 12;
        const preferredLeft = rect.left;
        const maxLeft = Math.max(margin, window.innerWidth - popoverWidth - margin);
        setRangePopoverPosition({
            top: rect.bottom + 10,
            left: clampValue(preferredLeft, margin, maxLeft),
        });
    };
    const openSpecifiedRangeEditor = () => {
        setRangeTopValue(String(Math.round(viewDepthRange.min)));
        setRangeBaseValue(String(Math.round(viewDepthRange.max)));
        setRangeEditorOpen((open) => {
            const nextOpen = !open;
            if (nextOpen) {
                window.requestAnimationFrame(updateSpecifiedRangePopoverPosition);
            }
            return nextOpen;
        });
    };
    const applySpecifiedRange = () => {
        const top = Number.parseFloat(rangeTopValue);
        const base = Number.parseFloat(rangeBaseValue);
        if (!Number.isFinite(top) || !Number.isFinite(base) || top === base)
            return;
        onSpecifyDepthRange({
            min: Math.min(top, base),
            max: Math.max(top, base),
        });
        setRangeEditorOpen(false);
    };
    useEffect(() => {
        if (!rangeEditorOpen)
            return undefined;
        const updatePosition = () => updateSpecifiedRangePopoverPosition();
        const onPointerDown = (event: PointerEvent) => {
            const target = event.target as Node | null;
            if (!target)
                return;
            if (specifyRangePopoverRef.current?.contains(target))
                return;
            if (specifyRangeButtonRef.current?.contains(target))
                return;
            setRangeEditorOpen(false);
        };
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                setRangeEditorOpen(false);
            }
        };
        updatePosition();
        window.addEventListener('resize', updatePosition, true);
        window.addEventListener('scroll', updatePosition, true);
        document.addEventListener('pointerdown', onPointerDown, true);
        document.addEventListener('keydown', onKeyDown, true);
        return () => {
            window.removeEventListener('resize', updatePosition, true);
            window.removeEventListener('scroll', updatePosition, true);
            document.removeEventListener('pointerdown', onPointerDown, true);
            document.removeEventListener('keydown', onKeyDown, true);
        };
    }, [rangeEditorOpen, viewDepthRange.min, viewDepthRange.max]);
    const updateDraft = (patch: Partial<AddTrackDraft>) => {
        setDraft((current) => ({ ...current, ...patch }));
    };
    const clampPanelPosition = (position: {
        top: number;
        left: number;
    }) => {
        const margin = 12;
        const panelWidth = 420;
        return {
            top: Math.max(margin, Math.min(position.top, window.innerHeight - margin - 80)),
            left: Math.max(margin, Math.min(position.left, window.innerWidth - panelWidth - margin)),
        };
    };
    const openAddTrackBuilder = () => {
        setDraft((current) => ({
            ...current,
            // Placement defaults must always be resolvable at builder-open time.
            // With no active track (including a blank canvas), relative insertion
            // is impossible, so default to Far right.  Once an active track
            // exists, preserve the normal After active track workflow.
            insertMode: selectedTrack ? 'after_selected' : 'far_right',
            referenceTrackId: selectedTrack?.trackId ?? null,
        }));
        setPanelPosition(clampPanelPosition({
            top: 118,
            left: Math.max(280, Math.round(window.innerWidth * 0.32)),
        }));
        setBuilderOpen(true);
    };
    const closeAddTrackBuilder = () => {
        setBuilderOpen(false);
        dragStateRef.current = null;
        onAddTrackCurveSelectionModeChange(false);
    };
    const toggleAddTrackBuilder = () => {
        if (builderOpen) {
            closeAddTrackBuilder();
            return;
        }
        openAddTrackBuilder();
    };
    const selectTrackType = (trackType: ActiveTrackType) => {
        updateDraft({ trackType });
        onAddTrackCurveSelectionModeChange(trackType === 'curve' && draft.curveSource === 'selected');
    };
    const selectCurveSource = (curveSource: AddTrackDraft['curveSource']) => {
        updateDraft({ curveSource });
        onAddTrackCurveSelectionModeChange(curveSource === 'selected');
    };
    const startPanelDrag = (event: ReactMouseEvent<HTMLDivElement>) => {
        event.preventDefault();
        dragStateRef.current = {
            startClientX: event.clientX,
            startClientY: event.clientY,
            startLeft: panelPosition.left,
            startTop: panelPosition.top,
        };
    };
    useEffect(() => {
        if (!builderOpen)
            return undefined;
        const onMouseMove = (event: MouseEvent) => {
            const dragState = dragStateRef.current;
            if (!dragState)
                return;
            setPanelPosition(clampPanelPosition({
                top: dragState.startTop + event.clientY - dragState.startClientY,
                left: dragState.startLeft + event.clientX - dragState.startClientX,
            }));
        };
        const onMouseUp = () => {
            dragStateRef.current = null;
        };
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                closeAddTrackBuilder();
            }
        };
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        document.addEventListener('keydown', onKeyDown, true);
        return () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
            document.removeEventListener('keydown', onKeyDown, true);
        };
    }, [builderOpen, panelPosition.left, panelPosition.top]);
    const clampIntervalBuilderPosition=(position:{top:number;left:number})=>{
        const margin=12;
        return {
            top:Math.max(margin,Math.min(position.top,window.innerHeight-margin-72)),
            left:Math.max(margin,Math.min(position.left,window.innerWidth-margin-180)),
        };
    };
    const selectedTieInNeighbours=useMemo(()=>{
        if(!intervalTieInHostTrackId)return {hostTrack:null,trackA:null,trackB:null};
        const ordered=sortTracks(tracks);
        const index=ordered.findIndex(track=>track.trackId===intervalTieInHostTrackId);
        const hostTrack=index>=0?ordered[index]:null;
        if(hostTrack?.trackType!=='interval')return {hostTrack:null,trackA:null,trackB:null};
        return {
            hostTrack,
            trackA:index>0?ordered[index-1]:null,
            trackB:index>=0&&index<ordered.length-1?ordered[index+1]:null,
        };
    },[intervalTieInHostTrackId,tracks]);

    const formationTopTieRows=useMemo<FormationTopTieRow[]>(()=>{
        const trackA=selectedTieInNeighbours.trackA;
        const trackB=selectedTieInNeighbours.trackB;
        const markersA:FormationTopMarker[]=trackA?.managedWellUid
            ? formationTopMarkersByWellUid[trackA.managedWellUid]??[]
            : [];
        const markersB:FormationTopMarker[]=trackB?.managedWellUid
            ? formationTopMarkersByWellUid[trackB.managedWellUid]??[]
            : [];
        return markersA.map((markerA):FormationTopTieRow=>{
            const ranked=markersB
                .map((markerB):{markerB:FormationTopMarker;score:number}=>({markerB,score:formationTopTieSimilarity(markerA.markerName,markerB.markerName)}))
                .sort((left,right)=>right.score-left.score);
            const best=ranked[0]??null;
            const suggestedMarkerB=best&&best.score>=0.55?best.markerB:null;
            return {
                markerA,
                suggestedMarkerB,
                score:best?.score??0,
                status:best?.score===1?'Exact':best&&best.score>=0.55?'Suggested':'Choose',
            };
        });
    },[formationTopMarkersByWellUid,selectedTieInNeighbours.trackA,selectedTieInNeighbours.trackB]);
    const formationTopBoundPairs=useMemo(()=>formationTopTieRows
        .filter(row=>row.suggestedMarkerB)
        .map(row=>({
            key:`${row.markerA.markerId}::${row.suggestedMarkerB!.markerId}`,
            markerA:row.markerA,
            markerB:row.suggestedMarkerB!,
            label:`${row.markerA.markerName} · ${Number(row.markerA.md).toFixed(2)} → ${Number(row.suggestedMarkerB!.md).toFixed(2)} MD`,
        })),[formationTopTieRows]);
    const selectedTieInFillTopPairKey=intervalTieInDraft.fillTopMarkerAId&&intervalTieInDraft.fillTopMarkerBId
        ?`${intervalTieInDraft.fillTopMarkerAId}::${intervalTieInDraft.fillTopMarkerBId}`:'';
    const selectedTieInFillBasePairKey=intervalTieInDraft.fillBaseMarkerAId&&intervalTieInDraft.fillBaseMarkerBId
        ?`${intervalTieInDraft.fillBaseMarkerAId}::${intervalTieInDraft.fillBaseMarkerBId}`:'';
    const applyTieInFormationFillBoundary=(boundary:'top'|'base',pairKey:string)=>{
        const pair=formationTopBoundPairs.find(candidate=>candidate.key===pairKey);
        if(!pair){
            updateIntervalTieInDraft(boundary==='top'
                ?{fillTopMarkerAId:'',fillTopMarkerBId:'',fillUpperA:null,fillUpperB:null}
                :{fillBaseMarkerAId:'',fillBaseMarkerBId:'',fillLowerA:null,fillLowerB:null});
            return;
        }
        updateIntervalTieInDraft(boundary==='top'
            ?{fillTopMarkerAId:pair.markerA.markerId,fillTopMarkerBId:pair.markerB.markerId,fillUpperA:pair.markerA.md,fillUpperB:pair.markerB.md}
            :{fillBaseMarkerAId:pair.markerA.markerId,fillBaseMarkerBId:pair.markerB.markerId,fillLowerA:pair.markerA.md,fillLowerB:pair.markerB.md});
    };

    const replaceIntervalTieInTopSelection=(next:Set<string>)=>{
        intervalTieInTopSelectionRef.current=next;
        setIntervalTieInTopSelection(next);
    };
    const setIntervalTieInTopSelected=(markerId:string,checked:boolean)=>{
        const next=new Set(intervalTieInTopSelectionRef.current);
        if(checked)next.add(markerId);else next.delete(markerId);
        replaceIntervalTieInTopSelection(next);
    };
    const setIntervalTieInTopMatch=(markerId:string,matchMarkerId:string)=>{
        const next={...intervalTieInTopMatchByMarkerIdRef.current,[markerId]:matchMarkerId};
        intervalTieInTopMatchByMarkerIdRef.current=next;
        setIntervalTieInTopMatchByMarkerId(next);
    };

    /*
     * WDV_TIE_IN_FORMATION_CORRELATION_V2_0_0
     *
     * Tie-in storage is authoritative. Formation Top creation commits to storage
     * first, verifies the exact host/layer set by reading it back, and only then
     * updates Toolbar React state and tells TrackCanvas to refresh.
     *
     * This removes the previous failure mode where local Toolbar state, preview
     * state and persisted Interval state could disagree about whether the new
     * correlation existed.
     */
    const commitIntervalTieInState=(trackId:string,nextState:IntervalTieInLayerState):boolean=>{
        try{
            const persisted=readIntervalBuilderPersistedPayload();
            const nextTieIns={
                ...persisted.tieInByTrackId,
                [trackId]:normalizeIntervalTieInLayerState(nextState),
            };
            persistIntervalBuilderState(intervalBuilderColumns,nextTieIns);

            const verified=loadIntervalTieInLayerState(trackId);
            const expectedIds=nextState.layers.map(layer=>layer.layerId);
            const verifiedIds=verified.layers.map(layer=>layer.layerId);
            const verifiedExact=
                expectedIds.length===verifiedIds.length
                && expectedIds.every((layerId,index)=>layerId===verifiedIds[index]);

            if(!verifiedExact){
                setIntervalTieInPickError('Tie-in storage verification failed. No correlation was committed.');
                return false;
            }

            const verifiedAll=loadIntervalTieInByTrackId();
            setIntervalTieInByTrackId(verifiedAll);
            window.dispatchEvent(new CustomEvent(INTERVAL_TIE_IN_CONFIG_CHANGED_EVENT));
            window.dispatchEvent(new CustomEvent(INTERVAL_STORAGE_COMMITTED_EVENT));
            window.dispatchEvent(new CustomEvent(INTERVAL_TIE_IN_PREVIEW_END_EVENT,{detail:{trackId}}));
            return true;
        }catch(error){
            setIntervalTieInPickError(`Tie-in commit failed: ${error instanceof Error?error.message:String(error)}`);
            return false;
        }
    };

    const tieInStateForHost=()=>{
        if(!intervalTieInHostTrackId)return {selectedLayerId:null,layers:[]} as IntervalTieInLayerState;
        return normalizeIntervalTieInLayerState(intervalTieInByTrackId[intervalTieInHostTrackId]);
    };
    const publishIntervalTieInPreview=(state:IntervalTieInLayerState,draft?:IntervalTieInLayer|null)=>{
        if(!intervalTieInHostTrackId)return;
        const previewLayers=[...state.layers];
        if(draft){
            const index=previewLayers.findIndex(layer=>layer.layerId===draft.layerId);
            if(index>=0)previewLayers[index]=draft;
            else if(draft.upperA!==null&&draft.upperB!==null&&draft.lowerA!==null&&draft.lowerB!==null)previewLayers.push(draft);
        }
        window.dispatchEvent(new CustomEvent(INTERVAL_TIE_IN_PREVIEW_EVENT,{detail:{trackId:intervalTieInHostTrackId,state:{selectedLayerId:draft?.layerId??state.selectedLayerId,layers:previewLayers}}}));
    };
    const endIntervalTieInPreview=()=>{
        if(!intervalTieInHostTrackId)return;
        window.dispatchEvent(new CustomEvent(INTERVAL_TIE_IN_PREVIEW_END_EVENT,{detail:{trackId:intervalTieInHostTrackId}}));
    };
    const updateIntervalTieInDraft=(patch:Partial<IntervalTieInConfig>&{name?:string})=>{
        setIntervalTieInDraft(current=>{
            const normalized=normalizeIntervalTieInConfig({...current,...patch});
            const next:IntervalTieInLayer={...normalized,layerId:current.layerId,name:typeof patch.name==='string'?(patch.name.trim()||current.name):current.name};
            publishIntervalTieInPreview(tieInStateForHost(),next);
            return next;
        });
    };
    const selectIntervalTieInLayer=(layerId:string)=>{
        if(intervalTieInPickField)cancelIntervalTieInPick();
        const state=tieInStateForHost();
        const layer=state.layers.find(candidate=>candidate.layerId===layerId);
        if(!layer)return;
        setIntervalTieInSelectedLayerId(layer.layerId);
        setIntervalTieInDraft({...layer});
        setIntervalTieInDraftMode('style');
        publishIntervalTieInPreview({...state,selectedLayerId:layer.layerId},layer);
    };
    const addIntervalTieInLayer=()=>{
        if(intervalTieInPickField)cancelIntervalTieInPick();
        const state=tieInStateForHost();
        const layer=newIntervalTieInLayer(state.layers.length+1,{enabled:true});
        setIntervalTieInSelectedLayerId(layer.layerId);
        setIntervalTieInDraft(layer);
        setIntervalTieInDraftMode('new');
        setIntervalTieInCreationMethod('manual');
        replaceIntervalTieInTopSelection(new Set());
        intervalTieInTopMatchByMarkerIdRef.current={};
        setIntervalTieInTopMatchByMarkerId({});
        setIntervalTieInPickError(null);
        publishIntervalTieInPreview(state,layer);
    };
    const addFormationTopTieInLayers=()=>{
        const hostTrackId=intervalTieInHostTrackId;
        if(!hostTrackId){
            setIntervalTieInPickError('No Interval Tie-in host track is selected.');
            return;
        }

        const selectedIds=new Set(intervalTieInTopSelectionRef.current);
        if(selectedIds.size===0){
            setIntervalTieInPickError('Select at least one Formation Top correlation.');
            return;
        }

        const trackB=selectedTieInNeighbours.trackB;
        const markersB:FormationTopMarker[]=trackB?.managedWellUid
            ? formationTopMarkersByWellUid[trackB.managedWellUid]??[]
            : [];
        const markersBById=new Map(markersB.map(marker=>[marker.markerId,marker]));

        // Read the latest authoritative state directly from storage. Do not build
        // a persisted transaction from possibly stale Toolbar React state.
        const persistedBefore=readIntervalBuilderPersistedPayload();
        const state=normalizeIntervalTieInLayerState(persistedBefore.tieInByTrackId[hostTrackId]);

        let ordinal=state.layers.length+1;
        const added:IntervalTieInLayer[]=[];
        const unresolved:string[]=[];

        for(const row of formationTopTieRows){
            if(!selectedIds.has(row.markerA.markerId))continue;

            const explicitMarkerId=intervalTieInTopMatchByMarkerIdRef.current[row.markerA.markerId]??'';
            const markerB=explicitMarkerId
                ? markersBById.get(explicitMarkerId)??null
                : row.suggestedMarkerB;

            if(!markerB){
                unresolved.push(`${row.markerA.markerName}: choose a Track B Formation Top`);
                continue;
            }

            const mdA=Number(row.markerA.md);
            const mdB=Number(markerB.md);
            if(!Number.isFinite(mdA)||!Number.isFinite(mdB)){
                unresolved.push(`${row.markerA.markerName}: invalid MD`);
                continue;
            }

            const layer=newIntervalTieInLayer(ordinal++,{
                enabled:true,
                upperA:mdA,
                upperB:mdB,
                lowerA:null,
                lowerB:null,
                fillEnabled:false,
                line:{...intervalTieInDraft.line},
            });
            added.push({...layer,name:`${row.markerA.markerName} → ${markerB.markerName}`});
        }

        if(unresolved.length>0){
            setIntervalTieInPickError(unresolved[0]);
            return;
        }
        if(added.length===0){
            setIntervalTieInPickError('No Formation Top Tie-ins were created.');
            return;
        }

        const nextState:IntervalTieInLayerState={
            selectedLayerId:added[added.length-1].layerId,
            layers:[...state.layers,...added],
        };

        if(!commitIntervalTieInState(hostTrackId,nextState))return;

        setIntervalTieInPickError(null);
        setIntervalTieInSelectedLayerId(nextState.selectedLayerId);
        setIntervalTieInDraftMode(null);
        replaceIntervalTieInTopSelection(new Set());
        intervalTieInTopMatchByMarkerIdRef.current={};
        setIntervalTieInTopMatchByMarkerId({});
    };
    const deleteIntervalTieInLayer=(layerId:string)=>{
        if(intervalTieInPickField)cancelIntervalTieInPick();
        if(!intervalTieInHostTrackId)return;
        const state=tieInStateForHost();
        const layers=state.layers.filter(layer=>layer.layerId!==layerId);
        const nextState={selectedLayerId:layers[0]?.layerId??null,layers};
        setIntervalTieInByTrackId(current=>({...current,[intervalTieInHostTrackId]:nextState}));
        if(intervalTieInSelectedLayerId===layerId){setIntervalTieInSelectedLayerId(null);setIntervalTieInDraft(newIntervalTieInLayer(layers.length+1));setIntervalTieInDraftMode(null);}
        publishIntervalTieInPreview(nextState,null);
    };
    const toggleIntervalTieInLayerEnabled=(layerId:string,enabled:boolean)=>{
        if(!intervalTieInHostTrackId)return;
        const state=tieInStateForHost();
        const nextState={...state,layers:state.layers.map(layer=>layer.layerId===layerId?{...layer,enabled}:layer)};
        setIntervalTieInByTrackId(current=>({...current,[intervalTieInHostTrackId]:nextState}));
        setIntervalTieInDraft(current=>current.layerId===layerId?{...current,enabled}:current);
        publishIntervalTieInPreview(nextState,null);
    };
    const toggleIntervalTieInLayerExpanded=(layerId:string)=>{
        setIntervalTieInExpandedLayerIds(current=>{const next=new Set(current);if(next.has(layerId))next.delete(layerId);else next.add(layerId);return next;});
    };
    const cancelIntervalTieInPick=()=>{
        window.dispatchEvent(new CustomEvent(
            CURVE_FILL_MD_PICK_CANCEL_EVENT,
            {detail:{token:intervalTieInPickTokenRef.current}},
        ));
        setIntervalTieInPickField(null);
        setIntervalTieInPickError(null);
    };

    const startIntervalTieInPick=(field:IntervalTieInField)=>{
        const target=(field==='upperA'||field==='lowerA')
            ? selectedTieInNeighbours.trackA
            : selectedTieInNeighbours.trackB;
        if(!target)return;
        if(intervalTieInPickField)cancelIntervalTieInPick();
        setIntervalTieInPickError(null);
        setIntervalTieInPickField(field);
        window.dispatchEvent(new CustomEvent(CURVE_FILL_MD_PICK_REQUEST_EVENT,{
            detail:{
                token:intervalTieInPickTokenRef.current,
                field:'from',
                allowedTrackId:target.trackId,
            },
        }));
    };

    const intervalTieInPickTarget=useMemo(()=>{
        if(!intervalTieInPickField)return null;
        const trackSide=(intervalTieInPickField==='upperA'||intervalTieInPickField==='lowerA')?'A':'B';
        const boundary=intervalTieInPickField.startsWith('upper')?'Upper':'Lower';
        const track=trackSide==='A'?selectedTieInNeighbours.trackA:selectedTieInNeighbours.trackB;
        return track?{trackSide,boundary,track}:null;
    },[intervalTieInPickField,selectedTieInNeighbours.trackA,selectedTieInNeighbours.trackB]);

    useEffect(()=>{
        const handleResult=(event:Event)=>{
            const detail=(event as CustomEvent<{token?:string;depth?:number}>).detail;
            if(!intervalTieInPickField||detail?.token!==intervalTieInPickTokenRef.current||typeof detail.depth!=='number'||!Number.isFinite(detail.depth))return;
            const field=intervalTieInPickField;
            const pickedDepth=Math.round(detail.depth*100)/100;
            updateIntervalTieInDraft({[field]:pickedDepth});
            setIntervalTieInPickError(null);
            setIntervalTieInPickField(null);
        };
        const handleWrongTrack=(event:Event)=>{
            const detail=(event as CustomEvent<{token?:string;expectedTrackId?:string;actualTrackId?:string}>).detail;
            if(detail?.token!==intervalTieInPickTokenRef.current||!intervalTieInPickTarget)return;
            setIntervalTieInPickError(
                `Pick ${intervalTieInPickTarget.boundary} Track ${intervalTieInPickTarget.trackSide} in T${intervalTieInPickTarget.track.trackIndex+1} ${intervalTieInPickTarget.track.title}.`,
            );
        };
        window.addEventListener(CURVE_FILL_MD_PICK_RESULT_EVENT,handleResult as EventListener);
        window.addEventListener('wlv:curve-fill-md-pick-wrong-track',handleWrongTrack as EventListener);
        return()=>{
            window.removeEventListener(CURVE_FILL_MD_PICK_RESULT_EVENT,handleResult as EventListener);
            window.removeEventListener('wlv:curve-fill-md-pick-wrong-track',handleWrongTrack as EventListener);
        };
    },[intervalTieInPickField,intervalTieInPickTarget]);

    const openIntervalBuilder=(
        mode:'create'|'edit'='create',
        initialTab?:IntervalBuilderTab,
        portalTarget:HTMLElement|null=null,
        embedded=false,
    )=>{
        setIntervalBuilderPortalTarget(portalTarget);
        setIntervalBuilderEmbedded(embedded);
        // Picker state is transient. Clear any stranded shared picker before
        // opening an Interval/Tie-in editing session; durable Tie-in data lives
        // independently in the Interval builder payload.
        window.dispatchEvent(new CustomEvent(CURVE_FILL_MD_PICK_CANCEL_EVENT));
        const loadedColumns=loadIntervalBuilderColumns();
        const openingBlankTrack=
            mode==='edit'
            && selectedTrack?.trackType==='interval'
            && selectedTrack.rendererType==='interval_blank';
        setIntervalBuilderColumns(
            openingBlankTrack
                ? loadedColumns.map(column=>({...column,enabled:false}))
                : loadedColumns,
        );
        setIntervalFormationConfig(loadIntervalFormationConfig());
        setIntervalDescriptionConfig(loadIntervalDescriptionConfig());
        const storedTieIns=loadIntervalTieInByTrackId();
        const hostTrackId=selectedTrack?.trackType==='interval'?selectedTrack.trackId:null;
        let workingTieIns=storedTieIns;
        let selectedLayer:IntervalTieInLayer|null=null;
        if(hostTrackId){
            const state=normalizeIntervalTieInLayerState(storedTieIns[hostTrackId]);
            selectedLayer=state.layers.find(layer=>layer.layerId===state.selectedLayerId)??state.layers[0]??null;
            workingTieIns={...storedTieIns,[hostTrackId]:{...state,selectedLayerId:selectedLayer?.layerId??null}};
        }
        setIntervalTieInByTrackId(workingTieIns);
        setIntervalTieInHostTrackId(hostTrackId);
        setIntervalTieInSelectedLayerId(selectedLayer?.layerId??null);
        setIntervalTieInDraft(selectedLayer?{...selectedLayer}:newIntervalTieInLayer(1));
        setIntervalTieInDraftMode(selectedLayer?'style':null);
        setIntervalTieInCreationMethod('manual');
        replaceIntervalTieInTopSelection(new Set());
        intervalTieInTopMatchByMarkerIdRef.current={};
        setIntervalTieInTopMatchByMarkerId({});
        setIntervalTieInExpandedLayerIds(new Set(selectedLayer?[selectedLayer.layerId]:[]));
        setIntervalTieInPickField(null);
        if(hostTrackId){
            const state=normalizeIntervalTieInLayerState(workingTieIns[hostTrackId]);
            window.dispatchEvent(new CustomEvent(INTERVAL_TIE_IN_PREVIEW_EVENT,{detail:{trackId:hostTrackId,state}}));
        }
        const loadedDepthConfig=loadIntervalDepthConfig();
        setIntervalDepthConfig({
            ...loadedDepthConfig,
            lineMode:loadedDepthConfig.lineMode==='source'?'draw':loadedDepthConfig.lineMode,
            lineColorMode:loadedDepthConfig.lineColorMode==='adjacent'?'custom':loadedDepthConfig.lineColorMode,
        });
        setIntervalBuilderMode(mode);
        if(initialTab){
            setIntervalBuilderTab(initialTab);
        }
        setIntervalBuilderPosition(clampIntervalBuilderPosition({
            top:Math.max(32,Math.round(window.innerHeight*0.07)),
            left:Math.max(40,Math.round(window.innerWidth*0.10)),
        }));
        setIntervalBuilderOpen(true);
    };
    useEffect(()=>{
        const openEditor=(event:Event)=>{
            const detail=(event as CustomEvent<{
                tab?:IntervalBuilderTab;
                portalTarget?:HTMLElement|null;
                embedded?:boolean;
            }>).detail;
            openIntervalBuilder(
                'edit',
                detail?.tab,
                detail?.portalTarget??null,
                Boolean(detail?.embedded),
            );
        };
        window.addEventListener('wlv:open-interval-track-editor',openEditor);
        return ()=>window.removeEventListener('wlv:open-interval-track-editor',openEditor);
    },[selectedTrack]);
    useEffect(()=>{
        if(intervalBuilderTab!=='tie_in'&&intervalTieInPickField){
            cancelIntervalTieInPick();
        }
    },[intervalBuilderTab,intervalTieInPickField]);
    const closeIntervalBuilder=()=>{
        intervalBuilderDragRef.current=null;
        if(intervalTieInPickField)cancelIntervalTieInPick();
        endIntervalTieInPreview();
        setIntervalTieInHostTrackId(null);
        setIntervalTieInSelectedLayerId(null);
        setIntervalTieInDraftMode(null);
        setIntervalBuilderOpen(false);
        setIntervalBuilderPortalTarget(null);
        setIntervalBuilderEmbedded(false);
        window.dispatchEvent(new CustomEvent(INTERVAL_DESCRIPTION_PREVIEW_END_EVENT));
    };
    const startIntervalBuilderDrag=(event:ReactMouseEvent<HTMLElement>)=>{
        if((event.target as HTMLElement).closest('button'))return;
        event.preventDefault();
        intervalBuilderDragRef.current={
            startClientX:event.clientX,
            startClientY:event.clientY,
            startLeft:intervalBuilderPosition.left,
            startTop:intervalBuilderPosition.top,
        };
    };
    useEffect(()=>{
        if(!intervalBuilderOpen)return undefined;
        const onMouseMove=(event:MouseEvent)=>{
            const drag=intervalBuilderDragRef.current;
            if(!drag)return;
            setIntervalBuilderPosition(clampIntervalBuilderPosition({
                top:drag.startTop+event.clientY-drag.startClientY,
                left:drag.startLeft+event.clientX-drag.startClientX,
            }));
        };
        const onMouseUp=()=>{intervalBuilderDragRef.current=null;};
        const onKeyDown=(event:KeyboardEvent)=>{
            if(event.key==='Escape'&&intervalTieInPickField){
                event.preventDefault();
                event.stopPropagation();
                cancelIntervalTieInPick();
            }
            // Outside pick mode, no Escape-to-close: this modal persists until Cancel or X.
        };
        window.addEventListener('mousemove',onMouseMove);
        window.addEventListener('mouseup',onMouseUp);
        document.addEventListener('keydown',onKeyDown,true);
        return ()=>{
            window.removeEventListener('mousemove',onMouseMove);
            window.removeEventListener('mouseup',onMouseUp);
            document.removeEventListener('keydown',onKeyDown,true);
        };
    },[intervalBuilderOpen,intervalBuilderPosition.left,intervalBuilderPosition.top,intervalTieInPickField]);
    const updateIntervalBuilderColumn=(key:IntervalBuilderColumnKey,patch:Partial<IntervalBuilderColumn>)=>setIntervalBuilderColumns(current=>current.map(column=>column.key===key?{...column,...patch}:column));
    const moveIntervalBuilderColumn=(key:IntervalBuilderColumnKey,delta:-1|1)=>setIntervalBuilderColumns(current=>{const index=current.findIndex(column=>column.key===key);const target=index+delta;if(index<0||target<0||target>=current.length)return current;const next=[...current];[next[index],next[target]]=[next[target],next[index]];return next;});
    const allLoadedFormationMarkers=formationTopDatasets.flatMap(dataset=>dataset.markers);
    const loadedFormationSelectedIds=intervalFormationConfig.selectionMode==='all'
        ? new Set(allLoadedFormationMarkers.map(marker=>marker.markerId))
        : new Set(intervalFormationConfig.selectedMarkerIds);
    const updateIntervalFormationConfig=(patch:Partial<IntervalFormationConfig>)=>setIntervalFormationConfig(current=>({...current,...patch}));
    const toggleIntervalFormationMarker=(markerId:string,checked:boolean)=>setIntervalFormationConfig(current=>{
        const next=new Set(current.selectedMarkerIds);
        if(checked)next.add(markerId);else next.delete(markerId);
        return {...current,selectedMarkerIds:Array.from(next)};
    });
    const addManualFormationTop=()=>{
        const name=manualTopName.trim();
        const md=manualTopMd.trim();
        if(!name||!md||!Number.isFinite(Number(md)))return;
        setIntervalFormationConfig(current=>({
            ...current,
            manualTops:[
                ...current.manualTops,
                {id:`manual-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,name,md,group:manualTopGroup.trim()},
            ],
        }));
        setManualTopName('');
        setManualTopMd('');
        setManualTopGroup('');
    };
    const deleteManualFormationTop=(id:string)=>setIntervalFormationConfig(current=>({
        ...current,
        manualTops:current.manualTops.filter(top=>top.id!==id),
    }));
    const existingIntervalBoundarySources=intervalTracks.map((track)=>({
        id:`track:${track.trackId}`,
        label:`Formation – T${track.trackIndex+1}`,
    }));
    const configuredBoundarySources=intervalBuilderColumns
        .map((column,index)=>({column,index}))
        .filter(({column})=>column.enabled&&column.key!=='depth'&&['formation','lithology','colour_band'].includes(column.key))
        .map(({column,index})=>({
            id:`column:${column.key}`,
            label:`${column.title||column.label} – T${index+1}`,
        }));
    const depthBoundarySources=[
        ...existingIntervalBoundarySources,
        ...configuredBoundarySources.filter((candidate)=>!existingIntervalBoundarySources.some((existing)=>existing.label===candidate.label)),
    ];
    const updateIntervalDepthConfig=(patch:Partial<IntervalDepthConfig>)=>setIntervalDepthConfig(current=>({...current,...patch}));

    const updateIntervalDescriptionConfig=(
        patch:Partial<IntervalDescriptionConfig>,
    )=>setIntervalDescriptionConfig(
        current=>({...current,...patch}),
    );

    useEffect(() => {
        if (!intervalBuilderOpen || intervalBuilderTab !== 'descriptions') return;
        const descriptionColumn = intervalBuilderColumns.find(
            column => column.key === 'descriptions',
        );
        if (!descriptionColumn) return;
        window.dispatchEvent(new CustomEvent<IntervalDescriptionPreviewDetail>(
            INTERVAL_DESCRIPTION_PREVIEW_EVENT,
            {
                detail: {
                    config: intervalDescriptionConfig,
                    column: descriptionColumn,
                },
            },
        ));
    }, [
        intervalBuilderOpen,
        intervalBuilderTab,
        intervalBuilderColumns,
        intervalDescriptionConfig,
    ]);

    const enabledIntervalColumns=intervalBuilderColumns.filter(column=>column.enabled);
    const applyIntervalBuilderColumns=async()=>{
        if(intervalTieInPickField)cancelIntervalTieInPick();
        let nextTieIns=intervalTieInByTrackId;
        let committedDraft:IntervalTieInLayer|null=null;
        if(intervalTieInHostTrackId){
            const state=normalizeIntervalTieInLayerState(intervalTieInByTrackId[intervalTieInHostTrackId]);
            if(intervalTieInDraftMode==='new'){
                const complete=intervalTieInDraft.upperA!==null&&intervalTieInDraft.upperB!==null&&intervalTieInDraft.lowerA!==null&&intervalTieInDraft.lowerB!==null;
                if(complete){
                    committedDraft={...intervalTieInDraft};
                    const layers=[...state.layers,committedDraft];
                    nextTieIns={...intervalTieInByTrackId,[intervalTieInHostTrackId]:{selectedLayerId:committedDraft.layerId,layers}};
                    setIntervalTieInSelectedLayerId(committedDraft.layerId);
                    setIntervalTieInDraftMode('style');
                    setIntervalTieInExpandedLayerIds(current=>new Set(current).add(committedDraft!.layerId));
                }
            }else if(intervalTieInDraftMode==='style'&&intervalTieInSelectedLayerId){
                const original=state.layers.find(layer=>layer.layerId===intervalTieInSelectedLayerId);
                if(original){
                    // Geometry is immutable after first commit.
                    committedDraft={...intervalTieInDraft,upperA:original.upperA,upperB:original.upperB,lowerA:original.lowerA,lowerB:original.lowerB};
                    nextTieIns={...intervalTieInByTrackId,[intervalTieInHostTrackId]:{selectedLayerId:committedDraft.layerId,layers:state.layers.map(layer=>layer.layerId===committedDraft!.layerId?committedDraft!:layer)}};
                }
            }
        }
        setIntervalTieInByTrackId(nextTieIns);
        persistIntervalBuilderState(intervalBuilderColumns,nextTieIns);
        if(intervalTieInHostTrackId){
            const committedState=normalizeIntervalTieInLayerState(nextTieIns[intervalTieInHostTrackId]);
            if(committedDraft)setIntervalTieInDraft({...committedDraft});
            publishIntervalTieInPreview(committedState,committedDraft);
        }
        window.dispatchEvent(new CustomEvent(INTERVAL_TIE_IN_CONFIG_CHANGED_EVENT));
        window.dispatchEvent(new CustomEvent(INTERVAL_STORAGE_COMMITTED_EVENT));
        window.localStorage.setItem(
            INTERVAL_FORMATION_STORAGE_KEY,
            JSON.stringify(intervalFormationConfig),
        );
        window.localStorage.setItem(
            INTERVAL_DEPTH_STORAGE_KEY,
            JSON.stringify(intervalDepthConfig),
        );
        window.localStorage.setItem(
            INTERVAL_DESCRIPTION_STORAGE_KEY,
            JSON.stringify(intervalDescriptionConfig),
        );
        window.dispatchEvent(
            new CustomEvent('wlv:interval-formation-config-changed'),
        );
        window.dispatchEvent(
            new CustomEvent('wlv:interval-depth-config-changed'),
        );
        window.dispatchEvent(
            new CustomEvent('wlv:interval-description-config-changed'),
        );
        if(
            intervalBuilderTab!=='tie_in'
            && intervalBuilderMode==='edit'
            && selectedTrack?.trackType==='interval'
            && onConfigureIntervalTrack
        ){
            const intervalColumn=
                enabledIntervalColumns.find(column=>column.key==='descriptions')
                ?? (enabledIntervalColumns.length===1
                    ? enabledIntervalColumns[0]
                    : enabledIntervalColumns.find(column=>column.key==='depth')
                      ?? enabledIntervalColumns[0]
                      ?? null);

            if(intervalColumn){
                const rendererType=
                    intervalColumn.key==='depth'
                        ? 'interval_depth'
                        : intervalColumn.key==='descriptions'
                          ? 'interval_core_description'
                          : 'interval_stratigraphy';
                const trackRole=
                    intervalColumn.key==='depth'
                        ? 'interval_depth'
                        : intervalColumn.key==='descriptions'
                          ? 'core_description'
                          : 'geological_interval';
                const trackName=
                    intervalColumn.title
                    || (
                        intervalColumn.key==='depth'
                            ? 'MD'
                            : intervalColumn.key==='descriptions'
                              ? 'Core Description'
                              : 'Formation'
                    );
                const widthPx=Math.max(
                    1,
                    intervalColumn.width||1,
                );

                await onConfigureIntervalTrack(
                    selectedTrack.trackId,
                    {
                        trackName,
                        rendererType,
                        trackRole,
                        widthPx,
                    },
                );
            }
        }

        // Apply is a commit checkpoint; keep the modal open for continued live adjustment.
    };

    useEffect(()=>{
        const applyEmbedded=(event:Event)=>{
            if(!intervalBuilderOpen||!intervalBuilderEmbedded)return;
            const detail=(event as CustomEvent<{
                resolve?:()=>void;
                reject?:(error:unknown)=>void;
            }>).detail;
            void applyIntervalBuilderColumns()
                .then(()=>detail?.resolve?.())
                .catch(error=>detail?.reject?.(error));
        };
        const cancelEmbedded=()=>{
            if(!intervalBuilderOpen||!intervalBuilderEmbedded)return;
            closeIntervalBuilder();
        };
        window.addEventListener('wlv:apply-interval-track-editor',applyEmbedded);
        window.addEventListener('wlv:cancel-interval-track-editor',cancelEmbedded);
        return ()=>{
            window.removeEventListener('wlv:apply-interval-track-editor',applyEmbedded);
            window.removeEventListener('wlv:cancel-interval-track-editor',cancelEmbedded);
        };
    },[
        intervalBuilderOpen,
        intervalBuilderEmbedded,
        intervalBuilderTab,
        intervalBuilderColumns,
        intervalTieInByTrackId,
        intervalTieInHostTrackId,
        intervalTieInDraftMode,
        intervalTieInDraft,
        intervalTieInSelectedLayerId,
        intervalFormationConfig,
        intervalDepthConfig,
        intervalDescriptionConfig,
        selectedTrack,
        enabledIntervalColumns,
    ]);

    const addTrackLabel = 'Add track';
    const eligibleLayoutRecommendations = layoutRecommendations.filter((item) => item.is_eligible);
    const layoutRecommendationOptions = eligibleLayoutRecommendations.length > 0 ? eligibleLayoutRecommendations : layoutRecommendations;
    const layoutPresetPlaceholder = layoutRecommendationsLoading
        ? 'Loading KR presets...'
        : layoutRecommendationsError
            ? 'Template service unavailable'
            : layoutRecommendationOptions.length > 0
                ? 'Layout Preset ▾'
                : 'Not Available';
    const addTrackBuilder = builderOpen ? createPortal(<div className="wlv-add-track-builder wlv-add-track-builder-draggable" role="dialog" aria-label="Add Track Builder" style={{ top: panelPosition.top, left: panelPosition.left }}>
      <div className="builder-heading builder-drag-handle" onMouseDown={startPanelDrag}>
        <strong>Add Track</strong>
        <button type="button" onMouseDown={(event) => event.stopPropagation()} onClick={closeAddTrackBuilder} aria-label="Close Add Track Builder">
          ×
        </button>
      </div>

      <section className="builder-section">
        <div className="builder-label">Track type</div>
        <div className="builder-choice-grid">
          <button type="button" className={draft.trackType === 'depth' ? 'active' : ''} onClick={() => selectTrackType('depth')}>
            Depth
          </button>
          <button type="button" className={draft.trackType === 'curve' ? 'active' : ''} onClick={() => selectTrackType('curve')}>
            Curve
          </button>
          <button type="button" className={draft.trackType === 'interval' ? 'active' : ''} onClick={() => selectTrackType('interval')}>Interval</button>
          <button type="button" className={draft.trackType === 'core' ? 'active' : ''} onClick={() => selectTrackType('core')}>Core</button>
          <button type="button" className={draft.trackType === 'completion' ? 'active' : ''} onClick={() => selectTrackType('completion')}>Completion</button>
          <button type="button" disabled title="Reserved for raster log images">Raster</button>
        </div>
      </section>

      {draft.trackType === 'depth' && (<section className="builder-section">
          <div className="builder-label">Depth subtype</div>
          <div className="builder-choice-grid three">
            {(['MD', 'TVD', 'TVDSS'] as DepthBasis[]).map((basis) => (<button key={basis} type="button" className={draft.depthBasis === basis ? 'active' : ''} onClick={() => updateDraft({ depthBasis: basis })}>
                {basis}
              </button>))}
          </div>
          <p className="builder-note">TVD/TVDSS are mock-enabled here; backend validation will eventually decide availability.</p>
        </section>)}

      {draft.trackType === 'curve' && (<>
          <section className="builder-section">
            <div className="builder-label">Curve source</div>
            <div className="builder-choice-grid two">
              <button type="button" className={draft.curveSource === 'empty' ? 'active' : ''} onClick={() => selectCurveSource('empty')}>
                Empty
              </button>
              <button type="button" className={draft.curveSource === 'selected' ? 'active' : ''} onClick={() => selectCurveSource('selected')}>
                From selected ({pendingAddTrackCurveCount})
              </button>
            </div>
          </section>

          <section className="builder-section">
            <div className="builder-label">Lattice</div>
            <select value={draft.latticeMode} onChange={(event) => updateDraft({ latticeMode: event.target.value as AddTrackDraft['latticeMode'] })}>
              <option value="auto">Auto from front curve</option>
              <option value="linear">Linear override</option>
              <option value="logarithmic">Logarithmic override</option>
            </select>
          </section>

          <section className="builder-section">
            <div className="builder-label">Scale mode</div>
            <select value={draft.scaleMode} onChange={(event) => updateDraft({ scaleMode: event.target.value as ScaleMode })}>
              <option value="shared">Shared</option>
              <option value="per_curve">Per curve</option>
              <option value="dual">Dual</option>
            </select>
          </section>
        </>)}

      {draft.trackType === 'core' && (<section className="builder-section">
          <div className="builder-label">Core source</div>
          <div className="builder-note">Create the Core track, then select published images from Core Image Inventory.</div>
        </section>)}

      {draft.trackType === 'interval' && (<section className="builder-section">
          <div className="builder-label">Initial state</div>
          <div className="builder-note">Creates a blank Interval track. Configure the selected track after it is added.</div>
        </section>)}

      {draft.trackType === 'completion' && (<section className="builder-section">
          <div className="builder-label">Completion source</div>
          <div className="builder-note">Displays the reviewed Completion Components dataset published to MWD for the track's owning well.</div>
        </section>)}

      <section className="builder-section">
        <div className="builder-label">Insert position</div>
        <select value={draft.insertMode} onChange={(event) => updateDraft({ insertMode: event.target.value as AddTrackDraft['insertMode'] })}>
          <option value="before_selected">Before active track</option>
          <option value="after_selected">After active track</option>
          <option value="far_right">Far right</option>
        </select>
      </section>

      <div className="builder-actions">
        <button type="button" onClick={closeAddTrackBuilder}>Cancel</button>
        <button type="button" className="builder-primary" onClick={() => {
            onAddTrack({
                ...draft,
                // Placement is relative to the track that is active at the
                // instant the user commits Add Track.  Do not rely on a
                // reference captured earlier while the builder was open.
                referenceTrackId: selectedTrack?.trackId ?? null,
            });
            closeAddTrackBuilder();
        }}>
          {addTrackLabel}
        </button>
      </div>
    </div>, document.body) : null;
    const intervalColumnBuilder=intervalBuilderOpen?createPortal(
<div className={intervalBuilderEmbedded?'wlv-interval-builder-embedded':'wlv-interval-builder-backdrop'}>
{intervalBuilderTab==='tie_in'&&intervalTieInPickField&&intervalTieInPickTarget?<section className="wlv-tie-in-pick-bar" role="status" aria-live="polite">
<div className="wlv-tie-in-pick-bar__copy">
<strong>{`Pick ${intervalTieInPickTarget.boundary} · Track ${intervalTieInPickTarget.trackSide}`}</strong>
<span>{`T${intervalTieInPickTarget.track.trackIndex+1} ${intervalTieInPickTarget.track.title}`}</span>
<em>{intervalTieInPickError??'Click the required MD in the indicated track. The editor returns after the pick.'}</em>
</div>
<button type="button" onClick={cancelIntervalTieInPick}>Cancel Pick</button>
</section>:null}
<section
className={`wlv-interval-builder-modal${intervalBuilderEmbedded?' is-embedded':''}${intervalBuilderTab==='tie_in'&&intervalTieInPickField?' is-tie-in-picking':''}`}
role={intervalBuilderEmbedded?undefined:'dialog'}
aria-label={intervalBuilderEmbedded?undefined:'Configure Interval Columns'}
style={intervalBuilderEmbedded?undefined:{top:intervalBuilderPosition.top,left:intervalBuilderPosition.left}}
>
{!intervalBuilderEmbedded?<header className="wlv-interval-builder-heading" onMouseDown={startIntervalBuilderDrag}><strong>{intervalBuilderMode==='edit'?'Edit Interval Track':'Configure Interval Columns'}</strong><button type="button" onMouseDown={event=>event.stopPropagation()} onClick={closeIntervalBuilder}>×</button></header>:null}
{!intervalBuilderEmbedded?<nav className="wlv-interval-builder-tabs">{[...intervalBuilderColumns.map(column=>({key:column.key,label:column.label})),{key:'tie_in' as const,label:'Tie-in'}].map(column=><button key={column.key} type="button" className={intervalBuilderTab===column.key?'active':''} onClick={()=>setIntervalBuilderTab(column.key)}>{column.label}</button>)}</nav>:null}
<div className="wlv-interval-builder-body">{intervalBuilderTab==='tie_in'?<div className="wlv-interval-builder-panel wlv-edit-track-overlay-panel wlv-curve-edit-modal-body wlv-tie-in-panel">
<section className="wlv-edit-track-overlay-style-panel">
<header className="wlv-edit-track-overlay-style-header">
<div><h3>Tie-in Correlation Layers</h3><p>Create a correlation once, then manage it as a saved visual layer. Saved correlation MDs are read-only.</p></div>
<button type="button" onClick={addIntervalTieInLayer}>+ Add Tie-in</button>
</header>
<div className="wlv-edit-track-overlay-style-body">
{intervalTieInDraftMode?<section className="wlv-edit-track-overlay-section wlv-tie-in-correlation-section"><h4>{intervalTieInDraftMode==='new'?'New Tie-in correlation':'Tie-in appearance'}</h4>
{intervalTieInDraftMode==='new'?<>
<div className="wlv-tie-in-method-row">
<strong>Tie method</strong>
<label><input type="radio" name="wlv-tie-in-method" checked={intervalTieInCreationMethod==='manual'} onChange={()=>setIntervalTieInCreationMethod('manual')}/><span>Manual MD</span></label>
<label><input type="radio" name="wlv-tie-in-method" checked={intervalTieInCreationMethod==='formation_tops'} onChange={()=>setIntervalTieInCreationMethod('formation_tops')}/><span>Formation Tops</span></label>
</div>
{intervalTieInCreationMethod==='manual'?<>
<div className="wlv-tie-in-correlation-table"><div className="wlv-tie-in-correlation-head"><span></span><span>{selectedTieInNeighbours.trackA?`Track A · T${selectedTieInNeighbours.trackA.trackIndex+1}`:'Track A'}</span><span></span><span>{selectedTieInNeighbours.trackB?`Track B · T${selectedTieInNeighbours.trackB.trackIndex+1}`:'Track B'}</span></div>{([['Upper','upperA','upperB'],['Lower','lowerA','lowerB']] as const).map(([label,aField,bField])=><div key={label} className="wlv-tie-in-correlation-row"><strong>{label}</strong><span className="wlv-tie-in-md-field"><input type="number" step="0.01" value={intervalTieInDraft[aField]??''} placeholder="MD" disabled={!selectedTieInNeighbours.trackA} onChange={event=>updateIntervalTieInDraft({[aField]:event.target.value===''?null:Number(event.target.value)})}/><button type="button" className={`wlv-tie-in-pick-button${intervalTieInPickField===aField?' is-active':''}`} disabled={!selectedTieInNeighbours.trackA} onClick={()=>startIntervalTieInPick(aField)}>Pick</button></span><span aria-hidden="true">→</span><span className="wlv-tie-in-md-field"><input type="number" step="0.01" value={intervalTieInDraft[bField]??''} placeholder="MD" disabled={!selectedTieInNeighbours.trackB} onChange={event=>updateIntervalTieInDraft({[bField]:event.target.value===''?null:Number(event.target.value)})}/><button type="button" className={`wlv-tie-in-pick-button${intervalTieInPickField===bField?' is-active':''}`} disabled={!selectedTieInNeighbours.trackB} onClick={()=>startIntervalTieInPick(bField)}>Pick</button></span></div>)}</div>
<div className="wlv-property-note">Apply Changes commits this correlation as an immutable Tie-in layer.</div>
</>:<div className="wlv-tie-in-formation-top-picker">
<div className="wlv-tie-in-formation-actions"><span>{selectedTieInNeighbours.trackA?`T${selectedTieInNeighbours.trackA.trackIndex+1} ${selectedTieInNeighbours.trackA.title}`:'Track A'} → {selectedTieInNeighbours.trackB?`T${selectedTieInNeighbours.trackB.trackIndex+1} ${selectedTieInNeighbours.trackB.title}`:'Track B'}</span><div><button type="button" onClick={()=>replaceIntervalTieInTopSelection(new Set(formationTopTieRows.map((row:FormationTopTieRow)=>row.markerA.markerId)))}>Select All</button><button type="button" onClick={()=>replaceIntervalTieInTopSelection(new Set())}>None</button><button type="button" className="builder-primary" disabled={intervalTieInTopSelection.size===0} onClick={addFormationTopTieInLayers}>Add Tie-ins</button></div></div>
<div className="wlv-tie-in-formation-grid wlv-tie-in-formation-grid--head"><span></span><span>Track A top</span><span>MD</span><span>Track B top</span><span>MD</span><span>Status</span></div>
<div className="wlv-tie-in-formation-list">
{formationTopTieRows.length===0?<div className="wlv-property-note">Formation Tops are not available for one or both adjacent track wells.</div>:formationTopTieRows.map((row:FormationTopTieRow)=>{
 const trackB=selectedTieInNeighbours.trackB;
 const markersB:FormationTopMarker[]=trackB?.managedWellUid?formationTopMarkersByWellUid[trackB.managedWellUid]??[]:[];
 const selectedMarkerId=intervalTieInTopMatchByMarkerId[row.markerA.markerId]??row.suggestedMarkerB?.markerId??'';
 const selectedMarkerB=markersB.find((candidate:FormationTopMarker)=>candidate.markerId===selectedMarkerId)??null;
 return <div key={row.markerA.markerId} className="wlv-tie-in-formation-grid"><input type="checkbox" checked={intervalTieInTopSelection.has(row.markerA.markerId)} onChange={event=>setIntervalTieInTopSelected(row.markerA.markerId,event.target.checked)}/><span title={row.markerA.markerName}>{row.markerA.markerName}</span><span>{Number(row.markerA.md).toFixed(2)}</span><select value={selectedMarkerId} onChange={event=>setIntervalTieInTopMatch(row.markerA.markerId,event.target.value)}><option value="">Choose…</option>{markersB.map((markerB:FormationTopMarker)=><option key={markerB.markerId} value={markerB.markerId}>{markerB.markerName}</option>)}</select><span>{selectedMarkerB?Number(selectedMarkerB.md).toFixed(2):'—'}</span><span>{selectedMarkerB?(selectedMarkerB.markerId===row.suggestedMarkerB?.markerId?row.status:'Manual'):'Choose'}</span></div>;
})}
</div>
<div className="wlv-property-note">Exact and conservative name matches are suggested. Different names remain selectable manually.</div>
{intervalTieInPickError?<div className="wlv-property-note wlv-tie-in-error" role="alert">{intervalTieInPickError}</div>:null}
</div>}
</>:<div className="wlv-property-note">{`Geometry locked: Upper ${intervalTieInDraft.upperA??'—'} → ${intervalTieInDraft.upperB??'—'} MD · Lower ${intervalTieInDraft.lowerA??'—'} → ${intervalTieInDraft.lowerB??'—'} MD`}</div>}
</section>:null}
{intervalTieInDraftMode?<section className="wlv-edit-track-overlay-section wlv-tie-in-line-section"><CurveLineStyleControl value={intervalTieInDraft.line} onPreview={line=>updateIntervalTieInDraft({line})} onCommit={line=>updateIntervalTieInDraft({line})}/></section>:null}
{intervalTieInDraftMode && !(intervalTieInDraftMode==='new'&&intervalTieInCreationMethod==='formation_tops')?<section className="wlv-edit-track-overlay-section wlv-tie-in-infill-section"><h4>Infill Options</h4><label className="wlv-checkbox-row"><input type="checkbox" checked={intervalTieInDraft.fillEnabled} onChange={event=>updateIntervalTieInDraft({fillEnabled:event.target.checked})}/><span>Show interval infill</span></label><div className="wlv-tie-in-infill-bounds"><label><span>Bounds</span><select disabled={!intervalTieInDraft.fillEnabled} value={intervalTieInDraft.fillDepthExtent} onChange={event=>updateIntervalTieInDraft({fillDepthExtent:event.target.value as IntervalTieInConfig['fillDepthExtent']})}><option value="correlation">Correlation</option><option value="specified_interval">MD interval</option><option value="formation_tops">Formation Tops</option></select></label>{intervalTieInDraft.fillDepthExtent==='specified_interval'?<div className="wlv-tie-in-infill-bound-grid"><strong>Upper</strong><input type="number" step="0.01" value={intervalTieInDraft.fillUpperA??''} placeholder="A MD" onChange={event=>updateIntervalTieInDraft({fillUpperA:event.target.value===''?null:Number(event.target.value)})}/><span>→</span><input type="number" step="0.01" value={intervalTieInDraft.fillUpperB??''} placeholder="B MD" onChange={event=>updateIntervalTieInDraft({fillUpperB:event.target.value===''?null:Number(event.target.value)})}/><strong>Lower</strong><input type="number" step="0.01" value={intervalTieInDraft.fillLowerA??''} placeholder="A MD" onChange={event=>updateIntervalTieInDraft({fillLowerA:event.target.value===''?null:Number(event.target.value)})}/><span>→</span><input type="number" step="0.01" value={intervalTieInDraft.fillLowerB??''} placeholder="B MD" onChange={event=>updateIntervalTieInDraft({fillLowerB:event.target.value===''?null:Number(event.target.value)})}/></div>:null}{intervalTieInDraft.fillDepthExtent==='formation_tops'?<div className="wlv-tie-in-infill-top-bounds"><label><span>Upper</span><select value={selectedTieInFillTopPairKey} onChange={event=>applyTieInFormationFillBoundary('top',event.target.value)}><option value="">Select top</option>{formationTopBoundPairs.map(pair=><option key={`top-${pair.key}`} value={pair.key}>{pair.label}</option>)}</select></label><label><span>Lower</span><select disabled={!selectedTieInFillTopPairKey} value={selectedTieInFillBasePairKey} onChange={event=>applyTieInFormationFillBoundary('base',event.target.value)}><option value="">Select base</option>{formationTopBoundPairs.filter(pair=>!intervalTieInDraft.fillUpperA||pair.markerA.md>intervalTieInDraft.fillUpperA).map(pair=><option key={`base-${pair.key}`} value={pair.key}>{pair.label}</option>)}</select></label></div>:null}</div><SharedInfillEditor disabled={!intervalTieInDraft.fillEnabled} option="track" optionOptions={[{value:'track',label:'Tie-in polygon'}]} onOptionChange={()=>{}} depthExtent="entire_track" onDepthExtentChange={()=>{}} appearance={intervalTieInDraft.fillAppearance} onAppearanceChange={fillAppearance=>updateIntervalTieInDraft({fillAppearance})} patternValue={intervalTieInDraft.fillPattern} patternOptions={[{value:'diagonal',label:'Diagonal'},{value:'dots',label:'Dots'},{value:'kr-lithology',label:'KR lithology pattern'},{value:'lithology-column',label:'Loaded lithology column'}]} onPatternChange={value=>updateIntervalTieInDraft({fillPattern:value as IntervalTieInConfig['fillPattern']})} rasterValue={intervalTieInDraft.fillRasterUrl} rasterTextMode onRasterChange={fillRasterUrl=>updateIntervalTieInDraft({fillRasterUrl})} rasterFit={intervalTieInDraft.fillRasterFit} onRasterFitChange={fillRasterFit=>updateIntervalTieInDraft({fillRasterFit})} selectorKind={intervalTieInDraft.fillAppearance==='pattern'&&intervalTieInDraft.fillPattern==='kr-lithology'?'kr':intervalTieInDraft.fillAppearance==='pattern'&&intervalTieInDraft.fillPattern==='lithology-column'?'lithology-column':null} selectorContent={intervalTieInDraft.fillAppearance==='pattern'&&intervalTieInDraft.fillPattern==='kr-lithology'?<KrLithologyPatternPicker selectedId={intervalTieInDraft.fillLithologyId||null} buttonLabel="Choose KR lithology pattern" onSelect={entry=>updateIntervalTieInDraft({fillLithologyId:entry.id,fillColor:entry.colors.defaultBackground})}/>:intervalTieInDraft.fillAppearance==='pattern'&&intervalTieInDraft.fillPattern==='lithology-column'?<div className="wlv-property-note">Uses the loaded lithology column and KR patterns.</div>:null} patternScale={intervalTieInDraft.fillPatternScale} onPatternScaleChange={fillPatternScale=>updateIntervalTieInDraft({fillPatternScale})} color={intervalTieInDraft.fillColor} onColorChange={fillColor=>updateIntervalTieInDraft({fillColor})} opacity={intervalTieInDraft.fillOpacity} opacityMax={0.8} onOpacityChange={fillOpacity=>updateIntervalTieInDraft({fillOpacity})}/></section>:null}
<div className="wlv-curve-fill-layer-heading"><strong>Tie-in layers</strong><span>{intervalTieInHostTrackId?tieInStateForHost().layers.length:0}</span></div>
{intervalTieInHostTrackId&&tieInStateForHost().layers.length===0?<div className="wlv-curve-fill-empty">No saved Tie-in layers for this track.</div>:null}
{intervalTieInHostTrackId?tieInStateForHost().layers.map((layer,index)=>{const expanded=intervalTieInExpandedLayerIds.has(layer.layerId);return <div key={layer.layerId} className={`wlv-curve-fill-rule-card wlv-curve-fill-layer-card${expanded?' is-expanded':''}`}><div className="wlv-curve-fill-layer-summary" onClick={()=>toggleIntervalTieInLayerExpanded(layer.layerId)}><label className="wlv-checkbox-row wlv-curve-fill-layer-toggle" onClick={event=>event.stopPropagation()}><input type="checkbox" checked={layer.enabled} onChange={event=>toggleIntervalTieInLayerEnabled(layer.layerId,event.target.checked)}/><strong>{layer.name||`Tie-in ${index+1}`}</strong></label><button type="button" className="wlv-curve-fill-layer-summary-button" aria-expanded={expanded} onClick={event=>{event.stopPropagation();toggleIntervalTieInLayerExpanded(layer.layerId);}}><span className="wlv-curve-fill-layer-expression">{`Upper ${layer.upperA??'—'} → ${layer.upperB??'—'} · Lower ${layer.lowerA??'—'} → ${layer.lowerB??'—'} MD`}</span><span className="wlv-curve-fill-layer-paint-summary">{`${layer.fillEnabled?(layer.fillAppearance==='solid'?'Solid':layer.fillAppearance==='raster'?'Raster':layer.fillPattern==='kr-lithology'?'KR lithology':layer.fillPattern==='lithology-column'?'Lithology column':'Pattern'):'No fill'} · ${layer.fillDepthExtent==='correlation'?'Correlation bounds':layer.fillDepthExtent==='formation_tops'?'Formation Top bounds':'MD bounds'} · ${layer.line.style} line`}</span><span className="wlv-curve-fill-layer-state state-resolved">Saved</span><span aria-hidden="true" className="wlv-curve-fill-layer-chevron">{expanded?'▴':'▾'}</span></button></div>{expanded?<div className="wlv-curve-fill-layer-details"><div className="wlv-curve-fill-rule-actions"><button type="button" onClick={()=>selectIntervalTieInLayer(layer.layerId)}>Edit appearance</button><button type="button" onClick={()=>deleteIntervalTieInLayer(layer.layerId)}>Delete</button></div></div>:null}</div>}):null}
</div></section></div>:intervalBuilderColumns.filter(column=>column.key===intervalBuilderTab).map(column=><div key={column.key} className={`wlv-interval-builder-panel${column.key==='descriptions'?' wlv-interval-builder-panel--descriptions':''}`}>
{column.key!=='descriptions'&&<>
<label className="wlv-interval-builder-toggle"><input type="checkbox" checked={column.enabled} onChange={e=>updateIntervalBuilderColumn(column.key,{enabled:e.target.checked})}/><span>Add this column</span></label>
<label><span>Column title</span><input value={column.title} onChange={e=>updateIntervalBuilderColumn(column.key,{title:e.target.value})}/></label>
<label><span>Column width</span><div className="wlv-interval-builder-width"><input type="number" min="1" max="240" value={column.width} onChange={e=>updateIntervalBuilderColumn(column.key,{width:Math.max(1,Math.min(240,Number(e.target.value)||column.width))})}/><em>px</em></div></label>
</>}
{column.key==='formation'&&<div className="wlv-interval-formation-settings">
<section className="wlv-interval-setting-section">
<h4>Formation Tops Source</h4>
<div className="wlv-interval-source-options">
<label className="wlv-interval-source-option"><input type="radio" name="interval-formation-source" checked={intervalFormationConfig.sourceMode==='loaded'} onChange={()=>updateIntervalFormationConfig({sourceMode:'loaded'})}/><span>Loaded Formation Tops</span></label>
<label className="wlv-interval-source-option"><input type="radio" name="interval-formation-source" checked={intervalFormationConfig.sourceMode==='manual'} onChange={()=>updateIntervalFormationConfig({sourceMode:'manual'})}/><span>Manually Add</span></label>
</div>
{intervalFormationConfig.sourceMode==='loaded'?<div className="wlv-interval-loaded-tops">
<div className="wlv-interval-tops-selection-mode">
<label><input type="radio" name="interval-top-selection" checked={intervalFormationConfig.selectionMode==='all'} onChange={()=>updateIntervalFormationConfig({selectionMode:'all'})}/><span>All Tops</span></label>
<label><input type="radio" name="interval-top-selection" checked={intervalFormationConfig.selectionMode==='selected'} onChange={()=>updateIntervalFormationConfig({selectionMode:'selected',selectedMarkerIds:intervalFormationConfig.selectedMarkerIds.length?intervalFormationConfig.selectedMarkerIds:Array.from(selectedFormationTopIds)})}/><span>Selected Tops</span></label>
</div>
{formationTopDatasets.length===0?<p className="wlv-interval-empty-note">No Formation Tops are loaded for the active well.</p>:<div className="wlv-interval-loaded-top-list">
{formationTopDatasets.map(dataset=><section key={dataset.datasetId} className="wlv-interval-loaded-top-dataset">
<div className="wlv-interval-loaded-top-heading"><strong>{dataset.datasetLabel}</strong><span>{dataset.markers.length} tops</span></div>
{dataset.markers.map(marker=><label key={marker.markerId} className="wlv-interval-loaded-top-row">
<input type="checkbox" disabled={intervalFormationConfig.selectionMode==='all'} checked={loadedFormationSelectedIds.has(marker.markerId)} onChange={event=>toggleIntervalFormationMarker(marker.markerId,event.target.checked)}/>
<span>{marker.markerName}</span><em>{marker.md.toLocaleString(undefined,{maximumFractionDigits:1})} m MD</em>
</label>)}
</section>)}
</div>}
</div>:<div className="wlv-interval-manual-tops">
<div className="wlv-interval-manual-top-entry">
<label><span>Name</span><input value={manualTopName} onChange={event=>setManualTopName(event.target.value)}/></label>
<label><span>MD</span><input type="number" value={manualTopMd} onChange={event=>setManualTopMd(event.target.value)}/></label>
<label><span>Group (optional)</span><input value={manualTopGroup} onChange={event=>setManualTopGroup(event.target.value)}/></label>
<button type="button" onClick={addManualFormationTop}>Add</button>
</div>
{intervalFormationConfig.manualTops.length===0?<p className="wlv-interval-empty-note">No manual tops added.</p>:<div className="wlv-interval-manual-top-list">
{intervalFormationConfig.manualTops.map(top=><div key={top.id} className="wlv-interval-manual-top-row"><span>{top.name}</span><em>{Number(top.md).toLocaleString(undefined,{maximumFractionDigits:2})} m MD</em><small>{top.group||'Unassigned'}</small><button type="button" onClick={()=>deleteManualFormationTop(top.id)}>×</button></div>)}
</div>}
<p className="wlv-interval-local-note">Manual tops remain local to this Interval configuration and do not write back to MWD.</p>
</div>}
</section>

<section className="wlv-interval-setting-section">
<h4>Label Properties</h4>
<div className="wlv-interval-setting-grid">
<label className="wlv-interval-builder-toggle"><input type="checkbox" checked={intervalFormationConfig.showLabels} onChange={event=>updateIntervalFormationConfig({showLabels:event.target.checked})}/><span>Show labels</span></label>
<label><span>Font size</span><div className="wlv-interval-builder-width"><input type="number" min="7" max="24" value={intervalFormationConfig.fontSize} onChange={event=>updateIntervalFormationConfig({fontSize:Math.max(7,Math.min(24,Number(event.target.value)||11))})}/><em>px</em></div></label>
<label><span>Font colour</span><input type="color" value={intervalFormationConfig.fontColor} onChange={event=>updateIntervalFormationConfig({fontColor:event.target.value})}/></label>
<label><span>Font weight</span><select value={intervalFormationConfig.fontWeight} onChange={event=>updateIntervalFormationConfig({fontWeight:event.target.value as IntervalFormationConfig['fontWeight']})}><option value="regular">Regular</option><option value="bold">Bold</option></select></label>
<label><span>Alignment</span><select value={intervalFormationConfig.labelAlignment} onChange={event=>updateIntervalFormationConfig({labelAlignment:event.target.value as IntervalFormationConfig['labelAlignment']})}><option value="left">Left</option><option value="center">Centre</option><option value="right">Right</option></select></label>
</div>
</section>

<section className="wlv-interval-setting-section">
<h4>Top Boundary Lines</h4>
<div className="wlv-interval-setting-grid">
<label className="wlv-interval-builder-toggle"><input type="checkbox" checked={intervalFormationConfig.showBoundaryLines} onChange={event=>updateIntervalFormationConfig({showBoundaryLines:event.target.checked})}/><span>Show boundary lines</span></label>
<label><span>Line colour</span><input type="color" value={intervalFormationConfig.boundaryColor} onChange={event=>updateIntervalFormationConfig({boundaryColor:event.target.value})}/></label>
<label><span>Line width</span><div className="wlv-interval-builder-width"><input type="number" min="0.5" max="6" step="0.5" value={intervalFormationConfig.boundaryWidth} onChange={event=>updateIntervalFormationConfig({boundaryWidth:Math.max(.5,Math.min(6,Number(event.target.value)||1))})}/><em>px</em></div></label>
<label><span>Line style</span><select value={intervalFormationConfig.boundaryStyle} onChange={event=>updateIntervalFormationConfig({boundaryStyle:event.target.value as IntervalFormationConfig['boundaryStyle']})}><option value="solid">Solid</option><option value="dashed">Dashed</option><option value="dotted">Dotted</option></select></label>
<label><span>Opacity</span><div className="wlv-interval-builder-width"><input type="number" min="0" max="100" value={intervalFormationConfig.boundaryOpacity} onChange={event=>updateIntervalFormationConfig({boundaryOpacity:Math.max(0,Math.min(100,Number(event.target.value)||0))})}/><em>%</em></div></label>
<label><span>Extend across</span><select value={intervalFormationConfig.boundaryExtent} onChange={event=>updateIntervalFormationConfig({boundaryExtent:event.target.value as IntervalFormationConfig['boundaryExtent']})}><option value="column">Formation Tops column only</option><option value="interval_columns">All configured Interval columns</option></select></label>
</div>
</section>

<section className="wlv-interval-setting-section">
<h4>Interval Box Fill</h4>
<div className="wlv-interval-setting-grid">
<label className="wlv-interval-builder-toggle"><input type="checkbox" checked={intervalFormationConfig.showBoxFill} onChange={event=>updateIntervalFormationConfig({showBoxFill:event.target.checked})}/><span>Show box fill</span></label>
<label><span>Fill colour</span><input type="color" value={intervalFormationConfig.boxFillColor} onChange={event=>updateIntervalFormationConfig({boxFillColor:event.target.value})}/></label>
<label><span>Fill opacity</span><div className="wlv-interval-builder-width"><input type="number" min="0" max="100" value={intervalFormationConfig.boxFillOpacity} onChange={event=>updateIntervalFormationConfig({boxFillOpacity:Math.max(0,Math.min(100,Number(event.target.value)||0))})}/><em>%</em></div></label>
<label className="wlv-interval-builder-toggle"><input type="checkbox" checked={intervalFormationConfig.showBoxBorder} onChange={event=>updateIntervalFormationConfig({showBoxBorder:event.target.checked})}/><span>Show box border</span></label>
<label><span>Border colour</span><input type="color" value={intervalFormationConfig.boxBorderColor} onChange={event=>updateIntervalFormationConfig({boxBorderColor:event.target.value})}/></label>
<label><span>Border width</span><div className="wlv-interval-builder-width"><input type="number" min="0.5" max="6" step="0.5" value={intervalFormationConfig.boxBorderWidth} onChange={event=>updateIntervalFormationConfig({boxBorderWidth:Math.max(.5,Math.min(6,Number(event.target.value)||1))})}/><em>px</em></div></label>
</div>
</section>
</div>}
{column.key==='lithology'&&<><label><span>Source</span><select defaultValue="manual"><option value="manual">Manual intervals</option><option value="formation">Formation-derived</option></select></label><label><span>Fill catalogue</span><select defaultValue="kr"><option value="kr">KR Lithology</option><option value="solid">Solid colours</option></select></label></>}
{column.key==='depth'&&<div className="wlv-interval-depth-settings">
<section className="wlv-interval-setting-section">
<h4>Depth Format</h4>
<div className="wlv-interval-depth-row">
<label><span>Depth reference</span><select value={intervalDepthConfig.reference} onChange={event=>updateIntervalDepthConfig({reference:event.target.value as IntervalDepthReference})}><option value="MD">MD</option><option value="TVD_RT">TVD RT</option><option value="TVD_MSL">TVD MSL</option></select></label>
<label><span>Decimal places</span><select value={intervalDepthConfig.decimalPlaces} onChange={event=>updateIntervalDepthConfig({decimalPlaces:Number(event.target.value) as 0|1|2})}><option value="0">0</option><option value="1">1</option><option value="2">2</option></select></label>
</div>
</section>

<section className="wlv-interval-depth-tie">
<h4>Boundary Source</h4>
<div className="wlv-interval-depth-tie-options">
<label><input type="radio" name="interval-depth-tie" checked={intervalDepthConfig.tieMode==='independent'} onChange={()=>updateIntervalDepthConfig({tieMode:'independent'})}/><span>Independent depth scale</span></label>
<label><input type="radio" name="interval-depth-tie" checked={intervalDepthConfig.tieMode==='boundaries'} onChange={()=>updateIntervalDepthConfig({tieMode:'boundaries',tiedColumnKey:depthBoundarySources.some((source)=>source.id===intervalDepthConfig.tiedColumnKey)?intervalDepthConfig.tiedColumnKey:(depthBoundarySources[0]?.id??'')})}/><span>Tie values to interval boundaries from</span></label>
<select disabled={intervalDepthConfig.tieMode!=='boundaries'||depthBoundarySources.length===0} value={depthBoundarySources.some((source)=>source.id===intervalDepthConfig.tiedColumnKey)?intervalDepthConfig.tiedColumnKey:(depthBoundarySources[0]?.id??'')} onChange={event=>updateIntervalDepthConfig({tiedColumnKey:event.target.value})}>
{depthBoundarySources.length===0?<option value="">No eligible interval columns</option>:depthBoundarySources.map((source)=><option key={source.id} value={source.id}>{source.label}</option>)}
</select>
</div>
</section>

<section className="wlv-interval-depth-line-settings">
<div className="wlv-interval-section-heading-row">
<h4>Boundary Line</h4>
<label className="wlv-interval-builder-toggle"><input type="checkbox" checked={intervalDepthConfig.lineMode!=='none'} onChange={event=>updateIntervalDepthConfig({lineMode:event.target.checked?'draw':'none',lineColorMode:'custom'})}/><span>Show</span></label>
</div>
<div className="wlv-interval-depth-line-grid">
<label><span>Line colour</span><input type="color" value={intervalDepthConfig.customLineColor} onChange={event=>updateIntervalDepthConfig({lineColorMode:'custom',customLineColor:event.target.value})}/></label>
<label><span>Line width</span><input type="number" min="0.5" max="6" step="0.5" value={intervalDepthConfig.lineWidth} onChange={event=>updateIntervalDepthConfig({lineWidth:Math.max(.5,Math.min(6,Number(event.target.value)||1))})}/></label>
<label><span>Line style</span><select value={intervalDepthConfig.lineStyle} onChange={event=>updateIntervalDepthConfig({lineStyle:event.target.value as IntervalDepthConfig['lineStyle']})}><option value="solid">Solid</option><option value="dashed">Dashed</option><option value="dotted">Dotted</option></select></label>
<label><span>Opacity</span><div className="wlv-interval-builder-width"><input type="number" min="0" max="100" value={intervalDepthConfig.lineOpacity} onChange={event=>updateIntervalDepthConfig({lineOpacity:Math.max(0,Math.min(100,Number(event.target.value)||0))})}/><em>%</em></div></label>
<label><span>Line length</span><select value={intervalDepthConfig.lineExtent} onChange={event=>updateIntervalDepthConfig({lineExtent:event.target.value as IntervalDepthLineExtent})}><option value="full">Full column width</option><option value="left_tick">Left tick only</option><option value="right_tick">Right tick only</option></select></label>
</div>
</section>

<section className="wlv-interval-depth-value-settings">
<h4>Depth value position</h4>
<div className="wlv-interval-depth-line-grid">
<label><span>Vertical</span><select value={intervalDepthConfig.valuePosition} onChange={event=>updateIntervalDepthConfig({valuePosition:event.target.value as IntervalDepthValuePosition})}><option value="on">On line</option><option value="above">Above line</option><option value="below">Below line</option></select></label>
<label><span>Horizontal</span><select value={intervalDepthConfig.horizontalPosition} onChange={event=>updateIntervalDepthConfig({horizontalPosition:event.target.value as IntervalDepthHorizontalPosition})}><option value="left">Left</option><option value="center">Centre</option><option value="right">Right</option></select></label>
{intervalDepthConfig.valuePosition!=='on'&&<label><span>Offset</span><div className="wlv-interval-builder-width"><input type="number" min="0" max="20" value={intervalDepthConfig.valueOffset} onChange={event=>updateIntervalDepthConfig({valueOffset:Math.max(0,Math.min(20,Number(event.target.value)||0))})}/><em>px</em></div></label>}
</div>
</section>
</div>}
{column.key==='thickness'&&<label><span>Units</span><select defaultValue="m"><option value="m">m</option><option value="ft">ft</option></select></label>}
{column.key==='uncertainty'&&<label><span>Source</span><select defaultValue="formation"><option value="formation">Formation Tops</option><option value="manual">Manual</option></select></label>}
{column.key==='notes'&&<label className="wlv-interval-builder-toggle"><input type="checkbox" defaultChecked/><span>Allow manual text</span></label>}
{column.key==='color_band'&&<label><span>Source</span><select defaultValue="group"><option value="group">Group colours</option><option value="manual">Manual colours</option></select></label>}

{column.key==='descriptions'&&<div className="wlv-core-description-editor">

<section className="wlv-interval-setting-section">
<h4>Source</h4>

<div className="wlv-core-description-source-grid">
<label>
<span>Description type</span>
<select value={intervalDescriptionConfig.descriptionType}>
<option value="core_description">Core Description</option>
</select>
</label>

<label>
<span>Core</span>
<select
 value={
   coreImageItems.some(item=>item.productId===intervalDescriptionConfig.coreProductId)
     ? intervalDescriptionConfig.coreProductId
     : (coreImageItems.find(item=>(item.descriptions?.length??0)>0)?.productId??'')
 }
 onChange={event=>updateIntervalDescriptionConfig({
   coreProductId:event.target.value
 })}
>
{coreImageItems
 .filter(item=>(item.descriptions?.length??0)>0)
 .map(item=><option key={item.productId} value={item.productId}>
   {item.label} · {item.topMd.toLocaleString()}–{item.baseMd.toLocaleString()} {item.depthUnit} MD · {(item.descriptions?.length??item.descriptionCount)} descriptions
 </option>)}
</select>
</label>
</div>

<p className="wlv-interval-empty-note">
Core Description records remain anchored to their exact measured depth.
Display offsets affect labels only.
</p>
</section>

<section className="wlv-interval-setting-section wlv-core-description-column-section">
<h4>Column</h4>
<div className="wlv-core-description-column-grid">
<label className="wlv-interval-builder-toggle"><input type="checkbox" checked={column.enabled} onChange={e=>updateIntervalBuilderColumn(column.key,{enabled:e.target.checked})}/><span>Add this column</span></label>
<label><span>Column title</span><input value={column.title} onChange={e=>updateIntervalBuilderColumn(column.key,{title:e.target.value})}/></label>
<label><span>Column width</span><div className="wlv-interval-builder-width"><input type="number" min="1" max="240" value={column.width} onChange={e=>updateIntervalBuilderColumn(column.key,{width:Math.max(1,Math.min(240,Number(e.target.value)||column.width))})}/><em>px</em></div></label>
</div>
</section>

<section className="wlv-interval-setting-section">
<h4>Elements</h4>

<div className="wlv-core-description-element-toggles">

<label>
<input
 type="checkbox"
 checked={intervalDescriptionConfig.showMarkerLine}
 onChange={event=>updateIntervalDescriptionConfig({
   showMarkerLine:event.target.checked
 })}
/>
<span>Line</span>
</label>

<label>
<input
 type="checkbox"
 checked={intervalDescriptionConfig.showMd}
 onChange={event=>updateIntervalDescriptionConfig({
   showMd:event.target.checked
 })}
/>
<span>Depth</span>
</label>

<label>
<input
 type="checkbox"
 checked={intervalDescriptionConfig.showText}
 onChange={event=>updateIntervalDescriptionConfig({
   showText:event.target.checked
 })}
/>
<span>Description</span>
</label>

</div>
</section>


<div className="wlv-core-description-main-controls">

<section className="wlv-interval-setting-section">
<h4>Line</h4>
<div className="wlv-core-description-control-grid">
<label><span>Colour</span><input type="color" value={intervalDescriptionConfig.markerColor} onChange={event=>updateIntervalDescriptionConfig({markerColor:event.target.value})}/></label>
<label><span>Width</span><div className="wlv-interval-builder-width"><input type="number" min="0.5" max="8" step="0.5" value={intervalDescriptionConfig.markerWidth} onChange={event=>updateIntervalDescriptionConfig({markerWidth:Math.max(.5,Math.min(8,Number(event.target.value)||1))})}/><em>px</em></div></label>
<label><span>Style</span><select value={intervalDescriptionConfig.markerStyle} onChange={event=>updateIntervalDescriptionConfig({markerStyle:event.target.value as IntervalDescriptionConfig['markerStyle']})}><option value="solid">Solid</option><option value="dashed">Dashed</option><option value="dotted">Dotted</option></select></label>
<label><span>Opacity</span><div className="wlv-interval-builder-width"><input type="number" min="0" max="100" value={intervalDescriptionConfig.markerOpacity} onChange={event=>updateIntervalDescriptionConfig({markerOpacity:Math.max(0,Math.min(100,Number(event.target.value)||0))})}/><em>%</em></div></label>
</div>
</section>

<section className="wlv-interval-setting-section">
<h4>Depth</h4>
<div className="wlv-core-description-control-grid">
<label><span>Font size</span><div className="wlv-interval-builder-width"><input type="number" min="7" max="30" value={intervalDescriptionConfig.depthFontSize} onChange={event=>updateIntervalDescriptionConfig({depthFontSize:Math.max(7,Math.min(30,Number(event.target.value)||10))})}/><em>px</em></div></label>
<label><span>Colour</span><input type="color" value={intervalDescriptionConfig.depthFontColor} onChange={event=>updateIntervalDescriptionConfig({depthFontColor:event.target.value})}/></label>
<label><span>Weight</span><select value={intervalDescriptionConfig.depthFontWeight} onChange={event=>updateIntervalDescriptionConfig({depthFontWeight:event.target.value as IntervalDescriptionConfig['depthFontWeight']})}><option value="regular">Regular</option><option value="bold">Bold</option></select></label>
<label><span>Opacity</span><div className="wlv-interval-builder-width"><input type="number" min="0" max="100" value={intervalDescriptionConfig.depthOpacity} onChange={event=>updateIntervalDescriptionConfig({depthOpacity:Math.max(0,Math.min(100,Number(event.target.value)||0))})}/><em>%</em></div></label>
</div>
</section>

<section className="wlv-interval-setting-section">
<h4>Description</h4>
<div className="wlv-core-description-control-grid">
<label><span>Font size</span><div className="wlv-interval-builder-width"><input type="number" min="7" max="30" value={intervalDescriptionConfig.fontSize} onChange={event=>updateIntervalDescriptionConfig({fontSize:Math.max(7,Math.min(30,Number(event.target.value)||10))})}/><em>px</em></div></label>
<label><span>Colour</span><input type="color" value={intervalDescriptionConfig.fontColor} onChange={event=>updateIntervalDescriptionConfig({fontColor:event.target.value})}/></label>
<label><span>Weight</span><select value={intervalDescriptionConfig.fontWeight} onChange={event=>updateIntervalDescriptionConfig({fontWeight:event.target.value as IntervalDescriptionConfig['fontWeight']})}><option value="regular">Regular</option><option value="bold">Bold</option></select></label>
<label><span>Opacity</span><div className="wlv-interval-builder-width"><input type="number" min="0" max="100" value={intervalDescriptionConfig.descriptionOpacity} onChange={event=>updateIntervalDescriptionConfig({descriptionOpacity:Math.max(0,Math.min(100,Number(event.target.value)||0))})}/><em>%</em></div></label>
<label><span>Alignment</span><select value={intervalDescriptionConfig.textAlignment} onChange={event=>updateIntervalDescriptionConfig({textAlignment:event.target.value as IntervalDescriptionConfig['textAlignment']})}><option value="left">Left</option><option value="center">Centre</option><option value="right">Right</option></select></label>
<label className="wlv-interval-builder-toggle"><input type="checkbox" checked={intervalDescriptionConfig.wrapText} onChange={event=>updateIntervalDescriptionConfig({wrapText:event.target.checked})}/><span>Wrap text</span></label>
</div>
</section>

</div>

<section className="wlv-interval-setting-section">
<h4>Relative Position</h4>

<div className="wlv-core-description-layout-grid">

<label>
<span>Depth relative to line</span>
<select
 value={intervalDescriptionConfig.depthRelativeToLine ?? 'on'}
 onChange={event=>updateIntervalDescriptionConfig({
   depthRelativeToLine:event.target.value as 'above'|'on'|'below'
 })}
>
<option value="above">Above line</option>
<option value="on">On line</option>
<option value="below">Below line</option>
</select>
</label>

<label>
<span>Description relative to line</span>
<select
 value={intervalDescriptionConfig.descriptionRelativeToLine ?? 'below'}
 onChange={event=>updateIntervalDescriptionConfig({
   descriptionRelativeToLine:event.target.value as 'above'|'on'|'below'
 })}
>
<option value="above">Above line</option>
<option value="on">On line</option>
<option value="below">Below line</option>
</select>
</label>

<label>
<span>Depth / description layout</span>
<select
 value={intervalDescriptionConfig.depthDescriptionOrder ?? 'depth_before'}
 onChange={event=>updateIntervalDescriptionConfig({
   depthDescriptionOrder:event.target.value as
     'depth_before'|'description_before'|'depth_above'|'description_above'
 })}
>
<option value="depth_before">Depth before description</option>
<option value="description_before">Description before depth</option>
<option value="depth_above">Depth above description</option>
<option value="description_above">Description above depth</option>
</select>
</label>

</div>
</section>


<section className="wlv-interval-setting-section wlv-core-description-fine-section">
<h4>Fine Adjustment</h4>
<div className="wlv-core-description-slider-grid">
<label className="wlv-core-description-slider"><div className="wlv-core-description-slider-heading"><span>Depth horizontal</span><output>{intervalDescriptionConfig.depthHorizontalOffset>0?'+':''}{intervalDescriptionConfig.depthHorizontalOffset}</output></div><input type="range" min="-40" max="40" step="1" value={intervalDescriptionConfig.depthHorizontalOffset} onChange={event=>updateIntervalDescriptionConfig({depthHorizontalOffset:Number(event.target.value)})}/><div className="wlv-core-description-slider-scale"><span>Left</span><span>Right</span></div></label>
<label className="wlv-core-description-slider"><div className="wlv-core-description-slider-heading"><span>Depth vertical</span><output>{intervalDescriptionConfig.depthVerticalOffset>0?'+':''}{intervalDescriptionConfig.depthVerticalOffset}</output></div><input type="range" min="-40" max="40" step="1" value={intervalDescriptionConfig.depthVerticalOffset} onChange={event=>updateIntervalDescriptionConfig({depthVerticalOffset:Number(event.target.value)})}/><div className="wlv-core-description-slider-scale"><span>Up</span><span>Down</span></div></label>
<label className="wlv-core-description-slider"><div className="wlv-core-description-slider-heading"><span>Description horizontal</span><output>{intervalDescriptionConfig.descriptionHorizontalOffset>0?'+':''}{intervalDescriptionConfig.descriptionHorizontalOffset}</output></div><input type="range" min="-40" max="40" step="1" value={intervalDescriptionConfig.descriptionHorizontalOffset} onChange={event=>updateIntervalDescriptionConfig({descriptionHorizontalOffset:Number(event.target.value)})}/><div className="wlv-core-description-slider-scale"><span>Left</span><span>Right</span></div></label>
<label className="wlv-core-description-slider"><div className="wlv-core-description-slider-heading"><span>Description vertical</span><output>{intervalDescriptionConfig.descriptionVerticalOffset>0?'+':''}{intervalDescriptionConfig.descriptionVerticalOffset}</output></div><input type="range" min="-40" max="40" step="1" value={intervalDescriptionConfig.descriptionVerticalOffset} onChange={event=>updateIntervalDescriptionConfig({descriptionVerticalOffset:Number(event.target.value)})}/><div className="wlv-core-description-slider-scale"><span>Up</span><span>Down</span></div></label>
</div>
</section>

<section className="wlv-interval-setting-section">
<h4>Display Density</h4>

<label>
<span>Density</span>
<select
 value={intervalDescriptionConfig.density}
 onChange={event=>updateIntervalDescriptionConfig({
   density:event.target.value as IntervalDescriptionConfig['density']
 })}
>
<option value="auto">Auto</option>
<option value="all">All</option>
<option value="sparse">Sparse</option>
</select>
</label>

</section>

</div>}

</div>)}</div>
{intervalBuilderTab !== 'descriptions' && intervalBuilderTab !== 'tie_in' && (<div className="wlv-interval-selected-columns"><div className="builder-label">Selected columns</div>{enabledIntervalColumns.length===0?<p>No columns selected.</p>:enabledIntervalColumns.map((column,index)=><div key={column.key} className="wlv-interval-selected-column-row"><span>{column.title||column.label}</span><input type="number" min="1" max="240" value={column.width} onChange={e=>updateIntervalBuilderColumn(column.key,{width:Math.max(1,Math.min(240,Number(e.target.value)||column.width))})}/><em>px</em><button type="button" disabled={index===0} onClick={()=>moveIntervalBuilderColumn(column.key,-1)}>↑</button><button type="button" disabled={index===enabledIntervalColumns.length-1} onClick={()=>moveIntervalBuilderColumn(column.key,1)}>↓</button><button type="button" onClick={()=>updateIntervalBuilderColumn(column.key,{enabled:false})}>×</button></div>)}</div>
)}{!intervalBuilderEmbedded?<footer className="wlv-interval-builder-actions"><button type="button" onClick={closeIntervalBuilder}>Cancel</button><button type="button" className="builder-primary" disabled={intervalBuilderTab==='tie_in'?(
    !selectedTieInNeighbours.trackA
    ||!selectedTieInNeighbours.trackB
    ||(
        intervalTieInDraftMode==='new'
        &&intervalTieInCreationMethod==='manual'
        &&(
            intervalTieInDraft.upperA===null
            ||intervalTieInDraft.upperB===null
            ||intervalTieInDraft.lowerA===null
            ||intervalTieInDraft.lowerB===null
        )
    )
):!enabledIntervalColumns.length} onClick={applyIntervalBuilderColumns}>{intervalBuilderMode==='edit'?'Apply Changes':'Apply Columns'}</button></footer>:null}
</section></div>,
intervalBuilderPortalTarget??document.body
):null;

    return (<div className="wlv-track-toolbar" aria-label="Well log viewer toolbar" style={{ position: 'relative' }}>
      <ToolbarZone id="tracks" title="Add / Delete Tracks" className="wlv-toolbar-group-track">
          <div className="wlv-add-track-control">
            <button type="button" className="wlv-add-track-button" disabled={managedLayoutDisabled} onClick={toggleAddTrackBuilder} aria-expanded={builderOpen}>
              + Add Track ▾
            </button>
          </div>
          {addTrackBuilder}{intervalColumnBuilder}
          <button type="button" disabled={managedLayoutDisabled || !selectedTrack} onClick={onDeleteTrack}>Delete</button>
          <button type="button" disabled={managedLayoutDisabled} onClick={onClearCanvas}>Clear Canvas</button>
      </ToolbarZone>

      <ToolbarZone id="track-layout" title="Track Layout" className="wlv-toolbar-group-arrange">
          <button type="button" className="wlv-toolbar-compact-button" disabled={managedLayoutDisabled || !canMoveSelectedTrackLeft} title={selectedTrack ? 'Move selected track left' : 'Select a track first'} aria-label="Move selected track left" onClick={() => onMoveSelectedTrack(-1)}>←</button>
          <button type="button" className="wlv-toolbar-compact-button" disabled={managedLayoutDisabled || !canMoveSelectedTrackRight} title={selectedTrack ? 'Move selected track right' : 'Select a track first'} aria-label="Move selected track right" onClick={() => onMoveSelectedTrack(1)}>→</button>
          <button type="button" className="wlv-toolbar-compact-button" disabled={managedLayoutDisabled || !canAdjustSelectedCurveTrackWidthDown} title={
              selectedTrack?.trackType === 'curve'
              || selectedTrack?.trackType === 'core'
              || selectedTrack?.trackType === 'interval'
                  ? 'Contract selected track'
                  : 'Select a Curve, Core, or Interval track first'
          } aria-label="Contract selected track" onClick={() => onAdjustSelectedCurveTrackWidth(-CURVE_TRACK_WIDTH_STEP)}>−</button>
          <span className="wlv-toolbar-width-label" aria-hidden="true">Width</span>
          <button type="button" className="wlv-toolbar-compact-button" disabled={managedLayoutDisabled || !canAdjustSelectedCurveTrackWidthUp} title={
              selectedTrack?.trackType === 'curve'
              || selectedTrack?.trackType === 'core'
              || selectedTrack?.trackType === 'interval'
                  ? 'Widen selected track'
                  : 'Select a Curve, Core, or Interval track first'
          } aria-label="Widen selected track" onClick={() => onAdjustSelectedCurveTrackWidth(CURVE_TRACK_WIDTH_STEP)}>+</button>
          <button type="button" className="wlv-toolbar-compact-button" disabled={managedLayoutDisabled} onClick={onResetCurveTrackWidths} title="Reset Curve, Core, and Interval tracks to uniform width; Depth tracks remain unchanged" aria-label="Reset resizable track widths">↺</button>
          <button type="button" className={`wlv-header-collapse-toggle ${trackHeadersCollapsed ? 'active' : ''}`} disabled={managedLayoutDisabled} aria-pressed={trackHeadersCollapsed} title={trackHeadersCollapsed ? 'Expand track headers' : 'Collapse track headers to rows 1 and 2'} aria-label={trackHeadersCollapsed ? 'Expand track headers' : 'Collapse track headers'} onClick={() => onTrackHeadersCollapsedChange(!trackHeadersCollapsed)}>
            {trackHeadersCollapsed ? '▤' : '▬'}
          </button>
      </ToolbarZone>

      <ToolbarZone id="presets" title="Presets" className="wlv-toolbar-group-presets">
          <select aria-label="Layout preset" className="wlv-layout-preset-select" style={{ minWidth: layoutRecommendationOptions.length > 0 ? 190 : 140 }} value={selectedLayoutRecommendationKey} disabled={managedLayoutDisabled || layoutRecommendationsLoading || layoutRecommendationOptions.length === 0} title={layoutRecommendationsError ?? 'Backend-approved KR layout presets'} onChange={(event) => onLayoutRecommendationChange(event.target.value)}>
            <option value="">{layoutPresetPlaceholder}</option>
            {layoutRecommendationOptions.map((item) => (<option key={item.template_key} value={item.template_key}>
                {item.template_label}
              </option>))}
          </select>
          <button type="button" className="wlv-layout-preset-refresh" title="Refresh backend KR template recommendations" aria-label="Refresh backend KR template recommendations" disabled={managedLayoutDisabled || layoutRecommendationsLoading} onClick={onRefreshLayoutRecommendations}>
            ↻
          </button>
      </ToolbarZone>

      <ToolbarZone id="depth-unit" title="Depth Unit" className="wlv-toolbar-group-depth-unit">
          <select aria-label="Depth Unit" value={commonDepthUnit} disabled={depthUnitDisabled} onChange={(event) => onCommonDepthUnitChange(event.target.value as 'm' | 'ft')}>
            <option value="m">m</option>
            <option value="ft">ft</option>
          </select>
      </ToolbarZone>

      <ToolbarZone id="zoom-view" title="Zoom / View" className="wlv-toolbar-group-view">
          <button type="button" title="Zoom Out" aria-label="Zoom Out" onClick={onZoomOut}>−</button>
          <button type="button" title="Zoom In" aria-label="Zoom In" onClick={onZoomIn}>+</button>
          <button
            type="button"
            className="wlv-combination-lock-toggle-button"
            disabled={viewportToolbarPresentation.lock.disabled}
            title={viewportToolbarPresentation.lock.title}
            onClick={viewportToolbarPresentation.lock.action === 'lock' ? onLockSelectedTracks : onUnlockSelectedTracks}
          >
            {viewportToolbarPresentation.lock.label}
          </button>
          <span className="wlv-viewport-tie-control">
            <button
              ref={viewportTieButtonRef}
              type="button"
              className={`wlv-viewport-tie-toggle-button${viewportToolbarPresentation.tie.visualState === 'tied' ? ' tied' : viewportToolbarPresentation.tie.action === 'tie' || viewportTiePickerOpen ? ' ready' : ' dim'}`}
              disabled={viewportToolbarPresentation.tie.disabled}
              title={viewportToolbarPresentation.tie.title}
              aria-expanded={viewportTiePickerOpen}
              onClick={() => {
                if (viewportToolbarPresentation.tie.action === 'untie') {
                  onUntieSelectedViewportTracks?.();
                  return;
                }
                if (viewportToolbarPresentation.tie.action === 'tie') {
                  setViewportTiePickerOpen((open) => {
                    const nextOpen = !open;
                    if (nextOpen) {
                      window.requestAnimationFrame(updateViewportTiePopoverPosition);
                    }
                    return nextOpen;
                  });
                }
              }}
            >
              {viewportToolbarPresentation.tie.label}
            </button>
            {viewportTiePickerOpen ? createPortal(
              <div
                ref={viewportTiePopoverRef}
                className="wlv-depth-command-popover wlv-viewport-tie-picker"
                role="dialog"
                aria-label="Tie leader track"
                style={{
                  top: viewportTiePopoverPosition.top,
                  left: viewportTiePopoverPosition.left,
                }}
              >
                {viewportToolbarPresentation.tie.candidates.map((candidate) => (
                  <label
                    key={candidate.trackId}
                    className="wlv-go-to-selection-line-toggle wlv-viewport-tie-picker-row"
                  >
                    <input
                      type="checkbox"
                      checked={false}
                      onChange={() => {
                        onCreateViewportTie?.(candidate.trackId);
                        setViewportTiePickerOpen(false);
                      }}
                    />
                    <span>{candidate.label}</span>
                  </label>
                ))}
              </div>,
              document.body,
            ) : null}
          </span>
          <button type="button" className={intervalZoomActive ? 'active' : ''} title="Drag on the log to zoom to a depth interval" onClick={onToggleIntervalZoom}>Drag</button>
          <div className="wlv-specified-range-control">
            <button ref={specifyRangeButtonRef} type="button" className={rangeEditorOpen ? 'active' : ''} onClick={openSpecifiedRangeEditor} title="Specify top and base measured depth range">Range</button>
            {rangeEditorOpen ? createPortal(<div ref={specifyRangePopoverRef} className="wlv-depth-command-popover wlv-range-command-popover" role="dialog" aria-label="Specify depth range" style={{ top: rangePopoverPosition.top, left: rangePopoverPosition.left }}>
                <label><span>Top MD</span><input autoFocus value={rangeTopValue} onChange={(event) => setRangeTopValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applySpecifiedRange(); if (event.key === 'Escape') setRangeEditorOpen(false); }}/></label>
                <label><span>Base MD</span><input value={rangeBaseValue} onChange={(event) => setRangeBaseValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applySpecifiedRange(); if (event.key === 'Escape') setRangeEditorOpen(false); }}/></label>
                <button type="button" className="primary" onClick={applySpecifiedRange}>Apply</button>
                <button type="button" onClick={() => setRangeEditorOpen(false)}>Cancel</button>
              </div>, document.body) : null}
          </div>
          <div className="wlv-specified-range-control wlv-go-to-md-control">
            <button ref={goToDepthButtonRef} type="button" className={goToEditorOpen ? 'active' : ''} onClick={openGoToDepthEditor} title="Go to a measured depth">Go to MD ▾</button>
            {goToEditorOpen ? createPortal(
        <div
            ref={goToDepthPopoverRef}
            className="wlv-depth-command-popover wlv-go-to-tight"
            role="dialog"
            aria-label="Go To"
            style={{
                top: goToDepthPopoverPosition.top,
                left: goToDepthPopoverPosition.left,
            }}
        >
            <div className="wlv-go-to-tight-row wlv-go-to-tight-md">
                <input
                    className="wlv-go-to-tight-depth"
                    autoFocus
                    value={goToDepthValue}
                    placeholder={`Depth (${commonDepthUnit})`}
                    onChange={(event) =>
                        onGoToDepthValueChange(event.target.value)
                    }
                    onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                            applyGoToDepth();
                        } else if (event.key === 'Escape') {
                            setGoToEditorOpen(false);
                        }
                    }}
                />

                <button
                    type="button"
                    className={
                        goToDepthPickActive ? 'active' : ''
                    }
                    onClick={() => {
                        setGoToEditorOpen(false);
                        onStartGoToDepthPick?.();
                    }}
                    title="Pick focus MD directly from a WDV track"
                >
                    Pick
                </button>

                <button
                    type="button"
                    className="primary"
                    onClick={applyGoToDepth}
                >
                    Go
                </button>
            </div>

            <div className="wlv-go-to-tight-row wlv-go-to-tight-top">
                {goToFormationTopOptions.length > 0 ? (
                    <>
                        <select
                            className="wlv-go-to-tight-select"
                            value={selectedGoToFormationTopId}
                            onChange={(event) =>
                                setSelectedGoToFormationTopId(
                                    event.target.value,
                                )
                            }
                        >
                            <option value="">
                                Select Formation Top…
                            </option>

                            {goToFormationTopOptions.map((marker) => (
                                <option
                                    key={marker.markerId}
                                    value={marker.markerId}
                                >
                                    {
                                        `${marker.markerName}`
                                        + ` · `
                                        + `${marker.md.toLocaleString(
                                            undefined,
                                            {
                                                maximumFractionDigits: 3,
                                            },
                                        )} ${commonDepthUnit}`
                                    }
                                </option>
                            ))}
                        </select>

                        <button
                            type="button"
                            className="primary"
                            disabled={!selectedGoToFormationTopId}
                            onClick={applyGoToFormationTop}
                        >
                            Go
                        </button>
                    </>
                ) : (
                    <div className="wlv-go-to-tight-empty">
                        No Formation Tops
                    </div>
                )}
            </div>

            <div className="wlv-go-to-tight-footer">
                <label className="wlv-go-to-selection-line-toggle">
                    <input
                        type="checkbox"
                        checked={displayGoToSelectionLine}
                        onChange={(event) =>
                            onDisplayGoToSelectionLineChange?.(
                                event.target.checked,
                            )
                        }
                    />
                    <span>Display selection line</span>
                </label>

                <button
                    type="button"
                    onClick={() => setGoToEditorOpen(false)}
                >
                    Cancel
                </button>
            </div>
        </div>,
        document.body,
    ) : null}
          </div>
          {coreThresholdAvailable ? (
              <button
                  type="button"
                  className="wlv-core-threshold-button active"
                  onClick={onCoreThreshold}
                  title="Zoom to the minimum scale required to render Core photography"
              >
                  Core Threshold
              </button>
          ) : null}
          <button type="button" onClick={onFitDepth}>Full</button>
          <button type="button" onClick={onResetView} title="Reset view">Reset</button>
          {viewDepthReadoutEnabled ? (<strong className="wlv-depth-readout" title={`Full range ${depthRangeLabel(fullDepthRange, commonDepthUnit)}`}>{depthRangeLabel(viewDepthRange, commonDepthUnit)}</strong>) : null}
        </ToolbarZone>

      <div className="wlv-toolbar-spacer"/>

      <div
          data-toolbar-group="right-actions"
          aria-label="Canvas actions"
          style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flex: '0 0 auto',
              alignSelf: 'flex-end',
              marginRight: `${Math.max(0, canvasRightInsetPx)}px`,
          }}
      >
          {wbvPublishAction ? (
              <span
                  className="wlv-inline-wbv-publish-action wlv-toolbar-wbv-standalone"
                  style={{ alignSelf: 'center', marginLeft: 0 }}
              >
                  {wbvPublishAction}
              </span>
          ) : null}

          {onSaveCanvas && onSaveActiveCanvas && onLoadSavedCanvas && onDeleteSavedCanvas ? (
              <div
                  className="wlv-toolbar-group wlv-toolbar-group-saved-canvas"
                  data-toolbar-group="saved-canvas"
                  aria-label="Saved Canvases"
                  data-anchor="canvas-right-edge"
                  style={{ flex: '0 0 auto', alignSelf: 'center' }}
              >
                  <div className="wlv-toolbar-actions">
                      <SavedCanvasToolbarControl
                          items={savedCanvases}
                          disabled={savedCanvasDisabled}
                          saving={savedCanvasSaving}
                          busySavedCanvasUid={savedCanvasBusyUid}
                          error={savedCanvasError}
                          onSave={onSaveCanvas}
                          onSaveChanges={onSaveActiveCanvas}
                          onLoad={onLoadSavedCanvas}
                          onDelete={onDeleteSavedCanvas}
                      />
                  </div>
              </div>
          ) : null}

          <div
              className="wlv-toolbar-group wlv-toolbar-group-backdrop wlv-toolbar-icon-only"
              style={{ flex: '0 0 auto', alignSelf: 'center', marginLeft: 0 }}
          >
              <div className="wlv-toolbar-actions">
                  <button type="button" className="wlv-backdrop-toggle" onClick={() => onTrackBackdropModeChange(trackBackdropMode === 'light' ? 'dark' : 'light')} aria-pressed={trackBackdropMode === 'dark'} title={trackBackdropMode === 'light' ? 'Switch to dark backdrop' : 'Switch to light backdrop'} aria-label={trackBackdropMode === 'light' ? 'Switch to dark backdrop' : 'Switch to light backdrop'}>
                    ◐
                  </button>
              </div>
          </div>
      </div>
    </div>);
}
export function CurveHeaderStack({ track, curveCatalogItems, selectedAssignmentId, openMenuAssignmentId, onSelectCurve, onEditCurve, onReorderCurve, onMoveCurveToTrack, onOpenCurveMenu, onCloseCurveMenu, onRemoveCurveFromTrack, }: {
    track: CurveTrack;
    curveCatalogItems: CurveCatalogItem[];
    selectedAssignmentId: string | null;
    openMenuAssignmentId: string | null;
    onSelectCurve: (trackId: string, assignmentId: string) => void;
    onEditCurve: (trackId: string, assignmentId: string) => void;
    onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
    onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
    onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
    onCloseCurveMenu: () => void;
    onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
}) {
    const ordered = orderedCurves(track);
    return (<div className="wlv-curve-header-stack">
      {ordered.map((assignment, index) => {
            const curve = resolveCurveAssignmentCatalogItem(curveCatalogItems, assignment);
            if (!curve)
                return null;
            return (<div key={assignment.assignmentId} role="button" tabIndex={0} className={`wlv-curve-header ${selectedAssignmentId === assignment.assignmentId ? 'selected' : ''}`} data-curve-assignment-id={assignment.assignmentId} draggable onClick={(event) => {
                    event.stopPropagation();
                    onSelectCurve(track.trackId, assignment.assignmentId);
                    if (openMenuAssignmentId === assignment.assignmentId) {
                        onCloseCurveMenu();
                    }
                }} onDoubleClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onSelectCurve(track.trackId, assignment.assignmentId);
                    onOpenCurveMenu(track.trackId, assignment.assignmentId);
                }} onDragStart={(event) => {
                    event.dataTransfer.setData('application/json', serialiseCurveDrag({
                        dragType: 'curve',
                        curveId: assignment.curveId,
                        fromTrackId: track.trackId,
                        assignmentId: assignment.assignmentId,
                    }));
                    event.dataTransfer.effectAllowed = 'move';
                }} onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
                    if (!payload)
                        return;
                    if (payload.fromTrackId === track.trackId && payload.assignmentId) {
                        onReorderCurve(track.trackId, payload.assignmentId, index);
                    }
                    else {
                        onMoveCurveToTrack(payload, track.trackId, index);
                    }
                }}>
            <div className="wlv-curve-header-meta">
              <span className="wlv-curve-color" style={{ background: assignment.color }}/>
              <strong>{curve.mnemonic}</strong>
              <em>{curve.unit}</em>
            </div>
            {(assignment.scaleTicks ?? []).length >= 2 ? (
              <div
                className="wlv-curve-scale-axis"
                style={{
                  left: `${CURVE_VIEW_PADDING_X}px`,
                  right: `${CURVE_VIEW_PADDING_X}px`,
                }}
                aria-label={`${curve.mnemonic} backend-owned scale`}
              >
                <span className="wlv-curve-scale-line" aria-hidden="true"/>
                {(assignment.scaleTicks ?? []).map((tick, tickIndex, ticks) => (
                  <span
                    key={`${assignment.assignmentId}-scale-${tickIndex}`}
                    className={`wlv-curve-scale-tick ${tickIndex === 0 ? 'edge-left' : tickIndex === ticks.length - 1 ? 'edge-right' : ''}`}
                    style={{ left: `${tick.normalizedPosition * 100}%` }}
                    data-scale-value={tick.value}
                    data-scale-position={tick.normalizedPosition}
                  >
                    <i aria-hidden="true"/>
                    <b>{tick.label}</b>
                  </span>
                ))}
              </div>
            ) : (
              <div className="wlv-curve-scale-fallback">
                {assignment.scaleMinLabel ?? String(assignment.scaleMin)}
                —
                {assignment.scaleMaxLabel ?? String(assignment.scaleMax)}
              </div>
            )}
            {openMenuAssignmentId === assignment.assignmentId && (<CurveHeaderActionMenuPortal trackId={track.trackId} assignmentId={assignment.assignmentId} assignmentIndex={index} assignmentCount={ordered.length} onEditCurve={onEditCurve} onReorderCurve={onReorderCurve} onCloseCurveMenu={onCloseCurveMenu} onRemoveCurveFromTrack={onRemoveCurveFromTrack}/>)}
          </div>);
        })}
    </div>);
}

function CoreImageProductView({
    item,
    viewDepthRange,
    trackBodyHeightPx,
    appearance,
}: {
    item: CoreImageInventoryItem;
    viewDepthRange: DepthViewRange;
    trackBodyHeightPx: number;
    appearance: CoreTrackAppearance;
}) {
    const [manifest, setManifest] = useState<CoreImageChunkManifest | null>(null);
    const [manifestFailed, setManifestFailed] = useState(false);

    useEffect(() => {
        let cancelled = false;
        setManifest(null);
        setManifestFailed(false);

        const load = async () => {
            try {
                const response = await fetch(
                    `${wlvApiBaseUrl()}${item.chunkManifestUrl}`,
                    { cache: 'no-store' },
                );
                if (!response.ok) {
                    throw new Error(`Core chunk manifest returned ${response.status}`);
                }

                const payload = await response.json() as CoreImageChunkManifest;
                if (cancelled) return;

                setManifest({
                    ...payload,
                    chunks: Array.isArray(payload.chunks) ? payload.chunks : [],
                });
            } catch {
                if (!cancelled) setManifestFailed(true);
            }
        };

        void load();
        return () => {
            cancelled = true;
        };
    }, [item.productId, item.chunkManifestUrl]);

    const visibleChunks = useMemo(
        () => (manifest?.chunks ?? [])
            .filter((chunk) => (
                Number.isFinite(chunk.top_depth)
                && Number.isFinite(chunk.base_depth)
                && chunk.base_depth >= viewDepthRange.min
                && chunk.top_depth <= viewDepthRange.max
            ))
            .sort(
                (left, right) =>
                    left.sequence_index - right.sequence_index
                    || left.top_depth - right.top_depth,
            ),
        [
            manifest,
            viewDepthRange.min,
            viewDepthRange.max,
        ],
    );

    const productCoreGeometry = useMemo(() => {
        const samples = (manifest?.chunks ?? []).flatMap((rawChunk) => {
            const chunk = rawChunk as unknown as {
                top_depth: number;
                base_depth: number;
                pixel_width?: number;
                pixel_height?: number;
            };

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
        });

        if (samples.length === 0) return null;

        const median = (values: number[]) => {
            const ordered = [...values].sort(
                (left, right) => left - right,
            );
            const middle = Math.floor(ordered.length / 2);

            return ordered.length % 2 === 0
                ? (
                    ordered[middle - 1]
                    + ordered[middle]
                ) / 2
                : ordered[middle];
        };

        return {
            nativeWidth: median(
                samples.map((sample) => sample.width),
            ),
            nativePixelsPerMd: median(
                samples.map((sample) => sample.pixelsPerMd),
            ),
        };
    }, [manifest]);

    if (visibleChunks.length > 0) {
        return (
            <>
                {visibleChunks.map((chunk) => {
                    const top = depthToYUnclamped(
                        chunk.top_depth,
                        viewDepthRange,
                        trackBodyHeightPx,
                    );
                    const base = depthToYUnclamped(
                        chunk.base_depth,
                        viewDepthRange,
                        trackBodyHeightPx,
                    );
                    const height = Math.max(1, base - top);

                    /*
                     * NO-DISTORTION CORE CONTRACT:
                     * MD controls height. Width uses the same scale factor.
                     */
                    const nativeWidth = Number(
                        (chunk as unknown as { pixel_width?: number }).pixel_width,
                    );
                    const nativeHeight = Number(
                        (chunk as unknown as { pixel_height?: number }).pixel_height,
                    );

                    const hasNativeGeometry =
                        Number.isFinite(nativeWidth)
                        && Number.isFinite(nativeHeight)
                        && nativeWidth > 0
                        && nativeHeight > 0;

                    const uniformScale = hasNativeGeometry
                        ? height / nativeHeight
                        : 0;

                    const renderedImageWidth = hasNativeGeometry
                        ? nativeWidth * uniformScale
                        : 0;

                    /*
                     * Overview/photo transition is controlled by vertical
                     * display resolution, not by derived image width.
                     *
                     * This keeps the full-well view lightweight while allowing
                     * photographic core once there are enough screen pixels per
                     * metre to show meaningful vertical detail.
                     */
                    const viewSpanMd =
                        viewDepthRange.max - viewDepthRange.min;

                    const pixelsPerMd =
                        viewSpanMd > 0
                            ? trackBodyHeightPx / viewSpanMd
                            : 0;

                    const chunkMdSpan =
                        chunk.base_depth - chunk.top_depth;

                    const nativePixelsPerMd =
                        hasNativeGeometry && chunkMdSpan > 0
                            ? nativeHeight / chunkMdSpan
                            : 0;

                    /*
                     * A Continuous Core should have coherent photographic
                     * geometry. Do not stretch an outlying chunk into place.
                     */
                    const geometryConsistent =
                        productCoreGeometry !== null
                        && nativePixelsPerMd > 0
                        && Math.abs(
                            nativeWidth
                            / productCoreGeometry.nativeWidth
                            - 1
                        ) <= 0.05
                        && Math.abs(
                            nativePixelsPerMd
                            / productCoreGeometry.nativePixelsPerMd
                            - 1
                        ) <= 0.05;

                    /*
                     * Enter photographic mode only when the image has enough
                     * vertical AND horizontal resolution to be interpretively
                     * useful without distortion.
                     */
                    /*
                     * Gradational Core-presence cue.
                     *
                     * Long before photography is useful, the interpreter must
                     * be able to see that physical Core exists at this MD.
                     *
                     * As WDV approaches photographic recognition scale the
                     * placement cue becomes progressively wider and stronger.
                     * No JPEG is requested until photographic mode begins.
                     */
                    const photoPixelsPerMdThreshold = CORE_PHOTO_THRESHOLD_PIXELS_PER_MD;
                    const photoWidthThresholdPx = CORE_PHOTO_THRESHOLD_WIDTH_PX;

                    const presenceStartPixelsPerMd = 15;
                    const presenceStartWidthPx = 1.5;

                    const verticalProgress = clampValue(
                        (
                            pixelsPerMd
                            - presenceStartPixelsPerMd
                        ) / (
                            photoPixelsPerMdThreshold
                            - presenceStartPixelsPerMd
                        ),
                        0,
                        1,
                    );

                    const horizontalProgress = clampValue(
                        (
                            renderedImageWidth
                            - presenceStartWidthPx
                        ) / (
                            photoWidthThresholdPx
                            - presenceStartWidthPx
                        ),
                        0,
                        1,
                    );

                    const coreDetailProgress = Math.min(
                        verticalProgress,
                        horizontalProgress,
                    );

                    /*
                     * 0.0 = unmistakable macro Core-location marker.
                     * 1.0 = immediately before photographic rendering.
                     */
                    const placementInsetPercent =
                        30 - coreDetailProgress * 18;

                    const placementOpacity =
                        0.30 + coreDetailProgress * 0.45;

                    /*
                     * A chunk with valid native geometry is renderable even if
                     * its dimensions differ from the product median by >5%.
                     * Uniform per-chunk scaling below still preserves aspect
                     * ratio, so geometryConsistent is diagnostic only.
                     */
                    const geometryEligibleForPhoto =
                        geometryConsistent || hasNativeGeometry;

                    const showPhotograph =
                        hasNativeGeometry
                        && geometryEligibleForPhoto
                        && pixelsPerMd >= photoPixelsPerMdThreshold;

                    if (!showPhotograph) {
                        const coreAppearance = appearance;
                        const placementStage =
                            coreDetailProgress < 0.30
                                ? 'macro'
                                : coreDetailProgress < 0.70
                                    ? 'mid'
                                    : 'near';

                        return (
                            <div
                                key={`${item.productId}:${chunk.chunk_id}`}
                                className={
                                    `wlv-core-placement-segment `
                                    + `is-${placementStage}`
                                }
                                data-core-detail-progress={
                                    coreDetailProgress.toFixed(3)
                                }
                                style={{
                                    top,
                                    height,
                                    left: `${placementInsetPercent}%`,
                                    right: `${placementInsetPercent}%`,
                                    opacity: placementOpacity,
                                    background: corePlacementBackground(coreAppearance),
                                    borderColor: mixHex(coreAppearance.baseColor, '#cfd5db', 0.22),
                                    boxShadow: coreAppearance.shadingMode === 'cylindrical'
                                        ? `inset 0 0 0 1px ${rgbaFromHex('#111820', 18)}, inset 8px 0 12px ${rgbaFromHex('#111820', 14)}, inset -8px 0 12px ${rgbaFromHex('#111820', 14)}`
                                        : `inset 0 0 0 1px ${rgbaFromHex('#111820', 14)}`,
                                    ['--wlv-core-detail-progress' as string]:
                                        coreDetailProgress,
                                }}
                                title={
                                    `${item.label} · `
                                    + `${chunk.top_depth}–${chunk.base_depth} `
                                    + `${chunk.depth_unit || item.depthUnit} MD`
                                }
                            />
                        );
                    }

                    const imageUrl =
                        `${wlvApiBaseUrl()}/api/wlv/inventory/wells/`
                        + `${encodeURIComponent(item.managedWellId)}`
                        + `/core-segment-display-chunk`
                        + `?product_id=${encodeURIComponent(item.productId)}`
                        + `&chunk_id=${encodeURIComponent(chunk.chunk_id)}`;

                    return (
                        <div
                            key={`${item.productId}:${chunk.chunk_id}`}
                            className="wlv-core-image-segment"
                            style={{ top, height }}
                            title={
                                `${item.label} · `
                                + `${chunk.top_depth}–${chunk.base_depth} `
                                + `${chunk.depth_unit || item.depthUnit} MD`
                            }
                        >
                            <img
                                src={imageUrl}
                                alt={item.label}
                                draggable={false}
                                loading="lazy"
                                decoding="async"
                                style={{
                                    width: renderedImageWidth,
                                    height,
                                }}
                            />
                        </div>
                    );
                })}
            </>
        );
    }


    /*
     * V1 backward compatibility:
     * - a V1 package returns an empty chunk manifest;
     * - a server without the V2 route may fail the manifest request.
     *
     * In both cases retain the original single-image renderer.
     */
    if (
        manifestFailed
        || (manifest !== null && manifest.chunks.length === 0)
    ) {
        if (
            item.baseMd < viewDepthRange.min
            || item.topMd > viewDepthRange.max
        ) {
            return null;
        }

        const top = depthToYUnclamped(
            item.topMd,
            viewDepthRange,
            trackBodyHeightPx,
        );
        const base = depthToYUnclamped(
            item.baseMd,
            viewDepthRange,
            trackBodyHeightPx,
        );
        const height = Math.max(1, base - top);

        return (
            <div
                className="wlv-core-image-segment"
                style={{ top, height }}
                title={
                    `${item.label} · `
                    + `${item.topMd}–${item.baseMd} ${item.depthUnit} MD`
                }
            >
                <img
                    src={`${wlvApiBaseUrl()}${item.imageUrl}`}
                    alt={item.label}
                    draggable={false}
                    loading="lazy"
                    decoding="async"
                />
            </div>
        );
    }

    return null;
}


function CoreDescriptionOverlayPane({
    items,
    selectedIds,
    viewDepthRange,
    trackBodyHeightPx,
    appearance,
}: {
    items: CoreImageInventoryItem[];
    selectedIds: Set<string>;
    viewDepthRange: DepthViewRange;
    trackBodyHeightPx: number;
    appearance: CoreTrackAppearance;
}) {
    const explicit = items.filter((item) => selectedIds.has(item.productId));
    const sourceItems = explicit.length > 0 ? explicit : items;
    const seen = new Set<string>();
    const descriptions = sourceItems
        .flatMap((item) => item.descriptions ?? [])
        .filter((item) => {
            if (!Number.isFinite(item.md) || !item.text.trim() || seen.has(item.descriptionId)) return false;
            seen.add(item.descriptionId);
            return item.md >= viewDepthRange.min && item.md <= viewDepthRange.max;
        })
        .sort((left, right) => left.md - right.md || left.descriptionId.localeCompare(right.descriptionId))
        .map((item) => ({
            ...item,
            y: depthToY(item.md, viewDepthRange, trackBodyHeightPx),
        }));

    const fontSize = clampValue(appearance.descriptionOverlayFontSize, 8, 20);
    const minimumSpacing = Math.max(14, fontSize * 1.45);
    let lastLabelY = Number.NEGATIVE_INFINITY;

    const displayed = descriptions.map((item) => {
        const showLabel = item.y - lastLabelY >= minimumSpacing;
        if (showLabel) lastLabelY = item.y;
        return { ...item, showLabel };
    });

    return (
        <div
            className="wlv-core-description-overlay-pane"
            aria-label="Core Description overlay"
        >
            {displayed.map((item) => (
                <div
                    key={item.descriptionId}
                    className="wlv-core-description-overlay-marker"
                    style={{ top: item.y }}
                    title={`${item.md.toLocaleString(undefined, { maximumFractionDigits: 3 })} m MD · ${item.text}`}
                >
                    <i aria-hidden="true" />
                    {item.showLabel ? (
                        <div
                            className="wlv-core-description-overlay-label"
                            style={{ fontSize: `${fontSize}px` }}
                        >
                            {appearance.descriptionOverlayShowMd ? (
                                <strong>
                                    {item.md.toLocaleString(undefined, { maximumFractionDigits: 3 })} m MD
                                </strong>
                            ) : null}
                            <span>{item.text}</span>
                        </div>
                    ) : null}
                </div>
            ))}
        </div>
    );
}

export function CoreImageTrackView({
    items,
    selectedIds,
    viewDepthRange,
    trackBodyHeightPx,
    appearance,
}: {
    items: CoreImageInventoryItem[];
    selectedIds: Set<string>;
    viewDepthRange: DepthViewRange;
    trackBodyHeightPx: number;
    appearance: CoreTrackAppearance;
}) {
    /*
     * CORE PRODUCT SELECTION CONTRACT:
     *
     * An empty selectedIds set means "no explicit product subset", not
     * "render no Core". The Core header and full-range calculation already
     * use this rule; the body must use the same authority.
     */
    const explicitlySelectedItems = items.filter(
        (item) => selectedIds.has(item.productId),
    );

    const renderItems =
        explicitlySelectedItems.length > 0
            ? explicitlySelectedItems
            : items;

    const selectedVisibleItems = renderItems.filter(
        (item) =>
            item.baseMd >= viewDepthRange.min
            && item.topMd <= viewDepthRange.max,
    );

    const coreViewSpan = Math.max(
        1e-9,
        viewDepthRange.max - viewDepthRange.min,
    );
    const corePixelsPerMd = Math.max(0, trackBodyHeightPx / coreViewSpan);
    const corePhotoThresholdIndex = clampValue(
        Math.round(
            100
            * (
                corePixelsPerMd
                / CORE_PHOTO_THRESHOLD_PIXELS_PER_MD
                - 1
            ),
        ),
        -100,
        0,
    );
    const showCorePhotoThresholdIndex =
        selectedVisibleItems.length > 0
        && corePixelsPerMd <= CORE_PHOTO_THRESHOLD_PIXELS_PER_MD;

    const presentationMode = appearance.descriptionPresentationMode;
    const descriptionOverlayEnabled = presentationMode !== 'core_centered';
    const descriptionOnLeft = presentationMode === 'description_left_core_right';
    const descriptionWidthPct = clampValue(appearance.descriptionOverlayWidthPct, 20, 70);
    const imageLaneStyle = descriptionOverlayEnabled
        ? descriptionOnLeft
            ? { left: `${descriptionWidthPct}%`, right: 0 }
            : { left: 0, right: `${descriptionWidthPct}%` }
        : { left: 0, right: 0 };
    const descriptionLaneStyle = descriptionOnLeft
        ? { left: 0, width: `${descriptionWidthPct}%` }
        : { right: 0, width: `${descriptionWidthPct}%` };

    return (
        <div
            className={
                `wlv-core-track-body is-${presentationMode}`
                + `${descriptionOverlayEnabled ? ' has-description-overlay' : ''}`
            }
            aria-label="Depth-calibrated core images"
        >
            <div className="wlv-core-image-lane" style={imageLaneStyle}>
                {selectedVisibleItems.map((item) => (
                    <CoreImageProductView
                        key={item.productId}
                        item={item}
                        viewDepthRange={viewDepthRange}
                        trackBodyHeightPx={trackBodyHeightPx}
                        appearance={appearance}
                    />
                ))}
                {showCorePhotoThresholdIndex ? (
                    <span
                        className="wlv-core-photo-threshold-index"
                        aria-label={`Core photo threshold ${corePhotoThresholdIndex}`}
                        title="Core photo rendering threshold: 0"
                    >
                        {corePhotoThresholdIndex}
                    </span>
                ) : null}
            </div>

            {descriptionOverlayEnabled ? (
                <div
                    className={`wlv-core-description-overlay-lane is-${descriptionOnLeft ? 'left' : 'right'}`}
                    style={descriptionLaneStyle}
                >
                    <CoreDescriptionOverlayPane
                        items={items}
                        selectedIds={selectedIds}
                        viewDepthRange={viewDepthRange}
                        trackBodyHeightPx={trackBodyHeightPx}
                        appearance={appearance}
                    />
                </div>
            ) : null}
        </div>
    );
}

export function DepthTrackView({
    track,
    depthTicks: _depthTicks,
    viewDepthRange,
    trackBodyHeightPx,
}: {
    track: DepthTrack;
    depthTicks: number[];
    viewDepthRange: DepthViewRange;
    trackBodyHeightPx: number;
}) {
    const renderedDepthTicks = useMemo(() => {
        const span = viewDepthRange.max - viewDepthRange.min;
        if (!Number.isFinite(span) || span <= 0) {
            return [] as AdaptiveDepthTick[];
        }

        /*
         * Choose a major interval from a 1/2/5 decade sequence.
         * Aim for labelled ticks roughly 70–90 px apart.
         */
        const targetMajorCount = Math.max(
            2,
            Math.floor(Math.max(1, trackBodyHeightPx) / 78),
        );

        const rawMajorStep = span / targetMajorCount;
        const exponent = Math.floor(Math.log10(rawMajorStep));
        const magnitude = 10 ** exponent;
        const normalized = rawMajorStep / magnitude;

        const multiplier =
            normalized <= 1 ? 1
            : normalized <= 2 ? 2
            : normalized <= 5 ? 5
            : 10;

        const majorStep = multiplier * magnitude;
        const minorStep = majorStep / 5;

        const startIndex = Math.ceil(
            (viewDepthRange.min - minorStep * 1e-7) / minorStep,
        );
        const endIndex = Math.floor(
            (viewDepthRange.max + minorStep * 1e-7) / minorStep,
        );

        const ticks: AdaptiveDepthTick[] = [];

        for (
            let index = startIndex;
            index <= endIndex && ticks.length < 1000;
            index += 1
        ) {
            const depth = Number(
                (index * minorStep).toPrecision(12),
            );

            const nearestMajor =
                Math.round(depth / majorStep) * majorStep;

            const major =
                Math.abs(depth - nearestMajor)
                <= Math.max(1e-10, minorStep * 1e-5);

            ticks.push({
                depth,
                labelled: major,
                major,
            });
        }

        return ticks;
    }, [
        viewDepthRange.min,
        viewDepthRange.max,
        trackBodyHeightPx,
    ]);

    const span = viewDepthRange.max - viewDepthRange.min;

    const labelDecimals =
        span <= 0.2 ? 3
        : span <= 2 ? 2
        : span <= 20 ? 1
        : 0;

    return (
        <div className="wlv-depth-track-body">
            {renderedDepthTicks.map((tick, depthIndex) => {
                const y = depthToY(
                    tick.depth,
                    viewDepthRange,
                    trackBodyHeightPx,
                );

                return (
                    <div
                        key={`${track.trackId}:depth-tick:${tick.depth}:${depthIndex}`}
                        className={
                            `wlv-depth-tick `
                            + `${tick.major ? 'major' : 'minor'} `
                            + `${tick.labelled ? 'labelled' : 'unlabelled'}`
                        }
                        style={{ top: y }}
                    >
                        {tick.labelled ? (
                            <span>
                                {tick.depth.toFixed(labelDecimals)}
                            </span>
                        ) : null}
                    </div>
                );
            })}
        </div>
    );
}

export function LithologyTrackView({ track, viewDepthRange, trackBodyHeightPx, }: {
    track: LithologyTrack;
    viewDepthRange: DepthViewRange;
    trackBodyHeightPx: number;
}) {
    const visibleIntervals = lithologyIntervals21_31.filter((interval) => (interval.baseFt >= viewDepthRange.min && interval.topFt <= viewDepthRange.max));
    return (<div className="wlv-lithology-track-body" aria-label={`${track.title} intervals for ${track.wellName}`}>
      {visibleIntervals.map((interval) => {
            const clippedTop = Math.max(interval.topFt, viewDepthRange.min);
            const clippedBase = Math.min(interval.baseFt, viewDepthRange.max);
            const top = depthToY(clippedTop, viewDepthRange, trackBodyHeightPx);
            const base = depthToY(clippedBase, viewDepthRange, trackBodyHeightPx);
            const height = Math.max(2, base - top);
            const showCode = height >= 16;
            const showName = height >= 40;
            const showTopDepth = height >= 26 && clippedTop === interval.topFt;
            const showBaseDepth = height >= 34 && clippedBase === interval.baseFt;
            return (<div key={interval.intervalId} className={`wlv-lithology-interval lith-${interval.unit.toLowerCase()}`} style={{
                    top,
                    height,
                    backgroundColor: interval.color,
                    backgroundImage: lithologyPattern(interval.unit),
                }} title={`${interval.unit}: ${interval.unitName} (${interval.topFt}–${interval.baseFt} ft MD)`}>
            {showTopDepth && <div className="wlv-lithology-depth-label top">{interval.topFt.toFixed(0)}</div>}
            <div className="wlv-lithology-interval-content">
              {showCode && <strong>{interval.unit}</strong>}
              {showName && <span>{interval.unitName}</span>}
            </div>
            {showBaseDepth && <div className="wlv-lithology-depth-label base">{interval.baseFt.toFixed(0)}</div>}
          </div>);
        })}
    </div>);
}
export type TrackContentCategory = 'curves' | 'curve-fill' | 'formation-tops' | 'tops-fill' | 'core' | 'raster' | 'other-overlays';

const DEFAULT_TRACK_CONTENT_ORDER: TrackContentCategory[] = [
    'formation-tops', 'curves', 'curve-fill', 'tops-fill', 'core', 'raster', 'other-overlays',
];

function trackContentCategoryLabel(category: TrackContentCategory): string {
    const labels: Record<TrackContentCategory, string> = {
        'curves': 'Curves',
        'curve-fill': 'Curve Fill',
        'formation-tops': 'Formation Tops',
        'tops-fill': 'Tops Fill',
        'core': 'Core',
        'raster': 'Raster / Image',
        'other-overlays': 'Other Overlays',
    };
    return labels[category];
}

function normalizedTrackContentOrder(order: TrackContentCategory[] | undefined): TrackContentCategory[] {
    const supplied = Array.isArray(order) ? order : [];
    return [
        ...supplied.filter((value, index) => DEFAULT_TRACK_CONTENT_ORDER.includes(value) && supplied.indexOf(value) === index),
        ...DEFAULT_TRACK_CONTENT_ORDER.filter((value) => !supplied.includes(value)),
    ];
}

function trackContentZIndex(order: TrackContentCategory[], category: TrackContentCategory): number {
    const normalized = normalizedTrackContentOrder(order);
    const index = normalized.indexOf(category);
    return 20 + Math.max(0, normalized.length - (index < 0 ? normalized.length : index));
}

function curveFillPolygonPathV2(
    geometry: CurveFillGeometryV2,
    viewDepthRange: DepthViewRange,
    trackBodyHeightPx: number,
): string[] {
    return geometry.polygons.flatMap((polygon) => {
        if (polygon.vertices.length < 2) return [];
        const left = polygon.vertices.map((vertex) =>
            `${vertex.x_a_px},${depthToY(vertex.depth, viewDepthRange, trackBodyHeightPx)}`
        );
        const right = [...polygon.vertices].reverse().map((vertex) =>
            `${vertex.x_b_px},${depthToY(vertex.depth, viewDepthRange, trackBodyHeightPx)}`
        );
        return [`M ${left.join(' L ')} L ${right.join(' L ')} Z`];
    });
}


type TransientCurveFillDraft = {
  trackId: string;
  curveAAssignmentId: string;
  body: {
    rule_type?: string;
    boundary?: string | null;
    comparison?: string | null;
    curve_b_assignment_uid?: string;
    reference_value?: number;
    band_min_value?: number;
    band_max_value?: number;
    depth_extent?: string;
    interval_from_md?: number | null;
    interval_to_md?: number | null;
    style?: {
      appearance?: string;
      color?: string;
      opacity?: number;
      pattern_uid?: string | null;
      pattern_scale?: number;
      raster_asset_uid?: string | null;
    };
  };
};

const CURVE_FILL_TRANSIENT_PREVIEW_EVENT =
  "wlv:curve-fill-transient-preview";
const CURVE_FILL_TRANSIENT_PREVIEW_CLEAR_EVENT =
  "wlv:curve-fill-transient-preview-clear";

const NATIVE_CURVE_FILL_PATTERN_UIDS = new Set([
  'hatch-45-v1',
  'crosshatch-v1',
  'cross-hatch-v1',
  'dots-v1',
  'bricks-v1',
  'stipple-v1',
  'lithology-column-v1',
]);

function isKrCurveFillPatternUid(
    value: string | null | undefined,
): boolean {
    return Boolean(
        value
        && !NATIVE_CURVE_FILL_PATTERN_UIDS.has(value),
    );
}

function curveFillPaintId(ruleUid: string): string { return `curve-fill-paint-${ruleUid.replace(/[^a-zA-Z0-9_-]/g, '-')}`; }
function curveFillLithologyPaintId(ruleUid: string, intervalId: string): string {
  return `curve-fill-lithology-${ruleUid}-${intervalId}`.replace(/[^a-zA-Z0-9_-]/g, '-');
}
function curveFillLithologyClipId(ruleUid: string, intervalId: string): string {
  return `curve-fill-lithology-clip-${ruleUid}-${intervalId}`.replace(/[^a-zA-Z0-9_-]/g, '-');
}
function curveFillSvgPaint(geometry: CurveFillGeometryV2): string {
  const paint = resolvedCurveFillPaintV2(geometry);
  if (paint.appearance === 'solid') return geometry.style.color;
  return `url(#${curveFillPaintId(geometry.rule_uid)})`;
}

export function CurveTrackView({ track, depthTicks, viewDepthRange, trackBodyHeightPx, managedSamplesByCurveId, managedSampleErrorsByCurveId, curveCatalogItems, lithologyIntervals = [], curveFillGeometryByRuleUid = new Map(), transientCurveFillDraft = null, renderMode = 'all', }: {
    track: CurveTrack;
    depthTicks: number[];
    viewDepthRange: DepthViewRange;
    trackBodyHeightPx: number;
    managedSamplesByCurveId: ManagedCurveSamplesByCurveId;
    managedSampleErrorsByCurveId: Record<string, string>;
    curveCatalogItems: CurveCatalogItem[];
    lithologyIntervals?: LithologyIntervalRecord[];
    curveFillGeometryByRuleUid?: ReadonlyMap<string, CurveFillGeometryV2>;
    transientCurveFillDraft?: TransientCurveFillDraft | null;
    renderMode?: 'all' | 'grid' | 'curve-fill' | 'curves';
}) {
    const ordered = orderedCurves(track);
    const backToFront = [...ordered].sort((a, b) => {
        const priorityDelta = curvePriorityWeight(a) - curvePriorityWeight(b);
        if (priorityDelta !== 0)
            return priorityDelta;
        return b.stackIndex - a.stackIndex;
    });
    const lattice = resolveTrackLattice(track, curveCatalogItems);
    const trackWidth = clampCurveTrackWidth(track.widthPx);
    const missingSampleMessages = ordered
        .map((assignment) => resolveManagedCurveError(managedSampleErrorsByCurveId, {
            managedWellUid: assignment.managedWellUid ?? null,
            curveUid: assignment.curveUid ?? null,
            curveId: assignment.curveId,
        }))
        .filter((message, index, all): message is string => Boolean(message) && all.indexOf(message) === index);
    const curveFillGeometry = [...curveFillGeometryByRuleUid.values()]
        .filter((geometry) => geometry.track_uid === track.trackId)
        .sort((left, right) => left.order - right.order || left.rule_uid.localeCompare(right.rule_uid));
    // Curve Fill v2 is backend-owned. Once canonical geometry exists for the
    // track, do not also render the legacy assignment-level fill polygon. The
    // legacy path is independently sampled and can self-intersect at crossings,
    // creating the triangular white gaps seen in paired-curve fills.
    const canonicalCurveFillActive = curveFillGeometry.length > 0;
    const previewDraft =
        transientCurveFillDraft?.trackId === track.trackId
            ? transientCurveFillDraft
            : null;
    const previewAssignmentA = previewDraft
        ? ordered.find(
            (candidate) =>
                candidate.assignmentId === previewDraft.curveAAssignmentId,
        ) ?? null
        : null;
    const previewAssignmentB = previewDraft?.body.curve_b_assignment_uid
        ? ordered.find(
            (candidate) =>
                candidate.assignmentId
                    === previewDraft.body.curve_b_assignment_uid,
        ) ?? null
        : null;
    const previewCurveA = previewAssignmentA
        ? resolveCurveAssignmentCatalogItem(curveCatalogItems, previewAssignmentA)
        : null;
    const previewCurveB = previewAssignmentB
        ? resolveCurveAssignmentCatalogItem(curveCatalogItems, previewAssignmentB)
        : null;
    const previewPointsA =
        previewCurveA && previewAssignmentA
            ? curveRenderPoints(
                previewCurveA,
                previewAssignmentA,
                track.trackIndex,
                viewDepthRange,
                lattice.lattice,
                trackWidth,
                trackBodyHeightPx,
                managedSamplesByCurveId,
            ).filter((point) => {
                if (
                    previewDraft?.body.depth_extent
                    !== 'specified_interval'
                ) return true;
                const from = previewDraft.body.interval_from_md;
                const to = previewDraft.body.interval_to_md;
                return (
                    typeof from === 'number'
                    && typeof to === 'number'
                    && point.depth >= Math.min(from, to)
                    && point.depth <= Math.max(from, to)
                );
            })
            : [];
    const previewPointsB =
        previewCurveB && previewAssignmentB
            ? curveRenderPoints(
                previewCurveB,
                previewAssignmentB,
                track.trackIndex,
                viewDepthRange,
                lattice.lattice,
                trackWidth,
                trackBodyHeightPx,
                managedSamplesByCurveId,
            ).filter((point) => {
                if (
                    previewDraft?.body.depth_extent
                    !== 'specified_interval'
                ) return true;
                const from = previewDraft.body.interval_from_md;
                const to = previewDraft.body.interval_to_md;
                return (
                    typeof from === 'number'
                    && typeof to === 'number'
                    && point.depth >= Math.min(from, to)
                    && point.depth <= Math.max(from, to)
                );
            })
            : [];
    const previewReferenceX =
        previewAssignmentA
        && typeof previewDraft?.body.reference_value === 'number'
            ? valueToX(
                previewDraft.body.reference_value,
                previewAssignmentA,
                lattice.lattice,
                trackWidth,
            )
            : null;
    const previewBandMinX =
        previewAssignmentA
        && typeof previewDraft?.body.band_min_value === 'number'
            ? valueToX(previewDraft.body.band_min_value, previewAssignmentA, lattice.lattice, trackWidth)
            : null;
    const previewBandMaxX =
        previewAssignmentA
        && typeof previewDraft?.body.band_max_value === 'number'
            ? valueToX(previewDraft.body.band_max_value, previewAssignmentA, lattice.lattice, trackWidth)
            : null;
    const previewPath =
        previewDraft?.body.rule_type === 'between_curves'
        || previewDraft?.body.rule_type === 'conditional'
        || previewDraft?.body.rule_type === 'crossover'
            ? polygonBetweenCurves(previewPointsA, previewPointsB)
            : previewDraft?.body.rule_type === 'to_boundary'
                ? polygonToAnchor(
                    previewPointsA,
                    previewDraft?.body.boundary === 'left' ? 0 : trackWidth,
                )
                : previewDraft?.body.rule_type === 'curve_to_value' && previewReferenceX !== null
                    ? polygonToAnchor(previewPointsA, previewReferenceX)
                    : previewDraft?.body.rule_type === 'threshold' && previewReferenceX !== null
                        ? polygonThresholdToAnchor(
                            previewPointsA,
                            previewReferenceX,
                            previewDraft.body.boundary === 'left'
                                ? 0
                                : previewDraft.body.boundary === 'right'
                                    ? trackWidth
                                    : previewReferenceX,
                            previewDraft.body.comparison,
                            previewAssignmentA?.scaleDirection,
                        )
                        : previewDraft?.body.rule_type === 'value_band' && previewBandMinX !== null && previewBandMaxX !== null
                            ? polygonBetweenCurves(
                                previewPointsA.map((point) => ({ ...point, x: previewBandMinX })),
                                previewPointsA.map((point) => ({ ...point, x: previewBandMaxX })),
                            )
                            : null;
    const previewStyle = previewDraft?.body.style ?? {};
    const previewPatternId = `curve-fill-transient-${track.trackId}`;
    return (<svg className={`wlv-curve-track-svg ${lattice.lattice} ${renderMode === 'grid' || renderMode === 'all' ? 'grid-layer' : 'content-layer'}`} viewBox={`0 0 ${trackWidth} ${trackBodyHeightPx}`} preserveAspectRatio="none">
      <defs>
        <pattern id={`infill-hatch-${track.trackId}`} width="8" height="8" patternUnits="userSpaceOnUse">
          <path d="M -2 8 L 8 -2 M 0 10 L 10 0" stroke="currentColor" strokeWidth="1" opacity="0.55"/>
        </pattern>
        <pattern id={`infill-dots-${track.trackId}`} width="8" height="8" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.2" fill="currentColor" opacity="0.5"/>
        </pattern>
      </defs>
      {(renderMode === 'all' || renderMode === 'grid') ? (<>
      {lattice.lattice === 'logarithmic' ? (<>
          <rect className="wlv-log-grid-background" x="0" y="0" width={trackWidth} height={trackBodyHeightPx}/>
          {renderLogarithmicGrid(track, trackWidth, trackBodyHeightPx)}
        </>) : (<>
          <defs>
            <pattern id={`grid-${track.trackId}`} width="24" height="30" patternUnits="userSpaceOnUse">
              <path d="M 24 0 L 0 0 0 30" fill="none" stroke="#e0e6ed" strokeWidth="1"/>
            </pattern>
          </defs>
          <rect x="0" y="0" width={trackWidth} height={trackBodyHeightPx} fill={`url(#grid-${track.trackId})`}/>
        </>)}
      {depthTicks.map((depth, depthIndex) => {
            const y = depthToY(depth, viewDepthRange, trackBodyHeightPx);
            return <line key={`${track.trackId}:curve-grid:${depth}:${depthIndex}`} x1="0" x2={trackWidth} y1={y} y2={y} stroke="#aeb8c5" strokeWidth="1"/>;
        })}
      </>) : null}
      {(renderMode === 'all' || renderMode === 'curve-fill') ? (<>
      <defs>
        {previewDraft && previewStyle.appearance === 'pattern' ? (
          previewStyle.pattern_uid === 'lithology-column-v1' ? (
            <Fragment>
              {lithologyIntervals.map((interval) => {
                const id = `${previewPatternId}-${interval.intervalId}`;
                const topY = depthToY(
                  interval.topMd,
                  viewDepthRange,
                  trackBodyHeightPx,
                );
                const baseY = depthToY(
                  interval.baseMd,
                  viewDepthRange,
                  trackBodyHeightPx,
                );
                return <Fragment key={id}>
                  <pattern id={id} width="32" height="32" patternUnits="userSpaceOnUse">
                    <image
                      href={lithologyPatternUrl(interval.patternId)}
                      x="0" y="0" width="32" height="32"
                      preserveAspectRatio="none"
                    />
                  </pattern>
                  <clipPath id={`${id}-clip`}>
                    <rect
                      x="0"
                      y={Math.min(topY, baseY)}
                      width={trackWidth}
                      height={Math.max(0, Math.abs(baseY - topY))}
                    />
                  </clipPath>
                </Fragment>;
              })}
            </Fragment>
          ) : isKrCurveFillPatternUid(previewStyle.pattern_uid) ? (
            <pattern
              id={previewPatternId}
              width={
                32 * Math.max(
                  0.25,
                  previewStyle.pattern_scale ?? 1,
                )
              }
              height={
                32 * Math.max(
                  0.25,
                  previewStyle.pattern_scale ?? 1,
                )
              }
              patternUnits="userSpaceOnUse"
            >
              <image
                href={lithologyPatternUrl(
                  previewStyle.pattern_uid ?? '',
                  previewStyle.color ?? '#d94841',
                )}
                x="0"
                y="0"
                width={
                  32 * Math.max(
                    0.25,
                    previewStyle.pattern_scale ?? 1,
                  )
                }
                height={
                  32 * Math.max(
                    0.25,
                    previewStyle.pattern_scale ?? 1,
                  )
                }
                preserveAspectRatio="none"
              />
            </pattern>
          ) : (
            <pattern
              id={previewPatternId}
              width={8 * Math.max(0.25, previewStyle.pattern_scale ?? 1)}
              height={8 * Math.max(0.25, previewStyle.pattern_scale ?? 1)}
              patternUnits="userSpaceOnUse"
            >
              {previewStyle.pattern_uid === 'dots-v1' ? (
                <circle cx="2" cy="2" r="1.2" fill={previewStyle.color ?? '#d94841'}/>
              ) : previewStyle.pattern_uid === 'cross-hatch-v1' ? (
                <path d="M -2 8 L 8 -2 M 0 10 L 10 0 M -2 0 L 8 10 M 0 -2 L 10 8"
                  stroke={previewStyle.color ?? '#d94841'} strokeWidth="1"/>
              ) : previewStyle.pattern_uid === 'bricks-v1' ? (
                <path d="M0 0H8 M0 4H8 M0 8H8 M0 0V4 M4 4V8 M8 0V4"
                  stroke={previewStyle.color ?? '#d94841'} strokeWidth="1" fill="none"/>
              ) : (
                <path d="M -2 8 L 8 -2 M 0 10 L 10 0"
                  stroke={previewStyle.color ?? '#d94841'} strokeWidth="1"/>
              )}
            </pattern>
          )
        ) : null}
        {curveFillGeometry.map((geometry) => {
        const id = curveFillPaintId(geometry.rule_uid);
        const paint = resolvedCurveFillPaintV2(geometry);
        if (paint.appearance === 'raster' && paint.raster) {
          const topY = depthToY(paint.raster.top_depth, viewDepthRange, trackBodyHeightPx);
          const baseY = depthToY(paint.raster.base_depth, viewDepthRange, trackBodyHeightPx);
          const y = Math.min(topY, baseY);
          const height = Math.max(1, Math.abs(baseY - topY));
          return <pattern key={id} id={id} x="0" y={y} width={trackWidth} height={height} patternUnits="userSpaceOnUse"><image href={paint.raster.image_url} x="0" y={y} width={trackWidth} height={height} preserveAspectRatio={paint.raster.horizontal_fit === 'stretch' ? 'none' : 'xMidYMid slice'} /></pattern>;
        }
        if (paint.appearance !== 'pattern') return null;
        const scale = Math.max(0.25, paint.pattern_scale || 1);
        if (paint.pattern_uid === 'lithology-column-v1') {
          return <Fragment key={id}>
            {lithologyIntervals.map((interval) => {
              const patternId = curveFillLithologyPaintId(geometry.rule_uid, interval.intervalId);
              const clipId = curveFillLithologyClipId(geometry.rule_uid, interval.intervalId);
              const topY = depthToY(interval.topMd, viewDepthRange, trackBodyHeightPx);
              const baseY = depthToY(interval.baseMd, viewDepthRange, trackBodyHeightPx);
              const y = Math.min(topY, baseY);
              const height = Math.max(0, Math.abs(baseY - topY));
              const size = 32 * scale;
              return <Fragment key={patternId}>
                <pattern id={patternId} width={size} height={size} patternUnits="userSpaceOnUse">
                  <image href={lithologyPatternUrl(interval.patternId)}
                    x="0" y="0" width={size} height={size} preserveAspectRatio="none"/>
                </pattern>
                <clipPath id={clipId}>
                  <rect x="0" y={y} width={trackWidth} height={height}/>
                </clipPath>
              </Fragment>;
            })}
          </Fragment>;
        }
        const size = 8 * scale;
        if (isKrCurveFillPatternUid(paint.pattern_uid)) {
          const lithologySize = 32 * scale;
          return <pattern key={id} id={id} width={lithologySize} height={lithologySize} patternUnits="userSpaceOnUse"><image href={lithologyPatternUrl(paint.pattern_uid ?? '', geometry.style.color)} x="0" y="0" width={lithologySize} height={lithologySize} preserveAspectRatio="none"/></pattern>;
        }
        if (paint.pattern_uid === 'dots-v1') return <pattern key={id} id={id} width={size} height={size} patternUnits="userSpaceOnUse"><circle cx={size/2} cy={size/2} r={Math.max(1, scale)} fill={geometry.style.color}/></pattern>;
        if (paint.pattern_uid === 'crosshatch-v1') return <pattern key={id} id={id} width={size} height={size} patternUnits="userSpaceOnUse"><path d={`M0 ${size}L${size} 0M0 0L${size} ${size}`} stroke={geometry.style.color} strokeWidth={Math.max(1, scale)}/></pattern>;
        if (paint.pattern_uid === 'bricks-v1') return <pattern key={id} id={id} width={size*2} height={size} patternUnits="userSpaceOnUse"><path d={`M0 0H${size*2}V${size}H0ZM0 ${size/2}H${size*2}M${size} 0V${size/2}M${size/2} ${size/2}V${size}`} fill="none" stroke={geometry.style.color} strokeWidth={Math.max(1, scale)}/></pattern>;
        return <pattern key={id} id={id} width={size} height={size} patternUnits="userSpaceOnUse"><path d={`M-${size/4} ${size/4}L${size/4} -${size/4}M0 ${size}L${size} 0M${size*3/4} ${size*5/4}L${size*5/4} ${size*3/4}`} stroke={geometry.style.color} strokeWidth={Math.max(1, scale)}/></pattern>;
      })}</defs>
      {previewDraft && previewPath ? (
        previewStyle.appearance === 'pattern'
        && previewStyle.pattern_uid === 'lithology-column-v1' ? (
          <>
            {lithologyIntervals.map((interval) => {
              const id = `${previewPatternId}-${interval.intervalId}`;
              return (
                <path
                  key={`${id}-path`}
                  d={previewPath}
                  fill={`url(#${id})`}
                  fillOpacity={previewStyle.opacity ?? 0.45}
                  clipPath={`url(#${id}-clip)`}
                  stroke="none"
                  data-curve-fill-transient-preview="true"
                />
              );
            })}
          </>
        ) : (
          <path
            d={previewPath}
            fill={
              previewStyle.appearance === 'pattern'
                ? `url(#${previewPatternId})`
                : (previewStyle.color ?? '#d94841')
            }
            fillOpacity={previewStyle.opacity ?? 0.45}
            stroke="none"
            data-curve-fill-transient-preview="true"
          />
        )
      ) : null}
      {curveFillGeometry.flatMap((geometry) => {
          const paths = curveFillPolygonPathV2(geometry, viewDepthRange, trackBodyHeightPx);
          const paint = resolvedCurveFillPaintV2(geometry);
          if (paint.pattern_uid === 'lithology-column-v1') {
            return lithologyIntervals.flatMap((interval) => {
              if (interval.baseMd <= viewDepthRange.min || interval.topMd >= viewDepthRange.max) return [];
              const patternId = curveFillLithologyPaintId(geometry.rule_uid, interval.intervalId);
              const clipId = curveFillLithologyClipId(geometry.rule_uid, interval.intervalId);
              return paths.map((path, index) => (
                <path key={`${geometry.rule_uid}-${geometry.geometry_revision}-${interval.intervalId}-${index}`}
                  d={path} fill={`url(#${patternId})`} fillOpacity={geometry.style.opacity}
                  clipPath={`url(#${clipId})`} stroke="none"
                  data-curve-fill-rule-uid={geometry.rule_uid}
                  data-lithology-interval-id={interval.intervalId}/>
              ));
            });
          }
          return paths.map((path, index) => (
            <path key={`${geometry.rule_uid}-${geometry.geometry_revision}-${index}`} d={path} fill={curveFillSvgPaint(geometry)} fillOpacity={geometry.style.opacity} stroke="none" data-curve-fill-rule-uid={geometry.rule_uid}/>
          ));
        })}
      </>) : null}
      {(renderMode === 'all' || renderMode === 'curves') ? (<>
      {backToFront.map((assignment, index) => {
            const curve = resolveCurveAssignmentCatalogItem(curveCatalogItems, assignment);
            if (!curve)
                return null;
            const points = curveRenderPoints(curve, assignment, index, viewDepthRange, lattice.lattice, trackWidth, trackBodyHeightPx, managedSamplesByCurveId);
            const clipToTrack = assignment.clipToTrack ?? true;
            const strokePoints = clipToTrack
                ? curveRenderPointsUnclipped(
                    curve,
                    assignment,
                    index,
                    viewDepthRange,
                    lattice.lattice,
                    trackWidth,
                    trackBodyHeightPx,
                    managedSamplesByCurveId,
                )
                : curveRenderPoints(
                    curve,
                    { ...assignment, clipToTrack: true },
                    index,
                    viewDepthRange,
                    lattice.lattice,
                    trackWidth,
                    trackBodyHeightPx,
                    managedSamplesByCurveId,
                );
            const path = clipToTrack
                ? pathFromGeometricallyClippedCurvePoints(
                    strokePoints,
                    CURVE_VIEW_PADDING_X,
                    trackWidth - CURVE_VIEW_PADDING_X,
                )
                : pathFromCurvePoints(strokePoints);
            const pairedAssignment = assignment.pairedCurveId
                ? ordered.find((candidate) => (
                    candidate.assignmentId === assignment.pairedCurveId
                    || candidate.curveUid === assignment.pairedCurveId
                    || candidate.curveId === assignment.pairedCurveId
                ))
                : null;
            const pairedCurve = pairedAssignment
                ? resolveCurveAssignmentCatalogItem(curveCatalogItems, pairedAssignment)
                : null;
            const pairedPoints = pairedAssignment && pairedCurve
                ? curveRenderPoints(pairedCurve, pairedAssignment, index, viewDepthRange, lattice.lattice, trackWidth, trackBodyHeightPx, managedSamplesByCurveId)
                : [];
            const anchorX = fillAnchorForAssignment(assignment, trackWidth);
            const baseFillPath = assignment.fillSide === 'between' && pairedPoints.length > 0
                ? polygonBetweenCurves(points, pairedPoints)
                : polygonToAnchor(points, anchorX);
            const intervalInfillActive = assignment.infillSource === 'interval-column'
                && assignment.infillIntervalColumn === 'lithology'
                && assignment.fillSide !== 'none';
            const visibleLithologyIntervals = intervalInfillActive
                ? lithologyIntervals21_31.filter((interval) => interval.baseFt >= viewDepthRange.min && interval.topFt <= viewDepthRange.max)
                : [];
            return (<g key={assignment.assignmentId}>
            {assignment.fillSide !== 'none' && baseFillPath && !intervalInfillActive && !canonicalCurveFillActive ? (<path d={baseFillPath} fill={svgFillForAssignment(assignment, null, track.trackId)} stroke="none" opacity={fillOpacityForAssignment(assignment)}/>) : null}
            {intervalInfillActive && !canonicalCurveFillActive ? visibleLithologyIntervals.map((interval) => {
                    const clippedTop = Math.max(interval.topFt, viewDepthRange.min);
                    const clippedBase = Math.min(interval.baseFt, viewDepthRange.max);
                    const topY = depthToY(clippedTop, viewDepthRange, trackBodyHeightPx);
                    const baseY = depthToY(clippedBase, viewDepthRange, trackBodyHeightPx);
                    return (<g key={`${assignment.assignmentId}-${interval.intervalId}`} clipPath={`url(#interval-clip-${track.trackId}-${assignment.assignmentId}-${interval.intervalId})`}>
                  <defs>
                    <clipPath id={`interval-clip-${track.trackId}-${assignment.assignmentId}-${interval.intervalId}`}>
                      <rect x="0" y={topY} width={trackWidth} height={Math.max(1, baseY - topY)}/>
                    </clipPath>
                  </defs>
                  <path d={baseFillPath} fill={svgFillForAssignment(assignment, interval.color, track.trackId)} stroke="none" opacity={fillOpacityForAssignment(assignment)}/>
                </g>);
                }) : null}
            {(assignment.lineVisible ?? true) && path ? (<path d={path} fill="none" stroke={assignment.color} strokeWidth={assignment.lineWidth} strokeDasharray={assignment.lineStyle === 'dash' ? '8 5' : assignment.lineStyle === 'dot' ? '2 6' : undefined} vectorEffect="non-scaling-stroke" opacity={lineOpacityForAssignment(assignment)}/>) : null}
          </g>);
        })}
      </>) : null}
      {(renderMode === 'all' || renderMode === 'curves') && missingSampleMessages.length > 0 ? (<text x={trackWidth / 2} y={24} textAnchor="middle" className="wlv-curve-sample-error">
          Curve samples unavailable
        </text>) : null}
    </svg>);
}
export function CurveHeaderActionMenuPortal({ trackId, assignmentId, assignmentIndex, assignmentCount, onEditCurve, onReorderCurve, onCloseCurveMenu, onRemoveCurveFromTrack, }: {
    trackId: string;
    assignmentId: string;
    assignmentIndex: number;
    assignmentCount: number;
    onEditCurve: (trackId: string, assignmentId: string) => void;
    onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
    onCloseCurveMenu: () => void;
    onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
}) {
    const [menuPosition, setMenuPosition] = useState<{
        top: number;
        left: number;
        width: number;
    } | null>(null);
    useEffect(() => {
        const updatePosition = () => {
            const anchor = document.querySelector<HTMLElement>(`[data-curve-assignment-id="${assignmentId}"]`);
            if (!anchor) {
                setMenuPosition(null);
                return;
            }
            const rect = anchor.getBoundingClientRect();
            const width = 220;
            const gutter = 8;
            const top = Math.max(gutter, rect.bottom + 6);
            const left = Math.min(Math.max(gutter, rect.right - width), Math.max(gutter, window.innerWidth - width - gutter));
            setMenuPosition({ top, left, width });
        };
        updatePosition();
        window.addEventListener('resize', updatePosition);
        window.addEventListener('scroll', updatePosition, true);
        return () => {
            window.removeEventListener('resize', updatePosition);
            window.removeEventListener('scroll', updatePosition, true);
        };
    }, [assignmentId]);
    if (!menuPosition)
        return null;
    return createPortal(<div className="curve-header-action-menu curve-header-action-menu-portal" role="menu" style={{ top: menuPosition.top, left: menuPosition.left, width: menuPosition.width }} onMouseDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()}>
      <button type="button" onClick={() => {
            onReorderCurve(trackId, assignmentId, 0);
            onCloseCurveMenu();
        }}>
        Move to Front
      </button>
      <button type="button" disabled={assignmentIndex <= 0} onClick={() => {
            onReorderCurve(trackId, assignmentId, Math.max(0, assignmentIndex - 1));
            onCloseCurveMenu();
        }}>
        Move Up
      </button>
      <button type="button" disabled={assignmentIndex >= assignmentCount - 1} onClick={() => {
            onReorderCurve(trackId, assignmentId, Math.min(assignmentCount - 1, assignmentIndex + 1));
            onCloseCurveMenu();
        }}>
        Move Down
      </button>
      <button type="button" onClick={() => {
            onReorderCurve(trackId, assignmentId, assignmentCount - 1);
            onCloseCurveMenu();
        }}>
        Send to Back
      </button>
      <button type="button" onClick={() => {
            onEditCurve(trackId, assignmentId);
        }}>
        Edit Style / Range / Fill
      </button>
      <div className="curve-menu-divider"/>
      <button type="button" className="danger" onClick={() => {
            onRemoveCurveFromTrack(trackId, assignmentId);
            onCloseCurveMenu();
        }}>
        Remove from Track
      </button>
    </div>, document.body);
}
export function TrackContentOrderMenuPortal({ trackId, order, availableCategories, onChangeOrder, onClose }: {
    trackId: string;
    order: TrackContentCategory[];
    availableCategories: TrackContentCategory[];
    onChangeOrder: (trackId: string, order: TrackContentCategory[]) => void;
    onClose: () => void;
}) {
    const [selectedCategory, setSelectedCategory] = useState<TrackContentCategory | null>(availableCategories[0] ?? null);
    const [menuPosition, setMenuPosition] = useState<{ top: number; left: number; width: number } | null>(null);
    const visibleOrder = normalizedTrackContentOrder(order).filter((category) => availableCategories.includes(category));
    useEffect(() => {
        const updatePosition = () => {
            const anchor = document.querySelector<HTMLElement>(`[data-track-title-id="${trackId}"]`);
            if (!anchor) return setMenuPosition(null);
            const rect = anchor.getBoundingClientRect();
            const width = 260;
            const gutter = 8;
            setMenuPosition({ top: Math.max(gutter, rect.bottom + 6), left: Math.min(Math.max(gutter, rect.left), Math.max(gutter, window.innerWidth - width - gutter)), width });
        };
        updatePosition();
        window.addEventListener('resize', updatePosition);
        window.addEventListener('scroll', updatePosition, true);
        return () => { window.removeEventListener('resize', updatePosition); window.removeEventListener('scroll', updatePosition, true); };
    }, [trackId]);
    if (!menuPosition) return null;
    const commit = (nextVisible: TrackContentCategory[]) => {
        const hidden = normalizedTrackContentOrder(order).filter((category) => !availableCategories.includes(category));
        onChangeOrder(trackId, [...nextVisible, ...hidden]);
    };
    const moveSelected = (delta: -1 | 1) => {
        if (!selectedCategory) return;
        const current = [...visibleOrder];
        const index = current.indexOf(selectedCategory);
        const target = Math.max(0, Math.min(current.length - 1, index + delta));
        if (index < 0 || target === index) return;
        current.splice(index, 1);
        current.splice(target, 0, selectedCategory);
        commit(current);
    };
    const dropCategory = (target: TrackContentCategory, source: TrackContentCategory) => {
        if (target === source || !availableCategories.includes(source)) return;
        const current = [...visibleOrder];
        const sourceIndex = current.indexOf(source);
        const targetIndex = current.indexOf(target);
        if (sourceIndex < 0 || targetIndex < 0) return;
        current.splice(sourceIndex, 1);
        current.splice(targetIndex, 0, source);
        commit(current);
    };
    return createPortal(<div className="track-content-order-menu track-content-order-menu-portal" role="dialog" aria-label="Track content order" style={{ top: menuPosition.top, left: menuPosition.left, width: menuPosition.width }} onMouseDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()}>
      <div className="track-content-order-title">Track Content Order</div>
      <div className="track-content-order-note">Top item renders in front.</div>
      <div className="track-content-order-list">
        {visibleOrder.map((category) => (<button key={category} type="button" draggable className={selectedCategory === category ? 'selected' : ''} onClick={() => setSelectedCategory(category)} onDragStart={(event) => { event.dataTransfer.setData('text/plain', category); event.dataTransfer.effectAllowed = 'move'; }} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; }} onDrop={(event) => { event.preventDefault(); dropCategory(category, event.dataTransfer.getData('text/plain') as TrackContentCategory); }}>
          <span className="track-content-drag-handle" aria-hidden="true">⋮⋮</span><span>{trackContentCategoryLabel(category)}</span>
        </button>))}
      </div>
      <div className="track-content-order-actions"><button type="button" onClick={() => moveSelected(-1)}>↑</button><button type="button" onClick={() => moveSelected(1)}>↓</button><button type="button" className="close" onClick={onClose}>Close</button></div>
    </div>, document.body);
}


function validDepthRangeFromValues(values: number[], fallback: DepthViewRange): DepthViewRange {
    const finite = values.filter(Number.isFinite);
    if (finite.length < 2) return fallback;
    const min = Math.min(...finite);
    const max = Math.max(...finite);
    return max > min ? { min, max } : fallback;
}
function trackMagnificationLabel(
    canvasReferenceRange: DepthViewRange,
    currentRange: DepthViewRange,
    fallbackTrackRange: DepthViewRange,
): string {
    const referenceSpan = canvasReferenceRange.max - canvasReferenceRange.min;
    const referenceRange =
        Number.isFinite(referenceSpan) && referenceSpan > 0
            ? canvasReferenceRange
            : fallbackTrackRange;
    return standardizedMagnificationLabel(referenceRange, currentRange);
}

export function TrackView({ track, sharedHeaderHeightPx, magnificationLabel, selected, selectedAssignmentId, openCurveMenu, depthTicks, viewDepthRange, lithologyIntervals, transientCurveFillDraft, onSelectTrack, onSelectCurve, onEditCurve, onReorderCurve, onMoveCurveToTrack, onOpenCurveMenu, onCloseCurveMenu, onRemoveCurveFromTrack, onStartCurveTrackResize, resizingTrackId, trackBodyHeightPx, managedSamplesByCurveId, managedSampleErrorsByCurveId, curveCatalogItems, curveFillGeometryByRuleUid = new Map(), trackContentOrder = DEFAULT_TRACK_CONTENT_ORDER, topsFillLayer = null, formationTopsLayer = null, onOpenTrackContentMenu, }: {
    track: WellLogTrack;
    sharedHeaderHeightPx: number;
    magnificationLabel: string;
    selected: boolean;
    selectedAssignmentId: string | null;
    openCurveMenu: {
        trackId: string;
        assignmentId: string;
    } | null;
    depthTicks: number[];
    viewDepthRange: DepthViewRange;
    lithologyIntervals: LithologyIntervalRecord[];
    transientCurveFillDraft: TransientCurveFillDraft | null;
    onSelectTrack: (trackId: string, additive?: boolean) => void;
    onSelectCurve: (trackId: string, assignmentId: string) => void;
    onEditCurve: (trackId: string, assignmentId: string) => void;
    onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
    onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
    onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
    onCloseCurveMenu: () => void;
    onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
    onStartCurveTrackResize: (trackId: string, startX: number, startWidth: number) => void;
    resizingTrackId: string | null;
    trackBodyHeightPx: number;
    managedSamplesByCurveId: ManagedCurveSamplesByCurveId;
    managedSampleErrorsByCurveId: Record<string, string>;
    curveCatalogItems: CurveCatalogItem[];
    curveFillGeometryByRuleUid?: ReadonlyMap<string, CurveFillGeometryV2>;
    trackContentOrder?: TrackContentCategory[];
    topsFillLayer?: ReactNode;
    formationTopsLayer?: ReactNode;
    onOpenTrackContentMenu: (trackId: string) => void;
}) {
    const widthPx = track.trackType === 'curve' ? clampCurveTrackWidth(track.widthPx) : track.widthPx;
    const width = `${widthPx}px`;
    const isCurveTrack = track.trackType === 'curve';
    const lattice = isCurveTrack ? resolveTrackLattice(track, curveCatalogItems) : null;
    const trackViewDepthRange = viewDepthRange;
    const trackDepthTicks = depthTicks;
    const topsFillZIndex = trackContentZIndex(trackContentOrder, 'tops-fill');
    const curveFillZIndex = Math.max(trackContentZIndex(trackContentOrder, 'curve-fill'), topsFillZIndex + 1);
    const curvesZIndex = Math.max(trackContentZIndex(trackContentOrder, 'curves'), curveFillZIndex + 1);
    return (<section className={`wlv-track ${track.trackType} ${selected ? 'selected' : ''} ${resizingTrackId === track.trackId ? 'resizing' : ''}`} style={{ width, minWidth: width, height: `${sharedHeaderHeightPx + trackBodyHeightPx}px` }} onMouseDownCapture={(event) => {
            if (track.trackType !== 'curve' || !event.shiftKey || event.button !== 0)
                return;
            const target = event.target;
            if (!(target instanceof Element) || !target.closest('.wlv-track-body'))
                return;
            event.preventDefault();
            event.stopPropagation();
            onCloseCurveMenu();
            onSelectTrack(track.trackId);
            onStartCurveTrackResize(track.trackId, event.clientX, widthPx);
        }} onClick={(event) => {
            onCloseCurveMenu();
            onSelectTrack(track.trackId, event.metaKey);
        }} onDragOver={(event) => {
            if (track.trackType === 'curve')
                event.preventDefault();
        }} onDrop={(event) => {
            if (track.trackType !== 'curve')
                return;
            event.preventDefault();
            const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
            if (payload)
                onMoveCurveToTrack(payload, track.trackId);
        }}>
      <header
        className="wlv-track-header wlv-track-header-aligned"
        style={{ height: `${sharedHeaderHeightPx}px`, minHeight: `${sharedHeaderHeightPx}px`, flexBasis: `${sharedHeaderHeightPx}px` }}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onCloseCurveMenu();
          onSelectTrack(track.trackId, event.metaKey);
        }}
      >
        <div className="wlv-track-title-row" data-track-title-id={track.trackId} title="Double-click to arrange track content" onDoubleClick={(event) => { event.preventDefault(); event.stopPropagation(); onSelectTrack(track.trackId); onOpenTrackContentMenu(track.trackId); }}>
          <strong>{displayTitleForTrack(track, curveCatalogItems)}</strong>
          <TrackPlacementSelector track={track}/>
        </div>
        <div className="wlv-track-header-row-2">
          {track.trackType === 'curve' ? (
            <div className="wlv-track-well-owner" title={track.ownerWellName ?? 'Curve track'}>
              {track.ownerWellName ?? 'Curve track'}
            </div>
          ) : track.trackType === 'depth' ? (
            <div className="wlv-track-header-placeholder" aria-hidden="true" />
          ) : (
            <div className="wlv-lithology-header">{lithologySource.name}</div>
          )}
          <span className="wlv-track-magnification">{magnificationLabel}</span>
        </div>
        <div className="wlv-track-header-row-3">
          {track.trackType === 'curve' ? (
            <div className="wlv-lattice-badge">
              {lattice?.lattice} · {lattice?.source === 'user_override' ? 'override' : `front ${lattice?.frontCurve?.mnemonic ?? 'none'}`}
            </div>
          ) : track.trackType === 'depth' ? (
            <div className="wlv-depth-header-unit">{depthUnitLabel}</div>
          ) : (
            <div className="wlv-track-header-placeholder" aria-hidden="true" />
          )}
        </div>
        <div className="wlv-track-header-detail-rows">
          {track.trackType === 'curve' ? (
            <CurveHeaderStack track={track} curveCatalogItems={curveCatalogItems} selectedAssignmentId={selectedAssignmentId} openMenuAssignmentId={openCurveMenu?.trackId === track.trackId ? openCurveMenu?.assignmentId ?? null : null} onSelectCurve={onSelectCurve} onEditCurve={onEditCurve} onReorderCurve={onReorderCurve} onMoveCurveToTrack={onMoveCurveToTrack} onOpenCurveMenu={onOpenCurveMenu} onCloseCurveMenu={onCloseCurveMenu} onRemoveCurveFromTrack={onRemoveCurveFromTrack}/>
          ) : (
            <div className="wlv-track-header-detail-placeholder" aria-hidden="true" />
          )}
        </div>
      </header>
      <div className="wlv-track-body" style={{ height: `${trackBodyHeightPx}px`, minHeight: `${trackBodyHeightPx}px`, flexBasis: `${trackBodyHeightPx}px` }}>
        {track.trackType === 'depth' ? <DepthTrackView track={track} depthTicks={trackDepthTicks} viewDepthRange={trackViewDepthRange} trackBodyHeightPx={trackBodyHeightPx}/> : null}
        {track.trackType === 'lithology' ? <LithologyTrackView track={track} viewDepthRange={trackViewDepthRange} trackBodyHeightPx={trackBodyHeightPx}/> : null}
        {track.trackType === 'curve' ? (<>
          <div className="wlv-track-content-layer fixed-grid" style={{ zIndex: 1 }}><CurveTrackView track={track} depthTicks={trackDepthTicks} viewDepthRange={trackViewDepthRange} trackBodyHeightPx={trackBodyHeightPx} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={curveCatalogItems} lithologyIntervals={lithologyIntervals} transientCurveFillDraft={transientCurveFillDraft} curveFillGeometryByRuleUid={curveFillGeometryByRuleUid} renderMode="grid"/></div>
          <div className="wlv-track-content-layer tops-fill-layer" style={{ zIndex: topsFillZIndex }}>{topsFillLayer}</div>
          <div className="wlv-track-content-layer formation-tops-layer" style={{ zIndex: trackContentZIndex(trackContentOrder, 'formation-tops') }}>{formationTopsLayer}</div>
          <div className="wlv-track-content-layer curve-fill-layer" style={{ zIndex: curveFillZIndex }}><CurveTrackView track={track} depthTicks={trackDepthTicks} viewDepthRange={trackViewDepthRange} trackBodyHeightPx={trackBodyHeightPx} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={curveCatalogItems} lithologyIntervals={lithologyIntervals} transientCurveFillDraft={transientCurveFillDraft} curveFillGeometryByRuleUid={curveFillGeometryByRuleUid} renderMode="curve-fill"/></div>
          <div className="wlv-track-content-layer curves-layer" style={{ zIndex: curvesZIndex }}><CurveTrackView track={track} depthTicks={trackDepthTicks} viewDepthRange={trackViewDepthRange} trackBodyHeightPx={trackBodyHeightPx} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={curveCatalogItems} lithologyIntervals={lithologyIntervals} transientCurveFillDraft={transientCurveFillDraft} curveFillGeometryByRuleUid={curveFillGeometryByRuleUid} renderMode="curves"/></div>
        </>) : null}
      </div>
    </section>);
}

function resolveOverlayCurveAssignment(
    track: CurveTrack,
    identity: string | undefined,
): CurveAssignment | null {
    if (!identity)
        return null;
    return track.curves.find((assignment) => (
        assignment.assignmentId === identity
        || assignment.curveUid === identity
        || assignment.curveId === identity
    )) ?? null;
}

type LithologyRuntimeWindow = Window & {
    __WLV_API_BASE_URL__?: string;
};

function lithologyApiBase(): string {
    const runtime = window as LithologyRuntimeWindow;
    if (runtime.__WLV_API_BASE_URL__)
        return runtime.__WLV_API_BASE_URL__.replace(/\/$/, '');
    const protocol = window.location.protocol || 'http:';
    const hostname = window.location.hostname || '127.0.0.1';
    const port = window.location.port;
    if (port === '8001')
        return '';
    if (port === '5173' || port === '5174' || port === '5175')
        return `${protocol}//${hostname}:8001`;
    return 'http://127.0.0.1:8001';
}

function lithologyPatternUrl(
    lithologyId: string,
    background?: string,
    foreground?: string,
): string {
    const base = (
        `${lithologyApiBase()}/api/wlv/knowledge/lithology/entries/`
        + `${encodeURIComponent(lithologyId)}/pattern.svg`
    );
    const parameters = new URLSearchParams();
    if (background) parameters.set('background', background);
    if (foreground) parameters.set('foreground', foreground);
    const query = parameters.toString();
    return query ? `${base}?${query}` : base;
}

function formationTopFillPaint(
    zone: FormationTopFillZone,
    patternId: string,
): string {
    if (zone.source === 'pattern')
        return `url(#${patternId})`;
    if (zone.source === 'raster' && zone.rasterUrl)
        return `url(#${patternId}-raster)`;
    if (zone.source === 'lithology' && zone.lithologyId)
        return `url(#${patternId}-lithology)`;
    return zone.color;
}

function legacyFormationTopFillZone(
    style: FormationTopOverlayStyle,
): FormationTopFillZone[] {
    if (style.fillZones.length > 0)
        return style.fillZones;
    if (
        style.fillMode !== 'interval'
        || !style.fillTopMarkerId
        || !style.fillBaseMarkerId
    )
        return [];
    return [{
        zoneId: 'legacy-zone',
        enabled: true,
        depthExtent: 'top_boundaries',
        intervalFromMd: undefined,
        intervalToMd: undefined,
        topMarkerId: style.fillTopMarkerId,
        baseMarkerId: style.fillBaseMarkerId,
        source: style.fillSource,
        color: style.fillColor,
        opacity: style.fillOpacity,
        pattern: style.fillPattern,
        rasterUrl: style.fillRasterUrl,
        rasterFit: style.fillRasterFit,
        lithologyId: undefined,
        constraint: style.fillConstraint,
        honorTieInGeometry: false,
        curveAId: style.fillCurveAId,
        curveBId: style.fillCurveBId,
    }];
}


const CURVE_FILL_MD_PICK_REQUEST_EVENT =
    'wlv:curve-fill-md-pick-request';
const CURVE_FILL_MD_PICK_RESULT_EVENT =
    'wlv:curve-fill-md-pick-result';
const CURVE_FILL_MD_PICK_CANCEL_EVENT =
    'wlv:curve-fill-md-pick-cancel';

type CurveFillMdPickCanvasState = {
    token: string;
    field: 'from' | 'to';
    allowedTrackId?: string;
};


function rgbaFromHex(hex: string, opacityPercent: number): string {
  const normalized = hex.replace('#', '').trim();
  const expanded = normalized.length === 3
    ? normalized.split('').map((value) => `${value}${value}`).join('')
    : normalized;
  const numeric = Number.parseInt(expanded, 16);
  if (!Number.isFinite(numeric) || expanded.length !== 6) return `rgba(215,220,226,${Math.max(0, Math.min(100, opacityPercent)) / 100})`;
  const red = (numeric >> 16) & 255;
  const green = (numeric >> 8) & 255;
  const blue = numeric & 255;
  return `rgba(${red},${green},${blue},${Math.max(0, Math.min(100, opacityPercent)) / 100})`;
}

function mixHex(hex: string, targetHex: string, weight: number): string {
  const normalize = (value: string): [number, number, number] => {
    const normalized = value.replace('#', '').trim();
    const expanded = normalized.length === 3
      ? normalized.split('').map((item) => `${item}${item}`).join('')
      : normalized;
    const numeric = Number.parseInt(expanded, 16);
    if (!Number.isFinite(numeric) || expanded.length !== 6) return [215, 220, 226];
    return [(numeric >> 16) & 255, (numeric >> 8) & 255, numeric & 255];
  };
  const [r1, g1, b1] = normalize(hex);
  const [r2, g2, b2] = normalize(targetHex);
  const factor = Math.max(0, Math.min(1, weight));
  const mix = (left: number, right: number) => Math.round(left + (right - left) * factor);
  return `rgb(${mix(r1, r2)}, ${mix(g1, g2)}, ${mix(b1, b2)})`;
}

function resolveCoreTrackAppearance(track: WellLogTrack): CoreTrackAppearance {
  if (track.trackType !== 'core') return DEFAULT_CORE_TRACK_APPEARANCE;
  return {
    ...DEFAULT_CORE_TRACK_APPEARANCE,
    ...(track.coreAppearance ?? {}),
  };
}

function corePlacementBackground(appearance: CoreTrackAppearance): string {
  const brightness = clampValue(appearance.brightness ?? 1, 0.55, 1.45);
  const shadingStrength = clampValue(appearance.shadingStrength ?? 0.38, 0, 1);
  const base = appearance.baseColor || DEFAULT_CORE_TRACK_APPEARANCE.baseColor;
  const brightMix = mixHex(base, '#ffffff', Math.min(0.42, 0.14 + (brightness - 1) * 0.55 + shadingStrength * 0.18));
  const softMid = mixHex(base, '#ffffff', Math.min(0.28, 0.08 + (brightness - 1) * 0.45));
  const edge = mixHex(base, '#0f1216', Math.min(0.34, shadingStrength * 0.36 + Math.max(0, 1 - brightness) * 0.22));
  if (appearance.shadingMode === 'cylindrical') {
    return `linear-gradient(90deg, ${edge} 0%, ${softMid} 18%, ${brightMix} 50%, ${softMid} 82%, ${edge} 100%)`;
  }
  return mixHex(base, '#ffffff', Math.max(0, (brightness - 1) * 0.35));
}

function resolveCoreOverlayLaneMetrics(track: WellLogTrack, overlayStyle: FormationTopOverlayStyle, trackWidth: number) {
  if (track.trackType !== 'core') {
    return { left: 0, width: trackWidth, right: 0 };
  }
  const leftInsetPct = clampValue(overlayStyle.trackLeftInsetPct ?? 0, 0, 80);
  const rightInsetPct = clampValue(overlayStyle.trackRightInsetPct ?? 0, 0, 80);
  const maxCombined = 88;
  const combined = leftInsetPct + rightInsetPct;
  const scale = combined > maxCombined ? maxCombined / combined : 1;
  const left = (trackWidth * leftInsetPct * scale) / 100;
  const right = (trackWidth * rightInsetPct * scale) / 100;
  const width = Math.max(18, trackWidth - left - right);
  return { left, width, right };
}

function resolveCoreObjectLaneMetrics(
  trackWidth: number,
  trackViewDepthRange: DepthViewRange,
  trackBodyHeightPx: number,
) {
  const span = Math.max(1e-9, trackViewDepthRange.max - trackViewDepthRange.min);
  const pixelsPerMd = Math.max(0, trackBodyHeightPx / span);
  const detailProgress = clampValue(
    (pixelsPerMd - 15) / (CORE_PHOTO_THRESHOLD_PIXELS_PER_MD - 15),
    0,
    1,
  );
  // Matches the Core presence renderer: macro object 40% wide, expanding
  // progressively toward the photographic threshold.
  const insetPct = 30 - detailProgress * 18;
  const left = (trackWidth * insetPct) / 100;
  const right = left;
  return { left, right, width: Math.max(18, trackWidth - left - right) };
}

function loadConfiguredFormationColumn(): IntervalBuilderColumn {
  try {
    const raw = window.localStorage.getItem(INTERVAL_BUILDER_STORAGE_KEY);
    if (raw) {
      const configured = JSON.parse(raw) as IntervalBuilderColumn[];
      const formation = configured.find((column) => column.key === 'formation');
      if (formation) return formation;
    }
  } catch { /* use defaults */ }
  return INTERVAL_BUILDER_DEFAULTS.find((column) => column.key === 'formation') ?? {
    key: 'formation',
    label: 'Formation Tops',
    enabled: true,
    width: 120,
    title: 'Formation',
  };
}


function IntervalCoreDescriptionTrack({
  track,
  coreImageItems,
  activeWellName,
  viewDepthRange,
  bodyHeight,
  sharedHeaderHeight,
  magnificationLabel,
  selected,
  onSelect,
}: {
  track: WellLogTrack;
  coreImageItems: CoreImageInventoryItem[];
  activeWellName: string;
  viewDepthRange: DepthViewRange;
  bodyHeight: number;
  sharedHeaderHeight: number;
  magnificationLabel: string;
  selected: boolean;
  onSelect: (trackId: string, additive?: boolean) => void;
}) {
  const [config, setConfig] =
    useState<IntervalDescriptionConfig>(
      () => loadIntervalDescriptionConfig(),
    );

  const [column, setColumn] =
    useState<IntervalBuilderColumn>(
      () => loadConfiguredDescriptionColumn(),
    );

  useEffect(() => {
    const refresh = () => {
      setConfig(loadIntervalDescriptionConfig());
      setColumn(loadConfiguredDescriptionColumn());
    };

    const preview = (event: Event) => {
      const detail = (
        event as CustomEvent<IntervalDescriptionPreviewDetail>
      ).detail;
      if (!detail?.config || detail.column?.key !== 'descriptions') return;
      setConfig({
        ...INTERVAL_DESCRIPTION_DEFAULTS,
        ...detail.config,
        descriptionType: 'core_description',
      });
      setColumn({ ...detail.column });
    };

    window.addEventListener('storage', refresh);
    window.addEventListener('focus', refresh);
    window.addEventListener(
      'wlv:interval-description-config-changed',
      refresh,
    );
    window.addEventListener(
      INTERVAL_DESCRIPTION_PREVIEW_EVENT,
      preview,
    );
    window.addEventListener(
      INTERVAL_DESCRIPTION_PREVIEW_END_EVENT,
      refresh,
    );

    return () => {
      window.removeEventListener('storage', refresh);
      window.removeEventListener('focus', refresh);
      window.removeEventListener(
        'wlv:interval-description-config-changed',
        refresh,
      );
      window.removeEventListener(
        INTERVAL_DESCRIPTION_PREVIEW_EVENT,
        preview,
      );
      window.removeEventListener(
        INTERVAL_DESCRIPTION_PREVIEW_END_EVENT,
        refresh,
      );
    };
  }, []);

  const core =
    coreImageItems.find(
      item => item.productId === config.coreProductId,
    )
    ?? coreImageItems.find(
      item => (item.descriptions?.length ?? 0) > 0,
    )
    ?? null;

  const allDescriptions = [...(core?.descriptions ?? [])]
    .filter(
      item =>
        Number.isFinite(item.md)
        && item.text.trim().length > 0,
    )
    .sort(
      (left, right) =>
        left.md - right.md
        || left.descriptionId.localeCompare(
          right.descriptionId,
        ),
    );

  const visible = allDescriptions
    .filter(
      item =>
        item.md >= viewDepthRange.min
        && item.md <= viewDepthRange.max,
    )
    .map(item => ({
      ...item,
      y: depthToY(
        item.md,
        viewDepthRange,
        bodyHeight,
      ),
    }));

  /*
   * Point-description display density.
   * This hides labels only; it never changes their MD.
   */
  const labelFontSize = Math.max(
    config.showMd ? config.depthFontSize : 0,
    config.showText ? config.fontSize : 0,
  );

  /*
   * Core Description collision safety.
   * Every record keeps its exact MD marker line. Text is progressively
   * disclosed in screen space and is never permitted to overlap.
   */
  const collisionFloor = Math.max(
    12,
    labelFontSize * 1.35,
  );

  const minimumSpacing =
    config.density === 'sparse'
      ? Math.max(28, labelFontSize * 2.2)
      : config.density === 'all'
        ? collisionFloor
        : Math.max(14, labelFontSize * 1.35);

  let lastAcceptedY = Number.NEGATIVE_INFINITY;

  const displayed = visible.filter(item => {
    if (minimumSpacing <= 0) return true;

    if (item.y - lastAcceptedY < minimumSpacing) {
      return false;
    }

    lastAcceptedY = item.y;
    return true;
  });

  const width = Math.max(
    1,
    column.width || track.widthPx || 260,
  );

  const lineColor = rgbaFromHex(
    config.markerColor,
    config.markerOpacity,
  );

  const relationOffset = (
    relation: 'above' | 'on' | 'below',
  ): number => (
    relation === 'above'
      ? -12
      : relation === 'below'
        ? 12
        : 0
  );

  const stacked =
    config.depthDescriptionOrder === 'depth_above'
    || config.depthDescriptionOrder === 'description_above';

  const descriptionFirst =
    config.depthDescriptionOrder === 'description_before'
    || config.depthDescriptionOrder === 'description_above';

  const depthStyle: React.CSSProperties = {
    color: rgbaFromHex(
      config.depthFontColor,
      config.depthOpacity,
    ),
    fontSize: `${config.depthFontSize}px`,
    fontWeight:
      config.depthFontWeight === 'bold' ? 700 : 400,
    transform: `translate(${config.depthHorizontalOffset}px, ${
      relationOffset(config.depthRelativeToLine)
      + config.depthVerticalOffset
    }px)`,
  };

  const descriptionStyle: React.CSSProperties = {
    color: rgbaFromHex(
      config.fontColor,
      config.descriptionOpacity,
    ),
    fontSize: `${config.fontSize}px`,
    fontWeight:
      config.fontWeight === 'bold' ? 700 : 400,
    textAlign: config.textAlignment,
    whiteSpace: config.wrapText ? 'normal' : 'nowrap',
    transform: `translate(${config.descriptionHorizontalOffset}px, ${
      relationOffset(config.descriptionRelativeToLine)
      + config.descriptionVerticalOffset
    }px)`,
  };

  return (
    <section
      className={
        `wlv-track wlv-interval-core-description-track${
          selected ? ' selected' : ''
        }`
      }
      style={{
        width: `${width}px`,
        minWidth: `${width}px`,
        flexBasis: `${width}px`,
      }}
      onMouseDown={(event) => {
        if (event.button !== 0) return;
        const target = event.target;
        if (target instanceof Element && target.closest('.wlv-track-header')) {
          event.preventDefault();
          event.stopPropagation();
          onSelect(track.trackId, event.metaKey);
          return;
        }
        onSelect(track.trackId, event.metaKey);
      }}
    >
      <header
        className="wlv-track-header wlv-track-header-aligned"
        style={{
          height: `${sharedHeaderHeight}px`,
          minHeight: `${sharedHeaderHeight}px`,
          flexBasis: `${sharedHeaderHeight}px`,
        }}
      >
        <div className="wlv-track-title-row">
          <strong>
            {column.title || 'Core Description'}
          </strong>
          <TrackPlacementSelector track={track}/>
        </div>

        <div className="wlv-track-header-row-2">
          <div className="wlv-depth-header">
            {track.ownerWellName || activeWellName || 'Well not resolved'}
          </div>
          <span className="wlv-track-magnification">{magnificationLabel}</span>
        </div>

        <div className="wlv-track-header-row-3">
          <div className="wlv-lattice-badge">
            {core
              ? `Core Description · ${allDescriptions.length}`
              : 'Core Description'}
          </div>
        </div>

        <div className="wlv-track-header-detail-rows">
          <div
            className="wlv-track-header-detail-placeholder"
            aria-hidden="true"
          />
        </div>
      </header>

      <div
        className="wlv-track-body wlv-interval-core-description-body"
        style={{
          height: `${bodyHeight}px`,
          minHeight: `${bodyHeight}px`,
          flexBasis: `${bodyHeight}px`,
        }}
      >
        {displayed.map(item => {
          const depthLabel = config.showMd ? (
            <span
              className="wlv-core-description-depth"
              style={depthStyle}
            >
              {item.md.toLocaleString(
                undefined,
                { maximumFractionDigits: 3 },
              )} m MD
            </span>
          ) : null;

          const descriptionLabel = config.showText ? (
            <span
              className={
                `wlv-core-description-text ${
                  config.wrapText
                    ? 'is-wrapped'
                    : 'is-single-line'
                }`
              }
              style={descriptionStyle}
            >
              {item.text}
            </span>
          ) : null;

          return (
            <div
              key={item.descriptionId}
              className="wlv-core-description-marker"
              style={{ top: item.y }}
              title={`${item.md.toLocaleString(
                undefined,
                { maximumFractionDigits: 3 },
              )} m MD · ${item.text}`}
            >
              {config.showMarkerLine ? (
                <i
                  style={{
                    borderTopColor: lineColor,
                    borderTopWidth: `${config.markerWidth}px`,
                    borderTopStyle: config.markerStyle,
                  }}
                />
              ) : null}

              {(depthLabel || descriptionLabel) ? (
                <div
                  className={
                    `wlv-core-description-labels${
                      stacked ? ' is-stacked' : ''
                    }`
                  }
                  style={{
                    flexDirection: stacked ? 'column' : 'row',
                    alignItems:
                      config.textAlignment === 'right'
                        ? 'flex-end'
                        : config.textAlignment === 'center'
                          ? 'center'
                          : 'flex-start',
                    justifyContent:
                      config.textAlignment === 'right'
                        ? 'flex-end'
                        : config.textAlignment === 'center'
                          ? 'center'
                          : 'flex-start',
                  }}
                >
                  {descriptionFirst ? (
                    <>
                      {descriptionLabel}
                      {depthLabel}
                    </>
                  ) : (
                    <>
                      {depthLabel}
                      {descriptionLabel}
                    </>
                  )}
                </div>
              ) : null}
            </div>
          );
        })}

        {!core ? (
          <div className="wlv-interval-formation-empty">
            No Core Description source selected.
          </div>
        ) : allDescriptions.length === 0 ? (
          <div className="wlv-interval-formation-empty">
            This Core product has no descriptions.
          </div>
        ) : visible.length === 0 ? (
          <div className="wlv-interval-formation-empty">
            No Core Descriptions in the current depth view.
          </div>
        ) : null}
      </div>
    </section>
  );
}



const COMPLETION_INTERVAL_CANONICAL_IDS = new Set<CompletionCanonicalId>([
  'completion.tubing',
  'completion.casing',
  'completion.liner',
  'completion.screen',
  'completion.open_hole',
  'completion.perforations',
]);

function completionUsesIntervalGeometry(item: CompletionComponentRecord): boolean {
  if (COMPLETION_INTERVAL_CANONICAL_IDS.has(item.canonicalId)) return true;
  return item.canonicalId === 'completion.cement_barrier'
    && item.baseMd !== null
    && item.baseMd > item.topMd;
}

type Completion3DGeometryFamily =
  | 'tubular'
  | 'screen_interval'
  | 'open_hole_interval'
  | 'perforation_cluster'
  | 'toolbody_inline'
  | 'toolbody_annular'
  | 'valve_body'
  | 'mandrel_body'
  | 'annular_barrier';

type Completion3DMaterialFamily =
  | 'metal_polished'
  | 'metal_brushed'
  | 'metal_dark_tool'
  | 'metal_mesh'
  | 'cement_matte'
  | 'formation_matte'
  | 'perforation_cut';

type Completion3DAnnotationPolicy =
  | 'aligned_conditional_leader'
  | 'interval_aligned_conditional_leader';

type Completion3DRenderRecipe = {
  geometryFamily: Completion3DGeometryFamily;
  materialFamily: Completion3DMaterialFamily;
  annotationPolicy: Completion3DAnnotationPolicy;
  // Compiled projection of the governed KR WDV Completion Glyph Standard.
  wdvGlyph?: string;
  wdvGlyphVersion?: '1.0';
  labelIndependentIdentity?: 'required';
  wdvGlyphStatus?: 'visually_reviewed' | 'baseline_locked';
};

// WDV_COMPLETION_3D_RENDER_STANDARD_V1
// Compiled projection of the KR completion render contract.
// All 15 normal canonical completion families carry a versioned `wdvGlyph`.
// `visually_reviewed` marks the nine glyphs explicitly reviewed and accepted;
// `baseline_locked` preserves the six existing glyphs as the V1 reference pending
// future visual review. `completion.other` remains a fallback outside the 15-family
// WDV Completion Glyph Standard.
// Future glyph changes must update the KR and this compiled projection together.
const COMPLETION_3D_RENDER_RECIPES: Record<CompletionCanonicalId, Completion3DRenderRecipe> = {
  'completion.tubing': {geometryFamily: 'tubular', materialFamily: 'metal_polished', annotationPolicy: 'interval_aligned_conditional_leader', wdvGlyph: 'wdv.completion.tubing.distinct_interval.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.casing': {geometryFamily: 'tubular', materialFamily: 'metal_brushed', annotationPolicy: 'interval_aligned_conditional_leader', wdvGlyph: 'wdv.completion.casing.brushed_tubular_interval.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'baseline_locked'},
  'completion.liner': {geometryFamily: 'tubular', materialFamily: 'metal_brushed', annotationPolicy: 'interval_aligned_conditional_leader', wdvGlyph: 'wdv.completion.liner.brushed_tubular_interval.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'baseline_locked'},
  'completion.screen': {geometryFamily: 'screen_interval', materialFamily: 'metal_mesh', annotationPolicy: 'interval_aligned_conditional_leader', wdvGlyph: 'wdv.completion.screen.ribbed_interval.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.open_hole': {geometryFamily: 'open_hole_interval', materialFamily: 'formation_matte', annotationPolicy: 'interval_aligned_conditional_leader', wdvGlyph: 'wdv.completion.open_hole.formation_interval.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'baseline_locked'},
  'completion.perforations': {geometryFamily: 'perforation_cluster', materialFamily: 'perforation_cut', annotationPolicy: 'interval_aligned_conditional_leader', wdvGlyph: 'wdv.completion.perforations.cluster_interval.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'baseline_locked'},
  'completion.packer': {geometryFamily: 'toolbody_annular', materialFamily: 'metal_dark_tool', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.packer.annular_isolation.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.safety_valve': {geometryFamily: 'valve_body', materialFamily: 'metal_brushed', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.safety_valve.symmetric_inline.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.downhole_valve': {geometryFamily: 'valve_body', materialFamily: 'metal_brushed', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.downhole_valve.faceted_inline.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.sliding_sleeve': {geometryFamily: 'valve_body', materialFamily: 'metal_brushed', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.sliding_sleeve.ported_body.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.gas_lift': {geometryFamily: 'mandrel_body', materialFamily: 'metal_brushed', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.gas_lift.sidecar_mandrel.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.icd_aicd': {geometryFamily: 'toolbody_inline', materialFamily: 'metal_dark_tool', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.icd_aicd.radial_nozzle.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.bridge_plug': {geometryFamily: 'toolbody_annular', materialFamily: 'metal_dark_tool', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.bridge_plug.opposed_cone.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'visually_reviewed'},
  'completion.retainer': {geometryFamily: 'toolbody_annular', materialFamily: 'metal_dark_tool', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.retainer.annular_toolbody.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'baseline_locked'},
  'completion.cement_barrier': {geometryFamily: 'annular_barrier', materialFamily: 'cement_matte', annotationPolicy: 'aligned_conditional_leader', wdvGlyph: 'wdv.completion.cement_barrier.annular_barrier.v1', wdvGlyphVersion: '1.0', labelIndependentIdentity: 'required', wdvGlyphStatus: 'baseline_locked'},
};

function completion3DRenderRecipe(item: CompletionComponentRecord): Completion3DRenderRecipe {
  return COMPLETION_3D_RENDER_RECIPES[item.canonicalId];
}

function completionUses3DRender(item: CompletionComponentRecord): boolean {
  return Boolean(COMPLETION_3D_RENDER_RECIPES[item.canonicalId]);
}

function CompletionOrthographic3DLayer({
  width,
  bodyHeight,
  axisX,
  contextWidth,
  tubingWidth,
  components,
  viewDepthRange,
  boreBaseMd,
  onReady,
}: {
  width: number;
  bodyHeight: number;
  axisX: number;
  contextWidth: number;
  tubingWidth: number;
  components: CompletionComponentRecord[];
  viewDepthRange: DepthViewRange;
  boreBaseMd?: number | null;
  onReady: (ready: boolean) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || width <= 0 || bodyHeight <= 0) return undefined;

    let renderer: THREE.WebGLRenderer | null = null;
    let disposed = false;
    const geometries: THREE.BufferGeometry[] = [];
    const materials: THREE.Material[] = [];
    const scene = new THREE.Scene();

    const rememberGeometry = <T extends THREE.BufferGeometry>(geometry: T): T => {
      geometries.push(geometry);
      return geometry;
    };
    const rememberMaterial = <T extends THREE.Material>(material: T): T => {
      materials.push(material);
      return material;
    };
    const pixelYToWorld = (pixelY: number) => bodyHeight * 0.5 - pixelY;
    const depthToWorldY = (md: number) => pixelYToWorld(depthToY(md, viewDepthRange, bodyHeight));
    const sceneX = axisX - width * 0.5;
    const addCylinder = ({
      radius,
      height,
      y,
      material,
      segments = 24,
      renderOrder = 1,
    }: {
      radius: number;
      height: number;
      y: number;
      material: THREE.Material;
      segments?: number;
      renderOrder?: number;
    }) => {
      const geometry = rememberGeometry(new THREE.CylinderGeometry(radius, radius, Math.max(.8, height), segments, 1, false));
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(sceneX, y, 0);
      mesh.renderOrder = renderOrder;
      scene.add(mesh);
      return mesh;
    };

    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      });
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, bodyHeight, false);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;

      const camera = new THREE.OrthographicCamera(
        -width * .5,
        width * .5,
        bodyHeight * .5,
        -bodyHeight * .5,
        .1,
        200,
      );
      camera.position.set(0, 0, 75);
      camera.lookAt(0, 0, 0);
      camera.updateProjectionMatrix();

      scene.add(new THREE.HemisphereLight(0xf4f8fb, 0x27343d, 1.35));
      const keyLight = new THREE.DirectionalLight(0xffffff, 3.25);
      keyLight.position.set(-50, 35, 65);
      keyLight.castShadow = true;
      scene.add(keyLight);
      const rimLight = new THREE.DirectionalLight(0xa9d5f2, 1.8);
      rimLight.position.set(55, -10, 45);
      scene.add(rimLight);
      const warmFill = new THREE.DirectionalLight(0xffd5a5, .85);
      warmFill.position.set(-35, -35, 30);
      scene.add(warmFill);

      const casingMaterial = rememberMaterial(new THREE.MeshStandardMaterial({
        color: 0xbfc8cd,
        metalness: .9,
        roughness: .28,
        transparent: true,
        opacity: .42,
      }));
      const tubingMaterial = rememberMaterial(new THREE.MeshPhysicalMaterial({
        color: 0xd8e1e5,
        metalness: 1,
        roughness: .16,
        clearcoat: .42,
        clearcoatRoughness: .2,
      }));
      const bronzeMaterial = rememberMaterial(new THREE.MeshPhysicalMaterial({
        color: 0x9b6b32,
        metalness: .88,
        roughness: .23,
        clearcoat: .3,
        clearcoatRoughness: .25,
      }));
      const darkMetalMaterial = rememberMaterial(new THREE.MeshStandardMaterial({
        color: 0x4b3a2d,
        metalness: .76,
        roughness: .34,
      }));
      const perfMaterial = rememberMaterial(new THREE.MeshStandardMaterial({
        color: 0x9a4f21,
        metalness: .42,
        roughness: .42,
      }));
      const cementMaterial = rememberMaterial(new THREE.MeshPhysicalMaterial({
        color: 0xbdb3a4,
        metalness: 0,
        roughness: .96,
        clearcoat: 0,
        transparent: true,
        opacity: .42,
        depthWrite: false,
        side: THREE.DoubleSide,
      }));
      const cementEdgeMaterial = rememberMaterial(new THREE.MeshStandardMaterial({
        color: 0x8f877c,
        metalness: 0,
        roughness: 1,
        transparent: true,
        opacity: .20,
        depthWrite: false,
        side: THREE.DoubleSide,
      }));
      const brushedMetalMaterial = rememberMaterial(new THREE.MeshPhysicalMaterial({
        color: 0xaab5bb,
        metalness: .92,
        roughness: .28,
        clearcoat: .2,
        clearcoatRoughness: .32,
      }));
      const meshMetalMaterial = rememberMaterial(new THREE.MeshStandardMaterial({
        color: 0x89979e,
        metalness: .82,
        roughness: .38,
        wireframe: true,
        transparent: true,
        opacity: .88,
      }));
      const completionTubingMaterial = rememberMaterial(new THREE.MeshPhysicalMaterial({
        color: 0x71818a,
        metalness: .96,
        roughness: .24,
        clearcoat: .36,
        clearcoatRoughness: .26,
      }));
      const screenRibMaterial = rememberMaterial(new THREE.MeshStandardMaterial({
        color: 0x354851,
        metalness: .72,
        roughness: .46,
      }));
      const formationMaterial = rememberMaterial(new THREE.MeshStandardMaterial({
        color: 0x8f8474,
        metalness: 0,
        roughness: 1,
        transparent: true,
        opacity: .22,
        depthWrite: false,
        side: THREE.BackSide,
      }));

      // Permanent WDV schematic context is bounded by the owning well's
      // authoritative depth record. The viewport is presentation only and must
      // never manufacture extra bore below host-well TD.
      const resolvedBoreBaseMd = Number.isFinite(boreBaseMd)
        ? Math.min(viewDepthRange.max, Math.max(viewDepthRange.min, Number(boreBaseMd)))
        : viewDepthRange.max;
      const boreVisible = boreBaseMd == null || boreBaseMd > viewDepthRange.min;
      if (boreVisible) {
        const boreTopY = depthToWorldY(viewDepthRange.min);
        const boreBaseY = depthToWorldY(resolvedBoreBaseMd);
        const boreHeight = Math.max(.8, Math.abs(boreTopY - boreBaseY));
        const boreCenterY = (boreTopY + boreBaseY) * .5;
        addCylinder({
          radius: Math.max(5, contextWidth * .5),
          height: boreHeight,
          y: boreCenterY,
          material: casingMaterial,
          renderOrder: 1,
        });
        addCylinder({
          radius: Math.max(2.1, tubingWidth * .54),
          height: boreHeight,
          y: boreCenterY,
          material: tubingMaterial,
          renderOrder: 4,
        });
      }

      for (const item of components) {
        if (!completionUses3DRender(item)) continue;
        const baseMd = item.baseMd ?? item.topMd;
        if (baseMd < viewDepthRange.min || item.topMd > viewDepthRange.max) continue;
        const anchorMd = item.baseMd !== null && item.baseMd > item.topMd
          ? (item.topMd + item.baseMd) * .5
          : item.topMd;
        const anchorY = depthToWorldY(anchorMd);

        if (item.canonicalId === 'completion.tubing') {
          if (item.baseMd === null || item.baseMd <= item.topMd) continue;
          const topY = depthToWorldY(Math.max(item.topMd, viewDepthRange.min));
          const baseY = depthToWorldY(Math.min(item.baseMd, viewDepthRange.max));
          const tubingRadius = Math.max(3.2, tubingWidth * .78);
          addCylinder({
            radius: tubingRadius,
            height: Math.abs(topY - baseY),
            y: (topY + baseY) * .5,
            material: completionTubingMaterial,
            renderOrder: 5,
          });
          [topY, baseY].forEach((boundaryY) => addCylinder({
            radius: tubingRadius * 1.12,
            height: 2,
            y: boundaryY,
            material: darkMetalMaterial,
            segments: 28,
            renderOrder: 6,
          }));
          continue;
        }

        const recipe = completion3DRenderRecipe(item);

        if (item.canonicalId === 'completion.casing' || item.canonicalId === 'completion.liner') {
          if (item.baseMd === null || item.baseMd <= item.topMd) continue;
          const topY = depthToWorldY(Math.max(item.topMd, viewDepthRange.min));
          const baseY = depthToWorldY(Math.min(item.baseMd, viewDepthRange.max));
          const radius = item.canonicalId === 'completion.casing'
            ? Math.max(5.2, contextWidth * .52)
            : Math.max(4.2, contextWidth * .43);
          addCylinder({
            radius,
            height: Math.abs(topY - baseY),
            y: (topY + baseY) * .5,
            material: brushedMetalMaterial,
            segments: 30,
            renderOrder: item.canonicalId === 'completion.casing' ? 2 : 3,
          });
          continue;
        }

        if (recipe.geometryFamily === 'screen_interval') {
          if (item.baseMd === null || item.baseMd <= item.topMd) continue;
          const topY = depthToWorldY(Math.max(item.topMd, viewDepthRange.min));
          const baseY = depthToWorldY(Math.min(item.baseMd, viewDepthRange.max));
          const screenHeight = Math.abs(topY - baseY);
          const screenRadius = Math.max(4.5, tubingWidth * .88);
          addCylinder({
            radius: screenRadius,
            height: screenHeight,
            y: (topY + baseY) * .5,
            material: brushedMetalMaterial,
            segments: 30,
            renderOrder: 6,
          });
          addCylinder({
            radius: screenRadius * 1.035,
            height: screenHeight,
            y: (topY + baseY) * .5,
            material: meshMetalMaterial,
            segments: 30,
            renderOrder: 7,
          });
          const screenRibCount = Math.max(4, Math.min(28, Math.floor(screenHeight / 6)));
          for (let ribIndex = 0; ribIndex < screenRibCount; ribIndex += 1) {
            const ratio = screenRibCount <= 1 ? .5 : ribIndex / (screenRibCount - 1);
            addCylinder({
              radius: screenRadius * 1.1,
              height: 1.15,
              y: THREE.MathUtils.lerp(topY, baseY, ratio),
              material: screenRibMaterial,
              segments: 30,
              renderOrder: 8,
            });
          }
          continue;
        }

        if (recipe.geometryFamily === 'open_hole_interval') {
          if (item.baseMd === null || item.baseMd <= item.topMd) continue;
          const topY = depthToWorldY(Math.max(item.topMd, viewDepthRange.min));
          const baseY = depthToWorldY(Math.min(item.baseMd, viewDepthRange.max));
          addCylinder({
            radius: Math.max(11, contextWidth * .78),
            height: Math.abs(topY - baseY),
            y: (topY + baseY) * .5,
            material: formationMaterial,
            segments: 20,
            renderOrder: 0,
          });
          continue;
        }

        if (item.canonicalId === 'completion.packer') {
          const toolHeight = Math.max(16, 22 * (tubingWidth / 6));
          addCylinder({ radius: Math.max(6.8, contextWidth * .34), height: toolHeight * .55, y: anchorY, material: darkMetalMaterial, segments: 30, renderOrder: 9 });
          [-1, 1].forEach((direction) => {
            const geometry = rememberGeometry(new THREE.TorusGeometry(Math.max(6.2, contextWidth * .31), Math.max(1.3, contextWidth * .065), 10, 30));
            const seal = new THREE.Mesh(geometry, bronzeMaterial);
            seal.position.set(sceneX, anchorY + direction * toolHeight * .27, 0);
            seal.rotation.x = Math.PI * .5;
            seal.renderOrder = 10;
            scene.add(seal);
          });
          continue;
        }

        if (item.canonicalId === 'completion.bridge_plug') {
          const toolHeight = Math.max(18, 24 * (tubingWidth / 6));
          const bodyRadius = Math.max(6.8, contextWidth * .34);
          addCylinder({
            radius: bodyRadius,
            height: toolHeight * .5,
            y: anchorY,
            material: bronzeMaterial,
            segments: 30,
            renderOrder: 9,
          });
          addCylinder({
            radius: bodyRadius * .72,
            height: toolHeight * .22,
            y: anchorY,
            material: darkMetalMaterial,
            segments: 24,
            renderOrder: 10,
          });
          [-1, 1].forEach((direction) => {
            const geometry = rememberGeometry(new THREE.ConeGeometry(
              bodyRadius * 1.18,
              toolHeight * .28,
              28,
              1,
              false,
            ));
            const cone = new THREE.Mesh(geometry, darkMetalMaterial);
            cone.position.set(sceneX, anchorY + direction * toolHeight * .38, 0);
            if (direction < 0) cone.rotation.z = Math.PI;
            cone.renderOrder = 11;
            scene.add(cone);
            addCylinder({
              radius: bodyRadius * 1.22,
              height: 1.9,
              y: anchorY + direction * toolHeight * .28,
              material: bronzeMaterial,
              segments: 30,
              renderOrder: 12,
            });
          });
          continue;
        }

        if (item.canonicalId === 'completion.safety_valve') {
          const toolHeight = 26;
          const bodyRadius = Math.max(5.2, contextWidth * .27);
          addCylinder({
            radius: bodyRadius,
            height: toolHeight,
            y: anchorY,
            material: darkMetalMaterial,
            segments: 30,
            renderOrder: 9,
          });
          [-toolHeight * .34, toolHeight * .34].forEach((offset) => addCylinder({
            radius: bodyRadius * 1.16,
            height: 3,
            y: anchorY + offset,
            material: brushedMetalMaterial,
            segments: 30,
            renderOrder: 10,
          }));
          addCylinder({
            radius: bodyRadius * 1.3,
            height: 5.5,
            y: anchorY,
            material: bronzeMaterial,
            segments: 30,
            renderOrder: 11,
          });
          addCylinder({
            radius: bodyRadius * .68,
            height: 3.2,
            y: anchorY,
            material: darkMetalMaterial,
            segments: 24,
            renderOrder: 12,
          });
          continue;
        }

        if (item.canonicalId === 'completion.downhole_valve') {
          const toolHeight = 22;
          const bodyRadius = Math.max(4.8, contextWidth * .25);
          addCylinder({
            radius: bodyRadius,
            height: toolHeight,
            y: anchorY,
            material: brushedMetalMaterial,
            segments: 28,
            renderOrder: 9,
          });
          [-toolHeight * .38, toolHeight * .38].forEach((offset) => addCylinder({
            radius: bodyRadius * 1.08,
            height: 2.3,
            y: anchorY + offset,
            material: darkMetalMaterial,
            segments: 28,
            renderOrder: 10,
          }));
          addCylinder({
            radius: bodyRadius * 1.28,
            height: 8,
            y: anchorY,
            material: darkMetalMaterial,
            segments: 6,
            renderOrder: 11,
          });
          addCylinder({
            radius: bodyRadius * .62,
            height: 4,
            y: anchorY,
            material: brushedMetalMaterial,
            segments: 20,
            renderOrder: 12,
          });
          continue;
        }

        if (item.canonicalId === 'completion.sliding_sleeve') {
          const toolHeight = 30;
          const bodyRadius = Math.max(4.7, contextWidth * .245);
          addCylinder({
            radius: bodyRadius,
            height: toolHeight,
            y: anchorY,
            material: brushedMetalMaterial,
            segments: 28,
            renderOrder: 9,
          });
          [-toolHeight * .4, toolHeight * .4].forEach((offset) => addCylinder({
            radius: bodyRadius * 1.1,
            height: 2.4,
            y: anchorY + offset,
            material: darkMetalMaterial,
            segments: 28,
            renderOrder: 10,
          }));
          [-5.6, 0, 5.6].forEach((offsetY) => {
            [-1, 1].forEach((side) => {
              const portGeometry = rememberGeometry(new THREE.BoxGeometry(
                Math.max(3.8, bodyRadius * .9),
                4.2,
                3.2,
              ));
              const port = new THREE.Mesh(portGeometry, darkMetalMaterial);
              port.position.set(
                sceneX + side * bodyRadius * .82,
                anchorY + offsetY,
                bodyRadius * .9,
              );
              port.renderOrder = 11;
              scene.add(port);
            });
          });
          addCylinder({
            radius: bodyRadius * 1.04,
            height: 1.8,
            y: anchorY,
            material: bronzeMaterial,
            segments: 28,
            renderOrder: 12,
          });
          continue;
        }

        if (item.canonicalId === 'completion.gas_lift') {
          const toolHeight = 30;
          const mandrelRadius = Math.max(4.8, contextWidth * .25);
          addCylinder({
            radius: mandrelRadius,
            height: toolHeight,
            y: anchorY,
            material: brushedMetalMaterial,
            segments: 28,
            renderOrder: 9,
          });
          [-toolHeight * .4, toolHeight * .4].forEach((offset) => addCylinder({
            radius: mandrelRadius * 1.08,
            height: 2.2,
            y: anchorY + offset,
            material: darkMetalMaterial,
            segments: 28,
            renderOrder: 10,
          }));
          const valveHousing = rememberGeometry(new THREE.CapsuleGeometry(
            Math.max(2.5, mandrelRadius * .56),
            10,
            6,
            14,
          ));
          const valve = new THREE.Mesh(valveHousing, bronzeMaterial);
          valve.position.set(sceneX + mandrelRadius * 1.12, anchorY, 1.2);
          valve.rotation.z = Math.PI * .5;
          valve.renderOrder = 11;
          scene.add(valve);
          const portGeometry = rememberGeometry(new THREE.CylinderGeometry(1.25, 1.25, 4.4, 16));
          const port = new THREE.Mesh(portGeometry, darkMetalMaterial);
          port.position.set(sceneX + mandrelRadius * 1.55, anchorY, 1.2);
          port.rotation.z = Math.PI * .5;
          port.renderOrder = 12;
          scene.add(port);
          continue;
        }

        if (item.canonicalId === 'completion.icd_aicd') {
          const toolHeight = item.baseMd !== null && item.baseMd > item.topMd
            ? Math.max(18, Math.abs(depthToWorldY(item.topMd) - depthToWorldY(item.baseMd)))
            : 22;
          const toolRadius = Math.max(5.0, contextWidth * .26);
          addCylinder({
            radius: toolRadius,
            height: toolHeight,
            y: anchorY,
            material: darkMetalMaterial,
            segments: 28,
            renderOrder: 9,
          });
          [-toolHeight * .36, toolHeight * .36].forEach((offset) => addCylinder({
            radius: toolRadius * 1.14,
            height: 2,
            y: anchorY + offset,
            material: bronzeMaterial,
            segments: 28,
            renderOrder: 10,
          }));
          [-4.5, 0, 4.5].forEach((offsetY) => {
            [-1, 1].forEach((side) => {
              const nozzleGeometry = rememberGeometry(new THREE.CylinderGeometry(
                1.35,
                1.35,
                3.6,
                14,
              ));
              const nozzle = new THREE.Mesh(nozzleGeometry, bronzeMaterial);
              nozzle.position.set(
                sceneX + side * toolRadius * .93,
                anchorY + offsetY,
                toolRadius * .78,
              );
              nozzle.rotation.z = Math.PI * .5;
              nozzle.renderOrder = 11;
              scene.add(nozzle);
            });
          });
          addCylinder({
            radius: toolRadius * .72,
            height: 3.2,
            y: anchorY,
            material: brushedMetalMaterial,
            segments: 24,
            renderOrder: 12,
          });
          continue;
        }

        if (item.canonicalId === 'completion.retainer') {
          const toolHeight = Math.max(18, 26 * (tubingWidth / 6));
          addCylinder({
            radius: Math.max(7, contextWidth * .34),
            height: toolHeight,
            y: anchorY,
            material: bronzeMaterial,
            segments: 30,
            renderOrder: 9,
          });
          // Dark machined collars make the mounted device read as a real assembly.
          [-toolHeight * .34, 0, toolHeight * .34].forEach((offset) => addCylinder({
            radius: Math.max(7.7, contextWidth * .38),
            height: 2.2,
            y: anchorY + offset,
            material: darkMetalMaterial,
            segments: 30,
            renderOrder: 10,
          }));
          continue;
        }

        if (item.canonicalId === 'completion.cement_barrier') {
          const barrierHeight = item.baseMd !== null && item.baseMd > item.topMd
            ? Math.max(14, Math.abs(depthToWorldY(item.topMd) - depthToWorldY(item.baseMd)))
            : 30;
          const baseRadius = Math.max(10.5, contextWidth * .70);
          const radiusProfile = [.88, .96, 1.02, 1, .97, .92, .86];
          const segmentHeight = barrierHeight / radiusProfile.length;

          // Build the squeeze cement as a deposited annular sleeve rather than a
          // capped translucent cylinder. Slight radius variation makes the outer
          // profile read as placed cement while the opaque tubular remains visible
          // through the open centre in the orthographic view.
          radiusProfile.forEach((radiusScale, index) => {
            const radius = baseRadius * radiusScale;
            const geometry = rememberGeometry(new THREE.CylinderGeometry(
              radius,
              radius,
              segmentHeight * 1.12,
              32,
              1,
              true,
            ));
            const sleeve = new THREE.Mesh(geometry, cementMaterial);
            sleeve.position.set(
              sceneX,
              anchorY - barrierHeight * .5 + segmentHeight * (index + .5),
              0,
            );
            sleeve.renderOrder = 2;
            scene.add(sleeve);
          });

          // Soft edge rings remove the box-like cut ends without turning the
          // cement into mechanical hardware.
          [-1, 1].forEach((direction) => {
            const edgeGeometry = rememberGeometry(new THREE.TorusGeometry(
              baseRadius * .90,
              Math.max(.45, baseRadius * .055),
              8,
              28,
            ));
            const edge = new THREE.Mesh(edgeGeometry, cementEdgeMaterial);
            edge.position.set(sceneX, anchorY + direction * barrierHeight * .49, 0);
            edge.rotation.x = Math.PI * .5;
            edge.renderOrder = 3;
            scene.add(edge);
          });
          continue;
        }

        if (item.canonicalId === 'completion.perforations') {
          if (item.baseMd === null || item.baseMd <= item.topMd) continue;
          const clippedTop = Math.max(item.topMd, viewDepthRange.min);
          const clippedBase = Math.min(item.baseMd, viewDepthRange.max);
          const topPx = depthToY(clippedTop, viewDepthRange, bodyHeight);
          const basePx = depthToY(clippedBase, viewDepthRange, bodyHeight);
          const intervalPx = Math.max(3, basePx - topPx);
          const stationCount = Math.max(3, Math.min(28, Math.floor(intervalPx / 13) + 1));
          const shotLength = Math.max(7, contextWidth * .32);
          const shotThickness = 1.25;
          for (let index = 0; index < stationCount; index += 1) {
            const ratio = stationCount <= 1 ? .5 : index / (stationCount - 1);
            const md = THREE.MathUtils.lerp(clippedTop, clippedBase, ratio);
            const y = depthToWorldY(md);
            const side = index % 2 === 0 ? -1 : 1;
            const geometry = rememberGeometry(new THREE.BoxGeometry(shotLength, shotThickness, 1.6));
            const shot = new THREE.Mesh(geometry, perfMaterial);
            shot.position.set(sceneX + side * (contextWidth * .5 + shotLength * .5 - 1), y, 2.2);
            shot.rotation.z = side * THREE.MathUtils.degToRad(16);
            shot.castShadow = true;
            shot.renderOrder = 8;
            scene.add(shot);
          }
        }
      }

      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.castShadow = true;
          object.receiveShadow = true;
        }
      });

      renderer.render(scene, camera);
      if (!disposed) onReady(true);
    } catch (error) {
      console.error('WDV Completion orthographic 3D renderer unavailable; using 2D fallback', error);
      if (!disposed) onReady(false);
    }

    return () => {
      disposed = true;
      onReady(false);
      geometries.forEach((geometry) => geometry.dispose());
      materials.forEach((material) => material.dispose());
      renderer?.dispose();
    };
  }, [axisX, bodyHeight, components, contextWidth, onReady, tubingWidth, viewDepthRange.max, viewDepthRange.min, width]);

  return <canvas
    ref={canvasRef}
    aria-hidden="true"
    style={{
      position: 'absolute',
      inset: 0,
      width: '100%',
      height: '100%',
      pointerEvents: 'none',
      zIndex: 3,
    }}
  />;
}

function CompletionTrack({
  track,
  components,
  viewDepthRange,
  bodyHeight,
  sharedHeaderHeight,
  magnificationLabel,
  selected,
  onSelect,
  onStartResize,
  resizing,
  boreBaseMd = null,
  topsFillLayer = null,
  formationTopsLayer = null,
}: {
  track: WellLogTrack;
  components: CompletionComponentRecord[];
  viewDepthRange: DepthViewRange;
  bodyHeight: number;
  sharedHeaderHeight: number;
  magnificationLabel: string;
  selected: boolean;
  onSelect: (trackId: string, additive?: boolean) => void;
  onStartResize: (trackId: string, startX: number, startWidth: number) => void;
  resizing: boolean;
  boreBaseMd?: number | null;
  topsFillLayer?: ReactNode;
  formationTopsLayer?: ReactNode;
}) {
  const width = Math.max(120, track.widthPx || 220);
  const [orthographic3dReady, setOrthographic3dReady] = useState(false);
  const appearance: CompletionTrackAppearance = {
    ...DEFAULT_COMPLETION_TRACK_APPEARANCE,
    ...(track.trackType === 'completion' ? track.completionAppearance : {}),
  };
  const visible = components.filter((item) => {
    const base = item.baseMd ?? item.topMd;
    return base >= viewDepthRange.min && item.topMd <= viewDepthRange.max;
  });

  const axisPct = appearance.schematicPosition === 'left'
    ? 0.25
    : appearance.schematicPosition === 'right'
      ? 0.75
      : 0.5;
  const contextWidth = Math.max(20, Math.min(32, Math.round(appearance.schematicWidthPx * 0.62)));
  const casingRadius = contextWidth / 2;
  const tubingWidth = Math.max(5, Math.min(9, Math.round(6 * appearance.symbolScale)));
  const axisX = Math.max(
    casingRadius + 16,
    Math.min(width - casingRadius - 16, Math.round(width * axisPct)),
  );
  const resolvedLabelPosition = appearance.labelPosition === 'auto'
    ? (axisX > width * 0.58 ? 'left' : 'right')
    : appearance.labelPosition;
  const labelGap = casingRadius + appearance.labelOffsetPx + 10;

  const cleanCompletionLabel = (value: string): string => value
    .replace(/\s+â[^\s]*/g, ' —')
    .replace(/\s+Ã¢[^\s]*/g, ' —')
    .replace(/â€”|â€“|â€"|â€™|â€˜|â€œ|â€|â€/g, '—')
    .replace(/\u00e2\u20ac\u201d|\u00e2\u20ac\u201c|\u00e2\u20ac\u2013/g, '—')
    .replace(/\s+—\s+/g, ' — ')
    .replace(/\s{2,}/g, ' ')
    .trim();

  const completionAnchorY = (item: CompletionComponentRecord): number => {
    if (item.baseMd !== null && item.baseMd > item.topMd) {
      return depthToY((item.topMd + item.baseMd) / 2, viewDepthRange, bodyHeight);
    }
    return depthToY(item.topMd, viewDepthRange, bodyHeight);
  };

  const clippedIntervalGeometry = (item: CompletionComponentRecord) => {
    const clippedTop = Math.max(item.topMd, viewDepthRange.min);
    const clippedBase = Math.min(item.baseMd ?? item.topMd, viewDepthRange.max);
    const top = depthToY(clippedTop, viewDepthRange, bodyHeight);
    const base = depthToY(clippedBase, viewDepthRange, bodyHeight);
    return {
      top,
      base,
      height: Math.max(2, base - top),
    };
  };

  const metallicTubularStyle = (
    tubularWidth: number,
    left: number,
    top: number,
    height: number,
    strong = false,
  ): React.CSSProperties => ({
    position: 'absolute',
    left,
    top,
    width: tubularWidth,
    height,
    boxSizing: 'border-box',
    borderLeft: `${strong ? Math.max(2, appearance.lineWeight + 1) : Math.max(1, appearance.lineWeight)}px solid ${strong ? '#4b5963' : '#62717b'}`,
    borderRight: `${strong ? Math.max(2, appearance.lineWeight + 1) : Math.max(1, appearance.lineWeight)}px solid ${strong ? '#4b5963' : '#62717b'}`,
    background: 'linear-gradient(90deg, #101b22 0%, #263740 5%, #5f737e 11%, #b9c7cd 20%, #f7fbfc 28%, #ffffff 34%, #8fa1aa 40%, #2a3c46 48%, #647985 54%, #eef4f6 61%, #ffffff 67%, #a4b4bc 74%, #50636e 84%, #22323b 94%, #0c171d 100%)',
    boxShadow: strong
      ? 'inset 3px 0 3px rgba(255,255,255,.96), inset -4px 0 4px rgba(5,12,17,.52), inset 0 1px 1px rgba(255,255,255,.70), inset 0 -1px 1px rgba(0,0,0,.24), 2px 2px 3px rgba(19,29,35,.34), -1px 0 1px rgba(255,255,255,.22)'
      : 'inset 2px 0 2px rgba(255,255,255,.66), inset -2px 0 2px rgba(0,0,0,.22), 1px 1px 1px rgba(18,28,34,.18)',
    opacity: strong ? 1 : 0.96,
    zIndex: 2,
  });

  const renderPerforations = (item: CompletionComponentRecord): ReactNode => {
    const geometry = clippedIntervalGeometry(item);
    const shotLength = Math.max(5, Math.round(6 * appearance.symbolScale));
    const minimumSpacing = Math.max(4, Math.round(5 * appearance.symbolScale));
    const shotCount = Math.max(3, Math.min(34, Math.floor(geometry.height / Math.max(minimumSpacing, 7)) + 1));
    const step = shotCount <= 1 ? 0 : geometry.height / (shotCount - 1);

    return <div
      key={`${item.componentId}:perforations`}
      aria-hidden="true"
      style={{
        position: 'absolute',
        left: 0,
        top: geometry.top,
        width: '100%',
        height: geometry.height,
        zIndex: 6,
        pointerEvents: 'none',
      }}
    >
      {Array.from({ length: shotCount }, (_, index) => {
        const y = Math.min(geometry.height - 1, index * step);
        const leftPhase = index % 2 === 0;
        const fan = [
          { dy: -2.4, angle: leftPhase ? 10 : -10, tone: '#8b5634' },
          { dy: 0, angle: 0, tone: '#7f4f31' },
          { dy: 2.4, angle: leftPhase ? -10 : 10, tone: '#9a6849' },
        ];
        return <span key={index}>
          {fan.map((shot, shotIndex) => <i
            key={shotIndex}
            style={{
              position: 'absolute',
              left: leftPhase
                ? axisX - casingRadius - shotLength + 1
                : axisX + casingRadius - 1,
              top: y + shot.dy,
              width: shotLength,
              height: 0,
              borderTop: `${Math.max(1, appearance.lineWeight)}px solid ${shot.tone}`,
              transform: `rotate(${shot.angle}deg)`,
              transformOrigin: leftPhase ? 'right center' : 'left center',
              filter: 'drop-shadow(1px 1px .7px rgba(55,28,12,.42)) drop-shadow(-.35px -.35px .35px rgba(255,216,178,.24))',
            }}
          />)}
        </span>;
      })}
      <i style={{
        position: 'absolute',
        left: axisX - casingRadius - 1,
        top: 0,
        width: Math.max(1, appearance.lineWeight),
        height: '100%',
        background: '#8e5a36',
        opacity: .55,
      }}/>
      <i style={{
        position: 'absolute',
        left: axisX + casingRadius,
        top: 0,
        width: Math.max(1, appearance.lineWeight),
        height: '100%',
        background: '#8e5a36',
        opacity: .55,
      }}/>
    </div>;
  };

  const renderInterval = (item: CompletionComponentRecord): ReactNode => {
    const geometry = clippedIntervalGeometry(item);

    if (item.canonicalId === 'completion.perforations') {
      return renderPerforations(item);
    }

    if (item.canonicalId === 'completion.open_hole') {
      return <div
        key={`${item.componentId}:open-hole`}
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: axisX - casingRadius - 6,
          top: geometry.top,
          width: contextWidth + 12,
          height: geometry.height,
          borderLeft: `${Math.max(1, appearance.lineWeight)}px dashed #756c61`,
          borderRight: `${Math.max(1, appearance.lineWeight)}px dashed #756c61`,
          background: 'repeating-linear-gradient(135deg, rgba(129,117,101,.10) 0 3px, transparent 3px 8px)',
          zIndex: 1,
          boxSizing: 'border-box',
        }}
      />;
    }

    if (item.canonicalId === 'completion.cement_barrier') {
      return <div
        key={`${item.componentId}:cement-interval`}
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: axisX - casingRadius - 8,
          top: geometry.top,
          width: contextWidth + 16,
          height: Math.max(geometry.height, 12),
          border: `${Math.max(1, appearance.lineWeight)}px solid #746a5d`,
          borderRadius: 2,
          background: [
            'radial-gradient(circle at 18% 28%, rgba(80,72,64,.44) 0 1.3px, transparent 1.6px)',
            'radial-gradient(circle at 67% 63%, rgba(80,72,64,.35) 0 1.3px, transparent 1.6px)',
            'linear-gradient(90deg, #958c7e 0%, #ddd8cf 16%, #b0a89b 46%, #eeeae4 52%, #aaa294 72%, #8d8476 100%)',
          ].join(', '),
          boxShadow: 'inset 0 0 2px rgba(255,255,255,.52), 0 1px 2px rgba(0,0,0,.16)',
          zIndex: 3,
          boxSizing: 'border-box',
        }}
      />;
    }

    if (item.canonicalId === 'completion.screen') {
      const screenWidth = Math.max(18, Math.round(22 * appearance.symbolScale));
      return <div
        key={`${item.componentId}:screen`}
        aria-hidden="true"
        style={{
          ...metallicTubularStyle(screenWidth, axisX - screenWidth / 2, geometry.top, geometry.height, true),
          background: [
            'repeating-linear-gradient(0deg, transparent 0 4px, rgba(58,71,80,.8) 4px 5px)',
            'repeating-linear-gradient(90deg, transparent 0 5px, rgba(58,71,80,.36) 5px 6px)',
            'linear-gradient(90deg, #2f414b 0%, #667882 10%, #c5cfd4 23%, #ffffff 35%, #9aa8af 48%, #dfe6e9 59%, #ffffff 67%, #8b9aa2 82%, #334650 100%)',
          ].join(', '),
          zIndex: 5,
        }}
      />;
    }

    if (item.canonicalId === 'completion.casing') {
      return <div
        key={`${item.componentId}:casing`}
        aria-hidden="true"
        style={metallicTubularStyle(contextWidth, axisX - casingRadius, geometry.top, geometry.height, true)}
      />;
    }

    if (item.canonicalId === 'completion.liner') {
      const linerWidth = Math.max(18, Math.round(contextWidth * .72));
      return <div
        key={`${item.componentId}:liner`}
        aria-hidden="true"
        style={metallicTubularStyle(linerWidth, axisX - linerWidth / 2, geometry.top, geometry.height, true)}
      />;
    }

    const completionTubingWidth = Math.max(9, Math.round(tubingWidth * 1.45));
    return <div
      key={`${item.componentId}:tubing`}
      aria-hidden="true"
      style={{
        ...metallicTubularStyle(
          completionTubingWidth,
          axisX - completionTubingWidth / 2,
          geometry.top,
          geometry.height,
          true,
        ),
        borderTop: `${Math.max(2, appearance.lineWeight + 1)}px solid #4b5963`,
        borderBottom: `${Math.max(2, appearance.lineWeight + 1)}px solid #4b5963`,
      }}
    />;
  };

  const pointClusterOffset = (item: CompletionComponentRecord): number => {
    if (item.canonicalId === 'completion.cement_barrier') return 0;
    const y = completionAnchorY(item);
    const peers = visible
      .filter((candidate) => !completionUsesIntervalGeometry(candidate))
      .filter((candidate) => candidate.canonicalId !== 'completion.cement_barrier')
      .filter((candidate) => Math.abs(completionAnchorY(candidate) - y) < 1)
      .sort((a, b) => a.componentId.localeCompare(b.componentId));
    if (peers.length <= 1) return 0;
    const index = Math.max(0, peers.findIndex((candidate) => candidate.componentId === item.componentId));
    const lanes = [0, -0.32, 0.32, -0.58, 0.58];
    return (lanes[index % lanes.length] ?? 0) * contextWidth;
  };

  // Strong 2.5D material pass: geometry remains canonical and unchanged.
  const renderPoint = (item: CompletionComponentRecord): ReactNode => {
    const y = completionAnchorY(item);
    const offsetX = pointClusterOffset(item);
    const symbolWidth = Math.max(20, Math.round(contextWidth * .78));
    const symbolHeight = Math.max(22, Math.round(25 * appearance.symbolScale));
    const line = Math.max(1.1, appearance.lineWeight);
    const stroke = '#4c5962';
    const dark = '#35434d';
    const brown = '#6f6253';
    const steelId = `completion-steel-${item.componentId}`;
    const darkSteelId = `completion-dark-steel-${item.componentId}`;
    const bronzeId = `completion-bronze-${item.componentId}`;

    const metallicDefs = <defs>
      <linearGradient id={steelId} x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stopColor="#101b22"/>
        <stop offset="7%" stopColor="#2d414c"/>
        <stop offset="17%" stopColor="#71858f"/>
        <stop offset="27%" stopColor="#d6e1e5"/>
        <stop offset="34%" stopColor="#ffffff"/>
        <stop offset="38%" stopColor="#eef5f7"/>
        <stop offset="47%" stopColor="#536873"/>
        <stop offset="53%" stopColor="#263943"/>
        <stop offset="60%" stopColor="#91a4ad"/>
        <stop offset="67%" stopColor="#ffffff"/>
        <stop offset="72%" stopColor="#e4ecef"/>
        <stop offset="84%" stopColor="#6a7e88"/>
        <stop offset="94%" stopColor="#2a3d47"/>
        <stop offset="100%" stopColor="#0c171d"/>
      </linearGradient>
      <linearGradient id={darkSteelId} x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stopColor="#071015"/>
        <stop offset="12%" stopColor="#23333c"/>
        <stop offset="25%" stopColor="#50636e"/>
        <stop offset="38%" stopColor="#9babb3"/>
        <stop offset="47%" stopColor="#f5f9fa"/>
        <stop offset="51%" stopColor="#ffffff"/>
        <stop offset="58%" stopColor="#687b85"/>
        <stop offset="72%" stopColor="#334650"/>
        <stop offset="88%" stopColor="#18262e"/>
        <stop offset="100%" stopColor="#050c10"/>
      </linearGradient>
      <linearGradient id={bronzeId} x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stopColor="#21160f"/>
        <stop offset="8%" stopColor="#4d3523"/>
        <stop offset="18%" stopColor="#8a6542"/>
        <stop offset="30%" stopColor="#d7b986"/>
        <stop offset="39%" stopColor="#fff1cf"/>
        <stop offset="45%" stopColor="#fffbea"/>
        <stop offset="52%" stopColor="#8e6b48"/>
        <stop offset="59%" stopColor="#5c402a"/>
        <stop offset="68%" stopColor="#d0ad79"/>
        <stop offset="75%" stopColor="#fff3d3"/>
        <stop offset="84%" stopColor="#9b744c"/>
        <stop offset="94%" stopColor="#4b3322"/>
        <stop offset="100%" stopColor="#1d130d"/>
      </linearGradient>
    </defs>;

    const baseStyle: React.CSSProperties = {
      position: 'absolute',
      left: axisX + offsetX,
      top: y,
      width: symbolWidth,
      height: symbolHeight,
      transform: 'translate(-50%, -50%)',
      overflow: 'visible',
      pointerEvents: 'none',
      zIndex: item.canonicalId === 'completion.cement_barrier' ? 5 : 9,
    };

    if (item.canonicalId === 'completion.cement_barrier') {
      const outerW = contextWidth + 12;
      const sleeveH = 28;
      const innerW = contextWidth + 1;
      const outerRadius = outerW / 2 - 1;
      const innerRadius = innerW / 2;
      return <svg
        aria-hidden="true"
        viewBox={`0 0 ${outerW} ${sleeveH}`}
        style={{ ...baseStyle, width: outerW, height: sleeveH, opacity: .54 }}
      >
        <defs>
          <pattern id={`cement-hatch-${item.componentId}`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
            <line x1="0" y1="0" x2="0" y2="5" stroke="#81776b" strokeWidth=".9"/>
          </pattern>
          <mask id={`cement-ring-${item.componentId}`}>
            <rect width={outerW} height={sleeveH} fill="white"/>
            <rect
              x={(outerW - innerW) / 2}
              y="2"
              width={innerW}
              height={sleeveH - 4}
              rx={Math.min(innerRadius, 4)}
              fill="black"
            />
          </mask>
        </defs>
        <rect
          x="1"
          y="1"
          width={outerW - 2}
          height={sleeveH - 2}
          rx={Math.min(outerRadius, 5)}
          fill={`url(#cement-hatch-${item.componentId})`}
          stroke="#978d81"
          strokeWidth=".8"
          mask={`url(#cement-ring-${item.componentId})`}
        />
      </svg>;
    }

    if (item.canonicalId === 'completion.packer') {
      return <svg aria-hidden="true" viewBox="0 0 24 30" style={{ ...baseStyle, filter: 'drop-shadow(2px 2.5px 2px rgba(6,12,16,.52)) drop-shadow(-.7px -.8px .55px rgba(255,255,255,.42))' }}>
        {metallicDefs}
        <rect x="8" y="1" width="8" height="28" rx="2" fill={`url(#${steelId})`} stroke={dark} strokeWidth={line}/>
        <path d="M8 7 L2 11 L8 15" fill="none" stroke={dark} strokeWidth="2.2"/>
        <path d="M16 7 L22 11 L16 15" fill="none" stroke={dark} strokeWidth="2.2"/>
        <path d="M8 15 L2 19 L8 23" fill="none" stroke={dark} strokeWidth="2.2"/>
        <path d="M16 15 L22 19 L16 23" fill="none" stroke={dark} strokeWidth="2.2"/>
      </svg>;
    }

    if (item.canonicalId === 'completion.retainer') {
      return <svg aria-hidden="true" viewBox="0 0 24 34" style={{ ...baseStyle, width: symbolWidth + 1, height: symbolHeight + 5, filter: 'drop-shadow(2px 2.5px 2.2px rgba(29,18,11,.58)) drop-shadow(-.7px -.8px .55px rgba(255,245,220,.40))' }}>
        {metallicDefs}
        <rect x="7" y="1.5" width="10" height="31" rx="1.8" fill={`url(#${bronzeId})`} stroke={brown} strokeWidth={Math.max(1.2, line)}/>
        <line x1="7" y1="8" x2="17" y2="8" stroke={brown} strokeWidth="1.2"/>
        <line x1="7" y1="17" x2="17" y2="17" stroke={brown} strokeWidth="1.2"/>
        <line x1="7" y1="26" x2="17" y2="26" stroke={brown} strokeWidth="1.2"/>
        <path d="M7 8 L3 11 L7 13" fill="#d5cec4" stroke={brown} strokeWidth="1.2"/>
        <path d="M17 8 L21 11 L17 13" fill="#d5cec4" stroke={brown} strokeWidth="1.2"/>
        <path d="M7 21 L3 24 L7 26" fill="#d5cec4" stroke={brown} strokeWidth="1.2"/>
        <path d="M17 21 L21 24 L17 26" fill="#d5cec4" stroke={brown} strokeWidth="1.2"/>
      </svg>;
    }

    if (item.canonicalId === 'completion.bridge_plug') {
      return <svg aria-hidden="true" viewBox="0 0 22 28" style={{ ...baseStyle, filter: 'drop-shadow(2px 2.5px 2.1px rgba(31,19,11,.54)) drop-shadow(-.7px -.8px .5px rgba(255,240,213,.34))' }}>
        {metallicDefs}
        <rect x="6" y="1.5" width="10" height="25" rx="1.5" fill={`url(#${bronzeId})`} stroke="#5d4435" strokeWidth={line}/>
        <line x1="6" y1="7" x2="16" y2="21" stroke="#5d4435" strokeWidth="2"/>
        <line x1="16" y1="7" x2="6" y2="21" stroke="#5d4435" strokeWidth="2"/>
        <line x1="4" y1="23" x2="18" y2="23" stroke="#5d4435" strokeWidth="2"/>
      </svg>;
    }

    if (item.canonicalId === 'completion.safety_valve') {
      return <svg aria-hidden="true" viewBox="0 0 22 28" style={{ ...baseStyle, filter: 'drop-shadow(1px 1.5px 1.3px rgba(18,27,33,.32))' }}>
        {metallicDefs}
        <rect x="6" y="2" width="10" height="24" rx="2" fill={`url(#${darkSteelId})`} stroke={dark} strokeWidth={line}/>
        <path d="M7.5 10 L11 6.5 L14.5 10 L11 13.5 Z" fill="#eef2f4" stroke={dark} strokeWidth="1.3"/>
        <line x1="11" y1="13.5" x2="11" y2="20.5" stroke={dark} strokeWidth="1.3"/>
      </svg>;
    }

    if (item.canonicalId === 'completion.downhole_valve') {
      return <svg aria-hidden="true" viewBox="0 0 22 26" style={{ ...baseStyle, filter: 'drop-shadow(1px 1.4px 1.25px rgba(18,27,33,.29))' }}>
        {metallicDefs}
        <rect x="6" y="2" width="10" height="22" rx="1.7" fill={`url(#${steelId})`} stroke={stroke} strokeWidth={line}/>
        <path d="M7.5 8 L14.5 18 M14.5 8 L7.5 18" stroke={stroke} strokeWidth="1.7"/>
      </svg>;
    }

    if (item.canonicalId === 'completion.sliding_sleeve') {
      return <svg aria-hidden="true" viewBox="0 0 22 28" style={{ ...baseStyle, filter: 'drop-shadow(1px 1.4px 1.25px rgba(18,27,33,.29))' }}>
        {metallicDefs}
        <rect x="6" y="2" width="10" height="24" rx="1.4" fill={`url(#${steelId})`} stroke={stroke} strokeWidth={line}/>
        <line x1="7.5" y1="10" x2="14.5" y2="10" stroke={stroke} strokeWidth="1.5"/>
        <line x1="7.5" y1="18" x2="14.5" y2="18" stroke={stroke} strokeWidth="1.5"/>
        <line x1="11" y1="10" x2="11" y2="18" stroke={stroke} strokeWidth="1"/>
      </svg>;
    }

    if (item.canonicalId === 'completion.gas_lift') {
      return <svg aria-hidden="true" viewBox="0 0 26 28" style={{ ...baseStyle, width: symbolWidth + 4, filter: 'drop-shadow(1px 1.4px 1.25px rgba(18,27,33,.29))' }}>
        {metallicDefs}
        <rect x="6" y="2" width="10" height="24" rx="1.5" fill={`url(#${steelId})`} stroke={stroke} strokeWidth={line}/>
        <rect x="16" y="8" width="7" height="12" rx="3" fill="#eef2f3" stroke={stroke} strokeWidth="1.2"/>
        <circle cx="19.5" cy="14" r="1.5" fill={stroke}/>
      </svg>;
    }

    if (item.canonicalId === 'completion.icd_aicd') {
      return <svg aria-hidden="true" viewBox="0 0 26 26" style={{ ...baseStyle, width: symbolWidth + 4, filter: 'drop-shadow(1px 1.3px 1.2px rgba(18,27,33,.26))' }}>
        {metallicDefs}
        <rect x="5" y="4" width="16" height="18" rx="2" fill={`url(#${steelId})`} stroke={stroke} strokeWidth={line}/>
        <circle cx="9" cy="13" r="1.5" fill={stroke}/>
        <circle cx="13" cy="13" r="1.5" fill={stroke}/>
        <circle cx="17" cy="13" r="1.5" fill={stroke}/>
      </svg>;
    }

    return <svg aria-hidden="true" viewBox="0 0 22 26" style={{ ...baseStyle, filter: 'drop-shadow(1px 1.3px 1.2px rgba(18,27,33,.26))' }}>
      {metallicDefs}
      <rect x="6" y="2" width="10" height="22" rx="1.6" fill={`url(#${steelId})`} stroke={stroke} strokeWidth={line}/>
      <circle cx="11" cy="13" r="3" fill="#eef2f3" stroke={stroke} strokeWidth="1.3"/>
    </svg>;
  };

  const boreEndY = boreBaseMd == null
    ? bodyHeight
    : boreBaseMd <= viewDepthRange.min
      ? 0
      : boreBaseMd >= viewDepthRange.max
        ? bodyHeight
        : depthToY(boreBaseMd, viewDepthRange, bodyHeight);

  const labelLineHeightPx = Math.max(11, Math.round(appearance.labelFontSize * 1.2));
  const labelHeightPx = appearance.labelWrap
    ? labelLineHeightPx * 2
    : labelLineHeightPx;
  const labelGapPx = 4;
  const labelPlacements = new Map<string, number>();

  if (appearance.showLabels) {
    const labelCandidates = visible
      .map((item) => ({ item, anchorY: completionAnchorY(item) }))
      .sort((a, b) => a.anchorY - b.anchorY || a.item.componentId.localeCompare(b.item.componentId));

    let cursor = labelHeightPx / 2 + 2;
    for (const candidate of labelCandidates) {
      const placed = appearance.labelCollisionMode === 'off'
        ? candidate.anchorY
        : Math.max(candidate.anchorY, cursor);
      labelPlacements.set(candidate.item.componentId, placed);
      cursor = placed + labelHeightPx + labelGapPx;
    }

    if (appearance.labelCollisionMode !== 'off') {
      const overflow = cursor - labelGapPx - labelHeightPx / 2 - bodyHeight;
      if (overflow > 0) {
        for (const candidate of labelCandidates) {
          const current = labelPlacements.get(candidate.item.componentId) ?? candidate.anchorY;
          labelPlacements.set(
            candidate.item.componentId,
            Math.max(labelHeightPx / 2 + 2, current - overflow),
          );
        }
      }
    }
  }

  return <section
    className={`wlv-track completion${selected ? ' selected' : ''}${resizing ? ' resizing' : ''}`}
    style={{ width: `${width}px`, minWidth: `${width}px`, flexBasis: `${width}px` }}
    onMouseDownCapture={(event) => {
      if (event.shiftKey && event.button === 0) {
        const target = event.target;
        if (target instanceof Element && target.closest('.wlv-track-body')) {
          event.preventDefault();
          event.stopPropagation();
          onSelect(track.trackId);
          onStartResize(track.trackId, event.clientX, width);
        }
      }
    }}
    onClick={(event) => {
      onSelect(track.trackId, event.metaKey);
    }}
  >
    <header
      className="wlv-track-header wlv-track-header-aligned"
      style={{ height: `${sharedHeaderHeight}px`, minHeight: `${sharedHeaderHeight}px`, flexBasis: `${sharedHeaderHeight}px` }}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onSelect(track.trackId, event.metaKey);
      }}
    >
      <div className="wlv-track-title-row">
        <strong>{track.title || 'Completion'}</strong>
        <TrackPlacementSelector track={track}/>
      </div>
      <div className="wlv-track-header-row-2">
        <div className="wlv-depth-header">{track.ownerWellName || 'Well not resolved'}</div>
        <span className="wlv-track-magnification">{magnificationLabel}</span>
      </div>
      <div className="wlv-track-header-row-3">
        <div className="wlv-depth-header">Completion Components</div>
      </div>
      <div className="wlv-track-header-detail-rows">
        <div className="wlv-track-header-detail-placeholder" aria-hidden="true" />
      </div>
    </header>

    <div
      className="wlv-track-body wlv-completion-track-body"
      style={{
        height: `${bodyHeight}px`,
        minHeight: `${bodyHeight}px`,
        flexBasis: `${bodyHeight}px`,
        position: 'relative',
        overflow: 'hidden',
        background: 'linear-gradient(90deg, rgba(247,249,250,.98), rgba(255,255,255,.99))',
      }}
    >
      <CompletionOrthographic3DLayer
        width={width}
        bodyHeight={bodyHeight}
        axisX={axisX}
        contextWidth={contextWidth}
        tubingWidth={tubingWidth}
        components={visible}
        viewDepthRange={viewDepthRange}
        boreBaseMd={boreBaseMd}
        onReady={setOrthographic3dReady}
      />

      {/* Completion is a presentation surface for its host well. Keep the
          well-owned Formation Tops/fill layers independent of completion data. */}
      <div className="wlv-track-content-layer tops-fill-layer" style={{ zIndex: 2 }}>
        {topsFillLayer}
      </div>
      <div className="wlv-track-content-layer formation-tops-layer" style={{ zIndex: 10 }}>
        {formationTopsLayer}
      </div>

      {/* 2D fallback remains live until WebGL has rendered successfully. */}
      {!orthographic3dReady ? <>
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: axisX - casingRadius,
          top: 0,
          width: contextWidth,
          height: `${boreEndY}px`,
          borderLeft: `${Math.max(1, appearance.lineWeight)}px solid rgba(78,91,100,.46)`,
          borderRight: `${Math.max(1, appearance.lineWeight)}px solid rgba(78,91,100,.46)`,
          background: 'linear-gradient(90deg, rgba(31,44,52,.20) 0%, rgba(98,115,124,.18) 10%, rgba(224,231,234,.34) 24%, rgba(255,255,255,.62) 36%, rgba(126,141,149,.16) 50%, rgba(255,255,255,.56) 64%, rgba(211,220,224,.30) 77%, rgba(81,98,107,.18) 90%, rgba(26,39,46,.20) 100%)',
          boxShadow: 'inset 2px 0 2px rgba(255,255,255,.46), inset -2px 0 2px rgba(0,0,0,.13), 1px 1px 2px rgba(35,48,55,.12)',
          zIndex: 1,
          boxSizing: 'border-box',
        }}
      />
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: axisX - tubingWidth / 2,
          top: 0,
          width: tubingWidth,
          height: `${boreEndY}px`,
          borderLeft: `${Math.max(1, appearance.lineWeight)}px solid rgba(66,80,89,.78)`,
          borderRight: `${Math.max(1, appearance.lineWeight)}px solid rgba(66,80,89,.78)`,
          background: 'linear-gradient(90deg, #17252d 0%, #41545e 9%, #95a6ae 19%, #e4ecef 30%, #ffffff 39%, #ffffff 44%, #73868f 51%, #324650 58%, #d8e2e6 67%, #ffffff 74%, #9aaab2 83%, #40535d 93%, #132129 100%)',
          boxShadow: 'inset 2px 0 2px rgba(255,255,255,.92), inset -3px 0 3px rgba(0,0,0,.34), 1px 1px 2px rgba(29,42,49,.32), -1px 0 1px rgba(255,255,255,.22)',
          zIndex: 4,
          boxSizing: 'border-box',
          opacity: .98,
        }}
      />
      </> : null}


      {visible.map((item) => {
        const isInterval = completionUsesIntervalGeometry(item);
        const y = completionAnchorY(item);
        const baseLabelY = labelPlacements.get(item.componentId) ?? y;
        const labelY = Math.max(
          labelHeightPx / 2 + 2,
          Math.min(bodyHeight - labelHeightPx / 2 - 2, baseLabelY + appearance.labelVerticalOffsetPx),
        );
        const labelSideX = resolvedLabelPosition === 'left'
          ? axisX - casingRadius - 1
          : axisX + casingRadius + 1;
        const labelX = resolvedLabelPosition === 'left'
          ? axisX - Math.max(8, labelGap - 4)
          : axisX + Math.max(8, labelGap - 4);
        const displayLabel = cleanCompletionLabel(item.label);
        const leaderNeeded = Math.abs(labelY - y) > Math.max(6, labelLineHeightPx * .45);

        return <div key={item.componentId}>
          {!orthographic3dReady || !completionUses3DRender(item) ? (isInterval ? renderInterval(item) : renderPoint(item)) : null}

          {appearance.showLabels && leaderNeeded ? <svg
            aria-hidden="true"
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              overflow: 'visible',
              pointerEvents: 'none',
              zIndex: 9,
            }}
          >
            <line
              x1={labelSideX}
              y1={y}
              x2={labelX}
              y2={labelY}
              stroke="#9aa5ad"
              strokeWidth={1}
            />
          </svg> : null}

          {appearance.showLabels ? <div
            style={{
              position: 'absolute',
              ...(resolvedLabelPosition === 'left'
                ? {
                    right: width - axisX + labelGap,
                    width: Math.min(appearance.labelMaxWidthPx, Math.max(44, axisX - labelGap - 8)),
                    textAlign: 'right' as const,
                  }
                : {
                    left: axisX + labelGap,
                    width: Math.min(appearance.labelMaxWidthPx, Math.max(44, width - axisX - labelGap - 8)),
                    textAlign: 'left' as const,
                  }),
              top: labelY,
              transform: 'translateY(-50%)',
              fontSize: appearance.labelFontSize,
              lineHeight: 1.15,
              color: '#34424d',
              fontWeight: 500,
              whiteSpace: appearance.labelWrap ? 'normal' : 'nowrap',
              overflow: 'hidden',
              textOverflow: appearance.labelWrap ? 'clip' : 'ellipsis',
              display: appearance.labelWrap ? '-webkit-box' : 'block',
              WebkitBoxOrient: appearance.labelWrap ? 'vertical' : undefined,
              WebkitLineClamp: appearance.labelWrap ? 2 : undefined,
              pointerEvents: 'none',
              zIndex: 10,
            }}
            title={`${displayLabel} · ${item.topMd}${item.baseMd !== null ? `–${item.baseMd}` : ''} ${item.depthUnit} MD`}
          >
            {displayLabel}
          </div> : null}
        </div>;
      })}

      {visible.length === 0 && <div
        style={{
          position: 'absolute',
          left: 8,
          right: 8,
          top: 18,
          color: '#7b8790',
          fontSize: 11,
          textAlign: 'center',
          zIndex: 12,
        }}
      >
        {components.length === 0 ? 'Select completion components in Well Data Inventory' : 'No completion components in view'}
      </div>}
    </div>
  </section>;
}

function IntervalDepthTrack({ track, markers, depthTicks, viewDepthRange, bodyHeight, sharedHeaderHeight, magnificationLabel, selected, onSelect }: {
  track: WellLogTrack;
  markers: FormationTopMarker[];
  depthTicks: number[];
  viewDepthRange: DepthViewRange;
  bodyHeight: number;
  sharedHeaderHeight: number;
  magnificationLabel: string;
  selected: boolean;
  onSelect: (trackId: string, additive?: boolean) => void;
}) {
  const [depthConfig,setDepthConfig]=useState<IntervalDepthConfig>(()=>loadIntervalDepthConfig());
  const [depthColumn,setDepthColumn]=useState<IntervalBuilderColumn>(()=>loadConfiguredDepthColumn());

  useEffect(()=>{
    const refresh=()=>{
      setDepthConfig(loadIntervalDepthConfig());
      setDepthColumn(loadConfiguredDepthColumn());
    };
    window.addEventListener('storage',refresh);
    window.addEventListener('focus',refresh);
    window.addEventListener('wlv:interval-depth-config-changed',refresh);
    return ()=>{
      window.removeEventListener('storage',refresh);
      window.removeEventListener('focus',refresh);
      window.removeEventListener('wlv:interval-depth-config-changed',refresh);
    };
  },[]);

  const decimals=depthConfig.decimalPlaces;
  const unit='m';
  const width=Math.max(1,depthColumn.width||58);
  const values=depthConfig.tieMode==='boundaries'
    ? markers.map((marker)=>marker.md)
    : depthTicks;

  const uniqueValues=Array.from(new Set(values))
    .filter((depth)=>depth>=viewDepthRange.min&&depth<=viewDepthRange.max)
    .sort((left,right)=>left-right);

  return <section
    className={`wlv-track wlv-interval-depth-track${selected?' selected':''}`}
    style={{width:`${width}px`,minWidth:`${width}px`,flexBasis:`${width}px`}}
    onMouseDown={(event)=>{
      if (event.button !== 0) return;
      const target = event.target;
      if (target instanceof Element && target.closest('.wlv-track-header')) return;
      onSelect(track.trackId, event.metaKey);
    }}
  >
    <header
      className="wlv-track-header wlv-track-header-aligned"
      style={{height:`${sharedHeaderHeight}px`,minHeight:`${sharedHeaderHeight}px`,flexBasis:`${sharedHeaderHeight}px`}}
            onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onSelect(track.trackId, event.metaKey);
        }}
      >
      <div className="wlv-track-title-row">
        <strong>{depthColumn.title||depthConfig.reference}</strong>
        <TrackPlacementSelector track={track}/>
      </div>
      <div className="wlv-track-header-row-2">
        <div className="wlv-track-header-placeholder" aria-hidden="true" />
        <span className="wlv-track-magnification">{magnificationLabel}</span>
      </div>
      <div className="wlv-track-header-row-3">
        <div className="wlv-depth-header">{track.ownerWellName || 'Well not resolved'}</div>
      </div>
      <div className="wlv-track-header-detail-rows">
        <div className="wlv-track-header-detail-placeholder" aria-hidden="true" />
      </div>
    </header>
    <div
      className="wlv-track-body wlv-interval-depth-body"
      style={{height:`${bodyHeight}px`,minHeight:`${bodyHeight}px`,flexBasis:`${bodyHeight}px`}}
    >
      {uniqueValues.map((depth,index)=>{
        const y=depthToY(depth,viewDepthRange,bodyHeight);
        const label=`${depth.toFixed(decimals)}${depthConfig.showUnitBesideValues?` ${unit}`:''}`;
        const inheritedLineColor=depthConfig.tieMode==='boundaries'?'#4b5563':'#9eabb8';
        const lineColor=depthConfig.lineColorMode==='custom'?depthConfig.customLineColor:inheritedLineColor;
        const lineClass=`wlv-interval-depth-line ${depthConfig.lineExtent}`;
        const lineOpacity=Math.max(0,Math.min(100,depthConfig.lineOpacity??100))/100;
        const labelClass=`wlv-interval-depth-label ${depthConfig.valuePosition} ${depthConfig.horizontalPosition}`;
        const offset=depthConfig.valuePosition==='above'?-depthConfig.valueOffset:depthConfig.valuePosition==='below'?depthConfig.valueOffset:0;
        return <div key={`${track.trackId}:interval-depth:${depth}:${index}`} className="wlv-interval-depth-value" style={{top:y}}>
          {depthConfig.lineMode!=='none'&&<i className={lineClass} style={{borderTopColor:lineColor,borderTopWidth:`${depthConfig.lineWidth}px`,borderTopStyle:depthConfig.lineStyle,opacity:lineOpacity}}/>}
          <span className={labelClass} style={{transform:`translateY(${offset}px)`}}>{label}</span>
        </div>;
      })}
      {uniqueValues.length===0&&<div className="wlv-interval-depth-empty">
        {depthConfig.tieMode==='boundaries'?'No boundary depths in view':'No depth values in view'}
      </div>}
    </div>
  </section>;
}

function IntervalBlankTrack({ track, bodyHeight, sharedHeaderHeight, magnificationLabel, selected, onSelect, trackA, trackB, topsFillLayer = null }: {
  track: WellLogTrack;
  bodyHeight: number;
  sharedHeaderHeight: number;
  magnificationLabel: string;
  selected: boolean;
  onSelect: (trackId: string, additive?: boolean) => void;
  trackA: WellLogTrack | null;
  trackB: WellLogTrack | null;
  topsFillLayer?: ReactNode;
}) {
  const [tieInHeaderState,setTieInHeaderState]=useState<IntervalTieInLayerState>(
    ()=>loadIntervalTieInLayerState(track.trackId),
  );
  useEffect(()=>{
    const refresh=()=>setTieInHeaderState(loadIntervalTieInLayerState(track.trackId));
    window.addEventListener('storage',refresh);
    window.addEventListener(INTERVAL_TIE_IN_CONFIG_CHANGED_EVENT,refresh);
    return()=>{
      window.removeEventListener('storage',refresh);
      window.removeEventListener(INTERVAL_TIE_IN_CONFIG_CHANGED_EVENT,refresh);
    };
  },[track.trackId]);
  const tieInLayerCount=intervalTieInRenderableLayers(tieInHeaderState).length;
  const tieInHeaderActive=tieInLayerCount>0&&trackA!==null&&trackB!==null;
  const tieInNeighbourLabel=tieInHeaderActive
    ? `T${trackA.trackIndex+1}-T${trackB.trackIndex+1}`
    : 'Blank interval track';
  const width = Math.max(1, track.widthPx || 180);
  return <section
    className={`wlv-track wlv-interval-blank-track${selected ? ' selected' : ''}`}
    style={{ width: `${width}px`, minWidth: `${width}px`, flexBasis: `${width}px` }}
    onMouseDown={(event) => {
        if (event.button !== 0) return;
        const target = event.target;
        if (target instanceof Element && target.closest('.wlv-track-header')) {
          event.preventDefault();
          event.stopPropagation();
          onSelect(track.trackId, event.metaKey);
          return;
        }
        onSelect(track.trackId, event.metaKey);
      }}
  >
    <header
      className="wlv-track-header wlv-track-header-aligned"
      style={{ height: `${sharedHeaderHeight}px`, minHeight: `${sharedHeaderHeight}px`, flexBasis: `${sharedHeaderHeight}px` }}
    >
      <div className="wlv-track-title-row">
        <strong>{tieInHeaderActive?'Tie-In':(track.title || 'Interval')}</strong>
        <TrackPlacementSelector track={track}/>
      </div>
      <div className="wlv-track-header-row-2">
        <div className="wlv-depth-header">{track.ownerWellName || 'Well not resolved'}</div>
        <span className="wlv-track-magnification">{magnificationLabel}</span>
      </div>
      <div className="wlv-track-header-row-3">
        <div className="wlv-depth-header">{tieInNeighbourLabel}</div>
      </div>
      <div className="wlv-track-header-detail-rows">
        <div className="wlv-track-header-detail-placeholder" aria-hidden="true" />
      </div>
    </header>
    <div
      className="wlv-track-body wlv-interval-blank-body"
      style={{height:`${bodyHeight}px`,minHeight:`${bodyHeight}px`,flexBasis:`${bodyHeight}px`}}
    >
      <div
        className="wlv-track-content-layer wlv-interval-overlay-infill-layer tops-fill-layer"
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          overflow: 'hidden',
          pointerEvents: 'none',
          zIndex: 20,
        }}
      >
        {topsFillLayer}
      </div>
    </div>
  </section>;
}

function IntervalFormationTrack({ track, markers, viewDepthRange, bodyHeight, sharedHeaderHeight, magnificationLabel, selected, onSelect }: {
  track: WellLogTrack;
  markers: FormationTopMarker[];
  viewDepthRange: DepthViewRange;
  bodyHeight: number;
  sharedHeaderHeight: number;
  magnificationLabel: string;
  selected: boolean;
  onSelect: (trackId: string, additive?: boolean) => void;
}) {
  const [formationConfig, setFormationConfig] = useState<IntervalFormationConfig>(() => loadIntervalFormationConfig());
  const [formationColumn, setFormationColumn] = useState<IntervalBuilderColumn>(() => loadConfiguredFormationColumn());

  useEffect(() => {
    const refresh = () => {
      setFormationConfig(loadIntervalFormationConfig());
      setFormationColumn(loadConfiguredFormationColumn());
    };
    window.addEventListener('storage', refresh);
    window.addEventListener('focus', refresh);
    window.addEventListener('wlv:interval-formation-config-changed', refresh);
    return () => {
      window.removeEventListener('storage', refresh);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('wlv:interval-formation-config-changed', refresh);
    };
  }, []);

  const selectedMarkerIds = new Set(formationConfig.selectedMarkerIds);
  const loadedTops = markers
    .filter((marker) => formationConfig.selectionMode === 'all' || selectedMarkerIds.has(marker.markerId))
    .map((marker) => ({
      id: marker.markerId,
      name: marker.markerName,
      md: marker.md,
      group: marker.group || '',
    }));

  const manualTops = formationConfig.manualTops
    .map((top) => ({
      id: top.id,
      name: top.name,
      md: Number(top.md),
      group: top.group || '',
    }))
    .filter((top) => Number.isFinite(top.md));

  const tops = (formationConfig.sourceMode === 'manual' ? manualTops : loadedTops)
    .filter((top) => top.md >= viewDepthRange.min && top.md <= viewDepthRange.max)
    .sort((left, right) => left.md - right.md);

  const allSourceTops = (formationConfig.sourceMode === 'manual' ? manualTops : loadedTops)
    .sort((left, right) => left.md - right.md);

  const intervals = allSourceTops.slice(0, -1).map((top, index) => ({
    ...top,
    baseMd: allSourceTops[index + 1].md,
  })).filter((interval) => interval.baseMd > interval.md);

  const width = Math.max(1, formationColumn.width || track.widthPx || 120);
  const labelStyle: React.CSSProperties = {
    color: formationConfig.fontColor,
    fontSize: `${formationConfig.fontSize}px`,
    fontWeight: formationConfig.fontWeight === 'bold' ? 700 : 400,
    textAlign: formationConfig.labelAlignment,
  };
  const boundaryStyle: React.CSSProperties = {
    borderTopColor: rgbaFromHex(formationConfig.boundaryColor, formationConfig.boundaryOpacity),
    borderTopWidth: `${formationConfig.boundaryWidth}px`,
    borderTopStyle: formationConfig.boundaryStyle,
  };

  return <section
    className={`wlv-track wlv-interval-formation-track${selected ? ' selected' : ''}`}
    style={{ width: `${width}px`, minWidth: `${width}px`, flexBasis: `${width}px` }}
    onMouseDown={(event) => {
        if (event.button !== 0) return;
        const target = event.target;
        if (target instanceof Element && target.closest('.wlv-track-header')) {
          event.preventDefault();
          event.stopPropagation();
          onSelect(track.trackId, event.metaKey);
          return;
        }
        onSelect(track.trackId, event.metaKey);
      }}
  >
    <header
      className="wlv-track-header wlv-track-header-aligned"
      style={{ height: `${sharedHeaderHeight}px`, minHeight: `${sharedHeaderHeight}px`, flexBasis: `${sharedHeaderHeight}px` }}
    >
      <div className="wlv-track-title-row">
        <strong>{formationColumn.title || 'Formation'}</strong>
        <TrackPlacementSelector track={track}/>
      </div>
      <div className="wlv-track-header-row-2">
        <div className="wlv-depth-header">{track.ownerWellName || 'Well not resolved'}</div>
        <span className="wlv-track-magnification">{magnificationLabel}</span>
      </div>
      <div className="wlv-track-header-row-3">
        <div className="wlv-depth-header">Formation Tops</div>
      </div>
      <div className="wlv-track-header-detail-rows">
        <div className="wlv-track-header-detail-placeholder" aria-hidden="true" />
      </div>
    </header>

    <div
      className="wlv-track-body wlv-interval-formation-body"
      style={{ height: `${bodyHeight}px`, minHeight: `${bodyHeight}px`, flexBasis: `${bodyHeight}px` }}
    >
      {formationConfig.showBoxFill && intervals.map((interval) => {
        const clippedTop = Math.max(interval.md, viewDepthRange.min);
        const clippedBase = Math.min(interval.baseMd, viewDepthRange.max);
        if (clippedBase <= clippedTop) return null;
        const top = depthToY(clippedTop, viewDepthRange, bodyHeight);
        const base = depthToY(clippedBase, viewDepthRange, bodyHeight);
        return <div
          key={`fill:${interval.id}`}
          className="wlv-interval-formation-fill"
          style={{
            top,
            height: Math.max(1, base - top),
            backgroundColor: rgbaFromHex(formationConfig.boxFillColor, formationConfig.boxFillOpacity),
            borderColor: formationConfig.showBoxBorder ? formationConfig.boxBorderColor : 'transparent',
            borderWidth: formationConfig.showBoxBorder ? `${formationConfig.boxBorderWidth}px` : 0,
          }}
        />;
      })}

      {tops.map((top) => {
        const y = depthToY(top.md, viewDepthRange, bodyHeight);
        return <div key={top.id} className="wlv-interval-formation-top" style={{ top: y }}>
          {formationConfig.showBoundaryLines && <i className="wlv-interval-formation-boundary" style={boundaryStyle}/>}
          {formationConfig.showLabels && <span className="wlv-interval-formation-label" style={labelStyle} title={`${top.name} · ${top.md.toLocaleString()} m MD`}>
            {top.name}
          </span>}
        </div>;
      })}

      {tops.length === 0 && <div className="wlv-interval-formation-empty">
        {formationConfig.sourceMode === 'manual'
          ? 'No manual Formation Tops'
          : markers.length === 0
            ? 'No loaded Formation Tops'
            : formationConfig.selectionMode === 'selected'
              ? 'No Formation Tops selected'
              : 'No Formation Tops in view'}
      </div>}
    </div>
  </section>;
}

// Tie-in layer durability invariant:
// - each persistent layer owns semantic MD correlation + style only;
// - legacy single-record Tie-ins migrate to Layer 1;
// - width, zoom and screen coordinates are never persisted;
// - every visible layer derives Y from the current A/B authoritative viewports;
// - host width only changes the SVG X extent.
function IntervalTieInOverlay({track,orderedTracks,trackDepthRangesById,fallbackViewDepthRange,lithologyIntervals,width,bodyHeight,bodyTop}:{track:WellLogTrack;orderedTracks:WellLogTrack[];trackDepthRangesById:Record<string,DepthViewRange>;fallbackViewDepthRange:DepthViewRange;lithologyIntervals:LithologyIntervalRecord[];width:number;bodyHeight:number;bodyTop:number;}){
  // HMR-safe transitional state:
  // Vite Fast Refresh can preserve the old single-config hook value when this
  // component is upgraded in-place. Never assume the preserved value already
  // has a .layers array. Normalize it on every render.
  const [tieInRenderState,setTieInRenderState]=useState<IntervalTieInLayerState|IntervalTieInConfig>(
    ()=>loadIntervalTieInLayerState(track.trackId),
  );
  const [tieInPreviewState,setTieInPreviewState]=useState<IntervalTieInLayerState|null>(null);
  useEffect(()=>{
    const refresh=()=>setTieInRenderState(loadIntervalTieInLayerState(track.trackId));
    const events=[
      INTERVAL_TIE_IN_CONFIG_CHANGED_EVENT,
      'wlv:interval-formation-config-changed',
      'wlv:interval-depth-config-changed',
      'wlv:interval-description-config-changed',
    ];
    const handlePreview=(event:Event)=>{const detail=(event as CustomEvent<{trackId?:string;state?:IntervalTieInLayerState}>).detail;if(detail?.trackId!==track.trackId||!detail.state)return;setTieInPreviewState(normalizeIntervalTieInLayerState(detail.state));};
    const handlePreviewEnd=(event:Event)=>{const detail=(event as CustomEvent<{trackId?:string}>).detail;if(detail?.trackId&&detail.trackId!==track.trackId)return;setTieInPreviewState(null);refresh();};
    window.addEventListener('storage',refresh);
    for(const eventName of events)window.addEventListener(eventName,refresh);
    window.addEventListener(INTERVAL_TIE_IN_PREVIEW_EVENT,handlePreview as EventListener);
    window.addEventListener(INTERVAL_TIE_IN_PREVIEW_END_EVENT,handlePreviewEnd as EventListener);
    return()=>{
      window.removeEventListener('storage',refresh);
      for(const eventName of events)window.removeEventListener(eventName,refresh);
      window.removeEventListener(INTERVAL_TIE_IN_PREVIEW_EVENT,handlePreview as EventListener);
      window.removeEventListener(INTERVAL_TIE_IN_PREVIEW_END_EVENT,handlePreviewEnd as EventListener);
    };
  },[track.trackId]);
  const index=orderedTracks.findIndex(candidate=>candidate.trackId===track.trackId);
  const trackA=index>0?orderedTracks[index-1]:null;
  const trackB=index>=0&&index<orderedTracks.length-1?orderedTracks[index+1]:null;
  if(!trackA||!trackB)return null;
  const rangeA=trackDepthRangesById[trackA.trackId]??fallbackViewDepthRange;
  const rangeB=trackDepthRangesById[trackB.trackId]??fallbackViewDepthRange;
  const mapY=(depth:number,range:DepthViewRange)=>{const span=range.max-range.min;return span===0?0:((depth-range.min)/span)*bodyHeight;};

  /*
   * WDV_TIE_IN_OFFSCREEN_CORRELATION_FIX_V1_0_0
   *
   * A Tie-in is a semantic relationship between two MD anchors. Either anchor
   * may legitimately be outside its track's current viewport. Do not reject or
   * clamp the anchor itself. Project both true MDs, then clip only the rendered
   * segment to the visible Tie-in rectangle.
   *
   * This preserves:
   * - A visible / B off-screen -> visible line exits through top/bottom edge;
   * - A off-screen / B visible -> visible line enters through top/bottom edge;
   * - both off-screen on opposite sides -> crossing portion remains visible;
   * - both off-screen on same side -> no visible segment.
   */
  const clipTieInSegment=(yA:number,yB:number):{x1:number;y1:number;x2:number;y2:number}|null=>{
    if(!Number.isFinite(yA)||!Number.isFinite(yB)||!Number.isFinite(width)||!Number.isFinite(bodyHeight)||width<=0||bodyHeight<=0)return null;
    const dy=yB-yA;
    let tMin=0;
    let tMax=1;
    if(Math.abs(dy)<1e-9){
      if(yA<0||yA>bodyHeight)return null;
    }else{
      const tAtTop=(0-yA)/dy;
      const tAtBottom=(bodyHeight-yA)/dy;
      const enter=Math.min(tAtTop,tAtBottom);
      const exit=Math.max(tAtTop,tAtBottom);
      tMin=Math.max(tMin,enter);
      tMax=Math.min(tMax,exit);
      if(tMin>tMax)return null;
    }
    tMin=Math.max(0,Math.min(1,tMin));
    tMax=Math.max(0,Math.min(1,tMax));
    if(tMin>tMax)return null;
    const y1=yA+(dy*tMin);
    const y2=yA+(dy*tMax);
    return {
      x1:width*tMin,
      y1:Math.max(0,Math.min(bodyHeight,y1)),
      x2:width*tMax,
      y2:Math.max(0,Math.min(bodyHeight,y2)),
    };
  };

  const visibleLayers=intervalTieInRenderableLayers(tieInPreviewState??tieInRenderState).filter(
    layer=>layer.enabled&&layer.upperA!==null&&layer.upperB!==null,
  );
  if(!visibleLayers.length)return null;
  return <svg aria-hidden="true" data-interval-tie-in-overlay={track.trackId} viewBox={`0 0 ${width} ${bodyHeight}`} preserveAspectRatio="none" style={{position:'absolute',left:0,top:bodyTop,width,height:bodyHeight,pointerEvents:'none',zIndex:130}}>
    {visibleLayers.map((layer,layerIndex)=>{
      const upperAY=mapY(layer.upperA as number,rangeA);
      const upperBY=mapY(layer.upperB as number,rangeB);
      const upperSegment=clipTieInSegment(upperAY,upperBY);
      const hasLower=layer.lowerA!==null&&layer.lowerB!==null;
      const lowerAY=hasLower?mapY(layer.lowerA as number,rangeA):upperAY;
      const lowerBY=hasLower?mapY(layer.lowerB as number,rangeB):upperBY;
      const lowerSegment=hasLower?clipTieInSegment(lowerAY,lowerBY):null;
      const dash=layer.line.style==='dash'?'8 5':layer.line.style==='dot'?'2 6':undefined;
      const safeLayerId=layer.layerId.replace(/[^a-zA-Z0-9_-]/g,'-');
      const patternId=`interval-tie-in-${track.trackId.replace(/[^a-zA-Z0-9_-]/g,'-')}-${safeLayerId}`;
      const tile=8*Math.max(.25,layer.fillPatternScale);
      const correlationUpperA=layer.upperA as number;
      const correlationUpperB=layer.upperB as number;
      const correlationLowerA=hasLower?layer.lowerA as number:correlationUpperA;
      const correlationLowerB=hasLower?layer.lowerB as number:correlationUpperB;
      const requestedUpperA=layer.fillDepthExtent==='correlation'?correlationUpperA:layer.fillUpperA??correlationUpperA;
      const requestedUpperB=layer.fillDepthExtent==='correlation'?correlationUpperB:layer.fillUpperB??correlationUpperB;
      const requestedLowerA=layer.fillDepthExtent==='correlation'?correlationLowerA:layer.fillLowerA??correlationLowerA;
      const requestedLowerB=layer.fillDepthExtent==='correlation'?correlationLowerB:layer.fillLowerB??correlationLowerB;
      const fillUpperA=Math.max(correlationUpperA,requestedUpperA);
      const fillUpperB=Math.max(correlationUpperB,requestedUpperB);
      const fillLowerA=Math.min(correlationLowerA,requestedLowerA);
      const fillLowerB=Math.min(correlationLowerB,requestedLowerB);
      const validFillBounds=hasLower&&fillLowerA>fillUpperA&&fillLowerB>fillUpperB;
      const fillUpperAY=mapY(fillUpperA,rangeA);
      const fillUpperBY=mapY(fillUpperB,rangeB);
      const fillLowerAY=mapY(fillLowerA,rangeA);
      const fillLowerBY=mapY(fillLowerB,rangeB);
      const fill=layer.fillAppearance==='pattern'&&layer.fillPattern!=='kr-lithology'&&layer.fillPattern!=='lithology-column'?`url(#${patternId})`:layer.fillAppearance==='pattern'&&layer.fillPattern==='kr-lithology'&&layer.fillLithologyId?`url(#${patternId}-kr)`:layer.fillAppearance==='raster'&&layer.fillRasterUrl?`url(#${patternId}-raster)`:layer.fillColor;
      const projectBFromA=(mdA:number)=>{
        const spanA=correlationLowerA-correlationUpperA;
        if(Math.abs(spanA)<1e-9)return correlationUpperB;
        return correlationUpperB+((mdA-correlationUpperA)/spanA)*(correlationLowerB-correlationUpperB);
      };
      const lithologyBands=validFillBounds&&layer.fillAppearance==='pattern'&&layer.fillPattern==='lithology-column'
        ?lithologyIntervals.filter(interval=>interval.baseMd>fillUpperA&&interval.topMd<fillLowerA).map(interval=>{
            const topA=Math.max(interval.topMd,fillUpperA);
            const lowerA=Math.min(interval.baseMd,fillLowerA);
            const topB=Math.max(fillUpperB,Math.min(fillLowerB,projectBFromA(topA)));
            const lowerB=Math.max(fillUpperB,Math.min(fillLowerB,projectBFromA(lowerA)));
            return {interval,topA,lowerA,topB,lowerB};
        }).filter(band=>band.lowerA>band.topA&&band.lowerB>band.topB)
        :[];
      return <g key={layer.layerId} data-interval-tie-in-layer={layer.layerId} data-interval-tie-in-layer-index={layerIndex}>
        <defs>
          {layer.fillAppearance==='pattern'&&layer.fillPattern!=='kr-lithology'&&layer.fillPattern!=='lithology-column'?<pattern id={patternId} width={tile} height={tile} patternUnits="userSpaceOnUse">{layer.fillPattern==='dots'?<circle cx={tile/2} cy={tile/2} r={Math.max(1,layer.fillPatternScale)} fill={layer.fillColor}/>:<path d={`M-${tile/4} ${tile/4}L${tile/4} -${tile/4}M0 ${tile}L${tile} 0M${tile*3/4} ${tile*5/4}L${tile*5/4} ${tile*3/4}`} stroke={layer.fillColor} strokeWidth={Math.max(1,layer.fillPatternScale)}/>}</pattern>:null}
          {layer.fillAppearance==='pattern'&&layer.fillPattern==='kr-lithology'&&layer.fillLithologyId?<pattern id={`${patternId}-kr`} width={32*Math.max(.25,layer.fillPatternScale)} height={32*Math.max(.25,layer.fillPatternScale)} patternUnits="userSpaceOnUse"><image href={lithologyPatternUrl(layer.fillLithologyId,layer.fillColor)} x="0" y="0" width={32*Math.max(.25,layer.fillPatternScale)} height={32*Math.max(.25,layer.fillPatternScale)} preserveAspectRatio="none"/></pattern>:null}
          {layer.fillAppearance==='raster'&&layer.fillRasterUrl?<pattern id={`${patternId}-raster`} width={width} height={bodyHeight} patternUnits="userSpaceOnUse"><image href={layer.fillRasterUrl} x="0" y="0" width={width} height={bodyHeight} preserveAspectRatio={layer.fillRasterFit==='stretch'?'none':'xMidYMid slice'}/></pattern>:null}
          {lithologyBands.map(({interval})=><pattern key={`${patternId}-${interval.intervalId}`} id={`${patternId}-${interval.intervalId}`} width={32*Math.max(.25,layer.fillPatternScale)} height={32*Math.max(.25,layer.fillPatternScale)} patternUnits="userSpaceOnUse"><image href={lithologyPatternUrl(interval.patternId)} x="0" y="0" width={32*Math.max(.25,layer.fillPatternScale)} height={32*Math.max(.25,layer.fillPatternScale)} preserveAspectRatio="none"/></pattern>)}
        </defs>
        {validFillBounds&&layer.fillEnabled&&layer.fillPattern!=='lithology-column'?<polygon points={`0,${fillUpperAY} ${width},${fillUpperBY} ${width},${fillLowerBY} 0,${fillLowerAY}`} fill={fill} fillOpacity={layer.fillOpacity} stroke="none"/>:null}
        {layer.fillEnabled?lithologyBands.map(({interval,topA,lowerA,topB,lowerB})=><polygon key={`${layer.layerId}-${interval.intervalId}`} points={`0,${mapY(topA,rangeA)} ${width},${mapY(topB,rangeB)} ${width},${mapY(lowerB,rangeB)} 0,${mapY(lowerA,rangeA)}`} fill={`url(#${patternId}-${interval.intervalId})`} fillOpacity={layer.fillOpacity} stroke="none" data-lithology-interval-id={interval.intervalId}/>):null}
        {layer.line.visible&&upperSegment?<line x1={upperSegment.x1} y1={upperSegment.y1} x2={upperSegment.x2} y2={upperSegment.y2} stroke={layer.line.color} strokeWidth={layer.line.width} strokeDasharray={dash} opacity={Math.max(0,Math.min(1,layer.line.opacity/100))} vectorEffect="non-scaling-stroke"/>:null}
        {hasLower&&layer.line.visible&&lowerSegment?<line x1={lowerSegment.x1} y1={lowerSegment.y1} x2={lowerSegment.x2} y2={lowerSegment.y2} stroke={layer.line.color} strokeWidth={layer.line.width} strokeDasharray={dash} opacity={Math.max(0,Math.min(1,layer.line.opacity/100))} vectorEffect="non-scaling-stroke"/>:null}
      </g>;
    })}
  </svg>;
}

export function TrackCanvas({ trackHeadersCollapsed, tracks, trackHeaderPresentationById = {}, viewportTieGroups = [], trackDepthRangesById = {}, trackContentDepthRangesById = {}, fullDepthRangesByWellUid = {}, fullDepthRange, onToggleCombinationTrack, trackHighlightedById = {}, selectedAssignmentIdByTrackId = {}, openCurveMenu, depthTicks, viewDepthRange, goToDepthMarker, goToSelectionTrackIds = [], displayGoToSelectionLine = true, goToDepthPickActive = false, onPickGoToDepth, renderBundlesByWellUid, liveFormationTopOverlayStylesByTrackId = {}, coreImageItems, coreImageItemsByWellUid, completionComponentsByWellUid, selectedCompletionComponentIds, selectedCompletionComponentIdsByWellUid, activeWellName, selectedCoreImageIds, selectedCoreImageIdsByWellUid, intervalZoomActive, intervalSelection, dragPanActive, onSelectTrack, onSelectCurve, onEditCurve, onReorderCurve, onMoveCurveToTrack, onOpenCurveMenu, onCloseCurveMenu, onRemoveCurveFromTrack, onStartIntervalSelection, onUpdateIntervalSelection, onCompleteIntervalSelection, onStartDragPan, onUpdateDragPan, onEndDragPan, onStartCurveTrackResize, resizingTrackId, managedSamplesByCurveId, managedSampleErrorsByCurveId, curveCatalogItems, }: {
    tracks: WellLogTrack[];
    trackHeaderPresentationById?: Record<string, { state: CombinationTrackState; selected: boolean; tied: boolean; title: string; ariaLabel: string }>;
    viewportTieGroups?: Array<{
        groupId: string;
        leaderTrackId: string;
        memberTrackIds: string[];
        viewport: DepthViewRange;
    }>;
    trackDepthRangesById?: Record<string, DepthViewRange>;
    trackContentDepthRangesById?: Record<string, DepthViewRange>;
    fullDepthRangesByWellUid?: Record<string, DepthViewRange>;
    fullDepthRange: DepthViewRange;
    onToggleCombinationTrack?: (trackId: string, additive?: boolean) => void;
    trackHighlightedById?: Record<string, boolean>;
    selectedAssignmentIdByTrackId?: Record<string, string | null>;
    openCurveMenu: {
        trackId: string;
        assignmentId: string;
    } | null;
    depthTicks: number[];
    viewDepthRange: DepthViewRange;
    goToDepthMarker: number | null;
    goToSelectionTrackIds?: string[];
    displayGoToSelectionLine?: boolean;
    goToDepthPickActive?: boolean;
    onPickGoToDepth?: (depth: number) => void;
    renderBundlesByWellUid: ReadonlyMap<string, WellOwnedTrackRenderBundle>;
    liveFormationTopOverlayStylesByTrackId?: Record<string, FormationTopOverlayStyle>;
    coreImageItems: CoreImageInventoryItem[];
    coreImageItemsByWellUid: Record<string, CoreImageInventoryItem[]>;
    completionComponentsByWellUid: Record<string, CompletionComponentRecord[]>;
    selectedCompletionComponentIds: Set<string>;
    selectedCompletionComponentIdsByWellUid: Record<string, Set<string>>;
    activeWellName: string;
    selectedCoreImageIds: Set<string>;
    selectedCoreImageIdsByWellUid: Record<string, Set<string>>;
    intervalZoomActive: boolean;
    intervalSelection: IntervalSelectionState | null;
    dragPanActive: boolean;
    onSelectTrack: (trackId: string, additive?: boolean) => void;
    onSelectCurve: (trackId: string, assignmentId: string) => void;
    onEditCurve: (trackId: string, assignmentId: string) => void;
    onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
    onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
    onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
    onCloseCurveMenu: () => void;
    onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
    onStartIntervalSelection: (depth: number, y: number, sourceTrackId: string | null) => void;
    onUpdateIntervalSelection: (depth: number, y: number) => void;
    onCompleteIntervalSelection: (depth: number, y: number) => void;
    onStartDragPan: (startY: number, sourceTrackId: string | null) => void;
    onUpdateDragPan: (currentY: number, canvasHeight: number) => void;
    onEndDragPan: () => void;
    onStartCurveTrackResize: (trackId: string, startX: number, startWidth: number) => void;
    resizingTrackId: string | null;
    managedSamplesByCurveId: ManagedCurveSamplesByCurveId;
    managedSampleErrorsByCurveId: Record<string, string>;
    curveCatalogItems: CurveCatalogItem[];
    trackHeadersCollapsed: boolean;
}) {
    const canvasRef = useRef<HTMLElement | null>(null);
    const suppressIntervalZoomClickRef = useRef(false);
    const [curveFillMdPick, setCurveFillMdPick] =
        useState<CurveFillMdPickCanvasState | null>(null);
    const [transientCurveFillDraft, setTransientCurveFillDraft] =
        useState<TransientCurveFillDraft | null>(null);

    useEffect(() => {
        const handlePreview = (event: Event) => {
            const detail = (
                event as CustomEvent<TransientCurveFillDraft>
            ).detail;
            if (!detail?.trackId) return;
            setTransientCurveFillDraft(detail);
        };
        const handleClear = (event: Event) => {
            const detail = (
                event as CustomEvent<{ trackId?: string }>
            ).detail;
            setTransientCurveFillDraft((current) => {
                if (
                    detail?.trackId
                    && current?.trackId !== detail.trackId
                ) return current;
                return null;
            });
        };

        window.addEventListener(
            CURVE_FILL_TRANSIENT_PREVIEW_EVENT,
            handlePreview as EventListener,
        );
        window.addEventListener(
            CURVE_FILL_TRANSIENT_PREVIEW_CLEAR_EVENT,
            handleClear as EventListener,
        );
        return () => {
            window.removeEventListener(
                CURVE_FILL_TRANSIENT_PREVIEW_EVENT,
                handlePreview as EventListener,
            );
            window.removeEventListener(
                CURVE_FILL_TRANSIENT_PREVIEW_CLEAR_EVENT,
                handleClear as EventListener,
            );
        };
    }, []);
    const orderedTracks = sortTracks(tracks);
    const [trackContentOrderByTrackId, setTrackContentOrderByTrackId] = useState<Record<string, TrackContentCategory[]>>({});
    const [openTrackContentMenuId, setOpenTrackContentMenuId] = useState<string | null>(null);
    const changeTrackContentOrder = (trackId: string, order: TrackContentCategory[]) => setTrackContentOrderByTrackId((current) => ({ ...current, [trackId]: normalizedTrackContentOrder(order) }));
    const sharedHeaderHeight = trackHeadersCollapsed ? TRACK_HEADER_COLLAPSED_HEIGHT_PX : sharedTrackHeaderHeightPx(orderedTracks);
    const {
        setContainerRef,
        trackBodyHeightPx: computedTrackBodyHeightPx,
    } = useTrackBodyGeometry({
        headerHeightPx: sharedHeaderHeight,
        fallbackBodyHeightPx: TRACK_BODY_HEIGHT_PX,
        minBodyHeightPx: TRACK_BODY_MIN_HEIGHT_PX,
        maxBodyHeightPx: TRACK_BODY_MAX_HEIGHT_PX,
        footerClearancePx: TRACK_FOOTER_CLEARANCE_PX,
        stripPaddingPx: TRACK_STRIP_PADDING_PX,
    });

    /*
     * The geometry hook provides an initial/fallback body height, but CSS flex
     * layout may produce a different actual DOM height.
     *
     * All MD -> screen Y rendering must use the ACTUAL rendered body height.
     */
    const [trackBodyHeightPx, setTrackBodyHeightPx] = useState(
        computedTrackBodyHeightPx,
    );

    type DepthRangeLocatorResolved = {
        topY: number;
        baseY: number;
        topVisible: boolean;
        baseVisible: boolean;
        side: 'left' | 'right';
        presentation: 'edge_arrows' | 'wall_bar' | 'data_bar';
    };
    type DepthRangeLocatorOverlayColumn = {
        targetTrack: WellLogTrack;
        widthPx: number;
        locator: DepthRangeLocatorResolved | null;
    };
    const locatorOverlayColumns: DepthRangeLocatorOverlayColumn[] = orderedTracks.map((targetTrack, targetIndex) => {
        const config = targetTrack.depthRangeLocator;
        const widthPx = targetTrack.trackType === 'curve'
            || targetTrack.trackType === 'core'
            || targetTrack.trackType === 'interval'
            || targetTrack.trackType === 'completion'
            ? clampCurveTrackWidth(targetTrack.widthPx)
            : targetTrack.widthPx;
        if (!config?.enabled || !config.sourceTrackId) {
            return { targetTrack, widthPx, locator: null };
        }
        const sourceIndex = orderedTracks.findIndex((candidate) => candidate.trackId === config.sourceTrackId);
        const sourceTrack = sourceIndex >= 0 ? orderedTracks[sourceIndex] : null;
        if (!sourceTrack || sourceTrack.managedWellUid !== targetTrack.managedWellUid) {
            return { targetTrack, widthPx, locator: null };
        }
        const sourceViewport = trackDepthRangesById[sourceTrack.trackId] ?? viewDepthRange;
        const sourceContent = trackContentDepthRangesById[sourceTrack.trackId] ?? fullDepthRange;
        const targetViewport = trackDepthRangesById[targetTrack.trackId] ?? viewDepthRange;
        const contentInsideViewport = sourceContent.min >= sourceViewport.min - 1e-9
            && sourceContent.max <= sourceViewport.max + 1e-9;
        const sourceRange = config.mode === 'content_extent'
            ? sourceContent
            : config.mode === 'viewport_extent'
                ? sourceViewport
                : contentInsideViewport ? sourceContent : sourceViewport;
        const side: 'left' | 'right' = config.side === 'left' || config.side === 'right'
            ? config.side
            : sourceIndex > targetIndex ? 'right' : 'left';
        const topVisible = sourceRange.min >= targetViewport.min && sourceRange.min <= targetViewport.max;
        const baseVisible = sourceRange.max >= targetViewport.min && sourceRange.max <= targetViewport.max;
        const clippedMin = Math.max(sourceRange.min, targetViewport.min);
        const clippedMax = Math.min(sourceRange.max, targetViewport.max);
        const hasVisibleSpan = clippedMax >= clippedMin;
        return {
            targetTrack,
            widthPx,
            locator: hasVisibleSpan ? {
                topY: depthToY(clippedMin, targetViewport, trackBodyHeightPx),
                baseY: depthToY(clippedMax, targetViewport, trackBodyHeightPx),
                topVisible,
                baseVisible,
                side,
                presentation: config.presentation,
            } : null,
        };
    });

    const macroCoreImageColumns = orderedTracks.map((track) => {
        const widthPx = track.trackType === 'curve'
            || track.trackType === 'core'
            || track.trackType === 'interval'
            || track.trackType === 'completion'
            ? clampCurveTrackWidth(track.widthPx)
            : track.widthPx;
        const config = track.macroCoreImage;
        const trackRange = trackDepthRangesById[track.trackId] ?? viewDepthRange;
        if (
            !config?.enabled
            || !Number.isFinite(config.topMd)
            || !Number.isFinite(config.baseMd)
            || config.baseMd <= config.topMd
        ) {
            return { track, widthPx, marker: null };
        }
        const clippedTop = Math.max(config.topMd, trackRange.min);
        const clippedBase = Math.min(config.baseMd, trackRange.max);
        if (clippedBase <= clippedTop) return { track, widthPx, marker: null };
        const cylinderWidthPx = 10;
        const edgeInset = 10;
        const anchorX = config.placement === 'left'
            ? edgeInset + cylinderWidthPx / 2
            : config.placement === 'right'
                ? widthPx - edgeInset - cylinderWidthPx / 2
                : widthPx / 2;
        const x = clampValue(
            anchorX + config.horizontalOffsetPx,
            cylinderWidthPx / 2 + 2,
            widthPx - cylinderWidthPx / 2 - 2,
        );
        return {
            track,
            widthPx,
            marker: {
                x,
                topY: depthToY(clippedTop, trackRange, trackBodyHeightPx),
                baseY: depthToY(clippedBase, trackRange, trackBodyHeightPx),
                cylinderWidthPx,
            },
        };
    });

    const sanitizeTrackTextBoxHtml = (value: string): string => {
        const template = document.createElement('template');
        template.innerHTML = value.slice(0, 6000);
        const allowed = new Set(['DIV', 'P', 'BR', 'B', 'STRONG', 'I', 'EM', 'U']);
        const cleanNode = (node: Node): void => {
            [...node.childNodes].forEach((child) => {
                if (child.nodeType === Node.TEXT_NODE) return;
                if (!(child instanceof HTMLElement)) {
                    child.remove();
                    return;
                }
                cleanNode(child);
                if (!allowed.has(child.tagName)) {
                    child.replaceWith(document.createTextNode(child.textContent ?? ''));
                    return;
                }
                [...child.attributes].forEach((attribute) => child.removeAttribute(attribute.name));
            });
        };
        cleanNode(template.content);
        return template.innerHTML;
    };

    const textOverlayColumns = orderedTracks.map((track) => {
        const widthPx = track.trackType === 'curve'
            || track.trackType === 'core'
            || track.trackType === 'interval'
            || track.trackType === 'completion'
            ? clampCurveTrackWidth(track.widthPx)
            : track.widthPx;
        const trackRange = trackDepthRangesById[track.trackId] ?? viewDepthRange;
        const overlays = (track.textOverlays ?? [])
            .filter((item) => Number.isFinite(item.md) && item.md >= trackRange.min && item.md <= trackRange.max)
            .map((item) => {
                const boxWidth = clampValue(
                    widthPx * (item.widthPercent / 100),
                    Math.min(48, widthPx),
                    widthPx,
                );
                const baseX = item.horizontalAnchor === 'left'
                    ? 8
                    : item.horizontalAnchor === 'right'
                        ? widthPx - 8
                        : widthPx / 2;
                const horizontalNudge = (item.horizontalOffset / 100) * Math.min(48, widthPx * 0.35);

                const minX = item.horizontalAnchor === 'left'
                    ? 4
                    : item.horizontalAnchor === 'right'
                        ? boxWidth + 4
                        : boxWidth / 2 + 4;
                const maxX = item.horizontalAnchor === 'left'
                    ? Math.max(4, widthPx - boxWidth - 4)
                    : item.horizontalAnchor === 'right'
                        ? Math.max(boxWidth + 4, widthPx - 4)
                        : Math.max(boxWidth / 2 + 4, widthPx - boxWidth / 2 - 4);

                const x = clampValue(baseX + horizontalNudge, minX, maxX);
                const y = depthToY(item.md, trackRange, trackBodyHeightPx) + (item.verticalOffset / 100) * 40;
                const translateX = item.horizontalAnchor === 'left'
                    ? '0'
                    : item.horizontalAnchor === 'right'
                        ? '-100%'
                        : '-50%';
                return {
                    item,
                    x,
                    y,
                    boxWidth,
                    translateX,
                    safeHtml: sanitizeTrackTextBoxHtml(item.contentHtml),
                };
            });
        return { track, widthPx, overlays };
    });

    const canvasRectFromCanvas = () => canvasRef.current?.getBoundingClientRect() ?? null;
    const bodyRectFromCanvas = () => {
        return canvasRef.current?.querySelector('.wlv-track-body')?.getBoundingClientRect() ?? null;
    };


    /*
     * Keep the MD coordinate system synchronized with the real DOM geometry.
     *
     * This prevents fine zoom from rendering into only the upper fraction of
     * a flex-expanded track body.
     */
    useEffect(() => {
        const canvas = canvasRef.current;

        if (!canvas) {
            setTrackBodyHeightPx(computedTrackBodyHeightPx);
            return undefined;
        }

        const body = canvas.querySelector<HTMLElement>(
            '.wlv-track-body',
        );

        const measureActualBodyHeight = () => {
            const measured =
                body?.getBoundingClientRect().height ?? 0;

            const nextHeight =
                Number.isFinite(measured) && measured > 0
                    ? measured
                    : computedTrackBodyHeightPx;

            setTrackBodyHeightPx((current) =>
                Math.abs(current - nextHeight) >= 0.5
                    ? nextHeight
                    : current
            );
        };

        measureActualBodyHeight();

        const resizeObserver = new ResizeObserver(
            measureActualBodyHeight,
        );

        resizeObserver.observe(canvas);

        if (body) {
            resizeObserver.observe(body);
        }

        window.addEventListener(
            'resize',
            measureActualBodyHeight,
        );

        return () => {
            resizeObserver.disconnect();
            window.removeEventListener(
                'resize',
                measureActualBodyHeight,
            );
        };
    }, [
        computedTrackBodyHeightPx,
        sharedHeaderHeight,
    ]);
    const stripRectFromCanvas = () => {
        return canvasRef.current?.querySelector('.wlv-track-strip')?.getBoundingClientRect() ?? null;
    };
    const sharedBodyTopOffset = () => {
        const canvasRect = canvasRectFromCanvas();
        const bodyRect = bodyRectFromCanvas();
        if (canvasRect && bodyRect)
            return bodyRect.top - canvasRect.top;
        return TRACK_STRIP_PADDING_PX + sharedHeaderHeight;
    };
    const stripBodyTopOffset = () => {
        const stripRect = stripRectFromCanvas();
        const bodyRect = bodyRectFromCanvas();
        if (stripRect && bodyRect)
            return bodyRect.top - stripRect.top;
        return sharedHeaderHeight;
    };
    const pointFromClientY = (clientY: number) => {
        const rect = bodyRectFromCanvas() ?? canvasRectFromCanvas();
        const height = rect?.height ?? trackBodyHeightPx;
        const top = rect?.top ?? 0;
        const y = clampValue(clientY - top, 0, height);
        const depth = yToDepth(y, viewDepthRange, height);
        return { depth, y, height };
    };
    const pointFromEvent = (event: ReactMouseEvent<HTMLElement>) => {
        /*
         * Resolve pointer MD from the actual track body that received the click.
         *
         * The previous implementation always used the first .wlv-track-body
         * in the canvas.  That is only safe when every rendered track body has
         * exactly the same DOM top and height.  Small per-track geometry
         * differences then become a depth offset during Go To MD picking.
         *
         * The clicked body's own rectangle is authoritative for click-based
         * depth picking.  Document-level drag handling continues to use the
         * shared pointFromClientY() fallback.
         */
        const target = event.target;
        const clickedBody =
            target instanceof Element
                ? target.closest('.wlv-track-body')
                : null;

        if (clickedBody instanceof HTMLElement) {
            const rect = clickedBody.getBoundingClientRect();
            const height =
                Number.isFinite(rect.height) && rect.height > 0
                    ? rect.height
                    : trackBodyHeightPx;
            const y = clampValue(
                event.clientY - rect.top,
                0,
                height,
            );
            const trackRoot = clickedBody.closest('.wlv-track');
            const placementSelector = trackRoot?.querySelector<HTMLElement>('[data-combination-track-id]');
            const clickedTrackId = placementSelector?.dataset.combinationTrackId;
            const clickedViewDepthRange = clickedTrackId
                ? (trackDepthRangesById[clickedTrackId] ?? viewDepthRange)
                : viewDepthRange;
            const depth = yToDepth(
                y,
                clickedViewDepthRange,
                height,
            );
            return { depth, y, height, trackId: clickedTrackId };
        }

        return { ...pointFromClientY(event.clientY), trackId: undefined };
    };
    useEffect(() => {
        const handleRequest = (event: Event) => {
            const detail = (
                event as CustomEvent<CurveFillMdPickCanvasState>
            ).detail;
            if (!detail?.token || !detail.field)
                return;
            setCurveFillMdPick(detail);
        };
        const handleCancel = (event: Event) => {
            const detail = (
                event as CustomEvent<{ token?: string }>
            ).detail;
            setCurveFillMdPick((current) => {
                if (!current)
                    return null;
                if (detail?.token && detail.token !== current.token)
                    return current;
                return null;
            });
        };
        window.addEventListener(
            CURVE_FILL_MD_PICK_REQUEST_EVENT,
            handleRequest as EventListener,
        );
        window.addEventListener(
            CURVE_FILL_MD_PICK_CANCEL_EVENT,
            handleCancel as EventListener,
        );
        return () => {
            window.removeEventListener(
                CURVE_FILL_MD_PICK_REQUEST_EVENT,
                handleRequest as EventListener,
            );
            window.removeEventListener(
                CURVE_FILL_MD_PICK_CANCEL_EVENT,
                handleCancel as EventListener,
            );
        };
    }, []);
    useEffect(()=>{
        if(!curveFillMdPick)return;
        if(goToDepthPickActive||intervalZoomActive){
            window.dispatchEvent(new CustomEvent(
                CURVE_FILL_MD_PICK_CANCEL_EVENT,
                {detail:{token:curveFillMdPick.token}},
            ));
            setCurveFillMdPick(null);
        }
    },[curveFillMdPick,goToDepthPickActive,intervalZoomActive]);
    const shouldStartDragPan = (event: ReactMouseEvent<HTMLElement>) => {
        if (intervalZoomActive || event.shiftKey || event.button !== 0)
            return false;
        const target = event.target;
        if (!(target instanceof Element))
            return false;
        return Boolean(target.closest('.wlv-track-body'));
    };
    useEffect(() => {
        if (!dragPanActive)
            return undefined;
        const handleDocumentMouseMove = (event: MouseEvent) => {
            event.preventDefault();
            const point = pointFromClientY(event.clientY);
            onUpdateDragPan(point.y, point.height);
        };
        const handleDocumentMouseUp = (event: MouseEvent) => {
            event.preventDefault();
            onEndDragPan();
        };
        document.addEventListener('mousemove', handleDocumentMouseMove);
        document.addEventListener('mouseup', handleDocumentMouseUp);
        return () => {
            document.removeEventListener('mousemove', handleDocumentMouseMove);
            document.removeEventListener('mouseup', handleDocumentMouseUp);
        };
    }, [dragPanActive, onEndDragPan, onUpdateDragPan, viewDepthRange]);
    const intervalBand = intervalSelection
        ? {
            top: Math.min(intervalSelection.startY, intervalSelection.currentY),
            height: Math.max(2, Math.abs(intervalSelection.currentY - intervalSelection.startY)),
            startDepth: Math.min(intervalSelection.startDepth, intervalSelection.currentDepth),
            endDepth: Math.max(intervalSelection.startDepth, intervalSelection.currentDepth),
        }
        : null;
    const bodyTopOffset = sharedBodyTopOffset();
    const intervalBandTopOffset = stripBodyTopOffset();
    // WDV_SELECTION_LINE_PER_TRACK_SCOPE_V1_0_2
    // The same MD can map to different Y coordinates on independently viewed
    // tracks. Scope comes from the consolidated selected/Tie viewport resolver.
    const goToSelectionTrackIdSet = new Set(goToSelectionTrackIds);
    const sharedDepthGridLines = depthTicks.map((depth) => ({
        depth,
        y: bodyTopOffset + depthToY(depth, viewDepthRange, trackBodyHeightPx),
    }));

    /*
     * WDV_TIEIN_COMPLETION_PASS_THROUGH_V1_0_1
     *
     * Completion tracks are zero-offset pass-through tracks for Tie-In.
     * Preserve immediate topology, but resolve geological authority outward
     * to the nearest same-well geological/log track.
     */
    const resolveCompletionPassThroughHostTrack = (
      track: WellLogTrack | null,
      outwardDirection?: 'left' | 'right',
    ): WellLogTrack | null => {
      if (!track || track.trackType !== 'completion' || !track.managedWellUid) return track;

      const completionWellUid = track.managedWellUid;
      const index = orderedTracks.findIndex((candidate) => candidate.trackId === track.trackId);
      if (index < 0) return track;

      const sameWellGeological = (candidate: WellLogTrack | undefined): boolean =>
        Boolean(
          candidate
          && candidate.managedWellUid === completionWellUid
          && candidate.trackType !== 'completion'
          && candidate.trackType !== 'interval',
        );

      const scan = (step: -1 | 1): WellLogTrack | null => {
        let fallback: WellLogTrack | null = null;
        for (let cursor = index + step; cursor >= 0 && cursor < orderedTracks.length; cursor += step) {
          const candidate = orderedTracks[cursor];
          if (!candidate) continue;
          if (!sameWellGeological(candidate)) {
            if (candidate?.managedWellUid && candidate.managedWellUid !== completionWellUid) break;
            continue;
          }
          if (candidate.trackType === 'curve') return candidate;
          fallback ??= candidate;
        }
        return fallback;
      };

      if (outwardDirection === 'left') return scan(-1) ?? scan(1) ?? track;
      if (outwardDirection === 'right') return scan(1) ?? scan(-1) ?? track;

      const left = scan(-1);
      const right = scan(1);
      if (!left) return right ?? track;
      if (!right) return left;

      const leftDistance = Math.abs(index - orderedTracks.findIndex((candidate) => candidate.trackId === left.trackId));
      const rightDistance = Math.abs(index - orderedTracks.findIndex((candidate) => candidate.trackId === right.trackId));
      return leftDistance <= rightDistance ? left : right;
    };

    const buildFormationTopLayers = (track: WellLogTrack, trackViewDepthRange: DepthViewRange): { topsFillLayer: ReactNode; formationTopsLayer: ReactNode } => {
          let renderBundle = renderBundleForTrack(track, renderBundlesByWellUid);
          if (track.trackType === 'core' && !track.managedWellUid) {
            // Legacy Core tracks can render the active Core inventory without an
            // owner UID. Resolve the overlay bundle from that exact inventory too,
            // so imagery and overlays cannot diverge between T12/T14-style tracks.
            const activeProductIds = new Set(coreImageItems.map((item) => item.productId));
            const ownerEntry = Object.entries(coreImageItemsByWellUid).find(([, items]) =>
              items.some((item) => activeProductIds.has(item.productId)),
            );
            if (ownerEntry) {
              renderBundle = renderBundlesByWellUid.get(ownerEntry[0]) ?? renderBundle;
            }
          }
          const formationTops = renderBundle.formationTops;
          const allFormationTops = renderBundle.allFormationTops;
          const lithologyIntervals = normalizeLithologyIntervalsForRendering(
            renderBundle.lithologyIntervals,
          );
          const loadedLithologyIntervals = normalizeLithologyIntervalsForRendering(
            renderBundle.loadedLithologyIntervals,
          );
          const persistedTrackOverlayStyle = renderBundle.formationTopOverlayStylesByTrackId[track.trackId] ?? {};
          const liveTrackOverlayStyle = liveFormationTopOverlayStylesByTrackId[track.trackId] ?? {};
          const completionPassThroughHost =
            track.trackType === 'completion'
              ? resolveCompletionPassThroughHostTrack(track)
              : null;
          const completionHostPersistedStyle = completionPassThroughHost
            ? renderBundle.formationTopOverlayStylesByTrackId[completionPassThroughHost.trackId] ?? {}
            : {};
          const completionHostLiveStyle = completionPassThroughHost
            ? liveFormationTopOverlayStylesByTrackId[completionPassThroughHost.trackId] ?? {}
            : {};
          const completionHostOverlayStyle: FormationTopOverlayStyle = {
            ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
            ...completionHostPersistedStyle,
            ...completionHostLiveStyle,
          };
          const ownOverlayStyle: FormationTopOverlayStyle = {
            ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
            ...persistedTrackOverlayStyle,
            ...liveTrackOverlayStyle,
          };
          const ownHasExplicitFill =
            ownOverlayStyle.fillZones.length > 0
            || ownOverlayStyle.fillMode !== 'off';
          const overlayStyle: FormationTopOverlayStyle =
            track.trackType === 'completion'
            && completionPassThroughHost
            && !ownHasExplicitFill
              ? {
                  ...ownOverlayStyle,
                  fillMode: completionHostOverlayStyle.fillMode,
                  fillTopMarkerId: completionHostOverlayStyle.fillTopMarkerId,
                  fillBaseMarkerId: completionHostOverlayStyle.fillBaseMarkerId,
                  fillSource: completionHostOverlayStyle.fillSource,
                  fillColor: completionHostOverlayStyle.fillColor,
                  fillOpacity: completionHostOverlayStyle.fillOpacity,
                  fillPattern: completionHostOverlayStyle.fillPattern,
                  fillRasterUrl: completionHostOverlayStyle.fillRasterUrl,
                  fillRasterFit: completionHostOverlayStyle.fillRasterFit,
                  fillConstraint: completionHostOverlayStyle.fillConstraint,
                  fillCurveAId: completionHostOverlayStyle.fillCurveAId,
                  fillCurveBId: completionHostOverlayStyle.fillCurveBId,
                  fillZones: completionHostOverlayStyle.fillZones,
                }
              : ownOverlayStyle;
          const visibleMarkers = formationTops
            .filter((marker) => marker.md >= trackViewDepthRange.min && marker.md <= trackViewDepthRange.max)
            .sort((left, right) => left.md - right.md);
          const trackWidth = track.widthPx;
          const overlayLane = resolveCoreOverlayLaneMetrics(track, overlayStyle, trackWidth);
          const coreObjectLane = resolveCoreObjectLaneMetrics(trackWidth, trackViewDepthRange, trackBodyHeightPx);
          const fillZones = legacyFormationTopFillZone(overlayStyle);
          // Fill-zone boundaries may reference any loaded Formation Top, even when
          // the line/label overlay is filtered to a smaller selected-top set.
          const renderedFillZones = fillZones.map((zone, zoneIndex) => {
            if (!zone.enabled) return null;

            const depthExtent = zone.depthExtent ?? 'top_boundaries';
            let requestedTopDepth: number;
            let requestedBaseDepth: number;

            if (depthExtent === 'entire_track') {
              requestedTopDepth = trackViewDepthRange.min;
              requestedBaseDepth = trackViewDepthRange.max;
            } else if (depthExtent === 'specified_interval') {
              if (
                !Number.isFinite(zone.intervalFromMd)
                || !Number.isFinite(zone.intervalToMd)
                || (zone.intervalFromMd as number) >= (zone.intervalToMd as number)
              ) return null;
              requestedTopDepth = zone.intervalFromMd as number;
              requestedBaseDepth = zone.intervalToMd as number;
            } else {
              if (!zone.topMarkerId || !zone.baseMarkerId) return null;
              const topMarker = allFormationTops.find(
                (marker) => marker.markerId === zone.topMarkerId,
              ) ?? null;
              const baseMarker = allFormationTops.find(
                (marker) => marker.markerId === zone.baseMarkerId,
              ) ?? null;
              if (!topMarker || !baseMarker || topMarker.md >= baseMarker.md)
                return null;
              requestedTopDepth = topMarker.md;
              requestedBaseDepth = baseMarker.md;
            }

            const intervalTopDepth = Math.max(
              requestedTopDepth,
              trackViewDepthRange.min,
            );
            const intervalBaseDepth = Math.min(
              requestedBaseDepth,
              trackViewDepthRange.max,
            );
            if (
              intervalTopDepth >= intervalBaseDepth
              || intervalBaseDepth < trackViewDepthRange.min
              || intervalTopDepth > trackViewDepthRange.max
            )
              return null;

            const intervalTopY = depthToY(intervalTopDepth, trackViewDepthRange, trackBodyHeightPx);
            const intervalBaseY = depthToY(intervalBaseDepth, trackViewDepthRange, trackBodyHeightPx);
            const patternId = `formation-fill-${track.trackId}-${zone.zoneId || zoneIndex}`;
            let constrainedPath = '';

            if (
              zone.constraint !== 'track'
              && track.trackType === 'curve'
            ) {
              const curveA = resolveOverlayCurveAssignment(track, zone.curveAId);
              if (curveA) {
                const orderedAssignments = orderedCurves(track);
                const lattice = resolveTrackLattice(track, curveCatalogItems);
                const curveAItem = resolveCurveAssignmentCatalogItem(curveCatalogItems, curveA);
                if (curveAItem) {
                  const curveAIndex = Math.max(
                    0,
                    orderedAssignments.findIndex(
                      (candidate) => candidate.assignmentId === curveA.assignmentId,
                    ),
                  );
                  const curveAPoints = curveRenderPoints(
                    curveAItem,
                    curveA,
                    curveAIndex,
                    trackViewDepthRange,
                    lattice.lattice,
                    trackWidth,
                    trackBodyHeightPx,
                    managedSamplesByCurveId,
                  );
                  if (zone.constraint === 'left-of-curve') {
                    constrainedPath = polygonToAnchor(curveAPoints, 0);
                  } else if (zone.constraint === 'right-of-curve') {
                    constrainedPath = polygonToAnchor(curveAPoints, trackWidth);
                  } else if (
                    zone.constraint === 'between-curves'
                    || zone.constraint === 'left-of-leftmost-curves'
                    || zone.constraint === 'right-of-rightmost-curves'
                  ) {
                    const curveB = resolveOverlayCurveAssignment(track, zone.curveBId);
                    if (curveB && curveB.assignmentId !== curveA.assignmentId) {
                      const curveBItem = resolveCurveAssignmentCatalogItem(
                        curveCatalogItems,
                        curveB,
                      );
                      if (curveBItem) {
                        const curveBIndex = Math.max(
                          0,
                          orderedAssignments.findIndex(
                            (candidate) => candidate.assignmentId === curveB.assignmentId,
                          ),
                        );
                        const curveBPoints = curveRenderPoints(
                          curveBItem,
                          curveB,
                          curveBIndex,
                          trackViewDepthRange,
                          lattice.lattice,
                          trackWidth,
                          trackBodyHeightPx,
                          managedSamplesByCurveId,
                        );
                        if (zone.constraint === 'between-curves') {
                          constrainedPath = polygonBetweenCurves(curveAPoints, curveBPoints);
                        } else if (zone.constraint === 'left-of-leftmost-curves') {
                          constrainedPath = polygonToExtremeCurveAnchor(
                            curveAPoints,
                            curveBPoints,
                            0,
                            'leftmost',
                          );
                        } else {
                          constrainedPath = polygonToExtremeCurveAnchor(
                            curveAPoints,
                            curveBPoints,
                            trackWidth,
                            'rightmost',
                          );
                        }
                      }
                    }
                  }
                }
              }
            }

            const useSvgConstraint =
              zone.constraint !== 'track' && Boolean(constrainedPath);
            const zoneLane = track.trackType === 'core' && zone.coreObjectOnly
              ? coreObjectLane
              : overlayLane;
            const zoneLithologyIntervals =
              zone.source === 'lithology-column'
                ? loadedLithologyIntervals.filter(
                    (interval) =>
                      interval.baseMd > intervalTopDepth
                      && interval.topMd < intervalBaseDepth,
                  )
                : [];
            const intervalTrackIndex = track.trackType === 'interval'
              ? tracks.findIndex((candidate) => candidate.trackId === track.trackId)
              : -1;
            const tieInTrackA = intervalTrackIndex > 0
              ? tracks[intervalTrackIndex - 1]
              : null;
            const tieInTrackB = intervalTrackIndex >= 0 && intervalTrackIndex < tracks.length - 1
              ? tracks[intervalTrackIndex + 1]
              : null;

            const tieInGeologicalTrackA = tieInTrackA?.trackType === 'completion'
              ? resolveCompletionPassThroughHostTrack(tieInTrackA, 'left')
              : tieInTrackA;
            const tieInGeologicalTrackB = tieInTrackB?.trackType === 'completion'
              ? resolveCompletionPassThroughHostTrack(tieInTrackB, 'right')
              : tieInTrackB;

            const tieInRangeA = tieInTrackA
              ? (
                  tieInGeologicalTrackA
                    ? trackDepthRangesById[tieInGeologicalTrackA.trackId]
                    : undefined
                )
                ?? trackDepthRangesById[tieInTrackA.trackId]
                ?? trackViewDepthRange
              : trackViewDepthRange;
            const tieInRangeB = tieInTrackB
              ? (
                  tieInGeologicalTrackB
                    ? trackDepthRangesById[tieInGeologicalTrackB.trackId]
                    : undefined
                )
                ?? trackDepthRangesById[tieInTrackB.trackId]
                ?? trackViewDepthRange
              : trackViewDepthRange;
            const tieInLithologyIntervalsA = tieInGeologicalTrackA
              ? normalizeLithologyIntervalsForRendering(
                  renderBundleForTrack(tieInGeologicalTrackA, renderBundlesByWellUid).loadedLithologyIntervals,
                )
              : [];
            const tieInLithologyIntervalsB = tieInGeologicalTrackB
              ? normalizeLithologyIntervalsForRendering(
                  renderBundleForTrack(tieInGeologicalTrackB, renderBundlesByWellUid).loadedLithologyIntervals,
                )
              : [];
            const useTieInWarp = Boolean(
              track.trackType === 'interval'
              && zone.constraint === 'track'
              && zone.honorTieInGeometry
              && tieInTrackA
              && tieInTrackB,
            );
            const tieInAnchorCandidates = useTieInWarp
              ? intervalTieInRenderableLayers(loadIntervalTieInLayerState(track.trackId))
                  .filter((layer) => layer.enabled)
                  .flatMap((layer) => {
                    const anchors: Array<{ mdA: number; mdB: number }> = [];
                    if (layer.upperA !== null && layer.upperB !== null) {
                      anchors.push({ mdA: layer.upperA, mdB: layer.upperB });
                    }
                    if (layer.lowerA !== null && layer.lowerB !== null) {
                      anchors.push({ mdA: layer.lowerA, mdB: layer.lowerB });
                    }
                    return anchors;
                  })
                  .filter((anchor) => Number.isFinite(anchor.mdA) && Number.isFinite(anchor.mdB))
                  .sort((left, right) => left.mdA - right.mdA)
              : [];
            const tieInAnchors = tieInAnchorCandidates.reduce<Array<{ mdA: number; mdB: number }>>(
              (anchors, candidate) => {
                const previous = anchors[anchors.length - 1];
                if (previous && Math.abs(previous.mdA - candidate.mdA) < 1e-9) {
                  // Multiple Tie-In layers may reuse the same left-well anchor.
                  // Keep the last saved mapping as the active presentation anchor.
                  anchors[anchors.length - 1] = candidate;
                } else {
                  anchors.push(candidate);
                }
                return anchors;
              },
              [],
            );
            const tieInBoundaryPairs: TieInLithologyBoundaryPair[] = (() => {
              if (!useTieInWarp || tieInAnchors.length < 1) return [];
              const boundariesA = uniqueLithologyBoundaryDepths(tieInLithologyIntervalsA);
              const boundariesB = uniqueLithologyBoundaryDepths(tieInLithologyIntervalsB);
              if (!boundariesA.length || !boundariesB.length) return [];

              // Formation/Tie-In anchors constrain correlation where they exist, but they are not
              // clipping limits for the lithology column. Extend the correlation frame to the
              // measured lithology extents on both wells so intervals above the first anchor and
              // below the last anchor remain renderable. The synthetic outer anchors are measured
              // lithology boundaries on both sides; no equal-MD assumption is made.
              const correlationAnchors = [...tieInAnchors];
              const firstAnchor = correlationAnchors[0];
              const lastAnchor = correlationAnchors[correlationAnchors.length - 1];
              const minBoundaryA = boundariesA[0];
              const minBoundaryB = boundariesB[0];
              const maxBoundaryA = boundariesA[boundariesA.length - 1];
              const maxBoundaryB = boundariesB[boundariesB.length - 1];

              if (minBoundaryA < firstAnchor.mdA - 1e-6 || minBoundaryB < firstAnchor.mdB - 1e-6) {
                correlationAnchors.unshift({ mdA: Math.min(minBoundaryA, firstAnchor.mdA), mdB: Math.min(minBoundaryB, firstAnchor.mdB) });
              }
              if (maxBoundaryA > lastAnchor.mdA + 1e-6 || maxBoundaryB > lastAnchor.mdB + 1e-6) {
                correlationAnchors.push({ mdA: Math.max(maxBoundaryA, lastAnchor.mdA), mdB: Math.max(maxBoundaryB, lastAnchor.mdB) });
              }

              const pairs: TieInLithologyBoundaryPair[] = [];

              /*
               * Saved Tie-In anchors are authoritative correlation boundaries.
               * They must participate in the polygon boundary lattice even when
               * one adjacent well has no measured lithology boundary at that MD.
               * Without these explicit pairs, upper Ekofisk/Tor correlation
               * segments can disappear when the opposite well's lithology starts
               * deeper (for example at Hod).
               */
              for (const anchor of correlationAnchors) {
                const measuredA = boundariesA.some((depth) => Math.abs(depth - anchor.mdA) < 1e-5);
                const measuredB = boundariesB.some((depth) => Math.abs(depth - anchor.mdB) < 1e-5);
                pairs.push({
                  mdA: anchor.mdA,
                  mdB: anchor.mdB,
                  authorityA: measuredA ? 'measured' : 'derived-tie-in',
                  authorityB: measuredB ? 'measured' : 'derived-tie-in',
                });
              }

              for (let anchorIndex = 0; anchorIndex < correlationAnchors.length - 1; anchorIndex += 1) {
                const upper = correlationAnchors[anchorIndex];
                const lower = correlationAnchors[anchorIndex + 1];
                if (!(lower.mdA > upper.mdA) || !(lower.mdB > upper.mdB)) continue;

                const spanA = lower.mdA - upper.mdA;
                const spanB = lower.mdB - upper.mdB;
                const projectB = (mdA: number) => upper.mdB + ((mdA - upper.mdA) / spanA) * spanB;
                const projectA = (mdB: number) => upper.mdA + ((mdB - upper.mdB) / spanB) * spanA;
                const localA = boundariesA.filter((depth) => depth >= upper.mdA - 1e-6 && depth <= lower.mdA + 1e-6);
                const localB = boundariesB.filter((depth) => depth >= upper.mdB - 1e-6 && depth <= lower.mdB + 1e-6);
                const matchedBByA = new Map<number, number>();
                const matchedBIndices = new Set<number>();
                if (localA.length && localB.length) {
                  const skipPenalty = 0.25;
                  const dp = Array.from({ length: localA.length + 1 }, () => Array<number>(localB.length + 1).fill(0));
                  const choice = Array.from({ length: localA.length }, () => Array<'match' | 'skipA' | 'skipB'>(localB.length).fill('match'));
                  for (let i = localA.length; i >= 0; i -= 1) {
                    for (let j = localB.length; j >= 0; j -= 1) {
                      if (i === localA.length && j === localB.length) continue;
                      if (i === localA.length) {
                        dp[i][j] = skipPenalty + dp[i][j + 1];
                        continue;
                      }
                      if (j === localB.length) {
                        dp[i][j] = skipPenalty + dp[i + 1][j];
                        continue;
                      }
                      const fractionA = (localA[i] - upper.mdA) / spanA;
                      const fractionB = (localB[j] - upper.mdB) / spanB;
                      const difference = Math.abs(fractionA - fractionB);
                      const matchCost = difference <= 0.5 ? difference + dp[i + 1][j + 1] : Number.POSITIVE_INFINITY;
                      const skipACost = skipPenalty + dp[i + 1][j];
                      const skipBCost = skipPenalty + dp[i][j + 1];
                      const best = Math.min(matchCost, skipACost, skipBCost);
                      dp[i][j] = best;
                      choice[i][j] = best === matchCost ? 'match' : best === skipACost ? 'skipA' : 'skipB';
                    }
                  }
                  let i = 0;
                  let j = 0;
                  while (i < localA.length && j < localB.length) {
                    const action = choice[i][j];
                    if (action === 'match') {
                      matchedBByA.set(localA[i], j);
                      matchedBIndices.add(j);
                      i += 1;
                      j += 1;
                    } else if (action === 'skipA') {
                      i += 1;
                    } else {
                      j += 1;
                    }
                  }
                }

                for (const mdA of localA) {
                  const matchedBIndex = matchedBByA.get(mdA);
                  pairs.push(matchedBIndex === undefined
                    ? { mdA, mdB: projectB(mdA), authorityA: 'measured', authorityB: 'derived-tie-in' }
                    : { mdA, mdB: localB[matchedBIndex], authorityA: 'measured', authorityB: 'measured' });
                }
                localB.forEach((mdB, index) => {
                  if (matchedBIndices.has(index)) return;
                  pairs.push({ mdA: projectA(mdB), mdB, authorityA: 'derived-tie-in', authorityB: 'measured' });
                });
              }

              return pairs
                .filter((pair) => Number.isFinite(pair.mdA) && Number.isFinite(pair.mdB))
                .sort((left, right) => left.mdA - right.mdA)
                .reduce<TieInLithologyBoundaryPair[]>((unique, pair) => {
                  const previous = unique[unique.length - 1];
                  if (previous && Math.abs(previous.mdA - pair.mdA) < 1e-5) {
                    const previousMeasured = Number(previous.authorityA === 'measured') + Number(previous.authorityB === 'measured');
                    const currentMeasured = Number(pair.authorityA === 'measured') + Number(pair.authorityB === 'measured');
                    if (currentMeasured > previousMeasured) unique[unique.length - 1] = pair;
                  } else {
                    unique.push(pair);
                  }
                  return unique;
                }, []);
            })();

            const tieInLithologySegments = tieInBoundaryPairs.slice(0, -1).flatMap((rawTopBoundary, index) => {
              const rawBaseBoundary = tieInBoundaryPairs[index + 1];
              if (!rawBaseBoundary || !(rawBaseBoundary.mdA > rawTopBoundary.mdA) || !(rawBaseBoundary.mdB > rawTopBoundary.mdB)) return [];

              /*
               * The fill-zone depth extent is authoritative on the interval
               * track's A-side depth axis. Apply it AFTER the Tie-In boundary
               * lattice is built, then project the clipped A boundaries onto B.
               * The previous renderer emitted the full paired polygons here,
               * allowing Conform-to-Tie-In fills to escape an explicit
               * Ekofisk->TD (or specified) range.
               */
              const clippedTopA = depthExtent === 'entire_track'
                ? rawTopBoundary.mdA
                : Math.max(requestedTopDepth, rawTopBoundary.mdA);
              const clippedBaseA = depthExtent === 'entire_track'
                ? rawBaseBoundary.mdA
                : Math.min(requestedBaseDepth, rawBaseBoundary.mdA);
              if (!(clippedBaseA > clippedTopA)) return [];

              const spanA = rawBaseBoundary.mdA - rawTopBoundary.mdA;
              const spanB = rawBaseBoundary.mdB - rawTopBoundary.mdB;
              const projectB = (mdA: number) => (
                rawTopBoundary.mdB + ((mdA - rawTopBoundary.mdA) / spanA) * spanB
              );

              const topBoundary: TieInLithologyBoundaryPair =
                Math.abs(clippedTopA - rawTopBoundary.mdA) < 1e-9
                  ? rawTopBoundary
                  : {
                      mdA: clippedTopA,
                      mdB: projectB(clippedTopA),
                      authorityA: 'derived-tie-in',
                      authorityB: 'derived-tie-in',
                    };
              const baseBoundary: TieInLithologyBoundaryPair =
                Math.abs(clippedBaseA - rawBaseBoundary.mdA) < 1e-9
                  ? rawBaseBoundary
                  : {
                      mdA: clippedBaseA,
                      mdB: projectB(clippedBaseA),
                      authorityA: 'derived-tie-in',
                      authorityB: 'derived-tie-in',
                    };

              if (!(baseBoundary.mdB > topBoundary.mdB)) return [];

              const midpointA = (topBoundary.mdA + baseBoundary.mdA) / 2;
              const midpointB = (topBoundary.mdB + baseBoundary.mdB) / 2;
              const intervalA = lithologyIntervalAtDepth(tieInLithologyIntervalsA, midpointA);
              const intervalB = lithologyIntervalAtDepth(tieInLithologyIntervalsB, midpointB);
              const paintInterval = intervalA ?? intervalB;
              if (!paintInterval) return [];
              const identityA = tieInLithologyIdentity(intervalA);
              const identityB = tieInLithologyIdentity(intervalB);
              const faciesMatch = Boolean(intervalA && intervalB && identityA && identityA === identityB);
              return [{
                topBoundary,
                baseBoundary,
                paintInterval,
                intervalA,
                intervalB,
                identityA,
                identityB,
                faciesMatch,
                index,
              }];
            });

            // Temporary clean facies-mismatch fallback. The prior uncertainty-band/zig-zag
            // experiment is fully backed out. Preserve a neutral transition center only.
            const tieInFaciesTransitionCenterPct = Math.max(0, Math.min(100, zone.tieInFaciesTransitionCenterPct ?? 50));
            const tieInFaciesTransitionCenter = tieInFaciesTransitionCenterPct / 100;

            const tieInWarpSegments = tieInAnchors.slice(0, -1).flatMap((anchor, layerIndex) => {
              const nextAnchor = tieInAnchors[layerIndex + 1];
              if (!nextAnchor || !(nextAnchor.mdA > anchor.mdA)) return [];
              const correlationUpperA = anchor.mdA;
              const correlationUpperB = anchor.mdB;
              const correlationLowerA = nextAnchor.mdA;
              const correlationLowerB = nextAnchor.mdB;
              if (!(correlationLowerB > correlationUpperB)) return [];
              const segmentTopA = depthExtent === 'entire_track'
                ? correlationUpperA
                : Math.max(requestedTopDepth, correlationUpperA);
              const segmentBaseA = depthExtent === 'entire_track'
                ? correlationLowerA
                : Math.min(requestedBaseDepth, correlationLowerA);
              if (!(segmentBaseA > segmentTopA)) return [];
              const projectBFromA = (mdA: number) => {
                const spanA = correlationLowerA - correlationUpperA;
                if (Math.abs(spanA) < 1e-9) return correlationUpperB;
                return correlationUpperB + ((mdA - correlationUpperA) / spanA) * (correlationLowerB - correlationUpperB);
              };
              const clampB = (mdB: number) => Math.max(
                correlationUpperB,
                Math.min(correlationLowerB, mdB),
              );
              const segmentTopB = clampB(projectBFromA(segmentTopA));
              const segmentBaseB = clampB(projectBFromA(segmentBaseA));
              if (!(segmentBaseB > segmentTopB)) return [];
              return [{
                layerIndex,
                segmentTopA,
                segmentBaseA,
                segmentTopB,
                segmentBaseB,
                patternKey: `${patternId}-tiein-${layerIndex}`,
                projectBFromA,
                clampB,
              }];
            });

            return (
              <div
                key={`${track.trackId}:${zone.zoneId}:${zoneIndex}`}
                className="wlv-formation-fill-zone"
              >
                {useTieInWarp && tieInWarpSegments.length > 0 ? (
                  <svg
                    className="wlv-formation-top-constrained-fill"
                    viewBox={`0 0 ${trackWidth} ${trackBodyHeightPx}`}
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <defs>
                      {zone.source === 'lithology-column'
                        ? tieInLithologySegments.flatMap(({ paintInterval, intervalA, intervalB, index }) => {
                            const tileSize = 32 * Math.max(0.25, zone.patternScale ?? 1);
                            const patterns: ReactNode[] = [];
                            const patternA = intervalA ?? paintInterval;
                            const boundaryPatternAId = `${patternId}-boundary-${index}-a-${patternA.intervalId}`;
                            patterns.push(
                              <pattern
                                key={boundaryPatternAId}
                                id={boundaryPatternAId}
                                width={tileSize}
                                height={tileSize}
                                patternUnits="userSpaceOnUse"
                              >
                                <image
                                  href={lithologyPatternUrl(patternA.patternId)}
                                  x="0"
                                  y="0"
                                  width={tileSize}
                                  height={tileSize}
                                  preserveAspectRatio="none"
                                />
                              </pattern>,
                            );
                            if (intervalB && intervalB.intervalId !== patternA.intervalId) {
                              const boundaryPatternBId = `${patternId}-boundary-${index}-b-${intervalB.intervalId}`;
                              patterns.push(
                                <pattern
                                  key={boundaryPatternBId}
                                  id={boundaryPatternBId}
                                  width={tileSize}
                                  height={tileSize}
                                  patternUnits="userSpaceOnUse"
                                >
                                  <image
                                    href={lithologyPatternUrl(intervalB.patternId)}
                                    x="0"
                                    y="0"
                                    width={tileSize}
                                    height={tileSize}
                                    preserveAspectRatio="none"
                                  />
                                </pattern>,
                              );
                            }
                            return patterns;
                          })
                        : null}
                      {tieInWarpSegments.map((segment) => {
                        const tileSize = 32 * Math.max(0.25, zone.patternScale ?? 1);
                        return (
                          <Fragment key={`${segment.patternKey}-defs`}>
                            {zone.source === 'pattern' ? (
                              <pattern
                                id={segment.patternKey}
                                width="8"
                                height="8"
                                patternUnits="userSpaceOnUse"
                              >
                                {zone.pattern === 'dots'
                                  ? <circle cx="2" cy="2" r="1.2" fill={zone.color}/>
                                  : <path d="M-2 8L8-2M0 10L10 0" stroke={zone.color} strokeWidth="1"/>}
                              </pattern>
                            ) : null}
                            {zone.source === 'raster' && zone.rasterUrl ? (
                              <pattern
                                id={`${segment.patternKey}-raster`}
                                x="0"
                                y="0"
                                width={trackWidth}
                                height={trackBodyHeightPx}
                                patternUnits="userSpaceOnUse"
                              >
                                <image
                                  href={zone.rasterUrl}
                                  x="0"
                                  y="0"
                                  width={trackWidth}
                                  height={trackBodyHeightPx}
                                  preserveAspectRatio={
                                    zone.rasterFit === 'stretch'
                                      ? 'none'
                                      : 'xMidYMid slice'
                                  }
                                />
                              </pattern>
                            ) : null}
                            {zone.source === 'lithology' && zone.lithologyId ? (
                              <pattern
                                id={`${segment.patternKey}-lithology`}
                                width={tileSize}
                                height={tileSize}
                                patternUnits="userSpaceOnUse"
                              >
                                <image
                                  href={lithologyPatternUrl(zone.lithologyId, zone.color)}
                                  x="0"
                                  y="0"
                                  width={tileSize}
                                  height={tileSize}
                                  preserveAspectRatio="none"
                                />
                              </pattern>
                            ) : null}
                            {zone.source === 'lithology-column'
                              ? zoneLithologyIntervals
                                .filter((interval) => interval.baseMd > segment.segmentTopA && interval.topMd < segment.segmentBaseA)
                                .map((interval) => (
                                  <pattern
                                    key={`${segment.patternKey}-${interval.intervalId}`}
                                    id={`${segment.patternKey}-${interval.intervalId}`}
                                    width={tileSize}
                                    height={tileSize}
                                    patternUnits="userSpaceOnUse"
                                  >
                                    <image
                                      href={lithologyPatternUrl(interval.patternId)}
                                      x="0"
                                      y="0"
                                      width={tileSize}
                                      height={tileSize}
                                      preserveAspectRatio="none"
                                    />
                                  </pattern>
                                ))
                              : null}
                          </Fragment>
                        );
                      })}
                    </defs>
                    {zone.source === 'lithology-column' && tieInLithologySegments.length > 0
                      ? tieInLithologySegments.map(({ topBoundary, baseBoundary, paintInterval, intervalA, intervalB, faciesMatch, index }) => {
                          const visibleA = baseBoundary.mdA > tieInRangeA.min && topBoundary.mdA < tieInRangeA.max;
                          const visibleB = baseBoundary.mdB > tieInRangeB.min && topBoundary.mdB < tieInRangeB.max;
                          if (!visibleA && !visibleB) return null;

                          /*
                           * Preserve full Tie-In polygon geometry across viewport edges.
                           *
                           * Clamped projection collapses any offscreen well edge onto y=0/height,
                           * distorting or erasing the visible intersection of a sloping polygon.
                           * Project endpoints without clamping and let the SVG viewport clip the
                           * resulting polygon naturally.
                           */
                          const yTopA = depthToYUnclamped(topBoundary.mdA, tieInRangeA, trackBodyHeightPx);
                          const yTopB = depthToYUnclamped(topBoundary.mdB, tieInRangeB, trackBodyHeightPx);
                          const yBaseA = depthToYUnclamped(baseBoundary.mdA, tieInRangeA, trackBodyHeightPx);
                          const yBaseB = depthToYUnclamped(baseBoundary.mdB, tieInRangeB, trackBodyHeightPx);
                          const interpolateY = (leftY: number, rightY: number, fraction: number) => leftY + ((rightY - leftY) * fraction);
                          type TieInPoint = { x: number; y: number };
                          const clipTieInPolygonToViewport = (input: TieInPoint[]): string => {
                            const clipAgainst = (
                              points: TieInPoint[],
                              inside: (point: TieInPoint) => boolean,
                              intersect: (start: TieInPoint, end: TieInPoint) => TieInPoint,
                            ) => {
                              if (!points.length) return points;
                              const output: TieInPoint[] = [];
                              let previous = points[points.length - 1];
                              let previousInside = inside(previous);
                              for (const current of points) {
                                const currentInside = inside(current);
                                if (currentInside) {
                                  if (!previousInside) output.push(intersect(previous, current));
                                  output.push(current);
                                } else if (previousInside) {
                                  output.push(intersect(previous, current));
                                }
                                previous = current;
                                previousInside = currentInside;
                              }
                              return output;
                            };
                            const intersectAtY = (targetY: number) => (start: TieInPoint, end: TieInPoint): TieInPoint => {
                              const dy = end.y - start.y;
                              if (Math.abs(dy) < 1e-12) return { x: end.x, y: targetY };
                              const fraction = (targetY - start.y) / dy;
                              return {
                                x: start.x + ((end.x - start.x) * fraction),
                                y: targetY,
                              };
                            };
                            const topClipped = clipAgainst(input, (point) => point.y >= 0, intersectAtY(0));
                            const fullyClipped = clipAgainst(
                              topClipped,
                              (point) => point.y <= trackBodyHeightPx,
                              intersectAtY(trackBodyHeightPx),
                            );
                            return fullyClipped.map((point) => `${point.x},${point.y}`).join(' ');
                          };
                          const polygonBetween = (startFraction: number, endFraction: number) => {
                            const x0 = trackWidth * startFraction;
                            const x1 = trackWidth * endFraction;
                            return clipTieInPolygonToViewport([
                              { x: x0, y: interpolateY(yTopA, yTopB, startFraction) },
                              { x: x1, y: interpolateY(yTopA, yTopB, endFraction) },
                              { x: x1, y: interpolateY(yBaseA, yBaseB, endFraction) },
                              { x: x0, y: interpolateY(yBaseA, yBaseB, startFraction) },
                            ]);
                          };
                          const fullPolygon = polygonBetween(0, 1);
                          const patternA = intervalA ?? paintInterval;
                          const patternAId = `${patternId}-boundary-${index}-a-${patternA.intervalId}`;
                          const patternBId = intervalB ? `${patternId}-boundary-${index}-b-${intervalB.intervalId}` : patternAId;
                          const commonData = {
                            'data-lithology-interval-id': intervalA?.intervalId ?? paintInterval.intervalId,
                            'data-lithology-interval-b-id': intervalB?.intervalId ?? '',
                            'data-lithology-top-left-authority': topBoundary.authorityA,
                            'data-lithology-top-right-authority': topBoundary.authorityB,
                            'data-lithology-base-left-authority': baseBoundary.authorityA,
                            'data-lithology-base-right-authority': baseBoundary.authorityB,
                            'data-lithology-left-top-md': topBoundary.mdA,
                            'data-lithology-left-base-md': baseBoundary.mdA,
                            'data-lithology-right-top-md': topBoundary.mdB,
                            'data-lithology-right-base-md': baseBoundary.mdB,
                          } as const;

                          /*
                           * One-sided lithology is evidence for one well only.
                           * Render only that well's half of the Tie-In track.
                           */
                          if (intervalA && !intervalB) {
                            const halfWidthA = trackWidth * 0.5;
                            const oneSidedAPolygon = clipTieInPolygonToViewport([
                              { x: 0, y: yTopA },
                              { x: halfWidthA, y: yTopA },
                              { x: halfWidthA, y: yBaseA },
                              { x: 0, y: yBaseA },
                            ]);
                            return (
                              <polygon
                                key={`${patternId}-boundary-${index}-one-sided-a`}
                                points={oneSidedAPolygon}
                                fill={`url(#${patternAId})`}
                                fillOpacity={zone.opacity}
                                stroke="none"
                                data-tiein-facies-mode="one-sided-well-a"
                                data-tiein-one-sided-width="half"
                                data-tiein-one-sided-geometry="rectangular-own-well"
                                {...commonData}
                              />
                            );
                          }

                          if (!intervalA && intervalB) {
                            const halfWidthB = trackWidth * 0.5;
                            const oneSidedBPolygon = clipTieInPolygonToViewport([
                              { x: halfWidthB, y: yTopB },
                              { x: trackWidth, y: yTopB },
                              { x: trackWidth, y: yBaseB },
                              { x: halfWidthB, y: yBaseB },
                            ]);
                            return (
                              <polygon
                                key={`${patternId}-boundary-${index}-one-sided-b`}
                                points={oneSidedBPolygon}
                                fill={`url(#${patternAId})`}
                                fillOpacity={zone.opacity}
                                stroke="none"
                                data-tiein-facies-mode="one-sided-well-b"
                                data-tiein-one-sided-width="half"
                                data-tiein-one-sided-geometry="rectangular-own-well"
                                {...commonData}
                              />
                            );
                          }

                          if (faciesMatch) {
                            return (
                              <polygon
                                key={`${patternId}-boundary-${index}-continuous-match`}
                                points={fullPolygon}
                                fill={`url(#${patternAId})`}
                                fillOpacity={zone.opacity}
                                stroke="none"
                                data-tiein-facies-mode="continuous-match"
                                {...commonData}
                              />
                            );
                          }

                          // Valid facies mismatch: preserve both well-edge observations with a
                          // simple neutral split. The earlier uncertainty-band and zig-zag geometry
                          // are fully removed in this rollback baseline.
                          const splitFraction = Math.max(0, Math.min(1, tieInFaciesTransitionCenter));
                          return (
                            <Fragment key={`${patternId}-boundary-${index}-facies-mismatch`}>
                              {splitFraction > 0 ? (
                                <polygon
                                  key={`${patternId}-boundary-${index}-facies-a`}
                                  points={polygonBetween(0, splitFraction)}
                                  fill={`url(#${patternAId})`}
                                  fillOpacity={zone.opacity}
                                  stroke="none"
                                  data-tiein-facies-mode="mismatch-well-a"
                                  data-tiein-facies-transition-mode="clean-neutral-split"
                                  data-tiein-facies-transition-center-pct={tieInFaciesTransitionCenterPct}
                                  {...commonData}
                                />
                              ) : null}
                              {splitFraction < 1 ? (
                                <polygon
                                  key={`${patternId}-boundary-${index}-facies-b`}
                                  points={polygonBetween(splitFraction, 1)}
                                  fill={`url(#${patternBId})`}
                                  fillOpacity={zone.opacity}
                                  stroke="none"
                                  data-tiein-facies-mode="mismatch-well-b"
                                  data-tiein-facies-transition-mode="clean-neutral-split"
                                  data-tiein-facies-transition-center-pct={tieInFaciesTransitionCenterPct}
                                  {...commonData}
                                />
                              ) : null}
                            </Fragment>
                          );
                        })
                      : tieInWarpSegments.map((segment) => {
                          const polygonPoints = `0,${depthToYUnclamped(segment.segmentTopA, tieInRangeA, trackBodyHeightPx)} ${trackWidth},${depthToYUnclamped(segment.segmentTopB, tieInRangeB, trackBodyHeightPx)} ${trackWidth},${depthToYUnclamped(segment.segmentBaseB, tieInRangeB, trackBodyHeightPx)} 0,${depthToYUnclamped(segment.segmentBaseA, tieInRangeA, trackBodyHeightPx)}`;
                          if (zone.source === 'lithology-column') {
                            return zoneLithologyIntervals
                              .filter((interval) => interval.baseMd > segment.segmentTopA && interval.topMd < segment.segmentBaseA)
                              .map((interval) => {
                                const clippedTopA = Math.max(interval.topMd, segment.segmentTopA);
                                const clippedBaseA = Math.min(interval.baseMd, segment.segmentBaseA);
                                const clippedTopB = segment.clampB(segment.projectBFromA(clippedTopA));
                                const clippedBaseB = segment.clampB(segment.projectBFromA(clippedBaseA));
                                if (!(clippedBaseA > clippedTopA) || !(clippedBaseB > clippedTopB)) return null;
                                return (
                                  <polygon
                                    key={`${segment.patternKey}-${interval.intervalId}-poly`}
                                    points={`0,${depthToYUnclamped(clippedTopA, tieInRangeA, trackBodyHeightPx)} ${trackWidth},${depthToYUnclamped(clippedTopB, tieInRangeB, trackBodyHeightPx)} ${trackWidth},${depthToYUnclamped(clippedBaseB, tieInRangeB, trackBodyHeightPx)} 0,${depthToYUnclamped(clippedBaseA, tieInRangeA, trackBodyHeightPx)}`}
                                    fill={`url(#${segment.patternKey}-${interval.intervalId})`}
                                    fillOpacity={zone.opacity}
                                    stroke="none"
                                    data-lithology-interval-id={interval.intervalId}
                                    data-lithology-left-authority="measured"
                                    data-lithology-right-authority="derived-tie-in"
                                  />
                                );
                              });
                          }
                          return (
                            <polygon
                              key={`${segment.patternKey}-poly`}
                              points={polygonPoints}
                              fill={formationTopFillPaint(zone, segment.patternKey)}
                              fillOpacity={zone.opacity}
                              stroke="none"
                            />
                          );
                        })}
                  </svg>
                ) : useSvgConstraint ? (
                  <svg
                    className="wlv-formation-top-constrained-fill"
                    viewBox={`0 0 ${trackWidth} ${trackBodyHeightPx}`}
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <defs>
                      <clipPath id={`${patternId}-clip`}>
                        <rect
                          x="0"
                          y={intervalTopY}
                          width={trackWidth}
                          height={Math.max(1, intervalBaseY - intervalTopY)}
                        />
                      </clipPath>
                      <clipPath id={`${patternId}-shape-clip`}>
                        <path d={constrainedPath} />
                      </clipPath>
                      <pattern
                        id={patternId}
                        width="8"
                        height="8"
                        patternUnits="userSpaceOnUse"
                      >
                        {zone.pattern === 'dots'
                          ? <circle cx="2" cy="2" r="1.2" fill={zone.color}/>
                          : <path d="M-2 8L8-2M0 10L10 0" stroke={zone.color} strokeWidth="1"/>}
                      </pattern>
                      {zone.source === 'raster' && zone.rasterUrl ? (
                        <pattern
                          id={`${patternId}-raster`}
                          x="0"
                          y={intervalTopY}
                          width={trackWidth}
                          height={Math.max(1, intervalBaseY - intervalTopY)}
                          patternUnits="userSpaceOnUse"
                        >
                          <image
                            href={zone.rasterUrl}
                            x="0"
                            y={intervalTopY}
                            width={trackWidth}
                            height={Math.max(1, intervalBaseY - intervalTopY)}
                            preserveAspectRatio={
                              zone.rasterFit === 'stretch'
                                ? 'none'
                                : 'xMidYMid slice'
                            }
                          />
                        </pattern>
                      ) : null}
                      {zone.source === 'lithology' && zone.lithologyId ? (
                        <pattern
                          id={`${patternId}-lithology`}
                          width={32}
                          height={32}
                          patternUnits="userSpaceOnUse"
                        >
                          <image
                            href={lithologyPatternUrl(
                              zone.lithologyId,
                              zone.color,
                            )}
                            x="0"
                            y="0"
                            width="32"
                            height="32"
                            preserveAspectRatio="none"
                          />
                        </pattern>
                      ) : null}
                      {zoneLithologyIntervals.map((interval) => {
                        const clippedTopDepth = Math.max(
                          interval.topMd,
                          intervalTopDepth,
                        );
                        const clippedBaseDepth = Math.min(
                          interval.baseMd,
                          intervalBaseDepth,
                        );
                        const clippedTopY = depthToY(
                          clippedTopDepth,
                          trackViewDepthRange,
                          trackBodyHeightPx,
                        );
                        const clippedBaseY = depthToY(
                          clippedBaseDepth,
                          trackViewDepthRange,
                          trackBodyHeightPx,
                        );
                        return (
                          <Fragment key={`${patternId}-${interval.intervalId}`}>
                            <pattern
                              id={`${patternId}-${interval.intervalId}`}
                              width={32}
                              height={32}
                              patternUnits="userSpaceOnUse"
                            >
                              <image
                                href={lithologyPatternUrl(interval.patternId)}
                                x="0"
                                y="0"
                                width="32"
                                height="32"
                                preserveAspectRatio="none"
                              />
                            </pattern>
                            <clipPath
                              id={`${patternId}-${interval.intervalId}-clip`}
                            >
                              <rect
                                x="0"
                                y={clippedTopY}
                                width={trackWidth}
                                height={Math.max(
                                  1,
                                  clippedBaseY - clippedTopY,
                                )}
                              />
                            </clipPath>
                          </Fragment>
                        );
                      })}
                    </defs>
                    {zone.source === 'lithology-column'
                      ? zoneLithologyIntervals.map((interval) => {
                          const clippedTopDepth = Math.max(interval.topMd, intervalTopDepth);
                          const clippedBaseDepth = Math.min(interval.baseMd, intervalBaseDepth);
                          const clippedTopY = depthToY(clippedTopDepth, trackViewDepthRange, trackBodyHeightPx);
                          const clippedBaseY = depthToY(clippedBaseDepth, trackViewDepthRange, trackBodyHeightPx);
                          const tileSize = 32 * Math.max(0.25, zone.patternScale ?? 1);
                          return (
                            <foreignObject
                              key={`${patternId}-${interval.intervalId}-html`}
                              x="0"
                              y={clippedTopY}
                              width={trackWidth}
                              height={Math.max(1, clippedBaseY - clippedTopY)}
                              clipPath={`url(#${patternId}-shape-clip)`}
                              opacity={zone.opacity}
                              data-lithology-interval-id={interval.intervalId}
                            >
                              <div style={{
                                width: '100%',
                                height: '100%',
                                backgroundImage: `url("${lithologyPatternUrl(interval.patternId)}")`,
                                backgroundSize: `${tileSize}px ${tileSize}px`,
                                backgroundRepeat: 'repeat',
                              }} />
                            </foreignObject>
                          );
                        })
                      : zone.source === 'lithology' && zone.lithologyId ? (
                        <foreignObject
                          x="0"
                          y={intervalTopY}
                          width={trackWidth}
                          height={Math.max(1, intervalBaseY - intervalTopY)}
                          clipPath={`url(#${patternId}-shape-clip)`}
                          opacity={zone.opacity}
                        >
                          <div style={{
                            width: '100%',
                            height: '100%',
                            backgroundColor: zone.color,
                            backgroundImage: `url("${lithologyPatternUrl(zone.lithologyId, zone.color)}")`,
                            backgroundSize: `${32 * Math.max(0.25, zone.patternScale ?? 1)}px ${32 * Math.max(0.25, zone.patternScale ?? 1)}px`,
                            backgroundRepeat: 'repeat',
                          }} />
                        </foreignObject>
                      ) : (
                        <path
                          d={constrainedPath}
                          clipPath={`url(#${patternId}-clip)`}
                          fill={formationTopFillPaint(zone, patternId)}
                          opacity={zone.opacity}
                          stroke="none"
                        />
                      )}
                  </svg>
                ) : zone.constraint === 'track' ? (
                  zone.source === 'lithology-column' ? (
                    <>
                      {zoneLithologyIntervals.map((interval) => {
                        const clippedTopDepth = Math.max(
                          interval.topMd,
                          intervalTopDepth,
                        );
                        const clippedBaseDepth = Math.min(
                          interval.baseMd,
                          intervalBaseDepth,
                        );
                        const clippedTopY = depthToY(
                          clippedTopDepth,
                          trackViewDepthRange,
                          trackBodyHeightPx,
                        );
                        const clippedBaseY = depthToY(
                          clippedBaseDepth,
                          trackViewDepthRange,
                          trackBodyHeightPx,
                        );
                        return (
                          <div
                            key={`${track.trackId}:${zone.zoneId}:${interval.intervalId}`}
                            className="wlv-formation-top-fill"
                            data-lithology-interval-id={interval.intervalId}
                            style={{
                              top: clippedTopY,
                              height: Math.max(
                                0,
                                clippedBaseY - clippedTopY,
                              ),
                              left: zoneLane.left,
                              width: zoneLane.width,
                              backgroundImage: `url("${lithologyPatternUrl(interval.patternId)}")`,
                              backgroundSize: `${32 * Math.max(0.25, zone.patternScale ?? 1)}px ${32 * Math.max(0.25, zone.patternScale ?? 1)}px`,
                              opacity: zone.opacity,
                            }}
                          />
                        );
                      })}
                    </>
                  ) : (
                    <div
                      className={`wlv-formation-top-fill pattern-${zone.pattern}`}
                      style={{
                        top: intervalTopY,
                        height: Math.max(0, intervalBaseY - intervalTopY),
                        left: zoneLane.left,
                        width: zoneLane.width,
                        backgroundColor:
                          zone.source === 'solid' ? zone.color : undefined,
                        backgroundImage:
                          zone.source === 'raster' && zone.rasterUrl
                            ? `url("${zone.rasterUrl}")`
                            : zone.source === 'lithology' && zone.lithologyId
                              ? `url("${lithologyPatternUrl(
                                  zone.lithologyId,
                                  zone.color,
                                )}")`
                              : undefined,
                        backgroundSize:
                          zone.source === 'raster'
                            ? (zone.rasterFit === 'stretch' ? '100% 100%' : 'cover')
                            : zone.source === 'lithology'
                              ? `${32 * Math.max(0.25, zone.patternScale ?? 1)}px ${32 * Math.max(0.25, zone.patternScale ?? 1)}px`
                              : undefined,
                        opacity: zone.opacity,
                      }}
                    />
                  )
                ) : null}
              </div>
            );
          });

          return {
            topsFillLayer: renderedFillZones,
            formationTopsLayer: (
              <>
            {overlayStyle.displayOnTrack ? lithologyIntervals.map((interval) => {
              const range = trackViewDepthRange.max - trackViewDepthRange.min;
              if (!(range > 0) || interval.baseMd <= trackViewDepthRange.min || interval.topMd >= trackViewDepthRange.max) return null;
              const clippedTop = Math.max(interval.topMd, trackViewDepthRange.min);
              const clippedBase = Math.min(interval.baseMd, trackViewDepthRange.max);
              const top = `${((clippedTop - trackViewDepthRange.min) / range) * 100}%`;
              const height = `${Math.max(0.2, ((clippedBase - clippedTop) / range) * 100)}%`;
              const patternUrl = interval.patternId ? lithologyPatternUrl(interval.patternId) : '';
              return <div key={`${track.trackId}:${interval.intervalId}`} className="wlv-lithology-interval-overlay" style={{ top, height, left: overlayLane.left, width: overlayLane.width, backgroundImage: patternUrl ? `url("${patternUrl}")` : undefined }} title={`${interval.lithology} · ${interval.topMd.toLocaleString()}–${interval.baseMd.toLocaleString()} ${interval.depthUnit} · ${interval.confidence || 'unrated'} confidence`}><span>{interval.lithology}</span></div>;
            }) : null}
            {overlayStyle.displayOnTrack ? visibleMarkers.map((marker) => {
              const y = depthToY(marker.md, trackViewDepthRange, trackBodyHeightPx);
              const isBase = marker.markerType.toLowerCase().includes('base');
              const lineStyle = isBase ? overlayStyle.baseLineStyle : overlayStyle.topLineStyle;
              const horizontalAnchorStyle =
                overlayStyle.labelPosition === 'right'
                  ? { left: 'auto', right: 8 }
                  : overlayStyle.labelPosition === 'center'
                    ? { left: '50%', right: 'auto' }
                    : { left: 8, right: 'auto' };
              const anchorTransform =
                overlayStyle.labelPosition === 'center'
                  ? 'translateX(-50%) '
                  : '';
              const labelStyle = {
                ...horizontalAnchorStyle,
                fontSize: overlayStyle.labelFontSize,
                color: overlayStyle.labelTextColor,
                borderColor: overlayStyle.labelBackground
                  ? rgbaFromHex(
                      overlayStyle.labelTextColor,
                      55,
                    )
                  : 'transparent',
                transform: `${anchorTransform}translate(${overlayStyle.labelOffsetX}px, ${overlayStyle.labelOffsetY}px)`,
                background: overlayStyle.labelBackground
                  ? rgbaFromHex(
                      overlayStyle.labelBackgroundColor,
                      overlayStyle.labelBackgroundOpacity * 100,
                    )
                  : 'transparent',
              };
              return (<div key={`${track.trackId}:${marker.markerId}`} className={`wlv-formation-top-overlay ${isBase ? 'formation-base' : 'formation-top'} label-${overlayStyle.labelPosition}`} style={{ top: y, left: overlayLane.left, width: overlayLane.width, borderTopColor: isBase ? overlayStyle.baseColor : overlayStyle.topColor, borderTopWidth: isBase ? overlayStyle.baseWidth : overlayStyle.topWidth, borderTopStyle: lineStyle === 'dash' ? 'dashed' : lineStyle === 'dot' ? 'dotted' : 'solid', opacity: overlayStyle.opacity }} title={`${marker.markerName} · ${marker.md.toLocaleString(undefined, { maximumFractionDigits: 1 })} m MD · ${marker.pickStatus}`}>
                {overlayStyle.showLabels ? <span style={labelStyle}>{marker.markerName}</span> : null}
              </div>);
            }) : null}
              </>
            ),
          };
    };
    const trackLabelById = Object.fromEntries(
        tracks.map((track) => [track.trackId, `T${track.trackIndex + 1}`]),
    );
    const tieStatusByTrackId = viewportTieGroups.reduce<Record<string, ViewportTieHeaderStatus>>(
        (statusByTrackId, group) => {
            const leaderLabel = trackLabelById[group.leaderTrackId];
            if (!leaderLabel) return statusByTrackId;
            const memberLabels = group.memberTrackIds
                .map((trackId) => trackLabelById[trackId])
                .filter((label): label is string => Boolean(label));
            for (const trackId of group.memberTrackIds) {
                if (!trackLabelById[trackId]) continue;
                statusByTrackId[trackId] = {
                    role: trackId === group.leaderTrackId ? 'leader' : 'member',
                    leaderLabel,
                    memberLabels,
                };
            }
            return statusByTrackId;
        },
        {},
    );

    return (<CombinationZoomContext.Provider value={{ presentationByTrackId: trackHeaderPresentationById, tieStatusByTrackId, onToggleTrack: onToggleCombinationTrack }}><main ref={(node) => {
            canvasRef.current = node;
            setContainerRef(node);
        }} className={`wlv-track-canvas ${trackHeadersCollapsed ? 'headers-collapsed' : 'headers-expanded'} ${intervalZoomActive ? 'interval-zoom-active' : ''} ${dragPanActive ? 'drag-pan-active' : ''} ${resizingTrackId ? 'curve-resize-active' : ''} ${curveFillMdPick ? 'curve-fill-md-pick-active' : ''} ${goToDepthPickActive ? 'go-to-depth-pick-active' : ''}`} onMouseDownCapture={(event) => {
            if (goToDepthPickActive) {
                const target = event.target;

                if (
                    event.button === 0
                    && target instanceof Element
                    && target.closest('.wlv-track-body')
                ) {
                    event.preventDefault();
                    event.stopPropagation();

                    const point = pointFromEvent(event);
                    onPickGoToDepth?.(point.depth);
                }

                return;
            }

            if (curveFillMdPick) {
                const target = event.target;
                if(
                    event.shiftKey
                    && event.button===0
                    && target instanceof Element
                    && target.closest('.wlv-track-body')
                ){
                    // Shift+MB1 is the established track-width resize gesture.
                    // A stranded MD picker must never block resizing. Cancel only
                    // the transient picker and let the event continue to the
                    // existing per-track resize handler.
                    window.dispatchEvent(new CustomEvent(
                        CURVE_FILL_MD_PICK_CANCEL_EVENT,
                        {detail:{token:curveFillMdPick.token}},
                    ));
                    setCurveFillMdPick(null);
                    return;
                }
                if (
                    event.button === 0
                    && target instanceof Element
                    && target.closest('.wlv-track-body')
                ) {
                    event.preventDefault();
                    event.stopPropagation();
                    const point = pointFromEvent(event);
                    if(curveFillMdPick.allowedTrackId&&point.trackId!==curveFillMdPick.allowedTrackId){
                        window.dispatchEvent(new CustomEvent(
                            'wlv:curve-fill-md-pick-wrong-track',
                            {
                                detail:{
                                    token:curveFillMdPick.token,
                                    expectedTrackId:curveFillMdPick.allowedTrackId,
                                    actualTrackId:point.trackId,
                                },
                            },
                        ));
                        return;
                    }
                    window.dispatchEvent(
                        new CustomEvent(
                            CURVE_FILL_MD_PICK_RESULT_EVENT,
                            {
                                detail: {
                                    token: curveFillMdPick.token,
                                    depth: point.depth,
                                    trackId: point.trackId,
                                },
                            },
                        ),
                    );
                    window.dispatchEvent(new CustomEvent(
                        CURVE_FILL_MD_PICK_CANCEL_EVENT,
                        {detail:{token:curveFillMdPick.token}},
                    ));
                    setCurveFillMdPick(null);
                }
                return;
            }
            if (intervalZoomActive) {
                event.preventDefault();
                event.stopPropagation();
                suppressIntervalZoomClickRef.current = false;
                const point = pointFromEvent(event);
                onStartIntervalSelection(point.depth, point.y, point.trackId ?? null);
                return;
            }
            if (!shouldStartDragPan(event))
                return;
            event.preventDefault();
            event.stopPropagation();
            const { y, trackId } = pointFromEvent(event);
            onStartDragPan(y, trackId ?? null);
        }} onMouseMoveCapture={(event) => {
            if (intervalZoomActive && intervalSelection?.dragging) {
                event.preventDefault();
                event.stopPropagation();
                const point = pointFromEvent(event);
                const sourceRange = intervalSelection.sourceTrackId
                    ? (trackDepthRangesById[intervalSelection.sourceTrackId] ?? viewDepthRange)
                    : viewDepthRange;
                const sourceDepth = yToDepth(point.y, sourceRange, point.height);
                onUpdateIntervalSelection(sourceDepth, point.y);
                return;
            }
            // Drag-pan movement is handled by document-level listeners once MB1 drag starts.
        }} onMouseUpCapture={(event) => {
            if (intervalZoomActive && intervalSelection?.dragging) {
                event.preventDefault();
                event.stopPropagation();
                const point = pointFromEvent(event);
                const sourceRange = intervalSelection.sourceTrackId
                    ? (trackDepthRangesById[intervalSelection.sourceTrackId] ?? viewDepthRange)
                    : viewDepthRange;
                const sourceDepth = yToDepth(point.y, sourceRange, point.height);
                suppressIntervalZoomClickRef.current = true;
                window.setTimeout(() => {
                    suppressIntervalZoomClickRef.current = false;
                }, 0);
                onCompleteIntervalSelection(sourceDepth, point.y);
                return;
            }
            // Drag-pan mouseup is handled by document-level listeners once MB1 drag starts.
        }} onClickCapture={(event) => {
            if (!suppressIntervalZoomClickRef.current)
                return;
            const target = event.target;
            if (!(target instanceof Element) || !target.closest('.wlv-track-body'))
                return;
            event.preventDefault();
            event.stopPropagation();
            suppressIntervalZoomClickRef.current = false;
        }}>
      <div className="wlv-shared-depth-grid-overlay" aria-hidden="true">
        {sharedDepthGridLines.map(({ depth, y }, depthIndex) => (<div key={`shared-grid:${depth}:${depthIndex}`} className="wlv-shared-depth-grid-line" style={{ top: y }}/>))}
      </div>
      <div
        className="wlv-depth-range-locator-overlay"
        aria-hidden="true"
        style={{ height: `${sharedHeaderHeight + trackBodyHeightPx}px` }}
      >
        {locatorOverlayColumns.map(({ targetTrack, widthPx, locator }) => (
          <div
            key={`depth-range-locator:${targetTrack.trackId}`}
            className="wlv-depth-range-locator-column"
            style={{ width: `${widthPx}px`, minWidth: `${widthPx}px`, maxWidth: `${widthPx}px` }}
          >
            {locator ? (() => {
              const dataInset = targetTrack.trackType === 'core' ? '12%' : '0px';
              const sideStyle = locator.side === 'right'
                ? { right: locator.presentation === 'data_bar' ? dataInset : '0px' }
                : { left: locator.presentation === 'data_bar' ? dataInset : '0px' };
              if (locator.presentation === 'edge_arrows') {
                return <>
                  {locator.topVisible ? <span className={`wlv-depth-range-locator-arrow is-${locator.side}`} style={{ top: bodyTopOffset + locator.topY, ...sideStyle }} /> : null}
                  {locator.baseVisible ? <span className={`wlv-depth-range-locator-arrow is-${locator.side}`} style={{ top: bodyTopOffset + locator.baseY, ...sideStyle }} /> : null}
                </>;
              }
              return <span
                className={`wlv-depth-range-locator-bar is-${locator.side} is-${locator.presentation}`}
                style={{
                  top: bodyTopOffset + locator.topY,
                  height: Math.max(2, locator.baseY - locator.topY),
                  ...sideStyle,
                }}
              />;
            })() : null}
          </div>
        ))}
      </div>
      <div
        className="wlv-macro-core-image-layer"
        aria-hidden="true"
        style={{ height: `${sharedHeaderHeight + trackBodyHeightPx}px` }}
      >
        {macroCoreImageColumns.map(({ track, widthPx, marker }) => (
          <div
            key={`macro-core-image:${track.trackId}`}
            className="wlv-macro-core-image-column"
            style={{ width: `${widthPx}px`, minWidth: `${widthPx}px`, maxWidth: `${widthPx}px` }}
          >
            {marker ? (
              <div
                className="wlv-macro-core-image-cylinder"
                style={{
                  left: marker.x,
                  top: sharedHeaderHeight + marker.topY,
                  width: marker.cylinderWidthPx,
                  height: Math.max(2, marker.baseY - marker.topY),
                }}
              />
            ) : null}
          </div>
        ))}
      </div>
      <div
        className="wlv-text-overlay-layer"
        aria-hidden="true"
        style={{ height: `${sharedHeaderHeight + trackBodyHeightPx}px` }}
      >
        {textOverlayColumns.map(({ track, widthPx, overlays }) => (
          <div
            key={`text-overlay:${track.trackId}`}
            className="wlv-text-overlay-column"
            style={{ width: `${widthPx}px`, minWidth: `${widthPx}px`, maxWidth: `${widthPx}px` }}
          >
            {overlays.map(({ item, x, y, boxWidth, translateX, safeHtml }) => (
              <div
                key={item.overlayUid}
                className={`wlv-track-text-overlay${item.background === 'light' ? ' has-light-background' : ''}`}
                style={{
                  left: x,
                  top: sharedHeaderHeight + y,
                  width: boxWidth,
                  transform: `translate(${translateX}, -50%)`,
                  fontSize: `${item.fontSize}px`,
                  color: item.color,
                  textAlign: item.textAlign,
                }}
                dangerouslySetInnerHTML={{ __html: safeHtml }}
              />
            ))}
          </div>
        ))}
      </div>
      {displayGoToSelectionLine && typeof goToDepthMarker === 'number' && (
        <div
          className="wlv-go-to-per-track-overlay"
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 0,
            height: `${sharedHeaderHeight + trackBodyHeightPx}px`,
            display: 'flex',
            pointerEvents: 'none',
            // WDV_SELECTION_LINE_STACKING_FIX_V1_0_0
            // .wlv-track-strip is a sibling stacking context at z-index 40 and
            // follows this overlay in DOM order. Keep the Go To overlay above
            // populated track content, matching the proven Formation Tops layer.
            zIndex: 60,
          }}
        >
          {orderedTracks.map((track) => {
            const trackRange = trackDepthRangesById[track.trackId] ?? viewDepthRange;
            const participates = goToSelectionTrackIdSet.has(track.trackId);
            const firstParticipatingTrackId = orderedTracks.find(
              (candidate) => goToSelectionTrackIdSet.has(candidate.trackId),
            )?.trackId ?? null;
            const showDepthLabel = participates && track.trackId === firstParticipatingTrackId;
            const visible = participates
              && goToDepthMarker >= trackRange.min
              && goToDepthMarker <= trackRange.max;
            const widthPx = track.trackType === 'curve'
              || track.trackType === 'core'
              || track.trackType === 'interval'
              ? clampCurveTrackWidth(track.widthPx)
              : track.widthPx;
            const top = visible
              ? bodyTopOffset + depthToY(goToDepthMarker, trackRange, trackBodyHeightPx)
              : null;
            return (
              <div
                key={`go-to-marker-track:${track.trackId}`}
                style={{
                  position: 'relative',
                  width: `${widthPx}px`,
                  minWidth: `${widthPx}px`,
                  maxWidth: `${widthPx}px`,
                  flex: `0 0 ${widthPx}px`,
                }}
              >
                {top !== null ? (
                  <div
                    className="wlv-shared-go-to-depth-marker"
                    style={{ top, left: 0, right: 0 }}
                  >
                    {showDepthLabel ? (
                      <span
                        style={{
                          position: 'absolute',
                          left: 4,
                          top: 0,
                          transform: 'translateY(-100%)',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {`${goToDepthMarker.toLocaleString(undefined, { maximumFractionDigits: 3 })} m MD`}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
      <div className="wlv-track-strip">
        {orderedTracks.map((track) => {
          const combinationViewDepthRange =
            trackDepthRangesById[track.trackId] ?? viewDepthRange;
          const combinationDepthTicks = depthTicksForIncrement(combinationViewDepthRange, GLOBAL_DEPTH_LATTICE_INCREMENT);
          const renderBundle = renderBundleForTrack(track, renderBundlesByWellUid);
          const formationLayers = buildFormationTopLayers(track, combinationViewDepthRange);

          const trackCoreImageItems: CoreImageInventoryItem[] =
            track.managedWellUid
              ? coreImageItemsByWellUid[track.managedWellUid] ?? []
              : coreImageItems;

          const trackSelectedCoreImageIds =
            track.managedWellUid
              ? selectedCoreImageIdsByWellUid[track.managedWellUid] ?? new Set<string>()
              : selectedCoreImageIds;

          let trackFullRenderableRange = fullDepthRange;
          if (track.trackType === 'depth') {
            const currentTrackIndex = orderedTracks.findIndex(
              (candidate) => candidate.trackId === track.trackId,
            );
            const rightTrack = orderedTracks
              .slice(currentTrackIndex + 1)
              .find((candidate) => candidate.trackType !== 'depth') ?? null;

            if (rightTrack?.trackType === 'curve') {
              trackFullRenderableRange = validDepthRangeFromValues(
                orderedCurves(rightTrack).flatMap((assignment, index) => {
                  const curve = resolveCurveAssignmentCatalogItem(
                    curveCatalogItems,
                    assignment,
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
                fullDepthRange,
              );
            } else if (rightTrack?.trackType === 'core') {
              const selectedItems = trackCoreImageItems.filter(
                (item) => trackSelectedCoreImageIds.has(item.productId),
              );
              const rangeItems =
                selectedItems.length > 0 ? selectedItems : trackCoreImageItems;
              trackFullRenderableRange = validDepthRangeFromValues(
                rangeItems.flatMap((item) => [item.topMd, item.baseMd]),
                fullDepthRange,
              );
            } else if (
              rightTrack?.trackType === 'interval'
              && rightTrack.rendererType === 'interval_core_description'
            ) {
              trackFullRenderableRange = validDepthRangeFromValues(
                trackCoreImageItems.flatMap((item) => [item.topMd, item.baseMd]),
                fullDepthRange,
              );
            } else if (
              rightTrack?.trackType === 'interval'
              && rightTrack.rendererType === 'interval_formation'
            ) {
              const rightBundle = renderBundleForTrack(
                rightTrack,
                renderBundlesByWellUid,
              );
              trackFullRenderableRange = validDepthRangeFromValues(
                rightBundle.allFormationTops.map((marker) => marker.md),
                fullDepthRange,
              );
            }
          } else if (track.trackType === 'curve') {
            trackFullRenderableRange = validDepthRangeFromValues(
              orderedCurves(track).flatMap((assignment, index) => {
                const curve = resolveCurveAssignmentCatalogItem(curveCatalogItems, assignment);
                return curve ? makeMockCurveSamples(curve, assignment, index, managedSamplesByCurveId).map((sample) => sample.depth) : [];
              }),
              fullDepthRange,
            );
          } else if (track.trackType === 'core') {
            const selectedItems = trackCoreImageItems.filter((item) => trackSelectedCoreImageIds.has(item.productId));
            const rangeItems = selectedItems.length > 0 ? selectedItems : trackCoreImageItems;
            trackFullRenderableRange = validDepthRangeFromValues(rangeItems.flatMap((item) => [item.topMd, item.baseMd]), fullDepthRange);
          } else if (track.trackType === 'interval' && track.rendererType === 'interval_core_description') {
            trackFullRenderableRange = validDepthRangeFromValues(trackCoreImageItems.flatMap((item) => [item.topMd, item.baseMd]), fullDepthRange);
          } else if (track.trackType === 'interval' && track.rendererType === 'interval_depth') {
            trackFullRenderableRange = trackCoreImageItems.length > 0
              ? validDepthRangeFromValues(
                  trackCoreImageItems.flatMap((item) => [item.topMd, item.baseMd]),
                  fullDepthRange,
                )
              : fullDepthRange;
          } else if (track.trackType === 'interval' && track.rendererType === 'interval_formation') {
            trackFullRenderableRange = validDepthRangeFromValues(
              renderBundle.allFormationTops.map((marker) => marker.md),
              fullDepthRange,
            );
          } else if (renderBundle.loadedLithologyIntervals.length > 0) {
            trackFullRenderableRange = validDepthRangeFromValues(
              renderBundle.loadedLithologyIntervals.flatMap((interval) => [interval.topMd, interval.baseMd]),
              fullDepthRange,
            );
          }
          const magnificationLabel =
            track.trackType === 'interval' && track.rendererType === 'interval_blank'
              ? '1×'
              : trackMagnificationLabel(
                  fullDepthRange,
                  combinationViewDepthRange,
                  trackFullRenderableRange,
                );

          const trackHighlighted = Boolean(trackHighlightedById[track.trackId]);

          if (track.trackType === 'core') {
            /*
             * Core header follows the same hierarchy as Curve tracks:
             *
             * Row 1 — track identity
             * Row 2 — active WDV well
             * Row 3 — selected Core MD coverage
             */
            const selectedCoreHeaderItems = trackCoreImageItems.filter(
                (item) => trackSelectedCoreImageIds.has(item.productId),
            );

            const coreHeaderItems =
                selectedCoreHeaderItems.length > 0
                    ? selectedCoreHeaderItems
                    : trackCoreImageItems;

            const coreHeaderDepthRange =
                coreHeaderItems.length > 0
                    ? (
                        `${Math.min(
                            ...coreHeaderItems.map((item) => item.topMd),
                        ).toLocaleString(
                            undefined,
                            { maximumFractionDigits: 3 },
                        )}`
                        + `–`
                        + `${Math.max(
                            ...coreHeaderItems.map((item) => item.baseMd),
                        ).toLocaleString(
                            undefined,
                            { maximumFractionDigits: 3 },
                        )} `
                        + `${coreHeaderItems[0]?.depthUnit || 'm'} MD`
                    )
                    : 'No Core coverage';

            return (
              <section
                  key={track.trackId}
                  className={
                      `wlv-track core ${
                          trackHighlighted ? 'selected' : ''
                      }${resizingTrackId === track.trackId ? ' resizing' : ''}`
                  }
                  style={{
                      width: clampCurveTrackWidth(track.widthPx),
                      minWidth: clampCurveTrackWidth(track.widthPx),
                      maxWidth: clampCurveTrackWidth(track.widthPx),
                  }}
                  onMouseDownCapture={(event) => {
                      if (!event.shiftKey || event.button !== 0) return;
                      const target = event.target;
                      if (!(target instanceof Element) || !target.closest('.wlv-track-body')) return;
                      event.preventDefault();
                      event.stopPropagation();
                      onSelectTrack(track.trackId);
                      onStartCurveTrackResize(
                          track.trackId,
                          event.clientX,
                          clampCurveTrackWidth(track.widthPx),
                      );
                  }}
                  onClick={(event) => onSelectTrack(track.trackId, event.metaKey)}
              >
                <header
                    className="wlv-track-header wlv-track-header-aligned"
                    style={{
                        height: `${sharedHeaderHeight}px`,
                        minHeight: `${sharedHeaderHeight}px`,
                        flexBasis: `${sharedHeaderHeight}px`,
                    }}
                    onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        onSelectTrack(track.trackId, event.metaKey);
                    }}
                >
                  <div className="wlv-track-title-row">
                    <strong>{track.title || 'Core'}</strong>
                    <TrackPlacementSelector track={track}/>
                  </div>

                  <div className="wlv-track-header-row-2">
                    <div className="wlv-lithology-header">
                      {track.ownerWellName || activeWellName || '—'}
                    </div>
                    <span className="wlv-track-magnification">{magnificationLabel}</span>
                  </div>

                  <div className="wlv-track-header-row-3">
                    <div className="wlv-lattice-badge">
                      {coreHeaderDepthRange}
                    </div>
                  </div>

                  <div className="wlv-track-header-detail-rows">
                    <div
                        className="wlv-track-header-detail-placeholder"
                        aria-hidden="true"
                    />
                  </div>
                </header>

                <div
                    className="wlv-track-body"
                    style={{
                        height: `${trackBodyHeightPx}px`,
                        minHeight: `${trackBodyHeightPx}px`,
                        flexBasis: `${trackBodyHeightPx}px`,
                    }}
                >
                  <CoreImageTrackView
                      items={trackCoreImageItems}
                      selectedIds={trackSelectedCoreImageIds}
                      viewDepthRange={combinationViewDepthRange}
                      trackBodyHeightPx={trackBodyHeightPx}
                      appearance={resolveCoreTrackAppearance(track)}
                  />
                  <div className="wlv-track-content-layer tops-fill-layer" style={{ zIndex: 2 }}>
                    {formationLayers.topsFillLayer}
                  </div>
                  <div className="wlv-track-content-layer formation-tops-layer" style={{ zIndex: 6 }}>
                    {formationLayers.formationTopsLayer}
                  </div>
                </div>
              </section>
            );
          }
          if (track.trackType === 'completion') {
            const trackCompletionComponents = track.managedWellUid
              ? (completionComponentsByWellUid[track.managedWellUid] ?? [])
              : [];
            const trackSelectedCompletionComponentIds = track.managedWellUid
              ? (selectedCompletionComponentIdsByWellUid[track.managedWellUid] ?? new Set<string>())
              : selectedCompletionComponentIds;
            const displayedCompletionComponents = trackCompletionComponents.filter(
              (component) => trackSelectedCompletionComponentIds.has(component.componentId),
            );
            const completionHostDepthRange = track.managedWellUid
              ? fullDepthRangesByWellUid[track.managedWellUid] ?? null
              : null;
            return <CompletionTrack
              key={track.trackId}
              track={track}
              components={displayedCompletionComponents}
              viewDepthRange={combinationViewDepthRange}
              bodyHeight={trackBodyHeightPx}
              sharedHeaderHeight={sharedHeaderHeight}
              magnificationLabel={magnificationLabel}
              selected={trackHighlighted}
              onSelect={onSelectTrack}
              onStartResize={onStartCurveTrackResize}
              resizing={resizingTrackId === track.trackId}
              boreBaseMd={completionHostDepthRange?.max ?? null}
              topsFillLayer={formationLayers.topsFillLayer}
              formationTopsLayer={formationLayers.formationTopsLayer}
            />;
          }
          if (track.trackType === 'interval') {
            const intervalWidth = clampCurveTrackWidth(track.widthPx);

            const intervalTrackView =
              track.rendererType === 'interval_blank'
                ? <IntervalBlankTrack
                    track={track}
                    bodyHeight={trackBodyHeightPx}
                    sharedHeaderHeight={sharedHeaderHeight}
                    magnificationLabel={magnificationLabel}
                    selected={trackHighlighted}
                    onSelect={onSelectTrack}
                    trackA={orderedTracks[orderedTracks.findIndex(candidate=>candidate.trackId===track.trackId)-1]??null}
                    trackB={orderedTracks[orderedTracks.findIndex(candidate=>candidate.trackId===track.trackId)+1]??null}
                    topsFillLayer={formationLayers.topsFillLayer}
                  />
                : track.rendererType === 'interval_core_description'
                  ? <IntervalCoreDescriptionTrack track={track} coreImageItems={trackCoreImageItems} activeWellName={activeWellName} viewDepthRange={combinationViewDepthRange} bodyHeight={trackBodyHeightPx} sharedHeaderHeight={sharedHeaderHeight} magnificationLabel={magnificationLabel} selected={trackHighlighted} onSelect={onSelectTrack}/>
                  : track.rendererType === 'interval_depth'
                    ? <IntervalDepthTrack track={track} markers={renderBundle.allFormationTops} depthTicks={combinationDepthTicks} viewDepthRange={combinationViewDepthRange} bodyHeight={trackBodyHeightPx} sharedHeaderHeight={sharedHeaderHeight} magnificationLabel={magnificationLabel} selected={trackHighlighted} onSelect={onSelectTrack}/>
                    : <IntervalFormationTrack track={track} markers={renderBundle.allFormationTops} viewDepthRange={combinationViewDepthRange} bodyHeight={trackBodyHeightPx} sharedHeaderHeight={sharedHeaderHeight} magnificationLabel={magnificationLabel} selected={trackHighlighted} onSelect={onSelectTrack}/>;

            return (
              <div
                key={track.trackId}
                className={`wlv-resizable-interval-shell${resizingTrackId === track.trackId ? ' resizing' : ''}`}
                style={{
                  width: `${intervalWidth}px`,
                  minWidth: `${intervalWidth}px`,
                  maxWidth: `${intervalWidth}px`,
                  flex: `0 0 ${intervalWidth}px`,
                  position: 'relative',
                }}
                onMouseDownCapture={(event) => {
                  if (!event.shiftKey || event.button !== 0) return;
                  const target = event.target;
                  if (!(target instanceof Element) || !target.closest('.wlv-track-body')) return;
                  event.preventDefault();
                  event.stopPropagation();
                  onSelectTrack(track.trackId);
                  onStartCurveTrackResize(
                    track.trackId,
                    event.clientX,
                    intervalWidth,
                  );
                }}
              >
                {intervalTrackView}
                {track.rendererType === 'interval_blank' ? null : (
                  <div
                    className="wlv-interval-overlay-infill-layer"
                    aria-hidden="true"
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: sharedHeaderHeight,
                      width: intervalWidth,
                      height: trackBodyHeightPx,
                      overflow: 'hidden',
                      pointerEvents: 'none',
                      zIndex: 20,
                    }}
                  >
                    {formationLayers.topsFillLayer}
                  </div>
                )}
                <IntervalTieInOverlay track={track} orderedTracks={orderedTracks} trackDepthRangesById={trackDepthRangesById} fallbackViewDepthRange={viewDepthRange} lithologyIntervals={renderBundle.loadedLithologyIntervals} width={intervalWidth} bodyHeight={trackBodyHeightPx} bodyTop={sharedHeaderHeight}/>
              </div>
            );
          }
          return (<TrackView key={track.trackId} track={track} sharedHeaderHeightPx={sharedHeaderHeight} magnificationLabel={magnificationLabel} selected={trackHighlighted} selectedAssignmentId={selectedAssignmentIdByTrackId[track.trackId] ?? null} openCurveMenu={openCurveMenu} depthTicks={combinationDepthTicks} viewDepthRange={combinationViewDepthRange} onSelectTrack={onSelectTrack} onSelectCurve={onSelectCurve} onEditCurve={onEditCurve} onReorderCurve={onReorderCurve} onMoveCurveToTrack={onMoveCurveToTrack} onOpenCurveMenu={onOpenCurveMenu} onCloseCurveMenu={onCloseCurveMenu} onRemoveCurveFromTrack={onRemoveCurveFromTrack} onStartCurveTrackResize={onStartCurveTrackResize} resizingTrackId={resizingTrackId} trackBodyHeightPx={trackBodyHeightPx} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={curveCatalogItems} lithologyIntervals={renderBundle.loadedLithologyIntervals} transientCurveFillDraft={transientCurveFillDraft} curveFillGeometryByRuleUid={renderBundle.curveFillGeometryByRuleUid} trackContentOrder={trackContentOrderByTrackId[track.trackId] ?? DEFAULT_TRACK_CONTENT_ORDER} topsFillLayer={formationLayers.topsFillLayer} formationTopsLayer={formationLayers.formationTopsLayer} onOpenTrackContentMenu={setOpenTrackContentMenuId}/>);
        })}
        {intervalBand && (<div className="wlv-interval-selection-band dragging" style={{ top: intervalBandTopOffset + intervalBand.top, height: intervalBand.height }}>
            <span>{Math.round(intervalBand.startDepth)}–{Math.round(intervalBand.endDepth)} m</span>
          </div>)}
      </div>
      {openTrackContentMenuId ? (() => {
        const menuTrack = orderedTracks.find((candidate) => candidate.trackId === openTrackContentMenuId);
        if (!menuTrack) return null;
        const renderBundle = renderBundleForTrack(menuTrack, renderBundlesByWellUid);
        const style: FormationTopOverlayStyle = {
          ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
          ...(renderBundle.formationTopOverlayStylesByTrackId[menuTrack.trackId] ?? {}),
        };
        const hasCurveFill = menuTrack.trackType === 'curve' && ([...renderBundle.curveFillGeometryByRuleUid.values()].some((geometry) => geometry.track_uid === menuTrack.trackId) || menuTrack.curves.some((assignment) => assignment.fillSide !== 'none'));
        const hasTopsFill = style.displayOnTrack && legacyFormationTopFillZone(style).some((zone) => zone.enabled);
        const categories: TrackContentCategory[] = [
          ...(menuTrack.trackType === 'curve' && menuTrack.curves.length > 0 ? ['curves' as const] : []),
          ...(hasCurveFill ? ['curve-fill' as const] : []),
          ...(style.displayOnTrack && renderBundle.formationTops.length > 0 ? ['formation-tops' as const] : []),
          ...(hasTopsFill ? ['tops-fill' as const] : []),
        ];
        return <TrackContentOrderMenuPortal trackId={menuTrack.trackId} order={trackContentOrderByTrackId[menuTrack.trackId] ?? DEFAULT_TRACK_CONTENT_ORDER} availableCategories={categories} onChangeOrder={changeTrackContentOrder} onClose={() => setOpenTrackContentMenuId(null)}/>;
      })() : null}
    </main></CombinationZoomContext.Provider>);
}
export function TrackProperties({ track, curveCatalogItems, updateTrack, }: {
    track: WellLogTrack;
    curveCatalogItems: CurveCatalogItem[];
    updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
}) {
    if (track.trackType === 'depth') {
        return (<div className="wlv-property-section">
        <h3>Selected Track</h3>
        <label>
          Track title
          <input value={track.title} onChange={(event) => updateTrack(track.trackId, { title: event.target.value })}/>
        </label>
        <label>
          Depth type
          <select value={track.depthBasis} onChange={(event) => updateTrack(track.trackId, { depthBasis: event.target.value as DepthBasis })}>
            <option value="MD">MD</option>
            <option value="TVD">TVD</option>
            <option value="TVDSS">TVDSS</option>
          </select>
        </label>
        <div className="wlv-property-note">
          Depth track width is fixed in this prototype. Curve tracks can be resized with Width − / Width + or Shift + MB1 drag.
        </div>
      </div>);
    }
    if (track.trackType === 'curve') {
        const lattice = resolveTrackLattice(track, curveCatalogItems);
        return (<div className="wlv-property-section">
        <h3>Selected Track</h3>
        <label>
          Track title
          <input value={track.title} onChange={(event) => updateTrack(track.trackId, { title: event.target.value })}/>
        </label>
        <label>
          Lattice
          <select value={lattice.lattice} onChange={(event) => updateTrack(track.trackId, {
                lattice: event.target.value as CurveTrack['lattice'],
                latticeOverride: true,
                latticeSource: 'user_override',
            })}>
            <option value="linear">Linear</option>
            <option value="logarithmic">Logarithmic</option>
          </select>
        </label>
        <button type="button" disabled={!track.latticeOverride} onClick={() => updateTrack(track.trackId, { latticeOverride: false, latticeSource: 'front_curve_default' })}>
          Reset lattice to front curve
        </button>
        <label>
          Scale mode
          <select value={track.scaleMode} onChange={(event) => updateTrack(track.trackId, { scaleMode: event.target.value as ScaleMode })}>
            <option value="shared">Shared</option>
            <option value="per_curve">Per curve</option>
            <option value="dual">Dual</option>
            <option value="normalized">Normalized</option>
          </select>
        </label>
        <label>
          Width
          <input type="number" min={CURVE_TRACK_MIN_WIDTH} max={CURVE_TRACK_MAX_WIDTH} value={track.widthPx} onChange={(event) => updateTrack(track.trackId, { widthPx: clampCurveTrackWidth(Number(event.target.value)) })}/>
        </label>
        <div className="wlv-property-note">
          Top curve header controls default lattice and front-most overpost order.
        </div>
      </div>);
    }
    return <div className="wlv-property-section">Reserved track type.</div>;
}
export function CurveProperties({ track, assignment, curveCatalogItems, updateCurveAssignment, }: {
    track: CurveTrack;
    assignment: CurveAssignment;
    curveCatalogItems: CurveCatalogItem[];
    updateCurveAssignment: (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => void;
}) {
    const curve = resolveCurveAssignmentCatalogItem(curveCatalogItems, assignment);
    if (!curve) {
        return (<div className="wlv-property-section">
        <h3>Selected Curve</h3>
        <div className="wlv-selected-curve-title">
          <span className="wlv-curve-color" style={{ background: assignment.color }}/>
          <strong>{assignment.observedMnemonic || assignment.normalizedMnemonic || 'Unavailable curve'}</strong>
          <span>Curve metadata is not available in the active well catalog.</span>
        </div>
      </div>);
    }
    return (<div className="wlv-property-section">
      <h3>Selected Curve</h3>
      <div className="wlv-selected-curve-title">
        <span className="wlv-curve-color" style={{ background: assignment.color }}/>
        <strong>{curve.mnemonic}</strong>
        <span>{curve.description}</span>
      </div>
      <label>
        Range min
        <input type="number" value={assignment.scaleMin ?? ''} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { scaleMin: Number(event.target.value) })}/>
      </label>
      <label>
        Range max
        <input type="number" value={assignment.scaleMax ?? ''} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { scaleMax: Number(event.target.value) })}/>
      </label>
      <button
        type="button"
        onClick={() => updateCurveAssignment(track.trackId, assignment.assignmentId, { rangeOverrideMode: "governed" })}
        title="Reset scale to governed KR default"
      >
        Reset to Default
      </button>
      <label>
        Color
        <input type="color" value={assignment.color} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { color: event.target.value })}/>
      </label>
      <label>
        Line style
        <select value={assignment.lineStyle} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { lineStyle: event.target.value as LineStyle })}>
          <option value="solid">Solid</option>
          <option value="dash">Dash</option>
          <option value="dot">Dot</option>
        </select>
      </label>
      <label>
        Fill
        <select value={assignment.fillSide} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { fillSide: event.target.value as FillSide })}>
          <option value="none">None</option>
          <option value="left">Left</option>
          <option value="right">Right</option>
          <option value="between">Between</option>
        </select>
      </label>
      <label>
        Fill color
        <input type="color" value="#c7e7c8" onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { fillColor: event.target.value })}/>
      </label>
      <div className="wlv-property-note">
        Curve headers can be dragged between tracks. Header stack order controls overpost order.
      </div>
    </div>);
}
export function RightPanel({ tracks, selection, curveCatalogItems, updateTrack, updateCurveAssignment, }: {
    tracks: WellLogTrack[];
    selection: SelectionRef;
    curveCatalogItems: CurveCatalogItem[];
    updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
    updateCurveAssignment: (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => void;
}) {
    const selectedTrack = tracks.find((track) => track.trackId === selection.trackId) ?? tracks[0];
    const selectedCurve = selectedTrack?.trackType === 'curve' && selection.kind === 'curve'
        ? selectedTrack.curves.find((assignment) => assignment.assignmentId === selection.assignmentId) ?? null
        : null;
    return (<aside className="wlv-right-panel">
      <div className="wlv-panel-heading">
        <h2>Properties</h2>
        <span>{selection.kind}</span>
      </div>
      {selectedTrack && selectedCurve && selectedTrack.trackType === 'curve' ? (<CurveProperties track={selectedTrack} assignment={selectedCurve} curveCatalogItems={curveCatalogItems} updateCurveAssignment={updateCurveAssignment}/>) : selectedTrack ? (<TrackProperties track={selectedTrack} curveCatalogItems={curveCatalogItems} updateTrack={updateTrack}/>) : null}
      <div className="wlv-property-section well-header">
        <h3>Well Header</h3>
        <dl>
          <dt>Well</dt><dd>{wellHeader.wellName}</dd>
          <dt>Wellbore</dt><dd>{wellHeader.wellboreName}</dd>
          <dt>Field</dt><dd>{wellHeader.field}</dd>
          <dt>Operator</dt><dd>{wellHeader.operator}</dd>
          <dt>Country</dt><dd>{wellHeader.country}</dd>
          <dt>KB</dt><dd>{wellHeader.kb}</dd>
          <dt>GL</dt><dd>{wellHeader.gl}</dd>
          <dt>Log start</dt><dd>{wellHeader.logStart}</dd>
          <dt>Log end</dt><dd>{wellHeader.logEnd}</dd>
          <dt>Source file</dt><dd>{wellHeader.sourceFile}</dd>
          <dt>TVD</dt><dd>{wellHeader.tvdStatus}</dd>
          <dt>MSI</dt><dd>{wellHeader.msiIdentity}</dd>
        </dl>
      </div>
    </aside>);
}
