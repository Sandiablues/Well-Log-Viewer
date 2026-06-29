import type {
  CurveAssignment,
  CurveCatalogItem,
  SelectionRef,
  WellLogTrack,
} from './trackLayoutModel';

export function findCurveForAssignment(
  curveCatalogItems: CurveCatalogItem[],
  assignment: CurveAssignment,
): CurveCatalogItem | null {
  const sameOwner = (curve: CurveCatalogItem): boolean => (
    assignment.managedWellUid == null
    || curve.managedWellUid == null
    || curve.managedWellUid === assignment.managedWellUid
  );
  if (assignment.curveUid != null) {
    const exactUid = curveCatalogItems.find((curve) => (
      sameOwner(curve)
      && curve.curveUid != null
      && curve.curveUid === assignment.curveUid
    ));
    if (exactUid) return exactUid;
  }
  return curveCatalogItems.find((curve) => (
    sameOwner(curve) && curve.curveId === assignment.curveId
  )) ?? null;
}

export function normalizePropertiesSelection(
  tracks: WellLogTrack[],
  selection: SelectionRef,
  curveCatalogItems: CurveCatalogItem[],
): SelectionRef {
  const selectedTrack = tracks.find((track) => track.trackId === selection.trackId)
    ?? tracks[0];

  if (!selectedTrack) {
    return selection;
  }

  if (selection.kind !== 'curve' || selectedTrack.trackType !== 'curve') {
    return { kind: 'track', trackId: selectedTrack.trackId };
  }

  const assignment = selectedTrack.curves.find(
    (candidate) => candidate.assignmentId === selection.assignmentId,
  );

  if (!assignment || !findCurveForAssignment(curveCatalogItems, assignment)) {
    return { kind: 'track', trackId: selectedTrack.trackId };
  }

  return selection;
}
