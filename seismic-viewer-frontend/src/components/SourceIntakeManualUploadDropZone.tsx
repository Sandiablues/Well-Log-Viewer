// MANUAL_UPLOAD_STAGING_3_FRONTEND

import { useMemo, useRef, useState } from "react";
import { Upload, X } from "lucide-react";
import {
  stageManualUploadRepositoryInWorkbench,
  uploadManualSourceIntakePackage,
  type ManualUploadPackageResult,
} from "../services/sourceIntakeManualUploadService";

type UploadEntry = {
  id: string;
  file: File;
  name: string;
  sizeBytes: number;
  extension: string;
  role: "segy" | "document" | "unsupported";
  error?: string;
};

type SourceIntakeManualUploadDropZoneProps = {
  mode: "2d" | "3d";
  onPackageStaged?: (result: ManualUploadPackageResult) => void;
};

const ACCEPTED_EXTENSIONS = new Set([
  ".sgy", ".segy", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
]);

const DOCUMENT_EXTENSIONS = new Set([
  ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
]);

function extensionFor(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function roleForExtension(extension: string): UploadEntry["role"] {
  if (extension === ".sgy" || extension === ".segy") return "segy";
  if (DOCUMENT_EXTENSIONS.has(extension)) return "document";
  return "unsupported";
}

function formatSize(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes)) return "—";
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  if (sizeBytes < 1024 * 1024 * 1024) return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(sizeBytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function makeEntry(file: File, current: UploadEntry[]): UploadEntry {
  const extension = extensionFor(file.name);
  const role = roleForExtension(extension);
  const duplicate = current.some((entry) => entry.name === file.name && entry.sizeBytes === file.size);
  let error: string | undefined;
  if (!ACCEPTED_EXTENSIONS.has(extension)) error = `Unsupported file type: ${extension || "unknown"}.`;
  if (duplicate) error = "Duplicate file ignored.";

  return {
    id: `${file.name}:${file.size}:${file.lastModified}:${Math.random().toString(16).slice(2)}`,
    file,
    name: file.name,
    sizeBytes: file.size,
    extension,
    role,
    error,
  };
}

const buttonStyle = (enabled: boolean, accent = false) => ({
  border: `1px solid ${enabled ? (accent ? "#60a5fa" : "#64748b") : "#475569"}`,
  color: enabled ? (accent ? "#93c5fd" : "#cbd5e1") : "#64748b",
  background: "transparent",
  borderRadius: 8,
  padding: "7px 11px",
  cursor: enabled ? "pointer" : "not-allowed",
  fontSize: 13,
  fontWeight: 750,
  whiteSpace: "nowrap",
} as const);

export default function SourceIntakeManualUploadDropZone({ mode, onPackageStaged }: SourceIntakeManualUploadDropZoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [entries, setEntries] = useState<UploadEntry[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [packageName, setPackageName] = useState("Manual Upload Package");
  const [isUploading, setIsUploading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<ManualUploadPackageResult | null>(null);

  const validEntries = useMemo(() => entries.filter((entry) => !entry.error), [entries]);
  const segyCount = validEntries.filter((entry) => entry.role === "segy").length;
  const documentCount = validEntries.filter((entry) => entry.role === "document").length;
  const unsupportedCount = entries.filter((entry) => entry.role === "unsupported" || entry.error).length;
  const canUpload = !isUploading && segyCount > 0 && validEntries.length > 0;

  const addFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    if (!incoming.length || isUploading) return;
    setEntries((current) => {
      const next = [...current];
      incoming.forEach((file) => next.push(makeEntry(file, next)));
      return next;
    });
    setResult(null);
    setError("");
    setStatus("");
  };

  const upload = async () => {
    if (!canUpload) return;
    setIsUploading(true);
    setError("");
    setResult(null);
    setStatus("Uploading and staging package. No conversion will be started.");
    try {
      const uploadResult = await uploadManualSourceIntakePackage({
        files: validEntries.map((entry) => entry.file),
        mode,
        packageName,
        intendedUse: "source_intake",
      });

      const repositoryId = String(uploadResult.repository_id || "").trim();
      if (repositoryId) {
        setStatus("Package uploaded. Staging repository in Selection & Conversion…");
        await stageManualUploadRepositoryInWorkbench({ mode, repositoryId });
      }

      setResult(uploadResult);
      setStatus("Package staged. Review Selection & Conversion before starting index or Zarr conversion.");
      onPackageStaged?.(uploadResult);
      window.dispatchEvent(new CustomEvent("multiviewer:source-intake-updated", { detail: { source: "manual-upload-drop-zone", repository_id: repositoryId, package_id: uploadResult.package_id } }));
    } catch (err) {
      console.error("Manual upload staging failed", err);
      setError(err instanceof Error ? err.message : "Manual upload staging failed.");
      setStatus("");
    } finally {
      setIsUploading(false);
    }
  };

  const clearQueue = () => {
    if (isUploading) return;
    setEntries([]);
    setResult(null);
    setError("");
    setStatus("");
  };

  return (
    <div style={{ border: "1px solid #334155", borderRadius: 10, background: "#0f172a", color: "#e5e7eb", padding: 12, marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 850, color: "#f8fafc" }}>Manual Upload / Drop Zone</div>
          <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4, lineHeight: 1.4 }}>
            Upload one or more SEG-Y files with supporting documents. Files are staged for Source Intake review; no index or Zarr conversion starts during upload.
          </div>
        </div>
        <div style={{ fontSize: 12, color: "#94a3b8", whiteSpace: "nowrap" }}>{mode.toUpperCase()} mode</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "140px minmax(0, 1fr)", gap: "8px 10px", alignItems: "center", marginBottom: 10 }}>
        <label style={{ fontSize: 12, color: "#94a3b8" }}>Package name</label>
        <input
          value={packageName}
          onChange={(event) => setPackageName(event.target.value)}
          disabled={isUploading}
          style={{ background: "#020617", color: "#e5e7eb", border: "1px solid #475569", borderRadius: 7, padding: "7px 9px" }}
        />
      </div>

      <div
        role="button"
        tabIndex={0}
        onClick={() => !isUploading && inputRef.current?.click()}
        onKeyDown={(event) => {
          if ((event.key === "Enter" || event.key === " ") && !isUploading) {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragEnter={(event) => { event.preventDefault(); if (!isUploading) setDragActive(true); }}
        onDragOver={(event) => { event.preventDefault(); if (!isUploading) setDragActive(true); }}
        onDragLeave={(event) => { event.preventDefault(); setDragActive(false); }}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          addFiles(event.dataTransfer.files);
        }}
        style={{
          minHeight: 118,
          border: `1.5px dashed ${dragActive ? "#93c5fd" : "#64748b"}`,
          borderRadius: 10,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          cursor: isUploading ? "not-allowed" : "pointer",
          background: dragActive ? "rgba(96, 165, 250, 0.08)" : "transparent",
          padding: 14,
        }}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".sgy,.segy,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.png,.jpg,.jpeg,.tif,.tiff"
          disabled={isUploading}
          onChange={(event) => {
            if (event.currentTarget.files) addFiles(event.currentTarget.files);
            event.currentTarget.value = "";
          }}
          style={{ display: "none" }}
        />
        <Upload size={22} />
        <div style={{ fontWeight: 850, marginTop: 8 }}>Drop SEG-Y and supporting documents here</div>
        <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>or click to browse. SEG-Y files are staged only; conversion remains manual.</div>
      </div>

      {entries.length > 0 && (
        <div style={{ marginTop: 10, border: "1px solid #334155", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 100px 90px 38px", gap: 8, padding: "7px 9px", background: "rgba(15,23,42,0.9)", fontSize: 11, color: "#94a3b8", fontWeight: 800 }}>
            <div>File</div>
            <div>Role</div>
            <div>Size</div>
            <div />
          </div>
          {entries.map((entry) => (
            <div key={entry.id} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 100px 90px 38px", gap: 8, alignItems: "center", padding: "7px 9px", borderTop: "1px solid rgba(100,116,139,0.24)", fontSize: 12 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entry.name}</div>
                {entry.error && <div style={{ color: "#fca5a5", marginTop: 2 }}>{entry.error}</div>}
              </div>
              <div style={{ color: entry.role === "segy" ? "#93c5fd" : entry.role === "document" ? "#c4b5fd" : "#fca5a5", fontWeight: 750 }}>{entry.role}</div>
              <div style={{ color: "#94a3b8" }}>{formatSize(entry.sizeBytes)}</div>
              <button type="button" onClick={() => setEntries((current) => current.filter((item) => item.id !== entry.id))} disabled={isUploading} style={buttonStyle(!isUploading)} aria-label={`Remove ${entry.name}`}>
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
        <button type="button" onClick={upload} disabled={!canUpload} style={buttonStyle(canUpload, true)}>
          {isUploading ? "Uploading…" : "Upload and Stage"}
        </button>
        <button type="button" onClick={clearQueue} disabled={isUploading || entries.length === 0} style={buttonStyle(!isUploading && entries.length > 0)}>
          Clear Queue
        </button>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>
          SEG-Y: {segyCount} · Documents: {documentCount} · Rejected: {unsupportedCount}
        </div>
      </div>

      {status && <div style={{ marginTop: 9, fontSize: 12, color: "#bfdbfe" }}>{status}</div>}
      {error && <div style={{ marginTop: 9, fontSize: 12, color: "#fca5a5", whiteSpace: "pre-wrap" }}>{error}</div>}

      {result && (
        <div style={{ marginTop: 10, border: "1px solid #334155", borderRadius: 8, padding: 10, background: "rgba(2,6,23,0.55)", fontSize: 12 }}>
          <div style={{ fontWeight: 850, marginBottom: 6 }}>Staged package</div>
          <div>Package: {result.package_id || "—"}</div>
          <div>Repository: {result.repository_id || "—"}</div>
          <div>SEG-Y candidates: {result.segy_candidates?.length ?? 0}</div>
          <div>Supporting documents staged for assignment: {result.supporting_documents?.length ?? 0}</div>
          {(result.supporting_documents?.length ?? 0) > 0 && (
            <div style={{ marginTop: 8, border: "1px solid #334155", borderRadius: 7, padding: 8 }}>
              <div style={{ color: "#cbd5e1", fontWeight: 800, marginBottom: 5 }}>Documents available to assign</div>
              {(result.supporting_documents || []).map((doc: Record<string, any>) => (
                <div key={String(doc.document_id || doc.filename)} style={{ color: "#e2e8f0", marginTop: 3 }}>
                  {String(doc.filename || doc.document_id || "Document")} <span style={{ color: "#94a3b8" }}>({String(doc.document_type || "document")})</span>
                </div>
              ))}
              <div style={{ color: "#94a3b8", marginTop: 6 }}>
                Select a staged SEG-Y row above and use Assign Documents, or click Assign in the Supporting Docs column.
              </div>
            </div>
          )}
          <div>Conversion started: {String(Boolean(result.conversion_started))}</div>
          <div>Index started: {String(Boolean(result.index_started))}</div>
        </div>
      )}
    </div>
  );
}
