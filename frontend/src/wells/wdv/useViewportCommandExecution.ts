import type { Dispatch, SetStateAction } from 'react';
import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { ViewportTieGroup } from './viewportSemantics';
import {
  calculateZoomViewportRange,
  planViewportRangeApplication,
} from './viewportControl';
import {
  planCombinationTrackToggle,
  planCreateViewportTie,
  planLockTracks,
  planUnlockTracks,
  planUntieViewportTracks,
} from './viewportMembershipControl';

type Args = {
  viewDepthRange: DepthViewRange;
  setViewDepthRange: Dispatch<SetStateAction<DepthViewRange>>;
  combinationActiveTrackIds: string[];
  setCombinationActiveTrackIds: Dispatch<SetStateAction<string[]>>;
  combinationLockedTrackIds: string[];
  setCombinationLockedTrackIds: Dispatch<SetStateAction<string[]>>;
  trackDepthRangesById: Record<string, DepthViewRange>;
  setTrackDepthRangesById: Dispatch<SetStateAction<Record<string, DepthViewRange>>>;
  setCombinationGroupViewRange: Dispatch<SetStateAction<DepthViewRange | null>>;
  setCombinationGroupHistory: Dispatch<SetStateAction<DepthViewRange[]>>;
  viewportTieGroups: ViewportTieGroup[];
  setViewportTieGroups: Dispatch<SetStateAction<ViewportTieGroup[]>>;
  viewportTieSuspendedTrackIds: string[];
  setViewportTieSuspendedTrackIds: Dispatch<SetStateAction<string[]>>;
  viewportTieHistoryByGroupId: Record<string, DepthViewRange[]>;
  setViewportTieHistoryByGroupId: Dispatch<SetStateAction<Record<string, DepthViewRange[]>>>;
  setViewHistory: Dispatch<SetStateAction<DepthViewRange[]>>;
  fullRange: DepthViewRange;
  magnificationReferenceRange: DepthViewRange;
  zoomOuterRange: DepthViewRange;
  minSpan: number;
  selectedViewportTieGroup: ViewportTieGroup | null;
  selectedViewportTieLeaderLocked: boolean;
  groupActionTrackIds: string[];
  globalViewportMode: boolean;
  lockedCombinationTrackIds: string[];
  activeGroupViewRange: DepthViewRange | null;
  effectiveTrackDepthRangesById: Record<string, DepthViewRange>;
  viewportTieCanCreate: boolean;
  viewportTieCanUntie: boolean;
  viewportTieCandidateTrackIds: string[];
  viewportTieActionTrackIds: string[];
  viewportTieSelectedTiedTrackIds: string[];
  viewportTieMembershipByTrackId: ReadonlyMap<string, ViewportTieGroup>;
  combinationLockActionTrackIds: string[];
  rangesEqual: (a: DepthViewRange, b: DepthViewRange) => boolean;
};

/**
 * Single local command-execution boundary for committed viewport relationship
 * operations. Pure planners own semantics; this controller only executes the
 * resulting React state changes. High-frequency drag preview remains outside
 * this hook so pointer latency never depends on backend or persistence work.
 */
export function useViewportCommandExecution(args: Args) {
  const clearUnlockedTrackViewport = (trackId: string) => {
    if (args.combinationLockedTrackIds.includes(trackId)) return;
    args.setTrackDepthRangesById((ranges) => {
      if (!(trackId in ranges)) return ranges;
      const next = { ...ranges };
      delete next[trackId];
      return next;
    });
  };

  const toggleCombinationTrack = (trackId: string) => {
    const plan = planCombinationTrackToggle({
      trackId,
      lockedTrackIds: args.combinationLockedTrackIds,
      activeTrackIds: args.combinationActiveTrackIds,
    });
    if (plan.kind === 'blocked') return;
    if (plan.clearTrackViewport) clearUnlockedTrackViewport(trackId);
    if (plan.groupViewRangeAction === 'set-current') args.setCombinationGroupViewRange(args.viewDepthRange);
    if (plan.groupViewRangeAction === 'clear') args.setCombinationGroupViewRange(null);
    if (plan.resetGroupHistory) args.setCombinationGroupHistory([]);
    args.setCombinationActiveTrackIds(plan.activeTrackIds);
  };

  const createViewportTie = (leaderTrackId: string) => {
    const plan = planCreateViewportTie({
      canCreate: args.viewportTieCanCreate,
      leaderTrackId,
      candidateTrackIds: args.viewportTieCandidateTrackIds,
      actionTrackIds: args.viewportTieActionTrackIds,
      effectiveTrackDepthRangesById: args.effectiveTrackDepthRangesById,
      viewDepthRange: args.viewDepthRange,
      groups: args.viewportTieGroups,
      historyByGroupId: args.viewportTieHistoryByGroupId,
      suspendedTrackIds: args.viewportTieSuspendedTrackIds,
    });
    if (!plan) return;
    args.setViewportTieGroups(plan.groups);
    args.setViewportTieHistoryByGroupId(plan.historyByGroupId);
    args.setViewportTieSuspendedTrackIds(plan.suspendedTrackIds);
  };

  const untieSelectedViewportTracks = () => {
    const plan = planUntieViewportTracks({
      canUntie: args.viewportTieCanUntie,
      selectedTiedTrackIds: args.viewportTieSelectedTiedTrackIds,
      groups: args.viewportTieGroups,
      trackDepthRangesById: args.trackDepthRangesById,
      suspendedTrackIds: args.viewportTieSuspendedTrackIds,
      historyByGroupId: args.viewportTieHistoryByGroupId,
    });
    if (!plan) return;
    args.setViewportTieGroups(plan.groups);
    args.setTrackDepthRangesById(plan.trackDepthRangesById);
    args.setViewportTieSuspendedTrackIds(plan.suspendedTrackIds);
    args.setViewportTieHistoryByGroupId(plan.historyByGroupId);
  };

  const lockSelectedCombinationTracks = () => {
    const plan = planLockTracks({
      actionTrackIds: args.combinationLockActionTrackIds,
      trackDepthRangesById: args.trackDepthRangesById,
      lockedTrackIds: args.combinationLockedTrackIds,
      activeTrackIds: args.combinationActiveTrackIds,
      groupActionTrackIds: args.groupActionTrackIds,
      activeGroupViewRange: args.activeGroupViewRange,
      effectiveTrackDepthRangesById: args.effectiveTrackDepthRangesById,
      viewDepthRange: args.viewDepthRange,
    });
    if (!plan) return;
    args.setTrackDepthRangesById(plan.trackDepthRangesById);
    args.setCombinationLockedTrackIds(plan.lockedTrackIds);
    args.setCombinationActiveTrackIds(plan.activeTrackIds);
    if (plan.clearGroupViewport) {
      args.setCombinationGroupViewRange(null);
      args.setCombinationGroupHistory([]);
    }
  };

  const unlockSelectedCombinationTracks = () => {
    const plan = planUnlockTracks({
      actionTrackIds: args.combinationLockActionTrackIds,
      lockedTrackIds: args.combinationLockedTrackIds,
      activeTrackIds: args.combinationActiveTrackIds,
      suspendedTrackIds: args.viewportTieSuspendedTrackIds,
      tieMemberTrackIds: Array.from(args.viewportTieMembershipByTrackId.keys()),
    });
    if (!plan) return;
    args.setCombinationLockedTrackIds(plan.lockedTrackIds);
    args.setCombinationActiveTrackIds(plan.activeTrackIds);
    args.setViewportTieSuspendedTrackIds(plan.suspendedTrackIds);
  };

  const suspendIndividuallyManipulatedTieFollowers = (trackIds: string[]) => {
    const tiedFollowerIds = trackIds.filter((trackId) => {
      const group = args.viewportTieMembershipByTrackId.get(trackId);
      return Boolean(group && group.leaderTrackId !== trackId);
    });
    if (tiedFollowerIds.length === 0) return;
    args.setViewportTieSuspendedTrackIds((current) => Array.from(new Set([
      ...current,
      ...tiedFollowerIds,
    ])));
  };

  const recordGroupHistory = () => {
    if (!args.activeGroupViewRange) return;
    if (args.selectedViewportTieGroup) {
      args.setViewportTieHistoryByGroupId((current) => ({
        ...current,
        [args.selectedViewportTieGroup!.groupId]: [
          ...(current[args.selectedViewportTieGroup!.groupId] ?? []).slice(-9),
          args.activeGroupViewRange!,
        ],
      }));
      return;
    }
    args.setCombinationGroupHistory((history) => [
      ...history.slice(-9),
      args.activeGroupViewRange!,
    ]);
  };

  const applyCombinationRange = (nextRange: DepthViewRange, recordHistory = true) => {
    const plan = planViewportRangeApplication({
      nextRange,
      fullRange: args.fullRange,
      minSpan: args.minSpan,
      selectedViewportTieGroup: args.selectedViewportTieGroup,
      selectedViewportTieLeaderLocked: args.selectedViewportTieLeaderLocked,
      groupActionTrackIds: args.groupActionTrackIds,
      globalViewportMode: args.globalViewportMode,
      lockedTrackIds: args.lockedCombinationTrackIds,
      trackDepthRangesById: args.trackDepthRangesById,
      viewDepthRange: args.viewDepthRange,
    });

    if (plan.kind === 'blocked') return;
    if (plan.kind === 'tie') {
      if (recordHistory) recordGroupHistory();
      args.setViewportTieGroups((groups) => groups.map((group) =>
        group.groupId === plan.groupId ? { ...group, viewport: plan.range } : group,
      ));
      args.setViewportTieSuspendedTrackIds((ids) => ids.filter((id) => !plan.memberTrackIds.includes(id)));
      return;
    }
    if (plan.kind === 'group') {
      if (recordHistory) recordGroupHistory();
      args.setTrackDepthRangesById((current) => {
        const next = { ...current };
        for (const trackId of plan.memberTrackIds) next[trackId] = plan.range;
        return next;
      });
      suspendIndividuallyManipulatedTieFollowers(plan.memberTrackIds);
      return;
    }

    args.setTrackDepthRangesById(plan.frozenTrackDepthRangesById);
    args.setViewDepthRange((current) => {
      if (args.rangesEqual(current, plan.range)) return current;
      if (recordHistory) args.setViewHistory((history) => [...history.slice(-9), current]);
      return plan.range;
    });
  };

  const zoomDepth = (factor: number) => {
    const nextRange = calculateZoomViewportRange({
      viewDepthRange: args.viewDepthRange,
      groupActionTrackIds: args.groupActionTrackIds,
      activeGroupViewRange: args.activeGroupViewRange,
      fullRange: args.zoomOuterRange,
      magnificationReferenceRange: args.magnificationReferenceRange,
      factor,
      minSpan: args.minSpan,
    });
    const plan = planViewportRangeApplication({
      nextRange,
      fullRange: args.zoomOuterRange,
      minSpan: args.minSpan,
      selectedViewportTieGroup: args.selectedViewportTieGroup,
      selectedViewportTieLeaderLocked: args.selectedViewportTieLeaderLocked,
      groupActionTrackIds: args.groupActionTrackIds,
      globalViewportMode: args.globalViewportMode,
      lockedTrackIds: args.lockedCombinationTrackIds,
      trackDepthRangesById: args.trackDepthRangesById,
      viewDepthRange: args.viewDepthRange,
    });

    if (plan.kind === 'blocked') return;
    if (plan.kind === 'tie') {
      recordGroupHistory();
      args.setViewportTieGroups((groups) => groups.map((group) =>
        group.groupId === plan.groupId ? { ...group, viewport: plan.range } : group,
      ));
      args.setViewportTieSuspendedTrackIds((ids) =>
        ids.filter((id) => !plan.memberTrackIds.includes(id)),
      );
      return;
    }
    if (plan.kind === 'group') {
      recordGroupHistory();
      args.setTrackDepthRangesById((current) => {
        const next = { ...current };
        for (const trackId of plan.memberTrackIds) next[trackId] = plan.range;
        return next;
      });
      suspendIndividuallyManipulatedTieFollowers(plan.memberTrackIds);
      return;
    }

    args.setTrackDepthRangesById(plan.frozenTrackDepthRangesById);
    args.setViewDepthRange((current) => {
      if (args.rangesEqual(current, plan.range)) return current;
      args.setViewHistory((history) => [...history.slice(-9), current]);
      return plan.range;
    });
  };

  return {
    toggleCombinationTrack,
    createViewportTie,
    untieSelectedViewportTracks,
    lockSelectedCombinationTracks,
    unlockSelectedCombinationTracks,
    recordGroupHistory,
    applyCombinationRange,
    zoomDepth,
  };
}
