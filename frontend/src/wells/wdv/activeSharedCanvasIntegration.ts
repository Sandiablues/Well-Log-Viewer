/**
 * Active shared canvas integration.
 *
 * Parallel to ActiveCanonicalWdvIntegration; uses the shared canvas path
 * instead of the per-well canonical workspace path.
 *
 * Key guarantees:
 *   - Generation counter: every load() call increments the generation.
 *     Responses from a prior generation are silently discarded — stale
 *     out-of-order network responses never update state.
 *   - Atomic clear on well switch: load() immediately publishes an idle
 *     state before any network call, clearing all prior-well curve UIDs.
 *   - Sample loading: only curves with binding_status === 'bound' are
 *     loaded; no other curves are fetched.
 *   - No localStorage: canvas state is never persisted across sessions.
 *   - No canonical workspace mutation: this integration is read-only.
 *
 * Returns the same ActiveCanonicalWdvState type as ActiveCanonicalWdvIntegration
 * so the WDV UI can swap between the two paths at a feature boundary.
 */

import type {
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
  ActiveCanonicalWdvIssue,
  ActiveCanonicalWdvState,
  ActiveCanonicalWdvStatus,
} from './activeCanonicalWdvIntegration';
import type {
  CanonicalWorkspaceControllerState,
} from './CanonicalWorkspaceControllerV2';
import {
  loadCanonicalManagedCurveSamples,
} from './canonicalSampleApi';
import {
  buildSharedCanvasPresentationModel,
  extractBoundCurveUids,
} from './sharedCanvasPresentationAdapter';
import {
  loadSharedCanvasSession,
} from './sharedCanvasApi';
import type {
  ResolvedWdvCanvasSession,
} from './sharedCanvasApiTypes';


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function emptyControllerState(
  managedWellUid: ManagedWellUid | null = null,
  status: CanonicalWorkspaceControllerState['status'] = 'idle',
): CanonicalWorkspaceControllerState {
  return {
    status,
    managedWellUid,
    workspace: null,
    samplesByManagedCurveUid: new Map(),
    error: null,
  };
}

function idleState(): ActiveCanonicalWdvState {
  return {
    status: 'idle',
    managedWellUid: null,
    presentation: null,
    controllerState: emptyControllerState(),
    samplesByManagedCurveUid: new Map(),
    issues: [],
    error: null,
  };
}


// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface ActiveSharedCanvasScope {
  /** Activation scope type, e.g. 'local_workspace'. */
  scopeType: string;
  /** Activation scope UID, e.g. the desktop workspace UID. */
  scopeUid: string;
}

export interface ActiveSharedCanvasDependencies {
  loadSession: typeof loadSharedCanvasSession;
  loadSamples: typeof loadCanonicalManagedCurveSamples;
  maxSamplesPerCurve: number;
}

function defaultDependencies(): ActiveSharedCanvasDependencies {
  return {
    loadSession: loadSharedCanvasSession,
    loadSamples: loadCanonicalManagedCurveSamples,
    maxSamplesPerCurve: 6000,
  };
}


// ---------------------------------------------------------------------------
// Integration class
// ---------------------------------------------------------------------------

export class ActiveSharedCanvasIntegration {
  private readonly scope: ActiveSharedCanvasScope;
  private readonly dependencies: ActiveSharedCanvasDependencies;
  private readonly listeners =
    new Set<(state: ActiveCanonicalWdvState) => void>();
  private generation = 0;
  private state: ActiveCanonicalWdvState;

  constructor(
    scope: ActiveSharedCanvasScope,
    dependencies: ActiveSharedCanvasDependencies = defaultDependencies(),
  ) {
    this.scope = scope;
    this.dependencies = dependencies;
    this.state = idleState();
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
    this.listeners.clear();
  }

  /**
   * Clear state and cancel any in-flight load.
   * Atomically wipes all prior-well curve UIDs from state.
   */
  clear(): void {
    this.generation += 1;
    this.publish(idleState());
  }

  /**
   * Load the active shared canvas session for a well, then load samples
   * for all BOUND curves.
   *
   * A new generation is started atomically before the first network call;
   * any response from a prior generation is discarded without updating state.
   */
  async load(
    managedWellUid: ManagedWellUid,
  ): Promise<ActiveCanonicalWdvState> {
    const generation = ++this.generation;

    // Step 1: publish loading state immediately — atomically clears
    // any prior-well curve UIDs from state before the first await.
    this.publish({
      ...idleState(),
      status: 'loading',
      managedWellUid,
      controllerState: emptyControllerState(managedWellUid, 'loading'),
    });

    // Step 2: fetch the resolved canvas session.
    let session: ResolvedWdvCanvasSession;
    try {
      session = await this.dependencies.loadSession({
        managedWellUid,
        scopeType: this.scope.scopeType,
        scopeUid: this.scope.scopeUid,
      });
    } catch (error) {
      if (generation !== this.generation) return this.state;
      const message = messageFrom(error);
      this.publish({
        ...idleState(),
        status: 'error',
        managedWellUid,
        controllerState: emptyControllerState(managedWellUid, 'error'),
        error: message,
        issues: [{ code: 'workspace_error', message }],
      });
      return this.state;
    }

    // Stale-response guard after first await.
    if (generation !== this.generation) return this.state;

    // Step 3: publish loading_samples with empty sample map.
    this.publish({
      ...idleState(),
      status: 'loading_samples',
      managedWellUid,
      controllerState: emptyControllerState(managedWellUid, 'loading'),
    });

    // Step 4: load samples for BOUND curves only.
    const boundCurveUids = extractBoundCurveUids(session);
    const responses = await Promise.all(
      boundCurveUids.map(async (managedCurveUid) => {
        try {
          const response = await this.dependencies.loadSamples({
            managedWellUid,
            managedCurveUid,
            sampleRevision: null,
            maxSamples: this.dependencies.maxSamplesPerCurve,
          });
          return { ok: true as const, response };
        } catch (error) {
          return {
            ok: false as const,
            managedCurveUid,
            error,
          };
        }
      }),
    );

    // Stale-response guard after second await.
    if (generation !== this.generation) return this.state;

    // Step 5: collect results.
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

    // Step 6: index samples and build presentation model.
    const samples: ManagedCurveSamplesByUidV21 =
      indexManagedCurveSamplesV21(successful);
    const presentation = buildSharedCanvasPresentationModel(session, samples);

    const status: ActiveCanonicalWdvStatus =
      presentation.tracks.length === 0 ? 'empty' : 'ready';

    this.publish({
      status,
      managedWellUid,
      presentation,
      controllerState: {
        ...emptyControllerState(managedWellUid, 'ready'),
        samplesByManagedCurveUid: samples,
      },
      samplesByManagedCurveUid: samples,
      issues,
      error: null,
    });

    return this.state;
  }

  private publish(state: ActiveCanonicalWdvState): void {
    this.state = state;
    for (const listener of this.listeners) listener(state);
  }
}
