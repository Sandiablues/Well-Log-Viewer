export type ViewportTieCandidate = Readonly<{ trackId: string; label: string }>;

export type ViewportToolbarPresentation = Readonly<{
  lock: Readonly<{
    selectedCount: number;
    action: 'lock' | 'unlock' | 'none';
    disabled: boolean;
    label: 'Lock' | 'Unlock';
    title: string;
  }>;
  tie: Readonly<{
    action: 'tie' | 'untie' | 'none';
    disabled: boolean;
    label: 'Tie' | 'Untie';
    title: string;
    visualState: 'tied' | 'ready' | 'dim';
    candidates: readonly ViewportTieCandidate[];
  }>;
}>;

export function buildViewportToolbarPresentation(input: Readonly<{
  quickView: boolean;
  combinationSelectedCount: number;
  combinationSelectedUnlockedCount: number;
  viewportTieCandidates: readonly ViewportTieCandidate[];
  viewportTieCanCreate: boolean;
  viewportTieCanUntie: boolean;
  viewportTieCreateDisabledReason: string;
}>): ViewportToolbarPresentation {
  const selectedCount = input.quickView ? 0 : input.combinationSelectedCount;
  const selectedUnlockedCount = input.quickView ? 0 : input.combinationSelectedUnlockedCount;
  const lockAction: 'lock' | 'unlock' | 'none' = selectedCount === 0
    ? 'none'
    : selectedUnlockedCount > 0 ? 'lock' : 'unlock';

  const tieCanUntie = !input.quickView && input.viewportTieCanUntie;
  const tieCanCreate = !input.quickView && input.viewportTieCanCreate;
  const tieAction: 'tie' | 'untie' | 'none' = tieCanUntie ? 'untie' : tieCanCreate ? 'tie' : 'none';

  return {
    lock: {
      selectedCount,
      action: lockAction,
      disabled: lockAction === 'none',
      label: lockAction === 'lock' ? 'Lock' : 'Unlock',
      title: lockAction === 'none'
        ? 'Highlight a track, or activate one or more T tracks'
        : lockAction === 'lock'
          ? 'Lock the highlighted track or highlighted track set'
          : 'Unlock the highlighted locked track or highlighted locked track set',
    },
    tie: {
      action: tieAction,
      disabled: tieAction === 'none',
      label: tieCanUntie ? 'Untie' : 'Tie',
      title: input.quickView
        ? 'Tie is unavailable in Quick View'
        : tieCanUntie
          ? 'Untie the selected tied track or tracks'
          : tieCanCreate
            ? 'Tie the selected tracks to one authoritative viewport'
            : input.viewportTieCreateDisabledReason || 'Select two or more untied tracks to create a Tie',
      visualState: tieCanUntie ? 'tied' : tieCanCreate ? 'ready' : 'dim',
      candidates: input.quickView ? [] : input.viewportTieCandidates,
    },
  };
}
