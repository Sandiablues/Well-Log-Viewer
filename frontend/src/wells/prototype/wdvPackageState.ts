import type { CurveCatalogItem, CurveLattice } from './trackLayoutModel';

type BackendViewerCurveLike = {
  product_id?: string | null;
  curve_id?: string | null;
  display_curve_id?: string | null;
  canonical_curve_id?: string | null;
  original_mnemonic?: string | null;
  mnemonic?: string | null;
  normalized_name?: string | null;
  display_name?: string | null;
  curve_family?: string | null;
  track_family?: string | null;
  unit?: string | null;
  is_renderable?: boolean | null;
  support_status?: string | null;
  scale?: {
    type?: string | null;
    min?: number | null;
    max?: number | null;
  } | null;
};

type BackendViewerTrackLike = {
  track_id?: string | null;
  track_type?: string | null;
  title?: string | null;
  track_family?: string | null;
  curves?: BackendViewerCurveLike[] | null;
};

type BackendViewerPackageLike = {
  tracks?: BackendViewerTrackLike[] | null;
  unsupported_products?: BackendViewerCurveLike[] | null;
} | null | undefined;

export type WdvLoadedCurveItem = {
  productId: string;
  curveId: string;
  displayCurveId: string;
  canonicalCurveId?: string | null;
  originalMnemonic: string;
  displayName: string;
  unit: string;
  curveFamily: CurveCatalogItem['curveClass'];
  trackFamily?: string | null;
  supportStatus?: string | null;
  catalogItem: CurveCatalogItem;
};

export type WdvPackageState = {
  loadedCurveItems: WdvLoadedCurveItem[];
  availableCurves: CurveCatalogItem[];
  curveUsageCounts: Map<string, number>;
  loadedProductCount: number;
  unsupportedProductCount: number;
};

export function emptyWdvPackageState(): WdvPackageState {
  return {
    loadedCurveItems: [],
    availableCurves: [],
    curveUsageCounts: new Map<string, number>(),
    loadedProductCount: 0,
    unsupportedProductCount: 0,
  };
}

function backendCurveClass(value: string | null | undefined): CurveCatalogItem['curveClass'] {
  const key = String(value || '').toLowerCase();
  if (key.includes('gamma')) return 'gamma';
  if (key.includes('caliper') || key.includes('borehole')) return 'borehole';
  if (key.includes('resistivity')) return 'resistivity';
  if (key.includes('density')) return 'density';
  if (key.includes('neutron')) return 'neutron';
  if (key.includes('sonic')) return 'sonic';
  if (key.includes('porosity')) return 'porosity';
  return 'depth';
}

function fallbackColor(index: number): string {
  const colors = ['#2f80ed', '#27ae60', '#f2994a', '#eb5757', '#9b51e0', '#00a6a6', '#f2c94c'];
  return colors[index % colors.length];
}

function scaleMode(curve: BackendViewerCurveLike): CurveLattice {
  return curve.scale?.type === 'log' ? 'logarithmic' : 'linear';
}

function isRenderable(curve: BackendViewerCurveLike): boolean {
  if (curve.is_renderable === false) return false;
  return curve.support_status !== 'unsupported_curve';
}

function loadedCurveFromBackend(curve: BackendViewerCurveLike, index: number): WdvLoadedCurveItem | null {
  if (!isRenderable(curve)) return null;

  const curveId = String(curve.display_curve_id || curve.curve_id || '').trim();
  if (!curveId) return null;

  const originalMnemonic = String(curve.original_mnemonic || curve.mnemonic || curveId).trim() || curveId;
  const displayName = String(curve.display_name || curve.normalized_name || originalMnemonic).trim() || originalMnemonic;
  const curveFamily = backendCurveClass(curve.curve_family || curve.track_family);
  const lattice = scaleMode(curve);
  const catalogItem: CurveCatalogItem = {
    curveId,
    mnemonic: originalMnemonic,
    description: displayName,
    unit: String(curve.unit || ''),
    curveClass: curveFamily,
    defaultLattice: lattice,
    defaultMin: typeof curve.scale?.min === 'number' ? curve.scale.min : 0,
    defaultMax: typeof curve.scale?.max === 'number' ? curve.scale.max : 150,
    defaultColor: fallbackColor(index),
    recognised: true,
  };

  return {
    productId: String(curve.product_id || `${curveId}:${index}`),
    curveId,
    displayCurveId: curveId,
    canonicalCurveId: curve.canonical_curve_id ?? null,
    originalMnemonic,
    displayName,
    unit: catalogItem.unit,
    curveFamily,
    trackFamily: curve.track_family ?? null,
    supportStatus: curve.support_status ?? null,
    catalogItem,
  };
}

export function buildWdvPackageState(viewerPackage: BackendViewerPackageLike): WdvPackageState {
  if (!viewerPackage?.tracks?.length) return emptyWdvPackageState();

  const loadedCurveItems: WdvLoadedCurveItem[] = [];
  const availableCurvesById = new Map<string, CurveCatalogItem>();
  const curveUsageCounts = new Map<string, number>();
  let curveIndex = 0;

  viewerPackage.tracks.forEach((track) => {
    if (!track.curves?.length) return;
    track.curves.forEach((curve) => {
      const loaded = loadedCurveFromBackend(curve, curveIndex++);
      if (!loaded) return;
      loadedCurveItems.push(loaded);
      if (!availableCurvesById.has(loaded.curveId)) {
        availableCurvesById.set(loaded.curveId, loaded.catalogItem);
      }
      curveUsageCounts.set(loaded.curveId, (curveUsageCounts.get(loaded.curveId) ?? 0) + 1);
    });
  });

  return {
    loadedCurveItems,
    availableCurves: Array.from(availableCurvesById.values()),
    curveUsageCounts,
    loadedProductCount: loadedCurveItems.length,
    unsupportedProductCount: viewerPackage.unsupported_products?.length ?? 0,
  };
}
