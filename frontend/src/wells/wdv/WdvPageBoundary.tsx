import { type Dispatch, type ReactNode, type SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { curveCatalog } from '../prototype/realLasTrackLayoutData';
import { WellLogPropertiesPanelSlot } from '../prototype/WellLogPropertiesPanelSlot';
import { loadBackendViewerPackageWithFallback, type BackendViewerPackageLoadResult } from '../prototype/backendViewerPackageAdapter';
import { buildWdvPackageState, emptyWdvPackageState, type WdvLoadedCurveItem, type WdvPackageState } from '../prototype/wdvPackageState';
import { indexManagedCurveSamples, parseManagedCurveSamples, type ManagedCurveSampleContractsByCurveId, type ManagedCurveSampleLoadResult, type ManagedCurveSamplesByCurveId, type ManagedCurveSamplesPayload } from '../prototype/managedCurveSamples';
import type { CurveAssignment, CurveCatalogItem, DragCurvePayload, SelectionRef, WellLogTrack } from '../prototype/trackLayoutModel';
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
import { AddTrackDraft, CURVE_TRACK_MAX_WIDTH, CURVE_TRACK_MIN_WIDTH, CurveInventory, CurveInventoryWellContext, DepthViewRange, IntervalSelectionState, RightPanel, Toolbar, TrackBackdropMode, TrackCanvas, WdvCanonicalTemplateApplySession, WdvRecommendedCurve, WdvTemplateRecommendationItem, WdvTemplateRecommendationModal, WdvWorkspaceLoadedWell, buildWdvTemplateRecommendationRequest, clampCurveTrackWidth, clampValue, fetchWlvJson, sortTracks } from './WdvPresentationPrimitives';
import { useWdvLayoutSource } from './useWdvLayoutSource';
import { replaceManagedWellDepthRanges } from './depthRangeState';
import type { CanonicalLayoutResult } from './useWdvLayoutSource';
import { buildCompleteLasLoadRequest, buildCompleteLasLoadUrl } from './completeLasWorkflow';
import { openQuickViewFile, sendQuickViewFileToWsi, isQuickViewFile, type QuickViewCurve, type QuickViewPackage, type QuickViewMetadataValue, type QuickViewQaqcFlag } from './quickViewWorkflow';
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
} from './curveFillV2';

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

type DragPanState = {
    startY: number;
    startRange: DepthViewRange;
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

const GO_TO_REVIEW_WINDOW_M = 600;

function clampDepthRange(range: DepthViewRange, fullRange: DepthViewRange): DepthViewRange {
    const span = Math.max(50, range.max - range.min);
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
        min: Math.round(min),
        max: Math.round(max),
    };
}

function makeDepthTicks(range: DepthViewRange, count = 11): number[] {
    const safeCount = Math.max(2, count);
    const step = (range.max - range.min) / (safeCount - 1);
    return Array.from({ length: safeCount }, (_, index) => Math.round(range.min + step * index));
}

function isAbortError(error: unknown): boolean {
    return error instanceof DOMException && error.name === 'AbortError';
}

async function mapWithConcurrency<TInput, TOutput>(items: TInput[], concurrency: number, worker: (item: TInput) => Promise<TOutput>): Promise<TOutput[]> {
    if (items.length === 0)
        return [];
    const results = new Array<TOutput>(items.length);
    let nextIndex = 0;
    const runWorker = async () => {
        while (nextIndex < items.length) {
            const currentIndex = nextIndex;
            nextIndex += 1;
            results[currentIndex] = await worker(items[currentIndex]);
        }
    };
    const workerCount = Math.max(1, Math.min(concurrency, items.length));
    await Promise.all(Array.from({ length: workerCount }, () => runWorker()));
    return results;
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

export function unionDepthRanges(ranges: DepthViewRange[], fallback: DepthViewRange): DepthViewRange {
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

function moveTrackById(tracks: WellLogTrack[], trackId: string, direction: -1 | 1): WellLogTrack[] {
    const ordered = sortTracks(tracks);
    const fromIndex = ordered.findIndex((track) => track.trackId === trackId);
    if (fromIndex < 0)
        return tracks;
    const toIndex = fromIndex + direction;
    if (toIndex < 0 || toIndex >= ordered.length)
        return tracks;
    const next = [...ordered];
    const [movingTrack] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, movingTrack);
    return reindexTracksInCurrentOrder(next);
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
  scale_type: string | null;
  scale_direction: string | null;
  color: string | null;
  unit: string | null;
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
  track_name: string;
  track_type: string;
  width_px?: number | null;
  lattice?: string | null;
  lattice_source?: string | null;
  lattice_override?: boolean | null;
  scale_mode?: string | null;
  depth_basis?: string | null;
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
export function canonicalRangeOverrideCommandBody(
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

  const hasRangeIntent =
    patch.rangeOverrideMode !== undefined
    || patch.manualScaleMin !== undefined
    || patch.manualScaleMax !== undefined
    || patch.scaleMin !== undefined
    || patch.scaleMax !== undefined;

  if (!hasRangeIntent) return Object.keys(body).length > 0 ? body : null;

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

export function canonicalCommandRequestBody(
  expectedRevision: number,
  body: Record<string, unknown>,
): Record<string, unknown> {
  return {
    ...body,
    expected_revision: expectedRevision,
  };
}

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
/** @internal exported for unit tests */
export function frontendTracksFromCanonicalSession(
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
        : trackType === 'depth' ? 86 : CURVE_TRACK_RESET_WIDTH;

    if (trackType === 'depth') {
      const db = rawTrack.depth_basis;
      result.push({
        trackId,
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

    if (trackType !== 'curve') return;

    const lattice = rawTrack.lattice === 'logarithmic' ? 'logarithmic' : 'linear';
    const ls = rawTrack.lattice_source ?? 'front_curve_default';
    const latticeSource =
      ls === 'user_override' || ls === 'template' ? ls : 'front_curve_default';

    const assignments: CurveAssignment[] = rawTrack.assignments
      .sort((a, b) => a.stack_index - b.stack_index)
      .flatMap((raw, assignIndex) => {
        const curve = catalog.find(
          (item) => item.curveUid === raw.managed_curve_uid,
        );
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
          scaleType,
          scaleDirection,
          color: raw.color ?? fallback.color,
          unit: raw.unit,
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

export function WdvPageBoundary({ managedViewerWell, setManagedViewerWell }: WdvPageBoundaryProps) {
  const managedViewerWellId = managedViewerWell?.managedWellId ?? null;
  const managedViewerWellUid = managedViewerWell?.managedWellUid ?? null;
  const activeView = 'log-viewer' as const;
  const [wdvWorkspace, setWdvWorkspace] = useState<WdvWorkspaceState | null>(null);
  const [wdvWorkspaceError, setWdvWorkspaceError] = useState<string | null>(null);
  const [, setViewerPackageLoad] = useState<BackendViewerPackageLoadResult | null>(null);
  const [wdvPackageState, setWdvPackageState] = useState<WdvPackageState>(() => emptyWdvPackageState());
  const [wdvIdentityMetadata, setWdvIdentityMetadata] = useState<WdvIdentityMetadataContract | null>(null);
  const [wdvIdentityMetadataError, setWdvIdentityMetadataError] = useState<string | null>(null);
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
  const sampleLoadAbortRef = useRef<AbortController | null>(null);
  const sampleLoadGenerationRef = useRef(0);
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
      setWdvPackageState(emptyWdvPackageState());
      void loadBackendViewerPackageWithFallback(managedViewerWellId, { signal: controller.signal })
          .then((result) => {
          if (controller.signal.aborted || viewerPackageGenerationRef.current !== generation)
              return;
          setViewerPackageLoad(result);
          setWdvPackageState(buildWdvPackageState(result.package));
      })
          .catch((error) => {
          if (controller.signal.aborted || viewerPackageGenerationRef.current !== generation || isAbortError(error))
              return;
          setViewerPackageLoad({
              source: 'prototype_fallback',
              package: null,
              warning: error instanceof Error ? error.message : 'Viewer package unavailable',
          });
          setWdvPackageState(emptyWdvPackageState());
      });
      return () => {
          controller.abort();
          if (viewerPackageAbortRef.current === controller)
              viewerPackageAbortRef.current = null;
      };
  }, [activeView, managedViewerWellId, viewerPackageRefreshRevision]);
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
  const [fullDepthRangesByWellUid, setFullDepthRangesByWellUid] = useState<Record<string, DepthViewRange>>({});
  const [viewDepthRange, setViewDepthRange] = useState<DepthViewRange>(EMPTY_DEPTH_RANGE);
  const previousCanvasFullDepthRangeRef = useRef<DepthViewRange | null>(null);
  const [, setViewHistory] = useState<DepthViewRange[]>([]);
  const [goToDepthValue, setGoToDepthValue] = useState('');
  const [goToDepthMarker, setGoToDepthMarker] = useState<number | null>(null);
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
  const [canonicalSession, setCanonicalSession] = useState<RawCanonicalSession | null>(null);
  const [curveFillFeatureEnabled, setCurveFillFeatureEnabled] = useState(false);
  const [curveFillGeometryByRuleUid, setCurveFillGeometryByRuleUid] = useState<Map<string, CurveFillGeometryV2>>(() => new Map());
  const [curveFillPending, setCurveFillPending] = useState(false);
  const [curveFillError, setCurveFillError] = useState<string | null>(null);
  const curveFillHydrationKeyRef = useRef<string | null>(null);
  const hasLoadedViewerWell = Boolean(managedViewerWellId);
  const [trackBackdropMode, setTrackBackdropMode] = useState<TrackBackdropMode>('light');
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
      void fetchCurveFillFeatureStatusV2()
          .then((status) => { if (!cancelled) setCurveFillFeatureEnabled(status.enabled); })
          .catch(() => { if (!cancelled) setCurveFillFeatureEnabled(false); });
      return () => { cancelled = true; };
  }, [activeView]);

  useEffect(() => {
      setCurveFillGeometryByRuleUid(new Map());
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
  const canvasAssignedCurveDepthRange = useMemo(() => {
      const ranges: DepthViewRange[] = [];
      for (const track of tracks) {
          if (track.trackType !== 'curve') continue;
          for (const assignment of track.curves) {
              const contract = managedSampleContractsByCurveId[
                  assignment.curveUid ?? assignment.curveId
              ] ?? managedSampleContractsByCurveId[assignment.curveId];
              const min = contract?.depth_min;
              const max = contract?.depth_max;
              if (
                  typeof min === 'number'
                  && Number.isFinite(min)
                  && typeof max === 'number'
                  && Number.isFinite(max)
                  && max > min
              ) {
                  ranges.push({ min, max });
              }
          }
      }
      return ranges.length > 0
          ? unionDepthRanges(ranges, canvasFullDepthRange)
          : canvasFullDepthRange;
  }, [canvasFullDepthRange, managedSampleContractsByCurveId, tracks]);
  const visibleDepthTicks = useMemo(() => makeDepthTicks(viewDepthRange), [viewDepthRange]);
  useEffect(() => {
      const previousFull = previousCanvasFullDepthRangeRef.current;
      setViewDepthRange((current) => {
          if (previousFull === null || rangesEqual(current, previousFull)) return { ...canvasFullDepthRange };
          return clampDepthRange(current, canvasFullDepthRange);
      });
      previousCanvasFullDepthRangeRef.current = { ...canvasFullDepthRange };
  }, [canvasFullDepthRange]);
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
          setTracks((current) => current.map((track) => (track.trackId === trackResizeState.trackId && track.trackType === 'curve'
              ? { ...track, widthPx: nextWidth }
              : track)));
      };
      const handleMouseUp = () => {
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
  const selectedCurveTrack = selectedTrack?.trackType === 'curve' ? selectedTrack : null;
  const canAdjustSelectedCurveTrackWidthDown = Boolean(selectedCurveTrack && selectedCurveTrack.widthPx > CURVE_TRACK_MIN_WIDTH);
  const canAdjustSelectedCurveTrackWidthUp = Boolean(selectedCurveTrack && selectedCurveTrack.widthPx < CURVE_TRACK_MAX_WIDTH);
  const activeViewerCurves = useMemo(() => wdvPackageState.availableCurves, [wdvPackageState]);
  const curveIdentityIndex = useMemo(() => buildCurveIdentityIndex(activeViewerCurves), [activeViewerCurves]);
  const activeWorkspaceWell = useMemo(() => wdvWorkspace?.loaded_wells.find((well) => well.managed_well_id === managedViewerWellId) ?? null, [managedViewerWellId, wdvWorkspace]);
  const activeInventoryWell = useMemo<CurveInventoryWellContext | null>(() => activeWorkspaceWell ? { managedWellId: activeWorkspaceWell.managed_well_id, wellName: activeWorkspaceWell.well_name } : null, [activeWorkspaceWell]);
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
      const existingCurveIds = new Set(merged.map((curve) => curve.curveId));
      activeViewerCurves.forEach((curve) => {
          if (!curve.curveId || existingCurveIds.has(curve.curveId))
              return;
          merged.push(curve);
          existingCurveIds.add(curve.curveId);
      });
      tracks.forEach((track) => {
          if (track.trackType !== 'curve') return;
          track.curves.forEach((assignment) => {
              if (existingCurveIds.has(assignment.curveId)) return;
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
              existingCurveIds.add(assignment.curveId);
          });
      });
      return merged;
  }, [activeViewerCurves, tracks]);
  useEffect(() => {
      sampleLoadAbortRef.current?.abort();
      const controller = new AbortController();
      sampleLoadAbortRef.current = controller;
      const generation = sampleLoadGenerationRef.current + 1;
      sampleLoadGenerationRef.current = generation;
      const requests = tracks.flatMap((track) =>
          track.trackType === 'curve'
              ? track.curves.flatMap((assignment) =>
                  assignment.managedWellUid && assignment.curveUid
                      ? [{ assignment, managedWellUid: assignment.managedWellUid, managedCurveUid: assignment.curveUid }]
                      : [],
                )
              : [],
      );
      const unique = Array.from(new Map(requests.map((item) => [item.managedCurveUid, item])).values());
      if (activeView !== 'log-viewer' || unique.length === 0) {
          setManagedSamplesByCurveId({});
          setManagedSampleContractsByCurveId({});
          setManagedSampleErrorsByCurveId({});
          setManagedSamplesLoading(false);
          return () => controller.abort();
      }
      setManagedSamplesLoading(true);
      void mapWithConcurrency(
          unique,
          4,
          async ({ assignment, managedWellUid, managedCurveUid }): Promise<ManagedCurveSampleLoadResult> => {
              const request = {
                  managedWellId: managedWellUid,
                  curveId: assignment.curveId,
                  curveUid: assignment.curveUid ?? managedCurveUid,
                  managedCurveUid,
                  productId: assignment.managedProductUid ?? managedCurveUid,
                  samplesUrl: '/api/wlv/v2/curve-samples',
              };
              try {
                  const payload = await fetchWlvJson<ManagedCurveSamplesPayload>(
                      '/api/wlv/v2/curve-samples',
                      {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                              managed_well_uid: managedWellUid,
                              managed_curve_uid: managedCurveUid,
                              target_depth_unit: wdvWorkspace?.common_depth_unit ?? 'm',
                              max_samples: 12000,
                          }),
                          signal: controller.signal,
                      },
                  );
                  const samples = parseManagedCurveSamples(payload);
                  return { request, contract: payload, samples, error: samples.length ? null : `No usable samples returned for ${assignment.curveId}` };
              } catch (error) {
                  return { request, contract: null, samples: [], error: error instanceof Error ? error.message : `Unable to load ${assignment.curveId}` };
              }
          },
      ).then((results) => {
          if (controller.signal.aborted || sampleLoadGenerationRef.current !== generation) return;
          const indexed = indexManagedCurveSamples(results);
          setManagedSamplesByCurveId(indexed.samplesByCurveId);
          setManagedSampleContractsByCurveId(indexed.contractsByCurveId);
          setManagedSampleErrorsByCurveId(indexed.errorsByCurveId);
          const sampledRanges = new Map<string, DepthViewRange>();
          results.forEach((result) => {
              if (result.samples.length === 0) return;
              const depths = result.samples.map((sample) => sample.depth);
              const range = { min: Math.min(...depths), max: Math.max(...depths) };
              if (!Number.isFinite(range.min) || !Number.isFinite(range.max) || range.max <= range.min) return;
              const existing = sampledRanges.get(result.request.managedWellId);
              sampledRanges.set(result.request.managedWellId, existing
                  ? { min: Math.min(existing.min, range.min), max: Math.max(existing.max, range.max) }
                  : range);
          });
          if (sampledRanges.size > 0) {
              setFullDepthRangesByWellUid((current) =>
                  replaceManagedWellDepthRanges(current, sampledRanges),
              );
          }
      }).finally(() => {
          if (!controller.signal.aborted && sampleLoadGenerationRef.current === generation) setManagedSamplesLoading(false);
      });
      return () => controller.abort();
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

  const loadCanonicalLayout = useCallback(
    async (signal: AbortSignal): Promise<CanonicalLayoutResult | null> => {
      if (!managedViewerWellUid || !wdvSessionKey || wdvPackageState.loadedCurveItems.length === 0) {
        return null;
      }
      const canonicalSession = await fetchWlvJson<RawCanonicalSession>(
        `/api/wlv/v2/wdv/sessions/${encodeURIComponent(managedViewerWellUid)}`,
        { signal },
      );
      canonicalRevisionRef.current = canonicalSession.revision;
      setCanonicalSession(canonicalSession);
      const canonicalTracks = canonicalSession.state_status === 'active'
        ? frontendTracksFromCanonicalSession(canonicalSession, activeCurveCatalog).map((track) => ({
            ...track,
            ownerWellName: track.managedWellUid ? ownerWellNames.get(track.managedWellUid) : undefined,
          }))
        : [];
      return {
        tracks: canonicalTracks,
        selectedTrackId: canonicalSession.selected_track_uid,
        hydratedSessionKey: wdvSessionKey,
      };
    },
    [activeCurveCatalog, managedViewerWellUid, ownerWellNames, wdvPackageState.loadedCurveItems.length, wdvSessionKey],
  );

  const layoutSource = useWdvLayoutSource({
    managedWellUid: managedViewerWellUid,
    canonicalLoadKey: wdvSessionKey ?? '',
    loadCanonicalLayout,
  });

  // ---------------------------------------------------------------------------
  // Canonical session command helpers (C2 Defect B)
  // ---------------------------------------------------------------------------

  /**
   * POST a canonical session command and return the raw session response.
   * On 409 (revision conflict), re-fetches the current canonical session
   * and applies it — no forced local convergence.
   */
  const executeWdvCanonicalCommand = useCallback(
    async (
      commandPath: string,
      body: Record<string, unknown>,
    ): Promise<RawCanonicalSession> => {
      if (!managedViewerWellUid) {
        throw new Error('executeWdvCanonicalCommand: managedViewerWellUid is not set');
      }
      return fetchWlvJson<RawCanonicalSession>(
        `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(managedViewerWellUid)}/${commandPath}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(
            canonicalCommandRequestBody(canonicalRevisionRef.current, body),
          ),
        },
      );
    },
    [managedViewerWellUid],
  );

  /**
   * Apply a raw canonical session response to component state.
   * Updates tracks, canonical revision, and selection from backend truth.
   */
  const applyCanonicalSession = useCallback(
    (
      rawSession: RawCanonicalSession,
      options: Readonly<{ preserveInteraction?: boolean }> = {},
    ): void => {
      const projectedTracks = frontendTracksFromCanonicalSession(rawSession, activeCurveCatalog).map((track) => ({
          ...track,
          ownerWellName: track.managedWellUid ? ownerWellNames.get(track.managedWellUid) : undefined,
      }));
      const nextTracks = options.preserveInteraction
        ? preserveCanonicalTrackOrder(tracksRef.current, projectedTracks)
        : projectedTracks;
      canonicalRevisionRef.current = rawSession.revision;
      setCanonicalSession(rawSession);
      setTracks(nextTracks);
      setSelection(
        options.preserveInteraction
          ? preserveSelectionAcrossCanonicalRefresh(
              selectionRef.current,
              nextTracks,
              rawSession.selected_track_uid,
            )
          : preserveSelectionAcrossCanonicalRefresh(
              { kind: 'track', trackId: rawSession.selected_track_uid ?? '' },
              nextTracks,
              rawSession.selected_track_uid,
            ),
      );
    },
    [activeCurveCatalog, ownerWellNames],
  );

  const refreshCanonicalSession = useCallback(async (
    options: Readonly<{ preserveInteraction?: boolean }> = {},
  ): Promise<void> => {
    if (!managedViewerWellUid) return;
    const fresh = await fetchWlvJson<RawCanonicalSession>(
      `/api/wlv/v2/wdv/sessions/${encodeURIComponent(managedViewerWellUid)}`,
    ).catch(() => null);
    if (fresh) applyCanonicalSession(fresh, options);
  }, [managedViewerWellUid, applyCanonicalSession]);

  const applyCurveFillWorkflowResult = useCallback((result: CurveFillWorkflowResultV2<RawCanonicalSession>): void => {
      setCurveFillGeometryByRuleUid((current) => applyCurveFillGeometryDeltaV2(current, result.geometry_delta));
      applyCanonicalSession(result.session, { preserveInteraction: true });
  }, [applyCanonicalSession]);

  const createCurveFillRule = useCallback(async (body: Readonly<Record<string, unknown>>): Promise<void> => {
      if (!managedViewerWellUid || !curveFillFeatureEnabled || canonicalRevisionRef.current < 0) return;
      setCurveFillPending(true); setCurveFillError(null);
      try {
          const result = await createCurveFillRuleV2<RawCanonicalSession>(managedViewerWellUid, { ...body, expected_revision: canonicalRevisionRef.current });
          applyCurveFillWorkflowResult(result);
      } catch (error) {
          setCurveFillError(error instanceof Error ? error.message : 'Curve Fill command failed');
          await refreshCanonicalSession();
      } finally { setCurveFillPending(false); }
  }, [applyCurveFillWorkflowResult, curveFillFeatureEnabled, managedViewerWellUid, refreshCanonicalSession]);

  const removeCurveFillRule = useCallback(async (ruleUid: string): Promise<void> => {
      if (!managedViewerWellUid || !curveFillFeatureEnabled || canonicalRevisionRef.current < 0) return;
      setCurveFillPending(true); setCurveFillError(null);
      try {
          const result = await removeCurveFillRuleV2<RawCanonicalSession>(managedViewerWellUid, canonicalRevisionRef.current, ruleUid);
          applyCurveFillWorkflowResult(result);
      } catch (error) {
          setCurveFillError(error instanceof Error ? error.message : 'Curve Fill delete failed');
          await refreshCanonicalSession();
      } finally { setCurveFillPending(false); }
  }, [applyCurveFillWorkflowResult, curveFillFeatureEnabled, managedViewerWellUid, refreshCanonicalSession]);

  const updateCurveFillRule = useCallback(async (ruleUid: string, patch: Readonly<Record<string, unknown>>): Promise<void> => {
      if (!managedViewerWellUid || !curveFillFeatureEnabled || canonicalRevisionRef.current < 0) return;
      setCurveFillPending(true); setCurveFillError(null);
      try {
          const result = await updateCurveFillRuleV2<RawCanonicalSession>(managedViewerWellUid, {
              expected_revision: canonicalRevisionRef.current,
              rule_uid: ruleUid,
              ...patch,
          });
          applyCurveFillWorkflowResult(result);
      } catch (error) {
          setCurveFillError(error instanceof Error ? error.message : 'Curve Fill update failed');
          await refreshCanonicalSession();
      } finally { setCurveFillPending(false); }
  }, [applyCurveFillWorkflowResult, curveFillFeatureEnabled, managedViewerWellUid, refreshCanonicalSession]);

  const reorderCurveFillRules = useCallback(async (trackUid: string, ruleUids: readonly string[]): Promise<void> => {
      if (!managedViewerWellUid || !curveFillFeatureEnabled || canonicalRevisionRef.current < 0) return;
      setCurveFillPending(true); setCurveFillError(null);
      try {
          const result = await reorderCurveFillRulesV2<RawCanonicalSession>(managedViewerWellUid, {
              expected_revision: canonicalRevisionRef.current,
              track_uid: trackUid,
              rule_uids: ruleUids,
          });
          applyCurveFillWorkflowResult(result);
      } catch (error) {
          setCurveFillError(error instanceof Error ? error.message : 'Curve Fill reorder failed');
          await refreshCanonicalSession();
      } finally { setCurveFillPending(false); }
  }, [applyCurveFillWorkflowResult, curveFillFeatureEnabled, managedViewerWellUid, refreshCanonicalSession]);

  useEffect(() => {
      if (!curveFillFeatureEnabled || !managedViewerWellUid || canonicalSession === null || curveFillPending) return;
      const enabledRules = (canonicalSession.curve_fills ?? []).filter((rule) => rule.enabled);
      if (!enabledRules.some((rule) => rule.state !== 'resolved' || !curveFillGeometryByRuleUid.has(rule.rule_uid))) return;
      const key = `${managedViewerWellUid}:${canonicalSession.revision}:${enabledRules.map((rule) => rule.rule_uid).join('|')}`;
      if (curveFillHydrationKeyRef.current === key) return;
      curveFillHydrationKeyRef.current = key;
      setCurveFillPending(true); setCurveFillError(null);
      void hydrateCurveFillV2<RawCanonicalSession>(managedViewerWellUid, canonicalSession.revision)
          .then(applyCurveFillWorkflowResult)
          .catch((error) => setCurveFillError(error instanceof Error ? error.message : 'Curve Fill hydration failed'))
          .finally(() => setCurveFillPending(false));
  }, [applyCurveFillWorkflowResult, canonicalSession, curveFillFeatureEnabled, curveFillGeometryByRuleUid, curveFillPending, managedViewerWellUid]);

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
      try {
          const workspace = await fetchWlvJson<WdvWorkspaceState>('/api/wlv/inventory/wdv-workspace/common-depth-unit', {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ common_depth_unit: commonDepthUnit }),
          });
          setWdvWorkspace(workspace);
          setWdvWorkspaceError(null);
      } catch (error) {
          setWdvWorkspaceError(error instanceof Error ? error.message : 'Unable to change Common Depth Unit');
      }
  }, []);

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
  const selectCanvasTrack = (trackId: string) => {
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

  // Apply canonical startup state only.
  useEffect(() => {
    if (layoutSource.mode !== 'ready') return;
    if (layoutSource.managedWellUid !== managedViewerWellUid) return;
    const orderedLayoutTracks = preserveCanonicalTrackOrder(tracksRef.current, layoutSource.tracks);
    setTracks(orderedLayoutTracks);
    if (orderedLayoutTracks.length > 0) {
      const selectedExists = layoutSource.selectedTrackId !== null
        && orderedLayoutTracks.some((track) => track.trackId === layoutSource.selectedTrackId);
      setSelection({
        kind: 'track',
        trackId: selectedExists ? layoutSource.selectedTrackId! : orderedLayoutTracks[0].trackId,
      });
    } else {
      setSelection({ kind: 'track', trackId: '' });
    }
  }, [layoutSource, managedViewerWellUid]);
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
      return new Set(
          selectedTrack.curves
              .map((assignment) => resolveAssignmentCanonicalCurveKey(curveIdentityIndex, assignment))
              .filter((identity): identity is string => Boolean(identity)),
      );
  }, [curveIdentityIndex, selectedTrack]);
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
  const updateCurveAssignment = (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => {
      const track = tracks.find((item) => item.trackId === trackId && item.trackType === 'curve');
      const assignment =
          track && track.trackType === 'curve'
              ? track.curves.find((item) => item.assignmentId === assignmentId)
              : undefined;
      const rangeCommandBody = assignment
          ? canonicalRangeOverrideCommandBody(assignment, patch)
          : null;

      if (rangeCommandBody !== null) {
          if (
              !managedViewerWellUid
              || canonicalRevisionRef.current < 0
              || !looksLikeUuid(trackId)
              || !looksLikeUuid(assignmentId)
          ) {
              console.error(
                  '[WdvPageBoundary] canonical range update blocked because canonical identity or revision is unavailable.',
              );
              return;
          }

          void (async () => {
              try {
                  const rawSession = await executeWdvCanonicalCommand(
                      'assignments/update',
                      {
                          assignment_uid: assignmentId,
                          ...rangeCommandBody,
                      },
                  );
                  applyCanonicalSession(rawSession, { preserveInteraction: true });
              } catch (error) {
                  if (error instanceof Error && error.message.startsWith('409 ')) {
                      await refreshCanonicalSession({ preserveInteraction: true });
                  } else {
                      console.error('[WdvPageBoundary] updateCurveAssignment range command failed:', error);
                  }
              }
          })();
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
  const addTrack = (draft: AddTrackDraft) => {
      if (!managedViewerWellUid || canonicalRevisionRef.current < 0) return;
      const selected = orderedTracks.find((track) => track.trackId === selection.trackId) ?? null;
      const initialCurveUids = draft.trackType === 'curve' && draft.curveSource === 'selected'
          ? pendingAddTrackCurveIds
              .map((curveId) => activeCurveCatalog.find((curve) => curve.curveId === curveId || curve.curveUid === curveId)?.curveUid)
              .filter((curveUid): curveUid is string => Boolean(curveUid && looksLikeUuid(curveUid)))
          : [];
      const referenceTrackUid = selected && looksLikeUuid(selected.trackId) ? selected.trackId : null;
      const insertPosition = draft.insertMode === 'before_selected' && referenceTrackUid
          ? { mode: 'before_track', reference_track_uid: referenceTrackUid }
          : draft.insertMode === 'after_selected' && referenceTrackUid
              ? { mode: 'after_track', reference_track_uid: referenceTrackUid }
              : { mode: 'far_right' };
      void (async () => {
          try {
              const rawSession = await executeWdvCanonicalCommand('tracks/configured', {
                  track_name: draft.trackType === 'depth' ? draft.depthBasis : 'NEW CURVE TRACK',
                  track_type: draft.trackType,
                  width_px: draft.trackType === 'depth' ? 86 : 220,
                  lattice: draft.trackType === 'curve' && draft.latticeMode !== 'auto' ? draft.latticeMode : undefined,
                  lattice_source: draft.trackType === 'curve' && draft.latticeMode !== 'auto' ? 'user_override' : 'front_curve_default',
                  lattice_override: draft.trackType === 'curve' && draft.latticeMode !== 'auto',
                  scale_mode: draft.scaleMode,
                  depth_basis: draft.trackType === 'depth' ? draft.depthBasis : undefined,
                  insert_position: insertPosition,
                  initial_managed_curve_uids: initialCurveUids,
              });
              applyCanonicalSession(rawSession);
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
      void (async () => {
          try {
              applyCanonicalSession(await executeWdvCanonicalCommand('tracks/remove', { track_uid: selectedTrack.trackId }));
          } catch (error) {
              if (error instanceof Error && error.message.startsWith('409 ')) await refreshCanonicalSession();
              else console.error('[WdvPageBoundary] deleteSelectedTrack failed:', error);
          }
      })();
  };
  const clearCanvas = () => {
      if (!managedViewerWellUid) return;
      void (async () => {
          const executeClear = async (): Promise<RawCanonicalSession> => {
              if (canonicalRevisionRef.current < 0) {
                  await refreshCanonicalSession();
              }
              if (canonicalRevisionRef.current < 0) {
                  throw new Error('Clear Canvas could not resolve the canonical WDV revision.');
              }
              return executeWdvCanonicalCommand('tracks/clear', { preserve_depth_tracks: false });
          };

          try {
              let session: RawCanonicalSession;
              try {
                  session = await executeClear();
              } catch (error) {
                  if (!(error instanceof Error) || !error.message.startsWith('409 ')) {
                      throw error;
                  }
                  await refreshCanonicalSession();
                  session = await executeClear();
              }

              applyCanonicalSession(session);
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
      if (!trackId)
          return;
      setTracks((current) => moveTrackById(current, trackId, direction));
      setSelection((current) => (current.trackId === trackId ? current : { kind: 'track', trackId }));
  };
  const adjustCurveTrackWidth = (trackId: string, delta: number) => {
      setTracks((current) => current.map((track) => {
          if (track.trackId !== trackId || track.trackType !== 'curve')
              return track;
          return { ...track, widthPx: clampCurveTrackWidth(track.widthPx + delta) };
      }));
  };
  const adjustSelectedCurveTrackWidth = (delta: number) => {
      if (!selectedCurveTrack)
          return;
      adjustCurveTrackWidth(selectedCurveTrack.trackId, delta);
  };
  const resetCurveTrackWidths = () => {
      setTracks((current) => current.map((track) => (track.trackType === 'curve'
          ? { ...track, widthPx: CURVE_TRACK_RESET_WIDTH }
          : track)));
  };
  const startCurveTrackResize = (trackId: string, startX: number, startWidth: number) => {
      setOpenCurveMenu(null);
      setDragPanState(null);
      setIntervalZoomActive(false);
      setIntervalSelection(null);
      setTrackResizeState({ trackId, startX, startWidth: clampCurveTrackWidth(startWidth) });
  };
  const setDepthView = (nextRange: DepthViewRange, recordHistory = true) => {
      setViewDepthRange((current) => {
          const clipped = clampDepthRange(nextRange, canvasFullDepthRange);
          if (rangesEqual(current, clipped)) {
              return current;
          }
          if (recordHistory) {
              setViewHistory((history) => [...history.slice(-9), current]);
          }
          return clipped;
      });
  };
  const zoomDepth = (factor: number) => {
      const center = (viewDepthRange.min + viewDepthRange.max) / 2;
      const nextSpan = Math.max(80, Math.min(canvasFullDepthRange.max - canvasFullDepthRange.min, (viewDepthRange.max - viewDepthRange.min) * factor));
      setDepthView({
          min: center - nextSpan / 2,
          max: center + nextSpan / 2,
      });
  };
  const previousDepthView = () => {
      setViewHistory((history) => {
          const previous = history[history.length - 1];
          if (!previous)
              return history;
          setViewDepthRange(previous);
          return history.slice(0, -1);
      });
  };
  const fitDepth = () => {
      setIntervalZoomActive(false);
      setIntervalSelection(null);
      setDragPanState(null);
      setGoToDepthMarker(null);
      setDepthView(canvasAssignedCurveDepthRange);
  };
  const resetDepthView = () => {
      setViewDepthRange(canvasFullDepthRange);
      setViewHistory([]);
      setIntervalZoomActive(false);
      setIntervalSelection(null);
      setDragPanState(null);
      setGoToDepthMarker(null);
      setGoToDepthValue('');
  };
  const goToDepth = () => {
      const target = Number.parseFloat(goToDepthValue);
      if (!Number.isFinite(target))
          return;
      const clampedTarget = clampValue(target, canvasFullDepthRange.min, canvasFullDepthRange.max);
      const currentSpan = viewDepthRange.max - viewDepthRange.min;
      const reviewSpan = currentSpan > GO_TO_REVIEW_WINDOW_M
          ? GO_TO_REVIEW_WINDOW_M
          : currentSpan;
      setDepthView({
          min: clampedTarget - reviewSpan / 2,
          max: clampedTarget + reviewSpan / 2,
      });
      setGoToDepthMarker(clampedTarget);
  };
  const startDragPan = (startY: number) => {
      setOpenCurveMenu(null);
      setIntervalZoomActive(false);
      setIntervalSelection(null);
      setViewHistory((history) => [...history.slice(-9), viewDepthRange]);
      setDragPanState({ startY, startRange: viewDepthRange });
  };
  const updateDragPan = (currentY: number, canvasHeight: number) => {
      if (!dragPanState)
          return;
      const safeHeight = Math.max(1, canvasHeight);
      const span = dragPanState.startRange.max - dragPanState.startRange.min;
      const pixelDelta = currentY - dragPanState.startY;
      const depthShift = -(pixelDelta / safeHeight) * span;
      setViewDepthRange(clampDepthRange({
          min: dragPanState.startRange.min + depthShift,
          max: dragPanState.startRange.max + depthShift,
      }, canvasFullDepthRange));
  };
  const endDragPan = () => {
      setDragPanState(null);
  };
  const startIntervalSelection = (depth: number, y: number) => {
      setDragPanState(null);
      setOpenCurveMenu(null);
      setIntervalSelection({
          startDepth: depth,
          currentDepth: depth,
          startY: y,
          currentY: y,
          dragging: true,
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
      if (nextMax <= nextMin) {
          setIntervalSelection(null);
          return;
      }
      setDepthView({ min: nextMin, max: nextMax });
      setIntervalSelection(null);
  };
  const toggleCurveForSelectedTrack = (curveId: string, checked: boolean) => {
      if (!selectedTrack || selectedTrack.trackType !== 'curve') return;
      if (canonicalRevisionRef.current < 0 || !looksLikeUuid(selectedTrack.trackId)) return;
      const curve = activeCurveCatalog.find((item) => item.curveId === curveId || item.curveUid === curveId);
      const managedCurveUid = curve?.curveUid ?? null;
      if (!managedCurveUid || !looksLikeUuid(managedCurveUid)) return;
      setOpenCurveMenu(null);
      void (async () => {
          try {
              if (checked) {
                  applyCanonicalSession(await executeWdvCanonicalCommand('assignments', {
                      track_uid: selectedTrack.trackId,
                      managed_curve_uid: managedCurveUid,
                  }));
                  return;
              }
              const matching = selectedTrack.curves.filter((assignment) =>
                  assignment.curveUid === managedCurveUid && looksLikeUuid(assignment.assignmentId));
              for (const assignment of matching) {
                  applyCanonicalSession(await executeWdvCanonicalCommand('assignments/remove', {
                      assignment_uid: assignment.assignmentId,
                  }));
              }
          } catch (error) {
              if (error instanceof Error && error.message.startsWith('409 ')) await refreshCanonicalSession();
              else console.error('[WdvPageBoundary] toggleCurveForSelectedTrack failed:', error);
          }
      })();
  };
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
      {wbvPublishPanelOpen ? (
        <div role="dialog" aria-label="Send WDV content to WBV" style={{ position: 'absolute', right: 0, top: 'calc(100% + 8px)', zIndex: 1000, minWidth: 310, maxWidth: 420, padding: 12, border: '1px solid rgba(255,255,255,0.22)', borderRadius: 5, background: '#171717', boxShadow: '0 10px 28px rgba(0,0,0,0.5)', display: 'grid', gap: 10 }}>
          <div style={{ display: 'grid', gap: 3 }}>
            <strong>Send WDV content to WBV</strong>
            <span style={{ opacity: 0.76, fontSize: 12 }}>WBV retains each published package independently until you explicitly update it.</span>
          </div>
          {activeWbvPublishedPackage ? (
            <div style={{ display: 'grid', gap: 4, padding: 8, border: '1px solid rgba(255,255,255,0.14)', borderRadius: 4 }}>
              <span style={{ fontSize: 12, opacity: 0.72 }}>Current retained package</span>
              <strong style={{ fontSize: 13 }}>{activeWbvPublishedPackage.package_name}</strong>
              <span style={{ fontSize: 12, opacity: 0.72 }}>Package revision {activeWbvPublishedPackage.package_revision} · source WDV revision {activeWbvPublishedPackage.source_wdv_revision}</span>
            </div>
          ) : (
            <span style={{ fontSize: 12, opacity: 0.76 }}>No retained WBV package exists for this well.</span>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="wlv-go-to-depth-button" onClick={() => setWbvPublishPanelOpen(false)} disabled={wbvPublishBusy}>Cancel</button>
            {activeWbvPublishedPackage ? (
              <button type="button" className="wlv-go-to-depth-button ready" onClick={() => void updateExistingWbvPublication(activeWbvPublishedPackage)} disabled={wbvPublishBusy}>Update existing</button>
            ) : null}
            <button type="button" className="wlv-go-to-depth-button ready" onClick={() => void publishCurrentWdvAsNewWbvPackage()} disabled={wbvPublishBusy}>Publish as new</button>
          </div>
        </div>
      ) : null}
    </span>
  );

  const moveCurveToTrack = (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => {
      if (!payload.assignmentId || !looksLikeUuid(payload.assignmentId) || !looksLikeUuid(toTrackId)) return;
      void (async () => {
          try {
              applyCanonicalSession(await executeWdvCanonicalCommand('assignments/move', {
                  assignment_uid: payload.assignmentId,
                  target_track_uid: toTrackId,
                  target_stack_index: typeof toIndex === 'number' ? toIndex : 0,
              }));
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
      const fromIndex = ordered.findIndex((assignment) => assignment.assignmentId === assignmentId);
      if (fromIndex < 0) return;
      const [moving] = ordered.splice(fromIndex, 1);
      ordered.splice(toIndex, 0, moving);
      const assignmentUids = ordered.map((assignment) => assignment.assignmentId);
      if (!assignmentUids.every(looksLikeUuid)) return;
      void (async () => {
          try {
              applyCanonicalSession(await executeWdvCanonicalCommand('assignments/reorder', {
                  track_uid: trackId,
                  assignment_uids: assignmentUids,
              }));
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
              applyCanonicalSession(await executeWdvCanonicalCommand('assignments/remove', {
                  assignment_uid: assignmentId,
              }));
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



      <Toolbar commonDepthUnit={quickViewPackage ? quickViewDepthUnit : (wdvWorkspace?.common_depth_unit ?? 'm')} onCommonDepthUnitChange={(unit) => quickViewPackage ? changeQuickViewDepthUnit(unit) : void changeCommonDepthUnit(unit)} managedLayoutDisabled={Boolean(quickViewPackage)} depthUnitDisabled={Boolean(quickViewPackage && !quickViewSourceUnit)} selectedTrack={quickViewPackage ? null : selectedTrack} pendingAddTrackCurveCount={pendingAddTrackCurveIds.length} viewDepthRange={quickViewPackage ? quickViewRange : viewDepthRange} fullDepthRange={quickViewPackage ? quickViewFullRange : canvasAssignedCurveDepthRange} viewDepthReadoutEnabled={quickViewPackage ? true : tracks.length > 0} intervalZoomActive={quickViewPackage ? quickViewIntervalZoomActive : intervalZoomActive} goToDepthValue={quickViewPackage ? quickViewGoToDepthValue : goToDepthValue} onGoToDepthValueChange={quickViewPackage ? setQuickViewGoToDepthValue : setGoToDepthValue} trackBackdropMode={trackBackdropMode} onTrackBackdropModeChange={setTrackBackdropMode} onAddTrack={addTrack} onDeleteTrack={deleteSelectedTrack} onClearCanvas={clearCanvas} onMoveSelectedTrack={moveSelectedTrack} canMoveSelectedTrackLeft={canMoveSelectedTrackLeft} canMoveSelectedTrackRight={canMoveSelectedTrackRight} canAdjustSelectedCurveTrackWidthDown={canAdjustSelectedCurveTrackWidthDown} canAdjustSelectedCurveTrackWidthUp={canAdjustSelectedCurveTrackWidthUp} onAdjustSelectedCurveTrackWidth={adjustSelectedCurveTrackWidth} onResetCurveTrackWidths={resetCurveTrackWidths} onZoomIn={() => quickViewPackage ? zoomQuickView(0.75) : zoomDepth(0.75)} onZoomOut={() => quickViewPackage ? zoomQuickView(1.33) : zoomDepth(1.33)} onPreviousView={quickViewPackage ? previousQuickView : previousDepthView} onFitDepth={() => quickViewPackage ? setQuickViewDepthWindow(quickViewFullRange) : fitDepth()} onSpecifyDepthRange={(range) => {
        if (quickViewPackage) {
            setQuickViewIntervalZoomActive(false);
            setQuickViewDepthWindow(range);
            return;
        }
        setOpenCurveMenu(null);
        setIntervalZoomActive(false);
        setIntervalSelection(null);
        setDragPanState(null);
        setDepthView(range);
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
    }} onToggleIntervalZoom={() => {
        if (quickViewPackage) {
            setQuickViewIntervalZoomActive((active) => !active);
            return;
        }
        setOpenCurveMenu(null);
        setIntervalSelection(null);
        setDragPanState(null);
        setIntervalZoomActive((active) => !active);
    }} onGoToDepth={quickViewPackage ? goToQuickViewDepth : goToDepth} onAddTrackCurveSelectionModeChange={(active) => {
        setAddTrackCurveSelectionMode(active);
        if (active) {
            setPendingAddTrackCurveIds([]);
        }
    }} wbvPublishAction={wbvPublishAction} layoutRecommendations={wdvTemplateRecommendations} layoutRecommendationsLoading={wdvTemplateRecommendationsLoading} layoutRecommendationsError={wdvTemplateRecommendationsError} selectedLayoutRecommendationKey={selectedWdvTemplateKey} onLayoutRecommendationChange={handleLayoutRecommendationChange} onRefreshLayoutRecommendations={refreshWdvTemplateRecommendations}/>

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
        <CurveInventory availableCurves={activeViewerCurves} curveUsageCounts={curveUsageCounts} visibleTrackCurveIds={visibleTrackCurveIds} selectedTrackCurveIds={addTrackCurveSelectionMode ? pendingAddTrackCanonicalIds : selectedTrackCurveIds} selectedCurveIds={visibleTrackCurveIds} assignmentEnabled={addTrackCurveSelectionMode || selectedTrack?.trackType === 'curve'} preferredInventoryTab={tracks.length > 0 ? 'selected' : 'all'} loadedWells={wdvWorkspace?.loaded_wells ?? []} activeWell={activeInventoryWell} curveRunMetadata={activeCurveRunMetadata} lasSources={completeLasSources} selectedLasSourceId={completeLasSourceId} lasPending={completeLasPending} lasIncludeReviewRequired={completeLasIncludeReview} lasMessage={completeLasError ?? completeLasResult} onLasSourceChange={(sourceId) => { setCompleteLasSourceId(sourceId); setCompleteLasError(null); setCompleteLasResult(null); }} onLasIncludeReviewRequiredChange={setCompleteLasIncludeReview} onAddCompleteLas={() => void loadCompleteLas()} logImageSources={logImageSourceOptions} selectedLogImageSourceId={selectedLogImageSourceId} onLogImageSourceChange={setSelectedLogImageSourceId} onActiveWellChange={(managedWellId) => {
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
            </section>)) : (<TrackCanvas tracks={tracks} selection={selection} openCurveMenu={openCurveMenu} depthTicks={visibleDepthTicks} viewDepthRange={viewDepthRange} goToDepthMarker={goToDepthMarker} intervalZoomActive={intervalZoomActive} intervalSelection={intervalSelection} dragPanActive={Boolean(dragPanState)} onSelectTrack={selectCanvasTrack} onSelectCurve={selectCanvasCurve} onReorderCurve={reorderCurve} onMoveCurveToTrack={moveCurveToTrack} onOpenCurveMenu={(trackId, assignmentId) => setOpenCurveMenu({ trackId, assignmentId })} onCloseCurveMenu={() => setOpenCurveMenu(null)} onRemoveCurveFromTrack={removeCurveFromTrack} onStartIntervalSelection={startIntervalSelection} onUpdateIntervalSelection={updateIntervalSelection} onCompleteIntervalSelection={completeIntervalSelection} onStartDragPan={startDragPan} onUpdateDragPan={updateDragPan} onEndDragPan={endDragPan} onStartCurveTrackResize={startCurveTrackResize} resizingTrackId={trackResizeState?.trackId ?? null} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={activeCurveCatalog} curveFillGeometryByRuleUid={curveFillFeatureEnabled ? curveFillGeometryByRuleUid : new Map()}/>)}
        </>)}
        {quickViewPackage ? (<QuickViewMetadataPanel pkg={quickViewPackage} collapsed={quickViewInfoCollapsed} onToggleCollapsed={() => setQuickViewInfoCollapsed((collapsed) => !collapsed)} />) : (tracks.length === 0 ? (<aside className="wlv-right-panel wlv-ready-properties-panel" aria-label="Track properties unavailable">
            <div className="wlv-panel-heading">
              <h2>Track Properties</h2>
            </div>
            <div className="wlv-ready-properties-copy">
              Create or select a visible track to edit display properties.
            </div>
          </aside>) : (<WellLogPropertiesPanelSlot tracks={tracks} selection={selection} curveCatalogItems={activeCurveCatalog} managedSampleContractsByCurveId={managedSampleContractsByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} wdvIdentityMetadata={wdvIdentityMetadata} wdvIdentityMetadataError={wdvIdentityMetadataError} updateTrack={updateTrack} updateCurveAssignment={updateCurveAssignment} collapsed={rightPropertiesCollapsed} onToggleCollapsed={() => setRightPropertiesCollapsed((collapsed) => !collapsed)} curveFillV2={{ enabled: curveFillFeatureEnabled, managedWellUid: managedViewerWellUid, revision: canonicalSession?.revision ?? canonicalRevisionRef.current, rules: canonicalSession?.curve_fills ?? [], pending: curveFillPending, error: curveFillError, onCreateRule: createCurveFillRule, onUpdateRule: updateCurveFillRule, onRemoveRule: removeCurveFillRule, onReorderRules: reorderCurveFillRules }} legacyPanel={(<RightPanel tracks={tracks} selection={selection} curveCatalogItems={activeCurveCatalog} updateTrack={updateTrack} updateCurveAssignment={updateCurveAssignment}/>)}/>))}
      </div>

      <footer className="wlv-status-footer">
        <span>Backend-managed WDV workspace</span>
        <span>Backend-owned depth and curve contracts</span>
        <span>Portable local and enterprise deployment</span>
      </footer>
        </div>;
}
