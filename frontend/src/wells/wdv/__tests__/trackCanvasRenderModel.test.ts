import { describe, expect, it } from 'vitest';
import { buildTrackCanvasRenderModel } from '../trackCanvasRenderModel';

const GLOBAL = { min: 1000, max: 1100 };
const FULL = { min: 500, max: 2500 };
const TRACKS = {
  t1: { min: 1200, max: 1250 },
  t2: { min: 3000, max: 3010 },
};
const STATES = { t1: 'active' as const, t2: 'locked' as const };
const SELECTED = { t1: true, t2: false };
const TIED = { t1: true, t2: false };

function build(overrides: Partial<Parameters<typeof buildTrackCanvasRenderModel>[0]> = {}) {
  return buildTrackCanvasRenderModel({
    globalViewportMode: false,
    combinationTrackStateById: STATES,
    combinationTrackSelectedById: SELECTED,
    viewportTieMemberByTrackId: TIED,
    effectiveTrackDepthRangesById: TRACKS,
    viewDepthRange: GLOBAL,
    fullDepthRange: FULL,
    dragPanActive: false,
    ...overrides,
  });
}

describe('buildTrackCanvasRenderModel', () => {
  it('suppresses per-track viewport overrides in global viewport mode', () => {
    expect(build({ globalViewportMode: true }).trackDepthRangesById).toEqual({});
  });

  it('exposes the effective per-track viewport map outside global mode', () => {
    expect(build().trackDepthRangesById).toBe(TRACKS);
  });

  it('preserves relationship visual-state maps without re-deriving semantics', () => {
    const result = build();
    expect(result.combinationTrackStateById).toBe(STATES);
    expect(result.combinationTrackSelectedById).toBe(SELECTED);
    expect(result.viewportTieMemberByTrackId).toBe(TIED);
  });

  it('passes authoritative global/full ranges through unchanged', () => {
    const result = build();
    expect(result.viewDepthRange).toBe(GLOBAL);
    expect(result.fullDepthRange).toBe(FULL);
  });

  it('carries only the render-facing drag-active flag', () => {
    expect(build({ dragPanActive: true }).dragPanActive).toBe(true);
    expect(build({ dragPanActive: false }).dragPanActive).toBe(false);
  });
});
