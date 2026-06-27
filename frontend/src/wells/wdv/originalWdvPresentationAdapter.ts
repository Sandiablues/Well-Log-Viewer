import type {
  ManagedCurveUid,
} from '../identity/wdvIdentityV21';
import type {
  ManagedCurveSamplesByUidV21,
} from '../prototype/managedCurveSamplesV21';
import type {
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
  SelectionRef,
  WellHeader,
  WellLogTrack,
} from '../prototype/trackLayoutModel';
import type {
  CurveAssignmentV21,
  CurveCatalogItemV21,
  CurveTrackV21,
  DepthTrackV21,
  WellLogTrackV21,
} from '../prototype/trackLayoutModelV21';
import type {
  CanonicalWdvSelection,
} from './canonicalSelection';
import {
  validateCanonicalSelection,
} from './canonicalSelection';
import type {
  CanonicalWorkspaceV1,
} from './canonicalWorkspaceV1';

export type OriginalWdvAdapterIssueCode =
  | 'unresolved_assignment_curve'
  | 'unsupported_depth_unit'
  | 'missing_scale_bounds'
  | 'missing_curve_unit'
  | 'missing_depth_range'
  | 'selection_fallback';

export interface OriginalWdvAdapterIssue {
  code: OriginalWdvAdapterIssueCode;
  message: string;
  trackUid?: string;
  assignmentUid?: string;
  managedCurveUid?: string;
}

export interface OriginalWdvLoadedCurveItem {
  managedCurveUid: ManagedCurveUid;
  curve: CurveCatalogItem;
  assigned: boolean;
  assignmentCount: number;
}

export interface OriginalWdvPropertiesInputs {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  curveCatalog: CurveCatalogItem[];
  wellHeader: WellHeader;
  curveSamplesByCurveId: Record<string, readonly (readonly [number, number])[]>;
  fullDepthRange: {
    min: number;
    max: number;
  };
}

export interface OriginalWdvPresentationModel {
  managedWellUid: string;
  revision: number;
  curveCatalog: CurveCatalogItem[];
  loadedCurves: OriginalWdvLoadedCurveItem[];
  tracks: WellLogTrack[];
  selection: SelectionRef;
  wellHeader: WellHeader;
  curveSamplesByCurveId: Record<
    string,
    readonly (readonly [number, number])[]
  >;
  fullDepthRange: {
    min: number;
    max: number;
  };
  propertiesInputs: OriginalWdvPropertiesInputs;
  issues: OriginalWdvAdapterIssue[];
}

function presentationCurveId(curve: CurveCatalogItemV21): string {
  return curve.managedCurveUid;
}

// Returns null for Tier-3 curves (null default bounds): the legacy CurveCatalogItem type
// requires concrete number bounds and cannot represent the no-safe-bounds contract.
// Tier-3 curves are absent from the legacy catalog but remain renderable when the
// assignment carries user-set non-null scaleMin/scaleMax (see toLegacyAssignment guard).
function toLegacyCurve(curve: CurveCatalogItemV21): CurveCatalogItem | null {
  if (curve.defaultMin === null || curve.defaultMax === null) return null;
  return {
    curveId: presentationCurveId(curve),
    curveUid: curve.managedCurveUid,
    krCurveTypeId: curve.krCurveTypeId,
    wellUid: curve.managedWellUid,
    managedWellUid: curve.managedWellUid,
    sourceUid: curve.managedSourceUid,
    managedSourceUid: curve.managedSourceUid,
    observedMnemonic: curve.observedMnemonic,
    normalizedMnemonic: curve.normalizedMnemonic,
    mnemonic:
      curve.normalizedMnemonic
      ?? curve.observedMnemonic
      ?? curve.displayName,
    description: curve.description ?? curve.displayName,
    unit: curve.unit ?? '',
    curveClass: curve.curveClass as CurveCatalogItem['curveClass'],
    defaultLattice: curve.defaultLattice,
    defaultMin: curve.defaultMin,
    defaultMax: curve.defaultMax,
    defaultScaleDirection: curve.defaultScaleDirection,
    defaultColor: curve.defaultColor,
    recognised: curve.recognised,
  };
}

// scaleMin and scaleMax are passed as explicit number parameters because TypeScript
// cannot propagate the null-narrowing from the call site through the CurveAssignmentV21
// object type into an intersection. Caller must guard for null before calling.
function toLegacyAssignment(
  assignment: CurveAssignmentV21,
  scaleMin: number,
  scaleMax: number,
): CurveAssignment {
  return {
    assignmentId: assignment.assignmentUid,
    curveId: assignment.managedCurveUid,
    curveUid: assignment.managedCurveUid,
    krCurveTypeId: null,
    wellUid: assignment.managedWellUid,
    managedWellUid: assignment.managedWellUid,
    sourceUid: assignment.managedSourceUid,
    managedSourceUid: assignment.managedSourceUid,
    observedMnemonic: null,
    normalizedMnemonic: null,
    stackIndex: assignment.stackIndex,
    visible: assignment.visible,
    scaleMin,
    scaleMax,
    scaleDirection: assignment.scaleDirection,
    scaleType: assignment.scaleType,
    rangeMode: assignment.rangeMode,
    color: assignment.color,
    lineVisible: assignment.lineVisible,
    lineStyle: assignment.lineStyle,
    lineWidth: assignment.lineWidth,
    lineOpacity: assignment.lineOpacity,
    positionAnchor: assignment.positionAnchor,
    horizontalOffsetPct: assignment.horizontalOffsetPct,
    clipToTrack: assignment.clipToTrack,
    fillSide: assignment.fillSide,
    fillColor: assignment.fillColor,
    fillOpacity: assignment.fillOpacity,
    infillSource:
      assignment.infillSource === 'lithology'
        ? 'interval-column'
        : 'solid',
    infillPattern:
      assignment.infillPattern === 'hatch'
      || assignment.infillPattern === 'dots'
        ? assignment.infillPattern
        : 'solid',
    infillIntervalColumn:
      assignment.infillIntervalColumn === 'biostratigraphy'
      || assignment.infillIntervalColumn === 'formation'
      || assignment.infillIntervalColumn === 'facies'
      || assignment.infillIntervalColumn === 'other'
        ? assignment.infillIntervalColumn
        : 'lithology',
    pairedCurveId: assignment.pairedManagedCurveUid ?? undefined,
    displayPriority:
      assignment.displayPriority === 'background'
        ? 'back'
        : assignment.displayPriority === 'foreground'
          ? 'front'
          : 'normal',
    showQaqcWarnings: assignment.showQaqcWarnings,
    showNullGaps: assignment.showNullGaps,
    showOutOfRange: assignment.showOutOfRange,
  };
}

function toLegacyCurveTrack(
  track: CurveTrackV21,
  curveIndex: ReadonlyMap<ManagedCurveUid, CurveCatalogItemV21>,
  issues: OriginalWdvAdapterIssue[],
): CurveTrack {
  const curves = [...track.curves]
    .sort((left, right) => left.stackIndex - right.stackIndex)
    .flatMap((assignment) => {
      if (!curveIndex.has(assignment.managedCurveUid)) {
        issues.push({
          code: 'unresolved_assignment_curve',
          message:
            `Assignment ${assignment.assignmentUid} references unavailable `
            + `curve ${assignment.managedCurveUid}`,
          trackUid: track.trackUid,
          assignmentUid: assignment.assignmentUid,
          managedCurveUid: assignment.managedCurveUid,
        });
        return [];
      }
      if (assignment.scaleMin === null || assignment.scaleMax === null) {
        issues.push({
          code: 'missing_scale_bounds',
          message:
            `Assignment ${assignment.assignmentUid} for curve `
            + `${assignment.managedCurveUid} has no backend-owned scale bounds.`,
          trackUid: track.trackUid,
          assignmentUid: assignment.assignmentUid,
          managedCurveUid: assignment.managedCurveUid,
        });
        return [];
      }
      // Pass narrowed scaleMin/scaleMax as explicit number arguments (TypeScript narrows
      // after the null guard above but cannot propagate through the object type).
      return [toLegacyAssignment(assignment, assignment.scaleMin, assignment.scaleMax)];
    });

  return {
    trackId: track.trackUid,
    trackIndex: track.trackIndex,
    title: track.title,
    widthPx: track.widthPx,
    visible: track.visible,
    trackType: 'curve',
    lattice: track.lattice,
    latticeSource: track.latticeSource,
    latticeOverride: track.latticeOverride,
    scaleMode: track.scaleMode,
    curves,
  };
}

function toLegacyDepthTrack(
  track: DepthTrackV21,
  issues: OriginalWdvAdapterIssue[],
): WellLogTrack {
  if (track.unit !== 'm' && track.unit !== 'ft') {
    const issue: OriginalWdvAdapterIssue = {
      code: 'unsupported_depth_unit',
      message:
        `Depth track ${track.trackUid} uses unsupported unit ${track.unit}; `
        + 'no frontend fallback is permitted.',
      trackUid: track.trackUid,
    };
    issues.push(issue);
    throw new Error(issue.message);
  }

  const unit = track.unit;

  return {
    trackId: track.trackUid,
    trackIndex: track.trackIndex,
    title: track.title,
    widthPx: track.widthPx,
    visible: track.visible,
    trackType: 'depth',
    depthBasis: track.depthBasis,
    unit,
  };
}

function toLegacyTrack(
  track: WellLogTrackV21,
  curveIndex: ReadonlyMap<ManagedCurveUid, CurveCatalogItemV21>,
  issues: OriginalWdvAdapterIssue[],
): WellLogTrack {
  return track.trackType === 'curve'
    ? toLegacyCurveTrack(track, curveIndex, issues)
    : toLegacyDepthTrack(track, issues);
}

function firstSelection(tracks: readonly WellLogTrack[]): SelectionRef {
  const first = tracks[0];
  if (!first) {
    return {
      kind: 'track',
      trackId: '__empty_wdv__',
    };
  }
  return {
    kind: 'track',
    trackId: first.trackId,
  };
}

function toLegacySelection(
  workspace: CanonicalWorkspaceV1,
  tracks: readonly WellLogTrack[],
  requestedSelection: CanonicalWdvSelection | undefined,
  issues: OriginalWdvAdapterIssue[],
): SelectionRef {
  const validated = validateCanonicalSelection(
    workspace.session,
    requestedSelection ?? (
      workspace.session.selectedTrackUid === null
        ? { kind: 'none' }
        : {
            kind: 'track',
            trackUid: workspace.session.selectedTrackUid,
          }
    ),
  );

  if (validated.kind === 'track') {
    return {
      kind: 'track',
      trackId: validated.trackUid,
    };
  }

  if (validated.kind === 'assignment') {
    return {
      kind: 'curve',
      trackId: validated.trackUid,
      assignmentId: validated.assignmentUid,
    };
  }

  issues.push({
    code: 'selection_fallback',
    message: 'Canonical workspace has no selected track; presentation fallback used',
  });
  return firstSelection(tracks);
}

function toLegacySamples(
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21,
): Record<string, readonly (readonly [number, number])[]> {
  const result: Record<
    string,
    readonly (readonly [number, number])[]
  > = {};

  for (const [managedCurveUid, samples] of samplesByManagedCurveUid) {
    result[managedCurveUid] = samples.map(
      (sample) => [sample.depth, sample.value] as const,
    );
  }
  return result;
}

function depthRange(
  workspace: CanonicalWorkspaceV1,
  issues: OriginalWdvAdapterIssue[],
): { min: number; max: number } {
  const minimum = workspace.viewerPackage.depthRange.minimum;
  const maximum = workspace.viewerPackage.depthRange.maximum;

  if (
    minimum === null
    || maximum === null
    || !Number.isFinite(minimum)
    || !Number.isFinite(maximum)
    || maximum <= minimum
  ) {
    issues.push({
      code: 'missing_depth_range',
      message: 'Canonical workspace does not contain a usable depth range',
    });
    return { min: 0, max: 1 };
  }

  return {
    min: minimum,
    max: maximum,
  };
}

function wellHeader(
  workspace: CanonicalWorkspaceV1,
  range: { min: number; max: number },
): WellHeader {
  return {
    wellName: workspace.viewerPackage.wellName,
    wellboreName: workspace.viewerPackage.wellboreName ?? 'Not supplied',
    field: 'Not supplied',
    operator: 'Not supplied',
    country: 'Not supplied',
    kb: 'Not supplied',
    gl: 'Not supplied',
    logStart: String(range.min),
    logEnd: String(range.max),
    sourceFile: 'Managed WDV workspace',
    msiIdentity: workspace.managedWellUid,
    tvdStatus: 'Not supplied',
  };
}

export function buildOriginalWdvPresentationModel(
  workspace: CanonicalWorkspaceV1,
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21 = new Map(),
  requestedSelection?: CanonicalWdvSelection,
): OriginalWdvPresentationModel {
  const issues: OriginalWdvAdapterIssue[] = [];
  const curveIndex = new Map(
    workspace.curves.map((curve) => [curve.managedCurveUid, curve]),
  );
  const curveCatalog = workspace.curves.flatMap((curve) => {
    const item = toLegacyCurve(curve);
    if (item !== null && curve.unit === null) {
      issues.push({
        code: 'missing_curve_unit',
        message: `Curve ${curve.managedCurveUid} has no backend-owned unit.`,
        managedCurveUid: curve.managedCurveUid,
      });
    }
    return item === null ? [] : [item];
  });
  const tracks = [...workspace.session.tracks]
    .sort((left, right) => left.trackIndex - right.trackIndex)
    .map((track) => toLegacyTrack(track, curveIndex, issues));

  const selection = toLegacySelection(
    workspace,
    tracks,
    requestedSelection,
    issues,
  );
  const curveSamplesByCurveId = toLegacySamples(
    samplesByManagedCurveUid,
  );
  const fullDepthRange = depthRange(workspace, issues);
  const header = wellHeader(workspace, fullDepthRange);

  const assignmentCounts = new Map<ManagedCurveUid, number>();
  for (const track of workspace.session.tracks) {
    if (track.trackType !== 'curve') continue;
    for (const assignment of track.curves) {
      assignmentCounts.set(
        assignment.managedCurveUid,
        (assignmentCounts.get(assignment.managedCurveUid) ?? 0) + 1,
      );
    }
  }

  const loadedCurves = curveCatalog.map((curve) => {
    const managedCurveUid = curve.curveId as ManagedCurveUid;
    const assignmentCount = assignmentCounts.get(managedCurveUid) ?? 0;
    return {
      managedCurveUid,
      curve,
      assigned: assignmentCount > 0,
      assignmentCount,
    };
  });

  const propertiesInputs: OriginalWdvPropertiesInputs = {
    tracks,
    selection,
    curveCatalog,
    wellHeader: header,
    curveSamplesByCurveId,
    fullDepthRange,
  };

  return {
    managedWellUid: workspace.managedWellUid,
    revision: workspace.session.revision,
    curveCatalog,
    loadedCurves,
    tracks,
    selection,
    wellHeader: header,
    curveSamplesByCurveId,
    fullDepthRange,
    propertiesInputs,
    issues,
  };
}
