/**
 * Presentation adapter for the shared canvas session.
 *
 * Maps ResolvedWdvCanvasSession + per-curve samples
 * → OriginalWdvPresentationModel (WellLogTrack[]).
 *
 * Contract:
 *   - Tracks are output in ascending track_order.
 *   - Slots are sorted by slot_order within each track.
 *   - Only BOUND slots produce a CurveAssignment and a CurveCatalogItem.
 *   - Non-BOUND slots are silently omitted from curves[]; the track itself
 *     is always present.
 *   - Numeric scale_min/scale_max are retained verbatim for plotting.
 *   - scale_min_label/scale_max_label (backend-formatted strings) are
 *     carried through for header display only.
 *   - depth_min/depth_max from the session feed fullDepthRange and
 *     WellHeader.logStart/logEnd.
 *   - This adapter never reads or writes any session store.
 *   - This adapter never retains curve UIDs from a previous well.
 */

import type {
  ManagedCurveUid,
} from '../identity/wdvIdentityV21';
import type {
  ManagedCurveSamplesByUidV21,
  ManagedCurveSampleV21,
} from '../prototype/managedCurveSamplesV21';
import type {
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
  DepthBasis,
  DepthTrack,
  CurveLattice,
  LatticeSource,
  ScaleMode,
  SelectionRef,
  WellHeader,
  WellLogTrack,
} from '../prototype/trackLayoutModel';
import type {
  OriginalWdvAdapterIssue,
  OriginalWdvLoadedCurveItem,
  OriginalWdvPresentationModel,
} from './originalWdvPresentationAdapter';
import type {
  ResolvedWdvCanvasSession,
  SharedCanvasResolvedSlot,
  SharedCanvasResolvedTrack,
} from './sharedCanvasApiTypes';


// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const DEFAULT_TRACK_WIDTH = 150;
const DEFAULT_CURVE_COLOR = '#2f80ed';


// ---------------------------------------------------------------------------
// Coercion helpers
// ---------------------------------------------------------------------------

function toLattice(value: string | null): CurveLattice {
  return value === 'logarithmic' ? 'logarithmic' : 'linear';
}

function toLatticeSource(value: string | null): LatticeSource {
  if (value === 'user_override') return 'user_override';
  if (value === 'template') return 'template';
  return 'front_curve_default';
}

function toScaleMode(value: string): ScaleMode {
  if (
    value === 'shared'
    || value === 'per_curve'
    || value === 'dual'
    || value === 'normalized'
  ) {
    return value;
  }
  return 'per_curve';
}

function toDepthBasis(value: string | null): DepthBasis {
  if (value === 'TVD') return 'TVD';
  if (value === 'TVDSS') return 'TVDSS';
  return 'MD';
}

function toDepthUnit(value: string): 'm' | 'ft' {
  if (value === 'm' || value === 'ft') return value;
  throw new Error(`Unsupported backend depth unit: ${value}`);
}


// ---------------------------------------------------------------------------
// Slot → CurveAssignment / CurveCatalogItem
// ---------------------------------------------------------------------------

/**
 * Convert a BOUND slot to a CurveAssignment.
 * The caller must guarantee slot.managed_curve_uid is non-null.
 */
function slotToAssignment(
  slot: SharedCanvasResolvedSlot,
  track: SharedCanvasResolvedTrack,
  managedWellUid: string,
): CurveAssignment {
  if (slot.scale_min === null || slot.scale_max === null) {
    throw new Error(`Shared-canvas slot ${slot.slot_uid} has no backend scale bounds.`);
  }
  const curveId = slot.managed_curve_uid as string; // BOUND guarantees non-null
  return {
    assignmentId: slot.slot_uid,
    curveId,
    curveUid: curveId,
    krCurveTypeId: slot.kr_curve_type_id ?? null,
    managedWellUid,
    unit: slot.unit,
    stackIndex: slot.slot_order,
    visible: true,
    scaleMin: slot.scale_min,
    scaleMax: slot.scale_max,
    scaleMinLabel: slot.scale_min_label ?? null,
    scaleMaxLabel: slot.scale_max_label ?? null,
    scaleDirection: slot.scale_min > slot.scale_max ? 'reverse' : 'normal',
    scaleType: track.lattice === 'logarithmic' ? 'log' : 'linear',
    rangeMode: 'fixed',
    color: DEFAULT_CURVE_COLOR,
    lineVisible: true,
    lineStyle: 'solid',
    lineWidth: 1.5,
    lineOpacity: 1,
    fillSide: 'none',
    fillColor: 'transparent',
    fillOpacity: 0,
    showNullGaps: false,
    showOutOfRange: false,
    showQaqcWarnings: false,
    clipToTrack: true,
  };
}

function slotToCatalogItem(
  slot: SharedCanvasResolvedSlot,
  track: SharedCanvasResolvedTrack,
  managedWellUid: string,
): CurveCatalogItem {
  const curveId = slot.managed_curve_uid as string;
  const mnemonic = slot.mnemonic ?? slot.display_name ?? curveId;
  return {
    curveId,
    curveUid: curveId,
    krCurveTypeId: slot.kr_curve_type_id ?? null,
    managedWellUid,
    mnemonic,
    description: slot.display_name ?? mnemonic,
    unit: slot.unit ?? '',
    curveClass: 'unknown',
    defaultLattice: toLattice(track.lattice),
    defaultMin: slot.scale_min as number,
    defaultMax: slot.scale_max as number,
    defaultColor: DEFAULT_CURVE_COLOR,
    recognised: false,
  };
}


// ---------------------------------------------------------------------------
// Track conversion
// ---------------------------------------------------------------------------

function trackToCurveTrack(
  track: SharedCanvasResolvedTrack,
  managedWellUid: string,
  issues: OriginalWdvAdapterIssue[],
): CurveTrack {
  const boundSlots = [...track.slots]
    .sort((a, b) => a.slot_order - b.slot_order)
    .filter((slot) => slot.binding_status === 'bound' && slot.managed_curve_uid !== null);

  const curves: CurveAssignment[] = boundSlots.flatMap((slot) => {
    if (slot.scale_min === null || slot.scale_max === null) {
      issues.push({
        code: 'missing_scale_bounds',
        message: `Shared-canvas slot ${slot.slot_uid} has no backend-owned scale bounds.`,
        trackUid: track.track_uid,
        assignmentUid: slot.slot_uid,
        managedCurveUid: slot.managed_curve_uid ?? undefined,
      });
      return [];
    }
    if (slot.unit === null) {
      issues.push({
        code: 'missing_curve_unit',
        message: `Shared-canvas slot ${slot.slot_uid} has no backend-owned unit.`,
        trackUid: track.track_uid,
        assignmentUid: slot.slot_uid,
        managedCurveUid: slot.managed_curve_uid ?? undefined,
      });
    }
    return [slotToAssignment(slot, track, managedWellUid)];
  });

  return {
    trackId: track.track_uid,
    trackIndex: track.track_order,
    title: track.track_name,
    widthPx: track.width_px ?? DEFAULT_TRACK_WIDTH,
    visible: true,
    trackType: 'curve',
    lattice: toLattice(track.lattice),
    latticeSource: toLatticeSource(track.lattice_source),
    latticeOverride: track.lattice_source === 'user_override',
    scaleMode: toScaleMode(track.scale_mode),
    curves,
  };
}

function trackToDepthTrack(
  track: SharedCanvasResolvedTrack,
  depthUnit: string,
): DepthTrack {
  return {
    trackId: track.track_uid,
    trackIndex: track.track_order,
    title: track.track_name,
    widthPx: track.width_px ?? DEFAULT_TRACK_WIDTH,
    visible: true,
    trackType: 'depth',
    depthBasis: toDepthBasis(track.depth_basis),
    unit: toDepthUnit(depthUnit),
  };
}

function convertTrack(
  track: SharedCanvasResolvedTrack,
  session: ResolvedWdvCanvasSession,
  issues: OriginalWdvAdapterIssue[],
): WellLogTrack {
  return track.track_type === 'depth'
    ? trackToDepthTrack(track, session.depth_unit)
    : trackToCurveTrack(track, session.managed_well_uid, issues);
}


// ---------------------------------------------------------------------------
// Samples
// ---------------------------------------------------------------------------

function toLegacySamples(
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21,
): Record<string, readonly (readonly [number, number])[]> {
  const result: Record<string, readonly (readonly [number, number])[]> = {};
  for (const [curveUid, samples] of samplesByManagedCurveUid) {
    result[curveUid] = (samples as readonly ManagedCurveSampleV21[]).map(
      (sample) => [sample.depth, sample.value] as const,
    );
  }
  return result;
}


// ---------------------------------------------------------------------------
// Well header
// ---------------------------------------------------------------------------

function buildWellHeader(
  session: ResolvedWdvCanvasSession,
): WellHeader {
  return {
    wellName: session.managed_well_uid,
    wellboreName: 'Not supplied',
    field: 'Not supplied',
    operator: 'Not supplied',
    country: 'Not supplied',
    kb: 'Not supplied',
    gl: 'Not supplied',
    logStart: String(session.depth_min),
    logEnd: String(session.depth_max),
    sourceFile: 'Shared canvas profile',
    msiIdentity: session.managed_well_uid,
    tvdStatus: 'Not supplied',
  };
}


// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------

function defaultSelection(tracks: readonly WellLogTrack[]): SelectionRef {
  const first = tracks[0];
  return first !== undefined
    ? { kind: 'track', trackId: first.trackId }
    : { kind: 'track', trackId: '__empty_shared_canvas__' };
}


// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Build an OriginalWdvPresentationModel from a ResolvedWdvCanvasSession.
 *
 * @param session    Resolved shared canvas session from the API.
 * @param samplesByManagedCurveUid  Samples for BOUND curves (may be empty).
 * @returns          Presentation model consumed by the WDV renderer.
 */
export function buildSharedCanvasPresentationModel(
  session: ResolvedWdvCanvasSession,
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21 = new Map(),
): OriginalWdvPresentationModel {
  const issues: OriginalWdvAdapterIssue[] = [];

  // Tracks: sort by track_order ascending; all tracks are always present.
  const tracks: WellLogTrack[] = [...session.resolved_tracks]
    .sort((a, b) => a.track_order - b.track_order)
    .map((track) => convertTrack(track, session, issues));

  // Curve catalog: built only from BOUND slots across all tracks.
  const curveCatalogMap = new Map<string, CurveCatalogItem>();
  for (const track of session.resolved_tracks) {
    for (const slot of track.slots) {
      if (
        slot.binding_status === 'bound'
        && slot.managed_curve_uid !== null
        && slot.scale_min !== null
        && slot.scale_max !== null
      ) {
        if (!curveCatalogMap.has(slot.managed_curve_uid)) {
          curveCatalogMap.set(
            slot.managed_curve_uid,
            slotToCatalogItem(slot, track, session.managed_well_uid),
          );
        }
      }
    }
  }
  const curveCatalog = [...curveCatalogMap.values()];

  // Loaded curves: each bound slot treated as assigned (count = 1 per slot).
  const assignmentCounts = new Map<string, number>();
  for (const track of session.resolved_tracks) {
    for (const slot of track.slots) {
      if (
        slot.binding_status === 'bound'
        && slot.managed_curve_uid !== null
        && slot.scale_min !== null
        && slot.scale_max !== null
      ) {
        assignmentCounts.set(
          slot.managed_curve_uid,
          (assignmentCounts.get(slot.managed_curve_uid) ?? 0) + 1,
        );
      }
    }
  }
  const loadedCurves: OriginalWdvLoadedCurveItem[] = curveCatalog.map((curve) => {
    const managedCurveUid = curve.curveId as ManagedCurveUid;
    const assignmentCount = assignmentCounts.get(curve.curveId) ?? 0;
    return {
      managedCurveUid,
      curve,
      assigned: assignmentCount > 0,
      assignmentCount,
    };
  });

  const curveSamplesByCurveId = toLegacySamples(samplesByManagedCurveUid);
  const fullDepthRange = { min: session.depth_min, max: session.depth_max };
  const wellHeader = buildWellHeader(session);
  const selection = defaultSelection(tracks);

  const propertiesInputs = {
    tracks,
    selection,
    curveCatalog,
    wellHeader,
    curveSamplesByCurveId,
    fullDepthRange,
  };

  return {
    managedWellUid: session.managed_well_uid,
    revision: session.profile_revision_number,
    curveCatalog,
    loadedCurves,
    tracks,
    selection,
    wellHeader,
    curveSamplesByCurveId,
    fullDepthRange,
    propertiesInputs,
    issues,
  };
}


// ---------------------------------------------------------------------------
// Utility: extract BOUND curve UIDs from a session (for sample loading)
// ---------------------------------------------------------------------------

export function extractBoundCurveUids(
  session: ResolvedWdvCanvasSession,
): ManagedCurveUid[] {
  const seen = new Set<string>();
  const result: ManagedCurveUid[] = [];
  for (const track of session.resolved_tracks) {
    for (const slot of track.slots) {
      if (
        slot.binding_status === 'bound'
        && slot.managed_curve_uid !== null
        && !seen.has(slot.managed_curve_uid)
      ) {
        seen.add(slot.managed_curve_uid);
        result.push(slot.managed_curve_uid as ManagedCurveUid);
      }
    }
  }
  return result;
}
