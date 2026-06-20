import {
  useEffect,
  useMemo,
  useState,
} from 'react';
import type {
  ManagedCurveUid,
  ManagedWellUid,
  TrackUid,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalSessionCommandV21,
} from '../prototype/canonicalViewerPackageV21';
import type {
  CurveAssignmentV21,
  CurveTrackV21,
} from '../prototype/trackLayoutModelV21';
import '../../styles/canonical-wdv.css';
import { CanonicalCurveInventory } from './CanonicalCurveInventory';
import { CanonicalPropertiesPanel } from './CanonicalPropertiesPanel';
import { CanonicalTrackCanvas } from './CanonicalTrackCanvas';
import {
  addAssignmentCommand,
  createTrackCommand,
} from './canonicalCommandBuilders';
import type {
  CanonicalWdvSelection,
} from './canonicalSelection';
import {
  selectionFromSession,
  validateCanonicalSelection,
} from './canonicalSelection';
import {
  useCanonicalWdvWorkspace,
} from './useCanonicalWdvWorkspace';

export interface CanonicalWdvViewProps {
  managedWellUid: ManagedWellUid | null;
  maxSamples?: number;
  defaultTemplateKey?: string | null;
  workflowContext?: string | null;
}

export function assignedManagedCurveUids(
  session: NonNullable<
    ReturnType<typeof useCanonicalWdvWorkspace>['state']['session']
  >,
): ReadonlySet<ManagedCurveUid> {
  const result = new Set<ManagedCurveUid>();
  for (const track of session.tracks) {
    if (track.trackType !== 'curve') continue;
    for (const assignment of track.curves) {
      result.add(assignment.managedCurveUid);
    }
  }
  return result;
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function CanonicalWdvView({
  managedWellUid,
  maxSamples = 4000,
  defaultTemplateKey = null,
  workflowContext = null,
}: CanonicalWdvViewProps) {
  const workspace = useCanonicalWdvWorkspace(
    managedWellUid,
    maxSamples,
  );
  const [selection, setSelection] = useState<CanonicalWdvSelection>({
    kind: 'none',
  });
  const [selectedInventoryCurveUid, setSelectedInventoryCurveUid] =
    useState<ManagedCurveUid | null>(null);
  const [templateKey, setTemplateKey] = useState(
    defaultTemplateKey ?? '',
  );
  const [newTrackTitle, setNewTrackTitle] = useState('New Track');
  const [targetTrackUid, setTargetTrackUid] = useState<TrackUid | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);

  const { state } = workspace;
  const viewerPackage = state.viewerPackage;
  const session = state.session;

  useEffect(() => {
    if (session === null) {
      setSelection({ kind: 'none' });
      return;
    }
    setSelection((current) => (
      current.kind === 'none'
        ? selectionFromSession(session)
        : validateCanonicalSelection(session, current)
    ));
  }, [session]);

  const assigned = useMemo(
    () => session === null
      ? new Set<ManagedCurveUid>()
      : assignedManagedCurveUids(session),
    [session],
  );

  const curveTracks = useMemo(
    () => session === null
      ? []
      : session.tracks.filter(
          (track): track is CurveTrackV21 => track.trackType === 'curve',
        ),
    [session],
  );

  useEffect(() => {
    if (
      targetTrackUid !== null
      && curveTracks.some((track) => track.trackUid === targetTrackUid)
    ) {
      return;
    }
    setTargetTrackUid(curveTracks[0]?.trackUid ?? null);
  }, [curveTracks, targetTrackUid]);

  const selectedManagedCurveUid =
    selection.kind === 'assignment'
      ? selection.managedCurveUid
      : selectedInventoryCurveUid;

  const selectedInventoryCurve = viewerPackage?.curves.find(
    (curve) => curve.managedCurveUid === selectedInventoryCurveUid,
  ) ?? null;

  const runCommand = async (
    command: CanonicalSessionCommandV21,
  ): Promise<void> => {
    setActionPending(true);
    setActionError(null);
    try {
      await workspace.execute(command);
    } catch (error) {
      setActionError(messageFrom(error));
    } finally {
      setActionPending(false);
    }
  };

  const createTrack = async (): Promise<void> => {
    if (session === null || newTrackTitle.trim().length === 0) return;
    await runCommand(
      createTrackCommand(session.revision, newTrackTitle.trim()),
    );
  };

  const addSelectedCurve = async (): Promise<void> => {
    if (
      session === null
      || selectedInventoryCurveUid === null
      || targetTrackUid === null
      || assigned.has(selectedInventoryCurveUid)
    ) {
      return;
    }
    await runCommand(
      addAssignmentCommand(
        session.revision,
        targetTrackUid,
        selectedInventoryCurveUid,
      ),
    );
  };

  const applyTemplate = async (): Promise<void> => {
    if (templateKey.trim().length === 0) return;
    setActionPending(true);
    setActionError(null);
    try {
      await workspace.applyTemplate(
        templateKey.trim(),
        workflowContext,
      );
    } catch (error) {
      setActionError(messageFrom(error));
    } finally {
      setActionPending(false);
    }
  };

  if (managedWellUid === null || state.status === 'idle') {
    return (
      <section className="wlv-canonical-empty-state">
        <strong>No well loaded in the Well Data Viewer</strong>
        <span>
          Select one well in Managed Data and use Load to make it available
          here.
        </span>
      </section>
    );
  }

  if (state.status === 'loading') {
    return (
      <section className="wlv-canonical-status">
        Loading well and curve inventory…
      </section>
    );
  }

  if (state.status === 'error' || viewerPackage === null || session === null) {
    return (
      <section className="wlv-canonical-status" role="alert">
        {state.error ?? 'Canonical WDV package unavailable.'}
      </section>
    );
  }

  const minimum = viewerPackage.depthRange.minimum;
  const maximum = viewerPackage.depthRange.maximum;
  if (minimum === null || maximum === null || !(maximum > minimum)) {
    return (
      <section className="wlv-canonical-status" role="alert">
        Valid backend depth range is required to render this well.
      </section>
    );
  }

  return (
    <section className="wlv-canonical-view">
      <header className="wlv-canonical-view-header">
        <div className="wlv-canonical-well-heading">
          <strong>{viewerPackage.wellName}</strong>
          <span>
            {viewerPackage.wellboreName ?? 'Primary wellbore'}
            {' · '}
            {viewerPackage.curves.length} loaded curves
            {' · '}
            {curveTracks.length} curve tracks
          </span>
        </div>

        <div className="wlv-canonical-template-controls">
          <input
            aria-label="Template key"
            value={templateKey}
            onChange={(event) => setTemplateKey(event.target.value)}
            placeholder="Template key"
          />
          <button
            type="button"
            disabled={actionPending || templateKey.trim().length === 0}
            onClick={() => void applyTemplate()}
          >
            Apply Template
          </button>
        </div>
      </header>

      <div className="wlv-canonical-workbench-toolbar">
        <div className="wlv-canonical-toolbar-group">
          <label htmlFor="wlv-new-track-title">New track</label>
          <input
            id="wlv-new-track-title"
            value={newTrackTitle}
            onChange={(event) => setNewTrackTitle(event.target.value)}
          />
          <button
            type="button"
            disabled={actionPending || newTrackTitle.trim().length === 0}
            onClick={() => void createTrack()}
          >
            Create Track
          </button>
        </div>

        <div className="wlv-canonical-toolbar-group">
          <label htmlFor="wlv-target-track">Add selected curve to</label>
          <select
            id="wlv-target-track"
            value={targetTrackUid ?? ''}
            disabled={curveTracks.length === 0}
            onChange={(event) => {
              setTargetTrackUid(
                (event.target.value || null) as TrackUid | null,
              );
            }}
          >
            {curveTracks.length === 0 ? (
              <option value="">Create a track first</option>
            ) : null}
            {curveTracks.map((track) => (
              <option key={track.trackUid} value={track.trackUid}>
                {track.title}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={
              actionPending
              || selectedInventoryCurveUid === null
              || targetTrackUid === null
              || assigned.has(selectedInventoryCurveUid)
            }
            onClick={() => void addSelectedCurve()}
          >
            Add Selected Curve
          </button>
          <span className="wlv-canonical-toolbar-selection">
            {selectedInventoryCurve
              ? `${selectedInventoryCurve.observedMnemonic} selected`
              : 'No curve selected'}
          </span>
        </div>
      </div>

      {actionError || state.error ? (
        <div className="wlv-canonical-action-error" role="alert">
          {actionError ?? state.error}
        </div>
      ) : null}

      <div className="wlv-canonical-component-grid">
        <CanonicalCurveInventory
          curves={viewerPackage.curves}
          assignedManagedCurveUids={assigned}
          selectedManagedCurveUid={selectedManagedCurveUid}
          onSelect={(managedCurveUid) => {
            setSelectedInventoryCurveUid(managedCurveUid);
            setSelection({ kind: 'none' });
          }}
        />

        <CanonicalTrackCanvas
          tracks={session.tracks}
          curves={viewerPackage.curves}
          samplesByManagedCurveUid={state.samplesByManagedCurveUid}
          depthRange={{
            minimum,
            maximum,
            unit: viewerPackage.depthRange.unit,
          }}
          selection={selection}
          onSelectTrack={(trackUid: TrackUid) => {
            setSelection({ kind: 'track', trackUid });
            void runCommand({
              kind: 'select_track',
              body: {
                expected_revision: session.revision,
                track_uid: trackUid,
              },
            });
          }}
          onSelectAssignment={(
            trackUid,
            assignment: CurveAssignmentV21,
          ) => {
            setSelection({
              kind: 'assignment',
              trackUid,
              assignmentUid: assignment.assignmentUid,
              managedCurveUid: assignment.managedCurveUid,
            });
          }}
        />

        <CanonicalPropertiesPanel
          session={session}
          curves={viewerPackage.curves}
          selection={selection}
          onCommand={(command) => void runCommand(command)}
        />
      </div>

      {state.sampleErrorsByManagedCurveUid.size > 0 ? (
        <footer className="wlv-canonical-sample-errors">
          {state.sampleErrorsByManagedCurveUid.size} assigned curve sample
          request(s) failed.
        </footer>
      ) : null}
    </section>
  );
}
