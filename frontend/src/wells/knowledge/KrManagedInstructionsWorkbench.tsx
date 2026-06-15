import { useCallback, useEffect, useMemo, useState } from 'react';

type KrInstructionSummary = {
  instruction_id: string;
  source_record_type: string;
  instruction_type: string;
  status: string;
  runtime_eligible: boolean;
  production_eligible: boolean;
  subject: string;
  application_area?: string | null;
  template_key?: string | null;
  track_id?: string | null;
  curve_family?: string | null;
  canonical_curve_id?: string | null;
  alias?: string | null;
  must_do: string;
  must_not_do?: string | null;
  evidence_ref_count: number;
  approved_by?: string | null;
  updated_at?: string | null;
};

type KrInstructionListResponse = {
  service: string;
  contract_version: string;
  approved_only: boolean;
  candidate_records_used: boolean;
  deprecated_records_used: boolean;
  total_count: number;
  returned_count: number;
  instructions: KrInstructionSummary[];
};

type KrInstructionSummaryResponse = {
  service: string;
  contract_version: string;
  record_type_counts: Record<string, number>;
  instruction_type_counts: Record<string, number>;
  status_counts: Record<string, number>;
  runtime_eligible_count: number;
  production_eligible_count: number;
  evidence_record_count: number;
};

type KrEvidenceRef = {
  evidence_id: string;
  source_type?: string | null;
  source_label?: string | null;
  source_reference?: string | null;
  confidence?: number | null;
  notes?: string | null;
};

type KrInstructionDetail = KrInstructionSummary & {
  evidence: KrEvidenceRef[];
  raw_record: Record<string, unknown>;
};

type KrInstructionDetailResponse = {
  service: string;
  contract_version: string;
  instruction: KrInstructionDetail;
};

type KrTemplateDecisionResponse = {
  service: string;
  contract_version: string;
  template_key: string;
  instruction_count: number;
  template_instructions: KrInstructionSummary[];
  track_instructions: KrInstructionSummary[];
  selection_instructions: KrInstructionSummary[];
  curve_instructions: KrInstructionSummary[];
  evidence: KrEvidenceRef[];
};

type KrCandidatePayload = {
  instruction_type: string;
  subject: string;
  application_area?: string | null;
  template_key?: string | null;
  track_id?: string | null;
  curve_family?: string | null;
  canonical_curve_id?: string | null;
  alias?: string | null;
  must_do: string;
  must_not_do?: string | null;
  allowed_use?: string | null;
  evidence_note?: string | null;
  change_reason?: string | null;
  supersedes_record_id?: string | null;
  reviewer?: string | null;
};

type KrGovernanceActionResponse = {
  service: string;
  contract_version: string;
  action: string;
  instruction: KrInstructionDetail;
  superseded_instruction_id?: string | null;
};

type KrCurationMode = 'create' | 'edit_candidate' | 'edit_as_candidate';

type KrCurationFormState = {
  mode: KrCurationMode;
  instructionId?: string | null;
  instruction_type: string;
  subject: string;
  application_area: string;
  template_key: string;
  track_id: string;
  curve_family: string;
  canonical_curve_id: string;
  alias: string;
  must_do: string;
  must_not_do: string;
  allowed_use: string;
  evidence_note: string;
  change_reason: string;
  supersedes_record_id: string;
};

type KrStatusFilter = 'all' | 'approved' | 'candidate' | 'rejected' | 'deprecated' | 'superseded' | 'runtime' | 'production';
type KrInstructionTypeFilter = 'all' | 'curve_instruction' | 'template_instruction' | 'track_instruction' | 'selection_instruction' | 'application_instruction';

type RuntimeWindow = Window & { __WLV_API_BASE_URL__?: string };

const TEMPLATE_KEYS = [
  'open_hole_triple_combo',
  'open_hole_quad_combo',
  'density_neutron_lithology',
  'resistivity_invasion_review',
  'sonic_seismic_tie',
  'cased_hole_cement_bond',
  'well_integrity_casing_inspection',
];

const PAGE_LIMIT = 500;

function wlvApiBaseUrl(): string {
  const runtimeConfig = window as RuntimeWindow;
  if (runtimeConfig.__WLV_API_BASE_URL__) {
    return runtimeConfig.__WLV_API_BASE_URL__.replace(/\/$/, '');
  }

  const protocol = window.location.protocol || 'http:';
  const hostname = window.location.hostname || '127.0.0.1';
  const port = window.location.port;
  const backendPort = '8001';

  if (port === backendPort) return '';
  if (port === '5173' || port === '5174' || port === '5175') return `${protocol}//${hostname}:${backendPort}`;
  return `http://127.0.0.1:${backendPort}`;
}

async function fetchKrJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${wlvApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

async function sendKrJson<T>(path: string, method: string, body: unknown): Promise<T> {
  return fetchKrJson<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function safeText(value: unknown, fallback = '—'): string {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text.length > 0 ? text : fallback;
}

function labelFromKey(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function uniqueSorted(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort((a, b) => a.localeCompare(b));
}


function blankCurationForm(): KrCurationFormState {
  return {
    mode: 'create',
    instruction_type: 'application_instruction',
    subject: '',
    application_area: '',
    template_key: '',
    track_id: '',
    curve_family: '',
    canonical_curve_id: '',
    alias: '',
    must_do: '',
    must_not_do: '',
    allowed_use: '',
    evidence_note: '',
    change_reason: '',
    supersedes_record_id: '',
  };
}

function curationFormFromInstruction(detail: KrInstructionDetail, mode: KrCurationMode): KrCurationFormState {
  return {
    mode,
    instructionId: mode === 'edit_candidate' ? detail.instruction_id : null,
    instruction_type: detail.instruction_type || 'application_instruction',
    subject: detail.subject || '',
    application_area: detail.application_area || '',
    template_key: detail.template_key || '',
    track_id: detail.track_id || '',
    curve_family: detail.curve_family || '',
    canonical_curve_id: detail.canonical_curve_id || '',
    alias: detail.alias || '',
    must_do: detail.must_do || '',
    must_not_do: detail.must_not_do || '',
    allowed_use: String(detail.raw_record?.instruction_allowed_use ?? ''),
    evidence_note: '',
    change_reason: mode === 'edit_as_candidate' ? `Candidate revision of ${detail.instruction_id}` : '',
    supersedes_record_id: mode === 'edit_as_candidate' ? detail.instruction_id : String(detail.raw_record?.supersedes_record_id ?? ''),
  };
}

function curationPayload(form: KrCurationFormState): KrCandidatePayload {
  const clean = (value: string) => value.trim() || null;
  return {
    instruction_type: form.instruction_type,
    subject: form.subject.trim(),
    application_area: clean(form.application_area),
    template_key: clean(form.template_key),
    track_id: clean(form.track_id),
    curve_family: clean(form.curve_family),
    canonical_curve_id: clean(form.canonical_curve_id),
    alias: clean(form.alias),
    must_do: form.must_do.trim(),
    must_not_do: clean(form.must_not_do),
    allowed_use: clean(form.allowed_use),
    evidence_note: clean(form.evidence_note),
    change_reason: clean(form.change_reason),
    supersedes_record_id: clean(form.supersedes_record_id),
    reviewer: 'Bwana',
  };
}

function KrCurationModal({ form, saving, error, onChange, onCancel, onSave }: {
  form: KrCurationFormState;
  saving: boolean;
  error: string | null;
  onChange: (next: KrCurationFormState) => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const update = (key: keyof KrCurationFormState, value: string) => onChange({ ...form, [key]: value });
  const title = form.mode === 'edit_candidate' ? 'Edit candidate instruction' : form.mode === 'edit_as_candidate' ? 'Edit as candidate revision' : 'Add candidate instruction';
  return (
    <div className="wlv-kr-modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <section className="wlv-kr-modal-card">
        <header className="wlv-kr-modal-header">
          <div>
            <span className="wlv-page-kicker">Knowledge curation</span>
            <h2>{title}</h2>
          </div>
          <button type="button" className="wlv-kr-outline-button" onClick={onCancel} disabled={saving}>Close</button>
        </header>
        {error ? <p className="wlv-kr-error">{error}</p> : null}
        <div className="wlv-kr-form-grid">
          <label>Instruction type
            <select value={form.instruction_type} onChange={(event) => update('instruction_type', event.target.value)}>
              <option value="application_instruction">Application</option>
              <option value="curve_instruction">Curve</option>
              <option value="template_instruction">Template</option>
              <option value="track_instruction">Track</option>
              <option value="selection_instruction">Selection</option>
            </select>
          </label>
          <label>Subject
            <input value={form.subject} onChange={(event) => update('subject', event.target.value)} placeholder="CALI, BS, Open-Hole Triple Combo…" />
          </label>
          <label>Application area
            <input value={form.application_area} onChange={(event) => update('application_area', event.target.value)} placeholder="WDV curve classification / template selection" />
          </label>
          <label>Template key
            <input value={form.template_key} onChange={(event) => update('template_key', event.target.value)} placeholder="open_hole_triple_combo" />
          </label>
          <label>Track ID
            <input value={form.track_id} onChange={(event) => update('track_id', event.target.value)} placeholder="optional" />
          </label>
          <label>Curve family
            <input value={form.curve_family} onChange={(event) => update('curve_family', event.target.value)} placeholder="caliper / bit_size / neutron_porosity" />
          </label>
          <label>Canonical curve
            <input value={form.canonical_curve_id} onChange={(event) => update('canonical_curve_id', event.target.value)} placeholder="optional" />
          </label>
          <label>Alias / mnemonic
            <input value={form.alias} onChange={(event) => update('alias', event.target.value)} placeholder="CALI / BS / NPHI" />
          </label>
          <label className="wide">Application must
            <textarea value={form.must_do} onChange={(event) => update('must_do', event.target.value)} rows={3} placeholder="Explicit instruction the application must follow" />
          </label>
          <label className="wide">Application must not
            <textarea value={form.must_not_do} onChange={(event) => update('must_not_do', event.target.value)} rows={3} placeholder="Explicit prohibition or non-equivalence" />
          </label>
          <label className="wide">Allowed use / notes
            <textarea value={form.allowed_use} onChange={(event) => update('allowed_use', event.target.value)} rows={2} placeholder="Optional: reference overlay, fallback only, etc." />
          </label>
          <label className="wide">Evidence note
            <textarea value={form.evidence_note} onChange={(event) => update('evidence_note', event.target.value)} rows={2} placeholder="Why this is true / source note" />
          </label>
          <label>Supersedes record ID
            <input value={form.supersedes_record_id} onChange={(event) => update('supersedes_record_id', event.target.value)} placeholder="optional" />
          </label>
          <label>Change reason
            <input value={form.change_reason} onChange={(event) => update('change_reason', event.target.value)} placeholder="optional" />
          </label>
        </div>
        <footer className="wlv-kr-modal-actions">
          <button type="button" className="wlv-kr-outline-button" onClick={onCancel} disabled={saving}>Cancel</button>
          <button type="button" className="wlv-kr-primary-button" onClick={onSave} disabled={saving || !form.subject.trim() || !form.must_do.trim()}>
            {saving ? 'Saving…' : 'Save candidate'}
          </button>
        </footer>
      </section>
    </div>
  );
}

function KrCountCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="wlv-kr-count-card">
      <strong>{label}</strong>
      <span>{value}</span>
    </div>
  );
}

function KrTruthBadge({ item }: { item: KrInstructionSummary }) {
  const ok = item.status === 'approved' && item.runtime_eligible && item.production_eligible;
  return (
    <span className={`wlv-kr-truth-badge ${ok ? 'approved' : 'review'}`}>
      {ok ? 'Live truth' : 'Review'}
    </span>
  );
}

function KrInstructionDetailPanel({ detail, loading, error }: { detail: KrInstructionDetail | null; loading: boolean; error: string | null }) {
  if (loading) {
    return <aside className="wlv-kr-detail-panel"><p>Loading instruction detail…</p></aside>;
  }

  if (error) {
    return <aside className="wlv-kr-detail-panel"><p className="wlv-kr-error">{error}</p></aside>;
  }

  if (!detail) {
    return (
      <aside className="wlv-kr-detail-panel">
        <h2>Instruction detail</h2>
        <p>Select an instruction to inspect the exact application rule, evidence, and raw approved record.</p>
      </aside>
    );
  }

  return (
    <aside className="wlv-kr-detail-panel">
      <div className="wlv-kr-detail-heading">
        <span>{labelFromKey(detail.instruction_type)}</span>
        <KrTruthBadge item={detail} />
      </div>
      <h2>{detail.subject}</h2>
      <dl className="wlv-kr-detail-dl">
        <dt>Instruction ID</dt><dd>{detail.instruction_id}</dd>
        <dt>Record type</dt><dd>{detail.source_record_type}</dd>
        <dt>Template</dt><dd>{safeText(detail.template_key)}</dd>
        <dt>Track</dt><dd>{safeText(detail.track_id)}</dd>
        <dt>Curve family</dt><dd>{safeText(detail.curve_family)}</dd>
        <dt>Canonical curve</dt><dd>{safeText(detail.canonical_curve_id)}</dd>
      </dl>

      <section className="wlv-kr-rule-box must">
        <h3>Application must</h3>
        <p>{detail.must_do}</p>
      </section>

      <section className="wlv-kr-rule-box must-not">
        <h3>Application must not</h3>
        <p>{safeText(detail.must_not_do, 'No explicit prohibition recorded yet.')}</p>
      </section>

      <section className="wlv-kr-evidence-section">
        <h3>Evidence</h3>
        {detail.evidence.length === 0 ? (
          <p className="wlv-kr-muted">No evidence records linked to this instruction.</p>
        ) : (
          <div className="wlv-kr-evidence-list">
            {detail.evidence.map((evidence) => (
              <article key={evidence.evidence_id} className="wlv-kr-evidence-card">
                <strong>{safeText(evidence.source_label, evidence.evidence_id)}</strong>
                <span>{safeText(evidence.source_type)}</span>
                <p>{safeText(evidence.notes, safeText(evidence.source_reference))}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </aside>
  );
}

function TemplateDecisionPanel({ templateKey }: { templateKey: string }) {
  const [decision, setDecision] = useState<KrTemplateDecisionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!templateKey) {
      setDecision(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchKrJson<KrTemplateDecisionResponse>(`/api/wlv/knowledge/instructions/templates/${encodeURIComponent(templateKey)}/decision`)
      .then((result) => {
        if (!cancelled) setDecision(result);
      })
      .catch((caught) => {
        if (!cancelled) {
          setDecision(null);
          setError(caught instanceof Error ? caught.message : 'Template decision instructions unavailable');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [templateKey]);

  const groups = decision
    ? [
        ['Template', decision.template_instructions],
        ['Track', decision.track_instructions],
        ['Selection', decision.selection_instructions],
        ['Curve', decision.curve_instructions],
      ] as const
    : [];

  return (
    <section className="wlv-kr-template-panel">
      <div className="wlv-kr-section-heading">
        <h2>Template decision instructions</h2>
        <span>{templateKey ? labelFromKey(templateKey) : 'Select a template'}</span>
      </div>
      {loading ? <p className="wlv-kr-muted">Loading template instructions…</p> : null}
      {error ? <p className="wlv-kr-error">{error}</p> : null}
      {decision ? (
        <div className="wlv-kr-template-groups">
          {groups.map(([label, items]) => (
            <article key={label} className="wlv-kr-template-group">
              <strong>{label}</strong>
              <span>{items.length} instruction{items.length === 1 ? '' : 's'}</span>
              <ul>
                {items.slice(0, 5).map((item) => (
                  <li key={item.instruction_id}>{item.must_do}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      ) : !loading && !error ? (
        <p className="wlv-kr-muted">Choose a template to see the approved KR rules the application must follow.</p>
      ) : null}
    </section>
  );
}

function buildInstructionPath(search: string, instructionType: KrInstructionTypeFilter, truthFilter: KrStatusFilter, templateFilter: string, curveFamilyFilter: string): string {
  const params = new URLSearchParams();
  params.set('limit', String(PAGE_LIMIT));
  params.set('approved_only', truthFilter === 'all' || truthFilter === 'approved' || truthFilter === 'runtime' || truthFilter === 'production' ? 'true' : 'false');
  const q = search.trim();
  if (q) params.set('q', q);
  if (instructionType !== 'all') params.set('instruction_type', instructionType);
  if (truthFilter === 'candidate' || truthFilter === 'rejected' || truthFilter === 'deprecated' || truthFilter === 'superseded') params.set('status', truthFilter);
  if (templateFilter !== 'all') params.set('template_key', templateFilter);
  if (curveFamilyFilter !== 'all') params.set('curve_family', curveFamilyFilter);
  return `/api/wlv/knowledge/instructions?${params.toString()}`;
}

export function KrManagedInstructionsWorkbench() {
  const [summary, setSummary] = useState<KrInstructionSummaryResponse | null>(null);
  const [instructions, setInstructions] = useState<KrInstructionSummary[]>([]);
  const [listTotalCount, setListTotalCount] = useState(0);
  const [listReturnedCount, setListReturnedCount] = useState(0);
  const [selectedInstructionId, setSelectedInstructionId] = useState<string | null>(null);
  const [detail, setDetail] = useState<KrInstructionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [listLoading, setListLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [instructionType, setInstructionType] = useState<KrInstructionTypeFilter>('all');
  const [truthFilter, setTruthFilter] = useState<KrStatusFilter>('all');
  const [templateFilter, setTemplateFilter] = useState('all');
  const [curveFamilyFilter, setCurveFamilyFilter] = useState('all');
  const [decisionTemplateKey, setDecisionTemplateKey] = useState('open_hole_triple_combo');
  const [curationForm, setCurationForm] = useState<KrCurationFormState | null>(null);
  const [curationSaving, setCurationSaving] = useState(false);
  const [curationError, setCurationError] = useState<string | null>(null);

  const loadSummary = useCallback(() => {
    setSummaryLoading(true);
    setError(null);
    void fetchKrJson<KrInstructionSummaryResponse>('/api/wlv/knowledge/instructions/summary')
      .then((nextSummary) => setSummary(nextSummary))
      .catch((caught) => {
        setSummary(null);
        setError(caught instanceof Error ? caught.message : 'KR instruction summary unavailable');
      })
      .finally(() => setSummaryLoading(false));
  }, []);

  const loadInstructions = useCallback(() => {
    setListLoading(true);
    setError(null);
    const path = buildInstructionPath(search, instructionType, truthFilter, templateFilter, curveFamilyFilter);
    void fetchKrJson<KrInstructionListResponse>(path)
      .then((list) => {
        const rows = (list.instructions ?? []).filter((item) => {
          if (truthFilter === 'runtime' && !item.runtime_eligible) return false;
          if (truthFilter === 'production' && !item.production_eligible) return false;
          return true;
        });
        setInstructions(rows);
        setListTotalCount(list.total_count ?? rows.length);
        setListReturnedCount(rows.length);
        setSelectedInstructionId((current) => (
          current && rows.some((item) => item.instruction_id === current)
            ? current
            : rows[0]?.instruction_id ?? null
        ));
      })
      .catch((caught) => {
        setInstructions([]);
        setListTotalCount(0);
        setListReturnedCount(0);
        setSelectedInstructionId(null);
        setError(caught instanceof Error ? caught.message : 'KR instruction service unavailable');
      })
      .finally(() => setListLoading(false));
  }, [curveFamilyFilter, instructionType, search, templateFilter, truthFilter]);

  const refreshAll = useCallback(() => {
    loadSummary();
    loadInstructions();
  }, [loadInstructions, loadSummary]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    loadInstructions();
  }, [loadInstructions]);

  useEffect(() => {
    if (!selectedInstructionId) {
      setDetail(null);
      setDetailError(null);
      return;
    }

    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    void fetchKrJson<KrInstructionDetailResponse>(`/api/wlv/knowledge/instructions/${encodeURIComponent(selectedInstructionId)}`)
      .then((result) => {
        if (!cancelled) setDetail(result.instruction);
      })
      .catch((caught) => {
        if (!cancelled) {
          setDetail(null);
          setDetailError(caught instanceof Error ? caught.message : 'Instruction detail unavailable');
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedInstructionId]);

  const templateOptions = useMemo(() => uniqueSorted([...TEMPLATE_KEYS, ...instructions.map((item) => item.template_key)]), [instructions]);
  const curveFamilyOptions = useMemo(() => uniqueSorted(instructions.map((item) => item.curve_family)), [instructions]);
  const hasActiveFilters = search.trim() || instructionType !== 'all' || truthFilter !== 'all' || templateFilter !== 'all' || curveFamilyFilter !== 'all';

  const clearFilters = () => {
    setSearch('');
    setInstructionType('all');
    setTruthFilter('all');
    setTemplateFilter('all');
    setCurveFamilyFilter('all');
  };


  const openCreateCandidate = () => {
    setCurationError(null);
    setCurationForm(blankCurationForm());
  };

  const openEditAsCandidate = () => {
    if (!detail) return;
    setCurationError(null);
    setCurationForm(curationFormFromInstruction(detail, detail.status === 'candidate' ? 'edit_candidate' : 'edit_as_candidate'));
  };

  const saveCandidate = () => {
    if (!curationForm) return;
    setCurationSaving(true);
    setCurationError(null);
    const payload = curationPayload(curationForm);
    const request = curationForm.mode === 'edit_candidate' && curationForm.instructionId
      ? sendKrJson<KrGovernanceActionResponse>(`/api/wlv/knowledge/instructions/candidates/${encodeURIComponent(curationForm.instructionId)}`, 'PUT', payload)
      : sendKrJson<KrGovernanceActionResponse>('/api/wlv/knowledge/instructions/candidates', 'POST', payload);
    void request
      .then((result) => {
        setCurationForm(null);
        setTruthFilter(result.instruction.status === 'candidate' ? 'candidate' : 'all');
        setSelectedInstructionId(result.instruction.instruction_id);
        refreshAll();
      })
      .catch((caught) => setCurationError(caught instanceof Error ? caught.message : 'Unable to save candidate instruction'))
      .finally(() => setCurationSaving(false));
  };

  const runGovernanceAction = (action: 'approve' | 'reject' | 'deprecate') => {
    if (!detail) return;
    const reason = window.prompt(`Reason to ${action} this instruction?`, action === 'approve' ? 'Approved by user.' : action === 'reject' ? 'Rejected by user.' : 'Deprecated by user.');
    if (reason === null) return;
    const path = action === 'approve'
      ? `/api/wlv/knowledge/instructions/candidates/${encodeURIComponent(detail.instruction_id)}/approve`
      : action === 'reject'
        ? `/api/wlv/knowledge/instructions/candidates/${encodeURIComponent(detail.instruction_id)}/reject`
        : `/api/wlv/knowledge/instructions/${encodeURIComponent(detail.instruction_id)}/deprecate`;
    setCurationSaving(true);
    setCurationError(null);
    void sendKrJson<KrGovernanceActionResponse>(path, 'POST', { reviewer: 'Bwana', reason })
      .then((result) => {
        if (action === 'approve') setTruthFilter('all');
        if (action === 'reject') setTruthFilter('rejected');
        if (action === 'deprecate') setTruthFilter('deprecated');
        setSelectedInstructionId(result.instruction.instruction_id);
        refreshAll();
      })
      .catch((caught) => setCurationError(caught instanceof Error ? caught.message : `Unable to ${action} instruction`))
      .finally(() => setCurationSaving(false));
  };

  return (
    <section className="wlv-kr-workbench" aria-label="Knowledge Repository manager">
      <header className="wlv-kr-header">
        <div>
          <span className="wlv-page-kicker">Knowledge Repository</span>
          <h1>KR Manager</h1>
          <p>Approved KR instructions are the application truth the WLV backend must follow.</p>
        </div>
        <div className="wlv-kr-header-actions">
          <button type="button" className="wlv-kr-primary-button" onClick={openCreateCandidate} disabled={curationSaving}>Add Instruction</button>
          <button type="button" className="wlv-kr-outline-button" onClick={openEditAsCandidate} disabled={!detail || curationSaving}>{detail?.status === 'candidate' ? 'Edit Candidate' : 'Edit as Candidate'}</button>
          <button type="button" className="wlv-kr-outline-button" onClick={() => runGovernanceAction('approve')} disabled={!detail || detail.status !== 'candidate' || curationSaving}>Approve</button>
          <button type="button" className="wlv-kr-outline-button" onClick={() => runGovernanceAction('reject')} disabled={!detail || detail.status !== 'candidate' || curationSaving}>Reject</button>
          <button type="button" className="wlv-kr-outline-button danger" onClick={() => runGovernanceAction('deprecate')} disabled={!detail || detail.status !== 'approved' || curationSaving}>Deprecate</button>
          <button type="button" className="wlv-kr-outline-button" onClick={clearFilters} disabled={!hasActiveFilters || listLoading}>
            Clear filters
          </button>
          <button type="button" className="wlv-kr-outline-button" onClick={refreshAll} disabled={summaryLoading || listLoading}>
            Refresh
          </button>
        </div>
      </header>

      {error ? <p className="wlv-kr-error">{error}</p> : null}

      <section className="wlv-kr-summary-grid" aria-label="KR instruction summary">
        <KrCountCard label="Approved live instructions" value={summaryLoading ? '…' : summary?.runtime_eligible_count ?? '—'} />
        <KrCountCard label="Visible result set" value={listLoading ? '…' : `${listReturnedCount} / ${listTotalCount}`} />
        <KrCountCard label="Production eligible" value={summaryLoading ? '…' : summary?.production_eligible_count ?? '—'} />
        <KrCountCard label="Evidence records" value={summaryLoading ? '…' : summary?.evidence_record_count ?? '—'} />
      </section>

      <section className="wlv-kr-controls" aria-label="KR instruction filters">
        <label>
          Search
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="CALI, BS, NPHI, resistivity, template…" />
        </label>
        <label>
          Instruction type
          <select value={instructionType} onChange={(event) => setInstructionType(event.target.value as KrInstructionTypeFilter)}>
            <option value="all">All</option>
            <option value="curve_instruction">Curve</option>
            <option value="template_instruction">Template</option>
            <option value="track_instruction">Track</option>
            <option value="selection_instruction">Selection</option>
            <option value="application_instruction">Application</option>
          </select>
        </label>
        <label>
          Truth status
          <select value={truthFilter} onChange={(event) => setTruthFilter(event.target.value as KrStatusFilter)}>
            <option value="all">Approved live truth</option>
            <option value="approved">Approved</option>
            <option value="candidate">Candidate</option>
            <option value="rejected">Rejected</option>
            <option value="deprecated">Deprecated</option>
            <option value="superseded">Superseded</option>
            <option value="runtime">Runtime eligible</option>
            <option value="production">Production eligible</option>
          </select>
        </label>
        <label>
          Template
          <select value={templateFilter} onChange={(event) => setTemplateFilter(event.target.value)}>
            <option value="all">All templates</option>
            {templateOptions.map((template) => <option key={template} value={template}>{labelFromKey(template)}</option>)}
          </select>
        </label>
        <label>
          Curve family
          <select value={curveFamilyFilter} onChange={(event) => setCurveFamilyFilter(event.target.value)}>
            <option value="all">All families</option>
            {curveFamilyOptions.map((family) => <option key={family} value={family}>{labelFromKey(family)}</option>)}
          </select>
        </label>
      </section>

      <div className="wlv-kr-main-grid">
        <section className="wlv-kr-instruction-list" aria-label="Approved KR instructions">
          <div className="wlv-kr-section-heading">
            <h2>Managed application instructions</h2>
            <span>{listLoading ? 'Loading…' : `${listReturnedCount} shown of ${listTotalCount}`}</span>
          </div>
          <div className="wlv-kr-table-wrap">
            <table className="wlv-kr-table">
              <thead>
                <tr>
                  <th>Truth</th>
                  <th>Type</th>
                  <th>Subject</th>
                  <th>Applies to</th>
                  <th>Application must</th>
                  <th>Must not</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {instructions.map((item) => (
                  <tr
                    key={item.instruction_id}
                    className={selectedInstructionId === item.instruction_id ? 'selected' : ''}
                    onClick={() => setSelectedInstructionId(item.instruction_id)}
                  >
                    <td><KrTruthBadge item={item} /></td>
                    <td>{labelFromKey(item.instruction_type)}</td>
                    <td><strong>{item.subject}</strong><span>{item.source_record_type}</span></td>
                    <td>{safeText(item.template_key || item.curve_family || item.application_area)}</td>
                    <td>{item.must_do}</td>
                    <td>{safeText(item.must_not_do)}</td>
                    <td>{item.evidence_ref_count}</td>
                  </tr>
                ))}
                {!listLoading && instructions.length === 0 ? (
                  <tr><td colSpan={7}>No KR instructions match the current filters.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <KrInstructionDetailPanel detail={detail} loading={detailLoading} error={detailError} />
      </div>

      {curationError && !curationForm ? <p className="wlv-kr-error">{curationError}</p> : null}

      <section className="wlv-kr-decision-workbench" aria-label="Template decision inspection">
        <div className="wlv-kr-controls compact">
          <label>
            Template decision preview
            <select value={decisionTemplateKey} onChange={(event) => setDecisionTemplateKey(event.target.value)}>
              {templateOptions.map((template) => <option key={template} value={template}>{labelFromKey(template)}</option>)}
            </select>
          </label>
        </div>
        <TemplateDecisionPanel templateKey={decisionTemplateKey} />
      </section>

      {curationForm ? (
        <KrCurationModal
          form={curationForm}
          saving={curationSaving}
          error={curationError}
          onChange={setCurationForm}
          onCancel={() => { setCurationForm(null); setCurationError(null); }}
          onSave={saveCandidate}
        />
      ) : null}
    </section>
  );
}
