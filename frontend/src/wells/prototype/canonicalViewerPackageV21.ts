import { fetchWlvApi } from '../api/wlvApiClient';
import type {
  AssignmentUid,
  ManagedCurveUid,
  ManagedProductUid,
  ManagedSourceUid,
  ManagedWellUid,
  ManagedWellboreUid,
  SessionUid,
  TrackUid,
} from '../identity/wdvIdentityV21';
import {
  WdvIdentityContractError,
  asAssignmentUid,
  asManagedCurveUid,
  asManagedProductUid,
  asManagedSourceUid,
  asManagedWellUid,
  asManagedWellboreUid,
  asSessionUid,
  asTrackUid,
  parseCanonicalCurveCatalogItemV21,
} from '../identity/wdvIdentityV21';
import type {
  CurveAssignmentV21,
  CurveCatalogItemV21,
  CurveLatticeV21,
  CurveTrackV21,
  DepthTrackV21,
  WellLogTrackV21,
} from './trackLayoutModelV21';
import { validateTrackGraphV21 } from './trackLayoutModelV21';

export interface CanonicalViewerPackageV21 {
  contractVersion: 'wdv_viewer_package_v2_2';
  managedWellUid: ManagedWellUid;
  managedWellboreUid: ManagedWellboreUid | null;
  wellName: string;
  wellboreName: string | null;
  depthRange: {
    minimum: number | null;
    maximum: number | null;
    unit: string;
  };
  curves: CurveCatalogItemV21[];
  session: CanonicalViewerSessionV21;
  warnings: string[];
}

export interface CanonicalViewerSessionV21 {
  contractVersion: 'wdv_session_layout_state_v2_1';
  sessionUid: SessionUid;
  managedWellUid: ManagedWellUid;
  revision: number;
  stateStatus: 'empty' | 'active' | 'cleared';
  selectedTrackUid: TrackUid | null;
  tracks: WellLogTrackV21[];
  curveFills?: CanonicalCurveFillV21[];
  warnings: string[];
  updatedAt: string;
}


export interface CanonicalCurveFillV21 {
  fillUid: string;
  trackUid: TrackUid;
  ownerAssignmentUid: AssignmentUid;
  fillMode: 'conditional' | 'crossover';
  operandACurveUid: ManagedCurveUid;
  operandBCurveUid: ManagedCurveUid;
  condition: 'a_greater_than_b' | 'a_less_than_b' | null;
  overlayPolicyId: string | null;
  overlayPolicyRevision: string | null;
  fill: string;
  opacity: number;
  deadband: number | null;
  minimumInterval: number | null;
  depthUnit: string;
  enabled: boolean;
}

export class CanonicalWdvApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'CanonicalWdvApiError';
    this.status = status;
  }
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new WdvIdentityContractError(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new WdvIdentityContractError(`${field} must be a non-blank string`);
  }
  return value.trim();
}

function optionalString(value: unknown, field: string): string | null {
  if (value === null || typeof value === 'undefined') return null;
  if (typeof value !== 'string') {
    throw new WdvIdentityContractError(`${field} must be a string or null`);
  }
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function finiteNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new WdvIdentityContractError(`${field} must be a finite number`);
  }
  return value;
}

function optionalFiniteNumber(value: unknown, field: string): number | null {
  if (value === null || typeof value === 'undefined') return null;
  return finiteNumber(value, field);
}

function requireInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new WdvIdentityContractError(`${field} must be a non-negative integer`);
  }
  return value;
}

function requireBoolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') {
    throw new WdvIdentityContractError(`${field} must be boolean`);
  }
  return value;
}

function optionalBoolean(
  value: unknown,
  field: string,
  fallback: boolean,
): boolean {
  if (value === null || typeof value === 'undefined') return fallback;
  return requireBoolean(value, field);
}

function optionalInteger(
  value: unknown,
  field: string,
  fallback: number,
): number {
  if (value === null || typeof value === 'undefined') return fallback;
  return requireInteger(value, field);
}

function enumValue<T extends string>(
  value: unknown,
  field: string,
  allowed: readonly T[],
  fallback: T,
): T {
  if (value === null || typeof value === 'undefined') return fallback;
  const normalized = requireString(value, field) as T;
  if (!allowed.includes(normalized)) {
    throw new WdvIdentityContractError(
      `${field} must be one of: ${allowed.join(', ')}`,
    );
  }
  return normalized;
}

function stringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new WdvIdentityContractError(`${field} must be an array of strings`);
  }
  return [...value];
}

function parseDisplayPolicy(
  value: unknown,
): Pick<
  CurveCatalogItemV21,
  | 'curveClass'
  | 'defaultLattice'
  | 'defaultMin'
  | 'defaultMax'
  | 'defaultScaleDirection'
  | 'defaultColor'
  | 'recognised'
  | 'reviewRequired'
> {
  const record = requireRecord(value, 'display_policy');
  const lattice = requireString(record.lattice, 'display_policy.lattice');
  if (lattice !== 'linear' && lattice !== 'logarithmic') {
    throw new WdvIdentityContractError(
      'display_policy.lattice must be linear or logarithmic',
    );
  }
  const direction = requireString(
    record.scale_direction,
    'display_policy.scale_direction',
  );
  if (direction !== 'normal' && direction !== 'reversed') {
    throw new WdvIdentityContractError(
      'display_policy.scale_direction must be normal or reversed',
    );
  }

  return {
    curveClass: requireString(record.curve_class, 'display_policy.curve_class'),
    defaultLattice: lattice as CurveLatticeV21,
    defaultMin: optionalFiniteNumber(record.display_min, 'display_policy.display_min'),
    defaultMax: optionalFiniteNumber(record.display_max, 'display_policy.display_max'),
    reviewRequired: optionalBoolean(record.review_required, 'display_policy.review_required', false),
    defaultScaleDirection: direction === 'reversed' ? 'reverse' : 'normal',
    defaultColor: requireString(record.default_color, 'display_policy.default_color'),
    recognised: true,
  };
}

function parseCurve(value: unknown): CurveCatalogItemV21 {
  const record = requireRecord(value, 'viewer curve');
  const identity = parseCanonicalCurveCatalogItemV21(record);
  return {
    ...identity,
    ...parseDisplayPolicy(record.display_policy),
  };
}

function parseAssignment(
  value: unknown,
  catalogue: ReadonlyMap<ManagedCurveUid, CurveCatalogItemV21>,
): CurveAssignmentV21 {
  const record = requireRecord(value, 'session assignment');
  for (const forbidden of [
    'curve_id',
    'curve_uid',
    'product_id',
    'display_curve_id',
    'canonical_curve_id',
    'mnemonic',
  ]) {
    if (Object.prototype.hasOwnProperty.call(record, forbidden)) {
      throw new WdvIdentityContractError(
        `Session assignment contains forbidden active identity field: ${forbidden}`,
      );
    }
  }

  const managedCurveUid = asManagedCurveUid(record.managed_curve_uid);
  const curve = catalogue.get(managedCurveUid);
  if (!curve) {
    throw new WdvIdentityContractError(
      `Assignment references unknown managed_curve_uid: ${managedCurveUid}`,
    );
  }

  const scaleMin = optionalFiniteNumber(record.scale_min, 'scale_min');
  const scaleMax = optionalFiniteNumber(record.scale_max, 'scale_max');
  const lineWidth = optionalFiniteNumber(record.line_width, 'line_width');

  const backendDirection = enumValue(
    record.scale_direction,
    'scale_direction',
    ['normal', 'reversed'] as const,
    curve.defaultScaleDirection === 'reverse' ? 'reversed' : 'normal',
  );
  const backendScaleType = enumValue(
    record.scale_type,
    'scale_type',
    ['linear', 'logarithmic'] as const,
    curve.defaultLattice === 'logarithmic' ? 'logarithmic' : 'linear',
  );

  return {
    assignmentUid: asAssignmentUid(record.assignment_uid),
    trackUid: asTrackUid(record.track_uid),
    managedCurveUid,
    managedProductUid: asManagedProductUid(record.managed_product_uid),
    managedWellUid: asManagedWellUid(record.managed_well_uid),
    managedWellboreUid:
      record.managed_wellbore_uid === null
        || typeof record.managed_wellbore_uid === 'undefined'
        ? null
        : asManagedWellboreUid(record.managed_wellbore_uid),
    managedSourceUid: asManagedSourceUid(record.managed_source_uid),
    stackIndex: requireInteger(record.stack_index, 'stack_index'),
    visible: requireBoolean(record.visible, 'visible'),
    scaleMin: scaleMin ?? curve.defaultMin,
    scaleMax: scaleMax ?? curve.defaultMax,
    scaleDirection: backendDirection === 'reversed' ? 'reverse' : 'normal',
    scaleType: backendScaleType === 'logarithmic' ? 'log' : 'linear',
    rangeMode: enumValue(
      record.range_mode,
      'range_mode',
      ['auto', 'fixed'] as const,
      'fixed',
    ),
    color: optionalString(record.color, 'color') ?? curve.defaultColor,
    lineVisible: optionalBoolean(record.line_visible, 'line_visible', true),
    lineStyle: enumValue(
      record.line_style,
      'line_style',
      ['solid', 'dash', 'dot'] as const,
      'solid',
    ),
    lineWidth: lineWidth ?? 1.8,
    lineOpacity: optionalInteger(record.line_opacity, 'line_opacity', 100),
    positionAnchor: enumValue(
      record.position_anchor,
      'position_anchor',
      ['left', 'center', 'right'] as const,
      'center',
    ),
    horizontalOffsetPct:
      optionalFiniteNumber(record.horizontal_offset_pct, 'horizontal_offset_pct')
      ?? 0,
    clipToTrack: optionalBoolean(record.clip_to_track, 'clip_to_track', true),
    fillSide: enumValue(
      record.fill_side,
      'fill_side',
      ['none', 'left', 'right', 'between'] as const,
      'none',
    ),
    fillColor: optionalString(record.fill_color, 'fill_color') ?? curve.defaultColor,
    fillOpacity: optionalInteger(record.fill_opacity, 'fill_opacity', 55),
    infillSource: enumValue(
      record.infill_source,
      'infill_source',
      ['solid', 'lithology', 'curve_pair'] as const,
      'solid',
    ),
    infillPattern: optionalString(record.infill_pattern, 'infill_pattern') ?? 'solid',
    infillIntervalColumn:
      optionalString(record.infill_interval_column, 'infill_interval_column')
      ?? 'lithology',
    pairedManagedCurveUid:
      record.paired_managed_curve_uid === null
        || typeof record.paired_managed_curve_uid === 'undefined'
        ? null
        : asManagedCurveUid(record.paired_managed_curve_uid),
    displayPriority: enumValue(
      record.display_priority,
      'display_priority',
      ['background', 'normal', 'foreground'] as const,
      'normal',
    ),
    showQaqcWarnings: optionalBoolean(
      record.show_qaqc_warnings,
      'show_qaqc_warnings',
      true,
    ),
    showNullGaps: optionalBoolean(record.show_null_gaps, 'show_null_gaps', true),
    showOutOfRange: optionalBoolean(
      record.show_out_of_range,
      'show_out_of_range',
      true,
    ),
  };
}

function parseTrack(
  value: unknown,
  index: number,
  catalogue: ReadonlyMap<ManagedCurveUid, CurveCatalogItemV21>,
): WellLogTrackV21 {
  const record = requireRecord(value, 'session track');
  const trackUid = asTrackUid(record.track_uid);
  const trackType = requireString(record.track_type, 'track_type');
  const title = requireString(record.track_name, 'track_name');
  const widthPx =
    typeof record.width_px === 'number' && Number.isInteger(record.width_px)
      ? Math.max(1, record.width_px)
      : trackType === 'depth' ? 96 : 240;

  const common = {
    trackUid,
    trackIndex: index,
    title,
    widthPx,
    visible: optionalBoolean(record.visible, 'visible', true),
    trackKey: optionalString(record.track_key, 'track_key'),
    rendererType: optionalString(record.renderer_type, 'renderer_type'),
    trackRole: optionalString(record.track_role, 'track_role'),
    sourceTemplateKey: optionalString(
      record.source_template_key,
      'source_template_key',
    ),
    sourceApplicationPlanUid: optionalString(
      record.source_application_plan_uid,
      'source_application_plan_uid',
    ),
  };

  if (trackType === 'depth') {
    if (!Array.isArray(record.assignments) || record.assignments.length !== 0) {
      throw new WdvIdentityContractError(
        'Depth track assignments must be an empty array',
      );
    }
    const depthTrack: DepthTrackV21 = {
      ...common,
      trackType: 'depth',
      depthBasis: enumValue(
        record.depth_basis,
        'depth_basis',
        ['MD', 'TVD', 'TVDSS'] as const,
        'MD',
      ),
      unit: 'ft',
    };
    return depthTrack;
  }

  if (trackType !== 'curve') {
    throw new WdvIdentityContractError(
      `Unsupported canonical track_type: ${trackType}`,
    );
  }
  if (!Array.isArray(record.assignments)) {
    throw new WdvIdentityContractError('Curve track assignments must be an array');
  }

  const lattice = enumValue(
    record.lattice,
    'lattice',
    ['linear', 'logarithmic'] as const,
    'linear',
  );
  const latticeSource = enumValue(
    record.lattice_source,
    'lattice_source',
    ['front_curve_default', 'user_override', 'template', 'governed_template'] as const,
    'front_curve_default',
  );

  const track: CurveTrackV21 = {
    ...common,
    trackType: 'curve',
    lattice,
    latticeSource:
      latticeSource === 'governed_template' ? 'template' : latticeSource,
    latticeOverride: optionalBoolean(
      record.lattice_override,
      'lattice_override',
      latticeSource === 'user_override',
    ),
    scaleMode: enumValue(
      record.scale_mode,
      'scale_mode',
      ['shared', 'per_curve', 'dual', 'normalized'] as const,
      'per_curve',
    ),
    curves: record.assignments.map((item) => parseAssignment(item, catalogue)),
  };
  return track;
}


function parseCurveFill(value: unknown): CanonicalCurveFillV21 {
  const record = requireRecord(value, 'curve fill');
  const operandA = requireRecord(record.operand_a, 'curve fill operand_a');
  const operandB = requireRecord(record.operand_b, 'curve fill operand_b');
  if (operandA.type !== 'curve' || operandB.type !== 'curve') {
    throw new WdvIdentityContractError('Canonical frontend currently requires curve operands');
  }
  const style = requireRecord(record.style, 'curve fill style');
  const fillMode = enumValue(record.fill_mode, 'fill_mode', ['conditional','crossover'] as const, 'conditional');
  return {
    fillUid: requireString(record.fill_uid, 'fill_uid'),
    trackUid: asTrackUid(record.track_uid),
    ownerAssignmentUid: asAssignmentUid(record.owner_assignment_uid),
    fillMode,
    operandACurveUid: asManagedCurveUid(operandA.curve_uid),
    operandBCurveUid: asManagedCurveUid(operandB.curve_uid),
    condition: record.condition == null ? null : enumValue(record.condition,'condition',['a_greater_than_b','a_less_than_b'] as const,'a_greater_than_b'),
    overlayPolicyId: optionalString(record.overlay_policy_id,'overlay_policy_id'),
    overlayPolicyRevision: optionalString(record.overlay_policy_revision,'overlay_policy_revision'),
    fill: requireString(style.fill,'style.fill'),
    opacity: finiteNumber(style.opacity,'style.opacity'),
    deadband: optionalFiniteNumber(record.deadband,'deadband'),
    minimumInterval: optionalFiniteNumber(record.minimum_interval,'minimum_interval'),
    depthUnit: requireString(record.depth_unit,'depth_unit'),
    enabled: optionalBoolean(record.enabled,'enabled',true),
  };
}

export function parseCanonicalViewerSessionV21(
  value: unknown,
  curves: readonly CurveCatalogItemV21[],
): CanonicalViewerSessionV21 {
  const record = requireRecord(value, 'viewer session');
  if (record.contract_version !== 'wdv_session_layout_state_v2_1') {
    throw new WdvIdentityContractError(
      'Session contract_version must be wdv_session_layout_state_v2_1',
    );
  }
  if (!Array.isArray(record.tracks)) {
    throw new WdvIdentityContractError('Session tracks must be an array');
  }

  const catalogue = new Map<ManagedCurveUid, CurveCatalogItemV21>();
  for (const curve of curves) {
    if (catalogue.has(curve.managedCurveUid)) {
      throw new WdvIdentityContractError(
        `Duplicate managedCurveUid: ${curve.managedCurveUid}`,
      );
    }
    catalogue.set(curve.managedCurveUid, curve);
  }

  const tracks = record.tracks.map((item, index) =>
    parseTrack(item, index, catalogue)
  );
  validateTrackGraphV21(tracks);

  const stateStatus = requireString(record.state_status, 'state_status');
  if (
    stateStatus !== 'empty'
    && stateStatus !== 'active'
    && stateStatus !== 'cleared'
  ) {
    throw new WdvIdentityContractError(
      'state_status must be empty, active, or cleared',
    );
  }

  return {
    contractVersion: 'wdv_session_layout_state_v2_1',
    sessionUid: asSessionUid(record.session_uid),
    managedWellUid: asManagedWellUid(record.managed_well_uid),
    revision: requireInteger(record.revision, 'revision'),
    stateStatus,
    selectedTrackUid:
      record.selected_track_uid === null
        || typeof record.selected_track_uid === 'undefined'
        ? null
        : asTrackUid(record.selected_track_uid),
    tracks,
    curveFills: Array.isArray(record.curve_fills) ? record.curve_fills.map(parseCurveFill) : [],
    warnings: stringArray(record.warnings, 'warnings'),
    updatedAt: requireString(record.updated_at, 'updated_at'),
  };
}

export function parseCanonicalViewerPackageV21(
  value: unknown,
): CanonicalViewerPackageV21 {
  const record = requireRecord(value, 'viewer package');
  if (record.contract_version !== 'wdv_viewer_package_v2_2') {
    throw new WdvIdentityContractError(
      'Viewer package contract_version must be wdv_viewer_package_v2_2',
    );
  }
  if (!Array.isArray(record.curves)) {
    throw new WdvIdentityContractError('Viewer package curves must be an array');
  }

  const curves = record.curves.map(parseCurve);
  const session = parseCanonicalViewerSessionV21(record.session, curves);
  const managedWellUid = asManagedWellUid(record.managed_well_uid);
  if (session.managedWellUid !== managedWellUid) {
    throw new WdvIdentityContractError(
      'Viewer package and session managedWellUid must match',
    );
  }

  const depthRange = requireRecord(record.depth_range, 'depth_range');

  return {
    contractVersion: 'wdv_viewer_package_v2_2',
    managedWellUid,
    managedWellboreUid:
      record.managed_wellbore_uid === null
        || typeof record.managed_wellbore_uid === 'undefined'
        ? null
        : asManagedWellboreUid(record.managed_wellbore_uid),
    wellName: requireString(record.well_name, 'well_name'),
    wellboreName: optionalString(record.wellbore_name, 'wellbore_name'),
    depthRange: {
      minimum: optionalFiniteNumber(depthRange.minimum, 'depth_range.minimum'),
      maximum: optionalFiniteNumber(depthRange.maximum, 'depth_range.maximum'),
      unit: requireString(depthRange.unit, 'depth_range.unit'),
    },
    curves,
    session,
    warnings: stringArray(record.warnings, 'warnings'),
  };
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const record =
      payload && typeof payload === 'object' && !Array.isArray(payload)
        ? payload as Record<string, unknown>
        : {};
    const detail =
      typeof record.detail === 'string'
        ? record.detail
        : `Canonical WDV API request failed (${response.status})`;
    throw new CanonicalWdvApiError(detail, response.status);
  }
  return payload;
}

export async function loadCanonicalViewerPackageV21(
  managedWellUid: ManagedWellUid,
  fetchImpl: typeof fetch = fetch,
): Promise<CanonicalViewerPackageV21> {
  const response = await fetchWlvApi(
    `/api/wlv/v2/viewer-packages/${encodeURIComponent(managedWellUid)}`,
    { headers: { Accept: 'application/json' } },
    fetchImpl,
  );
  return parseCanonicalViewerPackageV21(await parseJsonResponse(response));
}

export type CanonicalSessionCommandV21 =
  | { kind: 'create_track'; body: Record<string, unknown> }
  | { kind: 'remove_track'; body: Record<string, unknown> }
  | { kind: 'update_track'; body: Record<string, unknown> }
  | { kind: 'reorder_tracks'; body: Record<string, unknown> }
  | { kind: 'add_assignment'; body: Record<string, unknown> }
  | { kind: 'remove_assignment'; body: Record<string, unknown> }
  | { kind: 'update_assignment'; body: Record<string, unknown> }
  | { kind: 'move_assignment'; body: Record<string, unknown> }
  | { kind: 'reorder_assignments'; body: Record<string, unknown> }
  | { kind: 'select_track'; body: Record<string, unknown> }
  | { kind: 'upsert_curve_fill'; body: Record<string, unknown> }
  | { kind: 'remove_curve_fill'; body: Record<string, unknown> };

function commandPath(kind: CanonicalSessionCommandV21['kind']): string {
  switch (kind) {
    case 'create_track':
      return 'tracks';
    case 'remove_track':
      return 'tracks/remove';
    case 'update_track':
      return 'tracks/update';
    case 'reorder_tracks':
      return 'tracks/reorder';
    case 'add_assignment':
      return 'assignments';
    case 'remove_assignment':
      return 'assignments/remove';
    case 'update_assignment':
      return 'assignments/update';
    case 'move_assignment':
      return 'assignments/move';
    case 'reorder_assignments':
      return 'assignments/reorder';
    case 'select_track':
      return 'selection';
    case 'upsert_curve_fill':
      return 'curve-fills/upsert';
    case 'remove_curve_fill':
      return 'curve-fills/remove';
  }
}

export async function executeCanonicalSessionCommandV21(
  managedWellUid: ManagedWellUid,
  command: CanonicalSessionCommandV21,
  curves: readonly CurveCatalogItemV21[],
  fetchImpl: typeof fetch = fetch,
): Promise<CanonicalViewerSessionV21> {
  const response = await fetchWlvApi(
    `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(managedWellUid)}/${commandPath(command.kind)}`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(command.body),
    },
    fetchImpl,
  );
  return parseCanonicalViewerSessionV21(
    await parseJsonResponse(response),
    curves,
  );
}

export async function applyCanonicalTemplateV21(
  managedWellUid: ManagedWellUid,
  input: {
    expectedRevision: number;
    templateKey: string;
    workflowContext?: string | null;
  },
  curves: readonly CurveCatalogItemV21[],
  fetchImpl: typeof fetch = fetch,
): Promise<CanonicalViewerSessionV21> {
  const response = await fetchWlvApi(
    `/api/wlv/v2/wdv/template-commands/${encodeURIComponent(managedWellUid)}/apply`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        expected_revision: input.expectedRevision,
        template_key: input.templateKey,
        workflow_context: input.workflowContext ?? null,
      }),
    },
    fetchImpl,
  );
  return parseCanonicalViewerSessionV21(
    await parseJsonResponse(response),
    curves,
  );
}

export type {
  AssignmentUid,
  ManagedCurveUid,
  ManagedProductUid,
  ManagedSourceUid,
  ManagedWellUid,
  ManagedWellboreUid,
  SessionUid,
  TrackUid,
};
