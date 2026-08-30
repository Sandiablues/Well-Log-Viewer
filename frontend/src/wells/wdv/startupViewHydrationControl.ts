export type RevisionedStartupViewResponse = {
    available: boolean;
    session_revision?: number | null;
    current_session_revision?: number | null;
    stale?: boolean;
    view_state?: unknown | null;
};

function exactRevisionMatch(
    response: RevisionedStartupViewResponse,
    expectedSessionRevision: number,
): boolean {
    return response.session_revision === expectedSessionRevision
        && response.current_session_revision === expectedSessionRevision;
}

/**
 * A committed view is the canonical settled viewport source for one exact
 * canonical session revision. Never hydrate a stale or revision-ambiguous
 * committed view.
 */
export function canHydrateCommittedStartupView(
    response: RevisionedStartupViewResponse,
    expectedSessionRevision: number,
): boolean {
    return response.available === true
        && response.stale !== true
        && response.view_state != null
        && exactRevisionMatch(response, expectedSessionRevision);
}

/**
 * Recovery is a fallback checkpoint only. It is usable only when the backend
 * proves that it belongs to the exact canonical session revision currently
 * being hydrated.
 */
export function canHydrateRecoveryStartupView(
    response: RevisionedStartupViewResponse,
    expectedSessionRevision: number,
): boolean {
    return response.available === true
        && response.stale !== true
        && response.view_state != null
        && exactRevisionMatch(response, expectedSessionRevision);
}
