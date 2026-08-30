import { describe, expect, it } from 'vitest';
import { useViewportNavigationExecution } from '../useViewportNavigationExecution';

describe('useViewportNavigationExecution module contract', () => {
  it('exports one navigation execution boundary', () => {
    expect(typeof useViewportNavigationExecution).toBe('function');
  });

  it('keeps navigation execution frontend-local', () => {
    const source = useViewportNavigationExecution.toString();
    expect(source.includes('fetch(')).toBe(false);
    expect(source.includes('axios')).toBe(false);
  });
});
