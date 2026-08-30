import { describe, expect, it } from 'vitest';
import { planAddBlankTrack, planAssignmentReorder, planTrackReorder } from '../canvasCompositionControl';

function track(trackId: string, trackIndex: number) {
  return { trackId, trackIndex, trackType: 'curve', widthPx: 220, curves: [] } as any;
}

describe('canvasCompositionControl', () => {
  it('creates an interval as an explicit blank template', () => {
    const plan = planAddBlankTrack({ trackType: 'interval', insertMode: 'far_right' });
    expect(plan.ok).toBe(true);
    if (!plan.ok) return;
    expect(plan.command.renderer_type).toBe('interval_blank');
    expect(plan.command.track_role).toBe('interval_blank');
    expect(plan.command.initial_managed_curve_uids).toEqual([]);
  });

  it('does not inherit selected-track content into a blank interval', () => {
    const plan = planAddBlankTrack({
      trackType: 'interval', insertMode: 'after_selected', selectedTrackId: 'track-a',
      initialManagedCurveUids: ['curve-should-not-copy'],
    });
    expect(plan.ok).toBe(true);
    if (!plan.ok) return;
    expect(plan.command.initial_managed_curve_uids).toEqual([]);
    expect(plan.command.insert_position).toEqual({ mode: 'after_track', reference_track_uid: 'track-a' });
  });

  it('requires a reference for before/after insertion', () => {
    expect(planAddBlankTrack({ trackType: 'curve', insertMode: 'before_selected' })).toEqual({
      ok: false, reason: 'missing_reference_track',
    });
  });

  it('reorders tracks without changing identities', () => {
    const plan = planTrackReorder([track('a', 0), track('b', 1), track('c', 2)], 'b', 1);
    expect(plan?.orderedTrackIds).toEqual(['a', 'c', 'b']);
    expect(plan?.nextTracks.map((item) => item.trackId)).toEqual(['a', 'c', 'b']);
  });

  it('does not reorder beyond a canvas boundary', () => {
    expect(planTrackReorder([track('a', 0), track('b', 1)], 'a', -1)).toBeNull();
  });

  it('reorders assignments by UID only', () => {
    expect(planAssignmentReorder(['a', 'b', 'c'], 'b', 0)).toEqual(['b', 'a', 'c']);
  });

  it('rejects invalid assignment destinations', () => {
    expect(planAssignmentReorder(['a', 'b'], 'a', 3)).toBeNull();
  });
});
