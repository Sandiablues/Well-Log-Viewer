// WLV WDV presentation primitives.
// Extracted from TrackLayoutPrototype.

import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { depthUnitLabel, realCurveSamplesByCurveId, wellHeader } from '../prototype/realLasTrackLayoutData';
import { lithologyIntervals21_31, lithologySource } from '../prototype/lithologyTrackData';
import type { WdvLoadedCurveItem } from '../prototype/wdvPackageState';
import type { ManagedCurveSamplesByCurveId } from '../prototype/managedCurveSamples';
import { useTrackBodyGeometry } from '../prototype/useTrackBodyGeometry';
import type { ActiveTrackType, CurveAssignment, CurveCatalogItem, CurveTrack, DepthBasis, DepthTrack, DragCurvePayload, FillSide, LineStyle, LithologyTrack, ScaleMode, SelectionRef, WellLogTrack } from '../prototype/trackLayoutModel';
import { orderedCurves, parseDragPayload, resolveTrackLattice } from '../prototype/trackLayoutModel';
import { canonicalCurveKey } from '../identity/curveIdentityIndex';

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
};
export const CURVE_TRACK_MIN_WIDTH = 120;
export const CURVE_TRACK_MAX_WIDTH = 420;
export const CURVE_TRACK_WIDTH_STEP = 24;
export function depthRangeLabel(range: DepthViewRange): string {
    return `${range.min}–${range.max} ${depthUnitLabel} MD`;
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
export function resolveCurveAssignmentCatalogItem(catalog: CurveCatalogItem[], assignment: CurveAssignment): CurveCatalogItem | null {
    const identityCandidates = [
        assignment.curveId,
        assignment.curveUid,
        assignment.krCurveTypeId,
    ].map((value) => String(value || '').trim()).filter(Boolean);
    const directMatch = catalog.find((curve) => identityCandidates.includes(String(curve.curveId)));
    if (directMatch)
        return directMatch;
    const uidMatch = catalog.find((curve) => (Boolean(curve.curveUid) && identityCandidates.includes(String(curve.curveUid))));
    if (uidMatch)
        return uidMatch;
    const mnemonicCandidates = [
        assignment.normalizedMnemonic,
        assignment.observedMnemonic,
    ].map((value) => String(value || '').trim().toLowerCase()).filter(Boolean);
    if (mnemonicCandidates.length === 0)
        return null;
    return catalog.find((curve) => {
        const curveMnemonics = [
            curve.mnemonic,
            curve.normalizedMnemonic,
            curve.observedMnemonic,
        ].map((value) => String(value || '').trim().toLowerCase()).filter(Boolean);
        return curveMnemonics.some((value) => mnemonicCandidates.includes(value));
    }) ?? null;
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
export const TRACK_BODY_MIN_HEIGHT_PX = 650;
export const TRACK_BODY_MAX_HEIGHT_PX = 900;
export const TRACK_FOOTER_CLEARANCE_PX = 48;
export const TRACK_HEADER_TITLE_HEIGHT_PX = 24;
export const TRACK_HEADER_SUBTITLE_HEIGHT_PX = 28;
export const TRACK_CURVE_HEADER_ROW_HEIGHT_PX = 24;
export const TRACK_HEADER_BOTTOM_PADDING_PX = 8;
export const CURVE_VIEW_PADDING_X = 10;
export type MockCurveSample = {
    depth: number;
    value: number;
};
export function depthToY(depth: number, viewRange: DepthViewRange, bodyHeightPx = TRACK_BODY_HEIGHT_PX): number {
    const span = Math.max(1, viewRange.max - viewRange.min);
    const t = (depth - viewRange.min) / span;
    return clampValue(t, 0, 1) * bodyHeightPx;
}
export function yToDepth(y: number, viewRange: DepthViewRange, bodyHeight = TRACK_BODY_HEIGHT_PX): number {
    const ratio = bodyHeight <= 0 ? 0 : clampValue(y / bodyHeight, 0, 1);
    return viewRange.min + (viewRange.max - viewRange.min) * ratio;
}
export function clampValue(value: number, min: number, max: number): number {
    return Math.max(min, Math.min(max, value));
}
export function clampCurveTrackWidth(width: number): number {
    return Math.round(clampValue(width, CURVE_TRACK_MIN_WIDTH, CURVE_TRACK_MAX_WIDTH));
}
export function sharedTrackHeaderHeightPx(tracks: WellLogTrack[]): number {
    const maxCurveRows = tracks.reduce((maxRows, track) => (track.trackType === 'curve' ? Math.max(maxRows, orderedCurves(track).length) : maxRows), 0);
    const requiredCurveHeaderHeight = TRACK_HEADER_TITLE_HEIGHT_PX +
        TRACK_HEADER_SUBTITLE_HEIGHT_PX +
        maxCurveRows * TRACK_CURVE_HEADER_ROW_HEIGHT_PX +
        TRACK_HEADER_BOTTOM_PADDING_PX;
    return Math.max(TRACK_HEADER_HEIGHT_PX, requiredCurveHeaderHeight);
}
export function displayTitleForTrack(track: WellLogTrack, catalog: CurveCatalogItem[]): string {
    if (track.trackType !== 'curve')
        return track.title;
    const mnemonics = orderedCurves(track)
        .map((assignment) => catalog.find((curve) => curve.curveId === assignment.curveId)?.mnemonic ?? assignment.curveId)
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
export function makeMockCurveSamples(curve: CurveCatalogItem, _assignment: CurveAssignment, _trackPosition: number, managedSamplesByCurveId: ManagedCurveSamplesByCurveId): MockCurveSample[] {
    const managedSamples = sampleKeysForCurve(curve)
        .map((key) => managedSamplesByCurveId[key])
        .find((candidate) => candidate?.length);
    const samples = managedSamples ?? sampleKeysForCurve(curve)
        .map((key) => realCurveSamplesByCurveId[key])
        .find((candidate) => candidate?.length) ?? [];
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
    return visibleCurveSamples(curve, assignment, trackPosition, viewRange, managedSamplesByCurveId).map((sample) => ({
        depth: sample.depth,
        x: valueToX(sample.value, assignment, lattice, trackWidth),
        y: depthToY(sample.depth, viewRange, bodyHeightPx),
    }));
}
export function pathFromCurvePoints(points: CurveRenderPoint[]): string {
    return points.map((point, index) => (`${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)).join(' ');
}
export function polygonToAnchor(points: CurveRenderPoint[], anchorX: number): string {
    if (points.length < 2)
        return '';
    const first = points[0];
    const last = points[points.length - 1];
    return `${pathFromCurvePoints(points)} L ${anchorX.toFixed(1)} ${last.y.toFixed(1)} L ${anchorX.toFixed(1)} ${first.y.toFixed(1)} Z`;
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
    const pairedAtPrimaryDepths = primaryPoints
        .map((point) => interpolatePointAtDepth(pairedPoints, point.depth))
        .filter((point): point is CurveRenderPoint => Boolean(point));
    if (primaryPoints.length < 2 || pairedAtPrimaryDepths.length < 2)
        return '';
    const pairedReversed = [...pairedAtPrimaryDepths].reverse();
    return `${pathFromCurvePoints(primaryPoints)} ${pairedReversed.map((point) => `L${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ')} Z`;
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
export function CurveInventory({ availableCurves, curveUsageCounts, visibleTrackCurveIds, selectedTrackCurveIds, selectedCurveIds, assignmentEnabled, preferredInventoryTab, loadedWells, activeWell, curveRunMetadata, onActiveWellChange, onSelectCurve, onToggleCurveInSelectedTrack, }: {
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
    onActiveWellChange: (managedWellId: string) => void;
    onSelectCurve: (curveId: string) => void;
    onToggleCurveInSelectedTrack: (curveId: string, checked: boolean) => void;
}) {
    const [activeInventoryTab, setActiveInventoryTab] = useState<CurveInventoryTab>(preferredInventoryTab);
    const [expandedDuplicateGroups, setExpandedDuplicateGroups] = useState<Set<string>>(() => new Set());
    useEffect(() => {
        setActiveInventoryTab(preferredInventoryTab);
    }, [preferredInventoryTab]);
    const displayedCurves = useMemo(() => {
        if (activeInventoryTab === 'aliases')
            return [];
        if (activeInventoryTab === 'selected') {
            return availableCurves.filter((curve) => visibleTrackCurveIds.has(curveInventoryIdentityKey(curve)));
        }
        return availableCurves.filter((curve) => (curveUsageCounts.get(curveInventoryIdentityKey(curve)) ?? 0) > 0);
    }, [activeInventoryTab, availableCurves, curveUsageCounts, visibleTrackCurveIds]);
    const groups = useMemo(() => Array.from(new Set(displayedCurves.map((curve) => curve.curveClass))).filter((group) => group !== 'depth'), [displayedCurves]);
    const curvesByGroupAndMnemonic = useMemo(() => {
        const grouped = new Map<string, Map<string, CurveCatalogItem[]>>();
        displayedCurves.forEach((curve) => {
            const classKey = curve.curveClass;
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
    const toggleDuplicateGroup = (groupKey: string) => {
        setExpandedDuplicateGroups((current) => {
            const next = new Set(current);
            if (next.has(groupKey))
                next.delete(groupKey);
            else
                next.add(groupKey);
            return next;
        });
    };
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
    const renderLoadedMnemonicGroup = (group: string, mnemonic: string, curves: CurveCatalogItem[]) => {
        if (activeInventoryTab !== 'all' || curves.length === 1) {
            return curves.map((curve) => renderCurveRow(curve));
        }
        const groupKey = `${group}:${mnemonic}`;
        const assignedCount = curves.filter((curve) => visibleTrackCurveIds.has(curveInventoryIdentityKey(curve))).length;
        const checkedCount = curves.filter((curve) => selectedTrackCurveIds.has(curveInventoryIdentityKey(curve))).length;
        // WLV-UID-BLOCK5-GROUP-RENDER-REFINE:
        // Duplicate mnemonic groups are containers only. When any exact child
        // curve UID is assigned, expand the group and let the child row carry
        // the same checkbox/highlight behavior as single curve rows.
        const autoExpandedByAssignment = assignedCount > 0 || checkedCount > 0;
        const expanded = expandedDuplicateGroups.has(groupKey) || autoExpandedByAssignment;
        const units = Array.from(new Set(curves.map((curve) => curve.unit).filter(Boolean)));
        const intervals = Array.from(new Set(curves.map((curve) => curve.description).filter(Boolean)));
        const summaryText = `${curves.length} instances${intervals.length ? ` · ${intervals.length} intervals/runs` : ''}`;
        return (<div key={groupKey} className="wlv-duplicate-curve-block">
        <button type="button" className={`wlv-curve-row wlv-curve-duplicate-summary ${expanded ? 'expanded' : ''}`} onClick={() => toggleDuplicateGroup(groupKey)} aria-expanded={expanded} title="Expand duplicate mnemonic instances">
          <span className="wlv-duplicate-expander">{expanded ? '▾' : '▸'}</span>
          <strong>{mnemonic}</strong>
          <span>{summaryText}</span>
          <em>{units.length ? units.join(' / ') : ''}</em>
          <span className="wlv-curve-count" title="Loaded curve product instances">{curves.length}</span>
        </button>
        {expanded && (<div className="wlv-duplicate-instance-list">
            {curves.map((curve) => renderCurveRow(curve, { duplicateInstance: true }))}
          </div>)}
      </div>);
    };
    return (<aside className="wlv-curve-inventory">
      <div className="wlv-panel-heading">
        <h2>Curve Inventory</h2>
        <span>{inventoryCount}</span>
      </div>
      <div className="wlv-search-row">
        <input aria-label="Search curves" placeholder="Search curves..."/>
        <button type="button" title="Filter curves">Filter</button>
      </div>
      <div className="wlv-inventory-tabs">
        <button type="button" className={activeInventoryTab === 'all' ? 'active' : ''} onClick={() => setActiveInventoryTab('all')}>Loaded</button>
        <button type="button" className={activeInventoryTab === 'selected' ? 'active' : ''} onClick={() => setActiveInventoryTab('selected')}>Selected <span className="wlv-tab-count">{selectedCurveCount}</span></button>
        <button type="button" className={activeInventoryTab === 'aliases' ? 'active' : ''} onClick={() => setActiveInventoryTab('aliases')}>Aliases</button>
      </div>
      {activeInventoryTab === 'all' && (<div className="wlv-loaded-well-selector">
          <label htmlFor="wlv-loaded-well-select">Well</label>
          <select id="wlv-loaded-well-select" value={activeWell?.managedWellId ?? ''} disabled={loadedWells.length === 0} onChange={(event) => onActiveWellChange(event.target.value)}>
            {loadedWells.length === 0 ? (<option value="">No wells loaded</option>) : loadedWells.map((well) => (<option key={well.managed_well_id} value={well.managed_well_id}>
                {well.well_name} · {well.displayable_curve_count}
              </option>))}
          </select>
        </div>)}
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
      <div className="wlv-drop-help">Drag curves into curve tracks. Drag curve headers between tracks to move assignments.</div>
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
export type AddTrackDraft = {
    trackType: ActiveTrackType;
    depthBasis: DepthBasis;
    insertMode: 'before_selected' | 'after_selected' | 'far_right';
    curveSource: 'empty' | 'selected';
    latticeMode: 'auto' | 'linear' | 'logarithmic';
    scaleMode: ScaleMode;
};
export const defaultAddTrackDraft: AddTrackDraft = {
    trackType: 'curve',
    depthBasis: 'MD',
    insertMode: 'after_selected',
    curveSource: 'empty',
    latticeMode: 'auto',
    scaleMode: 'per_curve',
};
export type TrackBackdropMode = 'light' | 'dark';
export function Toolbar({ selectedTrack, pendingAddTrackCurveCount, viewDepthRange, fullDepthRange, viewDepthReadoutEnabled, intervalZoomActive, goToDepthValue, onGoToDepthValueChange, trackBackdropMode, onTrackBackdropModeChange, onAddTrack, onDeleteTrack, onMoveSelectedTrack, canMoveSelectedTrackLeft, canMoveSelectedTrackRight, canAdjustSelectedCurveTrackWidthDown, canAdjustSelectedCurveTrackWidthUp, onAdjustSelectedCurveTrackWidth, onResetCurveTrackWidths, onZoomIn, onZoomOut, onPreviousView, onFitDepth, onSpecifyDepthRange, onResetView, onToggleIntervalZoom, onGoToDepth, onAddTrackCurveSelectionModeChange, layoutRecommendations, layoutRecommendationsLoading, layoutRecommendationsError, selectedLayoutRecommendationKey, onLayoutRecommendationChange, onRefreshLayoutRecommendations, }: {
    selectedTrack: WellLogTrack | null;
    pendingAddTrackCurveCount: number;
    viewDepthRange: DepthViewRange;
    fullDepthRange: DepthViewRange;
    viewDepthReadoutEnabled: boolean;
    intervalZoomActive: boolean;
    goToDepthValue: string;
    onGoToDepthValueChange: (value: string) => void;
    trackBackdropMode: TrackBackdropMode;
    onTrackBackdropModeChange: (mode: TrackBackdropMode) => void;
    onAddTrack: (draft: AddTrackDraft) => void;
    onDeleteTrack: () => void;
    onMoveSelectedTrack: (direction: -1 | 1) => void;
    canMoveSelectedTrackLeft: boolean;
    canMoveSelectedTrackRight: boolean;
    canAdjustSelectedCurveTrackWidthDown: boolean;
    canAdjustSelectedCurveTrackWidthUp: boolean;
    onAdjustSelectedCurveTrackWidth: (delta: number) => void;
    onResetCurveTrackWidths: () => void;
    onZoomIn: () => void;
    onZoomOut: () => void;
    onPreviousView: () => void;
    onFitDepth: () => void;
    onSpecifyDepthRange: (range: DepthViewRange) => void;
    onResetView: () => void;
    onToggleIntervalZoom: () => void;
    onGoToDepth: () => void;
    onAddTrackCurveSelectionModeChange: (active: boolean) => void;
    layoutRecommendations: WdvTemplateRecommendationItem[];
    layoutRecommendationsLoading: boolean;
    layoutRecommendationsError: string | null;
    selectedLayoutRecommendationKey: string;
    onLayoutRecommendationChange: (templateKey: string) => void;
    onRefreshLayoutRecommendations: () => void;
}) {
    const [builderOpen, setBuilderOpen] = useState(false);
    const [draft, setDraft] = useState<AddTrackDraft>(defaultAddTrackDraft);
    const [panelPosition, setPanelPosition] = useState({ top: 128, left: 360 });
    const [rangeEditorOpen, setRangeEditorOpen] = useState(false);
    const [rangeTopValue, setRangeTopValue] = useState(String(Math.round(viewDepthRange.min)));
    const [rangeBaseValue, setRangeBaseValue] = useState(String(Math.round(viewDepthRange.max)));
    const specifyRangeButtonRef = useRef<HTMLButtonElement | null>(null);
    const specifyRangePopoverRef = useRef<HTMLDivElement | null>(null);
    const [rangePopoverPosition, setRangePopoverPosition] = useState({ top: 0, left: 0 });
    const dragStateRef = useRef<{
        startClientX: number;
        startClientY: number;
        startLeft: number;
        startTop: number;
    } | null>(null);
    useEffect(() => {
        if (rangeEditorOpen)
            return;
        setRangeTopValue(String(Math.round(viewDepthRange.min)));
        setRangeBaseValue(String(Math.round(viewDepthRange.max)));
    }, [rangeEditorOpen, viewDepthRange.min, viewDepthRange.max]);
    const updateSpecifiedRangePopoverPosition = () => {
        const button = specifyRangeButtonRef.current;
        if (!button)
            return;
        const rect = button.getBoundingClientRect();
        const popoverWidth = 292;
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
    const addTrackLabel = 'Add track';
    const eligibleLayoutRecommendations = layoutRecommendations.filter((item) => item.is_eligible);
    const layoutRecommendationOptions = eligibleLayoutRecommendations.length > 0 ? eligibleLayoutRecommendations : layoutRecommendations;
    const layoutPresetPlaceholder = layoutRecommendationsLoading
        ? 'Loading KR presets...'
        : layoutRecommendationsError
            ? 'Template service unavailable'
            : layoutRecommendationOptions.length > 0
                ? 'Layout Preset ▾'
                : 'No KR presets available';
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
          <button type="button" disabled title="Reserved for raster/core/lithology artifacts">Raster</button>
          <button type="button" disabled title="Reserved for marker datasets">Marker</button>
          <button type="button" disabled title="Reserved for interval datasets">Interval</button>
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

      <section className="builder-section">
        <div className="builder-label">Insert position</div>
        <select value={draft.insertMode} onChange={(event) => updateDraft({ insertMode: event.target.value as AddTrackDraft['insertMode'] })}>
          <option value="before_selected">Before selected track</option>
          <option value="after_selected">After selected track</option>
          <option value="far_right">Far right</option>
        </select>
      </section>

      <div className="builder-actions">
        <button type="button" onClick={closeAddTrackBuilder}>Cancel</button>
        <button type="button" className="builder-primary" onClick={() => {
            onAddTrack(draft);
            closeAddTrackBuilder();
        }}>
          {addTrackLabel}
        </button>
      </div>
    </div>, document.body) : null;
    return (<div className="wlv-track-toolbar" aria-label="Well log viewer toolbar">
      <div className="wlv-toolbar-group wlv-toolbar-group-track">
        <span>Add / Delete Tracks</span>
        <div className="wlv-toolbar-actions">
          <div className="wlv-add-track-control">
            <button type="button" className="wlv-add-track-button" onClick={toggleAddTrackBuilder} aria-expanded={builderOpen}>
              + Add Track ▾
            </button>
          </div>
          {addTrackBuilder}
          <button type="button" disabled={!selectedTrack} onClick={onDeleteTrack}>Delete</button>
        </div>
      </div>

      <div className="wlv-toolbar-group wlv-toolbar-group-arrange">
        <span>Track Layout</span>
        <div className="wlv-toolbar-actions">
          <button type="button" disabled={!canMoveSelectedTrackLeft} title={selectedTrack ? 'Move selected track left' : 'Select a track first'} aria-label="Move selected track left" onClick={() => onMoveSelectedTrack(-1)}>
            ←
          </button>
          <button type="button" disabled={!canMoveSelectedTrackRight} title={selectedTrack ? 'Move selected track right' : 'Select a track first'} aria-label="Move selected track right" onClick={() => onMoveSelectedTrack(1)}>
            →
          </button>
          <button type="button" disabled={!canAdjustSelectedCurveTrackWidthDown} title={selectedTrack?.trackType === 'curve' ? 'Contract selected curve track' : 'Select a curve track first'} onClick={() => onAdjustSelectedCurveTrackWidth(-CURVE_TRACK_WIDTH_STEP)}>
            − Width
          </button>
          <button type="button" disabled={!canAdjustSelectedCurveTrackWidthUp} title={selectedTrack?.trackType === 'curve' ? 'Widen selected curve track' : 'Select a curve track first'} onClick={() => onAdjustSelectedCurveTrackWidth(CURVE_TRACK_WIDTH_STEP)}>
            + Width
          </button>
          <button type="button" onClick={onResetCurveTrackWidths} title="Reset all curve tracks to uniform width; depth tracks remain unchanged">
            Reset
          </button>
          <select aria-label="Layout preset" className="wlv-layout-preset-select" value={selectedLayoutRecommendationKey} disabled={layoutRecommendationsLoading || layoutRecommendationOptions.length === 0} title={layoutRecommendationsError ?? 'Backend-approved KR layout presets'} onChange={(event) => onLayoutRecommendationChange(event.target.value)}>
            <option value="">{layoutPresetPlaceholder}</option>
            {layoutRecommendationOptions.map((item) => (<option key={item.template_key} value={item.template_key}>
                {item.template_label}
              </option>))}
          </select>
          <button type="button" className="wlv-layout-preset-refresh" title="Refresh backend KR template recommendations" aria-label="Refresh backend KR template recommendations" disabled={layoutRecommendationsLoading} onClick={onRefreshLayoutRecommendations}>
            ↻
          </button>
        </div>
      </div>

      <div className="wlv-toolbar-group wlv-toolbar-group-view">
        <span>Zoom / View</span>
        <div className="wlv-toolbar-actions">
          <button type="button" title="Zoom Out" aria-label="Zoom Out" onClick={onZoomOut}>−</button>
          <button type="button" title="Zoom In" aria-label="Zoom In" onClick={onZoomIn}>+</button>
          <button type="button" className={intervalZoomActive ? 'active' : ''} title="Drag on the log to zoom to a depth interval" onClick={onToggleIntervalZoom}>
            Drag Zoom
          </button>
          <div className="wlv-specified-range-control">
            <button ref={specifyRangeButtonRef} type="button" className={rangeEditorOpen ? 'active' : ''} onClick={openSpecifiedRangeEditor} title="Specify top and base measured depth range">
              Specify Range
            </button>
            {rangeEditorOpen ? createPortal(<div ref={specifyRangePopoverRef} className="wlv-specified-range-popover wlv-specified-range-popover-portal" role="dialog" aria-label="Specify drag zoom" style={{ top: rangePopoverPosition.top, left: rangePopoverPosition.left }}>
                <label>
                  <span>Top MD</span>
                  <input autoFocus value={rangeTopValue} onChange={(event) => setRangeTopValue(event.target.value)} onKeyDown={(event) => {
                if (event.key === 'Enter')
                    applySpecifiedRange();
                if (event.key === 'Escape')
                    setRangeEditorOpen(false);
            }}/>
                </label>
                <label>
                  <span>Base MD</span>
                  <input value={rangeBaseValue} onChange={(event) => setRangeBaseValue(event.target.value)} onKeyDown={(event) => {
                if (event.key === 'Enter')
                    applySpecifiedRange();
                if (event.key === 'Escape')
                    setRangeEditorOpen(false);
            }}/>
                </label>
                <div className="wlv-specified-range-actions">
                  <button type="button" onClick={applySpecifiedRange}>Apply</button>
                  <button type="button" onClick={() => setRangeEditorOpen(false)}>Cancel</button>
                </div>
              </div>, document.body) : null}
          </div>
          <button type="button" onClick={onPreviousView}>Prev</button>
          <button type="button" onClick={onFitDepth}>Full</button>
          <button type="button" onClick={onResetView}>Reset</button>
          {viewDepthReadoutEnabled ? (<strong className="wlv-depth-readout" title={`Full range ${depthRangeLabel(fullDepthRange)}`}>
              View: {depthRangeLabel(viewDepthRange)}
            </strong>) : null}
          <input className="wlv-go-to-depth-input" aria-label="Go to depth" value={goToDepthValue} placeholder="Go to MD" onChange={(event) => onGoToDepthValueChange(event.target.value)} onKeyDown={(event) => {
            if (event.key === 'Enter')
                onGoToDepth();
        }}/>
          <button type="button" className={`wlv-go-to-depth-button ${goToDepthValue.trim() ? 'ready' : ''}`} onClick={onGoToDepth} title="Go to entered measured depth" aria-label="Go to entered measured depth">
            ✓
          </button>
        </div>
      </div>

      <div className="wlv-toolbar-spacer"/>

      <div className="wlv-toolbar-group wlv-toolbar-group-backdrop wlv-toolbar-icon-only">
        <div className="wlv-toolbar-actions">
          <button type="button" className="wlv-backdrop-toggle" onClick={() => onTrackBackdropModeChange(trackBackdropMode === 'light' ? 'dark' : 'light')} aria-pressed={trackBackdropMode === 'dark'} title={trackBackdropMode === 'light' ? 'Switch to dark backdrop' : 'Switch to light backdrop'} aria-label={trackBackdropMode === 'light' ? 'Switch to dark backdrop' : 'Switch to light backdrop'}>
            ◐
          </button>
        </div>
      </div>
    </div>);
}
export function CurveHeaderStack({ track, curveCatalogItems, selectedAssignmentId, openMenuAssignmentId, onSelectCurve, onReorderCurve, onMoveCurveToTrack, onOpenCurveMenu, onCloseCurveMenu, onRemoveCurveFromTrack, }: {
    track: CurveTrack;
    curveCatalogItems: CurveCatalogItem[];
    selectedAssignmentId: string | null;
    openMenuAssignmentId: string | null;
    onSelectCurve: (trackId: string, assignmentId: string) => void;
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
            <span className="wlv-curve-color" style={{ background: assignment.color }}/>
            <strong>{curve.mnemonic}</strong>
            <span>{assignment.scaleMinLabel ?? (assignment.scaleMin !== null ? String(assignment.scaleMin) : '?')}—{assignment.scaleMaxLabel ?? (assignment.scaleMax !== null ? String(assignment.scaleMax) : '?')}</span>
            <em>{curve.unit}</em>
            {openMenuAssignmentId === assignment.assignmentId && (<CurveHeaderActionMenuPortal trackId={track.trackId} assignmentId={assignment.assignmentId} assignmentIndex={index} assignmentCount={ordered.length} onSelectCurve={onSelectCurve} onReorderCurve={onReorderCurve} onCloseCurveMenu={onCloseCurveMenu} onRemoveCurveFromTrack={onRemoveCurveFromTrack}/>)}
          </div>);
        })}
    </div>);
}
export function DepthTrackView({ track, depthTicks, viewDepthRange, trackBodyHeightPx, }: {
    track: DepthTrack;
    depthTicks: number[];
    viewDepthRange: DepthViewRange;
    trackBodyHeightPx: number;
}) {
    return (<div className="wlv-depth-track-body">
      {depthTicks.map((depth) => {
            const y = depthToY(depth, viewDepthRange, trackBodyHeightPx);
            return (<div key={`${track.trackId}-${depth}`} className="wlv-depth-tick" style={{ top: y }}>
            <span>{depth}</span>
          </div>);
        })}
    </div>);
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
export function CurveTrackView({ track, depthTicks, viewDepthRange, trackBodyHeightPx, managedSamplesByCurveId, managedSampleErrorsByCurveId, curveCatalogItems, }: {
    track: CurveTrack;
    depthTicks: number[];
    viewDepthRange: DepthViewRange;
    trackBodyHeightPx: number;
    managedSamplesByCurveId: ManagedCurveSamplesByCurveId;
    managedSampleErrorsByCurveId: Record<string, string>;
    curveCatalogItems: CurveCatalogItem[];
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
        .map((assignment) => managedSampleErrorsByCurveId[assignment.curveId])
        .filter((message, index, all): message is string => Boolean(message) && all.indexOf(message) === index);
    return (<svg className={`wlv-curve-track-svg ${lattice.lattice}`} viewBox={`0 0 ${trackWidth} ${trackBodyHeightPx}`} preserveAspectRatio="none">
      <defs>
        <pattern id={`infill-hatch-${track.trackId}`} width="8" height="8" patternUnits="userSpaceOnUse">
          <path d="M -2 8 L 8 -2 M 0 10 L 10 0" stroke="currentColor" strokeWidth="1" opacity="0.55"/>
        </pattern>
        <pattern id={`infill-dots-${track.trackId}`} width="8" height="8" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.2" fill="currentColor" opacity="0.5"/>
        </pattern>
      </defs>
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
      {depthTicks.map((depth) => {
            const y = depthToY(depth, viewDepthRange, trackBodyHeightPx);
            return <line key={depth} x1="0" x2={trackWidth} y1={y} y2={y} stroke="#aeb8c5" strokeWidth="1"/>;
        })}
      {backToFront.map((assignment, index) => {
            const curve = resolveCurveAssignmentCatalogItem(curveCatalogItems, assignment);
            if (!curve)
                return null;
            const points = curveRenderPoints(curve, assignment, index, viewDepthRange, lattice.lattice, trackWidth, trackBodyHeightPx, managedSamplesByCurveId);
            const path = pathFromCurvePoints(points);
            const pairedAssignment = assignment.pairedCurveId
                ? ordered.find((candidate) => candidate.assignmentId === assignment.pairedCurveId)
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
            {assignment.fillSide !== 'none' && baseFillPath && !intervalInfillActive ? (<path d={baseFillPath} fill={svgFillForAssignment(assignment, null, track.trackId)} stroke="none" opacity={fillOpacityForAssignment(assignment)}/>) : null}
            {intervalInfillActive ? visibleLithologyIntervals.map((interval) => {
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
      {missingSampleMessages.length > 0 ? (<text x={trackWidth / 2} y={24} textAnchor="middle" className="wlv-curve-sample-error">
          Curve samples unavailable
        </text>) : null}
    </svg>);
}
export function CurveHeaderActionMenuPortal({ trackId, assignmentId, assignmentIndex, assignmentCount, onSelectCurve, onReorderCurve, onCloseCurveMenu, onRemoveCurveFromTrack, }: {
    trackId: string;
    assignmentId: string;
    assignmentIndex: number;
    assignmentCount: number;
    onSelectCurve: (trackId: string, assignmentId: string) => void;
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
            onSelectCurve(trackId, assignmentId);
            onCloseCurveMenu();
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
export function TrackView({ track, sharedHeaderHeightPx, selected, selectedAssignmentId, openCurveMenu, depthTicks, viewDepthRange, onSelectTrack, onSelectCurve, onReorderCurve, onMoveCurveToTrack, onOpenCurveMenu, onCloseCurveMenu, onRemoveCurveFromTrack, onStartCurveTrackResize, resizingTrackId, trackBodyHeightPx, managedSamplesByCurveId, managedSampleErrorsByCurveId, curveCatalogItems, }: {
    track: WellLogTrack;
    sharedHeaderHeightPx: number;
    selected: boolean;
    selectedAssignmentId: string | null;
    openCurveMenu: {
        trackId: string;
        assignmentId: string;
    } | null;
    depthTicks: number[];
    viewDepthRange: DepthViewRange;
    onSelectTrack: (trackId: string) => void;
    onSelectCurve: (trackId: string, assignmentId: string) => void;
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
}) {
    const widthPx = track.trackType === 'curve' ? clampCurveTrackWidth(track.widthPx) : track.widthPx;
    const width = `${widthPx}px`;
    const isCurveTrack = track.trackType === 'curve';
    const lattice = isCurveTrack ? resolveTrackLattice(track, curveCatalogItems) : null;
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
        }} onClick={() => {
            onCloseCurveMenu();
            onSelectTrack(track.trackId);
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
      <header className="wlv-track-header" style={{ height: `${sharedHeaderHeightPx}px`, minHeight: `${sharedHeaderHeightPx}px`, flexBasis: `${sharedHeaderHeightPx}px` }}>
        <div className="wlv-track-title-row">
          <strong>{displayTitleForTrack(track, curveCatalogItems)}</strong>
          <span>T{track.trackIndex + 1}</span>
        </div>
        {track.trackType === 'depth' && (<div className="wlv-depth-header">{track.depthBasis} · {track.unit}</div>)}
        {track.trackType === 'lithology' && (<div className="wlv-lithology-header">{lithologySource.name} · {track.wellName}</div>)}
        {track.trackType === 'curve' && (<>
            <div className="wlv-lattice-badge">
              {lattice?.lattice} · {lattice?.source === 'user_override' ? 'override' : `front ${lattice?.frontCurve?.mnemonic ?? 'none'}`} · {widthPx}px
            </div>
            <CurveHeaderStack track={track} curveCatalogItems={curveCatalogItems} selectedAssignmentId={selectedAssignmentId} openMenuAssignmentId={openCurveMenu?.trackId === track.trackId ? openCurveMenu?.assignmentId ?? null : null} onSelectCurve={onSelectCurve} onReorderCurve={onReorderCurve} onMoveCurveToTrack={onMoveCurveToTrack} onOpenCurveMenu={onOpenCurveMenu} onCloseCurveMenu={onCloseCurveMenu} onRemoveCurveFromTrack={onRemoveCurveFromTrack}/>
          </>)}
      </header>
      <div className="wlv-track-body" style={{ height: `${trackBodyHeightPx}px`, minHeight: `${trackBodyHeightPx}px`, flexBasis: `${trackBodyHeightPx}px` }}>
        {track.trackType === 'depth' ? <DepthTrackView track={track} depthTicks={depthTicks} viewDepthRange={viewDepthRange} trackBodyHeightPx={trackBodyHeightPx}/> : null}
        {track.trackType === 'lithology' ? <LithologyTrackView track={track} viewDepthRange={viewDepthRange} trackBodyHeightPx={trackBodyHeightPx}/> : null}
        {track.trackType === 'curve' ? (<CurveTrackView track={track} depthTicks={depthTicks} viewDepthRange={viewDepthRange} trackBodyHeightPx={trackBodyHeightPx} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={curveCatalogItems}/>) : null}
      </div>
    </section>);
}
export function TrackCanvas({ tracks, selection, openCurveMenu, depthTicks, viewDepthRange, goToDepthMarker, intervalZoomActive, intervalSelection, dragPanActive, onSelectTrack, onSelectCurve, onReorderCurve, onMoveCurveToTrack, onOpenCurveMenu, onCloseCurveMenu, onRemoveCurveFromTrack, onStartIntervalSelection, onUpdateIntervalSelection, onArmIntervalSelection, onCompleteIntervalSelection, onStartDragPan, onUpdateDragPan, onEndDragPan, onStartCurveTrackResize, resizingTrackId, managedSamplesByCurveId, managedSampleErrorsByCurveId, curveCatalogItems, }: {
    tracks: WellLogTrack[];
    selection: SelectionRef;
    openCurveMenu: {
        trackId: string;
        assignmentId: string;
    } | null;
    depthTicks: number[];
    viewDepthRange: DepthViewRange;
    goToDepthMarker: number | null;
    intervalZoomActive: boolean;
    intervalSelection: IntervalSelectionState | null;
    dragPanActive: boolean;
    onSelectTrack: (trackId: string) => void;
    onSelectCurve: (trackId: string, assignmentId: string) => void;
    onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
    onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
    onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
    onCloseCurveMenu: () => void;
    onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
    onStartIntervalSelection: (depth: number, y: number) => void;
    onUpdateIntervalSelection: (depth: number, y: number) => void;
    onArmIntervalSelection: (depth: number, y: number) => void;
    onCompleteIntervalSelection: (depth: number, y: number) => void;
    onStartDragPan: (startY: number) => void;
    onUpdateDragPan: (currentY: number, canvasHeight: number) => void;
    onEndDragPan: () => void;
    onStartCurveTrackResize: (trackId: string, startX: number, startWidth: number) => void;
    resizingTrackId: string | null;
    managedSamplesByCurveId: ManagedCurveSamplesByCurveId;
    managedSampleErrorsByCurveId: Record<string, string>;
    curveCatalogItems: CurveCatalogItem[];
}) {
    const canvasRef = useRef<HTMLElement | null>(null);
    const orderedTracks = sortTracks(tracks);
    const sharedHeaderHeight = sharedTrackHeaderHeightPx(orderedTracks);
    const { setContainerRef, trackBodyHeightPx } = useTrackBodyGeometry({
        headerHeightPx: sharedHeaderHeight,
        fallbackBodyHeightPx: TRACK_BODY_HEIGHT_PX,
        minBodyHeightPx: TRACK_BODY_MIN_HEIGHT_PX,
        maxBodyHeightPx: TRACK_BODY_MAX_HEIGHT_PX,
        footerClearancePx: TRACK_FOOTER_CLEARANCE_PX,
        stripPaddingPx: TRACK_STRIP_PADDING_PX,
    });
    const canvasRectFromCanvas = () => canvasRef.current?.getBoundingClientRect() ?? null;
    const bodyRectFromCanvas = () => {
        return canvasRef.current?.querySelector('.wlv-track-body')?.getBoundingClientRect() ?? null;
    };
    const sharedBodyTopOffset = () => {
        const canvasRect = canvasRectFromCanvas();
        const bodyRect = bodyRectFromCanvas();
        if (canvasRect && bodyRect)
            return bodyRect.top - canvasRect.top;
        return TRACK_STRIP_PADDING_PX + sharedHeaderHeight;
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
        return pointFromClientY(event.clientY);
    };
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
    const sharedGoToMarkerY = typeof goToDepthMarker === 'number'
        && goToDepthMarker >= viewDepthRange.min
        && goToDepthMarker <= viewDepthRange.max
        ? bodyTopOffset + depthToY(goToDepthMarker, viewDepthRange, trackBodyHeightPx)
        : null;
    const sharedDepthGridLines = depthTicks.map((depth) => ({
        depth,
        y: bodyTopOffset + depthToY(depth, viewDepthRange, trackBodyHeightPx),
    }));
    return (<main ref={(node) => {
            canvasRef.current = node;
            setContainerRef(node);
        }} className={`wlv-track-canvas ${intervalZoomActive ? 'interval-zoom-active' : ''} ${dragPanActive ? 'drag-pan-active' : ''} ${resizingTrackId ? 'curve-resize-active' : ''}`} onMouseDownCapture={(event) => {
            if (intervalZoomActive) {
                event.preventDefault();
                event.stopPropagation();
                const point = pointFromEvent(event);
                if (intervalSelection && !intervalSelection.dragging) {
                    onCompleteIntervalSelection(point.depth, point.y);
                    return;
                }
                onStartIntervalSelection(point.depth, point.y);
                return;
            }
            if (!shouldStartDragPan(event))
                return;
            event.preventDefault();
            event.stopPropagation();
            const { y } = pointFromEvent(event);
            onStartDragPan(y);
        }} onMouseMoveCapture={(event) => {
            if (intervalZoomActive && intervalSelection?.dragging) {
                event.preventDefault();
                event.stopPropagation();
                const point = pointFromEvent(event);
                onUpdateIntervalSelection(point.depth, point.y);
                return;
            }
            // Drag-pan movement is handled by document-level listeners once MB1 drag starts.
        }} onMouseUpCapture={(event) => {
            if (intervalZoomActive && intervalSelection?.dragging) {
                event.preventDefault();
                event.stopPropagation();
                const point = pointFromEvent(event);
                if (Math.abs(point.y - intervalSelection.startY) >= 8) {
                    onCompleteIntervalSelection(point.depth, point.y);
                    return;
                }
                onArmIntervalSelection(point.depth, point.y);
                return;
            }
            // Drag-pan mouseup is handled by document-level listeners once MB1 drag starts.
        }}>
      {intervalBand && (<div className={`wlv-interval-selection-band ${intervalSelection?.dragging ? 'dragging' : 'armed'}`} style={{ top: bodyTopOffset + intervalBand.top, height: intervalBand.height }}>
          <span>
            {intervalSelection?.dragging
                ? `${Math.round(intervalBand.startDepth)}–${Math.round(intervalBand.endDepth)} m`
                : intervalSelection
                    ? `Start ${Math.round(intervalSelection.startDepth)} m — click end depth`
                    : 'Click first depth to start interval'}
          </span>
        </div>)}
      <div className="wlv-shared-depth-grid-overlay" aria-hidden="true">
        {sharedDepthGridLines.map(({ depth, y }) => (<div key={`shared-grid-${depth}`} className="wlv-shared-depth-grid-line" style={{ top: y }}/>))}
      </div>
      {sharedGoToMarkerY !== null && (<div className="wlv-shared-go-to-depth-marker" style={{ top: sharedGoToMarkerY }} aria-hidden="true">
          <span>{Math.round(goToDepthMarker as number)} m</span>
        </div>)}
      <div className="wlv-track-strip">
        {orderedTracks.map((track) => (<TrackView key={track.trackId} track={track} sharedHeaderHeightPx={sharedHeaderHeight} selected={selection.kind === 'track' && selection.trackId === track.trackId || selection.kind === 'curve' && selection.trackId === track.trackId} selectedAssignmentId={selection.kind === 'curve' && selection.trackId === track.trackId ? selection.assignmentId : null} openCurveMenu={openCurveMenu} depthTicks={depthTicks} viewDepthRange={viewDepthRange} onSelectTrack={onSelectTrack} onSelectCurve={onSelectCurve} onReorderCurve={onReorderCurve} onMoveCurveToTrack={onMoveCurveToTrack} onOpenCurveMenu={onOpenCurveMenu} onCloseCurveMenu={onCloseCurveMenu} onRemoveCurveFromTrack={onRemoveCurveFromTrack} onStartCurveTrackResize={onStartCurveTrackResize} resizingTrackId={resizingTrackId} trackBodyHeightPx={trackBodyHeightPx} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={curveCatalogItems}/>))}
      </div>
    </main>);
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
        onClick={() => updateCurveAssignment(track.trackId, assignment.assignmentId, { resetScaleToGovernedDefault: true })}
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
