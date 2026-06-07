/**
 * MultiViewer Well Log Viewer — Equinor ViDEx Adapter
 * WL-BUILD-001 scaffold
 *
 * This adapter is the ONLY place in the codebase where a backend-owned
 * well_multitrack_v1 viewer package is translated into ViDEx-facing props,
 * config, and data shapes.
 *
 * Architecture rules enforced here:
 * - Input:  WellMultitrackV1 (backend-owned contract)
 * - Output: ViDEx-compatible props/config (opaque to the rest of the codebase)
 * - No LAS parsing occurs here.
 * - No QAQC inference occurs here.
 * - No lifecycle state is held here.
 * - ViDEx internal shapes must not leak out of this file.
 *
 * WL-BUILD-001: adapter skeleton. ViDEx prop shapes will be filled in
 * when @equinor/videx-wellog integration is wired in a later sprint.
 */

import type { WellMultitrackV1, Track, Curve, DepthUnit } from '../types';

// ---------------------------------------------------------------------------
// ViDEx-facing output types (opaque outside this adapter)
//
// These are internal translation targets only.
// They must not be imported by other modules directly.
// All consumers should use WellMultitrackV1 and call this adapter.
// ---------------------------------------------------------------------------

/**
 * Placeholder type for the ViDEx log data structure.
 * Will be replaced with the actual @equinor/videx-wellog type in a later sprint.
 *
 * @internal — do not reference outside this adapter
 */
export interface _ViDExLogData {
  header: Record<string, unknown>;
  curves: _ViDExCurveEntry[];
  data: (number | null)[][];
}

/**
 * @internal
 */
export interface _ViDExCurveEntry {
  name: string;
  unit: string;
  valueType: string;
}

/**
 * @internal
 */
export interface _ViDExTrackConfig {
  type: string;
  plots: _ViDExPlotConfig[];
}

/**
 * @internal
 */
export interface _ViDExPlotConfig {
  id: string;
  type: string;
  scale: string;
  domain?: [number, number];
}

/**
 * The assembled ViDEx-facing props produced by this adapter.
 * Consumed only by MultiViewerWellLogViewer.
 *
 * @internal — do not pass WellMultitrackV1 to ViDEx directly
 */
export interface ViDExAdapterOutput {
  /** ViDEx logData prop — constructed from backend curves only */
  logData: _ViDExLogData | null;
  /** ViDEx tracks config prop */
  tracks: _ViDExTrackConfig[];
  /** ViDEx primary axis (depth domain string) */
  primaryAxis: string;
  /** Depth unit string as ViDEx expects it */
  axisMnemonics: string[];
}

// ---------------------------------------------------------------------------
// Adapter function
// ---------------------------------------------------------------------------

/**
 * Translate a backend-owned well_multitrack_v1 viewer package into
 * ViDEx-compatible props.
 *
 * This is the single translation boundary.
 * Do not duplicate this translation logic anywhere else in the frontend.
 *
 * @param viewerPackage - Backend-owned well_multitrack_v1 contract
 * @returns ViDExAdapterOutput for use by MultiViewerWellLogViewer only
 *
 * WL-BUILD-001: returns a null/empty skeleton.
 * Full curve sample fetching and ViDEx prop construction deferred to a later sprint.
 */
export function adaptToViDEx(viewerPackage: WellMultitrackV1): ViDExAdapterOutput {
  // WL-BUILD-001: placeholder translation
  // TODO (WL-BUILD-002+):
  //   1. Fetch curve samples via viewerPackage.tracks[*].curves[*].samples_url
  //   2. Construct logData header from viewerPackage metadata
  //   3. Build ViDEx track configs from viewerPackage.tracks
  //   4. Map scale type (linear/log) to ViDEx domain config
  //   5. Wire primaryAxis from viewerPackage.display_domain

  const primaryAxis = _mapDisplayDomainToViDExAxis(viewerPackage.display_domain);

  const tracks: _ViDExTrackConfig[] = viewerPackage.tracks
    .map(_translateTrack)
    .filter((t): t is _ViDExTrackConfig => t !== null);

  return {
    logData: null,  // populated when curve sample fetching is wired
    tracks,
    primaryAxis,
    axisMnemonics: [primaryAxis],
  };
}

// ---------------------------------------------------------------------------
// Internal translation helpers
// Private to this adapter — do not export.
// ---------------------------------------------------------------------------

function _mapDisplayDomainToViDExAxis(domain: WellMultitrackV1['display_domain']): string {
  // ViDEx uses its own axis mnemonic strings.
  // This mapping is owned by this adapter.
  // WL-BUILD-001: only MD is active. TVD/TVDSS cases are present for
  // forward-compatibility but will not be reached until transform services are wired.
  switch (domain) {
    case 'MD':    return 'md';
    case 'TVD':   return 'tvd';
    case 'TVDSS': return 'tvdss';
    default:      return 'md';
  }
}

/**
 * Translate a backend Track to a ViDEx track config.
 *
 * WL-BUILD-001 active scope: curve and depth tracks only.
 * Image tracks are reserved and must not be rendered — they are skipped here
 * until raster/core image rendering is wired in a later sprint.
 */
function _translateTrack(track: Track): _ViDExTrackConfig | null {
  if (track.track_type === 'image') {
    // IMAGE track rendering is deferred. Skip silently.
    // Do not attempt to render raster or core image tracks in WL-BUILD-001.
    return null;
  }
  return {
    type: 'stack',  // default ViDEx track type; will be refined per track_type
    plots: track.curves.map(_translateCurveToPlot),
  };
}

function _translateCurveToPlot(curve: Curve): _ViDExPlotConfig {
  return {
    id: curve.curve_id,
    type: 'line',  // default; log scale support wired in later sprint
    scale: curve.scale.type,
    domain: [curve.scale.min, curve.scale.max],
  };
}

/**
 * Utility: map DepthUnit to a ViDEx-friendly display string.
 * @internal
 */
export function _mapDepthUnitLabel(unit: DepthUnit): string {
  return unit === 'm' ? 'Depth (m)' : 'Depth (ft)';
}
