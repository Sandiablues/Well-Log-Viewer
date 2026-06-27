import { fetchWlvApi } from '../api/wlvApiClient';
import type {
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import {
  asManagedWellUid,
  WdvIdentityContractError,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalViewerPackageV21,
  CanonicalViewerSessionV21,
} from '../prototype/canonicalViewerPackageV21';
import {
  CanonicalWdvApiError,
  parseCanonicalViewerPackageV21,
  parseCanonicalViewerSessionV21,
} from '../prototype/canonicalViewerPackageV21';
import type {
  CurveCatalogItemV21,
} from '../prototype/trackLayoutModelV21';

export interface CanonicalWorkspaceV1 {
  contractVersion: 'wdv_workspace_v1';
  managedWellUid: ManagedWellUid;
  viewerPackage: CanonicalViewerPackageV21;
  curves: readonly CurveCatalogItemV21[];
  session: CanonicalViewerSessionV21;
  warnings: readonly string[];
}

function requireRecord(
  value: unknown,
  label: string,
): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new WdvIdentityContractError(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function stringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new WdvIdentityContractError(`${field} must be an array of strings`);
  }
  return [...value];
}

export function parseCanonicalWorkspaceV1(
  value: unknown,
): CanonicalWorkspaceV1 {
  const record = requireRecord(value, 'canonical workspace');
  if (record.contract_version !== 'wdv_workspace_v1') {
    throw new WdvIdentityContractError(
      'Workspace contract_version must be wdv_workspace_v1',
    );
  }

  const managedWellUid = asManagedWellUid(record.managed_well_uid);
  if (!Array.isArray(record.curve_registry)) {
    throw new WdvIdentityContractError(
      'Workspace curve_registry must be an array',
    );
  }

  const packagePayload = {
    contract_version: 'wdv_viewer_package_v2_2',
    managed_well_uid: record.managed_well_uid,
    managed_wellbore_uid: record.managed_wellbore_uid ?? null,
    well_name: record.well_name,
    wellbore_name: record.wellbore_name ?? null,
    depth_range: record.depth_range,
    curves: record.curve_registry,
    session: record.session,
    warnings: record.warnings ?? [],
  };

  const viewerPackage = parseCanonicalViewerPackageV21(packagePayload);
  if (viewerPackage.managedWellUid !== managedWellUid) {
    throw new WdvIdentityContractError(
      'Workspace and viewer package managedWellUid must match',
    );
  }

  const session = parseCanonicalViewerSessionV21(
    record.session,
    viewerPackage.curves,
  );
  if (session.managedWellUid !== managedWellUid) {
    throw new WdvIdentityContractError(
      'Workspace and session managedWellUid must match',
    );
  }

  return {
    contractVersion: 'wdv_workspace_v1',
    managedWellUid,
    viewerPackage: {
      ...viewerPackage,
      session,
    },
    curves: viewerPackage.curves,
    session,
    warnings: stringArray(record.warnings ?? [], 'warnings'),
  };
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
        : `Canonical WDV workspace request failed (${response.status})`;
    throw new CanonicalWdvApiError(detail, response.status);
  }
  return payload;
}

export async function loadCanonicalWorkspaceV1(
  managedWellUid: ManagedWellUid,
  fetchImpl: typeof fetch = fetch,
): Promise<CanonicalWorkspaceV1> {
  const response = await fetchWlvApi(
    `/api/wlv/v2/wdv/workspaces/${encodeURIComponent(managedWellUid)}`,
    {
      headers: {
        Accept: 'application/json',
      },
    },
    fetchImpl,
  );
  return parseCanonicalWorkspaceV1(await parseJsonResponse(response));
}
