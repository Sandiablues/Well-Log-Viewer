import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { ViewportTieGroup } from './viewportSemantics';

export type TrackRelationshipCleanupInput = {
  removedTrackId: string;
  combinationActiveTrackIds: readonly string[];
  combinationLockedTrackIds: readonly string[];
  multiHighlightedTrackIds: readonly string[];
  trackDepthRangesById: Readonly<Record<string, DepthViewRange>>;
  viewportTieGroups: readonly ViewportTieGroup[];
  viewportTieSuspendedTrackIds: readonly string[];
  viewportTieHistoryByGroupId: Readonly<Record<string, readonly DepthViewRange[]>>;
};

export type TrackRelationshipCleanupPlan = {
  combinationActiveTrackIds: string[];
  combinationLockedTrackIds: string[];
  multiHighlightedTrackIds: string[];
  trackDepthRangesById: Record<string, DepthViewRange>;
  viewportTieGroups: ViewportTieGroup[];
  viewportTieSuspendedTrackIds: string[];
  viewportTieHistoryByGroupId: Record<string, DepthViewRange[]>;
};

/**
 * Prune only semantic references owned by a removed track.
 *
 * A Tie is dissolved when its principal is removed or fewer than two members
 * remain. No surviving Tie is silently re-parented: principal authority is an
 * explicit semantic choice, not something deletion may guess.
 */
export function planTrackRelationshipCleanup(
  input: TrackRelationshipCleanupInput,
): TrackRelationshipCleanupPlan {
  const removed = input.removedTrackId;
  const survivingTieGroups = input.viewportTieGroups.flatMap((group) => {
    if (group.leaderTrackId === removed) return [];
    const memberTrackIds = group.memberTrackIds.filter((id) => id !== removed);
    if (memberTrackIds.length < 2) return [];
    return [{ ...group, memberTrackIds }];
  });
  const survivingTieIds = new Set(survivingTieGroups.map((group) => group.groupId));

  const trackDepthRangesById = Object.fromEntries(
    Object.entries(input.trackDepthRangesById)
      .filter(([trackId]) => trackId !== removed)
      .map(([trackId, range]) => [trackId, { ...range }]),
  );

  const viewportTieHistoryByGroupId = Object.fromEntries(
    Object.entries(input.viewportTieHistoryByGroupId)
      .filter(([groupId]) => survivingTieIds.has(groupId))
      .map(([groupId, history]) => [groupId, history.map((range) => ({ ...range }))]),
  );

  return {
    combinationActiveTrackIds: input.combinationActiveTrackIds.filter((id) => id !== removed),
    combinationLockedTrackIds: input.combinationLockedTrackIds.filter((id) => id !== removed),
    multiHighlightedTrackIds: input.multiHighlightedTrackIds.filter((id) => id !== removed),
    trackDepthRangesById,
    viewportTieGroups: survivingTieGroups,
    viewportTieSuspendedTrackIds: input.viewportTieSuspendedTrackIds.filter((id) => id !== removed),
    viewportTieHistoryByGroupId,
  };
}
