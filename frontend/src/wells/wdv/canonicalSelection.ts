import type {
  AssignmentUid,
  ManagedCurveUid,
  TrackUid,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalViewerSessionV21,
} from '../prototype/canonicalViewerPackageV21';

export type CanonicalWdvSelection =
  | { kind: 'none' }
  | { kind: 'track'; trackUid: TrackUid }
  | {
      kind: 'assignment';
      trackUid: TrackUid;
      assignmentUid: AssignmentUid;
      managedCurveUid: ManagedCurveUid;
    };

export function selectionFromSession(
  session: CanonicalViewerSessionV21,
): CanonicalWdvSelection {
  if (session.selectedTrackUid === null) return { kind: 'none' };
  return { kind: 'track', trackUid: session.selectedTrackUid };
}

export function validateCanonicalSelection(
  session: CanonicalViewerSessionV21,
  selection: CanonicalWdvSelection,
): CanonicalWdvSelection {
  if (selection.kind === 'none') return selection;
  const track = session.tracks.find(
    (item) => item.trackUid === selection.trackUid,
  );
  if (!track) return selectionFromSession(session);
  if (selection.kind === 'track') return selection;
  if (track.trackType !== 'curve') return { kind: 'track', trackUid: track.trackUid };
  const assignment = track.curves.find(
    (item) => item.assignmentUid === selection.assignmentUid,
  );
  if (!assignment || assignment.managedCurveUid !== selection.managedCurveUid) {
    return { kind: 'track', trackUid: track.trackUid };
  }
  return selection;
}
