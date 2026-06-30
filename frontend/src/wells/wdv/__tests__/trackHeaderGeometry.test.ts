import { describe, expect, it } from 'vitest';

import {
  TRACK_HEADER_HEIGHT_PX,
  TRACK_HEADER_TITLE_HEIGHT_PX,
  TRACK_HEADER_WELL_OWNER_HEIGHT_PX,
  TRACK_HEADER_SUBTITLE_HEIGHT_PX,
  TRACK_CURVE_HEADER_ROW_HEIGHT_PX,
  TRACK_HEADER_BOTTOM_PADDING_PX,
  sharedTrackHeaderHeightPx,
} from '../WdvPresentationPrimitives';

const curveTrack = (curveCount: number, managed = true) => ({
  trackId: `track-${curveCount}`,
  trackIndex: 0,
  trackType: 'curve' as const,
  title: 'Curve Track',
  widthPx: 220,
  managedWellUid: managed ? '01900000-0000-7000-8000-000000000001' : null,
  ownerWellName: managed ? 'Forge 21-31' : null,
  curves: Array.from({ length: curveCount }, (_, index) => ({
    assignmentId: `assignment-${index}`,
    curveId: `curve-${index}`,
    observedMnemonic: `C${index}`,
    color: '#000000',
    order: index,
    scaleMin: 0,
    scaleMax: 1,
    scaleMinLabel: '0',
    scaleMaxLabel: '1',
  })),
});

describe('shared track header geometry', () => {
  it('includes the managed-well owner row for multi-curve tracks', () => {
    const expected =
      TRACK_HEADER_TITLE_HEIGHT_PX +
      TRACK_HEADER_WELL_OWNER_HEIGHT_PX +
      TRACK_HEADER_SUBTITLE_HEIGHT_PX +
      2 * TRACK_CURVE_HEADER_ROW_HEIGHT_PX +
      TRACK_HEADER_BOTTOM_PADDING_PX;

    expect(sharedTrackHeaderHeightPx([curveTrack(2) as never])).toBe(expected);
  });

  it('keeps all tracks aligned to the tallest curve header', () => {
    const height = sharedTrackHeaderHeightPx([
      curveTrack(1) as never,
      curveTrack(3) as never,
      {
        trackId: 'md',
        trackIndex: 1,
        trackType: 'depth',
        title: 'MD',
        widthPx: 90,
        depthBasis: 'MD',
        unit: 'm',
      } as never,
    ]);

    const expected =
      TRACK_HEADER_TITLE_HEIGHT_PX +
      TRACK_HEADER_WELL_OWNER_HEIGHT_PX +
      TRACK_HEADER_SUBTITLE_HEIGHT_PX +
      3 * TRACK_CURVE_HEADER_ROW_HEIGHT_PX +
      TRACK_HEADER_BOTTOM_PADDING_PX;

    expect(height).toBe(expected);
    expect(height).toBeGreaterThan(TRACK_HEADER_HEIGHT_PX);
  });

  it('retains the compact minimum for unmanaged single-curve tracks', () => {
    expect(sharedTrackHeaderHeightPx([curveTrack(1, false) as never])).toBe(
      TRACK_HEADER_HEIGHT_PX,
    );
  });
});
