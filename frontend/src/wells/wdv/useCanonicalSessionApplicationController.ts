import { useCallback } from 'react';
import { planCanonicalSessionApplication } from './canonicalSessionResponseControl';
import {
  planCanonicalStartupApplication,
  projectCanonicalSession,
} from './canonicalSessionProjectionControl';

export type CanonicalSessionApplicationOptions = Readonly<{
  preserveInteraction?: boolean;
}>;

type CanonicalSessionLike = Readonly<{
  revision: number;
  state_status: 'empty' | 'active' | 'cleared';
  selected_track_uid?: string | null;
}>;

type MutableRevisionRef = { current: number };

type DiagnosticDetail = Readonly<{
  durationMs: number;
  revision: number;
  projectedTrackCount: number;
  nextTrackCount: number;
  preserveInteraction: boolean;
}>;

export function useCanonicalSessionApplicationController<
  TSession extends CanonicalSessionLike,
  TTrack,
  TSelection,
>(args: Readonly<{
  canonicalRevisionRef: MutableRevisionRef;
  setCanonicalSession: (session: TSession) => void;
  setTracks: (tracks: TTrack[]) => void;
  setSelection: (selection: TSelection) => void;
  currentSelection: () => TSelection;
  projectTracks: (session: TSession) => TTrack[];
  reindexTracks: (tracks: TTrack[]) => TTrack[];
  trackUid: (track: TTrack) => string;
  buildTrackSelection: (trackUid: string) => TSelection;
  backendSelection: (selectedTrackUid: string | null) => TSelection;
  preserveSelection: (
    selection: TSelection,
    tracks: TTrack[],
    backendSelectedTrackUid: string | null,
  ) => TSelection;
  recordDiagnostic?: (detail: DiagnosticDetail) => void;
  now?: () => number;
}>) {
  const project = useCallback((session: TSession) => projectCanonicalSession({
    session,
    projectTracks: args.projectTracks,
    reindexTracks: args.reindexTracks,
  }), [args.projectTracks, args.reindexTracks]);

  const prepareCanonicalStartupSession = useCallback((session: TSession) => {
    const projection = project(session);
    args.canonicalRevisionRef.current = projection.revision;
    args.setCanonicalSession(projection.session);
    return projection;
  }, [args.canonicalRevisionRef, args.setCanonicalSession, project]);

  const applyCanonicalStartupLayout = useCallback((
    tracks: TTrack[],
    selectedTrackUid: string | null,
  ): void => {
    const startupPlan = planCanonicalStartupApplication({
      tracks,
      selectedTrackUid,
      trackUid: args.trackUid,
      buildTrackSelection: args.buildTrackSelection,
    });
    args.setTracks(startupPlan.tracks);
    args.setSelection(startupPlan.selection);
  }, [args.buildTrackSelection, args.setSelection, args.setTracks, args.trackUid]);

  const applyCanonicalSession = useCallback((
    rawSession: TSession,
    options: CanonicalSessionApplicationOptions = {},
  ): void => {
    const now = args.now ?? (() => performance.now());
    const diagnosticStartedAt = now();
    const projection = project(rawSession);
    const plan = planCanonicalSessionApplication({
      projection,
      preserveInteraction: Boolean(options.preserveInteraction),
      currentSelection: args.currentSelection(),
      backendSelection: args.backendSelection,
      preserveSelection: args.preserveSelection,
    });
    args.canonicalRevisionRef.current = plan.revision;
    args.setCanonicalSession(plan.session);
    args.setTracks(plan.tracks);
    args.setSelection(plan.selection);
    args.recordDiagnostic?.({
      durationMs: now() - diagnosticStartedAt,
      revision: plan.revision,
      projectedTrackCount: plan.projectedTrackCount,
      nextTrackCount: plan.nextTrackCount,
      preserveInteraction: plan.preserveInteraction,
    });
  }, [args.backendSelection, args.canonicalRevisionRef, args.currentSelection, args.now, args.preserveSelection, args.recordDiagnostic, args.setCanonicalSession, args.setSelection, args.setTracks, project]);

  return { prepareCanonicalStartupSession, applyCanonicalStartupLayout, applyCanonicalSession } as const;
}
