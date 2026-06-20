import { fetchWlvApi } from '../api/wlvApiClient';
import type {
  ManagedCurveUid,
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalViewerPackageV21,
  CanonicalViewerSessionV21,
} from './canonicalViewerPackageV21';
import {
  applyCanonicalTemplateV21,
  executeCanonicalSessionCommandV21,
  loadCanonicalViewerPackageV21,
} from './canonicalViewerPackageV21';
import type {
  CanonicalSessionCommandV21,
} from './canonicalViewerPackageV21';
import type {
  ManagedCurveSampleV21,
  ManagedCurveSamplesByUidV21,
} from './managedCurveSamplesV21';
import {
  loadManagedCurveSamplesV21,
} from './managedCurveSamplesV21';

export type CanonicalWdvWorkspaceStatus =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'error';

export interface CanonicalWdvWorkspaceState {
  status: CanonicalWdvWorkspaceStatus;
  managedWellUid: ManagedWellUid | null;
  viewerPackage: CanonicalViewerPackageV21 | null;
  session: CanonicalViewerSessionV21 | null;
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21;
  sampleErrorsByManagedCurveUid: ReadonlyMap<ManagedCurveUid, string>;
  error: string | null;
}

export type CanonicalWdvWorkspaceListener = (
  state: CanonicalWdvWorkspaceState,
) => void;

export interface CanonicalWdvWorkspaceDependencies {
  loadViewerPackage: (
    managedWellUid: ManagedWellUid,
  ) => Promise<CanonicalViewerPackageV21>;
  executeCommand: (
    managedWellUid: ManagedWellUid,
    command: CanonicalSessionCommandV21,
    curves: CanonicalViewerPackageV21['curves'],
  ) => Promise<CanonicalViewerSessionV21>;
  applyTemplate?: (
    managedWellUid: ManagedWellUid,
    input: {
      expectedRevision: number;
      templateKey: string;
      workflowContext?: string | null;
    },
    curves: CanonicalViewerPackageV21['curves'],
  ) => Promise<CanonicalViewerSessionV21>;
  loadSamples: (
    managedWellUid: ManagedWellUid,
    managedCurveUid: ManagedCurveUid,
    maxSamples: number,
  ) => Promise<readonly ManagedCurveSampleV21[]>;
}

function defaultDependencies(): CanonicalWdvWorkspaceDependencies {
  return {
    loadViewerPackage: (managedWellUid) =>
      loadCanonicalViewerPackageV21(managedWellUid),
    executeCommand: (managedWellUid, command, curves) =>
      executeCanonicalSessionCommandV21(
        managedWellUid,
        command,
        curves,
      ),
    applyTemplate: (managedWellUid, input, curves) =>
      applyCanonicalTemplateV21(
        managedWellUid,
        input,
        curves,
      ),
    loadSamples: async (
      managedWellUid,
      managedCurveUid,
      maxSamples,
    ) => {
      const response = await loadManagedCurveSamplesV21(
        {
          managedWellUid,
          managedCurveUid,
          sampleRevision: null,
          maxSamples,
        },
        async (url, init) => {
          const result = await fetchWlvApi(url, init);
          const payload = await result.json().catch(() => null);
          if (!result.ok) {
            const detail =
              payload
              && typeof payload === 'object'
              && !Array.isArray(payload)
              && typeof (payload as Record<string, unknown>).detail === 'string'
                ? String((payload as Record<string, unknown>).detail)
                : `Canonical sample request failed (${result.status})`;
            throw new Error(detail);
          }
          return payload;
        },
      );
      return response.samples;
    },
  };
}

function emptyState(): CanonicalWdvWorkspaceState {
  return {
    status: 'idle',
    managedWellUid: null,
    viewerPackage: null,
    session: null,
    samplesByManagedCurveUid: new Map(),
    sampleErrorsByManagedCurveUid: new Map(),
    error: null,
  };
}

function assignedCurveUids(
  session: CanonicalViewerSessionV21,
): ManagedCurveUid[] {
  const ordered: ManagedCurveUid[] = [];
  const seen = new Set<ManagedCurveUid>();

  for (const track of session.tracks) {
    if (track.trackType !== 'curve') continue;
    for (const assignment of track.curves) {
      if (!assignment.visible || seen.has(assignment.managedCurveUid)) {
        continue;
      }
      seen.add(assignment.managedCurveUid);
      ordered.push(assignment.managedCurveUid);
    }
  }

  return ordered;
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export class CanonicalWdvWorkspaceController {
  private state: CanonicalWdvWorkspaceState = emptyState();
  private readonly listeners = new Set<CanonicalWdvWorkspaceListener>();
  private readonly dependencies: CanonicalWdvWorkspaceDependencies;
  private loadGeneration = 0;

  constructor(
    dependencies: CanonicalWdvWorkspaceDependencies = defaultDependencies(),
  ) {
    this.dependencies = dependencies;
  }

  getState(): CanonicalWdvWorkspaceState {
    return this.state;
  }

  subscribe(listener: CanonicalWdvWorkspaceListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => {
      this.listeners.delete(listener);
    };
  }

  clear(): void {
    this.loadGeneration += 1;
    this.publish(emptyState());
  }

  async load(
    managedWellUid: ManagedWellUid,
    maxSamples = 4000,
  ): Promise<CanonicalWdvWorkspaceState> {
    const generation = ++this.loadGeneration;
    this.publish({
      ...emptyState(),
      status: 'loading',
      managedWellUid,
    });

    try {
      const viewerPackage =
        await this.dependencies.loadViewerPackage(managedWellUid);
      if (generation !== this.loadGeneration) {
        return this.state;
      }

      const session = viewerPackage.session;
      this.publish({
        status: 'ready',
        managedWellUid,
        viewerPackage,
        session,
        samplesByManagedCurveUid: new Map(),
        sampleErrorsByManagedCurveUid: new Map(),
        error: null,
      });

      await this.hydrateAssignedSamples(generation, maxSamples);
      return this.state;
    } catch (error) {
      if (generation !== this.loadGeneration) {
        return this.state;
      }
      this.publish({
        ...emptyState(),
        status: 'error',
        managedWellUid,
        error: messageFrom(error),
      });
      return this.state;
    }
  }

  async execute(
    command: CanonicalSessionCommandV21,
    maxSamples = 4000,
  ): Promise<CanonicalWdvWorkspaceState> {
    const current = this.requireReadyState();
    const generation = this.loadGeneration;
    try {
      const session = await this.dependencies.executeCommand(
        current.managedWellUid,
        command,
        current.viewerPackage.curves,
      );
      if (generation !== this.loadGeneration) {
        return this.state;
      }

      this.acceptBackendSession(current, session);

      await this.hydrateAssignedSamples(generation, maxSamples);
      return this.state;
    } catch (error) {
      if (generation !== this.loadGeneration) {
        return this.state;
      }
      this.publish({
        ...current,
        error: messageFrom(error),
      });
      throw error;
    }
  }

  async applyTemplate(
    input: {
      templateKey: string;
      workflowContext?: string | null;
    },
    maxSamples = 4000,
  ): Promise<CanonicalWdvWorkspaceState> {
    const current = this.requireReadyState();
    const generation = this.loadGeneration;
    const applyTemplate = this.dependencies.applyTemplate
      ?? ((managedWellUid, request, curves) =>
        applyCanonicalTemplateV21(managedWellUid, request, curves));

    try {
      const session = await applyTemplate(
        current.managedWellUid,
        {
          expectedRevision: current.session.revision,
          templateKey: input.templateKey,
          workflowContext: input.workflowContext ?? null,
        },
        current.viewerPackage.curves,
      );
      if (generation !== this.loadGeneration) {
        return this.state;
      }
      this.acceptBackendSession(current, session);
      await this.hydrateAssignedSamples(generation, maxSamples);
      return this.state;
    } catch (error) {
      if (generation !== this.loadGeneration) {
        return this.state;
      }
      this.publish({
        ...current,
        error: messageFrom(error),
      });
      throw error;
    }
  }

  private requireReadyState(): CanonicalWdvWorkspaceState & {
    managedWellUid: ManagedWellUid;
    viewerPackage: CanonicalViewerPackageV21;
    session: CanonicalViewerSessionV21;
  } {
    const current = this.state;
    if (
      current.status !== 'ready'
      || current.managedWellUid === null
      || current.viewerPackage === null
      || current.session === null
    ) {
      throw new Error('Canonical WDV workspace is not ready');
    }
    return current as CanonicalWdvWorkspaceState & {
      managedWellUid: ManagedWellUid;
      viewerPackage: CanonicalViewerPackageV21;
      session: CanonicalViewerSessionV21;
    };
  }

  private acceptBackendSession(
    current: CanonicalWdvWorkspaceState & {
      viewerPackage: CanonicalViewerPackageV21;
    },
    session: CanonicalViewerSessionV21,
  ): void {
    this.publish({
      ...current,
      session,
      viewerPackage: {
        ...current.viewerPackage,
        session,
      },
      error: null,
    });
  }

  private async hydrateAssignedSamples(
    generation: number,
    maxSamples: number,
  ): Promise<void> {
    const current = this.state;
    if (
      current.status !== 'ready'
      || current.managedWellUid === null
      || current.session === null
    ) {
      return;
    }

    const required = assignedCurveUids(current.session);
    const retainedSamples = new Map(current.samplesByManagedCurveUid);
    const retainedErrors = new Map(current.sampleErrorsByManagedCurveUid);

    for (const managedCurveUid of [...retainedSamples.keys()]) {
      if (!required.includes(managedCurveUid)) {
        retainedSamples.delete(managedCurveUid);
      }
    }
    for (const managedCurveUid of [...retainedErrors.keys()]) {
      if (!required.includes(managedCurveUid)) {
        retainedErrors.delete(managedCurveUid);
      }
    }

    this.publish({
      ...current,
      samplesByManagedCurveUid: retainedSamples,
      sampleErrorsByManagedCurveUid: retainedErrors,
    });

    const missing = required.filter(
      (managedCurveUid) => !retainedSamples.has(managedCurveUid),
    );

    await Promise.all(
      missing.map(async (managedCurveUid) => {
        try {
          const samples = await this.dependencies.loadSamples(
            current.managedWellUid as ManagedWellUid,
            managedCurveUid,
            maxSamples,
          );
          if (generation !== this.loadGeneration) return;

          const nextSamples = new Map(this.state.samplesByManagedCurveUid);
          const nextErrors = new Map(
            this.state.sampleErrorsByManagedCurveUid,
          );
          nextSamples.set(managedCurveUid, samples);
          nextErrors.delete(managedCurveUid);
          this.publish({
            ...this.state,
            samplesByManagedCurveUid: nextSamples,
            sampleErrorsByManagedCurveUid: nextErrors,
          });
        } catch (error) {
          if (generation !== this.loadGeneration) return;

          const nextErrors = new Map(
            this.state.sampleErrorsByManagedCurveUid,
          );
          nextErrors.set(managedCurveUid, messageFrom(error));
          this.publish({
            ...this.state,
            sampleErrorsByManagedCurveUid: nextErrors,
          });
        }
      }),
    );
  }

  private publish(state: CanonicalWdvWorkspaceState): void {
    this.state = state;
    for (const listener of this.listeners) {
      listener(state);
    }
  }
}
