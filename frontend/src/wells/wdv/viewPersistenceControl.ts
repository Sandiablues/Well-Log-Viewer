export type CommittedViewRevisionLike = {
  available: boolean;
  session_revision?: number | null;
  current_session_revision?: number | null;
  view_revision?: number;
  stale?: boolean;
};

export type PersistCommittedViewRequest = {
  expected_revision: number;
  expected_view_revision: number;
};

/**
 * Save and Recovery are copy/checkpoint operations only. They may persist an
 * already committed view revision, but they may not author a second frontend
 * view payload independently of the committed-view command stream.
 */
export function persistenceRequestForCommittedView(
  response: CommittedViewRevisionLike | null | undefined,
  expectedSessionRevision: number,
): PersistCommittedViewRequest | null {
  if (!response?.available || response.stale) return null;
  if (response.session_revision !== expectedSessionRevision) return null;
  if (
    response.current_session_revision != null
    && response.current_session_revision !== expectedSessionRevision
  ) {
    return null;
  }
  if (
    typeof response.view_revision !== 'number'
    || !Number.isInteger(response.view_revision)
    || response.view_revision < 0
  ) {
    return null;
  }
  return {
    expected_revision: expectedSessionRevision,
    expected_view_revision: response.view_revision,
  };
}
