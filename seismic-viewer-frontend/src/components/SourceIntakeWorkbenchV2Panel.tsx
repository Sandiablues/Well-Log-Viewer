import { useEffect, useMemo, useState } from "react";
import type { SourceIntakeWorkbenchPayload, SourceIntakeWorkbenchRow } from "../services/registryService";
import SourceIntakeGeometryQaqcLegacyReport from "./SourceIntakeGeometryQaqcLegacyReport";
import SourceIntakeDocumentAssignmentDialog from "./SourceIntakeDocumentAssignmentDialog";
import {
  sourceIntakeCandidateId,
  sourceIntakeRowKey,
  useSourceIntakeWorkbenchV2Session,
  type WorkbenchMode,
} from "../services/sourceIntakeWorkbenchV2Session";

type SourceIntakeWorkbenchPanelProps = {
  repositoryId?: string;
  mode?: WorkbenchMode;
  refreshSignal?: number;
  stagedPayload?: SourceIntakeWorkbenchPayload | null;
  onViewIndexedPreview?: (viewerSource: any) => void;
};

type StatusFilter = "all" | "ready" | "building" | "failed";

const panelStyle = {
  border: "1px solid #334155",
  borderRadius: 10,
  background: "#0b1220",
  overflow: "hidden",
} as const;

const buttonStyle = (enabled: boolean, accent = false) => ({
  border: `1px solid ${enabled ? (accent ? "#38bdf8" : "#475569") : "#334155"}`,
  color: enabled ? (accent ? "#7dd3fc" : "#cbd5e1") : "#64748b",
  background: "transparent",
  borderRadius: 8,
  padding: "7px 12px",
  cursor: enabled ? "pointer" : "not-allowed",
  opacity: enabled ? 1 : 0.62,
  fontSize: 13,
  fontWeight: 700,
  whiteSpace: "nowrap",
} as const);

const cellStyle = {
  padding: "14px 12px",
  borderTop: "1px solid #1f2937",
  verticalAlign: "middle",
} as const;

function valueOrDash(value: unknown): string {
  const text = String(value ?? "").trim();
  return text || "—";
}

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" ? value as Record<string, any> : {};
}

function lifecycle(row: SourceIntakeWorkbenchRow): Record<string, any> {
  return asRecord((row as any).lifecycle);
}

function progress(row: SourceIntakeWorkbenchRow): Record<string, any> {
  return asRecord((row as any).progress);
}

function presentation(row: SourceIntakeWorkbenchRow): Record<string, any> {
  return asRecord((row as any).presentation);
}

function rowAction(row: SourceIntakeWorkbenchRow, name: string): Record<string, any> {
  const actions = asRecord((row as any).actions);
  return asRecord(actions[name]);
}

function rowActionEnabled(row: SourceIntakeWorkbenchRow, name: string): boolean {
  const action = rowAction(row, name);
  return action.enabled === true && typeof action.url === "string" && action.url.trim().length > 0;
}

function rowDimension(row: SourceIntakeWorkbenchRow): "2d" | "3d" | "unknown" {
  const dimension = String((row as any).dimension || "").trim().toLowerCase();
  if (dimension === "2d" || dimension === "3d") return dimension;
  const kind = String((row as any).candidate_kind || "").toLowerCase();
  const role = String((row as any).candidate_role || "").toLowerCase();
  if (kind.includes("2d") || role.includes("line")) return "2d";
  if (kind.includes("3d") || role.includes("volume")) return "3d";
  return "unknown";
}

function lifecycleState(row: SourceIntakeWorkbenchRow): string {
  return String(lifecycle(row).state || "").trim().toLowerCase();
}

function progressPercent(row: SourceIntakeWorkbenchRow): number | null {
  const raw = progress(row).percent;
  const value = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(value)) return null;
  return Math.max(0, Math.min(100, value));
}

function documentCount(row: SourceIntakeWorkbenchRow): number {
  const raw = (row as any).supporting_document_count ?? row.document_count ?? 0;
  const value = Number(raw || 0);
  return Number.isFinite(value) ? value : 0;
}

// MANUAL_UPLOAD_STAGING_4A_DOCUMENT_ASSIGNMENT
// Assigned supporting-document count and available assignment options are
// different backend-owned facts. Do not silently count package documents as
// assigned to a SEG-Y candidate. Surface them as assignable documents instead.
function discoveredDocumentCount(row: SourceIntakeWorkbenchRow): number {
  const summary = asRecord((row as any).document_assignment_summary);
  const raw =
    (row as any).discovered_document_count
    ?? (row as any).available_document_count
    ?? summary.discovered_document_count
    ?? summary.repository_document_count
    ?? documentCount(row);
  const value = Number(raw || 0);
  return Number.isFinite(value) ? value : 0;
}

function unassignedDocumentCount(row: SourceIntakeWorkbenchRow): number {
  const assigned = documentCount(row);
  const discovered = discoveredDocumentCount(row);
  return Math.max(0, discovered - assigned);
}

function documentAssignmentHint(row: SourceIntakeWorkbenchRow): string {
  const assigned = documentCount(row);
  const discovered = discoveredDocumentCount(row);
  const unassigned = Math.max(0, discovered - assigned);
  if (discovered === 0) return "No documents available";
  if (unassigned > 0) return `${unassigned} available to assign`;
  if (assigned === 1) return "1 assigned document";
  return `${assigned} assigned documents`;
}

function rowSearchText(row: SourceIntakeWorkbenchRow): string {
  return [
    row.filename,
    row.display_name,
    row.relative_path,
    row.survey_name,
    row.line_name,
    row.volume_name,
    row.line_id,
    row.candidate_id,
    row.source_segy_file_id,
    rowDimension(row),
    lifecycle(row).label,
    lifecycle(row).state,
  ].map((value) => String(value || "").toLowerCase()).join(" ");
}

async function postJson(url: string, body?: unknown): Promise<any> {
  const response = await fetch(url, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text().catch(() => "");
  if (!response.ok) {
    throw new Error(text || `Request failed with HTTP ${response.status}`);
  }
  return text ? JSON.parse(text) : null;
}

async function getJson(url: string): Promise<any> {
  const response = await fetch(url);
  const text = await response.text().catch(() => "");
  if (!response.ok) {
    throw new Error(text || `Request failed with HTTP ${response.status}`);
  }
  return text ? JSON.parse(text) : null;
}

export default function SourceIntakeWorkbenchV2Panel({ repositoryId, mode = "3d", refreshSignal = 0, stagedPayload = null, onViewIndexedPreview }: SourceIntakeWorkbenchPanelProps) {
  const activeMode: WorkbenchMode = mode === "2d" ? "2d" : "3d";
  const session = useSourceIntakeWorkbenchV2Session({ repositoryId, mode: activeMode, refreshSignal });
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [searchText, setSearchText] = useState("");
  const [actionRunning, setActionRunning] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [geometryQaqcReport, setGeometryQaqcReport] = useState<any | null>(null);
  const [documentAssignmentReview, setDocumentAssignmentReview] = useState<any | null>(null);
  const [documentAssignmentRow, setDocumentAssignmentRow] = useState<SourceIntakeWorkbenchRow | null>(null);
  const [documentAssignmentLoading, setDocumentAssignmentLoading] = useState(false);

  useEffect(() => {
    setSelectedKeys(new Set());
    setLocalError(null);
    setGeometryQaqcReport(null);
    setDocumentAssignmentReview(null);
    setDocumentAssignmentRow(null);
  }, [session.scopeKey]);

  useEffect(() => {
    const validKeys = new Set(session.rows.map((row, index) => sourceIntakeRowKey(row, index)));
    setSelectedKeys((current) => new Set([...current].filter((key) => validKeys.has(key))));
  }, [session.rows]);

  useEffect(() => {
    if (!stagedPayload) return;
    setLocalError(null);
    setSelectedKeys(new Set());
    session.acceptPayload(stagedPayload, "Repository staged into Selection and Conversion.");
  }, [stagedPayload, session.acceptPayload]);

  const rows = session.rows;
  const filteredRows = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    return rows.filter((row) => {
      const state = lifecycleState(row);
      if (statusFilter === "ready" && state !== "viewer_ready") return false;
      if (statusFilter === "building" && !["rebuilding", "building"].includes(state)) return false;
      if (statusFilter === "failed" && state !== "failed") return false;
      if (q && !rowSearchText(row).includes(q)) return false;
      return true;
    });
  }, [rows, searchText, statusFilter]);

  const selectedRows = useMemo(() => {
    const visibleByKey = new Map(filteredRows.map((row, index) => [sourceIntakeRowKey(row, index), row]));
    return [...selectedKeys].map((key) => visibleByKey.get(key)).filter(Boolean) as SourceIntakeWorkbenchRow[];
  }, [filteredRows, selectedKeys]);

  const selectedCount = selectedRows.length;
  const allSelected = filteredRows.length > 0 && filteredRows.every((row, index) => selectedKeys.has(sourceIntakeRowKey(row, index)));
  const selectedCandidateIds = () => selectedRows.map(sourceIntakeCandidateId).filter(Boolean);
  const rowsForAction = (name: string) => selectedRows.filter((row) => rowActionEnabled(row, name));
  const oneIndexedPreviewRow = selectedRows.length === 1 && Boolean(sourceIntakeCandidateId(selectedRows[0]));

  const summary = asRecord(session.payload?.summary);
  const rowCount = Number(session.payload?.row_count ?? rows.length);
  const error = localError || session.error;

  const runSelectedAction = async (actionName: string, label: string, bodyFactory?: (row: SourceIntakeWorkbenchRow) => unknown) => {
    const actionRows = rowsForAction(actionName);
    if (!actionRows.length || actionRunning) return;
    setActionRunning(true);
    setLocalError(null);
    session.setStatus(`Submitting ${label} for ${actionRows.length} row${actionRows.length === 1 ? "" : "s"}…`);
    let succeeded = 0;
    try {
      for (const row of actionRows) {
        const action = rowAction(row, actionName);
        const url = String(action.url || "").trim();
        if (!url) throw new Error(`Missing backend action URL for ${label}.`);
        const result = await postJson(url, bodyFactory ? bodyFactory(row) : undefined);
        if (actionName === "geometry_qaqc") {
          setGeometryQaqcReport({
            payload: result,
            row: {
              candidate_id: sourceIntakeCandidateId(row),
              filename: row.filename || row.display_name,
              display_name: row.display_name,
              relative_path: row.relative_path,
              volume_name: row.volume_name,
              survey_name: row.survey_name,
            },
          });
        }
        succeeded += 1;
      }
      session.setStatus(`${label} submitted for ${succeeded} row${succeeded === 1 ? "" : "s"}.`);
      setSelectedKeys(new Set());
      await session.load({ silent: true });
      window.dispatchEvent(new CustomEvent("multiviewer:managed-data-updated", { detail: { source: "source-intake-workbench-v2", action: actionName, succeeded } }));
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
      session.setStatus(`${label} failed after ${succeeded} successful submission${succeeded === 1 ? "" : "s"}.`);
    } finally {
      setActionRunning(false);
    }
  };

  const handleRefresh = () => {
    setLocalError(null);
    void session.load();
  };

  const handleClearSelected = async () => {
    const ids = selectedCandidateIds();
    await session.clearSelected(ids);
    setSelectedKeys(new Set());
  };

  const handleViewIndexedPreview = async () => {
    if (!oneIndexedPreviewRow || actionRunning) return;
    const candidateId = sourceIntakeCandidateId(selectedRows[0]);
    setActionRunning(true);
    setLocalError(null);
    session.setStatus("Opening indexed preview…");
    try {
      const result = await getJson(`/api/source-intake/candidates/${encodeURIComponent(candidateId)}/indexed-preview-viewer-source`);
      const viewerSource = result?.viewer_source;
      if (!viewerSource?.dataset_id) throw new Error("Indexed preview response did not include viewer_source.dataset_id.");
      onViewIndexedPreview?.(viewerSource);
      session.setStatus("Indexed preview opened in the 3D viewer.");
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
      session.setStatus("Indexed preview could not be opened.");
    } finally {
      setActionRunning(false);
    }
  };


  const openDocumentAssignmentForRow = async (row: SourceIntakeWorkbenchRow) => {
    if (actionRunning || documentAssignmentLoading) return;
    const candidateId = sourceIntakeCandidateId(row);
    if (!candidateId) {
      setLocalError("Selected row does not have a source-intake candidate id.");
      return;
    }
    setDocumentAssignmentLoading(true);
    setLocalError(null);
    session.setStatus("Loading document assignment review…");
    try {
      const review = await getJson(`/api/source-intake/candidates/${encodeURIComponent(candidateId)}/document-assignment-review`);
      setDocumentAssignmentRow(row);
      setDocumentAssignmentReview(review);
      session.setStatus("Document assignment review loaded.");
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
      session.setStatus("Document assignment review could not be loaded.");
    } finally {
      setDocumentAssignmentLoading(false);
    }
  };

  const openDocumentAssignment = async () => {
    if (selectedRows.length !== 1 || actionRunning || documentAssignmentLoading) return;
    await openDocumentAssignmentForRow(selectedRows[0]);
  };

  const submitDocumentAssignment = async (action: string, documentIds: string[]) => {
    if (!documentAssignmentRow || actionRunning) return;
    const candidateId = sourceIntakeCandidateId(documentAssignmentRow);
    if (!candidateId) throw new Error("Document assignment row is missing candidate id.");
    setActionRunning(true);
    setLocalError(null);
    session.setStatus("Submitting document assignment…");
    try {
      const result = await postJson(`/api/source-intake/candidates/${encodeURIComponent(candidateId)}/document-assignments`, {
        mode: activeMode,
        action,
        document_ids: documentIds,
      });
      const nextReview = result?.review;
      if (nextReview) {
        setDocumentAssignmentReview(nextReview);
      }
      session.setStatus("Document assignment saved.");
      await session.load({ silent: true });
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
      session.setStatus("Document assignment failed.");
      throw err;
    } finally {
      setActionRunning(false);
    }
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelectedKeys(new Set());
      return;
    }
    setSelectedKeys(new Set(filteredRows.map((row, index) => sourceIntakeRowKey(row, index))));
  };

  const toggleRow = (key: string) => {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const buildAction = activeMode === "2d" ? "build_2d_line" : "build_3d_volume";
  const buildLabel = activeMode === "2d" ? "Build 2D Line" : "Build 3D Volume";
  const buildRows = rowsForAction(buildAction);
  const geometryRows = rowsForAction("geometry_qaqc");
  const indexRows = rowsForAction("build_index");

  return (
    <section className="source-intake-workbench-panel" style={panelStyle}>
      <div style={{ padding: 16, borderBottom: "1px solid #334155", display: "grid", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h3 style={{ margin: 0, color: "#f8fafc" }}>Selection and Conversion</h3>
            <p style={{ margin: "6px 0 0", color: "#94a3b8" }}>
              Backend-owned Workbench V2 session. Rows render only when mode and repository context match.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" onClick={handleRefresh} disabled={session.loading || actionRunning} style={buttonStyle(!session.loading && !actionRunning, true)}>Refresh</button>
            <button type="button" onClick={handleClearSelected} disabled={!selectedCount || session.loading || actionRunning} style={buttonStyle(Boolean(selectedCount) && !session.loading && !actionRunning)}>Clear</button>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", color: "#cbd5e1" }}>
          <span>{selectedCount} selected / {filteredRows.length} shown</span>
          <button type="button" disabled={true} style={buttonStyle(false)}>Approve selected</button>
          <button type="button" disabled={true} style={buttonStyle(false)}>Exclude selected</button>
          <button type="button" disabled={!buildRows.length || actionRunning} style={buttonStyle(Boolean(buildRows.length) && !actionRunning)} onClick={() => void runSelectedAction(buildAction, buildLabel)}>{buildLabel}</button>
          {activeMode === "3d" && <button type="button" disabled={!geometryRows.length || geometryRows.length !== 1 || actionRunning} style={buttonStyle(geometryRows.length === 1 && !actionRunning)} onClick={() => void runSelectedAction("geometry_qaqc", "Geometry QAQC")}>Run Geometry QAQC</button>}
          <button type="button" disabled={selectedRows.length !== 1 || actionRunning || documentAssignmentLoading} style={buttonStyle(selectedRows.length === 1 && !actionRunning && !documentAssignmentLoading)} onClick={() => void openDocumentAssignment()}>Assign Documents</button>
          {activeMode === "3d" && <button type="button" disabled={!indexRows.length || actionRunning} style={buttonStyle(Boolean(indexRows.length) && !actionRunning)} onClick={() => void runSelectedAction("build_index", "Build Index")}>Build Index</button>}
          {activeMode === "3d" && <button type="button" disabled={!oneIndexedPreviewRow || actionRunning} style={buttonStyle(oneIndexedPreviewRow && !actionRunning)} onClick={() => void handleViewIndexedPreview()}>View Indexed Preview</button>}
          <button type="button" disabled={!selectedCount} style={buttonStyle(Boolean(selectedCount))} onClick={() => setSelectedKeys(new Set())}>Clear selection</button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <label style={{ color: "#cbd5e1" }}>Status</label>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)} style={{ background: "#0f172a", color: "#e2e8f0", border: "1px solid #475569", borderRadius: 8, padding: "8px 10px" }}>
            <option value="all">All</option>
            <option value="ready">Viewer Ready</option>
            <option value="building">Building / Rebuilding</option>
            <option value="failed">Failed</option>
          </select>
          <label style={{ color: "#cbd5e1" }}>Search</label>
          <input type="search" value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Type 2+ chars: line, file, survey, path, document" style={{ minWidth: 320, background: "#0f172a", color: "#e2e8f0", border: "1px solid #475569", borderRadius: 8, padding: "9px 10px" }} />
          <span style={{ color: "#94a3b8" }}>Showing {filteredRows.length} of {rows.length} rows</span>
        </div>

        <div style={{ border: "1px solid #334155", borderRadius: 8, padding: "10px 12px", color: "#cbd5e1" }}>
          {session.loading ? "Loading backend-owned workbench payload…" : session.status || "Select rows to enable valid toolbar actions."}
        </div>

        <div style={{ color: "#94a3b8", display: "flex", gap: 12, flexWrap: "wrap" }}>
          <span>Rows: {rowCount}</span>
          <span>Total: {Number(summary.total ?? rows.length)}</span>
          <span>Ready: {Number(summary.ready ?? 0)}</span>
          <span>Review Required: {Number(summary.review_required ?? 0)}</span>
          <span>Building: {Number(summary.building ?? 0)}</span>
          <span>Complete: {Number(summary.complete ?? 0)}</span>
          <span>Managed: {Number(summary.managed ?? 0)}</span>
          <span>Failed: {Number(summary.failed ?? 0)}</span>
          <span>Blocked: {Number(summary.blocked ?? 0)}</span>
          <span>Two D: {Number(summary.two_d ?? 0)}</span>
          <span>Three D: {Number(summary.three_d ?? 0)}</span>
        </div>

        {error && <div style={{ border: "1px solid #ef4444", borderRadius: 8, padding: "10px 12px", color: "#fecaca" }}>{error}</div>}

        {geometryQaqcReport && (
          <SourceIntakeGeometryQaqcLegacyReport
            report={geometryQaqcReport}
            onClose={() => setGeometryQaqcReport(null)}
          />
        )}

        {documentAssignmentReview && documentAssignmentRow && (
          <SourceIntakeDocumentAssignmentDialog
            review={documentAssignmentReview}
            row={documentAssignmentRow}
            mode={activeMode}
            submitting={actionRunning}
            onSubmit={submitDocumentAssignment}
            onClose={() => {
              setDocumentAssignmentReview(null);
              setDocumentAssignmentRow(null);
            }}
          />
        )}
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", color: "#cbd5e1", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#111827", color: "#cbd5e1" }}>
              <th style={{ ...cellStyle, textAlign: "left" }}><input type="checkbox" checked={allSelected} onChange={toggleAll} /></th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Status</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Type</th>
              <th style={{ ...cellStyle, textAlign: "left", minWidth: 340 }}>File</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Survey</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Line / Volume</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>QAQC</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Supporting Docs</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Conversion</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Managed Output</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.length === 0 && (
              <tr>
                <td colSpan={10} style={{ ...cellStyle, color: "#94a3b8" }}>
                  {session.loading ? "Loading rows…" : "No rows for the active mode/repository context."}
                </td>
              </tr>
            )}
            {filteredRows.map((row, index) => {
              const key = sourceIntakeRowKey(row, index);
              const checked = selectedKeys.has(key);
              const life = lifecycle(row);
              const prog = progress(row);
              const pres = presentation(row);
              const percent = progressPercent(row);
              const docs = documentCount(row);
              const availableDocs = discoveredDocumentCount(row);
              const unassignedDocs = unassignedDocumentCount(row);
              const dimension = rowDimension(row);
              return (
                <tr key={key}>
                  <td style={cellStyle}><input type="checkbox" checked={checked} onChange={() => toggleRow(key)} /></td>
                  <td style={{ ...cellStyle, minWidth: 220 }}>
                    <div style={{ color: "#e2e8f0", marginBottom: 6 }}>{valueOrDash(pres.status_label || life.label)}</div>
                    <div style={{ color: life.failed ? "#fecaca" : "#bbf7d0", fontWeight: 700 }}>{valueOrDash(prog.label || life.label)}</div>
                    {percent !== null && (
                      <div className="si-progress-row" aria-label={`Progress ${Math.round(percent)} percent`}>
                        <div className="si-progress-track">
                          <div
                            className={life.failed ? "si-progress-fill si-progress-fill-failed" : "si-progress-fill"}
                            style={{ width: `${percent}%` }}
                          />
                        </div>
                        <span className="si-progress-percent">{Math.round(percent)}%</span>
                      </div>
                    )}
                    <div style={{ marginTop: 6, color: "#94a3b8", fontSize: 12 }}>{valueOrDash(prog.detail || life.reason)}</div>
                  </td>
                  <td style={cellStyle}>{dimension === "2d" ? "2d\nLine" : dimension === "3d" ? "3d\nVolume" : "Review"}</td>
                  <td style={{ ...cellStyle, minWidth: 340 }}><div style={{ color: "#f8fafc", fontWeight: 700 }}>{valueOrDash(row.display_name || row.filename)}</div><div style={{ color: "#64748b", marginTop: 4 }}>{valueOrDash(row.relative_path || row.filename)}</div></td>
                  <td style={cellStyle}>{valueOrDash(row.survey_name)}</td>
                  <td style={cellStyle}>{valueOrDash(row.line_name || row.volume_name || row.line_id)}</td>
                  <td style={{ ...cellStyle, minWidth: 180 }}><div>{valueOrDash(pres.geometry_qaqc_label)}</div><div style={{ color: "#94a3b8", marginTop: 4 }}>{valueOrDash(asRecord((row as any).geometry_qaqc).message || asRecord((row as any).geometry_qaqc).summary)}</div></td>
                  <td style={cellStyle}>
                    <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", minWidth: 44, textAlign: "center", border: "1px solid #64748b", borderRadius: 8, padding: "5px 8px", color: "#f8fafc", fontWeight: 700 }}>{docs}</div>
                    <div style={{ color: "#94a3b8", marginTop: 4 }}>{docs === 1 ? "Assigned document" : "Assigned documents"}</div>
                    {availableDocs > 0 && (
                      <div style={{ color: unassignedDocs > 0 ? "#fbbf24" : "#94a3b8", marginTop: 4, fontSize: 12 }}>{documentAssignmentHint(row)}</div>
                    )}
                    {availableDocs > 0 && (
                      <button
                        type="button"
                        disabled={actionRunning || documentAssignmentLoading}
                        style={{ ...buttonStyle(!actionRunning && !documentAssignmentLoading, unassignedDocs > 0), marginTop: 6, padding: "5px 8px", fontSize: 12 }}
                        onClick={() => void openDocumentAssignmentForRow(row)}
                      >
                        Assign
                      </button>
                    )}
                  </td>
                  <td style={cellStyle}>{valueOrDash((row as any).conversion_state || "—")}</td>
                  <td style={cellStyle}>{valueOrDash(pres.managed_output_label || (row as any).managed_state)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
