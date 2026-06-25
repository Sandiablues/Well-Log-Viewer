import { useEffect, useRef, useState } from 'react';
import type { ManagedWellUid } from '../identity/wdvIdentityV21';
import type { WellLogTrack } from '../prototype/trackLayoutModel';

export interface CanonicalLayoutResult {
  readonly tracks: WellLogTrack[];
  readonly selectedTrackId: string | null;
  readonly hydratedSessionKey: string;
}

export type WdvLayoutSourceState =
  | { readonly mode: 'idle' }
  | { readonly mode: 'probing'; readonly managedWellUid: ManagedWellUid; readonly generation: number }
  | { readonly mode: 'ready'; readonly source: 'canonical'; readonly managedWellUid: ManagedWellUid; readonly generation: number; readonly tracks: WellLogTrack[]; readonly selectedTrackId: string | null; readonly hydratedSessionKey: string }
  | { readonly mode: 'error'; readonly managedWellUid: ManagedWellUid; readonly generation: number; readonly error: Error };

export interface UseWdvLayoutSourceOptions {
  readonly managedWellUid: ManagedWellUid | null;
  readonly canonicalLoadKey: string | null;
  readonly loadCanonicalLayout: (signal: AbortSignal) => Promise<CanonicalLayoutResult | null>;
}

export async function orchestrateCanonicalWdvLayout(
  managedWellUid: ManagedWellUid,
  generation: number,
  loadCanonicalLayout: (signal: AbortSignal) => Promise<CanonicalLayoutResult | null>,
  onState: (state: WdvLayoutSourceState) => void,
  signal: AbortSignal,
): Promise<void> {
  onState({ mode: 'probing', managedWellUid, generation });
  try {
    const result = await loadCanonicalLayout(signal);
    if (signal.aborted || result === null) return;
    onState({ mode: 'ready', source: 'canonical', managedWellUid, generation, ...result });
  } catch (error) {
    if (signal.aborted) return;
    onState({ mode: 'error', managedWellUid, generation, error: error instanceof Error ? error : new Error(String(error)) });
  }
}

export function useWdvLayoutSource(options: UseWdvLayoutSourceOptions): WdvLayoutSourceState {
  const { managedWellUid, canonicalLoadKey, loadCanonicalLayout } = options;
  const [state, setState] = useState<WdvLayoutSourceState>({ mode: 'idle' });
  const generationRef = useRef(0);
  const loaderRef = useRef(loadCanonicalLayout);
  loaderRef.current = loadCanonicalLayout;
  useEffect(() => {
    generationRef.current += 1;
    const generation = generationRef.current;
    if (!managedWellUid || !canonicalLoadKey) {
      setState({ mode: 'idle' });
      return undefined;
    }
    const controller = new AbortController();
    void orchestrateCanonicalWdvLayout(managedWellUid, generation, (signal) => loaderRef.current(signal), setState, controller.signal);
    return () => controller.abort();
  }, [managedWellUid, canonicalLoadKey]);
  return state;
}
