import { describe, expect, it } from 'vitest';
import {
  composeOriginalWdvPresentationProps,
} from '../originalWdvPresentationPropsComposer';

describe('completed original WDV presentation boundary', () => {
  it('exports the inactive composer', () => {
    expect(typeof composeOriginalWdvPresentationProps).toBe('function');
  });
});
