export interface CommittedViewportCommitGateInput {
  managedWellUid: string | null | undefined;
  canonicalRevision: number;
  hasCanonicalSession: boolean;
  recoveryHydrated: boolean;
  recoveryAutosaveArmed: boolean;
  startupSemanticHydrationReady: boolean;
  dragPanActive: boolean;
}

export interface CommittedViewportRevisionEnvelope {
  available: boolean;
  session_revision?: number | null;
  view_revision?: number | null;
}

export function shouldScheduleCommittedViewportCommit(
  input: CommittedViewportCommitGateInput,
): boolean {
  return Boolean(
    input.managedWellUid
    && input.canonicalRevision >= 0
    && input.hasCanonicalSession
    && input.recoveryHydrated
    && input.recoveryAutosaveArmed
    && input.startupSemanticHydrationReady
    && !input.dragPanActive
  );
}

export function expectedCommittedViewportRevision(
  envelope: CommittedViewportRevisionEnvelope,
  canonicalRevision: number,
): number {
  if (
    !envelope.available
    || envelope.session_revision !== canonicalRevision
    || !Number.isInteger(envelope.view_revision)
  ) {
    return -1;
  }
  return Number(envelope.view_revision);
}
