export type RepositoryRecord = {
  repository_id: string;
  name: string;
  root_path: string;
  repository_type?: string;
  status?: string;
  read_only?: boolean;
  created_at?: string;
  updated_at?: string;
  last_scanned_at?: string | null;
  notes?: string | null;
};

export type DocumentRecord = {
  document_id: string;
  filename: string;
  document_type?: string;
  storage_mode?: string;
  repository_id?: string;
  relative_path?: string;
  linked_scope?: string;
  package_id?: string | null;
  line_id?: string | null;
  volume_id?: string | null;
  size_bytes?: number;
  modified_at?: string;
  created_at?: string;
  updated_at?: string;
  status?: string;
  mime_type?: string;
  view_url?: string;
  download_url?: string;
  reveal_url?: string;
  notes?: string | null;
};

function getApiBase(): string {
  const envBase = (import.meta as any)?.env?.VITE_API_BASE_URL;
  if (typeof envBase === "string" && envBase.trim()) {
    return envBase.replace(/\/$/, "");
  }
  return "";
}

export function apiUrl(path?: string): string {
  if (!path) return "#";
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBase()}${cleanPath}`;
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
  const payload = await fetchJson<{ repositories: RepositoryRecord[] }>("/api/repositories");
  return payload.repositories || [];
}

export async function fetchDocuments(params?: {
  repository_id?: string;
  linked_scope?: string;
}): Promise<DocumentRecord[]> {
  const query = new URLSearchParams();

  if (params?.repository_id) {
    query.set("repository_id", params.repository_id);
  }

  if (params?.linked_scope) {
    query.set("linked_scope", params.linked_scope);
  }

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const payload = await fetchJson<{ documents: DocumentRecord[] }>(`/api/documents${suffix}`);

  return payload.documents || [];
}

function isMsiRepresentationId(value: string): boolean {
  return String(value || "").trim().startsWith("msi_repr:");
}

export async function fetchVolumeDocuments(volumeId: string): Promise<DocumentRecord[]> {
  const cleanVolumeId = String(volumeId || "").trim();

  const path = isMsiRepresentationId(cleanVolumeId)
    ? `/api/msi/representations/${encodeURIComponent(cleanVolumeId)}/documents`
    : `/api/volumes/${cleanVolumeId}/documents`;

  const payload = await fetchJson<{ documents: DocumentRecord[] }>(path);
  return payload.documents || [];
}

export async function revealDocument(documentId: string): Promise<void> {
  const response = await fetch(apiUrl(`/api/documents/${documentId}/reveal`), {
    method: "POST",
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Reveal failed: ${response.status}`);
  }
}



