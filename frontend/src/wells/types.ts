/**
 * MultiViewer Well Log Viewer — Frontend Types
 * WL-BUILD-001 scaffold
 *
 * These TypeScript types mirror the backend-owned well_multitrack_v1 contract.
 * The frontend must render this contract through the equinorWellLogAdapter.
 *
 * IMPORTANT:
 * - Do not add fields that are not present in the backend contract.
 * - Do not make ViDEx-internal types part of this file.
 * - Do not add lifecycle state fields — MSI owns lifecycle.
 * - Do not add LAS parsing state — backend owns LAS parsing.
 */

// ---------------------------------------------------------------------------
// Enumerations — matching backend enum values
// ---------------------------------------------------------------------------

export type DepthUnit = 'm' | 'ft';

/**
 * Depth display domain.
 *
 * Active in WL-BUILD-001: 'MD' only (Measured Depth).
 * Reserved — not exposed in frontend UI until backend transform services are wired:
 *   'TVD'   — True Vertical Depth (requires backend TVD transform)
 *   'TVDSS' — True Vertical Depth Sub-Sea (requires backend TVDSS transform)
 *
 * These values exist in the type so the contract remains forward-compatible
 * with backend-produced packages. The frontend must not expose TVD or TVDSS
 * as selectable options in WL-BUILD-001.
 */
export type DisplayDomain = 'MD' | 'TVD' | 'TVDSS';

export type ScaleType = 'linear' | 'log';

/**
 * Track rendering type.
 *
 * Active in WL-BUILD-001: 'curve' and 'depth' only.
 * Reserved — not rendered in WL-BUILD-001:
 *   'image' — Raster/core image track. Deferred to a later sprint.
 *
 * The frontend adapter must not attempt to render image tracks in WL-BUILD-001.
 */
export type TrackType = 'curve' | 'depth' | 'image';

export type QaqcSeverity = 'info' | 'warning' | 'error';

// ---------------------------------------------------------------------------
// MSI reference types
// These are references into the backend-owned MSI inventory.
// Frontend renders these as identifiers; it does not own their lifecycle.
// ---------------------------------------------------------------------------

export interface MsiDatasetRef {
  dataset_id: string;
  display_name?: string;
}

export interface MsiSourceRef {
  source_id: string;
  filename?: string;
}

export interface MsiRepresentationRef {
  representation_id: string;
  representation_type?: string;
}

// ---------------------------------------------------------------------------
// Curve and track types
// ---------------------------------------------------------------------------

export interface CurveScale {
  type: ScaleType;
  min: number;
  max: number;
}

export interface Curve {
  curve_id: string;
  mnemonic: string;
  normalized_name: string | null;
  unit: string | null;
  /** Backend-owned URL for fetching curve samples. Frontend fetches; does not parse. */
  samples_url: string;
  scale: CurveScale;
}

export interface Track {
  track_id: string;
  track_type: TrackType;
  title: string;
  curves: Curve[];
}

// ---------------------------------------------------------------------------
// QAQC finding type
// Backend generates findings; frontend displays them only.
// ---------------------------------------------------------------------------

export interface QaqcFinding {
  finding_id: string;
  severity: QaqcSeverity;
  code: string;
  object_type: string;
  object_id: string;
  message: string;
}

// ---------------------------------------------------------------------------
// well_multitrack_v1 — canonical backend-owned viewer package type
//
// This is the authoritative contract the frontend consumes.
// The equinorWellLogAdapter is the only place this is translated to ViDEx props.
// ---------------------------------------------------------------------------

export interface DepthRange {
  min: number;
  max: number;
}

export interface WellMultitrackV1 {
  viewer_package_version: 'well_multitrack_v1';
  dataset_id: string;
  representation_id: string;
  well_id: string;
  wellbore_id: string;
  display_domain: DisplayDomain;
  depth_unit: DepthUnit;
  depth_range: DepthRange;
  tracks: Track[];
  qaqc_findings: QaqcFinding[];
}

// ---------------------------------------------------------------------------
// API response wrapper (placeholder)
// ---------------------------------------------------------------------------

export interface ViewerPackageResponse {
  data: WellMultitrackV1 | null;
  loading: boolean;
  error: string | null;
}
