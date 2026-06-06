import { deleteVolume } from "../services/zarrService";
import type { Volume } from "../services/zarrService";
import { hardDeleteMsiRepresentation } from "../services/registryService";

function notifyManagedLifecycleDeleted(detail?: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent("multiviewer:managed-data-updated", { detail: detail || {} }));
  window.dispatchEvent(new CustomEvent("multiviewer:source-intake-updated", { detail: detail || {} }));
}

type UseManagedDeleteActionArgs = {
  selectedVolume: Volume | null;
  onRefreshVolumes: () => Promise<void>;
  onClearSelectedVolume: () => void;
  getDisplayName: (volume: Volume) => string;
};

export function useManagedDeleteAction({
  selectedVolume,
  onRefreshVolumes,
  onClearSelectedVolume,
  getDisplayName,
}: UseManagedDeleteActionArgs) {
  const handleDelete = async (volume: Volume) => {
    const name = getDisplayName(volume);

    const isMsiManaged =
      String(volume.id || "").startsWith("msi_repr:") ||
      volume.source === "msi" ||
      volume.registry_source === "msi" ||
      Boolean((volume as any).msi_representation_id);

    if (isMsiManaged) {
      const representationId = String((volume as any).msi_representation_id || volume.id || "").trim();

      if (!representationId) {
        window.alert("MSI-managed data cannot be deleted because the representation id is missing.");
        return;
      }

      const confirmed = window.confirm(
        `Delete MSI-managed dataset "${name}" from Managed Data?\n\nThis permanently deletes the managed lifecycle for this representation: MSI records, viewer/load state, source conversion linkage, and the app-owned managed Zarr artifact. The original source SEG-Y file is preserved.`
      );

      if (!confirmed) return;

      const result = await hardDeleteMsiRepresentation(representationId);
      await onRefreshVolumes();
      notifyManagedLifecycleDeleted({
        source: "managed-data-delete",
        action: "hard-delete",
        representationId,
        volumeId: volume.id,
        sourceReset: (result as any)?.source_reset,
      });

      if (
        selectedVolume?.id === volume.id ||
        (selectedVolume as any)?.msi_representation_id === representationId
      ) {
        onClearSelectedVolume();
      }

      return;
    }

    const isIndexedSegyRecord = volume.read_mode === "indexed_segy";

    const confirmed = window.confirm(
      isIndexedSegyRecord
        ? `Delete indexed dataset "${name}"?\n\nThis will remove the indexed SEG-Y registry entry and any app-owned optimized Zarr cache artifacts. The original source SEG-Y file will be preserved.`
        : `Delete converted dataset "${name}"?\n\nThis will remove the Zarr folder, sidecar header files, and registry entry. The original source SEG-Y file will be preserved.`
    );

    if (!confirmed) return;

    await deleteVolume(volume.id);
    await onRefreshVolumes();
    notifyManagedLifecycleDeleted({
      source: "managed-data-delete",
      action: "legacy-delete",
      volumeId: volume.id,
    });

    // Deleted selected dataset; clearing viewer.
    if (selectedVolume?.id === volume.id) {
      onClearSelectedVolume();
    }
  };

  return { handleDelete };
}
