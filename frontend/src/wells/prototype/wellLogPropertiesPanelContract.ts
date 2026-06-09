import type {
  CurveAssignment,
  CurveCatalogItem,
  SelectionRef,
  WellHeader,
  WellLogTrack,
} from './trackLayoutModel';
import { curveById, orderedCurves, resolveTrackLattice } from './trackLayoutModel';

export type PropertiesPanelTabKey = 'design' | 'info';

export interface PropertiesPanelRow {
  label: string;
  value: string;
  unit?: string;
  source?: string;
}

export interface PropertiesPanelSection {
  sectionId: string;
  title: string;
  rows: PropertiesPanelRow[];
}

export interface PropertiesPanelTabContract {
  tabKey: PropertiesPanelTabKey;
  label: string;
  sections: PropertiesPanelSection[];
}

export interface PropertiesPanelSelectedEntity {
  type: 'curve_assignment' | 'track' | 'lithology_track' | 'reserved_track';
  id: string;
  title: string;
  subtitle: string;
}

export interface PropertiesPanelContract {
  selectedEntity: PropertiesPanelSelectedEntity;
  selectedCurveAssignment: CurveAssignment | null;
  tabs: {
    design: PropertiesPanelTabContract;
    info: PropertiesPanelTabContract;
  };
}

export type CurveSampleTuple = readonly [number, number];

export interface ResolvePrototypePropertiesPanelArgs {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  curveCatalog: CurveCatalogItem[];
  wellHeader: WellHeader;
  curveSamplesByCurveId: Record<string, CurveSampleTuple[]>;
  fullDepthRange: { min: number; max: number };
}

function valueText(value: unknown): string {
  if (value === null || typeof value === 'undefined') return 'Not supplied';
  const text = String(value).trim();
  return text.length > 0 ? text : 'Not supplied';
}

function selectedTrackFrom(tracks: WellLogTrack[], selection: SelectionRef): WellLogTrack {
  return tracks.find((track) => track.trackId === selection.trackId) ?? tracks[0];
}

function selectedAssignmentFrom(track: WellLogTrack, selection: SelectionRef): CurveAssignment | null {
  if (track.trackType !== 'curve') return null;

  if (selection.kind === 'curve') {
    const explicit = track.curves.find((assignment) => assignment.assignmentId === selection.assignmentId);
    if (explicit) return explicit;
  }

  return orderedCurves(track)[0] ?? null;
}

function sampleStats(samples: CurveSampleTuple[] | undefined) {
  if (!samples || samples.length === 0) {
    return {
      count: '0',
      depthRange: 'Not supplied',
      valueRange: 'Not supplied',
      sampleStep: 'Not supplied',
      nullStatus: 'Not parsed in current fixture',
    };
  }

  let minDepth = Number.POSITIVE_INFINITY;
  let maxDepth = Number.NEGATIVE_INFINITY;
  let minValue = Number.POSITIVE_INFINITY;
  let maxValue = Number.NEGATIVE_INFINITY;

  samples.forEach(([depth, value]) => {
    if (Number.isFinite(depth)) {
      minDepth = Math.min(minDepth, depth);
      maxDepth = Math.max(maxDepth, depth);
    }

    if (Number.isFinite(value)) {
      minValue = Math.min(minValue, value);
      maxValue = Math.max(maxValue, value);
    }
  });

  let sampleStep = 'Not supplied';
  if (samples.length > 1) {
    const diffs: number[] = [];
    for (let i = 1; i < Math.min(samples.length, 200); i += 1) {
      const diff = samples[i][0] - samples[i - 1][0];
      if (Number.isFinite(diff) && diff > 0) diffs.push(Number(diff.toFixed(6)));
    }

    if (diffs.length > 0) {
      const sorted = [...diffs].sort((a, b) => a - b);
      const median = sorted[Math.floor(sorted.length / 2)];
      sampleStep = String(Number(median.toFixed(4)));
    }
  }

  return {
    count: String(samples.length),
    depthRange: Number.isFinite(minDepth) && Number.isFinite(maxDepth)
      ? `${minDepth.toFixed(1)}–${maxDepth.toFixed(1)}`
      : 'Not supplied',
    valueRange: Number.isFinite(minValue) && Number.isFinite(maxValue)
      ? `${Number(minValue.toFixed(4))}–${Number(maxValue.toFixed(4))}`
      : 'Not supplied',
    sampleStep,
    nullStatus: 'Null count not parsed in current fixture',
  };
}

function selectedEntityFor(
  track: WellLogTrack,
  assignment: CurveAssignment | null,
  curveCatalog: CurveCatalogItem[],
): PropertiesPanelSelectedEntity {
  if (track.trackType === 'curve' && assignment) {
    const curve = curveById(curveCatalog, assignment.curveId);
    return {
      type: 'curve_assignment',
      id: assignment.assignmentId,
      title: curve.mnemonic,
      subtitle: `${track.title} · ${curve.description}`,
    };
  }

  if (track.trackType === 'curve') {
    return {
      type: 'track',
      id: track.trackId,
      title: track.title,
      subtitle: 'Curve track · no curve assignment selected',
    };
  }

  if (track.trackType === 'lithology') {
    return {
      type: 'lithology_track',
      id: track.trackId,
      title: track.title,
      subtitle: `${track.sourceName} · ${track.wellName}`,
    };
  }

  if (track.trackType === 'raster' || track.trackType === 'marker' || track.trackType === 'interval') {
    return {
      type: 'reserved_track',
      id: track.trackId,
      title: track.title,
      subtitle: track.reservedReason,
    };
  }

  return {
    type: 'track',
    id: track.trackId,
    title: track.title,
    subtitle: `${track.trackType} track`,
  };
}

function designSection(
  track: WellLogTrack,
  assignment: CurveAssignment | null,
  curveCatalog: CurveCatalogItem[],
): PropertiesPanelSection {
  if (track.trackType === 'curve' && assignment) {
    const curve = curveById(curveCatalog, assignment.curveId);
    const lattice = resolveTrackLattice(track, curveCatalog);

    return {
      sectionId: 'design-parameters',
      title: 'Curve Design Parameters',
      rows: [
        { label: 'Curve', value: curve.mnemonic },
        { label: 'Curve class', value: curve.curveClass },
        { label: 'Unit', value: curve.unit },
        { label: 'Scale type', value: valueText(assignment.scaleType ?? (curve.defaultLattice === 'logarithmic' ? 'log' : 'linear')) },
        { label: 'Range mode', value: valueText(assignment.rangeMode ?? 'fixed') },
        { label: 'Scale min', value: String(assignment.scaleMin), unit: curve.unit },
        { label: 'Scale max', value: String(assignment.scaleMax), unit: curve.unit },
        { label: 'Scale direction', value: assignment.scaleDirection },
        { label: 'Line visible', value: valueText(assignment.lineVisible ?? true) },
        { label: 'Color', value: assignment.color },
        { label: 'Line style', value: assignment.lineStyle },
        { label: 'Line width', value: String(assignment.lineWidth) },
        { label: 'Line opacity', value: String(assignment.lineOpacity ?? 100), unit: '%' },
        { label: 'Position', value: valueText(assignment.positionAnchor ?? 'center') },
        { label: 'Offset', value: String(assignment.horizontalOffsetPct ?? 0), unit: '%' },
        { label: 'Clip to track', value: valueText(assignment.clipToTrack ?? true) },
        { label: 'Infill mode', value: assignment.fillSide === 'none' ? 'Off' : assignment.fillSide },
        { label: 'Infill source', value: valueText(assignment.infillSource ?? 'solid') },
        { label: 'Interval column', value: valueText(assignment.infillIntervalColumn ?? 'lithology') },
        { label: 'Pattern', value: valueText(assignment.infillPattern ?? 'solid') },
        { label: 'Paired curve', value: valueText(assignment.pairedCurveId) },
        { label: 'Infill opacity', value: String(assignment.fillOpacity ?? 55), unit: '%' },
        { label: 'Fill color', value: assignment.fillColor },
        { label: 'Display priority', value: valueText(assignment.displayPriority ?? 'normal') },
        { label: 'QAQC warnings', value: valueText(assignment.showQaqcWarnings ?? true) },
        { label: 'Null gaps', value: valueText(assignment.showNullGaps ?? true) },
        { label: 'Out-of-range', value: valueText(assignment.showOutOfRange ?? true) },
        { label: 'Track', value: track.title },
        { label: 'Track lattice', value: lattice.lattice },
        { label: 'Track scale mode', value: track.scaleMode },
      ],
    };
  }

  if (track.trackType === 'curve') {
    const lattice = resolveTrackLattice(track, curveCatalog);
    return {
      sectionId: 'design-parameters',
      title: 'Track Design Parameters',
      rows: [
        { label: 'Track', value: track.title },
        { label: 'Track type', value: 'Curve track' },
        { label: 'Lattice', value: lattice.lattice },
        { label: 'Scale mode', value: track.scaleMode },
        { label: 'Width', value: String(track.widthPx), unit: 'px' },
        { label: 'Curve count', value: String(track.curves.length) },
      ],
    };
  }

  return {
    sectionId: 'design-parameters',
    title: 'Track Design Parameters',
    rows: [
      { label: 'Track', value: track.title },
      { label: 'Track type', value: track.trackType },
      { label: 'Width', value: String(track.widthPx), unit: 'px' },
      { label: 'Visible', value: valueText(track.visible) },
    ],
  };
}

function curveMetadataSection(
  track: WellLogTrack,
  assignment: CurveAssignment | null,
  curveCatalog: CurveCatalogItem[],
  curveSamplesByCurveId: Record<string, CurveSampleTuple[]>,
): PropertiesPanelSection | null {
  if (track.trackType !== 'curve' || !assignment) return null;

  const curve = curveById(curveCatalog, assignment.curveId);
  const stats = sampleStats(curveSamplesByCurveId[curve.curveId]);

  return {
    sectionId: 'curve-metadata',
    title: 'Curve Metadata',
    rows: [
      { label: 'Mnemonic', value: curve.mnemonic, source: 'LAS curve section' },
      { label: 'Description', value: curve.description, source: 'LAS curve section' },
      { label: 'Unit', value: curve.unit, source: 'LAS curve section' },
      { label: 'Curve class', value: curve.curveClass, source: 'Prototype classification' },
      { label: 'Recognized', value: valueText(curve.recognised), source: 'Prototype classification' },
      { label: 'Sample count', value: stats.count, source: 'LAS sample fixture' },
      { label: 'Sample value range', value: stats.valueRange, unit: curve.unit, source: 'LAS sample fixture' },
      { label: 'Null status', value: stats.nullStatus, source: 'Current parser limitation' },
    ],
  };
}

function logMetadataSection(
  wellHeader: WellHeader,
  fullDepthRange: { min: number; max: number },
  selectedAssignment: CurveAssignment | null,
  curveSamplesByCurveId: Record<string, CurveSampleTuple[]>,
): PropertiesPanelSection {
  const stats = selectedAssignment ? sampleStats(curveSamplesByCurveId[selectedAssignment.curveId]) : null;

  const rows: PropertiesPanelRow[] = [
    { label: 'Source LAS file', value: valueText(wellHeader.sourceFile), source: 'LAS fixture' },
    { label: 'LAS version', value: valueText(wellHeader.lasVersion), source: 'LAS ~VERSION' },
    { label: 'Wrap mode', value: valueText(wellHeader.lasWrap), source: 'LAS ~VERSION' },
    { label: 'LAS producer', value: valueText(wellHeader.lasProducer), source: 'LAS ~VERSION' },
    { label: 'LAS program', value: valueText(wellHeader.lasProgram), source: 'LAS ~VERSION' },
    { label: 'LAS creation date', value: valueText(wellHeader.lasCreationDate), source: 'LAS ~VERSION' },
    { label: 'DLIS creation date', value: valueText(wellHeader.dlisCreationDate), source: 'LAS ~VERSION' },
    { label: 'DLIS source name', value: valueText(wellHeader.dlisSourceName), source: 'LAS ~VERSION' },
    { label: 'Log date', value: valueText(wellHeader.logDate), source: 'LAS ~WELL' },
    { label: 'Service company', value: valueText(wellHeader.serviceCompany), source: 'LAS ~WELL' },
    { label: 'Run number', value: valueText(wellHeader.runNumber), source: 'LAS ~PARAMETER' },
    { label: 'Logging unit location', value: valueText(wellHeader.loggingUnitLocation), source: 'LAS ~PARAMETER' },
    { label: 'Logging unit number', value: valueText(wellHeader.loggingUnitNumber), source: 'LAS ~PARAMETER' },
    { label: 'Service order number', value: valueText(wellHeader.serviceOrderNumber), source: 'LAS ~PARAMETER' },
    { label: 'Start depth', value: valueText(wellHeader.startDepth ?? wellHeader.logStart), source: 'LAS STRT' },
    { label: 'Stop depth', value: valueText(wellHeader.stopDepth ?? wellHeader.logEnd), source: 'LAS STOP' },
    { label: 'Step', value: valueText(wellHeader.step), source: 'LAS STEP' },
    { label: 'Null value', value: valueText(wellHeader.nullValue), source: 'LAS NULL' },
    { label: 'Top log interval', value: valueText(wellHeader.topLogInterval), source: 'LAS TLI' },
    { label: 'Bottom log interval', value: valueText(wellHeader.bottomLogInterval), source: 'LAS BLI' },
    { label: 'Driller TD', value: valueText(wellHeader.drillerTotalDepth), source: 'LAS TDD' },
    { label: 'Logger TD', value: valueText(wellHeader.loggerTotalDepth), source: 'LAS TDL' },
    { label: 'Drilling measured from', value: valueText(wellHeader.drillingMeasuredFrom), source: 'LAS DMF' },
    { label: 'Logging measured from', value: valueText(wellHeader.loggingMeasuredFrom), source: 'LAS LMF' },
    { label: 'Depth reference above permanent datum', value: valueText(wellHeader.depthReferenceAbovePermanentDatum), source: 'LAS APD' },
    { label: 'Full fixture MD range', value: `${fullDepthRange.min}–${fullDepthRange.max}`, unit: 'ft', source: 'Parsed sample fixture' },
  ];

  if (stats) {
    rows.push(
      { label: 'Selected-curve MD range', value: stats.depthRange, unit: 'ft', source: 'LAS sample fixture' },
      { label: 'Selected-curve sample step', value: stats.sampleStep, unit: 'ft', source: 'Derived from samples' },
    );
  }

  return {
    sectionId: 'log-metadata',
    title: 'Log Metadata',
    rows,
  };
}

function wellMetadataSection(wellHeader: WellHeader): PropertiesPanelSection {
  return {
    sectionId: 'well-metadata',
    title: 'Well Metadata',
    rows: [
      { label: 'Well', value: valueText(wellHeader.wellName), source: 'LAS WELL / WN' },
      { label: 'Wellbore', value: valueText(wellHeader.wellboreName), source: 'Prototype assignment' },
      { label: 'Field', value: valueText(wellHeader.field), source: 'LAS FLD / FN' },
      { label: 'Operator / company', value: valueText(wellHeader.operator ?? wellHeader.companyName), source: 'LAS COMP / CN' },
      { label: 'Country', value: valueText(wellHeader.country), source: 'LAS CTRY / NATI' },
      { label: 'State', value: valueText(wellHeader.state), source: 'LAS STAT' },
      { label: 'County', value: valueText(wellHeader.county), source: 'LAS CNTY / COUN' },
      { label: 'Location', value: valueText(wellHeader.fieldLocation), source: 'LAS LOC / FL' },
      { label: 'Location line 1', value: valueText(wellHeader.fieldLocationLine1), source: 'LAS FL1' },
      { label: 'API number', value: valueText(wellHeader.apiNumber), source: 'LAS API / APIN' },
      { label: 'UWI', value: valueText(wellHeader.uniqueWellId), source: 'LAS UWI' },
      { label: 'Latitude', value: valueText(wellHeader.latitude), source: 'LAS LATI' },
      { label: 'Longitude', value: valueText(wellHeader.longitude), source: 'LAS LONG' },
      { label: 'Permanent datum', value: valueText(wellHeader.permanentDatum), source: 'LAS PDAT' },
      { label: 'Ground level elevation', value: valueText(wellHeader.groundElevation ?? wellHeader.gl), source: 'LAS EGL / EPD' },
      { label: 'KB elevation', value: valueText(wellHeader.kbElevation ?? wellHeader.kb), source: 'LAS EKB' },
      { label: 'Permanent datum elevation', value: valueText(wellHeader.permanentDatumElevation), source: 'LAS EPD' },
      { label: 'TVD status', value: valueText(wellHeader.tvdStatus), source: 'Prototype normalization' },
      { label: 'MSI identity', value: valueText(wellHeader.msiIdentity), source: 'Prototype MSI status' },
    ],
  };
}

function qaqcMetadataSection(
  track: WellLogTrack,
  assignment: CurveAssignment | null,
  curveCatalog: CurveCatalogItem[],
): PropertiesPanelSection {
  const rows: PropertiesPanelRow[] = [
    { label: 'Metadata scope', value: 'Prototype LAS fixture with verified header fields', source: 'Current implementation' },
    { label: 'Backend authority', value: 'Planned MSI / well-log metadata service', source: 'Architecture target' },
  ];

  if (track.trackType === 'curve' && assignment) {
    const curve = curveById(curveCatalog, assignment.curveId);
    rows.push(
      { label: 'Curve recognition', value: curve.recognised ? 'Recognized' : 'Unrecognized', source: 'Prototype classification' },
      { label: 'Display scale source', value: 'Current viewer assignment', source: 'Viewer layout contract' },
    );
  }

  rows.push(
    { label: 'Known parser gap', value: 'Header parser should populate these fields automatically from LAS, not hard-coded fixture data', source: 'WLV-METADATA-1' },
  );

  return {
    sectionId: 'qaqc-metadata',
    title: 'QAQC / Derived Metadata',
    rows,
  };
}

export function resolvePrototypePropertiesPanelContract(args: ResolvePrototypePropertiesPanelArgs): PropertiesPanelContract {
  const selectedTrack = selectedTrackFrom(args.tracks, args.selection);
  const selectedAssignment = selectedAssignmentFrom(selectedTrack, args.selection);
  const selectedEntity = selectedEntityFor(selectedTrack, selectedAssignment, args.curveCatalog);

  const infoSections: PropertiesPanelSection[] = [
    curveMetadataSection(selectedTrack, selectedAssignment, args.curveCatalog, args.curveSamplesByCurveId),
    logMetadataSection(args.wellHeader, args.fullDepthRange, selectedAssignment, args.curveSamplesByCurveId),
    wellMetadataSection(args.wellHeader),
    qaqcMetadataSection(selectedTrack, selectedAssignment, args.curveCatalog),
  ].filter((section): section is PropertiesPanelSection => Boolean(section));

  return {
    selectedEntity,
    selectedCurveAssignment: selectedAssignment,
    tabs: {
      design: {
        tabKey: 'design',
        label: 'Curve Design',
        sections: [
          designSection(selectedTrack, selectedAssignment, args.curveCatalog),
        ],
      },
      info: {
        tabKey: 'info',
        label: 'Curve / Log / Well Info',
        sections: infoSections,
      },
    },
  };
}
