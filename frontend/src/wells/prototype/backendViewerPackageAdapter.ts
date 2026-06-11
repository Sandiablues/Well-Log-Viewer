import { fetchWlvJson } from '../../api/wlvBackendClient';
import type { CurveCatalogItem, CurveLattice, WellLogTrack } from './trackLayoutModel';

type BackendViewerCurve = {
  curve_id?: string;
  display_curve_id?: string;
  original_mnemonic?: string;
  mnemonic?: string;
  normalized_name?: string | null;
  display_name?: string | null;
  curve_family?: string | null;
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

function curveCatalogItemFromBackendCurve(curve: BackendViewerCurve, index: number): CurveCatalogItem | null {
  if (curve.is_renderable === false || curve.support_status === 'unsupported_curve') return null;

  const curveId = String(curve.display_curve_id || curve.curve_id || '').trim();
  if (!curveId) return null;

  const mnemonic = String(curve.original_mnemonic || curve.mnemonic || curveId);
  const scaleType = curve.scale?.type === 'log' ? 'logarithmic' : 'linear';
  return {
    curveId,
    mnemonic,
    description: String(curve.display_name || curve.normalized_name || mnemonic),
    unit: String(curve.unit || ''),
    curveClass: backendCurveClass(curve.curve_family),
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
          assignmentId: `assign-${String(track.track_id || trackIndex)}-${catalogCurve.curveId}-${stackIndex}`,
          curveId: catalogCurve.curveId,
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
