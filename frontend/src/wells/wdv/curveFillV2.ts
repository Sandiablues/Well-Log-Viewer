import { fetchWlvApi } from '../api/wlvApiClient';

export const WDV_CURVE_SAMPLE_LIMIT = 12000;

export type CurveFillRuleTypeV2 = 'conditional' | 'crossover' | 'between_curves' | 'to_boundary' | 'value_band' | 'curve_to_value' | 'threshold' | 'curve_envelope' | 'separation';
export type CurveFillComparisonV2 = 'greater_than' | 'less_than';
export type CurveFillBoundaryV2 = 'left' | 'right'; // threshold: selected boundary is the fill anchor; null means curve↔threshold
export type CurveFillSeparationModeV2 = 'absolute' | 'a_right_of_b' | 'a_left_of_b';
export type CurveFillRuleStateV2 = 'stored' | 'pending_geometry' | 'resolved' | 'disabled' | 'invalid';
export type CurveFillAppearanceV2 = 'solid' | 'pattern' | 'raster';
export type CurveFillDepthExtentV2 = 'entire_track' | 'specified_interval';
export interface CurveFillStyleV2 { appearance?: CurveFillAppearanceV2; color: string; opacity: number; pattern_uid?: string | null; pattern_scale?: number; raster_asset_uid?: string | null }

export interface CanonicalCurveFillRuleV2 {
  rule_uid: string;
  managed_well_uid: string;
  track_uid: string;
  curve_a_assignment_uid: string;
  curve_b_assignment_uid: string | null;
  curve_operand_assignment_uids: string[];
  order: number;
  enabled: boolean;
  rule_type: CurveFillRuleTypeV2;
  comparison: CurveFillComparisonV2 | null;
  boundary: CurveFillBoundaryV2 | null;
  reference_value: number | null;
  band_min_value: number | null;
  band_max_value: number | null;
  minimum_separation_px: number;
  separation_mode: CurveFillSeparationModeV2;
  overlay_policy_uid: string | null;
  overlay_policy_revision: string | null;
  deadband: number;
  minimum_interval: number;
  depth_extent: CurveFillDepthExtentV2;
  interval_from_md: number | null;
  interval_to_md: number | null;
  style: CurveFillStyleV2;
  state: CurveFillRuleStateV2;
  state_reason: string | null;
  geometry_revision: string | null;
}

export interface CurveFillVertexV2 { depth: number; x_a_px: number; x_b_px: number }
export interface CurveFillPolygonV2 { polygon_uid: string; top_depth: number; base_depth: number; vertices: CurveFillVertexV2[] }
export interface ResolvedCurveFillPaintV2 { appearance: CurveFillAppearanceV2; pattern_uid: string | null; pattern_scale: number; raster: null | { raster_asset_uid: string; image_url: string; top_depth: number; base_depth: number; depth_unit: string; horizontal_fit: string } }
export interface CurveFillGeometryV2 {
  contract_version: 'wdv_curve_fill_geometry_v2';
  rule_uid: string;
  order: number;
  dependency_key: string;
  geometry_revision: string;
  managed_well_uid: string;
  track_uid: string;
  depth_unit: string;
  style: CurveFillStyleV2;
  paint?: ResolvedCurveFillPaintV2;
  polygons: CurveFillPolygonV2[];
  warnings: string[];
}
export interface CurveFillGeometryDeltaV2 {
  contract_version: 'wdv_curve_fill_geometry_delta_v2';
  managed_well_uid: string;
  session_revision: number;
  upsert: CurveFillGeometryV2[];
  remove: string[];
}
export interface CurveFillOperandCapabilityV2 {
  assignment_uid: string;
  managed_curve_uid: string;
  display_name: string;
  mnemonic: string;
  curve_family: string | null;
  unit: string | null;
  eligible: boolean;
  disable_reason: string | null;
}
export interface CurveFillModeCapabilityV2 {
  rule_type: CurveFillRuleTypeV2;
  eligible: boolean;
  disable_reason: string | null;
  comparisons: CurveFillComparisonV2[];
  boundaries: CurveFillBoundaryV2[];
  overlay_policy_uid: string | null;
  overlay_policy_revision: string | null;
  curve_b_operands: CurveFillOperandCapabilityV2[];
}
export interface CurveFillPatternCapabilityV2 { pattern_uid: string; label: string }
export interface CurveFillRasterCapabilityV2 { raster_asset_uid: string; label: string; top_depth: number; base_depth: number; depth_unit: string }
export interface CurveFillPaintCapabilitiesV2 { appearances: CurveFillAppearanceV2[]; patterns: CurveFillPatternCapabilityV2[]; rasters: CurveFillRasterCapabilityV2[] }
export interface CurveFillCapabilitiesV2 {
  contract_version: 'wdv_curve_fill_capabilities_v2';
  managed_well_uid: string;
  session_revision: number;
  track_uid: string;
  curve_a_assignment_uid: string;
  curve_a_mnemonic: string;
  modes: CurveFillModeCapabilityV2[];
  paint?: CurveFillPaintCapabilitiesV2;
}
export interface CurveFillWorkflowResultV2<TSession> {
  contract_version: 'wdv_curve_fill_command_result_v2';
  session: TSession;
  geometry_delta: CurveFillGeometryDeltaV2;
}
export interface CurveFillFeatureStatusV2 {
  contract_version: 'wdv_curve_fill_feature_status_v2';
  enabled: boolean;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && !Array.isArray(payload)
      && typeof (payload as Record<string, unknown>).detail === 'string'
      ? String((payload as Record<string, unknown>).detail)
      : `Curve Fill request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload as T;
}

export async function fetchCurveFillFeatureStatusV2(fetchImpl: typeof fetch = fetch): Promise<CurveFillFeatureStatusV2> {
  const response = await fetchWlvApi('/api/wlv/v2/wdv/curve-fill-commands/feature-status', { headers: { Accept: 'application/json' } }, fetchImpl);
  return parseResponse<CurveFillFeatureStatusV2>(response);
}

export async function fetchCurveFillCapabilitiesV2(
  managedWellUid: string, trackUid: string, curveAAssignmentUid: string, fetchImpl: typeof fetch = fetch,
): Promise<CurveFillCapabilitiesV2> {
  const query = new URLSearchParams({ track_uid: trackUid, curve_a_assignment_uid: curveAAssignmentUid });
  const response = await fetchWlvApi(
    `/api/wlv/v2/wdv/curve-fill-commands/${encodeURIComponent(managedWellUid)}/capabilities?${query.toString()}`,
    { headers: { Accept: 'application/json' } }, fetchImpl,
  );
  return parseResponse<CurveFillCapabilitiesV2>(response);
}

async function postWorkflow<TSession>(
  managedWellUid: string, suffix: string, body: Readonly<Record<string, unknown>>, fetchImpl: typeof fetch,
): Promise<CurveFillWorkflowResultV2<TSession>> {
  const response = await fetchWlvApi(
    `/api/wlv/v2/wdv/curve-fill-commands/${encodeURIComponent(managedWellUid)}/workflow/${suffix}`,
    { method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    fetchImpl,
  );
  return parseResponse<CurveFillWorkflowResultV2<TSession>>(response);
}

export function hydrateCurveFillV2<TSession>(managedWellUid: string, expectedRevision: number, fetchImpl: typeof fetch = fetch) {
  return postWorkflow<TSession>(managedWellUid, 'hydrate', { expected_revision: expectedRevision, max_samples: WDV_CURVE_SAMPLE_LIMIT }, fetchImpl);
}
export function createCurveFillRuleV2<TSession>(managedWellUid: string, body: Readonly<Record<string, unknown>>, fetchImpl: typeof fetch = fetch) {
  return postWorkflow<TSession>(managedWellUid, 'rules', body, fetchImpl);
}
export function removeCurveFillRuleV2<TSession>(managedWellUid: string, expectedRevision: number, ruleUid: string, fetchImpl: typeof fetch = fetch) {
  return postWorkflow<TSession>(managedWellUid, 'rules/remove', { expected_revision: expectedRevision, rule_uid: ruleUid }, fetchImpl);
}
export function updateCurveFillRuleV2<TSession>(managedWellUid: string, body: Readonly<Record<string, unknown>>, fetchImpl: typeof fetch = fetch) {
  return postWorkflow<TSession>(managedWellUid, 'rules/update', body, fetchImpl);
}
export function reorderCurveFillRulesV2<TSession>(managedWellUid: string, body: Readonly<Record<string, unknown>>, fetchImpl: typeof fetch = fetch) {
  return postWorkflow<TSession>(managedWellUid, 'rules/reorder', body, fetchImpl);
}

export function applyCurveFillGeometryDeltaV2(
  current: ReadonlyMap<string, CurveFillGeometryV2>, delta: CurveFillGeometryDeltaV2,
): Map<string, CurveFillGeometryV2> {
  const next = new Map(current);

  // A geometry delta is owned by exactly one managed well. Hydration and
  // interactive commands for that well must never remove geometry belonging
  // to another well that is already represented on the shared canvas.
  for (const ruleUid of delta.remove) {
    const existing = next.get(ruleUid);
    if (existing && existing.managed_well_uid !== delta.managed_well_uid) continue;
    next.delete(ruleUid);
  }

  for (const geometry of delta.upsert) {
    if (geometry.managed_well_uid !== delta.managed_well_uid) continue;
    next.set(geometry.rule_uid, geometry);
  }
  return next;
}


export const EMPTY_CURVE_FILL_PAINT_CAPABILITIES_V2: CurveFillPaintCapabilitiesV2 = {
  appearances: ['solid', 'pattern', 'raster'],
  patterns: [],
  rasters: [],
};

export function curveFillPaintCapabilitiesV2(
  capabilities: CurveFillCapabilitiesV2 | null | undefined,
): CurveFillPaintCapabilitiesV2 {
  return capabilities?.paint ?? EMPTY_CURVE_FILL_PAINT_CAPABILITIES_V2;
}

export function resolvedCurveFillPaintV2(geometry: CurveFillGeometryV2): ResolvedCurveFillPaintV2 {
  const appearance = geometry.paint?.appearance ?? geometry.style.appearance ?? 'solid';
  return {
    appearance,
    pattern_uid: geometry.paint?.pattern_uid ?? geometry.style.pattern_uid ?? null,
    pattern_scale: geometry.paint?.pattern_scale ?? geometry.style.pattern_scale ?? 1,
    raster: geometry.paint?.raster ?? null,
  };
}
