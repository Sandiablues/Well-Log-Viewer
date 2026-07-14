import { describe, expect, it } from 'vitest';

import { buildWdvPackageState } from '../../prototype/wdvPackageState';

function curve(
  index: number,
  family: string,
  mnemonic: string,
): Record<string, unknown> {
  const uid = `019f0000-0000-7000-8000-${String(index).padStart(12, '0')}`;
  return {
    product_id: `product-${index}`,
    managed_product_uid: uid,
    curve_id: `curve-${index}`,
    display_curve_id: `curve-${index}`,
    managed_curve_uid: uid,
    original_mnemonic: mnemonic,
    display_name: mnemonic,
    curve_family: family,
    track_family: family === 'NMR' ? 'open_hole_logs' : 'other_review_required',
    unit: '',
    is_renderable: true,
    support_status: 'supported',
  };
}

describe('WDV backend family visibility', () => {
  it('does not misclassify unrecognised backend curve families as depth', () => {
    const state = buildWdvPackageState({
      loaded_product_count: 3,
      loaded_curve_items: [
        curve(1, 'NMR', 'T2DIST'),
        curve(2, 'Unclassified', 'FLAG01'),
        curve(3, 'Drilling', 'ROP'),
      ],
    });

    expect(state.availableCurves).toHaveLength(3);
    expect(state.availableCurves.map((item) => item.curveClass)).toEqual([
      'unknown',
      'unknown',
      'unknown',
    ]);
  });

  it('still classifies genuine recognised families normally', () => {
    const state = buildWdvPackageState({
      loaded_product_count: 2,
      loaded_curve_items: [
        curve(1, 'Density', 'RHOB'),
        curve(2, 'Gamma Ray', 'GR'),
      ],
    });

    expect(state.availableCurves.map((item) => item.curveClass)).toEqual([
      'density',
      'gamma',
    ]);
  });
});
