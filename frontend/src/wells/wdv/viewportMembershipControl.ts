import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { ViewportTieGroup } from './viewportSemantics';

/**
 * Pure membership/relationship command planning for WDV viewport architecture.
 *
 * Slice 3 moves Lock/Tie/Combination relationship decisions out of
 * WdvPageBoundary without moving high-frequency interaction or React setters.
 * These functions are deterministic transformations over immutable snapshots.
 */

export type CombinationTogglePlan =
    | { kind: 'blocked' }
    | {
        kind: 'apply';
        activeTrackIds: string[];
        clearTrackViewport: boolean;
        groupViewRangeAction: 'keep' | 'set-current' | 'clear';
        resetGroupHistory: boolean;
    };

export function planCombinationTrackToggle(input: {
    trackId: string;
    lockedTrackIds: string[];
    activeTrackIds: string[];
}): CombinationTogglePlan {
    if (input.lockedTrackIds.includes(input.trackId)) return { kind: 'blocked' };
    const isActive = input.activeTrackIds.includes(input.trackId);
    if (isActive) {
        const activeTrackIds = input.activeTrackIds.filter((id) => id !== input.trackId);
        return {
            kind: 'apply',
            activeTrackIds,
            clearTrackViewport: true,
            groupViewRangeAction: activeTrackIds.length === 0 ? 'clear' : 'keep',
            resetGroupHistory: activeTrackIds.length === 0,
        };
    }
    return {
        kind: 'apply',
        activeTrackIds: [...input.activeTrackIds, input.trackId],
        clearTrackViewport: true,
        groupViewRangeAction: input.activeTrackIds.length === 0 ? 'set-current' : 'keep',
        resetGroupHistory: input.activeTrackIds.length === 0,
    };
}

export type CreateViewportTiePlan = {
    groups: ViewportTieGroup[];
    historyByGroupId: Record<string, DepthViewRange[]>;
    suspendedTrackIds: string[];
    createdGroup: ViewportTieGroup;
} | null;

export function planCreateViewportTie(input: {
    canCreate: boolean;
    leaderTrackId: string;
    candidateTrackIds: string[];
    actionTrackIds?: string[];
    effectiveTrackDepthRangesById: Record<string, DepthViewRange>;
    viewDepthRange: DepthViewRange;
    groups: ViewportTieGroup[];
    historyByGroupId: Record<string, DepthViewRange[]>;
    suspendedTrackIds: string[];
}): CreateViewportTiePlan {
    if (!input.canCreate || !input.candidateTrackIds.includes(input.leaderTrackId)) return null;

    /*
     * Backward-compatible planner contract:
     * legacy/tests/new-Tie callers may omit actionTrackIds. In that case the
     * existing candidateTrackIds are the complete action selection.
     */
    const actionTrackIds = input.actionTrackIds ?? input.candidateTrackIds;

    const membershipByTrackId = new Map<string, ViewportTieGroup>();
    for (const group of input.groups) {
        for (const trackId of group.memberTrackIds) membershipByTrackId.set(trackId, group);
    }
    const selectedGroups = Array.from(new Map(
        actionTrackIds
            .map((trackId) => membershipByTrackId.get(trackId))
            .filter((group): group is ViewportTieGroup => Boolean(group))
            .map((group) => [group.groupId, group]),
    ).values());
    const untiedTrackIds = actionTrackIds.filter(
        (trackId) => !membershipByTrackId.has(trackId),
    );

    if (selectedGroups.length === 1 && untiedTrackIds.length > 0) {
        const existingGroup = selectedGroups[0];
        if (input.leaderTrackId !== existingGroup.leaderTrackId) return null;
        const memberTrackIds = Array.from(new Set([
            ...existingGroup.memberTrackIds,
            ...untiedTrackIds,
        ]));
        const createdGroup: ViewportTieGroup = {
            ...existingGroup,
            memberTrackIds,
        };
        return {
            groups: input.groups.map((group) =>
                group.groupId === existingGroup.groupId ? createdGroup : group
            ),
            historyByGroupId: input.historyByGroupId,
            suspendedTrackIds: input.suspendedTrackIds.filter(
                (id) => !untiedTrackIds.includes(id),
            ),
            createdGroup,
        };
    }

    if (selectedGroups.length > 0) return null;

    const leaderRange = input.effectiveTrackDepthRangesById[input.leaderTrackId] ?? input.viewDepthRange;
    const memberTrackIds = [...actionTrackIds];
    const groupId = `viewport-tie:${input.leaderTrackId}`;
    const createdGroup: ViewportTieGroup = {
        groupId,
        leaderTrackId: input.leaderTrackId,
        memberTrackIds,
        viewport: { ...leaderRange },
    };
    return {
        groups: [...input.groups, createdGroup],
        historyByGroupId: { ...input.historyByGroupId, [groupId]: [] },
        suspendedTrackIds: input.suspendedTrackIds.filter((id) => !memberTrackIds.includes(id)),
        createdGroup,
    };
}

export type UntieViewportTracksPlan = {
    groups: ViewportTieGroup[];
    trackDepthRangesById: Record<string, DepthViewRange>;
    suspendedTrackIds: string[];
    historyByGroupId: Record<string, DepthViewRange[]>;
};

export function planUntieViewportTracks(input: {
    canUntie: boolean;
    selectedTiedTrackIds: string[];
    groups: ViewportTieGroup[];
    trackDepthRangesById: Record<string, DepthViewRange>;
    suspendedTrackIds: string[];
    historyByGroupId: Record<string, DepthViewRange[]>;
}): UntieViewportTracksPlan | null {
    if (!input.canUntie) return null;
    const selected = new Set(input.selectedTiedTrackIds);
    const detachedTrackViewports: Record<string, DepthViewRange> = {};
    const dissolvedGroupIds = new Set<string>();
    const detachedTrackIds = new Set<string>();
    const groups = input.groups.flatMap((group) => {
        const selectedMemberTrackIds = group.memberTrackIds.filter((trackId) => selected.has(trackId));
        if (selectedMemberTrackIds.length === 0) return [group];
        const selectedIncludesLeader = selectedMemberTrackIds.includes(group.leaderTrackId);
        const remainingMemberTrackIds = group.memberTrackIds.filter((trackId) => !selected.has(trackId));
        const dissolveGroup = selectedIncludesLeader || remainingMemberTrackIds.length < 2;
        const idsToDetach = dissolveGroup ? group.memberTrackIds : selectedMemberTrackIds;
        for (const trackId of idsToDetach) {
            detachedTrackIds.add(trackId);
            detachedTrackViewports[trackId] = { ...group.viewport };
        }
        if (dissolveGroup) {
            dissolvedGroupIds.add(group.groupId);
            return [];
        }
        return [{ ...group, memberTrackIds: remainingMemberTrackIds }];
    });
    const trackDepthRangesById = { ...input.trackDepthRangesById, ...detachedTrackViewports };
    const suspendedTrackIds = input.suspendedTrackIds.filter((id) => !detachedTrackIds.has(id));
    const historyByGroupId = { ...input.historyByGroupId };
    for (const groupId of dissolvedGroupIds) delete historyByGroupId[groupId];
    return { groups, trackDepthRangesById, suspendedTrackIds, historyByGroupId };
}

export type LockTracksPlan = {
    trackDepthRangesById: Record<string, DepthViewRange>;
    lockedTrackIds: string[];
    activeTrackIds: string[];
    clearGroupViewport: boolean;
};

export function planLockTracks(input: {
    actionTrackIds: string[];
    trackDepthRangesById: Record<string, DepthViewRange>;
    lockedTrackIds: string[];
    activeTrackIds: string[];
    groupActionTrackIds: string[];
    activeGroupViewRange: DepthViewRange | null;
    effectiveTrackDepthRangesById: Record<string, DepthViewRange>;
    viewDepthRange: DepthViewRange;
}): LockTracksPlan | null {
    if (input.actionTrackIds.length === 0) return null;
    const groupActionTrackIdSet = new Set(input.groupActionTrackIds);
    const trackDepthRangesById = { ...input.trackDepthRangesById };
    for (const trackId of input.actionTrackIds) {
        trackDepthRangesById[trackId] =
            groupActionTrackIdSet.has(trackId) && input.activeGroupViewRange
                ? { ...input.activeGroupViewRange }
                : { ...(input.effectiveTrackDepthRangesById[trackId] ?? input.viewDepthRange) };
    }
    const locked = new Set(input.lockedTrackIds);
    for (const trackId of input.actionTrackIds) locked.add(trackId);
    const activeTrackIds = input.activeTrackIds.filter((id) => !input.actionTrackIds.includes(id));
    return {
        trackDepthRangesById,
        lockedTrackIds: Array.from(locked),
        activeTrackIds,
        clearGroupViewport: activeTrackIds.length === 0,
    };
}

export type UnlockTracksPlan = {
    lockedTrackIds: string[];
    activeTrackIds: string[];
    suspendedTrackIds: string[];
};

export function planUnlockTracks(input: {
    actionTrackIds: string[];
    lockedTrackIds: string[];
    activeTrackIds: string[];
    suspendedTrackIds: string[];
    tieMemberTrackIds: string[];
}): UnlockTracksPlan | null {
    if (input.actionTrackIds.length === 0) return null;
    const target = new Set(input.actionTrackIds);
    const tieMembers = new Set(input.tieMemberTrackIds);
    const suspended = new Set(input.suspendedTrackIds);
    for (const trackId of input.actionTrackIds) {
        if (tieMembers.has(trackId)) suspended.add(trackId);
    }
    return {
        lockedTrackIds: input.lockedTrackIds.filter((id) => !target.has(id)),
        activeTrackIds: input.activeTrackIds.filter((id) => !target.has(id)),
        suspendedTrackIds: Array.from(suspended),
    };
}
