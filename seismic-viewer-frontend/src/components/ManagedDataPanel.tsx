import { useEffect, useMemo, useState } from "react";
import { Database, Edit3, Eye, Info, Trash2 } from "lucide-react";
import ManagedDataBulkToolbar, {
  getManagedDataRowId,
  managedDataRowMatchesSearch,
} from "./ManagedDataBulkToolbar";
import DocumentDropZone, { type DocumentDropZoneFile } from "./DocumentDropZone";

type ManagedDataPanelProps = {
  visibleVolumes: any[];
  managedDataCollapsed: boolean;
  setManagedDataCollapsed: (value: boolean) => void;
  onRefreshVolumes: () => Promise<void> | void;
  managedDataMaxWidth: number | string;
  selectedVolume: any;
  selectedLoadMode: string | null | undefined;
  getDisplayName: (volume: any) => string;
  isManagedDisplayableDataset: (volume: any) => boolean;
  getSelectedTargets: (volumeId: string) => any;
  setSelectedTarget: (
    volumeId: string,
    target: string,
    checked: boolean,
  ) => void;
  clearSelectedTargets: (volumeId: string) => void;
  loadSelectedTargets: (
    volume: any,
    selectedTargets: any,
    optimizedCacheAvailable: boolean,
  ) => Promise<void> | void;
  viewLoadedDataset: (volume: any) => void;
  unloadFromViewerCatalog: (volume: any) => Promise<void> | void;
  handleRename: (volume: any) => void;
  handleDelete: (volume: any) => Promise<void> | void;
  hasAvailableOptimizedCache: (volume: any) => boolean;
  getShape: (volume: any) => string;
  getDatasetTypeLabel: (volume: any) => string;
  indexedDeleteHelpVolumeId: string | null;
  setIndexedDeleteHelpVolumeId: (volumeId: string | null) => void;
  setDataWorkflowTab: (tab: string) => void;
  viewerModeFilter: "2d" | "3d";
  onOpenSeismicDataInformation?: (volume: any) => void;
};


function firstNonEmpty(...values: unknown[]): string | null {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return null;
}

function compactInfoRecord(record: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(record).filter(([, value]) => {
      if (value === null || value === undefined) return false;
      if (typeof value === "string" && value.trim() === "") return false;
      return true;
    }),
  );
}

function buildManagedInfoVolume(volume: any): any {
  const metadata = volume?.metadata || {};
  const sourceReference =
    volume?.source_reference ||
    metadata?.source_reference ||
    metadata?.source ||
    {};

  const datasetIdentityDetails = compactInfoRecord({
    survey_name: firstNonEmpty(
      volume?.survey_name,
      metadata?.survey_name,
      sourceReference.survey_name,
      metadata?.identity?.survey_name,
      "—",
    ),
    line_name: firstNonEmpty(
      volume?.line_name,
      metadata?.line_name,
      sourceReference.line_name,
      metadata?.identity?.line_name,
    ),
    volume_name: firstNonEmpty(
      volume?.volume_name,
      metadata?.volume_name,
      sourceReference.volume_name,
      metadata?.identity?.volume_name,
    ),
  });

  const sourceFileDetails = compactInfoRecord({
    source_filename: firstNonEmpty(
      sourceReference.filename,
      sourceReference.source_filename,
      volume?.source_filename,
      volume?.source_file,
      volume?.filename,
      volume?.name,
      volume?.display_name,
    ),
    source_repository_id: firstNonEmpty(
      sourceReference.repository_id,
      volume?.repository_id,
      metadata?.repository_id,
    ),
    source_package_id: firstNonEmpty(
      sourceReference.package_id,
      volume?.package_id,
      metadata?.package_id,
    ),
    source_line_id: firstNonEmpty(
      sourceReference.line_id,
      volume?.line_id,
      metadata?.line_id,
    ),
    source_segy_file_id: firstNonEmpty(
      sourceReference.source_segy_file_id,
      sourceReference.segy_file_id,
      volume?.source_segy_file_id,
      metadata?.source_segy_file_id,
    ),
    source_relative_path: firstNonEmpty(
      sourceReference.relative_path,
      sourceReference.source_relative_path,
      volume?.relative_path,
      metadata?.source_relative_path,
    ),
    source_path: firstNonEmpty(
      sourceReference.source_path,
      sourceReference.input_path,
      sourceReference.path,
      volume?.source_path,
      metadata?.source_path,
    ),
    source_system: firstNonEmpty(
      sourceReference.source_system,
      volume?.source,
      volume?.registry_source,
    ),
  });

  const managedRepresentationDetails = compactInfoRecord({
    msi_dataset_id: firstNonEmpty(volume?.msi_dataset_id, sourceReference.msi_dataset_id),
    msi_representation_id: firstNonEmpty(volume?.msi_representation_id, sourceReference.msi_representation_id),
    physical_volume_id: firstNonEmpty(volume?.physical_volume_id, sourceReference.volume_id, volume?.id),
    conversion_job_id: firstNonEmpty(sourceReference.job_id, volume?.job_id, metadata?.job_id),
    zarr_url: firstNonEmpty(volume?.zarr_url, sourceReference.zarr_url, metadata?.zarr_url),
    storage_uri: firstNonEmpty(volume?.storage_uri, sourceReference.storage_uri, metadata?.storage_uri),
    dataset_type: firstNonEmpty(volume?.dataset_type, metadata?.dataset_type),
    representation_type: firstNonEmpty(volume?.representation_type, metadata?.representation?.representation_type),
    viewer_mode: firstNonEmpty(volume?.viewer_mode, metadata?.representation?.viewer_mode),
    loaded_state: Boolean(volume?.is_loaded) ? "loaded" : "unloaded",
  });

  return {
    ...volume,
    dataset_identity_details: datasetIdentityDetails,
    source_file_details: sourceFileDetails,
    managed_representation_details: managedRepresentationDetails,
    metadata: {
      ...metadata,
      managed_data_info: {
        dataset_identity: datasetIdentityDetails,
        managed_representation: managedRepresentationDetails,
        source_file: sourceFileDetails,
      },
    },
  };
}

const MD_SELECT_COLUMN_WIDTH = 46;
const MD_NAME_COLUMN_DEFAULT_WIDTH = 578;
const MD_SURVEY_COLUMN_WIDTH = 168;
const MD_GEOMETRY_COLUMN_WIDTH = 98;
const MD_STATUS_COLUMN_WIDTH = 98;
const MD_AVAILABLE_COLUMN_WIDTH = 98;
const MD_ACTIONS_COLUMN_WIDTH = 360;

export default function ManagedDataPanel({
  visibleVolumes,
  managedDataCollapsed,
  setManagedDataCollapsed,
  onRefreshVolumes,
  managedDataMaxWidth,
  selectedVolume,
  selectedLoadMode,
  getDisplayName,
  isManagedDisplayableDataset,
  getSelectedTargets,
  setSelectedTarget,
  clearSelectedTargets,
  loadSelectedTargets,
  viewLoadedDataset,
  unloadFromViewerCatalog,
  handleRename,
  handleDelete,
  hasAvailableOptimizedCache,
  getShape,
  getDatasetTypeLabel,
  indexedDeleteHelpVolumeId,
  setIndexedDeleteHelpVolumeId,
  setDataWorkflowTab,
  viewerModeFilter,
  onOpenSeismicDataInformation,
}: ManagedDataPanelProps) {
  const [groupBy, setGroupBy] = useState<
    "line_or_volume_name" | "survey_name" | "data_type" | "date_created"
  >("line_or_volume_name");
  const [managedDataSearchText, setManagedDataSearchText] = useState("");
  const [selectedManagedDataIds, setSelectedManagedDataIds] = useState<Record<string, boolean>>({});
  const [bulkDeleteBusy, setBulkDeleteBusy] = useState(false);
  const [bulkDeleteMessage, setBulkDeleteMessage] = useState<string | null>(null);
  const [selectedManagedDataAction, setSelectedManagedDataAction] = useState<"load" | "unload" | "add_documents" | "delete">("load");
  const [addDocumentsOpen, setAddDocumentsOpen] = useState(false);
  const [addDocumentsFiles, setAddDocumentsFiles] = useState<DocumentDropZoneFile[]>([]);
  const [addDocumentsScopeKind, setAddDocumentsScopeKind] = useState<"selected_data" | "survey">("selected_data");
  const [addDocumentsDocumentType, setAddDocumentsDocumentType] = useState("unknown");
  const [addDocumentsBusy, setAddDocumentsBusy] = useState(false);
  const [addDocumentsMessage, setAddDocumentsMessage] = useState<string | null>(null);
  const [managedDataQueryRows, setManagedDataQueryRows] = useState<any[]>([]);
  const [managedDataQueryTotalCount, setManagedDataQueryTotalCount] = useState(0);
  const [managedDataQueryLimit, setManagedDataQueryLimit] = useState(100);
  const [managedDataQueryOffset, setManagedDataQueryOffset] = useState(0);
  const [managedDataQueryLoading, setManagedDataQueryLoading] = useState(false);
  const [managedDataQueryError, setManagedDataQueryError] = useState<string | null>(null);
  const [managedDataQueryRefreshToken, setManagedDataQueryRefreshToken] = useState(0);
  const [expandedManagedDataNameRowId, setExpandedManagedDataNameRowId] = useState<string | null>(null);

  useEffect(() => {
    const handleManagedDataUpdated = () => {
      setManagedDataQueryRefreshToken((value) => value + 1);
      void onRefreshVolumes();
    };

    window.addEventListener(
      "multiviewer:managed-data-updated",
      handleManagedDataUpdated,
    );
    return () => {
      window.removeEventListener(
        "multiviewer:managed-data-updated",
        handleManagedDataUpdated,
      );
    };
  }, [onRefreshVolumes]);

  useEffect(() => {
    setManagedDataQueryOffset(0);
    setSelectedManagedDataIds({});
    setBulkDeleteMessage(null);
  }, [viewerModeFilter]);

  const getManagedDataSortBy = (): string => {
    if (groupBy === "line_or_volume_name") {
      return viewerModeFilter === "2d" ? "line_name" : "volume_name";
    }
    if (groupBy === "survey_name") return "survey_name";
    if (groupBy === "data_type") return "dataset_type";
    if (groupBy === "date_created") return "created_at";
    return viewerModeFilter === "2d" ? "line_name" : "volume_name";
  };

  useEffect(() => {
    const controller = new AbortController();
    const query = managedDataSearchText.trim();
    const sortBy = getManagedDataSortBy();
    const sortDir = groupBy === "date_created" ? "desc" : "asc";

    const timer = window.setTimeout(async () => {
      setManagedDataQueryLoading(true);
      setManagedDataQueryError(null);

      try {
        const params = new URLSearchParams();
        if (query) params.set("q", query);
        params.set("limit", String(managedDataQueryLimit));
        params.set("offset", String(managedDataQueryOffset));
        params.set("viewer_mode", viewerModeFilter);
        params.set("sort_by", sortBy);
        params.set("sort_dir", sortDir);

        const response = await fetch(`/api/managed-data/query?${params.toString()}`, {
          signal: controller.signal,
        });
        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
          throw new Error(payload?.detail || `Managed Data query failed: ${response.status}`);
        }

        setManagedDataQueryRows(Array.isArray(payload?.rows) ? payload.rows : []);
        setManagedDataQueryTotalCount(Number(payload?.total_count || 0));
      } catch (err: any) {
        if (err?.name !== "AbortError") {
          console.error("Managed Data enterprise query failed", err);
          setManagedDataQueryRows([]);
          setManagedDataQueryTotalCount(0);
          setManagedDataQueryError(err?.message || "Managed Data query failed.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setManagedDataQueryLoading(false);
        }
      }
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [
    managedDataSearchText,
    groupBy,
    managedDataQueryLimit,
    managedDataQueryOffset,
    managedDataQueryRefreshToken,
    viewerModeFilter,
  ]);

  const getVolumeSearchText = (volume: any): string => {
    const parts = [
      volume?.survey_name,
      volume?.survey,
      volume?.metadata?.survey_name,
      volume?.metadata?.survey,
      volume?.normalized_metadata?.survey_name,
      volume?.normalized_metadata?.identity?.survey_name,
      volume?.source_file,
      volume?.source_filename,
      volume?.filename,
      volume?.name,
      volume?.display_name,
    ];
    return parts.filter(Boolean).join(" ").toLowerCase();
  };

  const getSurveyDisplayName = (volume: any): string => {
    return firstNonEmpty(
      volume?.survey_name,
      volume?.metadata?.survey_name,
      volume?.metadata?.source_reference?.survey_name,
      volume?.normalized_metadata?.survey_name,
      volume?.normalized_metadata?.identity?.survey_name,
    ) || "—";
  };

  const getSurveySortKey = (volume: any): string => {
    const explicit =
      volume?.survey_name ||
      volume?.survey ||
      volume?.metadata?.survey_name ||
      volume?.metadata?.survey ||
      volume?.normalized_metadata?.survey_name ||
      volume?.normalized_metadata?.identity?.survey_name;

    if (explicit) return String(explicit).toLowerCase();

    const text = getVolumeSearchText(volume);
    const f3 = text.match(/\bf3\b|f3[_\s-]/i);
    if (f3) return "f3";

    const surveyLike = text.match(/([a-z]{1,4}\d{2,4}[a-z]?\d{0,4})/i);
    if (surveyLike) return surveyLike[1].toLowerCase();

    return getDisplayName(volume).toLowerCase();
  };

  const getDataTypeSortKey = (volume: any): string => {
    if (volume?.read_mode === "indexed_segy") {
      return hasAvailableOptimizedCache(volume)
        ? "01_indexed_segy_fast_cache"
        : "02_indexed_segy_preview";
    }

    const datasetType = String(volume?.dataset_type || "").toLowerCase();

    if (datasetType === "3d_volume") return "03_3d_zarr";
    if (datasetType === "2d_line") return "04_2d_line";
    if (datasetType === "2d_survey") return "05_2d_survey";

    return datasetType || "99_unknown";
  };

  const getDateSortKey = (volume: any): number => {
    const raw =
      volume?.created_at ||
      volume?.created ||
      volume?.metadata?.created_at ||
      volume?.updated_at ||
      volume?.updated ||
      volume?.metadata?.updated_at;

    if (!raw) return 0;

    const parsed = Date.parse(String(raw));
    return Number.isFinite(parsed) ? parsed : 0;
  };

  const searchedManagedVolumes = managedDataQueryRows;

  const visibleManagedDataIds = useMemo(() => {
    return searchedManagedVolumes
      .map((volume) => getManagedDataRowId(volume))
      .filter((id): id is string => Boolean(id));
  }, [searchedManagedVolumes]);

  const selectedManagedDataIdList = useMemo(() => {
    return Object.entries(selectedManagedDataIds)
      .filter(([, selected]) => selected)
      .map(([id]) => id);
  }, [selectedManagedDataIds]);

  const selectedManagedDataRows = useMemo(() => {
    const selected = new Set(selectedManagedDataIdList);
    return managedDataQueryRows.filter((row) => selected.has(getManagedDataRowId(row)));
  }, [managedDataQueryRows, selectedManagedDataIdList]);

  const selectedSurveyName = useMemo(() => {
    for (const row of selectedManagedDataRows) {
      const survey = getSurveyDisplayName(row);
      if (survey && survey !== "—") return survey;
    }
    return "";
  }, [selectedManagedDataRows]);

  const addDocumentTargetRows = useMemo(() => {
    if (addDocumentsScopeKind !== "survey" || !selectedSurveyName) {
      return selectedManagedDataRows;
    }
    return managedDataQueryRows.filter((row) => getSurveyDisplayName(row) === selectedSurveyName);
  }, [addDocumentsScopeKind, managedDataQueryRows, selectedManagedDataRows, selectedSurveyName]);

  const selectedVisibleManagedDataCount = visibleManagedDataIds.filter(
    (id) => selectedManagedDataIds[id],
  ).length;

  const allVisibleManagedDataSelected =
    visibleManagedDataIds.length > 0 &&
    selectedVisibleManagedDataCount === visibleManagedDataIds.length;

  const hasNextManagedDataPage =
    managedDataQueryOffset + managedDataQueryLimit < managedDataQueryTotalCount;

  const buildManagedDataQueryUrl = (offsetOverride?: number): string => {
    const query = managedDataSearchText.trim();
    const sortBy = getManagedDataSortBy();
    const sortDir = groupBy === "date_created" ? "desc" : "asc";

    const params = new URLSearchParams();
    if (query) params.set("q", query);
    params.set("limit", String(managedDataQueryLimit));
    params.set("offset", String(offsetOverride ?? managedDataQueryOffset));
    params.set("viewer_mode", viewerModeFilter);
    params.set("sort_by", sortBy);
    params.set("sort_dir", sortDir);

    return `/api/managed-data/query?${params.toString()}`;
  };

  const loadManagedDataQueryNow = async (offsetOverride?: number): Promise<void> => {
    setManagedDataQueryLoading(true);
    setManagedDataQueryError(null);

    try {
      const response = await fetch(buildManagedDataQueryUrl(offsetOverride));
      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(payload?.detail || `Managed Data query failed: ${response.status}`);
      }

      setManagedDataQueryRows(Array.isArray(payload?.rows) ? payload.rows : []);
      setManagedDataQueryTotalCount(Number(payload?.total_count || 0));
    } catch (err: any) {
      console.error("Managed Data enterprise query failed", err);
      setManagedDataQueryRows([]);
      setManagedDataQueryTotalCount(0);
      setManagedDataQueryError(err?.message || "Managed Data query failed.");
    } finally {
      setManagedDataQueryLoading(false);
    }
  };

  const refreshManagedDataQuery = () => {
    setManagedDataQueryRefreshToken((value) => value + 1);
  };

  const toggleManagedDataSelection = (rowId: string) => {
    if (!rowId || bulkDeleteBusy) return;
    setBulkDeleteMessage(null);
    setSelectedManagedDataIds((current) => ({
      ...current,
      [rowId]: !current[rowId],
    }));
  };

  const toggleVisibleManagedDataRows = (checked: boolean) => {
    setBulkDeleteMessage(null);
    setSelectedManagedDataIds((current) => {
      const next = { ...current };

      for (const rowId of visibleManagedDataIds) {
        if (checked) {
          next[rowId] = true;
        } else {
          delete next[rowId];
        }
      }

      return next;
    });
  };

  const selectedManagedDataActionLabel = () => {
    if (selectedManagedDataAction === "load") return "Load selected to Viewer";
    if (selectedManagedDataAction === "unload") return "Unload selected from Viewer";
    return "Delete selected records/artifacts";
  };

  const handleBulkViewerStateAction = async (action: "load" | "unload") => {
    const representationIds = selectedManagedDataIdList;

    if (!representationIds.length) {
      setBulkDeleteMessage("No Managed Data rows selected.");
      return;
    }

    const endpoint = action === "load"
      ? "/api/managed-data/bulk/load-selected"
      : "/api/managed-data/bulk/unload-selected";
    const actionText = action === "load" ? "load" : "unload";

    setBulkDeleteBusy(true);
    setBulkDeleteMessage(null);

    try {
      const dryRunResponse = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          // MD_DELETE_SCOPE_FINAL_UI
          representation_ids: representationIds,
          dry_run: true,
          delete_scope: representationIds.length === 1 ? "single" : "selected",
          confirm_count: representationIds.length,
        }),
      });

      const dryRunPayload = await dryRunResponse.json().catch(() => ({}));

      if (!dryRunResponse.ok) {
        const detail = dryRunPayload?.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : detail?.message || `Bulk ${actionText} dry-run failed: ${dryRunResponse.status}`,
        );
      }

      const actionableCount = Number(dryRunPayload?.actionable_count ?? representationIds.length);
      const targets = Array.isArray(dryRunPayload?.targets) ? dryRunPayload.targets : [];
      const previewNames = targets
        .map((target: any) => target?.display_name || target?.representation_id)
        .filter(Boolean)
        .slice(0, 10);
      const extraCount = Math.max(0, targets.length - previewNames.length);

      const confirmText = [
        `${selectedManagedDataActionLabel()} for ${representationIds.length} selected Managed Data record(s)?`,
        "",
        `Actionable records: ${actionableCount}`,
        "This changes viewer availability only. MSI records and artifacts are retained.",
        previewNames.length ? "" : null,
        previewNames.length ? "Targets:" : null,
        ...previewNames.map((name) => `- ${name}`),
        extraCount ? `...and ${extraCount} more` : null,
      ]
        .filter((line): line is string => line !== null)
        .join("\n");

      if (!window.confirm(confirmText)) {
        setBulkDeleteMessage(`Bulk ${actionText} cancelled.`);
        return;
      }

      const actionResponse = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          // MD_DELETE_SCOPE_FINAL_UI
          representation_ids: representationIds,
          dry_run: false,
          delete_scope: representationIds.length === 1 ? "single" : "selected",
          confirm_count: representationIds.length,
        }),
      });

      const actionPayload = await actionResponse.json().catch(() => ({}));

      if (!actionResponse.ok || actionPayload?.ok === false) {
        const detail = actionPayload?.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : detail?.message ||
                `Bulk ${actionText} failed. Failed count: ${actionPayload?.failed_count ?? "unknown"}`,
        );
      }

      setBulkDeleteMessage(
        `${selectedManagedDataActionLabel()} completed for ${actionPayload?.succeeded_count ?? representationIds.length} selected record(s).`,
      );
      await onRefreshVolumes();
      refreshManagedDataQuery();
      window.dispatchEvent(new CustomEvent("multiviewer:managed-data-updated"));
    } catch (err: any) {
      console.error(`Bulk Managed Data ${actionText} failed`, err);
      setBulkDeleteMessage(err?.message || `Bulk Managed Data ${actionText} failed.`);
    } finally {
      setBulkDeleteBusy(false);
    }
  };

  const handleBulkDeleteManagedData = async () => {
    const representationIds = selectedManagedDataIdList;

    if (!representationIds.length) {
      setBulkDeleteMessage("No Managed Data rows selected.");
      return;
    }

    setBulkDeleteBusy(true);
    setBulkDeleteMessage(null);

    try {
      const dryRunResponse = await fetch("/api/managed-data/bulk/delete-selected", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          representation_ids: representationIds,
          dry_run: true,
        }),
      });

      const dryRunPayload = await dryRunResponse.json().catch(() => ({}));

      if (!dryRunResponse.ok) {
        const detail = dryRunPayload?.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : detail?.message || `Bulk delete dry-run failed: ${dryRunResponse.status}`,
        );
      }

      const targets = Array.isArray(dryRunPayload?.targets)
        ? dryRunPayload.targets
        : [];
      const previewNames = targets
        .map((target: any) => target?.display_name || target?.representation_id)
        .filter(Boolean)
        .slice(0, 10);
      const extraCount = Math.max(0, targets.length - previewNames.length);

      const confirmText = [
        `Delete ${representationIds.length} selected Managed Data record(s)?`,
        "",
        "This deletes only the explicitly selected Managed Data representation(s). It will not traverse source-candidate graphs or delete sibling rows.",
        "Original source SEG-Y files and unselected Managed Data rows are preserved.",
        previewNames.length ? "" : null,
        previewNames.length ? "Targets:" : null,
        ...previewNames.map((name) => `- ${name}`),
        extraCount ? `...and ${extraCount} more` : null,
      ]
        .filter((line): line is string => line !== null)
        .join("\n");

      if (!window.confirm(confirmText)) {
        setBulkDeleteMessage("Bulk delete cancelled.");
        return;
      }

      const deleteResponse = await fetch("/api/managed-data/bulk/delete-selected", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          representation_ids: representationIds,
          dry_run: false,
        }),
      });

      const deletePayload = await deleteResponse.json().catch(() => ({}));

      if (!deleteResponse.ok || deletePayload?.ok === false) {
        const detail = deletePayload?.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : detail?.message ||
                `Bulk delete failed. Failed count: ${deletePayload?.failed_count ?? "unknown"}`,
        );
      }

      const deletedCount = Number(deletePayload?.deleted_count ?? representationIds.length);

      setBulkDeleteMessage(
        `Deleted ${deletedCount} selected Managed Data record(s).`,
      );

      // MD_BULK_STRUCTURE_2
      // Bulk delete state is owned by the backend query result. Do not wait for a
      // remount/navigation cycle to reconcile the table. Clear selection, remove
      // the deleted rows optimistically, then immediately reload the authoritative
      // Managed Data query from the backend using the current filter/sort/page.
      const nextTotalCount = Math.max(0, managedDataQueryTotalCount - deletedCount);
      const nextOffset = Math.max(
        0,
        Math.min(managedDataQueryOffset, Math.max(0, nextTotalCount - managedDataQueryLimit)),
      );

      setSelectedManagedDataIds({});
      setManagedDataQueryRows((currentRows) =>
        currentRows.filter((row: any) => {
          const rowId = getManagedDataRowId(row);
          return !rowId || !representationIds.includes(rowId);
        }),
      );
      setManagedDataQueryTotalCount(nextTotalCount);
      setManagedDataQueryOffset(nextOffset);

      await onRefreshVolumes();
      await loadManagedDataQueryNow(nextOffset);
      refreshManagedDataQuery();
      window.dispatchEvent(new CustomEvent("multiviewer:managed-data-updated"));
    } catch (err: any) {
      console.error("Bulk Managed Data delete failed", err);
      setBulkDeleteMessage(err?.message || "Bulk Managed Data delete failed.");
    } finally {
      setBulkDeleteBusy(false);
    }
  };

  const handleAddDocumentsSubmit = async () => {
    const pendingFiles = addDocumentsFiles.filter((entry) => entry.status !== "rejected");
    if (!pendingFiles.length) {
      setAddDocumentsMessage("Add at least one supported document file.");
      return;
    }

    const targetRows = addDocumentTargetRows;
    const targetIds = targetRows
      .map((row) => getManagedDataRowId(row))
      .filter((id): id is string => Boolean(id));

    if (!targetIds.length) {
      setAddDocumentsMessage("No Managed Data targets are selected.");
      return;
    }

    setAddDocumentsBusy(true);
    setAddDocumentsMessage(null);

    try {
      const formData = new FormData();
      pendingFiles.forEach((entry) => formData.append("files", entry.file, entry.name));
      formData.append("target_ids", JSON.stringify(targetIds));
      formData.append("scope_kind", addDocumentsScopeKind);
      formData.append("attachment_scope", addDocumentsScopeKind === "survey" ? "survey" : "dataset");
      formData.append("relationship_type", addDocumentsScopeKind === "survey" ? "survey_wide" : "line_volume_specific");
      formData.append("survey_name", addDocumentsScopeKind === "survey" ? selectedSurveyName : "");
      formData.append("document_type", addDocumentsDocumentType || "unknown");
      formData.append("document_role", "supporting_document");
      formData.append("source", "manual_upload");

      const response = await fetch("/api/msi/document-attachments/upload", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) {
        const detail = payload?.detail || payload?.error;
        throw new Error(typeof detail === "string" ? detail : detail?.message || `Add Documents failed: ${response.status}`);
      }

      const uploadedCount = Number(payload?.uploaded_documents?.length ?? payload?.documents?.length ?? pendingFiles.length);
      const attachedCount = Number(payload?.attached_dataset_count ?? payload?.target_count ?? targetIds.length);
      const rejectedCount = Number(payload?.rejected_documents?.length ?? 0);
      const suffix = rejectedCount ? ` (${rejectedCount} rejected)` : "";
      setAddDocumentsMessage(`Uploaded ${uploadedCount} document(s) and attached to ${attachedCount} target(s).${suffix}`);
      setBulkDeleteMessage(`Uploaded ${uploadedCount} document(s) and attached to ${attachedCount} Managed Data target(s).${suffix}`);
      setAddDocumentsFiles([]);
      setAddDocumentsOpen(false);
      refreshManagedDataQuery();
    } catch (err: any) {
      console.error("Add Documents failed", err);
      setAddDocumentsMessage(err?.message || "Add Documents failed.");
    } finally {
      setAddDocumentsBusy(false);
    }
  };

  const handleApplyManagedDataBulkAction = async () => {
    if (selectedManagedDataAction === "load") {
      await handleBulkViewerStateAction("load");
      return;
    }

    if (selectedManagedDataAction === "unload") {
      await handleBulkViewerStateAction("unload");
      return;
    }

    if (selectedManagedDataAction === "add_documents") {
      setAddDocumentsMessage(null);
      setAddDocumentsFiles([]);
      setAddDocumentsScopeKind("selected_data");
      setAddDocumentsOpen(true);
      return;
    }

    await handleBulkDeleteManagedData();
  };

  return (
    <section
      className={`collapsible-pane managed-data-pane ${managedDataCollapsed ? "collapsed" : "expanded"}`}
    >
      <div className="collapsible-pane-header">
        <div>
          <p>
            {managedDataQueryTotalCount} item{managedDataQueryTotalCount === 1 ? "" : "s"}{" "}
            in the {viewerModeFilter === "3d" ? "3D" : "2D"} Managed Data query.
          </p>
        </div>

        <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <label
            className="mv-type-property-label"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>Sort by</span>
            <select
              value={groupBy}
              onChange={(event) =>
                setGroupBy(event.currentTarget.value as typeof groupBy)
              }
              className="collapsible-pane-toggle md-control-select"
              style={{
                padding: "4px 8px",
              }}
            >
              <option value="line_or_volume_name">{viewerModeFilter === "2d" ? "Line name" : "Volume name"}</option>
              <option value="survey_name">Survey name</option>
              <option value="data_type">Data type</option>
              <option value="date_created">Date created</option>
            </select>
          </label>

          <button
            type="button"
            onClick={async () => {
              try {
                refreshManagedDataQuery();
                await onRefreshVolumes();
              } catch (err) {
                console.error("Failed to refresh Managed Data volumes", err);
              }
            }}
            title="Refresh Managed Data query"
            className="collapsible-pane-toggle md-control-button md-utility-button"
          >
            Refresh
          </button>

          <button
            type="button"
            onClick={() => setManagedDataCollapsed(!managedDataCollapsed)}
            className="collapsible-pane-toggle md-control-button md-utility-button"
          >
            {managedDataCollapsed ? "Expand" : "Collapse"}
          </button>
        </div>
      </div>

      {!managedDataCollapsed && (
        <div
          className="managed-data-scroll-area"
          style={{
            maxWidth: managedDataMaxWidth,
            overflowX: "auto",
            overflowY: "visible",
            minWidth: 0,
          }}
        >
          <ManagedDataBulkToolbar
            searchText={managedDataSearchText}
            onSearchTextChange={(value) => {
              setManagedDataSearchText(value);
              setManagedDataQueryOffset(0);
              setBulkDeleteMessage(null);
            }}
            totalCount={managedDataQueryTotalCount}
            visibleCount={searchedManagedVolumes.length}
            selectedCount={selectedManagedDataIdList.length}
            bulkDeleteBusy={bulkDeleteBusy}
            bulkDeleteMessage={bulkDeleteMessage}
            queryLoading={managedDataQueryLoading}
            queryError={managedDataQueryError}
            pageOffset={managedDataQueryOffset}
            pageLimit={managedDataQueryLimit}
            hasNextPage={hasNextManagedDataPage}
            onPreviousPage={() => {
              setManagedDataQueryOffset((value) =>
                Math.max(0, value - managedDataQueryLimit),
              );
            }}
            onNextPage={() => {
              if (hasNextManagedDataPage) {
                setManagedDataQueryOffset((value) => value + managedDataQueryLimit);
              }
            }}
            onPageLimitChange={(limit) => {
              setManagedDataQueryLimit(limit);
              setManagedDataQueryOffset(0);
            }}
            selectedAction={selectedManagedDataAction}
            onSelectedActionChange={(value) => {
              if (value === "load" || value === "unload" || value === "add_documents" || value === "delete") {
                setSelectedManagedDataAction(value);
                setBulkDeleteMessage(null);
              }
            }}
            onApplySelectedAction={handleApplyManagedDataBulkAction}
          />

          <div className="data-manager-table-wrap">
            <table
              className="data-manager-table managed-data-table"
              style={{
                minWidth:
                  MD_NAME_COLUMN_DEFAULT_WIDTH +
                  MD_SELECT_COLUMN_WIDTH +
                  MD_SURVEY_COLUMN_WIDTH +
                  MD_GEOMETRY_COLUMN_WIDTH +
                  MD_STATUS_COLUMN_WIDTH +
                  MD_AVAILABLE_COLUMN_WIDTH +
                  MD_ACTIONS_COLUMN_WIDTH,
                tableLayout: "fixed",
                width: "100%",
              }}
            >
              <colgroup>
                <col className="md-col-select" style={{ width: MD_SELECT_COLUMN_WIDTH }} />
                <col className="md-col-name" style={{ width: MD_NAME_COLUMN_DEFAULT_WIDTH }} />
                <col className="md-col-survey" style={{ width: MD_SURVEY_COLUMN_WIDTH }} />
                <col className="md-col-geometry" style={{ width: MD_GEOMETRY_COLUMN_WIDTH }} />
                <col className="md-col-status" style={{ width: MD_STATUS_COLUMN_WIDTH }} />
                <col className="md-col-available" style={{ width: MD_AVAILABLE_COLUMN_WIDTH }} />
                <col className="md-col-spacer" />
                <col className="md-col-actions" style={{ width: MD_ACTIONS_COLUMN_WIDTH }} />
              </colgroup>
              <thead>
                <tr>
                  <th style={{ width: 46, textAlign: "center" }}>
                    <input
                      type="checkbox"
                      checked={allVisibleManagedDataSelected}
                      disabled={!searchedManagedVolumes.length || bulkDeleteBusy || managedDataQueryLoading}
                      onChange={(event) => toggleVisibleManagedDataRows(event.currentTarget.checked)}
                      aria-label="Select or clear all Managed Data rows visible on this page"
                      title="Select or clear all rows visible on this page"
                    />
                  </th>
                  <th className="md-col-name">Name</th>
                  <th className="md-col-survey">Survey</th>
                  <th className="md-col-geometry">Geometry</th>
                  <th className="md-col-status">Status</th>
                  <th className="md-col-available">Available</th>
                  <th className="md-col-spacer" aria-hidden="true"></th>
                  <th className="md-col-actions"><span className="md-actions-heading">Actions</span></th>
                </tr>
              </thead>

              <tbody>
                {searchedManagedVolumes.map((volume) => {
                  const displayName = getDisplayName(volume);
                  const displayable = isManagedDisplayableDataset(volume);
                  const loaded = selectedVolume?.id === volume.id;
                  const optimizedCacheAvailable =
                    hasAvailableOptimizedCache(volume);
                  const isIndexedSegy = volume.read_mode === "indexed_segy";
                  const rowLoadTargets = {
                    preview: true,
                    optimized_cache: isIndexedSegy && optimizedCacheAvailable,
                  };
                  const isMsiManaged =
                    volume.source === "msi" ||
                    volume.registry_source === "msi" ||
                    Boolean(volume.msi_representation_id);
                  const msiLoaded = Boolean(volume.is_loaded);
                  const loadDisabled = isMsiManaged
                    ? !displayable || msiLoaded
                    : !displayable || !volume.hidden;
                  const viewDisabled = isMsiManaged
                    ? !displayable || !msiLoaded
                    : !displayable || volume.hidden;
                  const unloadDisabled = isMsiManaged
                    ? !msiLoaded
                    : volume.hidden;
                  const managedDataRowId = getManagedDataRowId(volume);
                  const rowSelected = Boolean(
                    managedDataRowId && selectedManagedDataIds[managedDataRowId],
                  );
                  const nameExpandKey = String(managedDataRowId || volume.id || displayName);
                  const nameExpanded = expandedManagedDataNameRowId === nameExpandKey;

                  return (
                    <tr
                      key={volume.id}
                      className={loaded ? "selected-row" : ""}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={rowSelected}
                          disabled={!managedDataRowId || bulkDeleteBusy}
                          onChange={() => {
                            if (managedDataRowId) {
                              toggleManagedDataSelection(managedDataRowId);
                            }
                          }}
                          aria-label={`Select ${displayName}`}
                        />
                      </td>

                      <td className="md-col-name">
                        <div className="volume-name">
                          <Database className="md-name-storage-icon" size={14} strokeWidth={2} aria-hidden="true" />
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              setExpandedManagedDataNameRowId((current) =>
                                current === nameExpandKey ? null : nameExpandKey,
                              );
                            }}
                            title={nameExpanded ? "Click to collapse name" : "Click to expand full name"}
                            style={{
                              border: 0,
                              background: "transparent",
                              color: "inherit",
                              cursor: "pointer",
                              font: "inherit",
                              margin: 0,
                              maxWidth: "100%",
                              minWidth: 0,
                              overflow: nameExpanded ? "visible" : "hidden",
                              overflowWrap: "anywhere",
                              padding: 0,
                              textAlign: "left",
                              textOverflow: nameExpanded ? "clip" : "ellipsis",
                              whiteSpace: nameExpanded ? "normal" : "nowrap",
                            }}
                          >
                            {displayName}
                          </button>
                        </div>
                        <div className="volume-id">{volume.id}</div>
                      </td>

                      <td className="md-col-survey" title={getSurveyDisplayName(volume)}>{getSurveyDisplayName(volume)}</td>
                      <td className="md-col-geometry">{getDatasetTypeLabel(volume)}</td>

                      <td className="md-col-status">
                        {volume.hidden ? (
                          <span className="status-pill hidden">Unloaded</span>
                        ) : volume.dataset_type === "2d_line" ? (
                          <span className="status-pill ready">Ready 2D</span>
                        ) : volume.dataset_type === "2d_survey" ? (
                          <span className="status-pill ready">
                            Ready Survey
                          </span>
                        ) : displayable ? (
                          <span className="status-pill ready">Ready 3D</span>
                        ) : (
                          <span className="status-pill warning">
                            Unsupported
                          </span>
                        )}
                      </td>

                      <td className="md-col-available">
                        <span className="md-available-text">
                          {isIndexedSegy
                            ? optimizedCacheAvailable
                              ? "Indexed + Fast Cache"
                              : "Indexed Preview"
                            : "Zarr"}
                        </span>
                      </td>

                      <td className="md-col-spacer" aria-hidden="true"></td>

                      <td className="md-col-actions">
                        <div
                          className="data-actions"
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "flex-end",
                            gap: 6,
                            flexWrap: "nowrap",
                          }}
                        >
                          <button
                            className="md-row-action md-row-action-load"
                            onClick={async () => {
                              await loadSelectedTargets(
                                volume,
                                rowLoadTargets,
                                optimizedCacheAvailable,
                              );
                              refreshManagedDataQuery();
                            }}
                            disabled={loadDisabled}
                            title={
                              loadDisabled
                                ? "Already loaded in viewer catalog/dropdown"
                                : "Load into viewer catalog/dropdown"
                            }
                          >
                            Load
                          </button>

                          <button
                            className="md-row-action md-row-action-neutral"
                            onClick={() => viewLoadedDataset(volume)}
                            disabled={viewDisabled}
                            title={
                              viewDisabled
                                ? "Load this dataset before viewing it"
                                : "Open this loaded dataset in the viewer"
                            }
                            aria-label="View loaded dataset"
                          >
                            <Eye size={14} />
                          </button>

                          <button
                            className="md-row-action md-row-action-unload"
                            onClick={async () => {
                              await unloadFromViewerCatalog(volume);
                              refreshManagedDataQuery();
                            }}
                            disabled={unloadDisabled}
                            title={
                              unloadDisabled
                                ? "Already unloaded from viewer catalog/dropdown"
                                : "Unload from viewer catalog/dropdown"
                            }
                          >
                            Unload
                          </button>

                          <button
                            className="md-row-action md-row-action-neutral"
                            onClick={() => onOpenSeismicDataInformation?.(buildManagedInfoVolume(volume))}
                            disabled={!onOpenSeismicDataInformation}
                            title="Open in Seismic Data Information"
                            aria-label="Open in Seismic Data Information"
                          >
                            <Info size={14} />
                          </button>

                          <button
                            className="md-row-action md-row-action-neutral"
                            onClick={() => handleRename(volume)}
                            title={
                              isMsiManaged
                                ? "Edit MSI-managed dataset display name and descriptive metadata"
                                : "Edit"
                            }
                          >
                            <Edit3 size={14} />
                          </button>

                          {isIndexedSegy ? (
                            <span
                              style={{
                                position: "relative",
                                display: "inline-flex",
                                zIndex:
                                  indexedDeleteHelpVolumeId === volume.id
                                    ? 10000
                                    : "auto",
                              }}
                            >
                              <button
                                type="button"
                                className="md-row-action md-row-action-neutral"
                                onClick={() => {
                                  setIndexedDeleteHelpVolumeId(
                                    indexedDeleteHelpVolumeId === volume.id
                                      ? null
                                      : volume.id,
                                  );
                                }}
                                title="Delete in Source Intake → Advanced Maintenance"
                                aria-label="Indexed data delete help"
                                style={{
                                  borderColor: "#64748b",
                                  color: "#94a3b8",
                                  opacity: 0.85,
                                }}
                              >
                                <Trash2 size={12} />
                              </button>

                              {indexedDeleteHelpVolumeId === volume.id && (
                                <div
                                  className="mv-managed-data-tooltip"
                                  role="tooltip"
                                  style={{
                                    position: "fixed",
                                    right: 48,
                                    top: 160,
                                    zIndex: 999999,
                                    width: 320,
                                    padding: "8px 10px",
                                    textAlign: "left",
                                  }}
                                >
                                  <span>Delete in Source Intake → </span>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setIndexedDeleteHelpVolumeId(null);
                                      setDataWorkflowTab("source-intake");
                                      window.setTimeout(() => {
                                        const el = document.querySelector(
                                          '[data-role="advanced-maintenance-3d"]',
                                        );
                                        if (el instanceof HTMLElement) {
                                          el.scrollIntoView({
                                            behavior: "smooth",
                                            block: "center",
                                          });
                                        }
                                      }, 180);
                                    }}
                                    style={{
                                      border: "none",
                                      background: "transparent",
                                      color: "#93c5fd",
                                      padding: 0,
                                      textDecoration: "underline",
                                      cursor: "pointer",
                                      fontSize: 12,
                                      fontWeight: 700,
                                    }}
                                  >
                                    Advanced Maintenance
                                  </button>
                                </div>
                              )}
                            </span>
                          ) : (
                            <button
                              className="md-row-action md-row-action-delete danger"
                              onClick={async () => {
                                await handleDelete(volume);
                                clearSelectedTargets(volume.id);
                                refreshManagedDataQuery();
                              }}
                              title={
                                isMsiManaged
                                  ? "Delete MSI-managed representation from Managed Data"
                                  : "Delete converted dataset"
                              }
                              disabled={false}
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}

                {searchedManagedVolumes.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty-table">
                      {managedDataSearchText.trim()
                        ? "No Managed Data rows match the current search."
                        : "No converted volumes found."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}


      {addDocumentsOpen && (
        <div
          className="mv-managed-data-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Add Documents to Managed Data"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 99999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
          }}
        >
          <div
            className="mv-managed-data-modal"
            style={{
              width: 620,
              maxWidth: "92vw",
              padding: 18,
            }}
          >
            <h3 className="mv-type-panel-title" style={{ margin: "0 0 8px 0" }}>Add Documents</h3>
            <p className="mv-type-helper" style={{ margin: "0 0 14px 0" }}>
              Attach a supporting document to the selected line/volume, or to all currently listed rows in the same survey.
            </p>

            <DocumentDropZone
              files={addDocumentsFiles}
              onFilesChange={setAddDocumentsFiles}
              disabled={addDocumentsBusy || !addDocumentTargetRows.length}
              allowMultiple={true}
              maxFiles={10}
              maxFileSizeBytes={100 * 1024 * 1024}
              title="Drop documents here"
              helperText={addDocumentTargetRows.length ? "or click to select supporting files" : "Select a document target before adding files."}
            />

            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
              <label className="mv-type-property-label" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <input
                  type="radio"
                  checked={addDocumentsScopeKind === "selected_data"}
                  onChange={() => setAddDocumentsScopeKind("selected_data")}
                />
                Attach to selected line / volume
              </label>
              <label className="mv-type-property-label" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <input
                  type="radio"
                  checked={addDocumentsScopeKind === "survey"}
                  onChange={() => setAddDocumentsScopeKind("survey")}
                  disabled={!selectedSurveyName}
                />
                Attach to entire survey{selectedSurveyName ? `: ${selectedSurveyName}` : ""}
              </label>
            </div>

            <label className="mv-type-property-label" style={{ display: "block", marginBottom: 12 }}>
              Document type
              <select
                className="mv-select"
                value={addDocumentsDocumentType}
                onChange={(event) => setAddDocumentsDocumentType(event.currentTarget.value)}
                style={{
                  display: "block",
                  width: "100%",
                  boxSizing: "border-box",
                  marginTop: 5,
                  padding: "7px 8px",
                }}
              >
                <option value="unknown">Other / Unknown</option>
                <option value="processing_report">Processing Report</option>
                <option value="acquisition_report">Acquisition Report</option>
                <option value="qc_report">QC Report</option>
                <option value="observer_log">Observer Log</option>
                <option value="navigation">Navigation</option>
                <option value="spreadsheet_or_table">Spreadsheet / Table</option>
                <option value="notes">Notes</option>
              </select>
            </label>

            <div
              className="mv-managed-data-target-list"
              style={{
                padding: 10,
                maxHeight: 180,
                overflow: "auto",
                marginBottom: 12,
              }}
            >
              <div style={{ fontWeight: 800, marginBottom: 6 }}>
                Targets: {addDocumentTargetRows.length}
              </div>
              {addDocumentTargetRows.length ? (
                addDocumentTargetRows.slice(0, 40).map((row) => (
                  <div key={getManagedDataRowId(row)} style={{ padding: "3px 0", borderBottom: "1px solid rgba(100,116,139,0.22)" }}>
                    {getDisplayName(row)} <span style={{ opacity: 0.7 }}>({getSurveyDisplayName(row)})</span>
                  </div>
                ))
              ) : (
                <div style={{ opacity: 0.7 }}>No targets selected.</div>
              )}
              {addDocumentTargetRows.length > 40 && <div style={{ marginTop: 6, opacity: 0.7 }}>...and {addDocumentTargetRows.length - 40} more</div>}
            </div>

            {addDocumentsMessage && (
              <div className="mv-managed-data-message" style={{ padding: "6px 8px", marginBottom: 12 }}>
                {addDocumentsMessage}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button
                type="button"
                className="md-control-button"
                onClick={() => {
                  if (!addDocumentsBusy) {
                    setAddDocumentsOpen(false);
                    setAddDocumentsFiles([]);
                  }
                }}
                disabled={addDocumentsBusy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="md-control-button"
                onClick={handleAddDocumentsSubmit}
                disabled={addDocumentsBusy || !addDocumentTargetRows.length || !addDocumentsFiles.some((entry) => entry.status !== "rejected")}
              >
                {addDocumentsBusy ? "Uploading..." : "Upload & Attach"}
              </button>
            </div>
          </div>
        </div>
      )}

    </section>
  );
}
