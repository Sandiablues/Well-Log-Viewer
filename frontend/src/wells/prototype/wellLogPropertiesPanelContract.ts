import type {
  CurveAssignment,
  CurveCatalogItem,
  SelectionRef,
  WellLogTrack,
} from './trackLayoutModel';
import { curveById, orderedCurves, resolveTrackLattice } from './trackLayoutModel';
import type { WdvIdentityMetadataContract, WdvMetadataSection, WdvMetadataValue } from '../contracts/wdvIdentityMetadataContract';
import { metadataSection } from '../contracts/wdvIdentityMetadataContract';
import {
  resolveManagedCurveContract,
  resolveManagedCurveError,
  type ManagedCurveSampleContractsByCurveId,
  type ManagedCurveSamplesPayload,
} from './managedCurveSamples';

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

export interface ResolvePrototypePropertiesPanelArgs {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  curveCatalog: CurveCatalogItem[];
  managedSampleContractsByCurveId: ManagedCurveSampleContractsByCurveId;
  managedSampleErrorsByCurveId: Record<string, string>;
  wdvIdentityMetadata: WdvIdentityMetadataContract | null;
  wdvIdentityMetadataError: string | null;
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

function compactNumber(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Not supplied';
  return Number(value.toPrecision(7)).toString();
}

function contractForAssignment(
  assignment: CurveAssignment,
  contracts: ManagedCurveSampleContractsByCurveId,
): ManagedCurveSamplesPayload | null {
  return resolveManagedCurveContract(contracts, {
    managedWellUid: assignment.managedWellUid ?? null,
    curveUid: assignment.curveUid ?? null,
    curveId: assignment.curveId,
  });
}

function backendSampleStatus(contract: ManagedCurveSamplesPayload): string {
  const rejected = contract.rejected_sample_count ?? 0;
  const nulls = contract.rejected_null_count ?? 0;
  const sentinels = contract.rejected_sentinel_count ?? 0;
  const nonfinite = contract.rejected_nonfinite_count ?? 0;
  return `${rejected} rejected (${nulls} null, ${sentinels} sentinel, ${nonfinite} non-finite)`;
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

  if (track.trackType === 'raster' || track.trackType === 'interval' || track.trackType === 'core') {
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
  contracts: ManagedCurveSampleContractsByCurveId,
  errors: Record<string, string>,
): PropertiesPanelSection | null {
  if (track.trackType !== 'curve' || !assignment) return null;

  const curve = curveById(curveCatalog, assignment.curveId);
  const sampleContract = contractForAssignment(assignment, contracts);
  const contractError = resolveManagedCurveError(errors, {
    managedWellUid: assignment.managedWellUid ?? null,
    curveUid: assignment.curveUid ?? null,
    curveId: assignment.curveId,
  });

  if (!sampleContract) {
    return {
      sectionId: 'curve-metadata',
      title: 'Curve Metadata',
      rows: [{
        label: 'Contract status',
        value: contractError ?? 'Backend curve sample contract not yet available',
        source: 'Backend curve sample contract',
      }],
    };
  }

  const mnemonic = sampleContract.observed_mnemonic
    ?? assignment.observedMnemonic
    ?? curve.mnemonic;
  const description = assignment.displayName
    ?? sampleContract.display_name
    ?? curve.description;
  const unit = sampleContract.value_unit ?? assignment.unit ?? curve.unit;
  const family = sampleContract.curve_family
    ?? assignment.curveFamily
    ?? curve.curveClass;
  const sampleSource = sampleContract.provenance?.sample_source ?? 'managed curve sample service';

  return {
    sectionId: 'curve-metadata',
    title: 'Curve Metadata',
    rows: [
      { label: 'Mnemonic', value: valueText(mnemonic), source: 'Backend curve sample contract' },
      { label: 'Description', value: valueText(description), source: 'Backend WDV assignment contract' },
      { label: 'Unit', value: valueText(unit), source: 'Backend curve sample contract' },
      { label: 'Curve family', value: valueText(family), source: 'Backend curve sample contract' },
      { label: 'Managed curve UID', value: valueText(sampleContract.managed_curve_uid), source: 'Backend curve sample contract' },
      { label: 'Sample count', value: valueText(sampleContract.sample_count), source: 'Backend curve sample contract' },
      { label: 'Raw numeric count', value: valueText(sampleContract.raw_numeric_sample_count), source: 'Backend curve sample contract' },
      {
        label: 'Curve depth range',
        value: `${compactNumber(sampleContract.depth_min)}–${compactNumber(sampleContract.depth_max)}`,
        unit: sampleContract.depth_unit ?? undefined,
        source: 'Backend curve sample contract',
      },
      {
        label: 'Sample value range',
        value: `${compactNumber(sampleContract.value_min)}–${compactNumber(sampleContract.value_max)}`,
        unit: unit ?? undefined,
        source: 'Backend curve sample contract',
      },
      {
        label: 'Robust value range (P5–P95)',
        value: `${compactNumber(sampleContract.robust_value_min)}–${compactNumber(sampleContract.robust_value_max)}`,
        unit: unit ?? undefined,
        source: 'Backend curve sample contract',
      },
      { label: 'Rejected samples', value: backendSampleStatus(sampleContract), source: 'Backend curve sample contract' },
      { label: 'Decimation stride', value: valueText(sampleContract.decimation_stride), source: 'Backend curve sample contract' },
      { label: 'Sample source', value: valueText(sampleSource), source: 'Backend curve sample provenance' },
    ],
  };
}

function contractValueText(item: WdvMetadataValue): string {
  return valueText(item.value);
}

function contractRows(
  section: WdvMetadataSection | null,
  source = 'Backend WDV metadata contract',
): PropertiesPanelRow[] {
  if (!section) return [];
  return section.values.map((item) => ({
    label: item.label,
    value: contractValueText(item),
    unit: item.unit ?? undefined,
    source: item.source?.trim() || source,
  }));
}

function unavailableMetadataRows(error: string | null): PropertiesPanelRow[] {
  return [{
    label: 'Contract status',
    value: error ?? 'Backend metadata not yet available',
    source: 'Backend WDV metadata contract',
  }];
}

function logMetadataSection(
  metadata: WdvIdentityMetadataContract | null,
  error: string | null,
): PropertiesPanelSection {
  const rows = [
    ...contractRows(metadataSection(metadata, 'source')),
    ...contractRows(metadataSection(metadata, 'depth')),
  ];
  return {
    sectionId: 'log-metadata',
    title: 'Log Metadata',
    rows: rows.length > 0 ? rows : unavailableMetadataRows(error),
  };
}

function wellMetadataSection(
  metadata: WdvIdentityMetadataContract | null,
  error: string | null,
): PropertiesPanelSection {
  const rows = contractRows(metadataSection(metadata, 'well'));
  return {
    sectionId: 'well-metadata',
    title: 'Well Metadata',
    rows: rows.length > 0 ? rows : unavailableMetadataRows(error),
  };
}

function qaqcMetadataSection(
  metadata: WdvIdentityMetadataContract | null,
  error: string | null,
): PropertiesPanelSection {
  const rows = contractRows(
    metadataSection(metadata, 'registration'),
    'Backend registration/provenance contract',
  );
  return {
    sectionId: 'qaqc-metadata',
    title: 'QAQC / Derived Metadata',
    rows: rows.length > 0 ? rows : unavailableMetadataRows(error),
  };
}

export function resolvePrototypePropertiesPanelContract(args: ResolvePrototypePropertiesPanelArgs): PropertiesPanelContract {
  const selectedTrack = selectedTrackFrom(args.tracks, args.selection);
  const selectedAssignment = selectedAssignmentFrom(selectedTrack, args.selection);
  const selectedEntity = selectedEntityFor(selectedTrack, selectedAssignment, args.curveCatalog);

  const infoSections: PropertiesPanelSection[] = [
    curveMetadataSection(selectedTrack, selectedAssignment, args.curveCatalog, args.managedSampleContractsByCurveId, args.managedSampleErrorsByCurveId),
    logMetadataSection(args.wdvIdentityMetadata, args.wdvIdentityMetadataError),
    wellMetadataSection(args.wdvIdentityMetadata, args.wdvIdentityMetadataError),
    qaqcMetadataSection(args.wdvIdentityMetadata, args.wdvIdentityMetadataError),
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
