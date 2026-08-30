import type { WbvInteractionStateV2, WbvScreenObservationV2 } from './contracts';

export type WbvInteractionTransport = {
  observe(observation: WbvScreenObservationV2): Promise<WbvInteractionStateV2>;
  start(observation: WbvScreenObservationV2, sequence: number): Promise<WbvInteractionStateV2>;
  update(sessionId: string, observation: WbvScreenObservationV2, sequence: number): Promise<WbvInteractionStateV2>;
  commit(sessionId: string, observation: WbvScreenObservationV2 | undefined, sequence: number): Promise<WbvInteractionStateV2>;
  cancel(sessionId: string, sequence: number): Promise<WbvInteractionStateV2>;
};

export type WbvInteractionCoordinatorOptions = {
  transport: WbvInteractionTransport;
  applyState: (state: WbvInteractionStateV2) => void;
  applyFallback: (message: string) => void;
  setOrbitEnabled: (enabled: boolean) => void;
  setPointerCapture: (pointerId: number) => void;
  releasePointerCapture: (pointerId: number) => void;
};

export function createWbvInteractionCoordinator(options: WbvInteractionCoordinatorOptions) {
  let activePointerId: number | null = null;
  let activeSessionId: string | null = null;
  let sequence = 0;
  let inFlight = false;
  let pending: WbvScreenObservationV2 | null = null;
  let disposed = false;

  const safe = async (command: () => Promise<WbvInteractionStateV2>) => {
    try {
      const state = await command();
      if (!disposed) options.applyState(state);
      return state;
    } catch (error) {
      options.applyFallback(error instanceof Error ? error.message : 'WBV interaction service unavailable.');
      return null;
    }
  };

  const flush = async () => {
    if (inFlight || !activeSessionId || !pending) return;
    const observation = pending;
    pending = null;
    inFlight = true;
    sequence += 1;
    await safe(() => options.transport.update(activeSessionId!, observation, sequence));
    inFlight = false;
    if (pending) void flush();
  };

  return {
    async click(observation: WbvScreenObservationV2) {
      await safe(() => options.transport.observe(observation));
    },
    async start(pointerId: number, observation: WbvScreenObservationV2) {
      activePointerId = pointerId;
      sequence += 1;
      options.setOrbitEnabled(false);
      options.setPointerCapture(pointerId);
      const state = await safe(() => options.transport.start(observation, sequence));
      activeSessionId = state?.active_tracking_session_id ?? null;
      if (!activeSessionId) {
        options.releasePointerCapture(pointerId);
        options.setOrbitEnabled(true);
        activePointerId = null;
      }
    },
    move(pointerId: number, observation: WbvScreenObservationV2) {
      if (pointerId !== activePointerId || !activeSessionId) return;
      pending = observation;
      void flush();
    },
    async commit(pointerId: number, observation?: WbvScreenObservationV2) {
      if (pointerId !== activePointerId || !activeSessionId) return;
      const sessionId = activeSessionId;
      sequence += 1;
      try {
        await safe(() => options.transport.commit(sessionId, observation, sequence));
      } finally {
        options.releasePointerCapture(pointerId);
        options.setOrbitEnabled(true);
        activePointerId = null;
        activeSessionId = null;
        pending = null;
      }
    },
    async cancel(pointerId: number) {
      if (pointerId !== activePointerId || !activeSessionId) return;
      const sessionId = activeSessionId;
      sequence += 1;
      try {
        await safe(() => options.transport.cancel(sessionId, sequence));
      } finally {
        options.releasePointerCapture(pointerId);
        options.setOrbitEnabled(true);
        activePointerId = null;
        activeSessionId = null;
        pending = null;
      }
    },
    dispose() {
      disposed = true;
      if (activePointerId !== null) {
        options.releasePointerCapture(activePointerId);
        options.setOrbitEnabled(true);
      }
      activePointerId = null;
      activeSessionId = null;
      pending = null;
    },
  };
}
