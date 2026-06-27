import type {
  AssignmentUid,
  ManagedCurveUid,
  TrackUid,
} from '../identity/wdvIdentityV21';
import type {
  CurveAssignment,
  CurveTrack,
  WellLogTrack,
} from '../prototype/trackLayoutModel';
import type {
  ActiveCanonicalWdvActions,
} from './useActiveCanonicalWdv';
import type {
  OriginalWdvPresentationModel,
} from './originalWdvPresentationAdapter';

export type CanonicalTrackInsertMode =
  | 'before_track'
  | 'after_track'
  | 'far_right';

export interface CreateConfiguredTrackInput {
  trackName: string;
  trackType?: 'depth' | 'curve' | 'image' | 'annotation';
  trackKey?: string | null;
  rendererType?: string | null;
  trackRole?: string | null;
  widthPx?: number | null;
  lattice?: 'linear' | 'logarithmic' | null;
  latticeSource?: string | null;
  latticeOverride?: boolean;
  scaleMode?: 'shared' | 'per_curve' | 'dual' | 'normalized';
  depthBasis?: 'MD' | 'TVD' | 'TVDSS' | null;
  insertPosition?: {
    mode: CanonicalTrackInsertMode;
    referenceTrackUid?: TrackUid | null;
  };
  initialManagedCurveUids?: readonly ManagedCurveUid[];
  selectCreatedTrack?: boolean;
}

export interface AddAssignmentInput {
  trackUid: TrackUid;
  managedCurveUid: ManagedCurveUid;
  targetStackIndex?: number | null;
  scaleMin?: number | null;
  scaleMax?: number | null;
  scaleType?: 'linear' | 'logarithmic' | null;
  scaleDirection?: 'normal' | 'reversed' | null;
  color?: string | null;
  lineStyle?: string | null;
  lineWidth?: number | null;
  fillMode?: string | null;
  visible?: boolean;
}

export interface TrackPatchInput {
  title?: string;
  widthPx?: number;
  visible?: boolean;
  lattice?: 'linear' | 'logarithmic';
  latticeSource?: string;
  latticeOverride?: boolean;
  scaleMode?: 'shared' | 'per_curve' | 'dual' | 'normalized';
  depthBasis?: 'MD' | 'TVD' | 'TVDSS';
}

export interface AssignmentPatchInput {
  visible?: boolean;
  scaleMin?: number;
  scaleMax?: number;
  scaleType?: 'linear' | 'logarithmic';
  scaleDirection?: 'normal' | 'reversed';
  rangeMode?: 'auto' | 'fixed';
  color?: string;
  lineVisible?: boolean;
  lineStyle?: 'solid' | 'dash' | 'dot';
  lineWidth?: number;
  lineOpacity?: number;
  positionAnchor?: 'left' | 'center' | 'right';
  horizontalOffsetPct?: number;
  clipToTrack?: boolean;
  fillSide?: 'none' | 'left' | 'right' | 'between';
  fillColor?: string;
  fillOpacity?: number;
  infillSource?: 'solid' | 'lithology' | 'curve_pair';
  infillPattern?: string;
  infillIntervalColumn?: string;
  pairedManagedCurveUid?: ManagedCurveUid | null;
  displayPriority?: 'background' | 'normal' | 'foreground';
  showQaqcWarnings?: boolean;
  showNullGaps?: boolean;
  showOutOfRange?: boolean;
  rangeOverrideMode?: 'governed' | 'manual' | 'fit_to_curve' | 'fit_to_curve_p05_p95' | 'fit_to_curve_p01_p99';
  manualScaleMin?: number;
  manualScaleMax?: number;
}

export interface CanonicalOriginalWdvMutationAdapterDependencies {
  actions: Pick<
    ActiveCanonicalWdvActions,
    'execute' | 'applyTemplate' | 'setPresentationSelection'
  >;
  getPresentation(): OriginalWdvPresentationModel | null;
}

function requirePresentation(
  dependencies: CanonicalOriginalWdvMutationAdapterDependencies,
): OriginalWdvPresentationModel {
  const presentation = dependencies.getPresentation();
  if (presentation === null) {
    throw new Error('Canonical WDV presentation is not ready');
  }
  return presentation;
}

function findTrack(
  presentation: OriginalWdvPresentationModel,
  trackUid: TrackUid,
): WellLogTrack {
  const track = presentation.tracks.find(
    (item) => item.trackId === trackUid,
  );
  if (!track) {
    throw new Error(`Track ${trackUid} is not in the canonical presentation`);
  }
  return track;
}

function findAssignment(
  presentation: OriginalWdvPresentationModel,
  assignmentUid: AssignmentUid,
): {
  track: CurveTrack;
  assignment: CurveAssignment;
} {
  for (const track of presentation.tracks) {
    if (track.trackType !== 'curve') continue;
    const assignment = track.curves.find(
      (item) => item.assignmentId === assignmentUid,
    );
    if (assignment) return { track, assignment };
  }
  throw new Error(
    `Assignment ${assignmentUid} is not in the canonical presentation`,
  );
}

function compactBody(
  body: Record<string, unknown>,
): Readonly<Record<string, unknown>> {
  return Object.fromEntries(
    Object.entries(body).filter(([, value]) => value !== undefined),
  );
}

export class CanonicalOriginalWdvMutationAdapter {
  constructor(
    private readonly dependencies:
      CanonicalOriginalWdvMutationAdapterDependencies,
  ) {}

  createConfiguredTrack(
    input: CreateConfiguredTrackInput,
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    return this.dependencies.actions.execute({
      kind: 'create_configured_track',
      body: compactBody({
        track_name: input.trackName,
        track_type: input.trackType ?? 'curve',
        track_key: input.trackKey,
        renderer_type: input.rendererType,
        track_role: input.trackRole,
        width_px: input.widthPx,
        lattice: input.lattice,
        lattice_source: input.latticeSource,
        lattice_override: input.latticeOverride ?? false,
        scale_mode: input.scaleMode ?? 'per_curve',
        depth_basis: input.depthBasis,
        insert_position: {
          mode: input.insertPosition?.mode ?? 'far_right',
          reference_track_uid:
            input.insertPosition?.referenceTrackUid ?? null,
        },
        initial_managed_curve_uids:
          [...(input.initialManagedCurveUids ?? [])],
        select_created_track: input.selectCreatedTrack ?? true,
      }),
    });
  }

  resetCurveTrackWidths(
    widthPx: number,
    visibleCurveTracksOnly = true,
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    return this.dependencies.actions.execute({
      kind: 'reset_curve_track_widths',
      body: {
        width_px: widthPx,
        visible_curve_tracks_only: visibleCurveTracksOnly,
      },
    });
  }

  removeTrack(
    trackUid: TrackUid,
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    return this.dependencies.actions.execute({
      kind: 'remove_track',
      body: { track_uid: trackUid },
    });
  }

  updateTrack(
    trackUid: TrackUid,
    patch: TrackPatchInput,
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    requirePresentation(this.dependencies);
    return this.dependencies.actions.execute({
      kind: 'update_track',
      body: compactBody({
        track_uid: trackUid,
        track_name: patch.title,
        width_px: patch.widthPx,
        visible: patch.visible,
        lattice: patch.lattice,
        lattice_source: patch.latticeSource,
        lattice_override: patch.latticeOverride,
        scale_mode: patch.scaleMode,
        depth_basis: patch.depthBasis,
      }),
    });
  }

  reorderTracks(
    trackUids: readonly TrackUid[],
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    return this.dependencies.actions.execute({
      kind: 'reorder_tracks',
      body: { track_uids: [...trackUids] },
    });
  }

  addAssignment(
    input: AddAssignmentInput,
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    const presentation = requirePresentation(this.dependencies);
    const track = findTrack(presentation, input.trackUid);
    if (track.trackType !== 'curve') {
      throw new Error('Curve assignments require a curve track');
    }

    return this.dependencies.actions.execute({
      kind: 'add_assignment',
      body: compactBody({
        track_uid: input.trackUid,
        managed_curve_uid: input.managedCurveUid,
        target_stack_index: input.targetStackIndex,
        scale_min: input.scaleMin,
        scale_max: input.scaleMax,
        scale_type: input.scaleType,
        scale_direction: input.scaleDirection,
        color: input.color,
        line_style: input.lineStyle,
        line_width: input.lineWidth,
        fill_mode: input.fillMode,
        visible: input.visible ?? true,
      }),
    });
  }

  removeAssignment(
    assignmentUid: AssignmentUid,
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    return this.dependencies.actions.execute({
      kind: 'remove_assignment',
      body: { assignment_uid: assignmentUid },
    });
  }

  async updateAssignment(
    assignmentUid: AssignmentUid,
    patch: AssignmentPatchInput,
  ): Promise<void> {
    const presentation = requirePresentation(this.dependencies);
    const { track, assignment } = findAssignment(presentation, assignmentUid);

    const scaleChanged =
      patch.scaleMin !== undefined || patch.scaleMax !== undefined;
    const rangeOverrideMode =
      patch.rangeOverrideMode ?? (scaleChanged ? 'manual' : undefined);
    const manualScaleMin =
      rangeOverrideMode === 'manual'
        ? patch.manualScaleMin ?? patch.scaleMin ?? assignment.scaleMin
        : undefined;
    const manualScaleMax =
      rangeOverrideMode === 'manual'
        ? patch.manualScaleMax ?? patch.scaleMax ?? assignment.scaleMax
        : undefined;

    await this.dependencies.actions.execute({
      kind: 'update_assignment',
      body: compactBody({
        assignment_uid: assignmentUid,
        visible: patch.visible,
        range_override_mode: rangeOverrideMode,
        manual_scale_min: manualScaleMin,
        manual_scale_max: manualScaleMax,
        range_mode: patch.rangeMode,
        color: patch.color,
        line_visible: patch.lineVisible,
        line_style: patch.lineStyle,
        line_width: patch.lineWidth,
        line_opacity: patch.lineOpacity,
        position_anchor: patch.positionAnchor,
        horizontal_offset_pct: patch.horizontalOffsetPct,
        clip_to_track: patch.clipToTrack,
        fill_side: patch.fillSide,
        fill_color: patch.fillColor,
        fill_opacity: patch.fillOpacity,
        infill_source: patch.infillSource,
        infill_pattern: patch.infillPattern,
        infill_interval_column: patch.infillIntervalColumn,
        paired_managed_curve_uid:
          patch.pairedManagedCurveUid ?? undefined,
        clear_paired_managed_curve_uid:
          patch.pairedManagedCurveUid === null ? true : undefined,
        display_priority: patch.displayPriority,
        show_qaqc_warnings: patch.showQaqcWarnings,
        show_null_gaps: patch.showNullGaps,
        show_out_of_range: patch.showOutOfRange,
      }),
    });

    this.dependencies.actions.setPresentationSelection({
      kind: 'assignment',
      trackUid: track.trackId as TrackUid,
      assignmentUid,
      managedCurveUid: assignment.curveId as ManagedCurveUid,
    });
  }

  moveAssignment(
    assignmentUid: AssignmentUid,
    targetTrackUid: TrackUid,
    targetStackIndex: number,
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    return this.dependencies.actions.execute({
      kind: 'move_assignment',
      body: {
        assignment_uid: assignmentUid,
        target_track_uid: targetTrackUid,
        target_stack_index: targetStackIndex,
      },
    });
  }

  reorderAssignments(
    trackUid: TrackUid,
    assignmentUids: readonly AssignmentUid[],
  ): ReturnType<ActiveCanonicalWdvActions['execute']> {
    return this.dependencies.actions.execute({
      kind: 'reorder_assignments',
      body: {
        track_uid: trackUid,
        assignment_uids: [...assignmentUids],
      },
    });
  }

  async selectTrack(trackUid: TrackUid | null): Promise<void> {
    await this.dependencies.actions.execute({
      kind: 'select_track',
      body: { track_uid: trackUid },
    });
    this.dependencies.actions.setPresentationSelection(
      trackUid === null
        ? { kind: 'none' }
        : { kind: 'track', trackUid },
    );
  }

  async selectAssignment(
    trackUid: TrackUid,
    assignmentUid: AssignmentUid,
    managedCurveUid: ManagedCurveUid,
  ): Promise<void> {
    await this.dependencies.actions.execute({
      kind: 'select_track',
      body: { track_uid: trackUid },
    });
    this.dependencies.actions.setPresentationSelection({
      kind: 'assignment',
      trackUid,
      assignmentUid,
      managedCurveUid,
    });
  }

  applyTemplate(
    templateKey: string,
    workflowContext?: string | null,
  ): ReturnType<ActiveCanonicalWdvActions['applyTemplate']> {
    return this.dependencies.actions.applyTemplate({
      templateKey,
      workflowContext,
    });
  }
}
