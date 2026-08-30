import { describe, expect, it } from 'vitest';
import {
  recoveryAuthorityWellUid,
  recoveryTargetWellUids,
  shouldArmRecoveryAutosave,
  shouldAttemptUnifiedRecoveryHydration,
  shouldRetryStartupHydration,
  shouldScheduleRecoveryAutosave,
} from '../recoveryPersistenceControl';

describe('recoveryPersistenceControl', () => {
  it('allows one recovery hydration only after canonical session authority exists', () => {
    expect(shouldAttemptUnifiedRecoveryHydration({
      managedViewerWellUid: 'well-a', canonicalRevision: 4, hasCanonicalSession: true, canvasRecoveryHydrated: false,
    })).toBe(true);
    expect(shouldAttemptUnifiedRecoveryHydration({
      managedViewerWellUid: 'well-a', canonicalRevision: -1, hasCanonicalSession: true, canvasRecoveryHydrated: false,
    })).toBe(false);
    expect(shouldAttemptUnifiedRecoveryHydration({
      managedViewerWellUid: 'well-a', canonicalRevision: 4, hasCanonicalSession: true, canvasRecoveryHydrated: true,
    })).toBe(false);
  });

  it('does not arm recovery autosave until semantic hydration is complete', () => {
    const base = { managedViewerWellUid: 'well-a', canvasRecoveryHydrated: true, recoveryHydratedWellUid: 'well-a' };
    expect(shouldArmRecoveryAutosave({ ...base, startupSemanticHydrationReady: false })).toBe(false);
    expect(shouldArmRecoveryAutosave({ ...base, startupSemanticHydrationReady: true })).toBe(true);
  });

  it('retries startup hydration only while recovery exists but semantic hydration is incomplete', () => {
    const base = { managedViewerWellUid: 'well-a', canvasRecoveryHydrated: true, recoveryHydratedWellUid: 'well-a' };
    expect(shouldRetryStartupHydration({ ...base, startupSemanticHydrationReady: false })).toBe(true);
    expect(shouldRetryStartupHydration({ ...base, startupSemanticHydrationReady: true })).toBe(false);
  });

  it('requires every durable gate before scheduling recovery autosave', () => {
    const ready = {
      managedViewerWellUid: 'well-a', recoveryAutosaveArmed: true, canvasRecoveryHydrated: true,
      recoveryHydratedWellUid: 'well-a', startupSemanticHydrationReady: true,
      canonicalRevision: 7, hasCanonicalSession: true,
    };
    expect(shouldScheduleRecoveryAutosave(ready)).toBe(true);
    expect(shouldScheduleRecoveryAutosave({ ...ready, recoveryAutosaveArmed: false })).toBe(false);
    expect(shouldScheduleRecoveryAutosave({ ...ready, canonicalRevision: -1 })).toBe(false);
    expect(shouldScheduleRecoveryAutosave({ ...ready, hasCanonicalSession: false })).toBe(false);
  });

  it('deduplicates loaded well recovery targets and preserves workspace order', () => {
    expect(recoveryTargetWellUids([
      { managed_well_uid: 'a' }, { managed_well_uid: 'b' }, { managed_well_uid: 'a' }, { managed_well_uid: null },
    ], 'fallback')).toEqual(['a', 'b']);
  });

  it('uses the active well only when no loaded-well target exists', () => {
    expect(recoveryTargetWellUids([], 'fallback')).toEqual(['fallback']);
    expect(recoveryTargetWellUids([], null)).toEqual([]);
  });
  it('preserves null recovery authority and returns a concrete UID when present', () => {
    expect(recoveryAuthorityWellUid(null)).toBeNull();
    expect(recoveryAuthorityWellUid(undefined)).toBeNull();
    expect(recoveryAuthorityWellUid('well-1')).toBe('well-1');
  });

});
