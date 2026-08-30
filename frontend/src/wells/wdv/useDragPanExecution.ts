import type { Dispatch, SetStateAction } from 'react';
import type { DepthViewRange } from './WdvPresentationPrimitives';
import { planDragPanViewportUpdate } from './viewportControl';
import type { ViewportTieGroup } from './viewportSemantics';

export type DragPanState = {
  startY: number;
  startRange: DepthViewRange;
  clampRange: DepthViewRange;
  targetTrackId?: string;
  targetTrackIds?: string[];
  targetViewportTieGroupId?: string;
  startTrackRangesById?: Record<string, DepthViewRange>;
};

export type DragPanStartPlan =
  | { kind: 'blocked' }
  | { kind: 'tie'; state: DragPanState; groupId: string; historyRange: DepthViewRange }
  | { kind: 'track'; state: DragPanState }
  | { kind: 'global'; state: DragPanState; historyRange: DepthViewRange };

function blankSpaceOverscrollRange(
  range: DepthViewRange,
  viewport: DepthViewRange,
  enabled: boolean,
): DepthViewRange {
  if (!enabled) return range;
  const halfViewportSpan = Math.max(0, (viewport.max - viewport.min) / 2);
  return {
    min: range.min - halfViewportSpan,
    max: range.max + halfViewportSpan,
  };
}

/** Pure gesture-start routing. No React state and no backend activity. */
export function planDragPanStart(input: {
  startY: number;
  sourceTrackId: string | null;
  lockedTrackIds: ReadonlySet<string>;
  viewportTieGroups: ViewportTieGroup[];
  globalViewportMode: boolean;
  viewDepthRange: DepthViewRange;
  trackFullDepthRangesById: Record<string, DepthViewRange>;
  canvasAllTrackDepthRange: DepthViewRange;
  effectiveTrackDepthRangesById: Record<string, DepthViewRange>;
  blankSpacePanTrackIds?: ReadonlySet<string>;
}): DragPanStartPlan {
  const sourceTrackId = input.sourceTrackId;
  const blankSpacePanTrackIds = input.blankSpacePanTrackIds;
  if (sourceTrackId && input.lockedTrackIds.has(sourceTrackId)) return { kind: 'blocked' };

  const tieGroup = sourceTrackId
    ? input.viewportTieGroups.find((group) => group.memberTrackIds.includes(sourceTrackId)) ?? null
    : null;
  if (tieGroup) {
    if (input.lockedTrackIds.has(tieGroup.leaderTrackId)) return { kind: 'blocked' };
    return {
      kind: 'tie',
      groupId: tieGroup.groupId,
      historyRange: tieGroup.viewport,
      state: {
        startY: input.startY,
        startRange: tieGroup.viewport,
        clampRange: blankSpaceOverscrollRange(
          input.trackFullDepthRangesById[tieGroup.leaderTrackId] ?? input.canvasAllTrackDepthRange,
          tieGroup.viewport,
          Boolean(
            blankSpacePanTrackIds
            && (
              (sourceTrackId ? blankSpacePanTrackIds.has(sourceTrackId) : false)
              || blankSpacePanTrackIds.has(tieGroup.leaderTrackId)
            )
          ),
        ),
        targetTrackIds: tieGroup.memberTrackIds,
        targetViewportTieGroupId: tieGroup.groupId,
      },
    };
  }

  if (input.globalViewportMode) {
    return {
      kind: 'global',
      historyRange: input.viewDepthRange,
      state: {
        startY: input.startY,
        startRange: input.viewDepthRange,
        clampRange: blankSpaceOverscrollRange(
          input.canvasAllTrackDepthRange,
          input.viewDepthRange,
          Boolean(sourceTrackId && blankSpacePanTrackIds?.has(sourceTrackId)),
        ),
      },
    };
  }

  if (sourceTrackId) {
    return {
      kind: 'track',
      state: {
        startY: input.startY,
        startRange: input.effectiveTrackDepthRangesById[sourceTrackId] ?? input.viewDepthRange,
        clampRange: blankSpaceOverscrollRange(
          input.trackFullDepthRangesById[sourceTrackId] ?? input.canvasAllTrackDepthRange,
          input.effectiveTrackDepthRangesById[sourceTrackId] ?? input.viewDepthRange,
          Boolean(blankSpacePanTrackIds?.has(sourceTrackId)),
        ),
        targetTrackId: sourceTrackId,
      },
    };
  }

  return {
    kind: 'global',
    historyRange: input.viewDepthRange,
    state: {
      startY: input.startY,
      startRange: input.viewDepthRange,
      clampRange: input.canvasAllTrackDepthRange,
    },
  };
}

type Args = {
  dragPanState: DragPanState | null;
  setDragPanState: Dispatch<SetStateAction<DragPanState | null>>;
  combinationLockedTrackIdSet: ReadonlySet<string>;
  viewportTieGroups: ViewportTieGroup[];
  setViewportTieGroups: Dispatch<SetStateAction<ViewportTieGroup[]>>;
  setViewportTieSuspendedTrackIds: Dispatch<SetStateAction<string[]>>;
  setViewportTieHistoryByGroupId: Dispatch<SetStateAction<Record<string, DepthViewRange[]>>>;
  globalViewportMode: boolean;
  viewDepthRange: DepthViewRange;
  setViewDepthRange: Dispatch<SetStateAction<DepthViewRange>>;
  setViewHistory: Dispatch<SetStateAction<DepthViewRange[]>>;
  trackFullDepthRangesById: Record<string, DepthViewRange>;
  canvasAllTrackDepthRange: DepthViewRange;
  effectiveTrackDepthRangesById: Record<string, DepthViewRange>;
  blankSpacePanTrackIds?: ReadonlySet<string>;
  setTrackDepthRangesById: Dispatch<SetStateAction<Record<string, DepthViewRange>>>;
  setCombinationGroupViewRange: Dispatch<SetStateAction<DepthViewRange | null>>;
  minSpan: number;
};

/**
 * Frontend-local drag-pan execution boundary.
 *
 * Pointer-move preview intentionally stays local. This controller owns gesture
 * routing and React setter choreography only; it performs no network or durable
 * persistence writes. The settled-view commit lane observes state after the
 * drag ends and persists it separately.
 */
export function useDragPanExecution(args: Args) {
  const beginDragPan = (startY: number, sourceTrackId: string | null) => {
    const plan = planDragPanStart({
      startY,
      sourceTrackId,
      lockedTrackIds: args.combinationLockedTrackIdSet,
      viewportTieGroups: args.viewportTieGroups,
      globalViewportMode: args.globalViewportMode,
      viewDepthRange: args.viewDepthRange,
      trackFullDepthRangesById: args.trackFullDepthRangesById,
      canvasAllTrackDepthRange: args.canvasAllTrackDepthRange,
      effectiveTrackDepthRangesById: args.effectiveTrackDepthRangesById,
      blankSpacePanTrackIds: args.blankSpacePanTrackIds,
    });
    if (plan.kind === 'blocked') return;

    if (plan.kind === 'tie') {
      args.setViewportTieHistoryByGroupId((current) => ({
        ...current,
        [plan.groupId]: [
          ...(current[plan.groupId] ?? []).slice(-9),
          plan.historyRange,
        ],
      }));
    } else if (plan.kind === 'global') {
      args.setViewHistory((history) => [...history.slice(-9), plan.historyRange]);
    }
    args.setDragPanState(plan.state);
  };

  const updateDragPan = (currentY: number, canvasHeight: number) => {
    if (!args.dragPanState) return;
    const plan = planDragPanViewportUpdate({
      dragPanState: args.dragPanState,
      currentY,
      canvasHeight,
      minSpan: args.minSpan,
    });

    if (plan.kind === 'tie') {
      args.setViewportTieGroups((groups) => groups.map((group) =>
        group.groupId === plan.groupId ? { ...group, viewport: plan.range } : group,
      ));
      args.setViewportTieSuspendedTrackIds((ids) => {
        const tiedTrackIds = new Set(plan.memberTrackIds);
        return ids.filter((id) => !tiedTrackIds.has(id));
      });
      return;
    }
    if (plan.kind === 'track') {
      args.setTrackDepthRangesById((ranges) => ({ ...ranges, [plan.trackId]: plan.range }));
      return;
    }
    if (plan.kind === 'group') {
      args.setCombinationGroupViewRange(plan.range);
      return;
    }
    args.setViewDepthRange(plan.range);
  };

  const endDragPan = () => args.setDragPanState(null);

  return { beginDragPan, updateDragPan, endDragPan };
}
