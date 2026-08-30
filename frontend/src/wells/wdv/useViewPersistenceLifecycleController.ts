import { useCallback, useRef } from 'react';
import {
  commitSettledViewState,
  loadAuthoritativeStartupView,
  saveRecoverySnapshotsFromCommittedView,
  saveSnapshotFromCommittedView,
} from './viewPersistenceOrchestrator';

type RevisionRef = Readonly<{ current: number }>;

export type SavedSnapshotResponse<TView, TSession> = {
  available: boolean;
  saved_at?: string | null;
  session_revision?: number | null;
  current_session_revision?: number | null;
  stale?: boolean;
  view_state?: TView | null;
  session?: TSession;
};

export function useViewPersistenceLifecycleController<
  TView,
  TSession extends { revision: number },
>(args: Readonly<{
  managedWellUid: string | null | undefined;
  canonicalRevisionRef: RevisionRef;
  fetchJson: <TResponse>(
    url: string,
    init?: RequestInit,
  ) => Promise<TResponse>;
}>) {
  const committedMutationTailRef = useRef<Promise<void>>(Promise.resolve());

  const commitCurrentViewState = useCallback(
    (viewState: TView) => {
      const wellUid = args.managedWellUid;
      const sessionRevision = args.canonicalRevisionRef.current;
      const mutation = committedMutationTailRef.current
        .catch(() => undefined)
        .then(async () => {
          if (!wellUid || args.canonicalRevisionRef.current !== sessionRevision) {
            return null;
          }
          return commitSettledViewState<TView>({
            fetchJson: args.fetchJson,
            wellUid,
            sessionRevision,
            viewState,
            currentSessionRevision: () => args.canonicalRevisionRef.current,
          });
        });

      committedMutationTailRef.current = mutation
        .then(() => undefined)
        .catch(() => undefined);
      return mutation;
    },
    [
      args.canonicalRevisionRef,
      args.fetchJson,
      args.managedWellUid,
    ],
  );

  const saveCommittedWorkspaceSnapshot = useCallback(
    async (viewState: TView) => {
      const wellUid = args.managedWellUid;
      const sessionRevision = args.canonicalRevisionRef.current;
      if (!wellUid || sessionRevision < 0) return null;

      const committed = await commitCurrentViewState(viewState);
      return saveSnapshotFromCommittedView<TView>({
        fetchJson: args.fetchJson,
        wellUid,
        committed,
        sessionRevision,
        currentSessionRevision: () => args.canonicalRevisionRef.current,
      });
    },
    [
      args.canonicalRevisionRef,
      args.fetchJson,
      args.managedWellUid,
      commitCurrentViewState,
    ],
  );

  const restoreSavedWorkspaceSnapshotResponse = useCallback(
    async (): Promise<SavedSnapshotResponse<TView, TSession>> => {
      const wellUid = args.managedWellUid;
      const expectedRevision = args.canonicalRevisionRef.current;
      if (!wellUid || expectedRevision < 0) {
        return { available: false };
      }

      return args.fetchJson<SavedSnapshotResponse<TView, TSession>>(
        `/api/wlv/v2/wdv/workspaces/${encodeURIComponent(wellUid)}/saved-snapshot/restore`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expected_revision: expectedRevision }),
        },
      );
    },
    [
      args.canonicalRevisionRef,
      args.fetchJson,
      args.managedWellUid,
    ],
  );

  const loadStartupView = useCallback(
    (
      authorityWellUid: string,
      expectedSessionRevision: number,
    ) => loadAuthoritativeStartupView<TView>({
      fetchJson: args.fetchJson,
      authorityWellUid,
      expectedSessionRevision,
      currentSessionRevision: () => args.canonicalRevisionRef.current,
    }),
    [
      args.canonicalRevisionRef,
      args.fetchJson,
    ],
  );

  const saveCommittedRecoverySnapshots = useCallback(
    async (
      wellUids: string[],
      viewState: TView,
    ) => {
      const sessionRevision = args.canonicalRevisionRef.current;
      if (sessionRevision < 0) return null;
      const committed = await commitCurrentViewState(viewState);
      return saveRecoverySnapshotsFromCommittedView<TView>({
        fetchJson: args.fetchJson,
        wellUids,
        committed,
        sessionRevision,
        currentSessionRevision: () => args.canonicalRevisionRef.current,
      });
    },
    [
      args.canonicalRevisionRef,
      args.fetchJson,
      commitCurrentViewState,
    ],
  );

  return {
    commitCurrentViewState,
    saveCommittedWorkspaceSnapshot,
    restoreSavedWorkspaceSnapshotResponse,
    loadStartupView,
    saveCommittedRecoverySnapshots,
  } as const;
}
