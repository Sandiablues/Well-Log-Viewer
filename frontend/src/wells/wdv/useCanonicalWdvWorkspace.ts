import {
  useEffect,
  useMemo,
  useState,
} from 'react';
import type {
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalSessionCommandV21,
} from '../prototype/canonicalViewerPackageV21';
import {
  CanonicalWdvWorkspaceController,
} from '../prototype/canonicalWdvWorkspaceController';
import type {
  CanonicalWdvWorkspaceState,
} from '../prototype/canonicalWdvWorkspaceController';

export interface UseCanonicalWdvWorkspaceResult {
  state: CanonicalWdvWorkspaceState;
  execute: (command: CanonicalSessionCommandV21) => Promise<void>;
  applyTemplate: (
    templateKey: string,
    workflowContext?: string | null,
  ) => Promise<void>;
  clear: () => void;
}

export function useCanonicalWdvWorkspace(
  managedWellUid: ManagedWellUid | null,
  maxSamples = 4000,
): UseCanonicalWdvWorkspaceResult {
  const controller = useMemo(
    () => new CanonicalWdvWorkspaceController(),
    [],
  );
  const [state, setState] = useState(controller.getState());

  useEffect(
    () => controller.subscribe(setState),
    [controller],
  );

  useEffect(() => {
    if (managedWellUid === null) {
      controller.clear();
      return;
    }
    void controller.load(managedWellUid, maxSamples);
    return () => {
      controller.clear();
    };
  }, [controller, managedWellUid, maxSamples]);

  return {
    state,
    execute: async (command) => {
      await controller.execute(command, maxSamples);
    },
    applyTemplate: async (templateKey, workflowContext = null) => {
      await controller.applyTemplate(
        { templateKey, workflowContext },
        maxSamples,
      );
    },
    clear: () => controller.clear(),
  };
}
