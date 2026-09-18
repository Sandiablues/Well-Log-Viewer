import { useMemo, useRef, useState } from "react";

export type DocumentDropZoneFile = {
  file: File;
  id: string;
  name: string;
  sizeBytes: number;
  mimeType: string;
  status?: "pending" | "rejected" | "uploading" | "uploaded" | "failed";
  error?: string;
};

export type DocumentDropZoneProps = {
  files: DocumentDropZoneFile[];
  onFilesChange: (files: DocumentDropZoneFile[]) => void;
  disabled?: boolean;
  allowMultiple?: boolean;
  acceptedMimeTypes?: string[];
  acceptedExtensions?: string[];
  maxFiles?: number;
  maxFileSizeBytes?: number;
  title?: string;
  helperText?: string;
};

const DEFAULT_EXTENSIONS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".tif", ".tiff"];
const DEFAULT_MIME_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/plain",
  "text/csv",
  "image/png",
  "image/jpeg",
  "image/tiff",
];

function formatSize(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes)) return "—";
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function extensionFor(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function makeEntry(file: File, error?: string): DocumentDropZoneFile {
  return {
    file,
    id: `${file.name}:${file.size}:${file.lastModified}:${Math.random().toString(16).slice(2)}`,
    name: file.name,
    sizeBytes: file.size,
    mimeType: file.type || "application/octet-stream",
    status: error ? "rejected" : "pending",
    error,
  };
}

export default function DocumentDropZone({
  files,
  onFilesChange,
  disabled = false,
  allowMultiple = true,
  acceptedMimeTypes = DEFAULT_MIME_TYPES,
  acceptedExtensions = DEFAULT_EXTENSIONS,
  maxFiles = 10,
  maxFileSizeBytes = 100 * 1024 * 1024,
  title = "Drop documents here",
  helperText = "or click to select files",
}: DocumentDropZoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const accept = useMemo(() => [...acceptedExtensions, ...acceptedMimeTypes].join(","), [acceptedExtensions, acceptedMimeTypes]);

  const validateFile = (file: File, current: DocumentDropZoneFile[]): string | undefined => {
    const ext = extensionFor(file.name);
    const mime = file.type || "";
    if (current.length >= maxFiles) return `Too many files. Maximum is ${maxFiles}.`;
    if (file.size > maxFileSizeBytes) return `File is too large. Maximum is ${formatSize(maxFileSizeBytes)}.`;
    const extensionOk = acceptedExtensions.includes(ext);
    const mimeOk = !mime || acceptedMimeTypes.includes(mime);
    if (!extensionOk && !mimeOk) return `Unsupported file type: ${ext || mime || "unknown"}.`;
    const duplicate = current.some((entry) => entry.name === file.name && entry.sizeBytes === file.size);
    if (duplicate) return "Duplicate file ignored.";
    return undefined;
  };

  const addFiles = (incoming: FileList | File[]) => {
    if (disabled) return;
    const next = [...files];
    Array.from(incoming).forEach((file) => {
      if (!allowMultiple && next.some((entry) => entry.status !== "rejected")) return;
      const error = validateFile(file, next.filter((entry) => entry.status !== "rejected"));
      if (error === "Duplicate file ignored.") {
        next.push(makeEntry(file, error));
        return;
      }
      next.push(makeEntry(file, error));
    });
    onFilesChange(next);
  };

  const openPicker = () => {
    if (!disabled) inputRef.current?.click();
  };

  return (
    <div style={{ marginBottom: 12 }}>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label="Add supporting documents. Drop files here or press Enter to select files."
        onClick={openPicker}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openPicker();
          }
        }}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) setDragActive(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragActive(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setDragActive(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          addFiles(event.dataTransfer.files);
        }}
        style={{
          minHeight: 104,
          border: `1.5px dashed ${disabled ? "#475569" : dragActive ? "#93c5fd" : "#64748b"}`,
          borderRadius: 10,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: 14,
          cursor: disabled ? "not-allowed" : "pointer",
          color: disabled ? "#94a3b8" : "#e5e7eb",
          background: dragActive && !disabled ? "rgba(148, 163, 184, 0.08)" : "transparent",
          outline: "none",
        }}
      >
        <input
          ref={inputRef}
          type="file"
          multiple={allowMultiple}
          accept={accept}
          disabled={disabled}
          onChange={(event) => {
            if (event.currentTarget.files) addFiles(event.currentTarget.files);
            event.currentTarget.value = "";
          }}
          style={{ display: "none" }}
        />
        <div style={{ fontWeight: 800, marginBottom: 4 }}>{title}</div>
        <div style={{ fontSize: 12, opacity: 0.78 }}>{helperText}</div>
        <div style={{ fontSize: 11, opacity: 0.62, marginTop: 6 }}>PDF, Word, Excel, CSV, text, and image files. Max {formatSize(maxFileSizeBytes)} each.</div>
      </div>
      {files.length > 0 && (
        <div style={{ marginTop: 10, border: "1px solid #334155", borderRadius: 8, overflow: "hidden" }}>
          {files.map((entry) => (
            <div key={entry.id} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 82px 78px", gap: 8, alignItems: "center", padding: "7px 9px", borderBottom: "1px solid rgba(100,116,139,0.22)", fontSize: 12 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{entry.name}</div>
                {entry.error && <div style={{ color: "#fca5a5", marginTop: 2 }}>{entry.error}</div>}
              </div>
              <div style={{ opacity: 0.75 }}>{formatSize(entry.sizeBytes)}</div>
              <button type="button" className="md-control-button" onClick={(event) => { event.stopPropagation(); onFilesChange(files.filter((item) => item.id !== entry.id)); }} disabled={disabled} style={{ padding: "4px 6px" }}>
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
