import { describe, expect, it } from 'vitest';
import {
  expectedCommittedViewportRevision,
  shouldScheduleCommittedViewportCommit,
} from '../viewportCommitControl';

describe('viewportCommitControl', () => {
  const ready = {
    managedWellUid: 'well-1',
    canonicalRevision: 7,
    hasCanonicalSession: true,
    recoveryHydrated: true,
    recoveryAutosaveArmed: true,
    startupSemanticHydrationReady: true,
    dragPanActive: false,
  };

  it('allows a settled hydrated viewport commit', () => {
    expect(shouldScheduleCommittedViewportCommit(ready)).toBe(true);
  });

  it('blocks backend commits while drag preview is active', () => {
    expect(shouldScheduleCommittedViewportCommit({ ...ready, dragPanActive: true })).toBe(false);
  });

  it('blocks commits before recovery/startup hydration is ready', () => {
    expect(shouldScheduleCommittedViewportCommit({ ...ready, recoveryHydrated: false })).toBe(false);
    expect(shouldScheduleCommittedViewportCommit({ ...ready, recoveryAutosaveArmed: false })).toBe(false);
    expect(shouldScheduleCommittedViewportCommit({ ...ready, startupSemanticHydrationReady: false })).toBe(false);
  });

  it('uses backend view revision only for the current canonical session', () => {
    expect(expectedCommittedViewportRevision({ available: true, session_revision: 7, view_revision: 4 }, 7)).toBe(4);
    expect(expectedCommittedViewportRevision({ available: true, session_revision: 6, view_revision: 4 }, 7)).toBe(-1);
  });

  it('treats an unavailable committed view as a new revision chain', () => {
    expect(expectedCommittedViewportRevision({ available: false, session_revision: 7, view_revision: 99 }, 7)).toBe(-1);
  });
});
