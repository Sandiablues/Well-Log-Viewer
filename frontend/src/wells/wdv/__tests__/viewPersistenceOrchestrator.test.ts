import { describe, expect, it, vi } from 'vitest';
import {
  commitSettledViewState,
  loadAuthoritativeStartupView,
  saveRecoverySnapshotsFromCommittedView,
  saveSnapshotFromCommittedView,
} from '../viewPersistenceOrchestrator';

type View = { global_viewport: { min: number; max: number } };
const VIEW: View = { global_viewport: { min: 1000, max: 1100 } };

function response(overrides: Record<string, unknown> = {}) {
  return { available: true, session_revision: 7, current_session_revision: 7, view_revision: 3, view_state: VIEW, ...overrides };
}

describe('viewPersistenceOrchestrator', () => {
  it('commits against the exact current view revision', async () => {
    const fetchJson = vi.fn()
      .mockResolvedValueOnce(response())
      .mockResolvedValueOnce(response({ view_revision: 4 }));
    const result = await commitSettledViewState({ fetchJson, wellUid: 'well 1', sessionRevision: 7, viewState: VIEW, currentSessionRevision: () => 7 });
    expect(result?.view_revision).toBe(4);
    const body = JSON.parse(fetchJson.mock.calls[1][1].body);
    expect(body.expected_session_revision).toBe(7);
    expect(body.expected_view_revision).toBe(3);
    expect(body.view_state).toEqual(VIEW);
  });

  it('aborts a commit if canonical revision changes after the read', async () => {
    let revision = 7;
    const fetchJson = vi.fn().mockImplementation(async () => { revision = 8; return response(); });
    const result = await commitSettledViewState({ fetchJson, wellUid: 'w1', sessionRevision: 7, viewState: VIEW, currentSessionRevision: () => revision });
    expect(result).toBeNull();
    expect(fetchJson).toHaveBeenCalledTimes(1);
  });

  it('loads exact committed view before recovery', async () => {
    const fetchJson = vi.fn().mockResolvedValueOnce(response());
    const result = await loadAuthoritativeStartupView<View>({ fetchJson, authorityWellUid: 'w1', expectedSessionRevision: 7, currentSessionRevision: () => 7 });
    expect(result).toEqual({ status: 'committed', viewState: VIEW });
    expect(fetchJson).toHaveBeenCalledTimes(1);
  });

  it('falls back to exact-revision recovery when committed view is unavailable', async () => {
    const fetchJson = vi.fn()
      .mockResolvedValueOnce(response({ available: false, view_state: null }))
      .mockResolvedValueOnce(response());
    const result = await loadAuthoritativeStartupView<View>({ fetchJson, authorityWellUid: 'w1', expectedSessionRevision: 7, currentSessionRevision: () => 7 });
    expect(result).toEqual({ status: 'recovery', viewState: VIEW });
  });

  it('aborts startup load if canonical revision changes in flight', async () => {
    let revision = 7;
    const fetchJson = vi.fn().mockImplementation(async () => { revision = 8; return response(); });
    const result = await loadAuthoritativeStartupView<View>({ fetchJson, authorityWellUid: 'w1', expectedSessionRevision: 7, currentSessionRevision: () => revision });
    expect(result.status).toBe('aborted');
    expect(fetchJson).toHaveBeenCalledTimes(1);
  });

  it('snapshots only an exact committed revision', async () => {
    const fetchJson = vi.fn().mockResolvedValue(response());
    const saved = await saveSnapshotFromCommittedView({ fetchJson, wellUid: 'w1', committed: response(), sessionRevision: 7, currentSessionRevision: () => 7 });
    expect(saved?.available).toBe(true);
    const body = JSON.parse(fetchJson.mock.calls[0][1].body);
    expect(body).toEqual({ expected_revision: 7, expected_view_revision: 3 });
  });

  it('writes recovery snapshots for every target from one committed revision', async () => {
    const fetchJson = vi.fn().mockResolvedValue(response());
    const results = await saveRecoverySnapshotsFromCommittedView({ fetchJson, wellUids: ['w1', 'w2'], committed: response(), sessionRevision: 7, currentSessionRevision: () => 7 });
    expect(results).toHaveLength(2);
    expect(fetchJson).toHaveBeenCalledTimes(2);
    expect(fetchJson.mock.calls[0][0]).toContain('/w1/recovery-state');
    expect(fetchJson.mock.calls[1][0]).toContain('/w2/recovery-state');
  });
});
