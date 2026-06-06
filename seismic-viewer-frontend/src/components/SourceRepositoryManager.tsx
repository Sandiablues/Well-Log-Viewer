import React, { useEffect, useMemo, useState } from "react";
import {
  fetchLines,
  fetchPackages,
  fetchRepositories,
  fetchSegyFiles,
} from "../services/registryService";
import {
  stageSourceIntakeRepositoryWorkbench,
  type SourceIntakeStageWorkbenchResult,
} from "../services/sourceIntakeWorkbenchV2Service";
import type {
  LineRecord,
  PackageRecord,
  RepositoryRecord,
  SegyFileRecord,
} from "../services/registryService";

type Props = {
  onRepositoryChanged?: () => Promise<void> | void;
  onBrowseRepository?: (repositoryId: string, repository?: RepositoryRecord) => void;
  onStageRepository?: (repositoryId: string, repository: RepositoryRecord, stageResult: SourceIntakeStageWorkbenchResult) => void | Promise<void>;
  activeDataTab?: "2d" | "3d";
};

type IntakeMode = "2d" | "3d";

type FolderBrowserEntry = {
  name: string;
  path: string;
  kind: "folder" | "file" | string;
  extension?: string | null;
  size_bytes?: number | null;
  file_role?: "segy" | "document" | "other" | string;
};

type FolderBrowserRoot = {
  name: string;
  path: string;
  kind: "root" | "volume" | string;
};

type FolderBrowserPayload = {
  status: string;
  current_path: string;
  parent_path?: string | null;
  roots?: FolderBrowserRoot[];
  entries: FolderBrowserEntry[];
};

function formatBrowserFileSize(sizeBytes?: number | null): string {
  if (!Number.isFinite(Number(sizeBytes))) return "—";
  const value = Number(sizeBytes);
  if (value < 1024) return `${value} B`;
  const kb = value / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function getBrowserEntryIcon(entry: FolderBrowserEntry): string {
  if (entry.kind === "folder") return "📁";
  if (entry.file_role === "segy") return "◈";
  if (entry.extension === ".pdf") return "📄";
  if (entry.extension === ".doc" || entry.extension === ".docx") return "📝";
  if (entry.extension === ".xls" || entry.extension === ".xlsx" || entry.extension === ".csv") return "▦";
  if (entry.extension === ".txt" || entry.extension === ".rtf") return "≡";
  return "•";
}

function getBrowserEntryTypeLabel(entry: FolderBrowserEntry): string {
  if (entry.kind === "folder") return "Folder";
  if (entry.file_role === "segy") return "SEG-Y";
  if (entry.file_role === "document") return `${(entry.extension || "file").replace(".", "").toUpperCase()} document`;
  return `${(entry.extension || "file").replace(".", "").toUpperCase() || "File"}`;
}

const modalBackdropStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,.55)",
  zIndex: 9998,
};

const modalStyle: React.CSSProperties = {
  position: "fixed",
  zIndex: 9999,
  top: "6vh",
  left: "50%",
  transform: "translateX(-50%)",
  width: "min(1040px, 88vw)",
  maxHeight: "86vh",
  display: "grid",
  gridTemplateRows: "auto auto 1fr auto",
  background: "#111827",
  border: "1px solid #374151",
  borderRadius: 12,
  boxShadow: "0 24px 70px rgba(0,0,0,.45)",
  color: "#e5e7eb",
  overflow: "hidden",
};


type SourceStructureType =
  | "single_isolated_line"
  | "single_line_with_docs"
  | "single_line_multi_version"
  | "survey_with_line_folders"
  | "survey_flat_lines"
  | "single_3d_volume"
  | "single_3d_volume_with_docs"
  | "multi_version_3d_delivery";

type SourceStructureOption = {
  value: SourceStructureType;
  label: string;
  description: string;
};

const sourceStructureOptions2D: SourceStructureOption[] = [
  {
    value: "single_isolated_line",
    label: "Single isolated 2D SEG-Y line",
    description: "One SEG-Y file with no supporting documentation.",
  },
  {
    value: "single_line_with_docs",
    label: "Single 2D line folder with supporting documents",
    description: "One line plus reports, observer logs, maps, navigation, or other supporting files.",
  },
  {
    value: "single_line_multi_version",
    label: "Single 2D line with multiple processing versions",
    description: "Several SEG-Y files representing versions of the same line, plus possible documents.",
  },
  {
    value: "survey_with_line_folders",
    label: "2D survey with multiple line folders",
    description: "A survey folder containing line-level folders, each with SEG-Y and possible documents.",
  },
  {
    value: "survey_flat_lines",
    label: "2D survey with flat SEG-Y lines and documents",
    description: "A survey folder containing many SEG-Y lines directly, plus possible supporting documents.",
  },
];

const sourceStructureOptions3D: SourceStructureOption[] = [
  {
    value: "single_3d_volume",
    label: "Single 3D SEG-Y volume",
    description: "One standalone 3D SEG-Y volume with no supporting documentation.",
  },
  {
    value: "single_3d_volume_with_docs",
    label: "3D volume folder with supporting documents",
    description: "One 3D SEG-Y volume plus reports, notes, navigation, velocity, or delivery documents.",
  },
  {
    value: "multi_version_3d_delivery",
    label: "Multi-version 3D delivery folder with supporting documents",
    description: "A delivery folder containing multiple processed 3D SEG-Y versions plus package-level documents.",
  },
];

function clean(value?: string): string {
  return value ? value.replaceAll("_", " ") : "unknown";
}

function formatRepositoryStatus(value?: string): string {
  const text = value ? value.trim() : "";
  if (!text) return "Unknown";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatRepositoryLastScanScope(repo: RepositoryRecord, latestByRepositoryId: Record<string, string>): string {
  const repositoryId = repo.repository_id || (repo as any).id;
  if (repositoryId && latestByRepositoryId[repositoryId]) {
    return latestByRepositoryId[repositoryId];
  }
  return "Not scanned this session";
}

function formatRepositoryFolderSummary(repo: RepositoryRecord): string {
  const summary = (repo as any).folder_summary || (repo as any).folderSummary;
  if (summary && typeof summary === "object") {
    const main = Number(summary.main ?? summary.main_count ?? 0);
    const subfolders = Number(summary.subfolders ?? summary.subfolder_count ?? 0);
    return `${Number.isFinite(main) ? main : 0} main / ${Number.isFinite(subfolders) ? subfolders : 0} subfolders`;
  }

  return repo.root_path ? "1 main / 0 subfolders" : "0 main / 0 subfolders";
}

function formatDate(value?: string | null): string {
  if (!value) return "Not scanned";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

const panelStyle: React.CSSProperties = {
  border: "1px solid #333",
  borderRadius: 10,
  background: "#1f1f1f",
  padding: 14,
  marginBottom: 16,
  color: "#e5e7eb",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "7px 9px",
  borderRadius: 6,
  border: "1px solid #555",
  background: "#2b2b2b",
  color: "#f8fafc",
  fontSize: 13,
};

const buttonStyle: React.CSSProperties = {
  border: "1px solid #60a5fa",
  borderRadius: 6,
  background: "transparent",
  color: "#60a5fa",
  padding: "6px 10px",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};

const secondaryButtonStyle: React.CSSProperties = {
  border: "1px solid #64748b",
  borderRadius: 6,
  background: "transparent",
  color: "#cbd5e1",
  padding: "6px 10px",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};

const dangerButtonStyle: React.CSSProperties = {
  border: "1px solid #f87171",
  borderRadius: 6,
  background: "transparent",
  color: "#f87171",
  padding: "6px 10px",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
};

export default function SourceRepositoryManager({
  onRepositoryChanged,
  onBrowseRepository,
  onStageRepository,
  activeDataTab = "2d",
}: Props) {
  const sourceRepositorySelectorMode = activeDataTab === "2d" ? "2d" : "3d";
  const sourceRepositoryListUrl = `/api/source-intake/repositories?mode=${sourceRepositorySelectorMode}`;
  const sourceRepositoryCreateUrl = `/api/source-intake/repositories?mode=${sourceRepositorySelectorMode}`;

  function filterRepositoriesForActiveMode(rows: any[]): any[] {
    const expectedUse = sourceRepositorySelectorMode === "2d" ? "2d_segy_intake" : "3d_segy_intake";
    const expectedStructure = sourceRepositorySelectorMode === "2d" ? "survey_with_line_folders" : "multi_version_3d_delivery";

    return (rows || []).filter((repo: any) => {
      const intendedUse = String(repo?.intended_use || repo?.source?.intended_use || "").toLowerCase();
      const workflowMode = String(repo?.workflow_mode || repo?.mode || "").toLowerCase();
      const structure = String(repo?.source_structure_type || repo?.source?.source_structure_type || "").toLowerCase();

      if (workflowMode === sourceRepositorySelectorMode) return true;
      if (intendedUse === expectedUse) return true;
      if (structure === expectedStructure) return true;
      return false;
    });
  }

  const [repositories, setRepositories] = useState<RepositoryRecord[]>([]);
  const [packages, setPackages] = useState<PackageRecord[]>([]);
  const [lines, setLines] = useState<LineRecord[]>([]);
  const [segyFiles, setSegyFiles] = useState<SegyFileRecord[]>([]);

  const [name, setName] = useState("2D Source Repository");
  const [rootPath, setRootPath] = useState("");
  const [includeSubfolders, setIncludeSubfolders] = useState(false);
  const [lastScanScopeByRepositoryId, setLastScanScopeByRepositoryId] = useState<Record<string, string>>({});
  const [intakeMode, setIntakeMode] = useState<IntakeMode>(activeDataTab === "3d" ? "3d" : "2d");
  const [sourceStructureType, setSourceStructureType] =
    useState<SourceStructureType>("survey_with_line_folders");

  const activeSourceStructureOptions =
    intakeMode === "3d" ? sourceStructureOptions3D : sourceStructureOptions2D;

  const [busyRepoId, setBusyRepoId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [utilityBlinkKey, setUtilityBlinkKey] = useState("");

  const [folderBrowserOpen, setFolderBrowserOpen] = useState(false);
  const [folderBrowsePath, setFolderBrowsePath] = useState("");
  const [folderBrowsePathInput, setFolderBrowsePathInput] = useState("");
  const [folderBrowseParentPath, setFolderBrowseParentPath] = useState<string | null>(null);
  const [folderBrowseRoots, setFolderBrowseRoots] = useState<FolderBrowserRoot[]>([]);
  const [folderBrowseEntries, setFolderBrowseEntries] = useState<FolderBrowserEntry[]>([]);
  const [folderBrowseFilter, setFolderBrowseFilter] = useState<"all" | "folders" | "segy" | "documents" | "other">("all");
  const [folderBrowseLoading, setFolderBrowseLoading] = useState(false);
  const [folderBrowseError, setFolderBrowseError] = useState("");

  async function reload() {
    setLoading(true);
    setError("");

    try {
      const repoRecords = await fetchRepositories();
      const allPackages = await fetchPackages();
      const allLines = await fetchLines();
      const allSegyFiles = await fetchSegyFiles();

      setRepositories(filterRepositoriesForActiveMode(repoRecords));
      setPackages(allPackages);
      setLines(allLines);
      setSegyFiles(allSegyFiles);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load source repositories");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, [sourceRepositorySelectorMode]);

  useEffect(() => {
    const handleSourceRepositoryExternalRefresh = () => {
      void reload();
    };

    window.addEventListener("multiviewer:source-intake-updated", handleSourceRepositoryExternalRefresh);
    window.addEventListener("multiviewer:managed-data-updated", handleSourceRepositoryExternalRefresh);

    return () => {
      window.removeEventListener("multiviewer:source-intake-updated", handleSourceRepositoryExternalRefresh);
      window.removeEventListener("multiviewer:managed-data-updated", handleSourceRepositoryExternalRefresh);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceRepositorySelectorMode]);

  useEffect(() => {
    const nextMode: IntakeMode = activeDataTab === "3d" ? "3d" : "2d";
    setIntakeMode(nextMode);
    if (nextMode === "3d") {
      setName("3D Source Repository");
      setSourceStructureType("multi_version_3d_delivery");
    } else {
      setName("2D Source Repository");
      setSourceStructureType("survey_with_line_folders");
    }
  }, [activeDataTab]);

  const packageCountByRepo = useMemo(() => {
    const map = new Map<string, number>();
    for (const pkg of packages) {
      map.set(pkg.repository_id, (map.get(pkg.repository_id) || 0) + 1);
    }
    return map;
  }, [packages]);

  const lineCountByRepo = useMemo(() => {
    const map = new Map<string, number>();
    for (const line of lines) {
      map.set(line.repository_id, (map.get(line.repository_id) || 0) + 1);
    }
    return map;
  }, [lines]);

  const segyCountByRepo = useMemo(() => {
    const map = new Map<string, number>();
    for (const file of segyFiles) {
      map.set(file.repository_id, (map.get(file.repository_id) || 0) + 1);
    }
    return map;
  }, [segyFiles]);

  const convertedCountByRepo = useMemo(() => {
    const map = new Map<string, number>();
    for (const file of segyFiles) {
      if (file.conversion_status === "converted" || file.conversion_status === "ready") {
        map.set(file.repository_id, (map.get(file.repository_id) || 0) + 1);
      }
    }
    return map;
  }, [segyFiles]);

  async function loadFolderBrowser(pathValue?: string) {
    setFolderBrowseLoading(true);
    setFolderBrowseError("");

    try {
      const query = pathValue ? `?path=${encodeURIComponent(pathValue)}` : "";
      const response = await fetch(`/api/local-folders${query}`);
      const payload = await response.json().catch(() => null) as FolderBrowserPayload | null;

      if (!response.ok || !payload) {
        throw new Error((payload as any)?.detail || `Folder browse failed: ${response.status}`);
      }

      setFolderBrowsePath(payload.current_path || "");
      setFolderBrowsePathInput(payload.current_path || "");
      setFolderBrowseParentPath(payload.parent_path || null);
      setFolderBrowseRoots(payload.roots || []);
      setFolderBrowseEntries(payload.entries || []);
    } catch (err) {
      setFolderBrowseError(err instanceof Error ? err.message : "Failed to browse folders");
    } finally {
      setFolderBrowseLoading(false);
    }
  }

  async function openFolderBrowser() {
    setFolderBrowserOpen(true);
    await loadFolderBrowser(rootPath.trim() || undefined);
  }

  function selectCurrentBrowseFolder() {
    if (!folderBrowsePath) return;
    setRootPath(folderBrowsePath);
    setFolderBrowserOpen(false);
  }

  async function goToFolderBrowsePath() {
    if (!folderBrowsePathInput.trim()) return;
    await loadFolderBrowser(folderBrowsePathInput.trim());
  }


  function blinkUtilityButton(key: string) {
    setUtilityBlinkKey(key);
    window.setTimeout(() => {
      setUtilityBlinkKey((current) => (current === key ? "" : current));
    }, 360);
  }

  function utilityButtonStyle(key: string, disabled?: boolean): React.CSSProperties {
    const active = utilityBlinkKey === key && !disabled;

    return {
      ...secondaryButtonStyle,
      border: "1px solid #64748b",
      background: "transparent",
      color: disabled ? "#71717a" : "#cbd5e1",
      boxShadow: active ? "0 0 0 2px rgba(203,213,225,.32)" : "none",
      opacity: active ? 0.96 : 1,
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "opacity 80ms ease, box-shadow 80ms ease",
    };
  }

  async function addRepository() {
    if (!name.trim()) {
      setError("Repository name is required.");
      return;
    }

    if (!rootPath.trim()) {
      setError("Root folder path is required.");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const selectedType = activeSourceStructureOptions.find((item) => item.value === sourceStructureType);
      const notesPrefix =
        intakeMode === "3d"
          ? `source_structure_type=${sourceStructureType}; intended_use=3d_segy_intake`
          : `source_structure_type=${sourceStructureType}; intended_use=2d_segy_intake`;

      const response = await fetch(sourceRepositoryCreateUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          root_path: rootPath.trim(),
          repository_type: "local_folder",
          read_only: true,
        include_subfolders: includeSubfolders,
          notes: `${notesPrefix}; ${selectedType?.label || ""}`,
        }),
      });

      const result = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(result?.detail || `Add repository failed: ${response.status}`);
      }

      setMessage("Repository added. Click Scan / Rescan to build inventory.");
      setShowAddForm(false);
      await reload();
      await onRepositoryChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add repository");
    } finally {
      setLoading(false);
    }
  }

  async function scanRepository(repositoryId: string) {
    setBusyRepoId(repositoryId);
    setError("");
    setMessage("");

    try {
      const response = await fetch(`/api/repositories/${repositoryId}/persist-scan?include_subfolders=${includeSubfolders ? "true" : "false"}`, {
        method: "POST",
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(JSON.stringify(result, null, 2));
      }

      const summary = result.summary || {};
      const scopeLabel = includeSubfolders ? "Root + subfolders" : "Root only";
      setLastScanScopeByRepositoryId((previous) => ({
        ...previous,
        [repositoryId]: scopeLabel,
      }));

      const primaryLabel = activeDataTab === "3d" ? "volumes" : "lines";
      const primaryCount = activeDataTab === "3d"
        ? Number(summary.segy_file_count || summary.candidate_count || summary.line_group_count || 0)
        : Number(summary.line_group_count || summary.line_count || 0);
      setMessage(
        `Scan complete (${includeSubfolders ? "root + subfolders" : "root only"}): ${summary.package_count || 0} packages, ${primaryCount} ${primaryLabel}, ${summary.segy_file_count || 0} SEG-Y files, ${summary.document_count || 0} documents.`
      );

      await reload();
      await onRepositoryChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Repository scan failed");
    } finally {
      setBusyRepoId(null);
    }
  }


  async function deleteRepository(repositoryId: string, repositoryName: string) {
    const confirmed = window.confirm(
      `Delete source repository "${repositoryName}"?\n\n` +
        "This removes the source repository and its scanned Source Intake candidate inventory.\n" +
        "Converted Managed Data volumes and Zarr files will NOT be deleted."
    );

    if (!confirmed) return;

    setBusyRepoId(repositoryId);
    setError("");
    setMessage("");

    try {
      const response = await fetch(`/api/repositories/${encodeURIComponent(repositoryId)}`, {
        method: "DELETE",
      });

      const result = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(result?.detail || `Delete repository failed: ${response.status}`);
      }

      const removed = result?.removed || {};
      setMessage(
        `Repository deleted. Removed ${removed.packages || 0} packages, ${removed.lines || 0} lines, ` +
          `${removed.segy_files || 0} SEG-Y records, and ${removed.documents || 0} documents. ` +
          "Converted Managed Data was not deleted."
      );

      onBrowseRepository?.("");
      await reload();
      await onRepositoryChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete repository");
    } finally {
      setBusyRepoId(null);
    }
  }

  async function stageRepository(repo: RepositoryRecord) {
    const repositoryId = repo.repository_id;
    if (!repositoryId || busyRepoId === repositoryId) return;

    blinkUtilityButton(`browse-source-${repositoryId}`);
    setBusyRepoId(repositoryId);
    setError("");

    try {
      const stageResult = await stageSourceIntakeRepositoryWorkbench(repositoryId, activeDataTab);
      const summary = (stageResult.repository?.scan_summary || {}) as Record<string, any>;
      const messageText = String(summary.message || "").trim();
      if (messageText) setMessage(messageText);

      if (onStageRepository) {
        await onStageRepository(repositoryId, repo, stageResult);
      } else {
        onBrowseRepository?.(repositoryId, repo);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyRepoId(null);
    }
  }

  const sourceStructureTypes3D = new Set([
    "single_3d_volume",
    "single_3d_volume_with_docs",
    "multi_version_3d_delivery",
  ]);

  const sourceStructureTypes2D = new Set([
    "single_isolated_line",
    "single_line_with_docs",
    "single_line_multi_version",
    "survey_with_line_folders",
    "survey_flat_lines",
  ]);

  function is3DRepository(repo: RepositoryRecord): boolean {
    return (
      repo.intended_use === "3d_segy_intake" ||
      sourceStructureTypes3D.has(String(repo.source_structure_type || ""))
    );
  }

  function is2DRepository(repo: RepositoryRecord): boolean {
    return (
      repo.intended_use === "2d_segy_intake" ||
      sourceStructureTypes2D.has(String(repo.source_structure_type || ""))
    );
  }

  const filteredFolderBrowseEntries = folderBrowseEntries.filter((entry) => {
    if (folderBrowseFilter === "all") return true;
    if (folderBrowseFilter === "folders") return entry.kind === "folder";
    if (folderBrowseFilter === "segy") return entry.kind === "file" && entry.file_role === "segy";
    if (folderBrowseFilter === "documents") return entry.kind === "file" && entry.file_role === "document";
    if (folderBrowseFilter === "other") return entry.kind === "file" && entry.file_role !== "segy" && entry.file_role !== "document";
    return true;
  });

  const filteredFolderCount = filteredFolderBrowseEntries.filter((entry) => entry.kind === "folder").length;
  const filteredFileCount = filteredFolderBrowseEntries.filter((entry) => entry.kind === "file").length;

  const filteredRepositories = repositories;

  return (
    <section className="source-intake-repository-manager" style={panelStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 12 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 18 }}>
            Source Repository Selection
          </h3>
          <div style={{ marginTop: 4, fontSize: 12, color: "#a1a1aa" }}>
            Register source folders, explicitly set 2D or 3D intake intent, then scan into Selection and Conversion.
          </div>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            style={utilityButtonStyle("refresh-repositories", loading)}
            onClick={() => {
              blinkUtilityButton("refresh-repositories");
              reload();
            }}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "Refresh"}
          </button>
          <button type="button" style={buttonStyle} onClick={() => setShowAddForm(!showAddForm)}>
            {showAddForm ? "Close" : "+ Add Source Repository"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 10, padding: 8, borderRadius: 7, background: "rgba(239,68,68,.15)", color: "#fecaca", fontSize: 12, whiteSpace: "pre-wrap" }}>
          {error}
        </div>
      )}

      {message && (
        <div style={{ marginBottom: 10, padding: 8, borderRadius: 7, background: "rgba(34,197,94,.12)", color: "#bbf7d0", fontSize: 12 }}>
          {message}
        </div>
      )}

      {folderBrowserOpen && (
        <>
          <div style={modalBackdropStyle} onClick={() => setFolderBrowserOpen(false)} />
          <div style={modalStyle}>
            <div style={{ padding: 14, borderBottom: "1px solid #374151", display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 17 }}>Choose Source Intake Folder</h3>
                <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                  Browse local folders and select the parent folder for Source Intake scanning.
                </div>
              </div>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12, color: "#cbd5e1" }}>
                <input
                  type="checkbox"
                  checked={includeSubfolders}
                  onChange={(event) => setIncludeSubfolders(event.target.checked)}
                />
                Include subfolders
              </label>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>
                When off, only the selected folder is scanned. When on, the selected folder and subfolders are scanned.
              </div>
            </div>

            <div style={{ padding: 10, borderBottom: "1px solid #374151", background: "#0f172a", display: "grid", gridTemplateColumns: "auto 1fr auto auto", gap: 8, alignItems: "center" }}>
              <button
                type="button"
                style={secondaryButtonStyle}
                onClick={() => folderBrowseParentPath && loadFolderBrowser(folderBrowseParentPath)}
                disabled={!folderBrowseParentPath || folderBrowseLoading}
              >
                Up
              </button>

              <input
                value={folderBrowsePathInput}
                onChange={(event) => setFolderBrowsePathInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    goToFolderBrowsePath();
                  }
                }}
                style={inputStyle}
              />

              <button
                type="button"
                style={utilityButtonStyle("go-folder", folderBrowseLoading)}
                onClick={() => {
                  blinkUtilityButton("go-folder");
                  goToFolderBrowsePath();
                }}
                disabled={folderBrowseLoading}
              >
                Go
              </button>

              <button type="button" style={buttonStyle} onClick={selectCurrentBrowseFolder} disabled={!folderBrowsePath}>
                Select Current Folder
              </button>
            </div>

            {folderBrowseError && (
              <div style={{ padding: 10, borderBottom: "1px solid #7f1d1d", background: "rgba(127,29,29,.2)", color: "#fecaca", fontSize: 12, whiteSpace: "pre-wrap" }}>
                {folderBrowseError}
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", minHeight: 0 }}>
              <aside style={{ borderRight: "1px solid #374151", background: "#0b1220", padding: 10, overflow: "auto" }}>
                <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 8 }}>
                  Locations
                </div>

                <div style={{ display: "grid", gap: 5 }}>
                  {folderBrowseRoots.map((rootEntry) => (
                    <button
                      key={`${rootEntry.kind}:${rootEntry.path}`}
                      type="button"
                      onClick={() => loadFolderBrowser(rootEntry.path)}
                      style={{
                        textAlign: "left",
                        border: rootEntry.path === folderBrowsePath ? "1px solid #8fb8e8" : "1px solid transparent",
                        borderRadius: 7,
                        background: rootEntry.path === folderBrowsePath ? "rgba(59,130,246,.24)" : "transparent",
                        color: "#e5e7eb",
                        padding: "7px 8px",
                        cursor: "pointer",
                        fontSize: 12,
                        fontWeight: 650,
                        overflowWrap: "anywhere",
                      }}
                    >
                      {rootEntry.kind === "volume" ? "💽" : "📁"} {rootEntry.name}
                    </button>
                  ))}
                </div>
              </aside>

              <main style={{ minHeight: 0, overflow: "auto", padding: 10 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center", marginBottom: 8 }}>
                  <div>
                    <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: ".04em" }}>
                      Current folder
                    </div>
                    <div style={{ marginTop: 3, fontSize: 12, color: "#cbd5e1", overflowWrap: "anywhere" }}>
                      {folderBrowsePath || "Loading..."}
                    </div>
                  </div>

                  <div style={{ fontSize: 12, color: "#94a3b8" }}>
                    {folderBrowseLoading
                      ? "Loading..."
                      : `${filteredFolderCount} folders · ${filteredFileCount} files shown`}
                  </div>
                </div>

                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                  {[
                    ["all", "All"],
                    ["folders", "Folders"],
                    ["segy", "SEG-Y"],
                    ["documents", "Documents"],
                    ["other", "Other files"],
                  ].map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setFolderBrowseFilter(key as typeof folderBrowseFilter)}
                      style={{
                        border: folderBrowseFilter === key ? "1px solid #8fb8e8" : "1px solid #64748b",
                        borderRadius: 6,
                        background: "transparent",
                        color: folderBrowseFilter === key ? "#bfdbfe" : "#cbd5e1",
                        padding: "4px 8px",
                        fontSize: 11,
                        fontWeight: folderBrowseFilter === key ? 800 : 650,
                        cursor: "pointer",
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <div style={{ border: "1px solid #334155", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 34%) 120px 90px 1fr", gap: 8, padding: "7px 10px", background: "#111827", color: "#94a3b8", fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em" }}>
                    <div>Name</div>
                    <div>Type</div>
                    <div>Size</div>
                    <div>Path</div>
                  </div>

                  {folderBrowseParentPath && (
                    <button
                      type="button"
                      onClick={() => loadFolderBrowser(folderBrowseParentPath)}
                      style={{
                        width: "100%",
                        display: "grid",
                        gridTemplateColumns: "minmax(220px, 34%) 120px 90px 1fr",
                        gap: 8,
                        textAlign: "left",
                        border: "0",
                        borderTop: "1px solid #1f2937",
                        background: "#0f172a",
                        color: "#dbeafe",
                        padding: "8px 10px",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 750 }}>⬆ Parent folder</div>
                      <div style={{ fontSize: 12, color: "#94a3b8" }}>Folder</div>
                      <div style={{ fontSize: 12, color: "#94a3b8" }}>—</div>
                      <div style={{ fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>{folderBrowseParentPath}</div>
                    </button>
                  )}

                  {filteredFolderBrowseEntries.length === 0 && !folderBrowseLoading ? (
                    <div style={{ padding: 12, fontSize: 12, color: "#94a3b8", borderTop: "1px solid #1f2937" }}>
                      No matching folders or files found. You can select the current folder or change the filter.
                    </div>
                  ) : (
                    filteredFolderBrowseEntries.map((entry) => {
                      const isFolder = entry.kind === "folder";

                      return (
                        <button
                          key={entry.path}
                          type="button"
                          onClick={() => {
                            if (isFolder) {
                              loadFolderBrowser(entry.path);
                            }
                          }}
                          disabled={!isFolder}
                          title={isFolder ? "Open folder" : "File shown for inspection only"}
                          style={{
                            width: "100%",
                            display: "grid",
                            gridTemplateColumns: "minmax(220px, 34%) 120px 90px 1fr",
                            gap: 8,
                            textAlign: "left",
                            border: "0",
                            borderTop: "1px solid #1f2937",
                            background: isFolder ? "#0f172a" : "#111827",
                            color: isFolder ? "#e5e7eb" : "#cbd5e1",
                            padding: "8px 10px",
                            cursor: isFolder ? "pointer" : "default",
                            opacity: isFolder ? 1 : 0.92,
                          }}
                        >
                          <div style={{ fontSize: 13, fontWeight: isFolder ? 700 : 600, overflowWrap: "anywhere" }}>
                            {getBrowserEntryIcon(entry)} {entry.name}
                          </div>
                          <div style={{ fontSize: 12, color: "#94a3b8" }}>{getBrowserEntryTypeLabel(entry)}</div>
                          <div style={{ fontSize: 12, color: "#94a3b8" }}>{entry.kind === "file" ? formatBrowserFileSize(entry.size_bytes) : "—"}</div>
                          <div style={{ fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>{entry.path}</div>
                        </button>
                      );
                    })
                  )}
                </div>
              </main>
            </div>

            <div style={{ padding: 12, borderTop: "1px solid #374151", display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
              <div style={{ fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>
                Selected: <span style={{ color: "#dbeafe" }}>{folderBrowsePath || "none"}</span>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" style={secondaryButtonStyle} onClick={() => setFolderBrowserOpen(false)}>
                  Cancel
                </button>
                <button type="button" style={buttonStyle} onClick={selectCurrentBrowseFolder} disabled={!folderBrowsePath}>
                  Select Current Folder
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {showAddForm && (
        <div style={{ border: "1px solid #3f3f46", borderRadius: 8, background: "#18181b", padding: 12, marginBottom: 12, display: "grid", gap: 10 }}>
          <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: "8px 10px", alignItems: "center" }}>
            <label style={{ fontSize: 13, color: "#cbd5e1" }}>Repository name</label>
            <input value={name} onChange={(event) => setName(event.target.value)} style={inputStyle} />

            <label style={{ fontSize: 13, color: "#cbd5e1" }}>Root folder path</label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8 }}>
              <input
                value={rootPath}
                onChange={(event) => setRootPath(event.target.value)}
                placeholder="/path/to/source/folder"
                style={inputStyle}
              />
              <button
                type="button"
                style={utilityButtonStyle("browse-folder")}
                onClick={() => {
                  blinkUtilityButton("browse-folder");
                  openFolderBrowser();
                }}
              >
                Browse...
              </button>
            </div>

            <label style={{ fontSize: 13, color: "#cbd5e1" }}>Intake mode</label>
            <select
              value={intakeMode}
              onChange={(event) => {
                const nextMode = event.target.value as IntakeMode;
                setIntakeMode(nextMode);
                if (nextMode === "3d") {
                  setName((current) => current === "2D Source Repository" || !current.trim() ? "3D Source Repository" : current);
                  setSourceStructureType("multi_version_3d_delivery");
                } else {
                  setName((current) => current === "3D Source Repository" || !current.trim() ? "2D Source Repository" : current);
                  setSourceStructureType("survey_with_line_folders");
                }
              }}
              style={inputStyle}
            >
              <option value="2d">2D SEG-Y intake</option>
              <option value="3d">3D SEG-Y intake</option>
            </select>

            <label style={{ fontSize: 13, color: "#cbd5e1" }}>Source structure</label>
            <select value={sourceStructureType} onChange={(event) => setSourceStructureType(event.target.value as SourceStructureType)} style={inputStyle}>
              {activeSourceStructureOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div style={{ fontSize: 12, color: "#94a3b8" }}>
            Intake mode: {intakeMode === "3d" ? "3D SEG-Y intake" : "2D SEG-Y intake"}. {activeSourceStructureOptions.find((item) => item.value === sourceStructureType)?.description}
          </div>

          <div>
            <button type="button" style={buttonStyle} onClick={addRepository} disabled={loading}>
              Register Repository
            </button>
          </div>
        </div>
      )}

      {repositories.length === 0 && (
        <div style={{ fontSize: 12, color: "#94a3b8" }}>No source repositories registered.</div>
      )}

      {repositories.length > 0 && (
        <div style={{ display: "grid", gap: 10 }}>
          {filteredRepositories.map((repo) => {
            const scanSummary = ((repo as any).scan_summary || {}) as Record<string, any>;
            const packageCount = Number(scanSummary.package_count ?? repo.package_count ?? packageCountByRepo.get(repo.repository_id) ?? 0);
            const primaryLabel = String(scanSummary.primary_label || (is3DRepository(repo) ? "volumes" : "lines"));
            const primaryCount = Number(scanSummary.primary_count ?? (is3DRepository(repo) ? (repo.candidate_count ?? segyCountByRepo.get(repo.repository_id) ?? 0) : (repo.line_count ?? lineCountByRepo.get(repo.repository_id) ?? 0)));
            const segyCount = Number(scanSummary.segy_file_count ?? repo.candidate_count ?? segyCountByRepo.get(repo.repository_id) ?? 0);
            const documentCount = Number(scanSummary.document_count ?? 0);
            const convertedCount = Number(scanSummary.converted_count ?? repo.submitted_count ?? convertedCountByRepo.get(repo.repository_id) ?? 0);

            return (
              <div key={repo.repository_id} style={{ border: "1px solid #3f3f46", borderRadius: 8, background: "#18181b", padding: 12, display: "grid", gridTemplateColumns: "1fr auto", gap: 12, alignItems: "start" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#f8fafc" }}>{repo.name}</div>
                  <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8", overflowWrap: "anywhere" }}>{repo.root_path}</div>

                  <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap", fontSize: 12 }}>
                    <span>Status: {formatRepositoryStatus(repo.status)}</span>
                    <span>Folder: {formatRepositoryFolderSummary(repo)}</span>
                    <span>Last scan: {formatRepositoryLastScanScope(repo, lastScanScopeByRepositoryId)}</span>
                    <span>Packages: {packageCount}</span>
                    <span>{primaryLabel.charAt(0).toUpperCase() + primaryLabel.slice(1)}: {primaryCount}</span>
                    <span>SEG-Y files: {segyCount}</span>
                    <span>Documents: {documentCount}</span>
                    <span>Converted: {convertedCount}</span>
                  </div>

                  <div style={{ marginTop: 5, fontSize: 11, color: "#71717a" }}>
                    Last scanned: {formatDate(repo.last_scanned_at)}
                  </div>

                  {repo.notes && (
                    <div style={{ marginTop: 5, fontSize: 11, color: "#71717a" }}>{repo.notes}</div>
                  )}
                </div>

                <div style={{ display: "grid", gap: 8 }}>
                  <button
                    type="button"
                    style={buttonStyle}
                    onClick={() => scanRepository(repo.repository_id)}
                    disabled={busyRepoId === repo.repository_id}
                  >
                    {busyRepoId === repo.repository_id ? "Scanning..." : "Scan / Rescan"}
                  </button>

                  <button
                    type="button"
                    style={utilityButtonStyle(`browse-source-${repo.repository_id}`)}
                    onClick={() => {
                      void stageRepository(repo);
                    }}
                  >
                    Stage
                  </button>

                  <button
                    type="button"
                    style={dangerButtonStyle}
                    onClick={() => deleteRepository(repo.repository_id, repo.name)}
                    disabled={busyRepoId === repo.repository_id}
                  >
                    Delete Repository
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
