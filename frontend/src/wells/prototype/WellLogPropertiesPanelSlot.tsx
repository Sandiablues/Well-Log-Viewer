import { type ReactElement, useEffect, useRef, useState } from 'react';
import {
  fullDepthRange,
  realCurveSamplesByCurveId,
  wellHeader,
} from './realLasTrackLayoutData';
import type {
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
  DepthBasis,
  FillSide,
  LineStyle,
  ScaleMode,
  SelectionRef,
  WellLogTrack,
} from './trackLayoutModel';
import {
  resolveTrackLattice,
} from './trackLayoutModel';
import type {
  PropertiesPanelSection,
  PropertiesPanelTabKey,
} from './wellLogPropertiesPanelContract';
import {
  resolvePrototypePropertiesPanelContract,
} from './wellLogPropertiesPanelContract';
import {
  findCurveForAssignment,
  normalizePropertiesSelection,
} from './propertiesSelectionModel';

const CURVE_TRACK_MIN_WIDTH = 120;
const CURVE_TRACK_MAX_WIDTH = 420;

function clampCurveTrackWidth(widthPx: number): number {
  if (!Number.isFinite(widthPx)) return 220;
  return Math.max(CURVE_TRACK_MIN_WIDTH, Math.min(CURVE_TRACK_MAX_WIDTH, Math.round(widthPx)));
}

function PropertiesContractTable({
  sections,
  collapsible = false,
  collapsed = false,
  onToggle,
}: {
  sections: PropertiesPanelSection[];
  collapsible?: boolean;
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  return (
    <div className={`wlv-properties-contract-table${collapsed ? ' is-collapsed' : ''}`}>
      {sections.map((section, sectionIndex) => {
        const canCollapseSection = collapsible && sectionIndex === 0;
        return (
          <section key={section.sectionId} className="wlv-properties-contract-section">
            <h3>
              {canCollapseSection ? (
                <button
                  type="button"
                  className="wlv-properties-collapse-toggle"
                  aria-expanded={!collapsed}
                  onClick={onToggle}
                >
                  <span>{collapsed ? '▸' : '▾'}</span>
                  <strong>{section.title}</strong>
                </button>
              ) : (
                section.title
              )}
            </h3>
            {canCollapseSection && collapsed ? null : (
              <table>
                <tbody>
                  {section.rows.map((row) => (
                    <tr key={`${section.sectionId}-${row.label}`}>
                      <th scope="row">{row.label}</th>
                      <td>
                        <span>{row.value}</span>
                        {row.unit ? <em>{row.unit}</em> : null}
                        {row.source ? <small>{row.source}</small> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}
    </div>
  );
}

function TrackDesignControls({
  track,
  curveCatalogItems,
  updateTrack,
}: {
  track: WellLogTrack;
  curveCatalogItems: CurveCatalogItem[];
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
}) {
  if (track.trackType === 'depth') {
    return (
      <div className="wlv-property-section wlv-properties-dark-section">
        <h3>Design Controls</h3>
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
          Depth track width is fixed in this prototype. Curve tracks can be resized from the toolbar.
        </div>
      </div>
    );
  }

  if (track.trackType === 'curve') {
    const lattice = resolveTrackLattice(track, curveCatalogItems);
    return (
      <div className="wlv-property-section wlv-properties-dark-section">
        <h3>Track Controls</h3>
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
          <input
            type="number"
            min={CURVE_TRACK_MIN_WIDTH}
            max={CURVE_TRACK_MAX_WIDTH}
            value={track.widthPx}
            onChange={(event) => updateTrack(track.trackId, { widthPx: clampCurveTrackWidth(Number(event.target.value)) })}
          />
        </label>
      </div>
    );
  }

  return (
    <div className="wlv-property-section wlv-properties-dark-section">
      <h3>Design Controls</h3>
      <div className="wlv-property-note">
        This selected item is read-only in the current prototype.
      </div>
    </div>
  );
}

export function resolvePropertiesEditorCurve(
  selectedTrack: WellLogTrack | undefined,
  selectedCurveAssignment: CurveAssignment | null,
): CurveAssignment | null {
  return selectedTrack?.trackType === 'curve'
    ? selectedCurveAssignment
    : null;
}

function CurveDesignControls({
  track,
  assignment,
  curveCatalogItems,
  updateCurveAssignment,
}: {
  track: CurveTrack;
  assignment: CurveAssignment;
  curveCatalogItems: CurveCatalogItem[];
  updateCurveAssignment: (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => void;
}) {
  const curve = findCurveForAssignment(curveCatalogItems, assignment);
  if (!curve) {
    return (
      <div className="wlv-property-section wlv-properties-dark-section">
        <h3>Curve Controls</h3>
        <div className="wlv-property-note">
          The selected curve is no longer available in the active well catalog.
        </div>
      </div>
    );
  }
  const scaleType = assignment.scaleType ?? (curve.defaultLattice === 'logarithmic' ? 'log' : 'linear');
  const lineVisible = assignment.lineVisible ?? true;
  const lineOpacity = assignment.lineOpacity ?? 100;
  const positionAnchor = assignment.positionAnchor ?? 'center';
  const horizontalOffsetPct = assignment.horizontalOffsetPct ?? 0;
  const clipToTrack = assignment.clipToTrack ?? true;
  const infillSource = assignment.infillSource ?? 'solid';
  const infillPattern = assignment.infillPattern ?? 'solid';
  const infillIntervalColumn = assignment.infillIntervalColumn ?? 'lithology';
  const fillOpacity = assignment.fillOpacity ?? 55;
  const displayPriority = assignment.displayPriority ?? 'normal';
  const showQaqcWarnings = assignment.showQaqcWarnings ?? true;
  const showNullGaps = assignment.showNullGaps ?? true;
  const showOutOfRange = assignment.showOutOfRange ?? true;

  const update = (patch: Partial<CurveAssignment>) => {
    updateCurveAssignment(track.trackId, assignment.assignmentId, patch);
  };

  return (
    <div className="wlv-property-section wlv-properties-dark-section wlv-curve-control-panel">
      <h3>Curve Controls</h3>
      <div className="wlv-selected-curve-title">
        <span className="wlv-curve-color" style={{ background: assignment.color }} />
        <strong>{curve.mnemonic}</strong>
        <span>{curve.description}</span>
      </div>

      <div className="wlv-curve-control-group">
        <h4>Scale</h4>
        <label>
          Scale type
          <select
            value={scaleType}
            onChange={(event) => update({ scaleType: event.target.value as CurveAssignment['scaleType'] })}
          >
            <option value="linear">Linear</option>
            <option value="log">Log</option>
          </select>
        </label>
        <label>
          Range mode
          <select
            value={assignment.rangeOverrideMode ?? 'governed'}
            onChange={(event) => {
              const rangeOverrideMode =
                event.target.value as NonNullable<CurveAssignment['rangeOverrideMode']>;
              update(
                rangeOverrideMode === 'manual'
                  ? {
                      rangeOverrideMode,
                      manualScaleMin: assignment.manualScaleMin ?? assignment.scaleMin,
                      manualScaleMax: assignment.manualScaleMax ?? assignment.scaleMax,
                    }
                  : {
                      rangeOverrideMode,
                      manualScaleMin: null,
                      manualScaleMax: null,
                    },
              );
            }}
          >
            <option value="governed">Governed</option>
            <option value="manual">Manual</option>
            <option value="fit_to_curve_p05_p95">Fit track to curve — P5–P95</option>
            <option value="fit_to_curve_p01_p99">Fit track to curve — P1–P99</option>
          </select>
        </label>
        <label>
          Range min
          <input
            type="number"
            value={
              assignment.rangeOverrideMode === 'manual'
                ? assignment.manualScaleMin ?? assignment.scaleMin
                : assignment.scaleMin
            }
            disabled={assignment.rangeOverrideMode !== 'manual'}
            step={assignment.rangeEditStep ?? 1}
            onChange={(event) =>
              update({
                rangeOverrideMode: 'manual',
                manualScaleMin: Number(event.target.value),
              })
            }
          />
        </label>
        <label>
          Range max
          <input
            type="number"
            value={
              assignment.rangeOverrideMode === 'manual'
                ? assignment.manualScaleMax ?? assignment.scaleMax
                : assignment.scaleMax
            }
            disabled={assignment.rangeOverrideMode !== 'manual'}
            step={assignment.rangeEditStep ?? 1}
            onChange={(event) =>
              update({
                rangeOverrideMode: 'manual',
                manualScaleMax: Number(event.target.value),
              })
            }
          />
        </label>
        {assignment.overrideWarningMessage ? (
          <div className="wlv-property-note" role="status">
            {assignment.overrideWarningMessage}
          </div>
        ) : null}
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={assignment.scaleDirection === 'reverse'}
            onChange={(event) => update({ scaleDirection: event.target.checked ? 'reverse' : 'normal' })}
          />
          Reverse scale
        </label>
      </div>

      <div className="wlv-curve-control-group">
        <h4>Line</h4>
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={lineVisible}
            onChange={(event) => update({ lineVisible: event.target.checked })}
          />
          Show line
        </label>
        <label>
          Color
          <input type="color" value={assignment.color} onChange={(event) => update({ color: event.target.value })} />
        </label>
        <label>
          Width
          <input
            type="number"
            min={0.5}
            max={8}
            step={0.1}
            value={assignment.lineWidth}
            onChange={(event) => update({ lineWidth: Number(event.target.value) })}
          />
        </label>
        <label>
          Style
          <select
            value={assignment.lineStyle}
            onChange={(event) => update({ lineStyle: event.target.value as LineStyle })}
          >
            <option value="solid">Solid</option>
            <option value="dash">Dashed</option>
            <option value="dot">Dotted</option>
          </select>
        </label>
        <label>
          Opacity
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={lineOpacity}
            onChange={(event) => update({ lineOpacity: Number(event.target.value) })}
          />
        </label>
      </div>

      <div className="wlv-curve-control-group">
        <h4>Position</h4>
        <label>
          Position
          <select
            value={positionAnchor}
            onChange={(event) => update({ positionAnchor: event.target.value as CurveAssignment['positionAnchor'] })}
          >
            <option value="left">Left</option>
            <option value="center">Center</option>
            <option value="right">Right</option>
          </select>
        </label>
        <label>
          Offset
          <input
            type="range"
            min={-100}
            max={100}
            step={5}
            value={horizontalOffsetPct}
            onChange={(event) => update({ horizontalOffsetPct: Number(event.target.value) })}
          />
        </label>
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={clipToTrack}
            onChange={(event) => update({ clipToTrack: event.target.checked })}
          />
          Clip to track
        </label>
      </div>

      <div className="wlv-curve-control-group">
        <h4>Infill</h4>
        <label>
          Infill
          <select
            value={assignment.fillSide}
            onChange={(event) => update({ fillSide: event.target.value as FillSide })}
          >
            <option value="none">Off</option>
            <option value="left">Left of curve</option>
            <option value="right">Right of curve</option>
            <option value="between">Between curves</option>
          </select>
        </label>
        {assignment.fillSide !== 'none' ? (
          <>
            <label>
              Infill source
              <select
                value={infillSource}
                onChange={(event) => update({ infillSource: event.target.value as CurveAssignment['infillSource'] })}
              >
                <option value="solid">Solid color</option>
                <option value="pattern">Pattern</option>
                <option value="interval-column">Interval column</option>
              </select>
            </label>
            {assignment.fillSide === 'between' ? (
              <label>
                Infill with curve
                <select
                  value={assignment.pairedCurveId ?? ''}
                  onChange={(event) => update({ pairedCurveId: event.target.value || undefined })}
                >
                  <option value="">Select curve</option>
                  {track.curves
                    .filter((candidate) => candidate.assignmentId !== assignment.assignmentId)
                    .map((candidate) => {
                      const pairedCurve = findCurveForAssignment(curveCatalogItems, candidate);
                      return pairedCurve
                        ? <option key={candidate.assignmentId} value={candidate.assignmentId}>{pairedCurve.mnemonic}</option>
                        : null;
                    })}
                </select>
              </label>
            ) : null}
            {infillSource === 'interval-column' ? (
              <label>
                Interval column
                <select
                  value={infillIntervalColumn}
                  onChange={(event) => update({ infillIntervalColumn: event.target.value as CurveAssignment['infillIntervalColumn'] })}
                >
                  <option value="lithology">Lithology</option>
                  <option value="biostratigraphy">Biostratigraphy</option>
                  <option value="formation">Formation / stratigraphy</option>
                  <option value="facies">Facies</option>
                  <option value="other">Other interval set</option>
                </select>
              </label>
            ) : null}
            {infillSource === 'pattern' ? (
              <label>
                Pattern
                <select
                  value={infillPattern}
                  onChange={(event) => update({ infillPattern: event.target.value as CurveAssignment['infillPattern'] })}
                >
                  <option value="solid">Solid</option>
                  <option value="hatch">Hatch</option>
                  <option value="dots">Dots</option>
                </select>
              </label>
            ) : null}
            {infillSource !== 'interval-column' ? (
              <label>
                Infill color
                <input type="color" value={assignment.fillColor} onChange={(event) => update({ fillColor: event.target.value })} />
              </label>
            ) : null}
            <label>
              Opacity
              <input
                type="range"
                min={10}
                max={100}
                step={5}
                value={fillOpacity}
                onChange={(event) => update({ fillOpacity: Number(event.target.value) })}
              />
            </label>
          </>
        ) : null}
      </div>

      <div className="wlv-curve-control-group">
        <h4>Display</h4>
        <label>
          Priority
          <select
            value={displayPriority}
            onChange={(event) => update({ displayPriority: event.target.value as CurveAssignment['displayPriority'] })}
          >
            <option value="back">Back</option>
            <option value="normal">Normal</option>
            <option value="front">Front</option>
          </select>
        </label>
      </div>

      <div className="wlv-curve-control-group">
        <h4>QAQC</h4>
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={showQaqcWarnings}
            onChange={(event) => update({ showQaqcWarnings: event.target.checked })}
          />
          Show warnings
        </label>
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={showNullGaps}
            onChange={(event) => update({ showNullGaps: event.target.checked })}
          />
          Show null gaps
        </label>
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={showOutOfRange}
            onChange={(event) => update({ showOutOfRange: event.target.checked })}
          />
          Show out-of-range
        </label>
      </div>
    </div>
  );
}

export function WellLogPropertiesPanelSlot({
  tracks,
  selection,
  curveCatalogItems,
  updateTrack,
  updateCurveAssignment,
  legacyPanel: _legacyPanel,
}: {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  curveCatalogItems: CurveCatalogItem[];
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
  updateCurveAssignment: (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => void;
  legacyPanel?: ReactElement;
}) {
  const [activeTab, setActiveTab] = useState<PropertiesPanelTabKey>('info');
  const [designParametersCollapsed, setDesignParametersCollapsed] = useState(false);
  const [metadataCollapsedSectionIds, setMetadataCollapsedSectionIds] = useState<Set<string>>(
    () => new Set(),
  );
  const metadataCollapseInitializedRef = useRef(false);

  const toggleMetadataSection = (sectionId: string) => {
    setMetadataCollapsedSectionIds((current) => {
      const next = new Set(current);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.add(sectionId);
      }
      return next;
    });
  };

  const normalizedSelection = normalizePropertiesSelection(
    tracks,
    selection,
    curveCatalogItems,
  );
  const selectedTrack = tracks.find((track) => track.trackId === normalizedSelection.trackId) ?? tracks[0];

  const contract = resolvePrototypePropertiesPanelContract({
    tracks,
    selection: normalizedSelection,
    curveCatalog: curveCatalogItems,
    wellHeader,
    curveSamplesByCurveId: realCurveSamplesByCurveId,
    fullDepthRange,
  });

  useEffect(() => {
    if (metadataCollapseInitializedRef.current) {
      return;
    }

    metadataCollapseInitializedRef.current = true;
    setMetadataCollapsedSectionIds(
      new Set(contract.tabs.info.sections.map((section) => section.sectionId)),
    );
  }, [contract.tabs.info.sections]);


  const selectedCurve = resolvePropertiesEditorCurve(
    selectedTrack,
    contract.selectedCurveAssignment,
  );
  const curveSelectionUnresolved =
    normalizedSelection.kind === 'curve' &&
    selectedTrack?.trackType === 'curve' &&
    selectedCurve === null;

  return (
    <aside className="wlv-right-panel wlv-properties-panel-v2">
      <div className="wlv-panel-heading">
        <h2>Properties</h2>
        <span>{contract.selectedEntity.type}</span>
      </div>

      <div className="wlv-properties-selected-entity">
        <strong>{contract.selectedEntity.title}</strong>
        <span>{contract.selectedEntity.subtitle}</span>
      </div>

      <div className="wlv-properties-tabs" role="tablist" aria-label="Properties tabs">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'design'}
          className={activeTab === 'design' ? 'active' : ''}
          onClick={() => setActiveTab('design')}
        >
          {contract.tabs.design.label}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'info'}
          className={activeTab === 'info' ? 'active' : ''}
          onClick={() => setActiveTab('info')}
        >
          {contract.tabs.info.label}
        </button>
      </div>

      {activeTab === 'design' ? (
        <div className="wlv-properties-tab-body" role="tabpanel" aria-label={contract.tabs.design.label}>
          <PropertiesContractTable
            sections={contract.tabs.design.sections}
            collapsible
            collapsed={designParametersCollapsed}
            onToggle={() => setDesignParametersCollapsed((value) => !value)}
          />
          {selectedTrack && selectedCurve && selectedTrack.trackType === 'curve' ? (
            <CurveDesignControls
              track={selectedTrack}
              assignment={selectedCurve}
              curveCatalogItems={curveCatalogItems}
              updateCurveAssignment={updateCurveAssignment}
            />
          ) : curveSelectionUnresolved ? (
            <div className="wlv-property-section wlv-properties-dark-section">
              <h3>Curve Controls</h3>
              <div className="wlv-property-note">
                The selected curve identity could not be resolved. Track controls are not shown
                because they would edit the wrong entity.
              </div>
            </div>
          ) : selectedTrack ? (
            <TrackDesignControls
              track={selectedTrack}
              curveCatalogItems={curveCatalogItems}
              updateTrack={updateTrack}
            />
          ) : null}
        </div>
      ) : (
        <div className="wlv-properties-tab-body" role="tabpanel" aria-label={contract.tabs.info.label}>
          <div className="wlv-properties-contract-table">
            {contract.tabs.info.sections.map((section) => {
              const sectionCollapsed = metadataCollapsedSectionIds.has(section.sectionId);
              return (
                <section
                  key={section.sectionId}
                  className={`wlv-properties-contract-section${sectionCollapsed ? ' is-collapsed' : ''}`}
                >
                  <h3>
                    <button
                      type="button"
                      className="wlv-properties-collapse-toggle"
                      aria-expanded={!sectionCollapsed}
                      onClick={() => toggleMetadataSection(section.sectionId)}
                    >
                      <span>{sectionCollapsed ? '▸' : '▾'}</span>
                      <strong>{section.title}</strong>
                    </button>
                  </h3>
                  {sectionCollapsed ? null : (
                    <table>
                      <tbody>
                        {section.rows.map((row) => (
                          <tr key={`${section.sectionId}-${row.label}`}>
                            <th scope="row">{row.label}</th>
                            <td>
                              <span>{row.value}</span>
                              {row.unit ? <em>{row.unit}</em> : null}
                              {row.source ? <small>{row.source}</small> : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>
              );
            })}
          </div>
        </div>
      )}
    </aside>
  );
}
