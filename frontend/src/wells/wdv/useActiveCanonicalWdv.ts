import {
  useEffect,
  useMemo,
  useSyncExternalStore,
} from 'react';
import type {
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import type {
  CanonicalWorkspaceCommandIntent,
} from './canonicalWorkspaceApi';
import type {
  CanonicalWdvSelection,
} from './canonicalSelection';
import type {
  ActiveCanonicalWdvState,
} from './activeCanonicalWdvIntegration';
import {
  ActiveCanonicalWdvIntegration,
} from './activeCanonicalWdvIntegration';

export interface ActiveCanonicalWdvActions {
  execute(
    intent: CanonicalWorkspaceCommandIntent,
  ): Promise<ActiveCanonicalWdvState>;
  applyTemplate(input: {
    templateKey: string;
    workflowContext?: string | null;
  }): Promise<ActiveCanonicalWdvState>;
  setPresentationSelection(
    selection: CanonicalWdvSelection | undefined,
  ): void;
  reload(): Promise<ActiveCanonicalWdvState>;
  clear(): void;
}

export interface UseActiveCanonicalWdvResult {
  state: ActiveCanonicalWdvState;
  actions: ActiveCanonicalWdvActions;
}

export function useActiveCanonicalWdv(
  managedWellUid: ManagedWellUid | null,
  integrationFactory: () => ActiveCanonicalWdvIntegration =
    () => new ActiveCanonicalWdvIntegration(),
): UseActiveCanonicalWdvResult {
  const integration = useMemo(
    () => integrationFactory(),
    [integrationFactory],
  );

  const state = useSyncExternalStore(
    (listener) => integration.subscribe(listener),
    () => integration.getState(),
    () => integration.getState(),
  );

  useEffect(() => {
    if (managedWellUid === null) {
      integration.clear();
      return;
    }

    void integration.load(managedWellUid);
  }, [integration, managedWellUid]);

  useEffect(
    () => () => integration.dispose(),
    [integration],
  );

  const actions = useMemo<ActiveCanonicalWdvActions>(() => ({
    execute: (intent) => integration.execute(intent),
    applyTemplate: (input) => integration.applyTemplate(input),
    setPresentationSelection: (selection) =>
      integration.setPresentationSelection(selection),
    reload: () => {
      if (managedWellUid === null) {
        throw new Error('No managed well is active');
      }
      return integration.load(managedWellUid);
    },
    clear: () => integration.clear(),
  }), [integration, managedWellUid]);

  return {
    state,
    actions,
  };
}
