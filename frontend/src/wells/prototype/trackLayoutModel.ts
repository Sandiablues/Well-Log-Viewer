export type TrackType = 'depth' | 'curve' | 'lithology' | 'raster' | 'interval' | 'core' | 'completion';
export type ActiveTrackType = 'depth' | 'curve' | 'interval' | 'core' | 'completion';
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
  | 'porosity'
  | 'unknown';
export type LineStyle = 'solid' | 'dash' | 'dot';
export type FillSide = 'none' | 'left' | 'right' | 'between';
export type InfillSource = 'solid' | 'pattern' | 'interval-column';
export type InfillPattern = 'solid' | 'hatch' | 'dots';
export type IntervalColumnType = 'lithology' | 'biostratigraphy' | 'formation' | 'facies' | 'other';
export type CurveScaleType = 'linear' | 'log';
export type CurveRangeMode = 'auto' | 'fixed';
export type CurvePositionAnchor = 'left' | 'center' | 'right';
export type CurveDisplayPriority = 'back' | 'normal' | 'front';

export type DepthRangeLocatorMode = 'content_extent' | 'viewport_extent' | 'auto';
export type DepthRangeLocatorPresentation = 'edge_arrows' | 'wall_bar' | 'data_bar';
export type DepthRangeLocatorSide = 'auto' | 'left' | 'right';

export interface DepthRangeLocatorConfig {
  enabled: boolean;
  sourceTrackId: string;
  mode: DepthRangeLocatorMode;
  presentation: DepthRangeLocatorPresentation;
  side: DepthRangeLocatorSide;
}

export type MacroCoreImagePlacement = 'left' | 'center' | 'right';

export interface MacroCoreImageConfig {
  enabled: boolean;
  topMd: number;
  baseMd: number;
  placement: MacroCoreImagePlacement;
  horizontalOffsetPx: number;
}

export const DEFAULT_MACRO_CORE_IMAGE_CONFIG: MacroCoreImageConfig = {
  enabled: false,
  topMd: 0,
  baseMd: 0,
  placement: 'center',
  horizontalOffsetPx: 0,
};

export type TextOverlayHorizontalAnchor = 'left' | 'center' | 'right';
export type TextOverlayBackground = 'none' | 'light';
export type TextOverlayTextAlign = 'left' | 'center' | 'right';

export interface TextOverlayConfig {
  overlayUid: string;
  contentHtml: string;
  md: number;
  horizontalAnchor: TextOverlayHorizontalAnchor;
  horizontalOffset: number;
  verticalOffset: number;
  widthPercent: number;
  fontSize: number;
  color: string;
  background: TextOverlayBackground;
  textAlign: TextOverlayTextAlign;
}

export const DEFAULT_TEXT_OVERLAY_CONFIG: Omit<TextOverlayConfig, 'overlayUid' | 'md'> = {
  contentHtml: '<div>Text</div>',
  horizontalAnchor: 'center',
  horizontalOffset: 0,
  verticalOffset: 0,
  widthPercent: 70,
  fontSize: 11,
  color: '#1f2937',
  background: 'none',
  textAlign: 'left',
};

export const DEFAULT_DEPTH_RANGE_LOCATOR_CONFIG: DepthRangeLocatorConfig = {
  enabled: false,
  sourceTrackId: '',
  mode: 'auto',
  presentation: 'edge_arrows',
  side: 'auto',
};

export interface CurveCatalogItem {
  curveId: string;
  curveUid?: string | null;
  identityAliases?: string[];
  krCurveTypeId?: string | null;
  wellUid?: string | null;
  managedWellUid?: string | null;
  managedProductUid?: string | null;
  sourceUid?: string | null;
  managedSourceUid?: string | null;
  observedMnemonic?: string | null;
  normalizedMnemonic?: string | null;
  mnemonic: string;
  description: string;
  unit: string;
  curveClass: CurveClass;
  backendCurveFamily?: string | null;
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

export interface CurveScaleTick {
  value: number;
  label: string;
  normalizedPosition: number;
}

export type CorePresentationMode =
  | 'core_left_description_right'
  | 'description_left_core_right'
  | 'core_centered';

export interface CoreTrackAppearance {
  baseColor: string;
  brightness: number;
  shadingMode: 'flat' | 'cylindrical';
  shadingStrength: number;
  descriptionPresentationMode: CorePresentationMode;
  descriptionOverlayWidthPct: number;
  descriptionOverlayFontSize: number;
  descriptionOverlayShowMd: boolean;
}

export const DEFAULT_CORE_TRACK_APPEARANCE: CoreTrackAppearance = {
  baseColor: '#d7d9dd',
  brightness: 1,
  shadingMode: 'flat',
  shadingStrength: 0.38,
  descriptionPresentationMode: 'core_centered',
  descriptionOverlayWidthPct: 42,
  descriptionOverlayFontSize: 10,
  descriptionOverlayShowMd: true,
};

export interface CompletionTrackAppearance {
  schematicPosition: 'left' | 'center' | 'right';
  schematicWidthPx: number;
  symbolScale: number;
  lineWeight: number;
  showLabels: boolean;
  labelPosition: 'left' | 'right' | 'auto';
  labelFontSize: number;
  labelOffsetPx: number;
  labelVerticalOffsetPx: number;
  labelMaxWidthPx: number;
  labelCollisionMode: 'auto' | 'off';
  labelWrap: boolean;
}

export const DEFAULT_COMPLETION_TRACK_APPEARANCE: CompletionTrackAppearance = {
  schematicPosition: 'center',
  schematicWidthPx: 44,
  symbolScale: 1,
  lineWeight: 2,
  showLabels: true,
  labelPosition: 'right',
  labelFontSize: 10,
  labelOffsetPx: 12,
  labelVerticalOffsetPx: 0,
  labelMaxWidthPx: 140,
  labelCollisionMode: 'auto',
  labelWrap: false,
};

export interface CurveAssignment {
  assignmentId: string;
  curveId: string;
  curveUid?: string | null;
  krCurveTypeId?: string | null;
  wellUid?: string | null;
  managedWellUid?: string | null;
  managedProductUid?: string | null;
  sourceUid?: string | null;
  managedSourceUid?: string | null;
  observedMnemonic?: string | null;
  normalizedMnemonic?: string | null;
  displayName?: string | null;
  curveFamily?: string | null;
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
  /** Backend-owned response-only scale ticks. */
  scaleTicks?: CurveScaleTick[];
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
  managedWellUid?: string;
  ownerWellName?: string;
  trackIndex: number;
  title: string;
  widthPx: number;
  visible: boolean;
  depthRangeLocator?: DepthRangeLocatorConfig;
  macroCoreImage?: MacroCoreImageConfig;
  textOverlays?: TextOverlayConfig[];
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
  trackType: 'raster' | 'interval' | 'core' | 'completion';
  reservedReason: string;
  rendererType?: string | null;
  trackRole?: string | null;
  coreAppearance?: CoreTrackAppearance;
  completionAppearance?: CompletionTrackAppearance;
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

export function makeCurveAssignment(
  curve: CurveCatalogItem,
  stackIndex: number,
  canonicalAssignmentUid?: string,
): CurveAssignment {
  return {
    // Durable identity is always backend-issued UUIDv7. This token is transient frontend-only state.
    assignmentId: canonicalAssignmentUid ?? `transient-assignment-${curve.curveUid ?? curve.curveId}-${stackIndex}`,
    curveId: curve.curveId,
    curveUid: curve.curveUid ?? curve.curveId,
    krCurveTypeId: curve.krCurveTypeId ?? null,
    wellUid: curve.wellUid ?? null,
    managedWellUid: curve.managedWellUid ?? null,
    managedProductUid: curve.managedProductUid ?? null,
    sourceUid: curve.sourceUid ?? null,
    observedMnemonic: curve.observedMnemonic ?? curve.mnemonic,
    normalizedMnemonic: curve.normalizedMnemonic ?? curve.mnemonic,
    displayName: curve.description,
    curveFamily: undefined,
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
