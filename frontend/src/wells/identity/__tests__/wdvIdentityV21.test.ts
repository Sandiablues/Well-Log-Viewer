import { describe, expect, it } from 'vitest';

import {
  WdvIdentityContractError,
  asManagedCurveUid,
  canonicalCurveByUid,
  indexCanonicalCurvesByUid,
  parseCanonicalAssignmentIdentityV21,
  parseCanonicalCurveCatalogItemV21,
} from '../wdvIdentityV21';

const WELL = '019f0000-0000-7000-8000-000000000001';
const WELLBORE = '019f0000-0000-7000-8000-000000000002';
const CURVE = '019f0000-0000-7000-8000-000000000003';
const PRODUCT = '019f0000-0000-7000-8000-000000000004';
const SOURCE = '019f0000-0000-7000-8000-000000000005';
const TRACK = '019f0000-0000-7000-8000-000000000006';
const ASSIGNMENT = '019f0000-0000-7000-8000-000000000007';

function curvePayload(overrides: Record<string, unknown> = {}) {
  return {
    contract_version: 'wdv_identity_v2_1',
    managed_curve_uid: CURVE,
    managed_product_uid: PRODUCT,
    managed_well_uid: WELL,
    managed_wellbore_uid: WELLBORE,
    managed_source_uid: SOURCE,
    kr_curve_type_id: 'gamma_ray',
    observed_mnemonic: 'GR',
    normalized_mnemonic: 'GR',
    display_name: 'Gamma Ray',
    unit: 'API',
    curve_family: 'gamma_ray',
    description: 'Natural gamma ray',
    ...overrides,
  };
}

describe('WDV frontend canonical identity v2.1 boundary', () => {
  it('parses one canonical curve occurrence without fallback', () => {
    const curve = parseCanonicalCurveCatalogItemV21(curvePayload());
    expect(curve.managedCurveUid).toBe(CURVE);
    expect(curve.managedProductUid).toBe(PRODUCT);
    expect(curve.observedMnemonic).toBe('GR');
  });

  it.each([
    ['curve_id', 'GR'],
    ['curve_uid', CURVE],
    ['product_id', 'legacy-product'],
    ['display_curve_id', 'GR'],
    ['canonical_curve_id', 'gamma_ray'],
    ['mnemonic', 'GR'],
  ])('rejects forbidden active identity field %s', (field, value) => {
    expect(() => parseCanonicalCurveCatalogItemV21(curvePayload({ [field]: value })))
      .toThrow(WdvIdentityContractError);
  });

  it('rejects non-UUIDv7 managed curve identity', () => {
    expect(() => asManagedCurveUid('GR')).toThrow('managed_curve_uid must be a UUIDv7');
  });

  it('parses assignment identity only from canonical UUIDv7 fields', () => {
    const assignment = parseCanonicalAssignmentIdentityV21({
      assignment_uid: ASSIGNMENT,
      managed_curve_uid: CURVE,
      managed_product_uid: PRODUCT,
      managed_well_uid: WELL,
      managed_wellbore_uid: WELLBORE,
      managed_source_uid: SOURCE,
      track_uid: TRACK,
    });
    expect(assignment.assignmentUid).toBe(ASSIGNMENT);
    expect(assignment.managedCurveUid).toBe(CURVE);
  });

  it('rejects product_id substitution in assignments', () => {
    expect(() => parseCanonicalAssignmentIdentityV21({
      assignment_uid: ASSIGNMENT,
      managed_curve_uid: CURVE,
      managed_product_uid: PRODUCT,
      managed_well_uid: WELL,
      managed_source_uid: SOURCE,
      track_uid: TRACK,
      product_id: 'legacy-product',
    })).toThrow(WdvIdentityContractError);
  });

  it('indexes and resolves curves only by managedCurveUid', () => {
    const curve = parseCanonicalCurveCatalogItemV21(curvePayload());
    const index = indexCanonicalCurvesByUid([curve]);
    expect(index.get(curve.managedCurveUid)).toEqual(curve);
    expect(canonicalCurveByUid([curve], curve.managedCurveUid)).toEqual(curve);
  });

  it('rejects duplicate managedCurveUid values', () => {
    const first = parseCanonicalCurveCatalogItemV21(curvePayload());
    const second = parseCanonicalCurveCatalogItemV21(
      curvePayload({ display_name: 'Gamma Ray Duplicate' }),
    );
    expect(() => indexCanonicalCurvesByUid([first, second]))
      .toThrow(`Duplicate managed_curve_uid: ${CURVE}`);
  });
});
