import type { SourceIntakeWorkbenchPayload } from "./registryService";

function cleanRepositoryId(repositoryId?: string | null): string {
  const value = String(repositoryId || "").trim();
  if (!value) throw new Error("Workbench V2 repository_id is required.");
  return value;
}

function cleanMode(mode?: "2d" | "3d" | string | null): "2d" | "3d" {
  const value = String(mode || "3d").trim().toLowerCase();
  if (value !== "2d" && value !== "3d") throw new Error("Workbench V2 mode must be 2d or 3d.");
  return value;
}

async function readJsonOrThrow(response: Response, fallbackMessage: string): Promise<any> {
  if (response.ok) return response.json();
  const detail = await response.text().catch(() => "");
  throw new Error(detail || `${fallbackMessage} failed with HTTP ${response.status}`);
}

export async function fetchSourceIntakeWorkbenchV2(
  repositoryId?: string | null,
  mode?: "2d" | "3d" | string | null,
): Promise<SourceIntakeWorkbenchPayload> {
  const cleanRepo = cleanRepositoryId(repositoryId);
  const cleanModeValue = cleanMode(mode);
  const params = new URLSearchParams({ repository_id: cleanRepo, mode: cleanModeValue });
  const response = await fetch(`/api/source-intake/workbench-v2?${params.toString()}`);
  return readJsonOrThrow(response, "Fetch Source Intake Workbench V2") as Promise<SourceIntakeWorkbenchPayload>;
}

export async function useRepositoryInSourceIntakeWorkbenchV2(
  repositoryId?: string | null,
  mode?: "2d" | "3d" | string | null,
): Promise<SourceIntakeWorkbenchPayload> {
  const response = await fetch("/api/source-intake/workbench-v2/use-repository", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      repository_id: cleanRepositoryId(repositoryId),
      mode: cleanMode(mode),
    }),
  });
  return readJsonOrThrow(response, "Use repository in Source Intake Workbench V2") as Promise<SourceIntakeWorkbenchPayload>;
}


export type SourceIntakeSessionResult = {
  schema_version?: string;
  mode?: "2d" | "3d" | string | null;
  active_repository_id?: string | null;
  repository?: {
    repository_id?: string | null;
    mode?: string | null;
    scan_summary?: Record<string, unknown> | null;
    [key: string]: unknown;
  } | null;
  workbench?: SourceIntakeWorkbenchPayload | null;
  state?: string | null;
  [key: string]: unknown;
};

export async function fetchSourceIntakeSession(
  mode?: "2d" | "3d" | string | null,
): Promise<SourceIntakeSessionResult> {
  const cleanModeValue = cleanMode(mode);
  const params = new URLSearchParams({ mode: cleanModeValue });
  const response = await fetch(`/api/source-intake/session?${params.toString()}`);
  return readJsonOrThrow(response, "Fetch Source Intake session") as Promise<SourceIntakeSessionResult>;
}

export type SourceIntakeStageWorkbenchResult = {
  schema_version?: string;
  mode?: "2d" | "3d" | string | null;
  repository_id?: string | null;
  repository?: {
    repository_id?: string | null;
    mode?: string | null;
    scan_summary?: Record<string, unknown> | null;
    [key: string]: unknown;
  } | null;
  workbench?: SourceIntakeWorkbenchPayload | null;
  [key: string]: unknown;
};

export async function stageSourceIntakeRepositoryWorkbench(
  repositoryId?: string | null,
  mode?: "2d" | "3d" | string | null,
): Promise<SourceIntakeStageWorkbenchResult> {
  const cleanRepo = cleanRepositoryId(repositoryId);
  const cleanModeValue = cleanMode(mode);
  const response = await fetch(`/api/source-intake/repositories/${encodeURIComponent(cleanRepo)}/stage-workbench`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: cleanModeValue }),
  });
  return readJsonOrThrow(response, "Stage Source Intake repository") as Promise<SourceIntakeStageWorkbenchResult>;
}

export async function clearSelectedSourceIntakeWorkbenchV2(
  repositoryId: string | null | undefined,
  mode: "2d" | "3d" | string | null | undefined,
  candidateIds: string[],
): Promise<SourceIntakeWorkbenchPayload & { cleared_count?: number; cleared_candidate_ids?: string[] }> {
  const response = await fetch("/api/source-intake/workbench-v2/clear-selected", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      repository_id: cleanRepositoryId(repositoryId),
      mode: cleanMode(mode),
      candidate_ids: candidateIds,
    }),
  });
  return readJsonOrThrow(response, "Clear selected Source Intake Workbench V2 rows") as Promise<SourceIntakeWorkbenchPayload & { cleared_count?: number; cleared_candidate_ids?: string[] }>;
}
