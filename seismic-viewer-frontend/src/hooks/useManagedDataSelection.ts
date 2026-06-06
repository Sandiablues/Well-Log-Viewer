import { useCallback, useState } from "react";

export type ManagedDataTargetSelection = {
  preview?: boolean;
  optimized_cache?: boolean;
};

export function useManagedDataSelection() {
  const [selectedDataTargets, setSelectedDataTargets] = useState<
    Record<string, ManagedDataTargetSelection>
  >({});

  const getSelectedTargets = useCallback(
    (volumeId: string): ManagedDataTargetSelection => selectedDataTargets[volumeId] || {},
    [selectedDataTargets]
  );

  const setSelectedTarget = useCallback(
    (
      volumeId: string,
      target: keyof ManagedDataTargetSelection,
      checked: boolean
    ) => {
      setSelectedDataTargets((current) => ({
        ...current,
        [volumeId]: {
          ...(current[volumeId] || {}),
          [target]: checked,
        },
      }));
    },
    []
  );

  const clearSelectedTargets = useCallback((volumeId: string) => {
    setSelectedDataTargets((current) => {
      const next = { ...current };
      delete next[volumeId];
      return next;
    });
  }, []);

  const countSelectedTargets = useCallback(
    (targets: ManagedDataTargetSelection): number =>
      Number(Boolean(targets.preview)) + Number(Boolean(targets.optimized_cache)),
    []
  );

  return {
    selectedDataTargets,
    getSelectedTargets,
    setSelectedTarget,
    clearSelectedTargets,
    countSelectedTargets,
  };
}
