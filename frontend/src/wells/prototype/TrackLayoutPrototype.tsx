import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { MouseEvent as ReactMouseEvent } from 'react';
import '../../styles/track-layout-prototype.css';
import '../../styles/kr-managed-instructions.css';
import { curveCatalog, defaultDepthRange, depthUnitLabel, fullDepthRange, realCurveSamplesByCurveId, wellHeader } from './realLasTrackLayoutData';
import { lithologyIntervals21_31, lithologySource } from './lithologyTrackData';
import { WellLogPropertiesPanelSlot } from './WellLogPropertiesPanelSlot';
import { SourceIntakeWorkbench } from '../source-intake/SourceIntakeWorkbench';
import { KrManagedInstructionsWorkbench } from '../knowledge/KrManagedInstructionsWorkbench';
import { Wellbore3DPage } from '../wbv/Wellbore3DPage';
import { loadBackendViewerPackageWithFallback, type BackendViewerPackageLoadResult } from './backendViewerPackageAdapter';
import { buildWdvPackageState, emptyWdvPackageState, type WdvLoadedCurveItem, type WdvPackageState } from './wdvPackageState';
import { useTrackBodyGeometry } from './useTrackBodyGeometry';
import type {
  ActiveTrackType,
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
  DepthBasis,
  DepthTrack,
  DragCurvePayload,
  FillSide,
  LineStyle,
  LithologyTrack,
  ScaleMode,
  SelectionRef,
  WellLogTrack,
} from './trackLayoutModel';
import {
  curveById,
  makeCurveAssignment,
  orderedCurves,
  parseDragPayload,
  renumberCurveStack,
  resolveTrackLattice,
} from './trackLayoutModel';

type DepthViewRange = {
  min: number;
  max: number;
};


type DemoNavView = 'log-viewer' | 'data' | 'sources' | 'knowledge' | 'wellbore-3d' | 'info';

type ManagedInventorySourceReference = {
  source_id: string;
  source_kind?: string | null;
  display_name?: string | null;
  original_path?: string | null;
  file_name?: string | null;
  file_format?: string | null;
  checksum?: string | null;
  path?: string | null;
  uri?: string | null;
  status?: string | null;
};

type ManagedInventoryViewerPackageReference = {
  viewer_package_id: string;
  viewer_package_version?: string | null;
  package_kind?: string | null;
  display_name?: string | null;
  dataset_id?: string | null;
  representation_id?: string | null;
  endpoint?: string | null;
  status?: string | null;
};

type ManagedProductGroupItem = {
  product_id: string;
  display_name?: string | null;
  curve_name?: string | null;
  curve_type?: string | null;
  curve_family?: string | null;
  product_subgroup_key?: string | null;
  product_subgroup_label?: string | null;
  classification_confidence?: string | null;
  run_date?: string | null;
  run_interval?: string | null;
  run_number?: string | null;
  qa_flag?: string | null;
  selectable?: boolean;
  source_kind?: string | null;
  source_id?: string | null;
  viewer_package_id?: string | null;
  wmdp_state?: string | null;
  wdv_state?: string | null;
};

type ManagedProductGroup = {
  group_key: string;
  group_label: string;
  collapsed_by_default?: boolean;
  items?: ManagedProductGroupItem[];
};

type ManagedInventoryWellRecord = {
  managed_well_id: string;
  well_id: string;
  uwi?: string | null;
  well_name?: string | null;
  display_name?: string | null;
  wellbore_id?: string | null;
  wellbore_name?: string | null;
  operator?: string | null;
  field?: string | null;
  block?: string | null;
  country?: string | null;
  depth_unit?: string | null;
  top_depth?: number | null;
  base_depth?: number | null;
  status?: string | null;
  lifecycle_state?: string | null;
  source_references?: ManagedInventorySourceReference[];
  viewer_packages?: ManagedInventoryViewerPackageReference[];
  product_groups?: ManagedProductGroup[];
  wmdp_state?: string | null;
  wdv_state?: string | null;
  tags?: string[];
  created_at?: string | null;
  updated_at?: string | null;
};

type WdvSessionLayoutCurveState = {
  assignment_id?: string;
  assignmentId?: string;
  curve_id?: string;
  curveId?: string;
  product_id?: string | null;
  productId?: string | null;
  mnemonic?: string | null;
  display_name?: string | null;
  displayName?: string | null;
  curve_family?: string | null;
  curveFamily?: string | null;
  unit?: string | null;
  stack_index?: number;
  stackIndex?: number;
  visible?: boolean;
  scale_min?: number | null;
  scaleMin?: number | null;
  scale_max?: number | null;
  scaleMax?: number | null;
  scale_type?: string | null;
  scaleType?: string | null;
  scale_direction?: string | null;
  scaleDirection?: string | null;
  color?: string | null;
};

type WdvSessionLayoutTrackState = {
  track_id?: string;
  trackId?: string;
  track_number?: number | null;
  trackNumber?: number | null;
  track_name?: string;
  trackName?: string;
  track_type?: string;
  trackType?: string;
  width_px?: number | null;
  widthPx?: number | null;
  lattice?: string | null;
  lattice_source?: string | null;
  latticeSource?: string | null;
  curves?: WdvSessionLayoutCurveState[];
};

type WdvSessionLayoutResponse = {
  state_status?: 'empty' | 'active' | 'cleared';
  selected_track_id?: string | null;
  selectedTrackId?: string | null;
  tracks?: WdvSessionLayoutTrackState[];
  revision?: number;
};


type ManagedInventoryStatusPayload = {
  ok: boolean;
  service: string;
  scope?: string | null;
  storage_backend?: string | null;
  schema_version?: string | null;
  managed_well_count: number;
  viewer_package_count: number;
  source_reference_count?: number;
  lifecycle_counts?: Record<string, number>;
  repository_path?: string | null;
  storage_path?: string | null;
  last_checked_at?: string | null;
};

type WdvTemplateRecommendationLoadedCurvePayload = {
  product_id?: string | null;
  curve_id?: string | null;
  display_curve_id?: string | null;
  canonical_curve_id?: string | null;
  original_mnemonic?: string | null;
  mnemonic?: string | null;
  normalized_name?: string | null;
  display_name?: string | null;
  curve_family?: string | null;
  track_family?: string | null;
  unit?: string | null;
  is_renderable?: boolean | null;
  support_status?: string | null;
  source_id?: string | null;
};

type WdvTemplateRecommendationRequestPayload = {
  loaded_curve_items: WdvTemplateRecommendationLoadedCurvePayload[];
  workflow_context?: string | null;
  selected_product_ids?: string[];
  include_ineligible?: boolean;
};

type WdvRecommendedCurve = {
  product_id?: string | null;
  curve_id?: string | null;
  mnemonic?: string | null;
  display_name?: string | null;
  unit?: string | null;
  curve_family?: string | null;
  raw_curve_family?: string | null;
  canonical_curve_id?: string | null;
  depth_role?: string | null;
  selection_reason?: string | null;
};

type WdvTemplateRequirementCoverage = {
  available_families?: string[];
  missing_families?: string[];
  coverage_ratio?: number;
};

type WdvTemplateRecommendationTrack = {
  track_id?: string | null;
  track_key?: string | null;
  track_number?: number | null;
  track_name?: string | null;
  track_role?: string | null;
  renderer_type?: string | null;
  required_renderer_capability?: string | null;
  selected_curves?: WdvRecommendedCurve[];
  alternate_curves?: WdvRecommendedCurve[];
  missing_curve_families?: string[];
  scale_defaults?: Array<Record<string, unknown>>;
};

type WdvTemplateRecommendationItem = {
  template_key: string;
  template_label: string;
  workflow_context?: string | null;
  template_priority?: number | null;
  is_eligible: boolean;
  rank: number;
  score: number;
  required_coverage?: WdvTemplateRequirementCoverage;
  preferred_coverage?: WdvTemplateRequirementCoverage;
  optional_coverage?: WdvTemplateRequirementCoverage;
  missing_required_families?: string[];
  missing_preferred_families?: string[];
  selected_curve_count?: number;
  alternate_curve_count?: number;
  excluded_curve_count?: number;
  selected_curves?: WdvRecommendedCurve[];
  alternate_curves?: WdvRecommendedCurve[];
  excluded_curves?: WdvRecommendedCurve[];
  tracks?: WdvTemplateRecommendationTrack[];
  renderer_requirements?: string[];
  reason_codes?: string[];
};

type WdvTemplateRecommendationEnvelope = {
  service: string;
  contract_version: string;
  source: string;
  available_curve_count: number;
  classified_curve_count: number;
  unresolved_curve_count: number;
  unresolved_curves?: WdvRecommendedCurve[];
  recommendation_count: number;
  recommendations: WdvTemplateRecommendationItem[];
  knowledge_policy?: Record<string, unknown>;
};


type WdvTemplateApplicationPlanTrack = WdvTemplateRecommendationTrack & {
  planned_action?: string | null;
};

type WdvTemplateApplicationPlan = {
  application_plan_id: string;
  plan_status: string;
  template_key: string;
  template_label: string;
  workflow_context?: string | null;
  source_recommendation_rank?: number | null;
  source_recommendation_score?: number | null;
  apply_eligible: boolean;
  apply_mode?: string | null;
  blocking_issues?: string[];
  warnings?: string[];
  selected_curve_count?: number;
  alternate_curve_count?: number;
  excluded_curve_count?: number;
  selected_curves?: WdvRecommendedCurve[];
  alternate_curves?: WdvRecommendedCurve[];
  excluded_curves?: WdvRecommendedCurve[];
  tracks?: WdvTemplateApplicationPlanTrack[];
  renderer_requirements?: string[];
  missing_required_families?: string[];
  missing_preferred_families?: string[];
  reason_codes?: string[];
};

type WdvTemplateApplicationPlanEnvelope = {
  service: string;
  contract_version: string;
  mutation_performed: boolean;
  plan: WdvTemplateApplicationPlan;
  knowledge_policy?: Record<string, unknown>;
};

type IntervalSelectionState = {
  startDepth: number;
  currentDepth: number;
  startY: number;
  currentY: number;
  dragging: boolean;
};

type DragPanState = {
  startY: number;
  startRange: DepthViewRange;
};

type TrackResizeState = {
  trackId: string;
  startX: number;
  startWidth: number;
};

const FULL_DEPTH_RANGE: DepthViewRange = fullDepthRange;
const DEFAULT_DEPTH_RANGE: DepthViewRange = defaultDepthRange;
const CURVE_TRACK_MIN_WIDTH = 120;
const CURVE_TRACK_MAX_WIDTH = 420;
const CURVE_TRACK_WIDTH_STEP = 24;
const CURVE_TRACK_RESET_WIDTH = 220;
const GO_TO_REVIEW_WINDOW_M = 600;

function clampDepthRange(range: DepthViewRange, fullRange: DepthViewRange = FULL_DEPTH_RANGE): DepthViewRange {
  const span = Math.max(50, range.max - range.min);
  let min = range.min;
  let max = range.max;

  if (min < fullRange.min) {
    min = fullRange.min;
    max = Math.min(fullRange.max, min + span);
  }

  if (max > fullRange.max) {
    max = fullRange.max;
    min = Math.max(fullRange.min, max - span);
  }

  if (min >= max) {
    return { ...fullRange };
  }

  return {
    min: Math.round(min),
    max: Math.round(max),
  };
}

function makeDepthTicks(range: DepthViewRange, count = 11): number[] {
  const safeCount = Math.max(2, count);
  const step = (range.max - range.min) / (safeCount - 1);
  return Array.from({ length: safeCount }, (_, index) => Math.round(range.min + step * index));
}

function depthRangeLabel(range: DepthViewRange): string {
  return `${range.min}–${range.max} ${depthUnitLabel} MD`;
}


function wlvApiBaseUrl(): string {
  // WLV-MDP-API-PORT-8001-1:
  // The active WLV backend runs on 8001. Keep runtime override support,
  // use relative paths when served by the backend, and send Vite/dev
  // frontend calls to the backend inventory/source-intake API on 8001.
  const runtimeConfig = window as unknown as { __WLV_API_BASE_URL__?: string };
  if (runtimeConfig.__WLV_API_BASE_URL__) {
    return runtimeConfig.__WLV_API_BASE_URL__.replace(/\/$/, '');
  }

  const protocol = window.location.protocol || 'http:';
  const hostname = window.location.hostname || '127.0.0.1';
  const port = window.location.port;
  const backendPort = '8001';

  if (port === backendPort) {
    return '';
  }

  if (port === '5173' || port === '5174' || port === '5175') {
    return `${protocol}//${hostname}:${backendPort}`;
  }

  return `http://127.0.0.1:${backendPort}`;
}

async function fetchWlvJson<T>(path: string, init?: RequestInit): Promise<T> {
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


function firstBackendLoadedWell(records: ManagedInventoryWellRecord[]): string | null {
  const record = records.find((well) => well.wdv_state === 'loaded_to_wdv');
  if (record?.managed_well_id) return record.managed_well_id;

  for (const well of records) {
    for (const group of well.product_groups ?? []) {
      if ((group.items ?? []).some((item) => item.wdv_state === 'loaded_to_wdv')) {
        return well.managed_well_id;
      }
    }
  }

  return null;
}

function finiteNumberOr(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function sessionCurveAssignmentFromFrontend(assignment: CurveAssignment, catalog: CurveCatalogItem[]): WdvSessionLayoutCurveState {
  const curve = catalog.find((item) => item.curveId === assignment.curveId);
  return {
    assignment_id: assignment.assignmentId,
    curve_id: assignment.curveId,
    product_id: curve?.curveId ?? assignment.curveId,
    mnemonic: curve?.mnemonic ?? assignment.curveId,
    display_name: curve?.description ?? curve?.mnemonic ?? assignment.curveId,
    curve_family: curve?.curveClass ?? null,
    unit: curve?.unit ?? null,
    stack_index: assignment.stackIndex,
    visible: assignment.visible,
    scale_min: assignment.scaleMin,
    scale_max: assignment.scaleMax,
    scale_type: assignment.scaleType ?? (curve?.defaultLattice === 'logarithmic' ? 'log' : 'linear'),
    scale_direction: assignment.scaleDirection,
    color: assignment.color,
  };
}

function sessionTracksFromFrontend(tracks: WellLogTrack[], catalog: CurveCatalogItem[]): WdvSessionLayoutTrackState[] {
  return sortTracks(tracks).map((track) => {
    if (track.trackType === 'depth') {
      return {
        track_id: track.trackId,
        track_number: track.trackIndex,
        track_name: track.title,
        track_type: 'depth',
        width_px: track.widthPx,
        curves: [],
      };
    }

    if (track.trackType === 'curve') {
      return {
        track_id: track.trackId,
        track_number: track.trackIndex,
        track_name: displayTitleForTrack(track, catalog),
        track_type: 'curve',
        width_px: track.widthPx,
        lattice: track.lattice,
        lattice_source: track.latticeSource,
        curves: orderedCurves(track).map((assignment) => sessionCurveAssignmentFromFrontend(assignment, catalog)),
      };
    }

    return {
      track_id: track.trackId,
      track_number: track.trackIndex,
      track_name: track.title,
      track_type: track.trackType,
      width_px: track.widthPx,
      curves: [],
    };
  });
}

function frontendTracksFromSession(session: WdvSessionLayoutResponse, catalog: CurveCatalogItem[]): WellLogTrack[] {
  const restoredTracks: WellLogTrack[] = [];

  (session.tracks ?? []).forEach((rawTrack, index) => {
    const trackType = rawTrack.track_type ?? rawTrack.trackType ?? 'curve';
    const trackId = rawTrack.track_id ?? rawTrack.trackId ?? `wdv-session-track-${index + 1}`;
    const trackIndex = finiteNumberOr(rawTrack.track_number ?? rawTrack.trackNumber, index);
    const title = rawTrack.track_name ?? rawTrack.trackName ?? `Track ${index + 1}`;
    const widthPx = finiteNumberOr(rawTrack.width_px ?? rawTrack.widthPx, trackType === 'depth' ? 86 : CURVE_TRACK_RESET_WIDTH);

    if (trackType === 'depth') {
      restoredTracks.push({
        trackId,
        trackIndex,
        trackType: 'depth',
        title,
        depthBasis: title === 'TVD' || title === 'TVDSS' ? title : 'MD',
        unit: 'm',
        widthPx,
        visible: true,
      });
      return;
    }

    if (trackType !== 'curve') return;

    const assignments = (rawTrack.curves ?? [])
      .map((rawAssignment, assignmentIndex) => {
        const curveId = rawAssignment.curve_id ?? rawAssignment.curveId;
        const curve = curveId ? catalog.find((item) => item.curveId === curveId) : null;
        if (!curve) return null;
        const fallback = makeCurveAssignment(curve, assignmentIndex);
        const scaleDirection = rawAssignment.scale_direction ?? rawAssignment.scaleDirection;
        const scaleType = rawAssignment.scale_type ?? rawAssignment.scaleType;
        const restoredAssignment: CurveAssignment = {
          ...fallback,
          assignmentId: rawAssignment.assignment_id ?? rawAssignment.assignmentId ?? fallback.assignmentId,
          stackIndex: finiteNumberOr(rawAssignment.stack_index ?? rawAssignment.stackIndex, assignmentIndex),
          visible: rawAssignment.visible ?? fallback.visible,
          scaleMin: finiteNumberOr(rawAssignment.scale_min ?? rawAssignment.scaleMin, fallback.scaleMin),
          scaleMax: finiteNumberOr(rawAssignment.scale_max ?? rawAssignment.scaleMax, fallback.scaleMax),
          scaleType: scaleType === 'log' || scaleType === 'linear' ? scaleType : fallback.scaleType,
          scaleDirection: scaleDirection === 'reverse' || scaleDirection === 'reversed' ? 'reverse' : 'normal',
          color: rawAssignment.color ?? fallback.color,
        };
        return restoredAssignment;
      })
      .filter((assignment): assignment is CurveAssignment => Boolean(assignment));

    restoredTracks.push({
      trackId,
      trackIndex,
      trackType: 'curve',
      title: assignments.length
        ? assignments.map((assignment) => curveById(catalog, assignment.curveId).mnemonic).join(' / ')
        : title,
      widthPx: clampCurveTrackWidth(widthPx),
      visible: true,
      lattice: rawTrack.lattice === 'logarithmic' ? 'logarithmic' : 'linear',
      latticeSource: rawTrack.lattice_source === 'user_override' || rawTrack.latticeSource === 'user_override' ? 'user_override' : 'front_curve_default',
      latticeOverride: rawTrack.lattice_source === 'user_override' || rawTrack.latticeSource === 'user_override',
      scaleMode: 'per_curve',
      curves: renumberCurveStack(assignments),
    });
  });

  return reindexTracks(restoredTracks);
}

function selectedTrackIdFromSession(session: WdvSessionLayoutResponse): string | null {
  return session.selected_track_id ?? session.selectedTrackId ?? null;
}

function recommendationCurveFamily(item: WdvLoadedCurveItem): string | null {
  if (item.trackFamily) return item.trackFamily;
  switch (item.curveFamily) {
    case 'gamma': return 'gamma_ray';
    case 'borehole': return 'caliper';
    case 'neutron': return 'neutron_porosity';
    case 'sonic': return 'sonic_slowness';
    default: return item.curveFamily || null;
  }
}

function buildWdvTemplateRecommendationRequest(
  loadedCurveItems: WdvLoadedCurveItem[],
): WdvTemplateRecommendationRequestPayload {
  return {
    workflow_context: 'open_hole',
    include_ineligible: true,
    selected_product_ids: [],
    loaded_curve_items: loadedCurveItems.map((item) => ({
      product_id: item.productId,
      curve_id: item.curveId,
      display_curve_id: item.displayCurveId,
      canonical_curve_id: item.canonicalCurveId ?? null,
      original_mnemonic: item.originalMnemonic,
      mnemonic: item.originalMnemonic,
      normalized_name: item.displayName,
      display_name: item.displayName,
      curve_family: recommendationCurveFamily(item),
      track_family: item.trackFamily ?? null,
      unit: item.unit,
      is_renderable: true,
      support_status: item.supportStatus ?? null,
      source_id: item.sourceId ?? null,
    })),
  };
}

async function evaluateWdvTemplateRecommendations(
  loadedCurveItems: WdvLoadedCurveItem[],
): Promise<WdvTemplateRecommendationEnvelope> {
  return fetchWlvJson<WdvTemplateRecommendationEnvelope>(
    '/api/wlv/wdv/templates/recommendations/evaluate',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildWdvTemplateRecommendationRequest(loadedCurveItems)),
    },
  );
}


async function buildWdvTemplateApplicationPlan(
  templateKey: string,
  loadedCurveItems: WdvLoadedCurveItem[],
  managedWellId?: string | null,
): Promise<WdvTemplateApplicationPlanEnvelope> {
  const recommendationPayload = buildWdvTemplateRecommendationRequest(loadedCurveItems);
  return fetchWlvJson<WdvTemplateApplicationPlanEnvelope>(
    '/api/wlv/wdv/templates/application-plans/build',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        managed_well_id: managedWellId || 'wdv_current_viewer_session',
        template_key: templateKey,
        workflow_context: recommendationPayload.workflow_context,
        loaded_curve_items: recommendationPayload.loaded_curve_items,
      }),
    },
  );
}


function compactFamilyList(values?: string[], fallback = 'None'): string {
  if (!values || values.length === 0) return fallback;
  return values.slice(0, 6).join(', ') + (values.length > 6 ? ` +${values.length - 6}` : '');
}


function compactRendererList(values?: string[], fallback = 'None'): string {
  if (!values || values.length === 0) return fallback;
  return values.map((value) => value.replace(/_/g, ' ')).slice(0, 5).join(', ') + (values.length > 5 ? ` +${values.length - 5}` : '');
}

function formatPlanStatus(value?: string | null): string {
  return (value || 'pending').replace(/_/g, ' ');
}

function formatTemplateMatch(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'Pending';
  if (value >= 85) return 'Strong';
  if (value >= 70) return 'Good';
  if (value >= 50) return 'Partial';
  return 'Weak';
}

function curveVisibleIdentity(curve: WdvRecommendedCurve): string {
  const visibleName = curve.mnemonic || curve.display_name || curve.curve_id || curve.product_id || '';
  const visibleFamily = curve.curve_family || curve.raw_curve_family || '';
  return `${visibleName}`.trim().toLowerCase().replace(/[\s\-/]+/g, '_') + '::' + `${visibleFamily}`.trim().toLowerCase().replace(/[\s\-/]+/g, '_');
}

function uniqueVisibleRecommendedCurves(curves: WdvRecommendedCurve[]): WdvRecommendedCurve[] {
  const seen = new Set<string>();
  const unique: WdvRecommendedCurve[] = [];
  for (const curve of curves) {
    const identity = curveVisibleIdentity(curve);
    if (seen.has(identity)) continue;
    seen.add(identity);
    unique.push(curve);
  }
  return unique;
}

function scaleSummary(scaleDefaults?: Array<Record<string, unknown>>): string {
  if (!scaleDefaults || scaleDefaults.length === 0) return 'scale defaults pending';
  return scaleDefaults.slice(0, 3).map((scale) => {
    const family = typeof scale.curve_family === 'string' ? scale.curve_family.replace(/_/g, ' ') : 'curve';
    const scaleType = typeof scale.scale_type === 'string' ? scale.scale_type : 'scale';
    const min = scale.scale_min;
    const max = scale.scale_max;
    const range = (typeof min === 'number' || typeof max === 'number') ? ` ${String(min ?? '—')}–${String(max ?? '—')}` : '';
    return `${family}: ${scaleType}${range}`;
  }).join('; ');
}

function statusLabel(status?: string | null): string {
  return (status ?? 'unknown').replace(/_/g, ' ');
}


function safeText(value: string | number | null | undefined, fallback = '—'): string {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  return String(value);
}

function wellDisplayName(well: ManagedInventoryWellRecord): string {
  return well.display_name || well.well_name || well.well_id || well.managed_well_id;
}

function wellStatus(well: ManagedInventoryWellRecord): string {
  return well.lifecycle_state || well.status || 'unknown';
}

function developmentSeedAlreadyRegistered(wells: ManagedInventoryWellRecord[]): boolean {
  return wells.some((well) => well.managed_well_id === 'managed-well:forge-21-31' || well.well_id === 'forge-21-31');
}

function wellTypeLabel(well: ManagedInventoryWellRecord): string {
  const record = well as ManagedInventoryWellRecord & {
    well_type?: string | null;
    type?: string | null;
    well_category?: string | null;
  };
  return statusLabel(record.well_type || record.type || record.well_category || '—');
}

function wellProductCount(well: ManagedInventoryWellRecord): number {
  const productGroups = well.product_groups ?? [];
  if (productGroups.length > 0) {
    return productGroups.reduce((total, group) => total + (group.items ?? []).length, 0);
  }
  return (well.viewer_packages ?? []).length;
}

type WmdpSortKey = 'wellName' | 'wellId' | 'field' | 'operator' | 'status' | 'updated';
type WmdpBulkAction = 'load' | 'unload' | 'remove';

type WmdpProductCategoryKey = string;

type WmdpProductSubgroup = {
  subgroupKey: string;
  subgroupLabel: string;
  items: ManagedProductGroupItem[];
};

// KR-1: Backend-owned Knowledge Repository contracts.
// The frontend renders these; it must not own subgroup order or label truth.
type KrSubgroup = {
  key: string;
  label: string;
  order: number;
};

type KrProductGroup = {
  key: string;
  label: string;
  order: number;
  subgroups: KrSubgroup[];
};

type KrProductGroupsPayload = {
  version: string;
  groups: KrProductGroup[];
};

function normalizedProductSubgroupKey(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

/**
 * Group product items using backend-provided subgroup order and labels.
 * Items whose key is not in the KR list fall into the last subgroup
 * (conventionally the "other/review" bucket) if one exists.
 * The frontend does not infer or re-order subgroups — it renders the
 * backend-provided order and labels only.
 */
function groupProductItemsByKrSubgroups(
  items: ManagedProductGroupItem[],
  krSubgroups: KrSubgroup[],
): WmdpProductSubgroup[] {
  if (krSubgroups.length === 0) return [];

  const sortedSubgroups = [...krSubgroups].sort((a, b) => a.order - b.order);
  const subgroupByKey = new Map<string, WmdpProductSubgroup>(
    sortedSubgroups.map((s) => [s.key, { subgroupKey: s.key, subgroupLabel: s.label, items: [] }]),
  );

  // Last subgroup absorbs unrecognised keys (typically the "other/review" bucket).
  const fallbackKey = sortedSubgroups[sortedSubgroups.length - 1].key;

  for (const item of items) {
    const rawKey = item.product_subgroup_key || item.curve_family || '';
    const normKey = normalizedProductSubgroupKey(rawKey);
    const targetKey = subgroupByKey.has(normKey) ? normKey : fallbackKey;
    subgroupByKey.get(targetKey)?.items.push(item);
  }

  return sortedSubgroups
    .map((s) => subgroupByKey.get(s.key)!)
    .filter((s) => s.items.length > 0);
}

function productItemClassificationTitle(item: ManagedProductGroupItem): string | undefined {
  const parts = [
    item.product_subgroup_label ? `Subclass: ${item.product_subgroup_label}` : '',
    item.curve_family ? `Family: ${item.curve_family}` : '',
    item.classification_confidence ? `Confidence: ${item.classification_confidence}` : '',
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(' | ') : undefined;
}

function productItemDisplayName(item: ManagedProductGroupItem): string {
  return item.curve_name || item.display_name || item.product_id;
}

function productItemRunDateDisplay(value: unknown): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (typeof value !== 'string' && typeof value !== 'number') {
    return '—';
  }

  const text = String(value).trim();
  if (!text) {
    return '—';
  }

  const normalized = text.replace(/[\s_-]+/g, ' ').trim().toUpperCase();
  const placeholders = new Set([
    'LOG DATE',
    'LOGDATE',
    'RUN DATE',
    'DATE',
    'N A',
    'NA',
    'N/A',
    'NONE',
    'NULL',
    'UNKNOWN',
    'UNAVAILABLE',
    '-',
    '—',
  ]);

  if (placeholders.has(normalized) || placeholders.has(text.toUpperCase())) {
    return '—';
  }

  return text;
}


function expandableProductName(value: string) {
  const text = safeText(value);
  const maxLength = 64;

  if (text.length <= maxLength) {
    return <>{text}</>;
  }

  return (
    <details className="wlv-wmdp-product-name-details">
      <summary title={text}>{text.slice(0, maxLength - 1)}…</summary>
      <span>{text}</span>
    </details>
  );
}


function WmdpProductItemRow({ item, selected, onToggle }: { item: ManagedProductGroupItem; selected: boolean; onToggle: () => void }) {
  return (
    <label className="wlv-wmdp-product-item" key={item.product_id}>
      <input
        type="checkbox"
        checked={selected}
        disabled={item.selectable === false}
        onChange={onToggle}
        aria-label={`Select ${productItemDisplayName(item)}`}
      />
      <span className="wlv-wmdp-product-item-summary">
        <span className="wlv-wmdp-product-item-code-wrap" title={productItemClassificationTitle(item)}>
          <strong className="wlv-wmdp-product-item-code">{productItemDisplayName(item)}</strong>
        </span>
        <span className="wlv-wmdp-product-item-description" title={safeText(item.curve_type)}>
          <strong>Description:</strong> {safeText(item.curve_type)}
        </span>
        <span className="wlv-wmdp-product-item-name" title={safeText(item.display_name || productItemDisplayName(item))}>
          <strong>File Name:</strong> {expandableProductName(item.display_name || productItemDisplayName(item))}
        </span>
        <span className="wlv-wmdp-product-item-run-date" title={productItemRunDateDisplay(item.run_date)}>
          <strong>Run Date:</strong> {productItemRunDateDisplay(item.run_date)}
        </span>
        <span className="wlv-wmdp-product-item-run-interval" title={safeText(item.run_interval)}>
          <strong>Run Interval:</strong> {safeText(item.run_interval)}
        </span>
        <span className="wlv-wmdp-product-item-run-number" title={safeText(item.run_number)}>
          <strong>Run Number:</strong> {safeText(item.run_number)}
        </span>
        <span className="wlv-wmdp-product-item-qa-flag" title={safeText(item.qa_flag)}>
          <strong>QA Flag:</strong> {safeText(item.qa_flag)}
        </span>
      </span>
    </label>
  );
}

function ManagedWellInventoryPage({ onOpenLogViewer, onClearLogViewer, activeManagedWellId }: { onOpenLogViewer: (managedWellId?: string | null) => void; onClearLogViewer: () => void; activeManagedWellId: string | null }) {
  const [status, setStatus] = useState<ManagedInventoryStatusPayload | null>(null);
  const [wells, setWells] = useState<ManagedInventoryWellRecord[]>([]);
  const [selectedWellId, setSelectedWellId] = useState<string | null>(null);
  const [selectedWellIds, setSelectedWellIds] = useState<Set<string>>(new Set());
  const [expandedWellIds, setExpandedWellIds] = useState<Set<string>>(new Set());
  const [expandedProductGroupIds, setExpandedProductGroupIds] = useState<Set<string>>(new Set());
  const [selectedProductItemIds, setSelectedProductItemIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [sortKey, setSortKey] = useState<WmdpSortKey>('wellName');
  const [pageSize, setPageSize] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);
  const [bulkAction, setBulkAction] = useState<WmdpBulkAction>('load');
  const [bulkApplying, setBulkApplying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // KR-1: backend-owned product groups fetched once on mount.
  // If unavailable the page degrades safely (subgroups not shown).
  const [krProductGroups, setKrProductGroups] = useState<KrProductGroup[]>([]);

  const seedAlreadyRegistered = developmentSeedAlreadyRegistered(wells);
  const backendConnected = Boolean(status?.ok && !error);

  const filteredWells = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const matchesSearch = (well: ManagedInventoryWellRecord) => {
      if (!query) return true;
      return [
        wellDisplayName(well),
        well.managed_well_id,
        well.well_id,
        well.field,
        well.operator,
        well.country,
        wellStatus(well),
      ].some((value) => safeText(value, '').toLowerCase().includes(query));
    };

    const sortValue = (well: ManagedInventoryWellRecord): string => {
      if (sortKey === 'wellId') return safeText(well.well_id, '').toLowerCase();
      if (sortKey === 'field') return safeText(well.field, '').toLowerCase();
      if (sortKey === 'operator') return safeText(well.operator, '').toLowerCase();
      if (sortKey === 'status') return statusLabel(wellStatus(well)).toLowerCase();
      if (sortKey === 'updated') return safeText(well.updated_at ?? well.created_at, '').toLowerCase();
      return wellDisplayName(well).toLowerCase();
    };

    return wells.filter(matchesSearch).sort((a, b) => sortValue(a).localeCompare(sortValue(b)));
  }, [searchQuery, sortKey, wells]);

  const totalPages = Math.max(1, Math.ceil(filteredWells.length / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const pageStartIndex = filteredWells.length === 0 ? 0 : (safeCurrentPage - 1) * pageSize;
  const pageEndIndex = Math.min(pageStartIndex + pageSize, filteredWells.length);
  const pagedWells = filteredWells.slice(pageStartIndex, pageEndIndex);
  const allVisibleSelected = pagedWells.length > 0 && pagedWells.every((well) => selectedWellIds.has(well.managed_well_id));

  const loadInventory = async () => {
    setLoading(true);
    setError(null);

    // KR-1: Fetch backend-owned product groups in parallel with inventory.
    // A KR failure is non-fatal — the page degrades gracefully (no subgrouping).
    fetchWlvJson<KrProductGroupsPayload>('/api/wlv/knowledge/product-groups')
      .then((payload) => setKrProductGroups(payload.groups ?? []))
      .catch(() => { /* KR unavailable — subgroup rendering degrades safely */ });

    try {
      const [nextStatus, nextWells] = await Promise.all([
        fetchWlvJson<ManagedInventoryStatusPayload>('/api/wlv/inventory/status'),
        fetchWlvJson<ManagedInventoryWellRecord[]>('/api/wlv/inventory/wells'),
      ]);
      setStatus(nextStatus);
      setWells(nextWells);
      setSelectedWellId((current) => (
        current && nextWells.some((well) => well.managed_well_id === current)
          ? current
          : nextWells[0]?.managed_well_id ?? null
      ));
      setSelectedWellIds((current) => {
        const validIds = new Set(nextWells.map((well) => well.managed_well_id));
        return new Set([...current].filter((id) => validIds.has(id)));
      });
      setExpandedWellIds((current) => {
        const validIds = new Set(nextWells.map((well) => well.managed_well_id));
        return new Set([...current].filter((id) => validIds.has(id)));
      });
      setExpandedProductGroupIds((current) => {
        const validPrefixes = nextWells.map((well) => `${well.managed_well_id}:`);
        return new Set([...current].filter((id) => validPrefixes.some((prefix) => id.startsWith(prefix))));
      });
      setSelectedProductItemIds(new Set());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load managed well inventory');
      setStatus(null);
      setWells([]);
      setSelectedWellId(null);
      setSelectedWellIds(new Set());
      setExpandedWellIds(new Set());
      setExpandedProductGroupIds(new Set());
      setSelectedProductItemIds(new Set());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadInventory();
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [pageSize, searchQuery, sortKey, wells.length]);

  const registerSeedWell = async () => {
    if (seedAlreadyRegistered) {
      setError('Development seed well is already registered. Use Refresh to reload the managed inventory.');
      return;
    }

    setRegistering(true);
    setError(null);
    try {
      const result = await fetchWlvJson<{ record: ManagedInventoryWellRecord }>('/api/wlv/inventory/wells/register-seed', {
        method: 'POST',
      });
      await loadInventory();
      setSelectedWellId(result.record.managed_well_id);
      setExpandedWellIds((current) => new Set(current).add(result.record.managed_well_id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to register development seed well');
    } finally {
      setRegistering(false);
    }
  };

  const toggleWellSelected = (managedWellId: string) => {
    setSelectedWellIds((current) => {
      const next = new Set(current);
      if (next.has(managedWellId)) {
        next.delete(managedWellId);
      } else {
        next.add(managedWellId);
      }
      return next;
    });
    setSelectedWellId(managedWellId);
  };

  const toggleVisibleSelection = () => {
    setSelectedWellIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) {
        pagedWells.forEach((well) => next.delete(well.managed_well_id));
      } else {
        pagedWells.forEach((well) => next.add(well.managed_well_id));
      }
      return next;
    });
  };

  const toggleWellExpanded = (managedWellId: string) => {
    setExpandedWellIds((current) => {
      const next = new Set(current);
      if (next.has(managedWellId)) {
        next.delete(managedWellId);
      } else {
        next.add(managedWellId);
      }
      return next;
    });
    setSelectedWellId(managedWellId);
  };

  const productGroupId = (managedWellId: string, categoryKey: WmdpProductCategoryKey): string => `${managedWellId}:${categoryKey}`;

  const toggleProductGroupExpanded = (managedWellId: string, categoryKey: WmdpProductCategoryKey) => {
    const groupId = productGroupId(managedWellId, categoryKey);
    setExpandedProductGroupIds((current) => {
      const next = new Set(current);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
    setSelectedWellId(managedWellId);
  };

  const toggleProductItemSelected = (itemId: string) => {
    setSelectedProductItemIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };


  const toggleProductGroupItemsSelected = (items: ManagedProductGroupItem[]) => {
    setSelectedProductItemIds((current) => {
      const selectableIds = items
        .filter((item) => item.selectable !== false)
        .map((item) => item.product_id);

      const allSelected = selectableIds.length > 0 && selectableIds.every((id) => current.has(id));
      const next = new Set(current);

      selectableIds.forEach((id) => {
        if (allSelected) {
          next.delete(id);
        } else {
          next.add(id);
        }
      });

      return next;
    });
  };

  const selectedProductWellIds = useMemo(() => {
    const owners = new Set<string>();
    if (selectedProductItemIds.size === 0) return owners;

    wells.forEach((well) => {
      const ownsSelectedProduct = (well.product_groups ?? []).some((group) => (group.items ?? []).some((item) => selectedProductItemIds.has(item.product_id)));
      if (ownsSelectedProduct) owners.add(well.managed_well_id);
    });

    return owners;
  }, [selectedProductItemIds, wells]);

  const selectedWellCount = selectedWellIds.size;
  const selectedProductCount = selectedProductItemIds.size;
  const hasSelection = selectedWellCount > 0 || selectedProductCount > 0;
  const canApplyBulkAction = hasSelection && !bulkApplying;

  const applyBulkAction = async () => {
    if (!canApplyBulkAction) return;

    const productIds = [...selectedProductItemIds];
    const productOwnerIds = [...selectedProductWellIds];

    if (bulkAction === 'remove') {
      const managedWellIds = [...selectedWellIds];

      setBulkApplying(true);
      setError(null);
      try {
        await fetchWlvJson('/api/wlv/inventory/remove-from-mdp', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            managed_well_ids: managedWellIds,
            product_ids: productIds,
          }),
        });
        const removedActiveWell = activeManagedWellId !== null
          && (managedWellIds.includes(activeManagedWellId) || productOwnerIds.includes(activeManagedWellId));
        setSelectedWellIds(new Set());
        setSelectedProductItemIds(new Set());
        await loadInventory();
        if (removedActiveWell) {
          onClearLogViewer();
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Unable to remove selected managed data from MDP');
      } finally {
        setBulkApplying(false);
      }
      return;
    }

    if (bulkAction !== 'load' && bulkAction !== 'unload') return;

    const managedWellId = productIds.length > 0
      ? productOwnerIds[0] ?? null
      : [...selectedWellIds][0] ?? selectedWellId;

    if (!managedWellId) {
      setError(`Select one managed well or product row to ${bulkAction === 'load' ? 'load to' : 'unload from'} the Well Data Viewer.`);
      return;
    }

    if (productOwnerIds.length > 1) {
      setError(`${bulkAction === 'load' ? 'Load to' : 'Unload from'} WDV supports one managed well at a time. Clear selections from other wells first.`);
      return;
    }

    const endpoint = bulkAction === 'load'
      ? '/api/wlv/inventory/load-to-wdv'
      : '/api/wlv/inventory/unload-from-wdv';

    setBulkApplying(true);
    setError(null);
    try {
      await fetchWlvJson(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          managed_well_id: managedWellId,
          product_ids: productIds,
        }),
      });
      await loadInventory();
      if (bulkAction === 'load') {
        onOpenLogViewer(managedWellId);
      } else if (managedWellId === activeManagedWellId) {
        onClearLogViewer();
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `Unable to ${bulkAction === 'load' ? 'load selected managed data to' : 'unload selected managed data from'} the Well Data Viewer`);
    } finally {
      setBulkApplying(false);
    }
  };

  return (
    <section className="wlv-managed-inventory-page wlv-wmdp-page" aria-label="Managed Well Data">
      <header className="wlv-managed-inventory-header wlv-wmdp-page-header">
        <div>
          <span className="wlv-page-kicker">Data</span>
          <h1>Managed Data</h1>
          <p>Manage registered wells and data made available to the Well Data Viewer.</p>
        </div>
        <div className="wlv-wmdp-page-actions">
          <button
            type="button"
            className="wlv-wmdp-disposable-seed-button"
            onClick={registerSeedWell}
            disabled={loading || registering || seedAlreadyRegistered}
            title="Temporary development bootstrap action. Remove when intake workflow is complete."
          >
            {seedAlreadyRegistered ? '[disposable] Seed Registered' : registering ? '[disposable] Seeding…' : '[disposable] Seed Example Well'}
          </button>
        </div>
      </header>

      {error ? <div className="wlv-managed-inventory-error" role="alert">{error}</div> : null}

      <section className="wlv-wmdp-panel" aria-label="Managed well data table">
        <header className="wlv-wmdp-panel-header">
          <div>
            <h2>Managed Well Data</h2>
            <p>{backendConnected ? 'Connected' : 'Backend unavailable'} · {safeText(status?.service, 'inventory')} · {wells.length} managed wells</p>
          </div>
          <div className="wlv-wmdp-panel-actions">
            <label className="wlv-wmdp-sort-control">
              <span>Sort by</span>
              <select value={sortKey} onChange={(event) => setSortKey(event.target.value as WmdpSortKey)}>
                <option value="wellName">Well name</option>
                <option value="wellId">Well ID</option>
                <option value="field">Field</option>
                <option value="operator">Operator</option>
                <option value="status">Status</option>
                <option value="updated">Updated</option>
              </select>
            </label>
            <button type="button" onClick={loadInventory} disabled={loading}>Refresh</button>
            <button type="button" onClick={() => setExpandedWellIds(new Set())} disabled={expandedWellIds.size === 0}>Collapse</button>
          </div>
        </header>

        <div className="wlv-wmdp-control-band" aria-label="Managed data controls">
          <div className="wlv-wmdp-control-row wlv-wmdp-control-row-paging">
            <input
              type="search"
              placeholder="Search Managed Wells..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              aria-label="Search Managed Wells"
            />
            <label className="wlv-wmdp-page-size-control">
              <span>Page size</span>
              <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
            <button type="button" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={safeCurrentPage <= 1}>Previous</button>
            <button type="button" onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))} disabled={safeCurrentPage >= totalPages}>Next</button>
            <span className="wlv-wmdp-page-readout">Showing {filteredWells.length === 0 ? '0' : `${pageStartIndex + 1}–${pageEndIndex}`} of {filteredWells.length}</span>
          </div>

          <div className="wlv-wmdp-control-row wlv-wmdp-control-row-bulk">
            <span className="wlv-wmdp-selected-readout">Selected wells {selectedWellCount} · products {selectedProductCount}</span>
            <label className="wlv-wmdp-action-control">
              <span>Action</span>
              <select value={bulkAction} onChange={(event) => setBulkAction(event.target.value as WmdpBulkAction)}>
                <option value="load">Load selected to Data Viewer</option>
                <option value="unload">Unload selected from Data Viewer</option>
                <option value="remove">Remove selected from MDP</option>
              </select>
            </label>
            <button type="button" onClick={applyBulkAction} disabled={!canApplyBulkAction}>{bulkApplying ? (bulkAction === 'remove' ? 'Removing…' : bulkAction === 'unload' ? 'Unloading…' : 'Loading…') : 'Apply'}</button>
          </div>
        </div>

        <div className="wlv-wmdp-table-wrap">
          <table className="wlv-wmdp-table">
            <thead>
              <tr>
                <th className="wlv-wmdp-col-select">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    disabled={pagedWells.length === 0}
                    onChange={toggleVisibleSelection}
                    aria-label="Select visible managed wells"
                  />
                </th>
                <th className="wlv-wmdp-col-expand" aria-label="Expand" />
                <th>Well Name</th>
                <th>UWI</th>
                <th>Well Type</th>
                <th>Field</th>
                <th>Block</th>
                <th>Operator</th>
                <th>Products</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={10} className="wlv-wmdp-empty-cell">Loading managed inventory from backend...</td></tr>
              ) : pagedWells.length === 0 ? (
                <tr>
                  <td colSpan={10} className="wlv-wmdp-empty-cell">
                    {wells.length === 0 ? 'No managed wells registered.' : 'No managed wells match the current search.'}
                  </td>
                </tr>
              ) : pagedWells.map((well) => {
                const expanded = expandedWellIds.has(well.managed_well_id);
                const rowSelected = selectedWellIds.has(well.managed_well_id);
                const productCategories = well.product_groups ?? [];
                return (
                  <>
                    <tr className={rowSelected || selectedWellId === well.managed_well_id ? 'is-selected' : ''} key={well.managed_well_id}>
                      <td className="wlv-wmdp-col-select">
                        <input
                          type="checkbox"
                          checked={rowSelected}
                          onChange={() => toggleWellSelected(well.managed_well_id)}
                          aria-label={`Select ${wellDisplayName(well)}`}
                        />
                      </td>
                      <td className="wlv-wmdp-col-expand">
                        <button
                          type="button"
                          className="wlv-wmdp-expand-btn"
                          onClick={() => toggleWellExpanded(well.managed_well_id)}
                          aria-label={`${expanded ? 'Collapse' : 'Expand'} ${wellDisplayName(well)}`}
                          aria-expanded={expanded}
                        >
                          {expanded ? '▾' : '▸'}
                        </button>
                      </td>
                      <td className="wlv-wmdp-name-cell">
                        <button type="button" onClick={() => setSelectedWellId(well.managed_well_id)}>
                          <strong>{wellDisplayName(well)}</strong>
                          <span>{well.managed_well_id}</span>
                        </button>
                      </td>
                      <td>{safeText(well.uwi)}</td>
                      <td>{wellTypeLabel(well)}</td>
                      <td>{safeText(well.field)}</td>
                      <td>{safeText(well.block)}</td>
                      <td>{safeText(well.operator)}</td>
                      <td>{wellProductCount(well)}</td>
                      <td>
                        <div className="wlv-wmdp-row-actions">
                          <button type="button" onClick={() => { setSelectedWellIds(new Set([well.managed_well_id])); void fetchWlvJson('/api/wlv/inventory/load-to-wdv', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ managed_well_id: well.managed_well_id, product_ids: [] }) }).then(() => loadInventory()).then(() => onOpenLogViewer(well.managed_well_id)).catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load managed well to WDV')); }}>Load</button>
                          <button type="button" onClick={() => setSelectedWellId(well.managed_well_id)}>Info</button>
                          <button type="button" onClick={() => { setSelectedWellIds(new Set([well.managed_well_id])); setSelectedProductItemIds(new Set()); setBulkAction('remove'); }}>Remove</button>
                        </div>
                      </td>
                    </tr>
                    {expanded ? (
                      <tr className="wlv-wmdp-expanded-row" key={`${well.managed_well_id}-expanded`}>
                        <td colSpan={10}>
                          <div className="wlv-wmdp-expanded-content wlv-wmdp-product-groups">
                            {productCategories.map((category) => {
                              const groupId = productGroupId(well.managed_well_id, category.group_key);
                              const categoryExpanded = expandedProductGroupIds.has(groupId);
                              const categoryItems = category.items ?? [];
                              const selectableCategoryItems = categoryItems.filter((item) => item.selectable !== false);
                              const categoryItemsAllSelected = selectableCategoryItems.length > 0
                                && selectableCategoryItems.every((item) => selectedProductItemIds.has(item.product_id));
                              return (
                                <section className="wlv-wmdp-product-group" key={category.group_key}>
                                  <div className="wlv-wmdp-product-group-header">
                                    <input
                                      type="checkbox"
                                      className="wlv-wmdp-product-group-select"
                                      checked={categoryItemsAllSelected}
                                      disabled={selectableCategoryItems.length === 0}
                                      onChange={() => toggleProductGroupItemsSelected(categoryItems)}
                                      aria-label={`Select all ${category.group_label}`}
                                    />
                                    <button
                                      type="button"
                                      className="wlv-wmdp-product-group-toggle"
                                      onClick={() => toggleProductGroupExpanded(well.managed_well_id, category.group_key)}
                                      aria-expanded={categoryExpanded}
                                    >
                                      <span className="wlv-wmdp-product-group-caret">{categoryExpanded ? '▾' : '▸'}</span>
                                      <span className="wlv-wmdp-product-group-title">{category.group_label}</span>
                                      <span className="wlv-wmdp-product-group-count">{categoryItems.length}</span>
                                    </button>
                                  </div>
                                  {categoryExpanded ? (() => {
                                    // KR-1: use backend-provided subgroups for any group that has them.
                                    const krGroup = krProductGroups.find((g) => g.key === category.group_key);
                                    const krSubgroups = krGroup?.subgroups ?? [];
                                    const subgroupedItems = krSubgroups.length > 0
                                      ? groupProductItemsByKrSubgroups(categoryItems, krSubgroups)
                                      : [];
                                    return subgroupedItems.length > 0 ? (
                                      <div className="wlv-wmdp-product-subgroups">
                                        {categoryItems.length === 0 ? (
                                          <div className="wlv-wmdp-product-empty">No registered items.</div>
                                        ) : subgroupedItems.map((subgroup) => (
                                          <section className="wlv-wmdp-product-subgroup" key={subgroup.subgroupKey}>
                                            <div className="wlv-wmdp-product-subgroup-header">
                                              <span className="wlv-wmdp-product-subgroup-caret">▾</span>
                                              <span className="wlv-wmdp-product-subgroup-title">{subgroup.subgroupLabel}</span>
                                              <span className="wlv-wmdp-product-subgroup-count">{subgroup.items.length}</span>
                                            </div>
                                            <div className="wlv-wmdp-product-items">
                                              {subgroup.items.map((item) => (
                                                <WmdpProductItemRow
                                                  item={item}
                                                  key={item.product_id}
                                                  selected={selectedProductItemIds.has(item.product_id)}
                                                  onToggle={() => toggleProductItemSelected(item.product_id)}
                                                />
                                              ))}
                                            </div>
                                          </section>
                                        ))}
                                      </div>
                                    ) : (
                                      <div className="wlv-wmdp-product-items">
                                        {categoryItems.length === 0 ? (
                                          <div className="wlv-wmdp-product-empty">No registered items.</div>
                                        ) : categoryItems.map((item) => (
                                          <WmdpProductItemRow
                                            item={item}
                                            key={item.product_id}
                                            selected={selectedProductItemIds.has(item.product_id)}
                                            onToggle={() => toggleProductItemSelected(item.product_id)}
                                          />
                                        ))}
                                      </div>
                                    );
                                  })() : null}
                                </section>
                              );
                            })}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

type DemoNavIconKey = 'log-viewer' | 'data' | 'sources' | 'knowledge' | 'wellbore-3d' | 'info' | 'toolbox' | 'settings';

type DemoNavItem = {
  label: string;
  icon: DemoNavIconKey;
  view?: DemoNavView;
};

function DemoRailIcon({ icon }: { icon: DemoNavIconKey }) {
  const commonProps = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    focusable: false,
  };

  if (icon === 'log-viewer') {
    return (
      <svg {...commonProps} aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <circle cx="8.5" cy="9" r="1.5" />
        <path d="M21 15l-5-5L5 21" />
      </svg>
    );
  }

  if (icon === 'data') {
    return (
      <svg {...commonProps} aria-hidden="true">
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5" />
        <path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3" />
      </svg>
    );
  }

  if (icon === 'sources') {
    return (
      <svg {...commonProps} aria-hidden="true">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    );
  }

  if (icon === 'knowledge') {
    return (
      <svg {...commonProps} aria-hidden="true">
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16z" />
        <path d="M8 7h8" />
        <path d="M8 11h8" />
        <path d="M8 15h5" />
        <path d="M4 5.5A2.5 2.5 0 0 0 6.5 8H20" />
      </svg>
    );
  }

  if (icon === 'wellbore-3d') {
    return (
      <svg {...commonProps} aria-hidden="true">
        <path d="M12 3 20 7.5v9L12 21 4 16.5v-9L12 3z" />
        <path d="M12 12 20 7.5" />
        <path d="M12 12 4 7.5" />
        <path d="M12 12v9" />
        <path d="M8.4 16.1c1.2-1.3 1.7-2.8 1.6-4.6-.1-1.7.7-2.9 2.1-3.6 1.5-.7 2.9-.3 3.7.8" />
        <circle cx="8.4" cy="16.1" r="0.85" />
        <circle cx="15.8" cy="8.7" r="0.85" />
      </svg>
    );
  }

  if (icon === 'info') {
    return (
      <svg {...commonProps} aria-hidden="true">
        <rect x="4" y="4" width="6" height="6" rx="1.2" />
        <rect x="14" y="4" width="6" height="6" rx="1.2" />
        <rect x="4" y="14" width="6" height="6" rx="1.2" />
        <rect x="14" y="14" width="6" height="6" rx="1.2" />
      </svg>
    );
  }

  if (icon === 'toolbox') {
    return (
      <svg {...commonProps} aria-hidden="true">
        <path d="M14.7 6.3a4 4 0 0 0-5.66 5.66L3.4 17.6a2 2 0 1 0 2.83 2.83l5.64-5.64a4 4 0 0 0 5.66-5.66l-2.83 2.83-2.83-2.83 2.83-2.83z" />
      </svg>
    );
  }

  return (
    <svg {...commonProps} aria-hidden="true">
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function DemoShellNavItem({
  item,
  activeView,
  onNavigate,
}: {
  item: DemoNavItem;
  activeView: DemoNavView;
  onNavigate: (view: DemoNavView) => void;
}) {
  const active = item.view === activeView;
  const navigable = Boolean(item.view);

  return (
    <button
      type="button"
      className={`wlv-demo-nav-item ${active ? 'active' : ''}`}
      aria-current={active ? 'page' : undefined}
      onClick={() => {
        if (item.view) onNavigate(item.view);
      }}
      disabled={!navigable}
      title={item.view === 'data' ? 'Open Managed Well Inventory' : item.view === 'sources' ? 'Open Source Intake' : item.view === 'knowledge' ? 'Open Knowledge Repository' : item.view === 'info' ? 'Open Info' : item.label}
    >
      <span className="wlv-demo-nav-icon" aria-hidden="true"><DemoRailIcon icon={item.icon} /></span>
      <span className="wlv-demo-nav-label">{item.label}</span>
    </button>
  );
}

function DemoShellRail({
  activeView,
  onNavigate,
}: {
  activeView: DemoNavView;
  onNavigate: (view: DemoNavView) => void;
}) {
  const topItems: DemoNavItem[] = [
    { label: 'Log Viewer', icon: 'log-viewer', view: 'log-viewer' },
    { label: '3D Wellbore', icon: 'wellbore-3d', view: 'wellbore-3d' },
    { label: 'Info', icon: 'info', view: 'info' },
    { label: 'Data', icon: 'data', view: 'data' },
    { label: 'Sources', icon: 'sources', view: 'sources' },
  ];

  const bottomItems: DemoNavItem[] = [
    { label: 'Knowledge', icon: 'knowledge', view: 'knowledge' },
    { label: 'Toolbox', icon: 'toolbox' },
    { label: 'Settings', icon: 'settings' },
  ];

  return (
    <aside className="wlv-demo-left-rail" aria-label="Well Log Viewer navigation">
      <div className="wlv-demo-rail-brand">
        <span>Well Log</span>
        <strong>Viewer</strong>
      </div>

      <div className="wlv-demo-nav-top">
        {topItems.map((item) => (
          <DemoShellNavItem key={item.label} item={item} activeView={activeView} onNavigate={onNavigate} />
        ))}
      </div>

      <div className="wlv-demo-nav-bottom">
        {bottomItems.map((item) => (
          <DemoShellNavItem key={item.label} item={item} activeView={activeView} onNavigate={onNavigate} />
        ))}
      </div>
    </aside>
  );
}

function rangesEqual(a: DepthViewRange, b: DepthViewRange): boolean {
  return a.min === b.min && a.max === b.max;
}

function sortTracks(tracks: WellLogTrack[]): WellLogTrack[] {
  return [...tracks].sort((a, b) => a.trackIndex - b.trackIndex);
}

function reindexTracks(tracks: WellLogTrack[]): WellLogTrack[] {
  return sortTracks(tracks).map((track, index) => ({ ...track, trackIndex: index }));
}

function reindexTracksInCurrentOrder(tracks: WellLogTrack[]): WellLogTrack[] {
  return tracks.map((track, index) => ({ ...track, trackIndex: index }));
}

function moveTrackById(tracks: WellLogTrack[], trackId: string, direction: -1 | 1): WellLogTrack[] {
  const ordered = sortTracks(tracks);
  const fromIndex = ordered.findIndex((track) => track.trackId === trackId);

  if (fromIndex < 0) return tracks;

  const toIndex = fromIndex + direction;
  if (toIndex < 0 || toIndex >= ordered.length) return tracks;

  const next = [...ordered];
  const [movingTrack] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, movingTrack);

  return reindexTracksInCurrentOrder(next);
}

function nextTrackId(trackType: ActiveTrackType): string {
  return `track-${trackType}-${Date.now()}-${Math.round(Math.random() * 100000)}`;
}

const TRACK_STRIP_PADDING_PX = 10;
const TRACK_HEADER_HEIGHT_PX = 108;
const TRACK_BODY_HEIGHT_PX = 900;
const TRACK_BODY_MIN_HEIGHT_PX = 650;
const TRACK_BODY_MAX_HEIGHT_PX = 900;
const TRACK_FOOTER_CLEARANCE_PX = 48;
const TRACK_HEADER_TITLE_HEIGHT_PX = 24;
const TRACK_HEADER_SUBTITLE_HEIGHT_PX = 28;
const TRACK_CURVE_HEADER_ROW_HEIGHT_PX = 24;
const TRACK_HEADER_BOTTOM_PADDING_PX = 8;
const CURVE_VIEW_PADDING_X = 10;

type MockCurveSample = {
  depth: number;
  value: number;
};

function depthToY(depth: number, viewRange: DepthViewRange, bodyHeightPx = TRACK_BODY_HEIGHT_PX): number {
  const span = Math.max(1, viewRange.max - viewRange.min);
  const t = (depth - viewRange.min) / span;
  return clampValue(t, 0, 1) * bodyHeightPx;
}

function yToDepth(y: number, viewRange: DepthViewRange, bodyHeight = TRACK_BODY_HEIGHT_PX): number {
  const ratio = bodyHeight <= 0 ? 0 : clampValue(y / bodyHeight, 0, 1);
  return viewRange.min + (viewRange.max - viewRange.min) * ratio;
}

function clampValue(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function clampCurveTrackWidth(width: number): number {
  return Math.round(clampValue(width, CURVE_TRACK_MIN_WIDTH, CURVE_TRACK_MAX_WIDTH));
}

function sharedTrackHeaderHeightPx(tracks: WellLogTrack[]): number {
  const maxCurveRows = tracks.reduce((maxRows, track) => (
    track.trackType === 'curve' ? Math.max(maxRows, orderedCurves(track).length) : maxRows
  ), 0);

  const requiredCurveHeaderHeight =
    TRACK_HEADER_TITLE_HEIGHT_PX +
    TRACK_HEADER_SUBTITLE_HEIGHT_PX +
    maxCurveRows * TRACK_CURVE_HEADER_ROW_HEIGHT_PX +
    TRACK_HEADER_BOTTOM_PADDING_PX;

  return Math.max(TRACK_HEADER_HEIGHT_PX, requiredCurveHeaderHeight);
}

function displayTitleForTrack(track: WellLogTrack, catalog: CurveCatalogItem[]): string {
  if (track.trackType !== 'curve') return track.title;
  const mnemonics = orderedCurves(track)
    .map((assignment) => catalog.find((curve) => curve.curveId === assignment.curveId)?.mnemonic ?? assignment.curveId)
    .map((value) => String(value || '').trim())
    .filter(Boolean);

  if (mnemonics.length === 0) return track.title || 'Curve Track';
  return mnemonics.join(' / ');
}

function valueToX(value: number, assignment: CurveAssignment, lattice: CurveTrack['lattice'], trackWidth: number): number {
  const safeTrackWidth = Math.max(CURVE_TRACK_MIN_WIDTH, trackWidth);
  const drawableWidth = safeTrackWidth - CURVE_VIEW_PADDING_X * 2;
  const rawLeft = assignment.scaleMin;
  const rawRight = assignment.scaleMax;
  const scaleType = assignment.scaleType ?? (lattice === 'logarithmic' ? 'log' : 'linear');
  const clipToTrack = assignment.clipToTrack ?? true;

  const leftEndpoint = assignment.scaleDirection === 'reverse' && rawLeft < rawRight ? rawRight : rawLeft;
  const rightEndpoint = assignment.scaleDirection === 'reverse' && rawLeft < rawRight ? rawLeft : rawRight;

  let t = 0.5;

  if (scaleType === 'log' && leftEndpoint > 0 && rightEndpoint > 0 && rightEndpoint !== leftEndpoint) {
    const low = Math.min(leftEndpoint, rightEndpoint);
    const high = Math.max(leftEndpoint, rightEndpoint);
    const logLeft = Math.log10(leftEndpoint);
    const logRight = Math.log10(rightEndpoint);
    const boundedValue = clipToTrack
      ? clampValue(value, low, high)
      : Math.max(value, Number.MIN_VALUE);
    t = (Math.log10(boundedValue) - logLeft) / (logRight - logLeft);
  } else {
    const denominator = rightEndpoint - leftEndpoint;
    if (denominator === 0) return safeTrackWidth / 2;
    const boundedValue = clipToTrack
      ? clampValue(value, Math.min(leftEndpoint, rightEndpoint), Math.max(leftEndpoint, rightEndpoint))
      : value;
    t = (boundedValue - leftEndpoint) / denominator;
  }

  const anchorBias = assignment.positionAnchor === 'left'
    ? -0.18
    : assignment.positionAnchor === 'right'
      ? 0.18
      : 0;
  const offset = ((assignment.horizontalOffsetPct ?? 0) / 100) * drawableWidth;
  const scaledT = clipToTrack ? clampValue(t, 0, 1) : t;
  const x = CURVE_VIEW_PADDING_X + scaledT * drawableWidth + anchorBias * drawableWidth + offset;

  return clipToTrack
    ? clampValue(x, CURVE_VIEW_PADDING_X, safeTrackWidth - CURVE_VIEW_PADDING_X)
    : x;
}




type LogGridLine = {
  value: number;
  x: number;
  major: boolean;
  powerOfTen: boolean;
};

function nearlyEqual(a: number, b: number): boolean {
  return Math.abs(a - b) <= Math.max(1e-9, Math.abs(b) * 1e-9);
}

function logValueToX(value: number, scaleMin: number, scaleMax: number, trackWidth: number): number {
  const safeTrackWidth = Math.max(CURVE_TRACK_MIN_WIDTH, trackWidth);
  const drawableWidth = safeTrackWidth - CURVE_VIEW_PADDING_X * 2;
  const safeValue = clampValue(value, Math.min(scaleMin, scaleMax), Math.max(scaleMin, scaleMax));
  const logMin = Math.log10(scaleMin);
  const logMax = Math.log10(scaleMax);
  const t = (Math.log10(safeValue) - logMin) / (logMax - logMin);

  return CURVE_VIEW_PADDING_X + clampValue(t, 0, 1) * drawableWidth;
}

function logGridRangeForTrack(track: CurveTrack): { min: number; max: number } | null {
  const positiveAssignments = orderedCurves(track).filter(
    (assignment) => assignment.scaleMin > 0 && assignment.scaleMax > 0 && assignment.scaleMin !== assignment.scaleMax,
  );

  if (positiveAssignments.length === 0) return null;

  const min = Math.min(...positiveAssignments.map((assignment) => Math.min(assignment.scaleMin, assignment.scaleMax)));
  const max = Math.max(...positiveAssignments.map((assignment) => Math.max(assignment.scaleMin, assignment.scaleMax)));

  if (!Number.isFinite(min) || !Number.isFinite(max) || min <= 0 || max <= min) return null;

  return { min, max };
}

function logGridMajorValues(scaleMin: number, scaleMax: number): number[] {
  const values: number[] = [];
  let value = scaleMin;
  let guard = 0;

  while (value <= scaleMax * (1 + 1e-9) && guard < 12) {
    values.push(value);
    value *= 10;
    guard += 1;
  }

  if (!values.some((candidate) => nearlyEqual(candidate, scaleMax))) {
    values.push(scaleMax);
  }

  return values;
}

function logGridLines(scaleMin: number, scaleMax: number, trackWidth: number): LogGridLine[] {
  const majorValues = logGridMajorValues(scaleMin, scaleMax);
  const startPower = Math.floor(Math.log10(scaleMin)) - 1;
  const endPower = Math.ceil(Math.log10(scaleMax)) + 1;
  const lines = new Map<string, LogGridLine>();

  const addLine = (value: number, major: boolean, powerOfTen: boolean) => {
    if (value < scaleMin * (1 - 1e-9) || value > scaleMax * (1 + 1e-9)) return;
    const roundedKey = value.toPrecision(12);
    const existing = lines.get(roundedKey);
    const x = logValueToX(value, scaleMin, scaleMax, trackWidth);
    lines.set(roundedKey, {
      value,
      x,
      major: major || existing?.major || false,
      powerOfTen: powerOfTen || existing?.powerOfTen || false,
    });
  };

  majorValues.forEach((value) => addLine(value, true, false));

  for (let power = startPower; power <= endPower; power += 1) {
    const decade = 10 ** power;
    for (let multiplier = 1; multiplier < 10; multiplier += 1) {
      const value = multiplier * decade;
      const isPowerOfTen = multiplier === 1;
      const isMajor = majorValues.some((majorValue) => nearlyEqual(majorValue, value));
      addLine(value, isMajor, isPowerOfTen);
    }
  }

  return [...lines.values()].sort((a, b) => a.value - b.value);
}

function renderLogarithmicGrid(track: CurveTrack, trackWidth: number, bodyHeightPx: number) {
  const range = logGridRangeForTrack(track);
  if (!range) return null;

  const lines = logGridLines(range.min, range.max, trackWidth);

  return (
    <g className="wlv-log-grid" aria-hidden="true">
      {lines.map((line) => (
        <line
          key={`log-grid-${track.trackId}-${line.value}`}
          className={`wlv-log-grid-line ${line.major ? 'major' : line.powerOfTen ? 'power' : 'minor'}`}
          x1={line.x}
          x2={line.x}
          y1="0"
          y2={bodyHeightPx}
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </g>
  );
}

const PROTOTYPE_SAMPLE_ALIASES_BY_MNEMONIC: Record<string, string[]> = {
  RXO: ['RXOZ', 'RXO8'],
};

function sampleKeysForCurve(curve: CurveCatalogItem): string[] {
  const keys = [curve.curveId, curve.mnemonic];
  const aliases = PROTOTYPE_SAMPLE_ALIASES_BY_MNEMONIC[String(curve.mnemonic || '').toUpperCase()] ?? [];
  return [...keys, ...aliases].filter((key, index, allKeys) => Boolean(key) && allKeys.indexOf(key) === index);
}

function makeMockCurveSamples(
  curve: CurveCatalogItem,
  _assignment: CurveAssignment,
  _trackPosition: number,
): MockCurveSample[] {
  const samples = sampleKeysForCurve(curve)
    .map((key) => realCurveSamplesByCurveId[key])
    .find((candidate) => candidate?.length) ?? [];
  const output: MockCurveSample[] = [];

  for (const sample of samples as unknown[]) {
    let depthValue: unknown;
    let curveValue: unknown;

    if (Array.isArray(sample)) {
      depthValue = sample[0];
      curveValue = sample[1];
    } else if (sample && typeof sample === 'object') {
      const sampleRecord = sample as {
        depth?: unknown;
        value?: unknown;
        values?: Record<string, unknown>;
      };

      depthValue =
        sampleRecord.depth ??
        sampleRecord.values?.DEPT ??
        sampleRecord.values?.DEPTH ??
        sampleRecord.values?.MD ??
        sampleRecord.values?.TDEP;

      curveValue = sampleRecord.value ?? sampleRecord.values?.[curve.curveId] ?? sampleRecord.values?.[curve.mnemonic];
    }

    if (
      typeof depthValue === 'number' &&
      Number.isFinite(depthValue) &&
      typeof curveValue === 'number' &&
      Number.isFinite(curveValue)
    ) {
      output.push({
        depth: depthValue,
        value: curveValue,
      });
    }
  }

  return output;
}


function visibleCurveSamples(
  curve: CurveCatalogItem,
  assignment: CurveAssignment,
  trackPosition: number,
  viewRange: DepthViewRange,
): MockCurveSample[] {
  const padding = Math.max(10, (viewRange.max - viewRange.min) * 0.03);
  return makeMockCurveSamples(curve, assignment, trackPosition).filter((sample) => (
    sample.depth >= viewRange.min - padding && sample.depth <= viewRange.max + padding
  ));
}

type CurveRenderPoint = {
  depth: number;
  x: number;
  y: number;
};

function curveRenderPoints(
  curve: CurveCatalogItem,
  assignment: CurveAssignment,
  trackPosition: number,
  viewRange: DepthViewRange,
  lattice: CurveTrack['lattice'],
  trackWidth: number,
  bodyHeightPx: number,
): CurveRenderPoint[] {
  return visibleCurveSamples(curve, assignment, trackPosition, viewRange).map((sample) => ({
    depth: sample.depth,
    x: valueToX(sample.value, assignment, lattice, trackWidth),
    y: depthToY(sample.depth, viewRange, bodyHeightPx),
  }));
}

function pathFromCurvePoints(points: CurveRenderPoint[]): string {
  return points.map((point, index) => (
    `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`
  )).join(' ');
}

function polygonToAnchor(points: CurveRenderPoint[], anchorX: number): string {
  if (points.length < 2) return '';
  const first = points[0];
  const last = points[points.length - 1];
  return `${pathFromCurvePoints(points)} L ${anchorX.toFixed(1)} ${last.y.toFixed(1)} L ${anchorX.toFixed(1)} ${first.y.toFixed(1)} Z`;
}

function interpolatePointAtDepth(points: CurveRenderPoint[], depth: number): CurveRenderPoint | null {
  if (points.length === 0) return null;

  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const minDepth = Math.min(previous.depth, current.depth);
    const maxDepth = Math.max(previous.depth, current.depth);

    if (depth >= minDepth && depth <= maxDepth) {
      const denominator = current.depth - previous.depth;
      const t = denominator === 0 ? 0 : (depth - previous.depth) / denominator;
      return {
        depth,
        x: previous.x + (current.x - previous.x) * t,
        y: previous.y + (current.y - previous.y) * t,
      };
    }
  }

  const nearest = points.reduce((best, point) => (
    Math.abs(point.depth - depth) < Math.abs(best.depth - depth) ? point : best
  ), points[0]);

  return Math.abs(nearest.depth - depth) <= 1 ? nearest : null;
}

function polygonBetweenCurves(primaryPoints: CurveRenderPoint[], pairedPoints: CurveRenderPoint[]): string {
  const pairedAtPrimaryDepths = primaryPoints
    .map((point) => interpolatePointAtDepth(pairedPoints, point.depth))
    .filter((point): point is CurveRenderPoint => Boolean(point));

  if (primaryPoints.length < 2 || pairedAtPrimaryDepths.length < 2) return '';

  const pairedReversed = [...pairedAtPrimaryDepths].reverse();
  return `${pathFromCurvePoints(primaryPoints)} ${pairedReversed.map((point) => `L${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ')} Z`;
}

function fillAnchorForAssignment(assignment: CurveAssignment, trackWidth: number): number {
  if (assignment.fillSide === 'left') return CURVE_VIEW_PADDING_X;
  if (assignment.fillSide === 'right') return trackWidth - CURVE_VIEW_PADDING_X;
  return trackWidth / 2;
}

function svgFillForAssignment(assignment: CurveAssignment, intervalColor: string | null, trackId: string): string {
  if (assignment.infillSource === 'interval-column' && intervalColor) return intervalColor;
  if (assignment.infillSource === 'pattern') {
    if (assignment.infillPattern === 'dots') return `url(#infill-dots-${trackId})`;
    if (assignment.infillPattern === 'hatch') return `url(#infill-hatch-${trackId})`;
  }
  return assignment.fillColor;
}

function fillOpacityForAssignment(assignment: CurveAssignment): number {
  return clampValue((assignment.fillOpacity ?? 55) / 100, 0.1, 1);
}

function curvePriorityWeight(assignment: CurveAssignment): number {
  if (assignment.displayPriority === 'back') return 0;
  if (assignment.displayPriority === 'front') return 2;
  return 1;
}

function lineOpacityForAssignment(assignment: CurveAssignment): number {
  const baseOpacity = assignment.visible ? 1 : 0.2;
  return baseOpacity * clampValue((assignment.lineOpacity ?? 100) / 100, 0, 1);
}


function serialiseCurveDrag(payload: DragCurvePayload): string {
  return JSON.stringify(payload);
}

function lithologyPattern(unit: string): string {
  switch (unit) {
    case 'QTs':
      return 'radial-gradient(rgba(80, 55, 20, 0.16) 18%, transparent 19%) 0 0 / 8px 8px';
    case 'Tba':
      return 'repeating-linear-gradient(135deg, rgba(32, 74, 44, 0.20) 0 4px, transparent 4px 9px)';
    case 'Trd':
      return 'repeating-linear-gradient(45deg, rgba(95, 50, 98, 0.18) 0 3px, transparent 3px 8px), repeating-linear-gradient(-45deg, rgba(95, 50, 98, 0.10) 0 3px, transparent 3px 8px)';
    case 'Mza':
      return 'repeating-linear-gradient(135deg, rgba(20, 63, 50, 0.26) 0 5px, transparent 5px 10px)';
    case 'Mzr':
      return 'repeating-linear-gradient(0deg, rgba(86, 61, 130, 0.15) 0 2px, transparent 2px 7px), repeating-linear-gradient(90deg, rgba(86, 61, 130, 0.10) 0 2px, transparent 2px 9px)';
    case 'Mzp':
      return 'repeating-linear-gradient(0deg, rgba(56, 76, 104, 0.22) 0 2px, transparent 2px 6px)';
    case 'Mzq':
      return 'repeating-linear-gradient(90deg, rgba(130, 112, 40, 0.18) 0 3px, transparent 3px 11px), repeating-linear-gradient(0deg, rgba(130, 112, 40, 0.12) 0 3px, transparent 3px 11px)';
    default:
      return 'none';
  }
}


type CurveInventoryTab = 'all' | 'selected' | 'aliases';

// WLV-WDV-CURVE-INVENTORY-RESIZE-1
// Keep the current WDV curve inventory width as the minimum/default and allow
// the user to widen it to the right without changing backend/session state.
const CURVE_INVENTORY_DEFAULT_WIDTH_PX = 300;
const CURVE_INVENTORY_MIN_WIDTH_PX = CURVE_INVENTORY_DEFAULT_WIDTH_PX;
const CURVE_INVENTORY_MAX_WIDTH_PX = 680;

type CurveInventoryResizeState = {
  startX: number;
  startWidth: number;
};

function clampCurveInventoryWidth(widthPx: number): number {
  return Math.max(
    CURVE_INVENTORY_MIN_WIDTH_PX,
    Math.min(CURVE_INVENTORY_MAX_WIDTH_PX, Math.round(widthPx)),
  );
}


function CurveInventory({
  availableCurves,
  curveUsageCounts,
  visibleTrackCurveIds,
  selectedTrackCurveIds,
  selectedCurveIds,
  assignmentEnabled,
  preferredInventoryTab,
  onSelectCurve,
  onToggleCurveInSelectedTrack,
}: {
  availableCurves: CurveCatalogItem[];
  curveUsageCounts: Map<string, number>;
  visibleTrackCurveIds: Set<string>;
  selectedTrackCurveIds: Set<string>;
  selectedCurveIds: Set<string>;
  assignmentEnabled: boolean;
  preferredInventoryTab: CurveInventoryTab;
  onSelectCurve: (curveId: string) => void;
  onToggleCurveInSelectedTrack: (curveId: string, checked: boolean) => void;
}) {
  const [activeInventoryTab, setActiveInventoryTab] = useState<CurveInventoryTab>(preferredInventoryTab);
  const [expandedDuplicateGroups, setExpandedDuplicateGroups] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setActiveInventoryTab(preferredInventoryTab);
  }, [preferredInventoryTab]);

  const displayedCurves = useMemo(() => {
    if (activeInventoryTab === 'aliases') return [];
    if (activeInventoryTab === 'selected') {
      return availableCurves.filter((curve) => visibleTrackCurveIds.has(curve.curveId));
    }
    return availableCurves.filter((curve) => (curveUsageCounts.get(curve.curveId) ?? 0) > 0);
  }, [activeInventoryTab, availableCurves, curveUsageCounts, visibleTrackCurveIds]);

  const groups = useMemo(
    () => Array.from(new Set(displayedCurves.map((curve) => curve.curveClass))).filter((group) => group !== 'depth'),
    [displayedCurves],
  );

  const curvesByGroupAndMnemonic = useMemo(() => {
    const grouped = new Map<string, Map<string, CurveCatalogItem[]>>();
    displayedCurves.forEach((curve) => {
      const classKey = curve.curveClass;
      const mnemonicKey = curve.mnemonic || curve.curveId;
      const classGroup = grouped.get(classKey) ?? new Map<string, CurveCatalogItem[]>();
      const mnemonicGroup = classGroup.get(mnemonicKey) ?? [];
      mnemonicGroup.push(curve);
      mnemonicGroup.sort((left, right) => {
        const leftDescription = `${left.description || ''} ${left.unit || ''}`;
        const rightDescription = `${right.description || ''} ${right.unit || ''}`;
        return leftDescription.localeCompare(rightDescription);
      });
      classGroup.set(mnemonicKey, mnemonicGroup);
      grouped.set(classKey, classGroup);
    });
    return grouped;
  }, [displayedCurves]);

  const selectedCurveCount = useMemo(
    () => availableCurves.filter((curve) => visibleTrackCurveIds.has(curve.curveId)).length,
    [availableCurves, visibleTrackCurveIds],
  );

  const loadedProductCount = useMemo(
    () => Array.from(curveUsageCounts.values()).reduce((total, count) => total + count, 0),
    [curveUsageCounts],
  );

  const inventoryCount = loadedProductCount;

  const toggleDuplicateGroup = (groupKey: string) => {
    setExpandedDuplicateGroups((current) => {
      const next = new Set(current);
      if (next.has(groupKey)) next.delete(groupKey);
      else next.add(groupKey);
      return next;
    });
  };

  const renderCurveRow = (curve: CurveCatalogItem, options?: { duplicateInstance?: boolean }) => {
    const usageCount = curveUsageCounts.get(curve.curveId) ?? 0;
    const usedAnywhere = visibleTrackCurveIds.has(curve.curveId);
    const checkedInSelectedTrack = selectedTrackCurveIds.has(curve.curveId);
    const highlightAsSelected = activeInventoryTab === 'selected' || (activeInventoryTab !== 'all' && selectedCurveIds.has(curve.curveId));

    return (
      <div
        key={curve.curveId}
        role="button"
        tabIndex={0}
        className={`wlv-curve-row ${options?.duplicateInstance ? 'duplicate-instance' : ''} ${usedAnywhere ? 'assigned' : ''} ${checkedInSelectedTrack ? 'checked-in-track' : ''} ${highlightAsSelected ? 'inventory-selected' : ''} ${curve.recognised ? '' : 'unrecognised'}`}
        draggable
        onClick={() => onSelectCurve(curve.curveId)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onSelectCurve(curve.curveId);
          }
        }}
        onDragStart={(event) => {
          event.dataTransfer.setData('application/json', serialiseCurveDrag({ dragType: 'curve', curveId: curve.curveId }));
          event.dataTransfer.effectAllowed = 'move';
        }}
      >
        <button
          type="button"
          className={`wlv-checkbox ${checkedInSelectedTrack ? 'checked' : ''}`}
          disabled={!assignmentEnabled}
          aria-label={`${checkedInSelectedTrack ? 'Remove' : 'Add'} ${curve.mnemonic} ${checkedInSelectedTrack ? 'from' : 'to'} selected track`}
          title={assignmentEnabled ? 'Assign/remove curve for selected track' : 'Select a curve track to assign curves'}
          onClick={(event) => {
            event.stopPropagation();
            if (!assignmentEnabled) return;
            onToggleCurveInSelectedTrack(curve.curveId, !checkedInSelectedTrack);
          }}
        >
          {checkedInSelectedTrack ? '✓' : ''}
        </button>
        <strong>{curve.mnemonic}</strong>
        <span>{curve.description}</span>
        <em>{curve.unit}</em>
        {activeInventoryTab !== 'all' && usageCount > 1 && <span className="wlv-curve-count" title="Curve is used in multiple tracks">{usageCount}</span>}
      </div>
    );
  };

  const renderLoadedMnemonicGroup = (group: string, mnemonic: string, curves: CurveCatalogItem[]) => {
    if (activeInventoryTab !== 'all' || curves.length === 1) {
      return curves.map((curve) => renderCurveRow(curve));
    }

    const groupKey = `${group}:${mnemonic}`;
    const expanded = expandedDuplicateGroups.has(groupKey);
    const assignedCount = curves.filter((curve) => visibleTrackCurveIds.has(curve.curveId)).length;
    const checkedCount = curves.filter((curve) => selectedTrackCurveIds.has(curve.curveId)).length;
    const units = Array.from(new Set(curves.map((curve) => curve.unit).filter(Boolean)));
    const intervals = Array.from(new Set(curves.map((curve) => curve.description).filter(Boolean)));
    const summaryText = `${curves.length} instances${intervals.length ? ` · ${intervals.length} intervals/runs` : ''}`;

    return (
      <div key={groupKey} className="wlv-duplicate-curve-block">
        <button
          type="button"
          className={`wlv-curve-row wlv-curve-duplicate-summary ${expanded ? 'expanded' : ''} ${checkedCount > 0 ? 'checked-in-track' : ''}`}
          onClick={() => toggleDuplicateGroup(groupKey)}
          aria-expanded={expanded}
          title="Expand duplicate mnemonic instances"
        >
          <span className="wlv-duplicate-expander">{expanded ? '▾' : '▸'}</span>
          <strong>{mnemonic}</strong>
          <span>{summaryText}</span>
          <em>{units.length ? units.join(' / ') : ''}</em>
          <span className="wlv-curve-count" title="Loaded curve product instances">{curves.length}</span>
        </button>
        {assignedCount > 0 && <div className="wlv-duplicate-group-note">{assignedCount} assigned to visible tracks</div>}
        {expanded && (
          <div className="wlv-duplicate-instance-list">
            {curves.map((curve) => renderCurveRow(curve, { duplicateInstance: true }))}
          </div>
        )}
      </div>
    );
  };

  return (
    <aside className="wlv-curve-inventory">
      <div className="wlv-panel-heading">
        <h2>Curve Inventory</h2>
        <span>{inventoryCount}</span>
      </div>
      <div className="wlv-search-row">
        <input aria-label="Search curves" placeholder="Search curves..." />
        <button type="button" title="Filter curves">Filter</button>
      </div>
      <div className="wlv-inventory-tabs">
        <button type="button" className={activeInventoryTab === 'all' ? 'active' : ''} onClick={() => setActiveInventoryTab('all')}>Loaded</button>
        <button type="button" className={activeInventoryTab === 'selected' ? 'active' : ''} onClick={() => setActiveInventoryTab('selected')}>Selected <span className="wlv-tab-count">{selectedCurveCount}</span></button>
        <button type="button" className={activeInventoryTab === 'aliases' ? 'active' : ''} onClick={() => setActiveInventoryTab('aliases')}>Aliases</button>
      </div>
      {!assignmentEnabled && (
        <div className="wlv-curve-assignment-hint">Select a curve track to assign curves. Loaded rows stay neutral; selected/assigned rows are highlighted only after you assign them.</div>
      )}
      {activeInventoryTab === 'all' && (
        <div className="wlv-curve-assignment-hint">Duplicate mnemonics are grouped. Expand a group to choose individual curve products by run or interval.</div>
      )}
      {activeInventoryTab === 'selected' && selectedCurveCount === 0 && (
        <div className="wlv-curve-assignment-hint">No curves are currently assigned to visible tracks.</div>
      )}
      {activeInventoryTab === 'aliases' && (
        <div className="wlv-curve-assignment-hint">Alias grouping is not available in this prototype fixture yet.</div>
      )}
      <div className="wlv-inventory-list">
        {groups.map((group) => {
          const mnemonicGroups = curvesByGroupAndMnemonic.get(group) ?? new Map<string, CurveCatalogItem[]>();
          return (
            <section key={group} className="wlv-curve-group">
              <div className="wlv-curve-group-title">{group}</div>
              {Array.from(mnemonicGroups.entries()).map(([mnemonic, curves]) => renderLoadedMnemonicGroup(group, mnemonic, curves))}
            </section>
          );
        })}
      </div>
      <div className="wlv-drop-help">Drag curves into curve tracks. Drag curve headers between tracks to move assignments.</div>
    </aside>
  );
}


function WdvTemplateRecommendationModal({
  recommendation,
  loadedCurveItems,
  managedWellId,
  onClose,
}: {
  recommendation: WdvTemplateRecommendationItem;
  loadedCurveItems: WdvLoadedCurveItem[];
  managedWellId?: string | null;
  onClose: () => void;
}) {
  const [applicationPlanEnvelope, setApplicationPlanEnvelope] = useState<WdvTemplateApplicationPlanEnvelope | null>(null);
  const [applicationPlanLoading, setApplicationPlanLoading] = useState(false);
  const [applicationPlanError, setApplicationPlanError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setApplicationPlanLoading(true);
    setApplicationPlanError(null);
    setApplicationPlanEnvelope(null);

    void buildWdvTemplateApplicationPlan(recommendation.template_key, loadedCurveItems, managedWellId)
      .then((result) => {
        if (!cancelled) {
          setApplicationPlanEnvelope(result);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setApplicationPlanError(error instanceof Error ? error.message : 'Application plan service unavailable');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setApplicationPlanLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [recommendation.template_key, loadedCurveItems, managedWellId]);

  const plan = applicationPlanEnvelope?.plan ?? null;
  const selectedCurves = uniqueVisibleRecommendedCurves(plan?.selected_curves ?? recommendation.selected_curves ?? []);
  const alternateCurves = uniqueVisibleRecommendedCurves(plan?.alternate_curves ?? recommendation.alternate_curves ?? []);
  const tracks = plan?.tracks ?? recommendation.tracks ?? [];
  const missingRequiredFamilies = plan?.missing_required_families ?? recommendation.missing_required_families ?? [];
  const missingPreferredFamilies = plan?.missing_preferred_families ?? recommendation.missing_preferred_families ?? [];
  const rendererRequirements = plan?.renderer_requirements ?? recommendation.renderer_requirements ?? [];
  const blockingIssues = plan?.blocking_issues ?? [];
  const planWarnings = plan?.warnings ?? [];
  const planStatus = plan?.plan_status ?? (applicationPlanLoading ? 'building_plan' : 'recommendation_only');
  const applyEligible = plan?.apply_eligible ?? false;
  const mutationPerformed = applicationPlanEnvelope?.mutation_performed ?? false;

  return createPortal(
    <div className="wlv-template-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="wlv-template-modal"
        role="dialog"
        aria-modal="true"
        aria-label="WDV template application plan"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="wlv-template-modal-header">
          <div>
            <span>Backend KR application plan</span>
            <h2>{plan?.template_label ?? recommendation.template_label}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close template application plan">×</button>
        </header>

        <div className="wlv-template-plan-banner">
          <strong>{applicationPlanLoading ? 'Building backend-owned staged plan…' : formatPlanStatus(planStatus)}</strong>
          <span>
            {applicationPlanError
              ? applicationPlanError
              : mutationPerformed
                ? 'Unexpected mutation reported by backend.'
                : 'Non-mutating preview only. Tracks are not populated in this block.'}
          </span>
        </div>

        <div className="wlv-template-modal-summary">
          <div><strong>Template match</strong><span>{formatTemplateMatch(plan?.source_recommendation_score ?? recommendation.score)}</span></div>
          <div><strong>Plan</strong><span>{applyEligible ? 'Ready for review' : 'Review required'}</span></div>
          <div><strong>Curves</strong><span>{selectedCurves.length} selected</span></div>
          <div><strong>Missing required</strong><span>{missingRequiredFamilies.length ? missingRequiredFamilies.length : 'None'}</span></div>
        </div>

        <section className="wlv-template-modal-section">
          <h3>Backend plan status</h3>
          <dl className="wlv-template-modal-dl">
            <dt>Plan status</dt>
            <dd>{formatPlanStatus(planStatus)}</dd>
            <dt>Apply mode</dt>
            <dd>{formatPlanStatus(plan?.apply_mode ?? 'review_required_non_mutating_plan')}</dd>
            <dt>Blocking issues</dt>
            <dd>{compactFamilyList(blockingIssues, 'None')}</dd>
            <dt>Warnings</dt>
            <dd>{compactFamilyList(planWarnings, 'None')}</dd>
          </dl>
        </section>

        <section className="wlv-template-modal-section">
          <h3>Coverage</h3>
          <dl className="wlv-template-modal-dl">
            <dt>Available families</dt>
            <dd>{compactFamilyList(recommendation.required_coverage?.available_families, 'No matching required families')}</dd>
            <dt>Missing required</dt>
            <dd>{compactFamilyList(missingRequiredFamilies, 'None')}</dd>
            <dt>Missing preferred</dt>
            <dd>{compactFamilyList(missingPreferredFamilies, 'None')}</dd>
            <dt>Renderers</dt>
            <dd>{compactRendererList(rendererRequirements)}</dd>
          </dl>
        </section>

        <section className="wlv-template-modal-section">
          <h3>Selected representative curves</h3>
          {selectedCurves.length > 0 ? (
            <div className="wlv-template-curve-list">
              {selectedCurves.slice(0, 12).map((curve, index) => (
                <div key={`${curve.product_id ?? curve.curve_id ?? curve.mnemonic ?? 'curve'}-${index}`} className="wlv-template-curve-row">
                  <strong>{curve.mnemonic || curve.display_name || curve.curve_id || 'Curve'}</strong>
                  <span>{curve.curve_family || curve.raw_curve_family || 'unclassified'}</span>
                  <em>{curve.selection_reason || 'backend selected'}</em>
                </div>
              ))}
            </div>
          ) : (
            <p className="wlv-template-empty-note">No representative curves selected by the backend for this template.</p>
          )}
        </section>

        <section className="wlv-template-modal-section">
          <h3>Alternates</h3>
          {alternateCurves.length > 0 ? (
            <div className="wlv-template-curve-list">
              {alternateCurves.slice(0, 8).map((curve, index) => (
                <div key={`${curve.product_id ?? curve.curve_id ?? curve.mnemonic ?? 'alternate'}-${index}`} className="wlv-template-curve-row">
                  <strong>{curve.mnemonic || curve.display_name || curve.curve_id || 'Curve'}</strong>
                  <span>{curve.curve_family || curve.raw_curve_family || 'unclassified'}</span>
                  <em>{curve.selection_reason || 'alternate'}</em>
                </div>
              ))}
            </div>
          ) : (
            <p className="wlv-template-empty-note">No alternate curves returned by the backend for this plan.</p>
          )}
        </section>

        <section className="wlv-template-modal-section">
          <h3>Track plan</h3>
          <div className="wlv-template-track-plan">
            {tracks.slice(0, 10).map((track) => (
              <div key={track.track_key || track.track_id || track.track_name || String(track.track_number)} className="wlv-template-track-row">
                <strong>{track.track_number ?? '—'}. {track.track_name || track.track_key || 'Track'}</strong>
                <span>{track.renderer_type || 'renderer pending'}</span>
                <small>
                  {(track.selected_curves ?? []).map((curve) => curve.mnemonic || curve.display_name || curve.curve_id).filter(Boolean).join(', ') || 'no selected curves'} · {scaleSummary(track.scale_defaults)}
                </small>
              </div>
            ))}
          </div>
        </section>

        <footer className="wlv-template-modal-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="button" disabled title="Template application is reserved for a later backend-owned apply block">
            Apply disabled
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

type AddTrackDraft = {
  trackType: ActiveTrackType;
  depthBasis: DepthBasis;
  insertMode: 'before_selected' | 'after_selected' | 'far_right';
  curveSource: 'empty' | 'selected';
  latticeMode: 'auto' | 'linear' | 'logarithmic';
  scaleMode: ScaleMode;
};

const defaultAddTrackDraft: AddTrackDraft = {
  trackType: 'curve',
  depthBasis: 'MD',
  insertMode: 'after_selected',
  curveSource: 'empty',
  latticeMode: 'auto',
  scaleMode: 'per_curve',
};

type TrackBackdropMode = 'light' | 'dark';

function Toolbar({
  selectedTrack,
  pendingAddTrackCurveCount,
  viewDepthRange,
  fullDepthRange,
  viewDepthReadoutEnabled,
  intervalZoomActive,
  goToDepthValue,
  onGoToDepthValueChange,
  trackBackdropMode,
  onTrackBackdropModeChange,
  onAddTrack,
  onDeleteTrack,
  onMoveSelectedTrack,
  canMoveSelectedTrackLeft,
  canMoveSelectedTrackRight,
  canAdjustSelectedCurveTrackWidthDown,
  canAdjustSelectedCurveTrackWidthUp,
  onAdjustSelectedCurveTrackWidth,
  onResetCurveTrackWidths,
  onZoomIn,
  onZoomOut,
  onPreviousView,
  onFitDepth,
  onSpecifyDepthRange,
  onResetView,
  onToggleIntervalZoom,
  onGoToDepth,
  onAddTrackCurveSelectionModeChange,
  layoutRecommendations,
  layoutRecommendationsLoading,
  layoutRecommendationsError,
  selectedLayoutRecommendationKey,
  onLayoutRecommendationChange,
  onRefreshLayoutRecommendations,
}: {
  selectedTrack: WellLogTrack | null;
  pendingAddTrackCurveCount: number;
  viewDepthRange: DepthViewRange;
  fullDepthRange: DepthViewRange;
  viewDepthReadoutEnabled: boolean;
  intervalZoomActive: boolean;
  goToDepthValue: string;
  onGoToDepthValueChange: (value: string) => void;
  trackBackdropMode: TrackBackdropMode;
  onTrackBackdropModeChange: (mode: TrackBackdropMode) => void;
  onAddTrack: (draft: AddTrackDraft) => void;
  onDeleteTrack: () => void;
  onMoveSelectedTrack: (direction: -1 | 1) => void;
  canMoveSelectedTrackLeft: boolean;
  canMoveSelectedTrackRight: boolean;
  canAdjustSelectedCurveTrackWidthDown: boolean;
  canAdjustSelectedCurveTrackWidthUp: boolean;
  onAdjustSelectedCurveTrackWidth: (delta: number) => void;
  onResetCurveTrackWidths: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onPreviousView: () => void;
  onFitDepth: () => void;
  onSpecifyDepthRange: (range: DepthViewRange) => void;
  onResetView: () => void;
  onToggleIntervalZoom: () => void;
  onGoToDepth: () => void;
  onAddTrackCurveSelectionModeChange: (active: boolean) => void;
  layoutRecommendations: WdvTemplateRecommendationItem[];
  layoutRecommendationsLoading: boolean;
  layoutRecommendationsError: string | null;
  selectedLayoutRecommendationKey: string;
  onLayoutRecommendationChange: (templateKey: string) => void;
  onRefreshLayoutRecommendations: () => void;
}) {
  const [builderOpen, setBuilderOpen] = useState(false);
  const [draft, setDraft] = useState<AddTrackDraft>(defaultAddTrackDraft);
  const [panelPosition, setPanelPosition] = useState({ top: 128, left: 360 });
  const [rangeEditorOpen, setRangeEditorOpen] = useState(false);
  const [rangeTopValue, setRangeTopValue] = useState(String(Math.round(viewDepthRange.min)));
  const [rangeBaseValue, setRangeBaseValue] = useState(String(Math.round(viewDepthRange.max)));
  const specifyRangeButtonRef = useRef<HTMLButtonElement | null>(null);
  const specifyRangePopoverRef = useRef<HTMLDivElement | null>(null);
  const [rangePopoverPosition, setRangePopoverPosition] = useState({ top: 0, left: 0 });
  const dragStateRef = useRef<{
    startClientX: number;
    startClientY: number;
    startLeft: number;
    startTop: number;
  } | null>(null);

  useEffect(() => {
    if (rangeEditorOpen) return;
    setRangeTopValue(String(Math.round(viewDepthRange.min)));
    setRangeBaseValue(String(Math.round(viewDepthRange.max)));
  }, [rangeEditorOpen, viewDepthRange.min, viewDepthRange.max]);

  const updateSpecifiedRangePopoverPosition = () => {
    const button = specifyRangeButtonRef.current;
    if (!button) return;

    const rect = button.getBoundingClientRect();
    const popoverWidth = 292;
    const margin = 12;
    const preferredLeft = rect.left;
    const maxLeft = Math.max(margin, window.innerWidth - popoverWidth - margin);

    setRangePopoverPosition({
      top: rect.bottom + 10,
      left: clampValue(preferredLeft, margin, maxLeft),
    });
  };

  const openSpecifiedRangeEditor = () => {
    setRangeTopValue(String(Math.round(viewDepthRange.min)));
    setRangeBaseValue(String(Math.round(viewDepthRange.max)));
    setRangeEditorOpen((open) => {
      const nextOpen = !open;
      if (nextOpen) {
        window.requestAnimationFrame(updateSpecifiedRangePopoverPosition);
      }
      return nextOpen;
    });
  };

  const applySpecifiedRange = () => {
    const top = Number.parseFloat(rangeTopValue);
    const base = Number.parseFloat(rangeBaseValue);
    if (!Number.isFinite(top) || !Number.isFinite(base) || top === base) return;

    onSpecifyDepthRange({
      min: Math.min(top, base),
      max: Math.max(top, base),
    });
    setRangeEditorOpen(false);
  };

  useEffect(() => {
    if (!rangeEditorOpen) return undefined;

    const updatePosition = () => updateSpecifiedRangePopoverPosition();
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (specifyRangePopoverRef.current?.contains(target)) return;
      if (specifyRangeButtonRef.current?.contains(target)) return;
      setRangeEditorOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setRangeEditorOpen(false);
      }
    };

    updatePosition();
    window.addEventListener('resize', updatePosition, true);
    window.addEventListener('scroll', updatePosition, true);
    document.addEventListener('pointerdown', onPointerDown, true);
    document.addEventListener('keydown', onKeyDown, true);

    return () => {
      window.removeEventListener('resize', updatePosition, true);
      window.removeEventListener('scroll', updatePosition, true);
      document.removeEventListener('pointerdown', onPointerDown, true);
      document.removeEventListener('keydown', onKeyDown, true);
    };
  }, [rangeEditorOpen, viewDepthRange.min, viewDepthRange.max]);

  const updateDraft = (patch: Partial<AddTrackDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
  };

  const clampPanelPosition = (position: { top: number; left: number }) => {
    const margin = 12;
    const panelWidth = 420;
    return {
      top: Math.max(margin, Math.min(position.top, window.innerHeight - margin - 80)),
      left: Math.max(margin, Math.min(position.left, window.innerWidth - panelWidth - margin)),
    };
  };

  const openAddTrackBuilder = () => {
    setPanelPosition(clampPanelPosition({
      top: 118,
      left: Math.max(280, Math.round(window.innerWidth * 0.32)),
    }));
    setBuilderOpen(true);
  };

  const closeAddTrackBuilder = () => {
    setBuilderOpen(false);
    dragStateRef.current = null;
    onAddTrackCurveSelectionModeChange(false);
  };

  const toggleAddTrackBuilder = () => {
    if (builderOpen) {
      closeAddTrackBuilder();
      return;
    }

    openAddTrackBuilder();
  };

  const selectTrackType = (trackType: ActiveTrackType) => {
    updateDraft({ trackType });
    onAddTrackCurveSelectionModeChange(trackType === 'curve' && draft.curveSource === 'selected');
  };

  const selectCurveSource = (curveSource: AddTrackDraft['curveSource']) => {
    updateDraft({ curveSource });
    onAddTrackCurveSelectionModeChange(curveSource === 'selected');
  };

  const startPanelDrag = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragStateRef.current = {
      startClientX: event.clientX,
      startClientY: event.clientY,
      startLeft: panelPosition.left,
      startTop: panelPosition.top,
    };
  };

  useEffect(() => {
    if (!builderOpen) return undefined;

    const onMouseMove = (event: MouseEvent) => {
      const dragState = dragStateRef.current;
      if (!dragState) return;

      setPanelPosition(clampPanelPosition({
        top: dragState.startTop + event.clientY - dragState.startClientY,
        left: dragState.startLeft + event.clientX - dragState.startClientX,
      }));
    };

    const onMouseUp = () => {
      dragStateRef.current = null;
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeAddTrackBuilder();
      }
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    document.addEventListener('keydown', onKeyDown, true);

    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      document.removeEventListener('keydown', onKeyDown, true);
    };
  }, [builderOpen, panelPosition.left, panelPosition.top]);

  const addTrackLabel = 'Add track';
  const eligibleLayoutRecommendations = layoutRecommendations.filter((item) => item.is_eligible);
  const layoutRecommendationOptions = eligibleLayoutRecommendations.length > 0 ? eligibleLayoutRecommendations : layoutRecommendations;
  const layoutPresetPlaceholder = layoutRecommendationsLoading
    ? 'Loading KR presets...'
    : layoutRecommendationsError
      ? 'Template service unavailable'
      : layoutRecommendationOptions.length > 0
        ? 'Layout Preset ▾'
        : 'No KR presets available';

  const addTrackBuilder = builderOpen ? createPortal(
    <div
      className="wlv-add-track-builder wlv-add-track-builder-draggable"
      role="dialog"
      aria-label="Add Track Builder"
      style={{ top: panelPosition.top, left: panelPosition.left }}
    >
      <div className="builder-heading builder-drag-handle" onMouseDown={startPanelDrag}>
        <strong>Add Track</strong>
        <button
          type="button"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={closeAddTrackBuilder}
          aria-label="Close Add Track Builder"
        >
          ×
        </button>
      </div>

      <section className="builder-section">
        <div className="builder-label">Track type</div>
        <div className="builder-choice-grid">
          <button
            type="button"
            className={draft.trackType === 'depth' ? 'active' : ''}
            onClick={() => selectTrackType('depth')}
          >
            Depth
          </button>
          <button
            type="button"
            className={draft.trackType === 'curve' ? 'active' : ''}
            onClick={() => selectTrackType('curve')}
          >
            Curve
          </button>
          <button type="button" disabled title="Reserved for raster/core/lithology artifacts">Raster</button>
          <button type="button" disabled title="Reserved for marker datasets">Marker</button>
          <button type="button" disabled title="Reserved for interval datasets">Interval</button>
        </div>
      </section>

      {draft.trackType === 'depth' && (
        <section className="builder-section">
          <div className="builder-label">Depth subtype</div>
          <div className="builder-choice-grid three">
            {(['MD', 'TVD', 'TVDSS'] as DepthBasis[]).map((basis) => (
              <button
                key={basis}
                type="button"
                className={draft.depthBasis === basis ? 'active' : ''}
                onClick={() => updateDraft({ depthBasis: basis })}
              >
                {basis}
              </button>
            ))}
          </div>
          <p className="builder-note">TVD/TVDSS are mock-enabled here; backend validation will eventually decide availability.</p>
        </section>
      )}

      {draft.trackType === 'curve' && (
        <>
          <section className="builder-section">
            <div className="builder-label">Curve source</div>
            <div className="builder-choice-grid two">
              <button
                type="button"
                className={draft.curveSource === 'empty' ? 'active' : ''}
                onClick={() => selectCurveSource('empty')}
              >
                Empty
              </button>
              <button
                type="button"
                className={draft.curveSource === 'selected' ? 'active' : ''}
                onClick={() => selectCurveSource('selected')}
              >
                From selected ({pendingAddTrackCurveCount})
              </button>
            </div>
          </section>

          <section className="builder-section">
            <div className="builder-label">Lattice</div>
            <select
              value={draft.latticeMode}
              onChange={(event) => updateDraft({ latticeMode: event.target.value as AddTrackDraft['latticeMode'] })}
            >
              <option value="auto">Auto from front curve</option>
              <option value="linear">Linear override</option>
              <option value="logarithmic">Logarithmic override</option>
            </select>
          </section>

          <section className="builder-section">
            <div className="builder-label">Scale mode</div>
            <select value={draft.scaleMode} onChange={(event) => updateDraft({ scaleMode: event.target.value as ScaleMode })}>
              <option value="shared">Shared</option>
              <option value="per_curve">Per curve</option>
              <option value="dual">Dual</option>
            </select>
          </section>
        </>
      )}

      <section className="builder-section">
        <div className="builder-label">Insert position</div>
        <select
          value={draft.insertMode}
          onChange={(event) => updateDraft({ insertMode: event.target.value as AddTrackDraft['insertMode'] })}
        >
          <option value="before_selected">Before selected track</option>
          <option value="after_selected">After selected track</option>
          <option value="far_right">Far right</option>
        </select>
      </section>

      <div className="builder-actions">
        <button type="button" onClick={closeAddTrackBuilder}>Cancel</button>
        <button
          type="button"
          className="builder-primary"
          onClick={() => {
            onAddTrack(draft);
            closeAddTrackBuilder();
          }}
        >
          {addTrackLabel}
        </button>
      </div>
    </div>,
    document.body,
  ) : null;

  return (
    <div className="wlv-track-toolbar" aria-label="Well log viewer toolbar">
      <div className="wlv-toolbar-group wlv-toolbar-group-track">
        <span>Add / Delete Tracks</span>
        <div className="wlv-toolbar-actions">
          <div className="wlv-add-track-control">
            <button
              type="button"
              className="wlv-add-track-button"
              onClick={toggleAddTrackBuilder}
              aria-expanded={builderOpen}
            >
              + Add Track ▾
            </button>
          </div>
          {addTrackBuilder}
          <button type="button" disabled={!selectedTrack} onClick={onDeleteTrack}>Delete</button>
        </div>
      </div>

      <div className="wlv-toolbar-group wlv-toolbar-group-arrange">
        <span>Track Layout</span>
        <div className="wlv-toolbar-actions">
          <button
            type="button"
            disabled={!canMoveSelectedTrackLeft}
            title={selectedTrack ? 'Move selected track left' : 'Select a track first'}
            aria-label="Move selected track left"
            onClick={() => onMoveSelectedTrack(-1)}
          >
            ←
          </button>
          <button
            type="button"
            disabled={!canMoveSelectedTrackRight}
            title={selectedTrack ? 'Move selected track right' : 'Select a track first'}
            aria-label="Move selected track right"
            onClick={() => onMoveSelectedTrack(1)}
          >
            →
          </button>
          <button
            type="button"
            disabled={!canAdjustSelectedCurveTrackWidthDown}
            title={selectedTrack?.trackType === 'curve' ? 'Contract selected curve track' : 'Select a curve track first'}
            onClick={() => onAdjustSelectedCurveTrackWidth(-CURVE_TRACK_WIDTH_STEP)}
          >
            − Width
          </button>
          <button
            type="button"
            disabled={!canAdjustSelectedCurveTrackWidthUp}
            title={selectedTrack?.trackType === 'curve' ? 'Widen selected curve track' : 'Select a curve track first'}
            onClick={() => onAdjustSelectedCurveTrackWidth(CURVE_TRACK_WIDTH_STEP)}
          >
            + Width
          </button>
          <button
            type="button"
            onClick={onResetCurveTrackWidths}
            title="Reset all curve tracks to uniform width; depth tracks remain unchanged"
          >
            Reset
          </button>
          <select
            aria-label="Layout preset"
            className="wlv-layout-preset-select"
            value={selectedLayoutRecommendationKey}
            disabled={layoutRecommendationsLoading || layoutRecommendationOptions.length === 0}
            title={layoutRecommendationsError ?? 'Backend-approved KR layout presets'}
            onChange={(event) => onLayoutRecommendationChange(event.target.value)}
          >
            <option value="">{layoutPresetPlaceholder}</option>
            {layoutRecommendationOptions.map((item) => (
              <option key={item.template_key} value={item.template_key}>
                {item.template_label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="wlv-layout-preset-refresh"
            title="Refresh backend KR template recommendations"
            aria-label="Refresh backend KR template recommendations"
            disabled={layoutRecommendationsLoading}
            onClick={onRefreshLayoutRecommendations}
          >
            ↻
          </button>
        </div>
      </div>

      <div className="wlv-toolbar-group wlv-toolbar-group-view">
        <span>Zoom / View</span>
        <div className="wlv-toolbar-actions">
          <button type="button" title="Zoom Out" aria-label="Zoom Out" onClick={onZoomOut}>−</button>
          <button type="button" title="Zoom In" aria-label="Zoom In" onClick={onZoomIn}>+</button>
          <button
            type="button"
            className={intervalZoomActive ? 'active' : ''}
            title="Drag on the log to zoom to a depth interval"
            onClick={onToggleIntervalZoom}
          >
            Drag Zoom
          </button>
          <div className="wlv-specified-range-control">
            <button
              ref={specifyRangeButtonRef}
              type="button"
              className={rangeEditorOpen ? 'active' : ''}
              onClick={openSpecifiedRangeEditor}
              title="Specify top and base measured depth range"
            >
              Specify Range
            </button>
            {rangeEditorOpen ? createPortal(
              <div
                ref={specifyRangePopoverRef}
                className="wlv-specified-range-popover wlv-specified-range-popover-portal"
                role="dialog"
                aria-label="Specify drag zoom"
                style={{ top: rangePopoverPosition.top, left: rangePopoverPosition.left }}
              >
                <label>
                  <span>Top MD</span>
                  <input
                    autoFocus
                    value={rangeTopValue}
                    onChange={(event) => setRangeTopValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') applySpecifiedRange();
                      if (event.key === 'Escape') setRangeEditorOpen(false);
                    }}
                  />
                </label>
                <label>
                  <span>Base MD</span>
                  <input
                    value={rangeBaseValue}
                    onChange={(event) => setRangeBaseValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') applySpecifiedRange();
                      if (event.key === 'Escape') setRangeEditorOpen(false);
                    }}
                  />
                </label>
                <div className="wlv-specified-range-actions">
                  <button type="button" onClick={applySpecifiedRange}>Apply</button>
                  <button type="button" onClick={() => setRangeEditorOpen(false)}>Cancel</button>
                </div>
              </div>,
              document.body,
            ) : null}
          </div>
          <button type="button" onClick={onPreviousView}>Prev</button>
          <button type="button" onClick={onFitDepth}>Full</button>
          <button type="button" onClick={onResetView}>Reset</button>
          {viewDepthReadoutEnabled ? (
            <strong className="wlv-depth-readout" title={`Full range ${depthRangeLabel(fullDepthRange)}`}>
              View: {depthRangeLabel(viewDepthRange)}
            </strong>
          ) : null}
          <input
            className="wlv-go-to-depth-input"
            aria-label="Go to depth"
            value={goToDepthValue}
            placeholder="Go to MD"
            onChange={(event) => onGoToDepthValueChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onGoToDepth();
            }}
          />
          <button
            type="button"
            className={`wlv-go-to-depth-button ${goToDepthValue.trim() ? 'ready' : ''}`}
            onClick={onGoToDepth}
            title="Go to entered measured depth"
            aria-label="Go to entered measured depth"
          >
            ✓
          </button>
        </div>
      </div>

      <div className="wlv-toolbar-spacer" />

      <div className="wlv-toolbar-group wlv-toolbar-group-backdrop wlv-toolbar-icon-only">
        <div className="wlv-toolbar-actions">
          <button
            type="button"
            className="wlv-backdrop-toggle"
            onClick={() => onTrackBackdropModeChange(trackBackdropMode === 'light' ? 'dark' : 'light')}
            aria-pressed={trackBackdropMode === 'dark'}
            title={trackBackdropMode === 'light' ? 'Switch to dark backdrop' : 'Switch to light backdrop'}
            aria-label={trackBackdropMode === 'light' ? 'Switch to dark backdrop' : 'Switch to light backdrop'}
          >
            ◐
          </button>
        </div>
      </div>
    </div>
  );
}

function CurveHeaderStack({
  track,
  selectedAssignmentId,
  openMenuAssignmentId,
  onSelectCurve,
  onReorderCurve,
  onMoveCurveToTrack,
  onOpenCurveMenu,
  onCloseCurveMenu,
  onRemoveCurveFromTrack,
}: {
  track: CurveTrack;
  selectedAssignmentId: string | null;
  openMenuAssignmentId: string | null;
  onSelectCurve: (trackId: string, assignmentId: string) => void;
  onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
  onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
  onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
  onCloseCurveMenu: () => void;
  onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
}) {
  const ordered = orderedCurves(track);

  return (
    <div className="wlv-curve-header-stack">
      {ordered.map((assignment, index) => {
        const curve = curveById(curveCatalog, assignment.curveId);
        return (
          <div
            key={assignment.assignmentId}
            role="button"
            tabIndex={0}
            className={`wlv-curve-header ${selectedAssignmentId === assignment.assignmentId ? 'selected' : ''}`}
            draggable
            onClick={(event) => {
              event.stopPropagation();
              onSelectCurve(track.trackId, assignment.assignmentId);
              if (openMenuAssignmentId === assignment.assignmentId) {
                onCloseCurveMenu();
              }
            }}
            onDoubleClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onSelectCurve(track.trackId, assignment.assignmentId);
              onOpenCurveMenu(track.trackId, assignment.assignmentId);
            }}
            onDragStart={(event) => {
              event.dataTransfer.setData(
                'application/json',
                serialiseCurveDrag({
                  dragType: 'curve',
                  curveId: assignment.curveId,
                  fromTrackId: track.trackId,
                  assignmentId: assignment.assignmentId,
                }),
              );
              event.dataTransfer.effectAllowed = 'move';
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              event.stopPropagation();
              const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
              if (!payload) return;
              if (payload.fromTrackId === track.trackId && payload.assignmentId) {
                onReorderCurve(track.trackId, payload.assignmentId, index);
              } else {
                onMoveCurveToTrack(payload, track.trackId, index);
              }
            }}
          >
            <span className="wlv-curve-color" style={{ background: assignment.color }} />
            <strong>{curve.mnemonic}</strong>
            <span>{assignment.scaleMin}—{assignment.scaleMax}</span>
            <em>{curve.unit}</em>
            {openMenuAssignmentId === assignment.assignmentId && (
              <div
                className="curve-header-action-menu"
                role="menu"
                onClick={(event) => event.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => {
                    onReorderCurve(track.trackId, assignment.assignmentId, 0);
                    onCloseCurveMenu();
                  }}
                >
                  Move to Front
                </button>
                <button
                  type="button"
                  disabled={index <= 0}
                  onClick={() => {
                    onReorderCurve(track.trackId, assignment.assignmentId, Math.max(0, index - 1));
                    onCloseCurveMenu();
                  }}
                >
                  Move Up
                </button>
                <button
                  type="button"
                  disabled={index >= ordered.length - 1}
                  onClick={() => {
                    onReorderCurve(track.trackId, assignment.assignmentId, Math.min(ordered.length - 1, index + 1));
                    onCloseCurveMenu();
                  }}
                >
                  Move Down
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onReorderCurve(track.trackId, assignment.assignmentId, ordered.length - 1);
                    onCloseCurveMenu();
                  }}
                >
                  Send to Back
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onSelectCurve(track.trackId, assignment.assignmentId);
                    onCloseCurveMenu();
                  }}
                >
                  Edit Style / Range / Fill
                </button>
                <div className="curve-menu-divider" />
                <button
                  type="button"
                  className="danger"
                  onClick={() => {
                    onRemoveCurveFromTrack(track.trackId, assignment.assignmentId);
                    onCloseCurveMenu();
                  }}
                >
                  Remove from Track
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DepthTrackView({
  track,
  depthTicks,
  viewDepthRange,
  trackBodyHeightPx,
}: {
  track: DepthTrack;
  depthTicks: number[];
  viewDepthRange: DepthViewRange;
  trackBodyHeightPx: number;
}) {
  return (
    <div className="wlv-depth-track-body">
      {depthTicks.map((depth) => {
        const y = depthToY(depth, viewDepthRange, trackBodyHeightPx);
        return (
          <div
            key={`${track.trackId}-${depth}`}
            className="wlv-depth-tick"
            style={{ top: y }}
          >
            <span>{depth}</span>
          </div>
        );
      })}
    </div>
  );
}


function LithologyTrackView({
  track,
  viewDepthRange,
  trackBodyHeightPx,
}: {
  track: LithologyTrack;
  viewDepthRange: DepthViewRange;
  trackBodyHeightPx: number;
}) {
  const visibleIntervals = lithologyIntervals21_31.filter((interval) => (
    interval.baseFt >= viewDepthRange.min && interval.topFt <= viewDepthRange.max
  ));

  return (
    <div className="wlv-lithology-track-body" aria-label={`${track.title} intervals for ${track.wellName}`}>
      {visibleIntervals.map((interval) => {
        const clippedTop = Math.max(interval.topFt, viewDepthRange.min);
        const clippedBase = Math.min(interval.baseFt, viewDepthRange.max);
        const top = depthToY(clippedTop, viewDepthRange, trackBodyHeightPx);
        const base = depthToY(clippedBase, viewDepthRange, trackBodyHeightPx);
        const height = Math.max(2, base - top);

        const showCode = height >= 16;
        const showName = height >= 40;
        const showTopDepth = height >= 26 && clippedTop === interval.topFt;
        const showBaseDepth = height >= 34 && clippedBase === interval.baseFt;

        return (
          <div
            key={interval.intervalId}
            className={`wlv-lithology-interval lith-${interval.unit.toLowerCase()}`}
            style={{
              top,
              height,
              backgroundColor: interval.color,
              backgroundImage: lithologyPattern(interval.unit),
            }}
            title={`${interval.unit}: ${interval.unitName} (${interval.topFt}–${interval.baseFt} ft MD)`}
          >
            {showTopDepth && <div className="wlv-lithology-depth-label top">{interval.topFt.toFixed(0)}</div>}
            <div className="wlv-lithology-interval-content">
              {showCode && <strong>{interval.unit}</strong>}
              {showName && <span>{interval.unitName}</span>}
            </div>
            {showBaseDepth && <div className="wlv-lithology-depth-label base">{interval.baseFt.toFixed(0)}</div>}
          </div>
        );
      })}
    </div>
  );
}

function CurveTrackView({
  track,
  depthTicks,
  viewDepthRange,
  trackBodyHeightPx,
}: {
  track: CurveTrack;
  depthTicks: number[];
  viewDepthRange: DepthViewRange;
  trackBodyHeightPx: number;
}) {
  const ordered = orderedCurves(track);
  const backToFront = [...ordered].sort((a, b) => {
    const priorityDelta = curvePriorityWeight(a) - curvePriorityWeight(b);
    if (priorityDelta !== 0) return priorityDelta;
    return b.stackIndex - a.stackIndex;
  });
  const lattice = resolveTrackLattice(track, curveCatalog);
  const trackWidth = clampCurveTrackWidth(track.widthPx);

  return (
    <svg className={`wlv-curve-track-svg ${lattice.lattice}`} viewBox={`0 0 ${trackWidth} ${trackBodyHeightPx}`} preserveAspectRatio="none">
      <defs>
        <pattern id={`infill-hatch-${track.trackId}`} width="8" height="8" patternUnits="userSpaceOnUse">
          <path d="M -2 8 L 8 -2 M 0 10 L 10 0" stroke="currentColor" strokeWidth="1" opacity="0.55" />
        </pattern>
        <pattern id={`infill-dots-${track.trackId}`} width="8" height="8" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.2" fill="currentColor" opacity="0.5" />
        </pattern>
      </defs>
      {lattice.lattice === 'logarithmic' ? (
        <>
          <rect className="wlv-log-grid-background" x="0" y="0" width={trackWidth} height={trackBodyHeightPx} />
          {renderLogarithmicGrid(track, trackWidth, trackBodyHeightPx)}
        </>
      ) : (
        <>
          <defs>
            <pattern id={`grid-${track.trackId}`} width="24" height="30" patternUnits="userSpaceOnUse">
              <path d="M 24 0 L 0 0 0 30" fill="none" stroke="#e0e6ed" strokeWidth="1" />
            </pattern>
          </defs>
          <rect x="0" y="0" width={trackWidth} height={trackBodyHeightPx} fill={`url(#grid-${track.trackId})`} />
        </>
      )}
      {depthTicks.map((depth) => {
        const y = depthToY(depth, viewDepthRange, trackBodyHeightPx);
        return <line key={depth} x1="0" x2={trackWidth} y1={y} y2={y} stroke="#aeb8c5" strokeWidth="1" />;
      })}
      {backToFront.map((assignment, index) => {
        const curve = curveById(curveCatalog, assignment.curveId);
        const points = curveRenderPoints(curve, assignment, index, viewDepthRange, lattice.lattice, trackWidth, trackBodyHeightPx);
        const path = pathFromCurvePoints(points);
        const pairedAssignment = assignment.pairedCurveId
          ? ordered.find((candidate) => candidate.assignmentId === assignment.pairedCurveId)
          : null;
        const pairedCurve = pairedAssignment ? curveById(curveCatalog, pairedAssignment.curveId) : null;
        const pairedPoints = pairedAssignment && pairedCurve
          ? curveRenderPoints(pairedCurve, pairedAssignment, index, viewDepthRange, lattice.lattice, trackWidth, trackBodyHeightPx)
          : [];
        const anchorX = fillAnchorForAssignment(assignment, trackWidth);
        const baseFillPath = assignment.fillSide === 'between' && pairedPoints.length > 0
          ? polygonBetweenCurves(points, pairedPoints)
          : polygonToAnchor(points, anchorX);
        const intervalInfillActive = assignment.infillSource === 'interval-column'
          && assignment.infillIntervalColumn === 'lithology'
          && assignment.fillSide !== 'none';
        const visibleLithologyIntervals = intervalInfillActive
          ? lithologyIntervals21_31.filter((interval) => interval.baseFt >= viewDepthRange.min && interval.topFt <= viewDepthRange.max)
          : [];

        return (
          <g key={assignment.assignmentId}>
            {assignment.fillSide !== 'none' && baseFillPath && !intervalInfillActive ? (
              <path
                d={baseFillPath}
                fill={svgFillForAssignment(assignment, null, track.trackId)}
                stroke="none"
                opacity={fillOpacityForAssignment(assignment)}
              />
            ) : null}
            {intervalInfillActive ? visibleLithologyIntervals.map((interval) => {
              const clippedTop = Math.max(interval.topFt, viewDepthRange.min);
              const clippedBase = Math.min(interval.baseFt, viewDepthRange.max);
              const topY = depthToY(clippedTop, viewDepthRange, trackBodyHeightPx);
              const baseY = depthToY(clippedBase, viewDepthRange, trackBodyHeightPx);
              return (
                <g key={`${assignment.assignmentId}-${interval.intervalId}`} clipPath={`url(#interval-clip-${track.trackId}-${assignment.assignmentId}-${interval.intervalId})`}>
                  <defs>
                    <clipPath id={`interval-clip-${track.trackId}-${assignment.assignmentId}-${interval.intervalId}`}>
                      <rect x="0" y={topY} width={trackWidth} height={Math.max(1, baseY - topY)} />
                    </clipPath>
                  </defs>
                  <path
                    d={baseFillPath}
                    fill={svgFillForAssignment(assignment, interval.color, track.trackId)}
                    stroke="none"
                    opacity={fillOpacityForAssignment(assignment)}
                  />
                </g>
              );
            }) : null}
            {(assignment.lineVisible ?? true) && path ? (
              <path
                d={path}
                fill="none"
                stroke={assignment.color}
                strokeWidth={assignment.lineWidth}
                strokeDasharray={assignment.lineStyle === 'dash' ? '8 5' : assignment.lineStyle === 'dot' ? '2 6' : undefined}
                vectorEffect="non-scaling-stroke"
                opacity={lineOpacityForAssignment(assignment)}
              />
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

function TrackView({
  track,
  sharedHeaderHeightPx,
  selected,
  selectedAssignmentId,
  openCurveMenu,
  depthTicks,
  viewDepthRange,
  onSelectTrack,
  onSelectCurve,
  onReorderCurve,
  onMoveCurveToTrack,
  onOpenCurveMenu,
  onCloseCurveMenu,
  onRemoveCurveFromTrack,
  onStartCurveTrackResize,
  resizingTrackId,
  trackBodyHeightPx,
}: {
  track: WellLogTrack;
  sharedHeaderHeightPx: number;
  selected: boolean;
  selectedAssignmentId: string | null;
  openCurveMenu: { trackId: string; assignmentId: string } | null;
  depthTicks: number[];
  viewDepthRange: DepthViewRange;
  onSelectTrack: (trackId: string) => void;
  onSelectCurve: (trackId: string, assignmentId: string) => void;
  onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
  onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
  onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
  onCloseCurveMenu: () => void;
  onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
  onStartCurveTrackResize: (trackId: string, startX: number, startWidth: number) => void;
  resizingTrackId: string | null;
  trackBodyHeightPx: number;
}) {
  const widthPx = track.trackType === 'curve' ? clampCurveTrackWidth(track.widthPx) : track.widthPx;
  const width = `${widthPx}px`;
  const isCurveTrack = track.trackType === 'curve';
  const lattice = isCurveTrack ? resolveTrackLattice(track, curveCatalog) : null;
  return (
    <section
      className={`wlv-track ${track.trackType} ${selected ? 'selected' : ''} ${resizingTrackId === track.trackId ? 'resizing' : ''}`}
      style={{ width, minWidth: width, height: `${sharedHeaderHeightPx + trackBodyHeightPx}px` }}
      onMouseDownCapture={(event) => {
        if (track.trackType !== 'curve' || !event.shiftKey || event.button !== 0) return;
        const target = event.target;
        if (!(target instanceof Element) || !target.closest('.wlv-track-body')) return;
        event.preventDefault();
        event.stopPropagation();
        onCloseCurveMenu();
        onSelectTrack(track.trackId);
        onStartCurveTrackResize(track.trackId, event.clientX, widthPx);
      }}
      onClick={() => {
        onCloseCurveMenu();
        onSelectTrack(track.trackId);
      }}
      onDragOver={(event) => {
        if (track.trackType === 'curve') event.preventDefault();
      }}
      onDrop={(event) => {
        if (track.trackType !== 'curve') return;
        event.preventDefault();
        const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
        if (payload) onMoveCurveToTrack(payload, track.trackId);
      }}
    >
      <header
        className="wlv-track-header"
        style={{ height: `${sharedHeaderHeightPx}px`, minHeight: `${sharedHeaderHeightPx}px`, flexBasis: `${sharedHeaderHeightPx}px` }}
      >
        <div className="wlv-track-title-row">
          <strong>{displayTitleForTrack(track, curveCatalog)}</strong>
          <span>T{track.trackIndex + 1}</span>
        </div>
        {track.trackType === 'depth' && (
          <div className="wlv-depth-header">{track.depthBasis} · {track.unit}</div>
        )}
        {track.trackType === 'lithology' && (
          <div className="wlv-lithology-header">{lithologySource.name} · {track.wellName}</div>
        )}
        {track.trackType === 'curve' && (
          <>
            <div className="wlv-lattice-badge">
              {lattice?.lattice} · {lattice?.source === 'user_override' ? 'override' : `front ${lattice?.frontCurve?.mnemonic ?? 'none'}`} · {widthPx}px
            </div>
            <CurveHeaderStack
              track={track}
              selectedAssignmentId={selectedAssignmentId}
              openMenuAssignmentId={openCurveMenu?.trackId === track.trackId ? openCurveMenu?.assignmentId ?? null : null}
              onSelectCurve={onSelectCurve}
              onReorderCurve={onReorderCurve}
              onMoveCurveToTrack={onMoveCurveToTrack}
              onOpenCurveMenu={onOpenCurveMenu}
              onCloseCurveMenu={onCloseCurveMenu}
              onRemoveCurveFromTrack={onRemoveCurveFromTrack}
            />
          </>
        )}
      </header>
      <div className="wlv-track-body" style={{ height: `${trackBodyHeightPx}px`, minHeight: `${trackBodyHeightPx}px`, flexBasis: `${trackBodyHeightPx}px` }}>
        {track.trackType === 'depth' ? <DepthTrackView track={track} depthTicks={depthTicks} viewDepthRange={viewDepthRange} trackBodyHeightPx={trackBodyHeightPx} /> : null}
        {track.trackType === 'lithology' ? <LithologyTrackView track={track} viewDepthRange={viewDepthRange} trackBodyHeightPx={trackBodyHeightPx} /> : null}
        {track.trackType === 'curve' ? <CurveTrackView track={track} depthTicks={depthTicks} viewDepthRange={viewDepthRange} trackBodyHeightPx={trackBodyHeightPx} /> : null}
      </div>
    </section>
  );
}

function TrackCanvas({
  tracks,
  selection,
  openCurveMenu,
  depthTicks,
  viewDepthRange,
  goToDepthMarker,
  intervalZoomActive,
  intervalSelection,
  dragPanActive,
  onSelectTrack,
  onSelectCurve,
  onReorderCurve,
  onMoveCurveToTrack,
  onOpenCurveMenu,
  onCloseCurveMenu,
  onRemoveCurveFromTrack,
  onStartIntervalSelection,
  onUpdateIntervalSelection,
  onArmIntervalSelection,
  onCompleteIntervalSelection,
  onStartDragPan,
  onUpdateDragPan,
  onEndDragPan,
  onStartCurveTrackResize,
  resizingTrackId,
}: {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  openCurveMenu: { trackId: string; assignmentId: string } | null;
  depthTicks: number[];
  viewDepthRange: DepthViewRange;
  goToDepthMarker: number | null;
  intervalZoomActive: boolean;
  intervalSelection: IntervalSelectionState | null;
  dragPanActive: boolean;
  onSelectTrack: (trackId: string) => void;
  onSelectCurve: (trackId: string, assignmentId: string) => void;
  onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
  onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
  onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
  onCloseCurveMenu: () => void;
  onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
  onStartIntervalSelection: (depth: number, y: number) => void;
  onUpdateIntervalSelection: (depth: number, y: number) => void;
  onArmIntervalSelection: (depth: number, y: number) => void;
  onCompleteIntervalSelection: (depth: number, y: number) => void;
  onStartDragPan: (startY: number) => void;
  onUpdateDragPan: (currentY: number, canvasHeight: number) => void;
  onEndDragPan: () => void;
  onStartCurveTrackResize: (trackId: string, startX: number, startWidth: number) => void;
  resizingTrackId: string | null;
}) {
  const canvasRef = useRef<HTMLElement | null>(null);
  const orderedTracks = sortTracks(tracks);
  const sharedHeaderHeight = sharedTrackHeaderHeightPx(orderedTracks);
  const { setContainerRef, trackBodyHeightPx } = useTrackBodyGeometry({
    headerHeightPx: sharedHeaderHeight,
    fallbackBodyHeightPx: TRACK_BODY_HEIGHT_PX,
    minBodyHeightPx: TRACK_BODY_MIN_HEIGHT_PX,
    maxBodyHeightPx: TRACK_BODY_MAX_HEIGHT_PX,
    footerClearancePx: TRACK_FOOTER_CLEARANCE_PX,
    stripPaddingPx: TRACK_STRIP_PADDING_PX,
  });

  const canvasRectFromCanvas = () => canvasRef.current?.getBoundingClientRect() ?? null;

  const bodyRectFromCanvas = () => {
    return canvasRef.current?.querySelector('.wlv-track-body')?.getBoundingClientRect() ?? null;
  };

  const sharedBodyTopOffset = () => {
    const canvasRect = canvasRectFromCanvas();
    const bodyRect = bodyRectFromCanvas();
    if (canvasRect && bodyRect) return bodyRect.top - canvasRect.top;
    return TRACK_STRIP_PADDING_PX + sharedHeaderHeight;
  };

  const pointFromClientY = (clientY: number) => {
    const rect = bodyRectFromCanvas() ?? canvasRectFromCanvas();
    const height = rect?.height ?? trackBodyHeightPx;
    const top = rect?.top ?? 0;
    const y = clampValue(clientY - top, 0, height);
    const depth = yToDepth(y, viewDepthRange, height);
    return { depth, y, height };
  };

  const pointFromEvent = (event: ReactMouseEvent<HTMLElement>) => {
    return pointFromClientY(event.clientY);
  };

  const shouldStartDragPan = (event: ReactMouseEvent<HTMLElement>) => {
    if (intervalZoomActive || event.shiftKey || event.button !== 0) return false;
    const target = event.target;
    if (!(target instanceof Element)) return false;
    return Boolean(target.closest('.wlv-track-body'));
  };

  useEffect(() => {
    if (!dragPanActive) return undefined;

    const handleDocumentMouseMove = (event: MouseEvent) => {
      event.preventDefault();
      const point = pointFromClientY(event.clientY);
      onUpdateDragPan(point.y, point.height);
    };

    const handleDocumentMouseUp = (event: MouseEvent) => {
      event.preventDefault();
      onEndDragPan();
    };

    document.addEventListener('mousemove', handleDocumentMouseMove);
    document.addEventListener('mouseup', handleDocumentMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleDocumentMouseMove);
      document.removeEventListener('mouseup', handleDocumentMouseUp);
    };
  }, [dragPanActive, onEndDragPan, onUpdateDragPan, viewDepthRange]);

  const intervalBand = intervalSelection
    ? {
        top: Math.min(intervalSelection.startY, intervalSelection.currentY),
        height: Math.max(2, Math.abs(intervalSelection.currentY - intervalSelection.startY)),
        startDepth: Math.min(intervalSelection.startDepth, intervalSelection.currentDepth),
        endDepth: Math.max(intervalSelection.startDepth, intervalSelection.currentDepth),
      }
    : null;

  const bodyTopOffset = sharedBodyTopOffset();

  const sharedGoToMarkerY = typeof goToDepthMarker === 'number'
    && goToDepthMarker >= viewDepthRange.min
    && goToDepthMarker <= viewDepthRange.max
    ? bodyTopOffset + depthToY(goToDepthMarker, viewDepthRange, trackBodyHeightPx)
    : null;

  const sharedDepthGridLines = depthTicks.map((depth) => ({
    depth,
    y: bodyTopOffset + depthToY(depth, viewDepthRange, trackBodyHeightPx),
  }));

  return (
    <main
      ref={(node) => {
        canvasRef.current = node;
        setContainerRef(node);
      }}
      className={`wlv-track-canvas ${intervalZoomActive ? 'interval-zoom-active' : ''} ${dragPanActive ? 'drag-pan-active' : ''} ${resizingTrackId ? 'curve-resize-active' : ''}`}
      onMouseDownCapture={(event) => {
        if (intervalZoomActive) {
          event.preventDefault();
          event.stopPropagation();
          const point = pointFromEvent(event);

          if (intervalSelection && !intervalSelection.dragging) {
            onCompleteIntervalSelection(point.depth, point.y);
            return;
          }

          onStartIntervalSelection(point.depth, point.y);
          return;
        }

        if (!shouldStartDragPan(event)) return;
        event.preventDefault();
        event.stopPropagation();
        const { y } = pointFromEvent(event);
        onStartDragPan(y);
      }}
      onMouseMoveCapture={(event) => {
        if (intervalZoomActive && intervalSelection?.dragging) {
          event.preventDefault();
          event.stopPropagation();
          const point = pointFromEvent(event);
          onUpdateIntervalSelection(point.depth, point.y);
          return;
        }

        // Drag-pan movement is handled by document-level listeners once MB1 drag starts.
      }}
      onMouseUpCapture={(event) => {
        if (intervalZoomActive && intervalSelection?.dragging) {
          event.preventDefault();
          event.stopPropagation();
          const point = pointFromEvent(event);

          if (Math.abs(point.y - intervalSelection.startY) >= 8) {
            onCompleteIntervalSelection(point.depth, point.y);
            return;
          }

          onArmIntervalSelection(point.depth, point.y);
          return;
        }

        // Drag-pan mouseup is handled by document-level listeners once MB1 drag starts.
      }}
    >
      {intervalBand && (
        <div
          className={`wlv-interval-selection-band ${intervalSelection?.dragging ? 'dragging' : 'armed'}`}
          style={{ top: bodyTopOffset + intervalBand.top, height: intervalBand.height }}
        >
          <span>
            {intervalSelection?.dragging
              ? `${Math.round(intervalBand.startDepth)}–${Math.round(intervalBand.endDepth)} m`
              : intervalSelection
                ? `Start ${Math.round(intervalSelection.startDepth)} m — click end depth`
                : 'Click first depth to start interval'}
          </span>
        </div>
      )}
      <div className="wlv-shared-depth-grid-overlay" aria-hidden="true">
        {sharedDepthGridLines.map(({ depth, y }) => (
          <div key={`shared-grid-${depth}`} className="wlv-shared-depth-grid-line" style={{ top: y }} />
        ))}
      </div>
      {sharedGoToMarkerY !== null && (
        <div
          className="wlv-shared-go-to-depth-marker"
          style={{ top: sharedGoToMarkerY }}
          aria-hidden="true"
        >
          <span>{Math.round(goToDepthMarker as number)} m</span>
        </div>
      )}
      <div className="wlv-track-strip">
        {orderedTracks.map((track) => (
          <TrackView
            key={track.trackId}
            track={track}
            sharedHeaderHeightPx={sharedHeaderHeight}
            selected={selection.kind === 'track' && selection.trackId === track.trackId || selection.kind === 'curve' && selection.trackId === track.trackId}
            selectedAssignmentId={selection.kind === 'curve' && selection.trackId === track.trackId ? selection.assignmentId : null}
            openCurveMenu={openCurveMenu}
            depthTicks={depthTicks}
            viewDepthRange={viewDepthRange}
            onSelectTrack={onSelectTrack}
            onSelectCurve={onSelectCurve}
            onReorderCurve={onReorderCurve}
            onMoveCurveToTrack={onMoveCurveToTrack}
            onOpenCurveMenu={onOpenCurveMenu}
            onCloseCurveMenu={onCloseCurveMenu}
            onRemoveCurveFromTrack={onRemoveCurveFromTrack}
            onStartCurveTrackResize={onStartCurveTrackResize}
            resizingTrackId={resizingTrackId}
            trackBodyHeightPx={trackBodyHeightPx}
          />
        ))}
      </div>
    </main>
  );
}

function TrackProperties({
  track,
  updateTrack,
}: {
  track: WellLogTrack;
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
}) {
  if (track.trackType === 'depth') {
    return (
      <div className="wlv-property-section">
        <h3>Selected Track</h3>
        <label>
          Track title
          <input value={track.title} onChange={(event) => updateTrack(track.trackId, { title: event.target.value })} />
        </label>
        <label>
          Depth type
          <select
            value={track.depthBasis}
            onChange={(event) => updateTrack(track.trackId, { depthBasis: event.target.value as DepthBasis })}
          >
            <option value="MD">MD</option>
            <option value="TVD">TVD</option>
            <option value="TVDSS">TVDSS</option>
          </select>
        </label>
        <div className="wlv-property-note">
          Depth track width is fixed in this prototype. Curve tracks can be resized with Width − / Width + or Shift + MB1 drag.
        </div>
      </div>
    );
  }

  if (track.trackType === 'curve') {
    const lattice = resolveTrackLattice(track, curveCatalog);
    return (
      <div className="wlv-property-section">
        <h3>Selected Track</h3>
        <label>
          Track title
          <input value={track.title} onChange={(event) => updateTrack(track.trackId, { title: event.target.value })} />
        </label>
        <label>
          Lattice
          <select
            value={lattice.lattice}
            onChange={(event) => updateTrack(track.trackId, {
              lattice: event.target.value as CurveTrack['lattice'],
              latticeOverride: true,
              latticeSource: 'user_override',
            })}
          >
            <option value="linear">Linear</option>
            <option value="logarithmic">Logarithmic</option>
          </select>
        </label>
        <button
          type="button"
          disabled={!track.latticeOverride}
          onClick={() => updateTrack(track.trackId, { latticeOverride: false, latticeSource: 'front_curve_default' })}
        >
          Reset lattice to front curve
        </button>
        <label>
          Scale mode
          <select
            value={track.scaleMode}
            onChange={(event) => updateTrack(track.trackId, { scaleMode: event.target.value as ScaleMode })}
          >
            <option value="shared">Shared</option>
            <option value="per_curve">Per curve</option>
            <option value="dual">Dual</option>
            <option value="normalized">Normalized</option>
          </select>
        </label>
        <label>
          Width
          <input type="number" min={CURVE_TRACK_MIN_WIDTH} max={CURVE_TRACK_MAX_WIDTH} value={track.widthPx} onChange={(event) => updateTrack(track.trackId, { widthPx: clampCurveTrackWidth(Number(event.target.value)) })} />
        </label>
        <div className="wlv-property-note">
          Top curve header controls default lattice and front-most overpost order.
        </div>
      </div>
    );
  }

  return <div className="wlv-property-section">Reserved track type.</div>;
}

function CurveProperties({
  track,
  assignment,
  updateCurveAssignment,
}: {
  track: CurveTrack;
  assignment: CurveAssignment;
  updateCurveAssignment: (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => void;
}) {
  const curve = curveById(curveCatalog, assignment.curveId);

  return (
    <div className="wlv-property-section">
      <h3>Selected Curve</h3>
      <div className="wlv-selected-curve-title">
        <span className="wlv-curve-color" style={{ background: assignment.color }} />
        <strong>{curve.mnemonic}</strong>
        <span>{curve.description}</span>
      </div>
      <label>
        Range min
        <input type="number" value={assignment.scaleMin} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { scaleMin: Number(event.target.value) })} />
      </label>
      <label>
        Range max
        <input type="number" value={assignment.scaleMax} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { scaleMax: Number(event.target.value) })} />
      </label>
      <label>
        Color
        <input type="color" value={assignment.color} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { color: event.target.value })} />
      </label>
      <label>
        Line style
        <select
          value={assignment.lineStyle}
          onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { lineStyle: event.target.value as LineStyle })}
        >
          <option value="solid">Solid</option>
          <option value="dash">Dash</option>
          <option value="dot">Dot</option>
        </select>
      </label>
      <label>
        Fill
        <select
          value={assignment.fillSide}
          onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { fillSide: event.target.value as FillSide })}
        >
          <option value="none">None</option>
          <option value="left">Left</option>
          <option value="right">Right</option>
          <option value="between">Between</option>
        </select>
      </label>
      <label>
        Fill color
        <input type="color" value="#c7e7c8" onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { fillColor: event.target.value })} />
      </label>
      <div className="wlv-property-note">
        Curve headers can be dragged between tracks. Header stack order controls overpost order.
      </div>
    </div>
  );
}

function RightPanel({
  tracks,
  selection,
  updateTrack,
  updateCurveAssignment,
}: {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
  updateCurveAssignment: (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => void;
}) {
  const selectedTrack = tracks.find((track) => track.trackId === selection.trackId) ?? tracks[0];
  const selectedCurve = selectedTrack?.trackType === 'curve' && selection.kind === 'curve'
    ? selectedTrack.curves.find((assignment) => assignment.assignmentId === selection.assignmentId) ?? null
    : null;

  return (
    <aside className="wlv-right-panel">
      <div className="wlv-panel-heading">
        <h2>Properties</h2>
        <span>{selection.kind}</span>
      </div>
      {selectedTrack && selectedCurve && selectedTrack.trackType === 'curve' ? (
        <CurveProperties track={selectedTrack} assignment={selectedCurve} updateCurveAssignment={updateCurveAssignment} />
      ) : selectedTrack ? (
        <TrackProperties track={selectedTrack} updateTrack={updateTrack} />
      ) : null}
      <div className="wlv-property-section well-header">
        <h3>Well Header</h3>
        <dl>
          <dt>Well</dt><dd>{wellHeader.wellName}</dd>
          <dt>Wellbore</dt><dd>{wellHeader.wellboreName}</dd>
          <dt>Field</dt><dd>{wellHeader.field}</dd>
          <dt>Operator</dt><dd>{wellHeader.operator}</dd>
          <dt>Country</dt><dd>{wellHeader.country}</dd>
          <dt>KB</dt><dd>{wellHeader.kb}</dd>
          <dt>GL</dt><dd>{wellHeader.gl}</dd>
          <dt>Log start</dt><dd>{wellHeader.logStart}</dd>
          <dt>Log end</dt><dd>{wellHeader.logEnd}</dd>
          <dt>Source file</dt><dd>{wellHeader.sourceFile}</dd>
          <dt>TVD</dt><dd>{wellHeader.tvdStatus}</dd>
          <dt>MSI</dt><dd>{wellHeader.msiIdentity}</dd>
        </dl>
      </div>
    </aside>
  );
}

export function TrackLayoutPrototype() {
  const [activeView, setActiveView] = useState<DemoNavView>('log-viewer');
  const [managedViewerWellId, setManagedViewerWellId] = useState<string | null>(null);
  const [, setViewerPackageLoad] = useState<BackendViewerPackageLoadResult | null>(null);
  const [wdvPackageState, setWdvPackageState] = useState<WdvPackageState>(() => emptyWdvPackageState());

  // WLV-WDV-REBUILD-1: WMDP load creates WDV availability only.
  // It must not auto-populate visible well-log tracks.
  useEffect(() => {
    if (activeView !== 'log-viewer') return;
    if (!managedViewerWellId) {
      setViewerPackageLoad({
        source: 'prototype_fallback',
        package: null,
        warning: 'No managed well is currently loaded to the Well Data Viewer',
      });
      setWdvPackageState(emptyWdvPackageState());
      return;
    }
    let cancelled = false;
    setWdvPackageState(emptyWdvPackageState());
    void loadBackendViewerPackageWithFallback(managedViewerWellId)
      .then((result) => {
        if (!cancelled) {
          setViewerPackageLoad(result);
          setWdvPackageState(buildWdvPackageState(result.package));
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setViewerPackageLoad({
            source: 'prototype_fallback',
            package: null,
            warning: error instanceof Error ? error.message : 'Viewer package unavailable',
          });
          setWdvPackageState(emptyWdvPackageState());
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeView, managedViewerWellId]);
  const [tracks, setTracks] = useState<WellLogTrack[]>([]);
  const [selection, setSelection] = useState<SelectionRef>({ kind: 'track', trackId: 'track-gr-sp' });
  const [selectedInventoryCurveIds, setSelectedInventoryCurveIds] = useState<string[]>([]);
  const [addTrackCurveSelectionMode, setAddTrackCurveSelectionMode] = useState(false);
  const [pendingAddTrackCurveIds, setPendingAddTrackCurveIds] = useState<string[]>([]);
  const [openCurveMenu, setOpenCurveMenu] = useState<{ trackId: string; assignmentId: string } | null>(null);
  const [viewDepthRange, setViewDepthRange] = useState<DepthViewRange>(DEFAULT_DEPTH_RANGE);
  const appliedBackendDepthDomainKeyRef = useRef<string | null>(null);
  const [, setViewHistory] = useState<DepthViewRange[]>([]);
  const [goToDepthValue, setGoToDepthValue] = useState('');
  const [goToDepthMarker, setGoToDepthMarker] = useState<number | null>(null);
  const [intervalZoomActive, setIntervalZoomActive] = useState(false);
  const [intervalSelection, setIntervalSelection] = useState<IntervalSelectionState | null>(null);
  const [dragPanState, setDragPanState] = useState<DragPanState | null>(null);
  const [trackResizeState, setTrackResizeState] = useState<TrackResizeState | null>(null);
  const [curveInventoryWidthPx, setCurveInventoryWidthPx] = useState(CURVE_INVENTORY_DEFAULT_WIDTH_PX);
  const [curveInventoryCollapsed, setCurveInventoryCollapsed] = useState(false);
  const [curveInventoryResizeState, setCurveInventoryResizeState] = useState<CurveInventoryResizeState | null>(null);
  const wdvSessionHydratedKeyRef = useRef<string | null>(null);
  const wdvSessionSaveTimerRef = useRef<number | null>(null);
  const hasLoadedViewerWell = Boolean(managedViewerWellId);
  const [trackBackdropMode, setTrackBackdropMode] = useState<TrackBackdropMode>('light');
  const [wdvTemplateRecommendations, setWdvTemplateRecommendations] = useState<WdvTemplateRecommendationItem[]>([]);
  const [wdvTemplateRecommendationsLoading, setWdvTemplateRecommendationsLoading] = useState(false);
  const [wdvTemplateRecommendationsError, setWdvTemplateRecommendationsError] = useState<string | null>(null);
  const [selectedWdvTemplateKey, setSelectedWdvTemplateKey] = useState('');
  const [wdvTemplateModalOpen, setWdvTemplateModalOpen] = useState(false);

  const activeFullDepthRange = useMemo(
    () => wdvPackageState.depthRange ?? FULL_DEPTH_RANGE,
    [wdvPackageState.depthRange],
  );
  const activeFullDepthRangeKey = `${activeFullDepthRange.min}:${activeFullDepthRange.max}`;
  const hasBackendDepthRange = Boolean(wdvPackageState.depthRange);
  const activeDefaultDepthRange = useMemo(
    () => (wdvPackageState.depthRange ? activeFullDepthRange : clampDepthRange(DEFAULT_DEPTH_RANGE, activeFullDepthRange)),
    [activeFullDepthRange, wdvPackageState.depthRange],
  );


  const visibleDepthTicks = useMemo(() => makeDepthTicks(viewDepthRange), [viewDepthRange]);

  useEffect(() => {
    setViewDepthRange((current) => {
      const clipped = clampDepthRange(current, activeFullDepthRange);

      if (hasBackendDepthRange && appliedBackendDepthDomainKeyRef.current !== activeFullDepthRangeKey) {
        appliedBackendDepthDomainKeyRef.current = activeFullDepthRangeKey;
        return { ...activeFullDepthRange };
      }

      appliedBackendDepthDomainKeyRef.current = activeFullDepthRangeKey;
      return clipped;
    });
  }, [activeFullDepthRange, activeFullDepthRangeKey, hasBackendDepthRange]);

  useEffect(() => {
    if (!trackResizeState) return undefined;

    const handleMouseMove = (event: MouseEvent) => {
      const delta = event.clientX - trackResizeState.startX;
      const nextWidth = clampCurveTrackWidth(trackResizeState.startWidth + delta);
      setTracks((current) => current.map((track) => (
        track.trackId === trackResizeState.trackId && track.trackType === 'curve'
          ? { ...track, widthPx: nextWidth }
          : track
      )));
    };

    const handleMouseUp = () => {
      setTrackResizeState(null);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [trackResizeState]);

  useEffect(() => {
    if (!curveInventoryResizeState) return undefined;

    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const handleMouseMove = (event: MouseEvent) => {
      const delta = event.clientX - curveInventoryResizeState.startX;
      setCurveInventoryWidthPx(clampCurveInventoryWidth(curveInventoryResizeState.startWidth + delta));
    };

    const handleMouseUp = () => {
      setCurveInventoryResizeState(null);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    };
  }, [curveInventoryResizeState]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setIntervalZoomActive(false);
      setIntervalSelection(null);
      setDragPanState(null);
      setTrackResizeState(null);
      setCurveInventoryResizeState(null);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const selectedTrack = tracks.find((track) => track.trackId === selection.trackId) ?? null;
  const orderedTracks = useMemo(() => sortTracks(tracks), [tracks]);
  const selectedTrackIndex = selectedTrack
    ? orderedTracks.findIndex((track) => track.trackId === selectedTrack.trackId)
    : -1;
  const canMoveSelectedTrackLeft = selectedTrackIndex > 0;
  const canMoveSelectedTrackRight = selectedTrackIndex >= 0 && selectedTrackIndex < orderedTracks.length - 1;
  const selectedCurveTrack = selectedTrack?.trackType === 'curve' ? selectedTrack : null;
  const canAdjustSelectedCurveTrackWidthDown = Boolean(selectedCurveTrack && selectedCurveTrack.widthPx > CURVE_TRACK_MIN_WIDTH);
  const canAdjustSelectedCurveTrackWidthUp = Boolean(selectedCurveTrack && selectedCurveTrack.widthPx < CURVE_TRACK_MAX_WIDTH);

  const activeViewerCurves = useMemo(() => wdvPackageState.availableCurves, [wdvPackageState]);
  const activeCurveCatalog = useMemo(() => {
    // WLV-WDV-CURVE-ASSIGNMENT-IDENTITY-1:
    // Loaded backend curve products must be registered in the same catalog
    // used by track rendering/properties code before any assignment is made.
    // This preserves duplicate mnemonics as distinct product-backed curveIds.
    const mutableCatalog = curveCatalog as CurveCatalogItem[];
    const existingCurveIds = new Set(mutableCatalog.map((curve) => curve.curveId));

    activeViewerCurves.forEach((curve) => {
      if (!curve.curveId || existingCurveIds.has(curve.curveId)) return;
      mutableCatalog.push(curve);
      existingCurveIds.add(curve.curveId);
    });

    return [...mutableCatalog];
  }, [activeViewerCurves]);
  const wdvSessionKey = useMemo(() => {
    if (!managedViewerWellId) return null;
    const productKey = wdvPackageState.loadedCurveItems.map((item) => item.productId || item.curveId).join('|');
    return `${managedViewerWellId}:${productKey}`;
  }, [managedViewerWellId, wdvPackageState.loadedCurveItems]);

  useEffect(() => {
    let cancelled = false;
    void fetchWlvJson<ManagedInventoryWellRecord[]>('/api/wlv/inventory/wells')
      .then((records) => {
        if (cancelled || managedViewerWellId) return;
        const activeManagedWellId = firstBackendLoadedWell(records);
        if (activeManagedWellId) setManagedViewerWellId(activeManagedWellId);
      })
      .catch(() => {
        // Restore is best-effort; explicit WMDP Load remains the authoritative entry point.
      });
    return () => {
      cancelled = true;
    };
  }, [managedViewerWellId]);

  useEffect(() => {
    if (!managedViewerWellId || !wdvSessionKey || wdvPackageState.loadedCurveItems.length === 0) {
      wdvSessionHydratedKeyRef.current = null;
      return undefined;
    }

    let cancelled = false;
    void fetchWlvJson<WdvSessionLayoutResponse>(`/api/wlv/wdv/sessions/${managedViewerWellId}/layout`)
      .then((session) => {
        if (cancelled) return;
        const restoredTracks = session.state_status === 'active'
          ? frontendTracksFromSession(session, activeCurveCatalog)
          : [];

        if (restoredTracks.length > 0) {
          setTracks(restoredTracks);
          const selectedTrackId = selectedTrackIdFromSession(session);
          const selectedTrackExists = selectedTrackId && restoredTracks.some((track) => track.trackId === selectedTrackId);
          setSelection({ kind: 'track', trackId: selectedTrackExists ? selectedTrackId : restoredTracks[0].trackId });
        }

        wdvSessionHydratedKeyRef.current = wdvSessionKey;
      })
      .catch(() => {
        if (!cancelled) wdvSessionHydratedKeyRef.current = wdvSessionKey;
      });

    return () => {
      cancelled = true;
    };
  }, [activeCurveCatalog, managedViewerWellId, wdvPackageState.loadedCurveItems.length, wdvSessionKey]);

  useEffect(() => {
    if (!managedViewerWellId || !wdvSessionKey || wdvSessionHydratedKeyRef.current !== wdvSessionKey) return undefined;
    if (wdvSessionSaveTimerRef.current !== null) {
      window.clearTimeout(wdvSessionSaveTimerRef.current);
    }

    wdvSessionSaveTimerRef.current = window.setTimeout(() => {
      void fetchWlvJson<WdvSessionLayoutResponse>(`/api/wlv/wdv/sessions/${managedViewerWellId}/layout`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_track_id: selection.kind === 'track' || selection.kind === 'curve' ? selection.trackId : null,
          tracks: sessionTracksFromFrontend(tracks, activeCurveCatalog),
          source: 'frontend_user_layout_update',
        }),
      }).catch(() => {
        // Keep rendering responsive; backend-owned restore will use the last successful session save.
      });
    }, 400);

    return () => {
      if (wdvSessionSaveTimerRef.current !== null) {
        window.clearTimeout(wdvSessionSaveTimerRef.current);
        wdvSessionSaveTimerRef.current = null;
      }
    };
  }, [activeCurveCatalog, managedViewerWellId, selection, tracks, wdvSessionKey]);

  const loadWdvTemplateRecommendations = () => {
    if (!hasLoadedViewerWell || wdvPackageState.loadedCurveItems.length === 0) {
      setWdvTemplateRecommendations([]);
      setWdvTemplateRecommendationsError(null);
      setSelectedWdvTemplateKey('');
      setWdvTemplateModalOpen(false);
      return;
    }

    setWdvTemplateRecommendationsLoading(true);
    setWdvTemplateRecommendationsError(null);
    void evaluateWdvTemplateRecommendations(wdvPackageState.loadedCurveItems)
      .then((result) => {
        const recommendations = [...(result.recommendations ?? [])].sort((a, b) => a.rank - b.rank);
        setWdvTemplateRecommendations(recommendations);
        setSelectedWdvTemplateKey((current) => (
          current && recommendations.some((item) => item.template_key === current) ? current : ''
        ));
      })
      .catch((error) => {
        setWdvTemplateRecommendations([]);
        setSelectedWdvTemplateKey('');
        setWdvTemplateModalOpen(false);
        setWdvTemplateRecommendationsError(error instanceof Error ? error.message : 'Template recommendation service unavailable');
      })
      .finally(() => setWdvTemplateRecommendationsLoading(false));
  };

  useEffect(() => {
    loadWdvTemplateRecommendations();
  }, [hasLoadedViewerWell, wdvPackageState.loadedCurveItems]);

  const selectedWdvTemplateRecommendation = useMemo(
    () => wdvTemplateRecommendations.find((item) => item.template_key === selectedWdvTemplateKey) ?? null,
    [selectedWdvTemplateKey, wdvTemplateRecommendations],
  );

  const handleLayoutRecommendationChange = (templateKey: string) => {
    setSelectedWdvTemplateKey(templateKey);
    setWdvTemplateModalOpen(Boolean(templateKey));
  };

  const curveUsageCounts = useMemo(() => wdvPackageState.curveUsageCounts, [wdvPackageState]);

  const selectedTrackCurveIds = useMemo(() => {
    if (!selectedTrack || selectedTrack.trackType !== 'curve') return new Set<string>();
    return new Set(selectedTrack.curves.map((assignment) => assignment.curveId));
  }, [selectedTrack]);

  // WLV-WDV-REBUILD-1B-EMPTY-STATE-CLEANUP:
  // Selected inventory reflects curves assigned to visible tracks only.
  // WMDP-loaded availability remains separate under Loaded Curves.
  const visibleTrackCurveIds = useMemo(() => {
    const ids = new Set<string>();
    tracks.forEach((track) => {
      if (track.trackType !== 'curve') return;
      track.curves.forEach((assignment) => ids.add(assignment.curveId));
    });
    return ids;
  }, [tracks]);

  const updateTrack = (trackId: string, patch: Partial<WellLogTrack>) => {
    setTracks((current) => current.map((track) => (track.trackId === trackId ? { ...track, ...patch } as WellLogTrack : track)));
  };

  const updateCurveAssignment = (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => {
    setTracks((current) => current.map((track) => {
      if (track.trackId !== trackId || track.trackType !== 'curve') return track;
      return {
        ...track,
        curves: track.curves.map((assignment) => (
          assignment.assignmentId === assignmentId ? { ...assignment, ...patch } : assignment
        )),
      };
    }));
  };

  const addTrack = (draft: AddTrackDraft) => {
    setTracks((current) => {
      const ordered = sortTracks(current);
      const selected = ordered.find((track) => track.trackId === selection.trackId) ?? null;
      const insertionIndex =
        draft.insertMode === 'before_selected' && selected
          ? selected.trackIndex
          : draft.insertMode === 'after_selected' && selected
            ? selected.trackIndex + 1
            : ordered.length;
      const shifted = current.map((track) => (
        track.trackIndex >= insertionIndex ? { ...track, trackIndex: track.trackIndex + 1 } : track
      ));

      const selectedCurves = pendingAddTrackCurveIds
        .map((curveId) => activeCurveCatalog.find((curve) => curve.curveId === curveId))
        .filter((curve): curve is CurveCatalogItem => Boolean(curve));

      const curveAssignments = draft.trackType === 'curve' && draft.curveSource === 'selected'
        ? selectedCurves.map((curve, index) => makeCurveAssignment(curve, index))
        : [];

      const frontCurve = curveAssignments[0]
        ? curveById(activeCurveCatalog, curveAssignments[0].curveId)
        : null;

      const latticeOverride = draft.trackType === 'curve' && draft.latticeMode !== 'auto';
      const lattice = draft.trackType === 'curve'
        ? draft.latticeMode === 'auto'
          ? frontCurve?.defaultLattice ?? 'linear'
          : draft.latticeMode
        : 'linear';

      const newTrack: WellLogTrack = draft.trackType === 'depth'
        ? {
            trackId: nextTrackId('depth'),
            trackIndex: insertionIndex,
            trackType: 'depth',
            title: draft.depthBasis,
            depthBasis: draft.depthBasis,
            unit: 'm',
            widthPx: 86,
            visible: true,
          }
        : {
            trackId: nextTrackId('curve'),
            trackIndex: insertionIndex,
            trackType: 'curve',
            title: curveAssignments.length > 0
              ? curveAssignments.map((assignment) => curveById(activeCurveCatalog, assignment.curveId).mnemonic).join(' / ')
              : 'NEW CURVE TRACK',
            widthPx: 220,
            visible: true,
            lattice,
            latticeSource: latticeOverride ? 'user_override' : 'front_curve_default',
            latticeOverride,
            scaleMode: draft.scaleMode,
            curves: curveAssignments,
          };
      setSelection({ kind: 'track', trackId: newTrack.trackId });
      if (draft.trackType === 'curve' && draft.curveSource === 'selected') {
        setPendingAddTrackCurveIds([]);
        setAddTrackCurveSelectionMode(false);
      }
      return reindexTracks([...shifted, newTrack]);
    });
  };

  const deleteSelectedTrack = () => {
    if (!selectedTrack) return;
    setTracks((current) => {
      const remaining = reindexTracks(current.filter((track) => track.trackId !== selectedTrack.trackId));
      const fallback = remaining[Math.min(selectedTrack.trackIndex, Math.max(remaining.length - 1, 0))];
      if (fallback) setSelection({ kind: 'track', trackId: fallback.trackId });
      return remaining;
    });
  };

  const moveSelectedTrack = (direction: -1 | 1) => {
    const trackId = selection.trackId;
    if (!trackId) return;

    setTracks((current) => moveTrackById(current, trackId, direction));

    setSelection((current) => (
      current.trackId === trackId ? current : { kind: 'track', trackId }
    ));
  };


  const adjustCurveTrackWidth = (trackId: string, delta: number) => {
    setTracks((current) => current.map((track) => {
      if (track.trackId !== trackId || track.trackType !== 'curve') return track;
      return { ...track, widthPx: clampCurveTrackWidth(track.widthPx + delta) };
    }));
  };

  const adjustSelectedCurveTrackWidth = (delta: number) => {
    if (!selectedCurveTrack) return;
    adjustCurveTrackWidth(selectedCurveTrack.trackId, delta);
  };

  const resetCurveTrackWidths = () => {
    setTracks((current) => current.map((track) => (
      track.trackType === 'curve'
        ? { ...track, widthPx: CURVE_TRACK_RESET_WIDTH }
        : track
    )));
  };

  const startCurveTrackResize = (trackId: string, startX: number, startWidth: number) => {
    setOpenCurveMenu(null);
    setDragPanState(null);
    setIntervalZoomActive(false);
    setIntervalSelection(null);
    setTrackResizeState({ trackId, startX, startWidth: clampCurveTrackWidth(startWidth) });
  };

  const setDepthView = (nextRange: DepthViewRange, recordHistory = true) => {
    setViewDepthRange((current) => {
      const clipped = clampDepthRange(nextRange, activeFullDepthRange);

      if (rangesEqual(current, clipped)) {
        return current;
      }

      if (recordHistory) {
        setViewHistory((history) => [...history.slice(-9), current]);
      }

      return clipped;
    });
  };

  const zoomDepth = (factor: number) => {
    const center = (viewDepthRange.min + viewDepthRange.max) / 2;
    const nextSpan = Math.max(80, Math.min(activeFullDepthRange.max - activeFullDepthRange.min, (viewDepthRange.max - viewDepthRange.min) * factor));
    setDepthView({
      min: center - nextSpan / 2,
      max: center + nextSpan / 2,
    });
  };

  const previousDepthView = () => {
    setViewHistory((history) => {
      const previous = history[history.length - 1];
      if (!previous) return history;
      setViewDepthRange(previous);
      return history.slice(0, -1);
    });
  };

  const fitDepth = () => {
    setDepthView(activeFullDepthRange);
  };

  const resetDepthView = () => {
    setViewDepthRange(activeDefaultDepthRange);
    setViewHistory([]);
    setIntervalZoomActive(false);
    setIntervalSelection(null);
    setDragPanState(null);
    setGoToDepthMarker(null);
    setGoToDepthValue('');
  };

  const goToDepth = () => {
    const target = Number.parseFloat(goToDepthValue);
    if (!Number.isFinite(target)) return;

    const clampedTarget = clampValue(target, activeFullDepthRange.min, activeFullDepthRange.max);
    const currentSpan = viewDepthRange.max - viewDepthRange.min;
    const reviewSpan = currentSpan > GO_TO_REVIEW_WINDOW_M
      ? GO_TO_REVIEW_WINDOW_M
      : currentSpan;

    setDepthView({
      min: clampedTarget - reviewSpan / 2,
      max: clampedTarget + reviewSpan / 2,
    });
    setGoToDepthMarker(clampedTarget);
  };

  const startDragPan = (startY: number) => {
    setOpenCurveMenu(null);
    setIntervalZoomActive(false);
    setIntervalSelection(null);
    setViewHistory((history) => [...history.slice(-9), viewDepthRange]);
    setDragPanState({ startY, startRange: viewDepthRange });
  };

  const updateDragPan = (currentY: number, canvasHeight: number) => {
    if (!dragPanState) return;
    const safeHeight = Math.max(1, canvasHeight);
    const span = dragPanState.startRange.max - dragPanState.startRange.min;
    const pixelDelta = currentY - dragPanState.startY;
    const depthShift = -(pixelDelta / safeHeight) * span;

    setViewDepthRange(clampDepthRange({
      min: dragPanState.startRange.min + depthShift,
      max: dragPanState.startRange.max + depthShift,
    }, activeFullDepthRange));
  };

  const endDragPan = () => {
    setDragPanState(null);
  };

  const openManagedWellLogViewer = (managedWellId?: string | null) => {
    if (managedWellId) {
      setManagedViewerWellId(managedWellId);
      wdvSessionHydratedKeyRef.current = null;
      setTracks([]);
      setSelectedInventoryCurveIds([]);
      setPendingAddTrackCurveIds([]);
      setAddTrackCurveSelectionMode(false);
    }
    setActiveView('log-viewer');
  };

  const clearManagedWellLogViewer = () => {
    setManagedViewerWellId(null);
    wdvSessionHydratedKeyRef.current = null;
    setTracks([]);
    setSelectedInventoryCurveIds([]);
    setPendingAddTrackCurveIds([]);
    setAddTrackCurveSelectionMode(false);
    setActiveView('log-viewer');
  };

  const startIntervalSelection = (depth: number, y: number) => {
    setDragPanState(null);
    setOpenCurveMenu(null);
    setIntervalSelection({
      startDepth: depth,
      currentDepth: depth,
      startY: y,
      currentY: y,
      dragging: true,
    });
  };

  const updateIntervalSelection = (depth: number, y: number) => {
    setIntervalSelection((current) => current
      ? { ...current, currentDepth: depth, currentY: y }
      : current);
  };

  const armIntervalSelection = (depth: number, y: number) => {
    setIntervalSelection((current) => current
      ? { ...current, currentDepth: depth, currentY: y, dragging: false }
      : {
          startDepth: depth,
          currentDepth: depth,
          startY: y,
          currentY: y,
          dragging: false,
        });
  };

  const completeIntervalSelection = (depth: number, y: number) => {
    if (!intervalSelection) return;

    const nextMin = Math.min(intervalSelection.startDepth, depth);
    const nextMax = Math.max(intervalSelection.startDepth, depth);

    if (nextMax - nextMin < 25) {
      setIntervalSelection({
        ...intervalSelection,
        currentDepth: depth,
        currentY: y,
        dragging: false,
      });
      return;
    }

    setDepthView({ min: nextMin, max: nextMax });
    setIntervalZoomActive(false);
    setIntervalSelection(null);
  };

  const toggleCurveForSelectedTrack = (curveId: string, checked: boolean) => {
    if (!selectedTrack || selectedTrack.trackType !== 'curve') return;
    const trackId = selectedTrack.trackId;

    setOpenCurveMenu(null);

    if (checked) {
      const curve = activeCurveCatalog.find((item) => item.curveId === curveId);
      if (!curve) {
        console.warn('Blocked curve assignment for unknown curve id', curveId);
        return;
      }
      const newAssignment = makeCurveAssignment(curve, selectedTrack.curves.length);

      setTracks((current) => current.map((track) => {
        if (track.trackId !== trackId || track.trackType !== 'curve') return track;
        if (track.curves.some((assignment) => assignment.curveId === curveId)) return track;

        const nextCurves = renumberCurveStack([...orderedCurves(track), newAssignment]);
        return {
          ...track,
          curves: nextCurves,
          latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default',
        };
      }));

      setSelection({ kind: 'curve', trackId, assignmentId: newAssignment.assignmentId });
      return;
    }

    setTracks((current) => current.map((track) => {
      if (track.trackId !== trackId || track.trackType !== 'curve') return track;
      return {
        ...track,
        curves: renumberCurveStack(track.curves.filter((assignment) => assignment.curveId !== curveId)),
        latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default',
      };
    }));

    setSelection({ kind: 'track', trackId });
  };

  const moveCurveToTrack = (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => {
    setTracks((current) => {
      let movingAssignment: CurveAssignment | null = null;
      let working = current.map((track) => {
        if (track.trackType !== 'curve') return track;
        if (payload.fromTrackId === track.trackId && payload.assignmentId) {
          const match = track.curves.find((assignment) => assignment.assignmentId === payload.assignmentId);
          if (match) movingAssignment = match;
          return { ...track, curves: renumberCurveStack(track.curves.filter((assignment) => assignment.assignmentId !== payload.assignmentId)) };
        }
        return track;
      });

      const curve = activeCurveCatalog.find((item) => item.curveId === payload.curveId);
      if (!curve) {
        console.warn('Blocked curve assignment for unknown curve id', payload.curveId);
        return reindexTracks(working);
      }
      const assignment = movingAssignment ?? makeCurveAssignment(curve, 0);

      working = working.map((track) => {
        if (track.trackId !== toTrackId || track.trackType !== 'curve') return track;
        const existing = track.curves.some((item) => item.assignmentId === assignment.assignmentId || item.curveId === assignment.curveId);
        if (existing) return track;
        const next = [...orderedCurves(track)];
        const targetIndex = typeof toIndex === 'number' ? toIndex : next.length;
        next.splice(targetIndex, 0, { ...assignment, stackIndex: targetIndex });
        return { ...track, curves: renumberCurveStack(next), latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default' };
      });

      setSelection({ kind: 'curve', trackId: toTrackId, assignmentId: assignment.assignmentId });
      return reindexTracks(working);
    });
  };

  const reorderCurve = (trackId: string, assignmentId: string, toIndex: number) => {
    setTracks((current) => current.map((track) => {
      if (track.trackId !== trackId || track.trackType !== 'curve') return track;
      const ordered = orderedCurves(track);
      const fromIndex = ordered.findIndex((assignment) => assignment.assignmentId === assignmentId);
      if (fromIndex < 0) return track;
      const [item] = ordered.splice(fromIndex, 1);
      ordered.splice(toIndex, 0, item);
      return { ...track, curves: renumberCurveStack(ordered), latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default' };
    }));
    setSelection({ kind: 'curve', trackId, assignmentId });
  };

  const removeCurveFromTrack = (trackId: string, assignmentId: string) => {
    setTracks((current) => current.map((track) => {
      if (track.trackId !== trackId || track.trackType !== 'curve') return track;
      return {
        ...track,
        curves: renumberCurveStack(track.curves.filter((assignment) => assignment.assignmentId !== assignmentId)),
        latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default',
      };
    }));

    setOpenCurveMenu(null);
    setSelection({ kind: 'track', trackId });
  };

  return (
    <div className="wlv-demo-shell">
      <DemoShellRail activeView={activeView} onNavigate={setActiveView} />
      <main className="wlv-demo-main" aria-label="Well Log Viewer workspace">
        {activeView === 'data' ? (
          <ManagedWellInventoryPage onOpenLogViewer={openManagedWellLogViewer} onClearLogViewer={clearManagedWellLogViewer} activeManagedWellId={managedViewerWellId} />
        ) : activeView === 'info' ? (
          <section className="wlv-prototype-root">
            <header className="wlv-app-header">
              <div className="wlv-app-title">
                <strong>Info</strong>
                <span>Well Log Viewer application information</span>
              </div>
            </header>
          </section>
        ) : activeView === 'knowledge' ? (
          <div className="wlv-kr-page-shell">
            <KrManagedInstructionsWorkbench />
          </div>
        ) : activeView === 'sources' ? (
          <SourceIntakeWorkbench />
        ) : activeView === 'wellbore-3d' ? (
          <Wellbore3DPage activeManagedWellId={managedViewerWellId} onOpenLogViewer={() => setActiveView('log-viewer')} />
        ) : (
        <div className="wlv-prototype-root">
      <header className="wlv-app-header">
        <div className="wlv-app-title">
          <strong>Well Log Viewer</strong>
        </div>
        <button
          type="button"
          className="wlv-wdv-3d-badge"
          onClick={() => setActiveView('wellbore-3d')}
          title="Open 3D Wellbore Viewer"
          aria-label="Open 3D Wellbore Viewer"
        >
          3D
        </button>
      </header>

      {!hasLoadedViewerWell && (
        <section className="wlv-empty-viewer-top-banner" aria-label="Well Data Viewer empty state">
          <strong>No data loaded in the Well Data Viewer</strong>
          <span>
            The WDV is ready. Load a managed well or selected products from the WMDP using Bulk Action → Load selected to Data Viewer.
          </span>
        </section>
      )}

      <Toolbar
        selectedTrack={selectedTrack}
        pendingAddTrackCurveCount={pendingAddTrackCurveIds.length}
        viewDepthRange={viewDepthRange}
        fullDepthRange={activeFullDepthRange}
        viewDepthReadoutEnabled={tracks.length > 0}
        intervalZoomActive={intervalZoomActive}
        goToDepthValue={goToDepthValue}
        onGoToDepthValueChange={setGoToDepthValue}
        trackBackdropMode={trackBackdropMode}
        onTrackBackdropModeChange={setTrackBackdropMode}
        onAddTrack={addTrack}
        onDeleteTrack={deleteSelectedTrack}
        onMoveSelectedTrack={moveSelectedTrack}
        canMoveSelectedTrackLeft={canMoveSelectedTrackLeft}
        canMoveSelectedTrackRight={canMoveSelectedTrackRight}
        canAdjustSelectedCurveTrackWidthDown={canAdjustSelectedCurveTrackWidthDown}
        canAdjustSelectedCurveTrackWidthUp={canAdjustSelectedCurveTrackWidthUp}
        onAdjustSelectedCurveTrackWidth={adjustSelectedCurveTrackWidth}
        onResetCurveTrackWidths={resetCurveTrackWidths}
        onZoomIn={() => zoomDepth(0.75)}
        onZoomOut={() => zoomDepth(1.33)}
        onPreviousView={previousDepthView}
        onFitDepth={fitDepth}
        onSpecifyDepthRange={(range) => {
          setOpenCurveMenu(null);
          setIntervalZoomActive(false);
          setIntervalSelection(null);
          setDragPanState(null);
          setDepthView(range);
        }}
        onResetView={resetDepthView}
        onToggleIntervalZoom={() => {
          setOpenCurveMenu(null);
          setIntervalSelection(null);
          setDragPanState(null);
          setIntervalZoomActive((active) => !active);
        }}
        onGoToDepth={goToDepth}
        onAddTrackCurveSelectionModeChange={(active) => {
          setAddTrackCurveSelectionMode(active);
          if (active) {
            setPendingAddTrackCurveIds([]);
          }
        }}
        layoutRecommendations={wdvTemplateRecommendations}
        layoutRecommendationsLoading={wdvTemplateRecommendationsLoading}
        layoutRecommendationsError={wdvTemplateRecommendationsError}
        selectedLayoutRecommendationKey={selectedWdvTemplateKey}
        onLayoutRecommendationChange={handleLayoutRecommendationChange}
        onRefreshLayoutRecommendations={loadWdvTemplateRecommendations}
      />

      {wdvTemplateModalOpen && selectedWdvTemplateRecommendation ? (
        <WdvTemplateRecommendationModal
          recommendation={selectedWdvTemplateRecommendation}
          loadedCurveItems={wdvPackageState.loadedCurveItems}
          managedWellId={managedViewerWellId}
          onClose={() => setWdvTemplateModalOpen(false)}
        />
      ) : null}

      <div
        className={`wlv-prototype-workspace wlv-track-backdrop-${trackBackdropMode} ${curveInventoryResizeState ? 'curve-inventory-resize-active' : ''} ${curveInventoryCollapsed ? 'curve-inventory-collapsed' : ''}`}
        style={{ gridTemplateColumns: `${curveInventoryCollapsed ? 38 : curveInventoryWidthPx}px minmax(0, 1fr) 330px` }}
      >
        <div className={`wlv-curve-inventory-shell ${curveInventoryCollapsed ? 'collapsed' : ''}`} style={{ width: curveInventoryCollapsed ? 38 : curveInventoryWidthPx }}>
        <button
          type="button"
          className="wlv-curve-inventory-collapse-toggle"
          onClick={() => setCurveInventoryCollapsed((collapsed) => !collapsed)}
          aria-expanded={!curveInventoryCollapsed}
          aria-label={curveInventoryCollapsed ? 'Expand Curve Inventory' : 'Collapse Curve Inventory'}
          title={curveInventoryCollapsed ? 'Expand Curve Inventory' : 'Collapse Curve Inventory'}
        >
          {curveInventoryCollapsed ? '›' : '‹'}
        </button>
        {curveInventoryCollapsed ? (
          <div className="wlv-curve-inventory-collapsed-label" aria-hidden="true">Curves</div>
        ) : (
        <CurveInventory
          availableCurves={activeViewerCurves}
          curveUsageCounts={curveUsageCounts}
          visibleTrackCurveIds={visibleTrackCurveIds}
          selectedTrackCurveIds={addTrackCurveSelectionMode ? new Set(pendingAddTrackCurveIds) : selectedTrackCurveIds}
          selectedCurveIds={new Set(selectedInventoryCurveIds)}
          assignmentEnabled={addTrackCurveSelectionMode || selectedTrack?.trackType === 'curve'}
          preferredInventoryTab={tracks.length > 0 ? 'selected' : 'all'}
          onToggleCurveInSelectedTrack={(curveId, checked) => {
            if (addTrackCurveSelectionMode) {
              setPendingAddTrackCurveIds((current) => (
                checked
                  ? Array.from(new Set([...current, curveId]))
                  : current.filter((item) => item !== curveId)
              ));
              return;
            }

            toggleCurveForSelectedTrack(curveId, checked);
          }}
          onSelectCurve={(curveId) => {
            setOpenCurveMenu(null);
            setSelectedInventoryCurveIds((current) => (
              current.includes(curveId)
                ? current.filter((item) => item !== curveId)
                : [...current, curveId]
            ));
            const containingTrack = selectedTrack?.trackType === 'curve' && selectedTrack.curves.some((assignment) => assignment.curveId === curveId)
              ? selectedTrack
              : tracks.find((track) => (
                  track.trackType === 'curve' && track.curves.some((assignment) => assignment.curveId === curveId)
                ));
            if (containingTrack?.trackType === 'curve') {
              const assignment = containingTrack.curves.find((item) => item.curveId === curveId);
              if (assignment) setSelection({ kind: 'curve', trackId: containingTrack.trackId, assignmentId: assignment.assignmentId });
            }
          }}
        />
        )}
        {!curveInventoryCollapsed && (
        <button
          type="button"
          className="wlv-curve-inventory-resize-handle"
          aria-label="Resize curve inventory panel"
          title="Drag to widen Curve Inventory"
          onMouseDown={(event) => {
            event.preventDefault();
            setCurveInventoryResizeState({ startX: event.clientX, startWidth: curveInventoryWidthPx });
          }}
          onDoubleClick={() => setCurveInventoryWidthPx(CURVE_INVENTORY_DEFAULT_WIDTH_PX)}
        />
        )}
        </div>
        {tracks.length === 0 ? (
          hasLoadedViewerWell ? (
            <section className="wlv-loaded-curves-ready-state" aria-label="Loaded curves ready">
              <div className="wlv-loaded-curves-ready-card">
                <h2>Loaded curves are ready</h2>
                <p>
                  {wdvPackageState.loadedProductCount} loaded curve product{wdvPackageState.loadedProductCount === 1 ? '' : 's'}
                  {' '}are available in the left Loaded Curves panel.
                </p>
                <p className="wlv-empty-viewer-note">
                  Select loaded curves and use Add Track, or drag curves into a manually created curve track.
                  WMDP Load does not automatically populate well-log tracks.
                </p>
                {wdvPackageState.unsupportedProductCount > 0 && (
                  <p className="wlv-empty-viewer-note">
                    {wdvPackageState.unsupportedProductCount} unsupported product{wdvPackageState.unsupportedProductCount === 1 ? '' : 's'}
                    {' '}were excluded from renderable Loaded Curves.
                  </p>
                )}
              </div>
            </section>
          ) : (
            <section className="wlv-track-canvas wlv-track-canvas-empty-active" aria-label="Blank Well Data Viewer track canvas">
              <div className="wlv-track-strip" aria-hidden="true" />
            </section>
          )
        ) : (
          <TrackCanvas
            tracks={tracks}
            selection={selection}
            openCurveMenu={openCurveMenu}
            depthTicks={visibleDepthTicks}
            viewDepthRange={viewDepthRange}
            goToDepthMarker={goToDepthMarker}
            intervalZoomActive={intervalZoomActive}
            intervalSelection={intervalSelection}
            dragPanActive={Boolean(dragPanState)}
            onSelectTrack={(trackId) => setSelection({ kind: 'track', trackId })}
            onSelectCurve={(trackId, assignmentId) => setSelection({ kind: 'curve', trackId, assignmentId })}
            onReorderCurve={reorderCurve}
            onMoveCurveToTrack={moveCurveToTrack}
            onOpenCurveMenu={(trackId, assignmentId) => setOpenCurveMenu({ trackId, assignmentId })}
            onCloseCurveMenu={() => setOpenCurveMenu(null)}
            onRemoveCurveFromTrack={removeCurveFromTrack}
            onStartIntervalSelection={startIntervalSelection}
            onUpdateIntervalSelection={updateIntervalSelection}
            onArmIntervalSelection={armIntervalSelection}
            onCompleteIntervalSelection={completeIntervalSelection}
            onStartDragPan={startDragPan}
            onUpdateDragPan={updateDragPan}
            onEndDragPan={endDragPan}
            onStartCurveTrackResize={startCurveTrackResize}
            resizingTrackId={trackResizeState?.trackId ?? null}
          />
        )}
        {tracks.length === 0 ? (
          <aside className="wlv-right-panel wlv-ready-properties-panel" aria-label="Track properties unavailable">
            <div className="wlv-panel-heading">
              <h2>Track Properties</h2>
            </div>
            <div className="wlv-ready-properties-copy">
              Create or select a visible track to edit display properties.
            </div>
          </aside>
        ) : (
          <WellLogPropertiesPanelSlot
            tracks={tracks}
            selection={selection}
            updateTrack={updateTrack}
            updateCurveAssignment={updateCurveAssignment}
            legacyPanel={(
              <RightPanel
                tracks={tracks}
                selection={selection}
                updateTrack={updateTrack}
                updateCurveAssignment={updateCurveAssignment}
              />
            )}
          />
        )}
      </div>

      <footer className="wlv-status-footer">
        <span>WL-PROTOTYPE-010B shared depth ruler geometry</span>
        <span>Track terminology only</span>
        <span>Mock frontend layout draft — no LAS parsing or MSI persistence</span>
      </footer>
        </div>
        )}
      </main>
    </div>
  );
}

export default TrackLayoutPrototype;
