import { buildViewerSemanticPresentation } from './viewerSemanticPresentation';
import { useViewportCommandExecution } from './useViewportCommandExecution';
import { useDragPanExecution } from './useDragPanExecution';
import { useViewportNavigationExecution } from './useViewportNavigationExecution';

type SemanticInput = Parameters<typeof buildViewerSemanticPresentation>[0];
type CommandInput = Parameters<typeof useViewportCommandExecution>[0];
type DragInput = Parameters<typeof useDragPanExecution>[0];
type NavigationInput = Parameters<typeof useViewportNavigationExecution>[0];

type CommandBaseInput = Omit<CommandInput,
  | 'selectedViewportTieGroup'
  | 'selectedViewportTieLeaderLocked'
  | 'groupActionTrackIds'
  | 'globalViewportMode'
  | 'lockedCombinationTrackIds'
  | 'activeGroupViewRange'
  | 'fullRange'
  | 'magnificationReferenceRange'
  | 'effectiveTrackDepthRangesById'
  | 'viewportTieCanCreate'
  | 'viewportTieCanUntie'
  | 'viewportTieCandidateTrackIds'
  | 'viewportTieActionTrackIds'
  | 'viewportTieSelectedTiedTrackIds'
  | 'viewportTieMembershipByTrackId'
>;

type DragBaseInput = Omit<DragInput,
  | 'globalViewportMode'
  | 'effectiveTrackDepthRangesById'
>;

type NavigationBaseInput = Omit<NavigationInput,
  | 'selectedViewportTieGroup'
  | 'groupActionTrackIds'
  | 'activeGroupViewRange'
  | 'viewportCommandFullRange'
  | 'globalViewportMode'
  | 'lockedCombinationTrackIds'
  | 'applyCombinationRange'
  | 'recordGroupHistory'
>;

export type ViewerViewportCompositionArgs = {
  semanticInput: SemanticInput;
  commandInput: CommandBaseInput;
  dragInput: DragBaseInput;
  navigationInput: NavigationBaseInput;
};

/**
 * Top-level frontend viewport composition boundary.
 *
 * One immutable semantic snapshot drives presentation plus all settled viewport
 * controllers. High-frequency drag state remains local; persistence remains in
 * the separate revision-guarded committed-view lane.
 */
export function useViewerViewportComposition(args: ViewerViewportCompositionArgs) {
  const viewerSemanticPresentation = buildViewerSemanticPresentation(args.semanticInput);
  const viewportSemantics = viewerSemanticPresentation.semantics;

  const commandExecution = useViewportCommandExecution({
    ...args.commandInput,
    selectedViewportTieGroup: viewportSemantics.selectedViewportTieGroup,
    selectedViewportTieLeaderLocked: viewportSemantics.selectedViewportTieLeaderLocked,
    groupActionTrackIds: viewportSemantics.groupActionTrackIds,
    globalViewportMode: viewportSemantics.globalViewportMode,
    lockedCombinationTrackIds: viewportSemantics.lockedCombinationTrackIds,
    activeGroupViewRange: viewportSemantics.activeGroupViewRange,
    fullRange: viewportSemantics.viewportCommandFullRange ?? args.commandInput.viewDepthRange,
    magnificationReferenceRange: args.semanticInput.fullDepthRange,
    effectiveTrackDepthRangesById: viewportSemantics.effectiveTrackDepthRangesById,
    viewportTieCanCreate: viewportSemantics.viewportTieCanCreate,
    viewportTieCanUntie: viewportSemantics.viewportTieCanUntie,
    viewportTieCandidateTrackIds: viewportSemantics.viewportTieCandidateTrackIds,
    viewportTieActionTrackIds: viewportSemantics.viewportTieActionTrackIds,
    viewportTieSelectedTiedTrackIds: viewportSemantics.viewportTieSelectedTiedTrackIds,
    viewportTieMembershipByTrackId: viewportSemantics.viewportTieMembershipByTrackId,
  });

  const dragExecution = useDragPanExecution({
    ...args.dragInput,
    globalViewportMode: viewportSemantics.globalViewportMode,
    effectiveTrackDepthRangesById: viewportSemantics.effectiveTrackDepthRangesById,
  });

  const navigationExecution = useViewportNavigationExecution({
    ...args.navigationInput,
    selectedViewportTieGroup: viewportSemantics.selectedViewportTieGroup,
    groupActionTrackIds: viewportSemantics.groupActionTrackIds,
    activeGroupViewRange: viewportSemantics.activeGroupViewRange,
    viewportCommandFullRange: viewportSemantics.viewportCommandFullRange,
    globalViewportMode: viewportSemantics.globalViewportMode,
    lockedCombinationTrackIds: viewportSemantics.lockedCombinationTrackIds,
    applyCombinationRange: commandExecution.applyCombinationRange,
    recordGroupHistory: commandExecution.recordGroupHistory,
  });

  return {
    viewerSemanticPresentation,
    viewportSemantics,
    viewerPresentationModel: viewerSemanticPresentation.presentation,
    ...commandExecution,
    ...dragExecution,
    ...navigationExecution,
  };
}
