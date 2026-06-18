import { describe, expect, it } from 'vitest';

import {
  buildInventoryActionPayload,
  buildInventoryRemovalPayload,
} from '../inventoryActionIdentity';

const WELL_UID = '01976c6d-4aa7-7e43-b118-d7d30e773e81';
const PRODUCT_UID = '01976c6d-4aa7-7e43-b118-d7d30e773e82';

describe('canonical inventory action payloads', () => {
  it('sends canonical well and product UUIDs when available', () => {
    expect(buildInventoryActionPayload(
      { managed_well_uid: WELL_UID, managed_well_id: 'legacy-well' },
      [{ managed_product_uid: PRODUCT_UID, product_id: 'legacy-product' }],
    )).toEqual({
      managed_well_uid: WELL_UID,
      managed_product_uids: [PRODUCT_UID],
    });
  });

  it('retains legacy aliases only for pre-migration records', () => {
    expect(buildInventoryActionPayload(
      { managed_well_id: 'legacy-well' },
      [{ product_id: 'legacy-product' }],
    )).toEqual({
      managed_well_id: 'legacy-well',
      product_ids: ['legacy-product'],
    });
  });

  it('builds canonical remove payloads for multiple selected rows', () => {
    expect(buildInventoryRemovalPayload(
      [{ managed_well_uid: WELL_UID, managed_well_id: 'legacy-well' }],
      [{ managed_product_uid: PRODUCT_UID, product_id: 'legacy-product' }],
    )).toEqual({
      managed_well_uids: [WELL_UID],
      managed_product_uids: [PRODUCT_UID],
    });
  });
});
