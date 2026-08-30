import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchWlvJson, wlvApiBaseUrl } from '../../api/wlvBackendClient';

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
  wellbore_geometry_candidate_count: number;
  unknown_file_count: number;
  review_required_count: number;
};

type ResolvedField = {
  value?: string | null;
  source?: string;
  confidence?: string;
  review_required?: boolean;
};

type EditableMetadataFields = {
  well_name: string;
  uwi: string;
  operator: string;
  field: string;
};

type QaqcStatus = {
  status?: string;
  severity?: string;
  check_count?: number;
  warning_count?: number;
  failure_count?: number;
  review_required?: boolean;
  messages?: string[];
  checks?: Array<{
    check_id: string;
    status?: string;
    finding_class?: string;
    review_required?: boolean;
  }>;
};

type SourceIntakeCurrentDecision = {
  decision: 'accept' | 'correct' | 'assign' | 'exclude' | 'clear_decision';
  assignment_target?: string | null;
  assignment_mode?: 'existing_well' | 'new_well' | null;
};

type SourceFileCandidate = {
  source_file_id: string;
  occurrence_id: string;
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
  registered_trajectory_count?: number;
  readiness_state: 'ready' | 'review_required' | 'blocked' | 'excluded' | 'registered';
  readiness_issues: string[];
  available_human_actions: string[];
  current_decision?: SourceIntakeCurrentDecision | null;
  depth_normalization?: {
    raw_unit?: string | null;
    raw_start_depth?: number | null;
    raw_stop_depth?: number | null;
    status: 'source_native' | 'review_required' | 'human_resolved' | 'unsupported';
    reason?: string | null;
    options: Array<{ target_unit: 'm' | 'ft'; start_depth: number; stop_depth: number }>;
    decision?: { target_unit: 'm' | 'ft'; actor?: string | null; decided_at: string; reason?: string | null } | null;
  } | null;
  parsed_metadata?: {
    well_header?: {
      well_name?: string | null;
      uwi?: string | null;
      operator?: string | null;
      field?: string | null;
      depth_unit?: string | null;
    } | null;
    log_header?: {
      curve_count?: number | null;
      start_depth?: number | null;
      stop_depth?: number | null;
      depth_unit?: string | null;
    } | null;
    curve_headers?: Array<{ mnemonic?: string | null }> | null;
  } | null;
  geometry_preview?: {
    source_format?: string;
    row_count?: number;
    station_count?: number;
    preview_station_count?: number;
    md_min?: number | null;
    md_max?: number | null;
    tvd_min?: number | null;
    tvd_max?: number | null;
    warning_count?: number;
    error_count?: number;
    column_mapping?: {
      measured_depth?: string | null;
      inclination?: string | null;
      azimuth?: string | null;
      tvd?: string | null;
      x_offset?: string | null;
      y_offset?: string | null;
      northing?: string | null;
      easting?: string | null;
      unmapped_headers?: string[];
    };
    stations_preview?: Array<{
      row_index: number;
      md: number;
      inclination: number;
      azimuth: number;
      tvd?: number | null;
      x_offset?: number | null;
      y_offset?: number | null;
      northing?: number | null;
      easting?: number | null;
    }>;
    warnings?: string[];
    errors?: string[];
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
  wellbore_geometry_candidate_count: number;
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


type ManagedWellSummary = {
  managed_well_id: string;
  well_name: string;
  well_id: string;
  operator?: string | null;
  field?: string | null;
  metadata?: {
    uwi?: string | null;
  };
};

type CandidateDiagnosticPhase = 'parse' | 'qaqc' | 'mdp_ready' | 'evidence';
type CandidateDiagnosticSeverity = 'info' | 'success' | 'warning' | 'error' | 'blocker';

type CandidateDiagnosticFlag = {
  phase: CandidateDiagnosticPhase;
  severity: CandidateDiagnosticSeverity;
  code: string;
  title: string;
  message: string;
  field_name?: string | null;
};

type CandidateDiagnosticAction = {
  phase: CandidateDiagnosticPhase;
  action_key: string;
  label: string;
  enabled: boolean;
  reason?: string | null;
};

type CandidateDiagnosticSummary = {
  candidate_id: string;
  file_name: string;
  relative_path: string;
  original_path?: string | null;
  detected_file_type: string;
  candidate_role: string;
  well_name?: string | null;
  curve_count: number;
  registration_status: string;
  managed_well_id?: string | null;
  managed_well_name?: string | null;
};

type CandidateDiagnosticsResponse = {
  ok: boolean;
  service: string;
  candidate_id: string;
  summary: CandidateDiagnosticSummary;
  parse_status: string;
  qaqc_status: QaqcStatus;
  mdp_ready_status: string;
  flags: CandidateDiagnosticFlag[];
  actions: CandidateDiagnosticAction[];
};

const WORKFLOW_LABELS = [
  'Search & Discover',
  'Categorize',
  'QAQC',
  'Make Available in WMD',
  'Available in WMD',
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
  return candidate.readiness_state === 'ready';
}

function candidateAcceptedFindingCodes(candidate: SourceFileCandidate): string[] {
  return (candidate.qaqc_status?.checks ?? [])
    .filter((check) => (
      check.finding_class !== 'hard_failure'
      && (check.review_required || check.status === 'warning' || check.status === 'review_required')
    ))
    .map((check) => check.check_id);
}

function geometryPreviewLabel(candidate: SourceFileCandidate): string {
  const preview = candidate.geometry_preview;
  if (!preview) return candidate.candidate_role === 'wellbore_geometry_candidate' ? 'No preview' : '—';
  const mdRange = typeof preview.md_min === 'number' && typeof preview.md_max === 'number'
    ? `MD ${preview.md_min.toLocaleString()}–${preview.md_max.toLocaleString()}`
    : 'MD —';
  return `${preview.station_count ?? 0} stations · ${mdRange}`;
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
// WLV-WSI-FLAGS-DETAIL-1: backend-owned diagnostics drawer for Parse, QAQC, and MDP Ready flags.
// WLV-WSI-FLAGS-DETAIL-HOTFIX-2: drawer fallback summary, known metadata, runtime-safe diagnostics load.
export function SourceIntakeWorkbench() {
  const [workbench, setWorkbench] = useState<SourceIntakeWorkbenchResponse | null>(null);
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<string>('');
  const [sourceName, setSourceName] = useState('');
  const [sourcePath, setSourcePath] = useState('');
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(new Set());
  const [candidateViewMode, setCandidateViewMode] = useState<string>('all');
  const [sourcePanelCollapsed, setSourcePanelCollapsed] = useState(false);
  const [diagnosticCandidateId, setDiagnosticCandidateId] = useState<string>('');
  const [diagnosticCandidate, setDiagnosticCandidate] = useState<SourceFileCandidate | null>(null);
  const [candidateDiagnostics, setCandidateDiagnostics] = useState<CandidateDiagnosticsResponse | null>(null);
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);
  const [diagnosticError, setDiagnosticError] = useState<string>('');
  // WLV-WSI-DETAIL-METADATA-EDITOR-STAGE1
  const [metadataEditMode, setMetadataEditMode] = useState(false);
  const [metadataDraft, setMetadataDraft] = useState<EditableMetadataFields>({
    well_name: '',
    uwi: '',
    operator: '',
    field: '',
  });
  const [includeQaqcReportOnPromotion, setIncludeQaqcReportOnPromotion] = useState(false);
  const headerSelectRef = useRef<HTMLInputElement | null>(null);
  const directIngestInputRef = useRef<HTMLInputElement | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [directIngestDragActive, setDirectIngestDragActive] = useState(false);
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
      case 'wellbore_geometry':
        return byFileName(rows.filter((candidate) => candidate.candidate_role === 'wellbore_geometry_candidate'));
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

  const selectedCandidateCount = selectedCandidateIds.size;
  const visibleSelectedCandidateCount = visibleCandidateIds.filter((candidateId) => selectedCandidateIds.has(candidateId)).length;
  const allVisibleCandidatesSelected = visibleCandidateIds.length > 0
    && visibleCandidateIds.every((candidateId) => selectedCandidateIds.has(candidateId));
  const partiallyVisibleCandidatesSelected = visibleSelectedCandidateCount > 0 && !allVisibleCandidatesSelected;

  const candidateTableRenderKey = useMemo(
    () => `${selectedRepositoryId || 'all'}:${visibleCandidateIds.length}:${visibleCandidateIds.join('|') || 'empty'}`,
    [selectedRepositoryId, visibleCandidateIds],
  );

  const diagnosticFallbackCandidate = useMemo(
    () => diagnosticCandidate
      ?? candidates.find((candidate) => candidate.source_file_id === diagnosticCandidateId)
      ?? null,
    [candidates, diagnosticCandidate, diagnosticCandidateId],
  );

  const diagnosticTitle = candidateDiagnostics?.summary.file_name
    ?? diagnosticFallbackCandidate?.file_name
    ?? 'Candidate diagnostic detail';

  const diagnosticRelativePath = candidateDiagnostics?.summary.relative_path
    ?? diagnosticFallbackCandidate?.relative_path
    ?? '';

  const diagnosticSourcePath = candidateDiagnostics?.summary.original_path
    ?? diagnosticFallbackCandidate?.original_path
    ?? '';

  const diagnosticEditableMetadata = useMemo<EditableMetadataFields>(() => {
    const fallback = diagnosticFallbackCandidate;
    return {
      well_name: String(
        candidateDiagnostics?.summary.well_name
          ?? fallback?.resolved_metadata?.well_name?.value
          ?? fallback?.parsed_metadata?.well_header?.well_name
          ?? '',
      ),
      uwi: String(
        fallback?.resolved_metadata?.uwi?.value
          ?? fallback?.parsed_metadata?.well_header?.uwi
          ?? '',
      ),
      operator: String(
        fallback?.resolved_metadata?.operator?.value
          ?? fallback?.parsed_metadata?.well_header?.operator
          ?? '',
      ),
      field: String(
        fallback?.resolved_metadata?.field?.value
          ?? fallback?.parsed_metadata?.well_header?.field
          ?? '',
      ),
    };
  }, [candidateDiagnostics, diagnosticFallbackCandidate]);

  const diagnosticKnownMetadata = useMemo(() => {
    const fallback = diagnosticFallbackCandidate;
    if (!fallback && !candidateDiagnostics) return [];

    const logHeader = fallback?.parsed_metadata?.log_header;
    const depthUnit = logHeader?.depth_unit ?? fallback?.parsed_metadata?.well_header?.depth_unit ?? '';
    const depthRange = typeof logHeader?.start_depth === 'number' && typeof logHeader?.stop_depth === 'number'
      ? `${logHeader.start_depth.toLocaleString()}–${logHeader.stop_depth.toLocaleString()}${depthUnit ? ` ${depthUnit}` : ''}`
      : '—';

    return [
      { label: 'Well', value: candidateDiagnostics?.summary.well_name ?? fallback?.resolved_metadata?.well_name?.value ?? '—' },
      { label: 'UWI/API', value: fallback?.resolved_metadata?.uwi?.value ?? '—' },
      { label: 'Operator', value: fallback?.resolved_metadata?.operator?.value ?? '—' },
      { label: 'Field', value: fallback?.resolved_metadata?.field?.value ?? fallback?.parsed_metadata?.well_header?.field ?? '—' },
      { label: 'Depth Range', value: depthRange },
      { label: 'File Type', value: labelize(candidateDiagnostics?.summary.detected_file_type ?? fallback?.detected_file_type ?? 'unknown') },
      { label: 'Role', value: labelize(candidateDiagnostics?.summary.candidate_role ?? fallback?.candidate_role ?? 'unknown') },
      { label: fallback?.candidate_role === 'wellbore_geometry_candidate' ? 'Geometry Preview' : 'Curves', value: fallback?.candidate_role === 'wellbore_geometry_candidate' ? geometryPreviewLabel(fallback) : String(candidateDiagnostics?.summary.curve_count ?? (fallback ? candidateCurveCount(fallback) : 0)) },
      { label: 'Parse', value: parseStatusLabel(candidateDiagnostics?.parse_status ?? fallback?.parser_status ?? 'not_parsed') },
      { label: 'QAQC', value: labelize(candidateDiagnostics?.qaqc_status.status ?? fallback?.qaqc_status?.status ?? 'not_checked') },
      { label: 'MWD Readiness', value: labelize(candidateDiagnostics?.mdp_ready_status ?? fallback?.readiness_state ?? 'review_required') },
      { label: 'Registration', value: labelize(candidateDiagnostics?.summary.registration_status ?? fallback?.registration_status ?? 'not_registered') },
    ];
  }, [candidateDiagnostics, diagnosticFallbackCandidate]);

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

  const ingestDirectFiles = (fileList: FileList | null) => runAction('ingest-files', async () => {
    const files = fileList ? Array.from(fileList) : [];
    if (files.length === 0) return;

    const body = new FormData();
    files.forEach((file) => body.append('files', file, file.name));
    const scan = await fetchWlvJson<ScanResponse>('/api/wlv/source-intake/ingest-files', {
      method: 'POST',
      body,
    });
    await loadWorkbench();
    setSelectedRepositoryId(scan.repository.repository_id);
    setMessage(`${files.length} file${files.length === 1 ? '' : 's'} ingested.`);
  });

  const resolveDepthUnit = (candidate: SourceFileCandidate, targetUnit: 'm' | 'ft') => runAction(
    `depth-normalization:${candidate.source_file_id}:${targetUnit}`,
    async () => {
      await fetchWlvJson<SourceFileCandidate>(
        `/api/wlv/source-intake/candidates/${encodeURIComponent(candidate.source_file_id)}/depth-normalization`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_unit: targetUnit,
            actor: 'user',
            reason: `Human-selected WSI depth normalization to ${targetUnit}.`,
          }),
        },
      );
      await loadWorkbench();
      setMessage(`Depth normalization resolved to ${targetUnit}.`);
    },
  );

  const exportSelectedOverlays = () => runAction('export-overlays', async () => {
    const candidateIds = Array.from(selectedCandidateIds);
    if (candidateIds.length === 0) {
      throw new Error('Select at least one candidate before exporting QAQC and metadata overlays.');
    }
    const response = await fetch(`${wlvApiBaseUrl()}/api/wlv/source-intake/export-overlays`, {
      method: 'POST',
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_ids: candidateIds }),
    });
    if (!response.ok) {
      const payload = await response.text();
      throw new Error(`${response.status} ${response.statusText}: ${payload}`);
    }
    const packagePayload = await response.json();
    const blob = new Blob([JSON.stringify(packagePayload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `wlv-qaqc-metadata-overlays-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setMessage(`Exported QAQC and metadata overlays for ${candidateIds.length} candidate(s).`);
  });

  const exportCandidateOverlay = (
    candidate: SourceFileCandidate,
  ) => runAction(`export-overlay-${candidate.source_file_id}`, async () => {
    const response = await fetch(
      `${wlvApiBaseUrl()}/api/wlv/source-intake/export-overlays`,
      {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          candidate_ids: [candidate.source_file_id],
        }),
      },
    );

    if (!response.ok) {
      const payload = await response.text();
      throw new Error(
        `${response.status} ${response.statusText}: ${payload}`,
      );
    }

    const packagePayload = await response.json();
    const blob = new Blob(
      [JSON.stringify(packagePayload, null, 2)],
      { type: 'application/json' },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download =
      `wlv-qaqc-report-${candidate.file_name}-${new Date()
        .toISOString()
        .replace(/[:.]/g, '-')}.json`;

    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    setMessage(`Exported QAQC report for ${candidate.file_name}.`);
  });

  const handlePromoteCandidate = (
    candidate: SourceFileCandidate,
  ) => runAction(`promote-${candidate.source_file_id}`, async () => {
    if (!candidateIsRegisterable(candidate)) {
      throw new Error(
        candidate.readiness_issues?.[0]
          ?? 'This candidate is not ready for MWD promotion.',
      );
    }

    const response = await fetchWlvJson<RegisterResponse>(
      '/api/wlv/source-intake/register',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_ids: [candidate.source_file_id],
          approval: {
            approved_by: 'user',
            approval_note: 'Promoted from WSI candidate row',
          },
          include_qaqc_report: includeQaqcReportOnPromotion,
        }),
      },
    );

    await loadWorkbench();

    setMessage(
      response.registered_count === 1
        ? `${candidate.file_name} promoted to MWD.`
        : `Promotion skipped for ${candidate.file_name}.`,
    );
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

  const openCandidateDiagnostics = async (candidate: SourceFileCandidate) => {
    const candidateId = candidate.source_file_id;
    setDiagnosticCandidateId(candidateId);
    setDiagnosticCandidate(candidate);
    setCandidateDiagnostics(null);
    setDiagnosticError('');
    setMetadataEditMode(false);
    setMetadataDraft({
      well_name: '',
      uwi: '',
      operator: '',
      field: '',
    });
    setDiagnosticLoading(true);
    try {
      const data = await fetchWlvJson<CandidateDiagnosticsResponse>(
        `/api/wlv/source-intake/candidates/${encodeURIComponent(candidateId)}/diagnostics`,
      );
      setCandidateDiagnostics(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setDiagnosticError(message.includes('404')
        ? `${message}. Restart the WLV backend if this is the first diagnostics request after applying the block.`
        : message);
    } finally {
      setDiagnosticLoading(false);
    }
  };

  const closeCandidateDiagnostics = () => {
    setDiagnosticCandidateId('');
    setDiagnosticCandidate(null);
    setCandidateDiagnostics(null);
    setDiagnosticError('');
    setDiagnosticLoading(false);
    setMetadataEditMode(false);
    setMetadataDraft({
      well_name: '',
      uwi: '',
      operator: '',
      field: '',
    });
  };

  const beginMetadataEdit = () => {
    setMetadataDraft(diagnosticEditableMetadata);
    setMetadataEditMode(true);
    setDiagnosticError('');
  };

  const cancelMetadataEdit = () => {
    setMetadataDraft(diagnosticEditableMetadata);
    setMetadataEditMode(false);
    setDiagnosticError('');
  };

  const acceptMetadataEdit = () => runAction(
    `metadata-correction:${diagnosticCandidateId}`,
    async () => {
      const candidate = diagnosticFallbackCandidate;
      if (!candidate?.occurrence_id) {
        throw new Error('Candidate occurrence identity is unavailable; metadata correction cannot be persisted.');
      }

      const normalizedDraft: EditableMetadataFields = {
        well_name: metadataDraft.well_name.trim(),
        uwi: metadataDraft.uwi.trim(),
        operator: metadataDraft.operator.trim(),
        field: metadataDraft.field.trim(),
      };

      const changedValues = Object.fromEntries(
        (Object.keys(normalizedDraft) as Array<keyof EditableMetadataFields>)
          .filter((key) => normalizedDraft[key] !== diagnosticEditableMetadata[key].trim())
          .map((key) => [key, normalizedDraft[key] || null]),
      );

      if (Object.keys(changedValues).length === 0) {
        setMetadataEditMode(false);
        setMessage('No metadata changes were made.');
        return;
      }

      await fetchWlvJson('/api/wlv/source-intake/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decisions: [{
            occurrence_id: candidate.occurrence_id,
            action: 'manual_correction',
            actor: 'user',
            reason: 'Metadata corrected in the WSI candidate Detail panel.',
            resolved_values: changedValues,
          }],
        }),
      });

      await loadWorkbench();

      const refreshedDiagnostics = await fetchWlvJson<CandidateDiagnosticsResponse>(
        `/api/wlv/source-intake/candidates/${encodeURIComponent(candidate.source_file_id)}/diagnostics`,
      );
      setCandidateDiagnostics(refreshedDiagnostics);
      setMetadataEditMode(false);
      setMessage('Candidate metadata corrections accepted.');
    },
  );

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
              Add Source
            </button>
            <button type="button" className="wlv-si-button wlv-si-button--primary" onClick={handleScan} disabled={Boolean(busyAction || !selectedRepository)}>
              Scan Source
            </button>
          </div>

          <div className="wlv-si-repository-list wlv-si-repository-list--scrollable">
            <div className="wlv-si-repository-list__header">
              <h3>Repositories</h3>
              <button
                type="button"
                className="wlv-si-inline-button"
                onClick={removeSelectedRepository}
                disabled={!selectedRepositoryId || Boolean(busyAction)}
              >
                Close Source
              </button>
            </div>
            {repositories.length === 0 ? (
              <p className="wlv-si-empty">No source locations added.</p>
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

          <div
            className={`wlv-si-direct-ingest ${directIngestDragActive ? 'is-drag-active' : ''}`}
            role="button"
            tabIndex={0}
            aria-label="Drop files here to open or click to browse"
            onClick={() => directIngestInputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                directIngestInputRef.current?.click();
              }
            }}
            onDragEnter={(event) => { event.preventDefault(); setDirectIngestDragActive(true); }}
            onDragOver={(event) => { event.preventDefault(); setDirectIngestDragActive(true); }}
            onDragLeave={(event) => {
              event.preventDefault();
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDirectIngestDragActive(false);
            }}
            onDrop={(event) => {
              event.preventDefault();
              setDirectIngestDragActive(false);
              void ingestDirectFiles(event.dataTransfer.files);
            }}
          >
            <input
              ref={directIngestInputRef}
              type="file"
              multiple
              hidden
              onChange={(event) => {
                void ingestDirectFiles(event.target.files);
                event.target.value = '';
              }}
            />
            <strong>{busyAction === 'ingest-files' ? 'Opening files…' : 'Drop files here to open'}</strong>
            <span>LAS, DLIS, LIS/LTI, CSV and other supported files</span>
            <small>or click to browse</small>
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
            <SummaryTile label="Geometry" value={summary?.wellbore_geometry_candidate_count ?? 0} />
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
                    <option value="eligible">Sift: ready for MWD</option>
                    <option value="review_required">Sift: review required</option>
                    <option value="well_logs">Sift: well-log candidates</option>
                    <option value="wellbore_geometry">Sift: wellbore geometry</option>
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
                <button type="button" className="wlv-si-button" onClick={exportSelectedOverlays} disabled={selectedCandidateCount === 0 || Boolean(busyAction)}>
                  Export QAQC / Metadata
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
                  <col className="wlv-si-col-detail" />
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
                    <th>MWD</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleCandidates.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="wlv-si-empty-row">No candidates discovered. Add and scan a source location.</td>
                    </tr>
                  ) : visibleCandidates.map((candidate) => {
                    const wellName = candidate.resolved_metadata?.well_name?.value ?? '—';
                    const qaqcStatus = candidate.qaqc_status?.status ?? 'not_checked';
                    const eligible = candidateIsRegisterable(candidate);
                    const registered = candidateIsRegistered(candidate);
                    const curveCount = candidateCurveCount(candidate);
                    const geometryPreview = geometryPreviewLabel(candidate);
                    return (
                      <tr
                        key={candidate.source_file_id}
                        className={[
                          candidate.review_required ? 'requires-review' : '',
                          selectedCandidateIds.has(candidate.source_file_id) ? 'is-selected' : '',
                          diagnosticCandidateId === candidate.source_file_id ? 'is-diagnostic-active' : '',
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
                        <td className="wlv-si-file-cell" title={candidate.file_name}>
                          <strong title={candidate.file_name}>{candidate.file_name}</strong>
                        </td>
                        <td className="wlv-si-cell-well wlv-si-well-cell">{wellName}</td>
                        <td className="wlv-si-cell-role"><span className="wlv-si-pill">{labelize(candidate.candidate_role)}</span></td>
                        <td className="wlv-si-cell-curves">{candidate.candidate_role === 'wellbore_geometry_candidate' ? geometryPreview : curveCount}</td>
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
                              <span className="wlv-si-pill is-ok">IN MWD</span>
                              <small>
                                {candidate.candidate_role === 'wellbore_geometry_candidate'
                                  ? `${candidate.registered_trajectory_count ?? 1} trajectory`
                                  : `${candidate.registered_curve_count ?? curveCount} curves`}
                              </small>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className={[
                                'wlv-si-button',
                                'wlv-si-promote-button',
                                eligible ? 'wlv-si-button--primary' : '',
                              ].filter(Boolean).join(' ')}
                              disabled={Boolean(
                                busyAction
                                || !eligible
                              )}
                              title={
                                eligible
                                  ? 'Promote this candidate to MWD'
                                  : (
                                    candidate.readiness_issues?.[0]
                                    ?? 'This candidate is not ready for promotion.'
                                  )
                              }
                              onClick={(event) => {
                                event.stopPropagation();
                                void handlePromoteCandidate(candidate);
                              }}
                            >
                              {busyAction === `promote-${candidate.source_file_id}`
                                ? 'PROMOTING…'
                                : 'PROMOTE'}
                            </button>
                          )}
                        </td>
                        <td className="wlv-si-cell-detail">
                          <button
                            type="button"
                            className="wlv-si-detail-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              void openCandidateDiagnostics(candidate);
                            }}
                            aria-label={`Open diagnostics for ${candidate.file_name}`}
                          >
                            Detail
                          </button>
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

      {diagnosticCandidateId ? (
        <aside
          className="wlv-si-diagnostic-drawer"
          aria-label="Source Intake candidate diagnostic detail"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="wlv-si-diagnostic-drawer__header">
            <div>
              <span className="wlv-si-diagnostic-drawer__kicker">Diagnostic Detail</span>
              <h2>{diagnosticTitle}</h2>
              {/* WLV-WSI-DETAIL-PATH-LINKS-1: reveal file paths only on user request. */}
              <div className="wlv-si-diagnostic-path-links" aria-label="Candidate file paths">
                <details className="wlv-si-diagnostic-path-link">
                  <summary>Source path</summary>
                  <p>{diagnosticSourcePath || '—'}</p>
                </details>
                <details className="wlv-si-diagnostic-path-link">
                  <summary>Relative path</summary>
                  <p>{diagnosticRelativePath || '—'}</p>
                </details>
              </div>
            </div>
            <button
              type="button"
              className="wlv-si-detail-button"
              onClick={closeCandidateDiagnostics}
            >
              Close
            </button>
          </div>

          <div className="wlv-si-diagnostic-drawer__body">
            <section className="wlv-si-diagnostic-section wlv-si-diagnostic-section--known-metadata">
              <div className="wlv-si-diagnostic-section__title-row">
                <h3>Metadata</h3>
                <div className="wlv-si-metadata-editor__actions">
                  {metadataEditMode ? (
                    <>
                      <button
                        type="button"
                        className="wlv-si-detail-button"
                        onClick={cancelMetadataEdit}
                        disabled={busyAction?.startsWith('metadata-correction:')}
                      >
                        Close
                      </button>
                      <button
                        type="button"
                        className="wlv-si-detail-button wlv-si-detail-button--primary"
                        onClick={() => void acceptMetadataEdit()}
                        disabled={busyAction?.startsWith('metadata-correction:')}
                      >
                        {busyAction?.startsWith('metadata-correction:') ? 'Saving…' : 'Accept and Close'}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="wlv-si-detail-button wlv-si-detail-button--compact"
                      onClick={beginMetadataEdit}
                      disabled={!diagnosticFallbackCandidate || diagnosticLoading}
                    >
                      Edit
                    </button>
                  )}
                </div>
              </div>

              {metadataEditMode ? (
                <div className="wlv-si-metadata-editor" aria-label="Editable candidate metadata">
                  <label>
                    <span>Well</span>
                    <input
                      value={metadataDraft.well_name}
                      onChange={(event) => setMetadataDraft((current) => ({
                        ...current,
                        well_name: event.target.value,
                      }))}
                    />
                  </label>
                  <label>
                    <span>UWI/API</span>
                    <input
                      value={metadataDraft.uwi}
                      onChange={(event) => setMetadataDraft((current) => ({
                        ...current,
                        uwi: event.target.value,
                      }))}
                    />
                  </label>
                  <label>
                    <span>Operator</span>
                    <input
                      value={metadataDraft.operator}
                      onChange={(event) => setMetadataDraft((current) => ({
                        ...current,
                        operator: event.target.value,
                      }))}
                    />
                  </label>
                  <label>
                    <span>Field</span>
                    <input
                      value={metadataDraft.field}
                      onChange={(event) => setMetadataDraft((current) => ({
                        ...current,
                        field: event.target.value,
                      }))}
                    />
                  </label>
                </div>
              ) : (
                <dl className="wlv-si-diagnostic-summary">
                  {diagnosticKnownMetadata.map((item) => (
                    <div key={item.label}>
                      <dt>{item.label}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>
              )}

              {diagnosticFallbackCandidate?.geometry_preview ? (
                <>
                  <h4>Wellbore Geometry</h4>
                  <dl className="wlv-si-diagnostic-summary">
                    <div>
                      <dt>Format</dt>
                      <dd>{diagnosticFallbackCandidate.geometry_preview.source_format ?? '—'}</dd>
                    </div>
                    <div>
                      <dt>Stations</dt>
                      <dd>{diagnosticFallbackCandidate.geometry_preview.station_count ?? 0}</dd>
                    </div>
                    <div>
                      <dt>MD Range</dt>
                      <dd>{geometryPreviewLabel(diagnosticFallbackCandidate)}</dd>
                    </div>
                    <div>
                      <dt>Warnings</dt>
                      <dd>{diagnosticFallbackCandidate.geometry_preview.warning_count ?? 0}</dd>
                    </div>
                  </dl>
                </>
              ) : null}
            </section>

            {diagnosticLoading ? (
              <p className="wlv-si-diagnostic-note">
                Loading backend-owned diagnostics…
              </p>
            ) : null}

            {diagnosticError ? (
              <p className="wlv-si-diagnostic-note is-error">
                {diagnosticError}
              </p>
            ) : null}

            {candidateDiagnostics ? (
              <>
                <section className="wlv-si-diagnostic-section">
                  <h3>Critical Actions</h3>

                  {diagnosticFallbackCandidate?.readiness_issues?.length ? (
                    <ul className="wlv-si-diagnostic-flags">
                      {diagnosticFallbackCandidate.readiness_issues.map(
                        (issue) => (
                          <li
                            key={issue}
                            className="is-blocker"
                          >
                            <strong>Promotion blocker</strong>
                            <p>{issue}</p>
                          </li>
                        ),
                      )}
                    </ul>
                  ) : (
                    <p className="wlv-si-diagnostic-note">
                      No critical actions required for promotion.
                    </p>
                  )}

                  {diagnosticFallbackCandidate?.depth_normalization?.status
                    === 'review_required' ? (
                    <div className="wlv-si-diagnostic-critical-action">
                      <strong>Choose depth unit</strong>
                      <p className="wlv-si-diagnostic-note">
                        The backend requires a normalized depth unit before
                        this source can be promoted.
                      </p>

                      <div className="wlv-si-toolbar-actions">
                        {diagnosticFallbackCandidate.depth_normalization.options.map(
                          (option) => (
                            <button
                              key={option.target_unit}
                              type="button"
                              className="wlv-si-detail-button"
                              disabled={busyAction !== null}
                              onClick={() =>
                                void resolveDepthUnit(
                                  diagnosticFallbackCandidate,
                                  option.target_unit,
                                )
                              }
                            >
                              Use{' '}
                              {option.target_unit === 'm'
                                ? 'metres'
                                : 'feet'}{' '}
                              (
                              {option.start_depth.toLocaleString(
                                undefined,
                                { maximumFractionDigits: 3 },
                              )}
                              –
                              {option.stop_depth.toLocaleString(
                                undefined,
                                { maximumFractionDigits: 3 },
                              )}{' '}
                              {option.target_unit})
                            </button>
                          ),
                        )}
                      </div>
                    </div>
                  ) : null}
                </section>

                <section className="wlv-si-diagnostic-section">
                  <h3>Parsing Analysis</h3>

                  {candidateDiagnostics.flags.filter(
                    (flag) => flag.phase === 'parse',
                  ).length === 0 ? (
                    <p className="wlv-si-diagnostic-note">
                      No parsing findings reported.
                    </p>
                  ) : (
                    <ul className="wlv-si-diagnostic-flags">
                      {candidateDiagnostics.flags
                        .filter((flag) => flag.phase === 'parse')
                        .map((flag) => (
                          <li
                            key={`${flag.phase}:${flag.code}:${flag.message}`}
                            className={`is-${flag.severity}`}
                          >
                            <strong>{flag.title}</strong>
                            <p>{flag.message}</p>
                            {flag.field_name ? (
                              <small>Field: {flag.field_name}</small>
                            ) : null}
                          </li>
                        ))}
                    </ul>
                  )}
                </section>

                <section className="wlv-si-diagnostic-section">
                  <h3>QAQC Analysis</h3>

                  {(() => {
                    const qaqcFlags = candidateDiagnostics.flags.filter(
                      (flag) => flag.phase === 'qaqc',
                    );
                    const passedFlags = qaqcFlags.filter(
                      (flag) => flag.severity === 'success',
                    );
                    const warningFlags = qaqcFlags.filter(
                      (flag) => flag.severity === 'warning',
                    );
                    const failureFlags = qaqcFlags.filter(
                      (flag) =>
                        flag.severity === 'error'
                        || flag.severity === 'blocker',
                    );
                    const informationalFlags = qaqcFlags.filter(
                      (flag) => flag.severity === 'info',
                    );
                    const issueFlags = [
                      ...failureFlags,
                      ...warningFlags,
                      ...informationalFlags,
                    ];

                    if (qaqcFlags.length === 0) {
                      return (
                        <p className="wlv-si-diagnostic-note">
                          No QAQC findings reported.
                        </p>
                      );
                    }

                    return (
                      <>
                        <div className="wlv-si-qaqc-summary">
                          <div className="is-success">
                            <span>{passedFlags.length}</span>
                            <small>Passed</small>
                          </div>
                          <div className="is-warning">
                            <span>{warningFlags.length}</span>
                            <small>Warnings</small>
                          </div>
                          <div className="is-error">
                            <span>{failureFlags.length}</span>
                            <small>Failures</small>
                          </div>
                        </div>

                        {issueFlags.length > 0 ? (
                          <>
                            <h4 className="wlv-si-diagnostic-subheading">
                              Findings requiring attention
                            </h4>
                            <ul className="wlv-si-diagnostic-flags">
                              {issueFlags.map((flag) => (
                                <li
                                  key={`${flag.phase}:${flag.code}:${flag.message}`}
                                  className={`is-${flag.severity}`}
                                >
                                  <strong>{flag.title}</strong>
                                  <p>{flag.message}</p>
                                  {flag.field_name ? (
                                    <small>Field: {flag.field_name}</small>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          </>
                        ) : (
                          <p className="wlv-si-diagnostic-note">
                            No QAQC warnings or failures reported.
                          </p>
                        )}

                        {passedFlags.length > 0 ? (
                          <details className="wlv-si-qaqc-passed">
                            <summary>
                              Passed checks ({passedFlags.length})
                            </summary>
                            <ul className="wlv-si-diagnostic-flags">
                              {passedFlags.map((flag) => (
                                <li
                                  key={`${flag.phase}:${flag.code}:${flag.message}`}
                                  className="is-success"
                                >
                                  <strong>{flag.title}</strong>
                                  <p>{flag.message}</p>
                                  {flag.field_name ? (
                                    <small>Field: {flag.field_name}</small>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          </details>
                        ) : null}
                      </>
                    );
                  })()}
                </section>

                <section className="wlv-si-diagnostic-section">
                  <h3>Suggested Actions</h3>

                  {candidateDiagnostics.actions.length === 0 ? (
                    <p className="wlv-si-diagnostic-note">
                      No suggested actions.
                    </p>
                  ) : (
                    <>
                      <div className="wlv-si-diagnostic-actions">
                        {candidateDiagnostics.actions.map((action) => (
                          <button
                            key={`${action.phase}:${action.action_key}`}
                            type="button"
                            className="wlv-si-button"
                            disabled={!action.enabled}
                            title={action.reason ?? undefined}
                          >
                            {action.label}
                          </button>
                        ))}
                      </div>

                      {candidateDiagnostics.actions.some(
                        (action) => action.reason,
                      ) ? (
                        <ul className="wlv-si-diagnostic-action-reasons">
                          {candidateDiagnostics.actions
                            .filter((action) => action.reason)
                            .map((action) => (
                              <li key={`${action.action_key}:reason`}>
                                <strong>{action.label}:</strong>{' '}
                                {action.reason}
                              </li>
                            ))}
                        </ul>
                      ) : null}
                    </>
                  )}
                </section>

                <section className="wlv-si-diagnostic-section">
                  <h3>Source Evidence</h3>

                  <dl className="wlv-si-diagnostic-source">
                    <div>
                      <dt>Detected file type</dt>
                      <dd>
                        {candidateDiagnostics.summary.detected_file_type}
                      </dd>
                    </div>

                    <div>
                      <dt>Original path</dt>
                      <dd>
                        {candidateDiagnostics.summary.original_path ?? '—'}
                      </dd>
                    </div>

                    <div>
                      <dt>Relative path</dt>
                      <dd>
                        {candidateDiagnostics.summary.relative_path ?? '—'}
                      </dd>
                    </div>

                    <div>
                      <dt>Managed well</dt>
                      <dd>
                        {candidateDiagnostics.summary.managed_well_name
                          ?? candidateDiagnostics.summary.managed_well_id
                          ?? '—'}
                      </dd>
                    </div>
                  </dl>
                </section>

                <section className="wlv-si-diagnostic-section">
                  <h3>Actions</h3>

                  <div className="wlv-si-diagnostic-actions">
                    {diagnosticFallbackCandidate ? (
                      <button
                        type="button"
                        className="wlv-si-button"
                        disabled={busyAction !== null}
                        onClick={() =>
                          void exportCandidateOverlay(
                            diagnosticFallbackCandidate,
                          )
                        }
                      >
                        Export QAQC Report
                      </button>
                    ) : null}
                  </div>

                  <label className="wlv-si-diagnostic-toggle">
                    <input
                      type="checkbox"
                      checked={includeQaqcReportOnPromotion}
                      onChange={(event) =>
                        setIncludeQaqcReportOnPromotion(event.target.checked)
                      }
                    />
                    <span>Include QAQC report with promoted data</span>
                  </label>
                </section>
              </>
            ) : null}
          </div>
        </aside>
      ) : null}
    </section>
  );
}

export default SourceIntakeWorkbench;
