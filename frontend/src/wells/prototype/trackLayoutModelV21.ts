import type {
  AssignmentUid,
  ManagedCurveUid,
  ManagedProductUid,
  ManagedSourceUid,
  ManagedWellUid,
  ManagedWellboreUid,
  TrackUid,
} from '../identity/wdvIdentityV21';
import {
  WdvIdentityContractError,
  canonicalCurveByUid,
  indexCanonicalCurvesByUid,
  type CanonicalCurveCatalogItemV21,
} from '../identity/wdvIdentityV21';

export type TrackTypeV21 = 'depth' | 'curve' | 'lithology' | 'raster' | 'marker' | 'interval';
export type CurveLatticeV21 = 'linear' | 'logarithmic';
export type LatticeSourceV21 = 'front_curve_default' | 'user_override' | 'template';
export type ScaleModeV21 = 'shared' | 'per_curve' | 'dual' | 'normalized';
export type CurveScaleTypeV21 = 'linear' | 'log';
export type CurveRangeModeV21 = 'auto' | 'fixed';
export type LineStyleV21 = 'solid' | 'dash' | 'dot';
export type FillSideV21 = 'none' | 'left' | 'right' | 'between';

export interface CurveCatalogItemV21 extends CanonicalCurveCatalogItemV21 {
  curveClass: string;
  defaultLattice: CurveLatticeV21;
  defaultMin: number | null;
  defaultMax: number | null;
  reviewRequired: boolean;
  defaultScaleDirection: 'normal' | 'reverse';
  defaultColor: string;
  recognised: boolean;
}

export interface CurveAssignmentV21 {
  assignmentUid: AssignmentUid;
  trackUid: TrackUid;
  managedCurveUid: ManagedCurveUid;
  managedProductUid: ManagedProductUid;
  managedWellUid: ManagedWellUid;
  managedWellboreUid: ManagedWellboreUid | null;
  managedSourceUid: ManagedSourceUid;
  stackIndex: number;
  visible: boolean;
  scaleMin: number | null;
  scaleMax: number | null;
  scaleDirection: 'normal' | 'reverse';
  scaleType: CurveScaleTypeV21;
  rangeMode: CurveRangeModeV21;
  color: string;
  lineVisible: boolean;
  lineStyle: LineStyleV21;
  lineWidth: number;
  lineOpacity: number;
  positionAnchor: 'left' | 'center' | 'right';
  horizontalOffsetPct: number;
  clipToTrack: boolean;
  fillSide: FillSideV21;
  fillColor: string;
  fillOpacity: number;
  infillSource: 'solid' | 'lithology' | 'curve_pair';
  infillPattern: string;
  infillIntervalColumn: string;
  pairedManagedCurveUid: ManagedCurveUid | null;
  displayPriority: 'background' | 'normal' | 'foreground';
  showQaqcWarnings: boolean;
  showNullGaps: boolean;
  showOutOfRange: boolean;
}

export interface CurveTrackV21 {
  trackUid: TrackUid;
  trackIndex: number;
  title: string;
  widthPx: number;
  visible: boolean;
  trackType: 'curve';
  trackKey: string | null;
  rendererType: string | null;
  trackRole: string | null;
  sourceTemplateKey: string | null;
  sourceApplicationPlanUid: string | null;
  lattice: CurveLatticeV21;
  latticeSource: LatticeSourceV21;
  latticeOverride: boolean;
  scaleMode: ScaleModeV21;
  curves: CurveAssignmentV21[];
}

export interface DepthTrackV21 {
  trackUid: TrackUid;
  trackIndex: number;
  title: string;
  widthPx: number;
  visible: boolean;
  trackType: 'depth';
  trackKey: string | null;
  rendererType: string | null;
  trackRole: string | null;
  sourceTemplateKey: string | null;
  sourceApplicationPlanUid: string | null;
  depthBasis: 'MD' | 'TVD' | 'TVDSS';
  unit: string;
}

export type WellLogTrackV21 = CurveTrackV21 | DepthTrackV21;

export interface BackendAssignmentSeedV21 {
  assignmentUid: AssignmentUid;
  trackUid: TrackUid;
  managedCurveUid: ManagedCurveUid;
  managedProductUid: ManagedProductUid;
  managedWellUid: ManagedWellUid;
  managedWellboreUid: ManagedWellboreUid | null;
  managedSourceUid: ManagedSourceUid;
}

/** @deprecated Compatibility/test helper only. Runtime assignments come from the backend canonical contract. */
export function buildCurveAssignmentV21(
  seed: BackendAssignmentSeedV21,
  curve: CurveCatalogItemV21,
  stackIndex: number,
): CurveAssignmentV21 {
  if (seed.managedCurveUid !== curve.managedCurveUid) {
    throw new WdvIdentityContractError(
      'Assignment managedCurveUid must match catalogue managedCurveUid',
    );
  }
  if (seed.managedWellUid !== curve.managedWellUid) {
    throw new WdvIdentityContractError(
      'Assignment managedWellUid must match catalogue managedWellUid',
    );
  }
  if (seed.managedProductUid !== curve.managedProductUid) {
    throw new WdvIdentityContractError(
      'Assignment managedProductUid must match catalogue managedProductUid',
    );
  }
  if (seed.managedSourceUid !== curve.managedSourceUid) {
    throw new WdvIdentityContractError(
      'Assignment managedSourceUid must match catalogue managedSourceUid',
    );
  }

  return {
    ...seed,
    stackIndex,
    visible: true,
    scaleMin: curve.defaultMin,
    scaleMax: curve.defaultMax,
    scaleDirection: curve.defaultScaleDirection,
    scaleType: curve.defaultLattice === 'logarithmic' ? 'log' : 'linear',
    rangeMode: 'fixed',
    color: curve.defaultColor,
    lineVisible: true,
    lineStyle: 'solid',
    lineWidth: 1.8,
    lineOpacity: 100,
    positionAnchor: 'center',
    horizontalOffsetPct: 0,
    clipToTrack: true,
    fillSide: 'none',
    fillColor: '#7fbf8f',
    fillOpacity: 55,
    infillSource: 'solid',
    infillPattern: 'solid',
    infillIntervalColumn: 'lithology',
    pairedManagedCurveUid: null,
    displayPriority: 'normal',
    showQaqcWarnings: true,
    showNullGaps: true,
    showOutOfRange: true,
  };
}

export function curveByManagedUidV21(
  curves: readonly CurveCatalogItemV21[],
  managedCurveUid: ManagedCurveUid,
): CurveCatalogItemV21 {
  return canonicalCurveByUid(curves, managedCurveUid) as CurveCatalogItemV21;
}

export function indexCurveCatalogV21(
  curves: readonly CurveCatalogItemV21[],
): ReadonlyMap<ManagedCurveUid, CurveCatalogItemV21> {
  return indexCanonicalCurvesByUid(curves) as ReadonlyMap<
    ManagedCurveUid,
    CurveCatalogItemV21
  >;
}

export function orderedCurvesV21(track: CurveTrackV21): CurveAssignmentV21[] {
  return [...track.curves].sort((left, right) => left.stackIndex - right.stackIndex);
}

export function renumberCurveStackV21(
  curves: readonly CurveAssignmentV21[],
): CurveAssignmentV21[] {
  return curves.map((curve, index) => ({ ...curve, stackIndex: index }));
}

export function resolveTrackLatticeV21(
  track: CurveTrackV21,
  catalogue: readonly CurveCatalogItemV21[],
): {
  lattice: CurveLatticeV21;
  source: LatticeSourceV21;
  frontCurve?: CurveCatalogItemV21;
} {
  if (track.latticeOverride) {
    return { lattice: track.lattice, source: 'user_override' };
  }

  const frontAssignment = orderedCurvesV21(track)[0];
  if (!frontAssignment) {
    return { lattice: track.lattice, source: track.latticeSource };
  }

  const frontCurve = curveByManagedUidV21(
    catalogue,
    frontAssignment.managedCurveUid,
  );
  return {
    lattice: frontCurve.defaultLattice,
    source: 'front_curve_default',
    frontCurve,
  };
}

export function validateTrackGraphV21(
  tracks: readonly WellLogTrackV21[],
): void {
  const trackUids = new Set<TrackUid>();
  const assignmentUids = new Set<AssignmentUid>();

  for (const track of tracks) {
    if (trackUids.has(track.trackUid)) {
      throw new WdvIdentityContractError(`Duplicate trackUid: ${track.trackUid}`);
    }
    trackUids.add(track.trackUid);

    if (track.trackType !== 'curve') continue;

    for (const assignment of track.curves) {
      if (assignment.trackUid !== track.trackUid) {
        throw new WdvIdentityContractError(
          `Assignment ${assignment.assignmentUid} references the wrong trackUid`,
        );
      }
      if (assignmentUids.has(assignment.assignmentUid)) {
        throw new WdvIdentityContractError(
          `Duplicate assignmentUid: ${assignment.assignmentUid}`,
        );
      }
      assignmentUids.add(assignment.assignmentUid);
    }
  }
}
