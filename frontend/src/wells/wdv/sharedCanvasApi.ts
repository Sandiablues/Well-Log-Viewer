/**
 * HTTP client for the shared canvas session API.
 *
 * Calls GET /api/wlv/v2/wdv/shared-canvas/workspaces/{well_uid}
 * with scope_type and scope_uid query parameters.
 *
 * Does not read or write canonical_sessions_v2_1.json or session_layouts.json.
 * Does not persist any canvas state — every call is a fresh read.
 */

import { fetchWlvApi } from '../api/wlvApiClient';
import type { ResolvedWdvCanvasSession } from './sharedCanvasApiTypes';

export interface SharedCanvasSessionRequest {
  managedWellUid: string;
  scopeType: string;
  scopeUid: string;
}

export async function loadSharedCanvasSession(
  request: SharedCanvasSessionRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<ResolvedWdvCanvasSession> {
  const params = new URLSearchParams({
    scope_type: request.scopeType,
    scope_uid: request.scopeUid,
  });
  const url =
    `/api/wlv/v2/wdv/shared-canvas/workspaces/${encodeURIComponent(request.managedWellUid)}`
    + `?${params.toString()}`;

  const response = await fetchWlvApi(
    url,
    { headers: { Accept: 'application/json' } },
    fetchImpl,
  );

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const record =
      payload && typeof payload === 'object' && !Array.isArray(payload)
        ? payload as Record<string, unknown>
        : {};
    const detail =
      typeof record.detail === 'string'
        ? record.detail
        : `Shared canvas session request failed (${response.status})`;
    throw new Error(detail);
  }

  return payload as ResolvedWdvCanvasSession;
}
