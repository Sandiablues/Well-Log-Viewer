import { fetchWlvApi } from '../api/wlvApiClient';
import type {
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalViewerSessionV21,
} from '../prototype/canonicalViewerPackageV21';
import {
  CanonicalWdvApiError,
  parseCanonicalViewerSessionV21,
} from '../prototype/canonicalViewerPackageV21';
import type {
  CurveCatalogItemV21,
} from '../prototype/trackLayoutModelV21';
import type {
  CanonicalCommandId,
} from './canonicalCommandId';

export type CanonicalWorkspaceCommandKind =
  | 'create_track'
  | 'create_configured_track'
  | 'reset_curve_track_widths'
  | 'remove_track'
  | 'update_track'
  | 'reorder_tracks'
  | 'add_assignment'
  | 'remove_assignment'
  | 'update_assignment'
  | 'move_assignment'
  | 'reorder_assignments'
  | 'select_track'
  | 'upsert_curve_fill'
  | 'remove_curve_fill';

export interface CanonicalWorkspaceCommandIntent {
  kind: CanonicalWorkspaceCommandKind;
  body: Readonly<Record<string, unknown>>;
}

function commandPath(kind: CanonicalWorkspaceCommandKind): string {
  switch (kind) {
    case 'create_track': return 'tracks';
    case 'create_configured_track': return 'tracks/configured';
    case 'reset_curve_track_widths': return 'tracks/reset-curve-widths';
    case 'remove_track': return 'tracks/remove';
    case 'update_track': return 'tracks/update';
    case 'reorder_tracks': return 'tracks/reorder';
    case 'add_assignment': return 'assignments';
    case 'remove_assignment': return 'assignments/remove';
    case 'update_assignment': return 'assignments/update';
    case 'move_assignment': return 'assignments/move';
    case 'reorder_assignments': return 'assignments/reorder';
    case 'select_track': return 'selection';
    case 'upsert_curve_fill': return 'curve-fills/upsert';
    case 'remove_curve_fill': return 'curve-fills/remove';
  }
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const record =
      payload && typeof payload === 'object' && !Array.isArray(payload)
        ? payload as Record<string, unknown>
        : {};
    const detail =
      typeof record.detail === 'string'
        ? record.detail
        : `Canonical WDV command failed (${response.status})`;
    throw new CanonicalWdvApiError(detail, response.status);
  }
  return payload;
}

export async function executeCanonicalWorkspaceCommand(
  managedWellUid: ManagedWellUid,
  revision: number,
  commandId: CanonicalCommandId,
  intent: CanonicalWorkspaceCommandIntent,
  curves: readonly CurveCatalogItemV21[],
  fetchImpl: typeof fetch = fetch,
): Promise<CanonicalViewerSessionV21> {
  const response = await fetchWlvApi(
    `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(managedWellUid)}/${commandPath(intent.kind)}`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ...intent.body,
        expected_revision: revision,
        command_id: commandId,
      }),
    },
    fetchImpl,
  );

  return parseCanonicalViewerSessionV21(
    await parseJsonResponse(response),
    curves,
  );
}

export async function applyCanonicalWorkspaceTemplate(
  managedWellUid: ManagedWellUid,
  revision: number,
  commandId: CanonicalCommandId,
  input: {
    templateKey: string;
    workflowContext?: string | null;
  },
  curves: readonly CurveCatalogItemV21[],
  fetchImpl: typeof fetch = fetch,
): Promise<CanonicalViewerSessionV21> {
  const response = await fetchWlvApi(
    `/api/wlv/v2/wdv/template-commands/${encodeURIComponent(managedWellUid)}/apply`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        expected_revision: revision,
        command_id: commandId,
        template_key: input.templateKey,
        workflow_context: input.workflowContext ?? null,
      }),
    },
    fetchImpl,
  );

  return parseCanonicalViewerSessionV21(
    await parseJsonResponse(response),
    curves,
  );
}
