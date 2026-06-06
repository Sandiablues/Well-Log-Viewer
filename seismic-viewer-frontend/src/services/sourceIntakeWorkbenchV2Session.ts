import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SourceIntakeWorkbenchPayload, SourceIntakeWorkbenchRow } from "./registryService";
import {
  clearSelectedSourceIntakeWorkbenchV2,
  fetchSourceIntakeWorkbenchV2,
  useRepositoryInSourceIntakeWorkbenchV2,
} from "./sourceIntakeWorkbenchV2Service";

export type WorkbenchMode = "2d" | "3d";

export function sourceIntakeCandidateId(row: SourceIntakeWorkbenchRow): string {
  return String(row.candidate_id || row.source_segy_file_id || (row as any).segy_file_id || (row as any).id || "").trim();
}

export function sourceIntakeRowKey(row: SourceIntakeWorkbenchRow, index = 0): string {
  return sourceIntakeCandidateId(row) || `${row.repository_id || "repo"}:${row.relative_path || row.filename || index}`;
}

function normalizeMode(mode?: string | null): WorkbenchMode {
  return String(mode || "3d").toLowerCase() === "2d" ? "2d" : "3d";
}

function rowArray(payload: SourceIntakeWorkbenchPayload | null): SourceIntakeWorkbenchRow[] {
  return payload && Array.isArray(payload.rows) ? payload.rows : [];
}

function monitoringState(payload: SourceIntakeWorkbenchPayload | null): Record<string, any> {
  const value = payload && typeof (payload as any).monitoring === "object" ? (payload as any).monitoring : null;
  return value && typeof value === "object" ? value as Record<string, any> : {};
}

function monitoringPollIntervalMs(payload: SourceIntakeWorkbenchPayload | null): number {
  const monitoring = monitoringState(payload);
  const raw = Number(monitoring.poll_interval_ms);
  if (!Number.isFinite(raw) || raw <= 0) return 1500;
  return Math.max(750, Math.min(10000, raw));
}

function monitoringHasActiveJobs(payload: SourceIntakeWorkbenchPayload | null): boolean {
  return monitoringState(payload).has_active_jobs === true;
}

function validatePayload(payload: SourceIntakeWorkbenchPayload, mode: WorkbenchMode, repositoryId: string): string | null {
  const data = payload as any;
  if (String(data.schema_version || "") !== "source_intake.workbench.v2") {
    return "Rejected workbench payload: schema_version is not source_intake.workbench.v2.";
  }
  if (String(data.mode || "").toLowerCase() !== mode) {
    return `Rejected workbench payload: mode ${data.mode || "missing"} does not match active mode ${mode}.`;
  }
  if (String(data.repository_id || "") !== repositoryId) {
    return "Rejected workbench payload: repository_id does not match active repository.";
  }
  const rows = rowArray(payload);
  const rowCount = Number(data.row_count ?? rows.length);
  if (rowCount !== rows.length) {
    return "Rejected workbench payload: row_count does not equal rows.length.";
  }
  const summary = data.summary && typeof data.summary === "object" ? data.summary : {};
  const total = Number(summary.total ?? rows.length);
  if (total !== rows.length) {
    return "Rejected workbench payload: summary.total does not equal rows.length.";
  }
  return null;
}

export function useSourceIntakeWorkbenchV2Session({
  repositoryId,
  mode,
  refreshSignal = 0,
}: {
  repositoryId?: string | null;
  mode?: WorkbenchMode | string | null;
  refreshSignal?: number;
}) {
  const activeMode = normalizeMode(mode);
  const activeRepositoryId = String(repositoryId || "").trim();
  const scopeKey = `${activeMode}:${activeRepositoryId || "none"}`;
  const requestSeq = useRef(0);

  const [payload, setPayload] = useState<SourceIntakeWorkbenchPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const acceptPayload = useCallback((nextPayload: SourceIntakeWorkbenchPayload, statusMessage?: string | null): boolean => {
    if (!activeRepositoryId) {
      setPayload(null);
      setError("Select a source repository before loading the workbench.");
      return false;
    }
    const problem = validatePayload(nextPayload, activeMode, activeRepositoryId);
    if (problem) {
      setPayload(null);
      setError(problem);
      return false;
    }
    setPayload(nextPayload);
    setError(null);
    if (statusMessage !== undefined) setStatus(statusMessage);
    return true;
  }, [activeMode, activeRepositoryId]);

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const repo = activeRepositoryId;
    const seq = ++requestSeq.current;
    if (!repo) {
      setPayload(null);
      setError(null);
      setStatus("Stage a source repository to populate Selection and Conversion.");
      return null;
    }
    if (!options?.silent) setLoading(true);
    try {
      const nextPayload = await fetchSourceIntakeWorkbenchV2(repo, activeMode);
      if (seq !== requestSeq.current) return null;
      const accepted = acceptPayload(nextPayload, "Workbench refreshed.");
      return accepted ? nextPayload : null;
    } catch (err) {
      if (seq !== requestSeq.current) return null;
      setPayload(null);
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      if (seq === requestSeq.current && !options?.silent) setLoading(false);
    }
  }, [acceptPayload, activeMode, activeRepositoryId]);

  const useRepository = useCallback(async () => {
    const repo = activeRepositoryId;
    const seq = ++requestSeq.current;
    if (!repo) {
      setPayload(null);
      setError("Select a source repository before staging.");
      return null;
    }
    setLoading(true);
    try {
      const nextPayload = await useRepositoryInSourceIntakeWorkbenchV2(repo, activeMode);
      if (seq !== requestSeq.current) return null;
      const accepted = acceptPayload(nextPayload, "Repository staged into Selection and Conversion.");
      return accepted ? nextPayload : null;
    } catch (err) {
      if (seq !== requestSeq.current) return null;
      setPayload(null);
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [acceptPayload, activeMode, activeRepositoryId]);

  const clearSelected = useCallback(async (candidateIds: string[]) => {
    const repo = activeRepositoryId;
    const seq = ++requestSeq.current;
    if (!repo) {
      setPayload(null);
      setError("Select a source repository before clearing rows.");
      return null;
    }
    setLoading(true);
    try {
      const nextPayload = await clearSelectedSourceIntakeWorkbenchV2(repo, activeMode, candidateIds);
      if (seq !== requestSeq.current) return null;
      const accepted = acceptPayload(nextPayload, `Cleared ${nextPayload.cleared_count || candidateIds.length} row${(nextPayload.cleared_count || candidateIds.length) === 1 ? "" : "s"}.`);
      return accepted ? nextPayload : null;
    } catch (err) {
      if (seq !== requestSeq.current) return null;
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [acceptPayload, activeMode, activeRepositoryId]);

  useEffect(() => {
    if (!activeRepositoryId) {
      requestSeq.current += 1;
      setPayload(null);
      setError(null);
      setStatus("Stage a source repository to populate Selection and Conversion.");
      return;
    }

    setError(null);
    setStatus("Loading Selection and Conversion rows...");
    void load({ silent: false });
  }, [scopeKey, activeRepositoryId, refreshSignal, load]);

  useEffect(() => {
    if (!activeRepositoryId || !monitoringHasActiveJobs(payload)) return undefined;

    const delayMs = monitoringPollIntervalMs(payload);
    const timer = window.setTimeout(() => {
      void load({ silent: true });
    }, delayMs);

    return () => window.clearTimeout(timer);
  }, [activeRepositoryId, payload, load]);

  return useMemo(() => ({
    scopeKey,
    payload,
    rows: rowArray(payload),
    loading,
    error,
    status,
    hasRepository: Boolean(activeRepositoryId),
    setStatus,
    load,
    useRepository,
    clearSelected,
    acceptPayload,
  }), [scopeKey, payload, loading, error, status, activeRepositoryId, load, useRepository, clearSelected, acceptPayload]);
}
