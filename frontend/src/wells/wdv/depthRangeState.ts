export type ManagedWellDepthRange = {
  min: number;
  max: number;
};

export function replaceManagedWellDepthRanges(
  current: Record<string, ManagedWellDepthRange>,
  replacements: ReadonlyMap<string, ManagedWellDepthRange>,
): Record<string, ManagedWellDepthRange> {
  if (replacements.size === 0) return current;

  const next = { ...current };
  replacements.forEach((range, managedWellUid) => {
    next[managedWellUid] = { ...range };
  });
  return next;
}
