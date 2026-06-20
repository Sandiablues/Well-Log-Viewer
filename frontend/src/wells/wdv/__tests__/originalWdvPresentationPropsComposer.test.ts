import { describe, expect, it } from 'vitest';
import {
  composeOriginalWdvPresentationProps,
} from '../originalWdvPresentationPropsComposer';

describe('original WDV presentation props composer', () => {
  it('exports the inactive composer', () => {
    expect(typeof composeOriginalWdvPresentationProps).toBe('function');
    expect(composeOriginalWdvPresentationProps.name).toBe(
      'composeOriginalWdvPresentationProps',
    );
  });
});
