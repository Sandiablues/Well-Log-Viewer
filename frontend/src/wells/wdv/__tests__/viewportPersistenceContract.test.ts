import { describe, expect, it } from 'vitest';
import {
  buildPersistedTrackViewports,
  buildPersistedViewportTieGroups,
  restorePersistedTrackViewports,
  restorePersistedViewportTieGroups,
  restorePersistedViewportTieSuspensions,
} from '../viewportPersistenceContract';

const A = { min: 1000, max: 1100 };
const B = { min: 3000, max: 3010 };

const tie = {
  groupId: 'viewport-tie:t1',
  leaderTrackId: 't1',
  memberTrackIds: ['t1', 't2'],
  viewport: A,
};

describe('viewportPersistenceContract', () => {
  it('persists detached per-track viewports independently of Lock', () => {
    expect(buildPersistedTrackViewports(['t1', 't2'], { t1: A, t2: B, stale: A }))
      .toEqual({ t1: A, t2: B });
  });

  it('serializes Tie relationships as explicit backend contract fields', () => {
    expect(buildPersistedViewportTieGroups([tie])).toEqual([{
      group_id: 'viewport-tie:t1',
      leader_track_uid: 't1',
      member_track_uids: ['t1', 't2'],
      viewport: A,
    }]);
  });

  it('restores explicit per-track viewport state ahead of legacy locked-only state', () => {
    expect(restorePersistedTrackViewports(
      { track_viewports_by_track_uid: { t2: B } },
      ['t1'],
      { t1: A },
    )).toEqual({ t2: B });
  });

  it('falls back to legacy locked viewports for old snapshots', () => {
    expect(restorePersistedTrackViewports({}, ['t1'], { t1: A })).toEqual({ t1: A });
  });

  it('restores typed Tie state and ignores absent tracks', () => {
    const state = {
      viewport_tie_groups: [{
        group_id: 'viewport-tie:t1',
        leader_track_uid: 't1',
        member_track_uids: ['t1', 't2', 'gone'],
        viewport: A,
      }],
    };
    expect(restorePersistedViewportTieGroups(state, ['t1', 't2'])).toEqual([tie]);
  });

  it('reads legacy presentation Tie state for compatibility', () => {
    const raw = buildPersistedViewportTieGroups([tie]);
    expect(restorePersistedViewportTieGroups({ presentation_state: { viewport_tie_groups: raw } }, ['t1', 't2']))
      .toEqual([tie]);
  });

  it('restores only suspended tracks that remain Tie members', () => {
    expect(restorePersistedViewportTieSuspensions(
      { viewport_tie_suspended_track_uids: ['t2', 'gone'] },
      [tie],
    )).toEqual(['t2']);
  });
});
