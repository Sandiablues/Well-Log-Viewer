import React, { useEffect, useMemo, useState } from "react";
import {
  apiUrl,
  fetchDocuments,
  fetchRepositories,
  fetchVolumeDocuments,
  
  revealDocument,
} from "../services/documentService";
import type {
  DocumentRecord,
  RepositoryRecord,
} from "../services/documentService";

type Props = {
  volumeId?: string;
  title?: string;
  repositoryId?: string;
  packageId?: string;
  packageDisplayName?: string;
  lineId?: string;
  sourceRelativePath?: string;
  linkedScope?: string;
  compact?: boolean;
};

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

function cleanType(value?: string): string {
  if (!value) return "unknown";
  return value.replaceAll("_", " ");
}

export default function SupportingDocumentsPanel({
  volumeId,
  title = "Supporting Documents",
  repositoryId,
  packageId,
  packageDisplayName,
  lineId,
  sourceRelativePath,
  linkedScope,
  compact = false,
}: Props) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [revealingId, setRevealingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadDocuments() {
    setLoading(true);
    setError(null);

    try {
      const [repoRecords, docRecords] = await Promise.all([
        fetchRepositories(),
        volumeId
          ? fetchVolumeDocuments(volumeId)
          : fetchDocuments({
              repository_id: repositoryId,
              linked_scope: linkedScope,
            }),
      ]);

      let scopedDocuments = docRecords;

      if (volumeId) {
        setRepositories(repoRecords);
        setDocuments(docRecords);
        return;
      }

      // Repository filtering happens in the API call.
      // Package/line filtering is applied here because older document records may
      // not have package_id/line_id populated, but they do preserve relative_path.
      const sourcePackageToken = String(sourceRelativePath || "")
        .split("/")[0]
        ?.trim()
        .toLowerCase();

      const packageToken = String(packageDisplayName || sourcePackageToken || "")
        .trim()
        .toLowerCase();

      const packageIdToken = String(packageId || "").trim().toLowerCase();
      const lineIdToken = String(lineId || "").trim().toLowerCase();

      if (packageToken || packageIdToken || lineIdToken) {
        scopedDocuments = docRecords.filter((doc: any) => {
          const docPackageId = String(doc.package_id || "").trim().toLowerCase();
          const docLineId = String(doc.line_id || "").trim().toLowerCase();
          const relPath = String(doc.relative_path || "").trim().toLowerCase();
          const filename = String(doc.filename || "").trim().toLowerCase();

          if (packageIdToken && docPackageId && docPackageId === packageIdToken) {
            return true;
          }

          if (lineIdToken && docLineId && docLineId === lineIdToken) {
            return true;
          }

          if (packageToken) {
            return (
              relPath === packageToken ||
              relPath.startsWith(`${packageToken}/`) ||
              filename.includes(packageToken)
            );
          }

          return false;
        });
      }

      setRepositories(repoRecords);
      setDocuments(scopedDocuments);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load supporting documents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [volumeId, repositoryId, packageId, packageDisplayName, lineId, sourceRelativePath, linkedScope]);

  const repositoryById = useMemo(() => {
    const map = new Map<string, RepositoryRecord>();
    for (const repo of repositories) {
      map.set(repo.repository_id, repo);
    }
    return map;
  }, [repositories]);

  async function handleReveal(documentId: string) {
    setRevealingId(documentId);
    setError(null);

    try {
      await revealDocument(documentId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reveal document");
    } finally {
      setRevealingId(null);
    }
  }

  return (
    <section
      style={{
        marginTop: compact ? 12 : 20,
        padding: compact ? 12 : 16,
        border: "1px solid #334155",
        borderRadius: 10,
        background: "#0f172a",
        color: "#e5e7eb",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 12,
        }}
      >
        <h3
          style={{
            fontSize: compact ? 15 : 17,
            fontWeight: 700,
            margin: 0,
            color: "#f8fafc",
          }}
        >
          {title}
        </h3>

        <button
          type="button"
          onClick={loadDocuments}
          disabled={loading}
          style={{
            padding: "5px 10px",
            fontSize: 12,
            fontWeight: 600,
            borderRadius: 6,
            border: "1px solid #64748b",
            background: loading ? "#1e293b" : "#334155",
            color: "#f8fafc",
            cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div
          style={{
            marginBottom: 10,
            padding: 8,
            borderRadius: 6,
            background: "rgba(239, 68, 68, 0.15)",
            color: "#fecaca",
            fontSize: 12,
          }}
        >
          {error}
        </div>
      )}

      {!loading && documents.length === 0 && (
        <div style={{ fontSize: 12, color: "#94a3b8" }}>
          No linked supporting documents found.
        </div>
      )}

      {documents.length > 0 && (
        <div style={{ display: "grid", gap: 8 }}>
          {documents.map((doc) => {
            const repo = doc.repository_id ? repositoryById.get(doc.repository_id) : undefined;

            const actionStyle: React.CSSProperties = {
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "5px 10px",
              minWidth: 64,
              fontSize: 12,
              fontWeight: 600,
              borderRadius: 6,
              border: "1px solid #64748b",
              background: "#1e293b",
              color: "#f8fafc",
              cursor: "pointer",
              textDecoration: "none",
              lineHeight: 1.2,
            };

            return (
              <div
                key={doc.document_id}
                style={{
                  padding: 12,
                  border: "1px solid #334155",
                  borderRadius: 8,
                  background: "#111827",
                  color: "#e5e7eb",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 12,
                    alignItems: "flex-start",
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontWeight: 650,
                        fontSize: 13,
                        color: "#f8fafc",
                        overflowWrap: "anywhere",
                        marginBottom: 5,
                      }}
                    >
                      {doc.filename}
                    </div>

                    <div style={{ fontSize: 12, color: "#cbd5e1", marginBottom: 5 }}>
                      {cleanType(doc.document_type)}
                      {doc.status ? ` · ${doc.status}` : ""}
                      {doc.size_bytes ? ` · ${formatBytes(doc.size_bytes)}` : ""}
                    </div>

                    <div
                      style={{
                        fontSize: 12,
                        color: "#94a3b8",
                        overflowWrap: "anywhere",
                      }}
                    >
                      {repo?.name || doc.repository_id || "repository unknown"}
                      {doc.relative_path ? ` · ${doc.relative_path}` : ""}
                    </div>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      gap: 6,
                      flexShrink: 0,
                      flexWrap: "wrap",
                      justifyContent: "flex-end",
                    }}
                  >
                    {doc.view_url && (
                      <a
                        href={apiUrl(doc.view_url)}
                        target="_blank"
                        rel="noreferrer"
                        style={actionStyle}
                      >
                        View
                      </a>
                    )}

                    {doc.download_url && (
                      <a
                        href={apiUrl(doc.download_url)}
                        target="_blank"
                        rel="noreferrer"
                        style={actionStyle}
                      >
                        Download
                      </a>
                    )}

                    {doc.reveal_url && (
                      <button
                        type="button"
                        disabled={revealingId === doc.document_id}
                        onClick={() => handleReveal(doc.document_id)}
                        style={{
                          ...actionStyle,
                          opacity: revealingId === doc.document_id ? 0.65 : 1,
                        }}
                      >
                        {revealingId === doc.document_id ? "Opening..." : "Reveal"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
