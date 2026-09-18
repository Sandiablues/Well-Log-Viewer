import { useEffect, useMemo, useState } from "react";
import type { SourceIntakeWorkbenchPayload, SourceIntakeWorkbenchRow } from "../services/registryService";
import SourceIntakeGeometryQaqcLegacyReport from "./SourceIntakeGeometryQaqcLegacyReport";
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
  overflow: "hidden",
} as const;

const buttonStyle = (enabled: boolean, accent = false) => ({
  padding: "7px 12px",
  cursor: enabled ? "pointer" : "not-allowed",
  opacity: enabled ? 1 : 0.62,
  whiteSpace: "nowrap",
} as const);

const cellStyle = {
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

  useEffect(() => {
    setSelectedKeys(new Set());
    setLocalError(null);
    setGeometryQaqcReport(null);
  }, [session.scopeKey]);

  useEffect(() => {
    const validKeys = new Set(session.rows.map((row, index) => sourceIntakeRowKey(row, index)));
    setSelectedKeys((current) => new Set([...current].filter((key) => validKeys.has(key))));
  }, [session.rows]);

  useEffect(() => {
    if (!stagedPayload) return;
    setLocalError(null);
    setSelectedKeys(new Set());
    session.acceptPayload(stagedPayload, "Repository staged into Candidates.");
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
    <section className="source-intake-workbench-panel mv-workbench ssi-candidates" style={panelStyle}>
      <div className="mv-workbench__header ssi-candidates__header">
        <div className="ssi-candidates__toolbar">
          <h3 className="mv-type-section-heading" style={{ margin: 0 }}>Candidates</h3>
          <div className="ssi-candidate-filterbar">
            <label className="mv-type-property-label">Status</label>
            <select className="mv-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
              <option value="all">All</option>
              <option value="ready">Viewer Ready</option>
              <option value="building">Building / Rebuilding</option>
              <option value="failed">Failed</option>
            </select>
            <label className="mv-type-property-label">Search</label>
            <input className="mv-input ssi-candidate-search" type="search" value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Line, file, survey, path" />
            <span className="mv-type-meta">{filteredRows.length} / {rows.length}</span>
            <button className="mv-button mv-button--compact" type="button" onClick={handleRefresh} disabled={session.loading || actionRunning} style={buttonStyle(!session.loading && !actionRunning, true)}>Refresh</button>
            <button className="mv-button mv-button--compact" type="button" onClick={handleClearSelected} disabled={!selectedCount || session.loading || actionRunning} style={buttonStyle(Boolean(selectedCount) && !session.loading && !actionRunning)}>Clear</button>
          </div>
        </div>

        {selectedCount > 0 && <div className="ssi-selection-actions">
          <span className="mv-type-meta">{selectedCount} selected / {filteredRows.length} shown</span>
          <button className="mv-button mv-button--compact" type="button" disabled={!buildRows.length || actionRunning} style={buttonStyle(Boolean(buildRows.length) && !actionRunning)} onClick={() => void runSelectedAction(buildAction, buildLabel)}>{buildLabel}</button>
          {activeMode === "3d" && <button className="mv-button mv-button--compact" type="button" disabled={!geometryRows.length || geometryRows.length !== 1 || actionRunning} style={buttonStyle(geometryRows.length === 1 && !actionRunning)} onClick={() => void runSelectedAction("geometry_qaqc", "Geometry QAQC")}>Run Geometry QAQC</button>}
          {activeMode === "3d" && <button className="mv-button mv-button--compact" type="button" disabled={!indexRows.length || actionRunning} style={buttonStyle(Boolean(indexRows.length) && !actionRunning)} onClick={() => void runSelectedAction("build_index", "Build Index")}>Build Index</button>}
          {activeMode === "3d" && <button className="mv-button mv-button--compact" type="button" disabled={!oneIndexedPreviewRow || actionRunning} style={buttonStyle(oneIndexedPreviewRow && !actionRunning)} onClick={() => void handleViewIndexedPreview()}>View Indexed Preview</button>}
          <button className="mv-button mv-button--compact" type="button" style={buttonStyle(true)} onClick={() => setSelectedKeys(new Set())}>Clear selection</button>
        </div>}

        {session.loading && <div className="mv-type-meta">Loading candidates…</div>}

        <div className="ssi-summary-grid" aria-label="Source Intake summary">
          <div className="ssi-summary-tile"><strong>{rowCount}</strong><span>Rows</span></div>
          <div className="ssi-summary-tile"><strong>{Number(summary.ready ?? 0)}</strong><span>Ready</span></div>
          <div className="ssi-summary-tile"><strong>{Number(summary.review_required ?? 0)}</strong><span>Review</span></div>
          <div className="ssi-summary-tile"><strong>{Number(summary.building ?? 0)}</strong><span>Building</span></div>
          <div className="ssi-summary-tile"><strong>{Number(summary.managed ?? 0)}</strong><span>Managed</span></div>
          <div className="ssi-summary-tile"><strong>{Number(summary.failed ?? 0)}</strong><span>Failed</span></div>
          <div className="ssi-summary-tile"><strong>{Number(summary.blocked ?? 0)}</strong><span>Blocked</span></div>
        </div>

        {error && <div style={{ border: "1px solid #ef4444", borderRadius: 8, padding: "10px 12px", color: "#fecaca" }}>{error}</div>}

        {geometryQaqcReport && (
          <SourceIntakeGeometryQaqcLegacyReport
            report={geometryQaqcReport}
            onClose={() => setGeometryQaqcReport(null)}
          />
        )}
      </div>

      <div className="ssi-candidate-table-wrap">
        <table className="mv-table ssi-candidate-table" style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...cellStyle, textAlign: "left" }}><input type="checkbox" checked={allSelected} onChange={toggleAll} /></th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Status</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Type</th>
              <th style={{ ...cellStyle, textAlign: "left", minWidth: 340 }}>File</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Survey</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Line / Volume</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>QAQC</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Conversion</th>
              <th style={{ ...cellStyle, textAlign: "left" }}>Managed Output</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.length === 0 && (
              <tr>
                <td colSpan={9} style={{ ...cellStyle, color: "#94a3b8" }}>
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
              const dimension = rowDimension(row);
              return (
                <tr key={key}>
                  <td style={cellStyle}><input type="checkbox" checked={checked} onChange={() => toggleRow(key)} /></td>
                  <td style={{ ...cellStyle, minWidth: 170 }}>
                    <div className={life.failed ? "ssi-status-label is-failed" : "ssi-status-label"}>{valueOrDash(pres.status_label || prog.label || life.label)}</div>
                    {percent !== null && percent < 100 && (
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
                  </td>
                  <td style={cellStyle}>{dimension === "2d" ? "2d\nLine" : dimension === "3d" ? "3d\nVolume" : "Review"}</td>
                  <td style={{ ...cellStyle, minWidth: 340 }}><div style={{ color: "#f8fafc", fontWeight: 700 }}>{valueOrDash(row.display_name || row.filename)}</div><div style={{ color: "#64748b", marginTop: 4 }}>{valueOrDash(row.relative_path || row.filename)}</div></td>
                  <td style={cellStyle}>{valueOrDash(row.survey_name)}</td>
                  <td style={cellStyle}>{valueOrDash(row.line_name || row.volume_name || row.line_id)}</td>
                  <td style={{ ...cellStyle, minWidth: 150 }}>{valueOrDash(pres.geometry_qaqc_label)}</td>
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
