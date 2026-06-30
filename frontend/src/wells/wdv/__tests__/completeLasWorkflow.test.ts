import { describe, expect, it } from 'vitest';
import {
  COMPLETE_LAS_PLACEMENTS,
  buildCompleteLasLoadRequest,
  buildCompleteLasLoadUrl,
  buildCompleteLasPlanUrl,
} from '../completeLasWorkflow';

describe('complete LAS frontend workflow', () => {
  it('builds governed backend plan and load endpoints', () => {
    expect(buildCompleteLasPlanUrl('managed well/1', 'source file/2')).toBe(
      '/api/wlv/v2/wdv/las/managed%20well%2F1/plan?source_id=source%20file%2F2',
    );
    expect(buildCompleteLasLoadUrl('managed well/1')).toBe(
      '/api/wlv/v2/wdv/las/managed%20well%2F1/load-complete',
    );
  });

  it('keeps inventory-only and canvas placement explicit', () => {
    expect(COMPLETE_LAS_PLACEMENTS).toEqual(['inventory_only', 'append_tracks']);
  });

  it('builds a revision-guarded backend-owned command', () => {
    expect(
      buildCompleteLasLoadRequest({
        expectedRevision: 17,
        sourceId: 'source-1',
        placement: 'inventory_only',
        includeReviewRequired: false,
      }),
    ).toEqual({
      expected_revision: 17,
      source_id: 'source-1',
      placement: 'inventory_only',
      include_review_required: false,
      skip_existing_assignments: true,
      track_width_px: 150,
    });
  });

  it('passes review-required selection explicitly', () => {
    expect(
      buildCompleteLasLoadRequest({
        expectedRevision: 2,
        sourceId: 'source-2',
        placement: 'append_tracks',
        includeReviewRequired: true,
      }).include_review_required,
    ).toBe(true);
  });
});
