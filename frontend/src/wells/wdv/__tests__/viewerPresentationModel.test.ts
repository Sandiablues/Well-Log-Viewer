import { describe, expect, it } from 'vitest';
import { buildViewerPresentationModel } from '../viewerPresentationModel';

const RANGE = { min: 1000, max: 1100 };
const FULL = { min: 900, max: 1200 };

function buildInput() {
  return {
    tracks: [
      { trackId: 't1', trackIndex: 0 },
      { trackId: 't2', trackIndex: 1 },
    ],
    selection: { kind: 'track' as const, trackId: 't1' },
    globalViewportMode: false,
    combinationTrackStateById: { t1: 'active' as const, t2: 'locked' as const },
    combinationTrackSelectedById: { t1: true, t2: false },
    viewportTieMemberByTrackId: { t1: true, t2: true },
    effectiveTrackDepthRangesById: { t1: RANGE, t2: { min: 2000, max: 2100 } },
    viewDepthRange: RANGE,
    fullDepthRange: FULL,
    dragPanActive: false,
    quickView: false,
    viewportTieCandidateTrackIds: ['t2', 't1'],
    combinationLockActionTrackIds: ['t1'],
    combinationLockedTrackIds: new Set<string>(),
    viewportTieCanCreate: false,
    viewportTieCanUntie: true,
    viewportTieCreateDisabledReason: '',
  };
}

describe('buildViewerPresentationModel', () => {
  it('projects canvas, selection, header and toolbar from one semantic snapshot', () => {
    const result = buildViewerPresentationModel(buildInput());
    expect(result.canvas.trackDepthRangesById.t2).toEqual({ min: 2000, max: 2100 });
    expect(result.selection.highlightedByTrackId.t1).toBe(true);
    expect(result.headerByTrackId.t2.state).toBe('locked');
    expect(result.headerByTrackId.t2.tied).toBe(true);
    expect(result.toolbar.tie.action).toBe('untie');
  });

  it('keeps global viewport mode renderer-facing without erasing semantic header facts', () => {
    const result = buildViewerPresentationModel({ ...buildInput(), globalViewportMode: true });
    expect(result.canvas.trackDepthRangesById).toEqual({});
    expect(result.headerByTrackId.t2.state).toBe('locked');
    expect(result.headerByTrackId.t2.tied).toBe(true);
  });

  it('projects curve assignment selection without teaching the renderer SelectionRef semantics', () => {
    const result = buildViewerPresentationModel({
      ...buildInput(),
      selection: { kind: 'curve' as const, trackId: 't2', assignmentId: 'a-2' },
      combinationTrackSelectedById: { t1: false, t2: false },
    });
    expect(result.selection.highlightedByTrackId.t2).toBe(true);
    expect(result.selection.selectedAssignmentIdByTrackId.t2).toBe('a-2');
  });

  it('dims toolbar actions in Quick View without changing canvas/header projection', () => {
    const result = buildViewerPresentationModel({ ...buildInput(), quickView: true });
    expect(result.toolbar.lock.disabled).toBe(true);
    expect(result.toolbar.tie.disabled).toBe(true);
    expect(result.headerByTrackId.t1.tied).toBe(true);
    expect(result.canvas.viewDepthRange).toEqual(RANGE);
  });

  it('derives Tie candidate order and labels from canonical track index', () => {
    const result = buildViewerPresentationModel(buildInput());
    expect(result.toolbar.tie.candidates).toEqual([
      { trackId: 't1', label: 'T1' },
      { trackId: 't2', label: 'T2' },
    ]);
  });

  it('derives unlocked Lock-action count from relationship state rather than page-level presentation logic', () => {
    const input = buildInput();
    const result = buildViewerPresentationModel({
      ...input,
      combinationLockActionTrackIds: ['t1', 't2'],
      combinationLockedTrackIds: new Set(['t2']),
    });
    expect(result.toolbar.lock.action).toBe('lock');
    expect(result.toolbar.lock.disabled).toBe(false);
  });
});
