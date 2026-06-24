import { describe, expect, it } from 'vitest';
import type { ManagedWellUid } from '../../identity/wdvIdentityV21';
import { CanonicalWorkspaceControllerV2 } from '../CanonicalWorkspaceControllerV2';
import type { CanonicalWorkspaceV1 } from '../canonicalWorkspaceV1';

const wellUid =
  '01901901-9000-7000-8000-000000000001' as ManagedWellUid;

function workspace(revision = 0): CanonicalWorkspaceV1 {
  return {
    contractVersion: 'wdv_workspace_v1',
    managedWellUid: wellUid,
    curves: [],
    session: {
      contractVersion: 'wdv_session_layout_state_v2_1',
      sessionUid: '01901901-9000-7000-8000-000000000002' as never,
      managedWellUid: wellUid,
      revision,
      stateStatus: 'empty',
      selectedTrackUid: null,
      tracks: [],
      warnings: [],
      updatedAt: '2026-06-19T00:00:00+00:00',
    },
    viewerPackage: {
      contractVersion: 'wdv_viewer_package_v2_2',
      managedWellUid: wellUid,
      managedWellboreUid: null,
      wellName: 'Well A',
      wellboreName: null,
      depthRange: { minimum: null, maximum: null, unit: 'ft' },
      curves: [],
      session: undefined as never,
      warnings: [],
    },
    warnings: [],
  } as CanonicalWorkspaceV1;
}

describe('CanonicalWorkspaceControllerV2', () => {
  it('serializes commands and advances revisions from backend results', async () => {
    const seen: number[] = [];
    const controller = new CanonicalWorkspaceControllerV2({
      loadWorkspace: async () => workspace(0),
      createCommandId: () =>
        '01901901-9000-7000-8000-000000000010' as never,
      executeCommand: async (_well, revision) => {
        seen.push(revision);
        await Promise.resolve();
        return { ...workspace(revision + 1).session };
      },
      applyTemplate: async () => workspace(1).session,
    });

    await controller.load(wellUid);
    const first = controller.execute({ kind: 'create_track', body: {} });
    const second = controller.execute({ kind: 'create_track', body: {} });
    await Promise.all([first, second]);

    expect(seen).toEqual([0, 1]);
    expect(controller.getState().workspace?.session.revision).toBe(2);
  });

  it('preserves the last valid workspace when a mutation fails', async () => {
    const controller = new CanonicalWorkspaceControllerV2({
      loadWorkspace: async () => workspace(4),
      createCommandId: () =>
        '01901901-9000-7000-8000-000000000010' as never,
      executeCommand: async () => {
        throw new Error('rejected');
      },
      applyTemplate: async () => workspace(5).session,
    });

    await controller.load(wellUid);
    await expect(
      controller.execute({ kind: 'create_track', body: {} }),
    ).rejects.toThrow('rejected');

    expect(controller.getState().workspace?.session.revision).toBe(4);
    expect(controller.getState().status).toBe('ready');
    expect(controller.getState().error).toBe('rejected');
  });
});
