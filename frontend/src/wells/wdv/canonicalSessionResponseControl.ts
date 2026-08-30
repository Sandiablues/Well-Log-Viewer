import type { CanonicalSessionProjection } from './canonicalSessionProjectionControl';

export type CanonicalSessionApplicationPlan<TSession, TTrack, TSelection> = Readonly<{
  revision: number;
  session: TSession;
  tracks: TTrack[];
  selection: TSelection;
  projectedTrackCount: number;
  nextTrackCount: number;
  preserveInteraction: boolean;
}>;

type CanonicalSessionLike = Readonly<{
  revision: number;
  selected_track_uid?: string | null;
}>;

/**
 * Convert one already-projected backend canonical-session response into one
 * deterministic React application plan. Projection is centralized separately
 * so startup, refresh, and command responses cannot interpret track identity
 * differently.
 */
export function planCanonicalSessionApplication<
  TSession extends CanonicalSessionLike,
  TTrack,
  TSelection,
>(args: Readonly<{
  projection: CanonicalSessionProjection<TSession, TTrack>;
  preserveInteraction: boolean;
  currentSelection: TSelection;
  backendSelection: (selectedTrackUid: string | null) => TSelection;
  preserveSelection: (
    selection: TSelection,
    tracks: TTrack[],
    backendSelectedTrackUid: string | null,
  ) => TSelection;
}>): CanonicalSessionApplicationPlan<TSession, TTrack, TSelection> {
  const backendSelectedTrackUid = args.projection.selectedTrackUid;
  const selectionSeed = args.preserveInteraction
    ? args.currentSelection
    : args.backendSelection(backendSelectedTrackUid);
  const nextSelection = args.preserveSelection(
    selectionSeed,
    args.projection.tracks,
    backendSelectedTrackUid,
  );

  return {
    revision: args.projection.revision,
    session: args.projection.session,
    tracks: args.projection.tracks,
    selection: nextSelection,
    projectedTrackCount: args.projection.projectedTrackCount,
    nextTrackCount: args.projection.tracks.length,
    preserveInteraction: args.preserveInteraction,
  };
}
