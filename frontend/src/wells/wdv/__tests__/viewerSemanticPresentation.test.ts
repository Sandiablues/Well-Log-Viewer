import { describe, expect, it } from 'vitest';
import { buildViewerSemanticPresentation } from '../viewerSemanticPresentation';

const GLOBAL = { min: 1000, max: 1100 };
const TIE = { min: 2000, max: 2010 };

function baseInput() {
  return {
    tracks: [
      { trackId: 't1', trackIndex: 0 },
      { trackId: 't2', trackIndex: 1 },
    ],
    selection: { kind: 'track' as const, trackId: 't1' },
    selectedTrackId: 't1',
    combinationActiveTrackIds: [] as string[],
    combinationLockedTrackIds: [] as string[],
    multiHighlightedTrackIds: [] as string[],
    trackDepthRangesById: {},
    combinationGroupViewRange: null,
    viewDepthRange: GLOBAL,
    viewportTieGroups: [] as Array<{ groupId: string; leaderTrackId: string; memberTrackIds: string[]; viewport: { min: number; max: number } }>,
    viewportTieSuspendedTrackIds: [] as string[],
    fullDepthRange: GLOBAL,
    dragPanActive: false,
    quickView: false,
    combinationLockActionTrackIds: ['t1'] as string[],
  };
}

describe('buildViewerSemanticPresentation', () => {
  it('derives global semantics and canvas presentation from one snapshot', () => {
    const result = buildViewerSemanticPresentation(baseInput());
    expect(result.semantics.globalViewportMode).toBe(true);
    expect(result.presentation.canvas.trackDepthRangesById).toEqual({});
  });

  it('projects explicit Tie membership into the same presentation snapshot', () => {
    const input = baseInput();
    input.viewportTieGroups = [{ groupId: 'g1', leaderTrackId: 't1', memberTrackIds: ['t1', 't2'], viewport: TIE }];
    const result = buildViewerSemanticPresentation(input);
    expect(result.semantics.viewportTieMemberByTrackId).toEqual({ t1: true, t2: true });
    expect(result.presentation.canvas.viewportTieMemberByTrackId).toEqual({ t1: true, t2: true });
  });

  it('keeps suspended Tie members detached in semantic and render models', () => {
    const input = baseInput();
    input.viewportTieGroups = [{ groupId: 'g1', leaderTrackId: 't1', memberTrackIds: ['t1', 't2'], viewport: TIE }];
    input.viewportTieSuspendedTrackIds = ['t2'];
    input.trackDepthRangesById = { t2: { min: 3000, max: 3010 } };
    const result = buildViewerSemanticPresentation(input);
    expect(result.semantics.effectiveTrackDepthRangesById.t2).toEqual({ min: 3000, max: 3010 });
    expect(result.presentation.canvas.trackDepthRangesById.t2).toEqual({ min: 3000, max: 3010 });
  });

  it('does not let selection create viewport ownership', () => {
    const input = baseInput();
    input.multiHighlightedTrackIds = ['t1', 't2'];
    const result = buildViewerSemanticPresentation(input);
    expect(result.semantics.globalViewportMode).toBe(true);
    expect(result.semantics.groupActionTrackIds).toEqual([]);
  });
});
