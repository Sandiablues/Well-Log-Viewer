import { type Dispatch, type SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { curveCatalog, defaultDepthRange, fullDepthRange } from '../prototype/realLasTrackLayoutData';
import { WellLogPropertiesPanelSlot } from '../prototype/WellLogPropertiesPanelSlot';
import { loadBackendViewerPackageWithFallback, type BackendViewerPackageLoadResult } from '../prototype/backendViewerPackageAdapter';
import { buildWdvPackageState, emptyWdvPackageState, type WdvLoadedCurveItem, type WdvPackageState } from '../prototype/wdvPackageState';
import { indexManagedCurveSamples, loadManagedCurveSamples, type ManagedCurveSamplesByCurveId, type ManagedCurveSamplesPayload } from '../prototype/managedCurveSamples';
import type { CurveAssignment, CurveCatalogItem, DragCurvePayload, SelectionRef, WellLogTrack } from '../prototype/trackLayoutModel';
import { makeCurveAssignment, orderedCurves } from '../prototype/trackLayoutModel';
import { managedWellIdentityFromPayload, sameManagedWellIdentity, type ManagedWellIdentity } from '../identity/managedWellIdentity';
import {
    buildCurveIdentityIndex,
    canonicalizeCurveIdentitySet,
    canonicalizeCurveUsageCounts,
    resolveAssignmentCanonicalCurveKey,
} from '../identity/curveIdentityIndex';
import { AddTrackDraft, CURVE_TRACK_MAX_WIDTH, CURVE_TRACK_MIN_WIDTH, CurveInventory, CurveInventoryWellContext, DepthViewRange, IntervalSelectionState, RightPanel, Toolbar, TrackBackdropMode, TrackCanvas, WdvCanonicalTemplateApplySession, WdvRecommendedCurve, WdvTemplateRecommendationItem, WdvTemplateRecommendationModal, WdvWorkspaceLoadedWell, buildWdvTemplateRecommendationRequest, clampCurveTrackWidth, clampValue, fetchWlvJson, sortTracks } from './WdvPresentationPrimitives';
import { useWdvLayoutSource } from './useWdvLayoutSource';
import type { CanonicalLayoutResult } from './useWdvLayoutSource';

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

const FULL_DEPTH_RANGE: DepthViewRange = fullDepthRange;

const DEFAULT_DEPTH_RANGE: DepthViewRange = defaultDepthRange;

const CURVE_TRACK_RESET_WIDTH = 220;

const GO_TO_REVIEW_WINDOW_M = 600;

function clampDepthRange(range: DepthViewRange, fullRange: DepthViewRange = FULL_DEPTH_RANGE): DepthViewRange {
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

type WdvWorkspaceState = {
    workspace_id: string;
    revision: number;
    active_managed_well_id?: string | null;
    active_managed_well_uid?: string | null;
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
  stack_index: number;
  visible: boolean;
  scale_min: number | null;
  scale_max: number | null;
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
}

/** @internal exported for unit tests */
export interface RawCanonicalTrack {
  track_uid: string;
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
        if (!curve) return [];
        const fallback = makeCurveAssignment(curve, assignIndex);
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
          stackIndex: raw.stack_index,
          visible: raw.visible,
          scaleMin: raw.scale_min,
          scaleMax: raw.scale_max,
          scaleType,
          scaleDirection,
          color: raw.color ?? fallback.color,
          unit: raw.unit,
          displayPolicySource: raw.display_policy_source,
          displayReviewRequired: raw.display_review_required,
          displayWarningCode: raw.display_warning_code,
          displayWarningMessage: raw.display_warning_message,
        };
        return [assignment];
      });

    result.push({
      trackId,
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

export interface WdvPageBoundaryProps {
  managedViewerWell: ManagedWellIdentity | null;
  setManagedViewerWell: Dispatch<SetStateAction<ManagedWellIdentity | null>>;
  onOpenWellbore3D(): void;
}

export function WdvPageBoundary({ managedViewerWell, setManagedViewerWell, onOpenWellbore3D }: WdvPageBoundaryProps) {
  const managedViewerWellId = managedViewerWell?.managedWellId ?? null;
  const managedViewerWellUid = managedViewerWell?.managedWellUid ?? null;
  const activeView = 'log-viewer' as const;
  const [wdvWorkspace, setWdvWorkspace] = useState<WdvWorkspaceState | null>(null);
  const [wdvWorkspaceError, setWdvWorkspaceError] = useState<string | null>(null);
  const [, setViewerPackageLoad] = useState<BackendViewerPackageLoadResult | null>(null);
  const [wdvPackageState, setWdvPackageState] = useState<WdvPackageState>(() => emptyWdvPackageState());
  const [managedSamplesByCurveId, setManagedSamplesByCurveId] = useState<ManagedCurveSamplesByCurveId>({});
  const [managedSampleErrorsByCurveId, setManagedSampleErrorsByCurveId] = useState<Record<string, string>>({});
  const [managedSamplesLoading, setManagedSamplesLoading] = useState(false);
  const [recommendationRefreshRevision, setRecommendationRefreshRevision] = useState(0);
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
  }, [activeView, managedViewerWellId]);
  useEffect(() => {
      sampleLoadAbortRef.current?.abort();
      const controller = new AbortController();
      sampleLoadAbortRef.current = controller;
      const generation = sampleLoadGenerationRef.current + 1;
      sampleLoadGenerationRef.current = generation;
      if (activeView !== 'log-viewer' || !managedViewerWellId || wdvPackageState.loadedCurveItems.length === 0) {
          setManagedSamplesByCurveId({});
          setManagedSampleErrorsByCurveId({});
          setManagedSamplesLoading(false);
          return () => controller.abort();
      }
      setManagedSamplesByCurveId({});
      setManagedSampleErrorsByCurveId({});
      setManagedSamplesLoading(true);
      const requests = wdvPackageState.loadedCurveItems
          .filter((item) => Boolean(item.productId && item.samplesUrl))
          .map((item) => ({
          managedWellId: managedViewerWellId,
          curveId: item.curveId,
          curveUid: item.curveUid,
          managedCurveUid: item.managedCurveUid,
          productId: item.productId,
          samplesUrl: item.samplesUrl as string,
          sampleRevision: item.sampleRevision,
      }));
      void mapWithConcurrency(requests, 4, (request) => loadManagedCurveSamples(request, (url) => fetchWlvJson<ManagedCurveSamplesPayload>(url, { signal: controller.signal }))).then((results) => {
          if (controller.signal.aborted || sampleLoadGenerationRef.current !== generation)
              return;
          const indexed = indexManagedCurveSamples(results);
          setManagedSamplesByCurveId(indexed.samplesByCurveId);
          setManagedSampleErrorsByCurveId(indexed.errorsByCurveId);
      }).catch((error) => {
          if (controller.signal.aborted || sampleLoadGenerationRef.current !== generation || isAbortError(error))
              return;
          setManagedSampleErrorsByCurveId({ __load__: error instanceof Error ? error.message : 'Curve samples unavailable' });
      }).finally(() => {
          if (!controller.signal.aborted && sampleLoadGenerationRef.current === generation) {
              setManagedSamplesLoading(false);
          }
      });
      return () => {
          controller.abort();
          if (sampleLoadAbortRef.current === controller)
              sampleLoadAbortRef.current = null;
      };
  }, [activeView, managedViewerWellId, wdvPackageState.loadedCurveItems]);
  const [tracks, setTracks] = useState<WellLogTrack[]>([]);
  const [selection, setSelection] = useState<SelectionRef>({ kind: 'track', trackId: 'track-gr-sp' });
  const [addTrackCurveSelectionMode, setAddTrackCurveSelectionMode] = useState(false);
  const [pendingAddTrackCurveIds, setPendingAddTrackCurveIds] = useState<string[]>([]);
  const [openCurveMenu, setOpenCurveMenu] = useState<{
      trackId: string;
      assignmentId: string;
  } | null>(null);
  const [viewDepthRange, setViewDepthRange] = useState<DepthViewRange>(DEFAULT_DEPTH_RANGE);
  const appliedBackendDepthDomainKeyRef = useRef<string | null>(null);
  const [, setViewHistory] = useState<DepthViewRange[]>([]);
  const [goToDepthValue, setGoToDepthValue] = useState('');
  const [goToDepthMarker, setGoToDepthMarker] = useState<number | null>(null);
  const [intervalZoomActive, setIntervalZoomActive] = useState(false);
  const [intervalSelection, setIntervalSelection] = useState<IntervalSelectionState | null>(null);
  const [dragPanState, setDragPanState] = useState<DragPanState | null>(null);
  const [trackResizeState, setTrackResizeState] = useState<TrackResizeState | null>(null);
  const [curveInventoryWidthPx, setCurveInventoryWidthPx] = useState(CURVE_INVENTORY_DEFAULT_WIDTH_PX);
  const [curveInventoryCollapsed, setCurveInventoryCollapsed] = useState(false);
  const [curveInventoryResizeState, setCurveInventoryResizeState] = useState<CurveInventoryResizeState | null>(null);
  // Tracks the current canonical session revision for revision-guarded commands.
  // -1 means the canonical session has not been initialised yet (canonical GET
  // returned empty or was unreachable).  ≥ 0 means the session is live and
  // canonical commands can be dispatched.
  const canonicalRevisionRef = useRef<number>(-1);
  const hasLoadedViewerWell = Boolean(managedViewerWellId);
  const [trackBackdropMode, setTrackBackdropMode] = useState<TrackBackdropMode>('light');
  const [wdvTemplateRecommendations, setWdvTemplateRecommendations] = useState<WdvTemplateRecommendationItem[]>([]);
  const [wdvTemplateRecommendationsLoading, setWdvTemplateRecommendationsLoading] = useState(false);
  const [wdvTemplateRecommendationsError, setWdvTemplateRecommendationsError] = useState<string | null>(null);
  const [selectedWdvTemplateKey, setSelectedWdvTemplateKey] = useState('');
  const [wdvTemplateModalOpen, setWdvTemplateModalOpen] = useState(false);
  const activeFullDepthRange = useMemo(() => wdvPackageState.depthRange ?? FULL_DEPTH_RANGE, [wdvPackageState.depthRange]);
  const activeFullDepthRangeKey = `${activeFullDepthRange.min}:${activeFullDepthRange.max}`;
  const hasBackendDepthRange = Boolean(wdvPackageState.depthRange);
  const activeDefaultDepthRange = useMemo(() => (wdvPackageState.depthRange ? activeFullDepthRange : clampDepthRange(DEFAULT_DEPTH_RANGE, activeFullDepthRange)), [activeFullDepthRange, wdvPackageState.depthRange]);
  const visibleDepthTicks = useMemo(() => makeDepthTicks(viewDepthRange), [viewDepthRange]);
  useEffect(() => {
      setViewDepthRange((current) => {
          const clipped = clampDepthRange(current, activeFullDepthRange);
          if (hasBackendDepthRange && appliedBackendDepthDomainKeyRef.current !== activeFullDepthRangeKey) {
              appliedBackendDepthDomainKeyRef.current = activeFullDepthRangeKey;
              return { ...activeFullDepthRange };
          }
          appliedBackendDepthDomainKeyRef.current = activeFullDepthRangeKey;
          return clipped;
      });
  }, [activeFullDepthRange, activeFullDepthRangeKey, hasBackendDepthRange]);
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
  const selectedTrack = tracks.find((track) => track.trackId === selection.trackId) ?? null;
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
  const activeCurveCatalog = useMemo(() => {
      const merged = [...curveCatalog];
      const existingCurveIds = new Set(merged.map((curve) => curve.curveId));
      activeViewerCurves.forEach((curve) => {
          if (!curve.curveId || existingCurveIds.has(curve.curveId))
              return;
          merged.push(curve);
          existingCurveIds.add(curve.curveId);
      });
      return merged;
  }, [activeViewerCurves]);
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
      const canonicalTracks = canonicalSession.state_status === 'active'
        ? frontendTracksFromCanonicalSession(canonicalSession, activeCurveCatalog)
        : [];
      return {
        tracks: canonicalTracks,
        selectedTrackId: canonicalSession.selected_track_uid,
        hydratedSessionKey: wdvSessionKey,
      };
    },
    [activeCurveCatalog, managedViewerWellUid, wdvPackageState.loadedCurveItems.length, wdvSessionKey],
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
    (rawSession: RawCanonicalSession): void => {
      const nextTracks = frontendTracksFromCanonicalSession(rawSession, activeCurveCatalog);
      canonicalRevisionRef.current = rawSession.revision;
      setTracks(nextTracks);
      if (nextTracks.length > 0) {
        const selectedUid = rawSession.selected_track_uid;
        const selectedExists =
          selectedUid !== null &&
          nextTracks.some((t) => t.trackId === selectedUid);
        setSelection({
          kind: 'track',
          trackId: selectedExists ? selectedUid! : nextTracks[0].trackId,
        });
      }
    },
    [activeCurveCatalog, wdvSessionKey],
  );

  const refreshCanonicalSession = useCallback(async (): Promise<void> => {
    if (!managedViewerWellUid) return;
    const fresh = await fetchWlvJson<RawCanonicalSession>(
      `/api/wlv/v2/wdv/sessions/${encodeURIComponent(managedViewerWellUid)}`,
    ).catch(() => null);
    if (fresh) applyCanonicalSession(fresh);
  }, [managedViewerWellUid, applyCanonicalSession]);

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
                setTracks([]);
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
  useEffect(() => {
      if (!managedViewerWellId || !wdvWorkspace)
          return;
      if (wdvWorkspace.active_managed_well_id === managedViewerWellId)
          return;
      if (managedViewerWell)
          void changeActiveWdvWell(managedViewerWell);
  }, [managedViewerWellId, managedViewerWellUid, wdvWorkspace?.active_managed_well_id, wdvWorkspace?.active_managed_well_uid]);
  // Clear stale display whenever a new probe starts. This ensures the WDV
  // never shows leftover tracks/samples from a prior well while the new probe
  // is in flight.
  useEffect(() => {
    if (layoutSource.mode !== 'probing') return;
    setTracks([]);
    setManagedSamplesByCurveId({});
    setManagedSampleErrorsByCurveId({});
  }, [layoutSource.mode]);

  // Apply canonical startup state only.
  useEffect(() => {
    if (layoutSource.mode !== 'ready') return;
    if (layoutSource.managedWellUid !== managedViewerWellUid) return;
    setTracks(layoutSource.tracks);
    if (layoutSource.tracks.length > 0) {
      const selectedExists = layoutSource.selectedTrackId !== null
        && layoutSource.tracks.some((track) => track.trackId === layoutSource.selectedTrackId);
      setSelection({
        kind: 'track',
        trackId: selectedExists ? layoutSource.selectedTrackId! : layoutSource.tracks[0].trackId,
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
      setTracks((current) => current.map((track) => {
          if (track.trackId !== trackId || track.trackType !== 'curve')
              return track;
          return {
              ...track,
              curves: track.curves.map((assignment) => (assignment.assignmentId === assignmentId ? { ...assignment, ...patch } : assignment)),
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
          const clipped = clampDepthRange(nextRange, activeFullDepthRange);
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
      const nextSpan = Math.max(80, Math.min(activeFullDepthRange.max - activeFullDepthRange.min, (viewDepthRange.max - viewDepthRange.min) * factor));
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
      setDepthView(activeFullDepthRange);
  };
  const resetDepthView = () => {
      setViewDepthRange(activeDefaultDepthRange);
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
      const clampedTarget = clampValue(target, activeFullDepthRange.min, activeFullDepthRange.max);
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
      }, activeFullDepthRange));
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
  const armIntervalSelection = (depth: number, y: number) => {
      setIntervalSelection((current) => current
          ? { ...current, currentDepth: depth, currentY: y, dragging: false }
          : {
              startDepth: depth,
              currentDepth: depth,
              startY: y,
              currentY: y,
              dragging: false,
          });
  };
  const completeIntervalSelection = (depth: number, y: number) => {
      if (!intervalSelection)
          return;
      const nextMin = Math.min(intervalSelection.startDepth, depth);
      const nextMax = Math.max(intervalSelection.startDepth, depth);
      if (nextMax - nextMin < 25) {
          setIntervalSelection({
              ...intervalSelection,
              currentDepth: depth,
              currentY: y,
              dragging: false,
          });
          return;
      }
      setDepthView({ min: nextMin, max: nextMax });
      setIntervalZoomActive(false);
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
        <button type="button" className="wlv-wdv-3d-badge" onClick={() => onOpenWellbore3D()} title="Open 3D Wellbore Viewer" aria-label="Open 3D Wellbore Viewer">
          3D
        </button>
      </header>

      {!hasLoadedViewerWell && (<section className="wlv-empty-viewer-top-banner" aria-label="Well Data Viewer empty state">
          <strong>No data loaded in the Well Data Viewer</strong>
          <span>
            The WDV is ready. Load a managed well or selected products from the WMDP using Bulk Action → Load selected to Data Viewer.
          </span>
        </section>)}

      <Toolbar selectedTrack={selectedTrack} pendingAddTrackCurveCount={pendingAddTrackCurveIds.length} viewDepthRange={viewDepthRange} fullDepthRange={activeFullDepthRange} viewDepthReadoutEnabled={tracks.length > 0} intervalZoomActive={intervalZoomActive} goToDepthValue={goToDepthValue} onGoToDepthValueChange={setGoToDepthValue} trackBackdropMode={trackBackdropMode} onTrackBackdropModeChange={setTrackBackdropMode} onAddTrack={addTrack} onDeleteTrack={deleteSelectedTrack} onMoveSelectedTrack={moveSelectedTrack} canMoveSelectedTrackLeft={canMoveSelectedTrackLeft} canMoveSelectedTrackRight={canMoveSelectedTrackRight} canAdjustSelectedCurveTrackWidthDown={canAdjustSelectedCurveTrackWidthDown} canAdjustSelectedCurveTrackWidthUp={canAdjustSelectedCurveTrackWidthUp} onAdjustSelectedCurveTrackWidth={adjustSelectedCurveTrackWidth} onResetCurveTrackWidths={resetCurveTrackWidths} onZoomIn={() => zoomDepth(0.75)} onZoomOut={() => zoomDepth(1.33)} onPreviousView={previousDepthView} onFitDepth={fitDepth} onSpecifyDepthRange={(range) => {
        setOpenCurveMenu(null);
        setIntervalZoomActive(false);
        setIntervalSelection(null);
        setDragPanState(null);
        setDepthView(range);
    }} onResetView={resetDepthView} onToggleIntervalZoom={() => {
        setOpenCurveMenu(null);
        setIntervalSelection(null);
        setDragPanState(null);
        setIntervalZoomActive((active) => !active);
    }} onGoToDepth={goToDepth} onAddTrackCurveSelectionModeChange={(active) => {
        setAddTrackCurveSelectionMode(active);
        if (active) {
            setPendingAddTrackCurveIds([]);
        }
    }} layoutRecommendations={wdvTemplateRecommendations} layoutRecommendationsLoading={wdvTemplateRecommendationsLoading} layoutRecommendationsError={wdvTemplateRecommendationsError} selectedLayoutRecommendationKey={selectedWdvTemplateKey} onLayoutRecommendationChange={handleLayoutRecommendationChange} onRefreshLayoutRecommendations={refreshWdvTemplateRecommendations}/>

      {wdvTemplateModalOpen && selectedWdvTemplateRecommendation ? (<WdvTemplateRecommendationModal recommendation={selectedWdvTemplateRecommendation} loadedCurveItems={wdvPackageState.loadedCurveItems} managedWellId={managedViewerWellId} managedWellUid={managedViewerWellUid} getCanonicalRevision={() => canonicalRevisionRef.current} onClose={() => setWdvTemplateModalOpen(false)} onApplied={handleWdvTemplateApplied}/>) : null}

      <div className={`wlv-prototype-workspace wlv-track-backdrop-${trackBackdropMode} ${curveInventoryResizeState ? 'curve-inventory-resize-active' : ''} ${curveInventoryCollapsed ? 'curve-inventory-collapsed' : ''}`} style={{ gridTemplateColumns: `${curveInventoryCollapsed ? 38 : curveInventoryWidthPx}px minmax(0, 1fr) 330px` }}>
        <div className={`wlv-curve-inventory-shell ${curveInventoryCollapsed ? 'collapsed' : ''}`} style={{ width: curveInventoryCollapsed ? 38 : curveInventoryWidthPx }}>
        <button type="button" className="wlv-curve-inventory-collapse-toggle" onClick={() => setCurveInventoryCollapsed((collapsed) => !collapsed)} aria-expanded={!curveInventoryCollapsed} aria-label={curveInventoryCollapsed ? 'Expand Curve Inventory' : 'Collapse Curve Inventory'} title={curveInventoryCollapsed ? 'Expand Curve Inventory' : 'Collapse Curve Inventory'}>
          {curveInventoryCollapsed ? '›' : '‹'}
        </button>
        {curveInventoryCollapsed ? (<div className="wlv-curve-inventory-collapsed-label" aria-hidden="true">Curves</div>) : (<>
        {wdvWorkspaceError && <div className="wlv-workspace-error">{wdvWorkspaceError}</div>}
        <CurveInventory availableCurves={activeViewerCurves} curveUsageCounts={curveUsageCounts} visibleTrackCurveIds={visibleTrackCurveIds} selectedTrackCurveIds={addTrackCurveSelectionMode ? pendingAddTrackCanonicalIds : selectedTrackCurveIds} selectedCurveIds={visibleTrackCurveIds} assignmentEnabled={addTrackCurveSelectionMode || selectedTrack?.trackType === 'curve'} preferredInventoryTab={tracks.length > 0 ? 'selected' : 'all'} loadedWells={wdvWorkspace?.loaded_wells ?? []} activeWell={activeInventoryWell} curveRunMetadata={activeCurveRunMetadata} onActiveWellChange={(managedWellId) => {
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
        {!curveInventoryCollapsed && (<button type="button" className="wlv-curve-inventory-resize-handle" aria-label="Resize curve inventory panel" title="Drag to widen Curve Inventory" onMouseDown={(event) => {
            event.preventDefault();
            setCurveInventoryResizeState({ startX: event.clientX, startWidth: curveInventoryWidthPx });
        }} onDoubleClick={() => setCurveInventoryWidthPx(CURVE_INVENTORY_DEFAULT_WIDTH_PX)}/>)}
        </div>
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
            </section>)) : (<TrackCanvas tracks={tracks} selection={selection} openCurveMenu={openCurveMenu} depthTicks={visibleDepthTicks} viewDepthRange={viewDepthRange} goToDepthMarker={goToDepthMarker} intervalZoomActive={intervalZoomActive} intervalSelection={intervalSelection} dragPanActive={Boolean(dragPanState)} onSelectTrack={(trackId) => setSelection({ kind: 'track', trackId })} onSelectCurve={(trackId, assignmentId) => setSelection({ kind: 'curve', trackId, assignmentId })} onReorderCurve={reorderCurve} onMoveCurveToTrack={moveCurveToTrack} onOpenCurveMenu={(trackId, assignmentId) => setOpenCurveMenu({ trackId, assignmentId })} onCloseCurveMenu={() => setOpenCurveMenu(null)} onRemoveCurveFromTrack={removeCurveFromTrack} onStartIntervalSelection={startIntervalSelection} onUpdateIntervalSelection={updateIntervalSelection} onArmIntervalSelection={armIntervalSelection} onCompleteIntervalSelection={completeIntervalSelection} onStartDragPan={startDragPan} onUpdateDragPan={updateDragPan} onEndDragPan={endDragPan} onStartCurveTrackResize={startCurveTrackResize} resizingTrackId={trackResizeState?.trackId ?? null} managedSamplesByCurveId={managedSamplesByCurveId} managedSampleErrorsByCurveId={managedSampleErrorsByCurveId} curveCatalogItems={activeCurveCatalog}/>)}
        {tracks.length === 0 ? (<aside className="wlv-right-panel wlv-ready-properties-panel" aria-label="Track properties unavailable">
            <div className="wlv-panel-heading">
              <h2>Track Properties</h2>
            </div>
            <div className="wlv-ready-properties-copy">
              Create or select a visible track to edit display properties.
            </div>
          </aside>) : (<WellLogPropertiesPanelSlot tracks={tracks} selection={selection} curveCatalogItems={activeCurveCatalog} updateTrack={updateTrack} updateCurveAssignment={updateCurveAssignment} legacyPanel={(<RightPanel tracks={tracks} selection={selection} curveCatalogItems={activeCurveCatalog} updateTrack={updateTrack} updateCurveAssignment={updateCurveAssignment}/>)}/>)}
      </div>

      <footer className="wlv-status-footer">
        <span>WL-PROTOTYPE-010B shared depth ruler geometry</span>
        <span>Track terminology only</span>
        <span>Mock frontend layout draft — no LAS parsing or MSI persistence</span>
      </footer>
        </div>;
}
