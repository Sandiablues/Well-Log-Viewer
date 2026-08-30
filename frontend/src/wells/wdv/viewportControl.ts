import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { ViewportTieGroup } from './viewportSemantics';
import { standardizedZoomSpan } from './magnificationScale';

/**
 * Pure viewport mutation planner.
 *
 * Slice 2 intentionally separates "which viewport authority should receive this
 * interaction?" from React state mutation.  The caller still executes the plan
 * with frontend-local setters; this module owns no React, API, persistence, or
 * rendering state.
 */

function clampRange(
    range: DepthViewRange,
    fullRange: DepthViewRange,
    minSpan: number,
): DepthViewRange {
    const span = Math.max(minSpan, range.max - range.min);
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
    if (min >= max) return { ...fullRange };
    return {
        min: Number(min.toFixed(6)),
        max: Number(max.toFixed(6)),
    };
}

export type ViewportRangeApplicationPlan =
    | { kind: 'blocked' }
    | {
        kind: 'tie';
        groupId: string;
        memberTrackIds: string[];
        range: DepthViewRange;
    }
    | { kind: 'group'; memberTrackIds: string[]; range: DepthViewRange }
    | {
        kind: 'global';
        range: DepthViewRange;
        frozenTrackDepthRangesById: Record<string, DepthViewRange>;
    };

export function planViewportRangeApplication(input: {
    nextRange: DepthViewRange;
    fullRange: DepthViewRange;
    minSpan: number;
    selectedViewportTieGroup: ViewportTieGroup | null;
    selectedViewportTieLeaderLocked: boolean;
    groupActionTrackIds: string[];
    globalViewportMode?: boolean;
    lockedTrackIds: string[];
    trackDepthRangesById: Record<string, DepthViewRange>;
    viewDepthRange: DepthViewRange;
}): ViewportRangeApplicationPlan {
    const range = clampRange(input.nextRange, input.fullRange, input.minSpan);

    if (input.selectedViewportTieGroup) {
        // A selected locked principal cannot manipulate the Tie. Locked
        // followers are excluded individually and remain frozen.
        if (input.selectedViewportTieLeaderLocked) return { kind: 'blocked' };
        const memberTrackIds = input.groupActionTrackIds.filter(
            (trackId) => !input.lockedTrackIds.includes(trackId),
        );
        if (memberTrackIds.length === 0) return { kind: 'blocked' };
        return {
            kind: 'tie',
            groupId: input.selectedViewportTieGroup.groupId,
            memberTrackIds,
            range,
        };
    }

    if (input.groupActionTrackIds.length > 0) {
        return {
            kind: 'group',
            memberTrackIds: [...input.groupActionTrackIds],
            range,
        };
    }

    if (input.globalViewportMode === false) return { kind: 'blocked' };

    const frozenTrackDepthRangesById: Record<string, DepthViewRange> = {};
    for (const trackId of input.lockedTrackIds) {
        frozenTrackDepthRangesById[trackId] =
            input.trackDepthRangesById[trackId] ?? input.viewDepthRange;
    }
    return { kind: 'global', range, frozenTrackDepthRangesById };
}

export function calculateZoomViewportRange(input: {
    viewDepthRange: DepthViewRange;
    groupActionTrackIds: string[];
    activeGroupViewRange: DepthViewRange | null;
    fullRange: DepthViewRange;
    magnificationReferenceRange: DepthViewRange;
    factor: number;
    minSpan: number;
}): DepthViewRange {
    const base = input.groupActionTrackIds.length > 0
        ? (input.activeGroupViewRange ?? input.viewDepthRange)
        : input.viewDepthRange;
    const center = (base.min + base.max) / 2;
    const nextSpan = standardizedZoomSpan({
        referenceRange: input.magnificationReferenceRange,
        currentRange: base,
        factor: input.factor,
        minSpan: input.minSpan,
        maxSpan: input.fullRange.max - input.fullRange.min,
    });
    return {
        min: center - nextSpan / 2,
        max: center + nextSpan / 2,
    };
}

type DragPanStateLike = {
    startY: number;
    startRange: DepthViewRange;
    clampRange: DepthViewRange;
    targetTrackId?: string;
    targetTrackIds?: string[];
    targetViewportTieGroupId?: string;
};

export type DragPanViewportUpdatePlan =
    | { kind: 'tie'; groupId: string; memberTrackIds: string[]; range: DepthViewRange }
    | { kind: 'track'; trackId: string; range: DepthViewRange }
    | { kind: 'group'; memberTrackIds: string[]; range: DepthViewRange }
    | { kind: 'global'; range: DepthViewRange };

export function planDragPanViewportUpdate(input: {
    dragPanState: DragPanStateLike;
    currentY: number;
    canvasHeight: number;
    minSpan: number;
}): DragPanViewportUpdatePlan {
    const safeHeight = Math.max(1, input.canvasHeight);
    const pixelDelta = input.currentY - input.dragPanState.startY;
    const span = input.dragPanState.startRange.max - input.dragPanState.startRange.min;
    const depthShift = -(pixelDelta / safeHeight) * span;
    const range = clampRange({
        min: input.dragPanState.startRange.min + depthShift,
        max: input.dragPanState.startRange.max + depthShift,
    }, input.dragPanState.clampRange, input.minSpan);

    if (input.dragPanState.targetViewportTieGroupId) {
        return {
            kind: 'tie',
            groupId: input.dragPanState.targetViewportTieGroupId,
            memberTrackIds: [...(input.dragPanState.targetTrackIds ?? [])],
            range,
        };
    }
    if (input.dragPanState.targetTrackId) {
        return { kind: 'track', trackId: input.dragPanState.targetTrackId, range };
    }
    if (input.dragPanState.targetTrackIds?.length) {
        return {
            kind: 'group',
            memberTrackIds: [...input.dragPanState.targetTrackIds],
            range,
        };
    }
    return { kind: 'global', range };
}
