import { useEffect, useMemo, useRef, useState } from 'react';
import * as XLSX from 'xlsx';
import { fetchWlvJson, wlvApiBaseUrl } from '../../api/wlvBackendClient';
import { toolboxAiExpectedResponseRevision, toolboxAiPackageFilename, toolboxAiPackageRevision, useToolboxAiRevision } from './toolboxAiRevision';
import { fetchToolboxAiRules } from './toolboxAiRulesClient';
import {
  type DeterministicFailureChoice,
  type DeterministicFailureDecision,
  type DeterministicFailurePrompt,
  type EvidencePreparationResponse,
  type EvidencePreparationSummary,
  type GraphicsExportChoice,
  type PreparedEvidenceFile,
  type SkippedArchiveMember,
  type SupportingFile,
  type SupportingFileAuditResult,
  type SupportingFilePreScanResult,
  downloadCompressedJsonPackage,
  downloadText,
  expandZipSupportingFile,
  filePayload,
} from './toolboxAiIntakeExport';

type ManagedWellRecord = {
  managed_well_id: string;
  well_id: string;
  uwi?: string | null;
  well_name?: string | null;
  display_name?: string | null;
  wellbore_name?: string | null;
  depth_unit?: string | null;
  top_depth?: number | null;
  base_depth?: number | null;
  product_groups?: Array<{
    items?: Array<{
      product_subgroup_key?: string | null;
      provenance?: {
        deviation_survey_stations?: Array<Record<string, unknown>>;
        survey_metadata?: Record<string, unknown>;
      } | null;
    }>;
  }>;
};

type ReviewState = 'unreviewed' | 'confirmed' | 'edited' | 'rejected' | 'existing';
type StationType = 'measured' | 'calculated' | 'extrapolated' | 'casing' | 'manual';

type Candidate = {
  id: string;
  state: ReviewState;
  selected: boolean;
  md: string;
  inclination: string;
  azimuth: string;
  tvd: string;
  northSouth: string;
  eastWest: string;
  doglegSeverity: string;
  verticalSection: string;
  depthUnit: string;
  coordinateUnit: string;
  doglegUnit: string;
  stationType: StationType;
  sourceFile: string;
  sourcePage: string;
  sourceTablePage: string;
  evidenceReference: string;
  confidence: string;
  notes: string;
  original: Omit<Candidate, 'original'> | null;
};

type SurveyMetadata = {
  surveyName: string;
  surveyType: string;
  status: string;
  rig: string;
  datum: string;
  coordinateOrigin: string;
  verticalSectionOrigin: string;
  verticalSectionAzimuth: string;
  calculationMethod: string;
  createdDate: string;
  revisedDate: string;
  sourceNotes: string;
};

type QaqcSeverity = 'information' | 'warning' | 'failure';
type QaqcFinding = {
  ruleId: string;
  category: string;
  severity: QaqcSeverity;
  message: string;
  stationId?: string;
  field?: string;
  observedValue?: unknown;
  expectedCondition?: string;
};

type PersistedSession = {
  selectedWellId: string;
  candidates: Candidate[];
  supportingFiles: SupportingFile[];
  surveyMetadata: SurveyMetadata;
  savedAt: string;
};

const STORAGE_PREFIX = 'wlv.dsm.review.v1.';
const ACTIVE_KEY = 'wlv.dsm.activeSession.v1';

const normalize = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim();
const key = (value: unknown) => normalize(value).toLowerCase().replace(/[^a-z0-9]+/g, '');
const idFor = (seed: string) => `${Date.now()}-${Math.random().toString(36).slice(2)}-${seed}`;
const numberOrNull = (value: string) => normalize(value) === '' ? null : Number(value);

function cloneCandidate(candidate: Candidate): Omit<Candidate, 'original'> {
  const { original: _original, ...copy } = candidate;
  return { ...copy };
}

function emptyMetadata(): SurveyMetadata {
  return {
    surveyName: '',
    surveyType: 'Definitive',
    status: 'reviewed',
    rig: '',
    datum: 'RKB',
    coordinateOrigin: '',
    verticalSectionOrigin: 'Wellhead',
    verticalSectionAzimuth: '',
    calculationMethod: 'minimum_curvature',
    createdDate: '',
    revisedDate: '',
    sourceNotes: '',
  };
}

function emptyCandidate(unit = 'm', md = ''): Candidate {
  const candidate: Candidate = {
    id: idFor('manual'),
    state: 'unreviewed',
    selected: false,
    md,
    inclination: '',
    azimuth: '',
    tvd: '',
    northSouth: '',
    eastWest: '',
    doglegSeverity: '',
    verticalSection: '',
    depthUnit: unit || 'm',
    coordinateUnit: unit || 'm',
    doglegUnit: 'deg/30m',
    stationType: 'manual',
    sourceFile: 'Manual entry',
    sourcePage: '',
    sourceTablePage: '',
    evidenceReference: '',
    confidence: '',
    notes: '',
    original: null,
  };
  candidate.original = cloneCandidate(candidate);
  return candidate;
}

function valueFrom(row: Record<string, unknown>, ...names: string[]): string {
  for (const name of names) {
    if (normalize(row[name])) return normalize(row[name]);
    const found = Object.keys(row).find((candidate) => key(candidate) === key(name));
    if (found && normalize(row[found])) return normalize(row[found]);
  }
  return '';
}

function stationTypeFrom(value: string): StationType {
  const normalized = value.toLowerCase();
  if (normalized.includes('extrap')) return 'extrapolated';
  if (normalized.includes('casing') || normalized.includes('shoe')) return 'casing';
  if (normalized.includes('calc')) return 'calculated';
  if (normalized.includes('manual')) return 'manual';
  return 'measured';
}

function fromRecord(row: Record<string, unknown>, index: number, source: string, unit: string): Candidate {
  const candidate: Candidate = {
    id: idFor(`${source}-${index}`),
    state: 'unreviewed',
    selected: false,
    md: valueFrom(row, 'MD', 'Measured Depth', 'MeasuredDepth', 'Depth'),
    inclination: valueFrom(row, 'Inclination', 'Inc', 'Incl'),
    azimuth: valueFrom(row, 'Azimuth', 'Azi', 'Azim'),
    tvd: valueFrom(row, 'TVD', 'True Vertical Depth'),
    northSouth: valueFrom(row, 'North South', 'North/South', 'NS', 'Y Offset', 'Northing'),
    eastWest: valueFrom(row, 'East West', 'East/West', 'EW', 'X Offset', 'Easting'),
    doglegSeverity: valueFrom(row, 'Dogleg', 'Dogleg Severity', 'DLS'),
    verticalSection: valueFrom(row, 'Vertical Section', 'VS'),
    depthUnit: valueFrom(row, 'Depth Unit', 'Unit') || unit || 'm',
    coordinateUnit: valueFrom(row, 'Coordinate Unit') || unit || 'm',
    doglegUnit: valueFrom(row, 'Dogleg Unit') || 'deg/30m',
    stationType: stationTypeFrom(valueFrom(row, 'Station Type', 'Type', 'Status')),
    sourceFile: valueFrom(row, 'Source File', 'Source Document', 'Source') || source,
    sourcePage: valueFrom(row, 'PDF Page', 'Source Page', 'Page'),
    sourceTablePage: valueFrom(row, 'Table Page', 'Survey Page'),
    evidenceReference: valueFrom(row, 'Evidence', 'Evidence Reference', 'Source Reference'),
    confidence: valueFrom(row, 'Confidence'),
    notes: valueFrom(row, 'Notes', 'Remarks', 'Comment'),
    original: null,
  };
  if (candidate.notes.toLowerCase().includes('extrapolat')) candidate.stationType = 'extrapolated';
  candidate.original = cloneCandidate(candidate);
  return candidate;
}

function readActive(): PersistedSession | null {
  try {
    const raw = sessionStorage.getItem(ACTIVE_KEY);
    return raw ? JSON.parse(raw) as PersistedSession : null;
  } catch {
    sessionStorage.removeItem(ACTIVE_KEY);
    return null;
  }
}

function assessCandidates(candidates: Candidate[], metadata: SurveyMetadata) {
  const findings: QaqcFinding[] = [];
  const rowFindings = new Map<string, QaqcFinding[]>();

  const add = (finding: QaqcFinding) => {
    findings.push(finding);
    if (finding.stationId) {
      rowFindings.set(finding.stationId, [...(rowFindings.get(finding.stationId) ?? []), finding]);
    }
  };

  const active = candidates.filter((candidate) => candidate.state !== 'rejected');
  const approved = active.filter((candidate) => candidate.state === 'confirmed' || candidate.state === 'edited');

  if (approved.length < 2) {
    add({ ruleId: 'DSM-PUB-001', category: 'Publication blockers', severity: 'failure', message: 'At least two approved stations are required for publication.' });
  }

  const depthUnits = new Set(active.map((candidate) => normalize(candidate.depthUnit).toLowerCase()).filter(Boolean));
  if (depthUnits.size > 1) {
    add({ ruleId: 'DSM-UNIT-001', category: 'Units and references', severity: 'failure', message: `Mixed depth units are unresolved: ${[...depthUnits].join(', ')}.` });
  }

  const doglegUnits = new Set(active.map((candidate) => normalize(candidate.doglegUnit).toLowerCase()).filter(Boolean));
  if (doglegUnits.size > 1) {
    add({ ruleId: 'DSM-UNIT-002', category: 'Units and references', severity: 'failure', message: `Mixed dogleg units are unresolved: ${[...doglegUnits].join(', ')}.` });
  }

  if (!normalize(metadata.datum)) {
    add({ ruleId: 'DSM-REF-001', category: 'Units and references', severity: 'warning', message: 'Survey datum is not recorded.', field: 'datum' });
  }
  if (!normalize(metadata.coordinateOrigin)) {
    add({ ruleId: 'DSM-REF-001', category: 'Units and references', severity: 'warning', message: 'Coordinate origin is not recorded.', field: 'coordinateOrigin' });
  }

  active.forEach((candidate) => {
    const md = Number(candidate.md);
    const inc = Number(candidate.inclination);
    const azi = Number(candidate.azimuth);
    const tvd = Number(candidate.tvd);
    const dls = Number(candidate.doglegSeverity);

    if (!Number.isFinite(md)) add({ ruleId: 'DSM-REQ-001', category: 'Required fields', severity: 'failure', message: 'Numeric MD is required.', stationId: candidate.id, field: 'md', observedValue: candidate.md });
    if (!Number.isFinite(inc)) add({ ruleId: 'DSM-REQ-001', category: 'Required fields', severity: 'failure', message: 'Numeric inclination is required.', stationId: candidate.id, field: 'inclination', observedValue: candidate.inclination });
    else if (inc < 0 || inc > 180) add({ ruleId: 'DSM-INC-001', category: 'Inclination and azimuth', severity: 'failure', message: 'Inclination must be between 0 and 180°.', stationId: candidate.id, field: 'inclination', observedValue: inc });

    if (!Number.isFinite(azi)) add({ ruleId: 'DSM-REQ-001', category: 'Required fields', severity: 'failure', message: 'Numeric azimuth is required.', stationId: candidate.id, field: 'azimuth', observedValue: candidate.azimuth });
    else if (azi < 0 || azi >= 360) add({ ruleId: 'DSM-AZI-001', category: 'Inclination and azimuth', severity: 'failure', message: 'Azimuth must be between 0 and less than 360°.', stationId: candidate.id, field: 'azimuth', observedValue: azi });

    if (Number.isFinite(md) && Number.isFinite(tvd) && tvd > md) {
      add({ ruleId: 'DSM-TVD-001', category: 'Trajectory calculation', severity: 'warning', message: 'Source TVD exceeds MD; confirm datum and units.', stationId: candidate.id, field: 'tvd', observedValue: tvd, expectedCondition: `≤ ${md}` });
    }

    if (Number.isFinite(dls) && dls < 0) {
      add({ ruleId: 'DSM-DLS-001', category: 'Trajectory calculation', severity: 'failure', message: 'Dogleg severity cannot be negative.', stationId: candidate.id, field: 'doglegSeverity', observedValue: dls });
    }

    if (candidate.stationType === 'extrapolated') {
      add({ ruleId: 'DSM-EXT-001', category: 'Extrapolated and calculated stations', severity: 'information', message: 'Station is explicitly extrapolated.', stationId: candidate.id, field: 'stationType' });
    } else if (candidate.stationType === 'casing') {
      add({ ruleId: 'DSM-CAS-001', category: 'Extrapolated and calculated stations', severity: 'information', message: 'Casing position is a related marker, not automatically a primary station.', stationId: candidate.id, field: 'stationType' });
    }

    if (!normalize(candidate.evidenceReference) && !normalize(candidate.sourcePage)) {
      add({ ruleId: 'DSM-EVD-001', category: 'Source and applicability', severity: 'warning', message: 'Station has no page or evidence reference.', stationId: candidate.id, field: 'evidenceReference' });
    }
  });

  const orderedApproved = approved.filter((candidate) => Number.isFinite(Number(candidate.md)));
  for (let index = 1; index < orderedApproved.length; index += 1) {
    const previous = orderedApproved[index - 1];
    const current = orderedApproved[index];
    const previousMd = Number(previous.md);
    const currentMd = Number(current.md);

    if (currentMd < previousMd) {
      add({ ruleId: 'DSM-MD-001', category: 'Depth sequence', severity: 'failure', message: 'Approved MD is not strictly increasing in publication order.', stationId: current.id, field: 'md' });
    } else if (currentMd === previousMd) {
      add({ ruleId: 'DSM-MD-002', category: 'Depth sequence', severity: 'failure', message: `Duplicate approved MD ${currentMd}.`, stationId: current.id, field: 'md' });
    }

    const inclination = Number(current.inclination);
    const previousAzimuth = Number(previous.azimuth);
    const azimuth = Number(current.azimuth);
    if (inclination >= 1 && Number.isFinite(previousAzimuth) && Number.isFinite(azimuth)) {
      const raw = Math.abs(azimuth - previousAzimuth);
      const delta = Math.min(raw, 360 - raw);
      if (delta >= 150) {
        add({ ruleId: 'DSM-AZI-002', category: 'Inclination and azimuth', severity: 'warning', message: `Abrupt azimuth reversal of ${delta.toFixed(1)}° requires review.`, stationId: current.id, field: 'azimuth' });
      }
    }
  }

  const failures = findings.filter((finding) => finding.severity === 'failure').length;
  const warnings = findings.filter((finding) => finding.severity === 'warning').length;
  const information = findings.filter((finding) => finding.severity === 'information').length;
  const publicationState = failures ? 'blocked' : warnings ? 'ready_with_warnings' : 'ready';

  return { findings, rowFindings, failures, warnings, information, publicationState };
}

export function DeviationSurveyManagerPage({ onBack }: { onBack: () => void }) {
  const activeRef = useRef<PersistedSession | null>(readActive());
  const [wells, setWells] = useState<ManagedWellRecord[]>([]);
  const [selectedWellId, setSelectedWellId] = useState(activeRef.current?.selectedWellId ?? '');
  const [wellSearch, setWellSearch] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>(activeRef.current?.candidates ?? []);
  const [supportingFiles, setSupportingFiles] = useState<SupportingFile[]>(activeRef.current?.supportingFiles ?? []);
  const [fileObjects, setFileObjects] = useState<File[]>([]);
  const fileObjectsRef = useRef<File[]>([]);
  const [selectedSupportingFileIndexes, setSelectedSupportingFileIndexes] = useState<Set<number>>(() => new Set());
  const [deterministicSupportingFileIndexes, setDeterministicSupportingFileIndexes] = useState<Set<number>>(() => new Set());
  const [skippedArchiveMembers, setSkippedArchiveMembers] = useState<SkippedArchiveMember[]>([]);
  const [supportingFilePreScanResults, setSupportingFilePreScanResults] = useState<Record<number, SupportingFilePreScanResult>>({});
  const [supportingFileAuditResults, setSupportingFileAuditResults] = useState<Record<string, SupportingFileAuditResult>>({});
  const [activeSupportingFileAudit, setActiveSupportingFileAudit] = useState<SupportingFileAuditResult | null>(null);
  const [supportingManifestCollapsed, setSupportingManifestCollapsed] = useState(false);
  const [preScanRunning, setPreScanRunning] = useState(false);
  const [graphicsChoiceFiles, setGraphicsChoiceFiles] = useState<string[] | null>(null);
  const graphicsChoiceResolverRef = useRef<((choice: GraphicsExportChoice) => void) | null>(null);
  const [deterministicFailurePrompt, setDeterministicFailurePrompt] = useState<DeterministicFailurePrompt | null>(null);
  const deterministicFailureResolverRef = useRef<((decision: DeterministicFailureDecision) => void) | null>(null);
  const [rememberDeterministicFailureChoice, setRememberDeterministicFailureChoice] = useState(false);
  const [surveyMetadata, setSurveyMetadata] = useState<SurveyMetadata>(activeRef.current?.surveyMetadata ?? emptyMetadata());
  const [loadingWells, setLoadingWells] = useState(true);
  const [status, setStatus] = useState('Select a managed well to begin.');
  const [error, setError] = useState<string | null>(null);
  const [activeEditId, setActiveEditId] = useState<string | null>(null);
  const [supportingDragActive, setSupportingDragActive] = useState(false);
  const [responseDragActive, setResponseDragActive] = useState(false);
  const [focusedQaqcRowId, setFocusedQaqcRowId] = useState<string | null>(null);
  const supportingDragDepth = useRef(0);
  const responseDragDepth = useRef(0);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const responseRef = useRef<HTMLInputElement | null>(null);

  const selectedWell = useMemo(
    () => wells.find((well) => well.managed_well_id === selectedWellId) ?? null,
    [wells, selectedWellId],
  );
  useEffect(() => { fileObjectsRef.current = fileObjects; }, [fileObjects]);
  const aiRevision = useToolboxAiRevision('DSM', selectedWellId, candidates.map((candidate) => candidate.id));
  const filteredWells = useMemo(() => {
    const query = wellSearch.trim().toLowerCase();
    if (!query) return wells;
    return wells.filter((well) =>
      [well.display_name, well.well_name, well.wellbore_name, well.uwi, well.managed_well_id]
        .some((value) => normalize(value).toLowerCase().includes(query)),
    );
  }, [wells, wellSearch]);
  const summary = useMemo(() => ({
    total: candidates.length,
    approved: candidates.filter((candidate) => candidate.state === 'confirmed' || candidate.state === 'edited').length,
    rejected: candidates.filter((candidate) => candidate.state === 'rejected').length,
    pending: candidates.filter((candidate) => candidate.state === 'unreviewed').length,
  }), [candidates]);
  const qaqc = useMemo(() => assessCandidates(candidates, surveyMetadata), [candidates, surveyMetadata]);
  const candidateById = useMemo(
    () => new Map(candidates.map((candidate) => [candidate.id, candidate])),
    [candidates],
  );

  const fieldLabel = (fieldName?: string) => {
    const labels: Record<string, string> = {
      md: 'MD',
      measured_depth: 'MD',
      inclination: 'Inc',
      azimuth: 'Azi',
      tvd: 'TVD',
      true_vertical_depth: 'TVD',
      northSouth: 'N/S',
      eastWest: 'E/W',
      doglegSeverity: 'DLS',
      verticalSection: 'VS',
      stationType: 'Type',
      sourceFile: 'Source',
      sourcePage: 'Source page',
      evidenceReference: 'Evidence',
      datum: 'Datum',
      coordinateOrigin: 'Coordinate origin',
    };
    return fieldName ? labels[fieldName] ?? fieldName : '';
  };

  const focusQaqcFinding = (finding: QaqcFinding) => {
    if (!finding.stationId) return;
    setFocusedQaqcRowId(finding.stationId);
    const row = document.getElementById(`dsm-station-${finding.stationId}`);
    row?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
    window.setTimeout(
      () => setFocusedQaqcRowId((current) => current === finding.stationId ? null : current),
      2400,
    );
  };

  const selectedIds = useMemo(() => new Set(candidates.filter((candidate) => candidate.selected).map((candidate) => candidate.id)), [candidates]);

  useEffect(() => {
    let cancelled = false;
    fetchWlvJson<ManagedWellRecord[]>('/api/wlv/inventory/wells')
      .then((records) => {
        if (cancelled) return;
        setWells(records);
        setStatus(records.length ? 'Select a managed well to begin.' : 'No managed wells are available.');
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'Unable to load managed wells.');
      })
      .finally(() => {
        if (!cancelled) setLoadingWells(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (loadingWells) return;
    if (!selectedWellId) {
      setCandidates([]);
      setSupportingFiles([]);
      setFileObjects([]);
      setSurveyMetadata(emptyMetadata());
      return;
    }
    const active = activeRef.current;
    if (active?.selectedWellId === selectedWellId) {
      setCandidates(active.candidates ?? []);
      setSupportingFiles(active.supportingFiles ?? []);
      setSurveyMetadata(active.surveyMetadata ?? emptyMetadata());
      activeRef.current = null;
      setStatus('Restored active Deviation Survey Manager session.');
      return;
    }
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${selectedWellId}`);
    if (raw) {
      try {
        const persisted = JSON.parse(raw) as PersistedSession;
        setCandidates(persisted.candidates ?? []);
        setSupportingFiles(persisted.supportingFiles ?? []);
        setSurveyMetadata(persisted.surveyMetadata ?? emptyMetadata());
        setStatus('Restored saved deviation-survey review.');
        return;
      } catch {
        localStorage.removeItem(`${STORAGE_PREFIX}${selectedWellId}`);
      }
    }
    const existing: Candidate[] = [];
    let existingMetadata = emptyMetadata();
    for (const group of selectedWell?.product_groups ?? []) {
      for (const item of group.items ?? []) {
        if (item.product_subgroup_key !== 'deviation_survey') continue;
        const rows = item.provenance?.deviation_survey_stations ?? [];
        rows.forEach((row, index) => {
          const candidate = fromRecord(row, index, 'Existing MWD deviation survey', selectedWell?.depth_unit || 'm');
          candidate.state = 'existing';
          existing.push(candidate);
        });
        const metadata = item.provenance?.survey_metadata;
        if (metadata) {
          existingMetadata = {
            surveyName: normalize(metadata.survey_name),
            surveyType: normalize(metadata.survey_type) || 'Definitive',
            status: normalize(metadata.status) || 'reviewed',
            rig: normalize(metadata.rig),
            datum: normalize(metadata.datum) || 'RKB',
            coordinateOrigin: normalize(metadata.coordinate_origin),
            verticalSectionOrigin: normalize(metadata.vertical_section_origin) || 'Wellhead',
            verticalSectionAzimuth: normalize(metadata.vertical_section_azimuth),
            calculationMethod: normalize(metadata.calculation_method) || 'minimum_curvature',
            createdDate: normalize(metadata.created_date),
            revisedDate: normalize(metadata.revised_date),
            sourceNotes: normalize(metadata.source_notes),
          };
        }
      }
    }
    setCandidates(existing);
    setSupportingFiles([]);
    setFileObjects([]);
    setSurveyMetadata(existingMetadata);
    setStatus(`Loaded ${existing.length} existing deviation-survey station(s).`);
  }, [selectedWellId, selectedWell, loadingWells]);

  useEffect(() => {
    if (!selectedWellId) {
      sessionStorage.removeItem(ACTIVE_KEY);
      return;
    }
    const persisted: PersistedSession = {
      selectedWellId,
      candidates,
      supportingFiles,
      surveyMetadata,
      savedAt: new Date().toISOString(),
    };
    const serialized = JSON.stringify(persisted);
    sessionStorage.setItem(ACTIVE_KEY, serialized);
    localStorage.setItem(`${STORAGE_PREFIX}${selectedWellId}`, serialized);
  }, [selectedWellId, candidates, supportingFiles, surveyMetadata]);

  const updateCandidate = (id: string, updates: Partial<Candidate>) => {
    setCandidates((current) => current.map((candidate) => candidate.id === id ? { ...candidate, ...updates } : candidate));
  };

  const saveReview = () => {
    if (!selectedWellId) {
      setError('Select a managed well before saving.');
      return;
    }
    localStorage.setItem(`${STORAGE_PREFIX}${selectedWellId}`, JSON.stringify({
      selectedWellId,
      candidates,
      supportingFiles,
      surveyMetadata,
      savedAt: new Date().toISOString(),
    }));
    setStatus('Deviation-survey review saved.');
    setError(null);
  };

  const importRows = async (file: File): Promise<Candidate[]> => {
    const extension = file.name.split('.').pop()?.toLowerCase();
    let rows: Record<string, unknown>[] = [];
    if (extension === 'json') {
      const parsed = JSON.parse(await file.text()) as unknown;
      if (Array.isArray(parsed)) {
        rows = parsed.filter((row): row is Record<string, unknown> => !!row && typeof row === 'object');
      } else if (parsed && typeof parsed === 'object') {
        const object = parsed as { candidates?: unknown[]; stations?: unknown[]; survey_metadata?: Record<string, unknown> };
        const rawRows = object.candidates ?? object.stations ?? [];
        rows = rawRows.filter((row): row is Record<string, unknown> => !!row && typeof row === 'object');
        if (object.survey_metadata) {
          const metadata = object.survey_metadata;
          setSurveyMetadata((current) => ({
            ...current,
            surveyName: valueFrom(metadata, 'Survey Name', 'survey_name') || current.surveyName,
            surveyType: valueFrom(metadata, 'Survey Type', 'survey_type') || current.surveyType,
            status: valueFrom(metadata, 'Status') || current.status,
            rig: valueFrom(metadata, 'Rig') || current.rig,
            datum: valueFrom(metadata, 'Datum') || current.datum,
            coordinateOrigin: valueFrom(metadata, 'Coordinate Origin', 'coordinate_origin') || current.coordinateOrigin,
            verticalSectionOrigin: valueFrom(metadata, 'Vertical Section Origin', 'vertical_section_origin') || current.verticalSectionOrigin,
            verticalSectionAzimuth: valueFrom(metadata, 'Vertical Section Azimuth', 'vertical_section_azimuth') || current.verticalSectionAzimuth,
            calculationMethod: valueFrom(metadata, 'Calculation Method', 'calculation_method') || current.calculationMethod,
            createdDate: valueFrom(metadata, 'Created Date', 'created_date') || current.createdDate,
            revisedDate: valueFrom(metadata, 'Revised Date', 'revised_date') || current.revisedDate,
            sourceNotes: valueFrom(metadata, 'Source Notes', 'source_notes') || current.sourceNotes,
          }));
        }
      }
    } else if (['csv', 'xlsx', 'xls'].includes(extension || '')) {
      const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' });
      rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(workbook.Sheets[workbook.SheetNames[0]], { defval: '' });
    }
    return rows.map((row, index) => fromRecord(row, index, file.name, selectedWell?.depth_unit || 'm'));
  };

  const supportedSourceExtensions = new Set(['pdf', 'csv', 'xlsx', 'xls', 'json', 'txt', 'asc', 'zip']);

  const filterSupportedSourceFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    const supported = incoming.filter((file) => {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
      return supportedSourceExtensions.has(extension);
    });
    const unsupported = incoming.filter((file) => !supported.includes(file));
    if (unsupported.length) {
      setError(`Unsupported supporting file type: ${unsupported.map((file) => file.name).join(', ')}`);
    }
    return supported;
  };

  const handleSupportingDragEnter = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedWellId) return;
    supportingDragDepth.current += 1;
    setSupportingDragActive(true);
    event.dataTransfer.dropEffect = 'copy';
  };

  const handleSupportingDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedWellId) {
      event.dataTransfer.dropEffect = 'none';
      return;
    }
    event.dataTransfer.dropEffect = 'copy';
    setSupportingDragActive(true);
  };

  const handleSupportingDragLeave = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    supportingDragDepth.current = Math.max(0, supportingDragDepth.current - 1);
    if (supportingDragDepth.current === 0) setSupportingDragActive(false);
  };

  const handleSupportingDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    supportingDragDepth.current = 0;
    setSupportingDragActive(false);

    if (!selectedWellId) {
      setError('Select a managed well before dropping supporting files.');
      return;
    }

    const supported = filterSupportedSourceFiles(event.dataTransfer.files);
    if (!supported.length) return;
    void handleFiles(supported);
  };

  const supportedResponseExtensions = new Set(['json', 'csv', 'xlsx', 'xls']);

  const filterSupportedResponseFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    const supported = incoming.filter((file) => {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
      return supportedResponseExtensions.has(extension);
    });
    const unsupported = incoming.filter((file) => !supported.includes(file));

    if (unsupported.length) {
      setError(`Unsupported AI-response file type: ${unsupported.map((file) => file.name).join(', ')}. Use JSON, CSV, XLSX or XLS.`);
      return [];
    }
    if (supported.length > 1) {
      setError('Import and Review accepts one AI-response file at a time.');
      return [];
    }
    return supported;
  };

  const handleResponseDragEnter = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedWellId) return;
    responseDragDepth.current += 1;
    setResponseDragActive(true);
    event.dataTransfer.dropEffect = 'copy';
  };

  const handleResponseDragOver = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedWellId) {
      event.dataTransfer.dropEffect = 'none';
      return;
    }
    event.dataTransfer.dropEffect = 'copy';
    setResponseDragActive(true);
  };

  const handleResponseDragLeave = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    responseDragDepth.current = Math.max(0, responseDragDepth.current - 1);
    if (responseDragDepth.current == 0) setResponseDragActive(false);
  };

  const handleResponseDrop = (event: React.DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    responseDragDepth.current = 0;
    setResponseDragActive(false);

    if (!selectedWellId) {
      setError('Select a managed well before importing an AI response.');
      return;
    }

    const supported = filterSupportedResponseFiles(event.dataTransfer.files);
    const file = supported[0];
    if (!file) return;
    void importAiResponse(file);
  };

  const toggleAllSupportingFiles = () => {
    if (selectedSupportingFileIndexes.size === fileObjects.length && fileObjects.length > 0) {
      setSelectedSupportingFileIndexes(new Set());
      return;
    }
    setSelectedSupportingFileIndexes(new Set(fileObjects.map((_, index) => index)));
  };

  const toggleSupportingFile = (index: number) => {
    setSelectedSupportingFileIndexes((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const invalidatePreScanForIndexes = (indexes: number[]) => {
    if (!indexes.length) return;
    setSupportingFilePreScanResults((current) => {
      const next = { ...current };
      indexes.forEach((index) => { delete next[index]; });
      return next;
    });
    setSupportingFileAuditResults((current) => {
      const next = { ...current };
      indexes.forEach((index) => {
        const file = fileObjects[index];
        if (file) delete next[file.name];
      });
      return next;
    });
    if (
      activeSupportingFileAudit
      && indexes.some((index) => fileObjects[index]?.name === activeSupportingFileAudit.fileName)
    ) setActiveSupportingFileAudit(null);
  };

  const toggleAllDeterministicSupportingFiles = () => {
    const selectedIndexes = Array.from(selectedSupportingFileIndexes);
    const allSelectedAreScreened = selectedIndexes.length > 0
      && selectedIndexes.every((index) => deterministicSupportingFileIndexes.has(index));

    invalidatePreScanForIndexes(selectedIndexes);
    setDeterministicSupportingFileIndexes(allSelectedAreScreened ? new Set() : new Set(selectedIndexes));
  };

  const toggleDeterministicSupportingFile = (index: number) => {
    invalidatePreScanForIndexes([index]);
    setDeterministicSupportingFileIndexes((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const handleFiles = async (files: FileList | File[]) => {
    if (!selectedWellId) {
      setError('Select a managed well before adding supporting files.');
      return;
    }

    setError(null);
    const rawIncoming = Array.from(files);
    const incoming: File[] = [];
    const newlySkippedArchiveMembers: SkippedArchiveMember[] = [];

    for (const file of rawIncoming) {
      const extension = file.name.split('.').pop()?.toLowerCase() || '';
      if (extension !== 'zip') {
        incoming.push(file);
        continue;
      }

      setStatus(`Expanding supporting archive ${file.name}…`);
      try {
        const expanded = await expandZipSupportingFile(file);
        incoming.push(...expanded.files);
        newlySkippedArchiveMembers.push(...expanded.skipped.map((item) => ({
          archive: file.name,
          member: item.member,
          reason: item.reason,
        })));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : `Could not expand ${file.name}.`);
        setStatus(`ZIP expansion failed for ${file.name}. No archive members were attached.`);
        return;
      }
    }

    if (!incoming.length) {
      setError('No supported supporting files were found.');
      setStatus('No supporting files attached.');
      return;
    }

    const existingCount = fileObjects.length;
    const nextObjects = [...fileObjects, ...incoming];
    fileObjectsRef.current = nextObjects;
    setFileObjects(nextObjects);
    setSupportingFiles((current) => [
      ...current,
      ...incoming.map((file) => ({ name: file.name, type: file.type, size: file.size })),
    ]);
    setSupportingFileAuditResults({});
    setSupportingFilePreScanResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    setSelectedSupportingFileIndexes((current) => {
      const next = new Set(current);
      incoming.forEach((_, offset) => next.add(existingCount + offset));
      return next;
    });
    setDeterministicSupportingFileIndexes((current) => {
      const next = new Set(current);
      incoming.forEach((_, offset) => next.add(existingCount + offset));
      return next;
    });
    if (newlySkippedArchiveMembers.length) {
      setSkippedArchiveMembers((current) => [...current, ...newlySkippedArchiveMembers]);
    }

    const zipCount = rawIncoming.filter((file) => file.name.toLowerCase().endsWith('.zip')).length;
    const skipSuffix = newlySkippedArchiveMembers.length
      ? ` ${newlySkippedArchiveMembers.length} unsupported/nested archive member(s) were reported and skipped.`
      : '';
    setStatus(
      `Staged ${incoming.length} supporting file(s)${zipCount ? ` from ${zipCount} ZIP archive(s)` : ''}. `
      + `Select files and screening mode, then Run Pre-Scan.${skipSuffix}`,
    );
  };

  const clearSupportingFiles = () => {
    setSupportingFiles([]);
    fileObjectsRef.current = [];
    setFileObjects([]);
    setSelectedSupportingFileIndexes(new Set());
    setDeterministicSupportingFileIndexes(new Set());
    setSkippedArchiveMembers([]);
    setSupportingFileAuditResults({});
    setSupportingFilePreScanResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    supportingDragDepth.current = 0;
    setSupportingDragActive(false);
    if (fileRef.current) fileRef.current.value = '';
    setStatus('Supporting files cleared. Deviation-survey candidates and review state were preserved.');
    setError(null);
  };

  const requestGraphicsExportChoice = (files: string[]): Promise<GraphicsExportChoice> => new Promise((resolve) => {
    graphicsChoiceResolverRef.current = resolve;
    setGraphicsChoiceFiles(files);
  });

  const resolveGraphicsExportChoice = (choice: GraphicsExportChoice) => {
    const resolve = graphicsChoiceResolverRef.current;
    graphicsChoiceResolverRef.current = null;
    setGraphicsChoiceFiles(null);
    resolve?.(choice);
  };

  const requestDeterministicFailureChoice = (
    fileName: string,
    detail: string,
  ): Promise<DeterministicFailureDecision> => new Promise((resolve) => {
    deterministicFailureResolverRef.current = resolve;
    setRememberDeterministicFailureChoice(false);
    setDeterministicFailurePrompt({
      fileName,
      detail,
      canBypassScoring: /minimum direct score/i.test(detail),
    });
  });

  const resolveDeterministicFailureChoice = (choice: DeterministicFailureChoice) => {
    const resolve = deterministicFailureResolverRef.current;
    deterministicFailureResolverRef.current = null;
    setDeterministicFailurePrompt(null);
    resolve?.({ choice, remember: rememberDeterministicFailureChoice });
    setRememberDeterministicFailureChoice(false);
  };

  const runSupportingFilePreScan = async () => {
    if (!selectedWell) {
      setError('Select a managed well before running document pre-scan.');
      return;
    }
    if (!fileObjects.length) {
      setError(
        supportingFiles.length
          ? 'Reload the remembered supporting files before running pre-scan.'
          : 'Add one or more supporting files before running pre-scan.',
      );
      return;
    }

    const selectedIndexes = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b);
    if (!selectedIndexes.length) {
      setError('Select at least one supporting file for pre-scan.');
      return;
    }

    setError(null);
    setPreScanRunning(true);
    setActiveSupportingFileAudit(null);
    let rememberedFailureChoice: DeterministicFailureChoice | null = null;

    try {
      const managedAiRules = await fetchToolboxAiRules('DSM');
      const combinedRules = { ...managedAiRules.rules } as Record<string, unknown>;
      const deterministicProfile = (
        combinedRules.deterministic_screening
        && typeof combinedRules.deterministic_screening === 'object'
        && !Array.isArray(combinedRules.deterministic_screening)
      ) ? combinedRules.deterministic_screening as Record<string, unknown> : {};
      const deterministicProfileSignature = JSON.stringify(deterministicProfile);

      const nextResults = { ...supportingFilePreScanResults };
      const nextAudit = { ...supportingFileAuditResults };

      for (const sourceIndex of selectedIndexes) {
        const file = fileObjects[sourceIndex];
        if (!file) continue;

        const payload = await filePayload(file);
        const deterministicRequested = deterministicSupportingFileIndexes.has(sourceIndex);
        const cached = nextResults[sourceIndex];
        if (
          cached
          && cached.sourceName === file.name
          && cached.sourceSha256 === payload.sha256
          && cached.deterministicRequested === deterministicRequested
          && cached.standardVersion === managedAiRules.active_version
          && cached.deterministicProfileSignature === deterministicProfileSignature
        ) continue;

        setStatus(`Pre-scanning ${file.name}…`);

        if (!deterministicRequested) {
          const preparedEvidence: PreparedEvidenceFile = {
            name: file.name,
            mime_type: file.type || 'application/octet-stream',
            size: file.size,
            content_base64: payload.content_base64,
            preprocessed_from_pdf: false,
            deterministic_screening: false,
            selected_pdf_pages_preserved: file.type === 'application/pdf',
          };
          nextResults[sourceIndex] = {
            sourceIndex,
            sourceName: file.name,
            sourceSha256: payload.sha256,
            deterministicRequested: false,
            standardVersion: managedAiRules.active_version,
            deterministicProfileSignature,
            preparedEvidence,
            evidencePreparation: {
              name: file.name,
              mode: 'full_original',
              original_size: file.size,
              prepared_size: file.size,
            },
            estimatedEvidenceTokens: 0,
          };
          nextAudit[file.name] = {
            fileName: file.name,
            requestedMode: 'full_original',
            completionStatus: 'full_original',
            payloadBytes: file.size,
            selectedPageCount: 0,
            totalPages: null,
            reason: 'Full original selected by operator before pre-scan.',
          };
          continue;
        }

        const makePrepareRequest = async (profile: Record<string, unknown>) => fetch(
          `${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/prepare`,
          {
            method: 'POST',
            headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify({
              candidate_package: {
                deterministic_screening_enabled: true,
                deterministic_screening_profile: profile,
              },
              evidence_files: [{
                name: file.name,
                mime_type: file.type || 'application/octet-stream',
                size: file.size,
                content_base64: payload.content_base64,
              }],
            }),
          },
        );

        let prepareResponse = await makePrepareRequest(deterministicProfile);
        if (!prepareResponse.ok) {
          let failureDetail = `Deterministic pre-screen returned ${prepareResponse.status}`;
          try {
            const failureBody = await prepareResponse.json() as { detail?: unknown };
            if (failureBody?.detail) failureDetail = String(failureBody.detail);
          } catch {
            const failureText = await prepareResponse.text().catch(() => '');
            if (failureText) failureDetail = failureText;
          }

          const rememberedChoiceUsable = rememberedFailureChoice !== 'bypass_scoring'
            || /minimum direct score/i.test(failureDetail);
          const decision: DeterministicFailureDecision = rememberedFailureChoice && rememberedChoiceUsable
            ? { choice: rememberedFailureChoice, remember: true }
            : await requestDeterministicFailureChoice(file.name, failureDetail);
          if (decision.remember) rememberedFailureChoice = decision.choice;

          if (decision.choice === 'cancel') {
            delete nextResults[sourceIndex];
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'pending',
              payloadBytes: 0,
              selectedPageCount: 0,
              totalPages: null,
              reason: `${failureDetail} Full-original fallback was not authorized.`,
            };
            continue;
          }

          if (decision.choice === 'full_original') {
            const preparedEvidence: PreparedEvidenceFile = {
              name: file.name,
              mime_type: file.type || 'application/octet-stream',
              size: file.size,
              content_base64: payload.content_base64,
              preprocessed_from_pdf: false,
              deterministic_screening: false,
              selected_pdf_pages_preserved: file.type === 'application/pdf',
            };
            nextResults[sourceIndex] = {
              sourceIndex,
              sourceName: file.name,
              sourceSha256: payload.sha256,
              deterministicRequested: true,
              standardVersion: managedAiRules.active_version,
              deterministicProfileSignature,
              preparedEvidence,
              evidencePreparation: {
                name: file.name,
                mode: 'full_original_fallback_after_deterministic_failure',
                original_size: file.size,
                prepared_size: file.size,
              },
              estimatedEvidenceTokens: 0,
            };
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'full_scan_fallback',
              payloadBytes: file.size,
              selectedPageCount: 0,
              totalPages: null,
              reason: failureDetail,
            };
            continue;
          }

          prepareResponse = await makePrepareRequest({
            ...deterministicProfile,
            bypass_min_direct_score: true,
          });
          if (!prepareResponse.ok) {
            const bypassText = await prepareResponse.text().catch(() => '');
            delete nextResults[sourceIndex];
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'pending',
              payloadBytes: 0,
              selectedPageCount: 0,
              totalPages: null,
              reason: `${failureDetail} Bypass scoring retry failed: ${bypassText || prepareResponse.status}.`,
            };
            continue;
          }
        }

        const prepared = await prepareResponse.json() as EvidencePreparationResponse;
        if (!Array.isArray(prepared.prepared_evidence) || prepared.prepared_evidence.length !== 1) {
          throw new Error(`Deterministic pre-screen did not return one prepared payload for ${file.name}.`);
        }

        let preparedEvidence = prepared.prepared_evidence[0];
        let evidencePreparation = Array.isArray(prepared.evidence_preparation)
          ? (prepared.evidence_preparation.find((item) => item.name === file.name) ?? prepared.evidence_preparation[0] ?? null)
          : null;

        if (String(evidencePreparation?.graphics_audit?.risk_level || '') === 'high') {
          const choice = await requestGraphicsExportChoice([file.name]);
          if (choice === 'cancel') {
            delete nextResults[sourceIndex];
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'pending',
              payloadBytes: 0,
              selectedPageCount: 0,
              totalPages: Number(evidencePreparation?.total_pages || 0) || null,
              reason: 'High graphics risk was detected and no payload choice was authorized.',
            };
            continue;
          }
          if (choice === 'full_original') {
            preparedEvidence = {
              name: file.name,
              mime_type: file.type || 'application/octet-stream',
              size: file.size,
              content_base64: payload.content_base64,
              preprocessed_from_pdf: false,
              deterministic_screening: false,
              selected_pdf_pages_preserved: file.type === 'application/pdf',
            };
            evidencePreparation = {
              ...(evidencePreparation ?? {
                name: file.name,
                mode: 'full_original_graphics_override',
                original_size: file.size,
              }),
              mode: 'full_original_graphics_override',
              prepared_size: file.size,
            };
          }
        }

        const payloadBytes = Math.max(
          0,
          Math.floor((String(preparedEvidence.content_base64 || '').length * 3) / 4),
        );
        const selectedPageCount = Number(
          evidencePreparation?.selected_page_count || preparedEvidence.source_pages?.length || 0,
        );
        const totalPagesValue = Number(evidencePreparation?.total_pages);
        const totalPages = Number.isFinite(totalPagesValue) && totalPagesValue > 0 ? totalPagesValue : null;
        const completionStatus: SupportingFileAuditResult['completionStatus'] =
          evidencePreparation?.mode === 'full_original_graphics_override'
            ? 'full_scan_graphics'
            : 'screened';

        nextResults[sourceIndex] = {
          sourceIndex,
          sourceName: file.name,
          sourceSha256: payload.sha256,
          deterministicRequested: true,
          standardVersion: managedAiRules.active_version,
          deterministicProfileSignature,
          preparedEvidence,
          evidencePreparation,
          estimatedEvidenceTokens: Number(prepared.estimated_evidence_tokens || 0),
        };
        nextAudit[file.name] = {
          fileName: file.name,
          requestedMode: 'deterministic',
          completionStatus,
          payloadBytes,
          selectedPageCount,
          totalPages,
          reason: evidencePreparation?.mode === 'full_original_graphics_override'
            ? 'Operator selected full original after high graphics-risk warning.'
            : 'Deterministic pre-scan completed.',
        };
      }

      setSupportingFilePreScanResults(nextResults);
      setSupportingFileAuditResults(nextAudit);

      const unresolved = selectedIndexes.filter((index) => !nextResults[index]).length;
      setStatus(
        unresolved
          ? `Document pre-scan completed with ${unresolved} unresolved selected file(s).`
          : `Document pre-scan completed for ${selectedIndexes.length} selected file(s). Review the manifest, then export.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Document pre-scan failed.');
    } finally {
      setPreScanRunning(false);
    }
  };

  const exportAiPackage = async () => {
    if (!selectedWell) {
      setError('Select a managed well first.');
      return;
    }
    const selectedIndexes = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b);
    if (!selectedIndexes.length) {
      setError('Select at least one supporting source file.');
      return;
    }
    try {
      setError(null);
      const managedAiRules = await fetchToolboxAiRules('DSM');
      const combinedRules = { ...managedAiRules.rules } as Record<string, unknown>;
      const deterministicProfile = (
        combinedRules.deterministic_screening
        && typeof combinedRules.deterministic_screening === 'object'
        && !Array.isArray(combinedRules.deterministic_screening)
      ) ? combinedRules.deterministic_screening as Record<string, unknown> : {};
      delete combinedRules.deterministic_screening;
      const deterministicProfileSignature = JSON.stringify(deterministicProfile);

      const selectedResults = selectedIndexes.map((index) => {
        const file = fileObjects[index];
        const result = supportingFilePreScanResults[index];
        if (!file || !result) throw new Error('All selected files must be resolved by Run Pre-Scan before export.');
        if (
          result.sourceName !== file.name
          || result.deterministicRequested !== deterministicSupportingFileIndexes.has(index)
          || result.standardVersion !== managedAiRules.active_version
          || result.deterministicProfileSignature !== deterministicProfileSignature
        ) throw new Error(`${file.name}: pre-scan result is stale. Run Pre-Scan again.`);
        return result;
      });

      const sourceFiles = selectedResults.map((result) => ({
        name: result.sourceName,
        type: result.preparedEvidence.mime_type || 'application/octet-stream',
        size: fileObjects[result.sourceIndex]?.size ?? result.preparedEvidence.size,
        sha256: result.sourceSha256,
      }));
      const preparedEvidence = selectedResults.map((result) => result.preparedEvidence);
      const evidencePreparation = selectedResults
        .map((result) => result.evidencePreparation)
        .filter((item): item is EvidencePreparationSummary => Boolean(item));
      const estimatedEvidenceTokens = selectedResults.reduce(
        (sum, result) => sum + Number(result.estimatedEvidenceTokens || 0),
        0,
      );
      const deterministicPreScreen = selectedResults.some((result) => result.deterministicRequested);
      const packageRevision = await aiRevision.allocateExport();
      const payload = {
        package_type: 'deviation_survey_manager_ai_package',
        managed_ai_rules: combinedRules,
        deterministic_screening: {
          enabled: deterministicPreScreen,
          execution: deterministicPreScreen ? 'application_side_completed_before_export' : 'disabled',
          profile: deterministicProfile,
          standard_version: managedAiRules.active_version,
          authority: 'AI Standards Manager',
          evidence_preparation: evidencePreparation,
          estimated_evidence_tokens: estimatedEvidenceTokens,
          budget_scope: 'per_document',
          max_selected_pages_per_document: Number(deterministicProfile.max_selected_pages ?? 50),
          provider_payload_policy: deterministicPreScreen
            ? 'Only application-selected original PDF pages are embedded. Graphics and layout on retained pages are preserved for LLM review; disable screening when full-document visual review is required.'
            : 'Full original supporting files are embedded because deterministic screening is disabled.',
        },
        managed_ai_rules_version: managedAiRules.active_version,
        managed_ai_rules_updated_at: managedAiRules.updated_at,
        managed_ai_rules_are_authoritative_overrides: true,
        revision: toolboxAiPackageRevision('DSM', packageRevision),
        schema_version: '1.1.0',
        created_at: new Date().toISOString(),
        managed_well: {
          managed_well_id: selectedWell.managed_well_id,
          well_id: selectedWell.well_id,
          well_name: selectedWell.well_name ?? selectedWell.display_name,
          wellbore_name: selectedWell.wellbore_name,
          uwi: selectedWell.uwi,
          depth_unit: selectedWell.depth_unit,
          top_depth: selectedWell.top_depth,
          base_depth: selectedWell.base_depth,
        },
        extraction_contract: {
          contract_revision: 'deviation-survey-discovery-and-qaqc-1.1.0',
          role: 'Act as a cold-start directional-survey discovery and extraction model. Use only evidence contained in this package.',
          governing_principles: [
            'Keep source extraction, normalization, calculation, inference and manual editing distinct.',
            'Never silently replace source values with calculated, inferred or normalized values.',
            'Apply these rules generally to every well, wellbore, sidetrack, source format and report layout.',
            'Named wells and page ranges are regression fixtures only, not discovery assumptions.',
          ],
          discovery_rules: {
            inspect: [
              'Complete source text and every retained rendered page image.',
              'Appendices, rotated pages, landscape pages, foldouts and image-only pages when retained by the deterministic selection.',
              'Repeated headers, continuation pages, comments and related marker pages.',
            ],
            applicability: [
              'Resolve exact well, wellbore and sidetrack.',
              'Return applicability as confirmed_selected_well, probable_selected_well, ambiguous_well or different_well.',
              'Only confirmed_selected_well is automatically primary-candidate eligible.',
              'Never merge parent and sidetrack data without explicit evidence.',
            ],
            assembly: [
              'Assemble cross-page evidence only from matching well/run identity, units, coordinate conventions, continuous MD, repeated headers or explicit continuation evidence.',
              'Do not combine pages merely because they occur near each other.',
              'Separate planned, provisional, definitive, actual, different-run and different-wellbore surveys.',
            ],
            scan_and_table: [
              'Detect orientation and deskew.',
              'Detect table, columns and row baselines.',
              'Read cells independently and reconstruct rows from fixed geometry.',
              'Retain page and cell evidence.',
              'Flag uncertain decimal points, direction letters and ambiguous characters.',
            ],
            preservation: [
              'Preserve original text, direction notation, units and source values.',
              'Normalize north positive, south negative, east positive and west negative only in separate normalized fields.',
              'Keep missing source cells null.',
              'Keep calculated completions separate from source values.',
            ],
          },
          station_types: ['measured', 'calculated', 'extrapolated', 'casing', 'planned', 'manual', 'unknown'],
          required_candidate_fields: [
            'md', 'inclination', 'azimuth', 'tvd', 'northSouth', 'eastWest',
            'doglegSeverity', 'verticalSection', 'depthUnit', 'coordinateUnit',
            'doglegUnit', 'stationType', 'sourceFile', 'sourcePage',
            'sourceTablePage', 'evidenceReference', 'confidence', 'notes',
          ],
          deterministic_qaqc_contract: {
            states: ['pass', 'warning', 'failure', 'not_tested', 'not_applicable'],
            severities: ['information', 'warning', 'failure'],
            categories: [
              'Source and applicability', 'Table extraction', 'Required fields',
              'Depth sequence', 'Inclination and azimuth', 'Units and references',
              'Trajectory calculation', 'Coordinates and vertical section',
              'Survey completeness', 'Duplicate and conflicting surveys',
              'Extrapolated and calculated stations', 'Publication blockers',
            ],
            hard_failures: [
              'Missing numeric MD, inclination or azimuth.',
              'Accepted MD not strictly increasing.',
              'Duplicate accepted MD.',
              'Inclination outside 0–180 degrees.',
              'Azimuth outside 0–<360 degrees.',
              'Mixed unresolved depth units.',
              'Mixed unresolved dogleg units.',
              'Wrong or ambiguous selected-well assignment.',
              'Planned and actual surveys merged.',
            ],
            warnings: [
              'Large unexplained station gap.',
              'Abrupt inclination or azimuth change.',
              'Source TVD greater than MD.',
              'Source versus minimum-curvature discrepancy.',
              'Coordinate sign or origin concern.',
              'Missing datum, origin or azimuth reference.',
              'OCR ambiguity or page-boundary discontinuity.',
              'Survey ending materially before or beyond known TD.',
            ],
            governing_rule: 'QAQC identifies discrepancies and proposals; it never silently resolves them.',
          },
          required_response_shape_note: 'Return only defensible source-derived candidates. Return zero candidates when no applicable survey exists.',
        },
        regression_fixtures: [
          {
            fixture_id: '15-9-19A-definitive-directional-survey',
            purpose: 'Validate multi-page scanned-table discovery, metadata assembly, explicit extrapolated-to-TD handling and related casing markers.',
            note: 'Fixture details are test guidance only and must never become general discovery assumptions.',
          },
        ],
        current_survey_metadata: surveyMetadata,
        existing_candidates: candidates,
        source_files: sourceFiles,
        source_payload_policy: deterministicPreScreen
          ? 'resolved_per_document_pre_scan_payloads_embedded'
          : 'original_binary_embedded_in_supporting_files',
        supporting_files: preparedEvidence.map((file, index) => ({
          name: file.name,
          type: file.mime_type || 'application/octet-stream',
          size: file.size,
          content_base64: file.content_base64,
          preprocessed_from_pdf: Boolean(file.preprocessed_from_pdf),
          source_pages: file.source_pages ?? [],
          deterministic_screening: Boolean(file.deterministic_screening),
          selected_pdf_pages_preserved: Boolean(file.selected_pdf_pages_preserved),
          source_sha256: sourceFiles[index]?.sha256 ?? '',
          original_source_size: sourceFiles[index]?.size ?? 0,
        })),
        required_response_shape: {
          package_type: 'deviation_survey_manager_ai_response',
          revision: toolboxAiExpectedResponseRevision(packageRevision),
          schema_version: '1.0.0',
          survey_metadata: surveyMetadata,
          screening: {
            deterministic_enabled: deterministicPreScreen,
            standard_version: managedAiRules.active_version,
            selected_pages_by_document: evidencePreparation.map((item) => ({
              source: item.name,
              selected_pages: item.selected_pages ?? [],
              selected_page_count: Number(item.selected_page_count || 0),
            })),
          },
          candidates: [{
            md: '', inclination: '', azimuth: '', tvd: '', northSouth: '', eastWest: '',
            doglegSeverity: '', verticalSection: '', depthUnit: selectedWell.depth_unit || 'm',
            coordinateUnit: selectedWell.depth_unit || 'm', doglegUnit: 'deg/30m',
            stationType: 'measured', sourceFile: '', sourcePage: '', sourceTablePage: '',
            evidenceReference: '', confidence: '', notes: '',
          }],
        },
      };
      const fileName = toolboxAiPackageFilename(
        'DSM_AI_PACKAGE',
        selectedWell.well_name || selectedWell.display_name || selectedWell.well_id,
        packageRevision,
      );
      const compressedPackageFilename = await downloadCompressedJsonPackage(
        fileName,
        JSON.stringify(payload, null, 2),
      );

      const totalSelectedPages = evidencePreparation.reduce(
        (sum, item) => sum + Number(item.selected_page_count || 0),
        0,
      );
      setStatus(
        `${compressedPackageFilename} exported from ${selectedResults.length} resolved selected document(s)`
        + `${totalSelectedPages ? ` · ${totalSelectedPages} selected PDF page(s)` : ''}.`,
      );
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to export DSM AI package.');
    }
  };

  const importAiResponse = async (file: File) => {
    try {
      if (file.name.toLowerCase().endsWith('.json')) { try { void aiRevision.syncImportedArtifact(file.name, JSON.parse(await file.text())); } catch {} } else void aiRevision.syncImportedArtifact(file.name);
      const imported = await importRows(file);
      if (!imported.length) throw new Error('No deviation-survey candidates were found.');
      setCandidates(imported);
      setStatus(`Imported ${imported.length} deviation-survey candidate(s) from AI response.`);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to import AI response.');
    }
  };

  const setSelectedState = (state: ReviewState) => {
    if (!selectedIds.size) return;
    setCandidates((current) => current.map((candidate) =>
      selectedIds.has(candidate.id) ? { ...candidate, state, selected: false } : candidate));
  };

  const deleteSelected = () => {
    if (!selectedIds.size) return;
    setCandidates((current) => current.filter((candidate) => !selectedIds.has(candidate.id)));
  };

  const addRow = () => {
    const previous = candidates[candidates.length - 1];
    setCandidates((current) => [...current, emptyCandidate(selectedWell?.depth_unit || 'm', previous?.md || '')]);
  };

  const sortByMd = () => {
    setCandidates((current) => [...current].sort((a, b) => {
      const left = Number(a.md);
      const right = Number(b.md);
      if (!Number.isFinite(left)) return 1;
      if (!Number.isFinite(right)) return -1;
      return left - right;
    }));
  };

  const exportCsv = () => {
    if (!candidates.length) return;
    const rows = candidates.map((candidate) => ({
      Review: candidate.state,
      Selected: candidate.selected ? 'Yes' : 'No',
      MD: candidate.md,
      Inclination: candidate.inclination,
      Azimuth: candidate.azimuth,
      TVD: candidate.tvd,
      'North/South': candidate.northSouth,
      'East/West': candidate.eastWest,
      'Dogleg Severity': candidate.doglegSeverity,
      'Vertical Section': candidate.verticalSection,
      'Depth Unit': candidate.depthUnit,
      'Coordinate Unit': candidate.coordinateUnit,
      'Dogleg Unit': candidate.doglegUnit,
      'Station Type': candidate.stationType,
      'Source File': candidate.sourceFile,
      'PDF Page': candidate.sourcePage,
      'Table Page': candidate.sourceTablePage,
      Evidence: candidate.evidenceReference,
      Confidence: candidate.confidence,
      Notes: candidate.notes,
    }));
    const sheet = XLSX.utils.json_to_sheet(rows);
    const csv = XLSX.utils.sheet_to_csv(sheet);
    downloadText('DSM_deviation_survey_review.csv', csv, 'text/csv');
  };

  const exportJson = () => {
    downloadText('DSM_deviation_survey_review.json', JSON.stringify({
      package_type: 'deviation_survey_manager_review',
      schema_version: '1.0.0',
      managed_well_id: selectedWellId,
      survey_metadata: surveyMetadata,
      candidates,
    }, null, 2));
  };

  const publish = async () => {
    if (!selectedWell) {
      setError('Select a managed well first.');
      return;
    }
    const approved = candidates.filter((candidate) => candidate.state === 'confirmed' || candidate.state === 'edited');
    if (approved.length < 2) {
      setError('At least two approved survey stations are required.');
      return;
    }
    for (const [index, candidate] of approved.entries()) {
      const md = Number(candidate.md);
      const inclination = Number(candidate.inclination);
      const azimuth = Number(candidate.azimuth);
      if (!Number.isFinite(md) || !Number.isFinite(inclination) || !Number.isFinite(azimuth)) {
        setError(`Row ${index + 1} requires numeric MD, inclination and azimuth.`);
        return;
      }
      if (inclination < 0 || inclination > 180) {
        setError(`Row ${index + 1} inclination must be between 0 and 180°.`);
        return;
      }
      if (azimuth < 0 || azimuth >= 360) {
        setError(`Row ${index + 1} azimuth must be between 0 and <360°.`);
        return;
      }
    }
    const ordered = [...approved].sort((a, b) => Number(a.md) - Number(b.md));
    for (let index = 1; index < ordered.length; index += 1) {
      if (Number(ordered[index].md) <= Number(ordered[index - 1].md)) {
        setError(`Approved survey MD must be strictly increasing at row ${index + 1}.`);
        return;
      }
    }
    const payload = {
      dataset_type: 'deviation_survey',
      dataset_status: 'reviewed',
      source: 'Deviation Survey Manager',
      managed_well_id: selectedWell.managed_well_id,
      survey_metadata: {
        survey_name: surveyMetadata.surveyName || `${selectedWell.display_name || selectedWell.well_name || selectedWell.well_id} deviation survey`,
        survey_type: surveyMetadata.surveyType,
        status: surveyMetadata.status,
        rig: surveyMetadata.rig || null,
        datum: surveyMetadata.datum || null,
        coordinate_origin: surveyMetadata.coordinateOrigin || null,
        vertical_section_origin: surveyMetadata.verticalSectionOrigin || null,
        vertical_section_azimuth: numberOrNull(surveyMetadata.verticalSectionAzimuth),
        calculation_method: surveyMetadata.calculationMethod || 'minimum_curvature',
        created_date: surveyMetadata.createdDate || null,
        revised_date: surveyMetadata.revisedDate || null,
        source_notes: surveyMetadata.sourceNotes || null,
      },
      stations: ordered.map((candidate) => ({
        measured_depth: Number(candidate.md),
        inclination: Number(candidate.inclination),
        azimuth: Number(candidate.azimuth),
        true_vertical_depth: numberOrNull(candidate.tvd),
        north_south: numberOrNull(candidate.northSouth),
        east_west: numberOrNull(candidate.eastWest),
        dogleg_severity: numberOrNull(candidate.doglegSeverity),
        vertical_section: numberOrNull(candidate.verticalSection),
        depth_unit: candidate.depthUnit || selectedWell.depth_unit || 'm',
        coordinate_unit: candidate.coordinateUnit || candidate.depthUnit || selectedWell.depth_unit || 'm',
        dogleg_unit: candidate.doglegUnit || 'deg/30m',
        station_type: candidate.stationType,
        source_document: candidate.sourceFile || null,
        source_page: candidate.sourcePage || null,
        source_table_page: candidate.sourceTablePage || null,
        source_reference: candidate.evidenceReference || null,
        confidence: candidate.confidence || null,
        notes: candidate.notes || null,
      })),
    };
    try {
      const response = await fetch(
        `${wlvApiBaseUrl()}/api/wlv/inventory/wells/${encodeURIComponent(selectedWell.managed_well_id)}/deviation-survey`,
        {
          method: 'POST',
          headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      );
      if (!response.ok) throw new Error(await response.text() || `Publication returned ${response.status}`);
      await response.json();
      saveReview();

      const refreshDetail = {
        source: 'Deviation Survey Manager',
        managedWellId: selectedWell.managed_well_id,
        productType: 'deviation_survey',
        publishedAt: new Date().toISOString(),
      };
      window.dispatchEvent(new CustomEvent('wlv:mwd-inventory-changed', { detail: refreshDetail }));
      try {
        const channel = new BroadcastChannel('wlv:mwd-inventory');
        channel.postMessage(refreshDetail);
        channel.close();
      } catch {
        // BroadcastChannel may be unavailable in restricted browser contexts.
      }
      try {
        window.localStorage.setItem('wlv:mwd-inventory-refresh', JSON.stringify(refreshDetail));
      } catch {
        // Cross-tab refresh remains optional when browser storage is unavailable.
      }

      const wellName = selectedWell.display_name || selectedWell.well_name || selectedWell.well_id;
      setStatus(`Deviation survey saved to ${wellName} in the MWD.`);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Direct MWD publication failed.');
    }
  };

  const clear = () => {
    if (!selectedWellId && !wellSearch && !candidates.length && !supportingFiles.length && !fileObjects.length) return;
    if (selectedWellId) localStorage.removeItem(`${STORAGE_PREFIX}${selectedWellId}`);
    sessionStorage.removeItem(ACTIVE_KEY);
    setSelectedWellId('');
    setWellSearch('');
    setCandidates([]);
    setSupportingFiles([]);
    setFileObjects([]);
    fileObjectsRef.current = [];
    setSelectedSupportingFileIndexes(new Set());
    setDeterministicSupportingFileIndexes(new Set());
    setSkippedArchiveMembers([]);
    setSupportingFilePreScanResults({});
    setSupportingFileAuditResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    setPreScanRunning(false);
    setDeterministicFailurePrompt(null);
    deterministicFailureResolverRef.current = null;
    setGraphicsChoiceFiles(null);
    graphicsChoiceResolverRef.current = null;
    setSurveyMetadata(emptyMetadata());
    setActiveEditId(null);
    supportingDragDepth.current = 0;
    setSupportingDragActive(false);
    if (fileRef.current) fileRef.current.value = '';
    if (responseRef.current) responseRef.current.value = '';
    setStatus('Deviation Survey Manager cleared. Published deviation survey data was not removed.');
    setError(null);
  };

  return (
    <section
      className="wlv-metadata-tool wlv-ftm-tool wlv-lcm-tool wlv-dsm-tool"
      onDragOver={(event) => {
        if (Array.from(event.dataTransfer.types).includes('Files')) event.preventDefault();
      }}
      onDrop={(event) => {
        if (Array.from(event.dataTransfer.types).includes('Files')) event.preventDefault();
      }}
    >
      {activeSupportingFileAudit ? <div
        role="dialog"
        aria-modal="true"
        aria-label="Supporting file audit"
        style={{ position: 'fixed', inset: 0, zIndex: 12000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center' }}
      >
        <div style={{ width: 'min(640px, calc(100vw - 40px))', background: '#151b21', border: '1px solid #465466', borderRadius: '6px', padding: '16px', color: '#dbe3eb' }}>
          <strong style={{ display: 'block', marginBottom: '8px' }}>{activeSupportingFileAudit.fileName}</strong>
          <div style={{ fontSize: '11px', lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>
            Requested mode: {activeSupportingFileAudit.requestedMode}{'\n'}
            Completion status: {activeSupportingFileAudit.completionStatus}{'\n'}
            Payload: {activeSupportingFileAudit.payloadBytes.toLocaleString()} bytes{'\n'}
            Pages: {activeSupportingFileAudit.selectedPageCount}{activeSupportingFileAudit.totalPages ? ` / ${activeSupportingFileAudit.totalPages}` : ''}{'\n'}
            Reason: {activeSupportingFileAudit.reason}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '14px' }}>
            <button type="button" onClick={() => setActiveSupportingFileAudit(null)}>Close</button>
          </div>
        </div>
      </div> : null}

      {deterministicFailurePrompt ? <div
        role="dialog"
        aria-modal="true"
        aria-label="Deterministic screening unavailable for this document"
        style={{ position: 'fixed', inset: 0, zIndex: 12000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center' }}
      >
        <div style={{ width: 'min(700px, calc(100vw - 40px))', background: '#151b21', border: '1px solid #465466', borderRadius: '6px', padding: '16px', color: '#dbe3eb' }}>
          <strong style={{ display: 'block', marginBottom: '6px' }}>Deterministic screening unavailable for this document</strong>
          <div style={{ fontSize: '11px', color: '#aeb9c5', marginBottom: '8px' }}>{deterministicFailurePrompt.fileName}</div>
          <div style={{ fontSize: '11px', lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>{deterministicFailurePrompt.detail}</div>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', marginTop: '12px', fontSize: '10px' }}>
            <input
              type="checkbox"
              checked={rememberDeterministicFailureChoice}
              onChange={(event) => setRememberDeterministicFailureChoice(event.target.checked)}
            />
            Remember this answer for the rest of this pre-scan
          </label>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '14px' }}>
            <button type="button" onClick={() => resolveDeterministicFailureChoice('cancel')}>Leave unresolved</button>
            <button type="button" onClick={() => resolveDeterministicFailureChoice('full_original')}>Use full original</button>
            {deterministicFailurePrompt.canBypassScoring ? (
              <button type="button" onClick={() => resolveDeterministicFailureChoice('bypass_scoring')}>Bypass scoring</button>
            ) : null}
          </div>
        </div>
      </div> : null}

      {graphicsChoiceFiles ? <div
        role="dialog"
        aria-modal="true"
        aria-label="High graphical-content risk"
        style={{ position: 'fixed', inset: 0, zIndex: 12000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center' }}
      >
        <div style={{ width: 'min(700px, calc(100vw - 40px))', background: '#151b21', border: '1px solid #465466', borderRadius: '6px', padding: '16px', color: '#dbe3eb' }}>
          <strong style={{ display: 'block', marginBottom: '8px' }}>High graphical-content risk</strong>
          <div style={{ fontSize: '11px', lineHeight: 1.45 }}>
            {graphicsChoiceFiles.join(', ')} may contain visually important evidence outside the deterministic text-selected pages.
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '14px' }}>
            <button type="button" onClick={() => resolveGraphicsExportChoice('cancel')}>Leave unresolved</button>
            <button type="button" onClick={() => resolveGraphicsExportChoice('full_original')}>Use full original document</button>
            <button type="button" onClick={() => resolveGraphicsExportChoice('selected_pages')}>Use deterministic selected pages</button>
          </div>
        </div>
      </div> : null}
      <style>{`
        .wlv-dsm-tool {
          height: 100%;
          max-height: 100vh;
          overflow-y: auto;
          overflow-x: hidden;
          padding-top: 18px;
          font-size: 12px;
        }

        .wlv-dsm-tool > .wlv-metadata-tool__status {
          width: calc(100% - 32px);
          max-width: 1120px;
          min-height: 18px;
          margin: 0 auto 8px;
          padding: 0;
          box-sizing: border-box;
          border: 0;
          background: transparent;
          color: #8f9ba8;
          font-size: 9px;
          font-weight: 500;
          line-height: 1.35;
          text-align: left;
        }

        .wlv-dsm-tool .wlv-ftm-workflow,
        .wlv-dsm-tool .wlv-metadata-tool__action-row,
        .wlv-dsm-tool > .wlv-ftm-panel,
        .wlv-dsm-tool .wlv-ftm-review {
          width: calc(100% - 32px);
          max-width: 1120px;
          margin-left: auto;
          margin-right: auto;
          box-sizing: border-box;
        }

        .wlv-dsm-tool .wlv-ftm-workflow {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 14px;
          margin-bottom: 14px;
        }

        .wlv-dsm-tool .wlv-dsm-intake-card {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          min-width: 0;
          min-height: 108px;
          padding: 18px 22px;
          border: 1px dashed #4b5867;
          border-radius: 5px;
          background: #171d24;
        }

        .wlv-dsm-tool .wlv-dsm-card-copy {
          min-width: 0;
          max-width: 100%;
          flex: 1 1 auto;
          overflow: hidden;
        }

        .wlv-dsm-tool .wlv-dsm-card-copy h2 {
          margin: 0 0 3px;
          color: #dce4ec;
          font-size: 12px;
          font-weight: 700;
          line-height: 1.2;
        }

        .wlv-dsm-tool .wlv-dsm-card-copy p {
          margin: 0;
          color: #8895a3;
          font-size: 10px;
          line-height: 1.3;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .wlv-dsm-tool .wlv-dsm-managed-card {
          display: grid;
          grid-template-columns: 105px minmax(0, 1fr);
          align-items: center;
          gap: 10px;
          padding-left: 14px;
          padding-right: 14px;
          overflow: hidden;
        }

        .wlv-dsm-tool .wlv-dsm-managed-controls {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 120px;
          gap: 8px;
          min-width: 0;
          width: 100%;
        }

        .wlv-dsm-tool .wlv-dsm-managed-controls input,
        .wlv-dsm-tool .wlv-dsm-managed-controls select {
          width: 100%;
          min-width: 0;
          height: 31px;
          box-sizing: border-box;
          border: 1px solid #465466;
          border-radius: 4px;
          background: #10161c;
          color: #dce5ee;
          padding: 5px 8px;
          font-size: 10px;
        }

        .wlv-dsm-tool .wlv-dsm-intake-card > button {
          flex: 0 0 auto;
          min-height: 31px;
          padding: 5px 11px;
          border: 1px solid #465466;
          border-radius: 4px;
          background: #181f27;
          color: #dce4ec;
          font-size: 10px;
          font-weight: 650;
        }

        .wlv-dsm-tool .wlv-metadata-tool__action-row {
          min-height: 60px;
          margin-bottom: 14px;
          padding: 12px 16px;
          gap: 10px;
          border: 1px solid #2d3640;
          border-radius: 5px;
          background: #181e25;
        }

        .wlv-dsm-tool .wlv-metadata-tool__action-row button {
          min-height: 31px;
          padding: 5px 11px;
          border-radius: 4px;
          font-size: 10px;
          font-weight: 650;
        }

        .wlv-dsm-tool > .wlv-ftm-panel {
          margin-bottom: 14px;
          padding: 14px 16px 16px;
          border: 1px solid #2d3640;
          border-radius: 5px;
          background: #181e25;
        }

        .wlv-dsm-tool > .wlv-ftm-panel > header {
          display: block;
          margin: 0 0 10px;
          padding-bottom: 9px;
          border-bottom: 1px solid #2d3640;
        }

        .wlv-dsm-tool > .wlv-ftm-panel > header > span {
          display: none;
        }

        .wlv-dsm-tool > .wlv-ftm-panel > header h2 {
          margin: 0 0 3px;
          color: #dce4ec;
          font-size: 12px;
          font-weight: 700;
        }

        .wlv-dsm-tool > .wlv-ftm-panel > header p {
          margin: 0;
          color: #8895a3;
          font-size: 10px;
        }

        .wlv-dsm-tool .wlv-ftm-grid {
          display: grid;
          grid-template-columns: repeat(5, minmax(0, 1fr));
          gap: 8px 10px;
        }

        .wlv-dsm-tool .wlv-ftm-grid label {
          display: grid;
          gap: 4px;
          min-width: 0;
          color: #8f9aa7;
          font-size: 9px;
          font-weight: 650;
        }

        .wlv-dsm-tool .wlv-ftm-grid input {
          width: 100%;
          min-width: 0;
          height: 31px;
          box-sizing: border-box;
          border: 1px solid #465466;
          border-radius: 4px;
          background: #10161c;
          color: #dce5ee;
          padding: 5px 8px;
          font-size: 10px;
        }

        .wlv-dsm-tool .wlv-ftm-review {
          margin-bottom: 16px;
          border: 1px solid #2d3640;
          border-radius: 5px;
          background: #171c22;
          overflow: hidden;
        }

        .wlv-dsm-tool .wlv-ftm-review__toolbar {
          display: flex;
          align-items: center;
          min-height: 54px;
          padding: 12px 16px;
          gap: 6px;
          border-bottom: 1px solid #2d3640;
          background: #171c22;
        }

        .wlv-dsm-tool .wlv-ftm-review__toolbar button {
          min-height: 31px;
          padding: 5px 11px;
          border-radius: 4px;
          font-size: 10px;
          font-weight: 650;
        }

        .wlv-dsm-tool .wlv-ftm-review__toolbar span {
          margin-left: auto;
          color: #84909d;
          font-size: 10px;
        }

        .wlv-dsm-tool .wlv-ftm-table-wrap {
          overflow-x: auto;
          overflow-y: visible;
        }

        .wlv-dsm-tool .wlv-ftm-table {
          width: 100%;
          min-width: 1480px;
          border-collapse: collapse;
          table-layout: fixed;
          font-size: 10px;
        }

        .wlv-dsm-tool .wlv-ftm-table th,
        .wlv-dsm-tool .wlv-ftm-table td {
          padding: 12px 8px;
          border-bottom: 1px solid #252d36;
          text-align: left;
          vertical-align: middle;
        }

        .wlv-dsm-tool .wlv-ftm-table th {
          position: sticky;
          top: 0;
          z-index: 1;
          background: #13181e;
          color: #8e9aa8;
          font-size: 8px;
          letter-spacing: .06em;
          text-transform: uppercase;
        }

        .wlv-dsm-tool .wlv-ftm-table td {
          color: #dce5ee;
          font-size: 10px;
        }

        .wlv-dsm-tool .wlv-ftm-table th:nth-child(1) { width: 28px; }
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(2) { width: 80px; }
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(3),
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(4),
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(5),
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(6),
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(7),
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(8),
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(9),
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(10) { width: 72px; }
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(11) { width: 95px; }
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(12) { width: 190px; }
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(13) { width: 180px; }
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(14) { width: 65px; }
        .wlv-dsm-tool .wlv-ftm-table th:nth-child(15) { width: 170px; }

        .wlv-dsm-tool .wlv-dsm-supporting-drop,
        .wlv-dsm-tool .wlv-dsm-response-drop {
          transition: border-color 120ms ease, background-color 120ms ease, box-shadow 120ms ease;
        }

        .wlv-dsm-tool .wlv-dsm-supporting-drop.is-drag-active,
        .wlv-dsm-tool .wlv-dsm-response-drop.is-drag-active {
          border-color: #65a8d8;
          background: #192735;
          box-shadow: inset 0 0 0 1px rgba(101, 168, 216, .24);
        }

        .wlv-dsm-tool .wlv-dsm-supporting-drop.is-drag-active .wlv-dsm-card-copy h2,
        .wlv-dsm-tool .wlv-dsm-supporting-drop.is-drag-active .wlv-dsm-card-copy p,
        .wlv-dsm-tool .wlv-dsm-response-drop.is-drag-active .wlv-dsm-card-copy h2,
        .wlv-dsm-tool .wlv-dsm-response-drop.is-drag-active .wlv-dsm-card-copy p {
          color: #dceeff;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-panel {
          width: calc(100% - 32px);
          max-width: 1120px;
          margin: 0 auto 12px;
          box-sizing: border-box;
          border: 1px solid #2c3540;
          border-radius: 5px;
          background: #171c22;
          color: #aab6c2;
          font-size: 9px;
          overflow: hidden;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-summary {
          display: flex;
          align-items: center;
          gap: 12px;
          min-height: 44px;
          padding: 8px 14px;
          border-bottom: 1px solid #2c3540;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-summary strong {
          color: #dce5ee;
          font-size: 11px;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-summary .is-ready { color: #83d9a5; }
        .wlv-dsm-tool .wlv-dsm-qaqc-summary .is-ready_with_warnings { color: #f0c36b; }
        .wlv-dsm-tool .wlv-dsm-qaqc-summary .is-blocked { color: #ff9ca7; }

        .wlv-dsm-tool .wlv-dsm-qaqc-panel details {
          padding: 8px 14px 12px;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-panel summary {
          cursor: pointer;
          color: #c7d1db;
          font-weight: 650;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-findings {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
          padding-top: 10px;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-findings section {
          border: 1px solid #2c3540;
          border-radius: 4px;
          padding: 8px;
          background: #141a20;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-findings h3 {
          margin: 0 0 6px;
          color: #dce5ee;
          font-size: 9px;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-finding {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 2px 8px;
          width: 100%;
          margin: 4px 0;
          padding: 5px 6px;
          border: 0;
          border-radius: 3px;
          background: transparent;
          color: #aab6c2;
          text-align: left;
          line-height: 1.35;
          cursor: pointer;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-finding > span:last-child {
          grid-column: 1 / -1;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-finding:disabled {
          cursor: default;
          opacity: 1;
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-finding:not(:disabled):hover {
          background: rgba(126, 157, 184, .10);
        }

        .wlv-dsm-tool .wlv-dsm-qaqc-finding.is-failure { color: #ff9ca7; }
        .wlv-dsm-tool .wlv-dsm-qaqc-finding.is-warning { color: #f0c36b; }

        .wlv-dsm-tool .wlv-ftm-table tr.qaqc-failure > td {
          background: rgba(154, 45, 57, .18);
        }

        .wlv-dsm-tool .wlv-ftm-table tr.qaqc-warning > td {
          background: rgba(157, 112, 31, .14);
        }

        .wlv-dsm-tool .wlv-ftm-table tr.qaqc-information > td {
          background: rgba(73, 96, 118, .10);
        }

        .wlv-dsm-tool .wlv-ftm-table td.qaqc-cell-failure {
          background: rgba(202, 56, 72, .34) !important;
          box-shadow: inset 0 0 0 1px rgba(255, 130, 143, .52);
        }

        .wlv-dsm-tool .wlv-ftm-table td.qaqc-cell-warning {
          background: rgba(210, 151, 41, .30) !important;
          box-shadow: inset 0 0 0 1px rgba(244, 193, 94, .46);
        }

        .wlv-dsm-tool .wlv-ftm-table td.qaqc-cell-information {
          box-shadow: inset 0 0 0 1px rgba(126, 157, 184, .28);
        }

        .wlv-dsm-tool .wlv-ftm-table tr.is-qaqc-focused > td {
          animation: dsm-qaqc-focus 800ms ease-in-out 2;
        }

        @keyframes dsm-qaqc-focus {
          0%, 100% { box-shadow: inset 0 0 0 1px transparent; }
          50% { box-shadow: inset 0 0 0 2px #8fc8f0; }
        }

        .wlv-dsm-tool .wlv-ftm-table .qaqc-indicator.is-failure {
          color: #ff9ca7;
          font-weight: 700;
        }

        .wlv-dsm-tool .wlv-ftm-table .qaqc-indicator.is-warning {
          color: #f0c36b;
          font-weight: 700;
        }

        @media (max-width: 1100px) {
          .wlv-dsm-tool .wlv-ftm-workflow {
            grid-template-columns: 1fr;
          }

          .wlv-dsm-tool .wlv-dsm-managed-card {
            grid-template-columns: 1fr;
          }

          .wlv-dsm-tool .wlv-ftm-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
      `}</style>
      <header className="wlv-metadata-tool__header">
        <button type="button" className="wlv-metadata-tool__back" onClick={onBack}>‹ Toolbox</button>
        <div className="wlv-metadata-tool__title">
          <h1>Deviation Survey Manager</h1>
          <p>Extract, review, validate and publish deviation-survey stations for a managed well.</p>
        </div>
        <div className="wlv-metadata-tool__window-actions">
          <button type="button" onClick={clear} disabled={!selectedWellId && !wellSearch && candidates.length === 0 && supportingFiles.length === 0 && fileObjects.length === 0} title="Clear the entire Deviation Survey Manager workspace">Clear</button>
          <button type="button" className="wlv-metadata-tool__close" aria-label="Close Deviation Survey Manager" onClick={onBack}>×</button>
        </div>
      </header>

      {error ? <div className="wlv-metadata-tool__error">{error}</div> : null}
      <div className="wlv-metadata-tool__status">{status}</div>

      <div className="wlv-ftm-workflow">
        <section className="wlv-ftm-panel wlv-dsm-intake-card wlv-dsm-managed-card">
          <div className="wlv-dsm-card-copy">
            <h2>Managed Well</h2>
            <p>{selectedWell ? (selectedWell.display_name || selectedWell.well_name || selectedWell.well_id) : 'Select a well from the MWD'}</p>
          </div>
          <div className="wlv-dsm-managed-controls">
            <input
              value={wellSearch}
              onChange={(event) => setWellSearch(event.target.value)}
              placeholder="Search MWD"
              aria-label="Search managed wells"
            />
            <select
              value={selectedWellId}
              onChange={(event) => setSelectedWellId(event.target.value)}
              disabled={loadingWells}
              aria-label="Select managed well"
            >
              <option value="">Select a well…</option>
              {filteredWells.map((well) => (
                <option key={well.managed_well_id} value={well.managed_well_id}>
                  {well.display_name || well.well_name || well.well_id}
                </option>
              ))}
            </select>
          </div>
        </section>

        <section
          className={`wlv-ftm-panel wlv-dsm-intake-card wlv-dsm-supporting-drop${supportingDragActive ? ' is-drag-active' : ''}`}
          onDragEnter={handleSupportingDragEnter}
          onDragOver={handleSupportingDragOver}
          onDragLeave={handleSupportingDragLeave}
          onDrop={handleSupportingDrop}
          aria-label="Supporting Files drop zone"
        >
          <div className="wlv-dsm-card-copy">
            <h2>Supporting Files</h2>
            <p>
              {!selectedWellId
                ? 'Select a managed well first'
                : supportingDragActive
                  ? 'Drop files to add them'
                  : supportingFiles.length
                    ? `${supportingFiles.length} file(s) ready`
                    : 'Drop files here or browse'}
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.csv,.xlsx,.xls,.json,.txt,.asc,.zip"
            hidden
            onChange={(event) => {
              if (!event.target.files) return;
              const supported = filterSupportedSourceFiles(event.target.files);
              if (supported.length) void handleFiles(supported);
              event.currentTarget.value = '';
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button type="button" onClick={() => fileRef.current?.click()} disabled={!selectedWellId}>Browse</button>
            <button type="button" onClick={clearSupportingFiles} disabled={!selectedWellId || supportingFiles.length === 0}>Clear</button>
          </div>
        </section>

        <section
          className={`wlv-ftm-panel wlv-dsm-intake-card wlv-dsm-response-drop${responseDragActive ? ' is-drag-active' : ''}`}
          onDragEnter={handleResponseDragEnter}
          onDragOver={handleResponseDragOver}
          onDragLeave={handleResponseDragLeave}
          onDrop={handleResponseDrop}
          aria-label="Import and Review drop zone"
        >
          <div className="wlv-dsm-card-copy">
            <h2>Import and Review</h2>
            <p>
              {!selectedWellId
                ? 'Select a managed well first'
                : responseDragActive
                  ? 'Drop AI response to import'
                  : 'Drop AI response JSON, CSV or Excel here'}
            </p>
          </div>
          <input
            ref={responseRef}
            type="file"
            accept=".json,.csv,.xlsx,.xls"
            hidden
            onChange={(event) => {
              if (!event.target.files) return;
              const supported = filterSupportedResponseFiles(event.target.files);
              const file = supported[0];
              if (file) void importAiResponse(file);
              event.currentTarget.value = '';
            }}
          />
          <button type="button" onClick={() => responseRef.current?.click()} disabled={!selectedWellId}>Browse</button>
        </section>
      </div>

      {(fileObjects.length > 0 || skippedArchiveMembers.length > 0) && (
        <section style={{ width: 'calc(100% - 24px)', maxWidth: '1136px', margin: '0 auto 12px', border: '1px solid #34414f', borderRadius: '5px', overflow: 'hidden', background: '#151b21' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '9px 12px', borderBottom: supportingManifestCollapsed ? undefined : '1px solid #34414f' }}>
            <div style={{ minWidth: 0 }}>
              <strong style={{ display: 'block', fontSize: '11px', color: '#e2e8ef' }}>Supporting file manifest</strong>
              <span style={{ fontSize: '10px', color: '#93a1b0' }}>
                {supportingManifestCollapsed
                  ? `${selectedSupportingFileIndexes.size} selected file${selectedSupportingFileIndexes.size === 1 ? '' : 's'}`
                  : 'Phase 1: select files and screening mode, then Run Pre-Scan. Review Completion Status, Payload and Audit. Phase 2: refine selection and Export AI package.'}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setSupportingManifestCollapsed((current) => !current)}
              aria-expanded={!supportingManifestCollapsed}
              aria-controls="dsm-supporting-file-manifest-body"
              title={supportingManifestCollapsed ? 'Expand supporting file manifest' : 'Collapse supporting file manifest'}
              style={{ flex: '0 0 auto', minWidth: '34px', padding: '4px 8px' }}
            >
              {supportingManifestCollapsed ? '▸' : '▾'}
            </button>
          </div>

          <div id="dsm-supporting-file-manifest-body" hidden={supportingManifestCollapsed}>
            {fileObjects.length > 0 && (
              <div style={{ maxHeight: '280px', overflow: 'auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) 82px 128px 132px 92px 42px', alignItems: 'center', minHeight: '32px', color: '#93a1b0', background: '#11171d', borderBottom: '1px solid #293440', fontSize: '10px', fontWeight: 600 }}>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '7px 14px' }}>
                    <input
                      type="checkbox"
                      checked={fileObjects.length > 0 && selectedSupportingFileIndexes.size === fileObjects.length}
                      onChange={toggleAllSupportingFiles}
                    />
                    SELECT FILES
                  </label>
                  <div style={{ padding: '7px 10px' }}>FILE / ZIP MEMBER</div>
                  <div style={{ padding: '7px 10px' }}>SIZE</div>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '7px 10px' }}>
                    <input
                      type="checkbox"
                      checked={selectedSupportingFileIndexes.size > 0 && Array.from(selectedSupportingFileIndexes).every((index) => deterministicSupportingFileIndexes.has(index))}
                      disabled={selectedSupportingFileIndexes.size === 0}
                      onChange={toggleAllDeterministicSupportingFiles}
                    />
                    DETERMINISTIC
                  </label>
                  <div style={{ padding: '7px 8px' }}>COMPLETION STATUS</div>
                  <div style={{ padding: '7px 8px' }}>PAYLOAD</div>
                  <div style={{ padding: '7px 4px', textAlign: 'center' }}>AUDIT</div>
                </div>

                {fileObjects.map((file, index) => {
                  const checked = selectedSupportingFileIndexes.has(index);
                  const deterministic = deterministicSupportingFileIndexes.has(index);
                  const audit = supportingFileAuditResults[file.name];
                  const statusLabel = !audit
                    ? 'Pending'
                    : audit.completionStatus === 'screened'
                      ? 'Screened'
                      : audit.completionStatus === 'full_original'
                        ? 'Full original'
                        : audit.completionStatus === 'full_scan_fallback'
                          ? 'Full scan fallback'
                          : audit.completionStatus === 'full_scan_graphics'
                            ? 'Full scan · graphics'
                            : audit.completionStatus === 'excluded'
                              ? 'Excluded'
                              : 'Pending';
                  const payloadLabel = audit?.payloadBytes
                    ? audit.payloadBytes >= 1024 * 1024
                      ? `${(audit.payloadBytes / 1024 / 1024).toFixed(2)} MB`
                      : `${(audit.payloadBytes / 1024).toFixed(1)} KB`
                    : '—';
                  return (
                    <div key={`${file.name}-${index}`} style={{ display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) 82px 128px 132px 92px 42px', alignItems: 'center', minHeight: '34px', borderTop: index ? '1px solid #293440' : undefined, color: '#d6dde5', fontSize: '10px' }}>
                      <div style={{ padding: '7px 14px' }}>
                        <input type="checkbox" checked={checked} onChange={() => toggleSupportingFile(index)} aria-label={`Include ${file.name}`} />
                      </div>
                      <div style={{ padding: '7px 10px', minWidth: 0, overflowWrap: 'anywhere' }}>{file.name}</div>
                      <div style={{ padding: '7px 10px', whiteSpace: 'nowrap', color: '#aeb9c5' }}>
                        {file.size >= 1024 * 1024 ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : `${(file.size / 1024).toFixed(1)} KB`}
                      </div>
                      <div style={{ padding: '7px 10px' }}>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', color: checked ? '#cdd6df' : '#6f7b87' }}>
                          <input type="checkbox" checked={deterministic} disabled={!checked} onChange={() => toggleDeterministicSupportingFile(index)} />
                          {deterministic ? 'Screen' : 'Full'}
                        </label>
                      </div>
                      <div style={{ padding: '7px 8px', whiteSpace: 'nowrap', color: audit ? '#c8d2dc' : '#768493' }}>{statusLabel}</div>
                      <div style={{ padding: '7px 8px', whiteSpace: 'nowrap', color: '#aeb9c5' }}>{payloadLabel}</div>
                      <div style={{ padding: '5px 4px', textAlign: 'center' }}>
                        <button type="button" disabled={!audit} onClick={() => audit && setActiveSupportingFileAudit(audit)} title={audit ? `View audit for ${file.name}` : 'Audit available after pre-scan'}>ⓘ</button>
                      </div>
                    </div>
                  );
                })}

                <div aria-label="Export totals" style={{ display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) 82px 128px 132px 92px 42px', alignItems: 'center', minHeight: '40px', borderTop: '1px solid #4a5968', background: '#11171d', color: '#dbe4ee', fontSize: '10px', fontWeight: 700 }}>
                  <div style={{ padding: '8px 14px', whiteSpace: 'nowrap' }}>EXPORT TOTALS</div>
                  <div style={{ padding: '8px 10px', color: '#aeb9c5', fontWeight: 600 }}>{selectedSupportingFileIndexes.size} selected file{selectedSupportingFileIndexes.size === 1 ? '' : 's'}</div>
                  <div style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                    {(Array.from(selectedSupportingFileIndexes).reduce((sum, index) => sum + Number(fileObjects[index]?.size || 0), 0) / 1024 / 1024).toFixed(2)} MB
                  </div>
                  <div style={{ padding: '8px 10px', color: '#7f8d9b', fontWeight: 600 }}>
                    {Array.from(selectedSupportingFileIndexes).filter((index) => !supportingFilePreScanResults[index]).length
                      ? `${Array.from(selectedSupportingFileIndexes).filter((index) => !supportingFilePreScanResults[index]).length} pending`
                      : 'Ready'}
                  </div>
                  <div style={{ padding: '8px 8px', color: '#aeb9c5', fontWeight: 600 }}>
                    {Array.from(selectedSupportingFileIndexes).every((index) => Boolean(supportingFilePreScanResults[index])) ? 'Ready for export' : 'Selection total'}
                  </div>
                  <div style={{ padding: '8px 8px', whiteSpace: 'nowrap' }}>
                    {(Array.from(selectedSupportingFileIndexes).reduce((sum, index) => sum + Number(supportingFileAuditResults[fileObjects[index]?.name]?.payloadBytes || 0), 0) / 1024 / 1024).toFixed(2)} MB
                  </div>
                  <div />
                </div>
              </div>
            )}

            {skippedArchiveMembers.length > 0 && (
              <details style={{ borderTop: fileObjects.length ? '1px solid #34414f' : undefined }}>
                <summary style={{ cursor: 'pointer', padding: '8px 12px', color: '#c0cad5', fontSize: '10px', fontWeight: 600 }}>
                  Skipped archive members ({skippedArchiveMembers.length})
                </summary>
                <div style={{ maxHeight: '180px', overflow: 'auto', borderTop: '1px solid #293440' }}>
                  {skippedArchiveMembers.map((item, index) => (
                    <div key={`${item.archive}-${item.member}-${index}`} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', padding: '6px 12px', borderTop: index ? '1px solid #242f39' : undefined, fontSize: '9px' }}>
                      <span style={{ color: '#abb7c3', wordBreak: 'break-word' }}>{item.archive}::{item.member}</span>
                      <span style={{ color: '#8e9ba8' }}>{item.reason}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        </section>
      )}

      <div className="wlv-metadata-tool__action-row">
        <button
          type="button"
          onClick={() => void runSupportingFilePreScan()}
          disabled={preScanRunning || !selectedWellId || (supportingFiles.length > 0 && fileObjects.length === 0) || selectedSupportingFileIndexes.size === 0}
        >
          {preScanRunning ? 'Pre-Scanning…' : 'Run Pre-Scan'}
        </button>
        <button
          type="button"
          onClick={() => void exportAiPackage()}
          disabled={
            preScanRunning
            || !selectedWellId
            || selectedSupportingFileIndexes.size === 0
            || !Array.from(selectedSupportingFileIndexes).every((index) => {
              const result = supportingFilePreScanResults[index];
              return Boolean(result) && result.deterministicRequested === deterministicSupportingFileIndexes.has(index);
            })
          }
          title="All currently selected files must have resolved current pre-scan results before AI export."
        >
          Export AI package
        </button>
        <span className="wlv-toolbox-ai-revision" style={{ color: '#9ca9b7', fontSize: '10px', fontWeight: 600, whiteSpace: 'nowrap' }}>{selectedWellId ? `AI Review Cycle: ${aiRevision.currentLabel} · Next export: ${aiRevision.nextLabel}` : 'AI Review Cycle: —'}</span>
        <button type="button" onClick={publish} disabled={!selectedWellId || summary.approved < 2 || qaqc.publicationState === 'blocked'}>Publish approved survey</button>
        <button type="button" onClick={saveReview} disabled={!selectedWellId}>Save review</button>
        <button type="button" onClick={exportCsv} disabled={!candidates.length}>Export CSV</button>
        <button type="button" onClick={exportJson} disabled={!candidates.length}>Export JSON</button>
        <button type="button" onClick={addRow} disabled={!selectedWellId}>Add row</button>
        <button type="button" onClick={sortByMd} disabled={!candidates.length}>Sort by MD</button>
        <span className="wlv-metadata-tool__session-summary">
          {selectedWell ? (selectedWell.display_name || selectedWell.well_name || selectedWell.well_id) : 'No well selected'}
          {candidates.length ? ` · ${candidates.length} station(s)` : ''}
          {summary.approved ? ` · ${summary.approved} approved` : ''}
        </span>
      </div>

      <section className="wlv-ftm-panel">
        <header><span>4</span><div><h2>Survey Metadata</h2><p>Preserve report-level survey context and calculation provenance.</p></div></header>
        <div className="wlv-ftm-grid">
          <label>Survey name<input value={surveyMetadata.surveyName} onChange={(event) => setSurveyMetadata((current) => ({ ...current, surveyName: event.target.value }))} /></label>
          <label>Survey type<input value={surveyMetadata.surveyType} onChange={(event) => setSurveyMetadata((current) => ({ ...current, surveyType: event.target.value }))} /></label>
          <label>Rig<input value={surveyMetadata.rig} onChange={(event) => setSurveyMetadata((current) => ({ ...current, rig: event.target.value }))} /></label>
          <label>Datum<input value={surveyMetadata.datum} onChange={(event) => setSurveyMetadata((current) => ({ ...current, datum: event.target.value }))} /></label>
          <label>Coordinate origin<input value={surveyMetadata.coordinateOrigin} onChange={(event) => setSurveyMetadata((current) => ({ ...current, coordinateOrigin: event.target.value }))} /></label>
          <label>Vertical-section origin<input value={surveyMetadata.verticalSectionOrigin} onChange={(event) => setSurveyMetadata((current) => ({ ...current, verticalSectionOrigin: event.target.value }))} /></label>
          <label>Vertical-section azimuth<input value={surveyMetadata.verticalSectionAzimuth} onChange={(event) => setSurveyMetadata((current) => ({ ...current, verticalSectionAzimuth: event.target.value }))} /></label>
          <label>Calculation method<input value={surveyMetadata.calculationMethod} onChange={(event) => setSurveyMetadata((current) => ({ ...current, calculationMethod: event.target.value }))} /></label>
          <label>Created date<input value={surveyMetadata.createdDate} onChange={(event) => setSurveyMetadata((current) => ({ ...current, createdDate: event.target.value }))} /></label>
          <label>Revised date<input value={surveyMetadata.revisedDate} onChange={(event) => setSurveyMetadata((current) => ({ ...current, revisedDate: event.target.value }))} /></label>
        </div>
      </section>



      <section className="wlv-dsm-qaqc-panel">
        <div className="wlv-dsm-qaqc-summary">
          <strong>Survey QAQC</strong>
          <span className={`is-${qaqc.publicationState}`}>
            {qaqc.publicationState === 'ready' ? 'Ready' : qaqc.publicationState === 'ready_with_warnings' ? 'Ready with warnings' : 'Blocked'}
          </span>
          <span>{qaqc.failures} failures</span>
          <span>{qaqc.warnings} warnings</span>
          <span>{qaqc.information} information</span>
        </div>
        {qaqc.findings.length ? (
          <details>
            <summary>Review QAQC findings</summary>
            <div className="wlv-dsm-qaqc-findings">
              {Object.entries(
                qaqc.findings.reduce<Record<string, QaqcFinding[]>>((groups, finding) => {
                  (groups[finding.category] ||= []).push(finding);
                  return groups;
                }, {}),
              ).map(([category, findings]) => (
                <section key={category}>
                  <h3>{category}</h3>
                  {findings.map((finding, index) => (
                    <button
                      key={`${finding.ruleId}-${finding.stationId || 'survey'}-${index}`}
                      type="button"
                      className={`wlv-dsm-qaqc-finding is-${finding.severity}`}
                      onClick={() => focusQaqcFinding(finding)}
                      disabled={!finding.stationId}
                      title={finding.stationId ? 'Go to affected survey station' : 'Survey-level finding'}
                    >
                      <strong>{finding.ruleId}</strong>
                      {finding.stationId ? (
                        <span>
                          MD {candidateById.get(finding.stationId)?.md || '—'}
                          {finding.field ? ` · ${fieldLabel(finding.field)}` : ''}
                          {finding.observedValue !== undefined ? ` = ${String(finding.observedValue)}` : ''}
                        </span>
                      ) : <span>Survey-level</span>}
                      <span>{finding.message}</span>
                    </button>
                  ))}
                </section>
              ))}
            </div>
          </details>
        ) : <p>No QAQC findings.</p>}
      </section>

      <section className="wlv-ftm-review">
        <div className="wlv-ftm-review__toolbar">
          <button type="button" onClick={() => setCandidates((current) => current.map((candidate) => ({ ...candidate, selected: true })))} disabled={!candidates.length}>Select all</button>
          <button type="button" onClick={() => setCandidates((current) => current.map((candidate) => ({ ...candidate, selected: false })))} disabled={!selectedIds.size}>Select none</button>
          <button type="button" onClick={() => setSelectedState('confirmed')} disabled={!selectedIds.size}>Accept</button>
          <button type="button" onClick={() => setSelectedState('rejected')} disabled={!selectedIds.size}>Reject</button>
          <button type="button" onClick={deleteSelected} disabled={!selectedIds.size}>Delete</button>
          <span>{summary.pending} pending · {summary.approved} approved · {summary.rejected} rejected</span>
        </div>

        <div className="wlv-ftm-table-wrap">
          <table className="wlv-ftm-table">
            <thead>
              <tr>
                <th aria-label="Select row"></th>
                <th>Status</th>
                <th>MD</th>
                <th>Inc</th>
                <th>Azi</th>
                <th>TVD</th>
                <th>N/S</th>
                <th>E/W</th>
                <th>DLS</th>
                <th>VS</th>
                <th>Type</th>
                <th>Source</th>
                <th>Evidence</th>
                <th>QAQC</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => {
                const editing = activeEditId === candidate.id;
                const rowQaqc = qaqc.rowFindings.get(candidate.id) ?? [];
                const rowSeverity = rowQaqc.some((finding) => finding.severity === 'failure')
                  ? 'failure'
                  : rowQaqc.some((finding) => finding.severity === 'warning')
                    ? 'warning'
                    : rowQaqc.some((finding) => finding.severity === 'information')
                      ? 'information'
                      : 'pass';
                const aliases: Partial<Record<keyof Candidate, string[]>> = {
                  md: ['md', 'measured_depth'],
                  inclination: ['inclination'],
                  azimuth: ['azimuth'],
                  tvd: ['tvd', 'true_vertical_depth'],
                  northSouth: ['northSouth', 'north_south'],
                  eastWest: ['eastWest', 'east_west'],
                  doglegSeverity: ['doglegSeverity', 'dogleg_severity'],
                  verticalSection: ['verticalSection', 'vertical_section'],
                  stationType: ['stationType', 'station_type'],
                  sourceFile: ['sourceFile', 'source_file'],
                  evidenceReference: ['evidenceReference', 'sourcePage', 'source_page'],
                };
                const cellSeverity = (property: keyof Candidate) => {
                  const names = aliases[property] ?? [String(property)];
                  const matches = rowQaqc.filter((finding) => finding.field && names.includes(finding.field));
                  if (matches.some((finding) => finding.severity === 'failure')) return 'failure';
                  if (matches.some((finding) => finding.severity === 'warning')) return 'warning';
                  if (matches.some((finding) => finding.severity === 'information')) return 'information';
                  return 'pass';
                };
                const field = (property: keyof Candidate, width = 72) => editing ? (
                  <input
                    style={{ width }}
                    value={String(candidate[property] ?? '')}
                    onChange={(event) => updateCandidate(candidate.id, { [property]: event.target.value, state: 'edited' } as Partial<Candidate>)}
                  />
                ) : String(candidate[property] ?? '') || '—';
                return (
                  <tr
                    id={`dsm-station-${candidate.id}`}
                    key={candidate.id}
                    className={`is-${candidate.state} qaqc-${rowSeverity}${focusedQaqcRowId === candidate.id ? ' is-qaqc-focused' : ''}`}
                  >
                    <td><input type="checkbox" checked={candidate.selected} onChange={(event) => updateCandidate(candidate.id, { selected: event.target.checked })} /></td>
                    <td>{candidate.state}</td>
                    <td className={`qaqc-cell-${cellSeverity('md')}`}>{field('md')}</td>
                    <td className={`qaqc-cell-${cellSeverity('inclination')}`}>{field('inclination')}</td>
                    <td className={`qaqc-cell-${cellSeverity('azimuth')}`}>{field('azimuth')}</td>
                    <td className={`qaqc-cell-${cellSeverity('tvd')}`}>{field('tvd')}</td>
                    <td className={`qaqc-cell-${cellSeverity('northSouth')}`}>{field('northSouth')}</td>
                    <td className={`qaqc-cell-${cellSeverity('eastWest')}`}>{field('eastWest')}</td>
                    <td className={`qaqc-cell-${cellSeverity('doglegSeverity')}`}>{field('doglegSeverity')}</td>
                    <td className={`qaqc-cell-${cellSeverity('verticalSection')}`}>{field('verticalSection')}</td>
                    <td className={`qaqc-cell-${cellSeverity('stationType')}`}>{editing ? (
                      <select value={candidate.stationType} onChange={(event) => updateCandidate(candidate.id, { stationType: event.target.value as StationType, state: 'edited' })}>
                        <option value="measured">Measured</option>
                        <option value="calculated">Calculated</option>
                        <option value="extrapolated">Extrapolated</option>
                        <option value="casing">Casing</option>
                        <option value="manual">Manual</option>
                      </select>
                    ) : candidate.stationType}</td>
                    <td className={`qaqc-cell-${cellSeverity('sourceFile')}`}>{editing ? <input value={candidate.sourceFile} onChange={(event) => updateCandidate(candidate.id, { sourceFile: event.target.value, state: 'edited' })} /> : candidate.sourceFile || '—'}</td>
                    <td className={`qaqc-cell-${cellSeverity('evidenceReference')}`}>{editing ? <input value={candidate.evidenceReference} onChange={(event) => updateCandidate(candidate.id, { evidenceReference: event.target.value, state: 'edited' })} /> : candidate.evidenceReference || [candidate.sourcePage && `PDF ${candidate.sourcePage}`, candidate.sourceTablePage && `Table ${candidate.sourceTablePage}`].filter(Boolean).join(' · ') || '—'}</td>
                    <td
                      className={`qaqc-indicator is-${rowSeverity}`}
                      title={rowQaqc.map((finding) => `${finding.ruleId}${finding.field ? ` ${fieldLabel(finding.field)}` : ''}${finding.observedValue !== undefined ? `=${String(finding.observedValue)}` : ''}: ${finding.message}`).join(' ')}
                    >
                      {rowQaqc.some((finding) => finding.severity === 'failure')
                        ? `Fail ${rowQaqc.filter((finding) => finding.severity === 'failure').length}`
                        : rowQaqc.some((finding) => finding.severity === 'warning')
                          ? `Warn ${rowQaqc.filter((finding) => finding.severity === 'warning').length}`
                          : rowQaqc.length
                            ? `Info ${rowQaqc.length}`
                            : 'Pass'}
                    </td>
                    <td>
                      <button type="button" onClick={() => setActiveEditId(editing ? null : candidate.id)}>{editing ? 'Done' : 'Edit'}</button>
                      <button type="button" onClick={() => updateCandidate(candidate.id, { state: 'confirmed' })}>Accept</button>
                      <button type="button" onClick={() => updateCandidate(candidate.id, { state: 'rejected' })}>Reject</button>
                    </td>
                  </tr>
                );
              })}
              {!candidates.length ? (
                <tr><td colSpan={15}>{selectedWellId ? 'Load supporting files or import an AI response.' : 'Select a managed well.'}</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

export default DeviationSurveyManagerPage;
