import type React from "react";
import SourceIntakeWorkbenchPanel from "./SourceIntakeWorkbenchPanel";

type Props = {
  repositoryId: string;
  onCancel?: () => void;
};

const panelStyle: React.CSSProperties = {
  border: "1px solid #334155",
  borderRadius: 10,
  background: "#0f172a",
  padding: 12,
  marginTop: 16,
  color: "#e5e7eb",
};

const noticeStyle: React.CSSProperties = {
  border: "1px solid #475569",
  borderRadius: 8,
  padding: "8px 10px",
  background: "rgba(15, 23, 42, 0.75)",
  color: "#cbd5e1",
  fontSize: 12,
  marginBottom: 10,
};

const buttonStyle: React.CSSProperties = {
  border: "1px solid #64748b",
  borderRadius: 6,
  background: "transparent",
  color: "#cbd5e1",
  padding: "6px 10px",
  fontSize: 12,
  fontWeight: 650,
  cursor: "pointer",
};

export default function SourceIntakeLoadSheetPanel({ repositoryId, onCancel }: Props) {
  return (
    <section className="source-intake-loadsheet-redirect" style={panelStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 750, color: "#f8fafc" }}>Selection and Conversion</div>
          <div style={{ marginTop: 3, fontSize: 12, color: "#94a3b8" }}>
            The old QAQC Load Sheet / Stage Selection screen has been retired from the active Source Intake workflow.
          </div>
        </div>
        {onCancel && (
          <button type="button" style={buttonStyle} onClick={onCancel}>
            Clear Repository
          </button>
        )}
      </div>

      <div style={noticeStyle}>
        Use this unified workbench for row selection, conversion readiness, build actions, and managed-output status.
      </div>

      <SourceIntakeWorkbenchPanel repositoryId={repositoryId || undefined} />
    </section>
  );
}
