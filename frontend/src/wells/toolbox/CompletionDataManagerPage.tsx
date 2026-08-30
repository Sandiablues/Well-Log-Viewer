import { useEffect, useMemo, useRef, useState } from 'react';
import * as XLSX from 'xlsx';
import { fetchWlvJson, wlvApiBaseUrl } from '../../api/wlvBackendClient';
import { toolboxAiExpectedResponseRevision, toolboxAiPackageFilename, useToolboxAiRevision } from './toolboxAiRevision';
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
  type SupportingFilePayload,
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
  product_groups?: Array<{
    items?: Array<{
      product_subgroup_key?: string | null;
      provenance?: { completion_components?: Array<Record<string, unknown>> } | null;
    }>;
  }>;
};

type ReviewState = 'unreviewed' | 'confirmed' | 'edited' | 'rejected' | 'existing';

type KrCompletionAuthority = {
  instructionId: string;
  recordType: 'component' | 'standard';
  componentKey: string;
  componentLabel: string;
  canonicalId: string;
  version: string;
  status: string;
  productionEligible: boolean;
  geometryClass?: 'interval' | 'point_or_short_interval' | 'point_or_interval' | 'point_or_interval_association' | string;
};

type KrCompletionCatalogue = {
  catalogueVersion: number;
  records: KrCompletionAuthority[];
};

type Candidate = {
  id: string;
  state: ReviewState;
  componentType: string;
  canonicalId: string;
  krInstructionId: string;
  krVersion: string;
  label: string;
  topMd: string;
  baseMd: string;
  unit: string;
  diameter: string;
  status: string;
  source: string;
  evidence: string;
  confidence: string;
  notes: string;
  original: Omit<Candidate, 'original'> | null;
};

type PersistedSession = { selectedWellId: string; candidates: Candidate[]; supportingFiles: SupportingFile[]; savedAt: string };

const STORAGE_PREFIX = 'wlv.cdm.review.v1.';
const ACTIVE_KEY = 'wlv.cdm.activeSession.v1';

const normalize = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim();
const normalizeKey = (value: unknown) => normalize(value).toLowerCase().replace(/[^a-z0-9]+/g, '');
const idFor = (seed: string) => `${Date.now()}-${Math.random().toString(36).slice(2)}-${seed}`;
const numberOrNull = (value: string) => normalize(value) === '' ? null : Number(value);

function clone(candidate: Candidate): Omit<Candidate, 'original'> {
  const { original: _original, ...rest } = candidate;
  return { ...rest };
}


function candidateIdentity(candidate: Candidate): string {
  return [
    candidate.componentType,
    normalizeKey(candidate.label),
    normalize(candidate.topMd),
    normalize(candidate.baseMd),
    normalizeKey(candidate.source),
  ].join('|');
}

function mergeCandidates(current: Candidate[], incoming: Candidate[]): Candidate[] {
  const byIdentity = new Map<string, Candidate>();

  for (const candidate of current) {
    const identity = candidateIdentity(candidate);
    if (!byIdentity.has(identity)) byIdentity.set(identity, candidate);
  }

  for (const candidate of incoming) {
    const identity = candidateIdentity(candidate);
    const existing = byIdentity.get(identity);
    if (!existing) {
      byIdentity.set(identity, candidate);
      continue;
    }
    byIdentity.set(identity, {
      ...candidate,
      id: existing.id,
      state: existing.state,
      original: existing.original ?? candidate.original,
    });
  }

  return Array.from(byIdentity.values());
}

function emptyCandidate(unit = 'm'): Candidate {
  const candidate: Candidate = {
    id: idFor('manual'),
    state: 'unreviewed',
    componentType: '',
    canonicalId: '',
    krInstructionId: '',
    krVersion: '',
    label: '',
    topMd: '',
    baseMd: '',
    unit,
    diameter: '',
    status: '',
    source: 'Manual entry',
    evidence: '',
    confidence: '',
    notes: '',
    original: null,
  };
  candidate.original = clone(candidate);
  return candidate;
}

function valueFrom(row: Record<string, unknown>, ...names: string[]): string {
  for (const name of names) {
    if (normalize(row[name])) return normalize(row[name]);
    const found = Object.keys(row).find((key) => normalizeKey(key) === normalizeKey(name));
    if (found && normalize(row[found])) return normalize(row[found]);
  }
  return '';
}

function normalizedType(value: unknown, label: unknown): string {
  const text = `${normalize(value)} ${normalize(label)}`.toLowerCase();
  if (/safety.?valve|sssv|scssv|dhsv/.test(text)) return 'safety_valve';
  if (/sliding.?sleeve|ssd|sliding.?side.?door/.test(text)) return 'sliding_sleeve';
  if (/gas.?lift/.test(text)) return 'gas_lift';
  if (/\baicd\b|\bicd\b|inflow.?control/.test(text)) return 'icd_aicd';
  if (/bridge.?plug/.test(text)) return 'bridge_plug';
  if (/retainer|ezsv/.test(text)) return 'retainer';
  if (/cement/.test(text) && /barrier|plug|squeeze/.test(text)) return 'cement_barrier';
  if (/packer/.test(text)) return 'packer';
  if (/perf/.test(text)) return 'perforations';
  if (/open.?hole|barefoot/.test(text)) return 'open_hole';
  if (/screen/.test(text)) return 'screen';
  if (/liner/.test(text)) return 'liner';
  if (/casing/.test(text)) return 'casing';
  if (/tubing|string/.test(text)) return 'tubing';
  if (/valve/.test(text)) return 'downhole_valve';
  return '';
}

const CDM_EXCLUDED_CONSTRUCTION_KEYS = new Set(['casing', 'liner', 'open_hole']);
const CDM_EXCLUDED_CONSTRUCTION_CANONICAL_IDS = new Set([
  'completion.casing',
  'completion.liner',
  'completion.open_hole',
]);

function isCdmCompletionCandidate(candidate: Candidate): boolean {
  const inferred = normalizedType(candidate.componentType, candidate.label);
  if (CDM_EXCLUDED_CONSTRUCTION_KEYS.has(inferred || candidate.componentType)) return false;
  if (CDM_EXCLUDED_CONSTRUCTION_CANONICAL_IDS.has(candidate.canonicalId)) return false;
  return true;
}

function authorityFor(
  componentKey: string,
  canonicalId: string,
  authorities: KrCompletionAuthority[],
): KrCompletionAuthority | null {
  return authorities.find((item) => item.canonicalId === canonicalId)
    ?? authorities.find((item) => item.componentKey === componentKey)
    ?? null;
}

function fromRecord(
  row: Record<string, unknown>,
  index: number,
  source: string,
  unit: string,
  authorities: KrCompletionAuthority[],
): Candidate {
  const label = valueFrom(row, 'Label', 'Component', 'Description', 'Name', 'label');
  const sourceType = valueFrom(
    row,
    'Canonical Component Key',
    'componentKey',
    'canonical_component_key',
    'Component Type',
    'Type',
    'component_type',
  );
  const explicitCanonical = valueFrom(row, 'Canonical ID', 'canonicalId', 'canonical_id');
  const key = normalizedType(sourceType, label);
  const authority = authorityFor(key, explicitCanonical, authorities);
  const candidate: Candidate = {
    id: idFor(`${source}-${index}`),
    state: 'unreviewed',
    componentType: authority?.componentKey ?? key,
    canonicalId: authority?.canonicalId ?? explicitCanonical,
    krInstructionId: authority?.instructionId ?? valueFrom(row, 'KR Instruction ID', 'kr_instruction_id'),
    krVersion: authority?.version ?? valueFrom(row, 'KR Version', 'kr_version'),
    label,
    topMd: valueFrom(row, 'Top MD', 'MD', 'Depth', 'From MD', 'Start MD', 'top_md'),
    baseMd: valueFrom(row, 'Base MD', 'To MD', 'End MD', 'base_md'),
    unit: valueFrom(row, 'Unit', 'Depth Unit', 'depth_unit') || unit || 'm',
    diameter: valueFrom(row, 'Diameter', 'OD', 'Size', 'diameter'),
    status: valueFrom(row, 'Status', 'state'),
    source: valueFrom(row, 'Source', 'Source Document', 'source_document') || source,
    evidence: valueFrom(row, 'Evidence', 'Source Reference', 'Page', 'source_reference'),
    confidence: valueFrom(row, 'Confidence', 'confidence'),
    notes: valueFrom(row, 'Notes', 'notes'),
    original: null,
  };
  candidate.original = clone(candidate);
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

export function CompletionDataManagerPage({ onBack }: { onBack: () => void }) {
  const activeRef = useRef<PersistedSession | null>(readActive());
  const [wells, setWells] = useState<ManagedWellRecord[]>([]);
  const [krComponents, setKrComponents] = useState<KrCompletionAuthority[]>([]);
  const [krCatalogueVersion, setKrCatalogueVersion] = useState(0);
  const [loadingKr, setLoadingKr] = useState(true);
  const [selectedWellId, setSelectedWellId] = useState(activeRef.current?.selectedWellId ?? '');
  const [wellSearch, setWellSearch] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>(
    mergeCandidates([], (activeRef.current?.candidates ?? []).filter(isCdmCompletionCandidate)),
  );
  const [supportingFiles, setSupportingFiles] = useState<SupportingFile[]>(activeRef.current?.supportingFiles ?? []);
  const [fileObjects, setFileObjects] = useState<File[]>([]);
  const [selectedSupportingFileIndexes, setSelectedSupportingFileIndexes] = useState<Set<number>>(() => new Set());
  const [deterministicSupportingFileIndexes, setDeterministicSupportingFileIndexes] = useState<Set<number>>(() => new Set());
  const [skippedArchiveMembers, setSkippedArchiveMembers] = useState<SkippedArchiveMember[]>([]);
  const [loadingWells, setLoadingWells] = useState(true);
  const [status, setStatus] = useState('Select a managed well to begin.');
  const [supportingFileAuditResults, setSupportingFileAuditResults] = useState<Record<string, SupportingFileAuditResult>>({});
  const [supportingFilePreScanResults, setSupportingFilePreScanResults] = useState<Record<number, SupportingFilePreScanResult>>({});
  const [activeSupportingFileAudit, setActiveSupportingFileAudit] = useState<SupportingFileAuditResult | null>(null);
  const [preScanRunning, setPreScanRunning] = useState(false);
  const [supportingManifestCollapsed, setSupportingManifestCollapsed] = useState(false);
  const [graphicsChoiceFiles, setGraphicsChoiceFiles] = useState<string[] | null>(null);
  const graphicsChoiceResolverRef = useRef<((choice: GraphicsExportChoice) => void) | null>(null);
  const [deterministicFailurePrompt, setDeterministicFailurePrompt] = useState<DeterministicFailurePrompt | null>(null);
  const [rememberDeterministicFailureChoice, setRememberDeterministicFailureChoice] = useState(false);
  const deterministicFailureResolverRef = useRef<((decision: DeterministicFailureDecision) => void) | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeEditId, setActiveEditId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const fileRef = useRef<HTMLInputElement | null>(null);
  const aiRef = useRef<HTMLInputElement | null>(null);

  const selectedWell = useMemo(
    () => wells.find((well) => well.managed_well_id === selectedWellId) ?? null,
    [selectedWellId, wells],
  );
  const aiRevision = useToolboxAiRevision('CDM', selectedWellId, candidates.map((candidate) => candidate.id));


  const krByKey = useMemo(
    () => new Map(krComponents.map((item) => [item.componentKey, item])),
    [krComponents],
  );
  const isIntervalType = (componentKey: string) => krByKey.get(componentKey)?.geometryClass === 'interval';
  const componentLabel = (componentKey: string) => krByKey.get(componentKey)?.componentLabel || (componentKey ? `Unresolved: ${componentKey}` : 'Select KR component…');

  const bindAuthority = (candidate: Candidate): Candidate => {
    const inferredKey = normalizedType(candidate.componentType, candidate.label);
    const authority = authorityFor(
      inferredKey || candidate.componentType,
      candidate.canonicalId,
      krComponents,
    );
    if (!authority) {
      return {
        ...candidate,
        componentType: inferredKey || candidate.componentType,
      };
    }
    return {
      ...candidate,
      componentType: authority.componentKey,
      canonicalId: authority.canonicalId,
      krInstructionId: authority.instructionId,
      krVersion: authority.version,
    };
  };

  const filteredWells = useMemo(() => {
    const query = wellSearch.trim().toLowerCase();
    if (!query) return wells;
    return wells.filter((well) =>
      [well.display_name, well.well_name, well.well_id, well.wellbore_name, well.uwi]
        .some((value) => String(value ?? '').toLowerCase().includes(query)),
    );
  }, [wellSearch, wells]);

  const summary = useMemo(() => ({
    total: candidates.length,
    approved: candidates.filter((candidate) => candidate.state === 'confirmed' || candidate.state === 'edited').length,
    rejected: candidates.filter((candidate) => candidate.state === 'rejected').length,
    unreviewed: candidates.filter((candidate) => candidate.state === 'unreviewed').length,
  }), [candidates]);

  useEffect(() => {
    let cancelled = false;
    fetchWlvJson<KrCompletionCatalogue>('/api/wlv/knowledge/managed/completions/production-eligible')
      .then((catalogue) => {
        if (cancelled) return;
        const components = (catalogue.records ?? []).filter(
          (record) =>
            record.recordType === 'component'
            && record.productionEligible
            && !CDM_EXCLUDED_CONSTRUCTION_KEYS.has(record.componentKey)
            && !CDM_EXCLUDED_CONSTRUCTION_CANONICAL_IDS.has(record.canonicalId),
        );
        setKrComponents(components);
        setKrCatalogueVersion(catalogue.catalogueVersion || 0);
      })
      .catch((caught) => !cancelled && setError(caught instanceof Error ? caught.message : 'Unable to load KR completion authority'))
      .finally(() => !cancelled && setLoadingKr(false));
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchWlvJson<ManagedWellRecord[]>('/api/wlv/inventory/wells')
      .then((records) => {
        if (cancelled) return;
        setWells(records);
        setStatus(records.length ? 'Select a managed well to begin.' : 'No managed wells are available.');
      })
      .catch((caught) => !cancelled && setError(caught instanceof Error ? caught.message : 'Unable to load managed wells'))
      .finally(() => !cancelled && setLoadingWells(false));
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (loadingWells || loadingKr) return;
    if (!selectedWellId) {
      setCandidates([]);
      setSupportingFiles([]);
      setFileObjects([]);
      setSelectedSupportingFileIndexes(new Set());
      setDeterministicSupportingFileIndexes(new Set());
      setSkippedArchiveMembers([]);
      return;
    }
    const active = activeRef.current;
    if (active?.selectedWellId === selectedWellId) {
      setCandidates(mergeCandidates([], (active.candidates ?? []).map((candidate) => {
        const migrated = bindAuthority(candidate);
        return {
          ...migrated,
          original: migrated.original ? bindAuthority(migrated.original as Candidate) : migrated.original,
        };
      }).filter(isCdmCompletionCandidate)));
      setSupportingFiles(active.supportingFiles ?? []);
      setFileObjects([]);
      setSelectedSupportingFileIndexes(new Set());
      setDeterministicSupportingFileIndexes(new Set());
      setSkippedArchiveMembers([]);
      activeRef.current = null;
      setStatus('Restored active Completion Data Manager session.');
      return;
    }
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${selectedWellId}`);
    if (raw) {
      try {
        const persisted = JSON.parse(raw) as PersistedSession;
        setCandidates(mergeCandidates([], (persisted.candidates ?? []).map((candidate) => {
          const migrated = bindAuthority(candidate);
          return {
            ...migrated,
            original: migrated.original ? bindAuthority(migrated.original as Candidate) : migrated.original,
          };
        }).filter(isCdmCompletionCandidate)));
        setSupportingFiles(persisted.supportingFiles ?? []);
        setFileObjects([]);
        setSelectedSupportingFileIndexes(new Set());
        setDeterministicSupportingFileIndexes(new Set());
        setSkippedArchiveMembers([]);
        setStatus('Restored saved completion review.');
        return;
      } catch {
        localStorage.removeItem(`${STORAGE_PREFIX}${selectedWellId}`);
      }
    }
    const existing: Candidate[] = [];
    for (const group of selectedWell?.product_groups ?? []) {
      for (const item of group.items ?? []) {
        if (item.product_subgroup_key !== 'completion_components') continue;
        for (const [index, row] of (item.provenance?.completion_components ?? []).entries()) {
          const candidate = fromRecord(row, index, 'Existing Completion Components dataset', selectedWell?.depth_unit || 'm', krComponents);
          candidate.state = 'existing';
          existing.push(candidate);
        }
      }
    }
    setCandidates(mergeCandidates([], existing));
    setSupportingFiles([]);
    setFileObjects([]);
    setSelectedSupportingFileIndexes(new Set());
    setDeterministicSupportingFileIndexes(new Set());
    setSkippedArchiveMembers([]);
    setStatus(`Loaded ${existing.length} existing completion component(s).`);
  }, [selectedWellId, selectedWell, loadingWells, loadingKr, krComponents]);

  useEffect(() => {
    if (!selectedWellId) {
      sessionStorage.removeItem(ACTIVE_KEY);
      return;
    }
    const persisted: PersistedSession = {
      selectedWellId,
      candidates,
      supportingFiles,
      savedAt: new Date().toISOString(),
    };
    const serialized = JSON.stringify(persisted);
    sessionStorage.setItem(ACTIVE_KEY, serialized);
    localStorage.setItem(`${STORAGE_PREFIX}${selectedWellId}`, serialized);
  }, [selectedWellId, candidates, supportingFiles]);

  const saveReview = () => {
    if (!selectedWellId) return;
    localStorage.setItem(`${STORAGE_PREFIX}${selectedWellId}`, JSON.stringify({
      selectedWellId, candidates, supportingFiles, savedAt: new Date().toISOString(),
    }));
    setStatus('Completion review saved.');
    setError(null);
  };

  const importRows = async (file: File): Promise<Candidate[]> => {
    const ext = file.name.split('.').pop()?.toLowerCase();
    let rows: Record<string, unknown>[] = [];
    if (ext === 'json') {
      const parsed = JSON.parse(await file.text()) as unknown;
      const raw = Array.isArray(parsed)
        ? parsed
        : parsed && typeof parsed === 'object' && Array.isArray((parsed as { candidates?: unknown[] }).candidates)
          ? (parsed as { candidates: unknown[] }).candidates
          : [];
      rows = raw.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object');
    } else if (['csv', 'xlsx', 'xls'].includes(ext || '')) {
      const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' });
      rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(workbook.Sheets[workbook.SheetNames[0]], { defval: '' });
    }
    return rows
      .map((row, index) => fromRecord(row, index, file.name, selectedWell?.depth_unit || 'm', krComponents))
      .filter(isCdmCompletionCandidate);
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
    if (activeSupportingFileAudit && indexes.some((index) => fileObjects[index]?.name === activeSupportingFileAudit.fileName)) {
      setActiveSupportingFileAudit(null);
    }
  };

  const toggleAllDeterministicSupportingFiles = () => {
    const selectedIndexes = Array.from(selectedSupportingFileIndexes);
    const allSelectedAreScreened = selectedIndexes.length > 0
      && selectedIndexes.every((index) => deterministicSupportingFileIndexes.has(index));

    invalidatePreScanForIndexes(selectedIndexes);

    if (allSelectedAreScreened) {
      setDeterministicSupportingFileIndexes(new Set());
      return;
    }

    setDeterministicSupportingFileIndexes(new Set(selectedIndexes));
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
      setError('Select a managed well first.');
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
      } catch (archiveError) {
        setError(archiveError instanceof Error ? archiveError.message : `Could not expand ${file.name}.`);
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
    setSupportingFileAuditResults({});
    setSupportingFilePreScanResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    setFileObjects((current) => [...current, ...incoming]);
    setSupportingFiles((current) => [...current, ...incoming.map((file) => ({ name: file.name, type: file.type, size: file.size }))]);
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

    const imported: Candidate[] = [];
    for (const file of incoming) {
      if (!['json', 'csv', 'xlsx', 'xls'].includes(file.name.split('.').pop()?.toLowerCase() || '')) continue;
      try { imported.push(...await importRows(file)); } catch { /* supporting source remains attached */ }
    }

    const zipCount = rawIncoming.filter((file) => file.name.toLowerCase().endsWith('.zip')).length;
    const skipSuffix = newlySkippedArchiveMembers.length
      ? ` ${newlySkippedArchiveMembers.length} unsupported/nested archive member(s) were reported and skipped.`
      : '';
    if (imported.length) {
      setCandidates((current) => mergeCandidates(current, imported));
      setStatus(
        `Attached ${incoming.length} supporting file(s)${zipCount ? ` from ${zipCount} ZIP archive(s)` : ''} `
        + `and reconciled ${imported.length} imported completion candidate(s).${skipSuffix}`,
      );
    } else {
      setStatus(
        `Attached ${incoming.length} supporting file(s)${zipCount ? ` from ${zipCount} ZIP archive(s)` : ''}.${skipSuffix}`,
      );
    }
  };

  const clearSupportingFiles = () => {
    setSupportingFiles([]);
    setFileObjects([]);
    setSelectedSupportingFileIndexes(new Set());
    setDeterministicSupportingFileIndexes(new Set());
    setSkippedArchiveMembers([]);
    setSupportingFileAuditResults({});
    setSupportingFilePreScanResults({});
    setActiveSupportingFileAudit(null);
    if (fileRef.current) fileRef.current.value = '';
    setStatus('Supporting files cleared. Completion candidates and review state were preserved.');
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

  const requestDeterministicFailureChoice = (fileName: string, detail: string): Promise<DeterministicFailureDecision> => new Promise((resolve) => {
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
      setError('Select a managed well first.');
      return;
    }

    if (supportingFiles.length > 0 && fileObjects.length === 0) {
      setError(
        'Supporting file references were restored from the saved CDM session, but the browser no longer has the actual file binary. '
        + 'Reload the supporting file(s) with Browse before running the document pre-scan.',
      );
      setStatus('Supporting file reload required before document pre-scan.');
      return;
    }

    if (supportingFiles.length !== fileObjects.length) {
      setError(
        `Supporting file state is inconsistent: ${supportingFiles.length} remembered file reference(s) but ${fileObjects.length} live file payload(s). `
        + 'Clear and reload the supporting files before running the document pre-scan.',
      );
      setStatus('Supporting file state mismatch · pre-scan blocked.');
      return;
    }

    const selectedIndexes = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b);
    if (!selectedIndexes.length) {
      setError('Select at least one supporting file before running the document pre-scan.');
      setStatus('Document pre-scan blocked · no supporting files selected.');
      return;
    }

    setPreScanRunning(true);
    setError(null);

    try {
      const managedAiRules = await fetchToolboxAiRules('CDM');
      const deterministicProfile = (
        managedAiRules.rules.deterministic_screening
        && typeof managedAiRules.rules.deterministic_screening === 'object'
        && !Array.isArray(managedAiRules.rules.deterministic_screening)
      ) ? managedAiRules.rules.deterministic_screening as Record<string, unknown> : {};
      const deterministicProfileSignature = JSON.stringify(deterministicProfile);

      const nextResults = { ...supportingFilePreScanResults };
      const nextAudit = { ...supportingFileAuditResults };
      let rememberedFailureChoice: DeterministicFailureChoice | null = null;
      const highGraphicsEntries: Array<{ index: number; file: SupportingFilePayload; summary: EvidencePreparationSummary }> = [];

      for (let position = 0; position < selectedIndexes.length; position += 1) {
        const sourceIndex = selectedIndexes[position];
        const file = await filePayload(fileObjects[sourceIndex]);
        const deterministicRequested = deterministicSupportingFileIndexes.has(sourceIndex);

        setStatus(`Document pre-scan ${position + 1}/${selectedIndexes.length}: ${file.name}`);

        if (!deterministicRequested) {
          const preparedEvidence: PreparedEvidenceFile = {
            name: file.name,
            mime_type: file.type || 'application/octet-stream',
            size: file.size,
            content_base64: file.content_base64,
            preprocessed_from_pdf: false,
            deterministic_screening: false,
            selected_pdf_pages_preserved: file.type === 'application/pdf',
          };
          const evidencePreparation: EvidencePreparationSummary = {
            name: file.name,
            mode: 'full_original_operator_selected',
            original_size: file.size,
            prepared_size: file.size,
          };
          nextResults[sourceIndex] = {
            sourceIndex,
            sourceName: file.name,
            sourceSha256: file.sha256,
            deterministicRequested: false,
            standardVersion: managedAiRules.active_version,
            deterministicProfileSignature,
            preparedEvidence,
            evidencePreparation,
            estimatedEvidenceTokens: 0,
          };
          nextAudit[file.name] = {
            fileName: file.name,
            requestedMode: 'full_original',
            completionStatus: 'full_original',
            payloadBytes: file.size,
            selectedPageCount: 0,
            totalPages: null,
            reason: 'Included as full original by operator selection during document pre-scan.',
          };
          continue;
        }

        const prepareResponse = await fetch(`${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/prepare`, {
          method: 'POST',
          headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
          body: JSON.stringify({
            candidate_package: {
              deterministic_screening_enabled: true,
              deterministic_screening_profile: deterministicProfile,
            },
            evidence_files: [{
              name: file.name,
              mime_type: file.type || 'application/octet-stream',
              size: file.size,
              content_base64: file.content_base64,
            }],
          }),
        });

        if (!prepareResponse.ok) {
          let failureDetail = `Deterministic pre-screen returned ${prepareResponse.status}`;
          try {
            const failureBody = await prepareResponse.json() as { detail?: unknown };
            if (failureBody?.detail) failureDetail = String(failureBody.detail);
          } catch {
            const failureText = await prepareResponse.text().catch(() => '');
            if (failureText) failureDetail = failureText;
          }

          const rememberedChoiceIsUsable = rememberedFailureChoice !== 'bypass_scoring' || /minimum direct score/i.test(failureDetail);
          const decision: DeterministicFailureDecision = rememberedFailureChoice && rememberedChoiceIsUsable
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
              reason: `${failureDetail} Full-original fallback was not authorized; this document must be deselected or resolved before export.`,
            };
            continue;
          }

          if (decision.choice === 'bypass_scoring') {
            const bypassResponse = await fetch(`${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/prepare`, {
              method: 'POST',
              headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
              body: JSON.stringify({
                candidate_package: {
                  deterministic_screening_enabled: true,
                  deterministic_screening_profile: {
                    ...deterministicProfile,
                    bypass_min_direct_score: true,
                  },
                },
                evidence_files: [{
                  name: file.name,
                  mime_type: file.type || 'application/octet-stream',
                  size: file.size,
                  content_base64: file.content_base64,
                }],
              }),
            });

            if (!bypassResponse.ok) {
              let bypassDetail = `Deterministic score bypass returned ${bypassResponse.status}`;
              try {
                const bypassBody = await bypassResponse.json() as { detail?: unknown };
                if (bypassBody?.detail) bypassDetail = String(bypassBody.detail);
              } catch {
                const bypassText = await bypassResponse.text().catch(() => '');
                if (bypassText) bypassDetail = bypassText;
              }
              delete nextResults[sourceIndex];
              nextAudit[file.name] = {
                fileName: file.name,
                requestedMode: 'deterministic',
                completionStatus: 'pending',
                payloadBytes: 0,
                selectedPageCount: 0,
                totalPages: null,
                reason: `${failureDetail} Operator selected Bypass scoring, but the bypass retry also failed: ${bypassDetail}`,
              };
              continue;
            }

            const bypassPrepared = await bypassResponse.json() as EvidencePreparationResponse;
            if (!Array.isArray(bypassPrepared.prepared_evidence) || bypassPrepared.prepared_evidence.length !== 1) {
              throw new Error(`Deterministic score bypass did not return one prepared evidence payload for ${file.name}.`);
            }

            const preparedEvidence = bypassPrepared.prepared_evidence[0];
            const evidencePreparation = Array.isArray(bypassPrepared.evidence_preparation)
              ? (bypassPrepared.evidence_preparation.find((entry) => entry.name === file.name) ?? bypassPrepared.evidence_preparation[0] ?? null)
              : null;

            nextResults[sourceIndex] = {
              sourceIndex,
              sourceName: file.name,
              sourceSha256: file.sha256,
              deterministicRequested: true,
              standardVersion: managedAiRules.active_version,
              deterministicProfileSignature,
              preparedEvidence,
              evidencePreparation,
              estimatedEvidenceTokens: Number(bypassPrepared.estimated_evidence_tokens || 0),
            };

            const selectedPageCount = Number(evidencePreparation?.selected_page_count || preparedEvidence.source_pages?.length || 0);
            const totalPagesValue = Number(evidencePreparation?.total_pages);
            const totalPages = Number.isFinite(totalPagesValue) && totalPagesValue > 0 ? totalPagesValue : null;
            const payloadBytes = Math.max(0, Math.floor((String(preparedEvidence.content_base64 || '').length * 3) / 4));

            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'screened',
              payloadBytes,
              selectedPageCount,
              totalPages,
              reason: `Minimum direct-score gate bypassed by operator after: ${failureDetail}`,
            };
            continue;
          }

          const preparedEvidence: PreparedEvidenceFile = {
            name: file.name,
            mime_type: file.type || 'application/octet-stream',
            size: file.size,
            content_base64: file.content_base64,
            preprocessed_from_pdf: false,
            deterministic_screening: false,
            selected_pdf_pages_preserved: file.type === 'application/pdf',
          };
          const evidencePreparation: EvidencePreparationSummary = {
            name: file.name,
            mode: 'full_original_fallback_after_deterministic_failure',
            original_size: file.size,
            prepared_size: file.size,
            graphics_audit: {
              risk_level: 'high',
              requires_visual_review: true,
              recommendation: failureDetail,
            },
          };
          nextResults[sourceIndex] = {
            sourceIndex,
            sourceName: file.name,
            sourceSha256: file.sha256,
            deterministicRequested: true,
            standardVersion: managedAiRules.active_version,
            deterministicProfileSignature,
            preparedEvidence,
            evidencePreparation,
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

        const prepared = await prepareResponse.json() as EvidencePreparationResponse;
        if (!Array.isArray(prepared.prepared_evidence) || prepared.prepared_evidence.length !== 1) {
          throw new Error(`Deterministic pre-screen did not return one prepared evidence payload for ${file.name}.`);
        }

        const preparedEvidence = prepared.prepared_evidence[0];
        const evidencePreparation = Array.isArray(prepared.evidence_preparation)
          ? (prepared.evidence_preparation.find((entry) => entry.name === file.name) ?? prepared.evidence_preparation[0] ?? null)
          : null;

        nextResults[sourceIndex] = {
          sourceIndex,
          sourceName: file.name,
          sourceSha256: file.sha256,
          deterministicRequested: true,
          standardVersion: managedAiRules.active_version,
          deterministicProfileSignature,
          preparedEvidence,
          evidencePreparation,
          estimatedEvidenceTokens: Number(prepared.estimated_evidence_tokens || 0),
        };

        const selectedPageCount = Number(evidencePreparation?.selected_page_count || preparedEvidence.source_pages?.length || 0);
        const totalPagesValue = Number(evidencePreparation?.total_pages);
        const totalPages = Number.isFinite(totalPagesValue) && totalPagesValue > 0 ? totalPagesValue : null;
        const recommendation = String(evidencePreparation?.graphics_audit?.recommendation || '');
        const payloadBytes = Math.max(0, Math.floor((String(preparedEvidence.content_base64 || '').length * 3) / 4));

        nextAudit[file.name] = {
          fileName: file.name,
          requestedMode: 'deterministic',
          completionStatus: 'screened',
          payloadBytes,
          selectedPageCount,
          totalPages,
          reason: recommendation || 'Deterministic screening completed successfully.',
        };

        if (String(evidencePreparation?.graphics_audit?.risk_level || '') === 'high' && evidencePreparation) {
          highGraphicsEntries.push({ index: sourceIndex, file, summary: evidencePreparation });
        }
      }

      if (highGraphicsEntries.length) {
        const graphicsChoice = await requestGraphicsExportChoice(highGraphicsEntries.map((entry) => entry.file.name));
        if (graphicsChoice === 'full_original') {
          highGraphicsEntries.forEach(({ index, file, summary }) => {
            const preparedEvidence: PreparedEvidenceFile = {
              name: file.name,
              mime_type: file.type || 'application/octet-stream',
              size: file.size,
              content_base64: file.content_base64,
              preprocessed_from_pdf: false,
              deterministic_screening: false,
              selected_pdf_pages_preserved: file.type === 'application/pdf',
            };
            const evidencePreparation: EvidencePreparationSummary = {
              ...summary,
              mode: 'full_original_fallback_after_graphics_warning',
              prepared_size: file.size,
            };
            nextResults[index] = {
              ...nextResults[index],
              preparedEvidence,
              evidencePreparation,
            };
            nextAudit[file.name] = {
              ...nextAudit[file.name],
              completionStatus: 'full_scan_graphics',
              payloadBytes: file.size,
              reason: String(summary.graphics_audit?.recommendation || 'High graphics risk was acknowledged; full original document was used.'),
            };
          });
        } else if (graphicsChoice === 'cancel') {
          highGraphicsEntries.forEach(({ index, file, summary }) => {
            delete nextResults[index];
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'pending',
              payloadBytes: 0,
              selectedPageCount: Number(summary.selected_page_count || 0),
              totalPages: Number(summary.total_pages || 0) || null,
              reason: 'High graphics-risk result was not accepted. Deselect this document or run pre-scan again and resolve it before export.',
            };
          });
        }
      }

      setSupportingFilePreScanResults(nextResults);
      setSupportingFileAuditResults(nextAudit);

      const resolvedCount = selectedIndexes.filter((index) => Boolean(nextResults[index])).length;
      const unresolvedCount = selectedIndexes.length - resolvedCount;
      const screenedCount = selectedIndexes.filter((index) => nextAudit[fileObjects[index]?.name]?.completionStatus === 'screened').length;
      const fallbackCount = selectedIndexes.filter((index) => {
        const status = nextAudit[fileObjects[index]?.name]?.completionStatus;
        return status === 'full_scan_fallback' || status === 'full_scan_graphics';
      }).length;

      setStatus(
        `Document pre-scan complete · ${resolvedCount}/${selectedIndexes.length} selected document(s) resolved`
        + ` · ${screenedCount} screened`
        + (fallbackCount ? ` · ${fallbackCount} full-scan fallback(s)` : '')
        + (unresolvedCount ? ` · ${unresolvedCount} unresolved; deselect or resolve before export.` : '.')
      );
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to complete document pre-scan');
      setStatus('Document pre-scan did not complete.');
    } finally {
      setPreScanRunning(false);
    }
  };

  const exportAiPackage = async () => {
    if (!selectedWell) {
      setError('Select a managed well first.');
      return;
    }

    try {
      setError(null);

      if (supportingFiles.length > 0 && fileObjects.length === 0) {
        setError(
          'Supporting file references were restored from the saved CDM session, but the browser no longer has the actual file binary. '
          + 'Reload the supporting file(s) with Browse before exporting an AI package.',
        );
        setStatus('Supporting file reload required before AI export.');
        return;
      }

      if (supportingFiles.length !== fileObjects.length) {
        setError(
          `Supporting file state is inconsistent: ${supportingFiles.length} remembered file reference(s) but ${fileObjects.length} live file payload(s). `
          + 'Clear and reload the supporting files before exporting.',
        );
        setStatus('Supporting file state mismatch · export blocked.');
        return;
      }

      const selectedIndexes = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b);
      if (!selectedIndexes.length) {
        setError('Select at least one supporting file before exporting an AI package.');
        setStatus('AI export blocked · no supporting files selected.');
        return;
      }

      const managedAiRules = await fetchToolboxAiRules('CDM');
      const combinedRules = { ...managedAiRules.rules } as Record<string, unknown>;
      const deterministicProfile = (
        combinedRules.deterministic_screening
        && typeof combinedRules.deterministic_screening === 'object'
        && !Array.isArray(combinedRules.deterministic_screening)
      ) ? combinedRules.deterministic_screening as Record<string, unknown> : {};
      const deterministicProfileSignature = JSON.stringify(deterministicProfile);
      delete combinedRules.deterministic_screening;

      const selectedEvidence = await Promise.all(selectedIndexes.map(async (index) => ({
        sourceIndex: index,
        payload: await filePayload(fileObjects[index]),
        deterministic: deterministicSupportingFileIndexes.has(index),
      })));

      const staleOrMissing: string[] = [];
      selectedEvidence.forEach((item) => {
        const cached = supportingFilePreScanResults[item.sourceIndex];
        if (
          !cached
          || cached.sourceName !== item.payload.name
          || cached.sourceSha256 !== item.payload.sha256
          || cached.deterministicRequested !== item.deterministic
          || cached.standardVersion !== managedAiRules.active_version
          || cached.deterministicProfileSignature !== deterministicProfileSignature
        ) {
          staleOrMissing.push(item.payload.name);
        }
      });

      if (staleOrMissing.length) {
        setError(
          `AI export blocked: ${staleOrMissing.length} selected document(s) do not have a current resolved pre-scan result. `
          + 'Run Pre-Scan after changing file selection mode or AI screening standards.',
        );
        setStatus('AI export blocked · document pre-scan required.');
        return;
      }

      const embedded = selectedEvidence.map((item) => item.payload);
      const preparedEvidence = selectedEvidence.map((item) => supportingFilePreScanResults[item.sourceIndex].preparedEvidence);
      const evidencePreparation = selectedEvidence
        .map((item) => supportingFilePreScanResults[item.sourceIndex].evidencePreparation)
        .filter((entry): entry is EvidencePreparationSummary => Boolean(entry));
      const estimatedEvidenceTokens = selectedEvidence.reduce(
        (sum, item) => sum + Number(supportingFilePreScanResults[item.sourceIndex].estimatedEvidenceTokens || 0),
        0,
      );

      const deterministicEmbedded = selectedEvidence.filter((item) => item.deterministic).map((item) => item.payload);
      const deterministicEnabled = deterministicEmbedded.length > 0;
      const mixedDeterministicMode = deterministicEnabled && deterministicEmbedded.length < embedded.length;

      const sourceFiles = embedded.map((file) => ({
        name: file.name,
        type: file.type || 'application/octet-stream',
        size: file.size,
        sha256: file.sha256,
      }));

      const packageRevision = await aiRevision.allocateExport();
      const payload = {
        package_type: 'completion_data_manager_ai_package',
        schema_version: '1.1.0',
        managed_ai_rules: combinedRules,
        deterministic_screening: {
          enabled: deterministicEnabled,
          execution: deterministicEnabled
            ? (mixedDeterministicMode ? 'mixed_per_document_pre_scan_completed_before_export' : 'document_pre_scan_completed_before_export')
            : 'disabled',
          profile: deterministicProfile,
          standard_version: managedAiRules.active_version,
          authority: 'AI Standards Manager',
          evidence_preparation: evidencePreparation,
          estimated_evidence_tokens: estimatedEvidenceTokens,
          budget_scope: 'per_document',
          max_selected_pages_per_document: Number(deterministicProfile.max_selected_pages ?? 50),
          per_document_selection: selectedEvidence.map((item, position) => ({
            source: item.payload.name,
            deterministic_screening_selected: item.deterministic,
            deterministic_screening_applied: Boolean(preparedEvidence[position]?.deterministic_screening),
            full_original_fallback: item.deterministic && !preparedEvidence[position]?.deterministic_screening,
            fallback_reason: evidencePreparation.find(
              (entry) => entry.name === item.payload.name && String(entry.mode || '').includes('fallback')
            )?.graphics_audit?.recommendation ?? null,
          })),
          provider_payload_policy: 'export uses only resolved document pre-scan payloads; export does not rerun deterministic preparation',
        },
        managed_well: {
          managed_well_id: selectedWell.managed_well_id,
          well_id: selectedWell.well_id,
          well_name: selectedWell.well_name,
          display_name: selectedWell.display_name,
          wellbore_name: selectedWell.wellbore_name,
          uwi: selectedWell.uwi,
          depth_unit: selectedWell.depth_unit,
        },
        task: {
          domain: 'completion_data',
          objective: 'Extract completion hardware and completion-state evidence suitable for WDV completion visualization. Do not infer well-construction geometry as completion hardware.',
          rules: [
            'Return completion hardware/state candidates only when directly supported by source evidence.',
            'Do not return casing, liner or open-hole geometry as CDM completion candidates; those belong to the separate well-construction domain.',
            'Use measured depth (MD) only for geometry. Do not convert TVD/TVDSS to MD.',
            'Do not force non-canonical completion hardware into an unrelated canonical class; retain it as unresolved evidence when relevant.',
            'Do not invent engineering details such as metallurgy, pressure rating, manufacturer, serial number, connection type, or equipment specification.',
            'Diameter is optional and should be returned only when explicitly supported and visually useful.',
            'Use exact source filenames and page/table/schematic references.',
            'Preserve materially conflicting alternatives in conflicts rather than silently choosing one.',
            'Return zero candidates rather than unsupported guesses.',
            'Confidence must be high, medium or low and must reflect source clarity, not model certainty.',
          ],
        },
        kr_completion_authority: krComponents.map((item) => ({
          canonicalId: item.canonicalId,
          componentKey: item.componentKey,
          componentLabel: item.componentLabel,
          instructionId: item.instructionId,
          version: item.version,
          geometryClass: item.geometryClass,
        })),
        kr_catalogue_version: krCatalogueVersion,
        output_contract: {
          package_type: 'completion_data_manager_ai_response',
          revision: toolboxAiExpectedResponseRevision(packageRevision),
          schema_version: '1.0.0',
          managed_well_id: selectedWell.managed_well_id,
          screening: {
            deterministic_enabled: deterministicEnabled,
            deterministic_by_document: selectedEvidence.map((item) => ({
              source: item.payload.name,
              enabled: item.deterministic,
            })),
            standard_version: managedAiRules.active_version,
            selected_pages_by_document: evidencePreparation.map((item) => ({
              source: item.name,
              selected_pages: item.selected_pages ?? [],
              selected_page_count: Number(item.selected_page_count || 0),
            })),
          },
          candidates: [{
            canonicalId: 'one canonicalId from kr_completion_authority',
            componentType: 'matching componentKey from kr_completion_authority',
            krInstructionId: 'matching instructionId from kr_completion_authority',
            krVersion: 'matching version from kr_completion_authority',
            label: 'short human-readable component label preserving source wording where useful',
            topMd: 'number or empty',
            baseMd: 'number or empty',
            unit: selectedWell.depth_unit || 'm',
            diameter: 'number or empty',
            status: 'installed/final/planned/historical/removed/etc when explicitly supported, otherwise empty',
            source: 'exact source filename',
            evidence: 'page/table/schematic/section reference',
            confidence: 'high | medium | low',
            notes: 'ambiguity, graphical reading or interpretation note',
          }],
          unresolved_evidence: [{
            source: 'exact source filename',
            evidence: 'page/table/schematic/section reference',
            description: 'completion-relevant evidence that cannot be defensibly mapped to a publishable canonical candidate',
            reason: 'why canonical identity, applicability, status or MD geometry is unresolved',
          }],
          conflicts: [{
            component: 'affected component or evidence subject',
            sources: ['exact source locations'],
            description: 'materially conflicting depth, status, configuration or applicability evidence',
          }],
          limitations: ['optional package-level limitation'],
        },
        existing_candidates: candidates.map(({ original: _original, ...candidate }) => candidate),
        source_files: sourceFiles,
        source_payload_policy: mixedDeterministicMode
          ? 'mixed_per_document_pre_scanned_selected_pdf_pages_and_full_original_binaries'
          : deterministicEnabled && preparedEvidence.some((file) => Boolean(file.deterministic_screening))
            ? 'pre_scanned_selected_pdf_pages_embedded'
            : deterministicEnabled
              ? 'pre_scanned_full_original_fallback_binaries_embedded'
              : 'full_original_binaries_prepared_before_export',
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

      const packageFilename = toolboxAiPackageFilename(
        'CDM_AI_PACKAGE',
        selectedWell.display_name || selectedWell.well_name || selectedWell.well_id,
        packageRevision,
      );

      const compressedPackageFilename = await downloadCompressedJsonPackage(
        packageFilename,
        JSON.stringify(payload, null, 2),
      );

      const totalSelectedPages = evidencePreparation.reduce(
        (sum, item) => sum + Number(item.selected_page_count || 0),
        0,
      );
      const fallbackCount = selectedEvidence.filter((item) => {
        const mode = String(supportingFilePreScanResults[item.sourceIndex].evidencePreparation?.mode || '');
        return mode.includes('fallback');
      }).length;

      setStatus(
        `${compressedPackageFilename} exported from resolved document pre-scan`
        + ` · ${selectedEvidence.length} document(s)`
        + (deterministicEnabled ? ` · ${totalSelectedPages} selected deterministic page(s)` : '')
        + (fallbackCount ? ` · ${fallbackCount} full-scan fallback(s)` : '')
        + '.'
      );
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to build AI package');
    }
  };

  const importAi = async (file: File) => {
    try {
      if (file.name.toLowerCase().endsWith('.json')) { try { void aiRevision.syncImportedArtifact(file.name, JSON.parse(await file.text())); } catch {} } else void aiRevision.syncImportedArtifact(file.name);
      const imported = await importRows(file);
      setCandidates((current) => mergeCandidates(current, imported));
      setStatus(`Reconciled ${imported.length} completion proposal(s) for review.`);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to import AI response');
    }
  };

  const update = <K extends keyof Candidate>(id: string, field: K, value: Candidate[K]) => {
    setCandidates((current) => current.map((candidate) =>
      candidate.id === id ? { ...candidate, [field]: value, state: candidate.state === 'existing' ? 'edited' : candidate.state } : candidate,
    ));
  };

  const confirm = (id: string) => {
    setCandidates((current) => current.map((candidate) =>
      candidate.id === id ? { ...candidate, state: candidate.state === 'edited' ? 'edited' : 'confirmed' } : candidate,
    ));
    setActiveEditId(null);
  };
  const reject = (id: string) => {
    setCandidates((current) => current.map((candidate) => candidate.id === id ? { ...candidate, state: 'rejected' } : candidate));
    setActiveEditId(null);
  };

  const clearSelectedCandidates = () => {
    if (!selectedIds.size) return;
    const removing = new Set(selectedIds);
    setCandidates((current) => current.filter((candidate) => !removing.has(candidate.id)));
    if (activeEditId && removing.has(activeEditId)) setActiveEditId(null);
    setSelectedIds(new Set());
    setError(null);
    setStatus(`Cleared ${removing.size} selected completion candidate(s) from the active review. No published completion data was removed.`);
  };

  const clearReviewCandidates = () => {
    if (!candidates.length) return;
    const count = candidates.length;
    setCandidates([]);
    setActiveEditId(null);
    setSelectedIds(new Set());
    setError(null);
    setStatus(`Cleared ${count} completion candidate(s) from the active review. Supporting files and published completion data were preserved.`);
  };

  const addRow = () => setCandidates((current) => [...current, emptyCandidate(selectedWell?.depth_unit || 'm')]);

  const toggleSelection = (id: string) => setSelectedIds((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const acceptSelected = () => {
    selectedIds.forEach(confirm);
    setSelectedIds(new Set());
  };

  const publish = async () => {
    if (!selectedWell) {
      setError('Select a managed well first.');
      return;
    }
    const approved = candidates.filter((candidate) => candidate.state === 'confirmed' || candidate.state === 'edited');
    if (!approved.length) {
      setError('No approved completion components are available.');
      return;
    }
    for (const [index, candidate] of approved.entries()) {
      const top = Number(candidate.topMd);
      const base = numberOrNull(candidate.baseMd);
      if (!normalize(candidate.label) || !Number.isFinite(top)) {
        setError(`Row ${index + 1} requires a Label and Top MD.`);
        return;
      }
      const authority = authorityFor(candidate.componentType, candidate.canonicalId, krComponents);
      if (!authority || !candidate.canonicalId || !candidate.krInstructionId || !candidate.krVersion) {
        setError(`Row ${index + 1} must be mapped to an approved KR completion component.`);
        return;
      }
      if (
        authority.instructionId !== candidate.krInstructionId
        || authority.version !== candidate.krVersion
        || authority.canonicalId !== candidate.canonicalId
      ) {
        setError(`Row ${index + 1} has stale KR completion authority. Refresh the CDM review.`);
        return;
      }
      if (isIntervalType(candidate.componentType) && (base === null || !Number.isFinite(base) || base <= top)) {
        setError(`Row ${index + 1} (${componentLabel(candidate.componentType)}) requires Base MD deeper than Top MD.`);
        return;
      }
      if (base !== null && (!Number.isFinite(base) || base < top)) {
        setError(`Row ${index + 1} Base MD cannot be shallower than Top MD.`);
        return;
      }
    }

    const payload = {
      dataset_type: 'completion_components',
      dataset_status: 'reviewed',
      source: 'Completion Data Manager',
      managed_well_id: selectedWell.managed_well_id,
      kr_catalogue_version: krCatalogueVersion,
      completion_components: approved.map((candidate) => ({
        canonical_id: candidate.canonicalId,
        canonical_component_key: candidate.componentType,
        kr_instruction_id: candidate.krInstructionId,
        kr_version: candidate.krVersion,
        label: candidate.label,
        top_md: Number(candidate.topMd),
        base_md: numberOrNull(candidate.baseMd),
        depth_unit: candidate.unit || selectedWell.depth_unit || 'm',
        diameter: numberOrNull(candidate.diameter),
        status: candidate.status || null,
        source_document: candidate.source || null,
        source_reference: candidate.evidence || null,
        confidence: candidate.confidence || null,
        notes: candidate.notes || null,
      })),
    };

    try {
      const response = await fetch(
        `${wlvApiBaseUrl()}/api/wlv/inventory/wells/${encodeURIComponent(selectedWell.managed_well_id)}/completion-components`,
        { method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
      );
      if (!response.ok) throw new Error(await response.text() || `Publication returned ${response.status}`);
      await response.json();
      saveReview();
      const wellName = selectedWell.display_name || selectedWell.well_name || selectedWell.well_id;
      setStatus(`Completion data saved to ${wellName} in the MWD.`);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Direct MWD publication failed.');
    }
  };

  const exportCsv = () => {
    if (!candidates.length) return;
    const columns = ['Canonical ID', 'Canonical Component Key', 'KR Instruction ID', 'KR Version', 'Label', 'Top MD', 'Base MD', 'Unit', 'Diameter', 'Status', 'Source', 'Evidence', 'Confidence', 'Review Status', 'Notes'];
    const esc = (value: unknown) => /[",\n]/.test(String(value ?? '')) ? `"${String(value ?? '').replace(/"/g, '""')}"` : String(value ?? '');
    const lines = [
      columns.join(','),
      ...candidates.map((candidate) => [
        candidate.canonicalId, candidate.componentType, candidate.krInstructionId, candidate.krVersion, candidate.label, candidate.topMd, candidate.baseMd, candidate.unit,
        candidate.diameter, candidate.status, candidate.source, candidate.evidence, candidate.confidence,
        candidate.state, candidate.notes,
      ].map(esc).join(',')),
    ];
    downloadText('CDM_COMPLETION_COMPONENTS.csv', lines.join('\n'), 'text/csv;charset=utf-8');
  };

  const clear = () => {
    if (!window.confirm(
      'Clear the entire Completion Data Manager workspace? '
      + 'This clears the selected well, supporting files, pre-scan results, imported/review candidates, selections and saved CDM review state. '
      + 'Published completion data in the MWD will not be removed.'
    )) return;

    const clearingWellId = selectedWellId;
    if (clearingWellId) localStorage.removeItem(`${STORAGE_PREFIX}${clearingWellId}`);
    sessionStorage.removeItem(ACTIVE_KEY);
    activeRef.current = null;

    setSelectedWellId('');
    setWellSearch('');
    setCandidates([]);
    setSupportingFiles([]);
    setFileObjects([]);
    setSelectedSupportingFileIndexes(new Set());
    setDeterministicSupportingFileIndexes(new Set());
    setSkippedArchiveMembers([]);
    setSupportingFileAuditResults({});
    setSupportingFilePreScanResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    setPreScanRunning(false);
    setActiveEditId(null);
    setSelectedIds(new Set());

    graphicsChoiceResolverRef.current = null;
    deterministicFailureResolverRef.current = null;
    setGraphicsChoiceFiles(null);
    setDeterministicFailurePrompt(null);
    setRememberDeterministicFailureChoice(false);

    if (fileRef.current) fileRef.current.value = '';
    if (aiRef.current) aiRef.current.value = '';

    setError(null);
    setStatus('Completion Data Manager cleared. Select a managed well to begin.');
  };

  const selectedPreScanIndexes = Array.from(selectedSupportingFileIndexes);
  const exportSelectedSourceBytes = selectedPreScanIndexes.reduce(
    (sum, index) => sum + Number(fileObjects[index]?.size || 0),
    0,
  );
  const exportSelectedPayloadBytes = selectedPreScanIndexes.reduce(
    (sum, index) => sum + Number(supportingFileAuditResults[fileObjects[index]?.name]?.payloadBytes || 0),
    0,
  );
  const exportSelectedPendingCount = selectedPreScanIndexes.reduce(
    (count, index) => count + (supportingFilePreScanResults[index] ? 0 : 1),
    0,
  );
  const formatManifestTotalBytes = (value: number) => {
    if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`;
    if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${Math.round(value)} B`;
  };

  const selectedPreScanReady = selectedPreScanIndexes.length > 0
    && selectedPreScanIndexes.every((index) => {
      const result = supportingFilePreScanResults[index];
      return Boolean(result) && result.deterministicRequested === deterministicSupportingFileIndexes.has(index);
    });

  return <section className="wlv-metadata-tool wlv-ftm-tool wlv-lcm-tool">
    {activeSupportingFileAudit ? <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cdm-file-audit-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10030,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(4, 8, 12, 0.72)',
      }}
    >
      <div style={{
        width: 'min(680px, calc(100vw - 48px))',
        border: '1px solid #4b5d70',
        borderRadius: '8px',
        background: '#151c23',
        boxShadow: '0 18px 60px rgba(0,0,0,0.5)',
        padding: '20px',
        color: '#dbe4ee',
      }}>
        <h2 id="cdm-file-audit-title" style={{ margin: '0 0 10px', fontSize: '17px' }}>Supporting file audit</h2>
        <div style={{ marginBottom: '12px', color: '#d4dde7', wordBreak: 'break-word' }}>{activeSupportingFileAudit.fileName}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: '7px 12px', fontSize: '11px', lineHeight: 1.45 }}>
          <strong>Requested</strong>
          <span>{activeSupportingFileAudit.requestedMode === 'deterministic' ? 'Deterministic screening' : activeSupportingFileAudit.requestedMode === 'full_original' ? 'Full original' : 'Excluded'}</span>
          <strong>Completion status</strong>
          <span>{activeSupportingFileAudit.completionStatus.replace(/_/g, ' ')}</span>
          <strong>Final payload</strong>
          <span>{activeSupportingFileAudit.payloadBytes >= 1024 * 1024 ? `${(activeSupportingFileAudit.payloadBytes / 1024 / 1024).toFixed(2)} MB` : activeSupportingFileAudit.payloadBytes ? `${(activeSupportingFileAudit.payloadBytes / 1024).toFixed(1)} KB` : 'None'}</span>
          <strong>Pages</strong>
          <span>{activeSupportingFileAudit.completionStatus === 'screened' ? `${activeSupportingFileAudit.selectedPageCount}${activeSupportingFileAudit.totalPages ? ` / ${activeSupportingFileAudit.totalPages}` : ''}` : activeSupportingFileAudit.completionStatus === 'excluded' ? 'Not exported' : 'Full document'}</span>
          <strong>Audit result</strong>
          <span>{activeSupportingFileAudit.reason}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '18px' }}>
          <button type="button" onClick={() => setActiveSupportingFileAudit(null)}>Close</button>
        </div>
      </div>
    </div> : null}
    {deterministicFailurePrompt ? <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cdm-deterministic-failure-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10020,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(4, 8, 12, 0.72)',
      }}
    >
      <div style={{
        width: 'min(640px, calc(100vw - 48px))',
        border: '1px solid #4b5d70',
        borderRadius: '8px',
        background: '#151c23',
        boxShadow: '0 18px 60px rgba(0,0,0,0.5)',
        padding: '20px',
        color: '#dbe4ee',
      }}>
        <h2 id="cdm-deterministic-failure-title" style={{ margin: '0 0 10px', fontSize: '17px' }}>Deterministic screening unavailable for this document</h2>
        <p style={{ margin: '0 0 8px', color: '#d4dde7', lineHeight: 1.5, wordBreak: 'break-word' }}>
          {deterministicFailurePrompt.fileName}
        </p>
        <p style={{ margin: '0 0 14px', color: '#aeb9c5', lineHeight: 1.5 }}>
          {deterministicFailurePrompt.detail}
        </p>
        <p style={{ margin: '0 0 14px', color: '#9eabb9', lineHeight: 1.5 }}>
          Choose whether to leave the document unresolved, use the full original, or bypass only the minimum score gate and continue deterministic page ranking.
        </p>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', marginBottom: '18px', color: '#c7d1dc', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={rememberDeterministicFailureChoice}
            onChange={(event) => setRememberDeterministicFailureChoice(event.target.checked)}
          />
          Remember this answer for the remaining documents in this pre-scan
        </label>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button type="button" onClick={() => resolveDeterministicFailureChoice('cancel')}>Leave unresolved</button>
          <button type="button" onClick={() => resolveDeterministicFailureChoice('full_original')}>Use full original</button>
          {deterministicFailurePrompt.canBypassScoring ? (
            <button
              type="button"
              onClick={() => resolveDeterministicFailureChoice('bypass_scoring')}
              title="Keep deterministic ranking and page-budget logic, but bypass the minimum direct-score threshold for this document."
            >
              Bypass scoring
            </button>
          ) : null}
        </div>
      </div>
    </div> : null}
    {graphicsChoiceFiles ? <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cdm-graphics-choice-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(4, 8, 12, 0.72)',
      }}
    >
      <div style={{
        width: 'min(620px, calc(100vw - 48px))',
        border: '1px solid #4b5d70',
        borderRadius: '8px',
        background: '#151c23',
        boxShadow: '0 18px 60px rgba(0,0,0,0.5)',
        padding: '20px',
        color: '#dbe4ee',
      }}>
        <h2 id="cdm-graphics-choice-title" style={{ margin: '0 0 10px', fontSize: '17px' }}>High graphical-content risk</h2>
        <p style={{ margin: '0 0 8px', color: '#c2ccd7', lineHeight: 1.5 }}>
          Deterministic screening found substantial graphical content in {graphicsChoiceFiles.join(', ')}.
          The application can rank text/OCR evidence, but it cannot interpret diagrams on excluded pages.
        </p>
        <p style={{ margin: '0 0 18px', color: '#9eabb9', lineHeight: 1.5 }}>
          Choose exactly what should be handed to the LLM for this export.
        </p>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button type="button" onClick={() => resolveGraphicsExportChoice('cancel')}>Leave unresolved</button>
          <button type="button" onClick={() => resolveGraphicsExportChoice('full_original')}>Use full original document</button>
          <button type="button" onClick={() => resolveGraphicsExportChoice('selected_pages')}>Use deterministic selected pages</button>
        </div>
      </div>
    </div> : null}
    <header className="wlv-metadata-tool__header">
      <button type="button" className="wlv-metadata-tool__back" onClick={onBack}>‹ Toolbox</button>
      <div className="wlv-metadata-tool__title">
        <h1>Completion Data Manager</h1>
        <p>Extract, review and publish visualization-focused completion landmarks and intervals using KR canonical completion identities.</p>
      </div>
      <div className="wlv-metadata-tool__window-actions">
        <button
          type="button"
          onClick={clear}
          disabled={
            !selectedWellId
            && !wellSearch
            && candidates.length === 0
            && supportingFiles.length === 0
            && fileObjects.length === 0
          }
          title="Clear the entire Completion Data Manager workspace"
        >
          Clear
        </button>
        <button type="button" className="wlv-metadata-tool__close" aria-label="Close Completion Data Manager" onClick={onBack}>×</button>
      </div>
    </header>

    <div className="wlv-metadata-tool__input-grid" style={{ gridTemplateColumns: 'repeat(3,minmax(0,1fr))' }}>
      <section className="wlv-metadata-tool__drop-panel wlv-ftm-tool__well-panel">
        <div className="wlv-metadata-tool__drop-copy">
          <strong>Managed Well</strong>
          <span>{selectedWell ? (selectedWell.display_name || selectedWell.well_name || selectedWell.well_id) : (loadingWells ? 'Loading wells from the Managed Well Directory…' : 'Select a managed well')}</span>
        </div>
        <div className="wlv-ftm-tool__well-controls">
          <input value={wellSearch} onChange={(event) => setWellSearch(event.target.value)} placeholder="Search MWD" />
          <select value={selectedWellId} onChange={(event) => { setSelectedWellId(event.target.value); setError(null); }}>
            <option value="">Select a well…</option>
            {filteredWells.map((well) => <option key={well.managed_well_id} value={well.managed_well_id}>
              {well.display_name || well.well_name || well.well_id}{well.wellbore_name ? ` — ${well.wellbore_name}` : ''}{well.uwi ? ` (${well.uwi})` : ''}
            </option>)}
          </select>
        </div>
      </section>

      <section className={`wlv-metadata-tool__drop-panel ${!selectedWellId ? 'is-disabled' : ''}`}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => { event.preventDefault(); if (selectedWellId) void handleFiles(event.dataTransfer.files); }}>
        <div className="wlv-metadata-tool__drop-copy">
          <strong>Supporting Files</strong>
          <span>{
            fileObjects.length
              ? `${fileObjects.length} staged · ${selectedSupportingFileIndexes.size} selected`
              : supportingFiles.length
                ? `${supportingFiles.length} file reference(s) remembered · reload required`
                : (selectedWellId ? 'Drop completion schematic, PDF, XLSX, CSV, TXT, JSON, image or ZIP bundle here' : 'Select a managed well first')
          }</span>
        </div>
        <div className="wlv-cdm-tool__supporting-file-actions" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <button type="button" disabled={!selectedWellId} onClick={() => fileRef.current?.click()}>Browse</button>
          <button type="button" disabled={!selectedWellId || supportingFiles.length === 0} onClick={clearSupportingFiles}>Clear</button>
        </div>
        <input ref={fileRef} type="file" multiple accept=".pdf,.csv,.xlsx,.xls,.txt,.json,.zip,image/*" hidden
          onChange={(event) => { if (event.target.files) void handleFiles(event.target.files); event.currentTarget.value = ''; }} />
      </section>

      <section className={`wlv-metadata-tool__drop-panel ${!selectedWellId ? 'is-disabled' : ''}`}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => { event.preventDefault(); const file = event.dataTransfer.files?.[0]; if (selectedWellId && file) void importAi(file); }}>
        <div className="wlv-metadata-tool__drop-copy">
          <strong>Import and Review</strong>
          <span>{selectedWellId ? 'Drop AI response JSON, CSV or Excel here' : 'Select a managed well first'}</span>
        </div>
        <button type="button" disabled={!selectedWellId} onClick={() => aiRef.current?.click()}>Browse</button>
        <input ref={aiRef} type="file" accept=".json,.csv,.xlsx,.xls" hidden
          onChange={(event) => { const file = event.target.files?.[0]; if (file) void importAi(file); event.currentTarget.value = ''; }} />
      </section>
    </div>

    {(fileObjects.length > 0 || skippedArchiveMembers.length > 0) && (
      <section style={{ width: 'calc(100% - 24px)', maxWidth: '1136px', margin: '0 auto 12px', border: '1px solid #34414f', borderRadius: '5px', overflow: 'hidden', background: '#151b21' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '9px 12px', borderBottom: supportingManifestCollapsed ? undefined : '1px solid #34414f' }}>
          <div style={{ minWidth: 0 }}>
            <strong style={{ display: 'block', fontSize: '11px', color: '#e2e8ef' }}>Supporting file manifest</strong>
            <span style={{ fontSize: '10px', color: '#93a1b0' }}>
              {supportingManifestCollapsed
                ? `${selectedPreScanIndexes.length} selected file${selectedPreScanIndexes.length === 1 ? '' : 's'} · ${formatManifestTotalBytes(exportSelectedPayloadBytes)} payload`
                : 'Phase 1: select files and screening mode, then Run Pre-Scan. Review Completion Status, Payload and Audit results. Phase 2: refine the file selection and Export AI package.'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setSupportingManifestCollapsed((current) => !current)}
            aria-expanded={!supportingManifestCollapsed}
            aria-controls="cdm-supporting-file-manifest-body"
            title={supportingManifestCollapsed ? 'Expand supporting file manifest' : 'Collapse supporting file manifest'}
            style={{ flex: '0 0 auto', minWidth: '34px', padding: '4px 8px' }}
          >
            {supportingManifestCollapsed ? '▸' : '▾'}
          </button>
        </div>

        <div id="cdm-supporting-file-manifest-body" hidden={supportingManifestCollapsed}>
        {fileObjects.length > 0 && (
          <div style={{ maxHeight: '280px', overflow: 'auto' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '112px minmax(0, 1fr) 82px 128px 132px 92px 42px',
                alignItems: 'center',
                minHeight: '32px',
                color: '#93a1b0',
                background: '#11171d',
                borderBottom: '1px solid #293440',
                fontSize: '10px',
                fontWeight: 600,
              }}
            >
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '7px 14px', cursor: fileObjects.length ? 'pointer' : 'default' }}>
                <input
                  type="checkbox"
                  checked={fileObjects.length > 0 && selectedSupportingFileIndexes.size === fileObjects.length}
                  disabled={!fileObjects.length}
                  onChange={toggleAllSupportingFiles}
                  aria-label="Select all supporting files"
                />
                SELECT FILES
              </label>
              <div style={{ padding: '7px 10px' }}>FILE / ZIP MEMBER</div>
              <div style={{ padding: '7px 10px' }}>SIZE</div>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '7px 10px', cursor: selectedSupportingFileIndexes.size ? 'pointer' : 'default' }}>
                <input
                  type="checkbox"
                  checked={
                    selectedSupportingFileIndexes.size > 0
                    && Array.from(selectedSupportingFileIndexes).every((index) => deterministicSupportingFileIndexes.has(index))
                  }
                  disabled={selectedSupportingFileIndexes.size === 0}
                  onChange={toggleAllDeterministicSupportingFiles}
                  aria-label="Deterministic screening for all selected supporting files"
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
              return (
                <div
                  key={`${file.name}-${index}`}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '112px minmax(0, 1fr) 82px 128px 132px 92px 42px',
                    alignItems: 'center',
                    minHeight: '34px',
                    borderTop: index ? '1px solid #293440' : undefined,
                    color: '#d6dde5',
                    fontSize: '10px',
                  }}
                >
                  <div style={{ padding: '7px 14px' }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleSupportingFile(index)}
                      aria-label={`Include ${file.name}`}
                    />
                  </div>
                  <div style={{ padding: '7px 10px', minWidth: 0, overflowWrap: 'anywhere' }}>{file.name}</div>
                  <div style={{ padding: '7px 10px', whiteSpace: 'nowrap', color: '#aeb9c5' }}>
                    {file.size >= 1024 * 1024
                      ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                      : `${(file.size / 1024).toFixed(1)} KB`}
                  </div>
                  <div style={{ padding: '7px 10px' }}>
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', color: checked ? '#cdd6df' : '#6f7b87' }}>
                      <input
                        type="checkbox"
                        checked={deterministic}
                        disabled={!checked}
                        onChange={() => toggleDeterministicSupportingFile(index)}
                        aria-label={`Deterministic pre-screen ${file.name}`}
                      />
                      {deterministic ? 'Screen' : 'Full'}
                    </label>
                  </div>
                  {(() => {
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
                    return <>
                      <div style={{ padding: '7px 8px', whiteSpace: 'nowrap', color: audit ? '#c8d2dc' : '#768493' }}>{statusLabel}</div>
                      <div style={{ padding: '7px 8px', whiteSpace: 'nowrap', color: '#aeb9c5' }}>{payloadLabel}</div>
                      <div style={{ padding: '5px 4px', textAlign: 'center' }}>
                        <button
                          type="button"
                          disabled={!audit}
                          onClick={() => audit && setActiveSupportingFileAudit(audit)}
                          title={audit ? `View audit for ${file.name}` : 'Audit available after document pre-scan'}
                          aria-label={`View audit for ${file.name}`}
                          style={{ minWidth: '28px', padding: '3px 6px', fontSize: '11px' }}
                        >
                          ⓘ
                        </button>
                      </div>
                    </>;
                  })()}
                </div>
              );
            })}
            <div
              aria-label="Export totals"
              style={{
                display: 'grid',
                gridTemplateColumns: '112px minmax(0, 1fr) 82px 128px 132px 92px 42px',
                alignItems: 'center',
                minHeight: '40px',
                borderTop: '1px solid #4a5968',
                background: '#11171d',
                color: '#dbe4ee',
                fontSize: '10px',
                fontWeight: 700,
              }}
            >
              <div style={{ padding: '8px 14px', whiteSpace: 'nowrap' }}>EXPORT TOTALS</div>
              <div style={{ padding: '8px 10px', color: '#aeb9c5', fontWeight: 600 }}>
                {selectedPreScanIndexes.length} selected file{selectedPreScanIndexes.length === 1 ? '' : 's'}
              </div>
              <div
                style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}
                title="Total original size of files currently selected for AI export"
              >
                {formatManifestTotalBytes(exportSelectedSourceBytes)}
              </div>
              <div style={{ padding: '8px 10px', color: '#7f8d9b', fontWeight: 600 }}>
                {exportSelectedPendingCount > 0 ? `${exportSelectedPendingCount} pending` : 'Ready'}
              </div>
              <div style={{ padding: '8px 8px', color: '#aeb9c5', fontWeight: 600 }}>
                {selectedPreScanReady ? 'Ready for export' : 'Selection total'}
              </div>
              <div
                style={{ padding: '8px 8px', whiteSpace: 'nowrap' }}
                title="Total prepared payload of files currently selected for AI export"
              >
                {formatManifestTotalBytes(exportSelectedPayloadBytes)}
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
        disabled={
          preScanRunning
          || !selectedWellId
          || (supportingFiles.length > 0 && fileObjects.length === 0)
          || (fileObjects.length > 0 && selectedSupportingFileIndexes.size === 0)
        }
        title={supportingFiles.length > 0 && fileObjects.length === 0
          ? 'Reload the remembered supporting file(s) with Browse before pre-scan.'
          : fileObjects.length > 0 && selectedSupportingFileIndexes.size === 0
            ? 'Select at least one supporting file for document pre-scan.'
            : undefined}
      >
        {preScanRunning ? 'Pre-Scanning…' : 'Run Pre-Scan'}
      </button>
      <button
        type="button"
        onClick={() => void exportAiPackage()}
        disabled={
          preScanRunning
          || !selectedWellId
          || !selectedPreScanReady
        }
        title={!selectedPreScanReady
          ? 'All currently selected files must have resolved, current pre-scan results before AI export.'
          : 'Export the currently selected files using their cached pre-scan payloads.'}
      >
        Export AI package
      </button>
      <span className="wlv-toolbox-ai-revision" style={{ color: '#9ca9b7', fontSize: '10px', fontWeight: 600, whiteSpace: 'nowrap' }}>{selectedWellId ? `AI Review Cycle: ${aiRevision.currentLabel} · Next export: ${aiRevision.nextLabel}` : 'AI Review Cycle: —'}</span>
      <button type="button" onClick={() => void publish()} disabled={!selectedWellId || summary.approved === 0}>Publish approved completions</button>
      <button type="button" onClick={saveReview} disabled={!selectedWellId}>Save review</button>
      <button type="button" onClick={exportCsv} disabled={!candidates.length}>Export CSV</button>
      <button type="button" onClick={addRow} disabled={!selectedWellId}>Add row</button>
      <span className="wlv-metadata-tool__session-summary">
        {selectedWell ? (selectedWell.display_name || selectedWell.well_name || selectedWell.well_id) : 'No well selected'}
        {candidates.length ? ` · ${candidates.length} component(s)` : ''}
        {summary.approved ? ` · ${summary.approved} approved` : ''}
      </span>
    </div>

    <div className="wlv-metadata-tool__message" role="status">
      <span>{error || status}</span>
      <span className="wlv-ftm-tool__counts">{summary.unreviewed} unreviewed · {summary.approved} approved · {summary.rejected} rejected</span>
    </div>

    <section className="wlv-metadata-tool__review">
      <header>
        <h2>Completion candidates</h2>
        <div
          className="wlv-lcm-tool__bulk-selection"
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px', marginLeft: 'auto', fontSize: '10px', fontWeight: 600 }}
        >
          <span>{candidates.length || 0}</span>
          <button type="button" onClick={() => setSelectedIds(new Set(candidates.map((candidate) => candidate.id)))} disabled={candidates.length === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Select All</button>
          <button type="button" onClick={() => setSelectedIds(new Set())} disabled={selectedIds.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Select None</button>
          <button type="button" onClick={acceptSelected} disabled={selectedIds.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Accept</button>
          <button type="button" onClick={clearSelectedCandidates} disabled={selectedIds.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Clear Selected</button>
          <button type="button" onClick={clearReviewCandidates} disabled={candidates.length === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Clear Review</button>
        </div>
      </header>
      <div className="wlv-metadata-tool__table-wrap wlv-ftm-tool__table-wrap">
        <table className="wlv-ftm-tool__table wlv-lcm-tool__table">
          <thead><tr><th>Component</th><th>Depth / type</th><th style={{ paddingRight: '4px' }}>Confidence</th><th style={{ paddingLeft: '4px', paddingRight: '4px' }}>Source</th><th style={{ paddingLeft: '4px' }}>Action</th></tr></thead>
          <tbody>
            {!candidates.length ? <tr><td colSpan={5} className="is-empty">{selectedWellId ? 'Load supporting files, import a response, or add a row.' : 'Select a managed well.'}</td></tr> :
              candidates.map((candidate) => {
                const editing = activeEditId === candidate.id;
                return <tr key={candidate.id} className={`is-populated is-${candidate.state}`}>
                  <td className="wlv-metadata-tool__editable-value" onClick={() => { if (!editing) setActiveEditId(candidate.id); }}>
                    {editing ? <div className="wlv-ftm-tool__edit-stack">
                      <input autoFocus value={candidate.label} placeholder="Label" onChange={(event) => update(candidate.id, 'label', event.target.value)} />
                      <select
                        value={candidate.componentType}
                        onChange={(event) => {
                          const authority = krByKey.get(event.target.value);
                          setCandidates((current) => current.map((item) => item.id === candidate.id ? {
                            ...item,
                            componentType: authority?.componentKey ?? '',
                            canonicalId: authority?.canonicalId ?? '',
                            krInstructionId: authority?.instructionId ?? '',
                            krVersion: authority?.version ?? '',
                            state: item.state === 'confirmed' || item.state === 'existing' ? 'edited' : item.state,
                          } : item));
                        }}
                      >
                        <option value="">Select KR component…</option>
                        {krComponents.map((item) => <option key={item.canonicalId} value={item.componentKey}>{item.componentLabel}</option>)}
                      </select>
                      <input value={candidate.status} placeholder="Status (optional)" onChange={(event) => update(candidate.id, 'status', event.target.value)} />
                    </div> : <>
                      <strong>{candidate.label || 'Unnamed component'}</strong>
                      <small>{componentLabel(candidate.componentType)}{candidate.status ? ` · ${candidate.status}` : ''}</small>
                    </>}
                  </td>
                  <td onClick={() => { if (!editing) setActiveEditId(candidate.id); }}>
                    {editing ? <div className="wlv-ftm-tool__edit-stack">
                      <input value={candidate.topMd} placeholder="Top / MD" inputMode="decimal" onChange={(event) => update(candidate.id, 'topMd', event.target.value)} />
                      <input value={candidate.baseMd} placeholder={isIntervalType(candidate.componentType) ? 'Base MD' : 'Base MD (optional)'} inputMode="decimal" onChange={(event) => update(candidate.id, 'baseMd', event.target.value)} />
                      <input value={candidate.unit} placeholder="Unit" onChange={(event) => update(candidate.id, 'unit', event.target.value)} />
                      <input value={candidate.diameter} placeholder="Diameter (optional)" inputMode="decimal" onChange={(event) => update(candidate.id, 'diameter', event.target.value)} />
                    </div> : <>
                      <strong>{candidate.topMd || '—'}{candidate.baseMd ? ` – ${candidate.baseMd}` : ''} {candidate.unit}</strong>
                      <small>{candidate.diameter ? `Diameter ${candidate.diameter}` : isIntervalType(candidate.componentType) ? 'Interval' : 'Point component'}</small>
                    </>}
                  </td>
                  <td className="wlv-metadata-tool__editable-value wlv-lcm-tool__confidence" onClick={() => { if (!editing) setActiveEditId(candidate.id); }}>
                    {editing ? <select value={candidate.confidence} onChange={(event) => update(candidate.id, 'confidence', event.target.value)}>
                      <option value="">Select…</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
                    </select> : <span className={`wlv-lcm-confidence is-${normalize(candidate.confidence) || 'unset'}`}>{normalize(candidate.confidence) || '—'}</span>}
                  </td>
                  <td onClick={() => { if (!editing) setActiveEditId(candidate.id); }}>
                    {editing ? <div className="wlv-ftm-tool__edit-stack">
                      <input value={candidate.source} placeholder="Source" onChange={(event) => update(candidate.id, 'source', event.target.value)} />
                      <input value={candidate.evidence} placeholder="Evidence / page / schematic" onChange={(event) => update(candidate.id, 'evidence', event.target.value)} />
                      <input value={candidate.notes} placeholder="Notes (optional)" onChange={(event) => update(candidate.id, 'notes', event.target.value)} />
                    </div> : <>
                      <strong>{candidate.source || '—'}</strong>
                      <small>{candidate.evidence || candidate.notes || 'No supporting detail'}</small>
                    </>}
                  </td>
                  <td>
                    {candidate.state === 'unreviewed' || editing ? <div className="wlv-metadata-tool__actions">
                      <label style={{ display: 'inline-flex', alignItems: 'center', marginRight: '6px' }} onClick={(event) => event.stopPropagation()} title="Select candidate">
                        <input type="checkbox" checked={selectedIds.has(candidate.id)} onChange={() => toggleSelection(candidate.id)} aria-label={`Select ${candidate.label || 'completion component'}`} style={{ width: '13px', height: '13px', margin: 0 }} />
                      </label>
                      <button type="button" onClick={() => confirm(candidate.id)}>Approve</button>
                      <button type="button" onClick={() => reject(candidate.id)}>Reject</button>
                    </div> : <span className="wlv-metadata-tool__loaded">{candidate.state === 'rejected' ? 'Rejected' : candidate.state === 'existing' ? 'Existing' : 'Approved'}</span>}
                  </td>
                </tr>;
              })}
          </tbody>
        </table>
      </div>
    </section>
  </section>;
}

export default CompletionDataManagerPage;
