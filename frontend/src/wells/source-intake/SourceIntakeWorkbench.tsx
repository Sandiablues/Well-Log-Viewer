import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  original_path?: string | null;
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

type SourceIntakeClearResponse = {
  ok: boolean;
  action: string;
  destructive: boolean;
  records_deleted: number;
  message: string;
  workbench: SourceIntakeWorkbenchResponse;
};

type SourceRepositoryRemoveResponse = {
  ok: boolean;
  action: string;
  destructive: boolean;
  repository_id: string;
  repository_removed: boolean;
  candidate_rows_removed: number;
  message: string;
  workbench: SourceIntakeWorkbenchResponse;
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

const PARSE_STATUS_LABELS: Record<string, string> = {
  not_parsed: 'Not Parsed',
  parsed: 'Parsed',
  parsed_with_warnings: 'Parsed With Warnings',
  parse_failed: 'Parse Failed',
  unsupported: 'Unsupported',
  container_pending_extraction: 'Container / Pending Extraction',
};

const PARSE_STATUS_DESCRIPTIONS: Record<string, string> = {
  not_parsed: 'Discovered only. No successful content extraction has been completed yet.',
  parsed: 'Content extraction succeeded and produced usable structured metadata.',
  parsed_with_warnings: 'Content extraction succeeded, but warnings or incomplete metadata remain.',
  parse_failed: 'A parser attempted extraction and failed.',
  unsupported: 'The file type is recognized, but no Source Intake parser is currently implemented for it.',
  container_pending_extraction: 'A container/archive was discovered and is pending extraction or child-file classification.',
};

function parseStatusLabel(value?: string | null): string {
  if (!value) return '—';
  return PARSE_STATUS_LABELS[value] ?? labelize(value);
}

function parseStatusDescription(value?: string | null): string {
  if (!value) return 'No parser status reported by backend.';
  return PARSE_STATUS_DESCRIPTIONS[value] ?? `Backend parser status: ${labelize(value)}.`;
}

function parseStatusClass(value?: string | null): string {
  switch (value) {
    case 'parsed':
      return 'is-ok';
    case 'parsed_with_warnings':
    case 'container_pending_extraction':
    case 'unsupported':
      return 'is-warning';
    case 'parse_failed':
      return 'is-error';
    case 'not_parsed':
    default:
      return 'is-neutral';
  }
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

// WLV-WSI-SELECTION-CONTROLS-1: repository deselect, candidate row selection, and select-all controls.
// WLV-WSI-MDP-HEADER-BUTTON-REFINE-1: MDP-aligned WSI header, smaller neutral buttons, no top header actions.
// WLV-WSI-HEADER-TABLE-REFINE-1: no redundant WSI kicker; fixed candidate columns with horizontal scroll.
// WLV-WSI-CANDIDATE-CLEAR-1: deterministic candidate clear and header select-all selection state.
// WLV-WSI-CANDIDATE-CLEAR-HOTFIX-1: remove unused select-all toggle helper after checked-state handler migration.
// WLV-WSI-CANDIDATE-CLEAR-REFRESH-1: candidate-panel refresh and unambiguous candidate clear visual state.
// WLV-WSI-CLEAR-CANDIDATE-ROWS-1: Clear Selection removes selected rows from backend candidate register.
// WLV-WSI-EMPTY-CANDIDATES-NO-FETCH-ERROR-1: do not show stale fetch errors over an intentionally empty candidate table.
// WLV-WSI-REMOVE-SOURCE-1: Remove Source deletes the selected repository record from backend Source Intake.
// WLV-WSI-STALE-CANDIDATE-RENDER-GUARD-1: Clear Selection reloads backend-canonical rows and remounts the table.
// WLV-WSI-PARSE-STATUS-FILENAME-1: expanded parser labels and full filename/details access.
// WLV-WSI-SIFT-SORT-FILENAME-WIDTH-1: candidate sift/sort controls and wider non-truncated file/parse columns.
// WLV-WSI-COLLAPSE-DETAIL-COLUMNS-V2-ROLE-1: collapsible source panel, detail toggle rows, and final candidate columns with Role before Curves.
// WLV-WSI-SOURCE-PANEL-TEXT-CLEANUP-1: remove redundant source-panel helper text and keep Search & Discover on one line.
// WLV-WSI-STRUCTURAL-CANDIDATE-LAYOUT-1: single authoritative semantic candidate table column model.
export function SourceIntakeWorkbench() {
  const [workbench, setWorkbench] = useState<SourceIntakeWorkbenchResponse | null>(null);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<string>('');
  const [sourceName, setSourceName] = useState('');
  const [sourcePath, setSourcePath] = useState('');
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(new Set());
  const [candidateViewMode, setCandidateViewMode] = useState<string>('all');
  const [sourcePanelCollapsed, setSourcePanelCollapsed] = useState(false);
  const [expandedCandidateIds, setExpandedCandidateIds] = useState<Set<string>>(new Set());
  const headerSelectRef = useRef<HTMLInputElement | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string>('');

  const repositories = workbench?.repositories ?? [];
  const candidates = workbench?.candidates ?? [];
  const summary = workbench?.summary;

  const selectedRepository = useMemo(
    () => repositories.find((repo) => repo.repository_id === selectedRepositoryId) ?? null,
    [repositories, selectedRepositoryId],
  );

  const repositoryCandidates = useMemo(() => {
    if (!selectedRepository?.repository_id) return candidates;
    return candidates.filter((candidate) => candidate.repository_id === selectedRepository.repository_id);
  }, [candidates, selectedRepository]);

  const visibleCandidates = useMemo(() => {
    const byFileName = (rows: SourceFileCandidate[]) => rows.sort((a, b) => a.file_name.localeCompare(b.file_name));
    const rows = [...repositoryCandidates];

    switch (candidateViewMode) {
      case 'eligible':
        return byFileName(rows.filter(candidateIsRegisterable));
      case 'review_required':
        return byFileName(rows.filter((candidate) => candidate.review_required || candidate.qaqc_status?.review_required));
      case 'well_logs':
        return byFileName(rows.filter((candidate) => candidate.candidate_role === 'well_log_candidate'));
      case 'supporting_documents':
        return byFileName(rows.filter((candidate) => candidate.candidate_role === 'supporting_document_candidate'));
      case 'containers':
        return byFileName(rows.filter((candidate) => candidate.parser_status === 'container_pending_extraction'));
      case 'unsupported':
        return byFileName(rows.filter((candidate) => candidate.parser_status === 'unsupported'));
      case 'parse_failed':
        return byFileName(rows.filter((candidate) => candidate.parser_status === 'parse_failed'));
      case 'not_parsed':
        return byFileName(rows.filter((candidate) => candidate.parser_status === 'not_parsed'));
      case 'parsed':
        return byFileName(rows.filter((candidate) => candidate.parser_status === 'parsed' || candidate.parser_status === 'parsed_with_warnings'));
      case 'sort_file':
        return byFileName(rows);
      case 'sort_role':
        return rows.sort((a, b) => `${a.candidate_role}:${a.file_name}`.localeCompare(`${b.candidate_role}:${b.file_name}`));
      case 'sort_parse':
        return rows.sort((a, b) => `${a.parser_status}:${a.file_name}`.localeCompare(`${b.parser_status}:${b.file_name}`));
      case 'sort_curves':
        return rows.sort((a, b) => candidateCurveCount(b) - candidateCurveCount(a) || a.file_name.localeCompare(b.file_name));
      case 'all':
      default:
        return rows;
    }
  }, [repositoryCandidates, candidateViewMode]);

  const visibleCurveCount = useMemo(
    () => visibleCandidates.reduce((total, candidate) => total + candidateCurveCount(candidate), 0),
    [visibleCandidates],
  );

  const visibleCandidateIds = useMemo(
    () => visibleCandidates.map((candidate) => candidate.source_file_id),
    [visibleCandidates],
  );

  const visibleEligibleCandidateIds = useMemo(
    () => visibleCandidates.filter(candidateIsRegisterable).map((candidate) => candidate.source_file_id),
    [visibleCandidates],
  );

  const selectedCandidateCount = selectedCandidateIds.size;
  const visibleSelectedCandidateCount = visibleCandidateIds.filter((candidateId) => selectedCandidateIds.has(candidateId)).length;
  const selectedRegisterableCount = visibleEligibleCandidateIds.filter((candidateId) => selectedCandidateIds.has(candidateId)).length;
  const allVisibleCandidatesSelected = visibleCandidateIds.length > 0
    && visibleCandidateIds.every((candidateId) => selectedCandidateIds.has(candidateId));
  const partiallyVisibleCandidatesSelected = visibleSelectedCandidateCount > 0 && !allVisibleCandidatesSelected;

  const candidateTableRenderKey = useMemo(
    () => `${selectedRepositoryId || 'all'}:${visibleCandidateIds.length}:${visibleCandidateIds.join('|') || 'empty'}`,
    [selectedRepositoryId, visibleCandidateIds],
  );

  const loadWorkbench = useCallback(async () => {
    const data = await fetchWlvJson<SourceIntakeWorkbenchResponse>('/api/wlv/source-intake/workbench');
    setWorkbench(data);
    setSelectedRepositoryId((current) => {
      if (current && data.repositories.some((repo) => repo.repository_id === current)) {
        return current;
      }
      return '';
    });
    setSelectedCandidateIds((current) => {
      const validIds = new Set(data.candidates.map((candidate) => candidate.source_file_id));
      return new Set([...current].filter((candidateId) => validIds.has(candidateId)));
    });
    setExpandedCandidateIds((current) => {
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

  useEffect(() => {
    if (headerSelectRef.current) {
      headerSelectRef.current.indeterminate = partiallyVisibleCandidatesSelected;
    }
  }, [partiallyVisibleCandidatesSelected, allVisibleCandidatesSelected]);

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
    setMessage(`Registered source repository: ${repository.name}`);
    await loadWorkbench();
    setSelectedRepositoryId(repository.repository_id);
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

  const handleRegister = () => runAction('register', async () => {
    const candidateIds = visibleCandidates
      .filter((candidate) => selectedCandidateIds.has(candidate.source_file_id) && candidateIsRegisterable(candidate))
      .map((candidate) => candidate.source_file_id);
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

  const setCandidateSelected = (candidateId: string, selected: boolean) => {
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      if (selected) next.add(candidateId);
      else next.delete(candidateId);
      return next;
    });
  };

  const toggleCandidate = (candidateId: string) => {
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });
  };

  const toggleCandidateDetail = (candidateId: string) => {
    setExpandedCandidateIds((current) => {
      const next = new Set(current);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });
  };

  const removeSelectedRepository = () => runAction('remove-source', async () => {
    const repositoryId = selectedRepository?.repository_id;
    if (!repositoryId) {
      throw new Error('Select a source repository before removing it from Source Intake.');
    }

    const response = await fetchWlvJson<SourceRepositoryRemoveResponse>(
      `/api/wlv/source-intake/repositories/${encodeURIComponent(repositoryId)}`,
      { method: 'DELETE' },
    );

    setWorkbench(response.workbench);
    setSelectedRepositoryId('');
    setSelectedCandidateIds(new Set());
    setMessage(response.message || 'Removed selected source repository from Source Intake.');
  });

  const clearCandidateSelection = () => runAction('clear-selection', async () => {
    const candidateIds = Array.from(selectedCandidateIds);
    if (candidateIds.length === 0) {
      setMessage('No Source Intake candidate rows are selected.');
      return;
    }

    const response = await fetchWlvJson<SourceIntakeClearResponse>('/api/wlv/source-intake/workbench/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repository_id: selectedRepository?.repository_id ?? undefined,
        candidate_ids: candidateIds,
      }),
    });

    setWorkbench(response.workbench);
    setSelectedCandidateIds(new Set());
    if (headerSelectRef.current) {
      headerSelectRef.current.checked = false;
      headerSelectRef.current.indeterminate = false;
    }

    // WLV-WSI-STALE-CANDIDATE-RENDER-GUARD-1:
    // The backend is authoritative. After candidate removal, reload the
    // canonical workbench so stale DOM/render state cannot leave an orphan row.
    await loadWorkbench();

    setMessage(response.message || `Removed ${response.records_deleted} selected candidate row(s) from Source Intake.`);
  });

  const setVisibleCandidateSelection = (selected: boolean) => {
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      visibleCandidateIds.forEach((candidateId) => {
        if (selected) next.add(candidateId);
        else next.delete(candidateId);
      });
      return next;
    });
  };


  const toggleAllVisibleEligible = () => {
    const allEligibleSelected = visibleEligibleCandidateIds.length > 0
      && visibleEligibleCandidateIds.every((candidateId) => selectedCandidateIds.has(candidateId));
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      visibleEligibleCandidateIds.forEach((candidateId) => {
        if (allEligibleSelected) next.delete(candidateId);
        else next.add(candidateId);
      });
      return next;
    });
  };

  return (
    <section className="wlv-source-intake" aria-label="WLV Source Intake workbench">
      <header className="wlv-source-intake__header wlv-managed-inventory-header wlv-wmdp-page-header">
        <div>
          <h1>Source Intake</h1>
          <p className="wlv-source-intake__subtitle">
            Search, discover, categorize, QAQC, and register well-log source data into the Managed Well Inventory.
          </p>
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

      <div className={`wlv-si-layout ${sourcePanelCollapsed ? 'is-source-collapsed' : ''}`}>
        {!sourcePanelCollapsed ? (
        <aside className="wlv-si-card wlv-si-card--setup">
          <div className="wlv-si-card__header">
            <h2>Search & Discover</h2>
            <div className="wlv-si-card__header-actions">
              <button
                type="button"
                className="wlv-si-inline-button wlv-si-panel-toggle"
                onClick={() => setSourcePanelCollapsed(true)}
              >
                Collapse
              </button>
            </div>
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
            <div className="wlv-si-repository-list__header">
              <h3>Repositories</h3>
              <button
                type="button"
                className="wlv-si-inline-button"
                onClick={removeSelectedRepository}
                disabled={!selectedRepositoryId || Boolean(busyAction)}
              >
                Remove Source
              </button>
            </div>
            {repositories.length === 0 ? (
              <p className="wlv-si-empty">No source repositories registered.</p>
            ) : repositories.map((repo) => (
              <button
                type="button"
                key={repo.repository_id}
                className={`wlv-si-repository ${repo.repository_id === selectedRepositoryId ? 'is-active' : ''}`}
                onClick={() => setSelectedRepositoryId(repo.repository_id)}
              >
                <strong>{repo.name}</strong>
                <span>{repo.root_path}</span>
                <small>{labelize(repo.status)} · {repo.file_count} files · {labelize(repo.last_scan_scope)}</small>
              </button>
            ))}
          </div>
        </aside>
        ) : null}

        <main className="wlv-si-main">
          {sourcePanelCollapsed ? (
            <div className="wlv-si-collapsed-source-bar">
              <button
                type="button"
                className="wlv-si-button"
                onClick={() => setSourcePanelCollapsed(false)}
              >
                Show Search & Discover
              </button>
            </div>
          ) : null}
          <div className="wlv-si-summary-grid">
            <SummaryTile label="Repositories" value={summary?.repository_count ?? 0} />
            <SummaryTile label="Files" value={summary?.file_count ?? 0} />
            <SummaryTile label="Well-log files" value={summary?.well_log_candidate_count ?? 0} />
            <SummaryTile label="Curves" value={visibleCurveCount} />
            <SummaryTile label="Rasters" value={summary?.raster_candidate_count ?? 0} />
            <SummaryTile label="Documents" value={summary?.document_candidate_count ?? 0} />
            <SummaryTile label="Review" value={summary?.review_required_count ?? 0} />
          </div>

          {(message || busyAction || (error && visibleCandidates.length > 0)) ? (
            <div className={`wlv-si-message ${error && visibleCandidates.length > 0 ? 'is-error' : ''}`}>
              {busyAction ? `Working: ${labelize(busyAction)}…` : (error && visibleCandidates.length > 0 ? error : message)}
            </div>
          ) : null}

          <section className="wlv-si-card wlv-si-card--workbench">
            <div className="wlv-si-card__header">
              <div>
                <h2>Candidates</h2>
                <p>
                  {visibleCandidates.length} candidates in current workbench view
                  {visibleSelectedCandidateCount > 0 ? ` · ${visibleSelectedCandidateCount} selected` : ''}.
                </p>
              </div>
              <div className="wlv-si-button-row wlv-si-candidate-controls">
                <label className="wlv-si-sift-sort-control">
                  <span>Sift / Sort</span>
                  <select value={candidateViewMode} onChange={(event) => setCandidateViewMode(event.currentTarget.value)}>
                    <option value="all">All candidates</option>
                    <option value="eligible">Sift: ready to register</option>
                    <option value="review_required">Sift: review required</option>
                    <option value="well_logs">Sift: well-log candidates</option>
                    <option value="supporting_documents">Sift: supporting documents</option>
                    <option value="containers">Sift: containers / pending extraction</option>
                    <option value="unsupported">Sift: unsupported parser</option>
                    <option value="parse_failed">Sift: parse failed</option>
                    <option value="not_parsed">Sift: not parsed</option>
                    <option value="parsed">Sift: parsed / parsed with warnings</option>
                    <option value="sort_file">Sort: file name A-Z</option>
                    <option value="sort_role">Sort: role</option>
                    <option value="sort_parse">Sort: parse status</option>
                    <option value="sort_curves">Sort: curve count high-low</option>
                  </select>
                </label>
                <button type="button" className="wlv-si-button" onClick={toggleAllVisibleEligible} disabled={visibleEligibleCandidateIds.length === 0}>
                  {selectedRegisterableCount === visibleEligibleCandidateIds.length && visibleEligibleCandidateIds.length > 0 ? 'Clear Eligible' : 'Select Eligible'}
                </button>
                <button
                  type="button"
                  className="wlv-si-button wlv-si-button--primary"
                  onClick={handleRegister}
                  disabled={Boolean(busyAction || selectedRegisterableCount === 0)}
                >
                  Register Selected ({selectedRegisterableCount})
                </button>
                <button type="button" className="wlv-si-button" onClick={clearCandidateSelection} disabled={selectedCandidateCount === 0}>
                  Clear Selection
                </button>
                <button type="button" className="wlv-si-button" onClick={handleRefresh} disabled={Boolean(busyAction)}>
                  Refresh
                </button>
              </div>
            </div>

            <div className="wlv-si-table-wrap">
              <table className="wlv-si-table wlv-si-candidate-table" key={candidateTableRenderKey} data-candidate-count={visibleCandidates.length}>
                <colgroup>
                  <col className="wlv-si-col-select" />
                  <col className="wlv-si-col-name" />
                  <col className="wlv-si-col-well" />
                  <col className="wlv-si-col-role" />
                  <col className="wlv-si-col-curves" />
                  <col className="wlv-si-col-parse" />
                  <col className="wlv-si-col-qaqc" />
                  <col className="wlv-si-col-mdp-ready" />
                </colgroup>
                <thead>
                  <tr>
                    <th className="wlv-si-select-col">
                      <input
                        ref={headerSelectRef}
                        type="checkbox"
                        checked={allVisibleCandidatesSelected}
                        disabled={visibleCandidateIds.length === 0}
                        onChange={(event) => setVisibleCandidateSelection(event.currentTarget.checked)}
                        aria-label="Select all visible Source Intake candidates"
                      />
                    </th>
                    <th>Name</th>
                    <th>Well</th>
                    <th>Role</th>
                    <th>Curves</th>
                    <th>Parse</th>
                    <th>QAQC</th>
                    <th>MDP Ready</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleCandidates.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="wlv-si-empty-row">No candidates discovered. Register and scan a source repository.</td>
                    </tr>
                  ) : visibleCandidates.map((candidate) => {
                    const wellName = candidate.resolved_metadata?.well_name?.value ?? '—';
                    const qaqcStatus = candidate.qaqc_status?.status ?? 'not_checked';
                    const eligible = candidateIsRegisterable(candidate);
                    const registered = candidateIsRegistered(candidate);
                    const curveCount = candidateCurveCount(candidate);
                    const detailExpanded = expandedCandidateIds.has(candidate.source_file_id);
                    return (
                      <tr
                        key={candidate.source_file_id}
                        className={[
                          candidate.review_required ? 'requires-review' : '',
                          selectedCandidateIds.has(candidate.source_file_id) ? 'is-selected' : '',
                        ].filter(Boolean).join(' ')}
                        onClick={() => toggleCandidate(candidate.source_file_id)}
                      >
                        <td className="wlv-si-cell-select">
                          <input
                            type="checkbox"
                            checked={selectedCandidateIds.has(candidate.source_file_id)}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) => setCandidateSelected(candidate.source_file_id, event.currentTarget.checked)}
                            aria-label={`Select ${candidate.file_name}`}
                          />
                        </td>
                        <td
                          className={`wlv-si-file-cell ${detailExpanded ? 'is-detail-open' : ''}`}
                          title={candidate.file_name}
                        >
                          <strong title={candidate.file_name}>{candidate.file_name}</strong>
                          {!detailExpanded ? (
                            <button
                              type="button"
                              className="wlv-si-detail-button"
                              onClick={(event) => {
                                event.stopPropagation();
                                toggleCandidateDetail(candidate.source_file_id);
                              }}
                            >
                              Detail
                            </button>
                          ) : (
                            <div className="wlv-si-file-detail-panel" onClick={(event) => event.stopPropagation()}>
                              <dl>
                                <div>
                                  <dt>Relative path</dt>
                                  <dd>{candidate.relative_path}</dd>
                                </div>
                                {candidate.original_path ? (
                                  <div>
                                    <dt>Source path</dt>
                                    <dd>{candidate.original_path}</dd>
                                  </div>
                                ) : null}
                              </dl>
                              <button
                                type="button"
                                className="wlv-si-detail-button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  toggleCandidateDetail(candidate.source_file_id);
                                }}
                              >
                                Detail
                              </button>
                            </div>
                          )}
                        </td>
                        <td className="wlv-si-cell-well wlv-si-well-cell">{wellName}</td>
                        <td className="wlv-si-cell-role"><span className="wlv-si-pill">{labelize(candidate.candidate_role)}</span></td>
                        <td className="wlv-si-cell-curves">{curveCount}</td>
                        <td className="wlv-si-cell-parse wlv-si-parse-cell">
                          <span
                            className={`wlv-si-pill ${parseStatusClass(candidate.parser_status)}`}
                            title={parseStatusDescription(candidate.parser_status)}
                          >
                            {parseStatusLabel(candidate.parser_status)}
                          </span>
                        </td>
                        <td className="wlv-si-cell-qaqc wlv-si-status-cell">
                          <div className="wlv-si-status-stack">
                            <span className={`wlv-si-pill ${statusClass(qaqcStatus)}`}>{labelize(qaqcStatus)}</span>
                            <small>{candidate.qaqc_status?.warning_count ?? 0} warn · {candidate.qaqc_status?.failure_count ?? 0} fail</small>
                          </div>
                        </td>
                        <td className="wlv-si-cell-mdp-ready wlv-si-status-cell">
                          {registered ? (
                            <div className="wlv-si-status-stack">
                              <span className="wlv-si-pill is-ok">Staged in MDP</span>
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
