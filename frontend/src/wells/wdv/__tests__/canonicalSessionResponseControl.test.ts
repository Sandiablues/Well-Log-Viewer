import { describe, expect, it } from 'vitest';
import { projectCanonicalSession } from '../canonicalSessionProjectionControl';
import { planCanonicalSessionApplication } from '../canonicalSessionResponseControl';

type Session = {
  revision: number;
  state_status: 'active';
  selected_track_uid?: string | null;
  ids: string[];
};
type Track = { id: string };
type Selection = { kind: 'track'; trackId: string } | { kind: 'none' };

const preserveSelection = (
  selection: Selection,
  tracks: Track[],
  backendSelectedTrackUid: string | null,
): Selection => {
  if (selection.kind === 'track' && tracks.some((track) => track.id === selection.trackId)) return selection;
  if (backendSelectedTrackUid && tracks.some((track) => track.id === backendSelectedTrackUid)) {
    return { kind: 'track', trackId: backendSelectedTrackUid };
  }
  return { kind: 'none' };
};

const projectionFor = (session: Session, limit?: number) => projectCanonicalSession({
  session,
  projectTracks: (value) => value.ids.map((id) => ({ id })),
  reindexTracks: (tracks) => limit === undefined ? tracks.slice() : tracks.slice(0, limit),
});

describe('planCanonicalSessionApplication', () => {
  it('uses the shared backend projection as authoritative', () => {
    const session: Session = { revision: 8, state_status: 'active', selected_track_uid: 't2', ids: ['t2', 't1'] };
    const plan = planCanonicalSessionApplication({
      projection: projectionFor(session),
      preserveInteraction: false,
      currentSelection: { kind: 'track', trackId: 't1' } as Selection,
      backendSelection: (uid): Selection => ({ kind: 'track', trackId: uid ?? '' }),
      preserveSelection,
    });
    expect(plan.tracks.map((track) => track.id)).toEqual(['t2', 't1']);
    expect(plan.selection).toEqual({ kind: 'track', trackId: 't2' });
    expect(plan.revision).toBe(8);
  });

  it('preserves valid interaction selection without changing canonical order', () => {
    const session: Session = { revision: 9, state_status: 'active', selected_track_uid: 't2', ids: ['t2', 't1'] };
    const plan = planCanonicalSessionApplication({
      projection: projectionFor(session),
      preserveInteraction: true,
      currentSelection: { kind: 'track', trackId: 't1' } as Selection,
      backendSelection: (uid): Selection => ({ kind: 'track', trackId: uid ?? '' }),
      preserveSelection,
    });
    expect(plan.tracks.map((track) => track.id)).toEqual(['t2', 't1']);
    expect(plan.selection).toEqual({ kind: 'track', trackId: 't1' });
  });

  it('falls back to backend selection if preserved interaction references a removed track', () => {
    const session: Session = { revision: 10, state_status: 'active', selected_track_uid: 't2', ids: ['t2'] };
    const plan = planCanonicalSessionApplication({
      projection: projectionFor(session),
      preserveInteraction: true,
      currentSelection: { kind: 'track', trackId: 'removed' } as Selection,
      backendSelection: (uid): Selection => ({ kind: 'track', trackId: uid ?? '' }),
      preserveSelection,
    });
    expect(plan.selection).toEqual({ kind: 'track', trackId: 't2' });
  });

  it('returns one coherent plan with projection diagnostic counts', () => {
    const session: Session = { revision: 11, state_status: 'active', selected_track_uid: null, ids: ['a', 'b', 'c'] };
    const plan = planCanonicalSessionApplication({
      projection: projectionFor(session, 2),
      preserveInteraction: false,
      currentSelection: { kind: 'none' } as Selection,
      backendSelection: (uid): Selection => ({ kind: 'track', trackId: uid ?? '' }),
      preserveSelection,
    });
    expect(plan.projectedTrackCount).toBe(3);
    expect(plan.nextTrackCount).toBe(2);
    expect(plan.preserveInteraction).toBe(false);
  });
});
