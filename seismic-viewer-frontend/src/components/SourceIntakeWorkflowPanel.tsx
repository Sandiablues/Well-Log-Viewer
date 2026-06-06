import { useEffect, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { fetchSourceIntakeSession, type SourceIntakeStageWorkbenchResult } from "../services/sourceIntakeWorkbenchV2Service";
import SourceRepositoryManager from "./SourceRepositoryManager";
import SourceIntakeManualUploadDropZone from "./SourceIntakeManualUploadDropZone";
import SourceIntakeWorkbenchPanel from "./SourceIntakeWorkbenchPanel";

type SourceIntakeWorkflowPanelProps = {
  dataManagerTab: "3d" | "2d";
  selectedSourceRepositoryId: string;
  onRefreshVolumes: () => Promise<void>;
  onBrowseRepository: (repositoryId: string, repository?: any) => void;
  externalRegistryCollapsed: boolean;
  externalRegistryMaxWidth: number | string;
  onViewIndexedPreview?: (viewerSource: any) => void;
  children?: ReactNode;
};

type CollapsibleSectionProps = {
  title: string;
  description: string;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
};

function CollapsibleSourceIntakeSection({
  title,
  description,
  collapsed,
  onToggle,
  children,
}: CollapsibleSectionProps) {
  return (
    <section
      style={{
        border: "1px solid #334155",
        background: "#0f172a",
        borderRadius: 10,
        padding: 12,
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
          border: "1px solid #475569",
          background: "transparent",
          color: "#e5e7eb",
          borderRadius: 8,
          padding: "9px 10px",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span>
          <span style={{ display: "block", fontSize: 15, fontWeight: 750, color: "#f8fafc" }}>{title}</span>
          <span style={{ display: "block", fontSize: 12, color: "#94a3b8", marginTop: 3, lineHeight: 1.4 }}>
            {description}
          </span>
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", color: "#cbd5e1", paddingTop: 2 }}>
          {collapsed ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
        </span>
      </button>

      {!collapsed && <div style={{ marginTop: 12 }}>{children}</div>}
    </section>
  );
}

export default function SourceIntakeWorkflowPanel({
  dataManagerTab,
  selectedSourceRepositoryId,
  onRefreshVolumes,
  onBrowseRepository,
  externalRegistryCollapsed,
  externalRegistryMaxWidth,
  onViewIndexedPreview,
  children,
}: SourceIntakeWorkflowPanelProps) {
  void externalRegistryCollapsed;
  void externalRegistryMaxWidth;

  const sourceModeLabel = dataManagerTab === "3d" ? "3D" : "2D";
  const [activeWorkbenchRepositoryId, setActiveWorkbenchRepositoryId] = useState(selectedSourceRepositoryId || "");
  const [workbenchRefreshNonce, setWorkbenchRefreshNonce] = useState(0);
  const [stagedWorkbenchPayload, setStagedWorkbenchPayload] = useState<any | null>(null);
  const [sourceRepositoryCollapsed, setSourceRepositoryCollapsed] = useState(true);
  const [manualUploadCollapsed, setManualUploadCollapsed] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const selectedRepository = String(selectedSourceRepositoryId || "").trim();

    if (selectedRepository) {
      setActiveWorkbenchRepositoryId(selectedRepository);
      setStagedWorkbenchPayload(null);
      setWorkbenchRefreshNonce((value) => value + 1);
      return () => {
        cancelled = true;
      };
    }

    setActiveWorkbenchRepositoryId("");
    setStagedWorkbenchPayload(null);

    async function restoreSession() {
      try {
        const session = await fetchSourceIntakeSession(dataManagerTab);
        if (cancelled) return;

        const sessionMode = String(session?.mode || "").toLowerCase();
        if (sessionMode && sessionMode !== dataManagerTab) return;

        const activeRepositoryId = String(session?.active_repository_id || session?.repository?.repository_id || "").trim();
        const workbench = session?.workbench || null;

        if (!activeRepositoryId || !workbench) {
          setWorkbenchRefreshNonce((value) => value + 1);
          return;
        }

        setActiveWorkbenchRepositoryId(activeRepositoryId);
        setStagedWorkbenchPayload(workbench);
        setWorkbenchRefreshNonce((value) => value + 1);
      } catch (err) {
        if (cancelled) return;
        console.warn("Restore Source Intake session failed", err);
        setWorkbenchRefreshNonce((value) => value + 1);
      }
    }

    void restoreSession();

    return () => {
      cancelled = true;
    };
  }, [selectedSourceRepositoryId, dataManagerTab]);

  function handleStageRepository(repositoryId: string, repository: any, stageResult: SourceIntakeStageWorkbenchResult) {
    const nextRepositoryId = String(repositoryId || "").trim();
    setActiveWorkbenchRepositoryId(nextRepositoryId);
    setStagedWorkbenchPayload(stageResult?.workbench || null);
    setWorkbenchRefreshNonce((value) => value + 1);
    onBrowseRepository(nextRepositoryId, repository);
  }

  function handleManualUploadPackageStaged(result: any) {
    const repositoryId = String(result?.repository_id || "").trim();
    if (!repositoryId) return;

    setActiveWorkbenchRepositoryId(repositoryId);
    setStagedWorkbenchPayload(null);
    setWorkbenchRefreshNonce((value) => value + 1);
    onBrowseRepository(repositoryId, {
      repository_id: repositoryId,
      name: result.package_name || "Manual Upload Package",
      display_name: result.package_name || "Manual Upload Package",
      source_structure_type: "manual_upload_package",
      intended_use: dataManagerTab === "3d" ? "3d_segy_intake" : "2d_segy_intake",
      repository_type: "manual_upload_package",
    });
  }

  return (
    <section className="source-intake-workflow" style={{ display: "grid", gap: 16 }}>
      <div
        style={{
          border: "1px solid #334155",
          background: "#111827",
          borderRadius: 10,
          padding: 14,
          color: "#e5e7eb",
        }}
      >
        <div style={{ fontSize: 18, fontWeight: 750, color: "#f8fafc", marginBottom: 4 }}>
          Source Intake
        </div>
        <div style={{ fontSize: 13, color: "#94a3b8", lineHeight: 1.45 }}>
          Manage {sourceModeLabel} source repository selection, manual upload staging, conversion readiness, and managed-output status.
        </div>
      </div>

      <CollapsibleSourceIntakeSection
        title="1. Source Repository Selection"
        description="Register source folders, scan or rescan them, and select the active repository for the intake workbench."
        collapsed={sourceRepositoryCollapsed}
        onToggle={() => setSourceRepositoryCollapsed((value) => !value)}
      >
        <SourceRepositoryManager
          activeDataTab={dataManagerTab}
          onRepositoryChanged={onRefreshVolumes}
          onStageRepository={handleStageRepository}
        />
      </CollapsibleSourceIntakeSection>

      <CollapsibleSourceIntakeSection
        title="2. Manual Upload / Drop Zone"
        description="Upload one or more SEG-Y files with supporting documents, then stage them for Source Intake review without automatic conversion."
        collapsed={manualUploadCollapsed}
        onToggle={() => setManualUploadCollapsed((value) => !value)}
      >
        <SourceIntakeManualUploadDropZone
          mode={dataManagerTab}
          onPackageStaged={handleManualUploadPackageStaged}
        />
      </CollapsibleSourceIntakeSection>

      <section
        style={{
          border: "1px solid #334155",
          background: "#0f172a",
          borderRadius: 10,
          padding: 12,
        }}
      >
        <SourceIntakeWorkbenchPanel
          repositoryId={activeWorkbenchRepositoryId || undefined}
          mode={dataManagerTab}
          refreshSignal={workbenchRefreshNonce}
          stagedPayload={stagedWorkbenchPayload}
          onViewIndexedPreview={onViewIndexedPreview}
        />
      </section>

      {children}
    </section>
  );
}
