import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildSourceIntake2DLine,
  type SourceIntakeWorkbenchPayload,
  type SourceIntakeWorkbenchRow,
} from "../services/registryService";
import {
  clearSelectedSourceIntakeWorkbenchV2,
  fetchSourceIntakeWorkbenchV2,
  useRepositoryInSourceIntakeWorkbenchV2,
} from "../services/sourceIntakeWorkbenchV2Service";

type SourceIntakeWorkbenchPanelProps = {
  repositoryId?: string;
  mode?: "2d" | "3d";
  refreshSignal?: number;
  onViewIndexedPreview?: (viewerSource: any) => void;
};

function valueOrDash(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function titleCaseToken(value: unknown): string {
  const raw = valueOrDash(value);
  if (raw === "—") return raw;
  return raw
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function rowKey(row: SourceIntakeWorkbenchRow, index: number): string {
  return row.candidate_id || row.source_segy_file_id || `${row.repository_id || "repo"}:${row.filename || index}`;
}

function actionEnabled(row: SourceIntakeWorkbenchRow, key: string): boolean {
  const action = row.actions?.[key] as any;
  return Boolean(action && (action.enabled || action.available));
}

function actionReason(row: SourceIntakeWorkbenchRow, key: string): string | null {
  const action = row.actions?.[key] as any;
  const reason = action?.reason;
  return typeof reason === "string" && reason.trim().length > 0 ? reason.trim() : null;
}

function actionUrl(row: SourceIntakeWorkbenchRow, key: string): string | null {
  const actions = row.actions as Record<string, { url?: string | null }> | undefined;
  const rawUrl = actions?.[key]?.url;
  if (typeof rawUrl !== "string") return null;
  const cleanUrl = rawUrl.trim();
  return cleanUrl.length > 0 ? cleanUrl : null;
}



function backendLifecycleRecord(row: SourceIntakeWorkbenchRow): Record<string, any> | null {
  const record = (row as any).lifecycle;
  return record && typeof record === "object" ? record : null;
}

function backendProgressRecord(row: SourceIntakeWorkbenchRow): Record<string, any> | null {
  const record = (row as any).progress;
  return record && typeof record === "object" ? record : null;
}

function backendPresentationRecord(row: SourceIntakeWorkbenchRow): Record<string, any> | null {
  const record = (row as any).presentation;
  return record && typeof record === "object" ? record : null;
}

function backendDimension(row: SourceIntakeWorkbenchRow): string {
  return String((row as any).dimension || "").trim().toLowerCase();
}

function backendLifecycleState(row: SourceIntakeWorkbenchRow): string {
  return String(backendLifecycleRecord(row)?.state || "").trim().toLowerCase();
}

function normalizedKind(row: SourceIntakeWorkbenchRow): string {
  return String(row.candidate_kind || row.candidate_role || "").trim().toLowerCase();
}

function is2DRow(row: SourceIntakeWorkbenchRow): boolean {
  const dimension = backendDimension(row);
  if (dimension === "2d") return true;
  if (dimension === "3d") return false;
  const kind = normalizedKind(row);
  return kind === "2d_line" || kind === "line_candidate" || kind.includes("2d");
}

function is3DRow(row: SourceIntakeWorkbenchRow): boolean {
  const dimension = backendDimension(row);
  if (dimension === "3d") return true;
  if (dimension === "2d") return false;
  const kind = normalizedKind(row);
  return kind === "3d_volume" || kind === "volume_candidate" || kind.includes("3d");
}

function rowIsManaged(row: SourceIntakeWorkbenchRow): boolean {
  const state = backendLifecycleState(row);
  if (state) return state === "viewer_ready" || state === "promotion_complete";
  return Boolean(row.managed_output?.viewer_ready || String(row.managed_state || "").toLowerCase() === "viewer_ready");
}

function statusLabel(row: SourceIntakeWorkbenchRow): string {
  const presentation = backendPresentationRecord(row);
  const backendLabel = presentation?.status_label;
  if (typeof backendLabel === "string" && backendLabel.trim()) return backendLabel.trim();
  const lifecycle = backendLifecycleRecord(row);
  const lifecycleLabel = lifecycle?.label;
  if (typeof lifecycleLabel === "string" && lifecycleLabel.trim()) return lifecycleLabel.trim();
  const status = row.status as unknown;
  if (status && typeof status === "object") {
    const record = status as Record<string, unknown>;
    return valueOrDash(record.label || record.state);
  }
  return titleCaseToken(status || row.conversion_state || row.managed_state);
}


function geometryQaqcRecord(row: SourceIntakeWorkbenchRow): Record<string, any> | null {
  const record = (row as any).geometry_qaqc;
  return record && typeof record === "object" ? record : null;
}

function geometryQaqcStatusLabel(row: SourceIntakeWorkbenchRow): string {
  const presentation = backendPresentationRecord(row);
  const backendLabel = presentation?.geometry_qaqc_label;
  if (typeof backendLabel === "string" && backendLabel.trim()) return backendLabel.trim();
  const record = geometryQaqcRecord(row);
  const status = String(record?.status || row.qaqc_state || "not_run").trim().toLowerCase();
  if (status === "passed") return "Geometry Passed";
  if (status === "review_required") return "Geometry Review";
  if (status === "failed") return "Geometry Failed";
  if (status === "blocked") return "Blocked";
  if (status === "ready") return "Ready";
  return titleCaseToken(status || "not_run");
}

function geometryQaqcSummary(row: SourceIntakeWorkbenchRow): string | null {
  const record = geometryQaqcRecord(row);
  const summary = record?.summary;
  return typeof summary === "string" && summary.trim() ? summary.trim() : null;
}


function documentStatusLabel(row: SourceIntakeWorkbenchRow): string {
  const presentation = backendPresentationRecord(row);
  const backendLabel = presentation?.document_label;
  if (typeof backendLabel === "string" && backendLabel.trim()) return backendLabel.trim();
  if (typeof backendLabel === "number" && Number.isFinite(backendLabel)) return String(backendLabel);
  const rawCount =
    (row as any).effective_document_count ??
    (row as any).assigned_document_count ??
    (row as any).document_count;
  const count = typeof rawCount === "number" ? rawCount : Number(rawCount || 0);
  if (!Number.isFinite(count) || count <= 0) return "–";
  return String(count);
}

function documentSubtitleLabel(row: SourceIntakeWorkbenchRow): string {
  const presentation = backendPresentationRecord(row);
  const backendSubtitle = presentation?.document_subtitle;
  if (typeof backendSubtitle === "string" && backendSubtitle.trim()) return backendSubtitle.trim();
  const rawDiscovered = (row as any).discovered_document_count;
  const discovered = typeof rawDiscovered === "number" ? rawDiscovered : Number(rawDiscovered || 0);
  const rawAssigned =
    (row as any).effective_document_count ??
    (row as any).assigned_document_count ??
    (row as any).document_count;
  const assigned = typeof rawAssigned === "number" ? rawAssigned : Number(rawAssigned || 0);
  if (Number.isFinite(discovered) && discovered > 0 && (!Number.isFinite(assigned) || assigned <= 0)) return `${discovered} discovered`;
  if (Number.isFinite(discovered) && discovered > assigned) return `${discovered} discovered`;
  return "Documents";
}

function candidateIdForDocuments(row: SourceIntakeWorkbenchRow): string {
  return String(row.candidate_id || row.source_segy_file_id || "").trim();
}

function rebuildState(_row: SourceIntakeWorkbenchRow): Record<string, any> | null {
  return null;
}

function stagedRebuildResult(_row: SourceIntakeWorkbenchRow): Record<string, any> | null {
  return null;
}

function rowHasStagedRebuildReady(_row: SourceIntakeWorkbenchRow): boolean {
  return false;
}

function shortIdentifier(value: unknown): string {
  const text = String(value || "").trim();
  if (!text) return "—";
  return text.length > 14 ? `${text.slice(0, 8)}…${text.slice(-4)}` : text;
}

function stagedRebuildSummary(row: SourceIntakeWorkbenchRow): string {
  const staged = stagedRebuildResult(row);
  if (!staged) return "";
  const artifact = staged.artifact_id || staged.job_id;
  const target = staged.target || "managed_2d_line_zarr";
  return `Job ${shortIdentifier(staged.job_id)} · Artifact ${shortIdentifier(artifact)} · Target ${target}`;
}

function managedOutputLabel(row: SourceIntakeWorkbenchRow): string {
  const presentation = backendPresentationRecord(row);
  const backendLabel = presentation?.managed_output_label;
  if (typeof backendLabel === "string" && backendLabel.trim()) return backendLabel.trim();
  if (row.managed_output?.viewer_ready) return "Viewer Ready";
  if (String(row.managed_state || "").toLowerCase() === "viewer_ready") return "Viewer Ready";
  return titleCaseToken(row.managed_state);
}

function rowJobRecord(row: SourceIntakeWorkbenchRow): Record<string, unknown> {
  return row.job && typeof row.job === "object" ? row.job : {};
}

function rowJobState(row: SourceIntakeWorkbenchRow): string {
  const job = rowJobRecord(row);
  return String(job.state || job.status || "").trim().toLowerCase();
}

function rowJobProgress(row: SourceIntakeWorkbenchRow): number | null {
  const job = rowJobRecord(row);
  const raw = job.progress;
  if (typeof raw === "number" && Number.isFinite(raw)) return Math.max(0, Math.min(100, raw));
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) return Math.max(0, Math.min(100, parsed));
  }
  return null;
}

function rowJobMessage(row: SourceIntakeWorkbenchRow): string | null {
  const job = rowJobRecord(row);
  const message = job.message;
  return typeof message === "string" && message.trim() ? message.trim() : null;
}

function rowJobType(row: SourceIntakeWorkbenchRow): string {
  const job = rowJobRecord(row);
  return String(job.job_type || job.type || job.action || "").trim().toLowerCase();
}

function rowHasIndexJob(row: SourceIntakeWorkbenchRow): boolean {
  const jobType = rowJobType(row);
  return jobType.includes("build_index") || jobType.includes("index_preview") || jobType.includes("source_intake_index");
}

function rowHasActiveJob(row: SourceIntakeWorkbenchRow): boolean {
  const conversionState = String(row.conversion_state || "").trim().toLowerCase();
  const jobState = rowJobState(row);
  const activeStates = new Set(["queued", "submitted", "pending", "running", "building", "converting", "processing", "in_progress", "started"]);
  return activeStates.has(conversionState) || activeStates.has(jobState);
}

type RowProgressModel = {
  visible: boolean;
  label: string;
  detail?: string | null;
  percent: number;
  active: boolean;
  failed: boolean;
};

function rowProgressModel(row: SourceIntakeWorkbenchRow): RowProgressModel {
  const backend = backendProgressRecord(row);
  if (backend) {
    const rawPercent = backend.percent;
    const percent = typeof rawPercent === "number" && Number.isFinite(rawPercent)
      ? Math.max(0, Math.min(100, rawPercent))
      : Number.isFinite(Number(rawPercent))
        ? Math.max(0, Math.min(100, Number(rawPercent)))
        : 0;
    return {
      visible: backend.visible !== false,
      label: typeof backend.label === "string" && backend.label.trim() ? backend.label.trim() : statusLabel(row),
      detail: typeof backend.detail === "string" ? backend.detail : null,
      percent,
      active: Boolean(backend.active),
      failed: Boolean(backend.failed),
    };
  }

  const conversionState = String(row.conversion_state || "").trim().toLowerCase();
  const managedState = String(row.managed_state || "").trim().toLowerCase();
  const jobState = rowJobState(row);
  const jobProgress = rowJobProgress(row);
  const jobMessage = rowJobMessage(row);
  const isIndexJob = rowHasIndexJob(row);
  if (row.managed_output?.viewer_ready || managedState === "viewer_ready") {
    return {
      visible: true,
      label: "Viewer Ready",
      detail: row.managed_output?.representation_type || row.managed_output?.viewer_mode || null,
      percent: 100,
      active: false,
      failed: false,
    };
  }

  if ([conversionState, jobState].some((state) => state === "failed" || state === "error")) {
    return {
      visible: true,
      label: "Failed",
      detail: jobMessage || "Conversion failed.",
      percent: 100,
      active: false,
      failed: true,
    };
  }

  if ([conversionState, jobState].some((state) => state === "queued" || state === "pending" || state === "submitted")) {
    return {
      visible: true,
      label: isIndexJob ? "Index Queued" : "Queued",
      detail: jobMessage || (isIndexJob ? "Waiting to build indexed SEG-Y preview." : "Waiting for conversion worker."),
      percent: Math.max(5, jobProgress ?? 5),
      active: true,
      failed: false,
    };
  }

  if ([conversionState, jobState].some((state) => state === "building" || state === "running" || state === "converting" || state === "in_progress" || state === "started")) {
    const percent = jobProgress ?? 12;
    return {
      visible: true,
      label: isIndexJob ? `Building Index ${Math.round(percent)}%` : `Converting ${Math.round(percent)}%`,
      detail: jobMessage || (isIndexJob ? "Building indexed SEG-Y preview." : "Converting SEG-Y to managed Zarr."),
      percent,
      active: true,
      failed: false,
    };
  }

  if ((conversionState === "complete" || jobState === "complete" || jobState === "completed") && !row.managed_output?.viewer_ready) {
    if (isIndexJob) {
      return {
        visible: true,
        label: "Index Ready",
        detail: jobMessage || "View Indexed Preview is available.",
        percent: 100,
        active: false,
        failed: false,
      };
    }
    return {
      visible: true,
      label: "Registering",
      detail: jobMessage || "Registering managed output.",
      percent: Math.max(95, Math.min(99, jobProgress ?? 98)),
      active: true,
      failed: false,
    };
  }

  return {
    visible: false,
    label: "Ready",
    detail: null,
    percent: 0,
    active: false,
    failed: false,
  };
}

function RowProgressMeter({ row }: { row: SourceIntakeWorkbenchRow }) {
  const progress = rowProgressModel(row);
  if (!progress.visible) return null;

  const barBorder = progress.failed ? "#7f1d1d" : progress.active ? "#1d4ed8" : "#334155";
  const barFill = progress.failed ? "#7f1d1d" : progress.active ? "#38bdf8" : "#22c55e";
  const textColor = progress.failed ? "#fecaca" : progress.active ? "#bfdbfe" : "#bbf7d0";
  const progressWidth = 240;

  return (
    <div
      style={{
        marginTop: 6,
        display: "grid",
        gap: 4,
        width: progressWidth,
        minWidth: progressWidth,
        maxWidth: progressWidth,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 42px",
          alignItems: "center",
          gap: 8,
          color: textColor,
          fontSize: 11,
          lineHeight: 1.2,
          height: 14,
          minHeight: 14,
          maxHeight: 14,
        }}
      >
        <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{progress.label}</span>
        <span style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{Math.round(progress.percent)}%</span>
      </div>
      <div
        aria-label={`${progress.label} progress`}
        style={{
          width: "100%",
          minWidth: "100%",
          maxWidth: "100%",
          height: 8,
          minHeight: 8,
          maxHeight: 8,
          border: `1px solid ${barBorder}`,
          borderRadius: 999,
          overflow: "hidden",
          background: "rgba(15, 23, 42, 0.95)",
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${Math.max(3, Math.min(100, progress.percent))}%`,
            background: barFill,
            opacity: progress.active ? 0.82 : 0.68,
            transition: "width 240ms ease-out",
          }}
        />
      </div>
      <div
        style={{
          color: "#94a3b8",
          fontSize: 10,
          lineHeight: 1.25,
          minHeight: 26,
          maxHeight: 26,
          overflow: "hidden",
          overflowWrap: "anywhere",
        }}
        title={progress.detail || ""}
      >
        {progress.detail || ""}
      </div>
    </div>
  );
}

function notifyManagedDataUpdated(detail?: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent("multiviewer:managed-data-updated", { detail: detail || {} }));
}

type WorkbenchStatusFilter = "all" | "ready" | "viewer_ready" | "building" | "failed";

function normalizedStatusState(row: SourceIntakeWorkbenchRow): string {
  const lifecycleState = backendLifecycleState(row);
  if (lifecycleState) return lifecycleState;
  const status = row.status as unknown;
  if (status && typeof status === "object") {
    const record = status as Record<string, unknown>;
    const state = String(record.state || "").trim().toLowerCase();
    if (state) return state;
  }
  if (row.managed_output?.viewer_ready || String(row.managed_state || "").toLowerCase() === "viewer_ready") {
    return "viewer_ready";
  }
  return String(row.conversion_state || row.managed_state || "").trim().toLowerCase();
}

function rowMatchesStatusFilter(row: SourceIntakeWorkbenchRow, filter: WorkbenchStatusFilter): boolean {
  if (filter === "all") return true;
  const state = normalizedStatusState(row);
  if (filter === "viewer_ready") return rowIsManaged(row) || state === "viewer_ready" || state === "managed";
  if (filter === "building") return state === "building" || state === "running" || state === "submitted";
  if (filter === "failed") return state === "failed" || state === "error";
  if (filter === "ready") return state === "ready" || state === "not_started" || state === "not_converted";
  return true;
}

function normalizeWorkbenchSearchValue(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[\s_\-./\\:]+/g, "")
    .trim();
}

function collectWorkbenchSearchParts(value: unknown, parts: string[], depth = 0): void {
  if (value === null || value === undefined || depth > 4) return;

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    const raw = String(value).trim();
    if (raw) parts.push(raw);
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((item) => collectWorkbenchSearchParts(item, parts, depth + 1));
    return;
  }

  if (typeof value === "object") {
    Object.entries(value as Record<string, unknown>).forEach(([key, item]) => {
      const lowerKey = key.toLowerCase();
      if (
        lowerKey.includes("path") ||
        lowerKey.includes("file") ||
        lowerKey.includes("name") ||
        lowerKey.includes("line") ||
        lowerKey.includes("survey") ||
        lowerKey.includes("volume") ||
        lowerKey.includes("candidate") ||
        lowerKey.includes("package") ||
        lowerKey.includes("source") ||
        lowerKey.includes("document") ||
        lowerKey.includes("id")
      ) {
        collectWorkbenchSearchParts(item, parts, depth + 1);
      }
    });
  }
}

function rowSearchText(row: SourceIntakeWorkbenchRow): string {
  const parts: string[] = [];

  collectWorkbenchSearchParts(row, parts);

  return Array.from(new Set(parts))
    .join(" ")
    .toLowerCase();
}

function rowMatchesSearchText(row: SourceIntakeWorkbenchRow, query: string): boolean {
  const rawQuery = query.trim();
  if (rawQuery.length < 2) return true;

  const rawNeedle = rawQuery.toLowerCase();
  const normalizedNeedle = normalizeWorkbenchSearchValue(rawQuery);
  const haystack = rowSearchText(row);
  const normalizedHaystack = normalizeWorkbenchSearchValue(haystack);

  return (
    haystack.includes(rawNeedle) ||
    (normalizedNeedle.length >= 2 && normalizedHaystack.includes(normalizedNeedle))
  );
}

export default function SourceIntakeWorkbenchPanel({ repositoryId, mode = "3d", refreshSignal = 0, onViewIndexedPreview }: SourceIntakeWorkbenchPanelProps) {
  const [payload, setPayload] = useState<SourceIntakeWorkbenchPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionRunning, setActionRunning] = useState(false);
  const [geometryQaqcReport, setGeometryQaqcReport] = useState<Record<string, any> | null>(null);
  const [statusFilter, setStatusFilter] = useState<WorkbenchStatusFilter>("all");
  const [searchText, setSearchText] = useState("");
  const [build2DConfirmOpen, setBuild2DConfirmOpen] = useState(false);
  const [build3DConfirmOpen, setBuild3DConfirmOpen] = useState(false);
  const [documentModalRow, setDocumentModalRow] = useState<SourceIntakeWorkbenchRow | null>(null);
  const [documentReview, setDocumentReview] = useState<Record<string, any> | null>(null);
  const [documentReviewLoading, setDocumentReviewLoading] = useState(false);
  const [documentActionRunning, setDocumentActionRunning] = useState(false);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<Set<string>>(() => new Set());
  const [documentModalError, setDocumentModalError] = useState<string | null>(null);
  const [expandedFilenameRowKey, setExpandedFilenameRowKey] = useState<string | null>(null);

  const toggleExpandedFilenameRow = (key: string) => {
    setExpandedFilenameRowKey((current) => (current === key ? null : key));
  };

  const loadWorkbench = async (options?: { silent?: boolean }) => {
    if (!options?.silent) setLoading(true);
    setError(null);
    try {
      const data = await fetchSourceIntakeWorkbenchV2(repositoryId || undefined, mode);
      setPayload(data);
      setSelectedKeys((current) => {
        const validKeys = new Set((data.rows || []).map((row, index) => rowKey(row, index)));
        return new Set([...current].filter((key) => validKeys.has(key)));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (!options?.silent) setLoading(false);
    }
  };

  useEffect(() => {
    void loadWorkbench();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repositoryId, mode, refreshSignal]);

  useEffect(() => {
    const handleSourceIntakeUpdated = (event: Event) => {
      const detail = (event as CustomEvent)?.detail || {};
      const action = String(detail?.action || "").trim();
      const eventRepositoryId = detail?.repository_id ? String(detail.repository_id) : "";
      const matchesRepository = !eventRepositoryId || !repositoryId || eventRepositoryId === repositoryId;

      setSelectedKeys(new Set());

      if (action === "use-in-workbench" && matchesRepository) {
        void (async () => {
          await useRepositoryInSourceIntakeWorkbenchV2(eventRepositoryId || repositoryId || undefined, mode);
          await loadWorkbench({ silent: true });
        })();
        return;
      }

      void loadWorkbench({ silent: true });
    };

    window.addEventListener("multiviewer:source-intake-updated", handleSourceIntakeUpdated);
    return () => {
      window.removeEventListener("multiviewer:source-intake-updated", handleSourceIntakeUpdated);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repositoryId, mode]);

  const backendRows = payload?.rows || [];
  const rows = backendRows;
  const displaySummary = ((payload as any)?.summary || null);
  const displayRowCount = ((payload as any)?.row_count ?? rows.length);
  const hasActiveRows = useMemo(() => rows.some(rowHasActiveJob), [rows]);
  const hadActiveRowsRef = useRef(false);

  useEffect(() => {
    if (!hasActiveRows) return;
    const timer = window.setInterval(() => {
      void loadWorkbench({ silent: true });
    }, 2500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActiveRows, repositoryId]);

  useEffect(() => {
    if (hasActiveRows) {
      hadActiveRowsRef.current = true;
      return;
    }
    if (hadActiveRowsRef.current) {
      hadActiveRowsRef.current = false;
      notifyManagedDataUpdated({ source: "source-intake-workbench", action: "active-jobs-finished" });
      void loadWorkbench({ silent: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActiveRows]);

  useEffect(() => {
    if (!actionStatus) return;

    const normalizedStatus = actionStatus.toLowerCase();
    const hasCompleted3DManagedOutput = rows.some((row) => is3DRow(row) && rowIsManaged(row));
    const hasCompleted2DManagedOutput = rows.some((row) => is2DRow(row) && rowIsManaged(row));
    const hasCompleted3DIndex = rows.some((row) => {
      const state = rowJobState(row);
      return is3DRow(row) && rowHasIndexJob(row) && (state === "complete" || state === "completed");
    });

    if (
      !hasActiveRows &&
      hasCompleted3DIndex &&
      (
        normalizedStatus.startsWith("build index submitted") ||
        normalizedStatus.startsWith("submitted build index") ||
        normalizedStatus.startsWith("submitting build index")
      )
    ) {
      setActionStatus("3D index complete. View Indexed Preview is now available.");
      return;
    }

    if (
      !hasActiveRows &&
      hasCompleted3DManagedOutput &&
      (
        normalizedStatus.startsWith("build 3d volume submitted") ||
        normalizedStatus.startsWith("submitted build 3d volume")
      )
    ) {
      setActionStatus("3D Volume conversion complete. Output is available in Managed Data.");
      return;
    }


    if (
      !hasActiveRows &&
      hasCompleted2DManagedOutput &&
      (
        normalizedStatus.startsWith("build 2d line submitted") ||
        normalizedStatus.startsWith("submitted build 2d line")
      )
    ) {
      setActionStatus("2D Line conversion complete. Output is available in Managed Data.");
    }
  }, [actionStatus, rows, hasActiveRows]);

  const normalizedSearch = searchText.trim();
  const visibleRows = useMemo(
    () => rows.filter((row) => rowMatchesStatusFilter(row, statusFilter) && rowMatchesSearchText(row, normalizedSearch)),
    [rows, statusFilter, normalizedSearch]
  );
  const selectedRows = useMemo(
    () => visibleRows.filter((row, index) => selectedKeys.has(rowKey(row, index))),
    [visibleRows, selectedKeys]
  );

  const selectedCount = selectedRows.length;
  const allSelected = visibleRows.length > 0 && selectedCount === visibleRows.length;

  const selectedLineIdsForDocuments = useMemo(
    () => mode === "2d" ? selectedRows.map((row) => String(row.line_id || "").trim()).filter(Boolean) : [],
    [mode, selectedRows]
  );

  const documentWorkflowIs3D = mode === "3d";
  const surveyDocumentActionLabel = documentWorkflowIs3D
    ? "Apply survey-level document to 3D package"
    : "Apply survey-level document to all lines";
  const singleCandidateDocumentActionLabel = documentWorkflowIs3D
    ? "Assign selected documents to this volume only"
    : "Assign selected documents to this line only";
  const selectedLineDocumentActionLabel = "Assign selected documents to selected lines";

  const openDocumentModal = async (row: SourceIntakeWorkbenchRow) => {
    const candidateId = candidateIdForDocuments(row);
    if (!candidateId) {
      setActionStatus("Cannot open document assignment: row has no candidate id.");
      return;
    }
    setDocumentModalRow(row);
    setDocumentReview(null);
    setSelectedDocumentIds(new Set());
    setDocumentModalError(null);
    setDocumentReviewLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("mode", mode || "2d");
      if (selectedLineIdsForDocuments.length > 0) params.set("selected_line_ids", selectedLineIdsForDocuments.join(","));
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const response = await fetch(`/api/source-intake/candidates/${encodeURIComponent(candidateId)}/document-assignment-review${suffix}`);
      if (!response.ok) throw new Error(await response.text());
      setDocumentReview(await response.json());
    } catch (err) {
      setDocumentModalError(err instanceof Error ? err.message : String(err));
    } finally {
      setDocumentReviewLoading(false);
    }
  };

  const closeDocumentModal = () => {
    if (documentActionRunning) return;
    setDocumentModalRow(null);
    setDocumentReview(null);
    setSelectedDocumentIds(new Set());
    setDocumentModalError(null);
  };

  const toggleDocumentSelection = (documentId: string) => {
    setSelectedDocumentIds((current) => {
      const next = new Set(current);
      if (next.has(documentId)) next.delete(documentId);
      else next.add(documentId);
      return next;
    });
  };

  const submitDocumentAssignment = async (action: "survey_all_lines" | "selected_lines" | "this_line" | "non_geophysical" | "clear") => {
    if (!documentModalRow) return;
    const candidateId = candidateIdForDocuments(documentModalRow);
    const documentIds = [...selectedDocumentIds];
    if (!candidateId) {
      setDocumentModalError("Cannot assign documents: row has no candidate id.");
      return;
    }
    if (action !== "clear" && documentIds.length === 0) {
      setDocumentModalError("Select at least one document first.");
      return;
    }
    if (action === "selected_lines" && selectedLineIdsForDocuments.length === 0) {
      setDocumentModalError("Select one or more 2D line rows in the workbench first.");
      return;
    }
    setDocumentActionRunning(true);
    setDocumentModalError(null);
    try {
      const response = await fetch("/api/source-intake/document-assignments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: candidateId, action, mode: mode || "2d", document_ids: documentIds, line_ids: selectedLineIdsForDocuments }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      setDocumentReview(data.review || null);
      setSelectedDocumentIds(new Set());
      await loadWorkbench({ silent: true });
      setActionStatus("Document assignments saved.");
    } catch (err) {
      setDocumentModalError(err instanceof Error ? err.message : String(err));
    } finally {
      setDocumentActionRunning(false);
    }
  };


  const toolbarState = useMemo(() => {
    const is2DMode = mode === "2d";
    const is3DMode = mode === "3d";
    const noneSelected = selectedRows.length === 0;
    const has2d = selectedRows.some(is2DRow);
    const has3d = selectedRows.some(is3DRow);
    const hasManaged = selectedRows.some(rowIsManaged);
    const hasUnknownType = selectedRows.some((row) => !is2DRow(row) && !is3DRow(row));
    const mixedDimensionality = selectedRows.length > 1 && ((has2d && has3d) || hasUnknownType);
    const all2d = is2DMode && !noneSelected && selectedRows.every(is2DRow);
    const all3d = is3DMode && !noneSelected && selectedRows.every(is3DRow);

    const approve = !noneSelected && selectedRows.every((row) => actionEnabled(row, "approve"));
    const exclude = !noneSelected && selectedRows.every((row) => actionEnabled(row, "exclude"));
    const build2d = is2DMode && all2d && !hasManaged && selectedRows.every((row) => actionEnabled(row, "build_2d_line"));
    const build3d = is3DMode && all3d && !hasManaged && selectedRows.every((row) => actionEnabled(row, "build_3d_volume"));
    const geometryQaqc = is3DMode;
    const buildIndex = is3DMode && all3d && !hasManaged && selectedRows.every((row) => actionEnabled(row, "build_index"));
    const show2DActions = is2DMode;
    const show3DActions = is3DMode;
    const showIndexActions = is3DMode;

    let message = "Select rows to enable valid toolbar actions.";
    if (!noneSelected) {
      if (mixedDimensionality) {
        message = "Mixed or unknown row types selected. Build actions are disabled until the selection contains only compatible 2D or 3D rows.";
      } else if (is2DMode && has3d) {
        message = "This is the 2D intake tab. 3D rows are not valid for 2D actions.";
      } else if (is3DMode && has2d) {
        message = "This is the 3D intake tab. 2D rows are not valid for 3D actions.";
      } else if (all2d && hasManaged) {
        message = "Selected managed 2D rows already have managed output. Build actions are disabled.";
      } else if (all3d && hasManaged) {
        message = "Selected managed 3D rows already have managed output. Build actions are disabled.";
      } else if (hasManaged) {
        message = "Selected rows already have managed output. Build actions are disabled.";
      } else if (all2d) {
        message = build2d ? "Selected rows are eligible for Build 2D Line." : "Selected rows are 2D candidates, but the backend has not enabled Build 2D Line for all selected rows.";
      } else if (all3d) {
        message = build3d ? "Selected rows are eligible for Build 3D Volume." : "Selected rows are 3D candidates, but the backend has not enabled Build 3D Volume for all selected rows.";
      }
    }

    return {
      approve,
      exclude,
      build2d,
      build3d,
      geometryQaqc,
      buildIndex,
      show2DActions,
      show3DActions,
      showIndexActions,
      noneSelected,
      mixedDimensionality,
      hasManaged,
      message,
    };
  }, [mode, selectedRows]);

  const selectedBuild2DRows = useMemo(
    () => mode === "2d" ? selectedRows.filter((row) => is2DRow(row) && actionEnabled(row, "build_2d_line") && !rowIsManaged(row)) : [],
    [mode, selectedRows]
  );

  const selectedBuild3DRows = useMemo(
    () =>
      mode === "3d"
        ? selectedRows.filter(
            (row) =>
              is3DRow(row) &&
              actionEnabled(row, "build_3d_volume") &&
              Boolean(actionUrl(row, "build_3d_volume")) &&
              !rowIsManaged(row)
          )
        : [],
    [mode, selectedRows]
  );

  const selectedBuildIndexRows = useMemo(
    () =>
      mode === "3d"
        ? selectedRows.filter(
            (row) =>
              is3DRow(row) &&
              actionEnabled(row, "build_index") &&
              Boolean(actionUrl(row, "build_index")) &&
              !rowIsManaged(row)
          )
        : [],
    [mode, selectedRows]
  );

  const selectedGeometryQaqcRows = useMemo(
    () =>
      mode === "3d"
        ? selectedRows.filter((row) => is3DRow(row) && actionEnabled(row, "geometry_qaqc") && Boolean(actionUrl(row, "geometry_qaqc")))
        : [],
    [mode, selectedRows]
  );

  const selectedIndexedPreviewRows = useMemo(
    () => mode === "3d" ? selectedRows.filter((row) => is3DRow(row) && Boolean(row.candidate_id || row.source_segy_file_id)) : [],
    [mode, selectedRows]
  );

  const handleViewIndexedPreview = async () => {
    if (actionRunning || selectedIndexedPreviewRows.length !== 1) return;

    const row = selectedIndexedPreviewRows[0];
    const candidateId = row.candidate_id || row.source_segy_file_id;
    if (!candidateId) {
      setError("Selected row has no Source Intake candidate id.");
      return;
    }

    setActionRunning(true);
    setError(null);
    setActionStatus("Opening indexed preview…");

    try {
      const response = await fetch(`/api/source-intake/candidates/${encodeURIComponent(candidateId)}/indexed-preview-viewer-source`);
      if (!response.ok) {
        const body = await response.text();
        throw new Error(`Indexed preview viewer source failed (${response.status}): ${body || response.statusText}`);
      }

      const payload = await response.json();
      const viewerSource = payload?.viewer_source;
      if (!viewerSource || !viewerSource.dataset_id) {
        throw new Error("Indexed preview viewer source response did not include viewer_source.dataset_id.");
      }

      onViewIndexedPreview?.(viewerSource);
      setActionStatus("Indexed preview opened in the 3D viewer.");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setActionStatus("Indexed preview could not be opened.");
    } finally {
      setActionRunning(false);
    }
  };

  const handleRunGeometryQaqc = async () => {
    const candidates = selectedGeometryQaqcRows;
    if (candidates.length !== 1 || actionRunning) return;

    const row = candidates[0];
    const url = actionUrl(row, "geometry_qaqc");
    if (!url) {
      setError("Selected row has no backend Geometry QAQC action URL.");
      return;
    }

    setActionRunning(true);
    setError(null);
    setActionStatus("Running Geometry QAQC for selected row…");

    try {
      const response = await fetch(url, { method: "POST" });
      const body = await response.text();
      if (!response.ok) {
        throw new Error(`Geometry QAQC request failed (${response.status}): ${body || response.statusText}`);
      }
      const report = body ? JSON.parse(body) : null;
      setGeometryQaqcReport(report);
      const status = String(report?.status || "complete").replace(/_/g, " ");
      setActionStatus(`Geometry QAQC ${status}. Review the report before using geometry-sensitive actions.`);
      await loadWorkbench({ silent: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setActionStatus("Geometry QAQC failed.");
    } finally {
      setActionRunning(false);
    }
  };

  const handleBuildIndex = async () => {
    const candidates = selectedBuildIndexRows;
    if (candidates.length === 0 || !toolbarState.buildIndex || actionRunning) return;

    setActionRunning(true);
    setActionStatus(`Submitting Build Index for ${candidates.length} selected row${candidates.length === 1 ? "" : "s"}...`);
    setError(null);

    const succeeded: string[] = [];
    try {
      for (const row of candidates) {
        const url = actionUrl(row, "build_index");
        if (!url) {
          throw new Error(`Selected row has no backend Build Index action URL: ${row.filename || "unknown file"}`);
        }

        const response = await fetch(url, { method: "POST" });
        if (!response.ok) {
          const body = await response.text();
          throw new Error(`Build Index request failed (${response.status}): ${body || response.statusText}`);
        }

        succeeded.push(row.candidate_id || row.source_segy_file_id || row.filename || url);
      }

      setActionStatus(`Build Index submitted for ${succeeded.length} row${succeeded.length === 1 ? "" : "s"}. Watch the row progress meter for completion.`);
      await loadWorkbench();
      notifyManagedDataUpdated({ source: "source-intake-workbench", action: "build-index", succeeded: succeeded.length });
      setSelectedKeys(new Set());
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setActionStatus(`Build Index failed after ${succeeded.length} successful submission${succeeded.length === 1 ? "" : "s"}.`);
    } finally {
      setActionRunning(false);
    }
  };

  const openBuild2DConfirmation = () => {
    if (!toolbarState.build2d || actionRunning || selectedBuild2DRows.length === 0) return;
    setBuild2DConfirmOpen(true);
  };

  const handleBuild2DLine = async () => {
    const candidates = selectedBuild2DRows;
    if (candidates.length === 0 || !toolbarState.build2d || actionRunning) return;

    setActionRunning(true);
    setActionStatus(`Submitting Build 2D Line for ${candidates.length} selected row${candidates.length === 1 ? "" : "s"}…`);
    setError(null);

    const succeeded: string[] = [];
    try {
      for (const row of candidates) {
        const candidateId = row.candidate_id || row.source_segy_file_id;
        if (!candidateId) {
          throw new Error(`Selected row has no candidate_id/source_segy_file_id: ${row.filename || "unknown file"}`);
        }
        await buildSourceIntake2DLine(candidateId);
        succeeded.push(candidateId);
      }
      setActionStatus(`Submitted Build 2D Line for ${succeeded.length} row${succeeded.length === 1 ? "" : "s"}. Progress will update in the affected row${succeeded.length === 1 ? "" : "s"}.`);
      await loadWorkbench();
      notifyManagedDataUpdated({ source: "source-intake-workbench", action: "build-2d-line", succeeded: succeeded.length });
      setSelectedKeys(new Set());
      setBuild2DConfirmOpen(false);
      setActionStatus(`Build 2D Line submitted for ${succeeded.length} row${succeeded.length === 1 ? "" : "s"}. Watch the row progress meter for completion.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setActionStatus(`Build 2D Line failed after ${succeeded.length} successful submission${succeeded.length === 1 ? "" : "s"}.`);
    } finally {
      setActionRunning(false);
    }
  };

  const openBuild3DConfirmation = () => {
    if (!toolbarState.build3d || actionRunning || selectedBuild3DRows.length === 0) return;
    setBuild3DConfirmOpen(true);
  };

  const handleBuild3DVolume = async () => {
    const candidates = selectedBuild3DRows;
    if (candidates.length === 0 || !toolbarState.build3d || actionRunning) return;

    setActionRunning(true);
    setActionStatus(`Submitting Build 3D Volume for ${candidates.length} selected row${candidates.length === 1 ? "" : "s"}…`);
    setError(null);

    const succeeded: string[] = [];
    try {
      for (const row of candidates) {
        const url = actionUrl(row, "build_3d_volume");
        if (!url) {
          throw new Error(`Selected row has no backend Build 3D action URL: ${row.filename || "unknown file"}`);
        }

        const response = await fetch(url, { method: "POST" });
        if (!response.ok) {
          const body = await response.text();
          throw new Error(`Build 3D request failed (${response.status}): ${body || response.statusText}`);
        }

        succeeded.push(row.candidate_id || row.source_segy_file_id || row.filename || url);
      }

      setActionStatus(`Submitted Build 3D Volume for ${succeeded.length} row${succeeded.length === 1 ? "" : "s"}. Progress will update in the affected row${succeeded.length === 1 ? "" : "s"}.`);
      await loadWorkbench();
      notifyManagedDataUpdated({ source: "source-intake-workbench", action: "build-3d-volume", succeeded: succeeded.length });
      setSelectedKeys(new Set());
      setBuild3DConfirmOpen(false);
      setActionStatus(`Build 3D Volume submitted for ${succeeded.length} row${succeeded.length === 1 ? "" : "s"}. Watch the row progress meter for completion.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setActionStatus(`Build 3D Volume failed after ${succeeded.length} successful submission${succeeded.length === 1 ? "" : "s"}.`);
    } finally {
      setActionRunning(false);
    }
  };


  const toggleRow = (key: string) => {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelectedKeys(new Set());
      return;
    }
    setSelectedKeys(new Set(visibleRows.map((row, index) => rowKey(row, index))));
  };

  const buttonStyle = (enabled: boolean) => ({
    border: `1px solid ${enabled ? "#38bdf8" : "#475569"}`,
    color: enabled ? "#7dd3fc" : "#94a3b8",
    background: "transparent",
    borderRadius: 8,
    padding: "7px 10px",
    cursor: enabled ? "pointer" : "not-allowed",
    opacity: enabled ? 1 : 0.55,
    fontSize: 12,
    fontWeight: 700,
  });


  const handleWorkbenchRefresh = () => {
    setError(null);

    const normalizedActionStatus = String(actionStatus || "").trim().toLowerCase();
    const shouldClearTransientStatus = Boolean(
      normalizedActionStatus &&
        (
          normalizedActionStatus.startsWith("submitting") ||
          normalizedActionStatus.startsWith("submitted") ||
          normalizedActionStatus.startsWith("refreshing") ||
          normalizedActionStatus.startsWith("opening") ||
          normalizedActionStatus.startsWith("running") ||
          normalizedActionStatus.startsWith("cleared ") ||
          normalizedActionStatus === "document assignments saved."
        )
    );

    if (!actionRunning && shouldClearTransientStatus) {
      setActionStatus(null);
    }

    void loadWorkbench();
  };


  const handleClearSelectedFromWorkbench = async () => {
    const rowsToClear = selectedRows;
    const candidateIds = Array.from(
      new Set(
        rowsToClear
          .map((row) => row.candidate_id || row.source_segy_file_id)
          .filter((value): value is string => Boolean(value))
      )
    );

    if (!candidateIds.length) {
      setActionStatus("Select one or more rows to clear from Selection and Conversion.");
      return;
    }

    setActionRunning(true);
    setError(null);
    setActionStatus(`Clearing ${candidateIds.length} selected row${candidateIds.length === 1 ? "" : "s"} from Selection and Conversion…`);

    try {
      const result = await clearSelectedSourceIntakeWorkbenchV2(repositoryId || undefined, mode, candidateIds);
      const clearedCount = Number(result?.cleared_count || candidateIds.length);
      setPayload(result);
      setSelectedKeys(new Set());
      setActionStatus(`Cleared ${clearedCount} selected row${clearedCount === 1 ? "" : "s"} from Selection and Conversion.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setActionStatus("Clear failed.");
    } finally {
      setActionRunning(false);
    }
  };

  return (
    <section
      className="source-intake-workbench-panel"
      style={{ border: "1px solid #334155", borderRadius: 10, background: "#0b1220", overflow: "hidden" }}
    >
      <div style={{ padding: 12, borderBottom: "1px solid #334155", display: "grid", gap: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 750, color: "#f8fafc" }}>Selection and Conversion</div>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 3 }}>
              Select source rows, review candidate readiness, and use backend-owned actions for conversion workflows.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={handleWorkbenchRefresh}
              disabled={loading}
              style={{ ...buttonStyle(true), minWidth: 84 }}
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
            <button
              type="button"
              onClick={() => void handleClearSelectedFromWorkbench()}
              disabled={loading || actionRunning || selectedCount === 0}
              style={{ ...buttonStyle(selectedCount > 0 && !loading && !actionRunning), minWidth: 84 }}
              title="Clear selected rows from Selection and Conversion. Backend records and artifacts are retained."
            >
              Clear
            </button>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ color: "#cbd5e1", fontSize: 12, marginRight: 4 }}>
            {selectedCount} selected / {visibleRows.length} shown
          </span>
          {hasActiveRows && (
            <span style={{ color: "#bfdbfe", fontSize: 12, marginRight: 4 }}>
              Active conversion running — rows refresh automatically
            </span>
          )}
          <button type="button" disabled={actionRunning || !toolbarState.approve} style={buttonStyle(!actionRunning && toolbarState.approve)} title="Placeholder only; approve action is not wired in this block">Approve selected</button>
          <button type="button" disabled={actionRunning || !toolbarState.exclude} style={buttonStyle(!actionRunning && toolbarState.exclude)} title="Placeholder only; exclude action is not wired in this block">Exclude selected</button>
          {toolbarState.show2DActions && (
            <button
              type="button"
              disabled={actionRunning || !toolbarState.build2d}
              style={buttonStyle(!actionRunning && toolbarState.build2d)}
              title={toolbarState.build2d ? "Submit Build 2D Line for selected eligible rows" : "Select eligible 2D rows to enable Build 2D Line"}
              onClick={openBuild2DConfirmation}
            >
              {actionRunning ? "Submitting…" : "Build 2D Line"}
            </button>
          )}
          {toolbarState.show3DActions && (
            <>
              <button
                type="button"
                disabled={actionRunning || !toolbarState.build3d || selectedBuild3DRows.length === 0}
                style={buttonStyle(!actionRunning && toolbarState.build3d && selectedBuild3DRows.length > 0)}
                title={toolbarState.build3d ? "Submit Build 3D Volume for selected eligible rows" : "Select eligible 3D rows to enable Build 3D Volume"}
                onClick={openBuild3DConfirmation}
              >
                {actionRunning ? "Submitting…" : "Build 3D Volume"}
              </button>
              <button
                type="button"
                disabled={actionRunning || !toolbarState.geometryQaqc || selectedGeometryQaqcRows.length !== 1}
                style={buttonStyle(!actionRunning && toolbarState.geometryQaqc && selectedGeometryQaqcRows.length === 1)}
                title={selectedGeometryQaqcRows.length === 1 ? "Run read-only geometry QAQC for the selected SEG-Y row" : "Select one eligible 3D row to run Geometry QAQC"}
                onClick={() => void handleRunGeometryQaqc()}
              >
                {actionRunning ? "Running…" : "Run Geometry QAQC"}
              </button>
            </>
          )}
          {toolbarState.showIndexActions && (
            <>
              <button
                type="button"
                disabled={actionRunning || !toolbarState.buildIndex || selectedBuildIndexRows.length === 0}
                style={buttonStyle(!actionRunning && toolbarState.buildIndex && selectedBuildIndexRows.length > 0)}
                title={toolbarState.buildIndex ? "Build indexed SEG-Y preview for selected eligible 3D rows" : "Select eligible 3D rows to enable Build Index"}
                onClick={() => void handleBuildIndex()}
              >
                {actionRunning ? "Submitting..." : "Build Index"}
              </button>
              <button
                type="button"
                disabled={actionRunning || !onViewIndexedPreview || selectedIndexedPreviewRows.length !== 1}
                style={buttonStyle(!actionRunning && Boolean(onViewIndexedPreview) && selectedIndexedPreviewRows.length === 1)}
                title={selectedIndexedPreviewRows.length === 1 ? "Open indexed SEG-Y preview in the 3D viewer" : "Select one indexed 3D source row to view indexed preview"}
                onClick={() => void handleViewIndexedPreview()}
              >
                View Indexed Preview
              </button>
            </>
          )}
          <button type="button" disabled={actionRunning || !selectedCount} style={buttonStyle(!actionRunning && selectedCount > 0)} onClick={() => setSelectedKeys(new Set())}>
            Clear selection
          </button>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#cbd5e1", fontSize: 12 }}>
            Status
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.currentTarget.value as WorkbenchStatusFilter)}
              style={{ border: "1px solid #475569", borderRadius: 7, background: "transparent", color: "#e5e7eb", padding: "6px 8px", fontSize: 12 }}
            >
              <option value="all">All</option>
              <option value="ready">Ready</option>
              <option value="viewer_ready">Viewer Ready</option>
              <option value="building">Building</option>
              <option value="failed">Failed</option>
            </select>
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#cbd5e1", fontSize: 12 }}>
            Search
            <input
              type="search"
              value={searchText}
              onChange={(event) => setSearchText(event.currentTarget.value)}
              placeholder="Type 2+ chars: line, file, survey, path, document…"
              style={{ width: 260, border: "1px solid #475569", borderRadius: 7, background: "transparent", color: "#e5e7eb", padding: "6px 8px", fontSize: 12 }}
            />
          </label>
          <span style={{ color: "#94a3b8", fontSize: 12 }}>
            Showing {visibleRows.length} of {rows.length} rows
          </span>
          {(statusFilter !== "all" || searchText.trim()) && (
            <button
              type="button"
              onClick={() => {
                setStatusFilter("all");
                setSearchText("");
                setSelectedKeys(new Set());
              }}
              style={buttonStyle(true)}
            >
              Clear filters
            </button>
          )}
        </div>

        <div
          style={{
            border: `1px solid ${toolbarState.mixedDimensionality ? "#92400e" : "#334155"}`,
            borderRadius: 8,
            padding: "8px 10px",
            color: toolbarState.mixedDimensionality ? "#fed7aa" : "#cbd5e1",
            background: toolbarState.mixedDimensionality ? "rgba(120, 53, 15, 0.20)" : "rgba(15, 23, 42, 0.55)",
            fontSize: 12,
          }}
        >
          {toolbarState.message}
        </div>

        {actionStatus && (
          <div
            style={{
              border: "1px solid #1d4ed8",
              borderRadius: 8,
              padding: "8px 10px",
              color: "#bfdbfe",
              background: "rgba(30, 64, 175, 0.18)",
              fontSize: 12,
            }}
          >
            {actionStatus}
          </div>
        )}

        {geometryQaqcReport && (
          <div
            style={{
              border: "1px solid #0f766e",
              borderRadius: 8,
              padding: "8px 10px",
              color: "#ccfbf1",
              background: "rgba(15, 118, 110, 0.16)",
              fontSize: 12,
              display: "grid",
              gap: 8,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
              <strong>Geometry QAQC Report: {titleCaseToken(geometryQaqcReport.status)}</strong>
              <button type="button" onClick={() => setGeometryQaqcReport(null)} style={buttonStyle(true)}>Close report</button>
            </div>
            <div>{String(geometryQaqcReport.summary || "No summary returned.")}</div>
            {geometryQaqcReport.selected_candidate && (
              <div style={{ color: "#99f6e4" }}>
                Selected candidate: inline byte {geometryQaqcReport.selected_candidate.inline_byte}, crossline byte {geometryQaqcReport.selected_candidate.crossline_byte}, score {geometryQaqcReport.selected_candidate.score}
              </div>
            )}
            <pre style={{ maxHeight: 260, overflow: "auto", whiteSpace: "pre-wrap", border: "1px solid #115e59", borderRadius: 8, padding: 8, margin: 0, color: "#e0f2fe", background: "rgba(8, 47, 73, 0.35)" }}>
              {JSON.stringify(geometryQaqcReport, null, 2)}
            </pre>
          </div>
        )}

        {displaySummary && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", color: "#94a3b8", fontSize: 12 }}>
            <span>Rows: {displayRowCount}</span>
            {Object.entries(displaySummary).map(([key, value]) => (
              <span key={key}>{titleCaseToken(key)}: {String(value)}</span>
            ))}
          </div>
        )}

        {error && (
          <div style={{ border: "1px solid #7f1d1d", color: "#fecaca", borderRadius: 8, padding: 10, fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>



      {build3DConfirmOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="build-3d-confirm-title"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(2, 6, 23, 0.72)",
            zIndex: 60,
            display: "grid",
            placeItems: "center",
            padding: 20,
          }}
          onClick={(event) => {
            if (event.target === event.currentTarget && !actionRunning) setBuild3DConfirmOpen(false);
          }}
        >
          <div
            style={{
              width: "min(680px, 100%)",
              border: "1px solid #334155",
              borderRadius: 12,
              background: "#0f172a",
              boxShadow: "0 24px 80px rgba(0, 0, 0, 0.45)",
              padding: 16,
            }}
          >
            <div id="build-3d-confirm-title" style={{ fontSize: 16, fontWeight: 800, color: "#f8fafc" }}>
              Confirm Build 3D Volume
            </div>
            <div style={{ marginTop: 8, color: "#cbd5e1", fontSize: 13, lineHeight: 1.5 }}>
              This will submit Build 3D Volume for {selectedBuild3DRows.length} selected row{selectedBuild3DRows.length === 1 ? "" : "s"}.
            </div>

            <div style={{ marginTop: 12, border: "1px solid #334155", borderRadius: 10, overflow: "hidden" }}>
              {selectedBuild3DRows.map((row) => (
                <div
                  key={row.candidate_id || row.source_segy_file_id || row.filename}
                  style={{
                    padding: "8px 10px",
                    borderBottom: "1px solid #1f2937",
                    color: "#e5e7eb",
                    fontSize: 12,
                  }}
                >
                  <div style={{ fontWeight: 700 }}>{valueOrDash(row.display_name || row.filename)}</div>
                  <div style={{ color: "#94a3b8", marginTop: 2 }}>{valueOrDash(row.relative_path)}</div>
                </div>
              ))}
            </div>

            {selectedBuild3DRows.length > 1 && (
              <div style={{ marginTop: 12, color: "#fbbf24", fontSize: 12 }}>
                Multiple rows are selected. Confirm only if you intentionally want to submit more than one 3D conversion job.
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button
                type="button"
                disabled={actionRunning}
                onClick={() => setBuild3DConfirmOpen(false)}
                style={buttonStyle(!actionRunning)}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={actionRunning || !toolbarState.build3d || selectedBuild3DRows.length === 0}
                onClick={() => void handleBuild3DVolume()}
                style={buttonStyle(!actionRunning && toolbarState.build3d && selectedBuild3DRows.length > 0)}
              >
                {actionRunning ? "Submitting…" : "Confirm Build 3D"}
              </button>
            </div>
          </div>
        </div>
      )}

      {documentModalRow && (
        <div role="dialog" aria-modal="true" aria-labelledby="document-assignment-title" style={{ position: "fixed", inset: 0, zIndex: 10000, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(2, 6, 23, 0.76)", padding: 24 }} onMouseDown={(event) => { if (event.target === event.currentTarget) closeDocumentModal(); }}>
          <div style={{ width: "min(980px, calc(100vw - 48px))", maxHeight: "calc(100vh - 72px)", overflow: "auto", border: "1px solid #475569", borderRadius: 12, background: "#0f172a", color: "#e5e7eb", boxShadow: "0 24px 80px rgba(0,0,0,0.55)" }}>
            <div style={{ padding: 16, borderBottom: "1px solid #334155" }}>
              <div id="document-assignment-title" style={{ fontSize: 16, fontWeight: 800, color: "#f8fafc" }}>Document Assignment</div>
              <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>{valueOrDash(documentModalRow.display_name || documentModalRow.filename)}</div>
              {!documentWorkflowIs3D && <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5e1" }}>Selected line rows available for bulk assignment: {selectedLineIdsForDocuments.length}</div>}
              {documentWorkflowIs3D && <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5e1" }}>3D volume document assignment</div>}
            </div>
            <div style={{ padding: 16, display: "grid", gap: 12 }}>
              {documentModalError && <div style={{ border: "1px solid #991b1b", borderRadius: 8, padding: 10, color: "#fecaca", background: "rgba(127, 29, 29, 0.22)", fontSize: 12 }}>{documentModalError}</div>}
              {documentReviewLoading && <div style={{ color: "#94a3b8", fontSize: 13 }}>Loading discovered documents…</div>}
              {!documentReviewLoading && documentReview && (
                <>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: 12, color: "#cbd5e1" }}>
                    <span>Discovered: {documentReview.summary?.discovered_document_count ?? 0}</span>
                    <span>Assigned: {documentReview.summary?.effective_document_count ?? 0}</span>
                    <span>Unassigned: {documentReview.summary?.unassigned_document_count ?? 0}</span>
                    <span>Assigned elsewhere: {(documentReview.summary as any)?.assigned_elsewhere_document_count ?? 0}</span>
                    <span>Non-geophysical: {documentReview.summary?.non_geophysical_count ?? 0}</span>
                  </div>
                  <div style={{ border: "1px solid #334155", borderRadius: 8, overflow: "hidden" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: "#111827", color: "#cbd5e1", textAlign: "left" }}>
                          <th style={{ padding: "8px 10px", borderBottom: "1px solid #334155" }}>Select</th>
                          <th style={{ padding: "8px 10px", borderBottom: "1px solid #334155" }}>Document</th>
                          <th style={{ padding: "8px 10px", borderBottom: "1px solid #334155" }}>Source</th>
                          <th style={{ padding: "8px 10px", borderBottom: "1px solid #334155" }}>Suggested Scope</th>
                          <th style={{ padding: "8px 10px", borderBottom: "1px solid #334155" }}>State</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(documentReview.documents || []).map((doc: any) => {
                          const docId = String(doc.document_id || "");
                          const checked = selectedDocumentIds.has(docId);
                          const state = doc.non_geophysical ? "Non-geophysical" : doc.assigned ? "Assigned" : (doc as any).assigned_elsewhere ? "Assigned elsewhere" : "Unassigned";
                          const openUrl = String(doc.open_url || doc.view_url || "").trim();
                          return (
                            <tr key={docId || doc.filename} style={{ background: checked ? "rgba(14, 165, 233, 0.08)" : "transparent" }}>
                              <td style={{ padding: "8px 10px", borderBottom: "1px solid #1f2937" }}><input type="checkbox" checked={checked} onChange={() => toggleDocumentSelection(docId)} aria-label={`Select document ${doc.filename || docId}`} /></td>
                              <td style={{ padding: "8px 10px", borderBottom: "1px solid #1f2937", color: "#e5e7eb", maxWidth: 420 }}>
                                <div style={{ fontWeight: 650, overflowWrap: "anywhere" }}>
                                  {openUrl ? <button type="button" onClick={() => window.open(openUrl, "_blank", "noopener,noreferrer")} style={{ border: 0, background: "transparent", color: "#93c5fd", padding: 0, cursor: "pointer", fontWeight: 750, textAlign: "left", overflowWrap: "anywhere" }} title="Open document">{valueOrDash(doc.filename)}</button> : valueOrDash(doc.filename)}
                                </div>
                                <div style={{ color: "#64748b", fontSize: 11, overflowWrap: "anywhere" }}>{valueOrDash(doc.relative_path)}</div>
                              </td>
                              <td style={{ padding: "8px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1" }}><div>{valueOrDash(doc.package_name || doc.package_id)}</div><div style={{ color: "#64748b", fontSize: 11 }}>{valueOrDash(doc.repository_id)}</div></td>
                              <td style={{ padding: "8px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1" }}><div>{titleCaseToken(doc.suggested_scope)}</div><div style={{ color: "#64748b", fontSize: 11 }}>{titleCaseToken(doc.match_confidence)}</div></td>
                              <td style={{ padding: "8px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1" }}>{state}</td>
                            </tr>
                          );
                        })}
                        {(!documentReview.documents || documentReview.documents.length === 0) && <tr><td colSpan={5} style={{ padding: 14, color: "#94a3b8" }}>No same-package documents available for this candidate.</td></tr>}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ display: "grid", gap: 8 }}>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-start" }}>
                      <button type="button" disabled={documentActionRunning} onClick={() => void submitDocumentAssignment("survey_all_lines")} style={buttonStyle(!documentActionRunning)}>{surveyDocumentActionLabel}</button>
                      {!documentWorkflowIs3D && <button type="button" disabled={documentActionRunning} onClick={() => void submitDocumentAssignment("selected_lines")} style={buttonStyle(!documentActionRunning)}>{selectedLineDocumentActionLabel}</button>}
                      <button type="button" disabled={documentActionRunning} onClick={() => void submitDocumentAssignment("this_line")} style={buttonStyle(!documentActionRunning)}>{singleCandidateDocumentActionLabel}</button>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                      <button className="doc-action-mark-non-geo-left" type="button" disabled={documentActionRunning} onClick={() => void submitDocumentAssignment("non_geophysical")} style={buttonStyle(!documentActionRunning)}>Mark as non-geophysical</button>
                      <button type="button" disabled={documentActionRunning} onClick={() => void submitDocumentAssignment("clear")} style={buttonStyle(!documentActionRunning)}>Clear assignment</button>
                    </div>
                  </div>
                </>
              )}
            </div>
            <div style={{ padding: 16, borderTop: "1px solid #334155", display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button type="button" disabled={documentActionRunning} onClick={closeDocumentModal} style={buttonStyle(!documentActionRunning)}>Save and return</button>
            </div>
          </div>
        </div>
      )}

      {build2DConfirmOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="build-2d-confirm-title"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(2, 6, 23, 0.74)",
            padding: 24,
          }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !actionRunning) setBuild2DConfirmOpen(false);
          }}
        >
          <div
            style={{
              width: "min(720px, calc(100vw - 48px))",
              maxHeight: "calc(100vh - 96px)",
              overflow: "auto",
              border: "1px solid #475569",
              borderRadius: 12,
              background: "#0f172a",
              color: "#e5e7eb",
              boxShadow: "0 24px 80px rgba(0,0,0,0.55)",
            }}
          >
            <div style={{ padding: 16, borderBottom: "1px solid #334155" }}>
              <div id="build-2d-confirm-title" style={{ fontSize: 16, fontWeight: 800, color: "#f8fafc" }}>
                Confirm Build 2D Line
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8", lineHeight: 1.45 }}>
                This will submit Build 2D Line for {selectedBuild2DRows.length} selected row{selectedBuild2DRows.length === 1 ? "" : "s"}.
              </div>
            </div>

            <div style={{ padding: 16, display: "grid", gap: 12 }}>
              {selectedBuild2DRows.length > 1 && (
                <div
                  style={{
                    border: "1px solid #92400e",
                    borderRadius: 8,
                    background: "rgba(120, 53, 15, 0.22)",
                    color: "#fed7aa",
                    padding: "9px 10px",
                    fontSize: 12,
                    lineHeight: 1.45,
                  }}
                >
                  Multiple rows are selected. Confirm only if you intentionally want to submit more than one 2D conversion job.
                </div>
              )}

              <div style={{ fontSize: 12, color: "#cbd5e1" }}>Selected files</div>
              <div
                style={{
                  border: "1px solid #334155",
                  borderRadius: 8,
                  background: "#111827",
                  maxHeight: 260,
                  overflow: "auto",
                }}
              >
                {selectedBuild2DRows.map((row, index) => (
                  <div
                    key={row.candidate_id || row.source_segy_file_id || `${row.filename || "row"}-${index}`}
                    style={{
                      padding: "8px 10px",
                      borderBottom: index === selectedBuild2DRows.length - 1 ? "none" : "1px solid #1f2937",
                      fontSize: 12,
                      color: "#e5e7eb",
                      overflowWrap: "anywhere",
                    }}
                  >
                    {valueOrDash(row.display_name || row.filename)}
                  </div>
                ))}
              </div>
            </div>

            <div style={{ padding: 16, borderTop: "1px solid #334155", display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button
                type="button"
                disabled={actionRunning}
                onClick={() => setBuild2DConfirmOpen(false)}
                style={buttonStyle(!actionRunning)}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={actionRunning || !toolbarState.build2d || selectedBuild2DRows.length === 0}
                onClick={() => void handleBuild2DLine()}
                style={buttonStyle(!actionRunning && toolbarState.build2d && selectedBuild2DRows.length > 0)}
              >
                {actionRunning ? "Submitting…" : "Confirm Build 2D"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1100 }}>
          <thead>
            <tr style={{ background: "#111827", color: "#cbd5e1", fontSize: 12, textAlign: "left" }}>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>
                <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all source intake rows" />
              </th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>Status</th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>Type</th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>File</th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>Survey</th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>Line / Volume</th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>QAQC</th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>Supporting Docs</th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>Conversion</th>
              <th style={{ padding: "9px 10px", borderBottom: "1px solid #334155" }}>Managed Output</th>
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 && (
              <tr>
                <td colSpan={10} style={{ padding: 14, color: "#94a3b8", fontSize: 13 }}>Loading workbench rows…</td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={10} style={{ padding: 14, color: "#94a3b8", fontSize: 13 }}>
                  No source intake rows found. Select a repository and scan source items to populate the workbench.
                </td>
              </tr>
            )}
            {!loading && rows.length > 0 && visibleRows.length === 0 && (
              <tr>
                <td colSpan={10} style={{ padding: 14, color: "#94a3b8", fontSize: 13 }}>
                  No rows match the current filters. Clear filters or adjust the filename search.
                </td>
              </tr>
            )}
            {visibleRows.map((row, index) => {
              const key = rowKey(row, index);
              const selected = selectedKeys.has(key);
              const lineOrVolume = row.line_name || row.volume_name || row.line_id || "—";
              const filenameText = valueOrDash(row.display_name || row.filename);
              const filenameExpanded = expandedFilenameRowKey === key;
              return (
                <tr key={key} style={{ background: selected ? "rgba(14, 165, 233, 0.08)" : "transparent" }}>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937" }}>
                    <input type="checkbox" checked={selected} onChange={() => toggleRow(key)} aria-label={`Select ${valueOrDash(row.filename)}`} />
                  </td>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#e5e7eb", fontSize: 12 }}>
                    <div>{statusLabel(row)}</div>
                    <RowProgressMeter row={row} />
                  </td>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1", fontSize: 12 }}>
                    {titleCaseToken(row.candidate_kind || row.candidate_role)}
                  </td>
                  <td
                    style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#f8fafc", fontSize: 12, maxWidth: 320 }}
                    title={filenameText === "—" ? "" : "Click filename to expand/collapse"}
                  >
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => toggleExpandedFilenameRow(key)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          toggleExpandedFilenameRow(key);
                        }
                      }}
                      style={{
                        fontWeight: 650,
                        whiteSpace: filenameExpanded ? "normal" : "nowrap",
                        overflow: filenameExpanded ? "visible" : "hidden",
                        textOverflow: filenameExpanded ? "clip" : "ellipsis",
                        overflowWrap: filenameExpanded ? "anywhere" : "normal",
                        cursor: "pointer",
                        color: filenameExpanded ? "#dbeafe" : "#f8fafc",
                      }}
                    >
                      {filenameText}
                    </div>
                    {!filenameExpanded && (
                      <div style={{ color: "#64748b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{valueOrDash(row.relative_path)}</div>
                    )}
                    {filenameExpanded && (
                      <div style={{ color: "#64748b", fontSize: 10, marginTop: 3 }}>Click filename to collapse</div>
                    )}
                  </td>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1", fontSize: 12 }}>
                    {valueOrDash(row.survey_name)}
                  </td>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1", fontSize: 12 }}>
                    {valueOrDash(lineOrVolume)}
                  </td>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1", fontSize: 12 }}>
                    <div>{geometryQaqcStatusLabel(row)}</div>
                    {geometryQaqcSummary(row) && (
                      <div style={{ color: "#94a3b8", fontSize: 10, marginTop: 3, maxWidth: 220, overflowWrap: "anywhere" }}>{geometryQaqcSummary(row)}</div>
                    )}
                  </td>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1", fontSize: 12 }}>
                    <button
                      type="button"
                      onClick={() => void openDocumentModal(row)}
                      style={{ border: "1px solid #64748b", borderRadius: 8, background: "transparent", color: "#e5e7eb", cursor: "pointer", padding: "4px 8px", fontWeight: 700, minWidth: 42 }}
                      title="Open document assignment"
                    >
                      {documentStatusLabel(row)}
                    </button>
                    <div style={{ color: "#94a3b8", fontSize: 10, marginTop: 3 }}>{documentSubtitleLabel(row)}</div>
                  </td>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1", fontSize: 12 }}>
                    {titleCaseToken(row.conversion_state)}
                  </td>
                  <td style={{ padding: "9px 10px", borderBottom: "1px solid #1f2937", color: "#cbd5e1", fontSize: 12 }}>
                    {managedOutputLabel(row)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
