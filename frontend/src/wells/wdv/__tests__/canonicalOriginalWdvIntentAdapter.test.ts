import { describe, expect, it, vi } from 'vitest';
import type {
  ManagedCurveUid,
  TrackUid,
  AssignmentUid,
} from '../../identity/wdvIdentityV21';
import type {
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
  WellHeader,
} from '../../prototype/trackLayoutModel';
import type {
  OriginalWdvPresentationModel,
} from '../originalWdvPresentationAdapter';
import {
  CanonicalOriginalWdvMutationAdapter,
} from '../canonicalOriginalWdvIntentAdapter';

const trackUid = '01900000-0000-7000-8000-000000000001' as TrackUid;
const targetTrackUid =
  '01900000-0000-7000-8000-000000000002' as TrackUid;
const assignmentUid =
  '01900000-0000-7000-8000-000000000003' as AssignmentUid;
const curveUid =
  '01900000-0000-7000-8000-000000000004' as ManagedCurveUid;

function presentation(): OriginalWdvPresentationModel {
  const curve: CurveCatalogItem = {
    curveId: curveUid,
    curveUid,
    krCurveTypeId: 'gamma_ray',
    wellUid: 'well',
    managedWellUid: 'well',
    sourceUid: 'source',
    managedSourceUid: 'source',
    observedMnemonic: 'GR',
    normalizedMnemonic: 'GR',
    mnemonic: 'GR',
    description: 'Gamma Ray',
    unit: 'API',
    curveClass: 'gamma',
    defaultLattice: 'linear',
    defaultMin: 0,
    defaultMax: 150,
    defaultScaleDirection: 'normal',
    defaultColor: '#000000',
    recognised: true,
  };

  const assignment: CurveAssignment = {
    assignmentId: assignmentUid,
    curveId: curveUid,
    curveUid,
    krCurveTypeId: null,
    wellUid: 'well',
    managedWellUid: 'well',
    sourceUid: 'source',
    managedSourceUid: 'source',
    observedMnemonic: 'GR',
    normalizedMnemonic: 'GR',
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
    lineWidth: 1,
    lineOpacity: 100,
    positionAnchor: 'center',
    horizontalOffsetPct: 0,
    clipToTrack: true,
    fillSide: 'none',
    fillColor: '#ffffff',
    fillOpacity: 0,
    infillSource: 'solid',
    infillPattern: 'solid',
    infillIntervalColumn: 'lithology',
    displayPriority: 'normal',
    showQaqcWarnings: true,
    showNullGaps: true,
    showOutOfRange: true,
  };

  const track: CurveTrack = {
    trackId: trackUid,
    trackIndex: 0,
    title: 'Curves',
    widthPx: 180,
    visible: true,
    trackType: 'curve',
    lattice: 'linear',
    latticeSource: 'front_curve_default',
    latticeOverride: false,
    scaleMode: 'per_curve',
    curves: [assignment],
  };

  const wellHeader: WellHeader = {
    wellName: 'Well',
    wellboreName: 'Wellbore',
    field: 'Field',
    operator: 'Operator',
    country: 'Country',
    kb: '0',
    gl: '0',
    logStart: '0',
    logEnd: '100',
    sourceFile: 'MSI',
    tvdStatus: 'available',
    msiIdentity: 'well',
  };

  const model: OriginalWdvPresentationModel = {
    managedWellUid: 'well',
    revision: 1,
    curveCatalog: [curve],
    loadedCurves: [{
      managedCurveUid: curveUid,
      curve,
      assigned: true,
      assignmentCount: 1,
    }],
    tracks: [track],
    selection: { kind: 'curve', trackId: trackUid, assignmentId: assignmentUid },
    wellHeader,
    curveSamplesByCurveId: {},
    fullDepthRange: { min: 0, max: 100 },
    propertiesInputs: {
      tracks: [track],
      selection: {
        kind: 'curve',
        trackId: trackUid,
        assignmentId: assignmentUid,
      },
      curveCatalog: [curve],
      wellHeader,
      curveSamplesByCurveId: {},
      fullDepthRange: { min: 0, max: 100 },
    },
    issues: [],
  };

  return model;
}

function harness() {
  const execute = vi.fn(async () => ({} as never));
  const applyTemplate = vi.fn(async () => ({} as never));
  const setPresentationSelection = vi.fn();
  const model = presentation();
  const adapter = new CanonicalOriginalWdvMutationAdapter({
    actions: {
      execute,
      applyTemplate,
      setPresentationSelection,
    },
    getPresentation: () => model,
  });
  return {
    adapter,
    execute,
    applyTemplate,
    setPresentationSelection,
  };
}

describe('CanonicalOriginalWdvMutationAdapter', () => {
  it('maps configured-track creation to one compound command', async () => {
    const { adapter, execute } = harness();

    await adapter.createConfiguredTrack({
      trackName: 'GR',
      insertPosition: {
        mode: 'after_track',
        referenceTrackUid: trackUid,
      },
      initialManagedCurveUids: [curveUid],
    });

    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute).toHaveBeenCalledWith({
      kind: 'create_configured_track',
      body: expect.objectContaining({
        track_name: 'GR',
        insert_position: {
          mode: 'after_track',
          reference_track_uid: trackUid,
        },
        initial_managed_curve_uids: [curveUid],
      }),
    });
  });

  it('maps width reset to one compound command', async () => {
    const { adapter, execute } = harness();

    await adapter.resetCurveTrackWidths(180);

    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute).toHaveBeenCalledWith({
      kind: 'reset_curve_track_widths',
      body: {
        width_px: 180,
        visible_curve_tracks_only: true,
      },
    });
  });

  it('maps exact assignment insertion to one command', async () => {
    const { adapter, execute } = harness();

    await adapter.addAssignment({
      trackUid,
      managedCurveUid: curveUid,
      targetStackIndex: 0,
    });

    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute).toHaveBeenCalledWith({
      kind: 'add_assignment',
      body: expect.objectContaining({
        track_uid: trackUid,
        managed_curve_uid: curveUid,
        target_stack_index: 0,
      }),
    });
  });

  it('merges one-ended scale edits from canonical presentation truth', async () => {
    const { adapter, execute } = harness();

    await adapter.updateAssignment(assignmentUid, {
      scaleMin: 10,
    });

    expect(execute).toHaveBeenCalledWith({
      kind: 'update_assignment',
      body: expect.objectContaining({
        assignment_uid: assignmentUid,
        range_override_mode: 'manual',
        manual_scale_min: 10,
        manual_scale_max: 150,
      }),
    });
  });

  it('persists containing track before local assignment selection', async () => {
    const { adapter, execute, setPresentationSelection } = harness();

    await adapter.selectAssignment(trackUid, assignmentUid, curveUid);

    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute).toHaveBeenCalledWith({
      kind: 'select_track',
      body: { track_uid: trackUid },
    });
    expect(setPresentationSelection).toHaveBeenCalledWith({
      kind: 'assignment',
      trackUid,
      assignmentUid,
      managedCurveUid: curveUid,
    });
  });

  it('does not expose revision, command id, fetch, or local mutation ownership', () => {
    const source = CanonicalOriginalWdvMutationAdapter.toString();
    expect(source).not.toContain('expected_revision');
    expect(source).not.toContain('command_id');
    expect(source).not.toContain('fetch(');
    expect(source).not.toContain('setTracks');
    expect(source).not.toContain('makeCurveAssignment');
  });

  it('maps assignment movement to one command', async () => {
    const { adapter, execute } = harness();

    await adapter.moveAssignment(
      assignmentUid,
      targetTrackUid,
      2,
    );

    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute).toHaveBeenCalledWith({
      kind: 'move_assignment',
      body: {
        assignment_uid: assignmentUid,
        target_track_uid: targetTrackUid,
        target_stack_index: 2,
      },
    });
  });
});
