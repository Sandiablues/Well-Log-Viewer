import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  CURVE_VIEW_PADDING_X,
  TRACK_CURVE_HEADER_ROW_HEIGHT_PX,
  sharedTrackHeaderHeightPx,
} from '../WdvPresentationPrimitives';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(here, '../WdvPresentationPrimitives.tsx'), 'utf8');
const boundary = readFileSync(resolve(here, '../WdvPageBoundary.tsx'), 'utf8');
const css = readFileSync(resolve(here, '../../../styles/track-layout-prototype.css'), 'utf8');

describe('backend-owned curve scale header', () => {
  it('uses backend tick positions and does not generate scale semantics in the frontend', () => {
    expect(source).toContain('(assignment.scaleTicks ?? []).map');
    expect(source).toContain('tick.normalizedPosition * 100');
    expect(source).toContain('<b>{tick.label}</b>');
    expect(source).not.toContain('generateScaleTicks');
    expect(source).not.toContain('Math.log10(tick');
  });

  it('keeps scale_ticks optional at the frontend compatibility boundary', () => {
    expect(boundary).toContain('scale_ticks?: Array<{');
    expect(boundary).toContain('(raw.scale_ticks ?? []).map');
  });

  it('uses exactly the same horizontal plot padding as the curve renderer', () => {
    expect(CURVE_VIEW_PADDING_X).toBe(10);
    expect(source).toContain('left: `${CURVE_VIEW_PADDING_X}px`');
    expect(source).toContain('right: `${CURVE_VIEW_PADDING_X}px`');
  });

  it('models the two-line scale row in shared header geometry', () => {
    expect(TRACK_CURVE_HEADER_ROW_HEIGHT_PX).toBe(38);
    const track = {
      trackId: 'track',
      trackIndex: 0,
      trackType: 'curve',
      title: 'Curves',
      widthPx: 220,
      managedWellUid: '01900000-0000-7000-8000-000000000001',
      curves: [
        { assignmentId: 'a', curveId: 'c', stackIndex: 0, scaleMin: 0, scaleMax: 150 },
        { assignmentId: 'b', curveId: 'd', stackIndex: 1, scaleMin: 0.2, scaleMax: 2000 },
      ],
    } as never;
    expect(sharedTrackHeaderHeightPx([track])).toBeGreaterThan(108);
  });

  it('uses the 35-percent reduced scale label font size', () => {
    expect(css).toContain('.wlv-curve-scale-tick {');
    expect(css).toContain('.wlv-curve-scale-fallback {');
    const eightPxMatches = (css.match(/font-size: 5.2px;/g) ?? []).length;
    expect(eightPxMatches).toBeGreaterThanOrEqual(2);
  });

  it('uses the adjusted curve-scale glyph size', () => {
    expect(css).toContain('transform: scale(0.715);');
    expect(css).toContain('transform-origin: center top;');
    expect(css).toContain('.wlv-curve-scale-tick.edge-left b {');
    expect(css).toContain('.wlv-curve-scale-tick.edge-right b {');
  });

  it('reduces the unit-label size and compresses the header card vertically', () => {
    expect(css).toContain('.wlv-curve-header-meta em {');
    expect(css).toContain('font-size: 10px;');
    expect(css).toContain('line-height: 1;');
    expect(css).toContain('height: 14px;');
    expect(css).toContain('height: 16px;');
  });

  it('uses the 35-percent reduced unit-label font size', () => {
    expect(css).toContain('.wlv-curve-header-meta em {');
    expect(css).toContain('font-size: 6.5px;');
  });

  it('keeps the scale axis inside the fixed curve-header row', () => {
    expect(css).toContain('min-height: 38px;');
    expect(css).toContain('height: 38px;');
    expect(css).toContain('.wlv-curve-scale-axis {');
  });
});
