import { useEffect, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
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

const WORKFLOW_STEPS = ["Source & Discover", "Review", "QAQC", "Build", "Managed"];

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

  const [activeWorkbenchRepositoryId, setActiveWorkbenchRepositoryId] = useState(selectedSourceRepositoryId || "");
  const [workbenchRefreshNonce, setWorkbenchRefreshNonce] = useState(0);
  const [stagedWorkbenchPayload, setStagedWorkbenchPayload] = useState<any | null>(null);
  const [sourcePanelCollapsed, setSourcePanelCollapsed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const selectedRepository = String(selectedSourceRepositoryId || "").trim();

    if (selectedRepository) {
      setActiveWorkbenchRepositoryId(selectedRepository);
      setStagedWorkbenchPayload(null);
      setWorkbenchRefreshNonce((value) => value + 1);
      return () => { cancelled = true; };
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
    return () => { cancelled = true; };
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
      name: result.package_name || "Manual SEG-Y Upload",
      display_name: result.package_name || "Manual SEG-Y Upload",
      source_structure_type: "manual_upload_package",
      intended_use: dataManagerTab === "3d" ? "3d_segy_intake" : "2d_segy_intake",
      repository_type: "manual_upload_package",
    });
  }

  return (
    <section className={`source-intake-workflow source-intake-workflow--wsi ${sourcePanelCollapsed ? "is-source-collapsed" : ""}`}>
      <ol className="ssi-workflow-strip" aria-label="Source Intake workflow">
        {WORKFLOW_STEPS.map((step, index) => (
          <li key={step} className={index === 0 ? "is-active" : ""}>
            <span>{index + 1}</span>
            {step}
          </li>
        ))}
      </ol>

      <div className="ssi-workspace-layout">
        {!sourcePanelCollapsed && (
          <aside className="ssi-source-rail mv-panel">
            <div className="ssi-source-rail__header">
              <div>
                <h2 className="mv-type-section-heading">Source &amp; Discover</h2>
                <p className="mv-type-helper">Choose or register a seismic source, scan it, or stage SEG-Y directly.</p>
              </div>
              <button className="mv-button mv-button--compact" type="button" onClick={() => setSourcePanelCollapsed(true)} aria-label="Collapse Source and Discover">
                <ChevronLeft size={16} />
              </button>
            </div>

            <div className="ssi-source-rail__section">
              <SourceRepositoryManager
                activeDataTab={dataManagerTab}
                onRepositoryChanged={onRefreshVolumes}
                onStageRepository={handleStageRepository}
              />
            </div>

            <div className="ssi-source-rail__section ssi-source-rail__upload">
              <SourceIntakeManualUploadDropZone mode={dataManagerTab} onPackageStaged={handleManualUploadPackageStaged} />
            </div>
          </aside>
        )}

        <main className="ssi-workspace-main">
          {sourcePanelCollapsed && (
            <div className="ssi-source-collapsed-bar">
              <button className="mv-button mv-button--compact" type="button" onClick={() => setSourcePanelCollapsed(false)}>
                <ChevronRight size={16} /> Show Source &amp; Discover
              </button>
            </div>
          )}

          <SourceIntakeWorkbenchPanel
            repositoryId={activeWorkbenchRepositoryId || undefined}
            mode={dataManagerTab}
            refreshSignal={workbenchRefreshNonce}
            stagedPayload={stagedWorkbenchPayload}
            onViewIndexedPreview={onViewIndexedPreview}
          />
          {children}
        </main>
      </div>
    </section>
  );
}
