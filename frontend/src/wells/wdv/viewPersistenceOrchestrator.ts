import { expectedCommittedViewportRevision } from './viewportCommitControl';
import { canHydrateCommittedStartupView, canHydrateRecoveryStartupView } from './startupViewHydrationControl';
import { persistenceRequestForCommittedView } from './viewPersistenceControl';

export type WdvJsonFetcher = <T>(url: string, init?: RequestInit) => Promise<T>;

export type CommittedViewResponse<TViewState> = {
    available: boolean;
    committed_at?: string | null;
    session_revision?: number | null;
    current_session_revision?: number | null;
    view_revision?: number;
    stale?: boolean;
    view_state?: TViewState | null;
};

export type SnapshotViewResponse<TViewState, TSession = unknown> = {
    available: boolean;
    saved_at?: string | null;
    session_revision?: number | null;
    current_session_revision?: number | null;
    stale?: boolean;
    view_state?: TViewState | null;
    session?: TSession;
};

export type StartupViewLoadResult<TViewState> =
    | { status: 'committed'; viewState: TViewState }
    | { status: 'recovery'; viewState: TViewState }
    | { status: 'none' }
    | { status: 'aborted' };

export async function commitSettledViewState<TViewState>(args: {
    fetchJson: WdvJsonFetcher;
    wellUid: string;
    sessionRevision: number;
    viewState: TViewState;
    currentSessionRevision: () => number;
}): Promise<CommittedViewResponse<TViewState> | null> {
    const { fetchJson, wellUid, sessionRevision, viewState, currentSessionRevision } = args;
    if (currentSessionRevision() !== sessionRevision) return null;

    const endpoint = `/api/wlv/v2/wdv/workspaces/${encodeURIComponent(wellUid)}/committed-view-state`;
    const current = await fetchJson<CommittedViewResponse<TViewState>>(endpoint);
    if (currentSessionRevision() !== sessionRevision) return null;

    const expectedViewRevision = expectedCommittedViewportRevision(current, sessionRevision);
    return fetchJson<CommittedViewResponse<TViewState>>(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            expected_session_revision: sessionRevision,
            expected_view_revision: expectedViewRevision,
            view_state: viewState,
        }),
    });
}

export async function loadAuthoritativeStartupView<TViewState>(args: {
    fetchJson: WdvJsonFetcher;
    authorityWellUid: string;
    expectedSessionRevision: number;
    currentSessionRevision: () => number;
}): Promise<StartupViewLoadResult<TViewState>> {
    const { fetchJson, authorityWellUid, expectedSessionRevision, currentSessionRevision } = args;
    const base = `/api/wlv/v2/wdv/workspaces/${encodeURIComponent(authorityWellUid)}`;

    const committed = await fetchJson<CommittedViewResponse<TViewState>>(`${base}/committed-view-state`);
    if (currentSessionRevision() !== expectedSessionRevision) return { status: 'aborted' };
    if (canHydrateCommittedStartupView(committed, expectedSessionRevision)) {
        return { status: 'committed', viewState: committed.view_state as TViewState };
    }

    const recovery = await fetchJson<SnapshotViewResponse<TViewState>>(`${base}/recovery-state`);
    if (currentSessionRevision() !== expectedSessionRevision) return { status: 'aborted' };
    if (canHydrateRecoveryStartupView(recovery, expectedSessionRevision)) {
        return { status: 'recovery', viewState: recovery.view_state as TViewState };
    }
    return { status: 'none' };
}

export async function saveSnapshotFromCommittedView<TViewState>(args: {
    fetchJson: WdvJsonFetcher;
    wellUid: string;
    committed: CommittedViewResponse<TViewState> | null;
    sessionRevision: number;
    currentSessionRevision: () => number;
}): Promise<SnapshotViewResponse<TViewState> | null> {
    const request = persistenceRequestForCommittedView(args.committed, args.sessionRevision);
    if (!request || args.currentSessionRevision() !== args.sessionRevision) return null;
    return args.fetchJson<SnapshotViewResponse<TViewState>>(
        `/api/wlv/v2/wdv/workspaces/${encodeURIComponent(args.wellUid)}/saved-snapshot`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request),
        },
    );
}

export async function saveRecoverySnapshotsFromCommittedView<TViewState>(args: {
    fetchJson: WdvJsonFetcher;
    wellUids: string[];
    committed: CommittedViewResponse<TViewState> | null;
    sessionRevision: number;
    currentSessionRevision: () => number;
}): Promise<Array<PromiseSettledResult<SnapshotViewResponse<TViewState>>> | null> {
    const request = persistenceRequestForCommittedView(args.committed, args.sessionRevision);
    if (!request || args.currentSessionRevision() !== args.sessionRevision) return null;
    return Promise.allSettled(
        args.wellUids.map((wellUid) =>
            args.fetchJson<SnapshotViewResponse<TViewState>>(
                `/api/wlv/v2/wdv/workspaces/${encodeURIComponent(wellUid)}/recovery-state`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(request),
                },
            ),
        ),
    );
}
