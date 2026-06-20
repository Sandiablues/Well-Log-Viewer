import { describe, expect, it } from 'vitest';
import type {
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
} from '../trackLayoutModel';
import {
  findCurveForAssignment,
  normalizePropertiesSelection,
} from '../propertiesSelectionModel';

const curve: CurveCatalogItem = {
  curveId: 'managed-curve-active',
  curveUid: '01900000-0000-7000-8000-000000000001',
  mnemonic: 'CALI',
  description: 'Caliper',
  unit: 'in',
  curveClass: 'borehole',
  defaultLattice: 'linear',
  defaultMin: 6,
  defaultMax: 16,
  defaultColor: '#000000',
  recognised: true,
};

const assignment: CurveAssignment = {
  assignmentId: 'assignment-active',
  curveId: curve.curveId,
  curveUid: curve.curveUid,
  stackIndex: 0,
  visible: true,
  scaleMin: 6,
  scaleMax: 16,
  scaleDirection: 'normal',
  scaleType: 'linear',
  rangeMode: 'fixed',
  color: '#000000',
  lineVisible: true,
  lineStyle: 'solid',
  lineWidth: 1.8,
  lineOpacity: 100,
  positionAnchor: 'center',
  horizontalOffsetPct: 0,
  clipToTrack: true,
  fillSide: 'none',
  fillColor: '#000000',
  fillOpacity: 55,
  infillSource: 'solid',
  infillPattern: 'solid',
  infillIntervalColumn: 'lithology',
  displayPriority: 'normal',
  showQaqcWarnings: true,
  showNullGaps: true,
  showOutOfRange: true,
};

const track: CurveTrack = {
  trackId: 'track-1',
  trackIndex: 0,
  title: 'Track 1',
  widthPx: 220,
  visible: true,
  trackType: 'curve',
  lattice: 'linear',
  latticeSource: 'front_curve_default',
  latticeOverride: false,
  scaleMode: 'shared',
  curves: [assignment],
};

describe('properties selection model', () => {
  it('resolves a selected assignment against the active loaded-well catalog', () => {
    expect(findCurveForAssignment([curve], assignment)).toEqual(curve);
    expect(normalizePropertiesSelection(
      [track],
      { kind: 'curve', trackId: track.trackId, assignmentId: assignment.assignmentId },
      [curve],
    )).toEqual({
      kind: 'curve',
      trackId: track.trackId,
      assignmentId: assignment.assignmentId,
    });
  });

  it('downgrades a stale assignment selection to its valid track', () => {
    expect(normalizePropertiesSelection(
      [track],
      { kind: 'curve', trackId: track.trackId, assignmentId: 'missing-assignment' },
      [curve],
    )).toEqual({ kind: 'track', trackId: track.trackId });
  });

  it('downgrades selection when the assignment curve is absent from the active catalog', () => {
    expect(normalizePropertiesSelection(
      [track],
      { kind: 'curve', trackId: track.trackId, assignmentId: assignment.assignmentId },
      [],
    )).toEqual({ kind: 'track', trackId: track.trackId });
  });

  it('supports canonical curve UID matching when the presentation curveId changes', () => {
    const migrated = { ...assignment, curveId: 'legacy-presentation-id' };
    expect(findCurveForAssignment([curve], migrated)).toEqual(curve);
  });
});
