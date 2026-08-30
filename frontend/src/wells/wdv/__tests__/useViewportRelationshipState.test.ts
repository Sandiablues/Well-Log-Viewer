import { describe, expect, it } from 'vitest';
import { createViewportRelationshipInitialState } from '../useViewportRelationshipState';

describe('createViewportRelationshipInitialState', () => {
  it('starts with the supplied global viewport and no relationship ownership', () => {
    const global = { min: 1000, max: 2000 };
    const state = createViewportRelationshipInitialState(global);
    expect(state.viewDepthRange).toEqual(global);
    expect(state.combinationActiveTrackIds).toEqual([]);
    expect(state.combinationLockedTrackIds).toEqual([]);
    expect(state.multiHighlightedTrackIds).toEqual([]);
    expect(state.trackDepthRangesById).toEqual({});
    expect(state.combinationGroupViewRange).toBeNull();
    expect(state.viewportTieGroups).toEqual([]);
    expect(state.viewportTieSuspendedTrackIds).toEqual([]);
    expect(state.viewportTieHistoryByGroupId).toEqual({});
  });

  it('does not invent a per-track viewport or relationship at initialization', () => {
    const state = createViewportRelationshipInitialState({ min: 0, max: 1 });
    expect(Object.keys(state.trackDepthRangesById)).toHaveLength(0);
    expect(state.combinationGroupHistory).toHaveLength(0);
    expect(Object.keys(state.viewportTieHistoryByGroupId)).toHaveLength(0);
  });
});
