import { describe, expect, it } from 'vitest';
import { deriveViewportSemantics, type ViewportTieGroup } from '../viewportSemantics';

const GLOBAL = { min: 1000, max: 2000 };
const TIE = { min: 1400, max: 1500 };
const FROZEN = { min: 3000, max: 3010 };

function base(overrides: Partial<Parameters<typeof deriveViewportSemantics>[0]> = {}) {
  return {
    trackIdsInDisplayOrder: ['t1', 't2', 't3'],
    selectedTrackId: null,
    combinationActiveTrackIds: [],
    combinationLockedTrackIds: [],
    multiHighlightedTrackIds: [],
    trackDepthRangesById: {},
    combinationGroupViewRange: null,
    viewDepthRange: GLOBAL,
    viewportTieGroups: [] as ViewportTieGroup[],
    viewportTieSuspendedTrackIds: [],
    ...overrides,
  };
}

const tie: ViewportTieGroup = {
  groupId: 'tie:t1',
  leaderTrackId: 't1',
  memberTrackIds: ['t1', 't2'],
  viewport: TIE,
};

describe('deriveViewportSemantics selected/Lock/Tie authority', () => {
  it('keeps unrestricted no-selection canvas global', () => {
    const result = deriveViewportSemantics(base());
    expect(result.globalViewportMode).toBe(true);
    expect(result.groupActionTrackIds).toEqual([]);
  });

  it('keeps unlocked tracks globally zoomable when other tracks are locked and nothing is selected', () => {
    const result = deriveViewportSemantics(base({
      combinationLockedTrackIds: ['t3'],
      trackDepthRangesById: { t3: FROZEN },
    }));
    expect(result.globalViewportMode).toBe(true);
    expect(result.groupActionTrackIds).toEqual([]);
    expect(result.effectiveTrackDepthRangesById.t3).toEqual(FROZEN);
  });

  it('makes a selected unlocked standalone track the explicit zoom target', () => {
    const result = deriveViewportSemantics(base({ selectedTrackId: 't2' }));
    expect(result.globalViewportMode).toBe(false);
    expect(result.groupActionTrackIds).toEqual(['t2']);
    expect(result.viewportCommandTrackId).toBe('t2');
  });

  it('blocks a selected locked standalone track from viewport targeting', () => {
    const result = deriveViewportSemantics(base({
      selectedTrackId: 't2',
      combinationLockedTrackIds: ['t2'],
      trackDepthRangesById: { t2: FROZEN },
    }));
    expect(result.globalViewportMode).toBe(false);
    expect(result.groupActionTrackIds).toEqual([]);
    expect(result.effectiveTrackDepthRangesById.t2).toEqual(FROZEN);
  });

  it('expands a selected unlocked Tie principal to all unlocked followers', () => {
    const result = deriveViewportSemantics(base({
      selectedTrackId: 't1',
      viewportTieGroups: [tie],
    }));
    expect(result.selectedViewportTieGroup).toEqual(tie);
    expect(result.groupActionTrackIds).toEqual(['t1', 't2']);
    expect(result.viewportCommandTrackId).toBe('t1');
    expect(result.activeGroupViewRange).toEqual(TIE);
  });

  it('excludes a locked Tie follower while keeping the selected principal and other followers zoomable', () => {
    const tie3: ViewportTieGroup = { ...tie, memberTrackIds: ['t1', 't2', 't3'] };
    const result = deriveViewportSemantics(base({
      selectedTrackId: 't1',
      viewportTieGroups: [tie3],
      combinationLockedTrackIds: ['t2'],
      trackDepthRangesById: { t2: FROZEN },
    }));
    expect(result.groupActionTrackIds).toEqual(['t1', 't3']);
    expect(result.effectiveTrackDepthRangesById.t1).toEqual(TIE);
    expect(result.effectiveTrackDepthRangesById.t2).toEqual(FROZEN);
    expect(result.effectiveTrackDepthRangesById.t3).toEqual(TIE);
  });

  it('does not promote a selected Tie follower to principal', () => {
    const result = deriveViewportSemantics(base({
      selectedTrackId: 't2',
      viewportTieGroups: [tie],
    }));
    expect(result.selectedViewportTieGroup).toBeNull();
    expect(result.groupActionTrackIds).toEqual(['t2']);
    expect(result.viewportCommandTrackId).toBe('t2');
    // Before individual manipulation, the follower starts from the Tie viewport
    // it is actually displaying.
    expect(result.activeGroupViewRange).toEqual(TIE);
  });

  it('keeps a suspended selected Tie follower on its independent per-track viewport', () => {
    const result = deriveViewportSemantics(base({
      selectedTrackId: 't2',
      viewportTieGroups: [tie],
      viewportTieSuspendedTrackIds: ['t2'],
      trackDepthRangesById: { t2: FROZEN },
    }));
    expect(result.selectedViewportTieGroup).toBeNull();
    expect(result.groupActionTrackIds).toEqual(['t2']);
    expect(result.activeGroupViewRange).toEqual(FROZEN);
    expect(result.effectiveTrackDepthRangesById.t2).toEqual(FROZEN);
  });

  it('uses explicit multi-selection as zoom targets without inventing a Tie', () => {
    const result = deriveViewportSemantics(base({
      selectedTrackId: 't3',
      multiHighlightedTrackIds: ['t2', 't3'],
    }));
    expect(result.globalViewportMode).toBe(false);
    expect(result.groupActionTrackIds).toEqual(['t2', 't3']);
    expect(result.selectedViewportTieGroup).toBeNull();
  });
});
