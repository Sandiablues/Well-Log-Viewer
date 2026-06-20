import { describe, expect, it } from 'vitest';
import {
  asAssignmentUid,
  asManagedCurveUid,
  asTrackUid,
} from '../../identity/wdvIdentityV21';
import {
  moveAssignmentCommand,
  updateAssignmentCommand,
  updateTrackCommand,
} from '../canonicalCommandBuilders';
import {
  renderSeriesForTrack,
} from '../canonicalTrackRenderModel';
import {
  validateCanonicalSelection,
} from '../canonicalSelection';
import type {
  CanonicalViewerSessionV21,
} from '../../prototype/canonicalViewerPackageV21';
import type {
  CurveTrackV21,
} from '../../prototype/trackLayoutModelV21';

const TRACK = asTrackUid('019ede00-0000-7000-8000-000000000101');
const OTHER_TRACK = asTrackUid('019ede00-0000-7000-8000-000000000102');
const ASSIGNMENT = asAssignmentUid('019ede00-0000-7000-8000-000000000103');
const CURVE = asManagedCurveUid('019ede00-0000-7000-8000-000000000104');

const track: CurveTrackV21 = {
  trackUid: TRACK,
  trackIndex: 0,
  title: 'Gamma',
  widthPx: 200,
  visible: true,
  trackType: 'curve',
  trackKey: null,
  rendererType: null,
  trackRole: null,
  sourceTemplateKey: null,
  sourceApplicationPlanUid: null,
  lattice: 'linear',
  latticeSource: 'front_curve_default',
  latticeOverride: false,
  scaleMode: 'per_curve',
  curves: [{
    assignmentUid: ASSIGNMENT,
    trackUid: TRACK,
    managedCurveUid: CURVE,
    managedProductUid: '019ede00-0000-7000-8000-000000000105' as never,
    managedWellUid: '019ede00-0000-7000-8000-000000000106' as never,
    managedWellboreUid: null,
    managedSourceUid: '019ede00-0000-7000-8000-000000000107' as never,
    stackIndex: 0,
    visible: true,
    scaleMin: 0,
    scaleMax: 100,
    scaleDirection: 'normal',
    scaleType: 'linear',
    rangeMode: 'fixed',
    color: '#000000',
    lineVisible: true,
    lineStyle: 'solid',
    lineWidth: 1,
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
    pairedManagedCurveUid: null,
    displayPriority: 'normal',
    showQaqcWarnings: true,
    showNullGaps: true,
    showOutOfRange: true,
  }],
};

describe('canonical WDV component contracts', () => {
  it('builds backend command payloads with canonical UID fields', () => {
    expect(updateTrackCommand(4, TRACK, { widthPx: 280 })).toEqual({
      kind: 'update_track',
      body: {
        expected_revision: 4,
        track_uid: TRACK,
        width_px: 280,
      },
    });
    expect(updateAssignmentCommand(4, ASSIGNMENT, {
      scaleMin: 10,
      scaleMax: 90,
      scaleDirection: 'reverse',
    })).toEqual({
      kind: 'update_assignment',
      body: {
        expected_revision: 4,
        assignment_uid: ASSIGNMENT,
        scale_min: 10,
        scale_max: 90,
        scale_direction: 'reversed',
      },
    });
    expect(moveAssignmentCommand(4, ASSIGNMENT, OTHER_TRACK, 2).body).toEqual({
      expected_revision: 4,
      assignment_uid: ASSIGNMENT,
      target_track_uid: OTHER_TRACK,
      target_stack_index: 2,
    });
  });

  it('renders sample series keyed only by managedCurveUid', () => {
    const result = renderSeriesForTrack(
      track,
      new Map([[CURVE, [
        { depth: 1000, value: 0 },
        { depth: 1100, value: 100 },
      ]]]),
      { minimum: 1000, maximum: 1100 },
      { width: 200, height: 400 },
    );
    expect(result[0].managedCurveUid).toBe(CURVE);
    expect(result[0].points).toEqual([
      { depth: 1000, x: 0, y: 0 },
      { depth: 1100, x: 200, y: 400 },
    ]);
  });

  it('downgrades stale assignment selection to its valid track', () => {
    const session = {
      tracks: [track],
      selectedTrackUid: TRACK,
    } as CanonicalViewerSessionV21;
    expect(validateCanonicalSelection(session, {
      kind: 'assignment',
      trackUid: TRACK,
      assignmentUid: asAssignmentUid(
        '019ede00-0000-7000-8000-000000000199',
      ),
      managedCurveUid: CURVE,
    })).toEqual({ kind: 'track', trackUid: TRACK });
  });
});
