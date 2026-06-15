import { useEffect, useMemo, useState } from 'react';

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

type KrStatusFilter = 'all' | 'runtime' | 'production';
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

function instructionSearchText(item: KrInstructionSummary): string {
  return [
    item.instruction_id,
    item.source_record_type,
    item.instruction_type,
    item.status,
    item.subject,
    item.application_area,
    item.template_key,
    item.track_id,
    item.curve_family,
    item.canonical_curve_id,
    item.alias,
    item.must_do,
    item.must_not_do,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

function uniqueSorted(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort((a, b) => a.localeCompare(b));
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

export function KrManagedInstructionsWorkbench() {
  const [summary, setSummary] = useState<KrInstructionSummaryResponse | null>(null);
  const [instructions, setInstructions] = useState<KrInstructionSummary[]>([]);
  const [selectedInstructionId, setSelectedInstructionId] = useState<string | null>(null);
  const [detail, setDetail] = useState<KrInstructionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [instructionType, setInstructionType] = useState<KrInstructionTypeFilter>('all');
  const [truthFilter, setTruthFilter] = useState<KrStatusFilter>('all');
  const [templateFilter, setTemplateFilter] = useState('all');
  const [curveFamilyFilter, setCurveFamilyFilter] = useState('all');
  const [decisionTemplateKey, setDecisionTemplateKey] = useState('open_hole_triple_combo');

  const loadInstructions = () => {
    setLoading(true);
    setError(null);
    void Promise.all([
      fetchKrJson<KrInstructionSummaryResponse>('/api/wlv/knowledge/instructions/summary'),
      fetchKrJson<KrInstructionListResponse>('/api/wlv/knowledge/instructions?limit=500'),
    ])
      .then(([nextSummary, list]) => {
        setSummary(nextSummary);
        setInstructions(list.instructions ?? []);
        setSelectedInstructionId((current) => (
          current && list.instructions.some((item) => item.instruction_id === current)
            ? current
            : list.instructions[0]?.instruction_id ?? null
        ));
      })
      .catch((caught) => {
        setSummary(null);
        setInstructions([]);
        setSelectedInstructionId(null);
        setError(caught instanceof Error ? caught.message : 'KR instruction service unavailable');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadInstructions();
  }, []);

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

  const filteredInstructions = useMemo(() => {
    const q = search.trim().toLowerCase();
    return instructions.filter((item) => {
      if (instructionType !== 'all' && item.instruction_type !== instructionType) return false;
      if (truthFilter === 'runtime' && !item.runtime_eligible) return false;
      if (truthFilter === 'production' && !item.production_eligible) return false;
      if (templateFilter !== 'all' && item.template_key !== templateFilter) return false;
      if (curveFamilyFilter !== 'all' && item.curve_family !== curveFamilyFilter) return false;
      if (q && !instructionSearchText(item).includes(q)) return false;
      return true;
    });
  }, [curveFamilyFilter, instructions, instructionType, search, templateFilter, truthFilter]);

  return (
    <section className="wlv-kr-workbench" aria-label="Knowledge Repository managed instructions">
      <header className="wlv-kr-header">
        <div>
          <span className="wlv-page-kicker">Knowledge Repository</span>
          <h1>Managed Instructions</h1>
          <p>Approved KR instructions are the application truth the WLV backend must follow.</p>
        </div>
        <button type="button" className="wlv-kr-outline-button" onClick={loadInstructions} disabled={loading}>
          Refresh
        </button>
      </header>

      {error ? <p className="wlv-kr-error">{error}</p> : null}

      <section className="wlv-kr-summary-grid" aria-label="KR instruction summary">
        <KrCountCard label="Approved live instructions" value={instructions.length} />
        <KrCountCard label="Runtime eligible" value={summary?.runtime_eligible_count ?? '—'} />
        <KrCountCard label="Production eligible" value={summary?.production_eligible_count ?? '—'} />
        <KrCountCard label="Evidence records" value={summary?.evidence_record_count ?? '—'} />
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
            <h2>Approved application instructions</h2>
            <span>{loading ? 'Loading…' : `${filteredInstructions.length} shown`}</span>
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
                {filteredInstructions.map((item) => (
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
                {!loading && filteredInstructions.length === 0 ? (
                  <tr><td colSpan={7}>No approved KR instructions match the current filters.</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <KrInstructionDetailPanel detail={detail} loading={detailLoading} error={detailError} />
      </div>

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
    </section>
  );
}
