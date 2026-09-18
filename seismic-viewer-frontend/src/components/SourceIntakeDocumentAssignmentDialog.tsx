import { useMemo, useState } from "react";
import type { SourceIntakeWorkbenchRow } from "../services/registryService";

type AssignmentAction = {
  action?: string;
  id?: string;
  value?: string;
  label?: string;
  description?: string;
  scope_type?: string;
  requires_document_ids?: boolean;
  requires_line_ids?: boolean;
};

type AssignmentDocument = {
  document_id?: string;
  id?: string;
  doc_id?: string;
  filename?: string;
  relative_path?: string;
  document_type?: string;
  document_role?: string;
  package_name?: string;
  match_reason?: string;
  match_confidence?: string;
  assignment_state?: string;
  assigned?: boolean;
  assigned_to_current_candidate?: boolean;
  assigned_elsewhere?: boolean;
  non_geophysical?: boolean;
  view_url?: string;
  open_url?: string;
  download_url?: string;
};

type Props = {
  review: any;
  row: SourceIntakeWorkbenchRow;
  mode: "2d" | "3d";
  submitting?: boolean;
  onSubmit: (action: string, documentIds: string[]) => Promise<void>;
  onClose: () => void;
};

function actionId(action: AssignmentAction): string {
  return String(action.action || action.id || action.value || "").trim();
}

function documentId(document: AssignmentDocument): string {
  return String(document.document_id || document.id || document.doc_id || "").trim();
}

function valueOrDash(value: unknown): string {
  const text = String(value ?? "").trim();
  return text || "—";
}

function documentsFromReview(review: any): AssignmentDocument[] {
  const docs = review?.documents || review?.available_documents || [];
  return Array.isArray(docs) ? docs : [];
}

function actionsFromReview(review: any): AssignmentAction[] {
  const actions = review?.assignment_actions || review?.actions || [];
  return Array.isArray(actions) ? actions : [];
}

const shellStyle = {
  padding: 14,
  display: "grid",
  gap: 12,
  maxWidth: 1080,
} as const;

const buttonBase = {
  padding: "7px 11px",
  whiteSpace: "nowrap",
} as const;

function buttonStyle(enabled: boolean, accent = false) {
  return {
    ...buttonBase,
    cursor: enabled ? "pointer" : "not-allowed",
    opacity: enabled ? 1 : 0.65,
  } as const;
}

export default function SourceIntakeDocumentAssignmentDialog({ review, row, mode, submitting = false, onSubmit, onClose }: Props) {
  const documents = useMemo(() => documentsFromReview(review), [review]);
  const actions = useMemo(() => actionsFromReview(review), [review]);
  const defaultAction = actions.find((a) => actionId(a) && actionId(a) !== "clear") || actions[0];
  const [selectedAction, setSelectedAction] = useState<string>(() => actionId(defaultAction || {}));
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<Set<string>>(() => {
    const initiallyAssigned = documents
      .filter((doc) => doc.assigned_to_current_candidate || doc.assigned)
      .map(documentId)
      .filter(Boolean);
    return new Set(initiallyAssigned);
  });
  const [localError, setLocalError] = useState<string | null>(null);

  const selectedActionObject = actions.find((a) => actionId(a) === selectedAction);
  const requiresDocuments = selectedActionObject?.requires_document_ids !== false && selectedAction !== "clear";
  const candidateName = valueOrDash(row.display_name || row.filename || (row as any).file_name);
  const summary = review?.summary && typeof review.summary === "object" ? review.summary : {};

  const toggleDocument = (id: string) => {
    setSelectedDocumentIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    setSelectedDocumentIds(new Set(documents.map(documentId).filter(Boolean)));
  };

  const clearSelection = () => {
    setSelectedDocumentIds(new Set());
  };

  const handleSubmit = async () => {
    setLocalError(null);
    if (!selectedAction) {
      setLocalError("Choose an assignment action.");
      return;
    }
    const ids = [...selectedDocumentIds];
    if (requiresDocuments && ids.length === 0) {
      setLocalError("Select at least one document for this assignment action.");
      return;
    }
    try {
      await onSubmit(selectedAction, ids);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <section className="mv-dialog-shell" style={shellStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
        <div>
          <div className="mv-dialog-title">Document Assignment</div>
          <div className="mv-dialog-subtitle" style={{ marginTop: 4 }}>{mode.toUpperCase()} · {candidateName}</div>
        </div>
        <button className="mv-button mv-button--compact" type="button" onClick={onClose} disabled={submitting} style={buttonStyle(!submitting)}>Close</button>
      </div>

      <div className="mv-type-meta" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <span>Discovered: {Number(summary.discovered_document_count ?? documents.length)}</span>
        <span>Effective: {Number(summary.effective_document_count ?? 0)}</span>
        <span>Assigned: {Number(summary.assigned_document_count ?? 0)}</span>
        <span>Unassigned: {Number(summary.unassigned_document_count ?? 0)}</span>
        <span>Scope: {valueOrDash(summary.scope_boundary || review?.mode)}</span>
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <label className="mv-type-property-label">Assignment action</label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {actions.map((action) => {
            const id = actionId(action);
            if (!id) return null;
            const active = selectedAction === id;
            return (
              <button className="mv-button mv-button--compact"
                key={id}
                type="button"
                onClick={() => setSelectedAction(id)}
                disabled={submitting}
                style={{
                  border: `1px solid ${active ? "#38bdf8" : "#475569"}`,
                  color: active ? "#7dd3fc" : "#cbd5e1",
                  background: "transparent",
                  borderRadius: 999,
                  padding: "6px 10px",
                  cursor: submitting ? "not-allowed" : "pointer",
                  fontSize: 12,
                  fontWeight: 700,
                }}
                title={action.description || id}
              >
                {action.label || id}
              </button>
            );
          })}
        </div>
        {selectedActionObject?.description && (
          <div className="mv-type-helper">{selectedActionObject.description}</div>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div className="mv-type-section-heading">Documents</div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="mv-button mv-button--compact" type="button" onClick={selectAll} disabled={submitting || documents.length === 0} style={buttonStyle(!submitting && documents.length > 0)}>Select all</button>
          <button className="mv-button mv-button--compact" type="button" onClick={clearSelection} disabled={submitting || selectedDocumentIds.size === 0} style={buttonStyle(!submitting && selectedDocumentIds.size > 0)}>Clear</button>
        </div>
      </div>

      <div style={{ border: "1px solid #1e3a8a", borderRadius: 8, overflow: "hidden" }}>
        {documents.length === 0 ? (
          <div className="mv-type-helper" style={{ padding: 12 }}>No documents are available for this candidate.</div>
        ) : documents.map((document) => {
          const id = documentId(document);
          const checked = selectedDocumentIds.has(id);
          return (
            <label key={id || document.filename} style={{ display: "grid", gridTemplateColumns: "28px 1fr auto", gap: 10, alignItems: "start", padding: "10px 12px", borderTop: "1px solid #1e293b", cursor: submitting ? "not-allowed" : "pointer" }}>
              <input type="checkbox" checked={checked} disabled={submitting || !id} onChange={() => id && toggleDocument(id)} />
              <div>
                <div className="mv-type-property-value">{valueOrDash(document.filename)}</div>
                <div className="mv-type-meta" style={{ marginTop: 3 }}>
                  {valueOrDash(document.document_role || document.document_type)} · {valueOrDash(document.package_name)} · {valueOrDash(document.assignment_state || (document.assigned ? "assigned" : "unassigned"))}
                </div>
                {document.match_reason && <div className="mv-type-helper" style={{ marginTop: 3 }}>{document.match_reason}</div>}
              </div>
              <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
                {(document.open_url || document.view_url) && <a href={document.open_url || document.view_url} target="_blank" rel="noreferrer" style={{ color: "#7dd3fc" }}>Open</a>}
                {document.download_url && <a href={document.download_url} target="_blank" rel="noreferrer" style={{ color: "#7dd3fc" }}>Download</a>}
              </div>
            </label>
          );
        })}
      </div>

      {localError && <div style={{ border: "1px solid #ef4444", borderRadius: 8, padding: "8px 10px", color: "#fecaca" }}>{localError}</div>}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button className="mv-button mv-button--compact" type="button" onClick={onClose} disabled={submitting} style={buttonStyle(!submitting)}>Cancel</button>
        <button className="mv-button mv-button--compact" type="button" onClick={() => void handleSubmit()} disabled={submitting || !selectedAction || (requiresDocuments && selectedDocumentIds.size === 0)} style={buttonStyle(!submitting && Boolean(selectedAction) && (!requiresDocuments || selectedDocumentIds.size > 0), true)}>
          {submitting ? "Saving…" : "Apply assignment"}
        </button>
      </div>
    </section>
  );
}
