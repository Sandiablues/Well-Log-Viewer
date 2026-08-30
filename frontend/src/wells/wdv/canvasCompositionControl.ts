import type { WellLogTrack } from '../prototype/trackLayoutModel';

export type CanvasTrackKind = 'depth' | 'curve' | 'interval' | 'core' | 'completion';
export type AddTrackInsertMode = 'before_selected' | 'after_selected' | 'far_right';

export type AddTrackCompositionInput = {
  trackType: CanvasTrackKind;
  depthBasis?: string;
  latticeMode?: string;
  scaleMode?: string;
  insertMode: AddTrackInsertMode;
  referenceTrackId?: string | null;
  selectedTrackId?: string | null;
  initialManagedCurveUids?: readonly string[];
};

export type ConfiguredTrackCommand = {
  track_name: string;
  track_type: string;
  renderer_type?: string;
  track_role?: string;
  width_px: number;
  lattice?: string;
  lattice_source?: string;
  lattice_override?: boolean;
  scale_mode?: string;
  depth_basis?: string;
  insert_position:
    | { mode: 'before_track'; reference_track_uid: string }
    | { mode: 'after_track'; reference_track_uid: string }
    | { mode: 'far_right' };
  initial_managed_curve_uids: string[];
};

export type AddTrackPlan =
  | { ok: true; command: ConfiguredTrackCommand }
  | { ok: false; reason: 'missing_reference_track' };

export function planAddBlankTrack(input: AddTrackCompositionInput): AddTrackPlan {
  const referenceTrackUid = input.referenceTrackId ?? input.selectedTrackId ?? null;
  let insert_position: ConfiguredTrackCommand['insert_position'];

  if (input.insertMode === 'far_right') {
    insert_position = { mode: 'far_right' };
  } else {
    if (!referenceTrackUid) return { ok: false, reason: 'missing_reference_track' };
    insert_position = input.insertMode === 'before_selected'
      ? { mode: 'before_track', reference_track_uid: referenceTrackUid }
      : { mode: 'after_track', reference_track_uid: referenceTrackUid };
  }

  // Track identity/content is constructed solely from the explicit draft.
  // No neighboring track object or selected-track content is copied here.
  return {
    ok: true,
    command: {
      track_name: input.trackType === 'depth'
        ? (input.depthBasis ?? 'MD')
        : input.trackType === 'interval'
          ? 'Interval'
          : input.trackType === 'core'
            ? 'Core'
            : input.trackType === 'completion'
              ? 'Completion'
              : 'NEW CURVE TRACK',
      track_type: input.trackType === 'interval' || input.trackType === 'completion'
        ? 'annotation'
        : input.trackType === 'core'
          ? 'image'
          : input.trackType,
      renderer_type: input.trackType === 'interval'
        ? 'interval_blank'
        : input.trackType === 'core'
          ? 'core_image'
          : input.trackType === 'completion'
            ? 'completion_components'
            : undefined,
      track_role: input.trackType === 'interval'
        ? 'interval_blank'
        : input.trackType === 'core'
          ? 'core_image'
          : input.trackType === 'completion'
            ? 'completion_components'
            : undefined,
      width_px: input.trackType === 'depth' ? 65 : input.trackType === 'curve' ? 220 : input.trackType === 'completion' ? 220 : 180,
      lattice: input.trackType === 'curve' && input.latticeMode && input.latticeMode !== 'auto'
        ? input.latticeMode
        : undefined,
      lattice_source: input.trackType === 'curve' && input.latticeMode && input.latticeMode !== 'auto'
        ? 'user_override'
        : 'front_curve_default',
      lattice_override: input.trackType === 'curve' && Boolean(input.latticeMode && input.latticeMode !== 'auto'),
      scale_mode: input.scaleMode,
      depth_basis: input.trackType === 'depth' ? input.depthBasis : undefined,
      insert_position,
      initial_managed_curve_uids: input.trackType === 'curve' ? [...(input.initialManagedCurveUids ?? [])] : [],
    },
  };
}

export function planTrackReorder(
  tracks: readonly WellLogTrack[],
  trackId: string,
  direction: -1 | 1,
): { nextTracks: WellLogTrack[]; orderedTrackIds: string[] } | null {
  const ordered = [...tracks].sort((a, b) => a.trackIndex - b.trackIndex);
  const fromIndex = ordered.findIndex((track) => track.trackId === trackId);
  if (fromIndex < 0) return null;
  const toIndex = fromIndex + direction;
  if (toIndex < 0 || toIndex >= ordered.length) return null;
  const next = [...ordered];
  const [moving] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moving);
  const nextTracks = next.map((track, index) => ({ ...track, trackIndex: index }));
  return { nextTracks, orderedTrackIds: nextTracks.map((track) => track.trackId) };
}

export function planAssignmentReorder(
  assignmentUids: readonly string[],
  assignmentUid: string,
  toIndex: number,
): string[] | null {
  const fromIndex = assignmentUids.indexOf(assignmentUid);
  if (fromIndex < 0) return null;
  if (toIndex < 0 || toIndex >= assignmentUids.length) return null;
  const next = [...assignmentUids];
  const [moving] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moving);
  return next;
}
