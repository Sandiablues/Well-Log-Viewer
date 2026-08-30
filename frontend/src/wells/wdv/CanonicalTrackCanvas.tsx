import type {
  ManagedCurveSamplesByUidV21,
} from '../prototype/managedCurveSamplesV21';
import type {
  CurveCatalogItemV21,
  CurveTrackV21,
  DepthTrackV21,
  CoreTrackV21,
  WellLogTrackV21,
} from '../prototype/trackLayoutModelV21';
import {
  curveByManagedUidV21,
  orderedCurvesV21,
} from '../prototype/trackLayoutModelV21';
import type {
  CanonicalWdvSelection,
} from './canonicalSelection';
import { renderSeriesForTrack } from './canonicalTrackRenderModel';

export interface CanonicalTrackCanvasProps {
  tracks: readonly WellLogTrackV21[];
  curves: readonly CurveCatalogItemV21[];
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21;
  depthRange: { minimum: number; maximum: number; unit: string };
  selection: CanonicalWdvSelection;
  onSelectTrack: (trackUid: WellLogTrackV21['trackUid']) => void;
  onSelectAssignment: (
    trackUid: CurveTrackV21['trackUid'],
    assignment: CurveTrackV21['curves'][number],
  ) => void;
}

function DepthTrackView({
  track,
  depthRange,
}: {
  track: DepthTrackV21;
  depthRange: CanonicalTrackCanvasProps['depthRange'];
}) {
  return (
    <div
      className="wlv-canonical-track wlv-canonical-depth-track"
      style={{ width: track.widthPx }}
    >
      <header className="wlv-canonical-track-header">
        <strong>{track.title}</strong>
        <span>{track.depthBasis}</span>
      </header>
      <div className="wlv-canonical-depth-values">
        <span>{depthRange.minimum.toFixed(0)}</span>
        <span>{depthRange.maximum.toFixed(0)} {depthRange.unit}</span>
      </div>
    </div>
  );
}

function CurveTrackView({
  track,
  curves,
  samplesByManagedCurveUid,
  depthRange,
  selection,
  onSelectTrack,
  onSelectAssignment,
}: {
  track: CurveTrackV21;
  curves: readonly CurveCatalogItemV21[];
  samplesByManagedCurveUid: ManagedCurveSamplesByUidV21;
  depthRange: CanonicalTrackCanvasProps['depthRange'];
  selection: CanonicalWdvSelection;
  onSelectTrack: CanonicalTrackCanvasProps['onSelectTrack'];
  onSelectAssignment: CanonicalTrackCanvasProps['onSelectAssignment'];
}) {
  const height = 680;
  const series = renderSeriesForTrack(
    track,
    samplesByManagedCurveUid,
    depthRange,
    { width: track.widthPx, height },
  );
  const selectedTrack = selection.kind !== 'none'
    && selection.trackUid === track.trackUid;
  const orderedAssignments = orderedCurvesV21(track);

  return (
    <div
      className={[
        'wlv-canonical-track',
        'wlv-canonical-curve-track',
        selectedTrack ? 'is-selected' : '',
      ].filter(Boolean).join(' ')}
      style={{ width: track.widthPx }}
    >
      <button
        type="button"
        className="wlv-canonical-track-header"
        onClick={() => onSelectTrack(track.trackUid)}
      >
        <strong>{track.title}</strong>
        <span>
          {orderedAssignments.length}
          {' '}
          {orderedAssignments.length === 1 ? 'curve' : 'curves'}
        </span>
      </button>

      <div className="wlv-canonical-track-curve-tabs">
        {orderedAssignments.map((assignment) => {
          const curve = curveByManagedUidV21(
            curves,
            assignment.managedCurveUid,
          );
          const selected = selection.kind === 'assignment'
            && selection.assignmentUid === assignment.assignmentUid;
          return (
            <button
              key={assignment.assignmentUid}
              type="button"
              className={selected ? 'is-selected' : ''}
              onClick={() => onSelectAssignment(track.trackUid, assignment)}
              title={curve.displayName}
            >
              <span
                className="wlv-canonical-curve-color"
                style={{ backgroundColor: assignment.color }}
              />
              {curve.observedMnemonic}
            </button>
          );
        })}
      </div>

      {orderedAssignments.length === 0 ? (
        <button
          type="button"
          className="wlv-canonical-empty-track"
          onClick={() => onSelectTrack(track.trackUid)}
        >
          Select a loaded curve and use Add Selected Curve.
        </button>
      ) : (
        <svg
          viewBox={`0 0 ${track.widthPx} ${height}`}
          width={track.widthPx}
          height={height}
          role="img"
          aria-label={`${track.title} well-log track`}
        >
          {series.map((item) => (
            <polyline
              key={item.assignment.assignmentUid}
              points={item.points.map(
                (point) => `${point.x},${point.y}`,
              ).join(' ')}
              fill="none"
              stroke={item.assignment.color}
              strokeWidth={item.assignment.lineWidth}
              strokeOpacity={item.assignment.lineOpacity / 100}
              strokeDasharray={
                item.assignment.lineStyle === 'dash'
                  ? '8 5'
                  : item.assignment.lineStyle === 'dot'
                    ? '2 4'
                    : undefined
              }
              onClick={() => onSelectAssignment(
                track.trackUid,
                item.assignment,
              )}
            />
          ))}
        </svg>
      )}
    </div>
  );
}

function CoreTrackView({
  track,
  onSelectTrack,
}: {
  track: CoreTrackV21;
  onSelectTrack: CanonicalTrackCanvasProps['onSelectTrack'];
}) {
  return (
    <div
      className="wlv-canonical-track wlv-canonical-core-track"
      style={{ width: track.widthPx }}
    >
      <button
        type="button"
        className="wlv-canonical-track-header"
        onClick={() => onSelectTrack(track.trackUid)}
      >
        <strong>{track.title || 'Core'}</strong>
        <span>Core Image</span>
      </button>
      <div className="wlv-canonical-empty-track">
        Core imagery is rendered in the standard WDV track canvas.
      </div>
    </div>
  );
}

export function CanonicalTrackCanvas(props: CanonicalTrackCanvasProps) {
  const visibleTracks = props.tracks.filter((track) => track.visible);

  return (
    <section className="wlv-canonical-canvas-shell">
      <header className="wlv-canonical-panel-header">
        <div>
          <strong>Track Workspace</strong>
          <span>
            {visibleTracks.length}
            {' '}
            {visibleTracks.length === 1 ? 'visible track' : 'visible tracks'}
          </span>
        </div>
      </header>

      {visibleTracks.length === 0 ? (
        <div className="wlv-canonical-canvas-empty">
          <strong>No tracks have been created.</strong>
          <span>
            Create a track above, then select a loaded curve and add it.
          </span>
        </div>
      ) : (
        <div className="wlv-canonical-canvas" aria-label="Well log tracks">
          {visibleTracks.map((track) => (
            track.trackType === 'depth'
              ? (
                  <DepthTrackView
                    key={track.trackUid}
                    track={track}
                    depthRange={props.depthRange}
                  />
                )
              : track.trackType === 'core'
                ? (
                    <CoreTrackView
                      key={track.trackUid}
                      track={track}
                      onSelectTrack={props.onSelectTrack}
                    />
                  )
                : (
                  <CurveTrackView
                    key={track.trackUid}
                    track={track}
                    curves={props.curves}
                    samplesByManagedCurveUid={
                      props.samplesByManagedCurveUid
                    }
                    depthRange={props.depthRange}
                    selection={props.selection}
                    onSelectTrack={props.onSelectTrack}
                    onSelectAssignment={props.onSelectAssignment}
                  />
                )
          ))}
        </div>
      )}
    </section>
  );
}
