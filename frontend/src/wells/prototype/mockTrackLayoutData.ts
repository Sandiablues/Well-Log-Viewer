import type { CurveCatalogItem, WellHeader, WellLogTrack } from './trackLayoutModel';
import { makeCurveAssignment } from './trackLayoutModel';

export const curveCatalog: CurveCatalogItem[] = [
  { curveId: 'curve-dept', mnemonic: 'DEPT', description: 'Measured Depth', unit: 'm', curveClass: 'depth', defaultLattice: 'linear', defaultMin: 0, defaultMax: 1, defaultColor: '#334155', recognised: true },
  { curveId: 'curve-tvd', mnemonic: 'TVD', description: 'True Vertical Depth', unit: 'm', curveClass: 'depth', defaultLattice: 'linear', defaultMin: 0, defaultMax: 1, defaultColor: '#64748b', recognised: true },
  { curveId: 'curve-gr', mnemonic: 'GR', description: 'Gamma Ray', unit: 'API', curveClass: 'gamma', defaultLattice: 'linear', defaultMin: 0, defaultMax: 150, defaultColor: '#2f9f63', recognised: true },
  { curveId: 'curve-sp', mnemonic: 'SP', description: 'Spontaneous Potential', unit: 'mV', curveClass: 'gamma', defaultLattice: 'linear', defaultMin: -100, defaultMax: 100, defaultColor: '#ef4444', recognised: true },
  { curveId: 'curve-cali', mnemonic: 'CALI', description: 'Caliper', unit: 'in', curveClass: 'borehole', defaultLattice: 'linear', defaultMin: 6, defaultMax: 16, defaultColor: '#1d70ff', recognised: true },
  { curveId: 'curve-bit', mnemonic: 'BIT', description: 'Bit Size', unit: 'in', curveClass: 'borehole', defaultLattice: 'linear', defaultMin: 6, defaultMax: 16, defaultColor: '#6b7280', recognised: true },
  { curveId: 'curve-lld', mnemonic: 'LLD', description: 'Deep Laterolog Resistivity', unit: 'ohm.m', curveClass: 'resistivity', defaultLattice: 'logarithmic', defaultMin: 0.2, defaultMax: 2000, defaultColor: '#111827', recognised: true },
  { curveId: 'curve-ilm', mnemonic: 'ILM', description: 'Medium Induction Resistivity', unit: 'ohm.m', curveClass: 'resistivity', defaultLattice: 'logarithmic', defaultMin: 0.2, defaultMax: 2000, defaultColor: '#dc2626', recognised: true },
  { curveId: 'curve-msfl', mnemonic: 'MSFL', description: 'Micro Spherically Focused Resistivity', unit: 'ohm.m', curveClass: 'resistivity', defaultLattice: 'logarithmic', defaultMin: 0.2, defaultMax: 2000, defaultColor: '#2563eb', recognised: true },
  { curveId: 'curve-rhob', mnemonic: 'RHOB', description: 'Bulk Density', unit: 'g/cc', curveClass: 'density', defaultLattice: 'linear', defaultMin: 1.95, defaultMax: 2.95, defaultColor: '#c026d3', recognised: true },
  { curveId: 'curve-tnph', mnemonic: 'TNPH', description: 'Thermal Neutron Porosity', unit: 'v/v', curveClass: 'neutron', defaultLattice: 'linear', defaultMin: 0.45, defaultMax: -0.15, defaultColor: '#0ea5e9', recognised: true },
  { curveId: 'curve-pef', mnemonic: 'PEF', description: 'Photo-Electric Factor', unit: 'b/e', curveClass: 'lithology', defaultLattice: 'linear', defaultMin: 0, defaultMax: 10, defaultColor: '#16a34a', recognised: true },
  { curveId: 'curve-dt', mnemonic: 'DT', description: 'Sonic Transit Time', unit: 'us/ft', curveClass: 'sonic', defaultLattice: 'linear', defaultMin: 40, defaultMax: 140, defaultColor: '#7c3aed', recognised: true },
  { curveId: 'curve-sw', mnemonic: 'SW', description: 'Water Saturation', unit: 'v/v', curveClass: 'porosity', defaultLattice: 'linear', defaultMin: 0, defaultMax: 1, defaultColor: '#0891b2', recognised: true },
  { curveId: 'curve-vsh', mnemonic: 'VSH', description: 'Shale Volume', unit: 'v/v', curveClass: 'lithology', defaultLattice: 'linear', defaultMin: 0, defaultMax: 1, defaultColor: '#84cc16', recognised: true },
];

const curve = (curveId: string): CurveCatalogItem => {
  const item = curveCatalog.find((entry) => entry.curveId === curveId);
  if (!item) {
    throw new Error(`Missing mock curve: ${curveId}`);
  }
  return item;
};

export const initialTracks: WellLogTrack[] = [
  {
    trackId: 'track-depth-md',
    trackIndex: 0,
    trackType: 'depth',
    title: 'DEPTH',
    depthBasis: 'MD',
    unit: 'm',
    widthPx: 86,
    visible: true,
  },
  {
    trackId: 'track-gamma-borehole',
    trackIndex: 1,
    trackType: 'curve',
    title: 'GR / SP / CALI',
    widthPx: 220,
    visible: true,
    lattice: 'linear',
    latticeSource: 'front_curve_default',
    latticeOverride: false,
    scaleMode: 'per_curve',
    curves: [
      makeCurveAssignment(curve('curve-gr'), 0),
      makeCurveAssignment(curve('curve-sp'), 1),
      makeCurveAssignment(curve('curve-cali'), 2),
    ],
  },
  {
    trackId: 'track-resistivity',
    trackIndex: 2,
    trackType: 'curve',
    title: 'RESISTIVITY',
    widthPx: 250,
    visible: true,
    lattice: 'logarithmic',
    latticeSource: 'front_curve_default',
    latticeOverride: false,
    scaleMode: 'shared',
    curves: [
      makeCurveAssignment(curve('curve-lld'), 0),
      makeCurveAssignment(curve('curve-ilm'), 1),
      makeCurveAssignment(curve('curve-msfl'), 2),
    ],
  },
  {
    trackId: 'track-depth-tvd',
    trackIndex: 3,
    trackType: 'depth',
    title: 'TVD',
    depthBasis: 'TVD',
    unit: 'm',
    widthPx: 86,
    visible: true,
  },
  {
    trackId: 'track-density-neutron',
    trackIndex: 4,
    trackType: 'curve',
    title: 'DENSITY / NEUTRON',
    widthPx: 230,
    visible: true,
    lattice: 'linear',
    latticeSource: 'front_curve_default',
    latticeOverride: false,
    scaleMode: 'dual',
    curves: [
      makeCurveAssignment(curve('curve-rhob'), 0),
      makeCurveAssignment(curve('curve-tnph'), 1),
    ],
  },
];

export const wellHeader: WellHeader = {
  wellName: '34/10-23 S',
  wellboreName: '34/10-23 SA',
  field: 'Example Field',
  operator: 'Example Operator',
  country: 'Norway',
  kb: '25.4 m',
  gl: '0.0 m',
  logStart: '2340.0 m MD',
  logEnd: '4582.5 m MD',
  sourceFile: '341023S_SA.las',
  msiIdentity: 'msi-wellbore-34-10-23-sa',
  tvdStatus: 'Available in mock trajectory',
};
