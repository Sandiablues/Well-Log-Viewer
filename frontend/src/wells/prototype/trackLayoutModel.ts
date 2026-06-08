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

export interface CurveCatalogItem {
  curveId: string;
  mnemonic: string;
  description: string;
  unit: string;
  curveClass: CurveClass;
  defaultLattice: CurveLattice;
  defaultMin: number;
  defaultMax: number;
  defaultColor: string;
  recognised: boolean;
}

export interface CurveAssignment {
  assignmentId: string;
  curveId: string;
  stackIndex: number;
  visible: boolean;
  scaleMin: number;
  scaleMax: number;
  scaleDirection: 'normal' | 'reverse';
  color: string;
  lineStyle: LineStyle;
  lineWidth: number;
  fillSide: FillSide;
  fillColor: string;
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
}

export interface DragCurvePayload {
  dragType: 'curve';
  curveId: string;
  fromTrackId?: string;
  assignmentId?: string;
}

export function makeCurveAssignment(curve: CurveCatalogItem, stackIndex: number): CurveAssignment {
  return {
    assignmentId: `assign-${curve.curveId}-${Date.now()}-${Math.round(Math.random() * 100000)}`,
    curveId: curve.curveId,
    stackIndex,
    visible: true,
    scaleMin: curve.defaultMin,
    scaleMax: curve.defaultMax,
    scaleDirection: curve.mnemonic === 'NPHI' || curve.mnemonic === 'TNPH' ? 'reverse' : 'normal',
    color: curve.defaultColor,
    lineStyle: 'solid',
    lineWidth: 1.8,
    fillSide: 'none',
    fillColor: 'rgba(47, 159, 99, 0.16)',
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
