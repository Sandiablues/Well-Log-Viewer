import { describe, expect, it } from 'vitest';
import { planTrackRelationshipCleanup } from '../trackRelationshipCleanupControl';

const R1 = { min: 1000, max: 1100 };
const R2 = { min: 2000, max: 2100 };

describe('planTrackRelationshipCleanup', () => {
  it('prunes only the removed track from simple relationship collections', () => {
    const result = planTrackRelationshipCleanup({
      removedTrackId: 't2',
      combinationActiveTrackIds: ['t1', 't2', 't3'],
      combinationLockedTrackIds: ['t2', 't3'],
      multiHighlightedTrackIds: ['t1', 't2'],
      trackDepthRangesById: { t1: R1, t2: R2 },
      viewportTieGroups: [],
      viewportTieSuspendedTrackIds: ['t2', 't3'],
      viewportTieHistoryByGroupId: {},
    });
    expect(result.combinationActiveTrackIds).toEqual(['t1', 't3']);
    expect(result.combinationLockedTrackIds).toEqual(['t3']);
    expect(result.multiHighlightedTrackIds).toEqual(['t1']);
    expect(result.trackDepthRangesById).toEqual({ t1: R1 });
    expect(result.viewportTieSuspendedTrackIds).toEqual(['t3']);
  });

  it('dissolves a Tie instead of guessing a new leader when its principal is removed', () => {
    const result = planTrackRelationshipCleanup({
      removedTrackId: 't1',
      combinationActiveTrackIds: [], combinationLockedTrackIds: [], multiHighlightedTrackIds: [],
      trackDepthRangesById: {},
      viewportTieGroups: [{ groupId: 'tie-a', leaderTrackId: 't1', memberTrackIds: ['t1', 't2', 't3'], viewport: R1 }],
      viewportTieSuspendedTrackIds: [],
      viewportTieHistoryByGroupId: { 'tie-a': [R1] },
    });
    expect(result.viewportTieGroups).toEqual([]);
    expect(result.viewportTieHistoryByGroupId).toEqual({});
  });

  it('retains a Tie with the same leader when a non-principal member is removed and two members survive', () => {
    const result = planTrackRelationshipCleanup({
      removedTrackId: 't3',
      combinationActiveTrackIds: [], combinationLockedTrackIds: [], multiHighlightedTrackIds: [],
      trackDepthRangesById: {},
      viewportTieGroups: [{ groupId: 'tie-a', leaderTrackId: 't1', memberTrackIds: ['t1', 't2', 't3'], viewport: R1 }],
      viewportTieSuspendedTrackIds: [],
      viewportTieHistoryByGroupId: { 'tie-a': [R1, R2] },
    });
    expect(result.viewportTieGroups[0]?.leaderTrackId).toBe('t1');
    expect(result.viewportTieGroups[0]?.memberTrackIds).toEqual(['t1', 't2']);
    expect(result.viewportTieHistoryByGroupId['tie-a']).toEqual([R1, R2]);
  });

  it('dissolves a Tie that would fall below two members', () => {
    const result = planTrackRelationshipCleanup({
      removedTrackId: 't2',
      combinationActiveTrackIds: [], combinationLockedTrackIds: [], multiHighlightedTrackIds: [],
      trackDepthRangesById: {},
      viewportTieGroups: [{ groupId: 'tie-a', leaderTrackId: 't1', memberTrackIds: ['t1', 't2'], viewport: R1 }],
      viewportTieSuspendedTrackIds: [],
      viewportTieHistoryByGroupId: { 'tie-a': [R1] },
    });
    expect(result.viewportTieGroups).toEqual([]);
    expect(result.viewportTieHistoryByGroupId).toEqual({});
  });

  it('does not mutate input collections', () => {
    const active = ['t1', 't2'];
    const ranges = { t1: R1, t2: R2 };
    planTrackRelationshipCleanup({
      removedTrackId: 't2', combinationActiveTrackIds: active, combinationLockedTrackIds: [],
      multiHighlightedTrackIds: [], trackDepthRangesById: ranges, viewportTieGroups: [],
      viewportTieSuspendedTrackIds: [], viewportTieHistoryByGroupId: {},
    });
    expect(active).toEqual(['t1', 't2']);
    expect(ranges).toEqual({ t1: R1, t2: R2 });
  });
});
