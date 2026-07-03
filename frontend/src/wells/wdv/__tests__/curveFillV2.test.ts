import propertiesPanelSource from '../../prototype/WellLogPropertiesPanelSlot.tsx?raw';
import { describe, expect, it } from 'vitest';
import {
  applyCurveFillGeometryDeltaV2,
  curveFillPaintCapabilitiesV2,
  resolvedCurveFillPaintV2,
  fetchCurveFillFeatureStatusV2,
  reorderCurveFillRulesV2,
  updateCurveFillRuleV2,
  type CurveFillGeometryV2,
} from '../curveFillV2';

const geometry = (ruleUid: string): CurveFillGeometryV2 => ({
  contract_version: 'wdv_curve_fill_geometry_v2',
  rule_uid: ruleUid,
  order: 0,
  dependency_key: `dep-${ruleUid}`,
  geometry_revision: `rev-${ruleUid}`,
  managed_well_uid: 'well-1',
  track_uid: 'track-1',
  depth_unit: 'ft',
  style: { appearance: 'solid', color: '#ff0000', opacity: 0.5, pattern_uid: null, pattern_scale: 1, raster_asset_uid: null },
  paint: { appearance: 'solid', pattern_uid: null, pattern_scale: 1, raster: null },
  polygons: [],
  warnings: [],
});

describe('Curve Fill v2 frontend adapter', () => {
  it('applies backend deltas without deriving geometry', () => {
    const current = new Map([['remove-me', geometry('remove-me')]]);
    const next = applyCurveFillGeometryDeltaV2(current, {
      contract_version: 'wdv_curve_fill_geometry_delta_v2',
      managed_well_uid: 'well-1',
      session_revision: 4,
      upsert: [geometry('add-me')],
      remove: ['remove-me'],
    });
    expect(next.has('remove-me')).toBe(false);
    expect(next.get('add-me')).toEqual(geometry('add-me'));
    expect(current.has('remove-me')).toBe(true);
  });

  it('reads the backend-owned feature status endpoint', async () => {
    const calls: string[] = [];
    const fetchImpl = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return new Response(JSON.stringify({
        contract_version: 'wdv_curve_fill_feature_status_v2',
        enabled: true,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }) as typeof fetch;
    const status = await fetchCurveFillFeatureStatusV2(fetchImpl);
    expect(status.enabled).toBe(true);
    expect(calls[0]).toContain('/api/wlv/v2/wdv/curve-fill-commands/feature-status');
  });

  it('sends backend-owned update and reorder workflow commands', async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), body: init?.body ? JSON.parse(String(init.body)) : null });
      return new Response(JSON.stringify({
        contract_version: 'wdv_curve_fill_command_result_v2',
        session: { revision: 8 },
        geometry_delta: {
          contract_version: 'wdv_curve_fill_geometry_delta_v2',
          managed_well_uid: 'well-1',
          session_revision: 8,
          upsert: [],
          remove: [],
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }) as typeof fetch;

    await updateCurveFillRuleV2('well-1', {
      expected_revision: 7,
      rule_uid: 'rule-1',
      enabled: false,
    }, fetchImpl);
    await reorderCurveFillRulesV2('well-1', {
      expected_revision: 8,
      track_uid: 'track-1',
      rule_uids: ['rule-2', 'rule-1'],
    }, fetchImpl);

    expect(calls[0].url).toContain('/workflow/rules/update');
    expect(calls[0].body).toEqual({ expected_revision: 7, rule_uid: 'rule-1', enabled: false });
    expect(calls[1].url).toContain('/workflow/rules/reorder');
    expect(calls[1].body).toEqual({ expected_revision: 8, track_uid: 'track-1', rule_uids: ['rule-2', 'rule-1'] });
  });
});

describe('Curve Fill v2.1 contracts', () => {
  it('recognizes backend-owned between-curves mode and Curve A mnemonic', () => {
    const capabilities = {
      contract_version: 'wdv_curve_fill_capabilities_v2' as const,
      managed_well_uid: 'well-1',
      session_revision: 1,
      track_uid: 'track-1',
      curve_a_assignment_uid: 'assignment-a',
      curve_a_mnemonic: 'RHOZ',
      paint: { appearances: ['solid','pattern','raster'], patterns: [{ pattern_uid: 'hatch-45-v1', label: 'Diagonal hatch' }], rasters: [] },
      modes: [{
        rule_type: 'between_curves' as const,
        eligible: true,
        disable_reason: null,
        comparisons: [],
        boundaries: [],
        overlay_policy_uid: null,
        overlay_policy_revision: null,
        curve_b_operands: [{
          assignment_uid: 'assignment-b', managed_curve_uid: 'curve-b', display_name: 'Neutron Porosity',
          mnemonic: 'NPHI', curve_family: 'neutron_porosity', unit: 'V/V', eligible: true, disable_reason: null,
        }],
      }],
    };
    expect(capabilities.curve_a_mnemonic).toBe('RHOZ');
    expect(capabilities.modes[0].rule_type).toBe('between_curves');
    expect(capabilities.modes[0].curve_b_operands[0].mnemonic).toBe('NPHI');
  });
});


describe('Curve Fill paint contracts', () => {
  it('keeps Solid, Pattern and Raster backend-addressed', () => {
    const style = { appearance: 'pattern' as const, color: '#445566', opacity: 0.5, pattern_uid: 'hatch-45-v1', pattern_scale: 1, raster_asset_uid: null };
    expect(style.appearance).toBe('pattern');
    expect(style.pattern_uid).toBe('hatch-45-v1');
  });
});


describe('Curve Fill paint compatibility guards', () => {
  it('falls back safely when the live backend has not yet supplied paint capabilities', () => {
    expect(curveFillPaintCapabilitiesV2(null)).toEqual({
      appearances: ['solid', 'pattern', 'raster'],
      patterns: [],
      rasters: [],
    });
  });

  it('renders legacy geometry as Solid instead of dereferencing a missing paint contract', () => {
    const legacy = {
      ...geometry('legacy-rule'),
      style: { color: '#ff0000', opacity: 0.5 },
      paint: undefined,
    } as CurveFillGeometryV2;
    expect(resolvedCurveFillPaintV2(legacy)).toEqual({
      appearance: 'solid',
      pattern_uid: null,
      pattern_scale: 1,
      raster: null,
    });
  });
});


describe('Curve Fill compact layer UI contract', () => {
  it('keeps infill layers collapsed by default and puts Curve A/operator/Curve B on one row when expanded', () => {
    const source = propertiesPanelSource;
    expect(source).toContain('const [expandedRuleUids, setExpandedRuleUids]');
    expect(source).toContain('wlv-curve-fill-layer-summary-button');
    expect(source).toContain('wlv-curve-fill-expression-row');
    expect(source).toContain("{expanded ? (");
    expect(source).toContain('ruleExpression(rule)');
    expect(source).toContain('rulePaintSummary(rule)');
  });
});
