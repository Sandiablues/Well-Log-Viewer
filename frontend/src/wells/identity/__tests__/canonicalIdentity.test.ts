import { describe, expect, it } from 'vitest';

import {
  canonicalCurveIdentity,
  canonicalProductIdentity,
  legacyProductId,
  nonEmptyIdentity,
} from '../canonicalIdentity';

describe('canonical frontend identity selection', () => {
  it('prefers the backend-owned managed curve UUID', () => {
    expect(canonicalCurveIdentity({
      managed_curve_uid: '01976c6d-4aa7-7e43-b118-d7d30e773e21',
      curve_uid: 'wlv_curve:legacy',
      product_id: 'legacy-product',
    }, 'fallback')).toBe('01976c6d-4aa7-7e43-b118-d7d30e773e21');
  });

  it('retains legacy fallback for pre-migration packages', () => {
    expect(canonicalCurveIdentity({ curve_uid: 'wlv_curve:legacy' }, 'fallback'))
      .toBe('wlv_curve:legacy');
  });

  it('prefers managed product UUID without discarding the legacy action ID', () => {
    const contract = {
      managed_product_uid: '01976c6d-4aa7-7e43-b118-d7d30e773e22',
      product_id: 'source-intake-curve:legacy',
    };
    expect(canonicalProductIdentity(contract))
      .toBe('01976c6d-4aa7-7e43-b118-d7d30e773e22');
    expect(legacyProductId(contract, 'fallback'))
      .toBe('source-intake-curve:legacy');
  });

  it('treats blank values as absent', () => {
    expect(nonEmptyIdentity(' ', null, 'identity')).toBe('identity');
  });
});
