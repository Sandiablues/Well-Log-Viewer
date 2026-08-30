import { describe, expect, it } from 'vitest';
import { planCanonicalStartupApplication, projectCanonicalSession } from '../canonicalSessionProjectionControl';

type Session = {
  revision: number;
  state_status: 'empty' | 'active' | 'cleared';
  selected_track_uid: string | null;
  ids: string[];
};
type Track = { id: string };
type Selection = { kind: 'track'; trackId: string };

describe('canonicalSessionProjectionControl', () => {
  it('projects active canonical sessions once in backend order', () => {
    const session: Session = { revision: 4, state_status: 'active', selected_track_uid: 'b', ids: ['b', 'a'] };
    const projection = projectCanonicalSession({
      session,
      projectTracks: (value) => value.ids.map((id) => ({ id })),
      reindexTracks: (tracks) => tracks.slice(),
    });
    expect(projection.revision).toBe(4);
    expect(projection.selectedTrackUid).toBe('b');
    expect(projection.tracks.map((track) => track.id)).toEqual(['b', 'a']);
    expect(projection.projectedTrackCount).toBe(2);
  });

  it('projects non-active canonical sessions to an empty track graph', () => {
    const session: Session = { revision: 5, state_status: 'cleared', selected_track_uid: 'stale', ids: ['stale'] };
    const projection = projectCanonicalSession({
      session,
      projectTracks: (value) => value.ids.map((id) => ({ id })),
      reindexTracks: (tracks) => tracks.slice(),
    });
    expect(projection.tracks).toEqual([]);
    expect(projection.projectedTrackCount).toBe(0);
  });

  it('startup uses valid backend selection', () => {
    const plan = planCanonicalStartupApplication<Track, Selection>({
      tracks: [{ id: 'a' }, { id: 'b' }],
      selectedTrackUid: 'b',
      trackUid: (track) => track.id,
      buildTrackSelection: (trackId) => ({ kind: 'track', trackId }),
    });
    expect(plan.selection).toEqual({ kind: 'track', trackId: 'b' });
  });

  it('startup falls back to the first canonical track when backend selection is stale', () => {
    const plan = planCanonicalStartupApplication<Track, Selection>({
      tracks: [{ id: 'a' }, { id: 'b' }],
      selectedTrackUid: 'removed',
      trackUid: (track) => track.id,
      buildTrackSelection: (trackId) => ({ kind: 'track', trackId }),
    });
    expect(plan.selection).toEqual({ kind: 'track', trackId: 'a' });
  });

  it('startup emits an empty track selection for an empty canonical graph', () => {
    const plan = planCanonicalStartupApplication<Track, Selection>({
      tracks: [],
      selectedTrackUid: null,
      trackUid: (track) => track.id,
      buildTrackSelection: (trackId) => ({ kind: 'track', trackId }),
    });
    expect(plan.selection).toEqual({ kind: 'track', trackId: '' });
  });
});
