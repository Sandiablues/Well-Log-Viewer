import { fetchWlvJson } from '../../api/wlvBackendClient';
import type { CurveCatalogItem, CurveLattice, WellLogTrack } from './trackLayoutModel';
import { canonicalCurveIdentity } from '../identity/canonicalIdentity';

type BackendViewerCurve = {
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
  product_id?: string | null;
  managed_product_uid?: string | null;
  curve_id?: string;
  display_curve_id?: string;
  original_mnemonic?: string;
  mnemonic?: string;
  normalized_name?: string | null;
  display_name?: string | null;
  curve_family?: string | null;
  track_family?: string | null;
  unit?: string | null;
  is_renderable?: boolean;
  support_status?: string;
  scale?: {
    type?: string;
    min?: number;
    max?: number;
  };
};

type BackendViewerTrack = {
  track_id?: string;
  track_type?: string;
  title?: string;
  track_family?: string;
  curves?: BackendViewerCurve[];
};

type BackendViewerPackage = {
  tracks?: BackendViewerTrack[];
  depth_unit?: string;
  depth_range?: { min?: number; max?: number };
  messages?: string[];
  unsupported_products?: BackendViewerCurve[];
  [key: string]: unknown;
};

export type BackendViewerPackageLoadResult = {
  source: 'managed_inventory' | 'prototype_fallback';
  package: BackendViewerPackage | null;
  warning?: string;
};

export async function loadBackendViewerPackageWithFallback(
  managedWellId: string,
): Promise<BackendViewerPackageLoadResult> {
  try {
    const managedPackage = await fetchWlvJson<BackendViewerPackage>(
      `/api/wlv/inventory/wells/${encodeURIComponent(managedWellId)}/viewer-package`,
    );
    return { source: 'managed_inventory', package: managedPackage };
  } catch (managedError) {
    const warning = managedError instanceof Error ? managedError.message : 'Managed viewer package unavailable';
    return { source: 'prototype_fallback', package: null, warning };
  }
}

function backendCurveClass(curve: BackendViewerCurve): CurveCatalogItem['curveClass'] {
  const mnemonic = String(curve.mnemonic || curve.original_mnemonic || curve.display_curve_id || curve.curve_id || '').toLowerCase();
  const key = `${String(curve.curve_family || '')} ${String(curve.track_family || '')} ${mnemonic}`.toLowerCase();
  if (key.includes('gamma') || key.includes('spontaneous') || mnemonic === 'sp') return 'gamma';
  if (key.includes('caliper') || key.includes('borehole')) return 'borehole';
  if (key.includes('resistivity') || /^(res|rt|ild|ilm|ll|rxo)/.test(mnemonic)) return 'resistivity';
  if (key.includes('density') || /^(rhob|rho|den)/.test(mnemonic)) return 'density';
  if (key.includes('neutron') || /^(nphi|tnph|np)/.test(mnemonic)) return 'neutron';
  if (key.includes('sonic') || /^(dt|ac|dts)/.test(mnemonic)) return 'sonic';
  if (key.includes('porosity') || key.includes('phi')) return 'porosity';
  return 'depth';
}

function fallbackColor(index: number): string {
  const colors = ['#2f80ed', '#27ae60', '#f2994a', '#eb5757', '#9b51e0', '#00a6a6', '#f2c94c'];
  return colors[index % colors.length];
}

function curveCatalogItemFromBackendCurve(curve: BackendViewerCurve, index: number): CurveCatalogItem | null {
  if (curve.is_renderable === false || curve.support_status === 'unsupported_curve') return null;

  const curveId = String(curve.display_curve_id || curve.curve_id || '').trim();
  if (!curveId) return null;

  const productId = String(curve.product_id || curveId).trim() || curveId;
  const curveUid = canonicalCurveIdentity(curve, productId);
  const krCurveTypeId = curve.kr_curve_type_id ?? curve.canonical_curve_type_id ?? null;
  const wellUid = curve.managed_well_uid ?? curve.well_uid ?? null;
  const sourceUid = curve.managed_source_uid ?? curve.source_uid ?? null;
  const observedMnemonic = curve.observed_mnemonic ?? curve.original_mnemonic ?? curve.mnemonic ?? curveId;
  const normalizedMnemonic = curve.normalized_mnemonic ?? observedMnemonic;

  const mnemonic = String(curve.original_mnemonic || curve.mnemonic || curveId);
  const scaleType = curve.scale?.type === 'log' ? 'logarithmic' : 'linear';
  return {
    curveId,
    curveUid,
    krCurveTypeId,
    wellUid,
    sourceUid,
    observedMnemonic,
    normalizedMnemonic,
    mnemonic,
    description: String(curve.display_name || curve.normalized_name || mnemonic),
    unit: String(curve.unit || ''),
    curveClass: backendCurveClass(curve),
    defaultLattice: scaleType as CurveLattice,
    defaultMin: typeof curve.scale?.min === 'number' ? curve.scale.min : 0,
    defaultMax: typeof curve.scale?.max === 'number' ? curve.scale.max : 150,
    defaultColor: fallbackColor(index),
    recognised: true,
  };
}

export function adaptBackendViewerPackageToTracks(viewerPackage: BackendViewerPackage | null | undefined): WellLogTrack[] {
  if (!viewerPackage?.tracks?.length) return [];

  const tracks: WellLogTrack[] = [];
  let curveIndex = 0;

  viewerPackage.tracks.forEach((track, trackIndex) => {
    const trackType = track.track_type || 'curve';
    const title = String(track.title || track.track_family || track.track_id || `Track ${trackIndex + 1}`);

    if (trackType === 'depth' || !track.curves?.length) {
      tracks.push({
        trackId: String(track.track_id || `depth-${trackIndex}`),
        trackIndex: tracks.length,
        title,
        widthPx: 84,
        visible: true,
        trackType: 'depth',
        depthBasis: 'MD',
        unit: viewerPackage.depth_unit === 'm' ? 'm' : 'ft',
      });
      return;
    }

    const assignments = track.curves
      .map((curve, stackIndex) => {
        const catalogCurve = curveCatalogItemFromBackendCurve(curve, curveIndex++);
        if (!catalogCurve) return null;
        return {
          assignmentId: `assign-${String(track.track_id || trackIndex)}-${catalogCurve.curveUid ?? catalogCurve.curveId}-${stackIndex}`,
          curveId: catalogCurve.curveId,
          curveUid: catalogCurve.curveUid ?? catalogCurve.curveId,
          krCurveTypeId: catalogCurve.krCurveTypeId ?? null,
          wellUid: catalogCurve.wellUid ?? null,
          sourceUid: catalogCurve.sourceUid ?? null,
          observedMnemonic: catalogCurve.observedMnemonic ?? catalogCurve.mnemonic,
          normalizedMnemonic: catalogCurve.normalizedMnemonic ?? catalogCurve.mnemonic,
          stackIndex,
          visible: true,
          scaleMin: catalogCurve.defaultMin,
          scaleMax: catalogCurve.defaultMax,
          scaleDirection: catalogCurve.mnemonic === 'NPHI' || catalogCurve.mnemonic === 'TNPH' ? 'reverse' : 'normal',
          scaleType: catalogCurve.defaultLattice === 'logarithmic' ? 'log' : 'linear',
          rangeMode: 'fixed',
          color: catalogCurve.defaultColor,
          lineVisible: true,
          lineStyle: 'solid',
          lineWidth: 1.8,
          lineOpacity: 100,
          positionAnchor: 'center',
          horizontalOffsetPct: 0,
          clipToTrack: true,
          fillSide: 'none',
          fillColor: '#7fbf8f',
          fillOpacity: 55,
          infillSource: 'solid',
          infillPattern: 'solid',
          infillIntervalColumn: 'lithology',
          displayPriority: 'normal',
          showQaqcWarnings: true,
          showNullGaps: true,
          showOutOfRange: true,
        } as const;
      })
      .filter((assignment): assignment is NonNullable<typeof assignment> => assignment !== null);

    if (assignments.length === 0) return;

    tracks.push({
      trackId: String(track.track_id || `track-${trackIndex}`),
      trackIndex: tracks.length,
      title,
      widthPx: 220,
      visible: true,
      trackType: 'curve',
      lattice: assignments.some((assignment) => assignment.scaleType === 'log') ? 'logarithmic' : 'linear',
      latticeSource: 'template',
      latticeOverride: false,
      scaleMode: assignments.length > 1 ? 'per_curve' : 'shared',
      curves: assignments,
    });
  });

  return tracks;
}
