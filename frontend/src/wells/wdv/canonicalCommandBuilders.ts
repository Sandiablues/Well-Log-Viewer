import type {
  AssignmentUid,
  ManagedCurveUid,
  TrackUid,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalSessionCommandV21,
} from '../prototype/canonicalViewerPackageV21';
import type {
  CurveAssignmentV21,
  CurveTrackV21,
} from '../prototype/trackLayoutModelV21';

export function updateTrackCommand(
  revision: number,
  trackUid: TrackUid,
  patch: Partial<Pick<
    CurveTrackV21,
    | 'title'
    | 'widthPx'
    | 'visible'
    | 'lattice'
    | 'latticeOverride'
    | 'scaleMode'
  >>,
): CanonicalSessionCommandV21 {
  return {
    kind: 'update_track',
    body: {
      expected_revision: revision,
      track_uid: trackUid,
      ...(patch.title === undefined ? {} : { track_name: patch.title }),
      ...(patch.widthPx === undefined ? {} : { width_px: patch.widthPx }),
      ...(patch.visible === undefined ? {} : { visible: patch.visible }),
      ...(patch.lattice === undefined ? {} : { lattice: patch.lattice }),
      ...(patch.latticeOverride === undefined
        ? {}
        : {
            lattice_override: patch.latticeOverride,
            lattice_source: patch.latticeOverride
              ? 'user_override'
              : 'front_curve_default',
          }),
      ...(patch.scaleMode === undefined ? {} : { scale_mode: patch.scaleMode }),
    },
  };
}

export function updateAssignmentCommand(
  revision: number,
  assignmentUid: AssignmentUid,
  patch: Partial<Pick<
    CurveAssignmentV21,
    | 'visible'
    | 'scaleMin'
    | 'scaleMax'
    | 'scaleDirection'
    | 'scaleType'
    | 'rangeMode'
    | 'color'
    | 'lineVisible'
    | 'lineStyle'
    | 'lineWidth'
    | 'lineOpacity'
    | 'positionAnchor'
    | 'horizontalOffsetPct'
    | 'clipToTrack'
    | 'fillSide'
    | 'fillColor'
    | 'fillOpacity'
    | 'infillSource'
    | 'infillPattern'
    | 'infillIntervalColumn'
    | 'pairedManagedCurveUid'
    | 'displayPriority'
    | 'showQaqcWarnings'
    | 'showNullGaps'
    | 'showOutOfRange'
  >>,
): CanonicalSessionCommandV21 {
  const hasPair = Object.prototype.hasOwnProperty.call(
    patch,
    'pairedManagedCurveUid',
  );
  return {
    kind: 'update_assignment',
    body: {
      expected_revision: revision,
      assignment_uid: assignmentUid,
      ...(patch.visible === undefined ? {} : { visible: patch.visible }),
      ...(patch.scaleMin === undefined ? {} : { scale_min: patch.scaleMin }),
      ...(patch.scaleMax === undefined ? {} : { scale_max: patch.scaleMax }),
      ...(patch.scaleDirection === undefined
        ? {}
        : {
            scale_direction:
              patch.scaleDirection === 'reverse' ? 'reversed' : 'normal',
          }),
      ...(patch.scaleType === undefined
        ? {}
        : {
            scale_type:
              patch.scaleType === 'log' ? 'logarithmic' : 'linear',
          }),
      ...(patch.rangeMode === undefined ? {} : { range_mode: patch.rangeMode }),
      ...(patch.color === undefined ? {} : { color: patch.color }),
      ...(patch.lineVisible === undefined
        ? {}
        : { line_visible: patch.lineVisible }),
      ...(patch.lineStyle === undefined ? {} : { line_style: patch.lineStyle }),
      ...(patch.lineWidth === undefined ? {} : { line_width: patch.lineWidth }),
      ...(patch.lineOpacity === undefined
        ? {}
        : { line_opacity: patch.lineOpacity }),
      ...(patch.positionAnchor === undefined
        ? {}
        : { position_anchor: patch.positionAnchor }),
      ...(patch.horizontalOffsetPct === undefined
        ? {}
        : { horizontal_offset_pct: patch.horizontalOffsetPct }),
      ...(patch.clipToTrack === undefined
        ? {}
        : { clip_to_track: patch.clipToTrack }),
      ...(patch.fillSide === undefined ? {} : { fill_side: patch.fillSide }),
      ...(patch.fillColor === undefined ? {} : { fill_color: patch.fillColor }),
      ...(patch.fillOpacity === undefined
        ? {}
        : { fill_opacity: patch.fillOpacity }),
      ...(patch.infillSource === undefined
        ? {}
        : { infill_source: patch.infillSource }),
      ...(patch.infillPattern === undefined
        ? {}
        : { infill_pattern: patch.infillPattern }),
      ...(patch.infillIntervalColumn === undefined
        ? {}
        : { infill_interval_column: patch.infillIntervalColumn }),
      ...(hasPair && patch.pairedManagedCurveUid === null
        ? { clear_paired_managed_curve_uid: true }
        : {}),
      ...(patch.pairedManagedCurveUid
        ? { paired_managed_curve_uid: patch.pairedManagedCurveUid }
        : {}),
      ...(patch.displayPriority === undefined
        ? {}
        : { display_priority: patch.displayPriority }),
      ...(patch.showQaqcWarnings === undefined
        ? {}
        : { show_qaqc_warnings: patch.showQaqcWarnings }),
      ...(patch.showNullGaps === undefined
        ? {}
        : { show_null_gaps: patch.showNullGaps }),
      ...(patch.showOutOfRange === undefined
        ? {}
        : { show_out_of_range: patch.showOutOfRange }),
    },
  };
}

export function createTrackCommand(
  revision: number,
  title: string,
): CanonicalSessionCommandV21 {
  return {
    kind: 'create_track',
    body: {
      expected_revision: revision,
      track_name: title,
      track_type: 'curve',
      width_px: 240,
      lattice: 'linear',
      lattice_source: 'front_curve_default',
    },
  };
}

export function addAssignmentCommand(
  revision: number,
  trackUid: TrackUid,
  managedCurveUid: ManagedCurveUid,
): CanonicalSessionCommandV21 {
  return {
    kind: 'add_assignment',
    body: {
      expected_revision: revision,
      track_uid: trackUid,
      managed_curve_uid: managedCurveUid,
    },
  };
}

export function moveAssignmentCommand(
  revision: number,
  assignmentUid: AssignmentUid,
  targetTrackUid: TrackUid,
  targetStackIndex: number,
): CanonicalSessionCommandV21 {
  return {
    kind: 'move_assignment',
    body: {
      expected_revision: revision,
      assignment_uid: assignmentUid,
      target_track_uid: targetTrackUid,
      target_stack_index: targetStackIndex,
    },
  };
}

export function upsertCurveFillCommand(input: {
  revision: number;
  fillUid?: string | null;
  trackUid: string;
  ownerAssignmentUid: string;
  ownerCurveUid: string;
  comparisonCurveUid: string;
  managedWellUid: string;
  ownerUnit: string | null;
  comparisonUnit: string | null;
  fillMode: 'conditional' | 'crossover';
  condition: 'a_greater_than_b' | 'a_less_than_b' | null;
  overlayPolicyId: string | null;
  overlayPolicyRevision: string | null;
  fill: string;
  opacity: number;
  deadband: number | null;
  minimumInterval: number | null;
  depthUnit: string;
}): CanonicalSessionCommandV21 {
  const depthDomainUid = `md:${input.managedWellUid}`;
  const operand = (curveUid: string, unit: string | null) => ({
    type: 'curve',
    managed_well_uid: input.managedWellUid,
    curve_uid: curveUid,
    depth_domain_uid: depthDomainUid,
    unit,
  });
  return {
    kind: 'upsert_curve_fill',
    body: {
      expected_revision: input.revision,
      fill_uid: input.fillUid ?? null,
      track_uid: input.trackUid,
      owner_assignment_uid: input.ownerAssignmentUid,
      fill_mode: input.fillMode,
      operand_a: operand(input.ownerCurveUid, input.ownerUnit),
      operand_b: operand(input.comparisonCurveUid, input.comparisonUnit),
      condition: input.fillMode === 'conditional' ? input.condition : null,
      comparison_basis: input.fillMode === 'conditional'
        ? 'engineering_value'
        : 'normalized_track_position',
      overlay_policy_id: input.fillMode === 'crossover'
        ? input.overlayPolicyId
        : null,
      overlay_policy_revision: input.fillMode === 'crossover'
        ? input.overlayPolicyRevision
        : null,
      style: { fill: input.fill, opacity: input.opacity },
      deadband: input.deadband,
      minimum_interval: input.minimumInterval,
      depth_unit: input.depthUnit,
      enabled: true,
    },
  };
}

export function removeCurveFillCommand(
  revision: number,
  fillUid: string,
): CanonicalSessionCommandV21 {
  return {
    kind: 'remove_curve_fill',
    body: { expected_revision: revision, fill_uid: fillUid },
  };
}
