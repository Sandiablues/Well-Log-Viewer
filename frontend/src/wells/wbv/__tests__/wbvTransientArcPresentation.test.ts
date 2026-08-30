import { describe, expect, it } from 'vitest';
import { advanceTransientArcPresentation } from '../selectedPointTracking/transientArcPresentation';

describe('WBV transient arc presentation', () => {
  it('advances monotonically toward the target', () => {
    let displayed = 2;
    const values: number[] = [];
    for (let index = 0; index < 12; index += 1) {
      displayed = advanceTransientArcPresentation(displayed, 5, 16.67);
      values.push(displayed);
    }
    expect(values.every((value, index) => index === 0 || value >= values[index - 1])).toBe(true);
    expect(values[values.length - 1]).toBeGreaterThan(4.8);
    expect(values[values.length - 1]).toBeLessThanOrEqual(5);
  });

  it('advances between pointer observations', () => {
    let displayed = advanceTransientArcPresentation(0, 3, 8);
    const first = displayed;
    displayed = advanceTransientArcPresentation(displayed, 3, 8);
    expect(displayed).toBeGreaterThan(first);
    expect(displayed).toBeLessThanOrEqual(3);
  });

  it('limits a very large frame step', () => {
    const displayed = advanceTransientArcPresentation(
      0,
      100,
      100,
      { timeConstantMs: 34, maximumProjectedPixelsPerSecond: 10, settleTolerancePx: 0.0005 },
    );
    expect(displayed).toBe(1);
  });

  it('settles exactly at the target', () => {
    expect(advanceTransientArcPresentation(4.9998, 5, 16.67)).toBe(5);
  });

  it('handles reverse movement symmetrically', () => {
    const displayed = advanceTransientArcPresentation(5, 2, 16.67);
    expect(displayed).toBeLessThan(5);
    expect(displayed).toBeGreaterThanOrEqual(2);
  });
});
