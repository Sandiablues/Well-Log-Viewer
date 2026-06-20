import type {
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalViewerSessionV21,
} from '../prototype/canonicalViewerPackageV21';
import type {
  ManagedCurveSamplesByUidV21,
} from '../prototype/managedCurveSamplesV21';
import type {
  CanonicalWorkspaceCommandIntent,
} from './canonicalWorkspaceApi';
import {
  applyCanonicalWorkspaceTemplate,
  executeCanonicalWorkspaceCommand,
} from './canonicalWorkspaceApi';
import {
  createCanonicalCommandId,
} from './canonicalCommandId';
import type {
  CanonicalWorkspaceV1,
} from './canonicalWorkspaceV1';
import {
  loadCanonicalWorkspaceV1,
} from './canonicalWorkspaceV1';

export type CanonicalWorkspaceControllerStatus =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'mutating'
  | 'error';

export interface CanonicalWorkspaceControllerState {
  status: CanonicalWorkspaceControllerStatus;
  managedWellUid: ManagedWellUid | null;
  workspace: CanonicalWorkspaceV1 | null;
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21;
  error: string | null;
}

export interface CanonicalWorkspaceControllerDependencies {
  loadWorkspace: typeof loadCanonicalWorkspaceV1;
  executeCommand: typeof executeCanonicalWorkspaceCommand;
  applyTemplate: typeof applyCanonicalWorkspaceTemplate;
  createCommandId: typeof createCanonicalCommandId;
}

function defaultDependencies(): CanonicalWorkspaceControllerDependencies {
  return {
    loadWorkspace: loadCanonicalWorkspaceV1,
    executeCommand: executeCanonicalWorkspaceCommand,
    applyTemplate: applyCanonicalWorkspaceTemplate,
    createCommandId: createCanonicalCommandId,
  };
}

function emptyState(): CanonicalWorkspaceControllerState {
  return {
    status: 'idle',
    managedWellUid: null,
    workspace: null,
    samplesByManagedCurveUid: new Map(),
    error: null,
  };
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export class CanonicalWorkspaceControllerV2 {
  private state: CanonicalWorkspaceControllerState = emptyState();
  private readonly listeners =
    new Set<(state: CanonicalWorkspaceControllerState) => void>();
  private readonly dependencies: CanonicalWorkspaceControllerDependencies;
  private loadGeneration = 0;
  private mutationChain: Promise<void> = Promise.resolve();

  constructor(
    dependencies: CanonicalWorkspaceControllerDependencies =
      defaultDependencies(),
  ) {
    this.dependencies = dependencies;
  }

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
    this.loadGeneration += 1;
    this.mutationChain = Promise.resolve();
    this.publish(emptyState());
  }

  async load(
    managedWellUid: ManagedWellUid,
  ): Promise<CanonicalWorkspaceControllerState> {
    const generation = ++this.loadGeneration;
    this.publish({
      ...emptyState(),
      status: 'loading',
      managedWellUid,
    });

    try {
      const workspace =
        await this.dependencies.loadWorkspace(managedWellUid);
      if (generation !== this.loadGeneration) return this.state;

      this.publish({
        status: 'ready',
        managedWellUid,
        workspace,
        samplesByManagedCurveUid: new Map(),
        error: null,
      });
      return this.state;
    } catch (error) {
      if (generation !== this.loadGeneration) return this.state;
      this.publish({
        ...emptyState(),
        status: 'error',
        managedWellUid,
        error: messageFrom(error),
      });
      return this.state;
    }
  }

  execute(
    intent: CanonicalWorkspaceCommandIntent,
  ): Promise<CanonicalWorkspaceControllerState> {
    return this.enqueueMutation(async (current) => {
      const commandId = this.dependencies.createCommandId();
      return this.dependencies.executeCommand(
        current.managedWellUid,
        current.workspace.session.revision,
        commandId,
        intent,
        current.workspace.curves,
      );
    });
  }

  applyTemplate(
    input: {
      templateKey: string;
      workflowContext?: string | null;
    },
  ): Promise<CanonicalWorkspaceControllerState> {
    return this.enqueueMutation(async (current) => {
      const commandId = this.dependencies.createCommandId();
      return this.dependencies.applyTemplate(
        current.managedWellUid,
        current.workspace.session.revision,
        commandId,
        input,
        current.workspace.curves,
      );
    });
  }

  private enqueueMutation(
    operation: (
      current: {
        managedWellUid: ManagedWellUid;
        workspace: CanonicalWorkspaceV1;
      },
    ) => Promise<CanonicalViewerSessionV21>,
  ): Promise<CanonicalWorkspaceControllerState> {
    let resolveResult:
      (state: CanonicalWorkspaceControllerState) => void = () => undefined;
    let rejectResult: (error: unknown) => void = () => undefined;

    const result = new Promise<CanonicalWorkspaceControllerState>(
      (resolve, reject) => {
        resolveResult = resolve;
        rejectResult = reject;
      },
    );

    this.mutationChain = this.mutationChain
      .catch(() => undefined)
      .then(async () => {
        const current = this.requireReady();
        const generation = this.loadGeneration;
        const lastValid = current.workspace;

        this.publish({
          ...this.state,
          status: 'mutating',
          error: null,
        });

        try {
          const session = await operation(current);
          if (generation !== this.loadGeneration) {
            resolveResult(this.state);
            return;
          }

          const workspace: CanonicalWorkspaceV1 = {
            ...lastValid,
            session,
            viewerPackage: {
              ...lastValid.viewerPackage,
              session,
            },
          };

          this.publish({
            ...this.state,
            status: 'ready',
            workspace,
            error: null,
          });
          resolveResult(this.state);
        } catch (error) {
          if (generation === this.loadGeneration) {
            this.publish({
              ...this.state,
              status: 'ready',
              workspace: lastValid,
              error: messageFrom(error),
            });
          }
          rejectResult(error);
        }
      });

    return result;
  }

  private requireReady(): {
    managedWellUid: ManagedWellUid;
    workspace: CanonicalWorkspaceV1;
  } {
    if (
      (this.state.status !== 'ready' && this.state.status !== 'mutating')
      || this.state.managedWellUid === null
      || this.state.workspace === null
    ) {
      throw new Error('Canonical WDV workspace is not ready');
    }

    return {
      managedWellUid: this.state.managedWellUid,
      workspace: this.state.workspace,
    };
  }

  private publish(state: CanonicalWorkspaceControllerState): void {
    this.state = state;
    for (const listener of this.listeners) listener(state);
  }
}
