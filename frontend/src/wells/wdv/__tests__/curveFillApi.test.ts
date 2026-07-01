import { describe, expect, it } from 'vitest';
import { parseCurveFillCapabilities } from '../curveFillApi';

describe('curve fill capability contract', () => {
  it('preserves backend-owned operand eligibility and policy identities', () => {
    const parsed = parseCurveFillCapabilities({
      contract_version: 'curve_fill_capabilities_v1',
      managed_well_uid: 'well',
      session_uid: 'session',
      session_revision: 4,
      track_uid: 'track',
      owner_assignment_uid: 'owner',
      modes: [{ mode: 'crossover', label: 'Crossover Fill', available: true, reason: null }],
      operands: [{
        operand_type: 'curve', identity: 'nphi', display_name: 'Neutron Porosity', unit: 'v/v',
        managed_well_uid: 'well', track_uid: 'track', available: true,
        eligible_fill_modes: ['between', 'crossover'], preset_ids: ['density-neutron-crossover'], reason: null,
      }],
      presets: [{
        preset_id: 'density-neutron-crossover', preset_revision: '1', label: 'Density–Neutron Crossover',
        fill_mode: 'crossover', available: true, default_condition: null,
        overlay_policy_id: 'density-neutron-overlay-v1', overlay_policy_revision: '1',
        default_fill: '#f0cf4c', default_opacity: 0.55, deadband: 0.005, minimum_interval: null, reason: null,
      }],
    });
    expect(parsed.operands[0].eligibleFillModes).toEqual(['between', 'crossover']);
    expect(parsed.operands[0].presetIds).toEqual(['density-neutron-crossover']);
    expect(parsed.presets[0].overlayPolicyId).toBe('density-neutron-overlay-v1');
  });
});
