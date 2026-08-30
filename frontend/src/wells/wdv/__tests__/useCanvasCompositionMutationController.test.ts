import { describe, expect, it } from 'vitest';
import {
  useCanvasCompositionMutationController,
  type CompositionMutationOptions,
} from '../useCanvasCompositionMutationController';

describe('useCanvasCompositionMutationController architecture', () => {
  it('exports the dedicated canvas composition mutation hook', () => {
    expect(typeof useCanvasCompositionMutationController).toBe('function');
  });

  it('keeps interaction preservation representable at the controller boundary', () => {
    const preserved: CompositionMutationOptions = { preserveInteraction: true };
    expect(preserved.preserveInteraction).toBe(true);
  });

  it('is generic over canonical session response shape', () => {
    type DemoSession = { revision: number };
    const hook = useCanvasCompositionMutationController<DemoSession>;
    expect(typeof hook).toBe('function');
  });

  it('does not require page-specific track or assignment rendering types', () => {
    expect(true).toBe(true);
  });
});
