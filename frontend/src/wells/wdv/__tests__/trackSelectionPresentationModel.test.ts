import { describe, expect, it } from 'vitest';
import { buildTrackSelectionPresentationModel } from '../trackSelectionPresentationModel';

const tracks = ['t1', 't2', 't3'];

describe('buildTrackSelectionPresentationModel', () => {
    it('highlights only the semantically selected track when no explicit group selection exists', () => {
        const result = buildTrackSelectionPresentationModel({
            trackIds: tracks,
            selection: { kind: 'track', trackId: 't2' },
            combinationTrackSelectedById: {},
        });
        expect(result.highlightedByTrackId).toEqual({ t1: false, t2: true, t3: false });
    });

    it('projects curve selection to track highlight plus assignment id', () => {
        const result = buildTrackSelectionPresentationModel({
            trackIds: tracks,
            selection: { kind: 'curve', trackId: 't2', assignmentId: 'a7' },
            combinationTrackSelectedById: {},
        });
        expect(result.highlightedByTrackId.t2).toBe(true);
        expect(result.selectedAssignmentIdByTrackId.t2).toBe('a7');
        expect(result.selectedAssignmentIdByTrackId.t1).toBeNull();
    });

    it('keeps explicit Combination selection visible without changing semantic selection', () => {
        const result = buildTrackSelectionPresentationModel({
            trackIds: tracks,
            selection: { kind: 'track', trackId: 't1' },
            combinationTrackSelectedById: { t3: true },
        });
        expect(result.highlightedByTrackId).toEqual({ t1: true, t2: false, t3: true });
        expect(result.selectedAssignmentIdByTrackId).toEqual({ t1: null, t2: null, t3: null });
    });

    it('does not synthesize assignments for a plain track selection', () => {
        const result = buildTrackSelectionPresentationModel({
            trackIds: tracks,
            selection: { kind: 'track', trackId: 't3' },
            combinationTrackSelectedById: { t1: true },
        });
        expect(Object.values(result.selectedAssignmentIdByTrackId)).toEqual([null, null, null]);
    });
});
