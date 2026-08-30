import { describe, expect, it } from 'vitest';
import { createWbvInteractionCommandAuthority } from '../interactionDomain/authority';
import type { WbvInteractionStateV2 } from '../interactionDomain/contracts';

const state = (revision: number): WbvInteractionStateV2 => ({ revision } as WbvInteractionStateV2);
const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

describe('WBV interaction command authority latency and concurrency contract', () => {
  it('serializes 100 revisioned commands under variable latency', async () => {
    let backendRevision = 290;
    let concurrent = 0;
    let maxConcurrent = 0;
    const expected: number[] = [];
    const applied: number[] = [];
    const authority = createWbvInteractionCommandAuthority({
      applyState: (value) => applied.push(value.revision),
      applyError: () => undefined,
    });
    authority.seed(state(backendRevision));
    const commands = Array.from({ length: 100 }, (_, index) => authority.runRevisioned(async (revision) => {
      expected.push(revision);
      concurrent += 1;
      maxConcurrent = Math.max(maxConcurrent, concurrent);
      await delay((index * 7) % 11);
      expect(revision).toBe(backendRevision);
      backendRevision += 1;
      concurrent -= 1;
      return state(backendRevision);
    }));
    await Promise.all(commands);
    expect(maxConcurrent).toBe(1);
    expect(expected).toEqual(Array.from({ length: 100 }, (_, i) => 290 + i));
    expect(authority.latestRevision()).toBe(390);
    expect(applied[applied.length - 1]).toBe(390);
  });

  it('prevents observe/start duplicate expected revisions', async () => {
    let backendRevision = 290;
    const seen: number[] = [];
    const authority = createWbvInteractionCommandAuthority({ applyState: () => undefined, applyError: () => undefined });
    authority.seed(state(290));
    const observe = authority.runRevisioned(async (revision) => {
      seen.push(revision); await delay(15); backendRevision += 1; return state(backendRevision);
    });
    const start = authority.runRevisioned(async (revision) => {
      seen.push(revision); expect(revision).toBe(backendRevision); backendRevision += 1; return state(backendRevision);
    });
    await Promise.all([observe, start]);
    expect(seen).toEqual([290, 291]);
  });

  it('discards an older session response arriving after a newer response', async () => {
    const applied: number[] = [];
    const authority = createWbvInteractionCommandAuthority({ applyState: (value) => applied.push(value.revision), applyError: () => undefined });
    authority.seed(state(50));
    const oldResponse = authority.runSession(async () => { await delay(20); return state(51); });
    const newResponse = authority.runSession(async () => { await delay(2); return state(52); });
    await Promise.all([oldResponse, newResponse]);
    expect(applied).toEqual([50, 52]);
    expect(authority.latestRevision()).toBe(52);
  });

  it('does not apply responses after disposal', async () => {
    const applied: number[] = [];
    const authority = createWbvInteractionCommandAuthority({ applyState: (value) => applied.push(value.revision), applyError: () => undefined });
    authority.seed(state(1));
    const command = authority.runSession(async () => { await delay(5); return state(2); });
    authority.dispose();
    await command;
    expect(applied).toEqual([1]);
  });

  it('continues the revision queue after a rejected command', async () => {
    const errors: Array<string | null> = [];
    const authority = createWbvInteractionCommandAuthority({ applyState: () => undefined, applyError: (value) => errors.push(value) });
    authority.seed(state(7));
    const failed = authority.runRevisioned(async () => { throw new Error('controlled failure'); });
    const next = authority.runRevisioned(async (revision) => state(revision + 1));
    expect(await failed).toBeNull();
    expect((await next)?.revision).toBe(8);
    expect(authority.latestRevision()).toBe(8);
    expect(errors).toContain('controlled failure');
  });
});
