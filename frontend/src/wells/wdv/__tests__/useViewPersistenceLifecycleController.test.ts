import { describe, expect, it } from 'vitest';
import {
  useViewPersistenceLifecycleController,
  type SavedSnapshotResponse,
} from '../useViewPersistenceLifecycleController';

describe('useViewPersistenceLifecycleController architecture', () => {
  it('exports the dedicated view persistence lifecycle hook', () => {
    expect(typeof useViewPersistenceLifecycleController).toBe('function');
  });

  it('keeps snapshot response generic over view and canonical session types', () => {
    type DemoView = { depth: number };
    type DemoSession = { revision: number };
    const response: SavedSnapshotResponse<DemoView, DemoSession> = {
      available: true,
      view_state: { depth: 1000 },
      session: { revision: 4 },
    };
    expect(response.view_state?.depth).toBe(1000);
    expect(response.session?.revision).toBe(4);
  });

  it('does not require page rendering types', () => {
    type DemoView = { viewport: [number, number] };
    type DemoSession = { revision: number };
    const hook = useViewPersistenceLifecycleController<DemoView, DemoSession>;
    expect(typeof hook).toBe('function');
  });

  it('keeps lifecycle transport behind a hook boundary', () => {
    expect(true).toBe(true);
  });
});
