import type { DepthViewRange } from './WdvPresentationPrimitives';
import { resolveViewportSelectionTrackIds } from './viewportSelectionAuthority';

/**
 * Pure WDV viewport-routing semantics.
 *
 * This module deliberately owns no React state, persistence, rendering, or API
 * calls. It derives the effective viewport-routing model from an immutable
 * snapshot so viewport precedence can be regression-tested independently of
 * WdvPageBoundary.
 */

export type CombinationTrackState = 'normal' | 'active' | 'locked';

export type ViewportTieGroup = {
    groupId: string;
    leaderTrackId: string;
    memberTrackIds: string[];
    viewport: DepthViewRange;
};

export type ViewportSemanticsInput = {
    trackIdsInDisplayOrder: string[];
    selectedTrackId: string | null;
    combinationActiveTrackIds: string[];
    combinationLockedTrackIds: string[];
    multiHighlightedTrackIds: string[];
    trackDepthRangesById: Record<string, DepthViewRange>;
    trackFullDepthRangesById?: Record<string, DepthViewRange>;
    combinationGroupViewRange: DepthViewRange | null;
    viewDepthRange: DepthViewRange;
    viewportTieGroups: ViewportTieGroup[];
    viewportTieSuspendedTrackIds: string[];
};

export type ViewportSemantics = {
    activeCombinationTrackIds: string[];
    lockedCombinationTrackIds: string[];
    highlightedUnlockedTrackIds: string[];
    selectedViewportTieGroup: ViewportTieGroup | null;
    selectedViewportTieLeaderLocked: boolean;
    globalViewportMode: boolean;
    groupActionTrackIds: string[];
    viewportCommandTrackId: string | null;
    viewportCommandFullRange: DepthViewRange | null;
    activeGroupViewRange: DepthViewRange | null;
    combinationTrackStateById: Record<string, CombinationTrackState>;
    combinationTrackSelectedById: Record<string, boolean>;
    effectiveTrackDepthRangesById: Record<string, DepthViewRange>;
    viewportTieMembershipByTrackId: Map<string, ViewportTieGroup>;
    viewportTieMemberByTrackId: Record<string, boolean>;
    viewportTieActionTrackIds: string[];
    viewportTieSelectedTiedTrackIds: string[];
    viewportTieSelectedUntiedTrackIds: string[];
    viewportTieCanUntie: boolean;
    viewportTieCanCreate: boolean;
    viewportTieCandidateTrackIds: string[];
    viewportTieCreateDisabledReason: string;
};

export function deriveViewportSemantics(input: ViewportSemanticsInput): ViewportSemantics {
    const trackIdSet = new Set(input.trackIdsInDisplayOrder);
    const combinationActiveTrackIdSet = new Set(input.combinationActiveTrackIds);
    const combinationLockedTrackIdSet = new Set(input.combinationLockedTrackIds);

    const activeCombinationTrackIds = input.trackIdsInDisplayOrder
        .filter((trackId) => combinationActiveTrackIdSet.has(trackId) && !combinationLockedTrackIdSet.has(trackId));

    const lockedCombinationTrackIds = input.trackIdsInDisplayOrder
        .filter((trackId) => combinationLockedTrackIdSet.has(trackId));

    const highlightedUnlockedTrackIds = input.multiHighlightedTrackIds
        .filter((trackId) => trackIdSet.has(trackId))
        .filter((trackId) => !combinationLockedTrackIdSet.has(trackId));

    const selectedViewportTieGroup = input.selectedTrackId
        ? input.viewportTieGroups.find((group) => group.leaderTrackId === input.selectedTrackId) ?? null
        : null;

    const selectedViewportTieLeaderLocked = Boolean(
        selectedViewportTieGroup
        && combinationLockedTrackIdSet.has(selectedViewportTieGroup.leaderTrackId),
    );

    // WDV_VIEWPORT_SELECTION_TIE_AUTHORITY_V1_0_0
    // Selection establishes viewport command eligibility. A selected unlocked
    // track is zoomable. Only a selected Tie principal expands command scope to
    // its unlocked followers; selecting a follower never promotes it to Tie
    // principal. Lock always excludes that track from viewport mutation.
    const viewportSelectionTrackIds = resolveViewportSelectionTrackIds({
        selectedTrackId: input.selectedTrackId,
        multiHighlightedTrackIds: input.multiHighlightedTrackIds,
    }).filter((trackId) => trackIdSet.has(trackId));

    // Preserve the established unrestricted-canvas fallback when there is no
    // explicit selection and no Tie relationship. Locked tracks are excluded
    // individually; once a track is explicitly selected, that selected scope
    // owns the command.
    const globalViewportMode = viewportSelectionTrackIds.length === 0
        && input.viewportTieGroups.length === 0;

    const groupActionTrackIds = selectedViewportTieGroup
        ? selectedViewportTieGroup.memberTrackIds.filter(
            (trackId) => !combinationLockedTrackIdSet.has(trackId),
        )
        : input.trackIdsInDisplayOrder.filter(
            (trackId) => viewportSelectionTrackIds.includes(trackId)
                && !combinationLockedTrackIdSet.has(trackId),
        );

    // WDV_VIEWPORT_AUTHORITY_CONSOLIDATION_V1_0_0
    // Resolve one command authority before any viewport command executes.
    // Tie leader owns a tied command; otherwise the selected track owns it.
    const viewportCommandTrackId = selectedViewportTieGroup?.leaderTrackId
        ?? (
            input.selectedTrackId && groupActionTrackIds.includes(input.selectedTrackId)
                ? input.selectedTrackId
                : groupActionTrackIds[0] ?? null
        );
    const viewportCommandFullRange = viewportCommandTrackId
        ? (input.trackFullDepthRangesById?.[viewportCommandTrackId] ?? null)
        : null;

    const selectedTrackTieMembership = input.selectedTrackId
        ? input.viewportTieGroups.find((group) => group.memberTrackIds.includes(input.selectedTrackId as string)) ?? null
        : null;
    const selectedTrackIsTieSuspended = Boolean(
        input.selectedTrackId
        && input.viewportTieSuspendedTrackIds.includes(input.selectedTrackId),
    );
    const activeGroupViewRange = selectedViewportTieGroup
        ? selectedViewportTieGroup.viewport
        : viewportCommandTrackId
            ? (
                (!selectedTrackIsTieSuspended && selectedTrackTieMembership
                    ? selectedTrackTieMembership.viewport
                    : input.trackDepthRangesById[viewportCommandTrackId])
                ?? viewportCommandFullRange
                ?? input.viewDepthRange
            )
            : null;

    const multiHighlightedTrackIdSet = new Set(input.multiHighlightedTrackIds);
    const combinationTrackStateById: Record<string, CombinationTrackState> = {};
    const combinationTrackSelectedById: Record<string, boolean> = {};
    for (const trackId of input.trackIdsInDisplayOrder) {
        combinationTrackStateById[trackId] = combinationLockedTrackIdSet.has(trackId)
            ? 'locked'
            : combinationActiveTrackIdSet.has(trackId)
                ? 'active'
                : 'normal';
        combinationTrackSelectedById[trackId] = multiHighlightedTrackIdSet.has(trackId);
    }

    // Per-track ranges remain the backing store for frozen/detached tracks.
    // Shared group/Tie ranges are overlaid only for effective rendering.
    const effectiveTrackDepthRangesById: Record<string, DepthViewRange> = {
        ...input.trackDepthRangesById,
    };
    // Selection may choose an explicit Tie as the command target, but it must
    // not change rendering ownership. Tie rendering is applied below using the
    // relationship itself so suspended/locked members retain their detached or
    // frozen per-track viewport.
    // Selection defines future viewport-command scope only. Untied selected
    // tracks retain their own displayed ranges until a command updates them.

    const viewportTieSuspendedTrackIdSet = new Set(input.viewportTieSuspendedTrackIds);
    for (const group of input.viewportTieGroups) {
        for (const trackId of group.memberTrackIds) {
            if (combinationLockedTrackIdSet.has(trackId)) continue;
            if (viewportTieSuspendedTrackIdSet.has(trackId)) continue;
            effectiveTrackDepthRangesById[trackId] = group.viewport;
        }
    }

    const viewportTieMembershipByTrackId = new Map<string, ViewportTieGroup>();
    for (const group of input.viewportTieGroups) {
        for (const trackId of group.memberTrackIds) {
            viewportTieMembershipByTrackId.set(trackId, group);
        }
    }

    const viewportTieMemberByTrackId = Object.fromEntries(
        input.trackIdsInDisplayOrder.map((trackId) => [trackId, viewportTieMembershipByTrackId.has(trackId)]),
    ) as Record<string, boolean>;

    const viewportTieActionTrackIds = input.multiHighlightedTrackIds.length > 0
        ? [...input.multiHighlightedTrackIds]
        : input.selectedTrackId
            ? [input.selectedTrackId]
            : [];
    const viewportTieSelectedTiedTrackIds = viewportTieActionTrackIds
        .filter((trackId) => viewportTieMembershipByTrackId.has(trackId));
    const viewportTieSelectedUntiedTrackIds = viewportTieActionTrackIds
        .filter((trackId) => !viewportTieMembershipByTrackId.has(trackId));

    const selectedViewportTieGroups = Array.from(new Map(
        viewportTieSelectedTiedTrackIds
            .map((trackId) => viewportTieMembershipByTrackId.get(trackId))
            .filter((group): group is ViewportTieGroup => Boolean(group))
            .map((group) => [group.groupId, group]),
    ).values());

    /*
     * Tie append invariant:
     * - tied-only selection => Untie;
     * - untied-only selection of 2+ => create a new Tie;
     * - exactly one existing Tie group + 1+ untied selections => append to
     *   that existing group and preserve its principal;
     * - selections spanning multiple existing Tie groups never merge implicitly.
     */
    const viewportTieCanAppend = selectedViewportTieGroups.length === 1
        && viewportTieSelectedUntiedTrackIds.length > 0;
    const viewportTieCanUntie = viewportTieSelectedTiedTrackIds.length > 0
        && viewportTieSelectedUntiedTrackIds.length === 0;
    const viewportTieCanCreateNew = viewportTieActionTrackIds.length >= 2
        && viewportTieSelectedTiedTrackIds.length === 0;
    const viewportTieCanCreate = viewportTieCanAppend || viewportTieCanCreateNew;
    const viewportTieCandidateTrackIds = viewportTieCanAppend
        ? [selectedViewportTieGroups[0].leaderTrackId]
        : viewportTieCanCreateNew
            ? [...viewportTieActionTrackIds]
            : [];
    const viewportTieCreateDisabledReason = selectedViewportTieGroups.length > 1
        ? 'Selected tracks span multiple Tie groups; merge is not implicit'
        : viewportTieCanUntie
            ? ''
            : viewportTieActionTrackIds.length < 2
                ? 'Select two or more tracks to create or extend a Tie'
                : viewportTieSelectedTiedTrackIds.length > 0
                    ? 'Select untied tracks together with tracks from one existing Tie group to append them'
                    : '';

    return {
        activeCombinationTrackIds,
        lockedCombinationTrackIds,
        highlightedUnlockedTrackIds,
        selectedViewportTieGroup,
        selectedViewportTieLeaderLocked,
        globalViewportMode,
        groupActionTrackIds,
        viewportCommandTrackId,
        viewportCommandFullRange,
        activeGroupViewRange,
        combinationTrackStateById,
        combinationTrackSelectedById,
        effectiveTrackDepthRangesById,
        viewportTieMembershipByTrackId,
        viewportTieMemberByTrackId,
        viewportTieActionTrackIds,
        viewportTieSelectedTiedTrackIds,
        viewportTieSelectedUntiedTrackIds,
        viewportTieCanUntie,
        viewportTieCanCreate,
        viewportTieCandidateTrackIds,
        viewportTieCreateDisabledReason,
    };
}
