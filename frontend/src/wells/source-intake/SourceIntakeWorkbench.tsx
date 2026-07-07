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

type HumanActionChoice =
  | ''
  | 'accept_current'
  | 'accept_with_warning'
  | 'correct_metadata'
  | 'assign_existing'
  | 'create_new'
  | 'leave_unresolved'
  | 'exclude'
  | 'restore_to_mdp';

type ResolveResponse = {
  ok: boolean;
  resolved_count: number;
};

type RestoreToMdpResponse = {
  ok: boolean;
  action: string;
  restored_count: number;
  already_visible_count: number;
  blocked_count: number;
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
  const headerSelectRef = useRef<HTMLInputElement | null>(null);
  const directIngestInputRef = useRef<HTMLInputElement | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [directIngestDragActive, setDirectIngestDragActive] = useState(false);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [managedWells, setManagedWells] = useState<ManagedWellSummary[]>([]);
  const [humanAction, setHumanAction] = useState<HumanActionChoice>('');
  const [assignmentTargetId, setAssignmentTargetId] = useState('');
  const [decisionReason, setDecisionReason] = useState('');
  const [newWellName, setNewWellName] = useState('');
  const [newWellUwi, setNewWellUwi] = useState('');
  const [newWellOperator, setNewWellOperator] = useState('');
  const [newWellField, setNewWellField] = useState('');
  const [newWellBlock, setNewWellBlock] = useState('');
  const [correctedWellName, setCorrectedWellName] = useState('');
  const [correctedWellUwi, setCorrectedWellUwi] = useState('');
  const [correctedWellOperator, setCorrectedWellOperator] = useState('');
  const [correctedWellField, setCorrectedWellField] = useState('');
  const [correctedWellBlock, setCorrectedWellBlock] = useState('');

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

  const visibleEligibleCandidateIds = useMemo(
    () => visibleCandidates.filter(candidateIsRegisterable).map((candidate) => candidate.source_file_id),
    [visibleCandidates],
  );

  const selectedCandidateCount = selectedCandidateIds.size;
  const selectedCandidates = useMemo(
    () => candidates.filter((candidate) => selectedCandidateIds.has(candidate.source_file_id)),
    [candidates, selectedCandidateIds],
  );
  const selectedCanAccept = selectedCandidates.length > 0
    && selectedCandidates.every((candidate) => candidate.available_human_actions.includes('accept'));
  const selectedCanCorrect = selectedCandidates.length === 1
    && selectedCandidates.every((candidate) => candidate.available_human_actions.includes('correct'));
  const selectedCanAssign = selectedCandidates.length > 0
    && selectedCandidates.every((candidate) => candidate.available_human_actions.includes('assign'));
  const selectedCanExclude = selectedCandidates.length > 0
    && selectedCandidates.every((candidate) => candidate.available_human_actions.includes('exclude'));
  const selectedCanClearDecision = selectedCandidates.length > 0
    && selectedCandidates.every((candidate) => Boolean(candidate.current_decision));
  const selectedCanRestoreToMdp = selectedCandidates.length > 0
    && selectedCandidates.every(
      (candidate) => candidate.registration_status === 'registered'
        && Boolean(candidate.managed_well_id),
    );
  const visibleSelectedCandidateCount = visibleCandidateIds.filter((candidateId) => selectedCandidateIds.has(candidateId)).length;
  const selectedRegisterableCount = visibleEligibleCandidateIds.filter((candidateId) => selectedCandidateIds.has(candidateId)).length;
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
      { label: 'MDP Ready', value: labelize(candidateDiagnostics?.mdp_ready_status ?? fallback?.readiness_state ?? 'review_required') },
      { label: 'Registration', value: labelize(candidateDiagnostics?.summary.registration_status ?? fallback?.registration_status ?? 'not_registered') },
    ];
  }, [candidateDiagnostics, diagnosticFallbackCandidate]);

  const loadManagedWells = useCallback(async () => {
    const records = await fetchWlvJson<ManagedWellSummary[]>('/api/wlv/inventory/wells');
    setManagedWells(
      [...records].sort((a, b) => a.well_name.localeCompare(b.well_name)),
    );
  }, []);

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
    Promise.all([loadWorkbench(), loadManagedWells()])
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Unable to load Source Intake workbench.'))
      .finally(() => setBusyAction(null));
  }, [loadManagedWells, loadWorkbench]);

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
    await Promise.all([loadWorkbench(), loadManagedWells()]);
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

  const resetHumanActionForm = () => {
    setHumanAction('');
    setAssignmentTargetId('');
    setDecisionReason('');
    setNewWellName('');
    setNewWellUwi('');
    setNewWellOperator('');
    setNewWellField('');
    setNewWellBlock('');
    setCorrectedWellName('');
    setCorrectedWellUwi('');
    setCorrectedWellOperator('');
    setCorrectedWellField('');
    setCorrectedWellBlock('');
  };

  const handleApplyHumanAction = () => runAction('human-action', async () => {
    if (selectedCandidates.length === 0) {
      throw new Error('Select at least one Source Intake candidate.');
    }
    if (!humanAction) {
      throw new Error('Select a human action before applying.');
    }
    if (humanAction === 'restore_to_mdp') {
      if (!selectedCanRestoreToMdp) {
        throw new Error('Every selected candidate must have a retained MSI registration.');
      }
      const response = await fetchWlvJson<RestoreToMdpResponse>('/api/wlv/source-intake/restore-to-mdp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_ids: selectedCandidates.map((candidate) => candidate.source_file_id),
          actor: 'user',
          reason: decisionReason.trim() || 'Restored from WSI to MDP.',
        }),
      });
      await Promise.all([loadWorkbench(), loadManagedWells()]);
      setSelectedCandidateIds(new Set());
      resetHumanActionForm();
      setMessage(
        `Restore to MDP: ${response.restored_count} restored · `
        + `${response.already_visible_count} already visible · ${response.blocked_count} blocked.`,
      );
      return;
    }
    if (
      (humanAction === 'accept_current' || humanAction === 'accept_with_warning')
      && !selectedCanAccept
    ) {
      throw new Error('The backend does not allow acceptance for every selected candidate.');
    }
    if (humanAction === 'correct_metadata' && !selectedCanCorrect) {
      throw new Error('Metadata correction requires exactly one selected candidate that permits correction.');
    }
    if (
      (humanAction === 'assign_existing' || humanAction === 'create_new')
      && !selectedCanAssign
    ) {
      throw new Error('The backend does not allow assignment for every selected candidate.');
    }
    if (humanAction === 'exclude' && !selectedCanExclude) {
      throw new Error('The backend does not allow exclusion for every selected candidate.');
    }
    if (humanAction === 'leave_unresolved' && !selectedCanClearDecision) {
      throw new Error('Every selected candidate must have a current decision before it can be cleared.');
    }
    if (humanAction === 'assign_existing' && !assignmentTargetId) {
      throw new Error('Select an existing managed well.');
    }
    if (humanAction === 'create_new' && !newWellName.trim()) {
      throw new Error('Enter the confirmed new well name.');
    }
    if (humanAction === 'accept_with_warning' && !decisionReason.trim()) {
      throw new Error('Enter a reason for accepting the current warning state.');
    }
    if (humanAction === 'correct_metadata' && ![
      correctedWellName,
      correctedWellUwi,
      correctedWellOperator,
      correctedWellField,
      correctedWellBlock,
    ].some((value) => value.trim())) {
      throw new Error('Enter at least one corrected metadata value.');
    }
    if (humanAction === 'exclude' && !decisionReason.trim()) {
      throw new Error('Enter a reason for exclusion.');
    }

    const decisions = selectedCandidates.map((candidate) => {
      if (humanAction === 'accept_current') {
        return {
          occurrence_id: candidate.occurrence_id,
          action: 'confirm_suggestion',
          actor: 'user',
          reason: decisionReason.trim() || 'Accepted current Source Intake metadata.',
        };
      }
      if (humanAction === 'accept_with_warning') {
        return {
          occurrence_id: candidate.occurrence_id,
          action: 'warning_accepted',
          actor: 'user',
          reason: decisionReason.trim(),
          accepted_warning_codes: candidateAcceptedFindingCodes(candidate),
        };
      }
      if (humanAction === 'correct_metadata') {
        return {
          occurrence_id: candidate.occurrence_id,
          action: 'manual_correction',
          actor: 'user',
          reason: decisionReason.trim() || 'Corrected Source Intake metadata.',
          resolved_values: {
            ...(correctedWellName.trim() ? { well_name: correctedWellName.trim() } : {}),
            ...(correctedWellUwi.trim() ? { uwi: correctedWellUwi.trim() } : {}),
            ...(correctedWellOperator.trim() ? { operator: correctedWellOperator.trim() } : {}),
            ...(correctedWellField.trim() ? { field: correctedWellField.trim() } : {}),
            ...(correctedWellBlock.trim() ? { block: correctedWellBlock.trim() } : {}),
          },
        };
      }
      if (humanAction === 'assign_existing') {
        return {
          occurrence_id: candidate.occurrence_id,
          action: 'well_assigned',
          actor: 'user',
          reason: decisionReason.trim() || 'Assigned from Source Intake.',
          assignment_mode: 'existing_well',
          target_managed_well_id: assignmentTargetId,
        };
      }
      if (humanAction === 'create_new') {
        return {
          occurrence_id: candidate.occurrence_id,
          action: 'well_assigned',
          actor: 'user',
          reason: decisionReason.trim() || 'New well confirmed from Source Intake.',
          assignment_mode: 'new_well',
          new_well_values: {
            well_name: newWellName.trim(),
            ...(newWellUwi.trim() ? { uwi: newWellUwi.trim() } : {}),
            ...(newWellOperator.trim() ? { operator: newWellOperator.trim() } : {}),
            ...(newWellField.trim() ? { field: newWellField.trim() } : {}),
            ...(newWellBlock.trim() ? { block: newWellBlock.trim() } : {}),
          },
        };
      }
      if (humanAction === 'exclude') {
        return {
          occurrence_id: candidate.occurrence_id,
          action: 'excluded',
          actor: 'user',
          reason: decisionReason.trim(),
        };
      }
      return {
        occurrence_id: candidate.occurrence_id,
        action: 'reopened',
        actor: 'user',
        reason: decisionReason.trim() || 'Current decision cleared from Source Intake.',
      };
    });

    const response = await fetchWlvJson<ResolveResponse>('/api/wlv/source-intake/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decisions }),
    });

    await Promise.all([loadWorkbench(), loadManagedWells()]);
    setSelectedCandidateIds(new Set());
    resetHumanActionForm();
    setMessage(`Applied human decision to ${response.resolved_count} candidate(s).`);
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

  const handleRegister = () => runAction('register', async () => {
    const candidateIds = visibleCandidates
      .filter((candidate) => selectedCandidateIds.has(candidate.source_file_id) && candidateIsRegisterable(candidate))
      .map((candidate) => candidate.source_file_id);
    if (candidateIds.length === 0) {
      throw new Error('Select at least one eligible well log or wellbore geometry candidate before registering.');
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

  const openCandidateDiagnostics = async (candidate: SourceFileCandidate) => {
    const candidateId = candidate.source_file_id;
    setDiagnosticCandidateId(candidateId);
    setDiagnosticCandidate(candidate);
    setCandidateDiagnostics(null);
    setDiagnosticError('');
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
            <span>LAS, DLIS, CSV and other supported files</span>
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
                    <option value="eligible">Sift: ready for WMD</option>
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
                <button type="button" className="wlv-si-button" onClick={toggleAllVisibleEligible} disabled={visibleEligibleCandidateIds.length === 0}>
                  {selectedRegisterableCount === visibleEligibleCandidateIds.length && visibleEligibleCandidateIds.length > 0 ? 'Clear Eligible' : 'Select Eligible'}
                </button>
                <button
                  type="button"
                  className="wlv-si-button wlv-si-button--primary"
                  onClick={handleRegister}
                  disabled={Boolean(busyAction || selectedRegisterableCount === 0)}
                >
                  Make Available ({selectedRegisterableCount})
                </button>
                <button type="button" className="wlv-si-button" onClick={clearCandidateSelection} disabled={selectedCandidateCount === 0}>
                  Clear Selection
                </button>
                <button type="button" className="wlv-si-button" onClick={exportSelectedOverlays} disabled={selectedCandidateCount === 0 || Boolean(busyAction)}>
                  Export QAQC / Metadata
                </button>
                <button type="button" className="wlv-si-button" onClick={handleRefresh} disabled={Boolean(busyAction)}>
                  Refresh
                </button>
              </div>
            </div>

            <section className="wlv-si-candidate-action-panel" aria-label="Selected candidate human action">
              <div className="wlv-si-candidate-action-panel__summary">
                <span className="wlv-si-candidate-action-panel__eyebrow">Selected candidates</span>
                <strong>{selectedCandidateCount}</strong>
                <span>Resolve non-fatal findings, assign a well, or exclude from intake.</span>
              </div>

              <div className="wlv-si-candidate-action-panel__controls">
                <label className="wlv-si-action-field wlv-si-action-field--wide">
                  <span>Action</span>
                  <select
                    value={humanAction}
                    onChange={(event) => setHumanAction(event.currentTarget.value as HumanActionChoice)}
                    disabled={selectedCandidateCount === 0 || Boolean(busyAction)}
                  >
                    <option value="">Choose an action</option>
                    <option value="accept_current" disabled={!selectedCanAccept}>
                      Accept current metadata
                    </option>
                    <option value="accept_with_warning" disabled={!selectedCanAccept}>
                      Accept current metadata with warning
                    </option>
                    <option value="correct_metadata" disabled={!selectedCanCorrect}>
                      Correct metadata for selected candidate
                    </option>
                    <option value="assign_existing" disabled={!selectedCanAssign}>
                      Assign selected to existing well
                    </option>
                    <option value="create_new" disabled={!selectedCanAssign}>
                      Create new well from selected
                    </option>
                    <option value="restore_to_mdp" disabled={!selectedCanRestoreToMdp}>
                      Restore to MDP
                    </option>
                    <option value="leave_unresolved" disabled={!selectedCanClearDecision}>
                      Clear current decision / leave unresolved
                    </option>
                    <option value="exclude" disabled={!selectedCanExclude}>
                      Exclude selected from intake
                    </option>
                  </select>
                </label>

              {humanAction === 'correct_metadata' && (
                <div className="wlv-si-action-fields-grid">
                  <label className="wlv-si-action-field">
                    <span>Well Name</span>
                    <input value={correctedWellName} onChange={(event) => setCorrectedWellName(event.currentTarget.value)} />
                  </label>
                  <label className="wlv-si-action-field">
                    <span>UWI / API</span>
                    <input value={correctedWellUwi} onChange={(event) => setCorrectedWellUwi(event.currentTarget.value)} />
                  </label>
                  <label className="wlv-si-action-field">
                    <span>Operator</span>
                    <input value={correctedWellOperator} onChange={(event) => setCorrectedWellOperator(event.currentTarget.value)} />
                  </label>
                  <label className="wlv-si-action-field">
                    <span>Field</span>
                    <input value={correctedWellField} onChange={(event) => setCorrectedWellField(event.currentTarget.value)} />
                  </label>
                  <label className="wlv-si-action-field">
                    <span>Block</span>
                    <input value={correctedWellBlock} onChange={(event) => setCorrectedWellBlock(event.currentTarget.value)} />
                  </label>
                </div>
              )}

              {humanAction === 'assign_existing' && (
                <label className="wlv-si-action-field">
                  <span>Existing Well</span>
                  <select
                    value={assignmentTargetId}
                    onChange={(event) => setAssignmentTargetId(event.currentTarget.value)}
                  >
                    <option value="">Select managed well</option>
                    {managedWells.map((well) => (
                      <option key={well.managed_well_id} value={well.managed_well_id}>
                        {well.well_name}{well.metadata?.uwi ? ` · ${well.metadata.uwi}` : ''}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {humanAction === 'create_new' && (
                <>
                  <label className="wlv-si-action-field">
                    <span>New Well Name</span>
                    <input value={newWellName} onChange={(event) => setNewWellName(event.currentTarget.value)} />
                  </label>
                  <label className="wlv-si-action-field">
                    <span>UWI / API</span>
                    <input value={newWellUwi} onChange={(event) => setNewWellUwi(event.currentTarget.value)} />
                  </label>
                  <label className="wlv-si-action-field">
                    <span>Operator</span>
                    <input value={newWellOperator} onChange={(event) => setNewWellOperator(event.currentTarget.value)} />
                  </label>
                  <label className="wlv-si-action-field">
                    <span>Field</span>
                    <input value={newWellField} onChange={(event) => setNewWellField(event.currentTarget.value)} />
                  </label>
                  <label className="wlv-si-action-field">
                    <span>Block</span>
                    <input value={newWellBlock} onChange={(event) => setNewWellBlock(event.currentTarget.value)} />
                  </label>
                </>
              )}

              {humanAction && (
                <label className="wlv-si-action-field wlv-si-action-field--reason">
                  <span>{humanAction === 'exclude' || humanAction === 'accept_with_warning' ? 'Reason (required)' : 'Reason / Note'}</span>
                  <input
                    value={decisionReason}
                    onChange={(event) => setDecisionReason(event.currentTarget.value)}
                  />
                </label>
              )}

                <button
                  type="button"
                  className="wlv-si-button wlv-si-button--primary wlv-si-candidate-action-panel__apply"
                  onClick={handleApplyHumanAction}
                  disabled={Boolean(busyAction || selectedCandidateCount === 0 || !humanAction)}
                >
                  Apply to Selected ({selectedCandidateCount})
                </button>
              </div>
            </section>

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
                    <th>WMD Available</th>
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
                              <span className="wlv-si-pill is-ok">Available in WMD</span>
                              <small>{candidate.candidate_role === 'wellbore_geometry_candidate' ? `${candidate.registered_trajectory_count ?? 1} trajectory` : `${candidate.registered_curve_count ?? curveCount} curves`} · {labelize(candidate.wdv_state ?? 'not_loaded')}</small>
                            </div>
                          ) : eligible ? (
                            <div className="wlv-si-status-stack">
                              <span className="wlv-si-pill is-ok">Ready for WMD</span>
                            </div>
                          ) : (
                            <div className="wlv-si-status-stack">
                              <span className="wlv-si-pill is-warning">Review</span>
                            </div>
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
              <h3>Known Metadata</h3>
              <dl className="wlv-si-diagnostic-summary">
                {diagnosticKnownMetadata.map((item) => (
                  <div key={item.label}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            {diagnosticLoading ? (
              <p className="wlv-si-diagnostic-note">Loading backend-owned diagnostics…</p>
            ) : null}

            {diagnosticError ? (
              <p className="wlv-si-diagnostic-note is-error">{diagnosticError}</p>
            ) : null}

            {candidateDiagnostics ? (
              <>
              <section className="wlv-si-diagnostic-section">
                <h3>Workflow Status</h3>
                <dl className="wlv-si-diagnostic-summary">
                  <div>
                    <dt>Well</dt>
                  <dd>{candidateDiagnostics.summary.well_name ?? '—'}</dd>
                </div>
                <div>
                  <dt>Role</dt>
                  <dd>{labelize(candidateDiagnostics.summary.candidate_role)}</dd>
                </div>
                <div>
                  <dt>Curves</dt>
                  <dd>{candidateDiagnostics.summary.curve_count}</dd>
                </div>
                <div>
                  <dt>Parse</dt>
                  <dd>{parseStatusLabel(candidateDiagnostics.parse_status)}</dd>
                </div>
                <div>
                  <dt>QAQC</dt>
                  <dd>{labelize(candidateDiagnostics.qaqc_status.status ?? 'not_checked')}</dd>
                </div>
                  <div>
                    <dt>WMD Available</dt>
                    <dd>{labelize(candidateDiagnostics.mdp_ready_status)}</dd>
                  </div>
                </dl>
              </section>



              {diagnosticFallbackCandidate?.depth_normalization ? (
                <section className="wlv-si-diagnostic-section">
                  <h3>Depth Normalization</h3>
                  <dl className="wlv-si-diagnostic-summary">
                    <div><dt>Raw encoding</dt><dd>{diagnosticFallbackCandidate.depth_normalization.raw_unit ?? '—'}</dd></div>
                    <div><dt>Raw interval</dt><dd>{typeof diagnosticFallbackCandidate.depth_normalization.raw_start_depth === 'number' && typeof diagnosticFallbackCandidate.depth_normalization.raw_stop_depth === 'number' ? `${diagnosticFallbackCandidate.depth_normalization.raw_start_depth.toLocaleString()}–${diagnosticFallbackCandidate.depth_normalization.raw_stop_depth.toLocaleString()}` : '—'}</dd></div>
                    <div><dt>Status</dt><dd>{labelize(diagnosticFallbackCandidate.depth_normalization.status)}</dd></div>
                    <div><dt>Selected unit</dt><dd>{diagnosticFallbackCandidate.depth_normalization.decision?.target_unit ?? 'Not selected'}</dd></div>
                  </dl>
                  {diagnosticFallbackCandidate.depth_normalization.status === 'review_required' ? (
                    <div
                      style={{
                        border: '2px solid rgba(239, 68, 68, 0.95)',
                        borderRadius: '10px',
                        padding: '0.9rem',
                        marginTop: '0.85rem',
                        background: 'rgba(127, 29, 29, 0.12)',
                        boxShadow: '0 0 0 1px rgba(239, 68, 68, 0.18) inset',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '0.74rem',
                          fontWeight: 700,
                          letterSpacing: '0.08em',
                          textTransform: 'uppercase',
                          color: '#fca5a5',
                          marginBottom: '0.45rem',
                        }}
                      >
                        Action required: choose depth unit
                      </div>
                      <p className="wlv-si-diagnostic-note" style={{ marginTop: 0 }}>The source provides a valid physical scale but does not govern whether WSI should normalize it to metres or feet. Select the target explicitly.</p>
                      <div className="wlv-si-toolbar-actions">
                        {diagnosticFallbackCandidate.depth_normalization.options.map((option) => (
                          <button
                            key={option.target_unit}
                            type="button"
                            className="wlv-si-detail-button"
                            disabled={busyAction !== null}
                            onClick={() => void resolveDepthUnit(diagnosticFallbackCandidate, option.target_unit)}
                          >
                            Use {option.target_unit === 'm' ? 'metres' : 'feet'} ({option.start_depth.toLocaleString(undefined, { maximumFractionDigits: 3 })}–{option.stop_depth.toLocaleString(undefined, { maximumFractionDigits: 3 })} {option.target_unit})
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>
              ) : null}

              {diagnosticFallbackCandidate?.geometry_preview ? (
                <section className="wlv-si-diagnostic-section">
                  <h3>Wellbore Geometry Preview</h3>
                  <dl className="wlv-si-diagnostic-summary">
                    <div><dt>Format</dt><dd>{diagnosticFallbackCandidate.geometry_preview.source_format ?? '—'}</dd></div>
                    <div><dt>Stations</dt><dd>{diagnosticFallbackCandidate.geometry_preview.station_count ?? 0}</dd></div>
                    <div><dt>MD Range</dt><dd>{geometryPreviewLabel(diagnosticFallbackCandidate)}</dd></div>
                    <div><dt>Warnings</dt><dd>{diagnosticFallbackCandidate.geometry_preview.warning_count ?? 0}</dd></div>
                  </dl>
                  <p className="wlv-si-diagnostic-note">
                    Preview only. Registration to MSI and WBV loading remain disabled until trajectory approval is implemented.
                  </p>
                </section>
              ) : null}

              {(['parse', 'qaqc', 'mdp_ready'] as CandidateDiagnosticPhase[]).map((phase) => {
                const phaseFlags = candidateDiagnostics.flags.filter((flag) => flag.phase === phase);
                return (
                  <section className="wlv-si-diagnostic-section" key={phase}>
                    <h3>{phase === 'mdp_ready' ? 'WMD Available' : phase.toUpperCase()}</h3>
                    {phaseFlags.length === 0 ? (
                      <p className="wlv-si-diagnostic-note">No diagnostic flags reported for this phase.</p>
                    ) : (
                      <ul className="wlv-si-diagnostic-flags">
                        {phaseFlags.map((flag) => (
                          <li key={`${flag.phase}:${flag.code}:${flag.message}`} className={`is-${flag.severity}`}>
                            <strong>{flag.title}</strong>
                            <p>{flag.message}</p>
                            {flag.field_name ? <small>Field: {flag.field_name}</small> : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                );
              })}

              <section className="wlv-si-diagnostic-section">
                <h3>Suggested Actions</h3>
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
                {candidateDiagnostics.actions.some((action) => action.reason) ? (
                  <ul className="wlv-si-diagnostic-action-reasons">
                    {candidateDiagnostics.actions
                      .filter((action) => action.reason)
                      .map((action) => (
                        <li key={`${action.action_key}:reason`}>
                          <strong>{action.label}:</strong> {action.reason}
                        </li>
                      ))}
                  </ul>
                ) : null}
              </section>

              <section className="wlv-si-diagnostic-section">
                <h3>Source Evidence</h3>
                <dl className="wlv-si-diagnostic-source">
                  <div>
                    <dt>Detected file type</dt>
                    <dd>{candidateDiagnostics.summary.detected_file_type}</dd>
                  </div>
                  <div>
                    <dt>Original path</dt>
                    <dd>{candidateDiagnostics.summary.original_path ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Managed well</dt>
                    <dd>{candidateDiagnostics.summary.managed_well_name ?? candidateDiagnostics.summary.managed_well_id ?? '—'}</dd>
                  </div>
                </dl>
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
