import { describe, expect, it } from 'vitest';
import type {
  ManagedCurveUid,
} from '../../identity/wdvIdentityV21';
import {
  asManagedCurveUid,
  asManagedProductUid,
  asManagedSourceUid,
  asManagedWellUid,
  asSessionUid,
  asTrackUid,
  asAssignmentUid,
} from '../../identity/wdvIdentityV21';
import type {
  CanonicalViewerPackageV21,
  CanonicalViewerSessionV21,
} from '../canonicalViewerPackageV21';
import {
  CanonicalWdvWorkspaceController,
} from '../canonicalWdvWorkspaceController';

const WELL = asManagedWellUid(
  '019ede00-0000-7000-8000-000000000001',
);
const CURVE = asManagedCurveUid(
  '019ede00-0000-7000-8000-000000000002',
);
const UNUSED_CURVE = asManagedCurveUid(
  '019ede00-0000-7000-8000-000000000003',
);
const PRODUCT = asManagedProductUid(
  '019ede00-0000-7000-8000-000000000004',
);
const SOURCE = asManagedSourceUid(
  '019ede00-0000-7000-8000-000000000005',
);
const TRACK = asTrackUid(
  '019ede00-0000-7000-8000-000000000006',
);
const ASSIGNMENT = asAssignmentUid(
  '019ede00-0000-7000-8000-000000000007',
);
const SESSION = asSessionUid(
  '019ede00-0000-7000-8000-000000000008',
);

function session(): CanonicalViewerSessionV21 {
  return {
    contractVersion: 'wdv_session_layout_state_v2_1',
    sessionUid: SESSION,
    managedWellUid: WELL,
    revision: 2,
    stateStatus: 'active',
    selectedTrackUid: TRACK,
    tracks: [
      {
        trackUid: TRACK,
        trackIndex: 0,
        title: 'Gamma Ray',
        widthPx: 240,
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
        curves: [
          {
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
            scaleMax: 200,
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
          },
        ],
      },
    ],
    warnings: [],
    updatedAt: '2026-06-19T08:00:00+00:00',
  };
}

function viewerPackage(): CanonicalViewerPackageV21 {
  const catalogueItem = (managedCurveUid: ManagedCurveUid) => ({
    managedCurveUid,
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
    legacyIds: [],
    curveClass: 'gamma',
    defaultLattice: 'linear' as const,
    defaultMin: 0,
    defaultMax: 200,
    defaultScaleDirection: 'normal' as const,
    defaultColor: '#000000',
    recognised: true,
  });

  return {
    contractVersion: 'wdv_viewer_package_v2_1',
    managedWellUid: WELL,
    managedWellboreUid: null,
    wellName: 'Test Well',
    wellboreName: null,
    depthRange: {
      minimum: 1000,
      maximum: 2000,
      unit: 'ft',
    },
    curves: [
      catalogueItem(CURVE),
      catalogueItem(UNUSED_CURVE),
    ],
    session: session(),
    warnings: [],
  };
}

describe('CanonicalWdvWorkspaceController', () => {
  it('loads the package and hydrates only assigned visible curves', async () => {
    const sampleRequests: ManagedCurveUid[] = [];
    const controller = new CanonicalWdvWorkspaceController({
      loadViewerPackage: async () => viewerPackage(),
      executeCommand: async () => session(),
      loadSamples: async (_wellUid, curveUid) => {
        sampleRequests.push(curveUid);
        return [{ depth: 1000, value: 50 }];
      },
    });

    const state = await controller.load(WELL);

    expect(state.status).toBe('ready');
    expect(sampleRequests).toEqual([CURVE]);
    expect(state.samplesByManagedCurveUid.get(CURVE)).toEqual([
      { depth: 1000, value: 50 },
    ]);
    expect(state.samplesByManagedCurveUid.has(UNUSED_CURVE)).toBe(false);
  });

  it('does not block package readiness while samples hydrate', async () => {
    let releaseSamples!: () => void;
    const waiting = new Promise<void>((resolve) => {
      releaseSamples = resolve;
    });

    const controller = new CanonicalWdvWorkspaceController({
      loadViewerPackage: async () => viewerPackage(),
      executeCommand: async () => session(),
      loadSamples: async () => {
        await waiting;
        return [{ depth: 1000, value: 50 }];
      },
    });

    const loadPromise = controller.load(WELL);
    await Promise.resolve();
    await Promise.resolve();

    expect(controller.getState().status).toBe('ready');
    expect(controller.getState().samplesByManagedCurveUid.size).toBe(0);

    releaseSamples();
    await loadPromise;
    expect(controller.getState().samplesByManagedCurveUid.size).toBe(1);
  });

  it('applies backend-returned session truth after a command', async () => {
    const updated = {
      ...session(),
      revision: 3,
      selectedTrackUid: null,
    };

    const controller = new CanonicalWdvWorkspaceController({
      loadViewerPackage: async () => viewerPackage(),
      executeCommand: async () => updated,
      loadSamples: async () => [],
    });

    await controller.load(WELL);
    const state = await controller.execute({
      kind: 'select_track',
      body: {
        expected_revision: 2,
        track_uid: null,
      },
    });

    expect(state.session?.revision).toBe(3);
    expect(state.session?.selectedTrackUid).toBeNull();
  });

  it('ignores stale asynchronous results after clear', async () => {
    let releasePackage!: (value: CanonicalViewerPackageV21) => void;
    const pendingPackage = new Promise<CanonicalViewerPackageV21>((resolve) => {
      releasePackage = resolve;
    });

    const controller = new CanonicalWdvWorkspaceController({
      loadViewerPackage: async () => pendingPackage,
      executeCommand: async () => session(),
      loadSamples: async () => [],
    });

    const loadPromise = controller.load(WELL);
    controller.clear();
    releasePackage(viewerPackage());
    await loadPromise;

    expect(controller.getState().status).toBe('idle');
    expect(controller.getState().managedWellUid).toBeNull();
  });

  it('keys sample errors only by managedCurveUid', async () => {
    const controller = new CanonicalWdvWorkspaceController({
      loadViewerPackage: async () => viewerPackage(),
      executeCommand: async () => session(),
      loadSamples: async () => {
        throw new Error('sample unavailable');
      },
    });

    const state = await controller.load(WELL);

    expect(state.sampleErrorsByManagedCurveUid.get(CURVE)).toBe(
      'sample unavailable',
    );
    expect([...state.sampleErrorsByManagedCurveUid.keys()]).toEqual([CURVE]);
  });
});
