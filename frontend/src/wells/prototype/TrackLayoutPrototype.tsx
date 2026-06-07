import { useMemo, useState } from 'react';
import '../../styles/track-layout-prototype.css';
import { curveCatalog, initialTracks, wellHeader } from './mockTrackLayoutData';
import type {
  ActiveTrackType,
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
  DepthBasis,
  DepthTrack,
  DragCurvePayload,
  FillSide,
  LineStyle,
  ScaleMode,
  SelectionRef,
  WellLogTrack,
} from './trackLayoutModel';
import {
  curveById,
  makeCurveAssignment,
  orderedCurves,
  parseDragPayload,
  renumberCurveStack,
  resolveTrackLattice,
} from './trackLayoutModel';

const depthTicks = [2400, 2600, 2800, 3000, 3200, 3400, 3600, 3800, 4000, 4200, 4400];

function sortTracks(tracks: WellLogTrack[]): WellLogTrack[] {
  return [...tracks].sort((a, b) => a.trackIndex - b.trackIndex);
}

function reindexTracks(tracks: WellLogTrack[]): WellLogTrack[] {
  return sortTracks(tracks).map((track, index) => ({ ...track, trackIndex: index }));
}

function nextTrackId(trackType: ActiveTrackType): string {
  return `track-${trackType}-${Date.now()}-${Math.round(Math.random() * 100000)}`;
}

function curvePath(curve: CurveCatalogItem, assignment: CurveAssignment, trackPosition: number): string {
  const phase = curve.mnemonic.length * 0.61 + trackPosition * 0.47;
  const points: string[] = [];
  const width = 220;
  const mid = width / 2;
  const amplitude = curve.defaultLattice === 'logarithmic' ? 62 : 48;
  const styleOffset = assignment.lineStyle === 'dot' ? 15 : assignment.lineStyle === 'dash' ? -12 : 0;

  for (let i = 0; i <= 58; i += 1) {
    const t = i / 58;
    const y = 16 + t * 560;
    const wiggle =
      Math.sin(t * Math.PI * (7 + curve.mnemonic.length) + phase) * amplitude +
      Math.sin(t * Math.PI * 31 + phase * 0.3) * amplitude * 0.26;
    const x = Math.max(8, Math.min(width - 8, mid + wiggle + styleOffset));
    points.push(`${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`);
  }

  return points.join(' ');
}

function serialiseCurveDrag(payload: DragCurvePayload): string {
  return JSON.stringify(payload);
}

function CurveInventory({
  assignedCurveIds,
  selectedCurveIds,
  onSelectCurve,
}: {
  assignedCurveIds: Set<string>;
  selectedCurveIds: Set<string>;
  onSelectCurve: (curveId: string) => void;
}) {
  const groups = useMemo(
    () => Array.from(new Set(curveCatalog.map((curve) => curve.curveClass))).filter((group) => group !== 'depth'),
    [],
  );

  return (
    <aside className="wlv-curve-inventory">
      <div className="wlv-panel-heading">
        <h2>Curve Inventory</h2>
        <span>{curveCatalog.length}</span>
      </div>
      <div className="wlv-search-row">
        <input aria-label="Search curves" placeholder="Search curves..." />
        <button type="button" title="Filter curves">Filter</button>
      </div>
      <div className="wlv-inventory-tabs">
        <button type="button" className="active">All Curves</button>
        <button type="button">Selected</button>
        <button type="button">Aliases</button>
      </div>
      <div className="wlv-inventory-list">
        {groups.map((group) => (
          <section key={group} className="wlv-curve-group">
            <div className="wlv-curve-group-title">{group}</div>
            {curveCatalog.filter((curve) => curve.curveClass === group).map((curve) => {
              const assigned = assignedCurveIds.has(curve.curveId);
              return (
                <button
                  key={curve.curveId}
                  type="button"
                  className={`wlv-curve-row ${assigned ? 'assigned' : ''} ${selectedCurveIds.has(curve.curveId) ? 'inventory-selected' : ''} ${curve.recognised ? '' : 'unrecognised'}`}
                  draggable
                  onClick={() => onSelectCurve(curve.curveId)}
                  onDragStart={(event) => {
                    event.dataTransfer.setData('application/json', serialiseCurveDrag({ dragType: 'curve', curveId: curve.curveId }));
                    event.dataTransfer.effectAllowed = 'move';
                  }}
                >
                  <span className="wlv-checkbox">{assigned ? '✓' : ''}</span>
                  <strong>{curve.mnemonic}</strong>
                  <span>{curve.description}</span>
                  <em>{curve.unit}</em>
                </button>
              );
            })}
          </section>
        ))}
      </div>
      <div className="wlv-drop-help">
        Drag curves into curve tracks. Drag curve headers between tracks to move assignments.
      </div>
    </aside>
  );
}

type AddTrackDraft = {
  trackType: ActiveTrackType;
  depthBasis: DepthBasis;
  insertMode: 'before_selected' | 'after_selected' | 'far_right';
  curveSource: 'empty' | 'selected';
  latticeMode: 'auto' | 'linear' | 'logarithmic';
  scaleMode: ScaleMode;
};

const defaultAddTrackDraft: AddTrackDraft = {
  trackType: 'curve',
  depthBasis: 'MD',
  insertMode: 'after_selected',
  curveSource: 'empty',
  latticeMode: 'auto',
  scaleMode: 'per_curve',
};

function Toolbar({
  selectedTrack,
  selectedInventoryCount,
  onAddTrack,
  onDeleteTrack,
  onMoveSelectedTrack,
}: {
  selectedTrack: WellLogTrack | null;
  selectedInventoryCount: number;
  onAddTrack: (draft: AddTrackDraft) => void;
  onDeleteTrack: () => void;
  onMoveSelectedTrack: (direction: -1 | 1) => void;
}) {
  const [builderOpen, setBuilderOpen] = useState(false);
  const [draft, setDraft] = useState<AddTrackDraft>(defaultAddTrackDraft);

  const updateDraft = (patch: Partial<AddTrackDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
  };

  const addTrackLabel = draft.trackType === 'depth'
    ? `Add ${draft.depthBasis} Depth Track`
    : draft.curveSource === 'selected' && selectedInventoryCount > 0
      ? `Add Curve Track from ${selectedInventoryCount} selected`
      : 'Add Empty Curve Track';

  return (
    <div className="wlv-track-toolbar">
      <div className="wlv-toolbar-group add-track-group">
        <span>Track</span>
        <div className="wlv-add-track-control">
          <button
            type="button"
            className="wlv-add-track-button"
            onClick={() => setBuilderOpen((open) => !open)}
            aria-expanded={builderOpen}
          >
            + Add Track ▾
          </button>
          {builderOpen && (
            <div className="wlv-add-track-builder" role="dialog" aria-label="Add Track Builder">
              <div className="builder-heading">
                <strong>Add Track</strong>
                <button type="button" onClick={() => setBuilderOpen(false)} aria-label="Close Add Track Builder">×</button>
              </div>

              <section className="builder-section">
                <div className="builder-label">Track type</div>
                <div className="builder-choice-grid">
                  <button
                    type="button"
                    className={draft.trackType === 'depth' ? 'active' : ''}
                    onClick={() => updateDraft({ trackType: 'depth' })}
                  >
                    Depth
                  </button>
                  <button
                    type="button"
                    className={draft.trackType === 'curve' ? 'active' : ''}
                    onClick={() => updateDraft({ trackType: 'curve' })}
                  >
                    Curve
                  </button>
                  <button type="button" disabled title="Reserved for raster/core/lithology artifacts">Raster</button>
                  <button type="button" disabled title="Reserved for marker datasets">Marker</button>
                  <button type="button" disabled title="Reserved for interval datasets">Interval</button>
                </div>
              </section>

              {draft.trackType === 'depth' && (
                <section className="builder-section">
                  <div className="builder-label">Depth subtype</div>
                  <div className="builder-choice-grid three">
                    {(['MD', 'TVD', 'TVDSS'] as DepthBasis[]).map((basis) => (
                      <button
                        key={basis}
                        type="button"
                        className={draft.depthBasis === basis ? 'active' : ''}
                        onClick={() => updateDraft({ depthBasis: basis })}
                      >
                        {basis}
                      </button>
                    ))}
                  </div>
                  <p className="builder-note">TVD/TVDSS are mock-enabled here; backend validation will eventually decide availability.</p>
                </section>
              )}

              {draft.trackType === 'curve' && (
                <>
                  <section className="builder-section">
                    <div className="builder-label">Curve source</div>
                    <div className="builder-choice-grid two">
                      <button
                        type="button"
                        className={draft.curveSource === 'empty' ? 'active' : ''}
                        onClick={() => updateDraft({ curveSource: 'empty' })}
                      >
                        Empty
                      </button>
                      <button
                        type="button"
                        className={draft.curveSource === 'selected' ? 'active' : ''}
                        disabled={selectedInventoryCount === 0}
                        onClick={() => updateDraft({ curveSource: 'selected' })}
                      >
                        From selected ({selectedInventoryCount})
                      </button>
                    </div>
                  </section>

                  <section className="builder-section">
                    <div className="builder-label">Lattice</div>
                    <select
                      value={draft.latticeMode}
                      onChange={(event) => updateDraft({ latticeMode: event.target.value as AddTrackDraft['latticeMode'] })}
                    >
                      <option value="auto">Auto from front curve</option>
                      <option value="linear">Linear override</option>
                      <option value="logarithmic">Logarithmic override</option>
                    </select>
                  </section>

                  <section className="builder-section">
                    <div className="builder-label">Scale mode</div>
                    <select value={draft.scaleMode} onChange={(event) => updateDraft({ scaleMode: event.target.value as ScaleMode })}>
                      <option value="shared">Shared</option>
                      <option value="per_curve">Per curve</option>
                      <option value="dual">Dual</option>
                    </select>
                  </section>
                </>
              )}

              <section className="builder-section">
                <div className="builder-label">Insert position</div>
                <select
                  value={draft.insertMode}
                  onChange={(event) => updateDraft({ insertMode: event.target.value as AddTrackDraft['insertMode'] })}
                >
                  <option value="before_selected">Before selected track</option>
                  <option value="after_selected">After selected track</option>
                  <option value="far_right">Far right</option>
                </select>
              </section>

              <div className="builder-actions">
                <button type="button" onClick={() => setBuilderOpen(false)}>Cancel</button>
                <button
                  type="button"
                  className="builder-primary"
                  onClick={() => {
                    onAddTrack(draft);
                    setBuilderOpen(false);
                  }}
                >
                  {addTrackLabel}
                </button>
              </div>
            </div>
          )}
        </div>
        <button type="button" disabled={!selectedTrack} onClick={onDeleteTrack}>Delete Track</button>
        <button type="button" disabled={!selectedTrack} onClick={() => onMoveSelectedTrack(-1)}>Move Left</button>
        <button type="button" disabled={!selectedTrack} onClick={() => onMoveSelectedTrack(1)}>Move Right</button>
      </div>
      <div className="wlv-toolbar-spacer" />
      <div className="wlv-toolbar-group">
        <span>Template</span>
        <select aria-label="Template">
          <option>dbMap-style QAQC Layout</option>
          <option>Corporate Triple Combo</option>
          <option>Blank Layout</option>
        </select>
        <button type="button">Save Layout</button>
        <button type="button">Reset</button>
      </div>
      <div className="wlv-toolbar-group">
        <span>View</span>
        <button type="button">Zoom +</button>
        <button type="button">Zoom −</button>
        <button type="button">Fit Depth</button>
      </div>
    </div>
  );
}

function CurveHeaderStack({
  track,
  selectedAssignmentId,
  openMenuAssignmentId,
  onSelectCurve,
  onReorderCurve,
  onMoveCurveToTrack,
  onOpenCurveMenu,
  onCloseCurveMenu,
  onRemoveCurveFromTrack,
}: {
  track: CurveTrack;
  selectedAssignmentId: string | null;
  openMenuAssignmentId: string | null;
  onSelectCurve: (trackId: string, assignmentId: string) => void;
  onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
  onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
  onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
  onCloseCurveMenu: () => void;
  onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
}) {
  const ordered = orderedCurves(track);

  return (
    <div className="wlv-curve-header-stack">
      {ordered.map((assignment, index) => {
        const curve = curveById(curveCatalog, assignment.curveId);
        return (
          <div
            key={assignment.assignmentId}
            role="button"
            tabIndex={0}
            className={`wlv-curve-header ${selectedAssignmentId === assignment.assignmentId ? 'selected' : ''}`}
            draggable
            onClick={(event) => {
              event.stopPropagation();
              onSelectCurve(track.trackId, assignment.assignmentId);
              if (openMenuAssignmentId === assignment.assignmentId) {
                onCloseCurveMenu();
              }
            }}
            onDoubleClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onSelectCurve(track.trackId, assignment.assignmentId);
              onOpenCurveMenu(track.trackId, assignment.assignmentId);
            }}
            onDragStart={(event) => {
              event.dataTransfer.setData(
                'application/json',
                serialiseCurveDrag({
                  dragType: 'curve',
                  curveId: assignment.curveId,
                  fromTrackId: track.trackId,
                  assignmentId: assignment.assignmentId,
                }),
              );
              event.dataTransfer.effectAllowed = 'move';
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              event.stopPropagation();
              const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
              if (!payload) return;
              if (payload.fromTrackId === track.trackId && payload.assignmentId) {
                onReorderCurve(track.trackId, payload.assignmentId, index);
              } else {
                onMoveCurveToTrack(payload, track.trackId, index);
              }
            }}
          >
            <span className="wlv-curve-color" style={{ background: assignment.color }} />
            <strong>{curve.mnemonic}</strong>
            <span>{assignment.scaleMin}—{assignment.scaleMax}</span>
            <em>{curve.unit}</em>
            {openMenuAssignmentId === assignment.assignmentId && (
              <div
                className="curve-header-action-menu"
                role="menu"
                onClick={(event) => event.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => {
                    onReorderCurve(track.trackId, assignment.assignmentId, 0);
                    onCloseCurveMenu();
                  }}
                >
                  Move to Front
                </button>
                <button
                  type="button"
                  disabled={index <= 0}
                  onClick={() => {
                    onReorderCurve(track.trackId, assignment.assignmentId, Math.max(0, index - 1));
                    onCloseCurveMenu();
                  }}
                >
                  Move Up
                </button>
                <button
                  type="button"
                  disabled={index >= ordered.length - 1}
                  onClick={() => {
                    onReorderCurve(track.trackId, assignment.assignmentId, Math.min(ordered.length - 1, index + 1));
                    onCloseCurveMenu();
                  }}
                >
                  Move Down
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onReorderCurve(track.trackId, assignment.assignmentId, ordered.length - 1);
                    onCloseCurveMenu();
                  }}
                >
                  Send to Back
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onSelectCurve(track.trackId, assignment.assignmentId);
                    onCloseCurveMenu();
                  }}
                >
                  Edit Style / Range / Fill
                </button>
                <div className="curve-menu-divider" />
                <button
                  type="button"
                  className="danger"
                  onClick={() => {
                    onRemoveCurveFromTrack(track.trackId, assignment.assignmentId);
                    onCloseCurveMenu();
                  }}
                >
                  Remove from Track
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DepthTrackView({ track }: { track: DepthTrack }) {
  return (
    <div className="wlv-depth-track-body">
      {depthTicks.map((depth) => (
        <div key={`${track.trackId}-${depth}`} className="wlv-depth-tick">
          <span>{depth}</span>
        </div>
      ))}
    </div>
  );
}

function CurveTrackView({ track }: { track: CurveTrack }) {
  const ordered = orderedCurves(track);
  const backToFront = [...ordered].reverse();
  const lattice = resolveTrackLattice(track, curveCatalog);

  return (
    <svg className={`wlv-curve-track-svg ${lattice.lattice}`} viewBox="0 0 240 610" preserveAspectRatio="none">
      <defs>
        <pattern id={`grid-${track.trackId}`} width={lattice.lattice === 'logarithmic' ? '30' : '24'} height="30" patternUnits="userSpaceOnUse">
          <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#e0e6ed" strokeWidth="1" />
        </pattern>
      </defs>
      <rect x="0" y="0" width="240" height="610" fill={`url(#grid-${track.trackId})`} />
      {depthTicks.map((_, index) => (
        <line key={index} x1="0" x2="240" y1={20 + index * 55} y2={20 + index * 55} stroke="#aeb8c5" strokeWidth="1" />
      ))}
      {backToFront.map((assignment, index) => {
        const curve = curveById(curveCatalog, assignment.curveId);
        const path = curvePath(curve, assignment, index);
        return (
          <g key={assignment.assignmentId}>
            {assignment.fillSide !== 'none' && (
              <path d={`${path} L 120 590 L 120 20 Z`} fill={assignment.fillColor} stroke="none" opacity="0.55" />
            )}
            <path
              d={path}
              fill="none"
              stroke={assignment.color}
              strokeWidth={assignment.lineWidth}
              strokeDasharray={assignment.lineStyle === 'dash' ? '8 5' : assignment.lineStyle === 'dot' ? '2 6' : undefined}
              vectorEffect="non-scaling-stroke"
              opacity={assignment.visible ? 1 : 0.2}
            />
          </g>
        );
      })}
    </svg>
  );
}

function TrackView({
  track,
  selected,
  selectedAssignmentId,
  openCurveMenu,
  onSelectTrack,
  onSelectCurve,
  onReorderCurve,
  onMoveCurveToTrack,
  onOpenCurveMenu,
  onCloseCurveMenu,
  onRemoveCurveFromTrack,
}: {
  track: WellLogTrack;
  selected: boolean;
  selectedAssignmentId: string | null;
  openCurveMenu: { trackId: string; assignmentId: string } | null;
  onSelectTrack: (trackId: string) => void;
  onSelectCurve: (trackId: string, assignmentId: string) => void;
  onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
  onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
  onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
  onCloseCurveMenu: () => void;
  onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
}) {
  const width = `${track.widthPx}px`;
  const isCurveTrack = track.trackType === 'curve';
  const lattice = isCurveTrack ? resolveTrackLattice(track, curveCatalog) : null;

  return (
    <section
      className={`wlv-track ${track.trackType} ${selected ? 'selected' : ''}`}
      style={{ width, minWidth: width }}
      onClick={() => {
        onCloseCurveMenu();
        onSelectTrack(track.trackId);
      }}
      onDragOver={(event) => {
        if (track.trackType === 'curve') event.preventDefault();
      }}
      onDrop={(event) => {
        if (track.trackType !== 'curve') return;
        event.preventDefault();
        const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
        if (payload) onMoveCurveToTrack(payload, track.trackId);
      }}
    >
      <header className="wlv-track-header">
        <div className="wlv-track-title-row">
          <strong>{track.title}</strong>
          <span>T{track.trackIndex + 1}</span>
        </div>
        {track.trackType === 'depth' && (
          <div className="wlv-depth-header">{track.depthBasis} · {track.unit}</div>
        )}
        {track.trackType === 'curve' && (
          <>
            <div className="wlv-lattice-badge">
              {lattice?.lattice} · {lattice?.source === 'user_override' ? 'override' : `front ${lattice?.frontCurve?.mnemonic ?? 'none'}`}
            </div>
            <CurveHeaderStack
              track={track}
              selectedAssignmentId={selectedAssignmentId}
              openMenuAssignmentId={openCurveMenu?.trackId === track.trackId ? openCurveMenu.assignmentId : null}
              onSelectCurve={onSelectCurve}
              onReorderCurve={onReorderCurve}
              onMoveCurveToTrack={onMoveCurveToTrack}
              onOpenCurveMenu={onOpenCurveMenu}
              onCloseCurveMenu={onCloseCurveMenu}
              onRemoveCurveFromTrack={onRemoveCurveFromTrack}
            />
          </>
        )}
      </header>
      <div className="wlv-track-body">
        {track.trackType === 'depth' ? <DepthTrackView track={track} /> : null}
        {track.trackType === 'curve' ? <CurveTrackView track={track} /> : null}
      </div>
    </section>
  );
}

function TrackCanvas({
  tracks,
  selection,
  openCurveMenu,
  onSelectTrack,
  onSelectCurve,
  onReorderCurve,
  onMoveCurveToTrack,
  onOpenCurveMenu,
  onCloseCurveMenu,
  onRemoveCurveFromTrack,
}: {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  openCurveMenu: { trackId: string; assignmentId: string } | null;
  onSelectTrack: (trackId: string) => void;
  onSelectCurve: (trackId: string, assignmentId: string) => void;
  onReorderCurve: (trackId: string, assignmentId: string, toIndex: number) => void;
  onMoveCurveToTrack: (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => void;
  onOpenCurveMenu: (trackId: string, assignmentId: string) => void;
  onCloseCurveMenu: () => void;
  onRemoveCurveFromTrack: (trackId: string, assignmentId: string) => void;
}) {
  return (
    <main className="wlv-track-canvas">
      <div className="wlv-track-strip">
        {sortTracks(tracks).map((track) => (
          <TrackView
            key={track.trackId}
            track={track}
            selected={selection.kind === 'track' && selection.trackId === track.trackId || selection.kind === 'curve' && selection.trackId === track.trackId}
            selectedAssignmentId={selection.kind === 'curve' && selection.trackId === track.trackId ? selection.assignmentId : null}
            openCurveMenu={openCurveMenu}
            onSelectTrack={onSelectTrack}
            onSelectCurve={onSelectCurve}
            onReorderCurve={onReorderCurve}
            onMoveCurveToTrack={onMoveCurveToTrack}
            onOpenCurveMenu={onOpenCurveMenu}
            onCloseCurveMenu={onCloseCurveMenu}
            onRemoveCurveFromTrack={onRemoveCurveFromTrack}
          />
        ))}
      </div>
    </main>
  );
}

function TrackProperties({
  track,
  updateTrack,
}: {
  track: WellLogTrack;
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
}) {
  if (track.trackType === 'depth') {
    return (
      <div className="wlv-property-section">
        <h3>Selected Track</h3>
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
        <label>
          Width
          <input type="number" value={track.widthPx} onChange={(event) => updateTrack(track.trackId, { widthPx: Number(event.target.value) })} />
        </label>
      </div>
    );
  }

  if (track.trackType === 'curve') {
    const lattice = resolveTrackLattice(track, curveCatalog);
    return (
      <div className="wlv-property-section">
        <h3>Selected Track</h3>
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
          <input type="number" value={track.widthPx} onChange={(event) => updateTrack(track.trackId, { widthPx: Number(event.target.value) })} />
        </label>
        <div className="wlv-property-note">
          Top curve header controls default lattice and front-most overpost order.
        </div>
      </div>
    );
  }

  return <div className="wlv-property-section">Reserved track type.</div>;
}

function CurveProperties({
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
    <div className="wlv-property-section">
      <h3>Selected Curve</h3>
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
        <input type="color" value="#c7e7c8" onChange={(event) => updateCurveAssignment(track.trackId, assignment.assignmentId, { fillColor: event.target.value })} />
      </label>
      <div className="wlv-property-note">
        Curve headers can be dragged between tracks. Header stack order controls overpost order.
      </div>
    </div>
  );
}

function RightPanel({
  tracks,
  selection,
  updateTrack,
  updateCurveAssignment,
}: {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
  updateCurveAssignment: (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => void;
}) {
  const selectedTrack = tracks.find((track) => track.trackId === selection.trackId) ?? tracks[0];
  const selectedCurve = selectedTrack?.trackType === 'curve' && selection.kind === 'curve'
    ? selectedTrack.curves.find((assignment) => assignment.assignmentId === selection.assignmentId) ?? null
    : null;

  return (
    <aside className="wlv-right-panel">
      <div className="wlv-panel-heading">
        <h2>Properties</h2>
        <span>{selection.kind}</span>
      </div>
      {selectedTrack && selectedCurve && selectedTrack.trackType === 'curve' ? (
        <CurveProperties track={selectedTrack} assignment={selectedCurve} updateCurveAssignment={updateCurveAssignment} />
      ) : selectedTrack ? (
        <TrackProperties track={selectedTrack} updateTrack={updateTrack} />
      ) : null}
      <div className="wlv-property-section well-header">
        <h3>Well Header</h3>
        <dl>
          <dt>Well</dt><dd>{wellHeader.wellName}</dd>
          <dt>Wellbore</dt><dd>{wellHeader.wellboreName}</dd>
          <dt>Field</dt><dd>{wellHeader.field}</dd>
          <dt>Operator</dt><dd>{wellHeader.operator}</dd>
          <dt>Country</dt><dd>{wellHeader.country}</dd>
          <dt>KB</dt><dd>{wellHeader.kb}</dd>
          <dt>GL</dt><dd>{wellHeader.gl}</dd>
          <dt>Log start</dt><dd>{wellHeader.logStart}</dd>
          <dt>Log end</dt><dd>{wellHeader.logEnd}</dd>
          <dt>Source file</dt><dd>{wellHeader.sourceFile}</dd>
          <dt>TVD</dt><dd>{wellHeader.tvdStatus}</dd>
          <dt>MSI</dt><dd>{wellHeader.msiIdentity}</dd>
        </dl>
      </div>
    </aside>
  );
}

export function TrackLayoutPrototype() {
  const [tracks, setTracks] = useState<WellLogTrack[]>(() => reindexTracks(initialTracks));
  const [selection, setSelection] = useState<SelectionRef>({ kind: 'track', trackId: initialTracks[1].trackId });
  const [selectedInventoryCurveIds, setSelectedInventoryCurveIds] = useState<string[]>([]);
  const [openCurveMenu, setOpenCurveMenu] = useState<{ trackId: string; assignmentId: string } | null>(null);

  const assignedCurveIds = useMemo(() => {
    const ids = new Set<string>();
    tracks.forEach((track) => {
      if (track.trackType === 'curve') {
        track.curves.forEach((assignment) => ids.add(assignment.curveId));
      }
    });
    return ids;
  }, [tracks]);

  const selectedTrack = tracks.find((track) => track.trackId === selection.trackId) ?? null;

  const updateTrack = (trackId: string, patch: Partial<WellLogTrack>) => {
    setTracks((current) => current.map((track) => (track.trackId === trackId ? { ...track, ...patch } as WellLogTrack : track)));
  };

  const updateCurveAssignment = (trackId: string, assignmentId: string, patch: Partial<CurveAssignment>) => {
    setTracks((current) => current.map((track) => {
      if (track.trackId !== trackId || track.trackType !== 'curve') return track;
      return {
        ...track,
        curves: track.curves.map((assignment) => (
          assignment.assignmentId === assignmentId ? { ...assignment, ...patch } : assignment
        )),
      };
    }));
  };

  const addTrack = (draft: AddTrackDraft) => {
    setTracks((current) => {
      const ordered = sortTracks(current);
      const selected = ordered.find((track) => track.trackId === selection.trackId) ?? null;
      const insertionIndex =
        draft.insertMode === 'before_selected' && selected
          ? selected.trackIndex
          : draft.insertMode === 'after_selected' && selected
            ? selected.trackIndex + 1
            : ordered.length;
      const shifted = current.map((track) => (
        track.trackIndex >= insertionIndex ? { ...track, trackIndex: track.trackIndex + 1 } : track
      ));

      const selectedCurves = selectedInventoryCurveIds
        .map((curveId) => curveCatalog.find((curve) => curve.curveId === curveId))
        .filter((curve): curve is CurveCatalogItem => Boolean(curve));

      const curveAssignments = draft.trackType === 'curve' && draft.curveSource === 'selected'
        ? selectedCurves.map((curve, index) => makeCurveAssignment(curve, index))
        : [];

      const frontCurve = curveAssignments[0]
        ? curveById(curveCatalog, curveAssignments[0].curveId)
        : null;

      const latticeOverride = draft.trackType === 'curve' && draft.latticeMode !== 'auto';
      const lattice = draft.trackType === 'curve'
        ? draft.latticeMode === 'auto'
          ? frontCurve?.defaultLattice ?? 'linear'
          : draft.latticeMode
        : 'linear';

      const newTrack: WellLogTrack = draft.trackType === 'depth'
        ? {
            trackId: nextTrackId('depth'),
            trackIndex: insertionIndex,
            trackType: 'depth',
            title: draft.depthBasis,
            depthBasis: draft.depthBasis,
            unit: 'm',
            widthPx: 86,
            visible: true,
          }
        : {
            trackId: nextTrackId('curve'),
            trackIndex: insertionIndex,
            trackType: 'curve',
            title: curveAssignments.length > 0
              ? curveAssignments.map((assignment) => curveById(curveCatalog, assignment.curveId).mnemonic).join(' / ')
              : 'NEW CURVE TRACK',
            widthPx: 220,
            visible: true,
            lattice,
            latticeSource: latticeOverride ? 'user_override' : 'front_curve_default',
            latticeOverride,
            scaleMode: draft.scaleMode,
            curves: curveAssignments,
          };
      setSelection({ kind: 'track', trackId: newTrack.trackId });
      if (draft.trackType === 'curve' && draft.curveSource === 'selected') {
        setSelectedInventoryCurveIds([]);
      }
      return reindexTracks([...shifted, newTrack]);
    });
  };

  const deleteSelectedTrack = () => {
    if (!selectedTrack) return;
    setTracks((current) => {
      const remaining = reindexTracks(current.filter((track) => track.trackId !== selectedTrack.trackId));
      const fallback = remaining[Math.min(selectedTrack.trackIndex, Math.max(remaining.length - 1, 0))];
      if (fallback) setSelection({ kind: 'track', trackId: fallback.trackId });
      return remaining;
    });
  };

  const moveSelectedTrack = (direction: -1 | 1) => {
    if (!selectedTrack) return;
    setTracks((current) => {
      const ordered = sortTracks(current);
      const index = ordered.findIndex((track) => track.trackId === selectedTrack.trackId);
      const target = index + direction;
      if (target < 0 || target >= ordered.length) return current;
      const copy = [...ordered];
      const [item] = copy.splice(index, 1);
      copy.splice(target, 0, item);
      return reindexTracks(copy);
    });
  };

  const moveCurveToTrack = (payload: DragCurvePayload, toTrackId: string, toIndex?: number) => {
    setTracks((current) => {
      let movingAssignment: CurveAssignment | null = null;
      let working = current.map((track) => {
        if (track.trackType !== 'curve') return track;
        if (payload.fromTrackId === track.trackId && payload.assignmentId) {
          const match = track.curves.find((assignment) => assignment.assignmentId === payload.assignmentId);
          if (match) movingAssignment = match;
          return { ...track, curves: renumberCurveStack(track.curves.filter((assignment) => assignment.assignmentId !== payload.assignmentId)) };
        }
        return track;
      });

      const curve = curveById(curveCatalog, payload.curveId);
      const assignment = movingAssignment ?? makeCurveAssignment(curve, 0);

      working = working.map((track) => {
        if (track.trackId !== toTrackId || track.trackType !== 'curve') return track;
        const existing = track.curves.some((item) => item.assignmentId === assignment.assignmentId || item.curveId === assignment.curveId);
        if (existing) return track;
        const next = [...orderedCurves(track)];
        const targetIndex = typeof toIndex === 'number' ? toIndex : next.length;
        next.splice(targetIndex, 0, { ...assignment, stackIndex: targetIndex });
        return { ...track, curves: renumberCurveStack(next), latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default' };
      });

      setSelection({ kind: 'curve', trackId: toTrackId, assignmentId: assignment.assignmentId });
      return reindexTracks(working);
    });
  };

  const reorderCurve = (trackId: string, assignmentId: string, toIndex: number) => {
    setTracks((current) => current.map((track) => {
      if (track.trackId !== trackId || track.trackType !== 'curve') return track;
      const ordered = orderedCurves(track);
      const fromIndex = ordered.findIndex((assignment) => assignment.assignmentId === assignmentId);
      if (fromIndex < 0) return track;
      const [item] = ordered.splice(fromIndex, 1);
      ordered.splice(toIndex, 0, item);
      return { ...track, curves: renumberCurveStack(ordered), latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default' };
    }));
    setSelection({ kind: 'curve', trackId, assignmentId });
  };

  const removeCurveFromTrack = (trackId: string, assignmentId: string) => {
    const sourceTrack = tracks.find((track) => track.trackId === trackId) ?? null;
    const removedCurveId = sourceTrack?.trackType === 'curve'
      ? sourceTrack.curves.find((assignment) => assignment.assignmentId === assignmentId)?.curveId ?? null
      : null;

    setTracks((current) => current.map((track) => {
      if (track.trackId !== trackId || track.trackType !== 'curve') return track;
      return {
        ...track,
        curves: renumberCurveStack(track.curves.filter((assignment) => assignment.assignmentId !== assignmentId)),
        latticeSource: track.latticeOverride ? track.latticeSource : 'front_curve_default',
      };
    }));

    if (removedCurveId) {
      setSelectedInventoryCurveIds((current) => current.filter((curveId) => curveId !== removedCurveId));
    }
    setOpenCurveMenu(null);
    setSelection({ kind: 'track', trackId });
  };

  return (
    <div className="wlv-prototype-root">
      <header className="wlv-app-header">
        <div>
          <span>MultiViewer</span>
          <strong>Well Log Viewer</strong>
        </div>
        <div className="wlv-loaded-context">
          <span>Well <strong>{wellHeader.wellName}</strong></span>
          <span>Wellbore <strong>{wellHeader.wellboreName}</strong></span>
          <span>Status <strong>QAQC Review</strong></span>
        </div>
      </header>

      <Toolbar
        selectedTrack={selectedTrack}
        selectedInventoryCount={selectedInventoryCurveIds.length}
        onAddTrack={addTrack}
        onDeleteTrack={deleteSelectedTrack}
        onMoveSelectedTrack={moveSelectedTrack}
      />

      <div className="wlv-prototype-workspace">
        <CurveInventory
          assignedCurveIds={assignedCurveIds}
          selectedCurveIds={new Set(selectedInventoryCurveIds)}
          onSelectCurve={(curveId) => {
            setOpenCurveMenu(null);
            setSelectedInventoryCurveIds((current) => (
              current.includes(curveId)
                ? current.filter((item) => item !== curveId)
                : [...current, curveId]
            ));
            const containingTrack = tracks.find((track) => (
              track.trackType === 'curve' && track.curves.some((assignment) => assignment.curveId === curveId)
            ));
            if (containingTrack?.trackType === 'curve') {
              const assignment = containingTrack.curves.find((item) => item.curveId === curveId);
              if (assignment) setSelection({ kind: 'curve', trackId: containingTrack.trackId, assignmentId: assignment.assignmentId });
            }
          }}
        />
        <TrackCanvas
          tracks={tracks}
          selection={selection}
          openCurveMenu={openCurveMenu}
          onSelectTrack={(trackId) => setSelection({ kind: 'track', trackId })}
          onSelectCurve={(trackId, assignmentId) => setSelection({ kind: 'curve', trackId, assignmentId })}
          onReorderCurve={reorderCurve}
          onMoveCurveToTrack={moveCurveToTrack}
          onOpenCurveMenu={(trackId, assignmentId) => setOpenCurveMenu({ trackId, assignmentId })}
          onCloseCurveMenu={() => setOpenCurveMenu(null)}
          onRemoveCurveFromTrack={removeCurveFromTrack}
        />
        <RightPanel
          tracks={tracks}
          selection={selection}
          updateTrack={updateTrack}
          updateCurveAssignment={updateCurveAssignment}
        />
      </div>

      <footer className="wlv-status-footer">
        <span>WL-PROTOTYPE-001 working template</span>
        <span>Track terminology only</span>
        <span>Mock frontend layout draft — no LAS parsing or MSI persistence</span>
      </footer>
    </div>
  );
}

export default TrackLayoutPrototype;
