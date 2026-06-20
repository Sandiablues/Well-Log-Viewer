import { describe, expect, it } from 'vitest';
import type { CurveAssignment, CurveCatalogItem } from '../../prototype/trackLayoutModel';
import {
  buildCurveIdentityIndex,
  canonicalizeCurveIdentitySet,
  canonicalizeCurveUsageCounts,
  resolveAssignmentCanonicalCurveKey,
  resolveCanonicalCurveKey,
} from '../curveIdentityIndex';

function curve(curveId: string, curveUid: string, mnemonic: string, aliases: string[] = []): CurveCatalogItem {
  return {
    curveId,
    curveUid,
    identityAliases: aliases,
    mnemonic,
    description: mnemonic,
    unit: 'unit',
    curveClass: 'gamma',
    defaultLattice: 'linear',
    defaultMin: 0,
    defaultMax: 100,
    defaultColor: '#000',
    recognised: true,
  };
}

function assignment(curveId: string, curveUid?: string | null): CurveAssignment {
  return {
    assignmentId: `assignment-${curveId}`,
    curveId,
    curveUid,
    stackIndex: 0,
    visible: true,
    scaleMin: 0,
    scaleMax: 100,
    scaleDirection: 'normal',
    color: '#000',
    lineStyle: 'solid',
    lineWidth: 1,
    fillSide: 'none',
    fillColor: '#000',
  };
}

describe('curve identity crossover', () => {
  it('crosses legacy and product aliases to the managed curve UID', () => {
    const uid = '019ed990-20d4-7d2a-99eb-a11770d8535f';
    const index = buildCurveIdentityIndex([curve('display-gr', uid, 'GR', ['legacy-gr', 'product-gr'])]);
    expect(resolveCanonicalCurveKey(index, 'legacy-gr')).toBe(uid);
    expect(resolveCanonicalCurveKey(index, 'product-gr')).toBe(uid);
  });

  it('keeps duplicate mnemonics independent by UID', () => {
    const index = buildCurveIdentityIndex([
      curve('at90-a', '019ed990-20d4-7d2a-99eb-a11770d8535f', 'AT90'),
      curve('at90-b', '019ed990-20d4-7d2a-99eb-a11770d85360', 'AT90'),
    ]);
    expect(resolveCanonicalCurveKey(index, 'at90-a')).not.toBe(resolveCanonicalCurveKey(index, 'at90-b'));
  });

  it('resolves restored assignments that carry only a legacy curveId', () => {
    const uid = '019ed990-20d4-7d2a-99eb-a11770d8535f';
    const index = buildCurveIdentityIndex([curve('display-gr', uid, 'GR', ['legacy-gr'])]);
    expect(resolveAssignmentCanonicalCurveKey(index, assignment('legacy-gr'))).toBe(uid);
  });

  it('counts repeated use by canonical UID while selected total stays distinct', () => {
    const uid = '019ed990-20d4-7d2a-99eb-a11770d8535f';
    const index = buildCurveIdentityIndex([curve('display-gr', uid, 'GR', ['legacy-gr'])]);
    const counts = canonicalizeCurveUsageCounts(index, new Map([['display-gr', 1], ['legacy-gr', 1]]));
    expect(counts.get(uid)).toBe(2);
    expect(canonicalizeCurveIdentitySet(index, ['display-gr', 'legacy-gr']).size).toBe(1);
  });

  it('fails closed for an ambiguous alias', () => {
    const index = buildCurveIdentityIndex([
      curve('curve-a', '019ed990-20d4-7d2a-99eb-a11770d8535f', 'AT90', ['shared']),
      curve('curve-b', '019ed990-20d4-7d2a-99eb-a11770d85360', 'AT90', ['shared']),
    ]);
    expect(resolveCanonicalCurveKey(index, 'shared')).toBeNull();
  });
});
