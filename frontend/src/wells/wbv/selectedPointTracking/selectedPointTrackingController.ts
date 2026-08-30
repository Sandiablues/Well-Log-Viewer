export type TrackingScreenPoint = Readonly<{ x: number; y: number }>;

export type TrackingTrajectoryStation<TPoint> = Readonly<{
  point: TPoint;
  segmentOrder: number;
  sceneX: number;
  sceneY: number;
  sceneZ: number;
  screenX: number;
  screenY: number;
}>;

export type TrackingLocation<TPoint> = Readonly<{
  point: TPoint;
  segmentIndex: number;
  ratio: number;
  arcPosition: number;
  sceneX: number;
  sceneY: number;
  sceneZ: number;
  screenX: number;
  screenY: number;
  pointerDistancePx: number;
}>;

export type TrackingContinuityPolicy = Readonly<{
  localSegmentRadius: number;
  maximumArcAdvancePerObservation: number;
  continuityPenaltyPx: number;
  globalHitTolerancePx: number;
}>;

export const DEFAULT_TRACKING_CONTINUITY_POLICY: TrackingContinuityPolicy = Object.freeze({
  localSegmentRadius: 10,
  maximumArcAdvancePerObservation: 3,
  continuityPenaltyPx: 3,
  globalHitTolerancePx: 24,
});

export type TrackingControllerState =
  | 'idle'
  | 'starting'
  | 'tracking'
  | 'committing'
  | 'cancelling'
  | 'failed'
  | 'disposed';

export type TrackingControllerDiagnostic = Readonly<{
  kind:
    | 'state-transition'
    | 'segment-transition'
    | 'continuity-clamp'
    | 'observation-coalesced'
    | 'stale-response-discarded'
    | 'commit-completed'
    | 'cancel-completed'
    | 'failure';
  detail: Record<string, string | number | boolean | null>;
}>;

export type TrackingBackendState = Readonly<{
  active_tracking_session_id?: string | null;
  revision?: number;
}>;

export type TrackingBackendCommand<TObservation> =
  | Readonly<{ kind: 'track-start'; sequence: number; observation: TObservation }>
  | Readonly<{ kind: 'track-update'; sessionId: string; sequence: number; observation: TObservation }>
  | Readonly<{ kind: 'track-commit'; sessionId: string; sequence: number; observation: TObservation }>
  | Readonly<{ kind: 'track-cancel'; sessionId: string; sequence: number }>;

type SegmentHit = Readonly<{
  segmentIndex: number;
  ratio: number;
  arcPosition: number;
  screenX: number;
  screenY: number;
  distancePx: number;
  score: number;
}>;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

function interpolate(first: number, second: number, ratio: number): number {
  return first + (second - first) * ratio;
}

function nearestOnSegment(
  pointer: TrackingScreenPoint,
  first: TrackingScreenPoint,
  second: TrackingScreenPoint,
  segmentIndex: number,
  currentArcPosition: number | null,
  continuityPenaltyPx: number,
): SegmentHit {
  const dx = second.x - first.x;
  const dy = second.y - first.y;
  const lengthSquared = dx * dx + dy * dy;
  const ratio = lengthSquared <= Number.EPSILON
    ? 0
    : clamp(((pointer.x - first.x) * dx + (pointer.y - first.y) * dy) / lengthSquared, 0, 1);
  const screenX = first.x + dx * ratio;
  const screenY = first.y + dy * ratio;
  const distancePx = Math.hypot(pointer.x - screenX, pointer.y - screenY);
  const arcPosition = segmentIndex + ratio;
  const continuityDistance = currentArcPosition === null ? 0 : Math.abs(arcPosition - currentArcPosition);
  return {
    segmentIndex,
    ratio,
    arcPosition,
    screenX,
    screenY,
    distancePx,
    score: distancePx + continuityDistance * continuityPenaltyPx,
  };
}

class ContinuityTrackingEngine<TPoint> {
  readonly #stations: readonly TrackingTrajectoryStation<TPoint>[];
  readonly #policy: TrackingContinuityPolicy;
  readonly #interpolatePoint: (first: TPoint, second: TPoint, ratio: number) => TPoint;
  #current: TrackingLocation<TPoint> | null = null;

  constructor(
    stations: readonly TrackingTrajectoryStation<TPoint>[],
    interpolatePoint: (first: TPoint, second: TPoint, ratio: number) => TPoint,
    policy: TrackingContinuityPolicy,
  ) {
    if (stations.length < 2) throw new Error('At least two projected trajectory stations are required');
    this.#stations = stations;
    this.#interpolatePoint = interpolatePoint;
    this.#policy = policy;
  }

  get current(): TrackingLocation<TPoint> | null {
    return this.#current;
  }

  start(pointer: TrackingScreenPoint): TrackingLocation<TPoint> | null {
    const hit = this.#bestHit(pointer, 0, this.#stations.length - 2, null);
    if (!hit || hit.distancePx > this.#policy.globalHitTolerancePx) return null;
    this.#current = this.#locationFromHit(hit);
    return this.#current;
  }

  update(pointer: TrackingScreenPoint): { location: TrackingLocation<TPoint>; clamped: boolean } {
    if (!this.#current) throw new Error('Continuity tracking has not started');
    const previous = this.#current;
    const minimumSegment = Math.max(0, previous.segmentIndex - this.#policy.localSegmentRadius);
    const maximumSegment = Math.min(this.#stations.length - 2, previous.segmentIndex + this.#policy.localSegmentRadius);
    const candidate = this.#bestHit(pointer, minimumSegment, maximumSegment, previous.arcPosition);
    if (!candidate) throw new Error('No local trajectory candidate is available');

    const minimumArc = Math.max(0, previous.arcPosition - this.#policy.maximumArcAdvancePerObservation);
    const maximumArc = Math.min(this.#stations.length - 1, previous.arcPosition + this.#policy.maximumArcAdvancePerObservation);
    const governedArc = clamp(candidate.arcPosition, minimumArc, maximumArc);
    const clamped = Math.abs(governedArc - candidate.arcPosition) > 1e-9;
    const hit = clamped ? this.#hitAtArcPosition(governedArc, pointer) : candidate;
    this.#current = this.#locationFromHit(hit);
    return { location: this.#current, clamped };
  }

  #bestHit(
    pointer: TrackingScreenPoint,
    minimumSegment: number,
    maximumSegment: number,
    currentArcPosition: number | null,
  ): SegmentHit | null {
    let best: SegmentHit | null = null;
    for (let segmentIndex = minimumSegment; segmentIndex <= maximumSegment; segmentIndex += 1) {
      const first = this.#stations[segmentIndex];
      const second = this.#stations[segmentIndex + 1];
      const hit = nearestOnSegment(
        pointer,
        { x: first.screenX, y: first.screenY },
        { x: second.screenX, y: second.screenY },
        segmentIndex,
        currentArcPosition,
        this.#policy.continuityPenaltyPx,
      );
      if (!best || hit.score < best.score) best = hit;
    }
    return best;
  }

  #hitAtArcPosition(arcPosition: number, pointer: TrackingScreenPoint): SegmentHit {
    const maximumSegment = this.#stations.length - 2;
    const segmentIndex = clamp(Math.floor(arcPosition), 0, maximumSegment);
    const ratio = clamp(arcPosition - segmentIndex, 0, 1);
    const first = this.#stations[segmentIndex];
    const second = this.#stations[segmentIndex + 1];
    const screenX = interpolate(first.screenX, second.screenX, ratio);
    const screenY = interpolate(first.screenY, second.screenY, ratio);
    const distancePx = Math.hypot(pointer.x - screenX, pointer.y - screenY);
    return { segmentIndex, ratio, arcPosition: segmentIndex + ratio, screenX, screenY, distancePx, score: distancePx };
  }

  #locationFromHit(hit: SegmentHit): TrackingLocation<TPoint> {
    const first = this.#stations[hit.segmentIndex];
    const second = this.#stations[hit.segmentIndex + 1];
    return Object.freeze({
      point: this.#interpolatePoint(first.point, second.point, hit.ratio),
      segmentIndex: hit.segmentIndex,
      ratio: hit.ratio,
      arcPosition: hit.arcPosition,
      sceneX: interpolate(first.sceneX, second.sceneX, hit.ratio),
      sceneY: interpolate(first.sceneY, second.sceneY, hit.ratio),
      sceneZ: interpolate(first.sceneZ, second.sceneZ, hit.ratio),
      screenX: hit.screenX,
      screenY: hit.screenY,
      pointerDistancePx: hit.distancePx,
    });
  }
}

export type SelectedPointTrackingControllerOptions<TPoint, TObservation, TState extends TrackingBackendState> = Readonly<{
  projectStations: () => readonly TrackingTrajectoryStation<TPoint>[];
  interpolatePoint: (first: TPoint, second: TPoint, ratio: number) => TPoint;
  sendCommand: (command: TrackingBackendCommand<TObservation>) => Promise<TState | null>;
  showTransient: (location: TrackingLocation<TPoint>) => void;
  clearTransient: () => void;
  reconcileCommitted: (state: TState | null) => void;
  setOrbitEnabled: (enabled: boolean) => void;
  emitDiagnostic?: (event: TrackingControllerDiagnostic) => void;
  policy?: TrackingContinuityPolicy;
}>;

export class SelectedPointTrackingController<TPoint, TObservation, TState extends TrackingBackendState> {
  readonly #options: SelectedPointTrackingControllerOptions<TPoint, TObservation, TState>;
  #state: TrackingControllerState = 'idle';
  #pointerId: number | null = null;
  #sessionId: string | null = null;
  #sequence = 0;
  #engine: ContinuityTrackingEngine<TPoint> | null = null;
  #startPromise: Promise<TState | null> | null = null;
  #updatePromise: Promise<void> | null = null;
  #pendingObservation: TObservation | null = null;
  #finishing = false;

  constructor(options: SelectedPointTrackingControllerOptions<TPoint, TObservation, TState>) {
    this.#options = options;
  }

  get state(): TrackingControllerState {
    return this.#state;
  }

  get activePointerId(): number | null {
    return this.#pointerId;
  }

  get isActive(): boolean {
    return this.#pointerId !== null && this.#state !== 'disposed';
  }

  async start(
    pointerId: number,
    pointer: TrackingScreenPoint,
    observation: TObservation,
  ): Promise<boolean> {
    if (this.#state !== 'idle') return false;
    const engine = new ContinuityTrackingEngine(
      this.#options.projectStations(),
      this.#options.interpolatePoint,
      this.#options.policy ?? DEFAULT_TRACKING_CONTINUITY_POLICY,
    );
    const location = engine.start(pointer);
    if (!location) return false;

    this.#engine = engine;
    this.#pointerId = pointerId;
    this.#transition('starting');
    this.#options.setOrbitEnabled(false);
    this.#options.showTransient(location);
    this.#sequence += 1;

    const startPromise = this.#options.sendCommand({
      kind: 'track-start',
      sequence: this.#sequence,
      observation,
    });
    this.#startPromise = startPromise;

    try {
      const state = await startPromise;
      if (this.#startPromise !== startPromise || this.#pointerId !== pointerId) return false;
      this.#sessionId = state?.active_tracking_session_id ?? null;
      this.#startPromise = null;
      if (!this.#sessionId) {
        this.#resetToIdle();
        return false;
      }
      this.#transition('tracking');
      if (this.#pendingObservation) void this.#flushUpdate();
      return true;
    } catch (error) {
      this.#fail(error);
      return false;
    }
  }

  move(
    pointerId: number,
    pointer: TrackingScreenPoint,
    observation: TObservation,
  ): TrackingLocation<TPoint> | null {
    if (pointerId !== this.#pointerId || !this.#engine || this.#finishing) return null;
    const previousSegment = this.#engine.current?.segmentIndex ?? null;
    const step = this.#engine.update(pointer);
    this.#options.showTransient(step.location);
    if (previousSegment !== step.location.segmentIndex) {
      this.#emit('segment-transition', {
        from: previousSegment,
        to: step.location.segmentIndex,
      });
    }
    if (step.clamped) {
      this.#emit('continuity-clamp', {
        segment: step.location.segmentIndex,
        arcPosition: step.location.arcPosition,
      });
    }
    if (this.#pendingObservation) {
      this.#emit('observation-coalesced', { sequence: this.#sequence });
    }
    this.#pendingObservation = observation;
    if (this.#sessionId) void this.#flushUpdate();
    return step.location;
  }

  async commit(pointerId: number, observation: TObservation): Promise<void> {
    await this.#finish(pointerId, true, observation);
  }

  async cancel(pointerId: number): Promise<void> {
    await this.#finish(pointerId, false, null);
  }

  dispose(): void {
    if (this.#state === 'disposed') return;
    this.#state = 'disposed';
    this.#pointerId = null;
    this.#sessionId = null;
    this.#pendingObservation = null;
    this.#engine = null;
    this.#options.clearTransient();
    this.#options.setOrbitEnabled(true);
  }

  async #finish(pointerId: number, commit: boolean, observation: TObservation | null): Promise<void> {
    if (pointerId !== this.#pointerId || this.#finishing || this.#state === 'disposed') return;
    this.#finishing = true;
    this.#transition(commit ? 'committing' : 'cancelling');

    try {
      if (this.#startPromise) await this.#startPromise;
      if (this.#updatePromise) await this.#updatePromise;
      this.#pendingObservation = null;
      const sessionId = this.#sessionId;
      let state: TState | null = null;
      if (sessionId) {
        this.#sequence += 1;
        state = await this.#options.sendCommand(
          commit
            ? { kind: 'track-commit', sessionId, sequence: this.#sequence, observation: observation as TObservation }
            : { kind: 'track-cancel', sessionId, sequence: this.#sequence },
        );
      }
      if (commit) {
        this.#options.reconcileCommitted(state);
        this.#emit('commit-completed', { sequence: this.#sequence });
      } else {
        this.#emit('cancel-completed', { sequence: this.#sequence });
      }
    } catch (error) {
      this.#fail(error);
      return;
    } finally {
      if (this.#state !== 'failed' && this.#pointerId === pointerId) this.#resetToIdle();
      this.#finishing = false;
    }
  }

  #flushUpdate(): Promise<void> | null {
    if (this.#updatePromise || this.#finishing || !this.#sessionId || !this.#pendingObservation) {
      return this.#updatePromise;
    }
    const observation = this.#pendingObservation;
    const sessionId = this.#sessionId;
    this.#pendingObservation = null;
    this.#sequence += 1;
    const sequence = this.#sequence;
    const task = (async () => {
      const state = await this.#options.sendCommand({
        kind: 'track-update',
        sessionId,
        sequence,
        observation,
      });
      const responseSession = state?.active_tracking_session_id ?? sessionId;
      if (responseSession !== sessionId) {
        this.#emit('stale-response-discarded', {
          expectedSession: sessionId,
          responseSession,
          sequence,
        });
      }
    })();
    this.#updatePromise = task;
    void task.finally(() => {
      if (this.#updatePromise === task) this.#updatePromise = null;
      if (!this.#finishing && this.#pendingObservation && this.#sessionId) void this.#flushUpdate();
    });
    return task;
  }

  #resetToIdle(): void {
    this.#pointerId = null;
    this.#sessionId = null;
    this.#startPromise = null;
    this.#updatePromise = null;
    this.#pendingObservation = null;
    this.#engine = null;
    this.#options.clearTransient();
    this.#options.setOrbitEnabled(true);
    this.#transition('idle');
  }

  #fail(error: unknown): void {
    this.#state = 'failed';
    this.#emit('failure', {
      message: error instanceof Error ? error.message : String(error),
    });
    this.#pointerId = null;
    this.#sessionId = null;
    this.#startPromise = null;
    this.#updatePromise = null;
    this.#pendingObservation = null;
    this.#engine = null;
    this.#options.clearTransient();
    this.#options.setOrbitEnabled(true);
  }

  #transition(next: TrackingControllerState): void {
    const previous = this.#state;
    this.#state = next;
    this.#emit('state-transition', { previous, next });
  }

  #emit(kind: TrackingControllerDiagnostic['kind'], detail: TrackingControllerDiagnostic['detail']): void {
    this.#options.emitDiagnostic?.({ kind, detail });
  }
}
