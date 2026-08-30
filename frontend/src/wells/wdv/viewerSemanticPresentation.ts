import type { SelectionRef, WellLogTrack } from '../prototype/trackLayoutModel';
import type { DepthViewRange } from './WdvPresentationPrimitives';
import {
  deriveViewportSemantics,
  type ViewportSemantics,
  type ViewportTieGroup,
} from './viewportSemantics';
import {
  buildViewerPresentationModel,
  type ViewerPresentationModel,
} from './viewerPresentationModel';

export type ViewerSemanticPresentationInput = Readonly<{
  tracks: readonly Pick<WellLogTrack, 'trackId' | 'trackIndex'>[];
  selection: SelectionRef;
  selectedTrackId: string | null;
  combinationActiveTrackIds: string[];
  combinationLockedTrackIds: string[];
  multiHighlightedTrackIds: string[];
  trackDepthRangesById: Record<string, DepthViewRange>;
  trackFullDepthRangesById?: Record<string, DepthViewRange>;
  combinationGroupViewRange: DepthViewRange | null;
  viewDepthRange: DepthViewRange;
  viewportTieGroups: ViewportTieGroup[];
  viewportTieSuspendedTrackIds: string[];
  fullDepthRange: DepthViewRange;
  dragPanActive: boolean;
  quickView: boolean;
  combinationLockActionTrackIds: readonly string[];
}>;

export type ViewerSemanticPresentation = Readonly<{
  semantics: ViewportSemantics;
  presentation: ViewerPresentationModel;
}>;

/**
 * Single composition boundary between semantic viewport state and renderer-facing
 * presentation state. It owns no React state, persistence, networking, or command
 * execution. WdvPageBoundary supplies raw semantic inputs and consumes the result.
 */
export function buildViewerSemanticPresentation(
  input: ViewerSemanticPresentationInput,
): ViewerSemanticPresentation {
  const semantics = deriveViewportSemantics({
    trackIdsInDisplayOrder: input.tracks.map((track) => track.trackId),
    selectedTrackId: input.selectedTrackId,
    combinationActiveTrackIds: input.combinationActiveTrackIds,
    combinationLockedTrackIds: input.combinationLockedTrackIds,
    multiHighlightedTrackIds: input.multiHighlightedTrackIds,
    trackDepthRangesById: input.trackDepthRangesById,
    trackFullDepthRangesById: input.trackFullDepthRangesById ?? {},
    combinationGroupViewRange: input.combinationGroupViewRange,
    viewDepthRange: input.viewDepthRange,
    viewportTieGroups: input.viewportTieGroups,
    viewportTieSuspendedTrackIds: input.viewportTieSuspendedTrackIds,
  });

  const presentation = buildViewerPresentationModel({
    tracks: input.tracks,
    selection: input.selection,
    // WDV_SELECTION_VIEWPORT_PRESENTATION_ORTHOGONALITY_V1_0_0
    // `semantics.globalViewportMode` remains authoritative for command scope
    // (Zoom/Full/Reset/Drag when no track is selected). It must not also switch
    // renderer ownership when selection toggles. Rendering always consumes the
    // already-established effective per-track ranges so selection remains
    // orthogonal to viewport presentation.
    globalViewportMode: false,
    combinationTrackStateById: semantics.combinationTrackStateById,
    combinationTrackSelectedById: semantics.combinationTrackSelectedById,
    viewportTieMemberByTrackId: semantics.viewportTieMemberByTrackId,
    effectiveTrackDepthRangesById: semantics.effectiveTrackDepthRangesById,
    viewDepthRange: input.viewDepthRange,
    fullDepthRange: input.fullDepthRange,
    dragPanActive: input.dragPanActive,
    quickView: input.quickView,
    viewportTieCandidateTrackIds: semantics.viewportTieCandidateTrackIds,
    combinationLockActionTrackIds: input.combinationLockActionTrackIds,
    combinationLockedTrackIds: new Set(input.combinationLockedTrackIds),
    viewportTieCanCreate: semantics.viewportTieCanCreate,
    viewportTieCanUntie: semantics.viewportTieCanUntie,
    viewportTieCreateDisabledReason: semantics.viewportTieCreateDisabledReason,
  });

  return { semantics, presentation };
}
