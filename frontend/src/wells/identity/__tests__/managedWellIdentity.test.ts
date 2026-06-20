import { describe, expect, it } from 'vitest';
import { managedWellIdentityFromActiveWorkspace, managedWellIdentityFromPayload, sameManagedWellIdentity } from '../managedWellIdentity';

describe('managed well identity pair', () => {
  const uid = '019ed990-20d4-7d2a-99eb-a11770d8535f';

  it('requires both backend-issued identifiers', () => {
    expect(managedWellIdentityFromPayload({ managed_well_id: 'managed-well:test', managed_well_uid: uid })).toEqual({
      managedWellId: 'managed-well:test',
      managedWellUid: uid,
    });
    expect(() => managedWellIdentityFromPayload({ managed_well_id: 'managed-well:test' })).toThrow();
  });

  it('builds the identity pair from the backend active-workspace contract', () => {
    expect(managedWellIdentityFromActiveWorkspace({
      active_managed_well_id: 'managed-well:test',
      active_managed_well_uid: uid,
    })).toEqual({
      managedWellId: 'managed-well:test',
      managedWellUid: uid,
    });
  });

  it('rejects an incomplete active-workspace identity pair', () => {
    expect(() => managedWellIdentityFromActiveWorkspace({
      active_managed_well_id: 'managed-well:test',
    })).toThrow();
  });

  it('does not treat a matching legacy id with a different uid as the same identity', () => {
    const left = managedWellIdentityFromPayload({ managed_well_id: 'managed-well:test', managed_well_uid: uid });
    const right = managedWellIdentityFromPayload({ managed_well_id: 'managed-well:test', managed_well_uid: '019ed990-20d5-7d2a-99eb-a11770d8535f' });
    expect(sameManagedWellIdentity(left, right)).toBe(false);
  });
});
