import { type ReactElement, useEffect, useRef, useState } from 'react';
import {
  curveCatalog,
  fullDepthRange,
  realCurveSamplesByCurveId,
  wellHeader,
} from './realLasTrackLayoutData';
import type {
  CurveAssignment,
  CurveTrack,
  DepthBasis,
  FillSide,
  LineStyle,
  ScaleMode,
  SelectionRef,
  WellLogTrack,
} from './trackLayoutModel';
import {
  curveById,
  resolveTrackLattice,
} from './trackLayoutModel';
import type {
  PropertiesPanelSection,
  PropertiesPanelTabKey,
} from './wellLogPropertiesPanelContract';
import {
  resolvePrototypePropertiesPanelContract,
} from './wellLogPropertiesPanelContract';

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
  updateTrack,
}: {
  track: WellLogTrack;
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
    const lattice = resolveTrackLattice(track, curveCatalog);
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

function CurveDesignControls({
  track,
  assignment,
  updateCurveAssignment,
}: {
  track: CurveTrack;
  assignment: CurveAssignment;
  updateCurveAssignment: (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => void;
}) {
  const curve = curveById(curveCatalog, assignment.curveId);

  return (
    <div className="wlv-property-section wlv-properties-dark-section">
      <h3>Curve Controls</h3>
      <div className="wlv-selected-curve-title">
        <span className="wlv-curve-color" style={{ background: assignment.color }} />
        <strong>{curve.mnemonic}</strong>
        <span>{curve.description}</span>
      </div>
      <label>
        Range min
        <input type="number" value={assignment.scaleMin} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { scaleMin: Number(event.target.value) })} />
      </label>
      <label>
        Range max
        <input type="number" value={assignment.scaleMax} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { scaleMax: Number(event.target.value) })} />
      </label>
      <label>
        Color
        <input type="color" value={assignment.color} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { color: event.target.value })} />
      </label>
      <label>
        Line style
        <select
          value={assignment.lineStyle}
          onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { lineStyle: event.target.value as LineStyle })}
        >
          <option value="solid">Solid</option>
          <option value="dash">Dash</option>
          <option value="dot">Dot</option>
        </select>
      </label>
      <label>
        Line width
        <input
          type="number"
          min={0.5}
          max={8}
          step={0.1}
          value={assignment.lineWidth}
          onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { lineWidth: Number(event.target.value) })}
        />
      </label>
      <label>
        Fill
        <select
          value={assignment.fillSide}
          onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { fillSide: event.target.value as FillSide })}
        >
          <option value="none">None</option>
          <option value="left">Left</option>
          <option value="right">Right</option>
          <option value="between">Between</option>
        </select>
      </label>
      <label>
        Fill color
        <input type="color" value={assignment.fillColor} onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { fillColor: event.target.value })} />
      </label>
    </div>
  );
}

export function WellLogPropertiesPanelSlot({
  tracks,
  selection,
  updateTrack,
  updateCurveAssignment,
  legacyPanel: _legacyPanel,
}: {
  tracks: WellLogTrack[];
  selection: SelectionRef;
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

  const selectedTrack = tracks.find((track) => track.trackId === selection.trackId) ?? tracks[0];

  const contract = resolvePrototypePropertiesPanelContract({
    tracks,
    selection,
    curveCatalog,
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


  const selectedCurve = selectedTrack?.trackType === 'curve' ? contract.selectedCurveAssignment : null;

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
              updateCurveAssignment={updateCurveAssignment}
            />
          ) : selectedTrack ? (
            <TrackDesignControls track={selectedTrack} updateTrack={updateTrack} />
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
