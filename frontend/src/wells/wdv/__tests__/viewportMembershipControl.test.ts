import { describe, expect, it } from 'vitest';
import {
    planCombinationTrackToggle,
    planCreateViewportTie,
    planLockTracks,
    planUnlockTracks,
    planUntieViewportTracks,
} from '../viewportMembershipControl';

const GLOBAL = { min: 1000, max: 1100 };
const GROUP = { min: 2000, max: 2010 };
const TIE = { min: 3000, max: 3005 };

describe('viewport membership command planning', () => {
    it('blocks Combination toggle for a locked track', () => {
        expect(planCombinationTrackToggle({ trackId: 't1', lockedTrackIds: ['t1'], activeTrackIds: [] })).toEqual({ kind: 'blocked' });
    });

    it('starts and ends a Combination group without mutating viewport values itself', () => {
        expect(planCombinationTrackToggle({ trackId: 't1', lockedTrackIds: [], activeTrackIds: [] })).toMatchObject({
            kind: 'apply', activeTrackIds: ['t1'], groupViewRangeAction: 'set-current', resetGroupHistory: true,
        });
        expect(planCombinationTrackToggle({ trackId: 't1', lockedTrackIds: [], activeTrackIds: ['t1'] })).toMatchObject({
            kind: 'apply', activeTrackIds: [], groupViewRangeAction: 'clear', resetGroupHistory: true,
        });
    });

    it('creates a Tie from the leader effective viewport and unsuspends its members', () => {
        const plan = planCreateViewportTie({
            canCreate: true,
            leaderTrackId: 't1',
            candidateTrackIds: ['t1', 't2'],
            effectiveTrackDepthRangesById: { t1: TIE },
            viewDepthRange: GLOBAL,
            groups: [],
            historyByGroupId: {},
            suspendedTrackIds: ['t2', 't3'],
        });
        expect(plan?.createdGroup.viewport).toEqual(TIE);
        expect(plan?.createdGroup.memberTrackIds).toEqual(['t1', 't2']);
        expect(plan?.suspendedTrackIds).toEqual(['t3']);
    });

    it('dissolves a Tie when the selected member is its leader and detaches members at Tie viewport', () => {
        const plan = planUntieViewportTracks({
            canUntie: true,
            selectedTiedTrackIds: ['t1'],
            groups: [{ groupId: 'g', leaderTrackId: 't1', memberTrackIds: ['t1', 't2'], viewport: TIE }],
            trackDepthRangesById: {},
            suspendedTrackIds: ['t2'],
            historyByGroupId: { g: [GLOBAL] },
        });
        expect(plan?.groups).toEqual([]);
        expect(plan?.trackDepthRangesById).toEqual({ t1: TIE, t2: TIE });
        expect(plan?.suspendedTrackIds).toEqual([]);
        expect(plan?.historyByGroupId).toEqual({});
    });

    it('detaches only selected followers when at least two Tie members remain', () => {
        const plan = planUntieViewportTracks({
            canUntie: true,
            selectedTiedTrackIds: ['t3'],
            groups: [{ groupId: 'g', leaderTrackId: 't1', memberTrackIds: ['t1', 't2', 't3'], viewport: TIE }],
            trackDepthRangesById: {},
            suspendedTrackIds: [],
            historyByGroupId: { g: [] },
        });
        expect(plan?.groups[0].memberTrackIds).toEqual(['t1', 't2']);
        expect(plan?.trackDepthRangesById.t3).toEqual(TIE);
        expect(plan?.historyByGroupId).toEqual({ g: [] });
    });

    it('freezes each locked track at its current effective viewport', () => {
        const plan = planLockTracks({
            actionTrackIds: ['t1', 't2'],
            trackDepthRangesById: { t2: GLOBAL },
            lockedTrackIds: [],
            activeTrackIds: ['t1', 't2'],
            groupActionTrackIds: ['t1'],
            activeGroupViewRange: GROUP,
            effectiveTrackDepthRangesById: { t1: GROUP, t2: TIE },
            viewDepthRange: GLOBAL,
        });
        expect(plan?.trackDepthRangesById.t1).toEqual(GROUP);
        expect(plan?.trackDepthRangesById.t2).toEqual(TIE);
        expect(plan?.lockedTrackIds).toEqual(['t1', 't2']);
        expect(plan?.activeTrackIds).toEqual([]);
        expect(plan?.clearGroupViewport).toBe(true);
    });

    it('unlock preserves frozen viewport storage and suspends Tie participation until explicit manipulation', () => {
        const plan = planUnlockTracks({
            actionTrackIds: ['t2'],
            lockedTrackIds: ['t1', 't2'],
            activeTrackIds: ['t2'],
            suspendedTrackIds: [],
            tieMemberTrackIds: ['t2'],
        });
        expect(plan).toEqual({ lockedTrackIds: ['t1'], activeTrackIds: [], suspendedTrackIds: ['t2'] });
    });
});
