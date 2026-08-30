import type { SelectionRef, WellLogTrack } from '../prototype/trackLayoutModel';
import type { DepthViewRange } from './WdvPresentationPrimitives';
import type { CombinationTrackState } from './viewportSemantics';
import { buildTrackCanvasRenderModel, type TrackCanvasRenderModel } from './trackCanvasRenderModel';
import { buildTrackSelectionPresentationModel, type TrackSelectionPresentationModel } from './trackSelectionPresentationModel';
import { buildTrackHeaderPresentationModel, type TrackHeaderPresentation } from './trackHeaderPresentationModel';
import { buildViewportToolbarPresentation, type ViewportToolbarPresentation } from './viewportToolbarPresentationModel';

export type ViewerPresentationModel = Readonly<{
  canvas: TrackCanvasRenderModel;
  selection: TrackSelectionPresentationModel;
  headerByTrackId: Readonly<Record<string, TrackHeaderPresentation>>;
  toolbar: ViewportToolbarPresentation;
}>;

export type ViewerPresentationModelInput = Readonly<{
  tracks: readonly Pick<WellLogTrack, 'trackId' | 'trackIndex'>[];
  selection: SelectionRef;
  globalViewportMode: boolean;
  combinationTrackStateById: Record<string, CombinationTrackState>;
  combinationTrackSelectedById: Record<string, boolean>;
  viewportTieMemberByTrackId: Record<string, boolean>;
  effectiveTrackDepthRangesById: Record<string, DepthViewRange>;
  viewDepthRange: DepthViewRange;
  fullDepthRange: DepthViewRange;
  dragPanActive: boolean;
  quickView: boolean;
  viewportTieCandidateTrackIds: readonly string[];
  combinationLockActionTrackIds: readonly string[];
  combinationLockedTrackIds: ReadonlySet<string>;
  viewportTieCanCreate: boolean;
  viewportTieCanUntie: boolean;
  viewportTieCreateDisabledReason: string;
}>;

/**
 * Single pure presentation boundary for viewer rendering.
 *
 * Semantic command state is resolved before this function. This model then
 * produces every renderer-facing viewport, selection, header, and toolbar
 * presentation fact from the same input snapshot. It owns no React state,
 * persistence, networking, or command execution.
 */
export function buildViewerPresentationModel(
  input: ViewerPresentationModelInput,
): ViewerPresentationModel {
  const canvas = buildTrackCanvasRenderModel({
    globalViewportMode: input.globalViewportMode,
    combinationTrackStateById: input.combinationTrackStateById,
    combinationTrackSelectedById: input.combinationTrackSelectedById,
    viewportTieMemberByTrackId: input.viewportTieMemberByTrackId,
    effectiveTrackDepthRangesById: input.effectiveTrackDepthRangesById,
    viewDepthRange: input.viewDepthRange,
    fullDepthRange: input.fullDepthRange,
    dragPanActive: input.dragPanActive,
  });

  const selection = buildTrackSelectionPresentationModel({
    trackIds: input.tracks.map((track) => track.trackId),
    selection: input.selection,
    combinationTrackSelectedById: canvas.combinationTrackSelectedById,
  });

  const headerByTrackId = buildTrackHeaderPresentationModel({
    tracks: input.tracks,
    stateByTrackId: canvas.combinationTrackStateById,
    selectedByTrackId: canvas.combinationTrackSelectedById,
    tiedByTrackId: canvas.viewportTieMemberByTrackId,
  });

  const trackIndexById = new Map(input.tracks.map((track) => [track.trackId, track.trackIndex] as const));
  const viewportTieCandidates = input.viewportTieCandidateTrackIds
    .filter((trackId) => trackIndexById.has(trackId))
    .sort((a, b) => (trackIndexById.get(a) ?? Number.MAX_SAFE_INTEGER) - (trackIndexById.get(b) ?? Number.MAX_SAFE_INTEGER))
    .map((trackId) => ({ trackId, label: `T${(trackIndexById.get(trackId) ?? 0) + 1}` }));
  const combinationSelectedUnlockedCount = input.combinationLockActionTrackIds
    .filter((trackId) => !input.combinationLockedTrackIds.has(trackId)).length;

  const toolbar = buildViewportToolbarPresentation({
    quickView: input.quickView,
    combinationSelectedCount: input.combinationLockActionTrackIds.length,
    combinationSelectedUnlockedCount,
    viewportTieCandidates,
    viewportTieCanCreate: input.viewportTieCanCreate,
    viewportTieCanUntie: input.viewportTieCanUntie,
    viewportTieCreateDisabledReason: input.viewportTieCreateDisabledReason,
  });

  return { canvas, selection, headerByTrackId, toolbar };
}
