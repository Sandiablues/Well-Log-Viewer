import { fetchWlvJson } from '../wdv/WdvPresentationPrimitives';

export type WmdSourceRecoveryState = 'available' | 'missing' | 'changed' | 'inaccessible';

export type WmdDownstreamRecoveryStatus = {
  managed_well_id: string;
  source_recovery_state: WmdSourceRecoveryState;
  payload_available: boolean;
  wdv_load_allowed: boolean;
  wbv_load_allowed: boolean;
  export_allowed: boolean;
  saved_workspace_resume_allowed: boolean;
  blocked_product_ids: string[];
  recovery_message?: string | null;
};

export function wmdRecoveryLabel(status: WmdDownstreamRecoveryStatus): string {
  if (status.payload_available) return 'Available';
  if (status.source_recovery_state === 'missing') return 'Source missing';
  if (status.source_recovery_state === 'changed') return 'Source changed';
  if (status.source_recovery_state === 'inaccessible') return 'Source inaccessible';
  return 'Rebuild required';
}

export function wmdRecoveryAction(status: WmdDownstreamRecoveryStatus): 'rebuild' | 'restore-source' | null {
  if (status.payload_available) return null;
  return status.source_recovery_state === 'available' ? 'rebuild' : 'restore-source';
}

export async function fetchWmdDownstreamRecovery(
  managedWellId: string,
): Promise<WmdDownstreamRecoveryStatus> {
  return fetchWlvJson<WmdDownstreamRecoveryStatus>(
    `/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}/downstream-recovery`,
  );
}

export async function rebuildWmdPayload(managedWellId: string): Promise<void> {
  await fetchWlvJson('/api/wlv/inventory/wmd/rebuild', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ managed_well_id: managedWellId }),
  });
}
