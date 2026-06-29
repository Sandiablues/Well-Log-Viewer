import { describe, expect, it } from 'vitest';
import {
  CurveInventory,
  RightPanel,
  Toolbar,
  TrackCanvas,
  WdvTemplateRecommendationModal,
  depthTicksForRange,
  resolveCurveAssignmentCatalogItem,
} from '../WdvPresentationPrimitives';

describe('WDV presentation primitives extraction', () => {
  it('exports the active WDV presentation components', () => {
    expect(typeof CurveInventory).toBe('function');
    expect(typeof RightPanel).toBe('function');
    expect(typeof Toolbar).toBe('function');
    expect(typeof TrackCanvas).toBe('function');
    expect(typeof WdvTemplateRecommendationModal).toBe('function');
  });

  it('uses one shared depth interval for every visible well track', () => {
    const sharedRange = { min: 301, max: 10414 };
    const ticks = depthTicksForRange(sharedRange);
    expect(ticks[0]).toBe(301);
    expect(ticks[ticks.length - 1]).toBe(10414);
  });

  it('resolves metadata by curve UUID and owning well before mnemonic fallback', () => {
    const assignment = {
      assignmentId: '01900000-0000-7000-8000-000000000010',
      curveId: '01900000-0000-7000-8000-000000000011',
      curveUid: '01900000-0000-7000-8000-000000000011',
      managedWellUid: '01900000-0000-7000-8000-000000000002',
      managedProductUid: null,
      managedSourceUid: null,
      observedMnemonic: 'GR',
      normalizedMnemonic: 'GR',
      displayName: 'State Gamma Ray',
      stackIndex: 0,
      visible: true,
      color: '#000000',
      lineStyle: 'solid',
      lineWidthPx: 1,
      scaleMin: 0,
      scaleMax: 150,
      scaleType: 'linear',
      scaleDirection: 'normal',
      unit: 'API',
    } as any;
    const catalog = [
      { curveId: 'forge-gr', curveUid: 'forge-gr', managedWellUid: '01900000-0000-7000-8000-000000000001', mnemonic: 'GR', description: 'Forge Gamma Ray' },
      { curveId: assignment.curveId, curveUid: assignment.curveUid, managedWellUid: assignment.managedWellUid, mnemonic: 'GR', description: 'State Gamma Ray' },
    ] as any;
    expect(resolveCurveAssignmentCatalogItem(catalog, assignment)?.description).toBe('State Gamma Ray');
  });

});
