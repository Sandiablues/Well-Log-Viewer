import { useEffect, useMemo, useRef, useState } from 'react';
import * as XLSX from 'xlsx';
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import { createWorker } from 'tesseract.js';
import { toolboxAiExpectedResponseRevision, toolboxAiPackageFilename, toolboxAiPackageRevision, useToolboxAiRevision } from './toolboxAiRevision';
import { fetchToolboxAiRules } from './toolboxAiRulesClient';
import {
  type DeterministicFailureChoice,
  type DeterministicFailureDecision,
  type DeterministicFailurePrompt,
  type EvidencePreparationResponse,
  type GraphicsExportChoice,
  type PreparedEvidenceFile,
  type SkippedArchiveMember,
  type SupportingFileAuditResult,
  type SupportingFilePreScanResult,
  expandZipSupportingFile,
  filePayload,
} from './toolboxAiIntakeExport';

GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

const WELL_INFO_SCHEMA_VERSION = '2.0.0';
const CANONICAL_WELL_INFO_FIELD_KEYS = new Set([
  'well_name', 'wellbore_name', 'uwi', 'field', 'site', 'block', 'operator', 'country', 'well_status',
  'latitude', 'longitude', 'northing', 'easting', 'coordinate_system', 'utm_zone', 'geodetic_datum',
  'epsg_code', 'north_reference', 'grid_convergence', 'depth_unit', 'depth_reference', 'reference_elevation',
  'surface_seabed_elevation', 'water_depth', 'seabed_depth_below_reference', 'wellhead_depth_below_reference',
  'total_depth_md', 'total_depth_tvd', 'survey_start_md', 'survey_end_md', 'survey_start_tvd', 'survey_end_tvd',
  'data_start_md', 'data_end_md', 'trajectory_source', 'survey_status', 'survey_type', 'calculation_method',
  'station_count', 'maximum_inclination', 'final_north_offset', 'final_east_offset',
]);
const LEGACY_WELL_INFO_FIELD_KEYS = new Set([
  'latitude_deg', 'longitude_deg', 'northing_m', 'easting_m',
  'rotary_table_elevation_msl_m', 'water_depth_m', 'wellhead_seabed_depth_m',
  'first_md_m', 'final_md_m', 'final_tvd_m', 'maximum_inclination_deg',
  'final_north_offset_m', 'final_east_offset_m',
]);

type ContextRow = {
  rowNumber: number;
  section: string;
  field: string;
  fieldKey: string;
  value: string;
  unit: string;
  source: string;
  sourceReference: string;
  notes: string;
  aiRecommendedValue: string;
  aiUnit: string;
  aiSource: string;
  aiSourceReference: string;
  aiEvidence: string;
  aiConfidence: string;
  aiStatus: string;
};

type ProposalSource = {
  file: string;
  reference: string;
  extraction: 'text' | 'ocr' | 'structured' | 'ai';
};

type Proposal = {
  fieldKey: string;
  value: string;
  sourceFile: string;
  sourceReference: string;
  accepted: boolean | null;
  editedValue: string;
  sources: ProposalSource[];
  alternatives: Array<{
    value: string;
    sourceFile: string;
    sourceReference: string;
  }>;
};

type SourceBlock = {
  reference: string;
  rows: string[][];
  text: string;
  extraction: 'text' | 'ocr' | 'structured' | 'ai';
};

type WmeScanMode = 'fast' | 'deep';

type WmeAiStatus = {
  available: boolean;
  service: string;
  model: string;
  detail: string;
};

type WmeAiProposal = {
  field_key: string;
  value: string;
  unit: string;
  reference: string;
  value_status: 'actual' | 'planned' | 'proposed' | 'forecast' | 'unknown';
  location_type: 'wellhead' | 'slot_centre' | 'surface_location' | 'bottomhole' | 'structure_centre' | 'unknown';
  subject_identity_match: 'selected' | 'other' | 'uncertain';
  evidence: string;
};

type WmeAiExtractResponse = {
  well_identity_match: 'match' | 'mismatch' | 'uncertain';
  page_relevance: 'relevant' | 'irrelevant' | 'uncertain';
  proposals: WmeAiProposal[];
  model: string;
};

type WmeExtractionSubmission = {
  job_id: string;
  document_id: string;
  source_name: string;
  state: string;
  cached: boolean;
};

type WmeExtractionJob = {
  job_id: string;
  document_id: string;
  source_name: string;
  state: 'queued' | 'preparing' | 'converting' | 'normalizing' | 'completed' | 'failed';
  stage: string;
  elapsed_seconds: number;
  cached: boolean;
  page_count?: number | null;
  table_count?: number | null;
  error?: string | null;
};

type WmeParsedTable = {
  table_id: string;
  page_number?: number | null;
  rows: string[][];
};

type WmeParsedPage = {
  page_number: number;
  text: string;
  table_ids: string[];
};

type WmeParsedDocument = {
  source_name: string;
  page_count: number;
  pages: WmeParsedPage[];
  tables: WmeParsedTable[];
};

type FieldRule = {
  labels: string[];
  validate: (value: string) => string | null;
  allowBelow?: boolean;
};

function normalize(value: unknown): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function normalizedKey(value: string): string {
  return normalize(value).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function stripOuterPunctuation(value: string): string {
  return normalize(value).replace(/^[\s:=\-–—]+/, '').replace(/[\s,;:]+$/, '');
}

function isNarrative(value: string): boolean {
  const cleaned = normalize(value);
  const words = cleaned.split(/\s+/).filter(Boolean);
  return cleaned.length > 80 || words.length > 10 || /[.!?]\s+[A-Z]/.test(cleaned);
}

function shortIdentifier(value: string): string | null {
  const cleaned = stripOuterPunctuation(value);
  if (!cleaned || cleaned.length > 32 || isNarrative(cleaned)) return null;
  if (!/^[A-Za-z0-9][A-Za-z0-9_./\- ]*[A-Za-z0-9]$/.test(cleaned)) return null;
  return cleaned;
}

function shortText(value: string, maxLength = 50, maxWords = 6): string | null {
  const cleaned = stripOuterPunctuation(value);
  if (!cleaned || cleaned.length > maxLength || cleaned.split(/\s+/).length > maxWords || isNarrative(cleaned)) {
    return null;
  }
  return cleaned;
}

function parseNumber(value: string): number | null {
  const match = value.replace(/,/g, '').match(/[+-]?\d+(?:\.\d+)?/);
  if (!match) return null;
  const parsed = Number(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function canonicalizeMetricUnitTokens(value: string): string {
  const tokens = normalize(value).replace(/\s+/g, ' ').trim().split(' ');
  if (tokens.length < 2) return tokens.join(' ');

  const isMetric = (token: string) => /^(m|metre|metres|meter|meters)$/i.test(token);
  const isFeet = (token: string) => /^(ft|foot|feet)$/i.test(token);
  const isDirection = (token: string) => /^[NSEW]$/i.test(token);

  const output: string[] = [];
  for (const token of tokens) {
    const previous = output[output.length - 1];

    if (previous && ((isMetric(previous) && isMetric(token)) || (isFeet(previous) && isFeet(token)))) {
      continue;
    }

    if (
      output.length >= 2 &&
      isDirection(previous) &&
      ((isMetric(output[output.length - 2]) && isMetric(token)) ||
        (isFeet(output[output.length - 2]) && isFeet(token)))
    ) {
      continue;
    }

    output.push(token);
  }

  return output.join(' ');
}

function numericWithOptionalUnit(
  value: string,
  min: number,
  max: number,
  acceptedUnits: string[] = [],
  unitRequired = false,
): string | null {
  const cleaned = canonicalizeMetricUnitTokens(stripOuterPunctuation(value));
  if (isNarrative(cleaned)) return null;
  const number = parseNumber(cleaned);
  if (number === null || number < min || number > max) return null;
  const unitMatch = cleaned.match(/\b(m|metres?|meters?|ft|feet|deg|degrees?|°)\b/i);
  if (unitRequired && !unitMatch) return null;
  if (unitMatch && acceptedUnits.length > 0) {
    const unit = unitMatch[1].toLowerCase();
    const valid = acceptedUnits.some((candidate) => unit.startsWith(candidate.toLowerCase()));
    if (!valid) return null;
  }
  return cleaned;
}

function validateLatitude(value: string): string | null {
  const cleaned = stripOuterPunctuation(value);
  if (isNarrative(cleaned)) return null;
  const decimal = cleaned.match(/^([+-]?\d{1,2}(?:\.\d+)?)\s*([NS])?$/i);
  if (decimal) {
    const number = Number(decimal[1]);
    return Math.abs(number) <= 90 ? cleaned : null;
  }
  const dms = cleaned.match(/^(\d{1,2})[°º:\s]+(\d{1,2})['′:\s]+(\d{1,2}(?:\.\d+)?)["″]?\s*([NS])$/i);
  if (!dms) return null;
  const deg = Number(dms[1]);
  const min = Number(dms[2]);
  const sec = Number(dms[3]);
  return deg <= 90 && min < 60 && sec < 60 ? cleaned : null;
}

function validateLongitude(value: string): string | null {
  const cleaned = stripOuterPunctuation(value);
  if (isNarrative(cleaned)) return null;
  const decimal = cleaned.match(/^([+-]?\d{1,3}(?:\.\d+)?)\s*([EW])?$/i);
  if (decimal) {
    const number = Number(decimal[1]);
    return Math.abs(number) <= 180 ? cleaned : null;
  }
  const dms = cleaned.match(/^(\d{1,3})[°º:\s]+(\d{1,2})['′:\s]+(\d{1,2}(?:\.\d+)?)["″]?\s*([EW])$/i);
  if (!dms) return null;
  const deg = Number(dms[1]);
  const min = Number(dms[2]);
  const sec = Number(dms[3]);
  return deg <= 180 && min < 60 && sec < 60 ? cleaned : null;
}

function validateUtmZone(value: string): string | null {
  const cleaned = stripOuterPunctuation(value).toUpperCase();
  const match = cleaned.match(/^(?:UTM\s*)?(?:ZONE\s*)?([1-9]|[1-5]\d|60)\s*([C-HJ-NP-X]|NORTH|SOUTH|N|S)?$/);
  if (!match) return null;
  return `${match[1]}${match[2] ? match[2].replace('NORTH', 'N').replace('SOUTH', 'S') : ''}`;
}

function validateCoordinateSystem(value: string): string | null {
  const cleaned = shortText(value, 60, 7);
  if (!cleaned) return null;
  if (!/\b(UTM|Universal Transverse Mercator|geographic|projected|grid)\b/i.test(cleaned)) return null;
  return cleaned;
}

function validateDatum(value: string): string | null {
  const cleaned = shortText(value, 70, 8);
  if (!cleaned) return null;
  if (!/\b(WGS|ED50|European|NAD|datum|ETRS|OSGB|Mean)\b/i.test(cleaned)) return null;
  return cleaned;
}

function validateNorthReference(value: string): string | null {
  const cleaned = shortText(value, 24, 3);
  if (!cleaned) return null;
  if (!/^(grid|true|magnetic)(\s+north)?$/i.test(cleaned)) return null;
  return cleaned;
}

function validateGridConvergence(value: string): string | null {
  const cleaned = stripOuterPunctuation(value);
  if (isNarrative(cleaned)) return null;
  if (!/[°]|deg(?:ree)?s?/i.test(cleaned)) return null;
  const number = parseNumber(cleaned);
  return number !== null && number >= -15 && number <= 15 ? cleaned : null;
}

function validateElevation(value: string): string | null {
  return numericWithOptionalUnit(value, -1000, 10000, ['m', 'met', 'ft', 'fee'], true);
}

function validateWaterDepth(value: string): string | null {
  return numericWithOptionalUnit(value, 0, 12000, ['m', 'met', 'ft', 'fee'], true);
}

function validateMethod(value: string): string | null {
  const cleaned = shortText(value, 45, 5);
  if (!cleaned) return null;
  if (!/\b(minimum curvature|balanced tangential|radius of curvature|tangential|average angle)\b/i.test(cleaned)) {
    return null;
  }
  return cleaned;
}


type EvidenceStatus = 'actual' | 'planned' | 'proposed' | 'forecast' | 'historical' | 'unknown';

const IDENTITY_CONTEXT_FIELDS = new Set([
  'well_name', 'wellbore_name', 'uwi', 'field', 'site', 'block', 'operator', 'country',
]);

const ACTUAL_ONLY_FIELDS = new Set([
  'well_status', 'latitude', 'longitude', 'northing', 'easting', 'coordinate_system',
  'utm_zone', 'geodetic_datum', 'epsg_code', 'north_reference', 'grid_convergence',
  'depth_unit', 'data_start_md', 'data_end_md', 'depth_reference', 'depth_reference',
  'reference_elevation', 'water_depth', 'wellhead_depth_below_reference', 'trajectory_source',
  'survey_status', 'survey_type', 'calculation_method', 'station_count', 'survey_start_md',
  'survey_end_md', 'survey_end_tvd', 'maximum_inclination', 'final_north_offset', 'final_east_offset',
]);

function normalizeWellIdentifier(value: string): string {
  return stripOuterPunctuation(value)
    .replace(
      /^(?:well(?:bore)?(?:\s+(?:name|number|no\.?|id|identifier))?|borehole(?:\s+(?:name|number|no\.?|id))?|no\.?|number)\s*[:#.\-]?\s*/i,
      '',
    )
    .replace(/\s+/g, ' ')
    .trim();
}

function validateCategoricalName(value: string): string | null {
  const cleaned = shortText(value, 55, 5);
  if (!cleaned) return null;
  if (/[.!?;]/.test(cleaned)) return null;
  if (/\b(?:is|are|was|were|will|shall|should|would|could|has|have|had|located|placed|drilled|dialog|staff|approximately|based|through|during|from|into)\b/i.test(cleaned)) return null;
  if (!/[A-Za-zÀ-ÖØ-öø-ÿ]/.test(cleaned)) return null;
  return cleaned;
}

function classifyEvidenceStatus(text: string): EvidenceStatus {
  const normalized = normalize(text).toLowerCase();

  if (/\b(?:as[- ]drilled|as built|final well report|completion report|end of well report|actual|measured|logged|surveyed|reached td|date abandoned|date completed)\b/.test(normalized)) return 'actual';
  if (/\b(?:recommendation to drill|drilling recommendation|well proposal|proposed well|planned well|well plan|drilling programme|drilling program|geological prognosis|prognos(?:is|ed|ticat(?:ed|ion))|planned|to be drilled|will be drilled|temporarily set|expected|budgeted)\b/.test(normalized)) return 'planned';
  if (/\b(?:proposed|proposal|optional|candidate|alternative target|guide point)\b/.test(normalized)) return 'proposed';
  if (/\b(?:forecast|predicted|anticipated|estimated)\b/.test(normalized)) return 'forecast';
  if (/\b(?:offset well|reference well|historical|previous well|nearby well|surrounding well)\b/.test(normalized)) return 'historical';
  return 'unknown';
}

function documentEvidenceStatus(blocks: SourceBlock[]): EvidenceStatus {
  return classifyEvidenceStatus(
    blocks.slice(0, Math.min(blocks.length, 6)).map((block) => block.text).join('\n'),
  );
}

function effectiveEvidenceStatus(documentStatus: EvidenceStatus, blockText: string): EvidenceStatus {
  const blockStatus = classifyEvidenceStatus(blockText);
  return blockStatus !== 'unknown' ? blockStatus : documentStatus;
}

function statusAllowsField(fieldKey: string, status: EvidenceStatus, documentStatus: EvidenceStatus): boolean {
  if (IDENTITY_CONTEXT_FIELDS.has(fieldKey)) return true;
  if (!ACTUAL_ONLY_FIELDS.has(fieldKey)) return true;
  if (status === 'actual') return true;
  if (status === 'planned' || status === 'proposed' || status === 'forecast' || status === 'historical') return false;
  return !['planned', 'proposed', 'forecast', 'historical'].includes(documentStatus);
}

function normalizeStoredFieldValue(fieldKey: string, value: string): string {
  const canonical = canonicalizeStoredMetadataValue(value);
  return fieldKey === 'well_name' || fieldKey === 'wellbore_name'
    ? normalizeWellIdentifier(canonical)
    : canonical;
}

const FIELD_RULES: Record<string, FieldRule> = {
  well_name: {
    labels: ['well name', 'well identifier', 'well'],
    validate: shortIdentifier,
  },
  wellbore_name: {
    labels: ['wellbore name', 'well bore name'],
    validate: shortIdentifier,
  },
  well_status: {
    labels: ['final well status', 'well status'],
    validate: (value) => {
      const cleaned = shortText(value, 30, 4);
      return cleaned && /^(p\s*&\s*a|plugged and abandoned|abandoned|completed|suspended|producing|producer|observation)$/i.test(cleaned)
        ? cleaned.replace(/^p\s*&\s*a$/i, 'P&A')
        : null;
    },
  },
  uwi: {
    labels: ['uwi', 'unique well identifier'],
    validate: shortIdentifier,
  },
  field: {
    labels: ['field name', 'field'],
    validate: (value) => shortText(value, 45, 5),
  },
  operator: {
    labels: ['operator name', 'operator'],
    validate: (value) => shortText(value, 55, 6),
  },
  country: {
    labels: ['country'],
    validate: (value) => shortText(value, 35, 3),
  },
  latitude: {
    labels: ['wellhead latitude', 'latitude'],
    validate: validateLatitude,
  },
  longitude: {
    labels: ['wellhead longitude', 'longitude'],
    validate: validateLongitude,
  },
  northing: {
    labels: ['wellhead northing', 'surface northing'],
    validate: (value) => numericWithOptionalUnit(value, 0, 10000000, ['m', 'met'], false),
  },
  easting: {
    labels: ['wellhead easting', 'surface easting'],
    validate: (value) => numericWithOptionalUnit(value, 0, 1000000, ['m', 'met'], false),
  },
  coordinate_system: {
    labels: ['coordinate system', 'map system', 'map projection'],
    validate: validateCoordinateSystem,
  },
  utm_zone: {
    labels: ['utm zone'],
    validate: validateUtmZone,
  },
  geodetic_datum: {
    labels: ['geodetic datum', 'map datum'],
    validate: validateDatum,
  },
  north_reference: {
    labels: ['north reference'],
    validate: validateNorthReference,
  },
  grid_convergence: {
    labels: ['grid convergence'],
    validate: validateGridConvergence,
  },
  reference_elevation: {
    labels: ['reference elevation', 'rt to msl', 'kb to msl', 'rkb to msl', 'rotary table elevation', 'kelly bushing elevation'],
    validate: validateElevation,
  },
  surface_seabed_elevation: {
    labels: ['surface elevation', 'ground elevation', 'seabed elevation', 'mudline elevation', 'msl to seabed'],
    validate: validateElevation,
  },
  water_depth: {
    labels: ['water depth', 'msl to seabed'],
    validate: validateWaterDepth,
  },
  seabed_depth_below_reference: {
    labels: ['rt to seabed', 'kb to seabed', 'rkb to seabed', 'reference to seabed'],
    validate: validateWaterDepth,
  },
  wellhead_depth_below_reference: {
    labels: ['wellhead depth', 'top of wellhead', 'rt to wellhead', 'kb to wellhead'],
    validate: validateWaterDepth,
  },
  depth_reference: {
    labels: ['depth reference', 'md reference', 'tvd reference'],
    validate: (value) => {
      const cleaned = shortText(value, 60, 4);
      return cleaned && /(RKB|RT|rotary table|kelly bushing|ground level|GL|MSL)/i.test(cleaned) ? cleaned : null;
    },
  },
  total_depth_md: {
    labels: ['total measured', 'total measured depth', 'total depth md', 'td md'],
    validate: (value) => numericWithOptionalUnit(value, 1, 20000, ['m', 'met', 'ft', 'fee'], false),
  },
  total_depth_tvd: {
    labels: ['total vertical depth', 'total depth tvd', 'td tvd'],
    validate: (value) => numericWithOptionalUnit(value, 1, 20000, ['m', 'met', 'ft', 'fee'], false),
  },
  survey_start_md: { labels: ['survey start md', 'first survey md'], validate: (value) => numericWithOptionalUnit(value, -1000, 20000, ['m', 'met', 'ft', 'fee'], false) },
  survey_end_md: { labels: ['survey end md', 'final survey md'], validate: (value) => numericWithOptionalUnit(value, -1000, 20000, ['m', 'met', 'ft', 'fee'], false) },
  survey_start_tvd: { labels: ['survey start tvd', 'first survey tvd'], validate: (value) => numericWithOptionalUnit(value, -1000, 20000, ['m', 'met', 'ft', 'fee'], false) },
  survey_end_tvd: { labels: ['survey end tvd', 'final survey tvd'], validate: (value) => numericWithOptionalUnit(value, -1000, 20000, ['m', 'met', 'ft', 'fee'], false) },
  data_start_md: { labels: ['data start md', 'log start md', 'curve start md'], validate: (value) => numericWithOptionalUnit(value, -1000, 20000, ['m', 'met', 'ft', 'fee'], false) },
  data_end_md: { labels: ['data end md', 'log end md', 'curve end md'], validate: (value) => numericWithOptionalUnit(value, -1000, 20000, ['m', 'met', 'ft', 'fee'], false) },
  trajectory_source: { labels: ['trajectory source', 'survey source', 'deviation source'], validate: (value) => shortText(value, 80, 10) },
  survey_status: { labels: ['survey status', 'trajectory status'], validate: (value) => shortText(value, 35, 5) },
  survey_type: { labels: ['survey type', 'trajectory type'], validate: (value) => shortText(value, 55, 7) },
  station_count: {
    labels: ['station count', 'number of stations', 'survey stations'],
    validate: (value) => { const n = parseNumber(stripOuterPunctuation(value)); return n !== null && Number.isInteger(n) && n >= 1 && n <= 100000 ? String(n) : null; },
  },
  first_md: { labels: ['first md', 'start md', 'minimum md'], validate: (value) => numericWithOptionalUnit(value, -1000, 20000, ['m', 'met', 'ft', 'fee'], false) },
  maximum_inclination: { labels: ['maximum inclination', 'max inclination'], validate: (value) => numericWithOptionalUnit(value, 0, 180, ['deg', 'degree'], false) },
  final_north_offset: { labels: ['final north offset', 'north offset'], validate: (value) => numericWithOptionalUnit(value, -100000, 100000, ['m', 'met', 'ft', 'fee'], false) },
  final_east_offset: { labels: ['final east offset', 'east offset'], validate: (value) => numericWithOptionalUnit(value, -100000, 100000, ['m', 'met', 'ft', 'fee'], false) },
  calculation_method: {
    labels: ['survey calculation method', 'calculation method', 'survey method'],
    validate: validateMethod,
  },
};

function detectHeaders(rows: unknown[][]): { headerRow: number; columns: Record<string, number> } | null {
  for (let i = 0; i < Math.min(rows.length, 25); i += 1) {
    const labels = rows[i].map((cell) => normalizedKey(normalize(cell)));
    const fieldKey = labels.findIndex((label) => label === 'field key');
    const value = labels.findIndex((label) => label === 'value');
    if (fieldKey >= 0 && value >= 0) {
      const indexOf = (name: string) => labels.findIndex((label) => label === name);
      return {
        headerRow: i,
        columns: {
          section: indexOf('section'),
          field: indexOf('field'),
          fieldKey,
          value,
          unit: indexOf('unit'),
          source: indexOf('source'),
          sourceReference: indexOf('source reference'),
          notes: indexOf('notes'),
          aiRecommendedValue: indexOf('ai recommended value'),
          aiUnit: indexOf('ai unit'),
          aiSource: indexOf('ai source'),
          aiSourceReference: indexOf('ai source reference'),
          aiEvidence: indexOf('ai evidence'),
          aiConfidence: indexOf('ai confidence'),
          aiStatus: indexOf('ai status'),
        },
      };
    }
  }
  return null;
}

function rowsFromWorkbook(workbook: XLSX.WorkBook): { sheetName: string; rows: ContextRow[] } {
  const sheetName = workbook.SheetNames.includes('Well Info') ? 'Well Info' : workbook.SheetNames[0];
  if (!sheetName) throw new Error('The workbook contains no worksheets.');
  const sheet = workbook.Sheets[sheetName];
  const data = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, raw: false, defval: '' });
  const headers = detectHeaders(data);
  if (!headers) throw new Error('Could not find the Field Key and Value columns.');
  const read = (row: unknown[], index: number) => index >= 0 ? normalize(row[index]) : '';
  const rows = data.slice(headers.headerRow + 1).map((row, offset) => ({
    rowNumber: headers.headerRow + offset + 2,
    section: read(row, headers.columns.section),
    field: read(row, headers.columns.field),
    fieldKey: read(row, headers.columns.fieldKey),
    value: read(row, headers.columns.value),
    unit: read(row, headers.columns.unit),
    source: read(row, headers.columns.source),
    sourceReference: read(row, headers.columns.sourceReference),
    notes: read(row, headers.columns.notes),
    aiRecommendedValue: read(row, headers.columns.aiRecommendedValue),
    aiUnit: read(row, headers.columns.aiUnit),
    aiSource: read(row, headers.columns.aiSource),
    aiSourceReference: read(row, headers.columns.aiSourceReference),
    aiEvidence: read(row, headers.columns.aiEvidence),
    aiConfidence: read(row, headers.columns.aiConfidence),
    aiStatus: read(row, headers.columns.aiStatus),
  })).filter((row) => row.fieldKey);
  const legacyKeys = rows.map((row) => row.fieldKey).filter((key) => LEGACY_WELL_INFO_FIELD_KEYS.has(key));
  if (legacyKeys.length > 0) {
    throw new Error(`Legacy Well Info template detected (${[...new Set(legacyKeys)].join(', ')}). Export a Version ${WELL_INFO_SCHEMA_VERSION} template from Well Information.`);
  }
  const unsupportedKeys = rows.map((row) => row.fieldKey).filter((key) => key && !CANONICAL_WELL_INFO_FIELD_KEYS.has(key));
  if (unsupportedKeys.length > 0) {
    throw new Error(`Unsupported Well Info field key(s): ${[...new Set(unsupportedKeys)].join(', ')}.`);
  }
  return { sheetName, rows };
}

type ScanProgress = {
  fileName: string;
  fileIndex: number;
  fileCount: number;
  pageNumber: number;
  pageCount: number;
  mode: 'text' | 'ocr';
};

const sourceBlockCache = new WeakMap<File, Partial<Record<WmeScanMode, Promise<SourceBlock[]>>>>();

const FAST_SCAN_MAX_OCR_PAGES = 12;
const FAST_SCAN_DISCOVERY_PAGE_BUDGET = 4;
const FAST_SCAN_REFERENCED_PAGE_BUDGET = 6;
const FAST_SCAN_FALLBACK_PAGE_BUDGET = 2;

function pageTextFromItems(
  items: Array<{ text: string; x: number; y: number }>,
): { rows: string[][]; text: string } {
  const grouped = new Map<number, Array<{ text: string; x: number }>>();
  for (const item of items) {
    const key = Math.round(item.y / 3) * 3;
    const row = grouped.get(key) ?? [];
    row.push({ text: item.text, x: item.x });
    grouped.set(key, row);
  }

  const rows = [...grouped.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([, row]) => row.sort((a, b) => a.x - b.x).map((item) => item.text));

  return {
    rows,
    text: rows.map((row) => row.join(' | ')).join('\n'),
  };
}

const FAST_SCAN_METADATA_TERMS = [
  'well data',
  'well summary',
  'general well data',
  'final well report',
  'end of well report',
  'well status',
  'wellhead',
  'coordinate',
  'northing',
  'easting',
  'latitude',
  'longitude',
  'datum',
  'utm zone',
  'survey',
  'directional',
  'trajectory',
  'total depth',
  'final depth',
  'final md',
  'final tvd',
  'water depth',
  'kb elevation',
  'rt elevation',
  'formation tops',
  'permanent abandonment',
  'completion summary',
];

function metadataReferenceScore(text: string): number {
  const normalized = normalize(text).toLowerCase();
  let score = 0;

  for (const term of FAST_SCAN_METADATA_TERMS) {
    if (normalized.includes(term)) score += term.includes(' ') ? 3 : 1;
  }

  score += (normalized.match(/\b(?:md|tvd|tvdss|rkb|kb|msl|utm|epsg)\b/g) ?? []).length;
  score += Math.min(4, (normalized.match(/\b\d{1,3}\b/g) ?? []).length);

  return score;
}

function referencedMetadataPages(text: string, pageCount: number): number[] {
  const candidates: Array<{ pageNumber: number; score: number }> = [];

  for (const rawLine of text.split(/\r?\n/)) {
    const line = normalize(rawLine);
    const score = metadataReferenceScore(line);
    if (score < 3) continue;

    const numberMatches = [...line.matchAll(/\b(\d{1,3})\b/g)];
    for (const match of numberMatches) {
      const pageNumber = Number(match[1]);
      if (pageNumber < 1 || pageNumber > pageCount) continue;
      candidates.push({ pageNumber, score });
    }
  }

  return candidates
    .sort((a, b) => b.score - a.score || a.pageNumber - b.pageNumber)
    .map((candidate) => candidate.pageNumber);
}

function initialFastOcrPages(pageCount: number, lowTextPages: number[]): number[] {
  const lowText = new Set(lowTextPages);
  const selected: number[] = [];

  for (
    let pageNumber = 1;
    pageNumber <= Math.min(FAST_SCAN_DISCOVERY_PAGE_BUDGET, pageCount);
    pageNumber += 1
  ) {
    if (lowText.has(pageNumber)) selected.push(pageNumber);
  }

  return selected;
}

function fallbackFastOcrPages(pageCount: number, lowTextPages: number[]): number[] {
  const lowText = new Set(lowTextPages);
  const priorities = [
    Math.round(pageCount * 0.25),
    Math.round(pageCount * 0.40),
    Math.round(pageCount * 0.50),
    Math.round(pageCount * 0.65),
    Math.round(pageCount * 0.80),
    pageCount,
  ];

  return priorities
    .map((pageNumber) => Math.max(1, Math.min(pageCount, pageNumber)))
    .filter((pageNumber, index, values) =>
      lowText.has(pageNumber) && values.indexOf(pageNumber) === index,
    );
}



async function ocrPdfPage(
  page: any,
  worker: Awaited<ReturnType<typeof createWorker>>,
): Promise<{ rows: string[][]; text: string }> {
  const viewport = page.getViewport({ scale: 1.35 });
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return { rows: [], text: '' };

  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  await page.render({ canvasContext: context, viewport }).promise;
  const result = await worker.recognize(canvas);
  const text = normalize(result.data.text).replace(/\s{2,}/g, '\n');

  return {
    rows: text.split(/\r?\n/).map((line) => [normalize(line)]).filter((row) => row[0]),
    text,
  };
}

async function extractPdfBlocks(
  file: File,
  scanMode: WmeScanMode,
  onProgress?: (progress: ScanProgress) => void,
  fileIndex = 1,
  fileCount = 1,
): Promise<SourceBlock[]> {
  const pdf = await getCachedPdfDocument(file);
  const blocks: SourceBlock[] = [];
  const lowTextPages: number[] = [];

  // Stage 1: index every page's embedded text layer. This is intentionally
  // lightweight and gives Fast Scan complete document coverage without OCR.
  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    const items = content.items
      .filter((item): item is typeof item & { str: string; transform: number[] } =>
        'str' in item && 'transform' in item
      )
      .map((item) => ({
        text: normalize(item.str),
        x: Number(item.transform[4] ?? 0),
        y: Number(item.transform[5] ?? 0),
      }))
      .filter((item) => item.text);

    const parsed = pageTextFromItems(items);
    const usableText = parsed.text.replace(/[^A-Za-z0-9]/g, '').length;
    if (usableText < 45) lowTextPages.push(pageNumber);

    blocks.push({
      reference: `Page ${pageNumber}`,
      rows: parsed.rows,
      text: parsed.text,
      extraction: 'text',
    });

    onProgress?.({
      fileName: file.name,
      fileIndex,
      fileCount,
      pageNumber,
      pageCount: pdf.numPages,
      mode: 'text',
    });
  }

  const lowTextSet = new Set(lowTextPages);
  const discoveryPages =
    scanMode === 'fast'
      ? initialFastOcrPages(pdf.numPages, lowTextPages)
      : [...lowTextPages];

  if (discoveryPages.length === 0) return blocks;

  let ocrWorker: Awaited<ReturnType<typeof createWorker>> | null = null;
  try {
    ocrWorker = await createWorker('eng');
    const completed = new Set<number>();

    const ocrOne = async (pageNumber: number) => {
      if (completed.has(pageNumber)) return '';
      completed.add(pageNumber);

      onProgress?.({
        fileName: file.name,
        fileIndex,
        fileCount,
        pageNumber,
        pageCount: pdf.numPages,
        mode: 'ocr',
      });

      const page = await pdf.getPage(pageNumber);
      const parsed = await ocrPdfPage(page, ocrWorker!);

      if (parsed.text) {
        blocks[pageNumber - 1] = {
          reference: `Page ${pageNumber}`,
          rows: parsed.rows,
          text: parsed.text,
          extraction: 'ocr',
        };
      }

      return parsed.text;
    };

    if (scanMode === 'deep') {
      for (const pageNumber of discoveryPages) {
        await ocrOne(pageNumber);
      }
      return blocks;
    }

    // Phase 1: front matter and contents discovery.
    const discoveryText: string[] = [];
    for (const pageNumber of discoveryPages) {
      discoveryText.push(await ocrOne(pageNumber));
    }

    // Phase 2: deterministic metadata-page references found in front matter.
    const referencedCandidates: number[] = [];
    for (const text of discoveryText) {
      for (const printedPage of referencedMetadataPages(text, pdf.numPages)) {
        // Printed report numbering often differs from PDF indexing.
        for (const offset of [0, 1, 2, -1]) {
          const candidate = printedPage + offset;
          if (
            candidate >= 1 &&
            candidate <= pdf.numPages &&
            lowTextSet.has(candidate) &&
            !completed.has(candidate) &&
            !referencedCandidates.includes(candidate)
          ) {
            referencedCandidates.push(candidate);
          }
        }
      }
    }

    for (const pageNumber of referencedCandidates.slice(0, FAST_SCAN_REFERENCED_PAGE_BUDGET)) {
      await ocrOne(pageNumber);
    }

    // Phase 3: bounded fallback, never allowed to consume discovery/reference budgets.
    const fallbackCandidates = fallbackFastOcrPages(pdf.numPages, lowTextPages)
      .filter((pageNumber) => !completed.has(pageNumber))
      .slice(0, FAST_SCAN_FALLBACK_PAGE_BUDGET);

    for (const pageNumber of fallbackCandidates) {
      await ocrOne(pageNumber);
    }

    // If front matter contained no page references, fill only the unused
    // referenced budget with the strongest remaining low-text candidates.
    const remainingBudget = FAST_SCAN_MAX_OCR_PAGES - completed.size;
    if (remainingBudget > 0 && referencedCandidates.length === 0) {
      for (const pageNumber of lowTextPages) {
        if (completed.has(pageNumber)) continue;
        await ocrOne(pageNumber);
        if (completed.size >= FAST_SCAN_MAX_OCR_PAGES) break;
      }
    }
  } finally {
    await ocrWorker?.terminate();
  }

  return blocks;
}

async function extractSpreadsheetBlocks(file: File): Promise<SourceBlock[]> {
  const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' });
  return workbook.SheetNames.map((sheetName) => {
    const rows = XLSX.utils.sheet_to_json<unknown[]>(workbook.Sheets[sheetName], {
      header: 1,
      raw: false,
      defval: '',
    }).map((row) => row.map(normalize).filter(Boolean));
    return {
      reference: `Sheet ${sheetName}`,
      rows,
      text: rows.map((row) => row.join(' | ')).join('\n'),
      extraction: 'structured',
    };
  });
}

async function extractDelimitedBlocks(file: File): Promise<SourceBlock[]> {
  const raw = await file.text();
  const workbook = XLSX.read(raw, { type: 'string' });
  const first = workbook.SheetNames[0];
  if (!first) return [{
    reference: 'File text',
    rows: raw.split(/\r?\n/).map((line) => [normalize(line)]),
    text: raw,
    extraction: 'structured',
  }];

  const rows = XLSX.utils.sheet_to_json<unknown[]>(workbook.Sheets[first], {
    header: 1,
    raw: false,
    defval: '',
  }).map((row) => row.map(normalize).filter(Boolean));

  return [{
    reference: 'File rows',
    rows,
    text: rows.map((row) => row.join(' | ')).join('\n'),
    extraction: 'structured',
  }];
}

function extractionApiUrl(path: string): string {
  if (window.location.port === '5173' || window.location.port === '5174' || window.location.port === '5175') {
    return `${window.location.protocol}//${window.location.hostname}:8001${path}`;
  }
  return path;
}

async function fetchExtractionJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(extractionApiUrl(path), init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json() as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // Preserve the HTTP status when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function extractPdfBlocksWithBackend(
  file: File,
  onProgress?: (progress: ScanProgress) => void,
  fileIndex = 1,
  fileCount = 1,
): Promise<SourceBlock[]> {
  const formData = new FormData();
  formData.append('file', file, file.name);
  const submission = await fetchExtractionJson<WmeExtractionSubmission>(
    '/api/wme/extraction/documents',
    { method: 'POST', body: formData },
  );

  for (;;) {
    const job = await fetchExtractionJson<WmeExtractionJob>(
      `/api/wme/extraction/jobs/${encodeURIComponent(submission.job_id)}`,
    );
    onProgress?.({
      fileName: file.name,
      fileIndex,
      fileCount,
      pageNumber: job.page_count ?? 0,
      pageCount: job.page_count ?? 0,
      mode: 'text',
    });
    if (job.state === 'completed') break;
    if (job.state === 'failed') throw new Error(job.error || 'Document extraction failed.');
    await wait(1000);
  }

  const document = await fetchExtractionJson<WmeParsedDocument>(
    `/api/wme/extraction/jobs/${encodeURIComponent(submission.job_id)}/document`,
  );
  const tablesByPage = new Map<number, WmeParsedTable[]>();
  for (const table of document.tables) {
    if (typeof table.page_number !== 'number') continue;
    const pageTables = tablesByPage.get(table.page_number) ?? [];
    pageTables.push(table);
    tablesByPage.set(table.page_number, pageTables);
  }

  return document.pages
    .slice()
    .sort((a, b) => a.page_number - b.page_number)
    .map((page) => {
      const tableRows = (tablesByPage.get(page.page_number) ?? []).flatMap((table) => table.rows ?? []);
      const textRows = page.text
        .split(/\r?\n/)
        .map((line) => [normalize(line)])
        .filter((row) => row[0]);
      const rows = [...tableRows, ...textRows];
      const tableText = tableRows.map((row) => row.map(normalize).join(' | ')).join('\n');
      return {
        reference: `Page ${page.page_number}`,
        rows,
        text: [page.text, tableText].filter(Boolean).join('\n'),
        extraction: 'structured' as const,
      };
    });
}

async function extractSourceBlocks(
  file: File,
  scanMode: WmeScanMode,
  onProgress?: (progress: ScanProgress) => void,
  fileIndex = 1,
  fileCount = 1,
): Promise<SourceBlock[]> {
  const modeCache = sourceBlockCache.get(file) ?? {};
  const cached = modeCache[scanMode];
  if (cached) return cached;

  const extractionPromise = (async () => {
    const lower = file.name.toLowerCase();
    if (lower.endsWith('.pdf')) {
      const legacyPdfCompatibilityEnabled =
        window.localStorage.getItem('wmeLegacyPdfExtraction') === 'enabled';
      if (legacyPdfCompatibilityEnabled) {
        return extractPdfBlocks(file, scanMode, onProgress, fileIndex, fileCount);
      }
      return extractPdfBlocksWithBackend(file, onProgress, fileIndex, fileCount);
    }
    if (lower.endsWith('.xlsx') || lower.endsWith('.xls')) {
      return extractSpreadsheetBlocks(file);
    }
    return extractDelimitedBlocks(file);
  })();

  modeCache[scanMode] = extractionPromise;
  sourceBlockCache.set(file, modeCache);

  try {
    return await extractionPromise;
  } catch (error) {
    delete modeCache[scanMode];
    if (Object.keys(modeCache).length === 0) sourceBlockCache.delete(file);
    throw error;
  }
}


function wmeApiUrl(path: string): string {
  if (window.location.port === '5173') return `http://127.0.0.1:8001${path}`;
  return path;
}

async function fetchWmeJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(wmeApiUrl(path), init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json() as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // Preserve the HTTP status when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function downloadWmeDiagnostic(payload: unknown): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `WME_DIAGNOSTIC_${stamp}.json`;
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return filename;
}

function pageHasExplicitUnresolvedLabel(block: SourceBlock, unresolvedFields: string[]): boolean {
  const textKey = normalizedKey(block.text);

  return unresolvedFields.some((fieldKey) => {
    const rule = FIELD_RULES[fieldKey];
    if (!rule) return false;

    if (
      (fieldKey === 'latitude' || fieldKey === 'longitude') &&
      /\bgeographic\b/i.test(block.text)
    ) {
      return true;
    }

    return rule.labels.some((label) => {
      const labelKey = normalizedKey(label);
      return labelKey.length > 0 && textKey.includes(labelKey);
    });
  });
}

function pageNumberFromReference(reference: string): number | null {
  const match = reference.match(/^Page\s+(\d+)$/i);
  if (!match) return null;
  const pageNumber = Number(match[1]);
  return Number.isInteger(pageNumber) && pageNumber > 0 ? pageNumber : null;
}

function relevantPageScore(block: SourceBlock, fieldKeys: string[]): number {
  const haystack = normalizedKey(block.text);
  if (!haystack) return 0;

  let score = 0;
  for (const fieldKey of fieldKeys) {
    const rule = FIELD_RULES[fieldKey];
    for (const label of rule?.labels ?? []) {
      if (haystack.includes(normalizedKey(label))) score += 5;
    }
  }

  const generalIndicators = [
    'general well data',
    'well information',
    'well summary',
    'geological summary',
    'final well report',
    'well data',
    'well:',
    'field',
    'country',
    'well status',
    'well coordinates',
    'kb elevation',
    'date spudded',
    'date abandoned',
    'total depth driller',
    'total depth logger',
    'coordinates',
    'coordinate reference',
    'surface location',
    'slot centre',
    'slot center',
    'wellhead',
    'latitude',
    'longitude',
    'northing',
    'easting',
    'water depth',
    'kelly bushing',
    'rotary table',
    'depth reference',
    'total depth',
    'final status',
    'datum',
    'projection',
  ];
  for (const indicator of generalIndicators) {
    if (haystack.includes(normalizedKey(indicator))) score += 2;
  }
  return score;
}


function metadataSummaryPageScore(block: SourceBlock): number {
  const haystack = normalizedKey(block.text);
  if (!haystack) return 0;

  const indicators = [
    'geological summary',
    'final well report',
    'well summary',
    'general well data',
    'well information',
    'well coordinates',
    'kb elevation',
    'water depth',
    'total depth driller',
    'total depth logger',
    'date spudded',
    'date abandoned',
    'well status',
    'country',
    'field',
  ];

  let score = 0;
  for (const indicator of indicators) {
    if (haystack.includes(normalizedKey(indicator))) score += 1;
  }
  return score;
}

function shouldRenderMetadataPageImage(block: SourceBlock, relevanceScore: number): boolean {
  return metadataSummaryPageScore(block) >= 3 || relevanceScore >= 12;
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}

const pdfDocumentCache = new WeakMap<File, ReturnType<typeof getDocument>['promise']>();
const pdfPageImageCache = new Map<string, Promise<string>>();

function canvasToJpegBase64(canvas: HTMLCanvasElement, pageNumber: number): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error(`Unable to encode page ${pageNumber} for local AI.`));
          return;
        }

        const reader = new FileReader();
        reader.onerror = () => reject(new Error(`Unable to read encoded page ${pageNumber} for local AI.`));
        reader.onload = () => {
          const dataUrl = String(reader.result ?? '');
          const comma = dataUrl.indexOf(',');
          if (comma < 0) {
            reject(new Error(`Unable to encode page ${pageNumber} for local AI.`));
            return;
          }
          resolve(dataUrl.slice(comma + 1));
        };
        reader.readAsDataURL(blob);
      },
      'image/jpeg',
      0.78,
    );
  });
}

function pdfCacheKey(file: File, pageNumber: number): string {
  return `${file.name}:${file.size}:${file.lastModified}:${pageNumber}`;
}

async function getCachedPdfDocument(file: File) {
  const cached = pdfDocumentCache.get(file);
  if (cached) return cached;

  const loadingPromise = (async () => {
    const bytes = new Uint8Array(await withTimeout(
      file.arrayBuffer(),
      30_000,
      `Timed out reading ${file.name} for local AI.`,
    ));

    const loadingTask = getDocument({ data: bytes });
    return withTimeout(
      loadingTask.promise,
      45_000,
      `Timed out opening ${file.name} for local AI.`,
    );
  })();

  pdfDocumentCache.set(file, loadingPromise);
  return loadingPromise;
}

async function renderPdfPageBase64(file: File, pageNumber: number): Promise<string> {
  const cacheKey = pdfCacheKey(file, pageNumber);
  const cached = pdfPageImageCache.get(cacheKey);
  if (cached) return cached;

  const renderPromise = (async () => {
    const pdf = await getCachedPdfDocument(file);
    const page = await withTimeout(
      pdf.getPage(pageNumber),
      20_000,
      `Timed out loading page ${pageNumber} for local AI.`,
    );

    const viewport = page.getViewport({ scale: 1.15 });
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d', { alpha: false });
    if (!context) throw new Error(`Unable to render page ${pageNumber} for local AI.`);

    canvas.width = Math.ceil(viewport.width);
    canvas.height = Math.ceil(viewport.height);

    await withTimeout(
      page.render({ canvasContext: context, viewport }).promise,
      45_000,
      `Timed out rendering page ${pageNumber} for local AI.`,
    );

    return withTimeout(
      canvasToJpegBase64(canvas, pageNumber),
      30_000,
      `Timed out encoding page ${pageNumber} for local AI.`,
    );
  })();

  pdfPageImageCache.set(cacheKey, renderPromise);

  try {
    return await renderPromise;
  } catch (error) {
    pdfPageImageCache.delete(cacheKey);
    throw error;
  }
}

function canonicalizeStoredMetadataValue(value: string): string {
  const tokens = normalize(value).replace(/\s+/g, ' ').trim().split(' ');
  if (tokens.length < 2) return tokens.join(' ');

  const isMetric = (token: string) =>
    /^(m|metre|metres|meter|meters)$/i.test(token);
  const isFeet = (token: string) =>
    /^(ft|foot|feet)$/i.test(token);
  const isDirection = (token: string) =>
    /^[NSEW]$/i.test(token);

  const output: string[] = [];

  for (const token of tokens) {
    const previous = output[output.length - 1];

    if (
      previous &&
      ((isMetric(previous) && isMetric(token)) ||
        (isFeet(previous) && isFeet(token)))
    ) {
      continue;
    }

    if (
      output.length >= 2 &&
      isDirection(previous) &&
      ((isMetric(output[output.length - 2]) && isMetric(token)) ||
        (isFeet(output[output.length - 2]) && isFeet(token)))
    ) {
      continue;
    }

    output.push(token);
  }

  return output.join(' ');
}

function groupThousands(value: string): string {
  const match = value.replace(/\s+/g, '').match(/^([+-]?)(\d+)(?:\.(\d+))?$/);
  if (!match) return value;

  const [, sign, integer, decimal = ''] = match;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return decimal ? `${sign}${grouped}.${decimal}` : `${sign}${grouped}`;
}

function displayMetadataSectionLabel(section: string): string {
  const normalized = normalize(section);
  if (normalized === 'Well Extent') return 'Well Extent (from Reference)';
  if (normalized === 'Survey Extent') return 'Survey Extent (from Reference)';
  if (normalized === 'Data Coverage') return 'Data Coverage (from Reference)';
  return section;
}

function displayMetadataFieldLabel(fieldKey: string, fallback: string): string {
  const labels: Record<string, string> = {
    reference_elevation: 'Reference Elevation (relative to MSL)',
    surface_seabed_elevation: 'Ground / Seabed Elevation (relative to MSL)',
    water_depth: 'Water Depth (below MSL)',
    seabed_depth_below_reference: 'Seabed Depth (below Reference)',
    wellhead_depth_below_reference: 'Top of Wellhead Depth (below Reference)',
    total_depth_md: 'Total Depth MD',
    total_depth_tvd: 'Total Depth TVD',
    survey_start_md: 'Survey Start MD',
    survey_end_md: 'Survey End MD',
    survey_start_tvd: 'Survey Start TVD',
    survey_end_tvd: 'Survey End TVD',
    data_start_md: 'Data Start MD',
    data_end_md: 'Data End MD',
  };
  return labels[fieldKey] || fallback;
}

function formatMetadataValue(fieldKey: string, value: string, unit: string, depthReference = ''): string {
  const cleanedValue = normalize(value);
  const cleanedUnit = normalize(unit);
  void depthReference;

  const coordinateMatch = cleanedValue
    .replace(/\s+/g, ' ')
    .trim()
    .match(/^([+-]?[\d\s,]+(?:\.\d+)?)\s*(?:m)?\s*([NSEW])?$/i);

  if ((fieldKey === 'northing' || fieldKey === 'easting') && coordinateMatch) {
    const numeric = Number(coordinateMatch[1].replace(/[\s,]/g, ''));
    if (Number.isFinite(numeric)) {
      const direction =
        coordinateMatch[2]?.toUpperCase() ||
        (fieldKey === 'northing' ? 'N' : 'E');
      return `${groupThousands(numeric.toFixed(2))} m ${direction}`;
    }
  }

  const depthFields = new Set([
    'data_start_md',
    'data_end_md',
    'reference_elevation',
    'surface_seabed_elevation',
    'water_depth',
    'seabed_depth_below_reference',
    'wellhead_depth_below_reference',
    'total_depth_md',
    'total_depth_tvd',
    'survey_start_md',
    'survey_end_md',
    'survey_start_tvd',
    'survey_end_tvd',
  ]);

  if (depthFields.has(fieldKey)) {
    const numericMatch = cleanedValue.replace(/,/g, '').match(/[+-]?\d+(?:\.\d+)?/);
    if (numericMatch) {
      const numeric = Number(numericMatch[0]);
      if (Number.isFinite(numeric)) {
        const formatted = groupThousands(numeric.toFixed(2));
        const base = cleanedUnit ? `${formatted} ${cleanedUnit}` : formatted;
        return base;
      }
    }
  }

  return displayValueWithWorkbookUnit(cleanedValue, cleanedUnit);
}

function displayValueWithWorkbookUnit(value: string, unit: string): string {
  const cleanedValue = normalize(value);
  const cleanedUnit = normalize(unit);
  if (!cleanedUnit) return cleanedValue;

  const valueKey = cleanedValue.toLowerCase().replace(/\s+/g, ' ').trim();
  const unitKey = cleanedUnit.toLowerCase().replace(/\s+/g, ' ').trim();

  if (
    valueKey === unitKey ||
    valueKey.endsWith(` ${unitKey}`) ||
    ((/(?:^|\s)m\s+[nsew]$/i.test(valueKey)) && /^m$/i.test(unitKey)) ||
    ((/(?:^|\s)ft\s+[nsew]$/i.test(valueKey)) && /^ft$/i.test(unitKey))
  ) {
    return cleanedValue;
  }

  return `${cleanedValue} ${cleanedUnit}`;
}

function proposalValueForValidation(proposal: WmeAiProposal): string {
  let value = normalize(proposal.value);

  if (proposal.field_key === 'northing' || proposal.field_key === 'easting') {
    const coordinate = normalizedCoordinateNumber(value);
    if (coordinate !== null) {
      const direction = proposal.field_key === 'northing' ? 'N' : 'E';
      value = `${coordinate.toFixed(2)} m ${direction}`;
    }
  }
  const unit = normalize(proposal.unit);
  if (!unit) return value;

  const compact = (input: string) =>
    input
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim();

  const valueKey = compact(value);
  const unitKey = compact(unit);
  const escapedUnit = unitKey.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const unitAtEnd = new RegExp(`(?:^|\\s)${escapedUnit}$`, 'i').test(valueKey);
  const directionalMetricAtEnd =
    /(?:^|\s)m\s+[nsew]$/i.test(valueKey) &&
    /^(?:m|m\s+[nsew])$/i.test(unitKey);

  if (
    valueKey === unitKey ||
    valueKey.endsWith(` ${unitKey}`) ||
    unitAtEnd ||
    directionalMetricAtEnd
  ) {
    return value;
  }

  return `${value} ${unit}`;
}

function normalizeFinalProposalValue(fieldKey: string, value: string): string {
  let cleaned = canonicalizeMetricUnitTokens(value);

  const metricFields = new Set([
    'northing',
    'easting',
    'reference_elevation',
    'water_depth',
    'wellhead_depth_below_reference',
    'survey_end_md',
    'survey_end_tvd',
  ]);

  if (!metricFields.has(fieldKey)) return cleaned;

  cleaned = cleaned
    .replace(/\b(m|metres?|meters?)\s+\1\b/gi, '$1')
    .replace(/\b(ft|feet)\s+\1\b/gi, '$1')
    .replace(/\b(m|metres?|meters?)\s+([NSEW])\s+(m|metres?|meters?)\b/gi, '$1 $2')
    .replace(/\b(ft|feet)\s+([NSEW])\s+(ft|feet)\b/gi, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();

  return cleaned;
}

function identityTokens(value: string): string[] {
  const normalized = value.toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim();
  const compact = normalized.replace(/\s+/g, '');
  const tokens = new Set<string>();
  if (normalized) tokens.add(normalized);
  if (compact) tokens.add(compact);
  for (const part of normalized.split(' ')) {
    if (part.length >= 3 && /\d/.test(part)) tokens.add(part);
  }
  return [...tokens];
}

function documentMatchesWell(fileName: string, blocks: SourceBlock[], wellName: string, wellboreName: string): boolean {
  const tokens = [...identityTokens(wellName), ...identityTokens(wellboreName)];
  if (tokens.length === 0) return true;
  const haystack = normalizedKey(`${fileName} ${blocks.slice(0, 3).map((block) => block.text.slice(0, 2500)).join(' ')}`)
    .replace(/\s+/g, '');
  return tokens.some((token) => haystack.includes(token.replace(/\s+/g, '').toLowerCase()));
}

function matchLabelCell(cell: string, label: string): string | null {
  const cellKey = normalizedKey(cell);
  const labelKey = normalizedKey(label);
  if (cellKey === labelKey) return '';
  if (cellKey.startsWith(`${labelKey} `)) {
    const remainder = stripOuterPunctuation(cell.slice(label.length));
    return remainder;
  }
  return null;
}

function candidateFromRows(rule: FieldRule, rows: string[][]): string | null {
  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    for (let cellIndex = 0; cellIndex < row.length; cellIndex += 1) {
      const cell = row[cellIndex];
      for (const label of rule.labels) {
        const inline = matchLabelCell(cell, label);
        if (inline === null) continue;

        const candidates: string[] = [];
        if (inline) candidates.push(inline);
        if (row[cellIndex + 1]) candidates.push(row[cellIndex + 1]);

        if (cellIndex === 0 && row.length === 2 && row[1]) {
          candidates.push(row[1]);
        }

        if (rule.allowBelow !== false && rows[rowIndex + 1]?.[cellIndex]) {
          candidates.push(rows[rowIndex + 1][cellIndex]);
        }

        for (const candidate of candidates) {
          const validated = rule.validate(candidate);
          if (validated) return validated;
        }
      }
    }
  }
  return null;
}


function normalizedComparable(value: string): string {
  return normalize(value).toLowerCase().replace(/,/g, '.').replace(/\s+/g, ' ');
}

function normalizedCoordinateNumber(value: string): number | null {
  const numericText = value
    .replace(/\b(?:metres?|meters?|m)\b/gi, '')
    .replace(/[NSEW]/gi, '')
    .replace(/[\s,]/g, '');
  const numeric = Number(numericText);
  return Number.isFinite(numeric) ? numeric : null;
}

function coordinateBlockCandidates(text: string): Record<string, string> {
  const flat = normalize(text);
  const found: Record<string, string> = {};

  const groupedNumber = String.raw`\d{1,3}(?:[\s,]\d{3})+(?:\.\d+)?`;

  const storePair = (northingText: string, eastingText: string) => {
    const northing = normalizedCoordinateNumber(northingText);
    const easting = normalizedCoordinateNumber(eastingText);

    if (
      northing !== null &&
      easting !== null &&
      northing >= 100000 &&
      northing <= 10000000 &&
      easting >= 10000 &&
      easting <= 1000000
    ) {
      found.northing = `${northing.toFixed(2)} m N`;
      found.easting = `${easting.toFixed(2)} m E`;
    }
  };

  const directionalPair = flat.match(
    new RegExp(
      `(?:UTM|coordinates?|co-ordinates?|surface location|wellhead)` +
      `[^0-9]{0,100}(${groupedNumber})\\s*(?:m|metres?|meters?)?\\s*N\\b` +
      `[^0-9]{0,60}(${groupedNumber})\\s*(?:m|metres?|meters?)?\\s*E\\b`,
      'i',
    ),
  );

  if (directionalPair) {
    storePair(directionalPair[1], directionalPair[2]);
  }

  if (!found.northing || !found.easting) {
    const labelledNorthing = flat.match(
      new RegExp(
        `(?:wellhead|surface|site)?\\s*northing[^0-9]{0,40}(${groupedNumber})` +
        `\\s*(?:m|metres?|meters?)?(?:\\s*N)?\\b`,
        'i',
      ),
    );
    const labelledEasting = flat.match(
      new RegExp(
        `(?:wellhead|surface|site)?\\s*easting[^0-9]{0,40}(${groupedNumber})` +
        `\\s*(?:m|metres?|meters?)?(?:\\s*E)?\\b`,
        'i',
      ),
    );

    if (labelledNorthing && labelledEasting) {
      storePair(labelledNorthing[1], labelledEasting[1]);
    }
  }

  if (!found.northing || !found.easting) {
    const reversedDirectionPair = flat.match(
      new RegExp(
        `\\bN\\s*(${groupedNumber})\\s*(?:m|metres?|meters?)?` +
        `[^0-9]{0,60}\\bE\\s*(${groupedNumber})\\s*(?:m|metres?|meters?)?`,
        'i',
      ),
    );

    if (reversedDirectionPair) {
      storePair(reversedDirectionPair[1], reversedDirectionPair[2]);
    }
  }

  if (found.northing && found.easting && /\bUTM\b/i.test(flat)) {
    found.coordinate_system = 'UTM';
  }

  const explicitZone = flat.match(
    /\bUTM\s+(?:zone\s+)([1-9]|[1-5]\d|60)\s*([C-HJ-NP-X]|NORTH|SOUTH|N|S)?\b/i,
  );
  if (explicitZone) {
    const hemisphere = explicitZone[2]
      ? explicitZone[2].toUpperCase().replace('NORTH', 'N').replace('SOUTH', 'S')
      : '';
    found.utm_zone = `${explicitZone[1]}${hemisphere}`;
  }

  const explicitDatum = flat.match(
    /\b(?:geodetic\s+datum|map\s+datum|datum)\s*[:=|-]?\s*([^|;\n]{3,70})/i,
  );
  if (explicitDatum) {
    const datum = stripOuterPunctuation(explicitDatum[1]);
    if (/\b(WGS|ED50|European|NAD|ETRS|OSGB|Mean)\b/i.test(datum)) {
      found.geodetic_datum = datum;
    }
  }

  const explicitConvergence = flat.match(
    /\bgrid\s+convergence\s*[:=|-]?\s*([+-]?\d+(?:\.\d+)?)\s*(°|deg(?:ree)?s?)/i,
  );
  if (explicitConvergence) {
    found.grid_convergence = `${explicitConvergence[1]}${explicitConvergence[2]}`;
  }

  const explicitNorthReference = flat.match(
    /\bnorth\s+reference\s*[:=|-]?\s*((?:grid|true|magnetic)(?:\s+north)?)/i,
  );
  if (explicitNorthReference) {
    found.north_reference = stripOuterPunctuation(explicitNorthReference[1]);
  }

  return found;
}


function headerContextCandidates(text: string): Record<string, string> {
  const found: Record<string, string> = {};
  const lines = text.split(/\r?\n/).map((line) => normalize(line)).filter(Boolean).slice(0, 30);

  const headerText = lines.join(' | ');

  // Generic petroleum-style identifiers from report titles and headers.
  const petroleumWell = headerText.match(
    /\b\d{1,3}\s*\/\s*\d{1,3}(?:\s*-\s*[A-Z0-9]+)+(?:\s*[A-Z])?\b/i,
  );
  if (petroleumWell) {
    found.well_name = petroleumWell[0]
      .replace(/\s*\/\s*/g, '/')
      .replace(/\s*-\s*/g, '-')
      .replace(/\s+/g, ' ')
      .trim();
  }

  for (const line of lines) {
    const wellMatch = line.match(/^(?:well(?:bore)?(?:\s+(?:name|number|no\.?|id))?|no\.?)\s*[:#.\-]?\s*(.+)$/i);
    if (wellMatch) {
      const normalizedWell = normalizeWellIdentifier(wellMatch[1]);
      if (shortIdentifier(normalizedWell)) found.well_name ??= normalizedWell;
    }

    const fieldMatch = line.match(
      /^(?:field\s*[:#.-]?\s*)?(.{2,45}?)\s+field\b(?:\s*[-–—:|].*)?$/i,
    );
    if (fieldMatch) {
      const candidate = validateCategoricalName(fieldMatch[1]);
      if (candidate && !/\b(?:main|oil|gas|production|exploration|reservoir)\b/i.test(candidate)) {
        found.field ??= candidate;
      }
    }
  }

  return found;
}

function pageSpecificCandidates(text: string): Record<string, string> {
  const flat = normalize(text);
  const found: Record<string, string> = {
    ...headerContextCandidates(text),
    ...coordinateBlockCandidates(text),
  };

  const slotCoordinates = flat.match(
    /slot\s+centre\s+coordinates.*?latitude\s+([0-9°º'’".\s]+[NS]).*?longitude\s+([0-9°º'’".\s]+[EW]).*?utm\s+co-?ordinates?\s+([0-9\s.,]+)\s*m?\s*N\s+([0-9\s.,]+)\s*m?\s*E/i,
  );
  if (slotCoordinates) {
    found.latitude = stripOuterPunctuation(slotCoordinates[1]);
    found.longitude = stripOuterPunctuation(slotCoordinates[2]);
    found.northing = stripOuterPunctuation(slotCoordinates[3]).replace(/\s/g, '');
    found.easting = stripOuterPunctuation(slotCoordinates[4]).replace(/\s/g, '');
    found.coordinate_system = 'UTM';
  }

  const wellheadTable = flat.match(
    /coordinates\s+at\s+wellhead\s+level.*?slot\s+centre\s+F-?10.*?UTM[:\s]+[0-9\s.,]+\s+[0-9\s.,]+\s+([0-9\s.,]+)\s+([0-9\s.,]+).*?Geographic\s+[0-9°º'’".\s]+[NS]?\s+[0-9°º'’".\s]+[EW]?\s+([0-9°º'’".\s]+[NS]?)\s+([0-9°º'’".\s]+[EW]?)/i,
  );
  if (wellheadTable) {
    found.northing = stripOuterPunctuation(wellheadTable[1]).replace(/\s/g, '');
    found.easting = stripOuterPunctuation(wellheadTable[2]).replace(/\s/g, '');
    if (validateLatitude(stripOuterPunctuation(wellheadTable[3]))) found.latitude = stripOuterPunctuation(wellheadTable[3]);
    if (validateLongitude(stripOuterPunctuation(wellheadTable[4]))) found.longitude = stripOuterPunctuation(wellheadTable[4]);
    found.coordinate_system = 'UTM';
  }

  const directGeographic = flat.match(
    /\bgeographic\b\s*[|:\-]?\s*([0-9°º'’".\s]+[NS])\s*[|,;]?\s*([0-9°º'’".\s]+[EW])/i,
  );
  if (directGeographic) {
    const latitude = stripOuterPunctuation(directGeographic[1]);
    const longitude = stripOuterPunctuation(directGeographic[2]);
    if (validateLatitude(latitude)) found.latitude = latitude;
    if (validateLongitude(longitude)) found.longitude = longitude;
  }

  const generalCoordinates = flat.match(
    /well\s+coordinates.*?geographic\s+([0-9°º'’".\s]+[NS])\s+([0-9°º'’".\s]+[EW]).*?UTM\s+([0-9\s.,]+)\s*m?\s*N\s+([0-9\s.,]+)\s*m?\s*E/i,
  );
  if (generalCoordinates) {
    found.latitude ??= stripOuterPunctuation(generalCoordinates[1]);
    found.longitude ??= stripOuterPunctuation(generalCoordinates[2]);
    found.northing ??= stripOuterPunctuation(generalCoordinates[3]).replace(/\s/g, '');
    found.easting ??= stripOuterPunctuation(generalCoordinates[4]).replace(/\s/g, '');
    found.coordinate_system ??= 'UTM';
  }

  const waterAirGap = flat.match(/water\s+depth\s*\/?\s*air\s*gap\s*[:\-]?\s*([0-9.,]+)\s*m(?:\s*MSL)?\s*\/\s*([0-9.,]+)\s*m/i);
  if (waterAirGap) {
    found.water_depth = `${waterAirGap[1]} m`;
    found.rt_kb_elevation = `${waterAirGap[2]} m`;
  }

  const waterDepth = flat.match(/water\s+depth\s*[:\-]?\s*([0-9.,]+)\s*m(?:\s*MSL)?/i);
  if (waterDepth) found.water_depth ??= `${waterDepth[1]} m`;

  const elevation = flat.match(
    /(?:KB|RKB|RT|rotary\s+table|kelly\s+bushing)\s+elevation\s*[|:\-]?\s*([0-9.,]+)\s*m/i,
  );
  if (elevation) found.rt_kb_elevation ??= `${elevation[1]} m`;

  const depthReference = flat.match(/depth\s+reference\s*[:\-]?\s*([^.;\n]{1,70})/i);
  if (depthReference && /\b(RKB|RT|rotary table|kelly bushing)\b/i.test(depthReference[1])) {
    const reference = stripOuterPunctuation(depthReference[1]);
    found.md_reference = reference;
    found.tvd_reference = reference;
  }

  const totalDepthPair = flat.match(/total\s+depth[^0-9]{0,30}([0-9.,]+)\s*m\s*MD\s*(?:RKB|RT)?.*?([0-9.,]+)\s*m\s*TVD\s*(?:RKB|RT)?/i);
  if (totalDepthPair) {
    found.final_md = `${totalDepthPair[1]} m`;
    found.final_tvd = `${totalDepthPair[2]} m`;
  }

  // A plotted event such as "SEA BED at 145.9 m MD" is not the
  // Wellhead / Seabed Depth metadata field and must not be imported.

  const finalStatus = flat.match(/final\s+well\s+status\s*[:\-]?\s*(P\s*&\s*A|plugged\s+and\s+abandoned|abandoned|completed|suspended|producing)/i);
  if (finalStatus) found.well_status = finalStatus[1].replace(/\s+/g, '').toUpperCase() === 'P&A' ? 'P&A' : finalStatus[1];

  return found;
}

type DeterministicCandidate = {
  value: string;
  block: SourceBlock;
  confidence: number;
};

function explicitValueAfterLabel(text: string, labels: string[], maxLength = 100): string | null {
  for (const label of labels) {
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(
      `(?:^|[\\n|])\\s*${escaped}\\s*(?:[:=|\\-]|\\s{2,})\\s*([^\\n|]{1,${maxLength}})`,
      'i',
    );
    const match = text.match(pattern);
    if (match) return stripOuterPunctuation(match[1]);
  }
  return null;
}

function candidateScore(fieldKey: string, block: SourceBlock, value: string): number {
  const text = normalize(block.text);
  let score = block.extraction === 'structured' ? 40 : block.extraction === 'text' ? 30 : 20;
  if (/\b(?:general well data|well summary|end of well report|final well report)\b/i.test(text)) score += 25;
  if (/\b(?:actual|as[- ]drilled|final|measured|logged|surveyed)\b/i.test(text)) score += 10;
  if (/\b(?:planned|proposed|forecast|prognos)/i.test(text)) score -= 35;
  const rule = FIELD_RULES[fieldKey];
  if (rule?.labels.some((label) => normalizedKey(text).includes(normalizedKey(label)))) score += 20;
  if (!value.trim()) score -= 100;
  return score;
}

function storeDeterministicCandidate(
  target: Record<string, DeterministicCandidate>,
  fieldKey: string,
  value: string | null | undefined,
  block: SourceBlock,
  confidenceBoost = 0,
) {
  if (!value) return;
  const rule = FIELD_RULES[fieldKey];
  if (!rule) return;
  const normalizedValue = normalizeStoredFieldValue(fieldKey, value);
  const validated = rule.validate(normalizedValue);
  if (!validated) return;
  const confidence = candidateScore(fieldKey, block, validated) + confidenceBoost;
  const existing = target[fieldKey];
  if (!existing || confidence > existing.confidence) {
    target[fieldKey] = {
      value: normalizeStoredFieldValue(fieldKey, validated),
      block,
      confidence,
    };
  }
}

function explicitReportCandidates(block: SourceBlock): Record<string, string> {
  const text = normalize(block.text);
  const found: Record<string, string> = { ...pageSpecificCandidates(text) };

  const explicitWell = explicitValueAfterLabel(
    text,
    ['well name', 'well no.', 'well no', 'well number', 'well identifier', 'well'],
    70,
  );
  if (explicitWell) {
    const normalizedWell = normalizeWellIdentifier(explicitWell);
    if (shortIdentifier(normalizedWell)) found.well_name ??= normalizedWell;
  }

  const explicitWellbore = explicitValueAfterLabel(
    text,
    ['wellbore name', 'well bore name', 'borehole name'],
    70,
  );
  if (explicitWellbore && shortIdentifier(explicitWellbore)) {
    found.wellbore_name = normalizeWellIdentifier(explicitWellbore);
  }

  const field = explicitValueAfterLabel(text, ['field name', 'field'], 60);
  if (field) {
    const validatedField = validateCategoricalName(field.replace(/\s+field$/i, ''));
    if (validatedField) found.field ??= validatedField;
  }

  const operator = explicitValueAfterLabel(text, ['operator name', 'operator', 'operating company'], 80);
  if (operator) {
    const validatedOperator = validateCategoricalName(operator);
    if (validatedOperator) found.operator = validatedOperator;
  }

  const country = explicitValueAfterLabel(text, ['country'], 40);
  if (country) {
    const validatedCountry = validateCategoricalName(country);
    if (validatedCountry) found.country = validatedCountry;
  }

  const uwi = explicitValueAfterLabel(text, ['unique well identifier', 'uwi', 'api number', 'well id'], 70);
  if (uwi && shortIdentifier(uwi)) found.uwi = uwi;

  const blockValue = explicitValueAfterLabel(text, ['licence block', 'license block', 'block'], 50);
  if (blockValue && !/\b(?:licen[cs]e|pl\s*\d+)\b/i.test(blockValue)) found.block = blockValue;

  const statusMatch = text.match(
    /\b(?:final\s+well\s+status|well\s+status|final\s+status)\s*(?:[:=|\-]|\s{2,})\s*(P\s*&\s*A|plugged\s+and\s+abandoned|permanently\s+abandoned|abandoned|completed|suspended|producing|producer|observation)\b/i,
  );
  if (statusMatch) {
    found.well_status = /P\s*&\s*A|plugged|permanently/i.test(statusMatch[1])
      ? 'P&A'
      : stripOuterPunctuation(statusMatch[1]);
  } else if (/\bpermanent(?:ly)?\s+(?:plugged\s+and\s+)?abandon(?:ed|ment)\b/i.test(text)) {
    found.well_status = 'P&A';
  }

  const coordinateSystem = explicitValueAfterLabel(
    text,
    ['coordinate reference system', 'coordinate system', 'map projection', 'projection'],
    90,
  );
  if (coordinateSystem) {
    const validatedCoordinateSystem = validateCoordinateSystem(coordinateSystem);
    if (validatedCoordinateSystem) found.coordinate_system = validatedCoordinateSystem;
  }

  const datum = explicitValueAfterLabel(
    text,
    ['geodetic datum', 'map datum', 'horizontal datum', 'datum'],
    70,
  );
  if (datum) {
    const validatedDatum = validateDatum(datum);
    if (validatedDatum) found.geodetic_datum = validatedDatum;
  }

  const utmZone = text.match(/\bUTM(?:\s+zone)?\s*[:=|\-]?\s*([1-5]?\d|60)\s*([C-HJ-NP-X]|N|S|North|South)?\b/i);
  if (utmZone) {
    const hemisphere = (utmZone[2] ?? '').replace(/north/i, 'N').replace(/south/i, 'S').toUpperCase();
    found.utm_zone = `${utmZone[1]}${hemisphere}`;
    found.coordinate_system ??= 'UTM';
  }

  const epsg = text.match(/\bEPSG\s*[:#]?\s*(\d{4,6})\b/i);
  if (epsg) found.epsg_code = epsg[1];

  const northReference = explicitValueAfterLabel(text, ['north reference'], 40);
  if (northReference) {
    const validatedNorth = validateNorthReference(northReference);
    if (validatedNorth) found.north_reference = validatedNorth;
  }

  const convergence = text.match(
    /\bgrid\s+convergence\s*(?:[:=|\-]|\s{2,})\s*([+-]?\d+(?:\.\d+)?)\s*(?:°|deg(?:ree)?s?)?/i,
  );
  if (convergence) found.grid_convergence = `${convergence[1]} deg`;

  const waterDepth = text.match(
    /\bwater\s+depth\b[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?)\s*(m|metres?|meters?|ft|feet)\b/i,
  );
  if (waterDepth) found.water_depth = `${waterDepth[1]} ${waterDepth[2]}`;

  const elevation = text.match(
    /\b(?:RT|RKB|KB|rotary\s+table|kelly\s+bushing)(?:\s*\/\s*(?:RT|RKB|KB))?\s+elevation\b[^0-9+-]{0,30}([+-]?[0-9]+(?:\.[0-9]+)?)\s*(m|metres?|meters?|ft|feet)\b/i,
  );
  if (elevation) found.rt_kb_elevation = `${elevation[1]} ${elevation[2]}`;

  const finalMd = text.match(
    /\b(?:total\s+depth(?:\s*\((?:driller|logger)\))?|final\s+MD|TD)\b[^0-9]{0,35}([0-9]+(?:\.[0-9]+)?)\s*(m|ft)\s*(?:MD)?\s*(?:RKB|RT|KB)?\b/i,
  );
  if (finalMd) found.final_md = `${finalMd[1]} ${finalMd[2]}`;

  const finalTvd = text.match(
    /\b(?:total\s+depth\s+TVD|final\s+TVD|TVD\s+at\s+TD)\b[^0-9]{0,35}([0-9]+(?:\.[0-9]+)?)\s*(m|ft)\s*(?:TVD)?\s*(?:RKB|RT|KB|MSL)?\b/i,
  );
  if (finalTvd) found.final_tvd = `${finalTvd[1]} ${finalTvd[2]}`;

  if (/\b(?:m|metres?|meters?)\s+MD\s+(?:RKB|RT|KB)\b/i.test(text)) {
    found.depth_unit ??= 'm';
    found.md_reference ??= text.match(/\b(?:m|metres?|meters?)\s+MD\s+(RKB|RT|KB)\b/i)?.[1] ?? 'RKB';
  } else if (/\b(?:ft|feet)\s+MD\s+(?:RKB|RT|KB)\b/i.test(text)) {
    found.depth_unit ??= 'ft';
    found.md_reference ??= text.match(/\b(?:ft|feet)\s+MD\s+(RKB|RT|KB)\b/i)?.[1] ?? 'RKB';
  }

  const tvdReference = text.match(/\b(?:m|ft)\s+TVD\s+(RKB|RT|KB|MSL)\b/i);
  if (tvdReference) found.tvd_reference = tvdReference[1];

  const surveyType = explicitValueAfterLabel(
    text,
    ['survey type', 'directional survey type', 'trajectory type'],
    70,
  );
  if (surveyType) found.survey_type = surveyType;

  const surveyMethod = explicitValueAfterLabel(
    text,
    ['survey calculation method', 'calculation method', 'survey method'],
    70,
  );
  if (surveyMethod) found.calculation_method = surveyMethod;

  if (/\bactual\s+(?:deviation|directional)\s+survey\b/i.test(text)) {
    found.survey_status = 'Actual';
    found.trajectory_source ??= 'Actual deviation survey';
  } else if (/\bfinal\s+(?:deviation|directional)\s+survey\b/i.test(text)) {
    found.survey_status = 'Final';
    found.trajectory_source ??= 'Final directional survey';
  }

  return found;
}

function surveySummaryCandidates(blocks: SourceBlock[]): Record<string, DeterministicCandidate> {
  const rows: Array<{ md: number; inclination: number; tvd: number; north: number; east: number; block: SourceBlock }> = [];

  for (const block of blocks) {
    if (!/\bMD\b/i.test(block.text) || !/\b(?:inclination|inc)\b/i.test(block.text)) continue;
    const linePattern = /^\s*(?:\d+\s*[|,;\t ]+)?([+-]?\d+(?:\.\d+)?)\s*[|,;\t ]+([+-]?\d+(?:\.\d+)?)\s*[|,;\t ]+([+-]?\d+(?:\.\d+)?)\s*[|,;\t ]+([+-]?\d+(?:\.\d+)?)\s*[|,;\t ]+([+-]?\d+(?:\.\d+)?)\s*$/;

    for (const line of block.text.split(/\r?\n/)) {
      const match = line.match(linePattern);
      if (!match) continue;
      const [md, inclination, tvd, north, east] = match.slice(1).map(Number);
      if (![md, inclination, tvd, north, east].every(Number.isFinite)) continue;
      if (md < -1000 || md > 30000 || inclination < 0 || inclination > 180) continue;
      rows.push({ md, inclination, tvd, north, east, block });
    }
  }

  if (rows.length < 2) return {};
  rows.sort((a, b) => a.md - b.md);
  const first = rows[0];
  const last = rows[rows.length - 1];
  const maxInclination = rows.reduce((max, row) => Math.max(max, row.inclination), 0);

  return {
    station_count: { value: String(rows.length), block: last.block, confidence: 90 },
    first_md: { value: `${first.md} m`, block: first.block, confidence: 90 },
    final_md: { value: `${last.md} m`, block: last.block, confidence: 95 },
    final_tvd: { value: `${last.tvd} m`, block: last.block, confidence: 95 },
    maximum_inclination: { value: `${maxInclination} deg`, block: last.block, confidence: 90 },
    final_north_offset: { value: `${last.north} m`, block: last.block, confidence: 90 },
    final_east_offset: { value: `${last.east} m`, block: last.block, confidence: 90 },
    survey_status: { value: 'Actual', block: last.block, confidence: 80 },
  };
}

function documentWideDeterministicCandidates(
  file: File,
  blocks: SourceBlock[],
): Record<string, DeterministicCandidate> {
  const candidates: Record<string, DeterministicCandidate> = {};

  const filenameWell = file.name.match(
    /\b\d{1,3}[_\s-]*\d{1,3}[_\s-]+[A-Z]\s*[-_]?\s*\d+(?:\s*[A-Z])?\b/i,
  );
  if (filenameWell && blocks[0]) {
    const parts = filenameWell[0].replace(/_/g, '-').match(/^(\d{1,3})-(\d{1,3})-([A-Z])-(\d+)([A-Z]?)$/i);
    const normalizedFilenameWell = parts
      ? `${parts[1]}/${parts[2]}-${parts[3].toUpperCase()}-${parts[4]}${parts[5].toUpperCase()}`
      : normalizeWellIdentifier(filenameWell[0]);
    storeDeterministicCandidate(candidates, 'well_name', normalizedFilenameWell, blocks[0], 10);
  }

  for (const block of blocks) {
    const perBlock = explicitReportCandidates(block);
    for (const [fieldKey, value] of Object.entries(perBlock)) {
      storeDeterministicCandidate(candidates, fieldKey, value, block);
    }
  }

  const survey = surveySummaryCandidates(blocks);
  for (const [fieldKey, candidate] of Object.entries(survey)) {
    const existing = candidates[fieldKey];
    if (!existing || candidate.confidence > existing.confidence) candidates[fieldKey] = candidate;
  }

  return candidates;
}


function mergeProposalMaps(
  current: Record<string, Proposal>,
  incoming: Record<string, Proposal>,
): Record<string, Proposal> {
  const merged = { ...current };

  for (const [fieldKey, next] of Object.entries(incoming)) {
    const existing = merged[fieldKey];
    if (!existing) {
      merged[fieldKey] = next;
      continue;
    }

    const sameValue = normalizedComparable(existing.value) === normalizedComparable(next.value);
    if (sameValue) {
      const sourceKey = `${next.sourceFile}|${next.sourceReference}`;
      const hasSource = existing.sources.some((source) => `${source.file}|${source.reference}` === sourceKey);
      merged[fieldKey] = {
        ...existing,
        sources: hasSource ? existing.sources : [...existing.sources, ...next.sources],
      };
      continue;
    }

    const alreadyRecorded = existing.alternatives.some(
      (alternative) =>
        normalizedComparable(alternative.value) === normalizedComparable(next.value) &&
        alternative.sourceFile === next.sourceFile &&
        alternative.sourceReference === next.sourceReference,
    );

    merged[fieldKey] = {
      ...existing,
      alternatives: alreadyRecorded
        ? existing.alternatives
        : [...existing.alternatives, {
            value: next.value,
            sourceFile: next.sourceFile,
            sourceReference: next.sourceReference,
          }],
    };
  }

  return merged;
}


const WME_SESSION_KEY = 'wlv:wme:session:v1';

type PersistedWmeSession = {
  contextFileName: string;
  sheetName: string;
  rows: ContextRow[];
  proposals: Record<string, Proposal>;
  workbookBase64: string;
  scannedFileKeys: string[];
  supportingFileNames: string[];
  message: string;
};

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function fileKey(file: File): string {
  return `${file.name}|${file.size}|${file.lastModified}`;
}

type WellMetadataExtractorPageProps = {
  onBack: () => void;
  initialContext?: { fileName: string; workbookBase64: string } | null;
  onApplyToWellInfo?: (values: Record<string, { value: string; unit?: string; source?: string; sourceReference?: string; notes?: string }>) => void;
};

export function WellMetadataExtractorPage({ onBack, initialContext = null, onApplyToWellInfo }: WellMetadataExtractorPageProps) {
  const contextInput = useRef<HTMLInputElement>(null);
  const supportInput = useRef<HTMLInputElement>(null);
  const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null);
  const [workbookBase64, setWorkbookBase64] = useState('');
  const [sheetName, setSheetName] = useState('');
  const [contextFileName, setContextFileName] = useState('');
  const [rows, setRows] = useState<ContextRow[]>([]);
  const [supportFiles, setSupportFiles] = useState<File[]>([]);
  const supportFilesRef = useRef<File[]>([]);
  const [supportingFileNames, setSupportingFileNames] = useState<string[]>([]);
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
  const [scannedFileKeys, setScannedFileKeys] = useState<Set<string>>(new Set());
  const [dragTarget, setDragTarget] = useState<'context' | 'support' | null>(null);
  const [proposals, setProposals] = useState<Record<string, Proposal>>({});
  const [selectedProposalKeys, setSelectedProposalKeys] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState('Load an exported Well Info workbook to begin.');
  const [exportNotice, setExportNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [selectedScanMode, setSelectedScanMode] = useState<WmeScanMode>('fast');
  const [scanElapsedSeconds, setScanElapsedSeconds] = useState(0);
  const scanStartedAtRef = useRef<number | null>(null);
  const rowsRef = useRef<ContextRow[]>([]);
  const supportingFileNamesRef = useRef<string[]>([]);

  const [editingFieldKey, setEditingFieldKey] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState('');
  const [editingSource, setEditingSource] = useState('');

  const [aiStatus, setAiStatus] = useState<WmeAiStatus | null>(null);


  useEffect(() => {
    let cancelled = false;
    fetchWmeJson<WmeAiStatus>('/api/wme/ai/status')
      .then((status) => {
        if (!cancelled) setAiStatus(status);
      })
      .catch((error) => {
        if (!cancelled) {
          setAiStatus({
            available: false,
            service: 'ollama',
            model: 'wme-qwen',
            detail: error instanceof Error ? error.message : 'Local AI status unavailable',
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!busy || scanStartedAtRef.current === null) return undefined;

    const updateElapsed = () => {
      const startedAt = scanStartedAtRef.current ?? performance.now();
      setScanElapsedSeconds(Math.max(0, Math.floor((performance.now() - startedAt) / 1000)));
    };

    updateElapsed();
    const timer = window.setInterval(updateElapsed, 250);
    return () => window.clearInterval(timer);
  }, [busy]);

  const formattedScanDuration = `${String(Math.floor(scanElapsedSeconds / 60)).padStart(2, '0')}:${String(
    scanElapsedSeconds % 60,
  ).padStart(2, '0')}`;

  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);

  useEffect(() => {
    supportingFileNamesRef.current = supportingFileNames;
  }, [supportingFileNames]);
  useEffect(() => {
    supportFilesRef.current = supportFiles;
  }, [supportFiles]);


  useEffect(() => {
    setSelectedProposalKeys((current) => {
      const next = new Set([...current].filter((fieldKey) => proposals[fieldKey]?.accepted === null));
      if (next.size === current.size && [...next].every((fieldKey) => current.has(fieldKey))) return current;
      return next;
    });
  }, [proposals]);

  const contextRefreshSummary = (nextRows: ContextRow[], importedProposalCount: number): string => {
    const previousByKey = new Map(rowsRef.current.map((row) => [row.fieldKey, row.value.trim()]));
    let replaced = 0;
    let cleared = 0;

    nextRows.forEach((row) => {
      const previous = previousByKey.get(row.fieldKey) ?? '';
      const next = row.value.trim();
      if (previous && !next) cleared += 1;
      else if (previous && next && previous !== next) replaced += 1;
    });

    const loaded = nextRows.filter((row) => row.value.trim()).length;
    const retainedDocuments = supportingFileNamesRef.current.length;
    const proposalText = importedProposalCount > 0
      ? `${importedProposalCount} imported AI proposal(s) loaded; prior proposal decisions reset`
      : 'prior deterministic and AI proposals reset';

    return `Context refreshed · ${loaded} fields loaded · ${replaced} values replaced · ` +
      `${cleared} stale values cleared · ${proposalText} · ` +
      `${retainedDocuments} supporting document(s) retained.`;
  };

  useEffect(() => {
    if (!initialContext?.workbookBase64) return;
    try {
      const loaded = XLSX.read(base64ToArrayBuffer(initialContext.workbookBase64), { type: 'array', cellStyles: true });
      const parsed = rowsFromWorkbook(loaded);
      setWorkbook(loaded);
      setWorkbookBase64(initialContext.workbookBase64);
      setSheetName(parsed.sheetName);
      const refreshMessage = contextRefreshSummary(parsed.rows, 0);
      rowsRef.current = parsed.rows;
      setRows(parsed.rows);
      setContextFileName(initialContext.fileName);
      setScannedFileKeys(new Set());
      setProposals({});
      setSelectedProposalKeys(new Set());
      setMessage(refreshMessage);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to receive Well Info context.');
    }
  }, [initialContext]);

  useEffect(() => {
    if (initialContext?.workbookBase64) return;
    try {
      const raw = sessionStorage.getItem(WME_SESSION_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as PersistedWmeSession;
      const restoredWorkbook = saved.workbookBase64
        ? XLSX.read(base64ToArrayBuffer(saved.workbookBase64), { type: 'array', cellStyles: true })
        : null;

      setWorkbook(restoredWorkbook);
      setWorkbookBase64(saved.workbookBase64 ?? '');
      setSheetName(saved.sheetName ?? '');
      setContextFileName(saved.contextFileName ?? '');
      setRows(saved.rows ?? []);
      setProposals(saved.proposals ?? {});
      setScannedFileKeys(new Set(saved.scannedFileKeys ?? []));
      setSupportingFileNames(saved.supportingFileNames ?? []);
      setMessage(saved.message || 'Restored previous Well Metadata Extractor session.');
    } catch {
      sessionStorage.removeItem(WME_SESSION_KEY);
    }
  }, [initialContext?.workbookBase64]);

  useEffect(() => {
    if (!contextFileName || !workbookBase64) return;
    const payload: PersistedWmeSession = {
      contextFileName,
      sheetName,
      rows,
      proposals,
      workbookBase64,
      scannedFileKeys: [...scannedFileKeys],
      supportingFileNames,
      message,
    };
    sessionStorage.setItem(WME_SESSION_KEY, JSON.stringify(payload));
  }, [
    contextFileName,
    sheetName,
    rows,
    proposals,
    workbookBase64,
    scannedFileKeys,
    supportingFileNames,
    message,
  ]);

  const missingRows = useMemo(() => rows.filter((row) => !row.value), [rows]);
  const selectableProposalKeys = useMemo(
    () => rows
      .map((row) => row.fieldKey)
      .filter((fieldKey) => proposals[fieldKey]?.accepted === null),
    [rows, proposals],
  );

  const loadContext = async (file: File) => {
    try {
      const buffer = await file.arrayBuffer();
      const loaded = XLSX.read(buffer, { type: 'array', cellStyles: true });
      const parsed = rowsFromWorkbook(loaded);
      setWorkbook(loaded);
      setWorkbookBase64(arrayBufferToBase64(buffer));
      setSheetName(parsed.sheetName);
      setContextFileName(file.name);
      setScannedFileKeys(new Set());
      const importedProposals = Object.fromEntries(parsed.rows
        .filter((row) => row.aiRecommendedValue.trim())
        .map((row) => [row.fieldKey, {
          fieldKey: row.fieldKey,
          value: canonicalizeStoredMetadataValue(row.aiRecommendedValue),
          sourceFile: row.aiSource || 'External AI recommendation',
          sourceReference: row.aiSourceReference || row.aiEvidence || 'Context workbook',
          accepted: null,
          editedValue: '',
          sources: [{
            file: row.aiSource || 'External AI recommendation',
            reference: row.aiSourceReference || row.aiEvidence || 'Context workbook',
            extraction: 'ai' as const,
          }],
          alternatives: [],
        }]));
      const recommended = Object.keys(importedProposals).length;
      const refreshMessage = contextRefreshSummary(parsed.rows, recommended);
      rowsRef.current = parsed.rows;
      setRows(parsed.rows);
      setProposals(importedProposals);
      setSelectedProposalKeys(new Set());
      setMessage(refreshMessage);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to load the workbook.');
    }
  };

  const crawlDocuments = async (scanMode: WmeScanMode) => {
    if (!workbook || supportFiles.length === 0) return;

    const selectedSupportFiles = Array.from(selectedSupportingFileIndexes)
      .sort((a, b) => a - b)
      .map((index) => supportFiles[index])
      .filter((file): file is File => Boolean(file));

    const filesToScan =
      scanMode === 'deep'
        ? selectedSupportFiles
        : selectedSupportFiles.filter((file) => !scannedFileKeys.has(fileKey(file)));

    if (filesToScan.length === 0) {
      setMessage(
        'All selected supporting files have already been Fast scanned. Select Deep to rescan them.',
      );
      return;
    }

    const scanModeLabel = scanMode === 'deep' ? 'Deep Scan' : 'Fast Scan';
    scanStartedAtRef.current = performance.now();
    setScanElapsedSeconds(0);
    setBusy(true);
    setExportNotice('');
    setMessage(`Preparing ${scanModeLabel}: ${filesToScan.length} supporting file(s)…`);

    try {
      const wellName = rows.find((row) => row.fieldKey === 'well_name')?.value ?? '';
      const wellboreName = rows.find((row) => row.fieldKey === 'wellbore_name')?.value ?? '';
      const found: Record<string, Proposal> = {};
      let rejectedDocuments = 0;
      let pagesIndexed = 0;
      let ocrPages = 0;
      const ocrPageNumbers: number[] = [];
      let aiPagesAttempted = 0;
      let aiResponsesReceived = 0;
      let aiProposalsReturned = 0;
      let aiProposalsAccepted = 0;
      let aiNoProposalResponses = 0;
      let aiWellMismatchResponses = 0;
      let aiValidationRejected = 0;
      let aiStructureCentreRejected = 0;
      let aiOtherWellProposalsRejected = 0;
      let aiRequestErrors = 0;
      const aiErrorMessages: string[] = [];
      const maxAiPagesAcrossScan = scanMode === 'deep' ? 12 : 0;
      const maxAiPagesPerDocument = scanMode === 'deep' ? 8 : 0;
      const diagnosticRun = {
        schema_version: 'wme-diagnostic-1.0',
        scan_mode: scanMode,
        started_at: new Date().toISOString(),
        context_file: contextFileName,
        selected_well: wellName,
        selected_wellbore: wellboreName,
        support_files: filesToScan.map((item) => ({
          name: item.name,
          size: item.size,
          type: item.type,
          last_modified: item.lastModified,
        })),
        timings_ms: {
          total: 0,
          source_extraction: [] as Array<Record<string, unknown>>,
        },
        documents: [] as Array<Record<string, unknown>>,
        ai_calls: [] as Array<Record<string, unknown>>,
        proposal_decisions: [] as Array<Record<string, unknown>>,
        final_found: {} as Record<string, unknown>,
        counters: {} as Record<string, number>,
      };
      const diagnosticTotalStarted = performance.now();

      for (let index = 0; index < filesToScan.length; index += 1) {
        const file = filesToScan[index];
        const sourceExtractionStarted = performance.now();
        const blocks = await extractSourceBlocks(
          file,
          scanMode,
          (progress) => {
            if (progress.mode === 'ocr') {
              ocrPages += 1;
              if (!ocrPageNumbers.includes(progress.pageNumber)) {
                ocrPageNumbers.push(progress.pageNumber);
              }
            } else {
              pagesIndexed += 1;
            }
            setMessage(
              `Scanning ${progress.fileIndex}/${progress.fileCount}: ${progress.fileName} · ` +
              `page ${progress.pageNumber}/${progress.pageCount} · ${progress.mode.toUpperCase()}`,
            );
          },
          index + 1,
          filesToScan.length,
        );
        const sourceExtractionDuration = performance.now() - sourceExtractionStarted;
        diagnosticRun.timings_ms.source_extraction.push({
          file: file.name,
          duration_ms: Math.round(sourceExtractionDuration),
          block_count: blocks.length,
        });
        const detectedDocumentStatus = documentEvidenceStatus(blocks);
        const reportWideCandidates = documentWideDeterministicCandidates(file, blocks);
        const documentDiagnostic: Record<string, unknown> = {
          file: file.name,
          document_status: detectedDocumentStatus,
          blocks: blocks.map((block) => ({
            reference: block.reference,
            extraction: block.extraction,
            text_length: block.text.length,
            text: block.text,
            row_count: block.rows.length,
          })),
          document_matches_well: documentMatchesWell(file.name, blocks, wellName, wellboreName),
          deterministic_proposals: [] as Array<Record<string, unknown>>,
          candidate_pages: [] as Array<Record<string, unknown>>,
        };
        diagnosticRun.documents.push(documentDiagnostic);

        if (!documentMatchesWell(file.name, blocks, wellName, wellboreName)) {
          rejectedDocuments += 1;
          continue;
        }

        for (const row of missingRows) {
          const existing = proposals[row.fieldKey];
          if (existing?.accepted === true || existing?.accepted === false) continue;

          const rule = FIELD_RULES[row.fieldKey];
          let candidate: string | null = null;
          let candidateBlock: SourceBlock | null = null;

          const reportWideCandidate = reportWideCandidates[row.fieldKey];
          if (reportWideCandidate) {
            candidate = reportWideCandidate.value;
            candidateBlock = reportWideCandidate.block;
          }

          for (const block of candidate ? [] : blocks) {
            const pageCandidates = pageSpecificCandidates(block.text);
            const pageValue = pageCandidates[row.fieldKey];
            if (pageValue && (!rule || rule.validate(pageValue))) {
              candidate = rule ? rule.validate(pageValue) : pageValue;
              candidateBlock = block;
              break;
            }

            if (rule) {
              const structured = candidateFromRows(rule, block.rows);
              if (structured) {
                candidate = structured;
                candidateBlock = block;
                break;
              }
            }
          }

          if (!candidate || !candidateBlock) continue;

          const candidateStatus = effectiveEvidenceStatus(detectedDocumentStatus, candidateBlock.text);
          if (!statusAllowsField(row.fieldKey, candidateStatus, detectedDocumentStatus)) {
            (documentDiagnostic.deterministic_proposals as Array<Record<string, unknown>>).push({
              field_key: row.fieldKey,
              raw_candidate: candidate,
              source_reference: candidateBlock.reference,
              extraction: candidateBlock.extraction,
              evidence_status: candidateStatus,
              accepted: false,
              reason: 'status_not_valid_for_actual_field',
            });
            continue;
          }

          const storedCandidate = normalizeStoredFieldValue(row.fieldKey, candidate);
          found[row.fieldKey] = {
            fieldKey: row.fieldKey,
            value: storedCandidate,
            sourceFile: file.name,
            sourceReference: `${candidateBlock.reference} · ${scanModeLabel}`,
            accepted: null,
            editedValue: storedCandidate,
            sources: [{
              file: file.name,
              reference: `${candidateBlock.reference} · ${scanModeLabel}`,
              extraction: candidateBlock.extraction,
            }],
            alternatives: [],
          };
          (documentDiagnostic.deterministic_proposals as Array<Record<string, unknown>>).push({
            field_key: row.fieldKey,
            raw_candidate: candidate,
            stored_candidate: storedCandidate,
            source_reference: candidateBlock.reference,
            extraction: candidateBlock.extraction,
            evidence_status: candidateStatus,
            accepted: true,
          });
        }

        const canUseAi =
          scanMode === 'deep' &&
          aiStatus?.available === true &&
          file.name.toLowerCase().endsWith('.pdf') &&
          aiPagesAttempted < maxAiPagesAcrossScan;

        if (canUseAi) {
          let unresolvedFields = missingRows
            .map((row) => row.fieldKey)
            .filter((fieldKey) => {
              const existing = proposals[fieldKey];
              return !found[fieldKey] && existing?.accepted !== true && existing?.accepted !== false;
            });

          const candidatePages = blocks
            .map((block) => {
              const score = relevantPageScore(block, unresolvedFields);
              return {
                block,
                pageNumber: pageNumberFromReference(block.reference),
                score,
                metadataScore: metadataSummaryPageScore(block),
              };
            })
            .filter((candidate): candidate is { block: SourceBlock; pageNumber: number; score: number; metadataScore: number } => {
              if (candidate.pageNumber === null) return false;

              const explicitLabel = pageHasExplicitUnresolvedLabel(
                candidate.block,
                unresolvedFields,
              );

              if (scanMode === 'fast') {
                return (
                  (candidate.score >= 2 || candidate.metadataScore >= 2) &&
                  explicitLabel
                );
              }

              return (
                explicitLabel ||
                candidate.metadataScore >= 2 ||
                candidate.score >= 5
              );
            })
            .sort((a, b) =>
              b.metadataScore - a.metadataScore || b.score - a.score || a.pageNumber - b.pageNumber,
            )
            .slice(
              0,
              Math.min(
                maxAiPagesPerDocument,
                maxAiPagesAcrossScan - aiPagesAttempted,
              ),
            );

          documentDiagnostic.candidate_pages = candidatePages.map((candidate) => ({
            page_number: candidate.pageNumber,
            score: candidate.score,
            metadata_score: candidate.metadataScore,
            text_length: candidate.block.text.length,
            extraction: candidate.block.extraction,
          }));

          for (const candidate of candidatePages) {
            if (unresolvedFields.length === 0 || aiPagesAttempted >= maxAiPagesAcrossScan) break;

            aiPagesAttempted += 1;
            setMessage(
              `${scanModeLabel} · Local AI ${aiPagesAttempted}/${maxAiPagesAcrossScan}: ` +
              `${file.name} · Page ${candidate.pageNumber} · ` +
              `${unresolvedFields.length} unresolved field(s)`,
            );

            try {
              const requestAi = async (pageImage = '') => {
                const requestPayload = {
                  selected_well: wellName,
                  selected_wellbore: wellboreName,
                  source_file: file.name,
                  page_number: candidate.pageNumber,
                  page_image: pageImage,
                  page_text: candidate.block.text,
                  missing_fields: [...unresolvedFields],
                  scan_mode: scanMode,
                  document_identity_verified: true,
                };
                const callDiagnostic: Record<string, unknown> = {
                  file: file.name,
                  page_number: candidate.pageNumber,
                  request: {
                    selected_well: wellName,
                    selected_wellbore: wellboreName,
                    source_file: file.name,
                    page_number: candidate.pageNumber,
                    page_image_included: Boolean(pageImage),
                    page_image_base64_length: pageImage.length,
                    page_text: candidate.block.text,
                    page_text_length: candidate.block.text.length,
                    missing_fields: [...unresolvedFields],
                    scan_mode: scanMode,
                    document_identity_verified: true,
                  },
                  started_at: new Date().toISOString(),
                };
                diagnosticRun.ai_calls.push(callDiagnostic);
                const aiCallStarted = performance.now();
                try {
                  const response = await fetchWmeJson<WmeAiExtractResponse>('/api/wme/ai/extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestPayload),
                  });
                  callDiagnostic.duration_ms = Math.round(performance.now() - aiCallStarted);
                  callDiagnostic.response = response;
                  return response;
                } catch (error) {
                  callDiagnostic.duration_ms = Math.round(performance.now() - aiCallStarted);
                  callDiagnostic.error = error instanceof Error ? error.message : String(error);
                  throw error;
                }
              };

              const renderImageFirst = shouldRenderMetadataPageImage(candidate.block, candidate.score);
              let response: WmeAiExtractResponse;

              if (renderImageFirst) {
                setMessage(
                  `${scanModeLabel} · Local AI visual metadata scan: ` +
                  `${file.name} · Page ${candidate.pageNumber} · ` +
                  `${unresolvedFields.length} unresolved field(s)`,
                );
                const pageImage = await renderPdfPageBase64(file, candidate.pageNumber);
                response = await requestAi(pageImage);
              } else {
                response = await requestAi();
              }

              if (
                response.proposals.length === 0 &&
                !renderImageFirst &&
                candidate.block.text.replace(/[^A-Za-z0-9]/g, '').length < 1200
              ) {
                setMessage(
                  `${scanModeLabel} · Local AI image fallback: ` +
                  `${file.name} · Page ${candidate.pageNumber} · ` +
                  `${unresolvedFields.length} unresolved field(s)`,
                );
                const pageImage = await renderPdfPageBase64(file, candidate.pageNumber);
                response = await requestAi(pageImage);
              }

              aiResponsesReceived += 1;
              aiProposalsReturned += response.proposals.length;

              if (response.well_identity_match === 'mismatch') {
                aiWellMismatchResponses += 1;
                if (scanMode === 'fast') continue;
              }

              if (response.proposals.length === 0) {
                aiNoProposalResponses += 1;
              }

              for (const proposal of response.proposals) {
                const decision: Record<string, unknown> = {
                  file: file.name,
                  page_number: candidate.pageNumber,
                  proposal,
                  raw_value_for_validation: proposalValueForValidation(proposal),
                  accepted: false,
                  reason: '',
                };
                diagnosticRun.proposal_decisions.push(decision);

                if (proposal.subject_identity_match === 'other') {
                  aiValidationRejected += 1;
                  aiOtherWellProposalsRejected += 1;
                  decision.reason = 'proposal_bound_to_other_well';
                  continue;
                }

                if (!unresolvedFields.includes(proposal.field_key)) {
                  aiValidationRejected += 1;
                  decision.reason = 'field_not_unresolved';
                  continue;
                }
                if (proposal.location_type === 'structure_centre') {
                  aiStructureCentreRejected += 1;
                  decision.reason = 'structure_centre_rejected';
                  continue;
                }

                const proposalStatus = proposal.value_status as EvidenceStatus;
                const effectiveProposalStatus =
                  proposalStatus === 'unknown' ? detectedDocumentStatus : proposalStatus;
                decision.document_status = detectedDocumentStatus;
                decision.effective_evidence_status = effectiveProposalStatus;

                if (!statusAllowsField(proposal.field_key, effectiveProposalStatus, detectedDocumentStatus)) {
                  aiValidationRejected += 1;
                  decision.reason = 'status_not_valid_for_actual_field';
                  continue;
                }

                if (
                  proposal.field_key === 'data_end_md' &&
                  !/\b(?:base|end|maximum)\s+depth\b/i.test(proposal.evidence)
                ) {
                  aiValidationRejected += 1;
                  decision.reason = 'base_depth_requires_explicit_label';
                  continue;
                }

                if (
                  proposal.field_key === 'data_start_md' &&
                  !/\b(?:top|start|minimum)\s+depth\b/i.test(proposal.evidence)
                ) {
                  aiValidationRejected += 1;
                  decision.reason = 'top_depth_requires_explicit_label';
                  continue;
                }

                const rule = FIELD_RULES[proposal.field_key];
                const rawValue = proposalValueForValidation(proposal);
                const validatedRaw = rule ? rule.validate(rawValue) : normalize(rawValue);
                const validated = validatedRaw
                  ? normalizeFinalProposalValue(proposal.field_key, validatedRaw)
                  : null;
                decision.validated_raw = validatedRaw;
                decision.validated_final = validated;
                if (!validated || !normalize(proposal.evidence)) {
                  aiValidationRejected += 1;
                  decision.reason = !validated ? 'frontend_field_validation_failed' : 'missing_evidence';
                  continue;
                }

                const sourceReference =
                  `Page ${candidate.pageNumber} · ${scanModeLabel} · Local AI · ${proposal.value_status}` +
                  (proposal.reference ? ` · ${proposal.reference}` : '');

                const storedValidated = normalizeStoredFieldValue(
                  proposal.field_key,
                  validated,
                );
                found[proposal.field_key] = {
                  fieldKey: proposal.field_key,
                  value: storedValidated,
                  sourceFile: file.name,
                  sourceReference,
                  accepted: null,
                  editedValue: storedValidated,
                  sources: [{
                    file: file.name,
                    reference: `${sourceReference} · Evidence: ${normalize(proposal.evidence)}`,
                    extraction: 'ai',
                  }],
                  alternatives: [],
                };
                aiProposalsAccepted += 1;
                decision.accepted = true;
                decision.reason = 'accepted';
                decision.stored_value = storedValidated;
                decision.source_reference = sourceReference;
              }

              unresolvedFields = unresolvedFields.filter((fieldKey) => !found[fieldKey]);
            } catch (error) {
              aiRequestErrors += 1;
              const detail = error instanceof Error ? error.message : 'Unknown local AI error';
              if (!aiErrorMessages.includes(detail)) aiErrorMessages.push(detail);
            }
          }
        }
      }

      setProposals((current) => mergeProposalMaps(current, found));
      if (scanMode === 'fast') {
        setScannedFileKeys((current) => {
          const next = new Set(current);
          filesToScan.forEach((file) => next.add(fileKey(file)));
          return next;
        });
      }

      diagnosticRun.timings_ms.total = Math.round(performance.now() - diagnosticTotalStarted);
      diagnosticRun.final_found = found;
      diagnosticRun.counters = {
        rejected_documents: rejectedDocuments,
        pages_indexed: pagesIndexed,
        ocr_pages: ocrPages,
        ocr_page_numbers: [...ocrPageNumbers].sort((a, b) => a - b),
        ai_pages_attempted: aiPagesAttempted,
        ai_responses_received: aiResponsesReceived,
        ai_proposals_returned: aiProposalsReturned,
        ai_proposals_accepted: aiProposalsAccepted,
        ai_empty_responses: aiNoProposalResponses,
        ai_well_mismatches: aiWellMismatchResponses,
        ai_validation_rejected: aiValidationRejected,
        ai_structure_centre_rejected: aiStructureCentreRejected,
        ai_other_well_proposals_rejected: aiOtherWellProposalsRejected,
        ai_request_errors: aiRequestErrors,
      };
      const rejectedText = rejectedDocuments ? ` · ${rejectedDocuments} file(s) skipped for well mismatch` : '';
      const aiText = aiStatus?.available
        ? ` · Local AI: ${aiPagesAttempted} attempted, ${aiResponsesReceived} response(s), ` +
          `${aiProposalsReturned} returned, ${aiProposalsAccepted} accepted, ` +
          `${aiNoProposalResponses} empty, ${aiWellMismatchResponses} mismatch, ` +
          `${aiValidationRejected} validation rejection(s), ` +
          `${aiOtherWellProposalsRejected} other-well proposal rejection(s), ` +
          `${aiStructureCentreRejected} structure-centre rejection(s), ` +
          `${aiRequestErrors} request error(s)`
        : ' · Local AI unavailable; rules/OCR only';
      const aiErrorText = aiErrorMessages.length
        ? ` · AI error: ${aiErrorMessages[0]}${aiErrorMessages.length > 1 ? ` (+${aiErrorMessages.length - 1} more)` : ''}`
        : '';
      setMessage(
        `${scanModeLabel} complete · deterministic authority · ${Object.keys(found).length} new validated proposal(s) · ` +
        `${pagesIndexed} page(s) indexed · ${ocrPages} page(s) OCR reviewed ` +
        `[${[...ocrPageNumbers].sort((a, b) => a - b).join(', ')}]${aiText}` +
        `${aiErrorText}${rejectedText}. Existing session values and prior evidence retained.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Supporting-file scan failed.');
    } finally {
      if (scanStartedAtRef.current !== null) {
        setScanElapsedSeconds(
          Math.max(0, Math.round((performance.now() - scanStartedAtRef.current) / 1000)),
        );
      }
      scanStartedAtRef.current = null;
      setBusy(false);
    }
  };

  const setDecision = (fieldKey: string, accepted: boolean) => {
    setProposals((current) => {
      const proposal = current[fieldKey];
      return proposal ? { ...current, [fieldKey]: { ...proposal, accepted } } : current;
    });
  };

  const toggleProposalSelection = (fieldKey: string) => {
    setSelectedProposalKeys((current) => {
      const next = new Set(current);
      if (next.has(fieldKey)) next.delete(fieldKey);
      else next.add(fieldKey);
      return next;
    });
  };

  const selectAllProposals = () => {
    setSelectedProposalKeys(new Set(selectableProposalKeys));
  };

  const clearProposalSelection = () => {
    setSelectedProposalKeys(new Set());
  };

  const acceptSelectedProposals = () => {
    if (selectedProposalKeys.size === 0) return;
    const selected = new Set(selectedProposalKeys);
    setProposals((current) => {
      const next = { ...current };
      selected.forEach((fieldKey) => {
        const proposal = next[fieldKey];
        if (proposal?.accepted === null) {
          next[fieldKey] = { ...proposal, accepted: true };
        }
      });
      return next;
    });
    setSelectedProposalKeys(new Set());
    setMessage(`${selected.size} recommendation(s) accepted for Well Info.`);
  };

  const updateEditedValue = (fieldKey: string, editedValue: string) => {
    setProposals((current) => {
      const proposal = current[fieldKey];
      const canonicalEditedValue = canonicalizeStoredMetadataValue(editedValue);
      return proposal
        ? { ...current, [fieldKey]: { ...proposal, editedValue: canonicalEditedValue } }
        : current;
    });
  };


  const beginFieldEdit = (row: ContextRow, proposal?: Proposal) => {
    const currentValue =
      proposal?.accepted === true
        ? proposal.value
        : row.value || proposal?.value || '';

    const currentSource =
      proposal?.accepted === true
        ? proposal.sourceFile
        : row.source || proposal?.sourceFile || '';

    setEditingFieldKey(row.fieldKey);
    setEditingValue(canonicalizeStoredMetadataValue(currentValue));
    setEditingSource(normalize(currentSource));
  };

  const acceptFieldEdit = (row: ContextRow) => {
    const committedValue = canonicalizeStoredMetadataValue(editingValue);
    const committedSource = normalize(editingSource) || 'User entered';

    setRows((current) =>
      current.map((item) =>
        item.fieldKey === row.fieldKey
          ? {
              ...item,
              value: committedValue,
              source: committedSource,
              sourceReference: 'Manual edit',
            }
          : item,
      ),
    );

    setProposals((current) => {
      const previous = current[row.fieldKey];
      const manualSource: ProposalSource = {
        file: committedSource,
        reference: 'Manual edit',
        extraction: 'structured',
      };

      return {
        ...current,
        [row.fieldKey]: {
          fieldKey: row.fieldKey,
          value: committedValue,
          sourceFile: committedSource,
          sourceReference: 'Manual edit',
          accepted: true,
          editedValue: committedValue,
          sources: previous
            ? [...previous.sources.filter((source) => source.reference !== 'Manual edit'), manualSource]
            : [manualSource],
          alternatives: previous?.alternatives ?? [],
        },
      };
    });

    setEditingFieldKey(null);
    setEditingValue('');
    setEditingSource('');
    setMessage(`${row.field || row.fieldKey} updated manually.`);
  };

  const rejectFieldEdit = () => {
    setEditingValue('');
    setEditingSource('');
  };

  const toggleAllSupportingFiles = () => {
    if (selectedSupportingFileIndexes.size === supportFiles.length && supportFiles.length > 0) {
      setSelectedSupportingFileIndexes(new Set());
      return;
    }
    setSelectedSupportingFileIndexes(new Set(supportFiles.map((_, index) => index)));
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
        const file = supportFiles[index];
        if (file) delete next[file.name];
      });
      return next;
    });
  };

  const toggleAllDeterministicSupportingFiles = () => {
    const selected = Array.from(selectedSupportingFileIndexes);
    const allSelectedAreScreened = selected.length > 0
      && selected.every((index) => deterministicSupportingFileIndexes.has(index));
    invalidatePreScanForIndexes(selected);
    setDeterministicSupportingFileIndexes(allSelectedAreScreened ? new Set() : new Set(selected));
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

  const addSupportingFiles = async (files: File[]) => {
    const incoming: File[] = [];
    const newlySkipped: SkippedArchiveMember[] = [];

    for (const file of files) {
      if (
        file.name.toLowerCase().endsWith('.zip')
        || file.type === 'application/zip'
        || file.type === 'application/x-zip-compressed'
      ) {
        setMessage(`Expanding supporting archive ${file.name}…`);
        try {
          const expanded = await expandZipSupportingFile(file);
          incoming.push(...expanded.files.filter((member) => /\.(pdf|xlsx|xls|csv|txt|json)$/i.test(member.name)));
          newlySkipped.push(...expanded.skipped.map((item) => ({
            archive: file.name,
            member: item.member,
            reason: item.reason,
          })));
        } catch (error) {
          setMessage(error instanceof Error ? error.message : `Could not expand ${file.name}.`);
          return;
        }
      } else if (/\.(pdf|xlsx|xls|csv|txt|json)$/i.test(file.name)) {
        incoming.push(file);
      }
    }

    const existingKeys = new Set(supportFilesRef.current.map(fileKey));
    const appended = incoming.filter((file) => !existingKeys.has(fileKey(file)));
    if (!appended.length) {
      if (newlySkipped.length) setSkippedArchiveMembers((current) => [...current, ...newlySkipped]);
      setMessage('No new supported supporting files were added.');
      return;
    }

    const existingCount = supportFilesRef.current.length;
    const nextFiles = [...supportFilesRef.current, ...appended];
    supportFilesRef.current = nextFiles;
    setSupportFiles(nextFiles);
    setSupportingFileNames((names) => [...new Set([...names, ...appended.map((file) => file.name)])]);
    setSelectedSupportingFileIndexes((current) => {
      const next = new Set(current);
      appended.forEach((_, offset) => next.add(existingCount + offset));
      return next;
    });
    setDeterministicSupportingFileIndexes((current) => {
      const next = new Set(current);
      appended.forEach((_, offset) => next.add(existingCount + offset));
      return next;
    });
    setSupportingFilePreScanResults({});
    setSupportingFileAuditResults({});
    setActiveSupportingFileAudit(null);
    setSupportingManifestCollapsed(false);
    if (newlySkipped.length) setSkippedArchiveMembers((current) => [...current, ...newlySkipped]);
    setMessage(`${appended.length} supporting file(s) staged. Select files and screening mode, then Run Pre-Scan.`);
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
    const selectedIndexes = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b);
    if (!selectedIndexes.length) {
      setMessage('Select at least one supporting file for pre-scan.');
      return;
    }

    setPreScanRunning(true);
    setMessage(`Preparing ${selectedIndexes.length} selected supporting file(s)…`);
    let rememberedFailureChoice: DeterministicFailureChoice | null = null;

    try {
      const managedAiRules = await fetchToolboxAiRules('WME');
      const combinedRules = { ...managedAiRules.rules } as Record<string, unknown>;
      const deterministicProfile = (
        combinedRules.deterministic_screening
        && typeof combinedRules.deterministic_screening === 'object'
        && !Array.isArray(combinedRules.deterministic_screening)
      ) ? combinedRules.deterministic_screening as Record<string, unknown> : {};
      const signature = JSON.stringify(deterministicProfile);

      const nextResults = { ...supportingFilePreScanResults };
      const nextAudit = { ...supportingFileAuditResults };

      for (const sourceIndex of selectedIndexes) {
        const file = supportFiles[sourceIndex];
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
          && cached.deterministicProfileSignature === signature
        ) continue;

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
            deterministicProfileSignature: signature,
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
            reason: 'Full original selected by operator.',
          };
          continue;
        }

        const makeRequest = (profile: Record<string, unknown>) => fetch(
          wmeApiUrl('/api/toolbox/ai-revisions/qualification/prepare'),
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

        let response = await makeRequest(deterministicProfile);
        if (!response.ok) {
          let detail = `Deterministic pre-screen returned ${response.status}`;
          try {
            const body = await response.json() as { detail?: unknown };
            if (body?.detail) detail = String(body.detail);
          } catch {}

          const rememberedUsable = rememberedFailureChoice !== 'bypass_scoring'
            || /minimum direct score/i.test(detail);
          const decision: DeterministicFailureDecision = rememberedFailureChoice && rememberedUsable
            ? { choice: rememberedFailureChoice, remember: true }
            : await requestDeterministicFailureChoice(file.name, detail);
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
              reason: detail,
            };
            continue;
          }

          if (decision.choice === 'full_original') {
            const preparedEvidence: PreparedEvidenceFile = {
              name: file.name,
              mime_type: file.type || 'application/octet-stream',
              size: file.size,
              content_base64: payload.content_base64,
              deterministic_screening: false,
              selected_pdf_pages_preserved: file.type === 'application/pdf',
            };
            nextResults[sourceIndex] = {
              sourceIndex,
              sourceName: file.name,
              sourceSha256: payload.sha256,
              deterministicRequested: true,
              standardVersion: managedAiRules.active_version,
              deterministicProfileSignature: signature,
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
              reason: detail,
            };
            continue;
          }

          response = await makeRequest({ ...deterministicProfile, bypass_min_direct_score: true });
          if (!response.ok) {
            delete nextResults[sourceIndex];
            nextAudit[file.name] = {
              fileName: file.name,
              requestedMode: 'deterministic',
              completionStatus: 'pending',
              payloadBytes: 0,
              selectedPageCount: 0,
              totalPages: null,
              reason: `${detail} Bypass scoring retry failed.`,
            };
            continue;
          }
        }

        const prepared = await response.json() as EvidencePreparationResponse;
        let preparedEvidence = prepared.prepared_evidence?.[0];
        if (!preparedEvidence) throw new Error(`${file.name}: deterministic pre-scan returned no prepared payload.`);
        let evidencePreparation = prepared.evidence_preparation?.find((item) => item.name === file.name)
          ?? prepared.evidence_preparation?.[0]
          ?? null;

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
              deterministic_screening: false,
              selected_pdf_pages_preserved: file.type === 'application/pdf',
            };
            evidencePreparation = {
              ...(evidencePreparation ?? { name: file.name, mode: 'full_original_graphics_override', original_size: file.size }),
              mode: 'full_original_graphics_override',
              prepared_size: file.size,
            };
          }
        }

        const payloadBytes = Math.max(0, Math.floor((preparedEvidence.content_base64.length * 3) / 4));
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
          deterministicProfileSignature: signature,
          preparedEvidence,
          evidencePreparation,
          estimatedEvidenceTokens: Number(prepared.estimated_evidence_tokens || 0),
        };
        nextAudit[file.name] = {
          fileName: file.name,
          requestedMode: 'deterministic',
          completionStatus,
          payloadBytes,
          selectedPageCount: Number(evidencePreparation?.selected_page_count || preparedEvidence.source_pages?.length || 0),
          totalPages: Number(evidencePreparation?.total_pages || 0) || null,
          reason: evidencePreparation?.mode === 'full_original_graphics_override'
            ? 'Operator selected full original after high graphics-risk warning.'
            : 'Deterministic pre-scan completed.',
        };
      }

      setSupportingFilePreScanResults(nextResults);
      setSupportingFileAuditResults(nextAudit);
      const unresolved = selectedIndexes.filter((index) => !nextResults[index]).length;
      setMessage(
        unresolved
          ? `Document pre-scan completed with ${unresolved} unresolved selected file(s).`
          : `Document pre-scan completed for ${selectedIndexes.length} selected file(s). Review the manifest, then export.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Document pre-scan failed.');
    } finally {
      setPreScanRunning(false);
    }
  };

  const clearExtractor = () => {
    sessionStorage.removeItem(WME_SESSION_KEY);
    setWorkbook(null);
    setWorkbookBase64('');
    setSheetName('');
    setContextFileName('');
    setRows([]);
    setSupportFiles([]);
    supportFilesRef.current = [];
    setSupportingFileNames([]);
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
    setScannedFileKeys(new Set());
    setProposals({});
    setSelectedProposalKeys(new Set());
    setMessage('Load an exported Well Info workbook to begin.');
    setBusy(false);
    setExportNotice('');
    setScanElapsedSeconds(0);
    scanStartedAtRef.current = null;
    setSelectedScanMode('fast');
    setDragTarget(null);
    setEditingFieldKey(null);
    setEditingValue('');
    setEditingSource('');
  };

  const handleDrop = (event: React.DragEvent<HTMLElement>, target: 'context' | 'support') => {
    event.preventDefault();
    setDragTarget(null);
    const files = Array.from(event.dataTransfer.files ?? []);
    if (target === 'context') {
      const context = files.find((file) => /\.(xlsx|xls)$/i.test(file.name));
      if (context) void loadContext(context);
      return;
    }
    void addSupportingFiles(files);
  };

  const wmeRevisionAuthority = rows.find((row) => row.fieldKey === 'well_name')?.value || rows.find((row) => row.fieldKey === 'wellbore_name')?.value || contextFileName;
  const aiRevision = useToolboxAiRevision('WME', wmeRevisionAuthority);

  const exportAiPackage = async () => {
    if (!workbook || !sheetName || selectedSupportingFileIndexes.size === 0 || busy) return;
    scanStartedAtRef.current = performance.now();
    setScanElapsedSeconds(0);
    setBusy(true);
    setExportNotice('');
    setMessage('Building AI package…');
    try {
      const packageWorkbook = XLSX.read(base64ToArrayBuffer(workbookBase64), { type: 'array', cellStyles: true });
      const contextSheetName = packageWorkbook.SheetNames[0];
      const contextRows = XLSX.utils.sheet_to_json<unknown[]>(packageWorkbook.Sheets[contextSheetName], { header: 1, raw: false, defval: '' });
      const contextHeaders = detectHeaders(contextRows);
      if (!contextHeaders) throw new Error('Context workbook does not contain the Well Info schema headers.');
      const exportedKeys = new Set(contextRows.slice(contextHeaders.headerRow + 1).map((row) => String(row[contextHeaders.columns.fieldKey] ?? '').trim()).filter(Boolean));
      const requiredV2Keys = ['depth_reference', 'reference_elevation', 'surface_seabed_elevation', 'seabed_depth_below_reference', 'wellhead_depth_below_reference', 'total_depth_md', 'total_depth_tvd', 'survey_start_md', 'survey_end_md', 'survey_start_tvd', 'survey_end_tvd', 'data_start_md', 'data_end_md'];
      const missingV2Keys = requiredV2Keys.filter((key) => !exportedKeys.has(key));
      const forbiddenLegacyKeys = ['top_depth', 'base_depth', 'rt_kb_elevation', 'wellhead_seabed_depth', 'first_md', 'final_md', 'final_tvd'].filter((key) => exportedKeys.has(key));
      if (missingV2Keys.length || forbiddenLegacyKeys.length) {
        throw new Error(`Context workbook schema mismatch. Missing V2 keys: ${missingV2Keys.join(', ') || 'none'}; legacy keys present: ${forbiddenLegacyKeys.join(', ') || 'none'}. Re-export Well Info after installing schema V2.`);
      }
      const packageBytes = XLSX.write(packageWorkbook, { bookType: 'xlsx', type: 'array', compression: true }) as ArrayBuffer;
      const form = new FormData();
      const managedAiRules = await fetchToolboxAiRules('WME');
      const combinedRules = { ...managedAiRules.rules } as Record<string, unknown>;
      const deterministicProfile = (
        combinedRules.deterministic_screening
        && typeof combinedRules.deterministic_screening === 'object'
        && !Array.isArray(combinedRules.deterministic_screening)
      ) ? combinedRules.deterministic_screening as Record<string, unknown> : {};
      const deterministicProfileSignature = JSON.stringify(deterministicProfile);

      const selectedIndexes = Array.from(selectedSupportingFileIndexes).sort((a, b) => a - b);
      const selectedResults = selectedIndexes.map((index) => {
        const file = supportFiles[index];
        const result = supportingFilePreScanResults[index];
        if (!file || !result) throw new Error('All selected supporting files must be resolved by Run Pre-Scan before export.');
        if (
          result.sourceName !== file.name
          || result.deterministicRequested !== deterministicSupportingFileIndexes.has(index)
          || result.standardVersion !== managedAiRules.active_version
          || result.deterministicProfileSignature !== deterministicProfileSignature
        ) throw new Error(`${file.name}: pre-scan result is stale. Run Pre-Scan again.`);
        return result;
      });

      const decodePreparedFile = (result: SupportingFilePreScanResult): File => {
        const buffer = base64ToArrayBuffer(result.preparedEvidence.content_base64);
        return new File(
          [buffer],
          result.preparedEvidence.name,
          { type: result.preparedEvidence.mime_type || 'application/octet-stream' },
        );
      };

      const preparedFiles = selectedResults.map(decodePreparedFile);


      form.append('context_workbook', new Blob([packageBytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), contextFileName || 'Well_Info_Context.xlsx');
      preparedFiles.forEach((file) => form.append('supporting_files', file, file.name));

      const packageRevision = await aiRevision.allocateExport();
      form.append('job_manifest', JSON.stringify({
        schema_version: WELL_INFO_SCHEMA_VERSION,
        managed_ai_rules: combinedRules,
        managed_ai_rules_version: managedAiRules.active_version,
        managed_ai_rules_updated_at: managedAiRules.updated_at,
        managed_ai_rules_are_authoritative_overrides: true,
        revision: toolboxAiPackageRevision('WME', packageRevision),
        expected_response_revision: toolboxAiExpectedResponseRevision(packageRevision),
        context_file: contextFileName,
        well_name: rows.find((row) => row.fieldKey === 'well_name')?.value || '',
        wellbore_name: rows.find((row) => row.fieldKey === 'wellbore_name')?.value || '',
        requested_fields: rows.filter((row) => !row.value).map((row) => row.fieldKey),
        deterministic_screening: {
          execution: 'application_side_completed_before_export',
          profile: deterministicProfile,
          evidence_preparation: selectedResults.map((result) => result.evidencePreparation).filter(Boolean),
          source_files: selectedResults.map((result) => ({
            name: result.sourceName,
            sha256: result.sourceSha256,
            deterministic_requested: result.deterministicRequested,
          })),
        },
      }));

      const response = await fetch(wmeApiUrl('/api/wme/exchange/package'), { method: 'POST', body: form });
      if (!response.ok) throw new Error(await response.text() || `AI package export failed (${response.status}).`);
      const blob = await response.blob();
      const disposition = response.headers.get('content-disposition') || '';
      const matched = disposition.match(/filename="?([^";]+)"?/i);
      const serverFilename = matched?.[1] || 'WME_AI_PACKAGE.zip';
      const wellName = rows.find((row) => row.fieldKey === 'well_name')?.value || rows.find((row) => row.fieldKey === 'wellbore_name')?.value || serverFilename.replace(/\.zip$/i, '');
      const filename = toolboxAiPackageFilename('WME_AI_PACKAGE', wellName, packageRevision, 'zip');
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);

      setExportNotice(`${filename} exported to Downloads.`);
      setMessage(`AI package ready from ${selectedResults.length} resolved supporting file(s). Submit it with the included instructions, then drag the completed Context workbook back into WME.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to export AI package.');
    } finally {
      const startedAt = scanStartedAtRef.current;
      if (startedAt !== null) {
        setScanElapsedSeconds(Math.max(0, Math.ceil((performance.now() - startedAt) / 1000)));
      }
      scanStartedAtRef.current = null;
      setBusy(false);
    }
  };

  const applyToWellInfo = () => {
    if (!onApplyToWellInfo) return;
    const values: Record<string, { value: string; unit?: string; source?: string; sourceReference?: string; notes?: string }> = {};
    for (const row of rows) {
      const proposal = proposals[row.fieldKey];
      if (proposal?.accepted !== true) continue;
      const value = canonicalizeStoredMetadataValue(proposal.editedValue || proposal.value);
      if (!value) continue;
      values[row.fieldKey] = {
        value,
        unit: row.aiUnit || row.unit || undefined,
        source: proposal.sourceFile || 'WME reviewed recommendation',
        sourceReference: proposal.sourceReference || undefined,
        notes: row.aiEvidence || row.notes || undefined,
      };
    }
    if (Object.keys(values).length === 0) {
      setMessage('Accept at least one AI recommendation before applying to Well Info.');
      return;
    }
    onApplyToWellInfo(values);
  };

  const exportWorkbook = () => {
    if (!workbook || !sheetName) return;
    const sheet = workbook.Sheets[sheetName];
    const data = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, raw: false, defval: '' });
    const headers = detectHeaders(data);
    if (!headers) {
      setMessage('The workbook structure changed and can no longer be exported.');
      return;
    }

    let exportedProposalCount = 0;

    for (const row of rows) {
      const proposal = proposals[row.fieldKey];
      if (!proposal) continue;

      const value =
        proposal.accepted === false
          ? proposal.editedValue.trim()
          : proposal.value.trim();

      if (!value) continue;

      XLSX.utils.sheet_add_aoa(sheet, [[value]], {
        origin: { r: row.rowNumber - 1, c: headers.columns.value },
      });

      if (headers.columns.source >= 0) {
        XLSX.utils.sheet_add_aoa(sheet, [[proposal.sourceFile || 'Supporting document']], {
          origin: { r: row.rowNumber - 1, c: headers.columns.source },
        });
      }

      if (headers.columns.sourceReference >= 0) {
        XLSX.utils.sheet_add_aoa(sheet, [[proposal.sourceReference || proposal.sourceFile]], {
          origin: { r: row.rowNumber - 1, c: headers.columns.sourceReference },
        });
      }

      exportedProposalCount += 1;
    }

    const stem = contextFileName.replace(/\.(xlsx|xls)$/i, '') || 'Well_Info_Context';
    XLSX.writeFile(workbook, `${stem}_COMPLETED.xlsx`);
    setExportNotice(
      `${exportedProposalCount} populated proposal(s) exported with the completed workbook.`,
    );
  };

  const unresolved = Object.values(proposals).filter((proposal) => proposal.accepted === null).length;
  const exportable = Object.values(proposals).some((proposal) =>
    proposal.accepted === false
      ? Boolean(proposal.editedValue.trim())
      : Boolean(proposal.value.trim()),
  );

  // The former embedded extraction implementation remains temporarily quarantined
  // for rollback compatibility, but it is intentionally not exposed by the exchange UI.
  // Keep these references until the retired implementation is removed in a dedicated cleanup.
  void selectedScanMode;
  void crawlDocuments;
  void exportWorkbook;
  void exportable;

  return (
    <section className="wlv-metadata-tool">
      {activeSupportingFileAudit ? <div role="dialog" aria-modal="true" style={{position:'fixed',inset:0,zIndex:12000,background:'rgba(0,0,0,0.6)',display:'grid',placeItems:'center'}}><div style={{width:'min(640px,calc(100vw - 40px))',background:'#151b21',border:'1px solid #465466',padding:'16px',color:'#dbe3eb'}}><strong>{activeSupportingFileAudit.fileName}</strong><div style={{fontSize:'11px',whiteSpace:'pre-wrap',marginTop:'8px'}}>Requested mode: {activeSupportingFileAudit.requestedMode}{'\n'}Completion status: {activeSupportingFileAudit.completionStatus}{'\n'}Payload: {activeSupportingFileAudit.payloadBytes.toLocaleString()} bytes{'\n'}Pages: {activeSupportingFileAudit.selectedPageCount}{activeSupportingFileAudit.totalPages?` / ${activeSupportingFileAudit.totalPages}`:''}{'\n'}Reason: {activeSupportingFileAudit.reason}</div><button type="button" onClick={()=>setActiveSupportingFileAudit(null)}>Close</button></div></div> : null}
      {deterministicFailurePrompt ? <div role="dialog" aria-modal="true" style={{position:'fixed',inset:0,zIndex:12000,background:'rgba(0,0,0,0.6)',display:'grid',placeItems:'center'}}><div style={{width:'min(700px,calc(100vw - 40px))',background:'#151b21',border:'1px solid #465466',padding:'16px',color:'#dbe3eb'}}><strong>Deterministic screening unavailable for this document</strong><div style={{fontSize:'11px',marginTop:'8px'}}>{deterministicFailurePrompt.fileName}</div><div style={{fontSize:'11px',whiteSpace:'pre-wrap',marginTop:'8px'}}>{deterministicFailurePrompt.detail}</div><label><input type="checkbox" checked={rememberDeterministicFailureChoice} onChange={e=>setRememberDeterministicFailureChoice(e.target.checked)}/> Remember this answer for the rest of this pre-scan</label><div style={{display:'flex',gap:'8px',justifyContent:'flex-end'}}><button type="button" onClick={()=>resolveDeterministicFailureChoice('cancel')}>Leave unresolved</button><button type="button" onClick={()=>resolveDeterministicFailureChoice('full_original')}>Use full original</button>{deterministicFailurePrompt.canBypassScoring?<button type="button" onClick={()=>resolveDeterministicFailureChoice('bypass_scoring')}>Bypass scoring</button>:null}</div></div></div> : null}
      {graphicsChoiceFiles ? <div role="dialog" aria-modal="true" style={{position:'fixed',inset:0,zIndex:12000,background:'rgba(0,0,0,0.6)',display:'grid',placeItems:'center'}}><div style={{width:'min(700px,calc(100vw - 40px))',background:'#151b21',border:'1px solid #465466',padding:'16px',color:'#dbe3eb'}}><strong>High graphical-content risk</strong><div style={{fontSize:'11px',marginTop:'8px'}}>{graphicsChoiceFiles.join(', ')}</div><div style={{display:'flex',gap:'8px',justifyContent:'flex-end'}}><button type="button" onClick={()=>resolveGraphicsExportChoice('cancel')}>Leave unresolved</button><button type="button" onClick={()=>resolveGraphicsExportChoice('full_original')}>Use full original document</button><button type="button" onClick={()=>resolveGraphicsExportChoice('selected_pages')}>Use deterministic selected pages</button></div></div></div> : null}

      <header className="wlv-metadata-tool__header">
        <button type="button" className="wlv-metadata-tool__back" onClick={onBack}>‹ Toolbox</button>
        <div className="wlv-metadata-tool__title">
          <h1>Well Metadata Exchange</h1>
          <p>Prepare external AI packages, review returned recommendations, and apply approved values to Well Info.</p>
        </div>
        <div className="wlv-metadata-tool__window-actions">
          <button type="button" onClick={clearExtractor}>Clear</button>
          <button type="button" className="wlv-metadata-tool__close" aria-label="Close Well Metadata Extractor" onClick={onBack}>×</button>
        </div>
      </header>

      <div className="wlv-metadata-tool__input-grid">
        <section
          className={`wlv-metadata-tool__drop-panel ${dragTarget === 'context' ? 'is-dragging' : ''}`}
          onDragEnter={(event) => { event.preventDefault(); event.stopPropagation(); setDragTarget('context'); }}
          onDragOver={(event) => { event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'copy'; }}
          onDragLeave={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (event.currentTarget === event.target) setDragTarget(null);
          }}
          onDrop={(event) => handleDrop(event, 'context')}
        >
          <div className="wlv-metadata-tool__drop-copy">
            <strong>Context workbook</strong>
            <span>{contextFileName || 'Drop exported Well Info .xlsx here'}</span>
          </div>
          <button type="button" onClick={() => contextInput.current?.click()}>Browse</button>
          <input ref={contextInput} type="file" accept=".xlsx,.xls" hidden onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void loadContext(file);
            event.currentTarget.value = '';
          }} />
        </section>

        <section
          className={`wlv-metadata-tool__drop-panel ${dragTarget === 'support' ? 'is-dragging' : ''} ${!workbook ? 'is-disabled' : ''}`}
          onDragEnter={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (workbook) setDragTarget('support');
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (workbook) event.dataTransfer.dropEffect = 'copy';
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (event.currentTarget === event.target) setDragTarget(null);
          }}
          onDrop={(event) => {
            if (!workbook) {
              event.preventDefault();
              return;
            }
            handleDrop(event, 'support');
          }}
        >
          <div className="wlv-metadata-tool__drop-copy">
            <strong>Supporting files</strong>
            <span>
              {supportFiles.length
                ? `${supportFiles.length} staged · ${selectedSupportingFileIndexes.size} selected`
                : supportingFileNames.length
                  ? `${supportingFileNames.length} file(s) retained in session`
                  : 'Drop PDF, XLSX, CSV, TXT, JSON or ZIP bundle here'}
            </span>
          </div>
          <button type="button" disabled={!workbook} onClick={() => supportInput.current?.click()}>Browse</button>
          <input ref={supportInput} type="file" multiple accept=".pdf,.xlsx,.xls,.csv,.txt,.json,.zip" hidden onChange={(event) => {
            void addSupportingFiles(Array.from(event.target.files ?? []));
            event.currentTarget.value = '';
          }} />
        </section>
      </div>

      
      {(supportFiles.length > 0 || skippedArchiveMembers.length > 0) ? <section style={{width:'calc(100% - 24px)',maxWidth:'1136px',margin:'0 auto 12px',border:'1px solid #34414f',borderRadius:'5px',overflow:'hidden',background:'#151b21'}}>
        <div style={{display:'flex',justifyContent:'space-between',padding:'9px 12px'}}>
          <div><strong>Supporting file manifest</strong><span style={{display:'block',fontSize:'10px',color:'#93a1b0'}}>Select files and screening mode, Run Pre-Scan, review Status/Payload/Audit, then export.</span></div>
          <button type="button" onClick={()=>setSupportingManifestCollapsed(v=>!v)}>{supportingManifestCollapsed?'▸':'▾'}</button>
        </div>
        <div hidden={supportingManifestCollapsed}>
          <div style={{display:'grid',gridTemplateColumns:'112px minmax(0,1fr) 82px 128px 132px 92px 42px',fontSize:'10px',fontWeight:600}}>
            <label><input type="checkbox" checked={supportFiles.length>0&&selectedSupportingFileIndexes.size===supportFiles.length} onChange={toggleAllSupportingFiles}/> SELECT FILES</label><div>FILE / ZIP MEMBER</div><div>SIZE</div>
            <label><input type="checkbox" checked={selectedSupportingFileIndexes.size>0&&Array.from(selectedSupportingFileIndexes).every(i=>deterministicSupportingFileIndexes.has(i))} onChange={toggleAllDeterministicSupportingFiles}/> DETERMINISTIC</label><div>COMPLETION STATUS</div><div>PAYLOAD</div><div>AUDIT</div>
          </div>
          {supportFiles.map((file,index)=>{const audit=supportingFileAuditResults[file.name];return <div key={`${file.name}-${index}`} style={{display:'grid',gridTemplateColumns:'112px minmax(0,1fr) 82px 128px 132px 92px 42px',fontSize:'10px',alignItems:'center'}}><div><input type="checkbox" checked={selectedSupportingFileIndexes.has(index)} onChange={()=>toggleSupportingFile(index)}/></div><div>{file.name}</div><div>{file.size>=1048576?`${(file.size/1048576).toFixed(2)} MB`:`${(file.size/1024).toFixed(1)} KB`}</div><div><label><input type="checkbox" disabled={!selectedSupportingFileIndexes.has(index)} checked={deterministicSupportingFileIndexes.has(index)} onChange={()=>toggleDeterministicSupportingFile(index)}/> {deterministicSupportingFileIndexes.has(index)?'Screen':'Full'}</label></div><div>{audit?(audit.completionStatus==='screened'?'Screened':audit.completionStatus==='full_scan_fallback'?'Full scan fallback':audit.completionStatus==='full_scan_graphics'?'Full scan · graphics':'Full original'):'Pending'}</div><div>{audit?.payloadBytes?(audit.payloadBytes>=1048576?`${(audit.payloadBytes/1048576).toFixed(2)} MB`:`${(audit.payloadBytes/1024).toFixed(1)} KB`):'—'}</div><div><button type="button" disabled={!audit} onClick={()=>audit&&setActiveSupportingFileAudit(audit)}>ⓘ</button></div></div>})}
          <div style={{display:'grid',gridTemplateColumns:'112px minmax(0,1fr) 82px 128px 132px 92px 42px',fontSize:'10px',fontWeight:700}}>
            <div>EXPORT TOTALS</div><div>{selectedSupportingFileIndexes.size} selected</div><div>{(Array.from(selectedSupportingFileIndexes).reduce((s,i)=>s+Number(supportFiles[i]?.size||0),0)/1048576).toFixed(2)} MB</div><div>{Array.from(selectedSupportingFileIndexes).filter(i=>!supportingFilePreScanResults[i]).length?`${Array.from(selectedSupportingFileIndexes).filter(i=>!supportingFilePreScanResults[i]).length} pending`:'Ready'}</div><div/><div>{(Array.from(selectedSupportingFileIndexes).reduce((s,i)=>s+Number(supportingFileAuditResults[supportFiles[i]?.name]?.payloadBytes||0),0)/1048576).toFixed(2)} MB</div><div/></div>
          {skippedArchiveMembers.length>0?<details><summary>Skipped archive members ({skippedArchiveMembers.length})</summary>{skippedArchiveMembers.map((item,index)=><div key={`${item.archive}-${item.member}-${index}`}>{item.archive}::{item.member} — {item.reason}</div>)}</details>:null}
        </div>
      </section> : null}
<div className="wlv-metadata-tool__action-row">
        <button type="button" disabled={!workbook || selectedSupportingFileIndexes.size === 0 || busy || preScanRunning} onClick={() => void runSupportingFilePreScan()}>
          {preScanRunning ? 'Pre-Scanning…' : 'Run Pre-Scan'}
        </button>
        <button type="button" disabled={!workbook || selectedSupportingFileIndexes.size === 0 || busy || preScanRunning || Array.from(selectedSupportingFileIndexes).some((index) => !supportingFilePreScanResults[index])} onClick={() => void exportAiPackage()}>
          {busy ? 'Building AI package…' : 'Export AI package'}
        </button>
        <span className="wlv-toolbox-ai-revision" style={{ color: '#9ca9b7', fontSize: '10px', fontWeight: 600, whiteSpace: 'nowrap' }}>{workbook ? `AI Review Cycle: ${aiRevision.currentLabel} · Next export: ${aiRevision.nextLabel}` : 'AI Review Cycle: —'}</span>
        <button type="button" disabled={!Object.values(proposals).some((proposal) => proposal.accepted === true)} onClick={applyToWellInfo}>
          Apply reviewed values to Well Info
        </button>
        <span className="wlv-metadata-tool__session-summary">
          {rows.length ? `${rows.length} fields` : 'No context loaded'}
          {supportingFileNames.length ? ` · ${supportingFileNames.length} supporting file(s)` : ''}
          {Object.keys(proposals).length ? ` · ${Object.keys(proposals).length} recommendation(s)` : ''}
        </span>
      </div>

      <div className="wlv-metadata-tool__message" role="status">
        <span>
          {message}
          {exportNotice ? ` · Export: ${exportNotice}` : ''}
        </span>
        <span className="wlv-metadata-tool__scan-duration">
          · Duration: {formattedScanDuration}
        </span>
      </div>

      <section className="wlv-metadata-tool__review">
        <header>
          <h2>Context fields</h2>
          <div
            className="wlv-ftm-tool__bulk-selection"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px', marginLeft: 'auto', fontSize: '10px', fontWeight: 600 }}
          >
            <span>{rows.length || 0}</span>
            <button type="button" onClick={selectAllProposals} disabled={selectableProposalKeys.length === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Select All</button>
            <button type="button" onClick={clearProposalSelection} disabled={selectedProposalKeys.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Select None</button>
            <button type="button" onClick={acceptSelectedProposals} disabled={selectedProposalKeys.size === 0} style={{ fontSize: '10px', fontWeight: 600 }}>Accept</button>
          </div>
        </header>

        <div className="wlv-metadata-tool__table-wrap">
          <table>
            <thead>
              <tr><th>Field</th><th>Value</th><th>Source</th><th>Action</th></tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={4} className="is-empty">Load a context workbook.</td></tr>
              ) : rows.map((row) => {
                const proposal = proposals[row.fieldKey];
                const editing = editingFieldKey === row.fieldKey;
                const effectiveValue =
                  proposal?.accepted === true
                    ? proposal.value
                    : row.value || proposal?.value || '';
                const effectiveSource =
                  proposal?.accepted === true
                    ? proposal.sourceFile
                    : row.source || proposal?.sourceFile || '';
                const populated = Boolean(effectiveValue);

                return (
                  <tr key={row.fieldKey} className={populated ? 'is-populated' : ''}>
                    <td><strong>{displayMetadataFieldLabel(row.fieldKey, row.field || row.fieldKey)}</strong><small>{displayMetadataSectionLabel(row.section)}</small></td>

                    <td
                      className="wlv-metadata-tool__editable-value"
                      onClick={() => {
                        if (!editing) beginFieldEdit(row, proposal);
                      }}
                    >
                      {editing ? (
                        <input
                          autoFocus
                          value={editingValue}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => setEditingValue(event.target.value)}
                          aria-label={`Edit value for ${displayMetadataFieldLabel(row.fieldKey, row.field || row.fieldKey)}`}
                        />
                      ) : populated ? (
                        <span>{formatMetadataValue(row.fieldKey, effectiveValue, row.unit, proposals.depth_reference?.accepted === true ? proposals.depth_reference.value : rows.find((candidate) => candidate.fieldKey === 'depth_reference')?.value || proposals.depth_reference?.value || '')}</span>
                      ) : (
                        <span className="is-missing">—</span>
                      )}
                    </td>

                    <td
                      className="wlv-metadata-tool__editable-source"
                      onClick={() => {
                        if (!editing) beginFieldEdit(row, proposal);
                      }}
                    >
                      {editing ? (
                        <input
                          value={editingSource}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => setEditingSource(event.target.value)}
                          aria-label={`Edit source for ${row.field || row.fieldKey}`}
                        />
                      ) : effectiveSource ? (
                        <>
                          <span>{effectiveSource}</span>
                          <small>
                            {proposal?.accepted === true
                              ? proposal.sourceReference
                              : row.sourceReference || proposal?.sourceReference}
                          </small>
                        </>
                      ) : (
                        <span className="is-missing">Not found</span>
                      )}
                    </td>

                    <td>
                      {editing ? (
                        <div className="wlv-metadata-tool__actions">
                          <button type="button" onClick={() => acceptFieldEdit(row)}>Accept</button>
                          <button type="button" onClick={rejectFieldEdit}>Reject</button>
                        </div>
                      ) : proposal?.accepted === null ? (
                        <div className="wlv-metadata-tool__actions">
                          <label
                            style={{ display: 'inline-flex', alignItems: 'center', marginRight: '6px' }}
                            onClick={(event) => event.stopPropagation()}
                            title="Select recommendation"
                          >
                            <input
                              type="checkbox"
                              checked={selectedProposalKeys.has(row.fieldKey)}
                              onChange={() => toggleProposalSelection(row.fieldKey)}
                              aria-label={`Select ${row.field || row.fieldKey}`}
                              style={{ width: '13px', height: '13px', margin: 0 }}
                            />
                          </label>
                          <button type="button" onClick={() => {
                            setProposals((current) => ({ ...current, [row.fieldKey]: { ...current[row.fieldKey], accepted: true } }));
                            setMessage(`${row.field || row.fieldKey} accepted for Well Info.`);
                          }}>Accept</button>
                          <button type="button" onClick={() => {
                            setProposals((current) => ({ ...current, [row.fieldKey]: { ...current[row.fieldKey], accepted: false } }));
                            setMessage(`${row.field || row.fieldKey} rejected.`);
                          }}>Reject</button>
                        </div>
                      ) : populated ? (
                        <span className="wlv-metadata-tool__loaded">
                          {proposal?.accepted === true ? 'Accepted' : proposal?.accepted === false ? 'Rejected' : 'Loaded'}
                        </span>
                      ) : (
                        <span className="is-missing">—</span>
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

export default WellMetadataExtractorPage;
