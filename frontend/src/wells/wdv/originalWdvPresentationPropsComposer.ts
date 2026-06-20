import type {
  ManagedCurveUid,
  TrackUid,
  AssignmentUid,
} from '../identity/wdvIdentityV21';
import type {
  OriginalWdvPresentationProps,
} from '../prototype/OriginalWdvPresentation';
import type {
  CurveAssignment,
  CurveTrack,
  DragCurvePayload,
  WellLogTrack,
} from '../prototype/trackLayoutModel';
import type {
  ActiveCanonicalWdvState,
} from './activeCanonicalWdvIntegration';
import type {
  CanonicalOriginalWdvMutationAdapter,
} from './canonicalOriginalWdvIntentAdapter';

type ToolbarProps = OriginalWdvPresentationProps['toolbarProps'];
type CurveInventoryProps =
  OriginalWdvPresentationProps['curveInventoryProps'];
type TrackCanvasProps =
  OriginalWdvPresentationProps['trackCanvasProps'];
type RightPanelProps =
  OriginalWdvPresentationProps['rightPanelProps'];

type PersistedToolbarKeys =
  | 'selectedTrack'
  | 'pendingAddTrackCurveCount'
  | 'fullDepthRange'
  | 'onAddTrack'
  | 'onDeleteTrack'
  | 'onMoveSelectedTrack'
  | 'canMoveSelectedTrackLeft'
  | 'canMoveSelectedTrackRight'
  | 'canAdjustSelectedCurveTrackWidthDown'
  | 'canAdjustSelectedCurveTrackWidthUp'
  | 'onAdjustSelectedCurveTrackWidth'
  | 'onResetCurveTrackWidths';

type PersistedInventoryKeys =
  | 'availableCurves'
  | 'curveUsageCounts'
  | 'visibleTrackCurveIds'
  | 'selectedTrackCurveIds'
  | 'selectedCurveIds'
  | 'assignmentEnabled'
  | 'onToggleCurveInSelectedTrack';

type PersistedCanvasKeys =
  | 'tracks'
  | 'selection'
  | 'depthTicks'
  | 'managedSamplesByCurveId'
  | 'managedSampleErrorsByCurveId'
  | 'curveCatalogItems'
  | 'onSelectTrack'
  | 'onSelectCurve'
  | 'onReorderCurve'
  | 'onMoveCurveToTrack'
  | 'onRemoveCurveFromTrack';

type PersistedRightPanelKeys =
  | 'tracks'
  | 'selection'
  | 'curveCatalogItems'
  | 'updateTrack'
  | 'updateCurveAssignment';

export interface OriginalWdvComposerLocalInputs {
  toolbar: Omit<ToolbarProps, PersistedToolbarKeys>;
  curveInventory: Omit<CurveInventoryProps, PersistedInventoryKeys>;
  trackCanvas: Omit<TrackCanvasProps, PersistedCanvasKeys>;
  rightPanel?: Omit<RightPanelProps, PersistedRightPanelKeys>;
  trackBackdropMode: OriginalWdvPresentationProps['trackBackdropMode'];
  addTrackCurveSelectionMode: boolean;
  pendingAddTrackCurveUids: readonly ManagedCurveUid[];
  selectedInventoryCurveUids: readonly ManagedCurveUid[];
  onPendingAddTrackCurveToggle(
    managedCurveUid: ManagedCurveUid,
    checked: boolean,
  ): void;
  renderPropertiesPanel?:
    OriginalWdvPresentationProps['renderPropertiesPanel'];
  defaultCurveTrackWidthPx: number;
  createTrackName(
    draft: Parameters<ToolbarProps['onAddTrack']>[0],
    presentationTrackCount: number,
  ): string;
}

export interface ComposeOriginalWdvPresentationPropsInput {
  state: ActiveCanonicalWdvState;
  mutationAdapter: CanonicalOriginalWdvMutationAdapter;
  local: OriginalWdvComposerLocalInputs;
}

function asTrackUid(value: string): TrackUid {
  return value as TrackUid;
}

function asAssignmentUid(value: string): AssignmentUid {
  return value as AssignmentUid;
}

function asManagedCurveUid(value: string): ManagedCurveUid {
  return value as ManagedCurveUid;
}

function selectedTrack(
  tracks: readonly WellLogTrack[],
  selection: OriginalWdvPresentationProps['trackCanvasProps']['selection'],
): WellLogTrack | null {
  return tracks.find((track) => track.trackId === selection.trackId)
    ?? tracks[0]
    ?? null;
}

function curveUsageCounts(
  tracks: readonly WellLogTrack[],
): Map<string, number> {
  const counts = new Map<string, number>();
  for (const track of tracks) {
    if (track.trackType !== 'curve') continue;
    for (const assignment of track.curves) {
      counts.set(
        assignment.curveId,
        (counts.get(assignment.curveId) ?? 0) + 1,
      );
    }
  }
  return counts;
}

function visibleTrackCurveIds(
  tracks: readonly WellLogTrack[],
): Set<string> {
  const ids = new Set<string>();
  for (const track of tracks) {
    if (!track.visible || track.trackType !== 'curve') continue;
    for (const assignment of track.curves) {
      if (!assignment.visible) continue;
      ids.add(assignment.curveId);
    }
  }
  return ids;
}

function selectedTrackCurveIds(
  track: WellLogTrack | null,
): Set<string> {
  if (!track || track.trackType !== 'curve') return new Set();
  return new Set(track.curves.map((assignment) => assignment.curveId));
}

function selectedCurveIds(
  selection: OriginalWdvPresentationProps['trackCanvasProps']['selection'],
  tracks: readonly WellLogTrack[],
): Set<string> {
  if (selection.kind !== 'curve') return new Set();
  const track = tracks.find((item) => item.trackId === selection.trackId);
  if (!track || track.trackType !== 'curve') return new Set();
  const assignment = track.curves.find(
    (item) => item.assignmentId === selection.assignmentId,
  );
  return assignment ? new Set([assignment.curveId]) : new Set();
}

function unionCurveUids(
  ...collections: readonly (readonly string[] | ReadonlySet<string>)[]
): Set<string> {
  const result = new Set<string>();
  for (const collection of collections) {
    for (const value of collection) result.add(value);
  }
  return result;
}

function depthTicks(
  range: { min: number; max: number },
): number[] {
  if (!Number.isFinite(range.min) || !Number.isFinite(range.max)) return [];
  if (range.max <= range.min) return [range.min];
  const span = range.max - range.min;
  const rough = span / 10;
  const exponent = 10 ** Math.floor(Math.log10(Math.max(rough, 1e-9)));
  const normalized = rough / exponent;
  const step = (
    normalized <= 1 ? 1
      : normalized <= 2 ? 2
        : normalized <= 5 ? 5
          : 10
  ) * exponent;
  const first = Math.ceil(range.min / step) * step;
  const ticks: number[] = [];
  for (let value = first; value <= range.max + step * 1e-9; value += step) {
    ticks.push(Number(value.toFixed(9)));
  }
  return ticks;
}

function sampleObjects(
  samples: Readonly<Record<string, readonly (readonly [number, number])[]>>,
): Record<string, { depth: number; value: number }[]> {
  return Object.fromEntries(
    Object.entries(samples).map(([curveUid, values]) => [
      curveUid,
      values.map(([depth, value]) => ({ depth, value })),
    ]),
  );
}

function reorderedTrackUids(
  tracks: readonly WellLogTrack[],
  selectedTrackId: string,
  direction: -1 | 1,
): TrackUid[] | null {
  const ordered = [...tracks].sort(
    (left, right) => left.trackIndex - right.trackIndex,
  );
  const index = ordered.findIndex(
    (track) => track.trackId === selectedTrackId,
  );
  const target = index + direction;
  if (index < 0 || target < 0 || target >= ordered.length) return null;
  const next = [...ordered];
  [next[index], next[target]] = [next[target], next[index]];
  return next.map((track) => asTrackUid(track.trackId));
}

function assignmentOrderAfterMove(
  track: CurveTrack,
  assignmentId: string,
  toIndex: number,
): AssignmentUid[] {
  const ordered = [...track.curves].sort(
    (left, right) => left.stackIndex - right.stackIndex,
  );
  const fromIndex = ordered.findIndex(
    (assignment) => assignment.assignmentId === assignmentId,
  );
  if (fromIndex < 0) return ordered.map(
    (assignment) => asAssignmentUid(assignment.assignmentId),
  );
  const [moved] = ordered.splice(fromIndex, 1);
  const bounded = Math.max(0, Math.min(toIndex, ordered.length));
  ordered.splice(bounded, 0, moved);
  return ordered.map(
    (assignment) => asAssignmentUid(assignment.assignmentId),
  );
}

function assignmentForCurve(
  track: CurveTrack,
  curveId: string,
): CurveAssignment | null {
  return track.curves.find(
    (assignment) => assignment.curveId === curveId,
  ) ?? null;
}

export function composeOriginalWdvPresentationProps({
  state,
  mutationAdapter,
  local,
}: ComposeOriginalWdvPresentationPropsInput):
  OriginalWdvPresentationProps | null {
  const presentation = state.presentation;
  if (presentation === null) return null;

  const tracks = presentation.tracks;
  const selection = presentation.selection;
  const activeTrack = selectedTrack(tracks, selection);
  const activeCurveTrack =
    activeTrack?.trackType === 'curve' ? activeTrack : null;
  const orderedTracks = [...tracks].sort(
    (left, right) => left.trackIndex - right.trackIndex,
  );
  const selectedIndex = activeTrack
    ? orderedTracks.findIndex(
        (track) => track.trackId === activeTrack.trackId,
      )
    : -1;

  const onAddTrack: ToolbarProps['onAddTrack'] = (draft) => {
    const referenceTrackUid = activeTrack
      ? asTrackUid(activeTrack.trackId)
      : null;
    const insertMode = draft.insertMode === 'before_selected'
      ? 'before_track'
      : draft.insertMode === 'after_selected'
        ? 'after_track'
        : 'far_right';

    void mutationAdapter.createConfiguredTrack({
      trackName: local.createTrackName(draft, tracks.length),
      trackType: draft.trackType === 'depth' ? 'depth' : 'curve',
      depthBasis: draft.trackType === 'depth' ? draft.depthBasis : null,
      widthPx: draft.trackType === 'curve'
        ? local.defaultCurveTrackWidthPx
        : null,
      lattice: draft.latticeMode === 'auto'
        ? null
        : draft.latticeMode,
      latticeOverride: draft.latticeMode !== 'auto',
      scaleMode: draft.scaleMode,
      insertPosition: {
        mode: insertMode,
        referenceTrackUid:
          insertMode === 'far_right' ? null : referenceTrackUid,
      },
      initialManagedCurveUids:
        draft.trackType === 'curve' && draft.curveSource === 'selected'
          ? local.pendingAddTrackCurveUids
          : [],
      selectCreatedTrack: true,
    });
  };

  const onDeleteTrack: ToolbarProps['onDeleteTrack'] = () => {
    if (!activeTrack) return;
    void mutationAdapter.removeTrack(asTrackUid(activeTrack.trackId));
  };

  const onMoveSelectedTrack: ToolbarProps['onMoveSelectedTrack'] =
    (direction) => {
      if (!activeTrack) return;
      const order = reorderedTrackUids(
        tracks,
        activeTrack.trackId,
        direction,
      );
      if (order) void mutationAdapter.reorderTracks(order);
    };

  const onAdjustSelectedCurveTrackWidth:
    ToolbarProps['onAdjustSelectedCurveTrackWidth'] = (delta) => {
      if (!activeCurveTrack) return;
      void mutationAdapter.updateTrack(
        asTrackUid(activeCurveTrack.trackId),
        { widthPx: activeCurveTrack.widthPx + delta },
      );
    };

  const onToggleCurveInSelectedTrack:
    CurveInventoryProps['onToggleCurveInSelectedTrack'] =
    (curveId, checked) => {
      if (local.addTrackCurveSelectionMode) {
        local.onPendingAddTrackCurveToggle(
          asManagedCurveUid(curveId),
          checked,
        );
        return;
      }
      if (!activeCurveTrack) return;
      const existing = assignmentForCurve(activeCurveTrack, curveId);
      if (checked && !existing) {
        void mutationAdapter.addAssignment({
          trackUid: asTrackUid(activeCurveTrack.trackId),
          managedCurveUid: asManagedCurveUid(curveId),
        });
      } else if (!checked && existing) {
        void mutationAdapter.removeAssignment(
          asAssignmentUid(existing.assignmentId),
        );
      }
    };

  const onSelectTrack: TrackCanvasProps['onSelectTrack'] = (trackId) => {
    void mutationAdapter.selectTrack(asTrackUid(trackId));
  };

  const onSelectCurve: TrackCanvasProps['onSelectCurve'] =
    (trackId, assignmentId) => {
      const track = tracks.find((item) => item.trackId === trackId);
      const assignment = track?.trackType === 'curve'
        ? track.curves.find(
            (item) => item.assignmentId === assignmentId,
          )
        : null;
      if (!assignment) return;
      void mutationAdapter.selectAssignment(
        asTrackUid(trackId),
        asAssignmentUid(assignmentId),
        asManagedCurveUid(assignment.curveId),
      );
    };

  const onReorderCurve: TrackCanvasProps['onReorderCurve'] =
    (trackId, assignmentId, toIndex) => {
      const track = tracks.find((item) => item.trackId === trackId);
      if (!track || track.trackType !== 'curve') return;
      void mutationAdapter.reorderAssignments(
        asTrackUid(trackId),
        assignmentOrderAfterMove(track, assignmentId, toIndex),
      );
    };

  const onMoveCurveToTrack: TrackCanvasProps['onMoveCurveToTrack'] =
    (payload: DragCurvePayload, toTrackId: string, toIndex = 0) => {
      if (payload.assignmentId && payload.fromTrackId) {
        if (payload.fromTrackId === toTrackId) {
          const track = tracks.find((item) => item.trackId === toTrackId);
          if (!track || track.trackType !== 'curve') return;
          void mutationAdapter.reorderAssignments(
            asTrackUid(toTrackId),
            assignmentOrderAfterMove(
              track,
              payload.assignmentId,
              toIndex,
            ),
          );
          return;
        }
        void mutationAdapter.moveAssignment(
          asAssignmentUid(payload.assignmentId),
          asTrackUid(toTrackId),
          toIndex,
        );
        return;
      }

      void mutationAdapter.addAssignment({
        trackUid: asTrackUid(toTrackId),
        managedCurveUid: asManagedCurveUid(payload.curveId),
        targetStackIndex: toIndex,
      });
    };

  const onRemoveCurveFromTrack:
    TrackCanvasProps['onRemoveCurveFromTrack'] =
    (_trackId, assignmentId) => {
      void mutationAdapter.removeAssignment(
        asAssignmentUid(assignmentId),
      );
    };

  const updateTrack: RightPanelProps['updateTrack'] =
    (trackId, patch) => {
      void mutationAdapter.updateTrack(
        asTrackUid(trackId),
        {
          title: patch.title,
          widthPx: patch.widthPx,
          visible: patch.visible,
          lattice:
            patch.trackType === 'curve' ? patch.lattice : undefined,
          latticeSource:
            patch.trackType === 'curve'
              ? patch.latticeSource
              : undefined,
          latticeOverride:
            patch.trackType === 'curve'
              ? patch.latticeOverride
              : undefined,
          scaleMode:
            patch.trackType === 'curve'
              ? patch.scaleMode
              : undefined,
          depthBasis:
            patch.trackType === 'depth'
              ? patch.depthBasis
              : undefined,
        },
      );
    };

  const updateCurveAssignment:
    RightPanelProps['updateCurveAssignment'] =
    (_trackId, assignmentId, patch) => {
      void mutationAdapter.updateAssignment(
        asAssignmentUid(assignmentId),
        {
          visible: patch.visible,
          scaleMin: patch.scaleMin,
          scaleMax: patch.scaleMax,
          scaleType:
            patch.scaleType === 'log'
              ? 'logarithmic'
              : patch.scaleType,
          scaleDirection:
            patch.scaleDirection === 'reverse'
              ? 'reversed'
              : patch.scaleDirection,
          rangeMode: patch.rangeMode,
          color: patch.color,
          lineVisible: patch.lineVisible,
          lineStyle: patch.lineStyle,
          lineWidth: patch.lineWidth,
          lineOpacity: patch.lineOpacity,
          positionAnchor: patch.positionAnchor,
          horizontalOffsetPct: patch.horizontalOffsetPct,
          clipToTrack: patch.clipToTrack,
          fillSide: patch.fillSide,
          fillColor: patch.fillColor,
          fillOpacity: patch.fillOpacity,
          infillPattern: patch.infillPattern,
          infillIntervalColumn: patch.infillIntervalColumn,
          pairedManagedCurveUid: patch.pairedCurveId
            ? asManagedCurveUid(patch.pairedCurveId)
            : undefined,
          showQaqcWarnings: patch.showQaqcWarnings,
          showNullGaps: patch.showNullGaps,
          showOutOfRange: patch.showOutOfRange,
        },
      );
    };

  return {
    status: state.status,
    issues: state.issues,
    error: state.error,
    hasLoadedViewerWell: state.managedWellUid !== null,
    toolbarProps: {
      ...local.toolbar,
      selectedTrack: activeTrack,
      pendingAddTrackCurveCount:
        local.pendingAddTrackCurveUids.length,
      fullDepthRange: presentation.fullDepthRange,
      onAddTrack,
      onDeleteTrack,
      onMoveSelectedTrack,
      canMoveSelectedTrackLeft: selectedIndex > 0,
      canMoveSelectedTrackRight:
        selectedIndex >= 0 && selectedIndex < orderedTracks.length - 1,
      canAdjustSelectedCurveTrackWidthDown:
        Boolean(activeCurveTrack && activeCurveTrack.widthPx > 80),
      canAdjustSelectedCurveTrackWidthUp:
        Boolean(activeCurveTrack),
      onAdjustSelectedCurveTrackWidth,
      onResetCurveTrackWidths: () => {
        void mutationAdapter.resetCurveTrackWidths(
          local.defaultCurveTrackWidthPx,
        );
      },
    },
    curveInventoryProps: {
      ...local.curveInventory,
      availableCurves: presentation.curveCatalog,
      curveUsageCounts: curveUsageCounts(tracks),
      visibleTrackCurveIds: visibleTrackCurveIds(tracks),
      selectedTrackCurveIds: local.addTrackCurveSelectionMode
        ? new Set(local.pendingAddTrackCurveUids)
        : selectedTrackCurveIds(activeTrack),
      selectedCurveIds: unionCurveUids(
        local.selectedInventoryCurveUids,
        selectedCurveIds(selection, tracks),
        visibleTrackCurveIds(tracks),
      ),
      assignmentEnabled:
        local.addTrackCurveSelectionMode || activeCurveTrack !== null,
      onToggleCurveInSelectedTrack,
    },
    trackCanvasProps: {
      ...local.trackCanvas,
      tracks,
      selection,
      depthTicks: depthTicks(local.trackCanvas.viewDepthRange),
      managedSamplesByCurveId: sampleObjects(
        presentation.curveSamplesByCurveId,
      ),
      managedSampleErrorsByCurveId: {},
      curveCatalogItems: presentation.curveCatalog,
      onSelectTrack,
      onSelectCurve,
      onReorderCurve,
      onMoveCurveToTrack,
      onRemoveCurveFromTrack,
    },
    rightPanelProps: {
      ...(local.rightPanel ?? {}),
      tracks,
      selection,
      curveCatalogItems: presentation.curveCatalog,
      updateTrack,
      updateCurveAssignment,
    },
    wellHeader: presentation.wellHeader,
    trackBackdropMode: local.trackBackdropMode,
    renderPropertiesPanel: local.renderPropertiesPanel,
  };
}
