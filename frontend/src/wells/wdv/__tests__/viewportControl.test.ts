import { describe, expect, it } from 'vitest';
import {
    calculateZoomViewportRange,
    planDragPanViewportUpdate,
    planViewportRangeApplication,
} from '../viewportControl';

const FULL = { min: 1000, max: 4000 };
const GLOBAL = { min: 1200, max: 1600 };
const GROUP = { min: 2000, max: 2200 };
const TIE = {
    groupId: 'tie:t1',
    leaderTrackId: 't1',
    memberTrackIds: ['t1', 't2'],
    viewport: { min: 3000, max: 3010 },
};

describe('viewportControl', () => {
    it('blocks a Tie range mutation when the selected principal itself is locked', () => {
        const plan = planViewportRangeApplication({
            nextRange: { min: 3100, max: 3110 }, fullRange: FULL, minSpan: 0.01,
            selectedViewportTieGroup: TIE, selectedViewportTieLeaderLocked: true,
            groupActionTrackIds: ['t2'], globalViewportMode: false, lockedTrackIds: ['t1'],
            trackDepthRangesById: { t1: TIE.viewport }, viewDepthRange: GLOBAL,
        });
        expect(plan).toEqual({ kind: 'blocked' });
    });

    it('routes a Tie range mutation to the Tie authority', () => {
        const plan = planViewportRangeApplication({
            nextRange: { min: 3100, max: 3110 }, fullRange: FULL, minSpan: 0.01,
            selectedViewportTieGroup: TIE, selectedViewportTieLeaderLocked: false,
            groupActionTrackIds: ['t1', 't2'], globalViewportMode: false, lockedTrackIds: [],
            trackDepthRangesById: {}, viewDepthRange: GLOBAL,
        });
        expect(plan).toEqual({
            kind: 'tie', groupId: 'tie:t1', memberTrackIds: ['t1', 't2'],
            range: { min: 3100, max: 3110 },
        });
    });

    it('excludes a locked Tie follower without blocking the selected principal', () => {
        const tie3 = { ...TIE, memberTrackIds: ['t1', 't2', 't3'] };
        const plan = planViewportRangeApplication({
            nextRange: { min: 3100, max: 3110 }, fullRange: FULL, minSpan: 0.01,
            selectedViewportTieGroup: tie3, selectedViewportTieLeaderLocked: false,
            groupActionTrackIds: ['t1', 't3'], globalViewportMode: false, lockedTrackIds: ['t2'],
            trackDepthRangesById: { t2: { min: 3300, max: 3310 } }, viewDepthRange: GLOBAL,
        });
        expect(plan).toEqual({
            kind: 'tie', groupId: 'tie:t1', memberTrackIds: ['t1', 't3'],
            range: { min: 3100, max: 3110 },
        });
    });

    it('routes a grouped range mutation to the group authority', () => {
        const plan = planViewportRangeApplication({
            nextRange: GROUP, fullRange: FULL, minSpan: 0.01,
            selectedViewportTieGroup: null, selectedViewportTieLeaderLocked: false,
            groupActionTrackIds: ['t2', 't3'], globalViewportMode: false, lockedTrackIds: [],
            trackDepthRangesById: {}, viewDepthRange: GLOBAL,
        });
        expect(plan).toEqual({
            kind: 'group',
            memberTrackIds: ['t2', 't3'],
            range: GROUP,
        });
    });

    it('uses the global fallback when there is no explicit selected/Tie viewport scope', () => {
        const plan = planViewportRangeApplication({
            nextRange: { min: 1100, max: 1500 }, fullRange: FULL, minSpan: 0.01,
            selectedViewportTieGroup: null, selectedViewportTieLeaderLocked: false,
            groupActionTrackIds: [], globalViewportMode: true, lockedTrackIds: ['t4', 't5'],
            trackDepthRangesById: { t4: { min: 3500, max: 3510 }, t5: { min: 3600, max: 3610 } },
            viewDepthRange: GLOBAL,
        });
        expect(plan).toEqual({
            kind: 'global', range: { min: 1100, max: 1500 },
            frozenTrackDepthRangesById: {
                t4: { min: 3500, max: 3510 },
                t5: { min: 3600, max: 3610 },
            },
        });
    });

    it('zooms around the authoritative group viewport when a group acts', () => {
        expect(calculateZoomViewportRange({
            viewDepthRange: GLOBAL,
            groupActionTrackIds: ['t2', 't3'],
            activeGroupViewRange: GROUP,
            fullRange: FULL,
            magnificationReferenceRange: FULL,
            factor: 0.5,
            minSpan: 0.01,
        })).toEqual({ min: 2050, max: 2150 });
    });

    it('can zoom a short Core viewport beyond content Full when given the all-track outer domain', () => {
        const next = calculateZoomViewportRange({
            viewDepthRange: { min: 1702.13916, max: 3674.5 },
            groupActionTrackIds: ['t10', 't11'],
            activeGroupViewRange: { min: 3837, max: 4017 },
            fullRange: { min: 197.9, max: 4131 },
            magnificationReferenceRange: { min: 197.9, max: 3674.5 },
            factor: 1.33,
            minSpan: 0.01,
        });
        expect(next.min).toBeLessThan(3837);
        expect(next.max).toBeGreaterThan(4017);
        expect(next.min).toBeGreaterThanOrEqual(197.9);
        expect(next.max).toBeLessThanOrEqual(4131);
    });

    it('routes drag pan to a Tie and preserves member identity', () => {
        expect(planDragPanViewportUpdate({
            dragPanState: {
                startY: 100,
                startRange: { min: 3000, max: 3010 },
                clampRange: FULL,
                targetTrackIds: ['t1', 't2'],
                targetViewportTieGroupId: 'tie:t1',
            },
            currentY: 200,
            canvasHeight: 1000,
            minSpan: 0.01,
        })).toEqual({
            kind: 'tie', groupId: 'tie:t1', memberTrackIds: ['t1', 't2'],
            range: { min: 2999, max: 3009 },
        });
    });

    it('routes drag pan to the actual detached track', () => {
        expect(planDragPanViewportUpdate({
            dragPanState: {
                startY: 100,
                startRange: { min: 1500, max: 1600 },
                clampRange: FULL,
                targetTrackId: 't6',
            },
            currentY: 0,
            canvasHeight: 1000,
            minSpan: 0.01,
        })).toEqual({ kind: 'track', trackId: 't6', range: { min: 1510, max: 1610 } });
    });

    it('routes drag pan without an explicit target to global viewport', () => {
        expect(planDragPanViewportUpdate({
            dragPanState: {
                startY: 0,
                startRange: { min: 1000, max: 1100 },
                clampRange: FULL,
            },
            currentY: 500,
            canvasHeight: 1000,
            minSpan: 0.01,
        })).toEqual({ kind: 'global', range: { min: 1000, max: 1100 } });
    });
});
