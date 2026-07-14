import { describe, expect, it } from 'vitest';

import { buildWdvPackageState } from '../../prototype/wdvPackageState';

function curve(index: number, family: string | null) {
  return {
    product_id: `product-${index}`,
    managed_product_uid: `019f0000-0000-7000-8000-${String(index).padStart(12, '0')}`,
    curve_id: `curve-${index}`,
    display_curve_id: `curve-${index}`,
    managed_curve_uid: `019f0000-0000-7000-8001-${String(index).padStart(12, '0')}`,
    original_mnemonic: `C${index}`,
    display_name: `Curve ${index}`,
    curve_family: family,
    track_family: 'open_hole_logs',
    is_renderable: true,
    support_status: 'supported',
  };
}

describe('WDV direct backend curve_family grouping contract', () => {
  it('preserves exact backend curve_family values', () => {
    const families = [
      'NMR',
      'Density',
      'Gamma Ray',
      'Neutron Porosity',
      'Borehole Geometry',
      'Photoelectric Factor',
      'Density Correction',
      'sonic',
      'Drilling',
      'Resistivity',
      'Unclassified',
    ];

    const state = buildWdvPackageState({
      loaded_product_count: families.length,
      loaded_curve_items: families.map((family, index) => curve(index + 1, family)),
    });

    expect(state.availableCurves.map((item) => item.backendCurveFamily)).toEqual(families);
  });

  it('uses Unclassified only when backend curve_family is absent', () => {
    const state = buildWdvPackageState({
      loaded_product_count: 2,
      loaded_curve_items: [curve(1, null), curve(2, '')],
    });

    expect(state.availableCurves.map((item) => item.backendCurveFamily)).toEqual([
      'Unclassified',
      'Unclassified',
    ]);
  });
});
