import { describe, expect, it } from 'vitest';
import type {
  AssignmentUid,
  ManagedCurveUid,
  ManagedProductUid,
  ManagedSourceUid,
  ManagedWellUid,
  SessionUid,
  TrackUid,
} from '../../identity/wdvIdentityV21';
import type {
  CanonicalWorkspaceV1,
} from '../canonicalWorkspaceV1';
import {
  buildOriginalWdvPresentationModel,
} from '../originalWdvPresentationAdapter';

const uid = {
  well: '01901901-9000-7000-8000-000000000001' as ManagedWellUid,
  source: '01901901-9000-7000-8000-000000000002' as ManagedSourceUid,
  product: '01901901-9000-7000-8000-000000000003' as ManagedProductUid,
  curve: '01901901-9000-7000-8000-000000000004' as ManagedCurveUid,
  track: '01901901-9000-7000-8000-000000000005' as TrackUid,
  assignment: '01901901-9000-7000-8000-000000000006' as AssignmentUid,
  session: '01901901-9000-7000-8000-000000000007' as SessionUid,
};

function workspace(): CanonicalWorkspaceV1 {
  const curve = {
    contractVersion: 'wdv_identity_v2_1' as const,
    managedCurveUid: uid.curve,
    managedProductUid: uid.product,
    managedWellUid: uid.well,
    managedWellboreUid: null,
    managedSourceUid: uid.source,
    krCurveTypeId: 'gamma_ray',
    observedMnemonic: 'GR',
    normalizedMnemonic: 'GR',
    displayName: 'Gamma Ray',
    unit: 'gAPI',
    curveFamily: 'gamma_ray',
    description: 'Gamma Ray',
    legacyIds: [],
    curveClass: 'gamma',
    defaultLattice: 'linear' as const,
    defaultMin: 0,
    defaultMax: 150,
    defaultScaleDirection: 'normal' as const,
    defaultColor: '#2f80ed',
    recognised: true,
  };

  const assignment = {
    assignmentUid: uid.assignment,
    trackUid: uid.track,
    managedCurveUid: uid.curve,
    managedProductUid: uid.product,
    managedWellUid: uid.well,
    managedWellboreUid: null,
    managedSourceUid: uid.source,
    stackIndex: 0,
    visible: true,
    scaleMin: 0,
    scaleMax: 150,
    scaleDirection: 'normal' as const,
    scaleType: 'linear' as const,
    rangeMode: 'fixed' as const,
    color: '#2f80ed',
    lineVisible: true,
    lineStyle: 'solid' as const,
    lineWidth: 1.8,
    lineOpacity: 100,
    positionAnchor: 'center' as const,
    horizontalOffsetPct: 0,
    clipToTrack: true,
    fillSide: 'none' as const,
    fillColor: '#7fbf8f',
    fillOpacity: 55,
    infillSource: 'solid' as const,
    infillPattern: 'solid',
    infillIntervalColumn: 'lithology',
    pairedManagedCurveUid: null,
    displayPriority: 'normal' as const,
    showQaqcWarnings: true,
    showNullGaps: true,
    showOutOfRange: true,
  };

  const session = {
    contractVersion: 'wdv_session_layout_state_v2_1' as const,
    sessionUid: uid.session,
    managedWellUid: uid.well,
    revision: 8,
    stateStatus: 'active' as const,
    selectedTrackUid: uid.track,
    tracks: [{
      trackUid: uid.track,
      trackIndex: 0,
      title: 'Gamma Ray',
      widthPx: 180,
      visible: true,
      trackType: 'curve' as const,
      trackKey: null,
      rendererType: null,
      trackRole: null,
      sourceTemplateKey: null,
      sourceApplicationPlanUid: null,
      lattice: 'linear' as const,
      latticeSource: 'front_curve_default' as const,
      latticeOverride: false,
      scaleMode: 'shared' as const,
      curves: [assignment],
    }],
    warnings: [],
    updatedAt: '2026-06-19T00:00:00+00:00',
  };

  const viewerPackage = {
    contractVersion: 'wdv_viewer_package_v2_1' as const,
    managedWellUid: uid.well,
    managedWellboreUid: null,
    wellName: 'Well A',
    wellboreName: 'Main',
    depthRange: {
      minimum: 1000,
      maximum: 2000,
      unit: 'ft',
    },
    curves: [curve],
    session,
    warnings: [],
  };

  return {
    contractVersion: 'wdv_workspace_v1',
    managedWellUid: uid.well,
    curves: [curve],
    session,
    viewerPackage,
    warnings: [],
  };
}

describe('original WDV presentation adapter', () => {
  it('preserves canonical identities as presentation keys', () => {
    const value = workspace();
    const samples = new Map([
      [uid.curve, [
        { depth: 1000, value: 10 },
        { depth: 1001, value: 11 },
      ]],
    ]);

    const model = buildOriginalWdvPresentationModel(
      value,
      samples,
      {
        kind: 'assignment',
        trackUid: uid.track,
        assignmentUid: uid.assignment,
        managedCurveUid: uid.curve,
      },
    );

    expect(model.revision).toBe(8);
    expect(model.curveCatalog[0].curveId).toBe(uid.curve);
    expect(model.tracks[0].trackId).toBe(uid.track);
    expect(model.tracks[0].trackType).toBe('curve');
    if (model.tracks[0].trackType !== 'curve') throw new Error('curve track expected');
    expect(model.tracks[0].curves[0].assignmentId).toBe(uid.assignment);
    expect(model.tracks[0].curves[0].curveId).toBe(uid.curve);
    expect(model.selection).toEqual({
      kind: 'curve',
      trackId: uid.track,
      assignmentId: uid.assignment,
    });
    expect(model.curveSamplesByCurveId[uid.curve]).toEqual([
      [1000, 10],
      [1001, 11],
    ]);
    expect(model.propertiesInputs.tracks).toBe(model.tracks);
    expect(model.issues).toEqual([]);
  });

  it('reports unresolved assignments without throwing or inventing a curve', () => {
    const value = workspace();
    const missing =
      '01901901-9000-7000-8000-000000000099' as ManagedCurveUid;
    const track = value.session.tracks[0];
    if (track.trackType !== 'curve') throw new Error('curve track expected');

    const broken = {
      ...value,
      session: {
        ...value.session,
        tracks: [{
          ...track,
          curves: [{
            ...track.curves[0],
            managedCurveUid: missing,
          }],
        }],
      },
    } as CanonicalWorkspaceV1;

    const model = buildOriginalWdvPresentationModel(broken);

    expect(model.tracks).toHaveLength(1);
    expect(model.tracks[0].trackType).toBe('curve');
    if (model.tracks[0].trackType !== 'curve') throw new Error('curve track expected');
    expect(model.tracks[0].curves).toEqual([]);
    expect(model.issues).toEqual([
      expect.objectContaining({
        code: 'unresolved_assignment_curve',
        managedCurveUid: missing,
      }),
    ]);
  });

  it('builds loaded-curve inventory from backend assignments', () => {
    const model = buildOriginalWdvPresentationModel(workspace());
    expect(model.loadedCurves).toEqual([
      expect.objectContaining({
        managedCurveUid: uid.curve,
        assigned: true,
        assignmentCount: 1,
      }),
    ]);
  });

  it('does not invent a unit when the canonical unit is absent', () => {
    const value = workspace();
    const curve = {
      ...value.curves[0],
      unit: null,
    };
    const withoutUnit = {
      ...value,
      curves: [curve],
      viewerPackage: {
        ...value.viewerPackage,
        curves: [curve],
      },
    } as CanonicalWorkspaceV1;

    const model = buildOriginalWdvPresentationModel(withoutUnit);

    expect(model.curveCatalog[0].unit).toBe('');
  });

});
