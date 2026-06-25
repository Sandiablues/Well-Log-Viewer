import { describe, expect, it, vi } from 'vitest';
import { orchestrateCanonicalWdvLayout, type CanonicalLayoutResult, type WdvLayoutSourceState } from '../useWdvLayoutSource';

const WELL = '018f0f2c-9d39-7c2a-8f3e-c4f34af1c101' as never;
const RESULT: CanonicalLayoutResult = { tracks: [], selectedTrackId: null, hydratedSessionKey: 'k' };

describe('canonical-only layout orchestration', () => {
  it('loads canonical state directly and emits ready canonical', async () => {
    const states: WdvLayoutSourceState[] = [];
    const loader = vi.fn().mockResolvedValue(RESULT);
    await orchestrateCanonicalWdvLayout(WELL, 1, loader, (s) => states.push(s), new AbortController().signal);
    expect(loader).toHaveBeenCalledTimes(1);
    expect(states.map((s) => s.mode)).toEqual(['probing', 'ready']);
    expect(states[1]).toMatchObject({ source: 'canonical', hydratedSessionKey: 'k' });
  });
  it('does not emit ready when prerequisites are incomplete', async () => {
    const states: WdvLayoutSourceState[] = [];
    await orchestrateCanonicalWdvLayout(WELL, 2, vi.fn().mockResolvedValue(null), (s) => states.push(s), new AbortController().signal);
    expect(states.map((s) => s.mode)).toEqual(['probing']);
  });
  it('rejects stale responses after abort', async () => {
    const states: WdvLayoutSourceState[] = [];
    const controller = new AbortController();
    let resolve!: (value: CanonicalLayoutResult) => void;
    const loader = vi.fn().mockReturnValue(new Promise<CanonicalLayoutResult>((r) => { resolve = r; }));
    const pending = orchestrateCanonicalWdvLayout(WELL, 3, loader, (s) => states.push(s), controller.signal);
    controller.abort();
    resolve(RESULT);
    await pending;
    expect(states.map((s) => s.mode)).toEqual(['probing']);
  });
  it('emits error on canonical load failure', async () => {
    const states: WdvLayoutSourceState[] = [];
    await orchestrateCanonicalWdvLayout(WELL, 4, vi.fn().mockRejectedValue(new Error('boom')), (s) => states.push(s), new AbortController().signal);
    expect(states[states.length - 1]?.mode).toBe('error');
  });
});
