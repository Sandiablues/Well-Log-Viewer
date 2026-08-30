import type { Dispatch, SetStateAction } from 'react';
import { clampValue, type DepthViewRange, type IntervalSelectionState } from './WdvPresentationPrimitives';
import type { DragPanState } from './useDragPanExecution';
import type { ViewportTieGroup } from './viewportSemantics';

function clampDepthRange(range: DepthViewRange, fullRange: DepthViewRange, minSpan: number): DepthViewRange {
  const span = Math.max(minSpan, range.max - range.min);
  let min = range.min;
  let max = min + span;
  if (min < fullRange.min) {
    max += fullRange.min - min;
    min = fullRange.min;
  }
  if (max > fullRange.max) {
    min -= max - fullRange.max;
    max = fullRange.max;
  }
  min = Math.max(fullRange.min, min);
  max = Math.min(fullRange.max, max);
  if (max - min < minSpan) {
    min = Math.max(fullRange.min, max - minSpan);
    max = Math.min(fullRange.max, min + minSpan);
  }
  return { min, max };
}

type Args = {
  viewDepthRange: DepthViewRange;
  setViewDepthRange: Dispatch<SetStateAction<DepthViewRange>>;
  setViewHistory: Dispatch<SetStateAction<DepthViewRange[]>>;
  selectedViewportTieGroup: ViewportTieGroup | null;
  setViewportTieGroups: Dispatch<SetStateAction<ViewportTieGroup[]>>;
  setViewportTieHistoryByGroupId: Dispatch<SetStateAction<Record<string, DepthViewRange[]>>>;
  groupActionTrackIds: string[];
  activeGroupViewRange: DepthViewRange | null;
  viewportCommandFullRange: DepthViewRange | null;
  setCombinationGroupHistory: Dispatch<SetStateAction<DepthViewRange[]>>;
  setCombinationGroupViewRange: Dispatch<SetStateAction<DepthViewRange | null>>;
  globalViewportMode: boolean;
  trackIds: string[];
  trackFullDepthRangesById: Record<string, DepthViewRange>;
  canvasAssignedCurveDepthRange: DepthViewRange;
  setTrackDepthRangesById: Dispatch<SetStateAction<Record<string, DepthViewRange>>>;
  lockedCombinationTrackIds: string[];
  setIntervalZoomActive: Dispatch<SetStateAction<boolean>>;
  setIntervalSelection: Dispatch<SetStateAction<IntervalSelectionState | null>>;
  setDragPanState: Dispatch<SetStateAction<DragPanState | null>>;
  setGoToDepthMarker: Dispatch<SetStateAction<number | null>>;
  goToDepthValue: string;
  setGoToDepthValue: Dispatch<SetStateAction<string>>;
  applyCombinationRange: (range: DepthViewRange, recordHistory?: boolean) => void;
  recordGroupHistory: () => void;
  rangesEqual: (a: DepthViewRange, b: DepthViewRange) => boolean;
  minSpan: number;
  goToReviewWindow: number;
};

/**
 * Execution boundary for discrete viewport navigation commands.
 *
 * These commands are settled interactions (Previous, Full, Reset, Go To MD /
 * Formation Top Go). They remain frontend-local for immediate response, but all
 * setter choreography is centralized here and is subsequently persisted by the
 * revision-guarded committed-view lane.
 */
export function useViewportNavigationExecution(args: Args) {
  const setDepthView = (nextRange: DepthViewRange, recordHistory = true) => {
    args.setViewDepthRange((current) => {
      const clipped = clampDepthRange(nextRange, args.canvasAssignedCurveDepthRange, args.minSpan);
      if (args.rangesEqual(current, clipped)) return current;
      if (recordHistory) args.setViewHistory((history) => [...history.slice(-9), current]);
      return clipped;
    });
  };

  const previousDepthView = () => {
    if (args.selectedViewportTieGroup) {
      args.setViewportTieHistoryByGroupId((current) => {
        const history = current[args.selectedViewportTieGroup!.groupId] ?? [];
        const previous = history[history.length - 1];
        if (!previous) return current;
        args.setViewportTieGroups((groups) => groups.map((group) =>
          group.groupId === args.selectedViewportTieGroup!.groupId
            ? { ...group, viewport: previous }
            : group,
        ));
        return { ...current, [args.selectedViewportTieGroup!.groupId]: history.slice(0, -1) };
      });
      return;
    }
    if (args.groupActionTrackIds.length > 0) {
      args.setCombinationGroupHistory((history) => {
        const previous = history[history.length - 1];
        if (!previous) return history;
        args.setTrackDepthRangesById((current) => {
          const next = { ...current };
          for (const trackId of args.groupActionTrackIds) next[trackId] = previous;
          return next;
        });
        return history.slice(0, -1);
      });
      return;
    }
    args.setViewHistory((history) => {
      const previous = history[history.length - 1];
      if (!previous) return history;
      args.setViewDepthRange(previous);
      return history.slice(0, -1);
    });
  };

  const clearTransientNavigationState = () => {
    args.setIntervalZoomActive(false);
    args.setIntervalSelection(null);
    args.setDragPanState(null);
    args.setGoToDepthMarker(null);
  };

  const fitDepth = () => {
    clearTransientNavigationState();
    if (!args.viewportCommandFullRange) return;
    if (!args.selectedViewportTieGroup && args.groupActionTrackIds.length === 0) return;
    // Full is target-owned: selected track domain, or Tie leader domain.
    args.applyCombinationRange(args.viewportCommandFullRange);
  };

  const resetDepthView = () => {
    // Until a distinct persisted per-track reset range exists, Reset returns the
    // selected authority to its own full/default renderable domain. It must never
    // borrow an unrelated canvas curve domain.
    if (args.viewportCommandFullRange
        && (args.selectedViewportTieGroup || args.groupActionTrackIds.length > 0)) {
      args.applyCombinationRange(args.viewportCommandFullRange, false);
    }
    clearTransientNavigationState();
    args.setGoToDepthValue('');
  };

  const centerGoToDepthTarget = (target: number) => {
    const scopeFullRange = args.viewportCommandFullRange;
    const scopeCurrentRange = args.activeGroupViewRange;
    if (!scopeFullRange || !scopeCurrentRange) return target;

    const clampedTarget = clampValue(
      target,
      scopeFullRange.min,
      scopeFullRange.max,
    );
    const currentSpan = Math.max(
      args.minSpan,
      scopeCurrentRange.max - scopeCurrentRange.min,
    );
    const requestedReviewSpan = Math.min(currentSpan, args.goToReviewWindow);
    const distanceToTop = clampedTarget - scopeFullRange.min;
    const distanceToBase = scopeFullRange.max - clampedTarget;
    const centeredBoundSpan = Math.max(args.minSpan, 2 * Math.min(distanceToTop, distanceToBase));
    const reviewSpan = Math.max(args.minSpan, Math.min(requestedReviewSpan, centeredBoundSpan));
    const centeredRange = clampDepthRange(
      { min: clampedTarget - reviewSpan / 2, max: clampedTarget + reviewSpan / 2 },
      scopeFullRange,
      args.minSpan,
    );

    // Go To MD and Formation Top Go use the same selected/Tie viewport authority
    // as Zoom and Range. With no selected target, Go To does not move the canvas.
    if (!args.selectedViewportTieGroup && args.groupActionTrackIds.length === 0) {
      return clampedTarget;
    }
    args.applyCombinationRange(centeredRange);
    args.setGoToDepthMarker(clampedTarget);
    return clampedTarget;
  };

  const goToDepth = () => {
    const target = Number.parseFloat(args.goToDepthValue);
    if (!Number.isFinite(target)) return;
    const centeredTarget = centerGoToDepthTarget(target);
    args.setGoToDepthValue(String(Number(centeredTarget.toFixed(6))));
  };

  return { setDepthView, previousDepthView, fitDepth, resetDepthView, centerGoToDepthTarget, goToDepth };
}
