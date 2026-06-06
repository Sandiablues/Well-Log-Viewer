import { loadMsiRepresentation, unloadMsiRepresentation, updateMsiRepresentationDisplayName, updateVolume } from "../services/zarrService";
import type { Volume } from "../services/zarrService";
import type { ManagedDataTargetSelection } from "./useManagedDataSelection";

type UseManagedVolumeActionsArgs = {
  selectedVolume: Volume | null;
  onSelectVolume: (volume: Volume, options?: { loadMode?: "preview" | "optimized_cache" }) => void;
  onRefreshVolumes: () => Promise<void>;
  onClearSelectedVolume: () => void;
  clearSelectedTargets: (volumeId: string) => void;
  countSelectedTargets: (targets: ManagedDataTargetSelection) => number;
  getDisplayName: (volume: Volume) => string;
};

export function useManagedVolumeActions({
  selectedVolume,
  onSelectVolume,
  onRefreshVolumes,
  onClearSelectedVolume,
  clearSelectedTargets,
  countSelectedTargets,
  getDisplayName,
}: UseManagedVolumeActionsArgs) {
  const loadSelectedTargets = async (
    volume: Volume,
    targets: ManagedDataTargetSelection,
    optimizedCacheAvailable: boolean
  ) => {
    const selectedCount = countSelectedTargets(targets);

    // Default-load behavior:
    // - Normal converted Zarr datasets should not require a checkbox first.
    // - Indexed SEG-Y datasets can still use explicit Preview / Fully Converted selection.
    // - If Fully Converted is selected and available, prefer it; otherwise load preview/Zarr.
    const effectiveTargets =
      selectedCount === 0
        ? { preview: true, optimized_cache: false }
        : targets;

    const loadMode: "preview" | "optimized_cache" =
      effectiveTargets.optimized_cache && optimizedCacheAvailable ? "optimized_cache" : "preview";

    if (loadMode === "optimized_cache" && !optimizedCacheAvailable) {
      window.alert("Fully Converted cache is not available for this dataset.");
      return;
    }

    if (volume.msi_representation_id) {
      await loadMsiRepresentation(volume.msi_representation_id);
      clearSelectedTargets(volume.id);
      await onRefreshVolumes();
      window.dispatchEvent(new CustomEvent("multiviewer:managed-data-updated"));
      return;
    }

    if (volume.hidden) {
      await updateVolume(volume.id, { hidden: false });
      clearSelectedTargets(volume.id);
      await onRefreshVolumes();
      window.dispatchEvent(new CustomEvent("multiviewer:managed-data-updated"));
      return;
    }

    // Already available in the viewer catalog. Load is intentionally non-navigating;
    // use the row View action or the left viewer navigation to display it.
    await onRefreshVolumes();
  };

  const handleRename = async (volume: Volume) => {
    const isMsiManaged =
      String(volume.id || "").startsWith("msi_repr:") ||
      volume.source === "msi" ||
      volume.registry_source === "msi" ||
      Boolean((volume as any).msi_representation_id);

    const currentName = getDisplayName(volume);
    const nextName = window.prompt("Dataset display name:", currentName);

    if (nextName === null) return;

    const cleanNextName = nextName.trim();
    const displayNameChanged = cleanNextName && cleanNextName !== currentName.trim();

    if (isMsiManaged) {
      const representationId = String((volume as any).msi_representation_id || volume.id || "").trim();

      if (!representationId) {
        window.alert("MSI-managed data cannot be edited because the representation id is missing.");
        return;
      }

      if (!displayNameChanged) return;

      await updateMsiRepresentationDisplayName(representationId, cleanNextName);
      await onRefreshVolumes();
      return;
    }

    if (!displayNameChanged) return;

    await updateVolume(volume.id, { display_name: cleanNextName });
    await onRefreshVolumes();
  };

  const unloadFromViewerCatalog = async (volume: Volume) => {
    // Unload means remove from viewer catalog/dropdown, not delete from Managed Data.
    if (volume.msi_representation_id) {
      await unloadMsiRepresentation(volume.msi_representation_id);
      clearSelectedTargets(volume.id);
      await onRefreshVolumes();

      if (selectedVolume?.id === volume.id || selectedVolume?.msi_representation_id === volume.msi_representation_id) {
        onClearSelectedVolume();
      }

      return;
    }

    await updateVolume(volume.id, { hidden: true });
    clearSelectedTargets(volume.id);
    await onRefreshVolumes();

    if (selectedVolume?.id === volume.id) {
      onClearSelectedVolume();
    }
  };

  return {
    loadSelectedTargets,
    handleRename,
    unloadFromViewerCatalog,
  };
}
