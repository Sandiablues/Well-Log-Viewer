import React, { useEffect, useMemo, useState } from "react";
import {
  fetchRepositories,
  fetchSubmittedExternalRegistryView,
  refreshSegyFileStatus,
} from "../services/registryService";
import type {
  RepositoryRecord,
  SubmittedExternalRegistryView,
} from "../services/registryService";

type Props = {
  onVolumeRegistered?: () => Promise<void> | void;
  selectedRepositoryIdFromManager?: string;
};

function clean(value?: string): string {
  return value ? String(value).replaceAll("_", " ") : "unknown";
}

function formatBytes(value?: number): string {
  if (!Number.isFinite(value || NaN)) return "";
  const bytes = value || 0;
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(1)} GB`;
}

function is3DRepository(repo: RepositoryRecord): boolean {
  const text = `${repo.name || ""} ${repo.notes || ""}`.toLowerCase();

  return (
    text.includes("3d") ||
    text.includes("3d_volume_delivery") ||
    text.includes("3d_segy_intake") ||
    text.includes("single_3d_volume") ||
    text.includes("multi_version_3d_delivery")
  );
}

type SourceSegyLifecycleRepresentation = {
  key: string;
  label: string;
  state: string;
  status_label: string;
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
  representations: SourceSegyLifecycleRepresentation[];
  active_job?: {
    job_id?: string;
    action?: string;
    label?: string;
    status?: string;
    progress?: number | null;
    message?: string;
  } | null;
  monitor?: {
    state?: string;
    label?: string;
    message?: string;
  };
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function managed2dRow(payload: SourceSegyLifecycleState): SourceSegyLifecycleRepresentation | null {
  return payload.representations.find((row) => row.key === "managed_2d_line_zarr") || null;
}

function rowIsTerminal(row: SourceSegyLifecycleRepresentation | null): boolean {
  if (!row) return true;
  return row.state === "exists" || row.state === "failed" || row.state === "missing";
}

const panelStyle: React.CSSProperties = {
  border: "1px solid #334155",
  borderRadius: 10,
  background: "#0f172a",
  color: "#e5e7eb",
  padding: 14,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#94a3b8",
  marginBottom: 4,
};

const selectStyle: React.CSSProperties = {
  width: "100%",
  padding: "7px 9px",
  borderRadius: 7,
  border: "1px solid #475569",
  background: "#111827",
  color: "#f8fafc",
  fontSize: 13,
};

const utilityButtonStyle: React.CSSProperties = {
  padding: "6px 10px",
  borderRadius: 7,
  border: "1px solid #64748b",
  background: "transparent",
  color: "#cbd5e1",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};

const primaryButtonStyle: React.CSSProperties = {
  ...utilityButtonStyle,
  border: "1px solid #60a5fa",
  color: "#60a5fa",
  fontWeight: 800,
};

const dangerButtonStyle: React.CSSProperties = {
  ...utilityButtonStyle,
  border: "1px solid #f87171",
  color: "#f87171",
  fontWeight: 800,
};

export default function ExternalDataRegistryPanel({
  onVolumeRegistered,
  selectedRepositoryIdFromManager,
}: Props) {
  const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState("");

  const [view, setView] = useState<SubmittedExternalRegistryView | null>(null);
  const [selectedPackageId, setSelectedPackageId] = useState("");
  const [selectedLineId, setSelectedLineId] = useState("");

  const [loading, setLoading] = useState(false);
  const [busyFileId, setBusyFileId] = useState<string | null>(null);
  const [clearHandoffBusy, setClearHandoffBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const [lastClearResult, setLastClearResult] = useState<any | null>(null);

  const packages = view?.packages || [];
  const lines = view?.lines || [];
  const segyFiles = view?.segy_files || [];
  const documents = view?.documents || [];
  const summary = view?.summary;

  const selectedRepository = useMemo(
    () => repositories.find((repo) => repo.repository_id === selectedRepositoryId),
    [repositories, selectedRepositoryId]
  );

  const selectedPackage = useMemo(
    () => packages.find((pkg) => String(pkg.package_id) === String(selectedPackageId)),
    [packages, selectedPackageId]
  );

  const selectedLine = useMemo(
    () => lines.find((line) => String(line.line_id) === String(selectedLineId)),
    [lines, selectedLineId]
  );

  const packageLines = useMemo(
    () => lines.filter((line) => String(line.package_id) === String(selectedPackageId)),
    [lines, selectedPackageId]
  );

  const lineSegyFiles = useMemo(
    () => segyFiles.filter((file) => String(file.line_id) === String(selectedLineId)),
    [segyFiles, selectedLineId]
  );

  const packageDocuments = useMemo(
    () => documents.filter((doc) => String(doc.package_id) === String(selectedPackageId)),
    [documents, selectedPackageId]
  );

  async function loadRepositories() {
    setLoading(true);
    setError("");

    try {
      const repoRecords = await fetchRepositories();
      const twoDRepoRecords = repoRecords.filter((repo) => !is3DRepository(repo));
      setRepositories(twoDRepoRecords);

      const submittedProbeResults = await Promise.allSettled(
        twoDRepoRecords.map(async (repo) => {
          const submittedView = await fetchSubmittedExternalRegistryView({
            repositoryId: repo.repository_id,
            mode: "2d",
          });

          return {
            repositoryId: repo.repository_id,
            submittedCount: submittedView.summary?.submitted_item_count || 0,
          };
        })
      );

      const submittedRepoIds = new Set(
        submittedProbeResults
          .filter((result): result is PromiseFulfilledResult<{ repositoryId: string; submittedCount: number }> => result.status === "fulfilled")
          .filter((result) => result.value.submittedCount > 0)
          .map((result) => result.value.repositoryId)
      );

      const managerSelectionIsValid =
        selectedRepositoryIdFromManager &&
        twoDRepoRecords.some((repo) => repo.repository_id === selectedRepositoryIdFromManager);

      const currentSelectionIsValid =
        selectedRepositoryId &&
        twoDRepoRecords.some((repo) => repo.repository_id === selectedRepositoryId);

      const currentSelectionHasSubmittedItems =
        currentSelectionIsValid && submittedRepoIds.has(selectedRepositoryId);

      const firstSubmittedRepositoryId =
        twoDRepoRecords.find((repo) => submittedRepoIds.has(repo.repository_id))?.repository_id || "";

      const preferred = managerSelectionIsValid
        ? selectedRepositoryIdFromManager
        : currentSelectionHasSubmittedItems
          ? selectedRepositoryId
          : firstSubmittedRepositoryId
            ? firstSubmittedRepositoryId
            : currentSelectionIsValid
              ? selectedRepositoryId
              : twoDRepoRecords[0]?.repository_id || "";

      setSelectedRepositoryId(preferred);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load repositories");
    } finally {
      setLoading(false);
    }
  }

  async function loadSubmittedView(
    repositoryId: string,
    preserveSelection: boolean = false
  ) {
    if (!repositoryId) {
      setView(null);
      setSelectedPackageId("");
      setSelectedLineId("");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const previousPackageId = selectedPackageId;
      const previousLineId = selectedLineId;

      const payload = await fetchSubmittedExternalRegistryView({
        repositoryId,
        mode: "2d",
      });

      setView(payload);

      const nextPackageId =
        preserveSelection &&
        previousPackageId &&
        payload.packages.some((pkg) => String(pkg.package_id) === String(previousPackageId))
          ? previousPackageId
          : payload.packages[0]?.package_id || "";

      setSelectedPackageId(nextPackageId);

      const nextLineId =
        preserveSelection &&
        previousLineId &&
        payload.lines.some((line) => String(line.line_id) === String(previousLineId))
          ? previousLineId
          : payload.lines.find((line) => String(line.package_id) === String(nextPackageId))?.line_id || "";

      setSelectedLineId(nextLineId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load submitted external registry view");
      setView(null);
      setSelectedPackageId("");
      setSelectedLineId("");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRepositories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (
      selectedRepositoryIdFromManager &&
      selectedRepositoryIdFromManager !== selectedRepositoryId &&
      repositories.some((repo) => repo.repository_id === selectedRepositoryIdFromManager)
    ) {
      setSelectedRepositoryId(selectedRepositoryIdFromManager);
    }
  }, [selectedRepositoryIdFromManager, selectedRepositoryId, repositories]);

  useEffect(() => {
    loadSubmittedView(selectedRepositoryId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepositoryId]);

  useEffect(() => {
    const packageLineIds = lines
      .filter((line) => String(line.package_id) === String(selectedPackageId))
      .map((line) => String(line.line_id));

    if (selectedLineId && packageLineIds.includes(String(selectedLineId))) {
      return;
    }

    setSelectedLineId(packageLineIds[0] || "");
  }, [selectedPackageId, lines, selectedLineId]);

  async function clearSubmittedHandoff() {
    if (!selectedRepositoryId) {
      setError("Select a repository before clearing submitted handoff records.");
      return;
    }

    const ok = window.confirm(
      `Clear submitted handoff for this repository?

This removes only the submitted QAQC handoff records used by Source Intake candidate review.

It preserves the registered source repository, scan results, original files, Managed Data, Zarr, jobs, and converted datasets.`
    );

    if (!ok) return;

    setClearHandoffBusy(true);
    setNotice("");
    setError("");
    setHelpOpen(false);
    setLastClearResult(null);

    try {
      const response = await fetch(
        `/api/repositories/${encodeURIComponent(selectedRepositoryId)}/submitted-handoff/clear`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ mode: "2d", confirm: true }),
        }
      );

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        const detail = payload?.detail || payload?.message || `Clear submitted handoff failed: ${response.status}`;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }

      setNotice(
        `Submitted handoff cleared: ${payload.cleared_segy_count || 0} SEG-Y file${(payload.cleared_segy_count || 0) === 1 ? "" : "s"} and ${payload.cleared_document_count || 0} document${(payload.cleared_document_count || 0) === 1 ? "" : "s"}. Repository and scan results were preserved.`
      );
      setLastClearResult(payload);
      await loadSubmittedView(selectedRepositoryId, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear submitted handoff");
    } finally {
      setClearHandoffBusy(false);
    }
  }

  function sleepMs(ms: number) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  async function handleRefreshStatus(file: any) {
    const segyFileId = file.segy_file_id;
    if (!segyFileId) return;

    setBusyFileId(segyFileId);
    setNotice("");
    setError("");

    try {
      const result = await refreshSegyFileStatus(segyFileId as any);
      if (result?.status === "error" || result?.status === "failed") {
        setNotice("Conversion status refreshed. The previous job failed and can be retried.");
      } else {
        setNotice("Conversion status refreshed.");
      }
      await loadSubmittedView(selectedRepositoryId, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh conversion status");
    } finally {
      setBusyFileId(null);
    }
  }

  async function fetch2dLifecycle(segyFileId: string): Promise<SourceSegyLifecycleState> {
    return fetchJson<SourceSegyLifecycleState>(
      `/api/segy-files/${encodeURIComponent(segyFileId)}/lifecycle?mode=2d`
    );
  }

  async function pollLifecycleConversion(segyFileId: string) {
    let lastLifecycle: SourceSegyLifecycleState | null = null;

    for (let attempt = 0; attempt < 20; attempt += 1) {
      await sleepMs(attempt === 0 ? 500 : 1000);

      lastLifecycle = await fetch2dLifecycle(segyFileId);
      const row = managed2dRow(lastLifecycle);

      // Do not reload the whole submitted-view panel on every polling tick.
      // Full reload causes visible scroll/layout jumps. Reload only after the
      // lifecycle reaches a terminal state, or after polling ends.
      if (!lastLifecycle.active_job && rowIsTerminal(row)) {
        await loadSubmittedView(selectedRepositoryId, true);
        return lastLifecycle;
      }
    }

    await loadSubmittedView(selectedRepositoryId, true);
    return lastLifecycle;
  }

  async function handleConvert(file: any) {
    const segyFileId = file.segy_file_id;
    if (!segyFileId) return;

    setBusyFileId(segyFileId);
    setNotice("");
    setError("");

    try {
      const lifecycle = await fetch2dLifecycle(segyFileId);
      const row = managed2dRow(lifecycle);

      if (!row) {
        throw new Error("Managed 2D Line Zarr lifecycle row is missing.");
      }

      if (row.state === "exists") {
        setNotice("Managed 2D Line Zarr already exists.");
        await loadSubmittedView(selectedRepositoryId, true);
        await onVolumeRegistered?.();
        return;
      }

      if (!row.can_create || !row.action_url) {
        throw new Error(`Managed 2D Line Zarr cannot be created from state: ${row.status_label || row.state}`);
      }

      await fetchJson<any>(`${row.action_url}?mode=2d`, {
        method: "POST",
      });

      setNotice("Managed 2D Line Zarr creation queued. Monitoring lifecycle...");

      const finalLifecycle = await pollLifecycleConversion(segyFileId);
      const finalRow = finalLifecycle ? managed2dRow(finalLifecycle) : null;

      if (finalRow?.state === "exists") {
        setNotice("Managed 2D Line Zarr is ready.");
        await onVolumeRegistered?.();
      } else if (finalRow?.state === "failed") {
        setNotice("");
        setError(finalRow.status_label || "Managed 2D Line Zarr creation failed.");
      } else {
        setNotice("Managed 2D Line Zarr is still running. Use Refresh Status to update.");
      }

      await loadSubmittedView(selectedRepositoryId, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create Managed 2D Line Zarr");
    } finally {
      setBusyFileId(null);
    }
  }

  return (
    <section style={panelStyle}>
      <div style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, color: "#f8fafc" }}>External Source Registry</h3>
            <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
              Submitted QAQC handoff view. Only submitted/ready source items are shown.
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

        {error && (
          <div style={{ padding: 8, borderRadius: 7, background: "rgba(239,68,68,.15)", color: "#fecaca", fontSize: 12 }}>
            {error}
          </div>
        )}

        {notice && (
          <div style={{ padding: 8, borderRadius: 7, background: "rgba(34,197,94,.12)", color: "#bbf7d0", fontSize: 12 }}>
            <span>{notice}</span>
            {lastClearResult && (
              <button
                type="button"
                onClick={() => setHelpOpen((value) => !value)}
                title="What was cleared?"
                style={{
                  marginLeft: 8,
                  width: 18,
                  height: 18,
                  borderRadius: 999,
                  border: "1px solid #22c55e",
                  background: "transparent",
                  color: "#22c55e",
                  fontSize: 12,
                  fontWeight: 900,
                  lineHeight: "14px",
                  cursor: "pointer",
                  padding: 0,
                }}
              >
                ?
              </button>
            )}

            {helpOpen && lastClearResult && (
              <div
                style={{
                  marginTop: 8,
                  border: "1px solid #22c55e",
                  borderRadius: 8,
                  background: "#0f172a",
                  color: "#d1fae5",
                  padding: 10,
                  maxWidth: 760,
                  lineHeight: 1.45,
                  boxShadow: "0 12px 28px rgba(0,0,0,.35)",
                }}
              >
                <div style={{ fontWeight: 800, marginBottom: 6 }}>Submitted handoff cleared</div>
                <div>Only submitted QAQC handoff records were cleared for the selected repository.</div>
                <div style={{ marginTop: 8 }}>
                  <strong>Cleared:</strong> {lastClearResult.cleared_segy_count || 0} SEG-Y file(s), {lastClearResult.cleared_document_count || 0} document(s).
                </div>
                <div style={{ marginTop: 6 }}>
                  <strong>Preserved:</strong> registered repository, scan/discovery inventory, original files, Managed Data, Zarr volumes, jobs, reports, and converted datasets.
                </div>
              </div>
            )}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <label>
            <div style={labelStyle}>Repository</div>
            <select
              value={selectedRepositoryId}
              onChange={(event) => setSelectedRepositoryId(event.target.value)}
              style={selectStyle}
            >
              {repositories.map((repo) => (
                <option key={repo.repository_id} value={repo.repository_id}>
                  {repo.name} · {repo.status || "unknown"}
                </option>
              ))}
            </select>
          </label>

          <label>
            <div style={labelStyle}>Package / Survey</div>
            <select
              value={selectedPackageId}
              onChange={(event) => setSelectedPackageId(event.target.value)}
              style={selectStyle}
              disabled={packages.length === 0}
            >
              {packages.map((pkg) => (
                <option key={pkg.package_id} value={pkg.package_id}>
                  {pkg.display_name} · {clean(pkg.package_type)} · {pkg.submitted_segy_count || 0} submitted SEG-Y
                </option>
              ))}
            </select>
          </label>
        </div>

        {selectedRepository && (
          <div style={{ fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>
            {selectedRepository.root_path}
          </div>
        )}

        {loading && (
          <div style={{ fontSize: 12, color: "#94a3b8" }}>Loading submitted handoff view...</div>
        )}

        {!loading && selectedRepositoryId && packages.length === 0 && (
          <div style={{ fontSize: 12, color: "#facc15" }}>
            No submitted QAQC handoff items are ready for this repository. Submit items from Source Intake / QAQC first.
          </div>
        )}

        {summary && summary.submitted_item_count > 0 && (
          <div style={{ fontSize: 12, color: "#86efac" }}>
            Showing submitted QAQC handoff only: {summary.submitted_segy_count} SEG-Y file{summary.submitted_segy_count === 1 ? "" : "s"} and {summary.submitted_document_count} document{summary.submitted_document_count === 1 ? "" : "s"}.
          </div>
        )}

        {selectedPackage && (
          <div style={{ fontSize: 12, color: "#cbd5e1" }}>
            {clean(selectedPackage.package_type)} · {packageLines.length} submitted line{packageLines.length === 1 ? "" : "s"} · {selectedPackage.submitted_segy_count || 0} submitted SEG-Y · {selectedPackage.submitted_document_count || 0} submitted docs
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 42%) 1fr", gap: 12, alignItems: "start" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <div style={labelStyle}>Submitted Lines</div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>
                {packageLines.length} line{packageLines.length === 1 ? "" : "s"}
              </div>
            </div>

            <div style={{ border: "1px solid #475569", borderRadius: 8, background: "#0b1220", padding: 8, display: "grid", gap: 6 }}>
              {packageLines.length === 0 && (
                <div style={{ fontSize: 12, color: "#94a3b8" }}>No submitted lines for this package.</div>
              )}

              {packageLines.map((line) => {
                const selected = String(line.line_id) === String(selectedLineId);

                return (
                  <button
                    key={line.line_id}
                    type="button"
                    onClick={() => setSelectedLineId(line.line_id)}
                    style={{
                      textAlign: "left",
                      borderRadius: 8,
                      padding: 9,
                      border: selected ? "2px solid #93c5fd" : "1px solid #334155",
                      background: selected ? "rgba(59,130,246,.28)" : "#111827",
                      color: "#e5e7eb",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: selected ? 700 : 600 }}>
                      {line.display_name}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: selected ? "#bfdbfe" : "#94a3b8" }}>
                      {clean(line.version_status)} · {line.submitted_segy_count || 0} submitted SEG-Y
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div style={labelStyle}>Submitted SEG-Y / Processing Versions</div>

            <div style={{ border: "1px solid #475569", borderRadius: 8, background: "#0b1220", padding: 10, minHeight: 150 }}>
              {!selectedLine && (
                <div style={{ fontSize: 12, color: "#94a3b8" }}>Select a submitted line to view available SEG-Y versions.</div>
              )}

              {selectedLine && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontWeight: 700, color: "#f8fafc" }}>{selectedLine.display_name}</div>
                  <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                    {clean(selectedLine.line_identity_status)} · {clean(selectedLine.version_status)}
                  </div>
                </div>
              )}

              {selectedLine && lineSegyFiles.length === 0 && (
                <div style={{ fontSize: 12, color: "#94a3b8" }}>No submitted SEG-Y source files found for this line.</div>
              )}

              <div style={{ display: "grid", gap: 8 }}>
                {lineSegyFiles.map((file) => {
                  const busy = busyFileId === file.segy_file_id;

                  return (
                    <div
                      key={file.segy_file_id}
                      style={{
                        border: "1px solid #334155",
                        borderRadius: 8,
                        background: "#111827",
                        padding: 9,
                        display: "grid",
                        gap: 6,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                        <div>
                          <div style={{ fontWeight: 700, color: "#f8fafc" }}>{file.display_name || file.filename}</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>
                            {file.relative_path}
                          </div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                            {formatBytes(file.size_bytes)} · {clean(file.conversion_status)}
                          </div>
                          {file.conversion_error && (
                            <div style={{ marginTop: 4, fontSize: 12, color: "#fecaca", overflowWrap: "anywhere" }}>
                              {file.conversion_error}
                            </div>
                          )}
                        </div>

                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                          <button
                            type="button"
                            onClick={() => handleRefreshStatus(file)}
                            disabled={busy}
                            style={{ ...utilityButtonStyle, opacity: busy ? 0.65 : 1 }}
                          >
                            Refresh Status
                          </button>

                          <button
                            type="button"
                            onClick={() => handleConvert(file)}
                            disabled={
                              busy ||
                              ["queued", "converting", "converted", "ready"].includes(String(file.conversion_status || ""))
                            }
                            style={{
                              ...primaryButtonStyle,
                              opacity:
                                busy ||
                                ["queued", "converting", "converted", "ready"].includes(String(file.conversion_status || ""))
                                  ? 0.65
                                  : 1,
                              cursor:
                                busy ||
                                ["queued", "converting", "converted", "ready"].includes(String(file.conversion_status || ""))
                                  ? "not-allowed"
                                  : "pointer",
                            }}
                          >
                            {busy
                              ? "Working..."
                              : ["converted", "ready"].includes(String(file.conversion_status || ""))
                                ? "Managed Zarr Exists"
                                : ["error", "failed"].includes(String(file.conversion_status || ""))
                                  ? "Retry Managed 2D Zarr"
                                  : ["queued", "converting"].includes(String(file.conversion_status || ""))
                                    ? "Creating Zarr..."
                                    : "Create Managed 2D Zarr"}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <section data-role="package-supporting-documents-2d">
          <div style={labelStyle}>Submitted Package Supporting Documents</div>

          <div style={{ border: "1px solid #475569", borderRadius: 8, background: "#0b1220", padding: 8, display: "grid", gap: 6 }}>
            {packageDocuments.length === 0 && (
              <div style={{ fontSize: 12, color: "#94a3b8" }}>No submitted package-level supporting documents found.</div>
            )}

            {packageDocuments.map((doc) => (
              <div key={doc.document_id} style={{ border: "1px solid #334155", borderRadius: 8, background: "#111827", padding: 9 }}>
                <div style={{ fontWeight: 700, color: "#f8fafc", overflowWrap: "anywhere" }}>
                  {doc.display_name || doc.filename}
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>
                  {doc.relative_path}
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                  {formatBytes(doc.size_bytes)} · {clean(doc.document_type)}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
