import { describe, expect, it } from 'vitest';
import { planDragPanStart } from '../useDragPanExecution';

const GLOBAL = { min: 1000, max: 1100 };
const TRACK = { min: 2000, max: 2010 };
const TIE = { min: 3000, max: 3010 };
const FULL = { min: 0, max: 5000 };

const common = {
  startY: 100,
  lockedTrackIds: new Set<string>(),
  viewportTieGroups: [],
  globalViewportMode: false,
  viewDepthRange: GLOBAL,
  trackFullDepthRangesById: { t1: FULL, t2: FULL },
  canvasAllTrackDepthRange: FULL,
  effectiveTrackDepthRangesById: { t1: TRACK },
};

describe('planDragPanStart', () => {
  it('blocks a locked source track', () => {
    const plan = planDragPanStart({ ...common, sourceTrackId: 't1', lockedTrackIds: new Set(['t1']) });
    expect(plan.kind).toBe('blocked');
  });

  it('routes a tied source to the Tie viewport', () => {
    const plan = planDragPanStart({
      ...common,
      sourceTrackId: 't2',
      viewportTieGroups: [{ groupId: 'tie-1', leaderTrackId: 't1', memberTrackIds: ['t1', 't2'], viewport: TIE }],
    });
    expect(plan.kind).toBe('tie');
    if (plan.kind === 'tie') {
      expect(plan.state.targetViewportTieGroupId).toBe('tie-1');
      expect(plan.state.startRange).toEqual(TIE);
    }
  });

  it('blocks Tie manipulation when its leader is locked', () => {
    const plan = planDragPanStart({
      ...common,
      sourceTrackId: 't2',
      lockedTrackIds: new Set(['t1']),
      viewportTieGroups: [{ groupId: 'tie-1', leaderTrackId: 't1', memberTrackIds: ['t1', 't2'], viewport: TIE }],
    });
    expect(plan.kind).toBe('blocked');
  });

  it('routes a fully global canvas to global viewport authority', () => {
    const plan = planDragPanStart({ ...common, sourceTrackId: 't1', globalViewportMode: true });
    expect(plan.kind).toBe('global');
    if (plan.kind === 'global') expect(plan.state.startRange).toEqual(GLOBAL);
  });

  it('routes an untied source on a governed canvas to its own viewport', () => {
    const plan = planDragPanStart({ ...common, sourceTrackId: 't1' });
    expect(plan.kind).toBe('track');
    if (plan.kind === 'track') {
      expect(plan.state.targetTrackId).toBe('t1');
      expect(plan.state.startRange).toEqual(TRACK);
    }
  });

  it('uses defensive global fallback when a track UID is unavailable', () => {
    const plan = planDragPanStart({ ...common, sourceTrackId: null });
    expect(plan.kind).toBe('global');
  });
});
