import { useCallback, useRef } from 'react';
import {
  executeCanonicalSessionCommand,
  type CanonicalCommandDiagnosticFactory,
  type CanonicalCommandFetch,
} from './canonicalSessionCommandOrchestrator';

type CanonicalRevisionRef = Readonly<{ current: number }>;

export type CanonicalSessionApplicationOptions = Readonly<{
  preserveInteraction?: boolean;
}>;

export function useCanonicalSessionMutationController<
  TSession extends { revision: number; tracks?: unknown[] },
>(args: Readonly<{
  managedWellUid: string | null | undefined;
  canonicalRevisionRef: CanonicalRevisionRef;
  applyCanonicalSession: (
    session: TSession,
    options?: CanonicalSessionApplicationOptions,
  ) => void;
  fetchJson: CanonicalCommandFetch;
  beginDiagnostic?: CanonicalCommandDiagnosticFactory;
}>) {
  const mutationTailRef = useRef<Promise<void>>(Promise.resolve());

  const executeCanonicalCommand = useCallback(
    async (
      commandPath: string,
      body: Record<string, unknown>,
    ): Promise<TSession> => executeCanonicalSessionCommand<TSession>({
      managedWellUid: args.managedWellUid,
      commandPath,
      body,
      getExpectedRevision: () => args.canonicalRevisionRef.current,
      fetchJson: args.fetchJson,
      beginDiagnostic: args.beginDiagnostic,
    }),
    [
      args.beginDiagnostic,
      args.canonicalRevisionRef,
      args.fetchJson,
      args.managedWellUid,
    ],
  );

  const refreshCanonicalSession = useCallback(async (
    options: CanonicalSessionApplicationOptions = {},
  ): Promise<void> => {
    if (!args.managedWellUid) return;
    const fresh = await args.fetchJson<TSession>(
      `/api/wlv/v2/wdv/sessions/${encodeURIComponent(args.managedWellUid)}`,
    ).catch(() => null);
    if (fresh) args.applyCanonicalSession(fresh, options);
  }, [args.applyCanonicalSession, args.fetchJson, args.managedWellUid]);

  const runSerializedCanonicalTask = useCallback(<TResult,>(
    task: () => Promise<TResult>,
  ): Promise<TResult> => {
    const result = mutationTailRef.current.then(task, task);
    mutationTailRef.current = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }, []);

  const runSerializedCanonicalMutation = useCallback(
    (
      commandPath: string,
      body: Record<string, unknown>,
      options: CanonicalSessionApplicationOptions = {
        preserveInteraction: true,
      },
    ): Promise<TSession> => runSerializedCanonicalTask(async () => {
      try {
        const rawSession = await executeCanonicalCommand(commandPath, body);
        args.applyCanonicalSession(rawSession, options);
        return rawSession;
      } catch (error) {
        if (error instanceof Error && error.message.startsWith('409 ')) {
          await refreshCanonicalSession(options);
        }
        throw error;
      }
    }),
    [args.applyCanonicalSession, executeCanonicalCommand, refreshCanonicalSession, runSerializedCanonicalTask],
  );

  return {
    executeCanonicalCommand,
    refreshCanonicalSession,
    runSerializedCanonicalMutation,
    runSerializedCanonicalTask,
  } as const;
}
