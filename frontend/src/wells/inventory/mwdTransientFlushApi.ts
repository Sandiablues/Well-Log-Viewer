import { fetchWlvJson } from '../wdv/WdvPresentationPrimitives';

export const MWD_TRANSIENT_FLUSH_ENDPOINT = '/api/wlv/inventory/mwd/flush' as const;
export const MWD_TRANSIENT_FLUSH_CONFIRMATION = 'FLUSH_MWD_TRANSIENT_DATA' as const;

export type MwdTransientFlushRequest = {
  confirm: typeof MWD_TRANSIENT_FLUSH_CONFIRMATION;
  actor: string;
  reason: string;
  dry_run: boolean;
};

export type MwdTransientFlushResponse = {
  ok: boolean;
  action: string;
  destructive: boolean;
  dry_run: boolean;
  removed_managed_well_count: number;
  removed_product_count: number;
  removed_source_reference_count: number;
  removed_viewer_package_count: number;
  removed_workspace_loaded_count: number;
  removed_canonical_session_count: number;
  removed_command_receipt_group_count: number;
  reset_source_candidate_count: number;
  preserved_source_candidate_count: number;
  audit: Record<string, unknown>;
};

export function buildMwdTransientFlushRequest(
  reason = 'Flush transient MWD managed data from the Managed Data page',
): MwdTransientFlushRequest {
  return {
    confirm: MWD_TRANSIENT_FLUSH_CONFIRMATION,
    actor: 'mwd-ui',
    reason,
    dry_run: false,
  };
}

export async function flushMwdTransientData(
  requester: <T>(path: string, init?: RequestInit) => Promise<T> = fetchWlvJson,
): Promise<MwdTransientFlushResponse> {
  return requester<MwdTransientFlushResponse>(MWD_TRANSIENT_FLUSH_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildMwdTransientFlushRequest()),
  });
}
