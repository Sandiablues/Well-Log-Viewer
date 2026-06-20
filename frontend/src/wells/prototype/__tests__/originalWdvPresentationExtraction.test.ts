import { describe, expect, it } from 'vitest';
import {
  OriginalWdvPresentation,
} from '../OriginalWdvPresentation';

describe('OriginalWdvPresentation extraction contract', () => {
  it('exports the inactive presentation component', () => {
    expect(typeof OriginalWdvPresentation).toBe('function');
    expect(OriginalWdvPresentation.name).toBe('OriginalWdvPresentation');
  });
});
