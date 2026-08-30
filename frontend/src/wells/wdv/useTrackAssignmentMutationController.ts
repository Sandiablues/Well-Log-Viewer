import { useCallback } from 'react';

type MutationOptions = Readonly<{ preserveInteraction?: boolean }>;

export function useTrackAssignmentMutationController<
  TSession extends { revision: number },
>(args: Readonly<{
  runSerializedCanonicalMutation: (
    commandPath: string,
    body: Record<string, unknown>,
    options?: MutationOptions,
  ) => Promise<TSession>;
  refreshCanonicalSession: (options?: MutationOptions) => Promise<void>;
}>) {
  const mutate = useCallback(
    (
      commandPath: string,
      body: Record<string, unknown>,
    ) => args.runSerializedCanonicalMutation(
      commandPath,
      body,
      { preserveInteraction: true },
    ),
    [args.runSerializedCanonicalMutation],
  );

  const commitTrackWidth = useCallback(
    (trackUid: string, widthPx: number) => mutate('tracks/update', {
      track_uid: trackUid,
      width_px: widthPx,
    }),
    [mutate],
  );

  const updateAssignment = useCallback(
    (
      assignmentUid: string,
      updateBody: Readonly<Record<string, unknown>>,
    ) => mutate('assignments/update', {
      assignment_uid: assignmentUid,
      ...updateBody,
    }),
    [mutate],
  );

  const commitAssignmentLineStyle = useCallback(
    (
      assignmentUid: string,
      lineStyleBody: Readonly<Record<string, unknown>>,
    ) => mutate('assignments/line-style', {
      assignment_uid: assignmentUid,
      ...lineStyleBody,
    }),
    [mutate],
  );

  const mutateOnceWithReconcile = useCallback(
    async (
      commandPath: string,
      body: Record<string, unknown>,
    ): Promise<TSession> => {
      try {
        return await mutate(commandPath, body);
      } catch (error) {
        if (!(error instanceof Error && error.message.startsWith('409 '))) {
          throw error;
        }
        await args.refreshCanonicalSession({ preserveInteraction: true });
        return mutate(commandPath, body);
      }
    },
    [args.refreshCanonicalSession, mutate],
  );

  const assignCurveToTrack = useCallback(
    (trackUid: string, managedCurveUid: string) => mutateOnceWithReconcile(
      'assignments',
      {
        track_uid: trackUid,
        managed_curve_uid: managedCurveUid,
      },
    ),
    [mutateOnceWithReconcile],
  );

  const removeCurveAssignment = useCallback(
    (assignmentUid: string) => mutateOnceWithReconcile(
      'assignments/remove',
      { assignment_uid: assignmentUid },
    ),
    [mutateOnceWithReconcile],
  );

  return {
    commitTrackWidth,
    updateAssignment,
    commitAssignmentLineStyle,
    assignCurveToTrack,
    removeCurveAssignment,
  } as const;
}
