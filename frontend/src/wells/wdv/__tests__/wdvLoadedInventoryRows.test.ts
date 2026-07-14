import { describe, expect, it } from 'vitest';

import type { CurveCatalogItem } from '../../prototype/trackLayoutModel';
import {
  curveInventoryIdentityKey,
  curveInventoryRowsForTab,
  loadedMnemonicRows,
} from '../WdvPresentationPrimitives';

function curve(curveId: string, curveUid: string, mnemonic: string): CurveCatalogItem {
  return {
    curveId,
    curveUid,
    identityAliases: [curveId, curveUid],
    mnemonic,
    observedMnemonic: mnemonic,
    normalizedMnemonic: mnemonic,
    description: mnemonic,
    unit: '',
    curveClass: 'unknown',
    defaultLattice: 'linear',
    defaultMin: 0,
    defaultMax: 1,
    defaultColor: '#000000',
    recognised: true,
  } as CurveCatalogItem;
}

describe('WDV backend-owned loaded curve inventory', () => {
  it('renders every backend-provided curve in Loaded regardless of track usage', () => {
    const curves = [
      curve('curve-a', '019f0000-0000-7000-8000-000000000001', 'GR'),
      curve('curve-b', '019f0000-0000-7000-8000-000000000002', 'RT'),
      curve('curve-c', '019f0000-0000-7000-8000-000000000003', 'NPHI'),
    ];
    expect(curveInventoryRowsForTab('all', curves, new Set())).toEqual(curves);
  });

  it('keeps duplicate mnemonics as separate backend rows', () => {
    const first = curve('curve-run-1', '019f0000-0000-7000-8000-000000000011', 'TPOR01');
    const second = curve('curve-run-2', '019f0000-0000-7000-8000-000000000012', 'TPOR01');
    const rows = loadedMnemonicRows([first, second]);
    expect(rows).toHaveLength(2);
    expect(curveInventoryIdentityKey(rows[0])).not.toBe(curveInventoryIdentityKey(rows[1]));
  });

  it('limits Selected to exact backend identities on visible tracks', () => {
    const first = curve('curve-a', '019f0000-0000-7000-8000-000000000021', 'GR');
    const second = curve('curve-b', '019f0000-0000-7000-8000-000000000022', 'GR');
    const selected = new Set([curveInventoryIdentityKey(second)]);
    expect(curveInventoryRowsForTab('selected', [first, second], selected)).toEqual([second]);
  });
});
