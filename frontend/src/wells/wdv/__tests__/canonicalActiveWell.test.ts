import { describe, expect, it } from 'vitest';
import {
  canonicalManagedWellUid,
} from '../canonicalActiveWell';

describe('canonical active-well handoff', () => {
  it('returns the backend-owned managed well UUID', () => {
    expect(canonicalManagedWellUid({
      managed_well_uid: '019ede00-0000-7000-8000-000000000401',
    })).toBe('019ede00-0000-7000-8000-000000000401');
  });

  it('does not substitute managed_well_id when UUID truth is absent', () => {
    expect(canonicalManagedWellUid({ managed_well_uid: null })).toBeNull();
    expect(canonicalManagedWellUid({})).toBeNull();
    expect(canonicalManagedWellUid(null)).toBeNull();
  });

  it('rejects malformed backend UUID truth', () => {
    expect(() => canonicalManagedWellUid({
      managed_well_uid: 'legacy-managed-well-id',
    })).toThrow();
  });
});
