import { describe, expect, it } from 'vitest';
import { persistenceRequestForCommittedView } from '../viewPersistenceControl';

describe('persistenceRequestForCommittedView', () => {
  it('returns the exact session and committed view revisions', () => {
    expect(persistenceRequestForCommittedView({
      available: true,
      session_revision: 12,
      current_session_revision: 12,
      view_revision: 7,
      stale: false,
    }, 12)).toEqual({
      expected_revision: 12,
      expected_view_revision: 7,
    });
  });

  it('rejects unavailable committed view state', () => {
    expect(persistenceRequestForCommittedView({ available: false }, 12)).toBeNull();
  });

  it('rejects stale committed view state', () => {
    expect(persistenceRequestForCommittedView({
      available: true,
      stale: true,
      session_revision: 12,
      view_revision: 7,
    }, 12)).toBeNull();
  });

  it('rejects a committed view built against another session revision', () => {
    expect(persistenceRequestForCommittedView({
      available: true,
      session_revision: 11,
      current_session_revision: 12,
      view_revision: 7,
    }, 12)).toBeNull();
  });

  it('rejects a missing or negative view revision', () => {
    expect(persistenceRequestForCommittedView({
      available: true,
      session_revision: 12,
      view_revision: -1,
    }, 12)).toBeNull();
  });
});
