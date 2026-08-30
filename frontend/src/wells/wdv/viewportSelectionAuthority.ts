/**
 * Pure explicit-selection authority shared by toolbar and pointer viewport
 * commands. Lock is an exclusion gate; selection never changes Tie topology.
 */
export function resolveViewportSelectionTrackIds(input: {
  selectedTrackId: string | null;
  multiHighlightedTrackIds: readonly string[];
}): string[] {
  return Array.from(new Set([
    ...(input.selectedTrackId ? [input.selectedTrackId] : []),
    ...input.multiHighlightedTrackIds,
  ]));
}

export function isSelectedViewportTrackEligible(input: {
  sourceTrackId: string | null;
  selectedTrackId: string | null;
  multiHighlightedTrackIds: readonly string[];
  lockedTrackIds: ReadonlySet<string>;
}): boolean {
  if (!input.sourceTrackId || input.lockedTrackIds.has(input.sourceTrackId)) return false;
  return resolveViewportSelectionTrackIds(input).includes(input.sourceTrackId);
}
