import { describe, expect, it } from 'vitest';

import type {
  CurveAssignment,
  CurveTrack,
  DepthTrack,
} from '../trackLayoutModel';
import { resolvePropertiesEditorCurve } from '../WellLogPropertiesPanelSlot';

const assignment: CurveAssignment = {
  assignmentId: 'canonical-assignment',
  curveId: 'curve-rhoz',
  stackIndex: 0,
  visible: true,
  scaleMin: 1.95,
  scaleMax: 2.95,
  scaleDirection: 'normal',
  color: '#111111',
  lineStyle: 'solid',
  lineWidth: 1,
  fillSide: 'none',
  fillColor: '#111111',
};

const curveTrack: CurveTrack = {
  trackId: 'track-density',
  trackIndex: 1,
  trackType: 'curve',
  title: 'Density',
  widthPx: 220,
  visible: true,
  lattice: 'linear',
  latticeSource: 'front_curve_default',
  latticeOverride: false,
  scaleMode: 'per_curve',
  curves: [
    {
      ...assignment,
      assignmentId: 'legacy-local-assignment-id',
    },
  ],
};

const depthTrack: DepthTrack = {
  trackId: 'track-depth',
  trackIndex: 0,
  trackType: 'depth',
  title: 'Depth',
  widthPx: 80,
  visible: true,
  depthBasis: 'MD',
  unit: 'm',
};

describe('properties editor canonical curve selection', () => {
  it('uses the curve assignment already resolved by the properties contract', () => {
    expect(resolvePropertiesEditorCurve(curveTrack, assignment)).toBe(assignment);
  });

  it('does not substitute a curve assignment while a non-curve track is selected', () => {
    expect(resolvePropertiesEditorCurve(depthTrack, assignment)).toBeNull();
  });

  it('preserves an unresolved canonical curve selection as unresolved', () => {
    expect(resolvePropertiesEditorCurve(curveTrack, null)).toBeNull();
  });
});
