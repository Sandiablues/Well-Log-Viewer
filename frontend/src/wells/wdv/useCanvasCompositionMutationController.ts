import { useCallback } from 'react';

export type CompositionMutationOptions = Readonly<{
  preserveInteraction?: boolean;
}>;

type RevisionRef = Readonly<{ current: number }>;

export function useCanvasCompositionMutationController<
  TSession extends { revision: number },
>(args: Readonly<{
  managedWellUid: string | null | undefined;
  canonicalRevisionRef: RevisionRef;
  applyCanonicalSession: (
    session: TSession,
    options?: CompositionMutationOptions,
  ) => void;
  executeCanonicalCommand: (
    commandPath: string,
    body: Record<string, unknown>,
  ) => Promise<TSession>;
  refreshCanonicalSession: (
    options?: CompositionMutationOptions,
  ) => Promise<void>;
  runSerializedCanonicalMutation: (
    commandPath: string,
    body: Record<string, unknown>,
    options?: CompositionMutationOptions,
  ) => Promise<TSession>;
}>) {
  const serialized = useCallback(
    (
      commandPath: string,
      body: Record<string, unknown>,
    ): Promise<TSession> => args.runSerializedCanonicalMutation(
      commandPath,
      body,
      { preserveInteraction: true },
    ),
    [args.runSerializedCanonicalMutation],
  );

  const configureBlankTrack = useCallback(
    async (command: Record<string, unknown>): Promise<TSession> => {
      const session = await serialized('tracks/configured', command);
      // WDV_CONFIGURED_TRACK_READ_AFTER_WRITE_RECONCILIATION_V1_0_0
      // The configured-track command response is not sufficient to guarantee
      // that the live empty-canvas projection sees the newly durable track.
      // Re-read canonical state immediately; backend authority is preserved.
      await args.refreshCanonicalSession({ preserveInteraction: true });
      return session;
    },
    [args.refreshCanonicalSession, serialized],
  );

  const removeTrack = useCallback(
    (trackUid: string) => serialized('tracks/remove', { track_uid: trackUid }),
    [serialized],
  );

  const reorderTracks = useCallback(
    (trackUids: string[]) => serialized('tracks/reorder', { track_uids: trackUids }),
    [serialized],
  );

  const configureTrack = useCallback(
    (
      trackUid: string,
      config: Readonly<{
        trackName: string;
        rendererType: string;
        trackRole: string;
        widthPx: number;
      }>,
    ) => serialized('tracks/update', {
      track_uid: trackUid,
      track_name: config.trackName,
      renderer_type: config.rendererType,
      track_role: config.trackRole,
      width_px: config.widthPx,
    }),
    [serialized],
  );

  const moveAssignment = useCallback(
    (
      assignmentUid: string,
      targetTrackUid: string,
      targetStackIndex: number,
    ) => serialized('assignments/move', {
      assignment_uid: assignmentUid,
      target_track_uid: targetTrackUid,
      target_stack_index: targetStackIndex,
    }),
    [serialized],
  );

  const reorderAssignments = useCallback(
    (trackUid: string, assignmentUids: string[]) => serialized(
      'assignments/reorder',
      {
        track_uid: trackUid,
        assignment_uids: assignmentUids,
      },
    ),
    [serialized],
  );

  const removeAssignment = useCallback(
    (assignmentUid: string) => serialized(
      'assignments/remove',
      { assignment_uid: assignmentUid },
    ),
    [serialized],
  );

  const clearCanvas = useCallback(async (): Promise<TSession> => {
    if (!args.managedWellUid) {
      throw new Error('Clear Canvas requires an active managed well.');
    }

    const executeClear = async (): Promise<TSession> => {
      if (args.canonicalRevisionRef.current < 0) {
        await args.refreshCanonicalSession();
      }
      if (args.canonicalRevisionRef.current < 0) {
        throw new Error('Clear Canvas could not resolve the canonical WDV revision.');
      }
      return args.executeCanonicalCommand(
        'tracks/clear',
        { preserve_depth_tracks: false },
      );
    };

    let session: TSession;
    try {
      session = await executeClear();
    } catch (error) {
      if (!(error instanceof Error) || !error.message.startsWith('409 ')) {
        throw error;
      }
      await args.refreshCanonicalSession();
      session = await executeClear();
    }

    args.applyCanonicalSession(session);
    return session;
  }, [
    args.applyCanonicalSession,
    args.canonicalRevisionRef,
    args.executeCanonicalCommand,
    args.managedWellUid,
    args.refreshCanonicalSession,
  ]);

  return {
    configureBlankTrack,
    removeTrack,
    clearCanvas,
    reorderTracks,
    configureTrack,
    moveAssignment,
    reorderAssignments,
    removeAssignment,
  } as const;
}
