import { useCallback, useEffect, useMemo, useState } from 'react';

type CompletionKnowledgeRecord = {
  instructionId: string;
  recordType: 'component' | 'standard';
  componentKey: string;
  componentLabel: string;
  canonicalId: string;
  category: 'Completions' | 'Standards';
  standardStatus: string;
  status: 'candidate' | 'approved' | 'rejected' | 'deprecated';
  productionEligible: boolean;
  version: string;
  description: string;
  mustDo: string;
  mustNotDo: string;
  evidenceCount: number;
  evidence: Array<{
    sourceType: string;
    title: string;
    documentId: string;
    section: string;
  }>;
  governanceHistory?: Array<{
    action: string;
    actor: string;
    timestamp: string;
    previousStatus?: string | null;
    newStatus?: string | null;
    reason?: string | null;
  }>;
  parentInstructionId?: string | null;
};

type CompletionEvidenceDraft = CompletionKnowledgeRecord['evidence'][number];

type CompletionCandidateForm = {
  recordType: 'component' | 'standard';
  componentKey: string;
  componentLabel: string;
  canonicalId: string;
  category: 'Completions' | 'Standards';
  version: string;
  description: string;
  mustDo: string;
  mustNotDo: string;
  changeReason: string;
  evidence: CompletionEvidenceDraft[];
};

type GovernanceAction = 'approve' | 'reject' | 'deprecate';

type CompletionGlyphKey =
  | 'tubing'
  | 'perforations'
  | 'packer'
  | 'safety_valve'
  | 'bridge_plug'
  | 'retainer'
  | 'cement_barrier'
  | 'casing'
  | 'liner'
  | 'screen'
  | 'sliding_sleeve'
  | 'downhole_valve'
  | 'gas_lift'
  | 'icd_aicd'
  | 'open_hole';

const COMPLETION_KR_BACKEND_ORIGIN =
  typeof window === 'undefined'
    ? 'http://127.0.0.1:8001'
    : `${window.location.protocol}//${window.location.hostname}:8001`;
const COMPLETION_KR_BASE = `${COMPLETION_KR_BACKEND_ORIGIN}/api/wlv/knowledge/managed/completions`;
const COMPLETION_KR_ENDPOINT = `${COMPLETION_KR_BASE}/catalogue`;

const EMPTY_EVIDENCE: CompletionEvidenceDraft = {
  sourceType: '',
  title: '',
  documentId: '',
  section: '',
};

const EMPTY_CANDIDATE: CompletionCandidateForm = {
  recordType: 'component',
  componentKey: '',
  componentLabel: '',
  canonicalId: 'completion.',
  category: 'Completions',
  version: 'v1.0',
  description: '',
  mustDo: '',
  mustNotDo: '',
  changeReason: '',
  evidence: [],
};

function recordToCandidateForm(record: CompletionKnowledgeRecord): CompletionCandidateForm {
  return {
    recordType: record.recordType,
    componentKey: record.componentKey,
    componentLabel: record.componentLabel,
    canonicalId: record.canonicalId,
    category: record.category,
    version: record.version,
    description: record.description,
    mustDo: record.mustDo,
    mustNotDo: record.mustNotDo,
    changeReason: '',
    evidence: record.evidence.map((item) => ({ ...item })),
  };
}

async function krJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `KR request failed: ${response.status}`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep status-based message.
    }
    throw new Error(detail);
  }
  return await response.json() as T;
}

const PREVIEW_GLYPHS: Array<{ key: CompletionGlyphKey; label: string }> = [
  { key: 'tubing', label: 'Tubing' },
  { key: 'casing', label: 'Casing' },
  { key: 'liner', label: 'Liner' },
  { key: 'screen', label: 'Screen' },
  { key: 'perforations', label: 'Perforations' },
  { key: 'packer', label: 'Packer' },
  { key: 'safety_valve', label: 'Safety Valve' },
  { key: 'downhole_valve', label: 'Downhole Valve' },
  { key: 'sliding_sleeve', label: 'Sliding Sleeve' },
  { key: 'gas_lift', label: 'Gas Lift' },
  { key: 'icd_aicd', label: 'ICD / AICD' },
  { key: 'bridge_plug', label: 'Bridge Plug' },
  { key: 'retainer', label: 'Retainer' },
  { key: 'cement_barrier', label: 'Cement Barrier' },
  { key: 'open_hole', label: 'Open Hole' },
];

function CompletionGlyph({ kind }: { kind: CompletionGlyphKey }) {
  return (
    <div className={`wlv-kr-completion-glyph ${kind}`} aria-hidden="true">
      <span className="well-axis" />
      <span className="metal-body" />
      <span className="glyph-detail detail-a" />
      <span className="glyph-detail detail-b" />
      <span className="glyph-detail detail-c" />
    </div>
  );
}

function truthBadge() {
  return <span className="wlv-kr-completion-truth" title="Approved live truth">✓</span>;
}

export function KrCompletionsWorkbench() {
  const [records, setRecords] = useState<CompletionKnowledgeRecord[]>([]);
  const [search, setSearch] = useState('');
  const [catalogueView, setCatalogueView] = useState<'all' | 'components' | 'standards'>('all');
  const [truthStatus, setTruthStatus] = useState<'approved' | 'candidate' | 'deprecated' | 'rejected' | 'all'>('approved');
  const [componentFamily, setComponentFamily] = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editorMode, setEditorMode] = useState<'add' | 'edit' | null>(null);
  const [candidateForm, setCandidateForm] = useState<CompletionCandidateForm>(EMPTY_CANDIDATE);
  const [governanceAction, setGovernanceAction] = useState<GovernanceAction | null>(null);
  const [governanceReason, setGovernanceReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const loadCatalogue = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(COMPLETION_KR_ENDPOINT, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(`Completion KR request failed: ${response.status}`);
      }
      const payload = await response.json() as { records?: CompletionKnowledgeRecord[] };
      const next = Array.isArray(payload.records) ? payload.records : [];
      setRecords(next);
      setLoadError(null);
      setSelectedId((current) => {
        if (current && next.some((record) => record.instructionId === current)) return current;
        return next[0]?.instructionId ?? null;
      });
    } catch (error) {
      setRecords([]);
      setLoadError(error instanceof Error ? error.message : 'Completion KR request failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCatalogue();
  }, [loadCatalogue]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return records.filter((record) => {
      if (catalogueView === 'components' && record.recordType !== 'component') return false;
      if (catalogueView === 'standards' && record.recordType !== 'standard') return false;
      if (truthStatus !== 'all' && record.status !== truthStatus) return false;
      if (componentFamily !== 'all' && record.componentKey !== componentFamily) return false;
      if (!needle) return true;
      return [
        record.componentLabel,
        record.canonicalId,
        record.description,
        record.mustDo,
        record.mustNotDo,
      ].some((value) => value.toLowerCase().includes(needle));
    });
  }, [catalogueView, componentFamily, records, search, truthStatus]);

  const selected = filtered.find((record) => record.instructionId === selectedId)
    ?? records.find((record) => record.instructionId === selectedId)
    ?? filtered[0]
    ?? records[0]
    ?? null;

  const approvedCount = records.filter((record) => record.status === 'approved').length;
  const productionCount = records.filter((record) => record.productionEligible).length;
  const evidenceTotal = records.reduce((sum, record) => sum + record.evidenceCount, 0);

  const clearFilters = () => {
    setSearch('');
    setCatalogueView('all');
    setTruthStatus('approved');
    setComponentFamily('all');
  };

  const selectPreview = (key: CompletionGlyphKey) => {
    const record = records.find((item) => item.componentKey === key && item.status === 'approved')
      ?? records.find((item) => item.componentKey === key);
    setComponentFamily(key);
    if (record) setSelectedId(record.instructionId);
  };

  const openAdd = () => {
    setCandidateForm({ ...EMPTY_CANDIDATE, evidence: [] });
    setEditorMode('add');
    setLoadError(null);
    setStatusMessage(null);
  };

  const openEdit = () => {
    if (!selected || !['approved', 'deprecated'].includes(selected.status)) return;
    setCandidateForm(recordToCandidateForm(selected));
    setEditorMode('edit');
    setLoadError(null);
    setStatusMessage(null);
  };

  const updateEvidence = (index: number, patch: Partial<CompletionEvidenceDraft>) => {
    setCandidateForm((current) => ({
      ...current,
      evidence: current.evidence.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item),
    }));
  };

  const submitCandidate = async () => {
    if (saving) return;
    if (!candidateForm.componentKey.trim() || !candidateForm.componentLabel.trim() || !candidateForm.canonicalId.trim()) {
      setLoadError('Component key, label and canonical ID are required.');
      return;
    }
    if (!candidateForm.description.trim() || !candidateForm.mustDo.trim() || !candidateForm.mustNotDo.trim()) {
      setLoadError('Description, Application MUST and Application MUST NOT are required.');
      return;
    }
    const evidence = candidateForm.evidence
      .map((item) => ({
        sourceType: item.sourceType.trim(),
        title: item.title.trim(),
        documentId: item.documentId.trim(),
        section: item.section.trim(),
      }))
      .filter((item) => item.sourceType && item.title && item.documentId && item.section);

    setSaving(true);
    setLoadError(null);
    setStatusMessage(null);
    try {
      let created: CompletionKnowledgeRecord;
      if (editorMode === 'edit' && selected) {
        created = await krJson<CompletionKnowledgeRecord>(
          `${COMPLETION_KR_BASE}/records/${encodeURIComponent(selected.instructionId)}/candidate`,
          {
            method: 'POST',
            body: JSON.stringify({
              actor: 'kr-manager',
              changeReason: candidateForm.changeReason.trim() || 'Edited as candidate in KR Manager',
              updates: {
                recordType: candidateForm.recordType,
                componentKey: candidateForm.componentKey.trim(),
                componentLabel: candidateForm.componentLabel.trim(),
                canonicalId: candidateForm.canonicalId.trim(),
                category: candidateForm.category,
                description: candidateForm.description.trim(),
                mustDo: candidateForm.mustDo.trim(),
                mustNotDo: candidateForm.mustNotDo.trim(),
                evidence,
              },
            }),
          },
        );
      } else {
        created = await krJson<CompletionKnowledgeRecord>(
          `${COMPLETION_KR_BASE}/records?actor=kr-manager`,
          {
            method: 'POST',
            body: JSON.stringify({
              recordType: candidateForm.recordType,
              componentKey: candidateForm.componentKey.trim(),
              componentLabel: candidateForm.componentLabel.trim(),
              canonicalId: candidateForm.canonicalId.trim(),
              category: candidateForm.category,
              version: candidateForm.version.trim() || 'v1.0',
              description: candidateForm.description.trim(),
              mustDo: candidateForm.mustDo.trim(),
              mustNotDo: candidateForm.mustNotDo.trim(),
              evidence,
              changeReason: candidateForm.changeReason.trim() || 'New completion KR candidate',
            }),
          },
        );
      }
      setEditorMode(null);
      setTruthStatus('candidate');
      await loadCatalogue();
      setSelectedId(created.instructionId);
      setStatusMessage(`${created.componentLabel} saved as candidate ${created.version}.`);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Candidate save failed');
    } finally {
      setSaving(false);
    }
  };

  const openGovernance = (action: GovernanceAction) => {
    if (!selected) return;
    setGovernanceAction(action);
    setGovernanceReason('');
    setLoadError(null);
    setStatusMessage(null);
  };

  const submitGovernance = async () => {
    if (!selected || !governanceAction || saving) return;
    if ((governanceAction === 'reject' || governanceAction === 'deprecate') && !governanceReason.trim()) {
      setLoadError(`${governanceAction === 'reject' ? 'Reject' : 'Deprecate'} requires a reason.`);
      return;
    }
    setSaving(true);
    setLoadError(null);
    try {
      const updated = await krJson<CompletionKnowledgeRecord>(
        `${COMPLETION_KR_BASE}/records/${encodeURIComponent(selected.instructionId)}/${governanceAction}`,
        {
          method: 'POST',
          body: JSON.stringify({
            actor: 'kr-manager',
            reason: governanceReason.trim() || undefined,
          }),
        },
      );
      setGovernanceAction(null);
      setGovernanceReason('');
      setTruthStatus(updated.status === 'approved' ? 'approved' : updated.status);
      await loadCatalogue();
      setSelectedId(updated.instructionId);
      setStatusMessage(`${updated.componentLabel}: ${updated.standardStatus}.`);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : `Governance action failed`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="wlv-kr-workbench wlv-kr-completions-workbench" aria-label="Knowledge Repository completions manager">
      <style>{`
        .wlv-kr-completions-workbench {
          color: #e7ebf1;
        }

        .wlv-kr-completions-workbench > .wlv-kr-header {
          padding: 12px 16px;
          gap: 12px;
        }

        .wlv-kr-completions-workbench > .wlv-kr-header h1 {
          margin: 2px 0 2px;
          font-size: 20px;
          line-height: 1.15;
        }

        .wlv-kr-completions-workbench > .wlv-kr-header p {
          margin: 0;
          font-size: 11px;
          line-height: 1.3;
        }

        .wlv-kr-completions-workbench > .wlv-kr-header .wlv-page-kicker {
          font-size: 9px;
          letter-spacing: 0.12em;
        }

        .wlv-kr-completions-workbench > .wlv-kr-header .wlv-kr-header-actions {
          gap: 6px;
        }

        .wlv-kr-completions-workbench > .wlv-kr-header .wlv-kr-header-actions button {
          min-height: 30px;
          padding: 6px 10px;
          border-radius: 4px;
          font-size: 12px;
          line-height: 1.1;
          background: #101216 !important;
          color: #ffffff !important;
          border: 1px solid #454b55 !important;
          box-shadow: none !important;
          font-weight: 500;
        }

        .wlv-kr-completions-workbench > .wlv-kr-header .wlv-kr-header-actions button:disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }

        .wlv-kr-completions-workbench > .wlv-kr-summary-grid {
          gap: 8px;
          margin-block: 8px;
        }

        .wlv-kr-completions-workbench > .wlv-kr-summary-grid .wlv-kr-count-card {
          min-height: 54px;
          padding: 8px 12px;
          border-radius: 10px;
        }

        .wlv-kr-completions-workbench > .wlv-kr-summary-grid .wlv-kr-count-card strong {
          font-size: 9px;
          letter-spacing: 0.1em;
        }

        .wlv-kr-completions-workbench > .wlv-kr-summary-grid .wlv-kr-count-card span {
          margin-top: 2px;
          font-size: 18px;
          line-height: 1.1;
        }

        .wlv-kr-completions-workbench > .wlv-kr-controls {
          gap: 8px;
          padding: 8px 12px;
          grid-template-columns: minmax(240px, 1.5fr) minmax(170px, .85fr) minmax(170px, .85fr) minmax(170px, .85fr);
        }

        .wlv-kr-completions-workbench > .wlv-kr-controls label {
          gap: 4px;
          font-size: 9px;
          letter-spacing: 0.08em;
        }

        .wlv-kr-completions-workbench > .wlv-kr-controls input,
        .wlv-kr-completions-workbench > .wlv-kr-controls select {
          min-height: 30px;
          padding: 4px 9px;
          font-size: 12px;
        }

        .wlv-kr-completion-preview {
          margin: 8px 0;
          padding: 9px 12px 10px;
          border: 1px solid #293244;
          border-radius: 10px;
          background:
            radial-gradient(circle at 50% -20%, rgba(52, 103, 175, .14), transparent 42%),
            #0a1120;
        }

        .wlv-kr-completion-preview > h2 {
          margin: 0 0 8px;
          color: #66c7f1;
          font-size: 9px;
          line-height: 1;
          letter-spacing: .12em;
          text-transform: uppercase;
        }

        .wlv-kr-completion-preview-grid {
          display: grid;
          grid-template-columns: repeat(8, minmax(92px, 1fr));
          gap: 7px;
        }

        .wlv-kr-completion-preview button {
          min-width: 0;
          padding: 0;
          border: 1px solid #33415a;
          border-radius: 6px;
          overflow: hidden;
          background: #09101c;
          color: #e5e9ef;
          text-align: left;
          cursor: pointer;
        }

        .wlv-kr-completion-preview button:hover,
        .wlv-kr-completion-preview button.active {
          border-color: #5f8fc0;
          box-shadow: inset 0 0 0 1px rgba(95, 143, 192, .28);
          background: #0c1525;
        }

        .wlv-kr-completion-preview button > span {
          display: block;
          padding: 5px 7px 6px;
          border-top: 1px solid #293244;
          color: #dce3ec;
          font-size: 10.5px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .wlv-kr-completion-glyph {
          position: relative;
          height: 86px;
          overflow: hidden;
          background:
            radial-gradient(ellipse at 50% 45%, rgba(186, 208, 230, .10), transparent 46%),
            linear-gradient(180deg, #101a2a, #080e18);
        }

        .wlv-kr-completion-glyph .well-axis {
          position: absolute;
          left: 50%;
          top: 7px;
          bottom: 7px;
          width: 2px;
          transform: translateX(-50%);
          background: linear-gradient(90deg, #5c6772, #d8e0e7 48%, #66717d);
          box-shadow: 0 0 6px rgba(188, 211, 228, .24);
        }

        .wlv-kr-completion-glyph .metal-body {
          position: absolute;
          left: 50%;
          top: 8px;
          bottom: 8px;
          width: 54px;
          transform: translateX(-50%);
          border: 1px solid #59636d;
          border-radius: 3px;
          background:
            linear-gradient(90deg,
              #242a2f 0%,
              #68717a 12%,
              #dfe4e7 33%,
              #858d94 49%,
              #edf0f2 63%,
              #5a6269 84%,
              #252b30 100%);
          box-shadow:
            inset 9px 0 11px rgba(0,0,0,.36),
            inset -8px 0 10px rgba(0,0,0,.42),
            0 5px 14px rgba(0,0,0,.38);
          opacity: .96;
        }

        .wlv-kr-completion-glyph .glyph-detail {
          position: absolute;
          display: block;
          pointer-events: none;
        }

        .wlv-kr-completion-glyph.tubing .metal-body {
          width: 36px;
        }

        .wlv-kr-completion-glyph.perforations .metal-body {
          width: 34px;
        }
        .wlv-kr-completion-glyph.perforations .detail-a,
        .wlv-kr-completion-glyph.perforations .detail-b {
          top: 18px;
          bottom: 18px;
          width: 32px;
          background:
            repeating-linear-gradient(135deg, transparent 0 9px, #ffb15c 9px 12px, transparent 12px 18px);
          filter: drop-shadow(0 0 4px rgba(255, 158, 62, .6));
        }
        .wlv-kr-completion-glyph.perforations .detail-a { right: calc(50% + 17px); }
        .wlv-kr-completion-glyph.perforations .detail-b {
          left: calc(50% + 17px);
          transform: scaleX(-1);
        }

        .wlv-kr-completion-glyph.packer .detail-a {
          left: 50%;
          top: 27px;
          width: 70px;
          height: 30px;
          transform: translateX(-50%);
          border: 3px solid #30363c;
          border-radius: 9px;
          background:
            linear-gradient(45deg, transparent 43%, #171b1e 44% 56%, transparent 57%),
            linear-gradient(-45deg, transparent 43%, #171b1e 44% 56%, transparent 57%),
            linear-gradient(180deg, #4b5055, #15191c 42%, #50565b);
          box-shadow: inset 0 0 9px #050708, 0 3px 9px rgba(0,0,0,.55);
        }

        .wlv-kr-completion-glyph.safety_valve .detail-a {
          left: 50%;
          top: 25px;
          width: 54px;
          height: 36px;
          transform: translateX(-50%);
          border: 2px solid #7e8589;
          border-radius: 5px;
          background: linear-gradient(90deg, #33393e, #c9a666 45%, #84652e 55%, #363c41);
          box-shadow: inset 0 0 8px #111, 0 4px 10px rgba(0,0,0,.46);
        }
        .wlv-kr-completion-glyph.safety_valve .detail-b {
          left: 50%;
          top: 34px;
          width: 18px;
          height: 18px;
          transform: translateX(-50%) rotate(45deg);
          border: 2px solid #edd193;
          background: #77541e;
        }

        .wlv-kr-completion-glyph.bridge_plug .detail-a,
        .wlv-kr-completion-glyph.retainer .detail-a {
          left: 50%;
          top: 25px;
          width: 66px;
          height: 34px;
          transform: translateX(-50%);
          border: 2px solid #484f55;
          border-radius: 7px;
          background:
            linear-gradient(45deg, transparent 43%, #24292d 44% 56%, transparent 57%),
            linear-gradient(-45deg, transparent 43%, #24292d 44% 56%, transparent 57%),
            linear-gradient(180deg, #70777d, #272c31 48%, #687077);
          box-shadow: inset 0 0 10px rgba(0,0,0,.75), 0 4px 10px rgba(0,0,0,.5);
        }
        .wlv-kr-completion-glyph.retainer .detail-b {
          left: 50%;
          top: 17px;
          width: 42px;
          height: 50px;
          transform: translateX(-50%);
          border-left: 4px double #c1c8cd;
          border-right: 4px double #697078;
        }

        .wlv-kr-completion-glyph.cement_barrier .metal-body {
          width: 60px;
          border-color: #747a7f;
          background:
            radial-gradient(circle at 23% 17%, #d6d2c8 0 2px, transparent 3px),
            radial-gradient(circle at 70% 37%, #97958e 0 2px, transparent 3px),
            radial-gradient(circle at 40% 73%, #b5b1a8 0 3px, transparent 4px),
            radial-gradient(circle at 77% 82%, #77776f 0 2px, transparent 3px),
            linear-gradient(90deg, #454846, #9b9a91 45%, #676963);
        }

        .wlv-kr-completion-glyph.casing .metal-body {
          width: 68px;
          background:
            linear-gradient(90deg, #1d2328 0 8%, #7f8a92 16%, #e0e6ea 30%, #59636b 45%, #d8dee2 63%, #737e86 82%, #1d2328 92% 100%);
        }

        .wlv-kr-completion-glyph.liner .metal-body {
          width: 58px;
          background:
            linear-gradient(90deg, #22292e, #aeb7bd 19%, #e0e4e7 33%, #636c73 50%, #d6dce0 68%, #7b858d 84%, #252c31);
        }
        .wlv-kr-completion-glyph.liner .detail-a {
          left: 50%;
          top: 10px;
          bottom: 10px;
          width: 46px;
          transform: translateX(-50%);
          border-left: 1px solid rgba(22,26,30,.8);
          border-right: 1px solid rgba(22,26,30,.8);
          box-shadow: inset 0 0 7px rgba(0,0,0,.35);
        }

        .wlv-kr-completion-glyph.screen .metal-body {
          width: 54px;
          background:
            repeating-linear-gradient(0deg, rgba(18,21,24,.94) 0 2px, transparent 2px 7px),
            linear-gradient(90deg, #252c31, #c5cbd0 34%, #6c747b 54%, #d9dde0 73%, #292f34);
        }
        .wlv-kr-completion-glyph.screen .detail-a {
          left: 50%;
          top: 8px;
          bottom: 8px;
          width: 38px;
          transform: translateX(-50%);
          background: repeating-linear-gradient(90deg, transparent 0 5px, rgba(17,20,22,.72) 5px 7px);
          opacity: .8;
        }

        .wlv-kr-completion-glyph.downhole_valve .detail-a {
          left: 50%;
          top: 28px;
          width: 48px;
          height: 28px;
          transform: translateX(-50%);
          border: 2px solid #8e979e;
          border-radius: 5px;
          background:
            linear-gradient(135deg, transparent 42%, #c9d1d7 43% 49%, transparent 50%),
            linear-gradient(45deg, transparent 42%, #c9d1d7 43% 49%, transparent 50%),
            linear-gradient(180deg, #3e464c, #1f2529 52%, #515a61);
          box-shadow: inset 0 0 8px rgba(0,0,0,.62), 0 4px 10px rgba(0,0,0,.45);
        }

        .wlv-kr-completion-glyph.sliding_sleeve .detail-a {
          left: 50%;
          top: 22px;
          width: 58px;
          height: 40px;
          transform: translateX(-50%);
          border: 2px solid #77828a;
          border-radius: 4px;
          background:
            linear-gradient(90deg, #2b3237 0 20%, #b8c0c5 21% 35%, #40484e 36% 49%, #d6dce0 50% 64%, #2e353a 65% 100%);
          box-shadow: inset 0 0 8px rgba(0,0,0,.5), 0 4px 10px rgba(0,0,0,.42);
        }
        .wlv-kr-completion-glyph.sliding_sleeve .detail-b {
          left: 50%;
          top: 33px;
          width: 72px;
          height: 8px;
          transform: translateX(-50%);
          border-radius: 4px;
          background: linear-gradient(90deg, transparent 0 9%, #d9b661 10% 28%, transparent 29% 71%, #d9b661 72% 90%, transparent 91%);
          filter: drop-shadow(0 0 4px rgba(217,182,97,.32));
        }

        .wlv-kr-completion-glyph.gas_lift .detail-a {
          left: calc(50% + 10px);
          top: 23px;
          width: 42px;
          height: 40px;
          border: 2px solid #7f8a91;
          border-radius: 8px 15px 15px 8px;
          background: linear-gradient(90deg, #3d454a, #c3cbd0 40%, #a68a4e 60%, #4a5156);
          box-shadow: inset 0 0 8px rgba(0,0,0,.46), 0 4px 9px rgba(0,0,0,.48);
        }
        .wlv-kr-completion-glyph.gas_lift .detail-b {
          left: calc(50% + 23px);
          top: 35px;
          width: 12px;
          height: 12px;
          border-radius: 50%;
          background: radial-gradient(circle, #efd99c 0 24%, #7d6027 27% 57%, #1d2327 60%);
        }

        .wlv-kr-completion-glyph.icd_aicd .detail-a {
          left: 50%;
          top: 18px;
          width: 64px;
          height: 48px;
          transform: translateX(-50%);
          border: 2px solid #79848c;
          border-radius: 7px;
          background:
            repeating-linear-gradient(90deg, #363d42 0 7px, #a7b0b6 7px 10px, #252b2f 10px 15px);
          box-shadow: inset 0 0 10px rgba(0,0,0,.55), 0 4px 10px rgba(0,0,0,.48);
        }
        .wlv-kr-completion-glyph.icd_aicd .detail-b {
          left: 50%;
          top: 34px;
          width: 74px;
          height: 10px;
          transform: translateX(-50%);
          border-radius: 5px;
          background: linear-gradient(90deg, transparent, #c89c48 18% 30%, transparent 31% 69%, #c89c48 70% 82%, transparent);
          opacity: .9;
        }

        .wlv-kr-completion-glyph.open_hole .metal-body {
          width: 70px;
          border: 0;
          border-radius: 0;
          background:
            radial-gradient(circle at 25% 22%, #6e6358 0 4px, transparent 5px),
            radial-gradient(circle at 68% 45%, #3c3935 0 7px, transparent 8px),
            radial-gradient(circle at 33% 72%, #8a7864 0 5px, transparent 6px),
            linear-gradient(90deg, #211f1d, #65594c 48%, #2b2925);
          filter: contrast(1.14);
          box-shadow: inset 10px 0 15px rgba(0,0,0,.56), inset -10px 0 15px rgba(0,0,0,.5);
        }
        .wlv-kr-completion-glyph.open_hole .well-axis { opacity: .32; }

        .wlv-kr-completions-workbench .wlv-kr-main-grid {
          grid-template-columns: minmax(0, 1fr) 360px;
        }

        .wlv-kr-completions-workbench .wlv-kr-table th,
        .wlv-kr-completions-workbench .wlv-kr-table td {
          font-size: 10.5px;
        }

        .wlv-kr-completions-workbench .wlv-kr-table td strong {
          display: block;
        }

        .wlv-kr-completion-version {
          display: inline-flex;
          min-width: 42px;
          height: 20px;
          align-items: center;
          justify-content: center;
          border: 1px solid #17795c;
          border-radius: 5px;
          color: #47d9a8;
          background: rgba(17, 109, 80, .12);
          font-size: 10px;
        }

        .wlv-kr-completion-truth {
          display: inline-flex;
          width: 18px;
          height: 18px;
          align-items: center;
          justify-content: center;
          border: 1px solid #31b783;
          border-radius: 50%;
          color: #56e0ad;
          background: rgba(23, 135, 96, .13);
          font-size: 11px;
          font-weight: 800;
        }

        .wlv-kr-completion-rule {
          margin-top: 9px;
          padding: 10px 11px;
          border: 1px solid #235f54;
          border-radius: 8px;
          background: rgba(10, 61, 52, .16);
        }

        .wlv-kr-completion-rule.must-not {
          border-color: #7f5d1a;
          background: rgba(97, 65, 6, .13);
        }

        .wlv-kr-completion-rule strong {
          display: block;
          margin-bottom: 5px;
          color: #4ed3a4;
          font-size: 9px;
          letter-spacing: .12em;
          text-transform: uppercase;
        }

        .wlv-kr-completion-rule.must-not strong {
          color: #e0b14a;
        }

        .wlv-kr-completion-rule p {
          margin: 0;
          color: #dbe1e8;
          font-size: 11px;
          line-height: 1.45;
        }

        .wlv-kr-completion-evidence {
          margin-top: 12px;
        }

        .wlv-kr-completion-evidence > strong {
          color: #98a3b2;
          font-size: 9px;
          letter-spacing: .1em;
          text-transform: uppercase;
        }

        .wlv-kr-completion-evidence-card {
          margin-top: 7px;
          padding: 9px 10px;
          border: 1px solid #2f3947;
          border-radius: 7px;
          background: #0b111c;
        }

        .wlv-kr-completion-evidence-card span,
        .wlv-kr-completion-evidence-card em {
          display: block;
          color: #8f9aaa;
          font-size: 9.5px;
          font-style: normal;
        }

        .wlv-kr-completion-evidence-card strong {
          display: block;
          margin: 2px 0;
          color: #e3e8ee;
          font-size: 11px;
        }

        .wlv-kr-governance-modal {
          position: fixed;
          inset: 0;
          z-index: 1400;
          display: grid;
          place-items: center;
          padding: 20px;
          background: rgba(0, 0, 0, .72);
        }

        .wlv-kr-governance-dialog {
          width: min(820px, 94vw);
          max-height: 90vh;
          overflow: auto;
          padding: 18px;
          border: 1px solid #343b45;
          border-radius: 8px;
          background: #171a1f;
          box-shadow: 0 18px 52px rgba(0,0,0,.55);
        }

        .wlv-kr-governance-dialog.compact {
          width: min(520px, 92vw);
        }

        .wlv-kr-governance-dialog > header,
        .wlv-kr-governance-dialog > footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
        }

        .wlv-kr-governance-dialog > header {
          margin-bottom: 14px;
        }

        .wlv-kr-governance-dialog > header h2 {
          margin: 0;
          font-size: 18px;
        }

        .wlv-kr-governance-dialog > footer {
          justify-content: flex-end;
          margin-top: 16px;
        }

        .wlv-kr-governance-dialog button {
          min-height: 30px;
          padding: 6px 10px;
          border: 1px solid #454b55;
          border-radius: 4px;
          background: #101216;
          color: #fff;
          font-size: 12px;
          cursor: pointer;
        }

        .wlv-kr-governance-dialog button.primary {
          border-color: #78c9ed;
          background: #78c9ed;
          color: #06111a;
        }

        .wlv-kr-governance-dialog button.danger {
          border-color: #a94a54;
          color: #ffb3bb;
        }

        .wlv-kr-governance-dialog button:disabled {
          opacity: .45;
          cursor: not-allowed;
        }

        .wlv-kr-governance-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
        }

        .wlv-kr-governance-field {
          display: grid;
          gap: 4px;
          font-size: 11px;
          color: #dfe4ea;
        }

        .wlv-kr-governance-field.full {
          grid-column: 1 / -1;
        }

        .wlv-kr-governance-field input,
        .wlv-kr-governance-field select,
        .wlv-kr-governance-field textarea {
          box-sizing: border-box;
          width: 100%;
          min-height: 32px;
          padding: 6px 8px;
          border: 1px solid #414852;
          border-radius: 4px;
          outline: none;
          background: #101318;
          color: #f1f4f7;
          font: inherit;
        }

        .wlv-kr-governance-field textarea {
          min-height: 78px;
          resize: vertical;
        }

        .wlv-kr-evidence-editor {
          grid-column: 1 / -1;
          padding: 10px;
          border: 1px solid #303844;
          border-radius: 7px;
          background: #10151d;
        }

        .wlv-kr-evidence-editor > header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;
        }

        .wlv-kr-evidence-editor > header strong {
          font-size: 10px;
          letter-spacing: .08em;
          text-transform: uppercase;
          color: #9ea8b6;
        }

        .wlv-kr-evidence-editor-row {
          display: grid;
          grid-template-columns: .9fr 1.2fr .8fr 1.2fr auto;
          gap: 6px;
          margin-top: 6px;
        }

        .wlv-kr-evidence-editor-row input {
          min-width: 0;
          min-height: 30px;
          padding: 5px 7px;
          border: 1px solid #3b434e;
          border-radius: 4px;
          background: #0c1016;
          color: #eef2f6;
          font-size: 10.5px;
        }

        .wlv-kr-history {
          margin-top: 12px;
          padding-top: 10px;
          border-top: 1px solid #2d3540;
        }

        .wlv-kr-history > strong {
          color: #98a3b2;
          font-size: 9px;
          letter-spacing: .1em;
          text-transform: uppercase;
        }

        .wlv-kr-history-item {
          margin-top: 6px;
          padding: 7px 8px;
          border: 1px solid #2e3743;
          border-radius: 6px;
          background: #0a1019;
          color: #aab4c2;
          font-size: 9.5px;
          line-height: 1.35;
        }

        @media (max-width: 1200px) {
          .wlv-kr-completion-preview-grid {
            grid-template-columns: repeat(5, minmax(92px, 1fr));
          }
        }
      `}</style>

      <header className="wlv-kr-header">
        <div>
          <span className="wlv-page-kicker">Knowledge Repository</span>
          <h1>KR Manager</h1>
          <p>Approved completion standards and knowledge are the application truth the WLV backend must follow.</p>
        </div>
        <div className="wlv-kr-header-actions">
          <button type="button" onClick={openAdd} disabled={saving}>Add Instruction</button>
          <button type="button" onClick={openEdit} disabled={!selected || !['approved', 'deprecated'].includes(selected.status) || saving}>Edit as Candidate</button>
          <button type="button" onClick={() => openGovernance('approve')} disabled={!selected || selected.status !== 'candidate' || saving}>Approve</button>
          <button type="button" onClick={() => openGovernance('reject')} disabled={!selected || selected.status !== 'candidate' || saving}>Reject</button>
          <button type="button" className="danger" onClick={() => openGovernance('deprecate')} disabled={!selected || selected.status !== 'approved' || saving}>Deprecate</button>
          <button type="button" onClick={clearFilters}>Clear filters</button>
          <button type="button" onClick={() => void loadCatalogue()}>Refresh</button>
        </div>
      </header>

      <section className="wlv-kr-summary-grid" aria-label="KR completion summary">
        <div className="wlv-kr-count-card"><strong>Approved live instructions</strong><span>{approvedCount}</span></div>
        <div className="wlv-kr-count-card"><strong>Visible result set</strong><span>{filtered.length === 0 ? '0' : `1–${filtered.length} of ${filtered.length}`}</span></div>
        <div className="wlv-kr-count-card"><strong>Production eligible</strong><span>{productionCount}</span></div>
        <div className="wlv-kr-count-card"><strong>Evidence records</strong><span>{evidenceTotal}</span></div>
      </section>

      <section className="wlv-kr-completion-preview" aria-label="Completion symbology preview">
        <h2>Completion symbology preview</h2>
        <div className="wlv-kr-completion-preview-grid">
          {PREVIEW_GLYPHS.map((glyph) => (
            <button
              type="button"
              key={glyph.key}
              className={componentFamily === glyph.key ? 'active' : ''}
              onClick={() => selectPreview(glyph.key)}
            >
              <CompletionGlyph kind={glyph.key} />
              <span>{glyph.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="wlv-kr-controls" aria-label="KR completion filters">
        <label>
          Search
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Component, standard, description…"
          />
        </label>
        <label>
          Catalogue view
          <select value={catalogueView} onChange={(event) => setCatalogueView(event.target.value as typeof catalogueView)}>
            <option value="all">Completion standards</option>
            <option value="components">Components</option>
            <option value="standards">Standards only</option>
          </select>
        </label>
        <label>
          Truth status
          <select value={truthStatus} onChange={(event) => setTruthStatus(event.target.value as typeof truthStatus)}>
            <option value="approved">Approved live truth</option>
            <option value="candidate">Candidates</option>
            <option value="deprecated">Deprecated</option>
            <option value="rejected">Rejected</option>
            <option value="all">All governance states</option>
          </select>
        </label>
        <label>
          Component family
          <select value={componentFamily} onChange={(event) => setComponentFamily(event.target.value)}>
            <option value="all">All families</option>
            {PREVIEW_GLYPHS.map((glyph) => <option key={glyph.key} value={glyph.key}>{glyph.label}</option>)}
          </select>
        </label>
      </section>

      {loadError ? (
        <div style={{ margin: '8px 0', padding: '8px 10px', border: '1px solid #7b3f46', borderRadius: 6, color: '#f0a3ad', fontSize: 11 }}>
          {loadError}
        </div>
      ) : null}
      {statusMessage ? (
        <div style={{ margin: '8px 0', padding: '8px 10px', border: '1px solid #2d6b58', borderRadius: 6, color: '#75dfb7', fontSize: 11 }}>
          {statusMessage}
        </div>
      ) : null}

      <div className="wlv-kr-main-grid">
        <section className="wlv-kr-instruction-list" aria-label="Managed completion knowledge">
          <div className="wlv-kr-section-heading">
            <h2>Managed completion knowledge</h2>
            <span>{filtered.length === 0 ? '0 of 0' : `1–${filtered.length} of ${filtered.length}`}</span>
          </div>
          <div className="wlv-kr-table-wrap">
            <table className="wlv-kr-table">
              <thead>
                <tr>
                  <th>Truth</th>
                  <th>Component / Standard</th>
                  <th>Canonical ID</th>
                  <th>Category</th>
                  <th>Standard status</th>
                  <th>Description</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((record) => (
                  <tr
                    key={record.instructionId}
                    className={selected?.instructionId === record.instructionId ? 'selected' : ''}
                    onClick={() => setSelectedId(record.instructionId)}
                  >
                    <td>{truthBadge()}</td>
                    <td><strong>{record.componentLabel}</strong><span>{record.recordType}</span></td>
                    <td>{record.canonicalId}</td>
                    <td>{record.category}</td>
                    <td><span className="wlv-kr-completion-version">{record.standardStatus} · {record.version}</span></td>
                    <td>{record.description}</td>
                    <td>{record.evidenceCount}</td>
                  </tr>
                ))}
                {filtered.length === 0 ? (
                  <tr><td colSpan={7}>No completion KR records match the current filters.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="wlv-kr-detail-panel" aria-label="Completion instruction detail">
          {selected ? (
            <>
              <div className="wlv-kr-detail-heading">
                <span>Completion Instruction</span>
                {selected.productionEligible ? truthBadge() : <span>{selected.standardStatus}</span>}
              </div>
              <h2>{selected.componentLabel}</h2>
              <dl className="wlv-kr-detail-dl">
                <dt>Instruction ID</dt><dd>{selected.instructionId}</dd>
                <dt>Record type</dt><dd>{selected.recordType === 'standard' ? 'Standard' : 'Instruction'}</dd>
                <dt>Template</dt><dd>Completion Instruction Template v1</dd>
                <dt>Component family</dt><dd>Completions</dd>
                <dt>Canonical component</dt><dd>{selected.canonicalId}</dd>
                <dt>Status</dt><dd>{selected.standardStatus} · {selected.version}</dd>
              </dl>

              <div className="wlv-kr-completion-rule">
                <strong>Application must</strong>
                <p>{selected.mustDo}</p>
              </div>

              <div className="wlv-kr-completion-rule must-not">
                <strong>Application must not</strong>
                <p>{selected.mustNotDo}</p>
              </div>

              <div className="wlv-kr-completion-evidence">
                <strong>Evidence</strong>
                {selected.evidence.map((evidence) => (
                  <div className="wlv-kr-completion-evidence-card" key={`${evidence.documentId}:${evidence.section}`}>
                    <span>{evidence.sourceType}</span>
                    <strong>{evidence.title}</strong>
                    <em>{evidence.documentId}</em>
                    <em>{evidence.section}</em>
                  </div>
                ))}
              </div>

              <div className="wlv-kr-history">
                <strong>Governance history</strong>
                {(selected.governanceHistory ?? []).slice().reverse().map((item, index) => (
                  <div className="wlv-kr-history-item" key={`${item.timestamp}:${item.action}:${index}`}>
                    <strong>{item.action.split('_').join(' ')}</strong>
                    <div>{item.actor} · {new Date(item.timestamp).toLocaleString()}</div>
                    {item.reason ? <div>{item.reason}</div> : null}
                  </div>
                ))}
                {(selected.governanceHistory ?? []).length === 0 ? (
                  <div className="wlv-kr-history-item">No governance history recorded.</div>
                ) : null}
              </div>
            </>
          ) : (
            <div style={{ padding: 12, color: '#9aa5b4', fontSize: 11 }}>
              {loading ? 'Loading completion knowledge from KR backend…' : loadError ?? 'No completion KR records match the current filters.'}
            </div>
          )}
        </aside>
      </div>

      {editorMode ? (
        <div
          className="wlv-kr-governance-modal"
          role="dialog"
          aria-modal="true"
          aria-label={editorMode === 'add' ? 'Add completion instruction' : 'Edit completion instruction as candidate'}
          onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setEditorMode(null); }}
        >
          <div className="wlv-kr-governance-dialog">
            <header>
              <h2>{editorMode === 'add' ? 'Add Completion Instruction' : `Edit as Candidate — ${selected?.componentLabel ?? ''}`}</h2>
              <button type="button" onClick={() => setEditorMode(null)} disabled={saving}>Close</button>
            </header>

            <div className="wlv-kr-governance-grid">
              <label className="wlv-kr-governance-field">
                <span>Record type</span>
                <select
                  value={candidateForm.recordType}
                  onChange={(event) => setCandidateForm((current) => ({
                    ...current,
                    recordType: event.target.value as CompletionCandidateForm['recordType'],
                    category: event.target.value === 'standard' ? 'Standards' : 'Completions',
                  }))}
                >
                  <option value="component">Component</option>
                  <option value="standard">Standard</option>
                </select>
              </label>

              <label className="wlv-kr-governance-field">
                <span>Version</span>
                <input
                  value={candidateForm.version}
                  disabled={editorMode === 'edit'}
                  onChange={(event) => setCandidateForm((current) => ({ ...current, version: event.target.value }))}
                />
              </label>

              <label className="wlv-kr-governance-field">
                <span>Component key</span>
                <input
                  value={candidateForm.componentKey}
                  onChange={(event) => setCandidateForm((current) => ({ ...current, componentKey: event.target.value }))}
                  placeholder="e.g. expansion_joint"
                />
              </label>

              <label className="wlv-kr-governance-field">
                <span>Display label</span>
                <input
                  value={candidateForm.componentLabel}
                  onChange={(event) => setCandidateForm((current) => ({ ...current, componentLabel: event.target.value }))}
                />
              </label>

              <label className="wlv-kr-governance-field full">
                <span>Canonical ID</span>
                <input
                  value={candidateForm.canonicalId}
                  onChange={(event) => setCandidateForm((current) => ({ ...current, canonicalId: event.target.value }))}
                  placeholder="completion.expansion_joint"
                />
              </label>

              <label className="wlv-kr-governance-field full">
                <span>Description</span>
                <textarea
                  value={candidateForm.description}
                  onChange={(event) => setCandidateForm((current) => ({ ...current, description: event.target.value }))}
                />
              </label>

              <label className="wlv-kr-governance-field full">
                <span>Application MUST</span>
                <textarea
                  value={candidateForm.mustDo}
                  onChange={(event) => setCandidateForm((current) => ({ ...current, mustDo: event.target.value }))}
                />
              </label>

              <label className="wlv-kr-governance-field full">
                <span>Application MUST NOT</span>
                <textarea
                  value={candidateForm.mustNotDo}
                  onChange={(event) => setCandidateForm((current) => ({ ...current, mustNotDo: event.target.value }))}
                />
              </label>

              <label className="wlv-kr-governance-field full">
                <span>Change reason</span>
                <textarea
                  value={candidateForm.changeReason}
                  onChange={(event) => setCandidateForm((current) => ({ ...current, changeReason: event.target.value }))}
                  placeholder={editorMode === 'edit' ? 'Why is this revision needed?' : 'Why should this instruction enter KR review?'}
                />
              </label>

              <section className="wlv-kr-evidence-editor">
                <header>
                  <strong>Evidence</strong>
                  <button
                    type="button"
                    onClick={() => setCandidateForm((current) => ({
                      ...current,
                      evidence: [...current.evidence, { ...EMPTY_EVIDENCE }],
                    }))}
                  >
                    Add Evidence
                  </button>
                </header>

                {candidateForm.evidence.map((item, index) => (
                  <div className="wlv-kr-evidence-editor-row" key={index}>
                    <input value={item.sourceType} placeholder="Source type" onChange={(event) => updateEvidence(index, { sourceType: event.target.value })} />
                    <input value={item.title} placeholder="Title" onChange={(event) => updateEvidence(index, { title: event.target.value })} />
                    <input value={item.documentId} placeholder="Document ID" onChange={(event) => updateEvidence(index, { documentId: event.target.value })} />
                    <input value={item.section} placeholder="Section / scope" onChange={(event) => updateEvidence(index, { section: event.target.value })} />
                    <button
                      type="button"
                      className="danger"
                      onClick={() => setCandidateForm((current) => ({
                        ...current,
                        evidence: current.evidence.filter((_, itemIndex) => itemIndex !== index),
                      }))}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {candidateForm.evidence.length === 0 ? (
                  <div style={{ color: '#8f99a6', fontSize: 10.5 }}>No evidence rows yet.</div>
                ) : null}
              </section>
            </div>

            <footer>
              <button type="button" onClick={() => setEditorMode(null)} disabled={saving}>Cancel</button>
              <button type="button" className="primary" onClick={() => void submitCandidate()} disabled={saving}>
                {saving ? 'Saving…' : editorMode === 'add' ? 'Create Candidate' : 'Save Candidate Revision'}
              </button>
            </footer>
          </div>
        </div>
      ) : null}

      {governanceAction && selected ? (
        <div
          className="wlv-kr-governance-modal"
          role="dialog"
          aria-modal="true"
          aria-label={`${governanceAction} completion knowledge`}
          onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setGovernanceAction(null); }}
        >
          <div className="wlv-kr-governance-dialog compact">
            <header>
              <h2>{governanceAction[0].toUpperCase() + governanceAction.slice(1)} — {selected.componentLabel}</h2>
              <button type="button" onClick={() => setGovernanceAction(null)} disabled={saving}>Close</button>
            </header>

            <p style={{ margin: '0 0 12px', color: '#b9c1cb', fontSize: 11, lineHeight: 1.45 }}>
              {governanceAction === 'approve'
                ? 'Approving this candidate makes it production-eligible. Any currently approved record with the same canonical ID will be superseded and deprecated by the backend.'
                : governanceAction === 'reject'
                  ? 'Rejecting this candidate preserves it in governance history but prevents production use.'
                  : 'Deprecating this approved record immediately removes it from production-eligible completion truth.'}
            </p>

            <label className="wlv-kr-governance-field full">
              <span>{governanceAction === 'approve' ? 'Approval reason (optional)' : 'Reason (required)'}</span>
              <textarea value={governanceReason} onChange={(event) => setGovernanceReason(event.target.value)} />
            </label>

            <footer>
              <button type="button" onClick={() => setGovernanceAction(null)} disabled={saving}>Cancel</button>
              <button
                type="button"
                className={governanceAction === 'approve' ? 'primary' : 'danger'}
                onClick={() => void submitGovernance()}
                disabled={saving}
              >
                {saving ? 'Applying…' : governanceAction[0].toUpperCase() + governanceAction.slice(1)}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </section>
  );
}
