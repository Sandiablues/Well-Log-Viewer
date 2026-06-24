import { describe, expect, it } from 'vitest';
import {
  asManagedCurveUid,
  asManagedProductUid,
  asManagedSourceUid,
  asManagedWellUid,
  asSessionUid,
  asTrackUid,
  asAssignmentUid,
} from '../../identity/wdvIdentityV21';
import {
  CanonicalWdvWorkspaceController,
} from '../../prototype/canonicalWdvWorkspaceController';
import type {
  CanonicalViewerPackageV21,
  CanonicalViewerSessionV21,
} from '../../prototype/canonicalViewerPackageV21';
import {
  assignedManagedCurveUids,
} from '../CanonicalWdvView';

const WELL = asManagedWellUid(
  '019ede00-0000-7000-8000-000000000301',
);
const CURVE = asManagedCurveUid(
  '019ede00-0000-7000-8000-000000000302',
);
const PRODUCT = asManagedProductUid(
  '019ede00-0000-7000-8000-000000000303',
);
const SOURCE = asManagedSourceUid(
  '019ede00-0000-7000-8000-000000000304',
);
const TRACK = asTrackUid(
  '019ede00-0000-7000-8000-000000000305',
);
const ASSIGNMENT = asAssignmentUid(
  '019ede00-0000-7000-8000-000000000306',
);
const SESSION = asSessionUid(
  '019ede00-0000-7000-8000-000000000307',
);

function session(revision = 1): CanonicalViewerSessionV21 {
  return {
    contractVersion: 'wdv_session_layout_state_v2_1',
    sessionUid: SESSION,
    managedWellUid: WELL,
    revision,
    stateStatus: 'active',
    selectedTrackUid: TRACK,
    warnings: [],
    updatedAt: '2026-06-19T09:00:00+00:00',
    tracks: [{
      trackUid: TRACK,
      trackIndex: 0,
      title: 'Gamma',
      widthPx: 220,
      visible: true,
      trackType: 'curve',
      trackKey: 'gamma',
      rendererType: 'line_curve',
      trackRole: 'open_hole',
      sourceTemplateKey: 'triple_combo',
      sourceApplicationPlanUid:
        '019ede00-0000-7000-8000-000000000308',
      lattice: 'linear',
      latticeSource: 'template',
      latticeOverride: false,
      scaleMode: 'per_curve',
      curves: [{
        assignmentUid: ASSIGNMENT,
        trackUid: TRACK,
        managedCurveUid: CURVE,
        managedProductUid: PRODUCT,
        managedWellUid: WELL,
        managedWellboreUid: null,
        managedSourceUid: SOURCE,
        stackIndex: 0,
        visible: true,
        scaleMin: 0,
        scaleMax: 150,
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
        pairedManagedCurveUid: null,
        displayPriority: 'normal',
        showQaqcWarnings: true,
        showNullGaps: true,
        showOutOfRange: true,
      }],
    }],
  };
}

function viewerPackage(): CanonicalViewerPackageV21 {
  return {
    contractVersion: 'wdv_viewer_package_v2_2',
    managedWellUid: WELL,
    managedWellboreUid: null,
    wellName: 'Test Well',
    wellboreName: null,
    depthRange: {
      minimum: 1000,
      maximum: 2000,
      unit: 'ft',
    },
    curves: [{
      managedCurveUid: CURVE,
      managedProductUid: PRODUCT,
      managedWellUid: WELL,
      managedWellboreUid: null,
      managedSourceUid: SOURCE,
      krCurveTypeId: 'gamma_ray',
      observedMnemonic: 'GR',
      normalizedMnemonic: 'GR',
      displayName: 'Gamma Ray',
      unit: 'API',
      curveFamily: 'gamma_ray',
      description: null,
      curveClass: 'gamma',
      defaultLattice: 'linear',
      defaultMin: 0,
      defaultMax: 150,
      defaultScaleDirection: 'normal',
      defaultColor: '#000000',
      recognised: true,
      reviewRequired: false,
    }],
    session: session(),
    warnings: [],
  };
}

describe('CanonicalWdvView feature root', () => {
  it('derives assigned inventory state only from managedCurveUid', () => {
    expect([...assignedManagedCurveUids(session())]).toEqual([CURVE]);
  });

  it('accepts an atomic backend template session and hydrates its curves', async () => {
    const applied = session(2);
    const controller = new CanonicalWdvWorkspaceController({
      loadViewerPackage: async () => viewerPackage(),
      executeCommand: async () => session(),
      applyTemplate: async (_well, input) => {
        expect(input).toEqual({
          expectedRevision: 1,
          templateKey: 'triple_combo',
          workflowContext: 'open_hole',
        });
        return applied;
      },
      loadSamples: async () => [{ depth: 1000, value: 50 }],
    });

    await controller.load(WELL);
    const state = await controller.applyTemplate({
      templateKey: 'triple_combo',
      workflowContext: 'open_hole',
    });

    expect(state.session?.revision).toBe(2);
    expect(state.viewerPackage?.session.revision).toBe(2);
    expect(state.samplesByManagedCurveUid.has(CURVE)).toBe(true);
  });
});
