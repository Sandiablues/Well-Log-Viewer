import { describe, expect, it } from 'vitest';
import {
  isSelectedViewportTrackEligible,
  resolveViewportSelectionTrackIds,
} from '../viewportSelectionAuthority';

describe('viewportSelectionAuthority', () => {
  it('unifies primary and multi-highlighted selection without duplicates', () => {
    expect(resolveViewportSelectionTrackIds({
      selectedTrackId: 't1',
      multiHighlightedTrackIds: ['t1', 't2'],
    })).toEqual(['t1', 't2']);
  });

  it('allows Drag Zoom only when the source track is explicitly selected', () => {
    expect(isSelectedViewportTrackEligible({
      sourceTrackId: 't1', selectedTrackId: 't1', multiHighlightedTrackIds: [], lockedTrackIds: new Set(),
    })).toBe(true);
    expect(isSelectedViewportTrackEligible({
      sourceTrackId: 't2', selectedTrackId: 't1', multiHighlightedTrackIds: [], lockedTrackIds: new Set(),
    })).toBe(false);
  });

  it('allows a multi-highlighted source track', () => {
    expect(isSelectedViewportTrackEligible({
      sourceTrackId: 't2', selectedTrackId: 't1', multiHighlightedTrackIds: ['t1', 't2'], lockedTrackIds: new Set(),
    })).toBe(true);
  });

  it('blocks a selected source track when it is locked', () => {
    expect(isSelectedViewportTrackEligible({
      sourceTrackId: 't1', selectedTrackId: 't1', multiHighlightedTrackIds: [], lockedTrackIds: new Set(['t1']),
    })).toBe(false);
  });
});
