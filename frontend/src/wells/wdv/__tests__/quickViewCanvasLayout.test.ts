import { describe, expect, it } from 'vitest';
import {
  QUICK_VIEW_DENSE_TRACK_WIDTH,
  QUICK_VIEW_MULTI_TRACK_WIDTH,
  QUICK_VIEW_SINGLE_TRACK_WIDTH,
  quickViewDisplayBounds,
  quickViewTrackWidth,
} from '../QuickViewCanvas';

describe('Quick View compact track layout', () => {
  it('uses narrow widths based on track density', () => {
    expect(quickViewTrackWidth(1)).toBe(QUICK_VIEW_SINGLE_TRACK_WIDTH);
    expect(quickViewTrackWidth(2)).toBe(QUICK_VIEW_MULTI_TRACK_WIDTH);
    expect(quickViewTrackWidth(5)).toBe(QUICK_VIEW_DENSE_TRACK_WIDTH);
    expect(QUICK_VIEW_DENSE_TRACK_WIDTH).toBeLessThan(220);
  });

  it('adds display headroom without changing backend scale values', () => {
    expect(quickViewDisplayBounds({ scale_min: 0, scale_max: 100, scale_type: 'linear' })).toEqual([-8, 108]);
    const [low, high] = quickViewDisplayBounds({ scale_min: 1, scale_max: 1000, scale_type: 'logarithmic' });
    expect(low).toBeLessThan(1);
    expect(high).toBeGreaterThan(1000);
  });
});
