import { useState } from 'react';
import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { ViewportTieGroup } from './viewportSemantics';

export type ViewportRelationshipInitialState = {
  viewDepthRange: DepthViewRange;
  combinationActiveTrackIds: string[];
  combinationLockedTrackIds: string[];
  multiHighlightedTrackIds: string[];
  trackDepthRangesById: Record<string, DepthViewRange>;
  combinationGroupViewRange: DepthViewRange | null;
  combinationGroupHistory: DepthViewRange[];
  viewportTieGroups: ViewportTieGroup[];
  viewportTieSuspendedTrackIds: string[];
  viewportTieHistoryByGroupId: Record<string, DepthViewRange[]>;
};

export function createViewportRelationshipInitialState(
  initialViewDepthRange: DepthViewRange,
): ViewportRelationshipInitialState {
  return {
    viewDepthRange: initialViewDepthRange,
    combinationActiveTrackIds: [],
    combinationLockedTrackIds: [],
    multiHighlightedTrackIds: [],
    trackDepthRangesById: {},
    combinationGroupViewRange: null,
    combinationGroupHistory: [],
    viewportTieGroups: [],
    viewportTieSuspendedTrackIds: [],
    viewportTieHistoryByGroupId: {},
  };
}

/**
 * Owns the React execution state for WDV viewport relationships.
 *
 * Semantic decisions remain in the pure viewport planners. This hook is the
 * single React-state boundary that executes those decisions. Keeping it out of
 * WdvPageBoundary prevents the page component from becoming a second semantic
 * owner while preserving local, latency-free interaction updates.
 */
export function useViewportRelationshipState(initialViewDepthRange: DepthViewRange) {
  const initial = createViewportRelationshipInitialState(initialViewDepthRange);

  const [viewDepthRange, setViewDepthRange] = useState<DepthViewRange>(initial.viewDepthRange);
  const [combinationActiveTrackIds, setCombinationActiveTrackIds] = useState<string[]>(initial.combinationActiveTrackIds);
  const [combinationLockedTrackIds, setCombinationLockedTrackIds] = useState<string[]>(initial.combinationLockedTrackIds);
  const [multiHighlightedTrackIds, setMultiHighlightedTrackIds] = useState<string[]>(initial.multiHighlightedTrackIds);
  const [trackDepthRangesById, setTrackDepthRangesById] = useState<Record<string, DepthViewRange>>(initial.trackDepthRangesById);
  const [combinationGroupViewRange, setCombinationGroupViewRange] = useState<DepthViewRange | null>(initial.combinationGroupViewRange);
  const [, setCombinationGroupHistory] = useState<DepthViewRange[]>(initial.combinationGroupHistory);
  const [viewportTieGroups, setViewportTieGroups] = useState<ViewportTieGroup[]>(initial.viewportTieGroups);
  const [viewportTieSuspendedTrackIds, setViewportTieSuspendedTrackIds] = useState<string[]>(initial.viewportTieSuspendedTrackIds);
  const [viewportTieHistoryByGroupId, setViewportTieHistoryByGroupId] = useState<Record<string, DepthViewRange[]>>(initial.viewportTieHistoryByGroupId);

  return {
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
  };
}
