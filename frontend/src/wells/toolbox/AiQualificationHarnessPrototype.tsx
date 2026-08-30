import { useEffect, useMemo, useRef, useState } from 'react';
import type { ToolboxAiRevisionTool } from './toolboxAiRevision';
import { wlvApiBaseUrl } from '../../api/wlvBackendClient';

type Props = {
  tool: ToolboxAiRevisionTool;
  toolLabel: string;
  standardVersion: number;
  rules: Record<string, unknown> | null;
  deterministicProfile: Record<string, unknown> | null;
};

type EvidenceFile = {
  name: string;
  mime_type: string;
  size: number;
  content_base64: string;
};

type ProviderInfo = {
  configured: boolean;
  label: string;
  model: string;
  candidate_model?: string;
  judge_model?: string;
};

type Finding = {
  marker?: string;
  depth?: number | string | null;
  unit?: string | null;
  source?: string | null;
  location?: string | null;
  confidence?: string | number | null;
  notes?: string | null;
};

type Candidate = {
  run_id?: string;
  model?: { provider?: string; model?: string };
  findings?: Finding[];
  conclusion?: { status?: string; summary?: string };
  limitations?: string[];
  parse_error?: boolean;
  review_required?: boolean;
  review_reason?: string;
  raw_text?: string;
  parsed_candidate?: Record<string, unknown> | null;
  unresolved_evidence?: Array<Record<string, unknown>>;
  conflicts?: Array<Record<string, unknown>>;
  unresolved_evidence_count?: number;
  conflict_count?: number;
  provider_response_empty_text?: boolean;
  provider_response_envelope?: Record<string, unknown>;
};

type CostProjection = {
  output_tokens: number;
  cost_usd: number;
};

type EstimateRow = {
  provider: string;
  label: string;
  model: string;
  estimated_input_tokens: number;
  cost_low_usd: number | null;
  cost_high_usd: number | null;
  cost_projections?: CostProjection[];
  execution_output_policy?: string;
  known_max_output_tokens?: number | null;
  gemini_free_tier_possible?: boolean;
  gemini_free_tier_billed_cost_usd?: number | null;
};

type Estimate = {
  evidence_preparation: Array<Record<string, unknown>>;
  estimated_evidence_tokens: number;
  estimated_input_tokens_per_candidate: number;
  providers: EstimateRow[];
  estimated_total_low_usd: number;
  estimated_total_high_usd: number;
  total_cost_projections?: Array<{
    output_tokens_per_model: number;
    paid_equivalent_total_usd: number;
    total_if_gemini_free_usd: number;
  }>;
  execution_output_policy?: string;
};

const graphicsRiskFromPreparation = (items: Array<Record<string, unknown>>) => {
  const rows = items.map((item) => {
    const audit = item.graphics_audit;
    return audit && typeof audit === 'object' && !Array.isArray(audit)
      ? audit as Record<string, unknown>
      : {};
  });
  return {
    high: rows.filter((row) => String(row.risk_level ?? '') === 'high'),
    moderate: rows.filter((row) => String(row.risk_level ?? '') === 'moderate'),
  };
};

const graphicsWarningText = (items: Array<Record<string, unknown>>) => {
  const risk = graphicsRiskFromPreparation(items);
  if (risk.high.length) {
    return 'High graphical-content risk detected. Local deterministic screening does not interpret graphics and may omit visually important pages. Consider disabling deterministic pre-screening and sending the full document to the LLM.';
  }
  if (risk.moderate.length) {
    return 'Graphical content detected. Retained pages will be forwarded as original PDF pages for LLM visual review, but graphics on pages excluded by text/OCR ranking cannot be assessed locally.';
  }
  return '';
};

type ProgressEvent = {
  seq: number;
  message: string;
};

type ReconciledRow = {
  marker: string;
  byProvider: Record<string, Finding[]>;
  status: string;
};

const PROVIDERS = ['openai', 'anthropic', 'gemini'] as const;
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Claude',
  gemini: 'Gemini',
};

const fileToEvidence = async (file: File): Promise<EvidenceFile> => {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const stride = 0x8000;
  for (let i = 0; i < bytes.length; i += stride) {
    binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + stride, bytes.length)));
  }
  return {
    name: file.name,
    mime_type: file.type || 'application/octet-stream',
    size: file.size,
    content_base64: btoa(binary),
  };
};

const normalizeMarker = (value: unknown) =>
  String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/\bformation\b/g, '')
    .replace(/\bgroup\b/g, '')
    .replace(/\bmember\b/g, '')
    .replace(/\s+/g, ' ')
    .trim();

const depthKey = (finding: Finding) => {
  if (finding.depth == null || finding.depth === '') return '—';
  const n = Number(finding.depth);
  if (Number.isFinite(n)) return n.toFixed(1);
  return String(finding.depth).trim();
};

const money = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return '—';
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
};

const smallMuted = {
  fontSize: '10px',
  opacity: 0.76,
  lineHeight: 1.45,
} as const;

export default function AiQualificationHarnessPrototype({
  tool,
  toolLabel,
  standardVersion,
  rules,
  deterministicProfile,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const pollRef = useRef<number | null>(null);

  const [task, setTask] = useState('');
  const [evidenceFiles, setEvidenceFiles] = useState<EvidenceFile[]>([]);
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
  const [selectedProviders, setSelectedProviders] = useState<string[]>([]);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [errors, setErrors] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [deterministicEnabled, setDeterministicEnabled] = useState(true);
  const [preparing, setPreparing] = useState(false);
  const [preparation, setPreparation] = useState<Array<Record<string, unknown>>>([]);

  const candidatePackage = useMemo(() => ({
    schema_version: 'multiviewer_ai_candidate_package_v0_2',
    qualification_mode: 'discovery',
    test_case_id: `${tool}-standard-v${standardVersion}`,
    tool,
    tool_label: toolLabel,
    standard_version: standardVersion,
    ai_standard_rules: rules ?? {},
    deterministic_screening_enabled: deterministicEnabled,
    deterministic_screening_profile: deterministicProfile ?? {},
    task: task.trim() || `Discover all defensible findings relevant to the active ${toolLabel} AI standard.`,
  }), [deterministicEnabled, deterministicProfile, rules, standardVersion, task, tool, toolLabel]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/providers`)
      .then((response) => {
        if (!response.ok) throw new Error(`Provider status ${response.status}`);
        return response.json();
      })
      .then((body) => {
        if (cancelled) return;
        const next = (body?.providers ?? {}) as Record<string, ProviderInfo>;
        setProviders(next);
        setSelectedProviders(PROVIDERS.filter((provider) => next[provider]?.configured));
      })
      .catch((error) => {
        if (!cancelled) setMessage(`Provider status unavailable: ${String(error)}`);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => () => {
    if (pollRef.current != null) window.clearInterval(pollRef.current);
  }, []);

  const addFiles = async (files: FileList | File[]) => {
    const accepted = Array.from(files).filter((file) => {
      const lower = file.name.toLowerCase();
      return lower.endsWith('.pdf')
        || lower.endsWith('.txt')
        || lower.endsWith('.csv')
        || lower.endsWith('.json')
        || lower.endsWith('.md');
    });
    if (!accepted.length) {
      setMessage('Use PDF, TXT, CSV, JSON, or Markdown evidence files.');
      return;
    }
    try {
      const converted = await Promise.all(accepted.map(fileToEvidence));
      setEvidenceFiles((current) => {
        const map = new Map(current.map((item) => [item.name, item]));
        converted.forEach((item) => map.set(item.name, item));
        return Array.from(map.values());
      });
      setEstimate(null);
      setPreparation([]);
      setCandidates([]);
      setErrors([]);
      setMessage('');
    } catch (error) {
      setMessage(`Unable to read evidence: ${String(error)}`);
    }
  };

  const toggleProvider = (provider: string) => {
    setSelectedProviders((current) => current.includes(provider)
      ? current.filter((item) => item !== provider)
      : [...current, provider]);
    setEstimate(null);
  };

  const prepareEvidence = async () => {
    if (!evidenceFiles.length) return;
    setPreparing(true);
    setMessage('');
    try {
      const response = await fetch(`${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/prepare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_package: candidatePackage,
          evidence_files: evidenceFiles,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(String(body?.detail ?? `Preparation ${response.status}`));
      setPreparation(Array.isArray(body?.evidence_preparation) ? body.evidence_preparation : []);
      setEstimate(null);
    } catch (error) {
      setMessage(`Evidence preparation failed: ${String(error)}`);
    } finally {
      setPreparing(false);
    }
  };

  const estimateCost = async () => {
    if (!evidenceFiles.length || !selectedProviders.length) return;
    setEstimating(true);
    setMessage('');
    try {
      const response = await fetch(`${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/estimate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_package: candidatePackage,
          evidence_files: evidenceFiles,
          providers: selectedProviders,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(body?.detail ?? `Estimate failed (${response.status})`));
      }
      setEstimate(body as Estimate);
    } catch (error) {
      setEstimate(null);
      setMessage(String(error));
    } finally {
      setEstimating(false);
    }
  };

  const runCandidates = async () => {
    if (!evidenceFiles.length || !selectedProviders.length || running) return;

    let runPreparation = preparation;
    if (deterministicEnabled) {
      try {
        const prepResponse = await fetch(`${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/prepare`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            candidate_package: candidatePackage,
            evidence_files: evidenceFiles,
          }),
        });
        const prepBody = await prepResponse.json().catch(() => ({}));
        if (!prepResponse.ok) throw new Error(String(prepBody?.detail ?? `Preparation ${prepResponse.status}`));
        runPreparation = Array.isArray(prepBody?.evidence_preparation) ? prepBody.evidence_preparation : [];
        setPreparation(runPreparation);

        const warning = graphicsWarningText(runPreparation);
        if (graphicsRiskFromPreparation(runPreparation).high.length) {
          const proceed = window.confirm(
            `${warning}\n\nContinue with deterministic pre-screening?\n\nChoose Cancel to return and switch the pre-screen off so the full document is sent to the LLM.`,
          );
          if (!proceed) {
            setMessage('Run cancelled. Disable Deterministic pre-screen to send the full document to the LLM.');
            return;
          }
        } else if (warning) {
          setMessage(warning);
        }
      } catch (error) {
        setMessage(`Evidence preparation failed: ${String(error)}`);
        return;
      }
    }

    setRunning(true);
    setCandidates([]);
    setErrors([]);
    setEvents([]);
    if (!graphicsWarningText(runPreparation)) setMessage('');
    try {
      const response = await fetch(`${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/run/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_package: candidatePackage,
          answer_key: {},
          evidence_files: evidenceFiles,
          providers: selectedProviders,
          judges: [],
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(body?.detail ?? `Run failed (${response.status})`));
      const jobId = String(body.job_id);

      if (pollRef.current != null) window.clearInterval(pollRef.current);
      const poll = async () => {
        try {
          const statusResponse = await fetch(
            `${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/run/status/${jobId}`,
          );
          const statusBody = await statusResponse.json().catch(() => ({}));
          if (!statusResponse.ok) throw new Error(String(statusBody?.detail ?? 'Status request failed'));
          setEvents(Array.isArray(statusBody.events) ? statusBody.events : []);

          if (statusBody.status === 'completed') {
            if (pollRef.current != null) window.clearInterval(pollRef.current);
            pollRef.current = null;
            const result = statusBody.result ?? {};
            setCandidates(Array.isArray(result.candidates) ? result.candidates : []);
            setErrors(Array.isArray(result.errors) ? result.errors : []);
            setRunning(false);
          } else if (statusBody.status === 'failed') {
            if (pollRef.current != null) window.clearInterval(pollRef.current);
            pollRef.current = null;
            setRunning(false);
            setMessage(String(statusBody.error ?? 'Discovery run failed.'));
          }
        } catch (error) {
          if (pollRef.current != null) window.clearInterval(pollRef.current);
          pollRef.current = null;
          setRunning(false);
          setMessage(String(error));
        }
      };
      await poll();
      pollRef.current = window.setInterval(poll, 750);
    } catch (error) {
      setRunning(false);
      setMessage(String(error));
    }
  };

  const reconciled = useMemo<ReconciledRow[]>(() => {
    const groups = new Map<string, ReconciledRow>();

    candidates.forEach((candidate) => {
      const provider = String(candidate.model?.provider ?? 'unknown');
      (candidate.findings ?? []).forEach((finding) => {
        const marker = String(finding.marker ?? '').trim();
        if (!marker) return;
        const key = normalizeMarker(marker) || marker.toLowerCase();
        const existing = groups.get(key) ?? {
          marker,
          byProvider: {},
          status: 'Unique',
        };
        existing.byProvider[provider] = [...(existing.byProvider[provider] ?? []), finding];
        groups.set(key, existing);
      });
    });

    return Array.from(groups.values()).map((row) => {
      const present = Object.keys(row.byProvider);
      const depthSets = present.map((provider) =>
        Array.from(new Set(row.byProvider[provider].map(depthKey))).sort().join('|'),
      );
      const sameDepth = depthSets.length > 1 && depthSets.every((item) => item === depthSets[0]);

      let status = 'Unique';
      if (present.length === selectedProviders.length && present.length > 1) {
        status = sameDepth ? 'Consensus' : 'Conflict';
      } else if (present.length >= 2) {
        status = sameDepth ? `${present.length}/${selectedProviders.length}` : 'Conflict';
      }
      return { ...row, status };
    }).sort((a, b) => {
      const rank: Record<string, number> = { Conflict: 0, Unique: 1, Consensus: 3 };
      const ar = rank[a.status] ?? 2;
      const br = rank[b.status] ?? 2;
      return ar - br || a.marker.localeCompare(b.marker);
    });
  }, [candidates, selectedProviders.length]);

  const providerCell = (row: ReconciledRow, provider: string) => {
    const findings = row.byProvider[provider] ?? [];
    if (!findings.length) return <span style={{ opacity: 0.45 }}>—</span>;
    return (
      <div style={{ display: 'grid', gap: '3px' }}>
        {findings.map((finding, index) => (
          <div key={`${provider}-${index}`}>
            <strong>{depthKey(finding)}{finding.unit ? ` ${finding.unit}` : ''}</strong>
            {finding.confidence ? <span> · {String(finding.confidence)}</span> : null}
            {finding.location ? <div style={{ opacity: 0.72 }}>{String(finding.location)}</div> : null}
          </div>
        ))}
      </div>
    );
  };

  const totalCost = estimate
    ? `${money(estimate.estimated_total_low_usd)}–${money(estimate.estimated_total_high_usd)}`
    : 'Not estimated';

  return (
    <div style={{
      display: 'grid',
      gridTemplateRows: 'auto auto auto minmax(0, 1fr)',
      gap: '8px',
      width: '100%',
      maxWidth: '1120px',
      margin: '0 auto',
      minHeight: 0,
      height: '100%',
      overflow: 'hidden',
    }}>
      <section className="wlv-metadata-tool__drop-panel" style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1.25fr) minmax(320px, 0.75fr)',
        gap: '10px',
        alignItems: 'stretch',
        padding: '9px 10px',
      }}>
        <div style={{ display: 'grid', gap: '5px', minWidth: 0 }}>
          <div className="wlv-metadata-tool__drop-copy">
            <strong>1 · Evidence</strong>
            <span>Introduce the source evidence. No LLM/API call is made here.</span>
          </div>
          <div
            onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
            onDragOver={(event) => { event.preventDefault(); setDragActive(true); }}
            onDragLeave={(event) => { event.preventDefault(); setDragActive(false); }}
            onDrop={(event) => {
              event.preventDefault();
              setDragActive(false);
              void addFiles(event.dataTransfer.files);
            }}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: dragActive ? '1px solid #8aa4c2' : '1px dashed #4a5868',
              borderRadius: '5px',
              minHeight: '52px',
              padding: '8px 10px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              background: '#111820',
            }}
          >
            <div style={{ display: 'grid', gap: '2px', minWidth: 0 }}>
              <strong style={{ fontSize: '10px' }}>
                {evidenceFiles.length ? `${evidenceFiles.length} evidence file(s)` : 'Drop evidence here'}
              </strong>
              <span style={{ ...smallMuted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {evidenceFiles.length
                  ? evidenceFiles.map((item) => `${item.name} · ${(item.size / 1024 / 1024).toFixed(1)} MB`).join('  •  ')
                  : 'or click to choose PDF, TXT, CSV, JSON, or Markdown'}
              </span>
            </div>
            <span style={{ fontSize: '9px', opacity: 0.72 }}>Add Files</span>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.txt,.csv,.json,.md"
            style={{ display: 'none' }}
            onChange={(event) => {
              if (event.target.files) void addFiles(event.target.files);
              event.currentTarget.value = '';
            }}
          />
        </div>
        <label style={{ display: 'grid', gap: '5px', minWidth: 0, fontSize: '10px' }}>
          <div><strong>Task / Objective</strong><span style={{ opacity: 0.6 }}> · Optional</span></div>
          <textarea
            value={task}
            rows={3}
            onChange={(event) => { setTask(event.target.value); setEstimate(null); }}
            placeholder={`Leave blank to use the active ${toolLabel} AI standard directly.`}
            style={{
              width: '100%', height: '52px', boxSizing: 'border-box', resize: 'none',
              border: '1px solid #374454', borderRadius: '5px', background: '#10161e',
              color: '#dbe3eb', padding: '8px 9px', fontFamily: 'inherit',
              fontSize: '10px', lineHeight: 1.35,
            }}
          />
        </label>
      </section>

      <section className="wlv-metadata-tool__drop-panel" style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) auto',
        alignItems: 'center',
        gap: '8px 12px',
        padding: '8px 10px',
      }}>
        <div className="wlv-metadata-tool__drop-copy">
          <strong>2 · Deterministic Parsing</strong>
          <span>
            {deterministicEnabled
              ? `${String(deterministicProfile?.profile_name ?? 'Active screening profile')} · local processing only`
              : 'Bypassed · full extracted evidence will continue to the LLM stage'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '10px', fontWeight: 700 }}>
            <input
              type="checkbox"
              checked={deterministicEnabled}
              disabled={running || estimating || preparing}
              onChange={(event) => {
                setDeterministicEnabled(event.target.checked);
                setPreparation([]);
                setEstimate(null);
              }}
            />
            Deterministic pre-screen
          </label>
          <button
            type="button"
            onClick={() => void prepareEvidence()}
            disabled={!evidenceFiles.length || preparing || running || estimating}
          >
            {preparing ? 'Preparing…' : deterministicEnabled ? 'Parse Evidence' : 'Prepare Direct Evidence'}
          </button>
        </div>
        {preparation.length ? (
          <div style={{
            gridColumn: '1 / -1',
            display: 'flex',
            gap: '12px',
            alignItems: 'center',
            flexWrap: 'wrap',
            borderTop: '1px solid #2e3945',
            paddingTop: '5px',
            fontSize: '9px',
          }}>
            {preparation.map((item) => (
              <span key={String(item.name)}>
                <strong>{String(item.name)}</strong>
                {' · '}
                {item.total_pages != null ? `${String(item.total_pages)} pages` : 'text'}
                {' → '}
                {item.selected_page_count != null ? `${String(item.selected_page_count)} forwarded` : 'forwarded'}
                {' · '}
                ~{Number(item.estimated_tokens ?? 0).toLocaleString()} tokens
                {(() => {
                  const audit = item.graphics_audit;
                  if (!audit || typeof audit !== 'object' || Array.isArray(audit)) return null;
                  const risk = String((audit as Record<string, unknown>).risk_level ?? 'none');
                  return risk === 'none' ? null : <>{' · '}graphics risk: <strong>{risk.toUpperCase()}</strong></>;
                })()}
              </span>
            ))}
          </div>
        ) : null}
        {deterministicEnabled && graphicsWarningText(preparation) ? (
          <div style={{
            gridColumn: '1 / -1',
            border: `1px solid ${graphicsRiskFromPreparation(preparation).high.length ? '#a8662c' : '#5b6774'}`,
            borderRadius: '5px',
            padding: '6px 8px',
            fontSize: '9px',
            lineHeight: 1.4,
            color: graphicsRiskFromPreparation(preparation).high.length ? '#ffc27d' : '#c7d0da',
            background: '#151b22',
          }}>
            <strong>Visual evidence warning · </strong>{graphicsWarningText(preparation)}
          </div>
        ) : null}
      </section>

      <section className="wlv-metadata-tool__drop-panel" style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) auto',
        gap: '8px 12px',
        alignItems: 'center',
        padding: '8px 10px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px', minWidth: 0, flexWrap: 'wrap' }}>
          <strong style={{ fontSize: '10px', marginRight: '2px' }}>3 · LLM Evaluation</strong>
          {PROVIDERS.map((provider) => {
            const info = providers[provider];
            const enabled = selectedProviders.includes(provider);
            return (
              <label key={provider} style={{
                border: enabled ? '1px solid #536579' : '1px solid #394654',
                borderRadius: '5px', padding: '5px 7px', display: 'flex',
                alignItems: 'center', gap: '6px', cursor: info?.configured ? 'pointer' : 'not-allowed',
                opacity: info?.configured ? 1 : 0.45, minWidth: '142px',
                background: enabled ? '#18212b' : '#141b23',
              }}>
                <input type="checkbox" checked={enabled} disabled={!info?.configured || running} onChange={() => toggleProvider(provider)} />
                <span style={{ display: 'grid', gap: '1px', minWidth: 0 }}>
                  <strong style={{ fontSize: '10px' }}>{info?.label ?? PROVIDER_LABELS[provider]}</strong>
                  <span style={{ fontSize: '9px', opacity: 0.7, whiteSpace: 'nowrap' }}>
                    {info?.candidate_model ?? info?.model ?? 'Not configured'}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px', whiteSpace: 'nowrap' }}>
          <button type="button" onClick={() => void estimateCost()} disabled={!evidenceFiles.length || !selectedProviders.length || estimating || running}>
            {estimating ? 'Estimating…' : 'Estimate Cost'}
          </button>
          <div style={{ borderLeft: '1px solid #394654', paddingLeft: '9px', minWidth: '118px', display: 'grid', gap: '1px' }}>
            <span style={{ fontSize: '9px', opacity: 0.65 }}>Estimated run</span>
            <strong style={{ fontSize: '11px' }}>{totalCost}</strong>
          </div>
          <button type="button" onClick={() => void runCandidates()} disabled={!evidenceFiles.length || !selectedProviders.length || running}>
            {running ? 'Running…' : 'Run Evaluation'}
          </button>
        </div>
        {estimate ? (
          <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', paddingTop: '5px', borderTop: '1px solid #2e3945', fontSize: '9px' }}>
            <span>~{estimate.estimated_evidence_tokens.toLocaleString()} evidence tokens to each model</span>
            <span><strong>Expected 8k–16k output:</strong> {money(estimate.estimated_total_low_usd)}–{money(estimate.estimated_total_high_usd)}</span>
            {estimate.total_cost_projections?.map((projection) => (
              <span key={projection.output_tokens_per_model}>
                <strong>{Math.round(projection.output_tokens_per_model / 1000)}k:</strong>
                {' '}
                {money(projection.paid_equivalent_total_usd)}
                {projection.total_if_gemini_free_usd !== projection.paid_equivalent_total_usd
                  ? ` · ${money(projection.total_if_gemini_free_usd)} if Gemini Free`
                  : ''}
              </span>
            ))}
            {estimate.providers.map((row) => (
              <span key={row.provider}>
                <strong>{row.label}</strong>
                {' '}
                {row.gemini_free_tier_possible
                  ? `Free tier: $0 billed if eligible · paid equivalent ${money(row.cost_low_usd)}–${money(row.cost_high_usd)}`
                  : `${money(row.cost_low_usd)}–${money(row.cost_high_usd)}`}
              </span>
            ))}
          </div>
        ) : null}
        {candidates.length ? (
          <div style={{
            gridColumn: '1 / -1',
            display: 'grid',
            gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
            gap: '6px',
            borderTop: '1px solid #2e3945',
            paddingTop: '6px',
          }}>
            {candidates.map((candidate) => {
              const provider = String(candidate.model?.provider ?? '');
              const label = PROVIDER_LABELS[provider] ?? provider;
              const findingCount = candidate.findings?.length ?? 0;
              return (
                <details
                  key={candidate.run_id ?? provider}
                  style={{
                    border: candidate.review_required ? '1px solid #7a6238' : '1px solid #33404d',
                    borderRadius: '5px',
                    padding: '5px 7px',
                    minWidth: 0,
                    background: '#121922',
                  }}
                >
                  <summary style={{ cursor: 'pointer', fontSize: '9px', fontWeight: 700 }}>
                    {label} · {findingCount} findings
                    {candidate.unresolved_evidence_count ? ` · ${candidate.unresolved_evidence_count} unresolved` : ''}
                    {candidate.conflict_count ? ` · ${candidate.conflict_count} conflicts` : ''}
                    {candidate.review_required ? ' · Review required' : ''}
                  </summary>
                  <div style={{ display: 'grid', gap: '6px', marginTop: '6px', fontSize: '9px' }}>
                    {candidate.review_reason ? (
                      <div><strong>Review reason:</strong> {candidate.review_reason}</div>
                    ) : null}
                    {candidate.unresolved_evidence?.length ? (
                      <div>
                        <strong>Unresolved evidence</strong>
                        <pre style={{
                          margin: '3px 0 0',
                          maxHeight: '140px',
                          overflow: 'auto',
                          whiteSpace: 'pre-wrap',
                          overflowWrap: 'anywhere',
                          background: '#0d131a',
                          border: '1px solid #2e3945',
                          borderRadius: '4px',
                          padding: '6px',
                          fontSize: '8px',
                        }}>
                          {JSON.stringify(candidate.unresolved_evidence, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                    {candidate.provider_response_envelope ? (
                      <div>
                        <strong>Provider response envelope</strong>
                        <pre style={{
                          margin: '3px 0 0',
                          maxHeight: '220px',
                          overflow: 'auto',
                          whiteSpace: 'pre-wrap',
                          overflowWrap: 'anywhere',
                          background: '#0d131a',
                          border: '1px solid #2e3945',
                          borderRadius: '4px',
                          padding: '6px',
                          fontSize: '8px',
                        }}>
                          {JSON.stringify(candidate.provider_response_envelope, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                    {candidate.conflicts?.length ? (
                      <div>
                        <strong>Conflicts</strong>
                        <pre style={{
                          margin: '3px 0 0',
                          maxHeight: '140px',
                          overflow: 'auto',
                          whiteSpace: 'pre-wrap',
                          overflowWrap: 'anywhere',
                          background: '#0d131a',
                          border: '1px solid #2e3945',
                          borderRadius: '4px',
                          padding: '6px',
                          fontSize: '8px',
                        }}>
                          {JSON.stringify(candidate.conflicts, null, 2)}
                        </pre>
                      </div>
                    ) : null}
                    <div>
                      <strong>Parsed candidate</strong>
                      <pre style={{
                        margin: '3px 0 0',
                        maxHeight: '180px',
                        overflow: 'auto',
                        whiteSpace: 'pre-wrap',
                        overflowWrap: 'anywhere',
                        background: '#0d131a',
                        border: '1px solid #2e3945',
                        borderRadius: '4px',
                        padding: '6px',
                        fontSize: '8px',
                      }}>
                        {JSON.stringify(candidate.parsed_candidate, null, 2)}
                      </pre>
                    </div>
                    <div>
                      <strong>Raw provider response</strong>
                      <pre style={{
                        margin: '3px 0 0',
                        maxHeight: '180px',
                        overflow: 'auto',
                        whiteSpace: 'pre-wrap',
                        overflowWrap: 'anywhere',
                        background: '#0d131a',
                        border: '1px solid #2e3945',
                        borderRadius: '4px',
                        padding: '6px',
                        fontSize: '8px',
                      }}>
                        {candidate.raw_text || 'No raw response preserved.'}
                      </pre>
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
        ) : null}

        {(events.length || errors.length || message) ? (
          <div style={{ gridColumn: '1 / -1', maxHeight: '70px', overflowY: 'auto', borderTop: '1px solid #2e3945', paddingTop: '5px', display: 'grid', gap: '3px', fontSize: '9px', lineHeight: 1.35 }}>
            {events.slice(-6).map((event) => <div key={event.seq}>{event.message}</div>)}
            {errors.map((item, index) => (
              <div key={`error-${index}`}><strong>{PROVIDER_LABELS[String(item.provider)] ?? String(item.provider)}</strong>{' · '}{String(item.message ?? 'Provider failed')}</div>
            ))}
            {message ? <div>{message}</div> : null}
          </div>
        ) : null}
      </section>

      <section className="wlv-metadata-tool__drop-panel" style={{
        minHeight: 0, overflow: 'hidden', display: 'grid',
        gridTemplateRows: 'auto minmax(0, 1fr)', padding: 0,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', padding: '8px 10px', borderBottom: '1px solid #303b47' }}>
          <div className="wlv-metadata-tool__drop-copy" style={{ minWidth: 0 }}>
            <strong>4 · Discovery Comparison</strong>
            <span>Consensus, unique findings and conflicts are reconciled locally. No additional LLM call.</span>
          </div>
          {candidates.length ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', whiteSpace: 'nowrap', fontSize: '9px' }}>
              <span><strong>{reconciled.filter((row) => row.status === 'Consensus').length}</strong> consensus</span>
              <span><strong>{reconciled.filter((row) => row.status === 'Conflict').length}</strong> conflicts</span>
              <span><strong>{reconciled.filter((row) => row.status === 'Unique').length}</strong> unique</span>
            </div>
          ) : null}
        </div>
        {!candidates.length ? (
          <div style={{ minHeight: '150px', display: 'grid', placeItems: 'center', padding: '18px', fontSize: '10px', opacity: 0.62 }}>
            Add evidence, choose the deterministic path, then run the LLM evaluation.
          </div>
        ) : (
          <div className="wlv-metadata-tool__table-wrap" style={{ minHeight: 0, height: '100%', overflow: 'auto', border: 0, borderRadius: 0 }}>
            <table className="wlv-ftm-tool__table">
              <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
                <tr><th>Finding</th><th>OpenAI</th><th>Claude</th><th>Gemini</th><th>Status</th></tr>
              </thead>
              <tbody>
                {reconciled.map((row) => (
                  <tr key={normalizeMarker(row.marker)}>
                    <td><strong>{row.marker}</strong></td>
                    <td>{providerCell(row, 'openai')}</td>
                    <td>{providerCell(row, 'anthropic')}</td>
                    <td>{providerCell(row, 'gemini')}</td>
                    <td><strong>{row.status}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
