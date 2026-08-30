import { describe, expect, it } from 'vitest';
import { deriveViewportSemantics } from '../viewportSemantics';
import {
  planDragPanViewportUpdate,
  planViewportRangeApplication,
} from '../viewportControl';
import {
  planLockTracks,
  planUnlockTracks,
} from '../viewportMembershipControl';
import { planAddBlankTrack } from '../canvasCompositionControl';
import { useViewportNavigationExecution } from '../useViewportNavigationExecution';
import type { DepthViewRange } from '../WdvPresentationPrimitives';

const fullRange: DepthViewRange = { min: 0, max: 1000 };
const viewRange: DepthViewRange = { min: 100, max: 900 };

function baseSemantics(overrides: Partial<Parameters<typeof deriveViewportSemantics>[0]> = {}) {
  return deriveViewportSemantics({
    trackIdsInDisplayOrder: ['t1', 't2', 't3'],
    selectedTrackId: null,
    combinationActiveTrackIds: [],
    combinationLockedTrackIds: [],
    multiHighlightedTrackIds: [],
    trackDepthRangesById: {},
    combinationGroupViewRange: null,
    viewDepthRange: viewRange,
    viewportTieGroups: [],
    viewportTieSuspendedTrackIds: [],
    ...overrides,
  });
}

describe('WDV rebuilt architecture cross-domain invariants', () => {
  it('scopes unlocked untied viewport operations to the selected tracks', () => {
    const semantics = baseSemantics({
      selectedTrackId: 't2',
      multiHighlightedTrackIds: ['t2', 't3'],
      combinationActiveTrackIds: ['t2', 't3'],
    });

    expect(semantics.globalViewportMode).toBe(false);
    expect(semantics.groupActionTrackIds).toEqual(['t2', 't3']);

    const plan = planViewportRangeApplication({
      nextRange: { min: 200, max: 600 },
      fullRange,
      minSpan: 1,
      selectedViewportTieGroup: semantics.selectedViewportTieGroup,
      selectedViewportTieLeaderLocked: semantics.selectedViewportTieLeaderLocked,
      groupActionTrackIds: semantics.groupActionTrackIds,
      lockedTrackIds: semantics.lockedCombinationTrackIds,
      trackDepthRangesById: {},
      viewDepthRange: viewRange,
    });

    expect(plan).toEqual({
      kind: 'group',
      memberTrackIds: ['t2', 't3'],
      range: { min: 200, max: 600 },
    });
  });

  it('lets a Tie principal remain manipulable while one pan update synchronizes the whole Tie group', () => {
    const pan = planDragPanViewportUpdate({
      dragPanState: {
        startY: 100,
        startRange: { min: 100, max: 300 },
        clampRange: fullRange,
        targetTrackIds: ['t1', 't2', 't3'],
        targetViewportTieGroupId: 'viewport-tie:t1',
      },
      currentY: 150,
      canvasHeight: 500,
      minSpan: 1,
    });

    expect(pan.kind).toBe('tie');
    if (pan.kind !== 'tie') throw new Error('Expected Tie pan plan');
    expect(pan.groupId).toBe('viewport-tie:t1');
    expect(pan.memberTrackIds).toEqual(['t1', 't2', 't3']);
    expect(pan.range).toEqual({ min: 80, max: 280 });
  });

  it('treats Lock as freeze/exclude only and preserves the frozen viewport through unlock', () => {
    const locked = planLockTracks({
      actionTrackIds: ['t2'],
      trackDepthRangesById: { t2: { min: 250, max: 450 } },
      lockedTrackIds: [],
      activeTrackIds: ['t2'],
      groupActionTrackIds: ['t2'],
      activeGroupViewRange: { min: 200, max: 400 },
      effectiveTrackDepthRangesById: { t2: { min: 200, max: 400 } },
      viewDepthRange: viewRange,
    });

    expect(locked).not.toBeNull();
    expect(locked?.trackDepthRangesById.t2).toEqual({ min: 200, max: 400 });
    expect(locked?.lockedTrackIds).toEqual(['t2']);

    const unlocked = planUnlockTracks({
      actionTrackIds: ['t2'],
      lockedTrackIds: locked?.lockedTrackIds ?? [],
      activeTrackIds: locked?.activeTrackIds ?? [],
      suspendedTrackIds: [],
      tieMemberTrackIds: [],
    });

    expect(unlocked?.lockedTrackIds).toEqual([]);
    expect(unlocked).not.toHaveProperty('trackDepthRangesById');

    const whileLocked = planViewportRangeApplication({
      nextRange: { min: 300, max: 500 },
      fullRange,
      minSpan: 1,
      selectedViewportTieGroup: null,
      selectedViewportTieLeaderLocked: false,
      groupActionTrackIds: ['t1'],
      lockedTrackIds: ['t2'],
      trackDepthRangesById: locked?.trackDepthRangesById ?? {},
      viewDepthRange: viewRange,
    });
    expect(whileLocked).toEqual({
      kind: 'group',
      memberTrackIds: ['t1'],
      range: { min: 300, max: 500 },
    });
    expect(locked?.trackDepthRangesById.t2).toEqual({ min: 200, max: 400 });

    const afterUnlock = planViewportRangeApplication({
      nextRange: { min: 300, max: 500 },
      fullRange,
      minSpan: 1,
      selectedViewportTieGroup: null,
      selectedViewportTieLeaderLocked: false,
      groupActionTrackIds: ['t2'],
      lockedTrackIds: unlocked?.lockedTrackIds ?? [],
      trackDepthRangesById: locked?.trackDepthRangesById ?? {},
      viewDepthRange: viewRange,
    });
    expect(afterUnlock).toEqual({
      kind: 'group',
      memberTrackIds: ['t2'],
      range: { min: 300, max: 500 },
    });
  });

  it('keeps selection orthogonal to rendered viewport while using it as command scope', () => {
    const unselected = baseSemantics();
    const selected = baseSemantics({
      selectedTrackId: 't3',
      multiHighlightedTrackIds: ['t1', 't3'],
    });

    expect(selected.globalViewportMode).toBe(false);
    expect(unselected.globalViewportMode).toBe(false);
    expect(selected.effectiveTrackDepthRangesById).toEqual(
      unselected.effectiveTrackDepthRangesById,
    );
    expect(unselected.groupActionTrackIds).toEqual([]);
    expect(selected.groupActionTrackIds).toEqual(['t1', 't3']);
  });

  it('creates a blank Interval track from the explicit draft and never inherits neighboring content', () => {
    const plan = planAddBlankTrack({
      trackType: 'interval',
      insertMode: 'before_selected',
      referenceTrackId: 'existing-core-description-track',
      initialManagedCurveUids: ['must-not-be-copied'],
    });

    expect(plan.ok).toBe(true);
    if (!plan.ok) throw new Error('Expected blank track plan');
    expect(plan.command.track_name).toBe('Interval');
    expect(plan.command.renderer_type).toBe('interval_blank');
    expect(plan.command.track_role).toBe('interval_blank');
    expect(plan.command.initial_managed_curve_uids).toEqual([]);
    expect(plan.command.insert_position).toEqual({
      mode: 'before_track',
      reference_track_uid: 'existing-core-description-track',
    });
  });

  it('centers GoTo/formation-top targets through the selected viewport authority', () => {
    let currentView: DepthViewRange = { min: 0, max: 1000 };
    let marker: number | null = null;
    let trackRanges: Record<string, DepthViewRange> = {};
    const history: DepthViewRange[] = [];

    const navigation = useViewportNavigationExecution({
      viewDepthRange: currentView,
      setViewDepthRange: (value) => {
        currentView = typeof value === 'function' ? value(currentView) : value;
      },
      setViewHistory: (value) => {
        const next = typeof value === 'function' ? value(history) : value;
        history.splice(0, history.length, ...next);
      },
      selectedViewportTieGroup: null,
      setViewportTieGroups: () => undefined,
      setViewportTieHistoryByGroupId: () => undefined,
      groupActionTrackIds: ['t1'],
      activeGroupViewRange: currentView,
      viewportCommandFullRange: fullRange,
      setCombinationGroupHistory: () => undefined,
      setCombinationGroupViewRange: () => undefined,
      globalViewportMode: false,
      trackIds: ['t1', 't2'],
      trackFullDepthRangesById: { t1: fullRange, t2: fullRange },
      canvasAssignedCurveDepthRange: fullRange,
      setTrackDepthRangesById: (value) => {
        trackRanges = typeof value === 'function' ? value(trackRanges) : value;
      },
      lockedCombinationTrackIds: [],
      setIntervalZoomActive: () => undefined,
      setIntervalSelection: () => undefined,
      setDragPanState: () => undefined,
      setGoToDepthMarker: (value) => {
        marker = typeof value === 'function' ? value(marker) : value;
      },
      goToDepthValue: '500',
      setGoToDepthValue: () => undefined,
      applyCombinationRange: (range) => {
        currentView = range;
      },
      recordGroupHistory: () => undefined,
      rangesEqual: (a, b) => a.min === b.min && a.max === b.max,
      minSpan: 1,
      goToReviewWindow: 200,
    });

    expect(navigation.centerGoToDepthTarget(500)).toBe(500);
    expect(currentView).toEqual({ min: 400, max: 600 });
    expect(marker).toBe(500);
    expect(trackRanges).toEqual({});
  });
});
