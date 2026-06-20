import { asManagedWellUid, type ManagedWellUid } from './wdvIdentityV21';

export type ManagedWellIdentity = Readonly<{
  managedWellId: string;
  managedWellUid: ManagedWellUid;
}>;

export type ManagedWellIdentityPayload = {
  managed_well_id?: string | null;
  managed_well_uid?: string | null;
};

export type ActiveManagedWellIdentityPayload = {
  active_managed_well_id?: string | null;
  active_managed_well_uid?: string | null;
};

export function managedWellIdentityFromPayload(
  payload: ManagedWellIdentityPayload,
): ManagedWellIdentity {
  const managedWellId = String(payload.managed_well_id ?? '').trim();
  if (!managedWellId) {
    throw new Error('managed_well_id is required for managed well identity');
  }
  return Object.freeze({
    managedWellId,
    managedWellUid: asManagedWellUid(payload.managed_well_uid),
  });
}

export function managedWellIdentityFromActiveWorkspace(
  payload: ActiveManagedWellIdentityPayload,
): ManagedWellIdentity {
  return managedWellIdentityFromPayload({
    managed_well_id: payload.active_managed_well_id,
    managed_well_uid: payload.active_managed_well_uid,
  });
}

export function sameManagedWellIdentity(
  left: ManagedWellIdentity | null | undefined,
  right: ManagedWellIdentity | null | undefined,
): boolean {
  return Boolean(
    left
    && right
    && left.managedWellId === right.managedWellId
    && left.managedWellUid === right.managedWellUid,
  );
}
