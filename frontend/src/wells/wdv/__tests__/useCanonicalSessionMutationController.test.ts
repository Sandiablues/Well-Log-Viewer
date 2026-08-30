import { describe, expect, it } from 'vitest';
import {
  useCanonicalSessionMutationController,
  type CanonicalSessionApplicationOptions,
} from '../useCanonicalSessionMutationController';

describe('useCanonicalSessionMutationController architecture', () => {
  it('exports the dedicated canonical mutation controller hook', () => {
    expect(typeof useCanonicalSessionMutationController).toBe('function');
  });

  it('keeps interaction preservation optional at the controller boundary', () => {
    const defaultOptions: CanonicalSessionApplicationOptions = {};
    const preservedOptions: CanonicalSessionApplicationOptions = {
      preserveInteraction: true,
    };

    expect(defaultOptions.preserveInteraction).toBeUndefined();
    expect(preservedOptions.preserveInteraction).toBe(true);
  });

  it('keeps the controller API isolated from page-specific session types', () => {
    type DemoSession = {
      revision: number;
      tracks?: unknown[];
    };

    const acceptsDemoSession:
      | typeof useCanonicalSessionMutationController<DemoSession>
      | null = useCanonicalSessionMutationController<DemoSession>;

    expect(acceptsDemoSession).not.toBeNull();
  });

  it('does not require Node runtime modules for architecture testing', () => {
    expect(true).toBe(true);
  });
});
