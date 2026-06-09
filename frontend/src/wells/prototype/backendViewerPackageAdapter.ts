import { fetchWlvJson } from '../../api/wlvBackendClient';

type BackendViewerPackage = Record<string, unknown>;

export type BackendViewerPackageLoadResult = {
  source: 'managed_inventory' | 'seed_repository' | 'prototype_fallback';
  package: BackendViewerPackage | null;
  warning?: string;
};

const DEFAULT_MANAGED_WELL_ID = 'managed-well:forge-21-31';
const DEFAULT_SEED_WELL_ID = 'forge-21-31';

export async function loadBackendViewerPackageWithFallback(
  managedWellId = DEFAULT_MANAGED_WELL_ID,
): Promise<BackendViewerPackageLoadResult> {
  try {
    const managedPackage = await fetchWlvJson<BackendViewerPackage>(
      `/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}/viewer-package`,
    );
    return { source: 'managed_inventory', package: managedPackage };
  } catch (managedError) {
    try {
      const seedPackage = await fetchWlvJson<BackendViewerPackage>(
        `/api/wlv/wells/${encodeURIComponent(DEFAULT_SEED_WELL_ID)}/viewer-package`,
      );
      return { source: 'seed_repository', package: seedPackage };
    } catch (seedError) {
      const warning = managedError instanceof Error ? managedError.message : 'Managed viewer package unavailable';
      return { source: 'prototype_fallback', package: null, warning };
    }
  }
}
