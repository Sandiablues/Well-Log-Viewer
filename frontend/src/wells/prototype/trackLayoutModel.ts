export type TrackType = 'depth' | 'curve' | 'lithology' | 'raster' | 'marker' | 'interval';
export type ActiveTrackType = 'depth' | 'curve';
export type DepthBasis = 'MD' | 'TVD' | 'TVDSS';
export type CurveLattice = 'linear' | 'logarithmic';
export type LatticeSource = 'front_curve_default' | 'user_override' | 'template';
export type ScaleMode = 'shared' | 'per_curve' | 'dual' | 'normalized';
export type CurveClass =
  | 'depth'
  | 'gamma'
  | 'borehole'
  | 'resistivity'
  | 'density'
  | 'neutron'
  | 'sonic'
  | 'lithology'
  | 'porosity';
export type LineStyle = 'solid' | 'dash' | 'dot';
export type FillSide = 'none' | 'left' | 'right' | 'between';
export type InfillSource = 'solid' | 'pattern' | 'interval-column';
export type InfillPattern = 'solid' | 'hatch' | 'dots';
export type IntervalColumnType = 'lithology' | 'biostratigraphy' | 'formation' | 'facies' | 'other';
export type CurveScaleType = 'linear' | 'log';
export type CurveRangeMode = 'auto' | 'fixed';
export type CurvePositionAnchor = 'left' | 'center' | 'right';
export type CurveDisplayPriority = 'back' | 'normal' | 'front';

export interface CurveCatalogItem {
  curveId: string;
  curveUid?: string | null;
  identityAliases?: string[];
  krCurveTypeId?: string | null;
  wellUid?: string | null;
  managedWellUid?: string | null;
  sourceUid?: string | null;
  managedSourceUid?: string | null;
  observedMnemonic?: string | null;
  normalizedMnemonic?: string | null;
  mnemonic: string;
  description: string;
  unit: string;
  curveClass: CurveClass;
  defaultLattice: CurveLattice;
  defaultMin: number;
  defaultMax: number;
  defaultScaleDirection?: 'normal' | 'reverse';
  scaleSource?: string;
  displayScaleMode?: string;
  recommendedDisplayScaleMode?: string;
  standardDisplayMin?: number | null;
  standardDisplayMax?: number | null;
  robustObservedDisplayMin?: number | null;
  robustObservedDisplayMax?: number | null;
  scaleWarnings?: string[];
  visualSpanRatio?: number | null;
  defaultColor: string;
  recognised: boolean;
}

export interface CurveAssignment {
  assignmentId: string;
  curveId: string;
  curveUid?: string | null;
  krCurveTypeId?: string | null;
  wellUid?: string | null;
  managedWellUid?: string | null;
  sourceUid?: string | null;
  managedSourceUid?: string | null;
  observedMnemonic?: string | null;
  normalizedMnemonic?: string | null;
  /** Canonical backend assignment unit. This is projection data, not a catalog fallback. */
  unit?: string | null;
  /** Backend-owned display-policy provenance for this canonical assignment. */
  displayPolicySource?: 'curve' | 'family' | 'system_default' | null;
  /** True only when the backend requires human review of the display policy. */
  displayReviewRequired?: boolean;
  /** Backend-owned machine-readable display warning. */
  displayWarningCode?: string | null;
  /** Backend-owned human-readable display warning. */
  displayWarningMessage?: string | null;
  stackIndex: number;
  visible: boolean;
  scaleMin: number;
  scaleMax: number;
  scaleMinLabel?: string | null;
  scaleMaxLabel?: string | null;
  scaleDirection: 'normal' | 'reverse';
  scaleType?: CurveScaleType;
  rangeMode?: CurveRangeMode;
  color: string;
  lineVisible?: boolean;
  lineStyle: LineStyle;
  lineWidth: number;
  lineOpacity?: number;
  positionAnchor?: CurvePositionAnchor;
  horizontalOffsetPct?: number;
  clipToTrack?: boolean;
  fillSide: FillSide;
  fillColor: string;
  fillOpacity?: number;
  infillSource?: InfillSource;
  infillPattern?: InfillPattern;
  infillIntervalColumn?: IntervalColumnType;
  pairedCurveId?: string;
  displayPriority?: CurveDisplayPriority;
  showQaqcWarnings?: boolean;
  showNullGaps?: boolean;
  showOutOfRange?: boolean;
  /** Backend-owned range override intent projected through the canonical assignment. */
  rangeOverrideMode?: 'governed' | 'manual' | 'fit_to_curve' | 'fit_to_curve_p05_p95' | 'fit_to_curve_p01_p99';
  /** Manual bounds are meaningful only when rangeOverrideMode is manual. */
  manualScaleMin?: number | null;
  manualScaleMax?: number | null;
  /** Backend source used for the current effective range. */
  effectiveRangeSource?: 'governed' | 'manual' | 'fit_to_curve' | 'fit_to_curve_p05_p95' | 'fit_to_curve_p01_p99';
  /** Backend warning when the requested override could not be resolved. */
  overrideWarningCode?: string | null;
  overrideWarningMessage?: string | null;
  rangeEditStep?: number;
  rangeEditPrecision?: number;
}

interface BaseTrack {
  trackId: string;
  trackIndex: number;
  title: string;
  widthPx: number;
  visible: boolean;
}

export interface DepthTrack extends BaseTrack {
  trackType: 'depth';
  depthBasis: DepthBasis;
  unit: 'm' | 'ft';
}

export interface CurveTrack extends BaseTrack {
  trackType: 'curve';
  lattice: CurveLattice;
  latticeSource: LatticeSource;
  latticeOverride: boolean;
  scaleMode: ScaleMode;
  curves: CurveAssignment[];
}

export interface LithologyTrack extends BaseTrack {
  trackType: 'lithology';
  sourceName: string;
  wellName: string;
}

export interface ReservedTrack extends BaseTrack {
  trackType: 'raster' | 'marker' | 'interval';
  reservedReason: string;
}

export type WellLogTrack = DepthTrack | CurveTrack | LithologyTrack | ReservedTrack;

export interface SelectedTrackRef {
  kind: 'track';
  trackId: string;
}

export interface SelectedCurveRef {
  kind: 'curve';
  trackId: string;
  assignmentId: string;
}

export type SelectionRef = SelectedTrackRef | SelectedCurveRef;

export interface WellHeader {
  wellName: string;
  wellboreName: string;
  field: string;
  operator: string;
  country: string;
  kb: string;
  gl: string;
  logStart: string;
  logEnd: string;
  sourceFile: string;
  msiIdentity: string;
  tvdStatus: string;

  lasVersion?: string;
  lasWrap?: string;
  lasProducer?: string;
  lasProgram?: string;
  lasCreationDate?: string;
  dlisCreationDate?: string;
  dlisSourceName?: string;

  companyName?: string;
  wellNameRaw?: string;
  fieldNameRaw?: string;
  fieldLocation?: string;
  fieldLocationLine1?: string;
  county?: string;
  state?: string;
  apiNumber?: string;
  uniqueWellId?: string;
  latitude?: string;
  longitude?: string;
  logDate?: string;

  drillingMeasuredFrom?: string;
  loggingMeasuredFrom?: string;
  permanentDatum?: string;
  kbElevation?: string;
  groundElevation?: string;
  permanentDatumElevation?: string;
  depthReferenceAbovePermanentDatum?: string;

  serviceCompany?: string;
  loggingUnitLocation?: string;
  loggingUnitNumber?: string;
  runNumber?: string;
  serviceOrderNumber?: string;

  startDepth?: string;
  stopDepth?: string;
  step?: string;
  nullValue?: string;
  topLogInterval?: string;
  bottomLogInterval?: string;
  drillerTotalDepth?: string;
  loggerTotalDepth?: string;

  engineer?: string;
  witness?: string;
  bitSize?: string;
  bottomHoleTemperature?: string;
  drillingFluidType?: string;
  drillingFluidDensity?: string;
  drillingFluidPH?: string;
}

export interface DragCurvePayload {
  dragType: 'curve';
  curveId: string;
  fromTrackId?: string;
  assignmentId?: string;
}

export function makeCurveAssignment(curve: CurveCatalogItem, stackIndex: number): CurveAssignment {
  return {
    assignmentId: `assign-${curve.curveUid ?? curve.curveId}-${Date.now()}-${Math.round(Math.random() * 100000)}`,
    curveId: curve.curveId,
    curveUid: curve.curveUid ?? curve.curveId,
    krCurveTypeId: curve.krCurveTypeId ?? null,
    wellUid: curve.wellUid ?? null,
    sourceUid: curve.sourceUid ?? null,
    observedMnemonic: curve.observedMnemonic ?? curve.mnemonic,
    normalizedMnemonic: curve.normalizedMnemonic ?? curve.mnemonic,
    stackIndex,
    visible: true,
    scaleMin: curve.defaultMin,
    scaleMax: curve.defaultMax,
    scaleDirection: curve.defaultScaleDirection ?? 'normal',
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
    displayPriority: 'normal',
    showQaqcWarnings: true,
    showNullGaps: true,
    showOutOfRange: true,
  };
}

export function curveById(curves: CurveCatalogItem[], curveId: string): CurveCatalogItem {
  const match = curves.find((curve) => curve.curveId === curveId);
  if (!match) {
    throw new Error(`Unknown curve id: ${curveId}`);
  }
  return match;
}

export function orderedCurves(track: CurveTrack): CurveAssignment[] {
  return [...track.curves].sort((a, b) => a.stackIndex - b.stackIndex);
}

export function renumberCurveStack(curves: CurveAssignment[]): CurveAssignment[] {
  return curves.map((curve, index) => ({ ...curve, stackIndex: index }));
}

export function resolveTrackLattice(
  track: CurveTrack,
  catalog: CurveCatalogItem[],
): { lattice: CurveLattice; source: LatticeSource; frontCurve?: CurveCatalogItem } {
  if (track.latticeOverride) {
    return { lattice: track.lattice, source: 'user_override' };
  }

  const frontAssignment = orderedCurves(track)[0];
  if (!frontAssignment) {
    return { lattice: track.lattice, source: track.latticeSource };
  }

  const frontCurve = curveById(catalog, frontAssignment.curveId);
  return {
    lattice: frontCurve.defaultLattice,
    source: 'front_curve_default',
    frontCurve,
  };
}

export function parseDragPayload(raw: string): DragCurvePayload | null {
  try {
    const parsed = JSON.parse(raw) as DragCurvePayload;
    return parsed.dragType === 'curve' ? parsed : null;
  } catch {
    return null;
  }
}
