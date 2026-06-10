import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchWlvJson } from '../../api/wlvBackendClient';

type SourceRepositoryRecord = {
  repository_id: string;
  name: string;
  root_path: string;
  include_subfolders: boolean;
  status: string;
  last_scan_scope?: string | null;
  file_count: number;
  well_log_candidate_count: number;
  raster_candidate_count: number;
  document_candidate_count: number;
  tabular_candidate_count: number;
  unknown_file_count: number;
  review_required_count: number;
};

type ResolvedField = {
  value?: string | null;
  source?: string;
  confidence?: string;
  review_required?: boolean;
};

type QaqcStatus = {
  status?: string;
  severity?: string;
  check_count?: number;
  warning_count?: number;
  failure_count?: number;
  review_required?: boolean;
  messages?: string[];
};

type SourceFileCandidate = {
  source_file_id: string;
  repository_id: string;
  file_name: string;
  relative_path: string;
  detected_file_type: string;
  candidate_role: string;
  parser_status: string;
  review_required: boolean;
  registration_status?: string | null;
  managed_well_id?: string | null;
  managed_well_name?: string | null;
  wmdp_state?: string | null;
  wdv_state?: string | null;
  registered_product_count?: number;
  registered_curve_count?: number;
  parsed_metadata?: {
    log_header?: { curve_count?: number | null } | null;
    curve_headers?: Array<{ mnemonic?: string | null }> | null;
  } | null;
  resolved_metadata?: {
    well_name?: ResolvedField;
    uwi?: ResolvedField;
    operator?: ResolvedField;
    field?: ResolvedField;
    review_required?: boolean;
    warning_count?: number;
  } | null;
  qaqc_status?: QaqcStatus;
};

type WorkbenchSummary = {
  repository_count: number;
  file_count: number;
  well_log_candidate_count: number;
  raster_candidate_count: number;
  document_candidate_count: number;
  tabular_candidate_count: number;
  unknown_file_count: number;
  review_required_count: number;
};

type SourceIntakeWorkbenchResponse = {
  ok: boolean;
  conversion_step_enabled: boolean;
  reserved_future_representation_step: boolean;
  workflow_steps: string[];
  summary: WorkbenchSummary;
  repositories: SourceRepositoryRecord[];
  candidates: SourceFileCandidate[];
};

type RegisterResponse = {
  registered_count: number;
  skipped_count: number;
  results: Array<{
    candidate_id: string;
    status: string;
    reason?: string | null;
    managed_well_id?: string | null;
    well_name?: string | null;
  }>;
  workbench?: SourceIntakeWorkbenchResponse | null;
};

type ScanResponse = {
  ok: boolean;
  scan_scope: string;
  file_count: number;
  repository: SourceRepositoryRecord;
  candidates: SourceFileCandidate[];
};

const WORKFLOW_LABELS = [
  'Search & Discover',
  'Categorize',
  'QAQC',
  'Register to Managed Well Inventory',
  'Stage in WMDP',
  'Load selected data to WDV',
];

function labelize(value?: string | null): string {
  if (!value) return '—';
  return value.replace(/_/g, ' ');
}

function statusClass(value?: string | null): string {
  const normalized = (value ?? '').toLowerCase();
  if (normalized.includes('fail') || normalized.includes('error')) return 'is-error';
  if (normalized.includes('review') || normalized.includes('warning')) return 'is-warning';
  if (normalized.includes('pass') || normalized.includes('parsed') || normalized.includes('staged')) return 'is-ok';
  return '';
}

function candidateIsRegistered(candidate: SourceFileCandidate): boolean {
  return candidate.registration_status === 'registered' || candidate.wmdp_state === 'staged_in_wmdp';
}

function candidateCurveCount(candidate: SourceFileCandidate): number {
  const explicitCount = candidate.parsed_metadata?.log_header?.curve_count;
  if (typeof explicitCount === 'number') return explicitCount;
  return candidate.parsed_metadata?.curve_headers?.length ?? 0;
}

function candidateIsRegisterable(candidate: SourceFileCandidate): boolean {
  if (candidateIsRegistered(candidate)) return false;
  const roleOk = candidate.candidate_role === 'well_log_candidate';
  const parserOk = candidate.parser_status === 'parsed' || candidate.parser_status === 'parsed_with_warnings';
  const qaqc = candidate.qaqc_status;
  const qaqcOk = qaqc?.status === 'pass' || qaqc?.status === 'warning' || qaqc?.status === 'review_required';
  const noFailures = (qaqc?.failure_count ?? 0) === 0;
  const wellName = candidate.resolved_metadata?.well_name?.value;
  return Boolean(roleOk && parserOk && qaqcOk && noFailures && wellName);
}

function SummaryTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="wlv-si-summary-tile">
      <span className="wlv-si-summary-tile__value">{value}</span>
      <span className="wlv-si-summary-tile__label">{label}</span>
    </div>
  );
}

export function SourceIntakeWorkbench() {
  const [workbench, setWorkbench] = useState<SourceIntakeWorkbenchResponse | null>(null);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<string>('');
  const [sourceName, setSourceName] = useState('');
  const [sourcePath, setSourcePath] = useState('');
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(new Set());
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string>('');

  const repositories = workbench?.repositories ?? [];
  const candidates = workbench?.candidates ?? [];
  const summary = workbench?.summary;

  const selectedRepository = useMemo(
    () => repositories.find((repo) => repo.repository_id === selectedRepositoryId) ?? repositories[0],
    [repositories, selectedRepositoryId],
  );

  const visibleCandidates = useMemo(() => {
    if (!selectedRepository?.repository_id) return candidates;
    return candidates.filter((candidate) => candidate.repository_id === selectedRepository.repository_id);
  }, [candidates, selectedRepository]);

  const visibleCurveCount = useMemo(
    () => visibleCandidates.reduce((total, candidate) => total + candidateCurveCount(candidate), 0),
    [visibleCandidates],
  );

  const selectedRegisterableCount = visibleCandidates.filter(
    (candidate) => selectedCandidateIds.has(candidate.source_file_id) && candidateIsRegisterable(candidate),
  ).length;

  const loadWorkbench = useCallback(async () => {
    const data = await fetchWlvJson<SourceIntakeWorkbenchResponse>('/api/wlv/source-intake/workbench');
    setWorkbench(data);
    setSelectedRepositoryId((current) => {
      if (current && data.repositories.some((repo) => repo.repository_id === current)) {
        return current;
      }
      return data.repositories[0]?.repository_id || '';
    });
    setSelectedCandidateIds((current) => {
      const validIds = new Set(data.candidates.map((candidate) => candidate.source_file_id));
      return new Set([...current].filter((candidateId) => validIds.has(candidateId)));
    });
  }, []);

  useEffect(() => {
    setBusyAction('refresh');
    loadWorkbench()
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Unable to load Source Intake workbench.'))
      .finally(() => setBusyAction(null));
  }, [loadWorkbench]);

  const runAction = async (action: string, operation: () => Promise<void>) => {
    setBusyAction(action);
    setError('');
    setMessage('');
    try {
      await operation();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  };

  const handleCreateRepository = () => runAction('create-repository', async () => {
    const trimmedPath = sourcePath.trim();
    if (!trimmedPath) {
      throw new Error('Enter a source folder path before registering a repository.');
    }
    const repository = await fetchWlvJson<SourceRepositoryRecord>('/api/wlv/source-intake/repositories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: sourceName.trim() || undefined,
        root_path: trimmedPath,
        include_subfolders: includeSubfolders,
      }),
    });
    setSelectedRepositoryId(repository.repository_id);
    setMessage(`Registered source repository: ${repository.name}`);
    await loadWorkbench();
  });

  const handleScan = () => runAction('scan', async () => {
    const repositoryId = selectedRepository?.repository_id;
    if (!repositoryId) {
      throw new Error('Select a source repository before scanning.');
    }
    const scan = await fetchWlvJson<ScanResponse>(
      `/api/wlv/source-intake/repositories/${encodeURIComponent(repositoryId)}/scan`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_subfolders: includeSubfolders }),
      },
    );
    setMessage(`Scan completed: ${scan.file_count} files · ${labelize(scan.scan_scope)}`);
    await loadWorkbench();
  });

  const handleRefresh = () => runAction('refresh', async () => {
    await loadWorkbench();
    setMessage('Source Intake workbench refreshed from backend.');
  });

  const handleClear = () => runAction('clear', async () => {
    const response = await fetchWlvJson<{ workbench: SourceIntakeWorkbenchResponse; message?: string }>(
      '/api/wlv/source-intake/workbench/clear',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repository_id: selectedRepository?.repository_id ?? null }),
      },
    );
    setSelectedCandidateIds(new Set());
    setWorkbench(response.workbench);
    setMessage(response.message ?? 'Cleared active Source Intake selection. Backend records were not deleted.');
  });

  const handleRegister = () => runAction('register', async () => {
    const candidateIds = [...selectedCandidateIds].filter((candidateId) => {
      const candidate = candidates.find((item) => item.source_file_id === candidateId);
      return candidate ? candidateIsRegisterable(candidate) : false;
    });
    if (candidateIds.length === 0) {
      throw new Error('Select at least one eligible well log candidate before registering.');
    }
    const response = await fetchWlvJson<RegisterResponse>('/api/wlv/source-intake/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        candidate_ids: candidateIds,
        approval: {
          approved_by: 'user',
          approval_note: 'Registered from WLV Source Intake workbench shell',
        },
      }),
    });
    if (response.workbench) {
      setWorkbench(response.workbench);
    } else {
      await loadWorkbench();
    }
    setSelectedCandidateIds(new Set());
    setMessage(`Registered ${response.registered_count}; skipped ${response.skipped_count}.`);
  });

  const toggleCandidate = (candidateId: string) => {
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      if (next.has(candidateId)) {
        next.delete(candidateId);
      } else {
        next.add(candidateId);
      }
      return next;
    });
  };

  const toggleAllVisibleEligible = () => {
    const eligibleIds = visibleCandidates.filter(candidateIsRegisterable).map((candidate) => candidate.source_file_id);
    const allSelected = eligibleIds.length > 0 && eligibleIds.every((candidateId) => selectedCandidateIds.has(candidateId));
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      eligibleIds.forEach((candidateId) => {
        if (allSelected) next.delete(candidateId);
        else next.add(candidateId);
      });
      return next;
    });
  };

  return (
    <section className="wlv-source-intake" aria-label="WLV Source Intake workbench">
      <header className="wlv-source-intake__header">
        <div>
          <p className="wlv-source-intake__eyebrow">Well Data Source Intake</p>
          <h1>Source Intake</h1>
          <p className="wlv-source-intake__subtitle">
            Search, discover, categorize, QAQC, and register well-log source data into the Managed Well Inventory.
          </p>
        </div>
        <div className="wlv-source-intake__header-actions">
          <button type="button" className="wlv-si-button" onClick={handleRefresh} disabled={Boolean(busyAction)}>
            Refresh
          </button>
          <button type="button" className="wlv-si-button" onClick={handleClear} disabled={Boolean(busyAction)}>
            Clear Selection
          </button>
        </div>
      </header>

      <ol className="wlv-si-workflow" aria-label="Source Intake workflow">
        {WORKFLOW_LABELS.map((step, index) => (
          <li key={step} className={index === WORKFLOW_LABELS.length - 1 ? 'is-reserved' : ''}>
            <span>{index + 1}</span>
            {step}
          </li>
        ))}
      </ol>

      <div className="wlv-si-layout">
        <aside className="wlv-si-card wlv-si-card--setup">
          <div className="wlv-si-card__header">
            <h2>Search & Discover</h2>
            <span className="wlv-si-pill wlv-si-pill--reserved">Representation space reserved</span>
          </div>

          <label className="wlv-si-field">
            <span>Repository name</span>
            <input value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder="Optional display name" />
          </label>

          <label className="wlv-si-field">
            <span>Source folder path</span>
            <input value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="/path/to/well-data-folder" />
          </label>

          <label className="wlv-si-checkbox">
            <input type="checkbox" checked={includeSubfolders} onChange={(event) => setIncludeSubfolders(event.target.checked)} />
            <span>Include subfolders</span>
          </label>

          <div className="wlv-si-button-row">
            <button type="button" className="wlv-si-button wlv-si-button--primary" onClick={handleCreateRepository} disabled={Boolean(busyAction)}>
              Register Source
            </button>
            <button type="button" className="wlv-si-button wlv-si-button--primary" onClick={handleScan} disabled={Boolean(busyAction || !selectedRepository)}>
              Scan Source
            </button>
          </div>

          <div className="wlv-si-repository-list">
            <h3>Repositories</h3>
            {repositories.length === 0 ? (
              <p className="wlv-si-empty">No source repositories registered.</p>
            ) : repositories.map((repo) => (
              <button
                type="button"
                key={repo.repository_id}
                className={`wlv-si-repository ${repo.repository_id === selectedRepository?.repository_id ? 'is-active' : ''}`}
                onClick={() => setSelectedRepositoryId(repo.repository_id)}
              >
                <strong>{repo.name}</strong>
                <span>{repo.root_path}</span>
                <small>{labelize(repo.status)} · {repo.file_count} files · {labelize(repo.last_scan_scope)}</small>
              </button>
            ))}
          </div>
        </aside>

        <main className="wlv-si-main">
          <div className="wlv-si-summary-grid">
            <SummaryTile label="Repositories" value={summary?.repository_count ?? 0} />
            <SummaryTile label="Files" value={summary?.file_count ?? 0} />
            <SummaryTile label="Well-log files" value={summary?.well_log_candidate_count ?? 0} />
            <SummaryTile label="Curves" value={visibleCurveCount} />
            <SummaryTile label="Rasters" value={summary?.raster_candidate_count ?? 0} />
            <SummaryTile label="Documents" value={summary?.document_candidate_count ?? 0} />
            <SummaryTile label="Review" value={summary?.review_required_count ?? 0} />
          </div>

          {(message || error || busyAction) ? (
            <div className={`wlv-si-message ${error ? 'is-error' : ''}`}>
              {busyAction ? `Working: ${labelize(busyAction)}…` : error || message}
            </div>
          ) : null}

          <section className="wlv-si-card wlv-si-card--workbench">
            <div className="wlv-si-card__header">
              <div>
                <h2>Candidates</h2>
                <p>{visibleCandidates.length} candidates in current workbench view.</p>
              </div>
              <div className="wlv-si-button-row">
                <button type="button" className="wlv-si-button" onClick={toggleAllVisibleEligible} disabled={visibleCandidates.length === 0}>
                  Select Eligible
                </button>
                <button
                  type="button"
                  className="wlv-si-button wlv-si-button--primary"
                  onClick={handleRegister}
                  disabled={Boolean(busyAction || selectedRegisterableCount === 0)}
                >
                  Register Selected ({selectedRegisterableCount})
                </button>
              </div>
            </div>

            <div className="wlv-si-table-wrap">
              <table className="wlv-si-table">
                <thead>
                  <tr>
                    <th aria-label="Select">Sel</th>
                    <th>File</th>
                    <th>Role</th>
                    <th>Curves</th>
                    <th>Parse</th>
                    <th>Well</th>
                    <th>UWI/API</th>
                    <th>QAQC</th>
                    <th>WMDP</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleCandidates.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="wlv-si-empty-row">No candidates discovered. Register and scan a source repository.</td>
                    </tr>
                  ) : visibleCandidates.map((candidate) => {
                    const wellName = candidate.resolved_metadata?.well_name?.value ?? '—';
                    const uwi = candidate.resolved_metadata?.uwi?.value ?? '—';
                    const qaqcStatus = candidate.qaqc_status?.status ?? 'not_checked';
                    const eligible = candidateIsRegisterable(candidate);
                    const registered = candidateIsRegistered(candidate);
                    const curveCount = candidateCurveCount(candidate);
                    return (
                      <tr key={candidate.source_file_id} className={candidate.review_required ? 'requires-review' : ''}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedCandidateIds.has(candidate.source_file_id)}
                            disabled={!eligible}
                            onChange={() => toggleCandidate(candidate.source_file_id)}
                            aria-label={`Select ${candidate.file_name}`}
                          />
                        </td>
                        <td>
                          <strong>{candidate.file_name}</strong>
                          <small>{candidate.relative_path}</small>
                        </td>
                        <td><span className="wlv-si-pill">{labelize(candidate.candidate_role)}</span></td>
                        <td>{curveCount}</td>
                        <td><span className={`wlv-si-pill ${statusClass(candidate.parser_status)}`}>{labelize(candidate.parser_status)}</span></td>
                        <td>{wellName}</td>
                        <td>{uwi}</td>
                        <td className="wlv-si-status-cell">
                          <div className="wlv-si-status-stack">
                            <span className={`wlv-si-pill ${statusClass(qaqcStatus)}`}>{labelize(qaqcStatus)}</span>
                            <small>{candidate.qaqc_status?.warning_count ?? 0} warn · {candidate.qaqc_status?.failure_count ?? 0} fail</small>
                          </div>
                        </td>
                        <td className="wlv-si-status-cell">
                          {registered ? (
                            <div className="wlv-si-status-stack">
                              <span className="wlv-si-pill is-ok">Staged in WMDP</span>
                              <small>{candidate.registered_curve_count ?? curveCount} curves · {labelize(candidate.wdv_state ?? 'not_loaded')}</small>
                            </div>
                          ) : eligible ? (
                            <div className="wlv-si-status-stack">
                              <span className="wlv-si-pill is-ok">Ready to register</span>
                            </div>
                          ) : (
                            <div className="wlv-si-status-stack">
                              <span className="wlv-si-pill is-warning">Review</span>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </main>
      </div>
    </section>
  );
}

export default SourceIntakeWorkbench;
