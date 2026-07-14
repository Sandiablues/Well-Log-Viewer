import type { CurveCatalogItem, CurveLattice } from './trackLayoutModel';
import { canonicalCurveIdentity, canonicalProductIdentity, legacyProductId } from '../identity/canonicalIdentity';

type BackendViewerCurveLike = {
  product_id?: string | null;
  managed_product_uid?: string | null;
  curve_uid?: string | null;
  managed_curve_uid?: string | null;
  managed_well_uid?: string | null;
  managed_source_uid?: string | null;
  well_uid?: string | null;
  source_uid?: string | null;
  kr_curve_type_id?: string | null;
  canonical_curve_type_id?: string | null;
  observed_mnemonic?: string | null;
  normalized_mnemonic?: string | null;
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
  scale_type?: string | null;
  scale_direction?: string | null;
  display_min?: number | null;
  display_max?: number | null;
  display_left_value?: number | null;
  display_right_value?: number | null;
  numeric_min?: number | null;
  numeric_max?: number | null;
  scale_source?: string | null;
  display_scale_mode?: string | null;
  recommended_display_scale_mode?: string | null;
  standard_display_min?: number | null;
  standard_display_max?: number | null;
  standard_display_left_value?: number | null;
  standard_display_right_value?: number | null;
  standard_numeric_min?: number | null;
  standard_numeric_max?: number | null;
  robust_observed_display_min?: number | null;
  robust_observed_display_max?: number | null;
  robust_observed_display_left_value?: number | null;
  robust_observed_display_right_value?: number | null;
  robust_observed_numeric_min?: number | null;
  robust_observed_numeric_max?: number | null;
  scale_warnings?: string[] | null;
  visual_span_ratio?: number | null;
  samples_url?: string | null;
  sample_revision?: string | null;
  sample_access?: {
    endpoint?: string | null;
    status?: string | null;
    sample_count?: number | null;
    depth_min?: number | null;
    depth_max?: number | null;
    depth_unit?: string | null;
    value_unit?: string | null;
    revision?: string | null;
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
  managedProductUid?: string | null;
  curveId: string;
  curveUid: string;
  managedCurveUid?: string | null;
  krCurveTypeId?: string | null;
  wellUid?: string | null;
  managedWellUid?: string | null;
  sourceUid?: string | null;
  managedSourceUid?: string | null;
  observedMnemonic?: string | null;
  normalizedMnemonic?: string | null;
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
  samplesUrl?: string | null;
  sampleRevision?: string | null;
  sampleCount?: number | null;
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

function backendCurveClass(curve: BackendViewerCurveLike): CurveCatalogItem['curveClass'] {
  const mnemonic = String(curve.mnemonic || curve.original_mnemonic || curve.display_curve_id || curve.curve_id || '').toLowerCase();
  const key = `${String(curve.curve_family || '')} ${String(curve.track_family || '')} ${mnemonic}`.toLowerCase();
  if (key.includes('gamma') || key.includes('spontaneous') || mnemonic === 'sp') return 'gamma';
  if (key.includes('caliper') || key.includes('borehole')) return 'borehole';
  if (key.includes('resistivity') || /^(res|rt|ild|ilm|ll|rxo)/.test(mnemonic)) return 'resistivity';
  if (key.includes('density') || /^(rhob|rho|den)/.test(mnemonic)) return 'density';
  if (key.includes('neutron') || /^(nphi|tnph|np)/.test(mnemonic)) return 'neutron';
  if (key.includes('sonic') || /^(dt|ac|dts)/.test(mnemonic)) return 'sonic';
  if (key.includes('porosity') || key.includes('phi')) return 'porosity';
  // Backend families that are not represented by the current CurveClass union
  // are not depth curves. Preserve them as visible unknown-family inventory rows.
  return 'unknown';
}

function fallbackColor(index: number): string {
  const colors = ['#2f80ed', '#27ae60', '#f2994a', '#eb5757', '#9b51e0', '#00a6a6', '#f2c94c'];
  return colors[index % colors.length];
}

function scaleMode(curve: BackendViewerCurveLike): CurveLattice {
  return (curve.scale_type ?? curve.scale?.type) === 'log' ? 'logarithmic' : 'linear';
}

function scaleDirection(curve: BackendViewerCurveLike): 'normal' | 'reverse' {
  const value = String(curve.scale_direction || '').toLowerCase();
  if (value === 'reverse' || value === 'reversed') return 'reverse';
  return 'normal';
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function isRenderable(curve: BackendViewerCurveLike): boolean {
  if (curve.is_renderable === false) return false;
  return curve.support_status !== 'unsupported_curve';
}

function loadedCurveFromBackend(curve: BackendViewerCurveLike, index: number): WdvLoadedCurveItem | null {
  if (!isRenderable(curve)) return null;

  const backendCurveId = String(curve.display_curve_id || curve.curve_id || '').trim();
  if (!backendCurveId) return null;

  const fallbackIdentity = `${backendCurveId}:${index}`;
  const productId = legacyProductId(curve, fallbackIdentity);
  const managedProductUid = canonicalProductIdentity(curve);
  const uniqueCurveId = canonicalCurveIdentity(curve, fallbackIdentity);
  const curveUid = uniqueCurveId;
  const managedCurveUid = curve.managed_curve_uid ?? null;
  const krCurveTypeId = curve.kr_curve_type_id ?? curve.canonical_curve_type_id ?? null;
  const wellUid = curve.managed_well_uid ?? curve.well_uid ?? null;
  const managedWellUid = curve.managed_well_uid ?? null;
  const sourceUid = curve.managed_source_uid ?? curve.source_uid ?? curve.source_id ?? null;
  const managedSourceUid = curve.managed_source_uid ?? null;
  const originalMnemonic = String(curve.original_mnemonic || curve.mnemonic || backendCurveId).trim() || backendCurveId;
  const normalizedName = String(curve.normalized_name || curve.display_name || originalMnemonic).trim() || originalMnemonic;
  const observedMnemonic = curve.observed_mnemonic ?? originalMnemonic;
  const normalizedMnemonic = curve.normalized_mnemonic ?? originalMnemonic;
  const runInterval = curve.run_interval ?? null;
  const runNumber = curve.run_number ?? null;
  const sourceDisplayName = curve.source_display_name ?? curve.source_id ?? null;
  const descriptionParts = [normalizedName];
  if (runInterval) descriptionParts.push(String(runInterval));
  if (runNumber && runNumber !== '—') descriptionParts.push(`Run ${runNumber}`);
  const displayDescription = descriptionParts.join(' · ');
  const curveFamily = backendCurveClass(curve);
  const samplesUrl = curve.sample_access?.endpoint ?? curve.samples_url ?? null;
  const sampleRevision = curve.sample_access?.revision ?? curve.sample_revision ?? null;
  const sampleCount = finiteNumber(curve.sample_access?.sample_count);
  const lattice = scaleMode(curve);
  const catalogItem: CurveCatalogItem = {
    curveId: uniqueCurveId,
    curveUid,
    identityAliases: Array.from(new Set([
      uniqueCurveId,
      curveUid,
      managedCurveUid,
      productId,
      managedProductUid,
      backendCurveId,
      curve.display_curve_id,
      curve.curve_id,
      curve.canonical_curve_id,
    ].map((value) => String(value || '').trim()).filter(Boolean))),
    krCurveTypeId,
    wellUid,
    managedWellUid,
    sourceUid,
    managedSourceUid,
    observedMnemonic,
    normalizedMnemonic,
    mnemonic: originalMnemonic,
    description: displayDescription,
    unit: String(curve.unit || ''),
    curveClass: curveFamily,
    backendCurveFamily: String(curve.curve_family || '').trim() || 'Unclassified',
    defaultLattice: lattice,
    defaultMin: finiteNumber(curve.display_left_value) ?? finiteNumber(curve.display_min) ?? finiteNumber(curve.scale?.min) ?? 0,
    defaultMax: finiteNumber(curve.display_right_value) ?? finiteNumber(curve.display_max) ?? finiteNumber(curve.scale?.max) ?? 150,
    defaultScaleDirection: scaleDirection(curve),
    scaleSource: typeof curve.scale_source === 'string' ? curve.scale_source : undefined,
    displayScaleMode: typeof curve.display_scale_mode === 'string' ? curve.display_scale_mode : undefined,
    recommendedDisplayScaleMode: typeof curve.recommended_display_scale_mode === 'string' ? curve.recommended_display_scale_mode : undefined,
    standardDisplayMin: finiteNumber(curve.standard_display_min),
    standardDisplayMax: finiteNumber(curve.standard_display_max),
    robustObservedDisplayMin: finiteNumber(curve.robust_observed_display_left_value) ?? finiteNumber(curve.robust_observed_display_min),
    robustObservedDisplayMax: finiteNumber(curve.robust_observed_display_right_value) ?? finiteNumber(curve.robust_observed_display_max),
    scaleWarnings: Array.isArray(curve.scale_warnings) ? curve.scale_warnings.filter((warning): warning is string => typeof warning === 'string') : undefined,
    visualSpanRatio: finiteNumber(curve.visual_span_ratio),
    defaultColor: fallbackColor(index),
    recognised: true,
  };

  return {
    productId,
    managedProductUid,
    curveId: uniqueCurveId,
    curveUid,
    managedCurveUid,
    krCurveTypeId,
    wellUid,
    managedWellUid,
    sourceUid,
    managedSourceUid,
    observedMnemonic,
    normalizedMnemonic,
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
    samplesUrl,
    sampleRevision,
    sampleCount,
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
