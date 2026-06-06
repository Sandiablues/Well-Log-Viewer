export type RepositoryRecord = {
  repository_id: string;
  name: string;
  root_path: string;
  repository_type?: string;
  status?: string;
  read_only?: boolean;
  last_scanned_at?: string | null;
  notes?: string | null;
  source_structure_type?: string | null;
  intended_use?: string | null;
};

export type PackageRecord = {
  package_id: string;
  repository_id: string;
  display_name: string;
  relative_path?: string;
  package_type?: string;
  segy_count?: number;
  document_count?: number;
  line_count?: number;
  scan_status?: string;
  last_scanned_at?: string;
};

export type LineRecord = {
  line_id: string;
  package_id: string;
  repository_id: string;
  line_key?: string;
  display_name: string;
  line_identity_status?: string;
  version_status?: string;
  segy_count?: number;
};

export type SegyFileRecord = {
  segy_file_id: string;
  repository_id: string;
  package_id: string;
  line_id: string;
  filename: string;
  relative_path: string;
  extension?: string;
  size_bytes?: number;
  modified_epoch?: number;
  inferred_line_key?: string;
  relationship_status?: string;
  conversion_status?: string;
  volume_id?: string | null;
};

function getApiBase(): string {
  const envBase = (import.meta as any)?.env?.VITE_API_BASE_URL;
  if (typeof envBase === "string" && envBase.trim()) {
    return envBase.replace(/\/$/, "");
  }
  return "";
}

function apiUrl(path: string): string {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBase()}${cleanPath}`;
}

function indexedDatasetIdFromManagedId(id: string): string | null {
  const prefix = "indexed-segy-";
  if (!id || !id.startsWith(prefix)) return null;
  const datasetId = id.slice(prefix.length).trim();
  return datasetId || null;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path));

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function fetchRepositories(): Promise<RepositoryRecord[]> {
  const payload = await fetchJson<{ repositories: RepositoryRecord[] }>("/api/source-intake/repositories");
  return payload.repositories || [];
}

export async function fetchPackages(repositoryId?: string): Promise<PackageRecord[]> {
  const query = new URLSearchParams();
  if (repositoryId) query.set("repository_id", repositoryId);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const payload = await fetchJson<{ packages: PackageRecord[] }>(`/api/source-intake/packages${suffix}`);
  return payload.packages || [];
}

export async function fetchLines(params?: {
  repositoryId?: string;
  packageId?: string;
}): Promise<LineRecord[]> {
  const query = new URLSearchParams();

  if (params?.repositoryId) query.set("repository_id", params.repositoryId);
  if (params?.packageId) query.set("package_id", params.packageId);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const payload = await fetchJson<{ lines: LineRecord[] }>(`/api/source-intake/lines${suffix}`);
  return payload.lines || [];
}

export async function fetchSegyFiles(params?: {
  repositoryId?: string;
  packageId?: string;
  lineId?: string;
}): Promise<SegyFileRecord[]> {
  const query = new URLSearchParams();

  if (params?.repositoryId) query.set("repository_id", params.repositoryId);
  if (params?.packageId) query.set("package_id", params.packageId);
  if (params?.lineId) query.set("line_id", params.lineId);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const payload = await fetchJson<{ segy_files: SegyFileRecord[] }>(`/api/source-intake/segy-files${suffix}`);
  return payload.segy_files || [];
}

export type ConvertSegyResponse = {
  status: string;
  message?: string;
  job_id?: string;
  volume_id?: string;
  zarr_url?: string;
  segy_file?: SegyFileRecord;
};

export type RefreshSegyStatusResponse = {
  status: string;
  job_status?: string;
  job_id?: string;
  volume_id?: string;
  zarr_url?: string;
  segy_file?: SegyFileRecord;
  job?: unknown;
};


export type QaqcFlag = {
  code?: string;
  severity?: string;
  message?: string;
};

export type SourceIntakeItem = {
  item_type?: string;
  filename?: string;
  relative_path?: string;
  size_bytes?: number;
  candidate_kind?: string;
  candidate_role?: string;
  document_type?: string;
  classification_source?: string;
  classification_confidence?: string;
  classification_reasons?: string[];
  artifact_bucket?: string;
  artifact_class?: string;
  artifact_subtype?: string;
  intake_role?: string;
  stageable_as_primary?: boolean;
  stageable_as_documentary_evidence?: boolean;
  stageable_as_associated_file?: boolean;
  user_confirmed_bucket?: string | null;
  matched_terms?: string[];
  processing_hints?: unknown[];
  qaqc_flags?: QaqcFlag[];
  segy_file_id?: string;
  document_id?: string;
  package_id?: string | null;
  line_id?: string | null;
  volume_id?: string | null;
  conversion_status?: string;
  view_url?: string;
  download_url?: string;
  reveal_url?: string;
  tree_node_id?: string;
  tree_path?: string[];
};

export type RepositoryTreeNode = {
  node_id: string;
  name: string;
  node_type: "repository" | "folder" | "segy_file" | "document" | "unknown" | string;
  relative_path?: string;
  children?: RepositoryTreeNode[];
  segy_file_id?: string;
  document_id?: string;
  package_id?: string;
  line_id?: string;
  candidate_kind?: string;
  candidate_role?: string;
  document_type?: string;
  classification_confidence?: string;
};

export type SourceIntakePackageRow = {
  package_id: string;
  repository_id?: string;
  display_name?: string;
  relative_path?: string;
  package_type?: string;
  scan_status?: string;
  last_scanned_at?: string;
  counts?: {
    segy?: number;
    documents?: number;
    review_required?: number;
    candidate_kind_counts?: Record<string, number>;
    document_type_counts?: Record<string, number>;
  artifact_bucket_counts?: Record<string, number>;
  };
  segy_files?: SourceIntakeItem[];
  documents?: SourceIntakeItem[];
  qaqc_flags?: QaqcFlag[];
};

export type SourceIntakeLoadSheet = {
  repository_id: string;
  repository?: {
    repository_id?: string;
    name?: string;
    root_path?: string;
    source_structure_type?: string;
    intended_use?: string;
    status?: string;
    last_scanned_at?: string | null;
  };
  status?: string;
  source?: string;
  load_errors?: string[];
  summary?: {
    package_count?: number;
    segy_items?: number;
    document_items?: number;
    unassigned_document_items?: number;
    review_required_items?: number;
    candidate_kind_counts?: Record<string, number>;
    document_type_counts?: Record<string, number>;
  artifact_bucket_counts?: Record<string, number>;
  };
  packages?: SourceIntakePackageRow[];
  unassigned_documents?: SourceIntakeItem[];
  items?: SourceIntakeItem[];
  repository_tree?: RepositoryTreeNode;
};


export type StageSelection = {
  package_ids?: string[];
  line_ids?: string[];
  segy_file_ids?: string[];
  document_ids?: string[];
};

export type StagedSourceItem = {
  staged_item_id: string;
  repository_id: string;
  staged_for?: "2d" | "3d" | string;
  source_item_type?: "package" | "line" | "segy_file" | "document" | string;
  source_item_id?: string;
  package_id?: string | null;
  line_id?: string | null;
  segy_file_id?: string | null;
  document_id?: string | null;
  relative_path?: string;
  filename?: string;
  display_name?: string;
  candidate_kind?: string;
  candidate_role?: string;
  document_type?: string;
  conversion_status?: string;
  staging_status?: string;
  staged_at?: string;
  updated_at?: string;
};

export type StageRepositoryResponse = {
  status: string;
  repository_id?: string;
  staged_for?: string;
  requested_count?: number;
  staged_count?: number;
  total_staged_for_repository?: number;
  staged_items?: StagedSourceItem[];
  errors?: unknown[];
  registry_path?: string;
};


export type SubmitStagedSourceItemsResponse = {
  status: string;
  repository_id?: string;
  staged_for?: string;
  submitted_count?: number;
  submitted_segy_count?: number;
  submitted_document_count?: number;
  submitted_package_count?: number;
  submitted_line_count?: number;
  external_registry_status?: string;
  submitted_at?: string;
  message?: string;
};


export async function fetchRepositoryLoadSheet(repositoryId: string): Promise<SourceIntakeLoadSheet> {
  const payload = await fetchJson<SourceIntakeLoadSheet>(
    `/api/source-intake/repositories/${encodeURIComponent(repositoryId)}/load-sheet`
  );
  return payload;
}

export async function convertSegyFile(segyFileId: string): Promise<ConvertSegyResponse> {
  const response = await fetch(apiUrl(`/api/segy-files/${segyFileId}/convert`), {
    method: "POST",
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Conversion request failed: ${response.status}`);
  }

  return response.json() as Promise<ConvertSegyResponse>;
}

export async function refreshSegyFileStatus(segyFileId: string): Promise<RefreshSegyStatusResponse> {
  const response = await fetch(apiUrl(`/api/segy-files/${segyFileId}/refresh-status`), {
    method: "POST",
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Status refresh failed: ${response.status}`);
  }

  return response.json() as Promise<RefreshSegyStatusResponse>;
}

export async function stageRepositorySelection(params: {
  repositoryId: string;
  mode: "2d" | "3d" | string;
  selection: StageSelection;
  replaceExisting?: boolean;
}): Promise<StageRepositoryResponse> {
  const response = await fetch(
    apiUrl(`/api/source-intake/repositories/${encodeURIComponent(params.repositoryId)}/stage`),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        mode: params.mode,
        selection: {
          package_ids: params.selection.package_ids || [],
          line_ids: params.selection.line_ids || [],
          segy_file_ids: params.selection.segy_file_ids || [],
          document_ids: params.selection.document_ids || [],
        },
        replace_existing: Boolean(params.replaceExisting),
      }),
    }
  );

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload?.detail || payload?.message || `Stage request failed: ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return payload as StageRepositoryResponse;
}

export async function fetchStagedSourceItems(params?: {
  repositoryId?: string;
  stagedFor?: "2d" | "3d" | string;
}): Promise<StagedSourceItem[]> {
  const query = new URLSearchParams();

  if (params?.repositoryId) query.set("repository_id", params.repositoryId);
  if (params?.stagedFor) query.set("staged_for", params.stagedFor);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const payload = await fetchJson<{ staged_items: StagedSourceItem[] }>(
    `/api/staged-source-items${suffix}`
  );

  return payload.staged_items || [];
}

export async function clearStagedSourceItems(params: {
  repositoryId: string;
  stagedFor?: "2d" | "3d" | string;
}): Promise<{ status: string; removed_count?: number }> {
  const query = new URLSearchParams();

  if (params.stagedFor) query.set("staged_for", params.stagedFor);

  const suffix = query.toString() ? `?${query.toString()}` : "";

  const response = await fetch(
    apiUrl(`/api/repositories/${encodeURIComponent(params.repositoryId)}/stage${suffix}`),
    {
      method: "DELETE",
    }
  );

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload?.detail || payload?.message || `Clear staged items failed: ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return payload as { status: string; removed_count?: number };
}

export async function submitStagedSourceItems(params: {
  repositoryId: string;
  mode: "2d" | "3d" | string;
}): Promise<SubmitStagedSourceItemsResponse> {
  const response = await fetch(
    apiUrl(`/api/source-intake/repositories/${encodeURIComponent(params.repositoryId)}/stage/submit`),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        mode: params.mode,
      }),
    }
  );

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload?.detail || payload?.message || `Submit staged items failed: ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return payload as SubmitStagedSourceItemsResponse;
}

export type SubmittedExternalRegistryView = {
  status: string;
  repository?: RepositoryRecord | null;
  mode?: string;
  packages: any[];
  lines: any[];
  segy_files: any[];
  documents: any[];
  submitted_items: any[];
  summary: {
    submitted_item_count: number;
    submitted_package_count: number;
    submitted_line_count: number;
    submitted_segy_count: number;
    submitted_document_count: number;
  };
};

export async function fetchSubmittedExternalRegistryView(params: {
  repositoryId: string;
  mode?: "2d" | "3d" | string;
}): Promise<SubmittedExternalRegistryView> {
  const mode = params.mode || "2d";
  return fetchJson<SubmittedExternalRegistryView>(
    apiUrl(`/api/source-intake/repositories/${encodeURIComponent(params.repositoryId)}/submitted-view?mode=${encodeURIComponent(mode)}`)
  );
}

export type SourceIntakeWorkbenchAction = {
  enabled?: boolean;
  url?: string | null;
  reason?: string | null;
  label?: string | null;
};

export type SourceIntakeWorkbenchRow = {
  candidate_id?: string | null;
  repository_id?: string | null;
  package_id?: string | null;
  line_id?: string | null;
  source_segy_file_id?: string | null;
  filename?: string | null;
  display_name?: string | null;
  relative_path?: string | null;
  source_path_exists?: boolean | null;
  selected?: boolean;
  status?: string | Record<string, unknown> | null;
  candidate_kind?: string | null;
  candidate_role?: string | null;
  classification_source?: string | null;
  classification_confidence?: string | number | null;
  classification_reasons?: string[];
  review_state?: string | null;
  qaqc_state?: string | null;
  qaqc_flags?: QaqcFlag[];
  conversion_state?: string | null;
  managed_state?: string | null;
  survey_name?: string | null;
  line_name?: string | null;
  volume_name?: string | null;
  processing_stage?: string | null;
  processing_version?: string | null;
  evidence_status?: string | Record<string, unknown> | null;
  document_count?: number | null;
  dimension?: string | null;
  lifecycle?: Record<string, unknown> | null;
  progress?: Record<string, unknown> | null;
  presentation?: Record<string, unknown> | null;
  action_contract?: Record<string, unknown> | null;
  promotion_required?: boolean | null;
  promotion_options?: unknown[] | null;
  staged_rebuild_result?: Record<string, unknown> | null;
  staged_rebuild?: Record<string, unknown> | null;
  actions?: Record<string, SourceIntakeWorkbenchAction>;
  job?: Record<string, unknown> | null;
  managed_output?: {
    state?: string | null;
    dataset_id?: string | null;
    representation_id?: string | null;
    viewer_ready?: boolean;
    viewer_mode?: string | null;
    representation_type?: string | null;
    storage_uri?: string | null;
    zarr_url?: string | null;
    physical_volume_id?: string | null;
    display_name?: string | null;
    is_preferred?: boolean;
    lifecycle_state?: string | null;
  };
};

export type SourceIntakeWorkbenchPayload = {
  repository_id?: string | null;
  row_count?: number;
  summary?: Record<string, unknown>;
  toolbar?: Record<string, unknown>;
  columns?: string[];
  rows: SourceIntakeWorkbenchRow[];
};


export type SourceIntakeBuildResponse = {
  status?: string;
  message?: string;
  candidate_id?: string;
  job_id?: string;
  job?: unknown;
  result?: unknown;
  [key: string]: unknown;
};

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function buildSourceIntake2DLine(candidateId: string): Promise<SourceIntakeBuildResponse> {
  return postJson<SourceIntakeBuildResponse>(`/api/source-intake/candidates/${encodeURIComponent(candidateId)}/build-2d-line`);
}

export async function hardDeleteMsiRepresentation(representationId: string): Promise<unknown> {
  const cleanId = String(representationId || "").trim();
  if (!cleanId) {
    throw new Error("MSI representation id is required for delete.");
  }

  const response = await fetch(apiUrl(`/api/msi/representations/${encodeURIComponent(cleanId)}`), {
    method: "DELETE",
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `MSI representation hard delete failed: ${response.status}`);
  }

  return response.json();
}

export async function deleteVolume(volumeId: string): Promise<unknown> {
  const indexedDatasetId = indexedDatasetIdFromManagedId(volumeId);

  if (indexedDatasetId) {
    const response = await fetch(apiUrl(`/api/datasets/${encodeURIComponent(indexedDatasetId)}`), {
      method: "DELETE",
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(text || `Dataset delete failed: ${response.status}`);
    }

    return response.json();
  }

  const response = await fetch(apiUrl(`/api/volumes/${encodeURIComponent(volumeId)}`), {
    method: "DELETE",
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Volume delete failed: ${response.status}`);
  }

  return response.json();
}
