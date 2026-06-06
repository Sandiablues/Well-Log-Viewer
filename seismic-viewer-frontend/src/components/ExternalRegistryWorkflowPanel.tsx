import SourceIntakeWorkbenchPanel from "./SourceIntakeWorkbenchPanel";

type ExternalRegistryWorkflowPanelProps = {
  dataManagerTab: "3d" | "2d";
  externalRegistryCollapsed: boolean;
  externalRegistryMaxWidth: number | string;
  onRefreshVolumes: () => Promise<void> | void;
  selectedSourceRepositoryId: string | null;
};

export default function ExternalRegistryWorkflowPanel({
  dataManagerTab,
  externalRegistryCollapsed,
  externalRegistryMaxWidth,
  selectedSourceRepositoryId,
}: ExternalRegistryWorkflowPanelProps) {
  if (externalRegistryCollapsed) {
    return null;
  }

  return (
    <section className="collapsible-pane external-registry-pane expanded">
      <div className="collapsible-pane-header">
        <div>
          <h3>Selection and Conversion</h3>
          <p>
            Candidate review and conversion readiness now live in the unified Source Intake workbench.
          </p>
        </div>
      </div>

      <div
        className="external-registry-scroll-area"
        style={{
          maxWidth: externalRegistryMaxWidth,
          overflow: "visible",
          minWidth: 0,
        }}
      >
        <SourceIntakeWorkbenchPanel repositoryId={selectedSourceRepositoryId || undefined} />
      </div>
    </section>
  );
}
