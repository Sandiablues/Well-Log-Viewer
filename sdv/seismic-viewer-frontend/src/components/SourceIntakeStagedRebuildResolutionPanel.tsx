import { useMemo, useState } from "react";
import type { SourceIntakeWorkbenchRow } from "../services/registryService";
import { sourceIntakeCandidateId } from "../services/sourceIntakeWorkbenchV2Session";

type StagedRebuildResolutionPanelProps = {
  row: SourceIntakeWorkbenchRow;
  disabled?: boolean;
  onResolve: (actionName: string, payload?: Record<string, unknown>) => Promise<void> | void;
};

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" ? value as Record<string, any> : {};
}

function text(value: unknown, fallback = "—"): string {
  const result = String(value ?? "").trim();
  return result || fallback;
}

function actionForResolution(row: SourceIntakeWorkbenchRow, resolutionAction: string): Record<string, any> {
  const actions = asRecord((row as any).actions);
  const mapping: Record<string, string> = {
    overwrite_current: "overwrite_staged_rebuild",
    save_as_new: "save_staged_rebuild_as_new",
    discard_staged: "discard_staged_rebuild",
  };
  return asRecord(actions[mapping[resolutionAction] || resolutionAction]);
}

const neutralButton = (enabled: boolean) => ({
  border: `1px solid ${enabled ? "#64748b" : "#334155"}`,
  color: enabled ? "#cbd5e1" : "#64748b",
  background: "transparent",
  borderRadius: 8,
  padding: "7px 10px",
  cursor: enabled ? "pointer" : "not-allowed",
  fontSize: 12,
  fontWeight: 700,
  whiteSpace: "nowrap" as const,
});

export default function SourceIntakeStagedRebuildResolutionPanel({ row, disabled = false, onResolve }: StagedRebuildResolutionPanelProps) {
  const staged = asRecord((row as any).staged_rebuild);
  const current = asRecord(staged.current_managed_output);
  const stagedArtifact = asRecord(staged.staged_artifact);
  const nextAction = asRecord((row as any).next_action || staged.next_action);
  const resolutions = Array.isArray(staged.available_resolutions) ? staged.available_resolutions.filter((item) => item && typeof item === "object") as Record<string, any>[] : [];
  const [saveAsName, setSaveAsName] = useState("");
  const [submittingAction, setSubmittingAction] = useState<string | null>(null);

  const displayName = text((row as any).display_name || (row as any).filename || (row as any).file_name);
  const candidateId = sourceIntakeCandidateId(row);

  const primaryResolutions = useMemo(() => {
    const order = ["overwrite_current", "save_as_new", "discard_staged"];
    return [...resolutions].sort((a, b) => order.indexOf(String(a.action)) - order.indexOf(String(b.action)));
  }, [resolutions]);

  if (!staged || staged.promotion_required !== true) return null;

  const submit = async (resolution: Record<string, any>) => {
    const resolutionAction = String(resolution.action || "");
    const backendAction = actionForResolution(row, resolutionAction);
    const actionName = String({
      overwrite_current: "overwrite_staged_rebuild",
      save_as_new: "save_staged_rebuild_as_new",
      discard_staged: "discard_staged_rebuild",
    }[resolutionAction] || resolutionAction);
    if (!backendAction.enabled || !backendAction.url || disabled || submittingAction) return;

    const payload = asRecord(backendAction.payload || resolution.payload || {});
    if (resolutionAction === "save_as_new") {
      const trimmed = saveAsName.trim();
      if (!trimmed) return;
      payload.display_name = trimmed;
    }

    setSubmittingAction(actionName);
    try {
      await onResolve(actionName, payload);
    } finally {
      setSubmittingAction(null);
    }
  };

  return (
    <div style={{ border: "1px solid #f59e0b", borderRadius: 10, padding: "12px 14px", background: "rgba(245, 158, 11, 0.06)", display: "grid", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ color: "#fde68a", fontWeight: 800, fontSize: 14 }}>{text(staged.label, "Staged Rebuild Ready")}</div>
          <div style={{ color: "#cbd5e1", fontSize: 13, marginTop: 3 }}>{text(staged.detail)}</div>
        </div>
        <div style={{ color: "#94a3b8", fontSize: 12 }}>Candidate: {text(candidateId)}</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
        <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 10 }}>
          <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 4 }}>Current managed output</div>
          <div style={{ color: "#e2e8f0", fontWeight: 700 }}>{current.viewer_ready ? "Viewer Ready" : text(current.state)}</div>
          <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 4 }}>{text(current.display_name || displayName)}</div>
        </div>
        <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 10 }}>
          <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 4 }}>Staged rebuild</div>
          <div style={{ color: "#e2e8f0", fontWeight: 700 }}>{text(stagedArtifact.state, "Ready")}</div>
          <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 4 }}>Job: {text(stagedArtifact.job_id)}</div>
        </div>
        <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 10 }}>
          <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 4 }}>Next action</div>
          <div style={{ color: "#e2e8f0", fontWeight: 700 }}>{text(nextAction.label, "Resolve staged rebuild")}</div>
          <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 4 }}>{text(nextAction.reason)}</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {primaryResolutions.map((resolution) => {
          const actionName = String(resolution.action || "");
          const backendAction = actionForResolution(row, actionName);
          const enabled = !disabled && backendAction.enabled === true && Boolean(backendAction.url) && !submittingAction;
          const requiresName = Boolean(resolution.requires_display_name || backendAction.requires_display_name || actionName === "save_as_new");
          return (
            <div key={actionName} style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              {requiresName && (
                <input
                  value={saveAsName}
                  onChange={(event) => setSaveAsName(event.target.value)}
                  placeholder="New managed output name"
                  disabled={disabled || Boolean(submittingAction)}
                  style={{ minWidth: 220, background: "#0f172a", color: "#e2e8f0", border: "1px solid #475569", borderRadius: 8, padding: "7px 9px", fontSize: 12 }}
                />
              )}
              <button type="button" disabled={!enabled || (requiresName && !saveAsName.trim())} style={neutralButton(enabled && (!requiresName || Boolean(saveAsName.trim())))} onClick={() => void submit(resolution)}>
                {submittingAction === actionName ? "Resolving…" : text(resolution.label || backendAction.label || actionName)}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
