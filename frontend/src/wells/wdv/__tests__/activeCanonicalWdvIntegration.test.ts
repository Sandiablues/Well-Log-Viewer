import { describe, expect, it } from 'vitest';
import type {
  ManagedCurveUid,
  ManagedProductUid,
  ManagedSourceUid,
  ManagedWellUid,
  SessionUid,
} from '../../identity/wdvIdentityV21';
import type {
  CanonicalWorkspaceControllerState,
} from '../CanonicalWorkspaceControllerV2';
import {
  ActiveCanonicalWdvIntegration,
} from '../activeCanonicalWdvIntegration';
import type {
  CanonicalWorkspaceV1,
} from '../canonicalWorkspaceV1';

const wellA =
  '01901901-9000-7000-8000-000000000001' as ManagedWellUid;
const wellB =
  '01901901-9000-7000-8000-000000000002' as ManagedWellUid;
const curveA =
  '01901901-9000-7000-8000-000000000003' as ManagedCurveUid;
const sourceA =
  '01901901-9000-7000-8000-000000000004' as ManagedSourceUid;
const productA =
  '01901901-9000-7000-8000-000000000005' as ManagedProductUid;
const sessionA =
  '01901901-9000-7000-8000-000000000006' as SessionUid;

function workspace(
  managedWellUid: ManagedWellUid,
  revision = 0,
): CanonicalWorkspaceV1 {
  const curve = {
    contractVersion: 'wdv_identity_v2_1' as const,
    managedCurveUid: curveA,
    managedProductUid: productA,
    managedWellUid,
    managedWellboreUid: null,
    managedSourceUid: sourceA,
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

  const session = {
    contractVersion: 'wdv_session_layout_state_v2_1' as const,
    sessionUid: sessionA,
    managedWellUid,
    revision,
    stateStatus: 'empty' as const,
    selectedTrackUid: null,
    tracks: [],
    warnings: [],
    updatedAt: '2026-06-19T00:00:00+00:00',
  };

  return {
    contractVersion: 'wdv_workspace_v1',
    managedWellUid,
    curves: [curve],
    session,
    viewerPackage: {
      contractVersion: 'wdv_viewer_package_v2_1',
      managedWellUid,
      managedWellboreUid: null,
      wellName: managedWellUid === wellA ? 'Well A' : 'Well B',
      wellboreName: null,
      depthRange: {
        minimum: 1000,
        maximum: 2000,
        unit: 'ft',
      },
      curves: [curve],
      session,
      warnings: [],
    },
    warnings: [],
  };
}

class FakeController {
  private state: CanonicalWorkspaceControllerState = {
    status: 'idle',
    managedWellUid: null,
    workspace: null,
    samplesByManagedCurveUid: new Map(),
    error: null,
  };
  private listeners =
    new Set<(state: CanonicalWorkspaceControllerState) => void>();
  readonly pendingLoads = new Map<
    ManagedWellUid,
    (state: CanonicalWorkspaceControllerState) => void
  >();

  getState(): CanonicalWorkspaceControllerState {
    return this.state;
  }

  subscribe(
    listener: (state: CanonicalWorkspaceControllerState) => void,
  ): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  clear(): void {
    this.publish({
      status: 'idle',
      managedWellUid: null,
      workspace: null,
      samplesByManagedCurveUid: new Map(),
      error: null,
    });
  }

  load(
    managedWellUid: ManagedWellUid,
  ): Promise<CanonicalWorkspaceControllerState> {
    this.publish({
      status: 'loading',
      managedWellUid,
      workspace: null,
      samplesByManagedCurveUid: new Map(),
      error: null,
    });
    return new Promise((resolve) => {
      this.pendingLoads.set(managedWellUid, resolve);
    });
  }

  resolveLoad(managedWellUid: ManagedWellUid): void {
    const next: CanonicalWorkspaceControllerState = {
      status: 'ready',
      managedWellUid,
      workspace: workspace(managedWellUid),
      samplesByManagedCurveUid: new Map(),
      error: null,
    };
    this.publish(next);
    this.pendingLoads.get(managedWellUid)?.(next);
  }

  async execute(): Promise<CanonicalWorkspaceControllerState> {
    const current = this.state.workspace;
    if (!current) throw new Error('not ready');
    const nextWorkspace = workspace(
      current.managedWellUid,
      current.session.revision + 1,
    );
    const next = {
      ...this.state,
      status: 'ready' as const,
      workspace: nextWorkspace,
    };
    this.publish(next);
    return next;
  }

  async applyTemplate(): Promise<CanonicalWorkspaceControllerState> {
    return this.execute();
  }

  failNextMutation = false;

  private publish(state: CanonicalWorkspaceControllerState): void {
    this.state = state;
    for (const listener of this.listeners) listener(state);
  }
}

describe('ActiveCanonicalWdvIntegration', () => {
  it('loads a workspace and indexes samples by managed curve UID', async () => {
    const controller = new FakeController();
    const integration = new ActiveCanonicalWdvIntegration({
      controller: controller as never,
      maxSamplesPerCurve: 500,
      loadSamples: async (request) => ({
        contractVersion: 'wdv_curve_samples_v2_1',
        managedWellUid: request.managedWellUid,
        managedCurveUid: request.managedCurveUid,
        sampleRevision: 'r1',
        samples: [{ depth: 1000, value: 25 }],
      }),
    });

    const pending = integration.load(wellA);
    controller.resolveLoad(wellA);
    await pending;

    const state = integration.getState();
    expect(state.status).toBe('empty');
    expect(
      state.samplesByManagedCurveUid.get(curveA),
    ).toEqual([{ depth: 1000, value: 25 }]);
    expect(
      state.presentation?.curveSamplesByCurveId[curveA],
    ).toEqual([[1000, 25]]);
  });

  it('ignores stale workspace and sample results after a well switch', async () => {
    const controller = new FakeController();
    type SampleResponse = {
      contractVersion: 'wdv_curve_samples_v2_1';
      managedWellUid: ManagedWellUid;
      managedCurveUid: ManagedCurveUid;
      sampleRevision: string | null;
      samples: { depth: number; value: number }[];
    };

    let resolveSampleA!: (value: SampleResponse) => void;
    const sampleAPromise = new Promise<SampleResponse>((resolve) => {
      resolveSampleA = resolve;
    });

    const integration = new ActiveCanonicalWdvIntegration({
      controller: controller as never,
      maxSamplesPerCurve: 500,
      loadSamples: async (request) => {
        if (request.managedWellUid === wellA) {
          return sampleAPromise;
        }
        return {
          contractVersion: 'wdv_curve_samples_v2_1',
          managedWellUid: request.managedWellUid,
          managedCurveUid: request.managedCurveUid,
          sampleRevision: 'b',
          samples: [{ depth: 1000, value: 2 }],
        };
      },
    });

    const first = integration.load(wellA);
    controller.resolveLoad(wellA);
    await Promise.resolve();

    const second = integration.load(wellB);
    controller.resolveLoad(wellB);
    await second;

    resolveSampleA({
      contractVersion: 'wdv_curve_samples_v2_1',
      managedWellUid: wellA,
      managedCurveUid: curveA,
      sampleRevision: 'a',
      samples: [{ depth: 1000, value: 1 }],
    });
    await first;

    expect(integration.getState().managedWellUid).toBe(wellB);
    expect(
      integration.getState().presentation?.wellHeader.wellName,
    ).toBe('Well B');
    expect(
      integration.getState().samplesByManagedCurveUid.get(curveA),
    ).toEqual([{ depth: 1000, value: 2 }]);
  });

  it('retains the last valid presentation after a mutation failure', async () => {
    const controller = new FakeController();
    controller.execute = async () => {
      throw new Error('command rejected');
    };

    const integration = new ActiveCanonicalWdvIntegration({
      controller: controller as never,
      maxSamplesPerCurve: 500,
      loadSamples: async (request) => ({
        contractVersion: 'wdv_curve_samples_v2_1',
        managedWellUid: request.managedWellUid,
        managedCurveUid: request.managedCurveUid,
        sampleRevision: null,
        samples: [],
      }),
    });

    const pending = integration.load(wellA);
    controller.resolveLoad(wellA);
    await pending;

    const before = integration.getState().presentation;
    await expect(
      integration.execute({
        kind: 'create_track',
        body: { track_name: 'Track 1' },
      }),
    ).rejects.toThrow('command rejected');

    expect(integration.getState().presentation).toBe(before);
    expect(integration.getState().status).toBe('ready');
    expect(integration.getState().error).toBe('command rejected');
  });

  it('delegates template application and refreshes the presentation revision', async () => {
    const controller = new FakeController();
    const integration = new ActiveCanonicalWdvIntegration({
      controller: controller as never,
      maxSamplesPerCurve: 500,
      loadSamples: async (request) => ({
        contractVersion: 'wdv_curve_samples_v2_1',
        managedWellUid: request.managedWellUid,
        managedCurveUid: request.managedCurveUid,
        sampleRevision: null,
        samples: [],
      }),
    });

    const pending = integration.load(wellA);
    controller.resolveLoad(wellA);
    await pending;

    await integration.applyTemplate({
      templateKey: 'triple_combo',
    });

    expect(integration.getState().presentation?.revision).toBe(1);
  });
});
