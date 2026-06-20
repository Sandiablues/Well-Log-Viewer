import { describe, expect, it } from 'vitest';
import { parseCanonicalWorkspaceV1 } from '../canonicalWorkspaceV1';

const uid = {
  well: '01901901-9000-7000-8000-000000000001',
  wellbore: '01901901-9000-7000-8000-000000000002',
  source: '01901901-9000-7000-8000-000000000003',
  product: '01901901-9000-7000-8000-000000000004',
  curve: '01901901-9000-7000-8000-000000000005',
  session: '01901901-9000-7000-8000-000000000006',
};

function fixture() {
  return {
    contract_version: 'wdv_workspace_v1',
    managed_well_uid: uid.well,
    managed_wellbore_uid: uid.wellbore,
    well_name: 'Well A',
    wellbore_name: 'Main',
    depth_range: { minimum: 0, maximum: 1000, unit: 'ft' },
    curve_registry: [{
      contract_version: 'wdv_identity_v2_1',
      managed_curve_uid: uid.curve,
      managed_product_uid: uid.product,
      managed_well_uid: uid.well,
      managed_wellbore_uid: uid.wellbore,
      managed_source_uid: uid.source,
      kr_curve_type_id: 'gamma_ray',
      observed_mnemonic: 'GR',
      normalized_mnemonic: 'GR',
      display_name: 'Gamma Ray',
      unit: 'gAPI',
      curve_family: 'gamma_ray',
      description: 'Gamma Ray',
      legacy_ids: [],
      display_policy: {
        curve_class: 'gamma',
        lattice: 'linear',
        scale_type: 'linear',
        display_min: 0,
        display_max: 150,
        scale_direction: 'normal',
        default_color: '#2f80ed',
        source: 'template_default',
        warnings: [],
      },
    }],
    session: {
      contract_version: 'wdv_session_layout_state_v2_1',
      session_uid: uid.session,
      managed_well_uid: uid.well,
      revision: 0,
      state_status: 'empty',
      selected_track_uid: null,
      tracks: [],
      warnings: [],
      updated_at: '2026-06-19T00:00:00+00:00',
    },
    warnings: [],
  };
}

describe('canonical workspace v1', () => {
  it('parses the aggregate through the existing canonical package parser', () => {
    const workspace = parseCanonicalWorkspaceV1(fixture());
    expect(workspace.managedWellUid).toBe(uid.well);
    expect(workspace.curves).toHaveLength(1);
    expect(workspace.session.revision).toBe(0);
  });

  it('rejects a workspace/session well mismatch', () => {
    const value = fixture();
    value.session.managed_well_uid =
      '01901901-9000-7000-8000-000000000099';
    expect(() => parseCanonicalWorkspaceV1(value)).toThrow();
  });
});
