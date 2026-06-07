/**
 * MultiViewer Well Log Viewer — Equinor ViDEx Adapter
 * WL-BUILD-001B
 *
 * This adapter is the translation boundary between the backend-owned
 * well_multitrack_v1 contract and the ViDEx rendering system.
 *
 * Architecture rules:
 * - Input:  WellMultitrackV1 (backend-owned contract)
 * - Output: ViDExAdapterOutput (ViDEx-facing config + curve data format)
 * - This file does NOT import @equinor/videx-wellog.
 * - ViDEx class instantiation happens only in videxWellLogRenderer.tsx,
 *   which is the explicitly documented ViDEx rendering boundary.
 * - No LAS parsing occurs here.
 * - No QAQC inference occurs here.
 * - No lifecycle state is held here.
 * - image tracks are skipped (reserved in WL-BUILD-001).
 * - TVD/TVDSS domains are not active in WL-BUILD-001 (MD only).
 */

import type { Curve, Track, WellMultitrackV1, DepthUnit } from '../types';

// ---------------------------------------------------------------------------
// ViDEx-facing output types
//
// These types define what the adapter produces.
// They are consumed only by videxWellLogRenderer.tsx.
// They do NOT expose ViDEx class types — the renderer instantiates those.
// ---------------------------------------------------------------------------

/**
 * A ViDEx curve plot definition, translated from a backend Curve record.
 * Consumed by videxWellLogRenderer.tsx to create LinePlot instances.
 */
export interface ViDExCurveDef {
  /** Corresponds to LinePlot id — matches curve_id from the contract */
  plotId: string;
  mnemonic: string;
  unit: string | null;
  /** X-axis domain for this curve [min, max] */
  valueDomain: [number, number];
  /** CSS color string for this curve's line */
  color: string;
  /** Line weight in canvas pixels */
  lineWidth: number;
}

/**
 * A ViDEx track definition, translated from a backend Track record.
 * Consumed by videxWellLogRenderer.tsx to create ScaleTrack or GraphTrack instances.
 */
export interface ViDExTrackDef {
  trackId: string;
  /** 'scale' → ScaleTrack; 'graph' → GraphTrack; 'skip' → image track, not rendered */
  type: 'scale' | 'graph' | 'skip';
  label: string;
  /** 4-char abbreviation for track title when space is constrained */
  abbr: string;
  /** For graph tracks: ordered list of curve plot definitions */
  curves: ViDExCurveDef[];
}

/**
 * Complete ViDEx-facing output from the adapter.
 * videxWellLogRenderer.tsx consumes this to build the LogController setup.
 */
export interface ViDExAdapterOutput {
  /** Depth domain [minMD, maxMD] in the contract's depth_unit */
  domain: [number, number];
  /** Depth unit string from the backend contract */
  depthUnit: DepthUnit;
  /**
   * ViDEx primary axis mnemonic.
   * WL-BUILD-001: always 'md' (Phase 1 is MD-only).
   */
  primaryAxis: string;
  /** Track definitions in display order */
  trackDefs: ViDExTrackDef[];
}

// ---------------------------------------------------------------------------
// Curve color palette
// One color per curve mnemonic. Used by the adapter; not ViDEx-internal.
// ---------------------------------------------------------------------------

const CURVE_COLORS: Record<string, string> = {
  GR:   '#4caf82',  // green  — standard GR colour convention
  RHOB: '#e05a4a',  // red    — standard density colour convention
  NPHI: '#4a90d9',  // blue   — standard neutron colour convention
  CALI: '#d4a017',  // amber  — standard caliper colour convention
  DEPT: '#8b949e',  // grey   — depth reference
};

const DEFAULT_CURVE_COLOR = '#7e8fa0';

function curveColor(mnemonic: string): string {
  return CURVE_COLORS[mnemonic.toUpperCase()] ?? DEFAULT_CURVE_COLOR;
}

// ---------------------------------------------------------------------------
// Translation helpers
// ---------------------------------------------------------------------------

function translateCurve(curve: Curve): ViDExCurveDef {
  return {
    plotId:      curve.curve_id,
    mnemonic:    curve.mnemonic,
    unit:        curve.unit,
    valueDomain: [curve.scale.min, curve.scale.max],
    color:       curveColor(curve.mnemonic),
    lineWidth:   1.5,
  };
}

function translateTrack(track: Track): ViDExTrackDef {
  if (track.track_type === 'image') {
    // Image tracks are reserved and not rendered in WL-BUILD-001.
    return {
      trackId: track.track_id,
      type:    'skip',
      label:   track.title,
      abbr:    track.title.substring(0, 4).toUpperCase(),
      curves:  [],
    };
  }

  if (track.track_type === 'depth') {
    return {
      trackId: track.track_id,
      type:    'scale',
      label:   track.title,
      abbr:    'MD',
      curves:  [],  // ScaleTrack handles depth ticks internally
    };
  }

  // curve track → GraphTrack
  return {
    trackId: track.track_id,
    type:    'graph',
    label:   track.title,
    abbr:    track.title.substring(0, 4).toUpperCase(),
    curves:  track.curves.map(translateCurve),
  };
}

/**
 * Map depth display domain to ViDEx primary axis mnemonic.
 * WL-BUILD-001: only MD is active.
 * TVD/TVDSS present for forward-compatibility; not reachable in Phase 1.
 */
function mapDomainToAxis(domain: WellMultitrackV1['display_domain']): string {
  switch (domain) {
    case 'MD':    return 'md';
    case 'TVD':   return 'tvd';
    case 'TVDSS': return 'tvdss';
    default:      return 'md';
  }
}

// ---------------------------------------------------------------------------
// Main adapter function
// ---------------------------------------------------------------------------

/**
 * Translate a backend-owned well_multitrack_v1 viewer package into
 * ViDEx-facing configuration.
 *
 * This is the single translation boundary.
 * The renderer (videxWellLogRenderer.tsx) takes this output and
 * instantiates the actual ViDEx classes.
 *
 * @param viewerPackage - Backend-owned well_multitrack_v1 contract
 * @returns ViDExAdapterOutput consumed by videxWellLogRenderer.tsx only
 */
export function adaptToViDEx(viewerPackage: WellMultitrackV1): ViDExAdapterOutput {
  const trackDefs = viewerPackage.tracks
    .map(translateTrack)
    .filter((t): t is ViDExTrackDef => t.type !== 'skip');

  return {
    domain:      [viewerPackage.depth_range.min, viewerPackage.depth_range.max],
    depthUnit:   viewerPackage.depth_unit,
    primaryAxis: mapDomainToAxis(viewerPackage.display_domain),
    trackDefs,
  };
}

/**
 * Utility: map DepthUnit to a display label.
 */
export function mapDepthUnitLabel(unit: DepthUnit): string {
  return unit === 'm' ? 'Depth (m MD)' : 'Depth (ft MD)';
}
