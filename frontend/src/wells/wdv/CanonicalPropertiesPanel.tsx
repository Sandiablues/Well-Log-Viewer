import type {
  CanonicalSessionCommandV21,
  CanonicalViewerSessionV21,
} from '../prototype/canonicalViewerPackageV21';
import type {
  CurveCatalogItemV21,
} from '../prototype/trackLayoutModelV21';
import {
  curveByManagedUidV21,
} from '../prototype/trackLayoutModelV21';
import type {
  CanonicalWdvSelection,
} from './canonicalSelection';
import {
  updateAssignmentCommand,
  updateTrackCommand,
} from './canonicalCommandBuilders';

export interface CanonicalPropertiesPanelProps {
  session: CanonicalViewerSessionV21;
  curves: readonly CurveCatalogItemV21[];
  selection: CanonicalWdvSelection;
  onCommand: (command: CanonicalSessionCommandV21) => void;
}

function EmptyProperties() {
  return (
    <aside className="wlv-canonical-properties">
      <header className="wlv-canonical-panel-header">
        <div>
          <strong>Properties</strong>
          <span>No selection</span>
        </div>
      </header>
      <div className="wlv-canonical-properties-empty">
        Select a track or an assigned curve to edit its display properties.
      </div>
    </aside>
  );
}

export function CanonicalPropertiesPanel({
  session,
  curves,
  selection,
  onCommand,
}: CanonicalPropertiesPanelProps) {
  if (selection.kind === 'none') return <EmptyProperties />;

  const track = session.tracks.find(
    (item) => item.trackUid === selection.trackUid,
  );
  if (!track) return <EmptyProperties />;

  if (selection.kind === 'track' || track.trackType !== 'curve') {
    return (
      <aside className="wlv-canonical-properties">
        <header className="wlv-canonical-panel-header">
          <div>
            <strong>Track Properties</strong>
            <span>{track.title}</span>
          </div>
        </header>
        <div className="wlv-canonical-properties-form">
          <label>
            <span>Track title</span>
            <input
              value={track.title}
              onChange={(event) => onCommand(updateTrackCommand(
                session.revision,
                track.trackUid,
                { title: event.target.value },
              ))}
            />
          </label>
          <label>
            <span>Width</span>
            <input
              type="number"
              min={80}
              max={600}
              value={track.widthPx}
              onChange={(event) => onCommand(updateTrackCommand(
                session.revision,
                track.trackUid,
                { widthPx: Number(event.target.value) },
              ))}
            />
          </label>
        </div>
      </aside>
    );
  }

  const assignment = track.curves.find(
    (item) => item.assignmentUid === selection.assignmentUid,
  );
  if (!assignment) return <EmptyProperties />;

  const curve = curveByManagedUidV21(
    curves,
    assignment.managedCurveUid,
  );

  return (
    <aside className="wlv-canonical-properties">
      <header className="wlv-canonical-panel-header">
        <div>
          <strong>Curve Properties</strong>
          <span>{curve.observedMnemonic} · {curve.unit ?? 'No unit'}</span>
        </div>
      </header>

      <div className="wlv-canonical-properties-summary">
        <strong>{curve.displayName}</strong>
        <span>{track.title}</span>
      </div>

      <div className="wlv-canonical-properties-form">
        <label>
          <span>Scale minimum</span>
          <input
            type="number"
            value={assignment.scaleMin ?? ''}
            onChange={(event) => {
              const raw = event.target.value;
              if (raw === '') return;
              const newMin = Number(raw);
              if (!isFinite(newMin)) return;
              if (assignment.scaleMax === null) return;
              onCommand(updateAssignmentCommand(
                session.revision,
                assignment.assignmentUid,
                { scaleMin: newMin, scaleMax: assignment.scaleMax },
              ));
            }}
          />
        </label>
        <label>
          <span>Scale maximum</span>
          <input
            type="number"
            value={assignment.scaleMax ?? ''}
            onChange={(event) => {
              const raw = event.target.value;
              if (raw === '') return;
              const newMax = Number(raw);
              if (!isFinite(newMax)) return;
              if (assignment.scaleMin === null) return;
              onCommand(updateAssignmentCommand(
                session.revision,
                assignment.assignmentUid,
                { scaleMin: assignment.scaleMin, scaleMax: newMax },
              ));
            }}
          />
        </label>
        <label>
          <span>Line color</span>
          <input
            type="color"
            value={assignment.color}
            onChange={(event) => onCommand(updateAssignmentCommand(
              session.revision,
              assignment.assignmentUid,
              { color: event.target.value },
            ))}
          />
        </label>
        <label className="wlv-canonical-checkbox-label">
          <span>Visible</span>
          <input
            type="checkbox"
            checked={assignment.visible}
            onChange={(event) => onCommand(updateAssignmentCommand(
              session.revision,
              assignment.assignmentUid,
              { visible: event.target.checked },
            ))}
          />
        </label>
      </div>
    </aside>
  );
}
