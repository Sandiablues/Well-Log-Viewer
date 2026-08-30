import { describe, expect, it, vi } from 'vitest';
import {
  canonicalCommandRequestBody,
  executeCanonicalSessionCommand,
  type CanonicalCommandFetch,
} from '../canonicalSessionCommandOrchestrator';

type TestSession = { revision: number; tracks: Array<{ track_uid: string }> };

function asFetch<TValue>(
  implementation: (url: string, init?: RequestInit) => Promise<TValue>,
): CanonicalCommandFetch {
  return async <T>(url: string, init?: RequestInit): Promise<T> =>
    implementation(url, init) as unknown as Promise<T>;
}

describe('canonical session command orchestrator', () => {
  it('adds expected_revision without mutating the source body', () => {
    const body = { track_uid: 't1' };
    expect(canonicalCommandRequestBody(7, body)).toEqual({ track_uid: 't1', expected_revision: 7 });
    expect(body).toEqual({ track_uid: 't1' });
  });

  it('posts a revision-guarded canonical command to the managed well', async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const fetchJson = asFetch(async (url, init) => {
      calls.push([url, init]);
      return { revision: 12, tracks: [{ track_uid: 't1' }] } satisfies TestSession;
    });

    const result = await executeCanonicalSessionCommand<TestSession>({
      managedWellUid: 'well / 1',
      commandPath: 'tracks/remove',
      body: { track_uid: 't1' },
      getExpectedRevision: () => 11,
      fetchJson,
    });

    expect(result.revision).toBe(12);
    expect(calls).toHaveLength(1);
    const [url, init] = calls[0];
    expect(url).toBe('/api/wlv/v2/wdv/session-commands/well%20%2F%201/tracks/remove');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ track_uid: 't1', expected_revision: 11 });
  });

  it('reads the revision at execution time rather than capture time', async () => {
    let revision = 3;
    const fetchJson = asFetch(async (_url, init) => {
      expect(JSON.parse(String(init?.body)).expected_revision).toBe(4);
      return { revision: 5, tracks: [] } satisfies TestSession;
    });
    revision = 4;

    await executeCanonicalSessionCommand<TestSession>({
      managedWellUid: 'well-1',
      commandPath: 'tracks/reorder',
      body: { track_uids: [] },
      getExpectedRevision: () => revision,
      fetchJson,
    });
  });

  it('refuses to execute without a canonical managed well uid', async () => {
    let called = false;
    const fetchJson = asFetch(async () => {
      called = true;
      return { revision: 1, tracks: [] } satisfies TestSession;
    });

    await expect(executeCanonicalSessionCommand<TestSession>({
      managedWellUid: null,
      commandPath: 'tracks/remove',
      body: { track_uid: 't1' },
      getExpectedRevision: () => 0,
      fetchJson,
    })).rejects.toThrow('managedWellUid is not set');
    expect(called).toBe(false);
  });

  it('records success and error outcomes without swallowing revision conflicts', async () => {
    const end = vi.fn();
    const beginDiagnostic = vi.fn(() => ({ end }));

    await executeCanonicalSessionCommand<TestSession>({
      managedWellUid: 'well-1',
      commandPath: 'tracks/remove',
      body: { track_uid: 't1' },
      getExpectedRevision: () => 8,
      fetchJson: asFetch(async () => ({ revision: 9, tracks: [] } satisfies TestSession)),
      beginDiagnostic,
    });
    expect(end).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'success', responseRevision: 9 }));

    const conflict = new Error('409 revision conflict');
    await expect(executeCanonicalSessionCommand<TestSession>({
      managedWellUid: 'well-1',
      commandPath: 'tracks/remove',
      body: { track_uid: 't1' },
      getExpectedRevision: () => 9,
      fetchJson: asFetch(async () => { throw conflict; }),
      beginDiagnostic,
    })).rejects.toBe(conflict);
    expect(end).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'error', error: '409 revision conflict' }));
  });
});
