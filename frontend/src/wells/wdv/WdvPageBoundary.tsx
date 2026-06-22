import { type Dispatch, type SetStateAction, useEffect, useMemo, useRef, useState } from 'react';
import { curveCatalog, defaultDepthRange, fullDepthRange } from '../prototype/realLasTrackLayoutData';
import { WellLogPropertiesPanelSlot } from '../prototype/WellLogPropertiesPanelSlot';
import { loadBackendViewerPackageWithFallback, type BackendViewerPackageLoadResult } from '../prototype/backendViewerPackageAdapter';
import { buildWdvPackageState, emptyWdvPackageState, type WdvLoadedCurveItem, type WdvPackageState } from '../prototype/wdvPackageState';
import { indexManagedCurveSamples, loadManagedCurveSamples, type ManagedCurveSamplesByCurveId, type ManagedCurveSamplesPayload } from '../prototype/managedCurveSamples';
import type { ActiveTrackType, CurveAssignment, CurveCatalogItem, DragCurvePayload, SelectionRef, WellLogTrack } from '../prototype/trackLayoutModel';
import { curveById, makeCurveAssignment, orderedCurves, renumberCurveStack } from '../prototype/trackLayoutModel';
import { managedWellIdentityFromPayload, sameManagedWellIdentity, type ManagedWellIdentity } from '../identity/managedWellIdentity';
import {
    buildCurveIdentityIndex,
    canonicalizeCurveIdentitySet,
    canonicalizeCurveUsageCounts,
    resolveAssignmentCanonicalCurveKey,
} from '../identity/curveIdentityIndex';
import { AddTrackDraft, CURVE_TRACK_MAX_WIDTH, CURVE_TRACK_MIN_WIDTH, CurveInventory, CurveInventoryWellContext, DepthViewRange, IntervalSelectionState, RightPanel, Toolbar, TrackBackdropMode, TrackCanvas, WdvRecommendedCurve, WdvSessionLayoutCurveState, WdvSessionLayoutResponse, WdvSessionLayoutTrackState, WdvTemplateRecommendationItem, WdvTemplateRecommendationModal, WdvWorkspaceLoadedWell, buildWdvTemplateRecommendationRequest, clampCurveTrackWidth, clampValue, displayTitleForTrack, fetchWlvJson, sortTracks } from './WdvPresentationPrimitives';

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


function finiteNumberOr(value: unknown, fallback: number): number {
    const parsed = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function sessionCurveAssignmentFromFrontend(assignment: CurveAssignment, catalog: CurveCatalogItem[]): WdvSessionLayoutCurveState {
    const curve = catalog.find((item) => item.curveId === assignment.curveId);
    return {
        assignment_id: assignment.assignmentId,
        curve_uid: assignment.curveUid ?? curve?.curveUid ?? null,
        well_uid: assignment.wellUid ?? curve?.wellUid ?? null,
        source_uid: assignment.sourceUid ?? curve?.sourceUid ?? null,
        kr_curve_type_id: assignment.krCurveTypeId ?? curve?.krCurveTypeId ?? null,
        observed_mnemonic: assignment.observedMnemonic ?? curve?.observedMnemonic ?? curve?.mnemonic ?? assignment.curveId,
        normalized_mnemonic: assignment.normalizedMnemonic ?? curve?.normalizedMnemonic ?? curve?.mnemonic ?? assignment.curveId,
        curve_id: assignment.curveId,
        product_id: curve?.curveId ?? assignment.curveId,
        mnemonic: curve?.mnemonic ?? assignment.curveId,
        display_name: curve?.description ?? curve?.mnemonic ?? assignment.curveId,
        curve_family: curve?.curveClass ?? null,
        unit: curve?.unit ?? null,
        stack_index: assignment.stackIndex,
        visible: assignment.visible,
        scale_min: assignment.scaleMin,
        scale_max: assignment.scaleMax,
        scale_type: assignment.scaleType ?? (curve?.defaultLattice === 'logarithmic' ? 'log' : 'linear'),
        scale_direction: assignment.scaleDirection,
        color: assignment.color,
    };
}

function sessionTracksFromFrontend(tracks: WellLogTrack[], catalog: CurveCatalogItem[]): WdvSessionLayoutTrackState[] {
    return sortTracks(tracks).map((track) => {
        if (track.trackType === 'depth') {
            return {
                track_id: track.trackId,
                track_number: track.trackIndex,
                track_name: track.title,
                track_type: 'depth',
                width_px: track.widthPx,
                curves: [],
            };
        }
        if (track.trackType === 'curve') {
            return {
                track_id: track.trackId,
                track_number: track.trackIndex,
                track_name: displayTitleForTrack(track, catalog),
                track_type: 'curve',
                width_px: track.widthPx,
                lattice: track.lattice,
                lattice_source: track.latticeSource,
                curves: orderedCurves(track).map((assignment) => sessionCurveAssignmentFromFrontend(assignment, catalog)),
            };
        }
        return {
            track_id: track.trackId,
            track_number: track.trackIndex,
            track_name: track.title,
            track_type: track.trackType,
            width_px: track.widthPx,
            curves: [],
        };
    });
}

function sessionAssignmentIdentityCandidates(rawAssignment: WdvSessionLayoutCurveState): string[] {
    return [
        rawAssignment.curve_uid,
        rawAssignment.curveUid,
        rawAssignment.curve_id,
        rawAssignment.curveId,
        rawAssignment.product_id,
        rawAssignment.productId,
        rawAssignment.display_curve_id,
        rawAssignment.displayCurveId,
    ]
        .map((value) => String(value || '').trim())
        .filter((value, index, values) => Boolean(value) && values.indexOf(value) === index);
}

function curveFromSessionAssignment(rawAssignment: WdvSessionLayoutCurveState, catalog: CurveCatalogItem[]): CurveCatalogItem | null {
    const identityCandidates = sessionAssignmentIdentityCandidates(rawAssignment);
    const uidMatch = catalog.find((item) => item.curveUid && identityCandidates.includes(item.curveUid));
    if (uidMatch)
        return uidMatch;
    const directMatch = catalog.find((item) => identityCandidates.includes(item.curveId));
    if (directMatch)
        return directMatch;
    const mnemonic = String(rawAssignment.mnemonic || '').trim().toLowerCase();
    const unit = String(rawAssignment.unit || '').trim().toLowerCase();
    if (!mnemonic)
        return null;
    return catalog.find((item) => (item.mnemonic.trim().toLowerCase() === mnemonic
        && (!unit || item.unit.trim().toLowerCase() === unit))) ?? null;
}

function activeCurveIdsFromSession(session: WdvSessionLayoutResponse, catalog: CurveCatalogItem[]): string[] {
    const backendIdentities = [
        ...(session.active_curve_ids ?? session.activeCurveIds ?? []),
        ...(session.active_product_ids ?? session.activeProductIds ?? []),
        ...(session.active_display_curve_ids ?? session.activeDisplayCurveIds ?? []),
    ].map((value) => String(value || '').trim()).filter(Boolean);
    const activeIds = new Set<string>();
    catalog.forEach((curve) => {
        if (backendIdentities.includes(curve.curveId)) {
            activeIds.add(curve.curveId);
        }
    });
    (session.tracks ?? []).forEach((track) => {
        (track.curves ?? []).forEach((assignment) => {
            const curve = curveFromSessionAssignment(assignment, catalog);
            if (curve)
                activeIds.add(curve.curveId);
        });
    });
    return Array.from(activeIds);
}

function frontendTracksFromSession(session: WdvSessionLayoutResponse, catalog: CurveCatalogItem[]): WellLogTrack[] {
    const restoredTracks: WellLogTrack[] = [];
    (session.tracks ?? []).forEach((rawTrack, index) => {
        const trackType = rawTrack.track_type ?? rawTrack.trackType ?? 'curve';
        const trackId = rawTrack.track_id ?? rawTrack.trackId ?? `wdv-session-track-${index + 1}`;
        const trackIndex = finiteNumberOr(rawTrack.track_number ?? rawTrack.trackNumber, index);
        const title = rawTrack.track_name ?? rawTrack.trackName ?? `Track ${index + 1}`;
        const widthPx = finiteNumberOr(rawTrack.width_px ?? rawTrack.widthPx, trackType === 'depth' ? 86 : CURVE_TRACK_RESET_WIDTH);
        if (trackType === 'depth') {
            restoredTracks.push({
                trackId,
                trackIndex,
                trackType: 'depth',
                title,
                depthBasis: title === 'TVD' || title === 'TVDSS' ? title : 'MD',
                unit: 'm',
                widthPx,
                visible: true,
            });
            return;
        }
        if (trackType !== 'curve')
            return;
        const assignments = (rawTrack.curves ?? [])
            .map((rawAssignment, assignmentIndex) => {
            const curve = curveFromSessionAssignment(rawAssignment, catalog);
            if (!curve)
                return null;
            const fallback = makeCurveAssignment(curve, assignmentIndex);
            const scaleDirection = rawAssignment.scale_direction ?? rawAssignment.scaleDirection;
            const scaleType = rawAssignment.scale_type ?? rawAssignment.scaleType;
            const restoredAssignment: CurveAssignment = {
                ...fallback,
                assignmentId: rawAssignment.assignment_id ?? rawAssignment.assignmentId ?? fallback.assignmentId,
                curveUid: rawAssignment.curve_uid ?? rawAssignment.curveUid ?? fallback.curveUid ?? curve.curveUid ?? null,
                krCurveTypeId: rawAssignment.kr_curve_type_id ?? rawAssignment.krCurveTypeId ?? fallback.krCurveTypeId ?? curve.krCurveTypeId ?? null,
                wellUid: rawAssignment.well_uid ?? rawAssignment.wellUid ?? fallback.wellUid ?? curve.wellUid ?? null,
                sourceUid: rawAssignment.source_uid ?? rawAssignment.sourceUid ?? fallback.sourceUid ?? curve.sourceUid ?? null,
                observedMnemonic: rawAssignment.observed_mnemonic ?? rawAssignment.observedMnemonic ?? fallback.observedMnemonic ?? curve.observedMnemonic ?? curve.mnemonic,
                normalizedMnemonic: rawAssignment.normalized_mnemonic ?? rawAssignment.normalizedMnemonic ?? fallback.normalizedMnemonic ?? curve.normalizedMnemonic ?? curve.mnemonic,
                stackIndex: finiteNumberOr(rawAssignment.stack_index ?? rawAssignment.stackIndex, assignmentIndex),
                visible: rawAssignment.visible ?? fallback.visible,
                scaleMin: finiteNumberOr(rawAssignment.scale_min ?? rawAssignment.scaleMin, fallback.scaleMin),
                scaleMax: finiteNumberOr(rawAssignment.scale_max ?? rawAssignment.scaleMax, fallback.scaleMax),
                scaleMinLabel: typeof rawAssignment.scale_min_label === 'string' ? rawAssignment.scale_min_label : null,
                scaleMaxLabel: typeof rawAssignment.scale_max_label === 'string' ? rawAssignment.scale_max_label : null,
                scaleType: scaleType === 'log' || scaleType === 'linear' ? scaleType : fallback.scaleType,
                scaleDirection: scaleDirection === 'reverse' || scaleDirection === 'reversed' ? 'reverse' : 'normal',
                color: rawAssignment.color ?? fallback.color,
            };
            return restoredAssignment;
        })
            .filter((assignment): assignment is CurveAssignment => Boolean(assignment));
        restoredTracks.push({
            trackId,
            trackIndex,
            trackType: 'curve',
            title: assignments.length
                ? assignments.map((assignment) => curveById(catalog, assignment.curveId).mnemonic).join(' / ')
                : title,
            widthPx: clampCurveTrackWidth(widthPx),
            visible: true,
            lattice: rawTrack.lattice === 'logarithmic' ? 'logarithmic' : 'linear',
            latticeSource: rawTrack.lattice_source === 'user_override' || rawTrack.latticeSource === 'user_override' ? 'user_override' : 'front_curve_default',
            latticeOverride: rawTrack.lattice_source === 'user_override' || rawTrack.latticeSource === 'user_override',
            scaleMode: 'per_curve',
            curves: renumberCurveStack(assignments),
        });
    });
    return reindexTracks(restoredTracks);
}

function hasRenderableWdvTrackContent(tracks: WellLogTrack[]): boolean {
    return tracks.some((track) => track.trackType === 'curve' && track.curves.length > 0);
}

function sessionTracksForBackendPersistence(tracks: WellLogTrack[], catalog: CurveCatalogItem[]): WdvSessionLayoutTrackState[] {
    return hasRenderableWdvTrackContent(tracks) ? sessionTracksFromFrontend(tracks, catalog) : [];
}

function selectedTrackIdFromSession(session: WdvSessionLayoutResponse): string | null {
    return session.selected_track_id ?? session.selectedTrackId ?? null;
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

function reindexTracks(tracks: WellLogTrack[]): WellLogTrack[] {
    return sortTracks(tracks).map((track, index) => ({ ...track, trackIndex: index }));
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

function nextTrackId(trackType: ActiveTrackType): string {
    return `track-${trackType}-${Date.now()}-${Math.round(Math.random() * 100000)}`;
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
  const sessionLoadAbortRef = useRef<AbortController | null>(null);
  const sessionLoadGenerationRef = useRef(0);
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
  const [selectedInventoryCurveIds, setSelectedInventoryCurveIds] = useState<string[]>([]);
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
  const wdvSessionHydratedKeyRef = useRef<string | null>(null);
  const wdvSessionSaveTimerRef = useRef<number | null>(null);
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
          wdvSessionHydratedKeyRef.current = null;
          setTracks([]);
          setSelectedInventoryCurveIds([]);
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
  useEffect(() => {
      sessionLoadAbortRef.current?.abort();
      const controller = new AbortController();
      sessionLoadAbortRef.current = controller;
      const generation = sessionLoadGenerationRef.current + 1;
      sessionLoadGenerationRef.current = generation;
      if (!managedViewerWellId || !wdvSessionKey || wdvPackageState.loadedCurveItems.length === 0) {
          wdvSessionHydratedKeyRef.current = null;
          return () => controller.abort();
      }
      void fetchWlvJson<WdvSessionLayoutResponse>(`/api/wlv/wdv/sessions/${managedViewerWellId}/layout`, { signal: controller.signal })
          .then((session) => {
          if (controller.signal.aborted || sessionLoadGenerationRef.current !== generation)
              return;
          const candidateTracks = session.state_status === 'active'
              ? frontendTracksFromSession(session, activeCurveCatalog)
              : [];
          const restoredTracks = hasRenderableWdvTrackContent(candidateTracks) ? candidateTracks : [];
          if (restoredTracks.length > 0) {
              setTracks(restoredTracks);
              const selectedTrackId = selectedTrackIdFromSession(session);
              const selectedTrackExists = selectedTrackId && restoredTracks.some((track) => track.trackId === selectedTrackId);
              setSelection({ kind: 'track', trackId: selectedTrackExists ? selectedTrackId : restoredTracks[0].trackId });
          }
          else {
              setTracks([]);
              setSelection({ kind: 'track', trackId: '' });
              setSelectedInventoryCurveIds([]);
          }
          wdvSessionHydratedKeyRef.current = wdvSessionKey;
      })
          .catch((error) => {
          if (!controller.signal.aborted && sessionLoadGenerationRef.current === generation && !isAbortError(error)) {
              wdvSessionHydratedKeyRef.current = wdvSessionKey;
          }
      });
      return () => {
          controller.abort();
          if (sessionLoadAbortRef.current === controller)
              sessionLoadAbortRef.current = null;
      };
  }, [activeCurveCatalog, managedViewerWellId, wdvPackageState.loadedCurveItems.length, wdvSessionKey]);
  useEffect(() => {
      if (!managedViewerWellId || !wdvSessionKey || wdvSessionHydratedKeyRef.current !== wdvSessionKey)
          return undefined;
      if (wdvSessionSaveTimerRef.current !== null) {
          window.clearTimeout(wdvSessionSaveTimerRef.current);
      }
      wdvSessionSaveTimerRef.current = window.setTimeout(() => {
          const persistedTracks = sessionTracksForBackendPersistence(tracks, activeCurveCatalog);
          const selectedTrackId = persistedTracks.length > 0 && (selection.kind === 'track' || selection.kind === 'curve')
              ? selection.trackId
              : null;
          void fetchWlvJson<WdvSessionLayoutResponse>(`/api/wlv/wdv/sessions/${managedViewerWellId}/layout`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  selected_track_id: selectedTrackId,
                  tracks: persistedTracks,
                  source: 'frontend_user_layout_update',
              }),
          }).catch(() => {
              // Keep rendering responsive; backend-owned restore will use the last successful session save.
          });
      }, 400);
      return () => {
          if (wdvSessionSaveTimerRef.current !== null) {
              window.clearTimeout(wdvSessionSaveTimerRef.current);
              wdvSessionSaveTimerRef.current = null;
          }
      };
  }, [activeCurveCatalog, managedViewerWellId, selection, tracks, wdvSessionKey]);
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
  const handleWdvTemplateApplied = (session: WdvSessionLayoutResponse) => {
      const restoredTracks = frontendTracksFromSession(session, activeCurveCatalog);
      const activeCurveIds = activeCurveIdsFromSession(session, activeCurveCatalog);
      setTracks(restoredTracks);
      setSelectedInventoryCurveIds(Array.from(canonicalizeCurveIdentitySet(curveIdentityIndex, activeCurveIds)));
      const selectedTrackId = selectedTrackIdFromSession(session);
      const selectedTrackExists = selectedTrackId && restoredTracks.some((track) => track.trackId === selectedTrackId);
      if (restoredTracks.length > 0) {
          setSelection({ kind: 'track', trackId: selectedTrackExists ? selectedTrackId : restoredTracks[0].trackId });
      }
      wdvSessionHydratedKeyRef.current = wdvSessionKey;
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
  const selectedInventoryCanonicalIds = useMemo(
      () => canonicalizeCurveIdentitySet(curveIdentityIndex, selectedInventoryCurveIds),
      [curveIdentityIndex, selectedInventoryCurveIds],
  );
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
      setTracks((current) => {
          const ordered = sortTracks(current);
          const selected = ordered.find((track) => track.trackId === selection.trackId) ?? null;
          const insertionIndex = draft.insertMode === 'before_selected' && selected
              ? selected.trackIndex
              : draft.insertMode === 'after_selected' && selected
                  ? selected.trackIndex + 1
                  : ordered.length;
          const shifted = current.map((track) => (track.trackIndex >= insertionIndex ? { ...track, trackIndex: track.trackIndex + 1 } : track));
          const selectedCurves = pendingAddTrackCurveIds
              .map((curveId) => activeCurveCatalog.find((curve) => curve.curveId === curveId))
              .filter((curve): curve is CurveCatalogItem => Boolean(curve));
          const curveAssignments = draft.trackType === 'curve' && draft.curveSource === 'selected'
              ? selectedCurves.map((curve, index) => makeCurveAssignment(curve, index))
              : [];
          const frontCurve = curveAssignments[0]
              ? curveById(activeCurveCatalog, curveAssignments[0].curveId)
              : null;
          const latticeOverride = draft.trackType === 'curve' && draft.latticeMode !== 'auto';
          const lattice = draft.trackType === 'curve'
              ? draft.latticeMode === 'auto'
                  ? frontCurve?.defaultLattice ?? 'linear'
                  : draft.latticeMode
              : 'linear';
          const newTrack: WellLogTrack = draft.trackType === 'depth'
              ? {
                  trackId: nextTrackId('depth'),
                  trackIndex: insertionIndex,
                  trackType: 'depth',
                  title: draft.depthBasis,
                  depthBasis: draft.depthBasis,
                  unit: 'm',
                  widthPx: 86,
                  visible: true,
              }
              : {
                  trackId: nextTrackId('curve'),
                  trackIndex: insertionIndex,
                  trackType: 'curve',
                  title: curveAssignments.length > 0
                      ? curveAssignments.map((assignment) => curveById(activeCurveCatalog, assignment.curveId).mnemonic).join(' / ')
                      : 'NEW CURVE TRACK',
                  widthPx: 220,
                  visible: true,
                  lattice,
                  latticeSource: latticeOverride ? 'user_override' : 'front_curve_default',
                  latticeOverride,
                  scaleMode: draft.scaleMode,
                  curves: curveAssignments,
              };
          setSelection({ kind: 'track', trackId: newTrack.trackId });
          if (draft.trackType === 'curve' && draft.curveSource === 'selected') {
              setPendingAddTrackCurveIds([]);
              setAddTrackCurveSelectionMode(false);
          }
          return reindexTracks([...shifted, newTrack]);
      });
  };
  const deleteSelectedTrack = () => {
      if (!selectedTrack)
          return;
      setTracks((current) => {
          const remaining = reindexTracks(current.filter((track) => track.trackId !== selectedTrack.trackId));
          const fallback = remaining[Math.min(selectedTrack.trackIndex, Math.max(remaining.length - 1, 0))];
          if (fallback)
              setSelection({ kind: 'track', trackId: fallback.trackId });
          return remaining;
      });
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
      if (!selectedTrack || selectedTrack.trackType !== 'curve')
          return;
      const trackId = selectedTrack.trackId;
      setOpenCurveMenu(null);
      if (checked) {
          const curve = activeCurveCatalog.find((item) => item.curveId === curveId);
          if (!curve) {
              console.warn('Blocked curve assignment for unknown curve id', curveId);
              return;
          }
          const newAssignment = makeCurveAssignment(curve, selectedTrack.curves.length);
          setTracks((current) => current.map((track) => {
              if (track.trackId !== trackId || track.trackType !== 'curve')
                  return track;
              if (track.curves.some((assignment) => assignment.curveId === curveId))
                  return track;
              const nextCurves = renumberCurveStack([...orderedCurves(track), newAssignment]);
              return {
                  ...track,
                  curves: nextCurves,
                  latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default',
              };
          }));
          setSelection({ kind: 'curve', trackId, assignmentId: newAssignment.assignmentId });
          return;
      }
      setTracks((current) => current.map((track) => {
          if (track.trackId !== trackId || track.trackType !== 'curve')
              return track;
          return {
              ...track,
              curves: renumberCurveStack(track.curves.filter((assignment) => assignment.curveId !== curveId)),
              latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default',
          };
      }));
      setSelection({ kind: 'track', trackId });
  };
  const moveCurveToTrack = (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => {
      setTracks((current) => {
          let movingAssignment: CurveAssignment | null = null;
          let working = current.map((track) => {
              if (track.trackType !== 'curve')
                  return track;
              if (payload.fromTrackId === track.trackId && payload.assignmentId) {
                  const match = track.curves.find((assignment) => assignment.assignmentId === payload.assignmentId);
                  if (match)
                      movingAssignment = match;
                  return { ...track, curves: renumberCurveStack(track.curves.filter((assignment) => assignment.assignmentId !== payload.assignmentId)) };
              }
              return track;
          });
          const curve = activeCurveCatalog.find((item) => item.curveId === payload.curveId);
          if (!curve) {
              console.warn('Blocked curve assignment for unknown curve id', payload.curveId);
              return reindexTracks(working);
          }
          const assignment = movingAssignment ?? makeCurveAssignment(curve, 0);
          working = working.map((track) => {
              if (track.trackId !== toTrackId || track.trackType !== 'curve')
                  return track;
              const existing = track.curves.some((item) => item.assignmentId === assignment.assignmentId || item.curveId === assignment.curveId);
              if (existing)
                  return track;
              const next = [...orderedCurves(track)];
              const targetIndex = typeof toIndex === 'number' ? toIndex : next.length;
              next.splice(targetIndex, 0, { ...assignment, stackIndex: targetIndex });
              return { ...track, curves: renumberCurveStack(next), latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default' };
          });
          setSelection({ kind: 'curve', trackId: toTrackId, assignmentId: assignment.assignmentId });
          return reindexTracks(working);
      });
  };
  const reorderCurve = (trackId: string, assignmentId: string, toIndex: number) => {
      setTracks((current) => current.map((track) => {
          if (track.trackId !== trackId || track.trackType !== 'curve')
              return track;
          const ordered = orderedCurves(track);
          const fromIndex = ordered.findIndex((assignment) => assignment.assignmentId === assignmentId);
          if (fromIndex < 0)
              return track;
          const [item] = ordered.splice(fromIndex, 1);
          ordered.splice(toIndex, 0, item);
          return { ...track, curves: renumberCurveStack(ordered), latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default' };
      }));
      setSelection({ kind: 'curve', trackId, assignmentId });
  };
  const removeCurveFromTrack = (trackId: string, assignmentId: string) => {
      setTracks((current) => current.map((track) => {
          if (track.trackId !== trackId || track.trackType !== 'curve')
              return track;
          return {
              ...track,
              curves: renumberCurveStack(track.curves.filter((assignment) => assignment.assignmentId !== assignmentId)),
              latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default',
          };
      }));
      setOpenCurveMenu(null);
      setSelection({ kind: 'track', trackId });
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

      {wdvTemplateModalOpen && selectedWdvTemplateRecommendation ? (<WdvTemplateRecommendationModal recommendation={selectedWdvTemplateRecommendation} loadedCurveItems={wdvPackageState.loadedCurveItems} managedWellId={managedViewerWellId} onClose={() => setWdvTemplateModalOpen(false)} onApplied={handleWdvTemplateApplied}/>) : null}

      <div className={`wlv-prototype-workspace wlv-track-backdrop-${trackBackdropMode} ${curveInventoryResizeState ? 'curve-inventory-resize-active' : ''} ${curveInventoryCollapsed ? 'curve-inventory-collapsed' : ''}`} style={{ gridTemplateColumns: `${curveInventoryCollapsed ? 38 : curveInventoryWidthPx}px minmax(0, 1fr) 330px` }}>
        <div className={`wlv-curve-inventory-shell ${curveInventoryCollapsed ? 'collapsed' : ''}`} style={{ width: curveInventoryCollapsed ? 38 : curveInventoryWidthPx }}>
        <button type="button" className="wlv-curve-inventory-collapse-toggle" onClick={() => setCurveInventoryCollapsed((collapsed) => !collapsed)} aria-expanded={!curveInventoryCollapsed} aria-label={curveInventoryCollapsed ? 'Expand Curve Inventory' : 'Collapse Curve Inventory'} title={curveInventoryCollapsed ? 'Expand Curve Inventory' : 'Collapse Curve Inventory'}>
          {curveInventoryCollapsed ? '›' : '‹'}
        </button>
        {curveInventoryCollapsed ? (<div className="wlv-curve-inventory-collapsed-label" aria-hidden="true">Curves</div>) : (<>
        {wdvWorkspaceError && <div className="wlv-workspace-error">{wdvWorkspaceError}</div>}
        <CurveInventory availableCurves={activeViewerCurves} curveUsageCounts={curveUsageCounts} visibleTrackCurveIds={visibleTrackCurveIds} selectedTrackCurveIds={addTrackCurveSelectionMode ? pendingAddTrackCanonicalIds : selectedTrackCurveIds} selectedCurveIds={new Set([...selectedInventoryCanonicalIds, ...Array.from(visibleTrackCurveIds)])} assignmentEnabled={addTrackCurveSelectionMode || selectedTrack?.trackType === 'curve'} preferredInventoryTab={tracks.length > 0 ? 'selected' : 'all'} loadedWells={wdvWorkspace?.loaded_wells ?? []} activeWell={activeInventoryWell} curveRunMetadata={activeCurveRunMetadata} onActiveWellChange={(managedWellId) => {
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
            setSelectedInventoryCurveIds((current) => (current.includes(curveId)
                ? current.filter((item) => item !== curveId)
                : [...current, curveId]));
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
