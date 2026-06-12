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
  run_date?: string | null;
  run_interval?: string | null;
  run_number?: string | null;
  qa_flag?: string | null;
  source_id?: string | null;
  source_display_name?: string | null;
  source_intake_candidate_id?: string | null;
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

type BackendDepthRangeLike = {
  min?: number | null;
  max?: number | null;
};

type BackendViewerPackageLike = {
  tracks?: BackendViewerTrackLike[] | null;
  loaded_curve_items?: BackendViewerCurveLike[] | null;
  loaded_product_count?: number | null;
  unsupported_products?: BackendViewerCurveLike[] | null;
  depth_range?: BackendDepthRangeLike | null;
  depth_domain?: BackendDepthRangeLike | null;
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
  runDate?: string | null;
  runInterval?: string | null;
  runNumber?: string | null;
  qaFlag?: string | null;
  sourceId?: string | null;
  sourceDisplayName?: string | null;
  sourceIntakeCandidateId?: string | null;
  catalogItem: CurveCatalogItem;
};

export type WdvPackageState = {
  loadedCurveItems: WdvLoadedCurveItem[];
  availableCurves: CurveCatalogItem[];
  curveUsageCounts: Map<string, number>;
  loadedProductCount: number;
  unsupportedProductCount: number;
  depthRange: { min: number; max: number } | null;
};

export function emptyWdvPackageState(): WdvPackageState {
  return {
    loadedCurveItems: [],
    availableCurves: [],
    curveUsageCounts: new Map<string, number>(),
    loadedProductCount: 0,
    unsupportedProductCount: 0,
    depthRange: null,
  };
}


function depthRangeFromBackend(viewerPackage: BackendViewerPackageLike): { min: number; max: number } | null {
  const rawRange = viewerPackage?.depth_domain ?? viewerPackage?.depth_range ?? null;
  const min = rawRange?.min;
  const max = rawRange?.max;
  if (typeof min !== 'number' || typeof max !== 'number') return null;
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return null;
  return { min, max };
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

  const backendCurveId = String(curve.display_curve_id || curve.curve_id || '').trim();
  if (!backendCurveId) return null;

  const productId = String(curve.product_id || `${backendCurveId}:${index}`).trim();
  const uniqueCurveId = productId || `${backendCurveId}:${index}`;
  const originalMnemonic = String(curve.original_mnemonic || curve.mnemonic || backendCurveId).trim() || backendCurveId;
  const normalizedName = String(curve.normalized_name || curve.display_name || originalMnemonic).trim() || originalMnemonic;
  const runInterval = curve.run_interval ?? null;
  const runNumber = curve.run_number ?? null;
  const sourceDisplayName = curve.source_display_name ?? curve.source_id ?? null;
  const descriptionParts = [normalizedName];
  if (runInterval) descriptionParts.push(String(runInterval));
  if (runNumber && runNumber !== '—') descriptionParts.push(`Run ${runNumber}`);
  const displayDescription = descriptionParts.join(' · ');
  const curveFamily = backendCurveClass(curve.curve_family || curve.track_family);
  const lattice = scaleMode(curve);
  const catalogItem: CurveCatalogItem = {
    curveId: uniqueCurveId,
    mnemonic: originalMnemonic,
    description: displayDescription,
    unit: String(curve.unit || ''),
    curveClass: curveFamily,
    defaultLattice: lattice,
    defaultMin: typeof curve.scale?.min === 'number' ? curve.scale.min : 0,
    defaultMax: typeof curve.scale?.max === 'number' ? curve.scale.max : 150,
    defaultColor: fallbackColor(index),
    recognised: true,
  };

  return {
    productId,
    curveId: uniqueCurveId,
    displayCurveId: backendCurveId,
    canonicalCurveId: curve.canonical_curve_id ?? null,
    originalMnemonic,
    displayName: normalizedName,
    unit: catalogItem.unit,
    curveFamily,
    trackFamily: curve.track_family ?? null,
    supportStatus: curve.support_status ?? null,
    runDate: curve.run_date ?? null,
    runInterval,
    runNumber,
    qaFlag: curve.qa_flag ?? null,
    sourceId: curve.source_id ?? null,
    sourceDisplayName,
    sourceIntakeCandidateId: curve.source_intake_candidate_id ?? null,
    catalogItem,
  };
}

export function buildWdvPackageState(viewerPackage: BackendViewerPackageLike): WdvPackageState {
  if (!viewerPackage) return emptyWdvPackageState();

  const depthRange = depthRangeFromBackend(viewerPackage);

  const backendLoadedCurves = viewerPackage.loaded_curve_items?.length
    ? viewerPackage.loaded_curve_items
    : viewerPackage.tracks?.flatMap((track) => track.curves ?? []) ?? [];

  if (!backendLoadedCurves.length) {
    return { ...emptyWdvPackageState(), depthRange };
  }

  const loadedCurveItems: WdvLoadedCurveItem[] = [];
  const availableCurves: CurveCatalogItem[] = [];
  const curveUsageCounts = new Map<string, number>();

  backendLoadedCurves.forEach((curve, curveIndex) => {
    const loaded = loadedCurveFromBackend(curve, curveIndex);
    if (!loaded) return;
    loadedCurveItems.push(loaded);
    availableCurves.push(loaded.catalogItem);
    curveUsageCounts.set(loaded.curveId, (curveUsageCounts.get(loaded.curveId) ?? 0) + 1);
  });

  return {
    loadedCurveItems,
    availableCurves,
    curveUsageCounts,
    loadedProductCount: loadedCurveItems.length,
    unsupportedProductCount: viewerPackage.unsupported_products?.length ?? 0,
    depthRange,
  };
}
