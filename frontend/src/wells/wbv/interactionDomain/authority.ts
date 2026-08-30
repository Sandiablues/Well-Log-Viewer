import type { WbvInteractionStateV2 } from './contracts';

export type WbvRevisionedCommand = (expectedRevision: number) => Promise<WbvInteractionStateV2>;

export type WbvInteractionCommandAuthorityOptions = {
  applyState: (state: WbvInteractionStateV2) => void;
  applyError: (message: string | null) => void;
};

/**
 * Sole frontend owner of the latest backend-acknowledged interaction revision.
 * Revision-guarded writes are strictly serialized. Session commands may remain
 * high-frequency, but stale responses can never overwrite newer state.
 */
export function createWbvInteractionCommandAuthority(options: WbvInteractionCommandAuthorityOptions) {
  let latestState: WbvInteractionStateV2 | null = null;
  let revisionQueue: Promise<void> = Promise.resolve();
  let disposed = false;

  const applyIfCurrent = (state: WbvInteractionStateV2): WbvInteractionStateV2 => {
    if (disposed) return state;
    if (latestState && state.revision < latestState.revision) return state;
    latestState = state;
    options.applyState(state);
    return state;
  };

  const fail = (error: unknown): null => {
    if (!disposed) options.applyError(error instanceof Error ? error.message : 'WBV interaction command failed.');
    return null;
  };

  return {
    seed(state: WbvInteractionStateV2 | null) {
      latestState = state;
      if (state && !disposed) options.applyState(state);
    },

    latestRevision(): number {
      return latestState?.revision ?? 0;
    },

    runRevisioned(command: WbvRevisionedCommand): Promise<WbvInteractionStateV2 | null> {
      let result: WbvInteractionStateV2 | null = null;
      revisionQueue = revisionQueue.then(async () => {
        if (disposed) return;
        options.applyError(null);
        try {
          result = applyIfCurrent(await command(latestState?.revision ?? 0));
        } catch (error) {
          result = fail(error);
        }
      });
      return revisionQueue.then(() => result);
    },

    async runSession(command: () => Promise<WbvInteractionStateV2>): Promise<WbvInteractionStateV2 | null> {
      if (disposed) return null;
      options.applyError(null);
      try {
        return applyIfCurrent(await command());
      } catch (error) {
        return fail(error);
      }
    },

    dispose() {
      disposed = true;
    },
  };
}

export type WbvInteractionCommandAuthority = ReturnType<typeof createWbvInteractionCommandAuthority>;
