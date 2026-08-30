import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { CombinationTrackState } from './viewportSemantics';

/**
 * Coherent viewport/relationship render contract consumed by TrackCanvas.
 *
 * This module owns no React state and performs no persistence or API work. It
 * converts semantic viewport authority into the exact render-facing shape so
 * WdvPageBoundary no longer branches independently while constructing canvas
 * props.
 */
export type TrackCanvasRenderModel = {
    combinationTrackStateById: Record<string, CombinationTrackState>;
    combinationTrackSelectedById: Record<string, boolean>;
    viewportTieMemberByTrackId: Record<string, boolean>;
    trackDepthRangesById: Record<string, DepthViewRange>;
    viewDepthRange: DepthViewRange;
    fullDepthRange: DepthViewRange;
    dragPanActive: boolean;
};

export type TrackCanvasRenderModelInput = {
    globalViewportMode: boolean;
    combinationTrackStateById: Record<string, CombinationTrackState>;
    combinationTrackSelectedById: Record<string, boolean>;
    viewportTieMemberByTrackId: Record<string, boolean>;
    effectiveTrackDepthRangesById: Record<string, DepthViewRange>;
    viewDepthRange: DepthViewRange;
    fullDepthRange: DepthViewRange;
    dragPanActive: boolean;
};

export function buildTrackCanvasRenderModel(
    input: TrackCanvasRenderModelInput,
): TrackCanvasRenderModel {
    return {
        combinationTrackStateById: input.combinationTrackStateById,
        combinationTrackSelectedById: input.combinationTrackSelectedById,
        viewportTieMemberByTrackId: input.viewportTieMemberByTrackId,
        trackDepthRangesById: input.globalViewportMode
            ? {}
            : input.effectiveTrackDepthRangesById,
        viewDepthRange: input.viewDepthRange,
        fullDepthRange: input.fullDepthRange,
        dragPanActive: input.dragPanActive,
    };
}
