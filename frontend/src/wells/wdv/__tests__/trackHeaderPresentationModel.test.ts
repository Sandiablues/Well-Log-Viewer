import { describe, expect, it } from 'vitest';
import { buildTrackHeaderPresentationModel } from '../trackHeaderPresentationModel';

describe('buildTrackHeaderPresentationModel', () => {
  const tracks = [
    { trackId: 't1', trackIndex: 0 },
    { trackId: 't2', trackIndex: 1 },
    { trackId: 't3', trackIndex: 2 },
  ] as const;

  it('projects normal header presentation without semantic reinterpretation in the renderer', () => {
    const result = buildTrackHeaderPresentationModel({ tracks, stateByTrackId: {}, selectedByTrackId: {}, tiedByTrackId: {} });
    expect(result.t1).toEqual({ state: 'normal', selected: false, tied: false, title: 'T1', ariaLabel: 'Track T1: unlocked, untied' });
  });

  it('keeps selection independent from lock and Tie presentation', () => {
    const result = buildTrackHeaderPresentationModel({ tracks, stateByTrackId: { t2: 'active' }, selectedByTrackId: { t2: true }, tiedByTrackId: {} });
    expect(result.t2).toEqual({ state: 'active', selected: true, tied: false, title: 'T2', ariaLabel: 'Track T2: unlocked, untied' });
  });

  it('projects Tie state without converting it into Lock state', () => {
    const result = buildTrackHeaderPresentationModel({ tracks, stateByTrackId: {}, selectedByTrackId: {}, tiedByTrackId: { t3: true } });
    expect(result.t3.state).toBe('normal');
    expect(result.t3.tied).toBe(true);
    expect(result.t3.title).toBe('T3 is tied');
    expect(result.t3.ariaLabel).toBe('Track T3: unlocked, tied');
  });

  it('projects locked+tied as two orthogonal visual facts', () => {
    const result = buildTrackHeaderPresentationModel({ tracks, stateByTrackId: { t1: 'locked' }, selectedByTrackId: { t1: true }, tiedByTrackId: { t1: true } });
    expect(result.t1).toEqual({ state: 'locked', selected: true, tied: true, title: 'T1 is locked and tied', ariaLabel: 'Track T1: locked, tied' });
  });
});
