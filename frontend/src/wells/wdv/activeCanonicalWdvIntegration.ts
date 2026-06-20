import type {
  ManagedCurveUid,
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import type {
  ManagedCurveSampleResponseV21,
  ManagedCurveSamplesByUidV21,
} from '../prototype/managedCurveSamplesV21';
import {
  indexManagedCurveSamplesV21,
} from '../prototype/managedCurveSamplesV21';
import type {
  CanonicalWorkspaceCommandIntent,
} from './canonicalWorkspaceApi';
import type {
  CanonicalWorkspaceControllerState,
} from './CanonicalWorkspaceControllerV2';
import {
  CanonicalWorkspaceControllerV2,
} from './CanonicalWorkspaceControllerV2';
import type {
  CanonicalWdvSelection,
} from './canonicalSelection';
import {
  loadCanonicalManagedCurveSamples,
} from './canonicalSampleApi';
import type {
  OriginalWdvPresentationModel,
} from './originalWdvPresentationAdapter';
import {
  buildOriginalWdvPresentationModel,
} from './originalWdvPresentationAdapter';

export type ActiveCanonicalWdvStatus =
  | 'idle'
  | 'loading'
  | 'loading_samples'
  | 'ready'
  | 'mutating'
  | 'empty'
  | 'error';

export interface ActiveCanonicalWdvIssue {
  code:
    | 'workspace_error'
    | 'sample_error'
    | 'presentation_issue';
  message: string;
  managedCurveUid?: ManagedCurveUid;
}

export interface ActiveCanonicalWdvState {
  status: ActiveCanonicalWdvStatus;
  managedWellUid: ManagedWellUid | null;
  presentation: OriginalWdvPresentationModel | null;
  controllerState: CanonicalWorkspaceControllerState;
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21;
  issues: readonly ActiveCanonicalWdvIssue[];
  error: string | null;
}

export interface ActiveCanonicalWdvDependencies {
  controller: CanonicalWorkspaceControllerV2;
  loadSamples: typeof loadCanonicalManagedCurveSamples;
  maxSamplesPerCurve: number;
}

function defaultDependencies(): ActiveCanonicalWdvDependencies {
  return {
    controller: new CanonicalWorkspaceControllerV2(),
    loadSamples: loadCanonicalManagedCurveSamples,
    maxSamplesPerCurve: 6000,
  };
}

function emptyState(
  controllerState: CanonicalWorkspaceControllerState,
): ActiveCanonicalWdvState {
  return {
    status: 'idle',
    managedWellUid: null,
    presentation: null,
    controllerState,
    samplesByManagedCurveUid: new Map(),
    issues: [],
    error: null,
  };
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export class ActiveCanonicalWdvIntegration {
  private readonly dependencies: ActiveCanonicalWdvDependencies;
  private readonly listeners =
    new Set<(state: ActiveCanonicalWdvState) => void>();
  private readonly unsubscribeController: () => void;
  private generation = 0;
  private requestedSelection: CanonicalWdvSelection | undefined;
  private state: ActiveCanonicalWdvState;

  constructor(
    dependencies: ActiveCanonicalWdvDependencies = defaultDependencies(),
  ) {
    this.dependencies = dependencies;
    this.state = emptyState(dependencies.controller.getState());
    this.unsubscribeController = dependencies.controller.subscribe(
      (controllerState) => this.onControllerState(controllerState),
    );
  }

  getState(): ActiveCanonicalWdvState {
    return this.state;
  }

  subscribe(
    listener: (state: ActiveCanonicalWdvState) => void,
  ): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  dispose(): void {
    this.generation += 1;
    this.unsubscribeController();
    this.listeners.clear();
  }

  clear(): void {
    this.generation += 1;
    this.requestedSelection = undefined;
    this.dependencies.controller.clear();
    this.publish(
      emptyState(this.dependencies.controller.getState()),
    );
  }

  async load(
    managedWellUid: ManagedWellUid,
  ): Promise<ActiveCanonicalWdvState> {
    const generation = ++this.generation;
    this.requestedSelection = undefined;
    this.publish({
      ...emptyState(this.dependencies.controller.getState()),
      status: 'loading',
      managedWellUid,
    });

    const controllerState =
      await this.dependencies.controller.load(managedWellUid);

    if (generation !== this.generation) return this.state;
    if (
      controllerState.managedWellUid !== managedWellUid
      || controllerState.workspace === null
    ) {
      const error =
        controllerState.error ?? 'Canonical WDV workspace failed to load';
      this.publish({
        ...this.state,
        status: 'error',
        managedWellUid,
        controllerState,
        error,
        issues: [{
          code: 'workspace_error',
          message: error,
        }],
      });
      return this.state;
    }

    this.publishFromController(
      controllerState,
      new Map(),
      'loading_samples',
      [],
    );

    const responses = await Promise.all(
      controllerState.workspace.curves.map(async (curve) => {
        try {
          const response = await this.dependencies.loadSamples({
            managedWellUid,
            managedCurveUid: curve.managedCurveUid,
            sampleRevision: null,
            maxSamples: this.dependencies.maxSamplesPerCurve,
          });
          return {
            ok: true as const,
            response,
          };
        } catch (error) {
          return {
            ok: false as const,
            managedCurveUid: curve.managedCurveUid,
            error,
          };
        }
      }),
    );

    if (generation !== this.generation) return this.state;
    if (
      this.dependencies.controller.getState().managedWellUid
      !== managedWellUid
    ) {
      return this.state;
    }

    const successful: ManagedCurveSampleResponseV21[] = [];
    const issues: ActiveCanonicalWdvIssue[] = [];

    for (const result of responses) {
      if (result.ok) {
        successful.push(result.response);
      } else {
        issues.push({
          code: 'sample_error',
          managedCurveUid: result.managedCurveUid,
          message: messageFrom(result.error),
        });
      }
    }

    const samples = indexManagedCurveSamplesV21(successful);
    this.publishFromController(
      this.dependencies.controller.getState(),
      samples,
      undefined,
      issues,
    );
    return this.state;
  }

  execute(
    intent: CanonicalWorkspaceCommandIntent,
  ): Promise<ActiveCanonicalWdvState> {
    return this.executeMutation(
      () => this.dependencies.controller.execute(intent),
    );
  }

  applyTemplate(
    input: {
      templateKey: string;
      workflowContext?: string | null;
    },
  ): Promise<ActiveCanonicalWdvState> {
    return this.executeMutation(
      () => this.dependencies.controller.applyTemplate(input),
    );
  }

  setPresentationSelection(
    selection: CanonicalWdvSelection | undefined,
  ): void {
    this.requestedSelection = selection;
    this.publishFromController(
      this.dependencies.controller.getState(),
      this.state.samplesByManagedCurveUid,
      undefined,
      this.state.issues.filter(
        (issue) => issue.code !== 'presentation_issue',
      ),
    );
  }

  private async executeMutation(
    operation: () => Promise<CanonicalWorkspaceControllerState>,
  ): Promise<ActiveCanonicalWdvState> {
    const generation = this.generation;
    const wellUid = this.state.managedWellUid;
    const lastPresentation = this.state.presentation;

    if (wellUid === null || lastPresentation === null) {
      throw new Error('Canonical WDV integration is not ready');
    }

    this.publish({
      ...this.state,
      status: 'mutating',
      error: null,
    });

    try {
      const controllerState = await operation();
      if (
        generation !== this.generation
        || controllerState.managedWellUid !== wellUid
      ) {
        return this.state;
      }

      this.publishFromController(
        controllerState,
        this.state.samplesByManagedCurveUid,
        undefined,
        this.state.issues.filter(
          (issue) => issue.code !== 'workspace_error',
        ),
      );
      return this.state;
    } catch (error) {
      if (
        generation === this.generation
        && this.state.managedWellUid === wellUid
      ) {
        this.publish({
          ...this.state,
          status: 'ready',
          presentation: lastPresentation,
          error: messageFrom(error),
          issues: [
            ...this.state.issues.filter(
              (issue) => issue.code !== 'workspace_error',
            ),
            {
              code: 'workspace_error',
              message: messageFrom(error),
            },
          ],
        });
      }
      throw error;
    }
  }

  private onControllerState(
    controllerState: CanonicalWorkspaceControllerState,
  ): void {
    if (
      controllerState.managedWellUid !== null
      && this.state.managedWellUid !== null
      && controllerState.managedWellUid !== this.state.managedWellUid
    ) {
      return;
    }

    if (
      controllerState.status === 'mutating'
      && this.state.presentation !== null
    ) {
      this.publish({
        ...this.state,
        status: 'mutating',
        controllerState,
        error: null,
      });
    }
  }

  private publishFromController(
    controllerState: CanonicalWorkspaceControllerState,
    samples: ManagedCurveSamplesByUidV21,
    forcedStatus?: ActiveCanonicalWdvStatus,
    baseIssues: readonly ActiveCanonicalWdvIssue[] = [],
  ): void {
    const workspace = controllerState.workspace;
    if (workspace === null) {
      const error =
        controllerState.error ?? 'Canonical WDV workspace is unavailable';
      this.publish({
        ...this.state,
        status: 'error',
        managedWellUid: controllerState.managedWellUid,
        controllerState,
        samplesByManagedCurveUid: samples,
        error,
        issues: [{
          code: 'workspace_error',
          message: error,
        }],
      });
      return;
    }

    const presentation = buildOriginalWdvPresentationModel(
      workspace,
      samples,
      this.requestedSelection,
    );
    const presentationIssues: ActiveCanonicalWdvIssue[] =
      presentation.issues.map((issue) => ({
        code: 'presentation_issue',
        message: issue.message,
        managedCurveUid:
          issue.managedCurveUid as ManagedCurveUid | undefined,
      }));

    const status =
      forcedStatus
      ?? (presentation.tracks.length === 0 ? 'empty' : 'ready');

    this.publish({
      status,
      managedWellUid: workspace.managedWellUid,
      presentation,
      controllerState,
      samplesByManagedCurveUid: samples,
      issues: [...baseIssues, ...presentationIssues],
      error: controllerState.error,
    });
  }

  private publish(state: ActiveCanonicalWdvState): void {
    this.state = state;
    for (const listener of this.listeners) listener(state);
  }
}
