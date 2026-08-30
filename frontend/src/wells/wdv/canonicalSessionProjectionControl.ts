export type CanonicalSessionProjection<TSession, TTrack> = Readonly<{
  revision: number;
  session: TSession;
  tracks: TTrack[];
  selectedTrackUid: string | null;
  projectedTrackCount: number;
}>;

type CanonicalSessionLike = Readonly<{
  revision: number;
  state_status: 'empty' | 'active' | 'cleared';
  selected_track_uid?: string | null;
}>;

/**
 * Project backend canonical session truth into the ordered frontend track graph.
 * This is the only canonical-session -> frontend-track projection boundary.
 * It owns no React state and performs no I/O.
 */
export function projectCanonicalSession<TSession extends CanonicalSessionLike, TTrack>(args: Readonly<{
  session: TSession;
  projectTracks: (session: TSession) => TTrack[];
  reindexTracks: (tracks: TTrack[]) => TTrack[];
}>): CanonicalSessionProjection<TSession, TTrack> {
  const projected = args.session.state_status === 'active'
    ? args.projectTracks(args.session)
    : [];
  const tracks = args.reindexTracks(projected);
  return {
    revision: args.session.revision,
    session: args.session,
    tracks,
    selectedTrackUid: args.session.selected_track_uid ?? null,
    projectedTrackCount: projected.length,
  };
}

/**
 * Apply a projected canonical startup layout deterministically. Startup does not
 * preserve stale interaction selection: backend selection wins when valid,
 * otherwise the first canonical track is selected.
 */
export function planCanonicalStartupApplication<TTrack, TSelection>(args: Readonly<{
  tracks: TTrack[];
  selectedTrackUid: string | null;
  trackUid: (track: TTrack) => string;
  buildTrackSelection: (trackUid: string) => TSelection;
}>): Readonly<{ tracks: TTrack[]; selection: TSelection }> {
  const selectedExists = args.selectedTrackUid !== null
    && args.tracks.some((track) => args.trackUid(track) === args.selectedTrackUid);
  const nextTrackUid = selectedExists
    ? args.selectedTrackUid!
    : (args.tracks[0] ? args.trackUid(args.tracks[0]) : '');
  return {
    tracks: args.tracks,
    selection: args.buildTrackSelection(nextTrackUid),
  };
}
