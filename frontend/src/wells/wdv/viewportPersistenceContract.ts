import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { ViewportTieGroup } from './viewportSemantics';

export type PersistedViewportTieGroup = {
  group_id: string;
  leader_track_uid: string;
  member_track_uids: string[];
  viewport: DepthViewRange;
};

export type PersistedViewportRelationshipState = {
  track_viewports_by_track_uid?: Record<string, DepthViewRange>;
  viewport_tie_groups?: PersistedViewportTieGroup[];
  viewport_tie_suspended_track_uids?: string[];
  presentation_state?: {
    // Legacy fields remain readable for snapshots written before Slice 6.
    viewport_tie_groups?: PersistedViewportTieGroup[];
    viewport_tie_suspended_track_uids?: string[];
  };
};

export function buildPersistedTrackViewports(
  liveTrackIds: readonly string[],
  trackDepthRangesById: Record<string, DepthViewRange>,
): Record<string, DepthViewRange> {
  const live = new Set(liveTrackIds);
  return Object.fromEntries(
    Object.entries(trackDepthRangesById)
      .filter(([trackId, range]) => live.has(trackId) && range.min < range.max)
      .map(([trackId, range]) => [trackId, { ...range }]),
  );
}

export function buildPersistedViewportTieGroups(
  groups: readonly ViewportTieGroup[],
): PersistedViewportTieGroup[] {
  return groups.map((group) => ({
    group_id: group.groupId,
    leader_track_uid: group.leaderTrackId,
    member_track_uids: [...group.memberTrackIds],
    viewport: { ...group.viewport },
  }));
}

export function restorePersistedTrackViewports(
  state: PersistedViewportRelationshipState,
  lockedTrackIds: readonly string[],
  lockedViewportsByTrackUid: Record<string, DepthViewRange>,
): Record<string, DepthViewRange> {
  const explicit = state.track_viewports_by_track_uid;
  if (explicit && Object.keys(explicit).length > 0) {
    return Object.fromEntries(
      Object.entries(explicit)
        .filter(([, range]) => range.min < range.max)
        .map(([trackId, range]) => [trackId, { ...range }]),
    );
  }

  // Backward-compatible restore for pre-Slice-6 snapshots/recovery records.
  return Object.fromEntries(
    lockedTrackIds.flatMap((trackId) => {
      const range = lockedViewportsByTrackUid[trackId];
      return range && range.min < range.max ? [[trackId, { ...range }] as const] : [];
    }),
  );
}

export function restorePersistedViewportTieGroups(
  state: PersistedViewportRelationshipState,
  liveTrackIds: readonly string[],
): ViewportTieGroup[] {
  const currentTrackIds = new Set(liveTrackIds);
  const rawGroups = state.viewport_tie_groups
    ?? state.presentation_state?.viewport_tie_groups
    ?? [];

  return rawGroups.flatMap((raw) => {
    const memberTrackIds = Array.isArray(raw.member_track_uids)
      ? raw.member_track_uids.filter((trackId) => currentTrackIds.has(trackId))
      : [];
    if (!currentTrackIds.has(raw.leader_track_uid)) return [];
    if (!memberTrackIds.includes(raw.leader_track_uid) || memberTrackIds.length < 2) return [];
    if (!raw.viewport || !(raw.viewport.min < raw.viewport.max)) return [];
    return [{
      groupId: raw.group_id || `viewport-tie:${raw.leader_track_uid}`,
      leaderTrackId: raw.leader_track_uid,
      memberTrackIds,
      viewport: { ...raw.viewport },
    }];
  });
}

export function restorePersistedViewportTieSuspensions(
  state: PersistedViewportRelationshipState,
  groups: readonly ViewportTieGroup[],
): string[] {
  const raw = state.viewport_tie_suspended_track_uids
    ?? state.presentation_state?.viewport_tie_suspended_track_uids
    ?? [];
  const members = new Set(groups.flatMap((group) => group.memberTrackIds));
  return raw.filter((trackId) => members.has(trackId));
}
