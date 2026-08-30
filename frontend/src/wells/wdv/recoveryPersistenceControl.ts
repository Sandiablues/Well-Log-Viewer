export const UNIFIED_WDV_RECOVERY_RESTORE_KEY = 'recovery:__unified_wdv_canvas__';
export const WDV_RECOVERY_AUTOSAVE_DELAY_MS = 450;
export const WDV_STARTUP_HYDRATION_RETRY_DELAY_MS = 1500;

export type RecoveryLoadedWell = Readonly<{
  managed_well_uid?: string | null;
}>;

export function shouldAttemptUnifiedRecoveryHydration(input: Readonly<{
  managedViewerWellUid: string | null | undefined;
  canonicalRevision: number;
  hasCanonicalSession: boolean;
  canvasRecoveryHydrated: boolean;
}>): boolean {
  return Boolean(input.managedViewerWellUid)
    && input.canonicalRevision >= 0
    && input.hasCanonicalSession
    && !input.canvasRecoveryHydrated;
}

export function shouldArmRecoveryAutosave(input: Readonly<{
  managedViewerWellUid: string | null | undefined;
  canvasRecoveryHydrated: boolean;
  recoveryHydratedWellUid: string | null | undefined;
  startupSemanticHydrationReady: boolean;
}>): boolean {
  return Boolean(input.managedViewerWellUid)
    && input.canvasRecoveryHydrated
    && Boolean(input.recoveryHydratedWellUid)
    && input.startupSemanticHydrationReady;
}

export function shouldRetryStartupHydration(input: Readonly<{
  managedViewerWellUid: string | null | undefined;
  canvasRecoveryHydrated: boolean;
  recoveryHydratedWellUid: string | null | undefined;
  startupSemanticHydrationReady: boolean;
}>): boolean {
  return Boolean(input.managedViewerWellUid)
    && input.canvasRecoveryHydrated
    && Boolean(input.recoveryHydratedWellUid)
    && !input.startupSemanticHydrationReady;
}

export function shouldScheduleRecoveryAutosave(input: Readonly<{
  managedViewerWellUid: string | null | undefined;
  recoveryAutosaveArmed: boolean;
  canvasRecoveryHydrated: boolean;
  recoveryHydratedWellUid: string | null | undefined;
  startupSemanticHydrationReady: boolean;
  canonicalRevision: number;
  hasCanonicalSession: boolean;
}>): boolean {
  return Boolean(input.managedViewerWellUid)
    && input.recoveryAutosaveArmed
    && input.canvasRecoveryHydrated
    && Boolean(input.recoveryHydratedWellUid)
    && input.startupSemanticHydrationReady
    && input.canonicalRevision >= 0
    && input.hasCanonicalSession;
}

export function recoveryAuthorityWellUid(
  managedViewerWellUid: string | null | undefined,
): string | null {
  return managedViewerWellUid ? String(managedViewerWellUid) : null;
}

export function recoveryTargetWellUids(
  loadedWells: readonly RecoveryLoadedWell[],
  fallbackWellUid: string | null | undefined,
): string[] {
  const targets = Array.from(new Set(
    loadedWells
      .map((well) => well.managed_well_uid)
      .filter((wellUid): wellUid is string => Boolean(wellUid)),
  ));
  if (targets.length === 0 && fallbackWellUid) targets.push(fallbackWellUid);
  return targets;
}
