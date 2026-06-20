import { describe, expect, it } from 'vitest';
import {
  CurveInventory,
  RightPanel,
  Toolbar,
  TrackCanvas,
  WdvTemplateRecommendationModal,
} from '../WdvPresentationPrimitives';

describe('WDV presentation primitives extraction', () => {
  it('exports the active WDV presentation components', () => {
    expect(typeof CurveInventory).toBe('function');
    expect(typeof RightPanel).toBe('function');
    expect(typeof Toolbar).toBe('function');
    expect(typeof TrackCanvas).toBe('function');
    expect(typeof WdvTemplateRecommendationModal).toBe('function');
  });
});
