import React, { useEffect, useMemo, useState } from "react";

type RepositoryRecord = {
  repository_id: string;
  name: string;
  root_path: string;
  status?: string;
  notes?: string;
  source_structure_type?: string | null;
  intended_use?: string | null;
};

type PackageRecord = {
  package_id: string;
  repository_id: string;
  display_name?: string;
  relative_path?: string;
  package_type?: string;
  submitted_segy_count?: number;
  submitted_document_count?: number;
};

type SegyFileRecord = {
  segy_file_id: string;
  repository_id: string;
  package_id?: string;
  filename: string;
  relative_path: string;
  size_bytes?: number;
  conversion_status?: string;
  volume_id?: string | null;
  zarr_url?: string | null;
  job_id?: string | null;
  conversion_error?: string | null;
  candidate_kind?: "3d_volume" | "2d_line" | "unknown" | string;
  candidate_role?: "volume_candidate" | "line_candidate" | "excluded_from_3d_intake" | "review_required" | string;
  classification_source?: string;
  classification_confidence?: "high" | "medium" | "low" | string;
  classification_reasons?: string[];
};

type DocumentRecord = {
  document_id?: string;
  repository_id?: string;
  package_id?: string;
  filename?: string;
  relative_path?: string;
  document_type?: string;
  artifact_bucket?: string;
  artifact_class?: string;
  artifact_subtype?: string;
  classification_confidence?: string;
  size_bytes?: number;
};


type MinimalRepresentationStatus = {
  indexedPreview: string;
  indexedPreviewActionAvailable?: boolean;
  indexedPreviewDatasetId?: string | null;
  optimizedCache: string;
  optimizedCacheActionAvailable?: boolean;
  optimizedCacheDatasetId?: string | null;
  fullZarrConversion: string;
  fullZarrVolumeId?: string | null;
  fullZarrUrl?: string | null;
};


type SourceSegyLifecycleRepresentation = {
  key: "index_preview" | "fast_zarr_cache" | "managed_zarr" | string;
  label: string;
  status_label: string;
  state: string;
  can_create: boolean;
  can_load: boolean;
  can_delete: boolean;
  can_archive: boolean;
  action_url?: string | null;
  delete_url?: string | null;
};

type SourceSegyLifecycleState = {
  status: string;
  source_id?: string;
  mode: string;
  display_name?: string;
  source?: {
    segy_file_id?: string;
    filename?: string;
    source_path_exists?: boolean;
    candidate_kind?: string;
    candidate_role?: string;
  };
  representations: SourceSegyLifecycleRepresentation[];
  monitor: {
    state: string;
    label: string;
    message: string;
  };
  active_job?: {
    job_id?: string;
    action?: string;
    label?: string;
    status?: string;
    progress?: number | null;
    message?: string;
  } | null;
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(
      payload?.detail?.message ||
        payload?.detail ||
        payload?.message ||
        `Request failed: ${response.status}`
    );
  }

  return payload as T;
}

function summarizeLifecycle(payload: SourceSegyLifecycleState): MinimalRepresentationStatus {
  const byKey = new Map(
    (payload.representations || []).map((item) => [item.key, item])
  );

  const indexPreview = byKey.get("index_preview");
  const optimizedCache = byKey.get("fast_zarr_cache");
  const managedZarr = byKey.get("managed_zarr");

  return {
    indexedPreview: indexPreview?.state || "not_created",
    indexedPreviewActionAvailable: !!indexPreview?.can_create,
    indexedPreviewDatasetId: null,
    optimizedCache: optimizedCache?.state || "not_created",
    optimizedCacheActionAvailable: !!optimizedCache?.can_create,
    optimizedCacheDatasetId: null,
    fullZarrConversion: managedZarr?.state || "missing",
    fullZarrVolumeId: null,
    fullZarrUrl: null,
  };
}

function formatBytes(value?: number): string {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

function isActive(status?: string): boolean {
  return status === "queued" || status === "converting";
}

function isConverted(status?: string): boolean {
  return status === "converted" || status === "ready";
}

function statusLabel(status?: string): string {
  if (isConverted(status)) return "Converted";
  if (status === "queued") return "Queued";
  if (status === "converting") return "Converting";
  if (status === "error") return "Error";
  return "Not converted";
}


function edrStatusLabel(value?: string | null, missingLabel = "Not created"): string {
  const status = String(value || "").replaceAll("_", " ").trim().toLowerCase();

  if (!status || status === "not built" || status === "not_built") return missingLabel;
  if (status === "available" || status === "converted" || status === "ready") return "Exists";
  if (status === "reconvert required") return "Reconvert required";
  if (["queued", "converting", "reading index", "validating zarr", "promoting output"].includes(status)) return "In progress";
  if (status === "failed" || status === "error") return "Failed";

  return status.charAt(0).toUpperCase() + status.slice(1);
}

function edrRefreshButtonStyle(enabled: boolean): React.CSSProperties {
  return {
    border: enabled ? "1px solid #64748b" : "1px solid #4b5563",
    borderRadius: 6,
    background: "transparent",
    color: enabled ? "#cbd5e1" : "#71717a",
    padding: "5px 9px",
    fontSize: 11,
    fontWeight: 750,
    cursor: enabled ? "pointer" : "not-allowed",
    width: "fit-content",
    minWidth: 0,
    height: 31,
    textAlign: "center",
    lineHeight: 1.15,
    whiteSpace: "nowrap",
  };
}

function edrActionButtonStyle(enabled: boolean): React.CSSProperties {
  return {
    border: enabled ? "1px solid #60a5fa" : "1px solid #4b5563",
    borderRadius: 6,
    background: "transparent",
    color: enabled ? "#93c5fd" : "#71717a",
    padding: "5px 8px",
    fontSize: 11,
    fontWeight: 750,
    cursor: enabled ? "pointer" : "not-allowed",
    width: 210,
    height: 31,
    textAlign: "left",
    lineHeight: 1.15,
  };
}


function edrProgressOuterStyle(): React.CSSProperties {
  return {
    gridColumn: "1 / span 2",
    width: "100%",
    height: 9,
    border: "1px solid #60a5fa",
    borderRadius: 999,
    background: "transparent",
    overflow: "hidden",
    marginTop: 2,
  };
}

function edrProgressInnerStyle(progress: number): React.CSSProperties {
  return {
    width: `${Math.max(0, Math.min(100, progress))}%`,
    height: "100%",
    background: "rgba(96, 165, 250, 0.55)",
    transition: "width 240ms ease",
  };
}

function edrProgressTextStyle(): React.CSSProperties {
  return {
    gridColumn: "1 / span 2",
    color: "#94a3b8",
    fontSize: 11,
    lineHeight: 1.25,
  };
}

function edrStateChipStyle(label: string): React.CSSProperties {
  const good = label === "Exists";
  const warn = label === "Reconvert required" || label === "In progress";
  const bad = label === "Failed";

  return {
    border: good ? "1px solid #22c55e" : warn ? "1px solid #facc15" : bad ? "1px solid #f87171" : "1px solid #64748b",
    borderRadius: 999,
    padding: "2px 7px",
    fontSize: 10,
    color: good ? "#86efac" : warn ? "#fde68a" : bad ? "#fecaca" : "#cbd5e1",
    whiteSpace: "nowrap",
    width: 128,
    textAlign: "center",
    display: "inline-block",
  };
}

function edrMonitorState(status: MinimalRepresentationStatus | null): { label: string; message: string } {
  if (!status) {
    return { label: "Checking", message: "Checking current state." };
  }

  const indexed = edrStatusLabel(status.indexedPreview);
  const cache = edrStatusLabel(status.optimizedCache);
  const full = edrStatusLabel(status.fullZarrConversion, "Not converted");

  if (indexed === "In progress") return { label: "Indexing", message: "Index / preview creation is running." };
  if (cache === "In progress") return { label: "Building optimized Zarr", message: "Indexed Zarr conversion is running." };
  if (full === "In progress") return { label: "Converting", message: "Full Zarr conversion is running." };
  if (indexed === "Failed" || cache === "Failed" || full === "Failed") return { label: "Failed", message: "The last operation failed. Refresh or retry the relevant action." };
  if (full === "Reconvert required") return { label: "Reconvert required", message: "The previous converted artifact is missing. Convert to Zarr is available." };
  if (indexed === "Exists" && cache === "Exists" && full === "Exists") return { label: "Complete", message: "Index, indexed Zarr, and full Zarr all exist." };
  if (indexed === "Exists" && cache === "Exists") return { label: "Indexed Zarr ready", message: "Index and indexed Zarr conversion exist." };
  if (indexed === "Exists") return { label: "Index ready", message: "Use the index to convert to Zarr, or run full Zarr conversion." };

  return { label: "Ready", message: "Create an index/preview, convert to Zarr, or use the index for faster Zarr conversion." };
}

function representationLineLabel(value: any): string {
  const status = String(value?.status || value?.artifact_status || "not_built").replaceAll("_", " ");

  if (value?.available) {
    if (status === "available" || status === "ready" || status === "converted") {
      return status;
    }
    return `${status} · available`;
  }

  return status;
}

function summarizeRepresentations(payload: any): MinimalRepresentationStatus {
  const reps = payload?.representations || {};
  const indexed = reps.indexed_preview || {};
  const cache = reps.optimized_cache || {};
  const full = reps.zarr_full_conversion || {};

  return {
    indexedPreview: representationLineLabel(indexed),
    indexedPreviewActionAvailable: !!indexed.action_available,
    indexedPreviewDatasetId: indexed.dataset_id || null,
    optimizedCache: representationLineLabel(cache),
    optimizedCacheActionAvailable: !!cache.action_available,
    optimizedCacheDatasetId: cache.dataset_id || null,
    fullZarrConversion: representationLineLabel(full),
    fullZarrVolumeId: full.volume_id || null,
    fullZarrUrl: full.zarr_url || null,
  };
}

function isVolumeCandidate(file: SegyFileRecord): boolean {
  return file.candidate_kind === "3d_volume" && file.candidate_role === "volume_candidate";
}

function isExcludedFrom3D(file: SegyFileRecord): boolean {
  return (
    file.candidate_role === "excluded_from_3d_intake" ||
    file.candidate_kind === "2d_line"
  );
}

function isReviewRequired(file: SegyFileRecord): boolean {
  return (
    file.candidate_role === "review_required" ||
    file.candidate_kind === "unknown" ||
    !file.candidate_kind
  );
}

function classificationLabel(file: SegyFileRecord): string {
  const kind = file.candidate_kind || "unknown";
  const role = file.candidate_role || "review_required";
  const confidence = file.classification_confidence || "low";
  return `${kind.replaceAll("_", " ")} · ${role.replaceAll("_", " ")} · ${confidence}`;
}

function is3DRepository(repo: RepositoryRecord): boolean {
  const intendedUse = String(repo.intended_use || "").toLowerCase();
  const sourceStructure = String(repo.source_structure_type || "").toLowerCase();
  const text = `${repo.name || ""} ${repo.notes || ""} ${intendedUse} ${sourceStructure}`.toLowerCase();

  return (
    intendedUse === "3d_segy_intake" ||
    sourceStructure === "single_3d_volume" ||
    sourceStructure === "single_3d_volume_with_docs" ||
    sourceStructure === "multi_version_3d_delivery" ||
    text.includes("3d_segy_intake") ||
    text.includes("3d_volume_delivery") ||
    text.includes("single_3d_volume") ||
    text.includes("multi_version_3d_delivery")
  );
}

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#94a3b8",
  marginBottom: 5,
};

const selectStyle: React.CSSProperties = {
  width: "100%",
  padding: "7px 9px",
  borderRadius: 6,
  border: "1px solid #555",
  background: "#2b2b2b",
  color: "#f8fafc",
  fontSize: 13,
};

const buttonStyle: React.CSSProperties = {
  border: "1px solid #557ca5",
  borderRadius: 6,
  background: "#2f5f8f",
  color: "#fff",
  padding: "6px 10px",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};

const secondaryButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  background: "#334155",
  border: "1px solid #64748b",
};

const dangerButtonStyle: React.CSSProperties = {
  border: "1px solid #f87171",
  borderRadius: 6,
  background: "transparent",
  color: "#f87171",
  padding: "6px 10px",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};


function StatusBadge({ status }: { status?: string }) {
  const background = isConverted(status)
    ? "rgba(34,197,94,.18)"
    : status === "error"
      ? "rgba(239,68,68,.18)"
      : isActive(status)
        ? "rgba(234,179,8,.18)"
        : "rgba(148,163,184,.16)";

  const color = isConverted(status)
    ? "#bbf7d0"
    : status === "error"
      ? "#fecaca"
      : isActive(status)
        ? "#fde68a"
        : "#cbd5e1";

  return (
    <span
      style={{
        display: "inline-flex",
        padding: "3px 8px",
        borderRadius: 999,
        background,
        color,
        fontSize: 11,
        fontWeight: 700,
        whiteSpace: "nowrap",
      }}
    >
      {statusLabel(status)}
    </span>
  );
}

export default function External3DRegistryPanel({
  onVolumeRegistered,
}: {
  onVolumeRegistered?: () => Promise<void> | void;
}) {
  const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
  const [packages, setPackages] = useState<PackageRecord[]>([]);
  const [segyFiles, setSegyFiles] = useState<SegyFileRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);

  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");
  const [selectedPackageId, setSelectedPackageId] = useState("");
  const [selectedSegyId, setSelectedSegyId] = useState("");

  const [loading, setLoading] = useState(false);
  const [busyFileId, setBusyFileId] = useState("");
  const [clearHandoffBusy, setClearHandoffBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [representationStatus, setRepresentationStatus] = useState<MinimalRepresentationStatus | null>(null);
  const [representationStatusLoading, setRepresentationStatusLoading] = useState(false);
  const [sourceLifecycle, setSourceLifecycle] = useState<SourceSegyLifecycleState | null>(null);
  const [sourceLifecycleLoading, setSourceLifecycleLoading] = useState(false);
  const [indexPreviewBusy, setIndexPreviewBusy] = useState(false);
  const [optimizedCacheBusy, setOptimizedCacheBusy] = useState(false);

  async function loadRepositories() {
    setLoading(true);
    setError("");

    try {
      const payload = await fetchJson<{ repositories: RepositoryRecord[] }>("/api/source-intake/repositories");
      const records = (payload.repositories || []).filter(is3DRepository);

      setRepositories(records);

      if (!selectedRepositoryId && records[0]) {
        setSelectedRepositoryId(records[0].repository_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load repositories");
    } finally {
      setLoading(false);
    }
  }

  async function loadRepositoryInventory(repositoryId: string) {
    if (!repositoryId) return;

    setLoading(true);
    setError("");

    try {
      const payload = await fetchJson<{
        packages: PackageRecord[];
        segy_files: SegyFileRecord[];
        documents: DocumentRecord[];
      }>(
        `/api/source-intake/repositories/${encodeURIComponent(repositoryId)}/submitted-view?mode=3d`
      );

      const packageRecords = payload.packages || [];
      const fileRecords = payload.segy_files || [];
      const documentRecords = payload.documents || [];

      setPackages(packageRecords);
      setSegyFiles(fileRecords);
      setDocuments(documentRecords);

      const nextPackageId =
        selectedPackageId && packageRecords.some((pkg) => pkg.package_id === selectedPackageId)
          ? selectedPackageId
          : packageRecords[0]?.package_id || "";

      setSelectedPackageId(nextPackageId);

      const nextFiles = nextPackageId
        ? fileRecords.filter((file) => file.package_id === nextPackageId)
        : fileRecords;

      const firstCandidate = nextFiles.find(isVolumeCandidate);
      setSelectedSegyId((current) =>
        current && nextFiles.some((file) => file.segy_file_id === current && isVolumeCandidate(file))
          ? current
          : firstCandidate?.segy_file_id || ""
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load submitted 3D Source Browser handoff");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRepositories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedRepositoryId) {
      loadRepositoryInventory(selectedRepositoryId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepositoryId]);

  const selectedRepository = repositories.find((repo) => repo.repository_id === selectedRepositoryId);
  const selectedPackage = packages.find((pkg) => pkg.package_id === selectedPackageId);

  const packageFiles = useMemo(() => {
    if (!selectedPackageId) return segyFiles;
    return segyFiles.filter((file) => file.package_id === selectedPackageId);
  }, [segyFiles, selectedPackageId]);

  const volumeCandidates = useMemo(
    () => packageFiles.filter(isVolumeCandidate),
    [packageFiles]
  );

  const excludedFiles = useMemo(
    () => packageFiles.filter(isExcludedFrom3D),
    [packageFiles]
  );

  const reviewRequiredFiles = useMemo(
    () => packageFiles.filter(isReviewRequired),
    [packageFiles]
  );

  const selectedFile =
    volumeCandidates.find((file) => file.segy_file_id === selectedSegyId) ||
    volumeCandidates[0] ||
    null;

  useEffect(() => {
    const handleExternal3DStateRefresh = () => {
      if (selectedRepositoryId) {
        void loadRepositoryInventory(selectedRepositoryId);
      }
      if (selectedFile?.segy_file_id) {
        void refreshSourceLifecycle(selectedFile);
      }
    };

    window.addEventListener("multiviewer:source-intake-updated", handleExternal3DStateRefresh);
    window.addEventListener("multiviewer:managed-data-updated", handleExternal3DStateRefresh);

    return () => {
      window.removeEventListener("multiviewer:source-intake-updated", handleExternal3DStateRefresh);
      window.removeEventListener("multiviewer:managed-data-updated", handleExternal3DStateRefresh);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepositoryId, selectedFile?.segy_file_id]);

  useEffect(() => {
    let cancelled = false;

    async function fetchRepresentationStatusForSelectedFile() {
      if (!selectedFile?.segy_file_id) {
        setRepresentationStatus(null);
        return;
      }

      setRepresentationStatusLoading(true);
      setSourceLifecycleLoading(true);

      try {
        const lifecyclePayload = await fetchJson<SourceSegyLifecycleState>(
          `/api/segy-files/${encodeURIComponent(selectedFile.segy_file_id)}/lifecycle?mode=3d`
        );

        if (!cancelled) {
          setSourceLifecycle(lifecyclePayload);
          setRepresentationStatus(summarizeLifecycle(lifecyclePayload));
        }
      } catch {
        if (!cancelled) {
          setRepresentationStatus(null);
          setSourceLifecycle(null);
        }
      } finally {
        if (!cancelled) {
          setRepresentationStatusLoading(false);
          setSourceLifecycleLoading(false);
        }
      }
    }

    fetchRepresentationStatusForSelectedFile();

    return () => {
      cancelled = true;
    };
  }, [selectedFile?.segy_file_id]);


  const packageDocs = useMemo(() => {
    if (!selectedPackage) return documents;

    const packagePath = (selectedPackage.relative_path || "").toLowerCase();
    const packageName = (selectedPackage.display_name || "").toLowerCase();

    return documents.filter((doc) => {
      const rel = String(doc.relative_path || "").toLowerCase();
      const filename = String(doc.filename || "").toLowerCase();

      if (!packagePath && !packageName) return true;

      return (
        (!!packagePath && (rel === packagePath || rel.startsWith(`${packagePath}/`))) ||
        (!!packageName && (rel.startsWith(`${packageName}/`) || filename.includes(packageName)))
      );
    });
  }, [documents, selectedPackage]);

  const hasActiveConversions = segyFiles.some((file) => isActive(file.conversion_status));

  useEffect(() => {
    if (!selectedRepositoryId || !hasActiveConversions) return;

    const timer = window.setInterval(() => {
      loadRepositoryInventory(selectedRepositoryId);
    }, 5000);

    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepositoryId, hasActiveConversions]);

  async function clearSubmittedHandoff() {
    if (!selectedRepositoryId) {
      setError("Select a repository before clearing submitted handoff records.");
      return;
    }

    const ok = window.confirm(
      `Clear submitted 3D handoff for this repository?

This removes only the submitted QAQC handoff records used by 3D Source Intake candidate review.

It preserves the registered source repository, scan results, original files, Managed Data, Zarr, jobs, and converted datasets.`
    );

    if (!ok) return;

    setClearHandoffBusy(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(
        `/api/repositories/${encodeURIComponent(selectedRepositoryId)}/submitted-handoff/clear`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ mode: "3d", confirm: true }),
        }
      );

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        const detail = payload?.detail || payload?.message || `Clear submitted handoff failed: ${response.status}`;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }

      setMessage(
        `Submitted 3D handoff cleared: ${payload.cleared_segy_count || 0} SEG-Y file${(payload.cleared_segy_count || 0) === 1 ? "" : "s"} and ${payload.cleared_document_count || 0} supporting/associated file${(payload.cleared_document_count || 0) === 1 ? "" : "s"}. Repository and scan results were preserved.`
      );

      setSelectedPackageId("");
      setSelectedSegyId("");
      await loadRepositoryInventory(selectedRepositoryId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear submitted 3D handoff");
    } finally {
      setClearHandoffBusy(false);
    }
  }

  useEffect(() => {
    if (!selectedFile?.segy_file_id || !sourceLifecycle?.active_job) return;

    let cancelled = false;

    const intervalId = window.setInterval(async () => {
      if (cancelled) return;

      try {
        await refreshSourceLifecycle(selectedFile);
      } catch {
        // Keep polling lightweight and non-disruptive. The normal error UI
        // remains driven by explicit user actions.
      }
    }, 1000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [selectedFile?.segy_file_id, sourceLifecycle?.active_job?.job_id]);

  async function handleLifecycleAction(
    file: SegyFileRecord,
    row: SourceSegyLifecycleRepresentation
  ) {
    if (!row.action_url) {
      setError(`No lifecycle action is available for ${row.label}.`);
      return;
    }

    setBusyFileId(`${file.segy_file_id}:${row.key}:action`);
    setError("");
    setMessage("");

    try {
      const result = await fetchJson<any>(`${row.action_url}?mode=3d`, {
        method: "POST",
      });

      const jobId =
        result?.action_result?.job_id ||
        result?.action_result?.job?.job_id ||
        result?.action_result?.segy_file?.job_id;

      setMessage(jobId ? `${row.label} action queued. Job: ${jobId}` : `${row.label} action complete.`);

      await loadRepositoryInventory(file.repository_id);
      await refreshSourceLifecycle(file);
      await onVolumeRegistered?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to run ${row.label} action`);
    } finally {
      setBusyFileId("");
    }
  }

  async function handleLifecycleDelete(
    file: SegyFileRecord,
    row: SourceSegyLifecycleRepresentation
  ) {
    setBusyFileId(`${file.segy_file_id}:${row.key}:delete`);
    setError("");
    setMessage("");

    try {
      const preflight = await fetchJson<any>(
        `/api/segy-files/${encodeURIComponent(file.segy_file_id)}/maintenance/${encodeURIComponent(row.key)}/preflight?action=delete&mode=3d`
      );

      if (!preflight?.allowed) {
        setError(preflight?.reason || `${row.label} is not currently deletable.`);
        return;
      }

      const impact = preflight?.impact || {};
      const deletes = Array.isArray(impact.deletes) ? impact.deletes.join(", ") : row.label;
      const preserves = Array.isArray(impact.preserves) ? impact.preserves.join(", ") : "Source SEG-Y";
      const dependency = impact.dependency_behavior || "";
      const viewerImpact = impact.viewer_impact || "";

      const ok = window.confirm(
        `Delete ${preflight.artifact_label || row.label}?\n\n` +
          `Deletes: ${deletes}\n` +
          `Preserves: ${preserves}\n\n` +
          `${dependency ? dependency + "\n" : ""}` +
          `${viewerImpact ? viewerImpact + "\n\n" : "\n"}` +
          `This action uses the backend maintenance service and does not delete the source SEG-Y.`
      );

      if (!ok) return;

      const result = await fetchJson<any>(
        `/api/segy-files/${encodeURIComponent(file.segy_file_id)}/maintenance/${encodeURIComponent(row.key)}/execute?action=delete&mode=3d&confirm=true`,
        { method: "POST" }
      );

      const after = result?.lifecycle_after;
      const monitor = after?.monitor?.label ? ` ${after.monitor.label}.` : "";
      setMessage(`${preflight.artifact_label || row.label} deleted.${monitor}`);

      await loadRepositoryInventory(file.repository_id);
      await refreshSourceLifecycle(file);
      await onVolumeRegistered?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to delete ${row.label}`);
    } finally {
      setBusyFileId("");
    }
  }

  async function handleConvert(file: SegyFileRecord) {
    const row = sourceLifecycle?.representations.find((item) => item.key === "managed_zarr");
    if (!row) {
      setError("Managed Zarr lifecycle row is missing.");
      return;
    }
    await handleLifecycleAction(file, row);
  }

  async function refreshSourceLifecycle(file: SegyFileRecord | null) {
    if (!file?.segy_file_id) {
      setSourceLifecycle(null);
      setRepresentationStatus(null);
      return;
    }

    const payload = await fetchJson<SourceSegyLifecycleState>(
      `/api/segy-files/${encodeURIComponent(file.segy_file_id)}/lifecycle?mode=3d`
    );

    setSourceLifecycle(payload);
    setRepresentationStatus(summarizeLifecycle(payload));
  }

  async function refreshRepresentationStatus(file: SegyFileRecord | null) {
    await refreshSourceLifecycle(file);
  }

  async function handleIndexPreview(file: SegyFileRecord) {
    const row = sourceLifecycle?.representations.find((item) => item.key === "index_preview");
    if (!row) {
      setError("Index / Preview lifecycle row is missing.");
      return;
    }

    setIndexPreviewBusy(true);
    try {
      await handleLifecycleAction(file, row);
    } finally {
      setIndexPreviewBusy(false);
    }
  }

  async function handleBuildOptimizedCache(file: SegyFileRecord) {
    const row = sourceLifecycle?.representations.find((item) => item.key === "fast_zarr_cache");
    if (!row) {
      setError("Fast Zarr Cache lifecycle row is missing.");
      return;
    }

    setOptimizedCacheBusy(true);
    try {
      await handleLifecycleAction(file, row);
    } finally {
      setOptimizedCacheBusy(false);
    }
  }

  async function handleRefresh(file: SegyFileRecord) {
    setBusyFileId(file.segy_file_id);
    setError("");
    setMessage("");

    try {
      await fetchJson<any>(`/api/segy-files/${file.segy_file_id}/refresh-status`, {
        method: "POST",
      });

      await loadRepositoryInventory(file.repository_id);
      await refreshSourceLifecycle(file);
      await onVolumeRegistered?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh status");
    } finally {
      setBusyFileId("");
    }
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {error && (
        <div style={{ padding: 8, borderRadius: 7, background: "rgba(239,68,68,.15)", color: "#fecaca", fontSize: 12 }}>
          {error}
        </div>
      )}

      {message && (
        <div style={{ padding: 8, borderRadius: 7, background: "rgba(34,197,94,.12)", color: "#bbf7d0", fontSize: 12 }}>
          {message}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: "#f8fafc" }}>3D Source Browser</div>
          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
            Submitted QAQC handoff view. Only submitted/ready 3D source items are shown.
          </div>
        </div>

        <button
          type="button"
          onClick={clearSubmittedHandoff}
          disabled={clearHandoffBusy || !selectedRepositoryId}
          style={{
            ...dangerButtonStyle,
            opacity: clearHandoffBusy || !selectedRepositoryId ? 0.65 : 1,
            cursor: clearHandoffBusy || !selectedRepositoryId ? "not-allowed" : "pointer",
          }}
        >
          {clearHandoffBusy ? "Clearing handoff..." : "Clear Submitted Handoff"}
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <div style={labelStyle}>Repository</div>
          <select
            value={selectedRepositoryId}
            onChange={(event) => {
              setSelectedRepositoryId(event.target.value);
              setSelectedPackageId("");
              setSelectedSegyId("");
            }}
            style={selectStyle}
          >
            {repositories.map((repo) => (
              <option key={repo.repository_id} value={repo.repository_id}>
                {repo.name}
              </option>
            ))}
          </select>
          {selectedRepository && (
            <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>
              {selectedRepository.root_path}
            </div>
          )}
        </div>

        <div>
          <div style={labelStyle}>Package / Delivery Folder</div>
          <select
            value={selectedPackageId}
            onChange={(event) => {
              setSelectedPackageId(event.target.value);
              setSelectedSegyId("");
            }}
            style={selectStyle}
          >
            {packages.map((pkg) => (
              <option key={pkg.package_id} value={pkg.package_id}>
                {pkg.display_name || pkg.relative_path || pkg.package_id}
              </option>
            ))}
          </select>
          <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5e1" }}>
            {volumeCandidates.length} volume candidate{volumeCandidates.length === 1 ? "" : "s"} · {reviewRequiredFiles.length} review · {excludedFiles.length} excluded · {packageDocs.length} docs
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 42%) 1fr", gap: 12, alignItems: "start" }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <div style={labelStyle}>Volume Candidates</div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>{volumeCandidates.length} files</div>
          </div>

          <div style={{ border: "1px solid #3f3f46", borderRadius: 8, overflow: "hidden" }}>
            {volumeCandidates.length === 0 && (
              <div style={{ padding: 10, fontSize: 12, color: "#94a3b8" }}>
                No submitted 3D volume candidates found.
              </div>
            )}

            {volumeCandidates.map((file) => {
              const selected = file.segy_file_id === selectedFile?.segy_file_id;

              return (
                <button
                  key={file.segy_file_id}
                  type="button"
                  onClick={() => setSelectedSegyId(file.segy_file_id)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    border: "none",
                    borderBottom: "1px solid #27272a",
                    background: selected ? "rgba(59,130,246,.18)" : "#18181b",
                    color: "#e5e7eb",
                    padding: "9px 10px",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: selected ? 700 : 600, overflowWrap: "anywhere" }}>
                    {file.filename}
                  </div>
                  <div style={{ marginTop: 4, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", fontSize: 12, color: "#94a3b8" }}>
                    <span>{formatBytes(file.size_bytes)}</span>
                    <span>{classificationLabel(file)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div style={labelStyle}>Selected Volume / Conversion Details</div>

          <div style={{ border: "1px solid #3f3f46", borderRadius: 8, minHeight: 178, padding: 12, background: "#18181b" }}>
            {!selectedFile ? (
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Select a 3D volume candidate.</div>
            ) : (
              <div style={{ display: "grid", gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 800, color: "#f8fafc", overflowWrap: "anywhere", fontSize: 15 }}>
                    {selectedFile.filename}
                  </div>
                </div>

                <div
                  style={{
                    border: "1px solid #334155",
                    borderRadius: 9,
                    padding: 12,
                    background: "#111827",
                    display: "grid",
                    gap: 8,
                  }}
                >
                  <div style={{ fontWeight: 800, color: "#e5e7eb", fontSize: 13 }}>
                    Actions
                    {(representationStatusLoading || sourceLifecycleLoading) && (
                      <span style={{ marginLeft: 8, color: "#94a3b8", fontWeight: 500 }}>
                        checking...
                      </span>
                    )}
                  </div>

                  {(() => {
                    const rows = sourceLifecycle?.representations || [];

                    function runAction(row: SourceSegyLifecycleRepresentation) {
                      return handleLifecycleAction(selectedFile, row);
                    }

                    function busyFor(row: SourceSegyLifecycleRepresentation): boolean {
                      return busyFileId.startsWith(`${selectedFile.segy_file_id}:${row.key}:`);
                    }

                    function buttonLabel(row: SourceSegyLifecycleRepresentation): string {
                      if (busyFor(row)) {
                        if (busyFileId.endsWith(":delete")) return "Deleting...";
                        if (row.key === "index_preview") return "Creating index...";
                        if (row.key === "fast_zarr_cache") return "Building cache...";
                        if (row.key === "managed_zarr") return "Creating Zarr...";
                        return "Working...";
                      }

                      if (!row.can_create) {
                        if (row.state === "exists") return row.label;
                        if (row.state === "running") return row.label;
                        if (row.state === "missing") return row.label;
                        if (row.state === "failed") return row.label;
                      }

                      if (row.key === "index_preview") return row.state === "failed" ? "Retry Index / Preview" : "Create Index / Preview";
                      if (row.key === "fast_zarr_cache") return row.state === "failed" ? "Retry Fast Zarr Cache" : "Build Fast Zarr Cache";
                      if (row.key === "managed_zarr") return row.state === "failed" || row.state === "missing" ? "Recreate Managed Zarr" : "Create Managed Zarr";
                      return "Create";
                    }

                    return (
                      <div style={{ display: "grid", gap: 8 }}>
                        {rows.map((row) => {
                          const activeJob = sourceLifecycle?.active_job || null;
                          const rowHasActiveJob =
                            (row.key === "index_preview" && activeJob?.action === "index_preview") ||
                            (row.key === "fast_zarr_cache" && activeJob?.action === "build_fast_zarr_cache") ||
                            (row.key === "managed_zarr" && activeJob?.action === "create_managed_zarr");
                          const busy = busyFor(row) || rowHasActiveJob;
                          const createEnabled = !!row.can_create && !!row.action_url && !busy;
                          const progress = typeof activeJob?.progress === "number" ? activeJob.progress : 0;

                          return (
                            <div
                              key={row.key}
                              style={{ display: "grid", gridTemplateColumns: "210px 128px", alignItems: "center", gap: 10 }}
                            >
                              <button
                                type="button"
                                onClick={() => runAction(row)}
                                disabled={!createEnabled}
                                style={edrActionButtonStyle(createEnabled)}
                              >
                                {buttonLabel(row)}
                              </button>
                              <span style={edrStateChipStyle(rowHasActiveJob ? "In progress" : row.status_label)}>
                                {rowHasActiveJob ? "In progress" : row.status_label}
                              </span>

                              {rowHasActiveJob && (
                                <>
                                  <div style={edrProgressOuterStyle()}>
                                    <div style={edrProgressInnerStyle(progress)} />
                                  </div>
                                  <div style={edrProgressTextStyle()}>
                                    {progress}% · {activeJob?.message || activeJob?.label || "Running"}
                                  </div>
                                </>
                              )}
                            </div>
                          );
                        })}

                        <details
                          data-role="advanced-maintenance-3d"
                          style={{
                            borderTop: "1px solid #334155",
                            paddingTop: 10,
                            marginTop: 2,
                          }}
                        >
                          <summary
                            style={{
                              cursor: "pointer",
                              color: "#cbd5e1",
                              fontSize: 12,
                              fontWeight: 800,
                            }}
                          >
                            Advanced Maintenance
                          </summary>

                          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
                            {rows.map((row) => {
                              const busy = busyFor(row);
                              const maintenanceEnabled = row.state === "exists" && !busy;

                              let maintenanceLabel = `Delete ${row.label}`;
                              if (busy && busyFileId.endsWith(":delete")) maintenanceLabel = "Deleting...";
                              if (row.key === "index_preview") maintenanceLabel = busy ? "Deleting index..." : "Delete Index / Preview";
                              if (row.key === "fast_zarr_cache") maintenanceLabel = busy ? "Deleting cache..." : "Delete Fast Zarr Cache";
                              if (row.key === "managed_zarr") maintenanceLabel = busy ? "Deleting managed Zarr..." : "Delete Managed Zarr";

                              return (
                                <div
                                  key={`maintenance-${row.key}`}
                                  style={{ display: "grid", gridTemplateColumns: "210px 1fr", alignItems: "center", gap: 10 }}
                                >
                                  <button
                                    type="button"
                                    onClick={() => handleLifecycleDelete(selectedFile, row)}
                                    disabled={!maintenanceEnabled}
                                    style={edrActionButtonStyle(maintenanceEnabled)}
                                  >
                                    {maintenanceLabel}
                                  </button>
                                  <span style={{ color: "#94a3b8", fontSize: 11 }}>
                                    {row.key === "index_preview"
                                      ? "Deletes index and attached fast cache; preserves Managed Zarr."
                                      : row.key === "fast_zarr_cache"
                                        ? "Deletes fast cache only; preserves index and Managed Zarr."
                                        : "Deletes Managed Zarr only; preserves source, index, and fast cache."}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </details>

                        <div style={{ display: "flex", alignItems: "center" }}>
                          <button
                            type="button"
                            onClick={() => handleRefresh(selectedFile)}
                            disabled={busyFileId === selectedFile.segy_file_id}
                            style={edrRefreshButtonStyle(busyFileId !== selectedFile.segy_file_id)}
                          >
                            {busyFileId === selectedFile.segy_file_id ? "Refreshing..." : "Refresh"}
                          </button>
                        </div>
                      </div>
                    );
                  })()}
                </div>

                <div
                  style={{
                    border: "1px solid #334155",
                    borderRadius: 9,
                    padding: 12,
                    background: "#0f172a",
                    display: "grid",
                    gap: 6,
                  }}
                >
                  <div style={{ fontWeight: 800, color: "#e5e7eb", fontSize: 13 }}>
                    Active State Monitor
                  </div>
                  {(() => {
                    const state = sourceLifecycle?.monitor || {
                      label: sourceLifecycleLoading ? "Checking" : "Ready",
                      message: sourceLifecycleLoading ? "Checking current state." : "Select refresh to update current state.",
                    };
                    return (
                      <>
                        <div style={{ color: "#f8fafc", fontSize: 13 }}>{state.label}</div>
                        <div style={{ color: "#94a3b8", fontSize: 12 }}>{state.message}</div>
                      </>
                    );
                  })()}
                </div>
              </div>
            )}
          </div>

          <section data-role="submitted-supporting-associated-files-3d">
            <div style={labelStyle}>Submitted Supporting / Associated Files</div>
            <div style={{ border: "1px solid #3f3f46", borderRadius: 8, padding: 10, background: "#18181b" }}>
              {packageDocs.length === 0 ? (
                <div style={{ fontSize: 12, color: "#94a3b8" }}>No submitted supporting or associated files found.</div>
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {packageDocs.map((doc) => (
                    <div key={doc.document_id || doc.relative_path || doc.filename}>
                      <div style={{ fontSize: 13, fontWeight: 650 }}>{doc.filename}</div>
                      <div style={{ marginTop: 3, fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>
                        {doc.relative_path}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {reviewRequiredFiles.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={labelStyle}>Review Required</div>
              <div style={{ border: "1px solid #854d0e", borderRadius: 8, padding: 10, background: "rgba(113,63,18,.18)" }}>
                {reviewRequiredFiles.map((file) => (
                  <div key={file.segy_file_id} style={{ fontSize: 12, color: "#fde68a", marginBottom: 6 }}>
                    <div style={{ fontWeight: 650, overflowWrap: "anywhere" }}>{file.filename}</div>
                    <div style={{ color: "#facc15", overflowWrap: "anywhere" }}>
                      {classificationLabel(file)}
                    </div>
                    {file.classification_reasons && file.classification_reasons.length > 0 && (
                      <div style={{ color: "#d6d3d1", overflowWrap: "anywhere" }}>
                        {file.classification_reasons.join("; ")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {excludedFiles.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={labelStyle}>Excluded / Not 3D</div>
              <div style={{ border: "1px solid #3f3f46", borderRadius: 8, padding: 10, background: "rgba(63,63,70,.25)" }}>
                {excludedFiles.map((file) => (
                  <div key={file.segy_file_id} style={{ fontSize: 12, color: "#cbd5e1", marginBottom: 6 }}>
                    <div style={{ fontWeight: 650, overflowWrap: "anywhere" }}>{file.filename}</div>
                    <div style={{ color: "#94a3b8", overflowWrap: "anywhere" }}>
                      {formatBytes(file.size_bytes)} · {classificationLabel(file)}
                    </div>
                    {file.classification_reasons && file.classification_reasons.length > 0 && (
                      <div style={{ color: "#94a3b8", overflowWrap: "anywhere" }}>
                        {file.classification_reasons.join("; ")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>


      <div
        data-role="package-supporting-documents-full-width"
        style={{
          marginTop: 0,
          textAlign: "left",
        }}
      >
        <div style={labelStyle}>Package Supporting Documents</div>
        <div
          style={{
            border: "1px solid #3f3f46",
            borderRadius: 8,
            padding: 10,
            background: "#18181b",
          }}
        >
          {packageDocs.length === 0 ? (
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              No package-level supporting documents found.
            </div>
          ) : (
            <div style={{ display: "grid", gap: 8 }}>
              {packageDocs.map((doc) => (
                <div key={doc.document_id || doc.relative_path || doc.filename}>
                  <div style={{ fontSize: 13, fontWeight: 650 }}>
                    {doc.filename}
                  </div>
                  <div
                    style={{
                      marginTop: 3,
                      fontSize: 12,
                      color: "#94a3b8",
                      overflowWrap: "anywhere",
                    }}
                  >
                    {doc.relative_path}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {loading && <div style={{ fontSize: 12, color: "#94a3b8" }}>Loading...</div>}
    </div>
  );
}
