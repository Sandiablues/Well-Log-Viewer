export const COMPLETE_LAS_PLACEMENTS = ['inventory_only', 'append_tracks'] as const;

export type CompleteLasPlacement = (typeof COMPLETE_LAS_PLACEMENTS)[number];

export type CompleteLasLoadRequestInput = {
  expectedRevision: number;
  sourceId: string;
  placement: CompleteLasPlacement;
  includeReviewRequired: boolean;
};

export type CompleteLasLoadRequest = {
  expected_revision: number;
  source_id: string;
  placement: CompleteLasPlacement;
  include_review_required: boolean;
  skip_existing_assignments: true;
  track_width_px: 150;
};

export function buildCompleteLasPlanUrl(managedWellUid: string, sourceId: string): string {
  return `/api/wlv/v2/wdv/las/${encodeURIComponent(managedWellUid)}/plan?source_id=${encodeURIComponent(sourceId)}`;
}

export function buildCompleteLasLoadUrl(managedWellUid: string): string {
  return `/api/wlv/v2/wdv/las/${encodeURIComponent(managedWellUid)}/load-complete`;
}

export function buildCompleteLasLoadRequest(input: CompleteLasLoadRequestInput): CompleteLasLoadRequest {
  return {
    expected_revision: input.expectedRevision,
    source_id: input.sourceId,
    placement: input.placement,
    include_review_required: input.includeReviewRequired,
    skip_existing_assignments: true,
    track_width_px: 150,
  };
}
