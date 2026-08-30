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
  managed_well_uid?: string | null;
  well_id: string;
  uwi?: string | null;
  well_name?: string | null;
  display_name?: string | null;
  wellbore_id?: string | null;
  wellbore_name?: string | null;
  depth_unit?: string | null;
  top_depth?: number | null;
  base_depth?: number | null;
  status?: string | null;
  product_groups?: Array<{
    items?: Array<{
      product_subgroup_key?: string | null;
      provenance?: {
        formation_tops?: Array<{
          group?: string | null;
          marker_name?: string | null;
          marker_type?: string | null;
          md_m_rt?: number | null;
          tvd_m_rt?: number | null;
          tvdss_m_msl?: number | null;
          pick_status?: string | null;
          uncertainty_m?: number | null;
          source_document?: string | null;
          source_page?: string | number | null;
        }>;
      } | null;
    }>;
  }>;
};

type ReviewState = 'unreviewed' | 'confirmed' | 'edited' | 'rejected' | 'conflict' | 'existing';

type FormationTopEvidenceRecord = {
  source: string;
  evidence: string;
  confidence?: string;
  authority?: string;
};

type FormationTopCandidate = {
  id: string;
  state: ReviewState;
  marker: string;
  group: string;
  markerType: string;
  pickStatus: string;
  md: string;
  tvd: string;
  tvdss: string;
  unit: string;
  depthReference: string;
  uncertainty: string;
  source: string;
  evidence: string;
  evidenceRecords: FormationTopEvidenceRecord[];
  confidence: string;
  notes: string;
  original: Omit<FormationTopCandidate, 'original'> | null;
};

type PersistedFtmSession = {
  selectedWellId: string;
  candidates: FormationTopCandidate[];
  supportingFiles: SupportingFile[];
  savedAt: string;
};

const FTM_STORAGE_PREFIX = 'wlv.ftm.review.v1.';
const FTM_ACTIVE_SESSION_KEY = 'wlv.ftm.activeSession.v1';

function normalize(value: unknown): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function hasUsableMeasuredDepth(candidate: Pick<FormationTopCandidate, 'md'>): boolean {
  const md = normalize(candidate.md);
  if (!md) return false;
  return Number.isFinite(Number(md));
}

function normalizedConfidenceForCandidate(candidate: Pick<FormationTopCandidate, 'md' | 'confidence'>): string {
  return hasUsableMeasuredDepth(candidate) ? normalize(candidate.confidence).toLowerCase() : 'invalid';
}

function formatMarkerName(value: unknown): string {
  const text = normalize(value);
  if (!text) return '';
  return text
    .replace(/\bFm\.?\s*Base\b/gi, '(Base)')
    .replace(/\bFormation\s+Base\b/gi, '(Base)')
    .replace(/\bFm\.?\s*Top\b/gi, '')
    .replace(/\bFormation\s+Top\b/gi, '')
    .replace(/\s+\(/g, ' (')
    .replace(/\(\s+/g, '(')
    .replace(/\s+\)/g, ')')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function idForCandidate(seed: string): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${seed}`;
}

function cloneWithoutOriginal(candidate: FormationTopCandidate): Omit<FormationTopCandidate, 'original'> {
  const { original: _original, ...rest } = candidate;
  return { ...rest };
}

function emptyCandidate(unit = 'm'): FormationTopCandidate {
  const candidate: FormationTopCandidate = {
    id: idForCandidate('manual'),
    state: 'unreviewed',
    marker: '',
    group: '',
    markerType: 'Formation top',
    pickStatus: 'Interpreted',
    md: '',
    tvd: '',
    tvdss: '',
    unit,
    depthReference: 'RT',
    uncertainty: '',
    source: 'Manual entry',
    evidence: '',
    evidenceRecords: [],
    confidence: 'invalid',
    notes: '',
    original: null,
  };
  candidate.original = cloneWithoutOriginal(candidate);
  return candidate;
}

function candidateFromRecord(
  row: Record<string, unknown>,
  index: number,
  sourceName: string,
  defaultUnit: string,
): FormationTopCandidate {
  const get = (...keys: string[]) => {
    for (const key of keys) {
      const exact = row[key];
      if (exact !== undefined && normalize(exact)) return normalize(exact);
      const foundKey = Object.keys(row).find((candidate) =>
        candidate.toLowerCase().replace(/[^a-z0-9]+/g, '') === key.toLowerCase().replace(/[^a-z0-9]+/g, ''),
      );
      if (foundKey && normalize(row[foundKey])) return normalize(row[foundKey]);
    }
    return '';
  };

  const rawEvidenceRecords = row.evidenceRecords ?? row.evidence_records;
  const evidenceRecords: FormationTopEvidenceRecord[] = Array.isArray(rawEvidenceRecords)
    ? rawEvidenceRecords
        .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
        .map((item) => ({
          source: normalize(item.source ?? item.source_document ?? item.document),
          evidence: normalize(item.evidence ?? item.source_reference ?? item.page),
          confidence: normalize(item.confidence) || undefined,
          authority: normalize(item.authority) || undefined,
        }))
        .filter((item) => item.source || item.evidence)
    : [];

  const candidate: FormationTopCandidate = {
    id: idForCandidate(`${sourceName}-${index}`),
    state: 'unreviewed',
    marker: formatMarkerName(get('Formation or Marker', 'Marker', 'Formation', 'marker_name')),
    group: get('Group', 'Stratigraphic Group', 'group'),
    markerType: get('Marker Type', 'marker_type') || 'Formation top',
    pickStatus: get('Pick Status', 'Status', 'pick_status') || 'Imported',
    md: get('MD (m RT)', 'MD', 'Measured Depth', 'md_m_rt'),
    tvd: get('TVD (m RT)', 'TVD', 'tvd_m_rt'),
    tvdss: get('TVDSS (m MSL)', 'TVDSS', 'tvdss_m_msl'),
    unit: get('Unit', 'Depth Unit') || defaultUnit || 'm',
    depthReference: get('Depth Reference', 'Reference') || 'RT',
    uncertainty: get('Uncertainty (+/- m)', 'Uncertainty', 'uncertainty_m'),
    source: get('Source Document', 'Source') || sourceName,
    evidence: get('Evidence', 'Source Reference', 'Source Page') || evidenceRecords.map((item) => item.evidence).filter(Boolean).join(' | '),
    evidenceRecords,
    confidence: get('Confidence'),
    notes: get('Notes'),
    original: null,
  };
  candidate.confidence = normalizedConfidenceForCandidate(candidate);
  candidate.original = cloneWithoutOriginal(candidate);
  return candidate;
}

function readActiveFtmSession(): PersistedFtmSession | null {
  try {
    const stored = window.sessionStorage.getItem(FTM_ACTIVE_SESSION_KEY);
    if (!stored) return null;
    const parsed = JSON.parse(stored) as PersistedFtmSession;
    return parsed?.selectedWellId ? parsed : null;
  } catch {
    window.sessionStorage.removeItem(FTM_ACTIVE_SESSION_KEY);
    return null;
  }
}

export function FormationTopsManagerPage({ onBack }: { onBack: () => void }) {
  const activeSessionRef = useRef<PersistedFtmSession | null>(readActiveFtmSession());
  const [wells, setWells] = useState<ManagedWellRecord[]>([]);
  const [selectedWellId, setSelectedWellId] = useState(activeSessionRef.current?.selectedWellId ?? '');
  const [wellSearch, setWellSearch] = useState('');
  const [candidates, setCandidates] = useState<FormationTopCandidate[]>(activeSessionRef.current?.candidates ?? []);
  const [supportingFiles, setSupportingFiles] = useState<SupportingFile[]>(activeSessionRef.current?.supportingFiles ?? []);
  const [supportingFileObjects, setSupportingFileObjects] = useState<File[]>([]);
  const supportingFileObjectsRef = useRef<File[]>([]);
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
  const [loadingWells, setLoadingWells] = useState(true);
  const [status, setStatus] = useState('Select a managed well to begin.');
  const [error, setError] = useState<string | null>(null);
  const [activeEditId, setActiveEditId] = useState<string | null>(null);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(() => new Set());
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const aiInputRef = useRef<HTMLInputElement | null>(null);

  const selectedWell = useMemo(
    () => wells.find((well) => well.managed_well_id === selectedWellId) ?? null,
    [selectedWellId, wells],
  );

  const filteredWells = useMemo(() => {
    const query = wellSearch.trim().toLowerCase();
    if (!query) return wells;
    return wells.filter((well) =>
      [
        well.display_name,
        well.well_name,
        well.wellbore_name,
        well.uwi,
        well.managed_well_id,
      ].some((value) => normalize(value).toLowerCase().includes(query)),
    );
  }, [wellSearch, wells]);

  const summary = useMemo(() => ({
    total: candidates.length,
    confirmed: candidates.filter((candidate) => candidate.state === 'confirmed' || candidate.state === 'edited').length,
    rejected: candidates.filter((candidate) => candidate.state === 'rejected').length,
    unreviewed: candidates.filter((candidate) => candidate.state === 'unreviewed' || candidate.state === 'conflict').length,
  }), [candidates]);

  const aiRevision = useToolboxAiRevision('FTM', selectedWellId, candidates.map((candidate) => candidate.id));

  useEffect(() => {
    let cancelled = false;
    setLoadingWells(true);
    fetchWlvJson<ManagedWellRecord[]>('/api/wlv/inventory/wells')
      .then((records) => {
        if (cancelled) return;
        setWells(records);
        setStatus(records.length ? 'Select a managed well to begin.' : 'No managed wells are available.');
      })
      .catch((caught) => {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : 'Unable to load MWD wells');
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
      supportingFileObjectsRef.current = [];
      setSupportingFileObjects([]);
      setStatus('Select a managed well to begin.');
      return;
    }
    const activeSession = activeSessionRef.current;
    if (activeSession?.selectedWellId === selectedWellId) {
      setCandidates(activeSession.candidates ?? []);
      setSupportingFiles(activeSession.supportingFiles ?? []);
      supportingFileObjectsRef.current = [];
      setSupportingFileObjects([]);
      setStatus(`Restored active Formation Tops Manager session for ${selectedWell?.display_name || selectedWell?.well_name || selectedWellId}.`);
      activeSessionRef.current = null;
      return;
    }

    const stored = window.localStorage.getItem(`${FTM_STORAGE_PREFIX}${selectedWellId}`);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as PersistedFtmSession;
        setCandidates(parsed.candidates ?? []);
        setSupportingFiles(parsed.supportingFiles ?? []);
        supportingFileObjectsRef.current = [];
        setSupportingFileObjects([]);
        setStatus(
          parsed.supportingFiles?.length
            ? `Restored saved review. Reattach ${parsed.supportingFiles.length} supporting file(s) before exporting a new AI package.`
            : `Restored saved review for ${selectedWell?.display_name || selectedWell?.well_name || selectedWellId}.`,
        );
        return;
      } catch {
        window.localStorage.removeItem(`${FTM_STORAGE_PREFIX}${selectedWellId}`);
      }
    }

    const existing: FormationTopCandidate[] = [];
    for (const group of selectedWell?.product_groups ?? []) {
      for (const item of group.items ?? []) {
        if (item.product_subgroup_key !== 'formation_tops') continue;
        for (const [index, marker] of (item.provenance?.formation_tops ?? []).entries()) {
          const candidate: FormationTopCandidate = {
            id: idForCandidate(`existing-${index}`),
            state: 'existing',
            marker: formatMarkerName(marker.marker_name),
            group: normalize(marker.group),
            markerType: normalize(marker.marker_type) || 'Formation top',
            pickStatus: normalize(marker.pick_status) || 'Existing',
            md: normalize(marker.md_m_rt),
            tvd: normalize(marker.tvd_m_rt),
            tvdss: normalize(marker.tvdss_m_msl),
            unit: selectedWell?.depth_unit || 'm',
            depthReference: 'RT',
            uncertainty: normalize(marker.uncertainty_m),
            source: normalize(marker.source_document) || 'Existing Formation Tops dataset',
            evidence: normalize(marker.source_page),
            evidenceRecords: [{
              source: normalize(marker.source_document) || 'Existing Formation Tops dataset',
              evidence: normalize(marker.source_page),
            }],
            confidence: normalize(marker.md_m_rt) ? '' : 'invalid',
            notes: '',
            original: null,
          };
          candidate.confidence = normalizedConfidenceForCandidate(candidate);
          candidate.original = cloneWithoutOriginal(candidate);
          existing.push(candidate);
        }
      }
    }
    setCandidates(existing);
    setSupportingFiles([]);
    supportingFileObjectsRef.current = [];
    setSupportingFileObjects([]);
    setStatus(`Loaded ${existing.length} existing Formation Tops for ${selectedWell?.display_name || selectedWell?.well_name || selectedWellId}.`);
  }, [selectedWellId, selectedWell, loadingWells]);

  useEffect(() => {
    if (!selectedWellId) {
      window.sessionStorage.removeItem(FTM_ACTIVE_SESSION_KEY);
      return;
    }

    const payload: PersistedFtmSession = {
      selectedWellId,
      candidates,
      supportingFiles,
      savedAt: new Date().toISOString(),
    };
    const serialized = JSON.stringify(payload);
    window.sessionStorage.setItem(FTM_ACTIVE_SESSION_KEY, serialized);
    window.localStorage.setItem(`${FTM_STORAGE_PREFIX}${selectedWellId}`, serialized);
  }, [selectedWellId, candidates, supportingFiles]);

  const saveReview = () => {
    if (!selectedWellId) {
      setError('Select a managed well before saving.');
      return;
    }
    const payload: PersistedFtmSession = {
      selectedWellId,
      candidates,
      supportingFiles,
      savedAt: new Date().toISOString(),
    };
    window.localStorage.setItem(`${FTM_STORAGE_PREFIX}${selectedWellId}`, JSON.stringify(payload));
    setStatus(`Review saved for ${selectedWell?.display_name || selectedWell?.well_name || selectedWellId}.`);
    setError(null);
  };

  const importRows = async (file: File): Promise<FormationTopCandidate[]> => {
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (extension === 'json') {
      const parsed = JSON.parse(await file.text()) as unknown;
      const documentRows = typeof parsed === 'object' && parsed !== null && Array.isArray((parsed as { document_results?: unknown[] }).document_results)
        ? (parsed as { document_results: Array<{ candidates?: unknown[] }> }).document_results.flatMap((result) => Array.isArray(result?.candidates) ? result.candidates : [])
        : [];
      const rawRows = Array.isArray(parsed)
        ? parsed
        : typeof parsed === 'object' && parsed !== null && Array.isArray((parsed as { candidates?: unknown[] }).candidates)
          ? (parsed as { candidates: unknown[] }).candidates
          : documentRows;
      return rawRows
        .filter((row): row is Record<string, unknown> => typeof row === 'object' && row !== null)
        .map((row, index) => candidateFromRecord(row, index, file.name, selectedWell?.depth_unit || 'm'));
    }

    if (extension === 'csv' || extension === 'xlsx' || extension === 'xls') {
      const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' });
      const sheet = workbook.Sheets[workbook.SheetNames[0]];
      const rawRows = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
      return rawRows.map((row, index) =>
        candidateFromRecord(row, index, file.name, selectedWell?.depth_unit || 'm'),
      );
    }

    return [];
  };

  const toggleAllSupportingFiles = () => {
    if (selectedSupportingFileIndexes.size === supportingFileObjects.length && supportingFileObjects.length > 0) {
      setSelectedSupportingFileIndexes(new Set());
      return;
    }
    setSelectedSupportingFileIndexes(new Set(supportingFileObjects.map((_, index) => index)));
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
        const file = supportingFileObjects[index];
        if (file) delete next[file.name];
      });
      return next;
    });
    if (
      activeSupportingFileAudit
      && indexes.some((index) => supportingFileObjects[index]?.name === activeSupportingFileAudit.fileName)
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

  const handleSupportingFiles = async (files: FileList | File[]) => {
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

    const existingCount = supportingFileObjects.length;
    const nextObjects = [...supportingFileObjects, ...incoming];
    supportingFileObjectsRef.current = nextObjects;
    setSupportingFileObjects(nextObjects);
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
    supportingFileObjectsRef.current = [];
    setSupportingFileObjects([]);
    setSelectedSupportingFileIndexes(new Set());
    setDeterministicSupportingFileIndexes(new Set());
    setSkippedArchiveMembers([]);
    setSupportingFileAuditResults({});
    setSupportingFilePreScanResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setStatus('Supporting files cleared. Formation-top candidates and review state were preserved.');
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
    if (!supportingFileObjects.length) {
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
      const managedAiRules = await fetchToolboxAiRules('FTM');
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
        const file = supportingFileObjects[sourceIndex];
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

  const candidateIdentity = (row: Record<string, unknown>): string => {
    const marker = formatMarkerName(row.marker ?? row.marker_name ?? row['Formation or Marker']).toLowerCase();
    const rawMd = normalize(row.md ?? row.md_m_rt ?? row['MD'] ?? row['Measured Depth']);
    const numericMd = rawMd && Number.isFinite(Number(rawMd)) ? Number(rawMd).toFixed(3) : rawMd;
    return `${marker}@@${numericMd}`;
  };

  const validateMultiDocumentAiResponse = (parsed: unknown): string | null => {
    if (selectedSupportingFileIndexes.size <= 1) return null;
    if (typeof parsed !== 'object' || parsed === null) return 'Multi-document AI response must be a JSON object.';
    const payload = parsed as { candidates?: unknown[]; document_results?: unknown[] };
    if (!Array.isArray(payload.document_results)) return 'Multi-document AI response is missing required document_results. Each supporting document must be extracted independently.';
    if (!Array.isArray(payload.candidates)) return 'Multi-document AI response is missing the reconciled top-level candidates union.';

    const expectedSources = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b).map((index) => supportingFileObjectsRef.current[index]?.name).filter((name): name is string => Boolean(name));
    const resultsBySource = new Map<string, Record<string, unknown>>();
    for (const rawResult of payload.document_results) {
      if (typeof rawResult !== 'object' || rawResult === null) continue;
      const result = rawResult as Record<string, unknown>;
      const source = normalize(result.source_document);
      if (source) resultsBySource.set(source, result);
    }
    const missingSources = expectedSources.filter((source) => !resultsBySource.has(source));
    if (missingSources.length) return `AI response omitted independent document result(s): ${missingSources.join(', ')}`;

    const unionRows = payload.candidates.filter((row): row is Record<string, unknown> => typeof row === 'object' && row !== null);
    const unionByIdentity = new Map<string, Record<string, unknown>>();
    unionRows.forEach((row) => unionByIdentity.set(candidateIdentity(row), row));

    for (const source of expectedSources) {
      const result = resultsBySource.get(source)!;
      const rows = Array.isArray(result.candidates) ? result.candidates : [];
      for (const rawRow of rows) {
        if (typeof rawRow !== 'object' || rawRow === null) continue;
        const row = rawRow as Record<string, unknown>;
        const identity = candidateIdentity(row);
        if (!identity || identity === '@@') continue;
        const unionRow = unionByIdentity.get(identity);
        if (!unionRow) return `Non-destructive union violation: ${normalize(row.marker ?? row.marker_name) || 'candidate'} from ${source} is missing from reconciled candidates.`;
        const evidenceRecords = unionRow.evidenceRecords ?? unionRow.evidence_records;
        if (!Array.isArray(evidenceRecords) || !evidenceRecords.some((item) => typeof item === 'object' && item !== null && normalize((item as Record<string, unknown>).source ?? (item as Record<string, unknown>).source_document) === source)) {
          return `Provenance violation: reconciled candidate ${normalize(row.marker ?? row.marker_name) || identity} does not retain evidence from ${source}.`;
        }
      }
    }
    return null;
  };

  const exportAiPackage = async () => {
    if (!selectedWell) {
      setError('Select a managed well before exporting an AI package.');
      return;
    }

    const selectedIndexes = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b);
    if (!selectedIndexes.length) {
      setError('Select at least one supporting file for AI export.');
      return;
    }

    try {
      const managedAiRules = await fetchToolboxAiRules('FTM');
      const combinedRules = { ...managedAiRules.rules } as Record<string, unknown>;
      const deterministicProfile = (
        combinedRules.deterministic_screening
        && typeof combinedRules.deterministic_screening === 'object'
        && !Array.isArray(combinedRules.deterministic_screening)
      ) ? combinedRules.deterministic_screening as Record<string, unknown> : {};
      delete combinedRules.deterministic_screening;
      const deterministicProfileSignature = JSON.stringify(deterministicProfile);

      const selectedResults = selectedIndexes.map((index) => {
        const file = supportingFileObjects[index];
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
        size: supportingFileObjects[result.sourceIndex]?.size ?? result.preparedEvidence.size,
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
      const anyDeterministic = selectedResults.some((result) => result.deterministicRequested);

      const packageRevision = await aiRevision.allocateExport();
      const packagePayload = {
        package_type: 'formation_tops_manager_ai_package',
        managed_ai_rules: combinedRules,
        deterministic_screening: {
          enabled: anyDeterministic,
          execution: anyDeterministic ? 'application_side_completed_before_export' : 'disabled',
          profile: deterministicProfile,
          standard_version: managedAiRules.active_version,
          authority: 'AI Standards Manager',
          evidence_preparation: evidencePreparation,
          estimated_evidence_tokens: estimatedEvidenceTokens,
          provider_payload_policy: anyDeterministic
            ? 'Per-document pre-scan results are embedded exactly as resolved in the Supporting file manifest. Selected original PDF pages preserve graphics/layout.'
            : 'Full original supporting files are embedded because the selected documents use full-original mode.',
        },
        managed_ai_rules_version: managedAiRules.active_version,
        managed_ai_rules_updated_at: managedAiRules.updated_at,
        managed_ai_rules_are_authoritative_overrides: true,
        schema_version: '1.2.0',
        revision: toolboxAiPackageRevision('FTM', packageRevision),
        created_at: new Date().toISOString(),
        managed_well: {
          managed_well_id: selectedWell.managed_well_id,
          managed_well_uid: selectedWell.managed_well_uid ?? null,
          well_id: selectedWell.well_id,
          well_name: selectedWell.well_name ?? selectedWell.display_name ?? null,
          wellbore_id: selectedWell.wellbore_id ?? null,
          wellbore_name: selectedWell.wellbore_name ?? null,
          uwi: selectedWell.uwi ?? null,
          depth_unit: selectedWell.depth_unit ?? null,
          top_depth: selectedWell.top_depth ?? null,
          base_depth: selectedWell.base_depth ?? null,
        },
        package_instructions: {
          purpose: 'External AI formation-top discovery package for human review in Formation Tops Manager.',
          deterministic_screening_budget_scope: 'per_document',
          max_selected_pages_per_document: Number(deterministicProfile.max_selected_pages ?? 50),
          no_shared_cross_document_page_budget: true,
          existing_candidates_are_reconciliation_context_only: true,
          existing_candidates_must_not_suppress_new_document_discoveries: true,
          reconciliation_rules: {
            preserve_union_of_all_valid_per_document_candidates: true,
            identical_marker_and_depth_may_consolidate: true,
            consolidated_candidates_must_retain_evidence_from_every_supporting_source: true,
            materially_different_depths_for_the_same_marker_must_remain_separate_conflicts_or_alternatives: true,
            do_not_deduplicate_by_marker_name_alone: true,
          },
        },
        document_work_units: selectedResults.map((result, index) => ({
          work_unit_id: `document-${index + 1}`,
          source_document: result.sourceName,
          source_mime_type: result.preparedEvidence.mime_type,
          source_size: sourceFiles[index]?.size ?? result.preparedEvidence.size,
          sha256: result.sourceSha256,
          deterministic_screening: {
            enabled: result.deterministicRequested,
            executed_in_application: result.deterministicRequested,
            max_selected_pages: Number(deterministicProfile.max_selected_pages ?? 50),
            budget_scope: 'this_document_only',
            preparation: result.evidencePreparation,
          },
          instruction: 'Screen and extract this document independently. Return every defensible candidate from this document before any cross-document reconciliation.',
        })),
        extraction_contract: {
          task: 'Discover and extract all reasonably supported formation, group, stratigraphic boundary and useful operational marker candidates from the embedded supporting files for human review.',
          governing_rule: 'Capture broadly. Label precisely. Do not silently promote inference to fact.',
          imported_values_are_proposals: true,
          evidence_required_for_every_candidate: true,
          preserve_reported_depth_unit_and_reference: true,
          distinguish_actual_prognosed_interpreted_and_imported_picks: true,
          distinguish_top_base_unconformity_and_other_marker_types: true,
          include_source_file_and_specific_page_table_section_figure_or_row_reference: true,
          do_not_replace_existing_tops_automatically: true,
          comprehensive_discovery: {
            capture_explicit_candidates_first: true,
            also_capture_supported_candidates_from_narrative_figures_logs_correlations_and_sequence_context: true,
            do_not_omit_a_useful_candidate_only_because_it_is_uncertain: true,
            allow_coincident_group_and_formation_markers_at_the_same_depth: true,
            allow_candidates_with_only_some_depth_fields_present: true,
            leave_unsupported_fields_empty: true,
            never_invent_unsupported_values: true,
          },
          confidence_rules: {
            high: 'Marker identity and measured depth are explicit in an authoritative table, interpreted log, labelled figure or final report source, and classification is explicit or unambiguous.',
            medium: 'Marker is explicit and has a supported measured depth, but a depth or classification requires limited derivation, graphical reading, indirect corroboration or reconciliation between credible sources.',
            low: 'Marker has a supported measured depth, but the marker, depth or classification is materially inferred, approximate, ambiguous or supported only by incomplete contextual evidence.',
            invalid: 'Marker identity may be supported and should still be returned for review, but no usable measured depth (MD) is available.',
          },
        },
        expected_response: {
          package_type: 'formation_tops_manager_ai_response',
          schema_version: '1.2.0',
          revision: toolboxAiExpectedResponseRevision(packageRevision),
          document_results: [{
            work_unit_id: 'document-1',
            source_document: 'embedded source filename',
            screening: { selected_pages: ['page numbers'], selected_page_count: 'number' },
            candidates: [{
              marker: 'string',
              group: 'string or empty',
              markerType: 'Formation top | Formation base | Unconformity | Other',
              pickStatus: 'Actual | Prognosed | Interpreted | Imported',
              md: 'number or empty',
              tvd: 'number or empty',
              tvdss: 'number or empty',
              unit: 'reported depth unit',
              depthReference: 'RT | RKB | KB | MSL | other reported reference',
              source: 'this work unit source filename',
              evidence: 'page, table, section or quoted evidence reference',
              confidence: 'high | medium | low | invalid',
              notes: 'string or empty',
            }],
          }],
          candidates: [{
            marker: 'string',
            group: 'string or empty',
            markerType: 'Formation top | Formation base | Unconformity | Other',
            pickStatus: 'Actual | Prognosed | Interpreted | Imported',
            md: 'number or empty',
            tvd: 'number or empty',
            tvdss: 'number or empty',
            unit: 'reported depth unit',
            depthReference: 'RT | RKB | KB | MSL | other reported reference',
            source: 'embedded source filename',
            evidence: 'legacy display summary of supporting evidence',
            evidenceRecords: [{
              source: 'embedded source filename',
              evidence: 'page, table, section or quoted evidence reference',
              confidence: 'high | medium | low | invalid',
              authority: 'optional source authority note',
            }],
            confidence: 'high | medium | low | invalid',
            notes: 'string or empty',
          }],
        },
        existing_candidates: candidates.map(({ original: _original, ...candidate }) => candidate),
        source_files: sourceFiles,
        source_payload_policy: anyDeterministic
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
      };

      const safeName = normalize(
        selectedWell.well_name || selectedWell.display_name || selectedWell.managed_well_id,
      ).replace(/[^A-Za-z0-9_-]+/g, '_');
      const packageFilename = toolboxAiPackageFilename('FTM_AI_PACKAGE', safeName, packageRevision);
      const compressedPackageFilename = await downloadCompressedJsonPackage(
        packageFilename,
        JSON.stringify(packagePayload, null, 2),
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
      setError(caught instanceof Error ? caught.message : 'Unable to build AI package');
    }
  };

  const importAiResponse = async (file: File) => {
    if (!selectedWellId) {
      setError('Select a managed well before importing an AI response.');
      return;
    }
    try {
      if (file.name.toLowerCase().endsWith('.json')) {
        const parsed = JSON.parse(await file.text()) as unknown;
        const multiDocumentError = validateMultiDocumentAiResponse(parsed);
        if (multiDocumentError) throw new Error(multiDocumentError);
        void aiRevision.syncImportedArtifact(file.name, parsed);
      } else {
        if (selectedSupportingFileIndexes.size > 1) throw new Error('Multi-document AI responses must use JSON schema 1.2.0 so per-document extraction and provenance can be validated.');
        void aiRevision.syncImportedArtifact(file.name);
      }
      const imported = await importRows(file);
      setCandidates((current) => [...current, ...imported]);
      setStatus(`Imported ${imported.length} AI proposal(s) for confirmation, editing or rejection.`);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to import AI response');
    }
  };


  const exportCsv = () => {
    if (!selectedWell) {
      setError('Select a managed well before exporting CSV.');
      return;
    }
    if (!candidates.length) {
      setError('No formation-top candidates are available to export.');
      return;
    }

    const safeName = normalize(
      selectedWell.well_name || selectedWell.display_name || selectedWell.managed_well_id,
    ).replace(/[^A-Za-z0-9_-]+/g, '_');

    const columns = [
      'Marker',
      'Group',
      'Type',
      'Pick Status',
      'MD',
      'TVD',
      'TVDSS',
      'Unit',
      'Reference',
      'Uncertainty',
      'Source',
      'Evidence',
      'Evidence Records',
      'Confidence',
      'Review Status',
      'Notes',
    ];

    const escapeCsv = (value: unknown) => {
      const stringValue = String(value ?? '');
      return /[",\n]/.test(stringValue)
        ? `"${stringValue.replace(/"/g, '""')}"`
        : stringValue;
    };

    const lines = [columns.join(',')];
    for (const candidate of candidates) {
      lines.push([
        candidate.marker,
        candidate.group,
        candidate.markerType,
        candidate.pickStatus,
        candidate.md,
        candidate.tvd,
        candidate.tvdss,
        candidate.unit,
        candidate.depthReference,
        candidate.uncertainty,
        candidate.source,
        candidate.evidence,
        JSON.stringify(candidate.evidenceRecords ?? []),
        normalizedConfidenceForCandidate(candidate),
        candidate.state,
        candidate.notes,
      ].map(escapeCsv).join(','));
    }

    downloadText(`FTM_TOPS_${safeName}.csv`, lines.join('\n'), 'text/csv;charset=utf-8');
    setStatus(`Exported ${candidates.length} Formation Tops row(s) to CSV.`);
    setError(null);
  };


  const deleteCandidate = (id: string) => {
    setCandidates((current) => current.filter((candidate) => candidate.id !== id));
    if (activeEditId === id) setActiveEditId(null);
    setStatus('Formation Top row deleted.');
    setError(null);
  };

  const sortCandidates = (sortBy: 'name' | 'md') => {
    setCandidates((current) => [...current].sort((left, right) => {
      if (sortBy === 'name') {
        const nameComparison = normalize(left.marker).localeCompare(
          normalize(right.marker),
          undefined,
          { sensitivity: 'base' },
        );
        if (nameComparison !== 0) return nameComparison;
      }

      const leftMd = Number(left.md);
      const rightMd = Number(right.md);
      const leftValid = Number.isFinite(leftMd) && normalize(left.md) !== '';
      const rightValid = Number.isFinite(rightMd) && normalize(right.md) !== '';

      if (leftValid && rightValid) return leftMd - rightMd;
      if (leftValid) return -1;
      if (rightValid) return 1;
      return normalize(left.marker).localeCompare(normalize(right.marker), undefined, { sensitivity: 'base' });
    }));
    setStatus(
      sortBy === 'name'
        ? 'Formation Tops sorted by name.'
        : 'Formation Tops sorted by MD. Rows without MD are placed last.',
    );
    setError(null);
  };

  const updateCandidate = (id: string, field: keyof FormationTopCandidate, value: string) => {
    setCandidates((current) => current.map((candidate) => {
      if (candidate.id !== id) return candidate;
      const next = { ...candidate, [field]: value };
      if (!hasUsableMeasuredDepth(next)) {
        next.confidence = 'invalid';
      } else if (field === 'confidence' && normalize(value).toLowerCase() === 'invalid') {
        next.confidence = 'invalid';
      }
      if (field !== 'state' && candidate.state !== 'existing' && candidate.state !== 'rejected') {
        next.state = 'edited';
      }
      return next;
    }));
  };

  const confirmCandidate = (id: string) => {
    setCandidates((current) => current.map((candidate) =>
      candidate.id === id
        ? { ...candidate, state: candidate.state === 'edited' ? 'edited' : 'confirmed' }
        : candidate,
    ));
    setActiveEditId(null);
  };

  const toggleCandidateSelection = (id: string) => {
    setSelectedCandidateIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllCandidates = () => {
    setSelectedCandidateIds(new Set(candidates.map((candidate) => candidate.id)));
  };

  const clearCandidateSelection = () => {
    setSelectedCandidateIds(new Set());
  };

  const acceptSelectedCandidates = () => {
    selectedCandidateIds.forEach((id) => confirmCandidate(id));
    setSelectedCandidateIds(new Set());
  };

  const rejectCandidate = (id: string) => {
    setCandidates((current) => current.map((candidate) =>
      candidate.id === id ? { ...candidate, state: 'rejected' } : candidate,
    ));
    setActiveEditId(null);
  };


  const publishApproved = async () => {
    if (!selectedWell) {
      setError('Select a managed well before publishing.');
      return;
    }
    const reviewed = candidates.filter((candidate) =>
      candidate.state === 'confirmed' || candidate.state === 'edited',
    );
    const approved = reviewed.filter((candidate) =>
      hasUsableMeasuredDepth(candidate) && normalize(candidate.confidence).toLowerCase() !== 'invalid',
    );
    const withheldInvalid = reviewed.length - approved.length;
    if (!approved.length) {
      setError(
        withheldInvalid
          ? `${withheldInvalid} reviewed candidate(s) are retained but cannot be published because they have no usable MD or still have Invalid confidence.`
          : 'No confirmed or edited-and-confirmed tops are available to publish.',
      );
      return;
    }

    const payload = {
      dataset_type: 'formation_tops',
      dataset_status: 'reviewed',
      source: 'Formation Tops Manager',
      managed_well_id: selectedWell.managed_well_id,
      formation_tops: approved.map((candidate) => ({
        group: candidate.group || null,
        marker_name: candidate.marker,
        marker_type: candidate.markerType,
        pick_status: candidate.pickStatus,
        md_m_rt: candidate.md ? Number(candidate.md) : null,
        tvd_m_rt: candidate.tvd ? Number(candidate.tvd) : null,
        tvdss_m_msl: candidate.tvdss ? Number(candidate.tvdss) : null,
        depth_unit: candidate.unit,
        depth_reference: candidate.depthReference,
        uncertainty_m: candidate.uncertainty ? Number(candidate.uncertainty) : null,
        source_document: candidate.source,
        source_reference: candidate.evidence,
        evidence_records: candidate.evidenceRecords ?? [],
        confidence: normalizedConfidenceForCandidate(candidate) || null,
        notes: candidate.notes || null,
      })),
    };

    try {
      const response = await fetch(
        `${wlvApiBaseUrl()}/api/wlv/inventory/wells/${encodeURIComponent(selectedWell.managed_well_id)}/formation-tops`,
        {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        },
      );
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Publication endpoint returned ${response.status}`);
      }
      const result = await response.json() as { published_count?: number };
      setStatus(
        `Published ${result.published_count ?? approved.length} approved Formation Tops directly to MWD for ${selectedWell.display_name || selectedWell.well_name || selectedWell.managed_well_id}.` +
        (withheldInvalid ? ` Retained ${withheldInvalid} reviewed candidate(s) as non-promotable because MD is missing or confidence is Invalid.` : ''),
      );
      setError(null);
      saveReview();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Direct MWD publication failed.');
    }
  };

  const clearReview = () => {
    if (!selectedWellId && !wellSearch && !candidates.length && !supportingFiles.length && !supportingFileObjects.length) return;
    if (selectedWellId) window.localStorage.removeItem(`${FTM_STORAGE_PREFIX}${selectedWellId}`);
    window.sessionStorage.removeItem(FTM_ACTIVE_SESSION_KEY);
    setSelectedWellId('');
    setWellSearch('');
    setCandidates([]);
    setSupportingFiles([]);
    supportingFileObjectsRef.current = [];
    setSupportingFileObjects([]);
    setSelectedSupportingFileIndexes(new Set());
    setDeterministicSupportingFileIndexes(new Set());
    setSkippedArchiveMembers([]);
    setSupportingFilePreScanResults({});
    setSupportingFileAuditResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    setPreScanRunning(false);
    setSelectedCandidateIds(new Set());
    setActiveEditId(null);
    setDeterministicFailurePrompt(null);
    deterministicFailureResolverRef.current = null;
    setGraphicsChoiceFiles(null);
    graphicsChoiceResolverRef.current = null;
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (aiInputRef.current) aiInputRef.current.value = '';
    setStatus('Formation Tops Manager cleared. Published Formation Tops were not removed.');
    setError(null);
  };

  return (
    <section className="wlv-metadata-tool wlv-ftm-tool">
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
      <header className="wlv-metadata-tool__header">
        <button type="button" className="wlv-metadata-tool__back" onClick={onBack}>‹ Toolbox</button>
        <div className="wlv-metadata-tool__title">
          <h1>Formation Tops Manager</h1>
          <p>Prepare external AI packages, review returned formation-marker recommendations, and publish approved tops.</p>
        </div>
        <div className="wlv-metadata-tool__window-actions">
          <button
            type="button"
            onClick={clearReview}
            disabled={!selectedWellId && !wellSearch && candidates.length === 0 && supportingFiles.length === 0 && supportingFileObjects.length === 0}
            title="Clear the entire Formation Tops Manager workspace"
          >
            Clear
          </button>
          <button type="button" className="wlv-metadata-tool__close" aria-label="Close Formation Tops Manager" onClick={onBack}>×</button>
        </div>
      </header>

      <div
        className="wlv-metadata-tool__input-grid"
        style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}
      >
        <section className="wlv-metadata-tool__drop-panel wlv-ftm-tool__well-panel">
          <div className="wlv-metadata-tool__drop-copy">
            <strong>Managed Well</strong>
            <span>
              {selectedWell
                ? `${selectedWell.display_name || selectedWell.well_name || selectedWell.well_id}${selectedWell.wellbore_name ? ` · ${selectedWell.wellbore_name}` : ''}`
                : loadingWells
                  ? 'Loading wells from the Managed Well Directory…'
                  : 'Select a well from the Managed Well Directory'}
            </span>
          </div>
          <div className="wlv-ftm-tool__well-controls">
            <input
              value={wellSearch}
              onChange={(event) => setWellSearch(event.target.value)}
              placeholder="Search MWD"
              aria-label="Search managed wells"
            />
            <select
              value={selectedWellId}
              aria-label="Select managed well"
              onChange={(event) => {
                const next = event.target.value;
                if (
                  selectedWellId
                  && next !== selectedWellId
                  && candidates.some((candidate) => candidate.state === 'edited' || candidate.state === 'confirmed')
                  && !window.confirm('Switch wells and leave the current review? Save first if required.')
                ) return;
                setSelectedWellId(next);
                setError(null);
              }}
            >
              <option value="">Select a well…</option>
              {filteredWells.map((well) => (
                <option key={well.managed_well_id} value={well.managed_well_id}>
                  {well.display_name || well.well_name || well.well_id}
                  {well.wellbore_name ? ` — ${well.wellbore_name}` : ''}
                  {well.uwi ? ` (${well.uwi})` : ''}
                </option>
              ))}
            </select>
          </div>
        </section>

        <section
          className={`wlv-metadata-tool__drop-panel ${!selectedWellId ? 'is-disabled' : ''}`}
          onDragOver={(event) => {
            event.preventDefault();
            if (selectedWellId) event.dataTransfer.dropEffect = 'copy';
          }}
          onDrop={(event) => {
            event.preventDefault();
            if (selectedWellId) void handleSupportingFiles(event.dataTransfer.files);
          }}
        >
          <div className="wlv-metadata-tool__drop-copy">
            <strong>Supporting Files</strong>
            <span>
              {supportingFileObjects.length
                ? `${supportingFileObjects.length} staged · ${selectedSupportingFileIndexes.size} selected`
                : supportingFiles.length
                  ? `${supportingFiles.length} file reference(s) remembered · reload required`
                  : selectedWellId
                    ? 'Drop PDF, XLSX, CSV, TXT, JSON, image or ZIP bundle here'
                    : 'Select a managed well first'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button type="button" disabled={!selectedWellId} onClick={() => fileInputRef.current?.click()}>Browse</button>
            <button type="button" disabled={!selectedWellId || supportingFiles.length === 0} onClick={clearSupportingFiles}>Clear</button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.csv,.xlsx,.xls,.txt,.json,.zip,image/*"
            hidden
            onChange={(event) => {
              if (event.target.files) void handleSupportingFiles(event.target.files);
              event.currentTarget.value = '';
            }}
          />
        </section>

        <section
          className={`wlv-metadata-tool__drop-panel ${!selectedWellId ? 'is-disabled' : ''}`}
          onDragOver={(event) => {
            event.preventDefault();
            if (selectedWellId) event.dataTransfer.dropEffect = 'copy';
          }}
          onDrop={(event) => {
            event.preventDefault();
            const file = event.dataTransfer.files?.[0];
            if (selectedWellId && file) void importAiResponse(file);
          }}
        >
          <div className="wlv-metadata-tool__drop-copy">
            <strong>Import and Review</strong>
            <span>
              {selectedWellId
                ? 'Drop AI response JSON, CSV or Excel here'
                : 'Select a managed well first'}
            </span>
          </div>
          <button type="button" disabled={!selectedWellId} onClick={() => aiInputRef.current?.click()}>Browse</button>
          <input
            ref={aiInputRef}
            type="file"
            accept=".json,.csv,.xlsx,.xls"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void importAiResponse(file);
              event.currentTarget.value = '';
            }}
          />
        </section>
      </div>

      {(supportingFileObjects.length > 0 || skippedArchiveMembers.length > 0) && (
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
              aria-controls="ftm-supporting-file-manifest-body"
              title={supportingManifestCollapsed ? 'Expand supporting file manifest' : 'Collapse supporting file manifest'}
              style={{ flex: '0 0 auto', minWidth: '34px', padding: '4px 8px' }}
            >
              {supportingManifestCollapsed ? '▸' : '▾'}
            </button>
          </div>

          <div id="ftm-supporting-file-manifest-body" hidden={supportingManifestCollapsed}>
            {supportingFileObjects.length > 0 && (
              <div style={{ maxHeight: '280px', overflow: 'auto' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) 82px 128px 132px 92px 42px', alignItems: 'center', minHeight: '32px', color: '#93a1b0', background: '#11171d', borderBottom: '1px solid #293440', fontSize: '10px', fontWeight: 600 }}>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '7px 14px' }}>
                    <input
                      type="checkbox"
                      checked={supportingFileObjects.length > 0 && selectedSupportingFileIndexes.size === supportingFileObjects.length}
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

                {supportingFileObjects.map((file, index) => {
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
                    {(Array.from(selectedSupportingFileIndexes).reduce((sum, index) => sum + Number(supportingFileObjects[index]?.size || 0), 0) / 1024 / 1024).toFixed(2)} MB
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
                    {(Array.from(selectedSupportingFileIndexes).reduce((sum, index) => sum + Number(supportingFileAuditResults[supportingFileObjects[index]?.name]?.payloadBytes || 0), 0) / 1024 / 1024).toFixed(2)} MB
                  </div>
                  <div />
                </div>
              </div>
            )}

            {skippedArchiveMembers.length > 0 && (
              <details style={{ borderTop: supportingFileObjects.length ? '1px solid #34414f' : undefined }}>
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
          disabled={
            preScanRunning
            || !selectedWellId
            || (supportingFiles.length > 0 && supportingFileObjects.length === 0)
            || selectedSupportingFileIndexes.size === 0
          }
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
        <button type="button" onClick={publishApproved} disabled={!selectedWellId || summary.confirmed === 0}>Publish approved tops</button>
        <button type="button" onClick={saveReview} disabled={!selectedWellId}>Save review</button>
        <button type="button" onClick={exportCsv} disabled={!selectedWellId || candidates.length === 0}>Export CSV</button>
        <label
          className="wlv-ftm-tool__sort-control"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: '#dbe3eb', fontSize: '11px', fontWeight: 600 }}
        >
          <span>Sort by</span>
          <select
            defaultValue=""
            disabled={candidates.length < 2}
            aria-label="Sort Formation Tops"
            style={{
              height: '32px',
              minWidth: '96px',
              padding: '0 28px 0 10px',
              border: '1px solid #465466',
              borderRadius: '5px',
              background: '#18202a',
              color: '#dbe3eb',
              font: 'inherit',
              fontSize: '10px',
              fontWeight: 600,
              cursor: candidates.length < 2 ? 'not-allowed' : 'pointer',
              opacity: candidates.length < 2 ? 0.5 : 1,
            }}
            onChange={(event) => {
              const sortBy = event.currentTarget.value;
              if (sortBy === 'name' || sortBy === 'md') sortCandidates(sortBy);
              event.currentTarget.value = '';
            }}
          >
            <option value="" disabled>Select…</option>
            <option value="name">Name</option>
            <option value="md">MD</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => setCandidates((current) => [...current, emptyCandidate(selectedWell?.depth_unit || 'm')])}
          disabled={!selectedWellId}
        >
          Add row
        </button>
        <span className="wlv-metadata-tool__session-summary">
          {selectedWell ? `${selectedWell.display_name || selectedWell.well_name || selectedWell.well_id}` : 'No well selected'}
          {candidates.length ? ` · ${candidates.length} top(s)` : ''}
          {supportingFiles.length ? ` · ${supportingFiles.length} supporting file(s)` : ''}
          {summary.confirmed ? ` · ${summary.confirmed} approved` : ''}
        </span>
      </div>

      <div className="wlv-metadata-tool__message" role="status">
        <span>{error || status}</span>
        <span className="wlv-ftm-tool__counts">
          {summary.unreviewed} unreviewed · {summary.confirmed} approved · {summary.rejected} rejected
        </span>
      </div>

      <section className="wlv-metadata-tool__review">
        <header>
          <h2>Formation top candidates</h2>
          <div
            className="wlv-ftm-tool__bulk-selection"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px', marginLeft: 'auto', fontSize: '10px', fontWeight: 600 }}
          >
            <span>{candidates.length || 0}</span>
            <button type="button" onClick={selectAllCandidates} disabled={candidates.length === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Select All</button>
            <button type="button" onClick={clearCandidateSelection} disabled={selectedCandidateIds.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Select None</button>
            <button type="button" onClick={acceptSelectedCandidates} disabled={selectedCandidateIds.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Accept</button>
          </div>
        </header>

        <div className="wlv-metadata-tool__table-wrap wlv-ftm-tool__table-wrap">
          <table className="wlv-ftm-tool__table">
            <thead>
              <tr>
                <th>Marker</th>
                <th style={{ paddingRight: '4px' }}>Depth / classification</th>
                <th style={{ paddingLeft: '4px', paddingRight: '4px' }}>Confidence</th>
                <th style={{ paddingLeft: '4px' }}>Source</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {candidates.length === 0 ? (
                <tr>
                  <td colSpan={5} className="is-empty">
                    {selectedWellId ? 'Load supporting files or import an AI response.' : 'Select a managed well.'}
                  </td>
                </tr>
              ) : candidates.map((candidate) => {
                const editing = activeEditId === candidate.id;
                const populated = Boolean(candidate.marker || candidate.md || candidate.tvd || candidate.tvdss);
                const selectionControl = (
                  <label
                    style={{ display: 'inline-flex', alignItems: 'center', marginRight: '6px' }}
                    onClick={(event) => event.stopPropagation()}
                    title="Select candidate"
                  >
                    <input
                      type="checkbox"
                      checked={selectedCandidateIds.has(candidate.id)}
                      onChange={() => toggleCandidateSelection(candidate.id)}
                      aria-label={`Select ${candidate.marker || 'candidate'}`}
                      style={{ width: '13px', height: '13px', margin: 0 }}
                    />
                  </label>
                );
                return (
                  <tr key={candidate.id} className={`${populated ? 'is-populated' : ''} is-${candidate.state}`}>
                    <td
                      className="wlv-metadata-tool__editable-value"
                      onClick={() => {
                        if (!editing) setActiveEditId(candidate.id);
                      }}
                    >
                      {editing ? (
                        <div className="wlv-ftm-tool__edit-stack">
                          <input
                            autoFocus
                            value={candidate.marker}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) => updateCandidate(candidate.id, 'marker', event.target.value)}
                            aria-label="Formation or marker name"
                          />
                          <input
                            value={candidate.group}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) => updateCandidate(candidate.id, 'group', event.target.value)}
                            placeholder="Group"
                          />
                        </div>
                      ) : (
                        <>
                          <strong>{candidate.marker || 'Unnamed marker'}</strong>
                          <small>
                            {[candidate.group, candidate.markerType, candidate.pickStatus].filter(Boolean).join(' · ') || 'No classification'}
                          </small>
                        </>
                      )}
                    </td>

                    <td className="wlv-metadata-tool__editable-value" onClick={() => {
                      if (!editing) setActiveEditId(candidate.id);
                    }}>
                      {editing ? (
                        <div className="wlv-ftm-tool__depth-grid">
                          <label>MD<input value={candidate.md} onClick={(event) => event.stopPropagation()} onChange={(event) => updateCandidate(candidate.id, 'md', event.target.value)} /></label>
                          <label>TVD<input value={candidate.tvd} onClick={(event) => event.stopPropagation()} onChange={(event) => updateCandidate(candidate.id, 'tvd', event.target.value)} /></label>
                          <label>TVDSS<input value={candidate.tvdss} onClick={(event) => event.stopPropagation()} onChange={(event) => updateCandidate(candidate.id, 'tvdss', event.target.value)} /></label>
                          <label>Unit<input value={candidate.unit} onClick={(event) => event.stopPropagation()} onChange={(event) => updateCandidate(candidate.id, 'unit', event.target.value)} /></label>
                          <label>Reference<input value={candidate.depthReference} onClick={(event) => event.stopPropagation()} onChange={(event) => updateCandidate(candidate.id, 'depthReference', event.target.value)} /></label>
                        </div>
                      ) : (
                        <>
                          <span>
                            {candidate.md ? `MD ${candidate.md} ${candidate.unit}` : 'MD —'}
                            {candidate.tvd ? ` · TVD ${candidate.tvd}` : ''}
                            {candidate.tvdss ? ` · TVDSS ${candidate.tvdss}` : ''}
                          </span>
                          <small>{candidate.depthReference || 'No reference'}</small>
                        </>
                      )}
                    </td>

                    <td className="wlv-metadata-tool__editable-value wlv-ftm-tool__confidence" onClick={() => {
                      if (!editing) setActiveEditId(candidate.id);
                    }}>
                      {editing ? (
                        <select
                          value={normalizedConfidenceForCandidate(candidate)}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => updateCandidate(candidate.id, 'confidence', event.target.value)}
                          aria-label="Confidence"
                          disabled={!hasUsableMeasuredDepth(candidate)}
                          title={!hasUsableMeasuredDepth(candidate) ? 'Invalid until a usable measured depth (MD) is supplied.' : undefined}
                        >
                          <option value="">Select…</option>
                          <option value="high">High</option>
                          <option value="medium">Medium</option>
                          <option value="low">Low</option>
                          <option value="invalid">Invalid</option>
                        </select>
                      ) : (
                        <span className={`wlv-lcm-confidence is-${normalizedConfidenceForCandidate(candidate) || 'unset'}`}>
                          {normalizedConfidenceForCandidate(candidate) === 'high' ? 'High' : normalizedConfidenceForCandidate(candidate) === 'medium' ? 'Medium' : normalizedConfidenceForCandidate(candidate) === 'low' ? 'Low' : normalizedConfidenceForCandidate(candidate) === 'invalid' ? 'Invalid' : '—'}
                        </span>
                      )}
                    </td>

                    <td className="wlv-metadata-tool__editable-source" onClick={() => {
                      if (!editing) setActiveEditId(candidate.id);
                    }}>
                      {editing ? (
                        <div className="wlv-ftm-tool__edit-stack">
                          <input value={candidate.source} onClick={(event) => event.stopPropagation()} onChange={(event) => updateCandidate(candidate.id, 'source', event.target.value)} placeholder="Source" />
                          <input value={candidate.evidence} onClick={(event) => event.stopPropagation()} onChange={(event) => updateCandidate(candidate.id, 'evidence', event.target.value)} placeholder="Evidence / page" />
                          <input value={candidate.notes} onClick={(event) => event.stopPropagation()} onChange={(event) => updateCandidate(candidate.id, 'notes', event.target.value)} placeholder="Notes" />
                        </div>
                      ) : candidate.source ? (
                        <>
                          <span>{candidate.source}</span>
                          <small>{candidate.evidence || candidate.notes || 'No source reference'}</small>
                        </>
                      ) : (
                        <span className="is-missing">Not found</span>
                      )}
                    </td>

                    <td>
                      {editing ? (
                        <div className="wlv-metadata-tool__actions">
                          {selectionControl}
                          <button type="button" onClick={() => confirmCandidate(candidate.id)}>Accept</button>
                          <button type="button" onClick={() => rejectCandidate(candidate.id)}>Reject</button>
                          <button type="button" onClick={() => deleteCandidate(candidate.id)}>Delete</button>
                        </div>
                      ) : candidate.state === 'unreviewed' || candidate.state === 'conflict' ? (
                        <div className="wlv-metadata-tool__actions">
                          {selectionControl}
                          <button type="button" onClick={() => confirmCandidate(candidate.id)}>Accept</button>
                          <button type="button" onClick={() => rejectCandidate(candidate.id)}>Reject</button>
                          <button type="button" onClick={() => deleteCandidate(candidate.id)}>Delete</button>
                        </div>
                      ) : populated ? (
                        <div className="wlv-metadata-tool__actions">
                          <span className="wlv-metadata-tool__loaded">
                            {candidate.state === 'existing' ? 'Loaded' : candidate.state === 'rejected' ? 'Rejected' : 'Accepted'}
                          </span>
                          <button type="button" onClick={() => deleteCandidate(candidate.id)}>Delete</button>
                        </div>
                      ) : (
                        <div className="wlv-metadata-tool__actions">
                          <span className="is-missing">—</span>
                          <button type="button" onClick={() => deleteCandidate(candidate.id)}>Delete</button>
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
    </section>
  );

}

export default FormationTopsManagerPage;
