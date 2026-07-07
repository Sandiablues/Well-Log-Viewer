import { describe, expect, it } from 'vitest';

import { replaceManagedWellDepthRanges } from '../depthRangeState';

describe('replaceManagedWellDepthRanges', () => {
  it('replaces cached metre ranges with freshly returned feet ranges', () => {
    const current = {
      'f5-well': { min: 1400, max: 3878 },
    };
    const replacements = new Map([
      ['f5-well', { min: 4593.1759, max: 12723.0971 }],
    ]);

    expect(replaceManagedWellDepthRanges(current, replacements)).toEqual({
      'f5-well': { min: 4593.1759, max: 12723.0971 },
    });
  });

  it('replaces cached feet ranges when switching back to metres and preserves other wells', () => {
    const current = {
      'f5-well': { min: 4593.1759, max: 12723.0971 },
      'f-21-31-well': { min: 300.5, max: 6076 },
    };
    const replacements = new Map([
      ['f5-well', { min: 1400, max: 3878 }],
    ]);

    expect(replaceManagedWellDepthRanges(current, replacements)).toEqual({
      'f5-well': { min: 1400, max: 3878 },
      'f-21-31-well': { min: 300.5, max: 6076 },
    });
  });
});
