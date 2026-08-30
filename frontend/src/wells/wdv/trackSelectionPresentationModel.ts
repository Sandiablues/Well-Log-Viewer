import type { SelectionRef } from '../prototype/trackLayoutModel';

export type TrackSelectionPresentationModel = {
    highlightedByTrackId: Record<string, boolean>;
    selectedAssignmentIdByTrackId: Record<string, string | null>;
};

export type TrackSelectionPresentationInput = {
    trackIds: readonly string[];
    selection: SelectionRef;
    combinationTrackSelectedById: Readonly<Record<string, boolean>>;
};

/**
 * Pure projection from semantic selection/explicit group-selection state into
 * renderer-facing presentation facts. The renderer does not interpret
 * SelectionRef or decide what constitutes a selected track.
 */
export function buildTrackSelectionPresentationModel(
    input: TrackSelectionPresentationInput,
): TrackSelectionPresentationModel {
    const highlightedByTrackId: Record<string, boolean> = {};
    const selectedAssignmentIdByTrackId: Record<string, string | null> = {};

    for (const trackId of input.trackIds) {
        const semanticTrackSelected =
            input.selection.trackId === trackId
            && (input.selection.kind === 'track' || input.selection.kind === 'curve');
        highlightedByTrackId[trackId] =
            Boolean(input.combinationTrackSelectedById[trackId]) || semanticTrackSelected;
        selectedAssignmentIdByTrackId[trackId] =
            input.selection.kind === 'curve' && input.selection.trackId === trackId
                ? input.selection.assignmentId
                : null;
    }

    return { highlightedByTrackId, selectedAssignmentIdByTrackId };
}
