import type {
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import {
  asManagedWellUid,
} from '../identity/wdvIdentityV21';

export interface CanonicalActiveWellReference {
  managed_well_uid?: string | null;
}

export function canonicalManagedWellUid(
  well: CanonicalActiveWellReference | null,
): ManagedWellUid | null {
  const value = well?.managed_well_uid?.trim() ?? '';
  if (value.length === 0) return null;
  return asManagedWellUid(value);
}
