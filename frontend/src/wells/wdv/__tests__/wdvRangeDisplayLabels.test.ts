import { describe, expect, it } from 'vitest';

import { frontendTracksFromCanonicalSession } from '../WdvPageBoundary';
import type { RawCanonicalSession } from '../WdvPageBoundary';
import type { CurveCatalogItem, CurveTrack } from '../../prototype/trackLayoutModel';

describe('backend-owned WDV range labels', () => {
  it('projects labels while preserving full numeric endpoints', () => {
    const curveUid = 'bbbbbbbb-0000-7000-8000-000000000099';
    const session: RawCanonicalSession = {
      revision: 1,
      state_status: 'active',
      selected_track_uid: null,
      tracks: [{
        track_uid: 'a1b2c3d4-e5f6-7890-abcd-ef0123456789',
        managed_well_uid: '01930e4a-8db4-7001-8b21-3f4abc123456',
        track_name: 'Curve Track',
        track_type: 'curve',
        width_px: 220,
        lattice: 'linear',
        lattice_source: 'front_curve_default',
        lattice_override: false,
        scale_mode: 'per_curve',
        depth_basis: null,
        assignments: [{
          assignment_uid: 'cccccccc-0000-7000-8000-000000000099',
          managed_curve_uid: curveUid,
          managed_product_uid: '01930e4a-8db4-7002-8b21-3f4abc123456',
          managed_well_uid: '01930e4a-8db4-7001-8b21-3f4abc123456',
          managed_source_uid: '01930e4a-8db4-7003-8b21-3f4abc123456',
          observed_mnemonic: 'DNPH',
          display_name: 'Density neutron porosity',
          stack_index: 0,
          visible: true,
          scale_min: -0.07529999999999999,
          scale_max: 0.0219,
          scale_min_label: '-0.0753',
          scale_max_label: '0.0219',
          scale_type: 'linear',
          scale_direction: 'normal',
          color: null,
          unit: 'V/V',
          display_policy_source: 'curve',
          display_review_required: false,
          display_warning_code: null,
          display_warning_message: null,
        }],
      }],
    };
    const catalog: CurveCatalogItem[] = [{
      curveId: curveUid,
      curveUid,
      mnemonic: 'DNPH',
      description: 'Density neutron porosity',
      unit: 'V/V',
      curveClass: 'neutron',
      defaultLattice: 'linear',
      defaultMin: 0,
      defaultMax: 1,
      defaultColor: '#000000',
      recognised: true,
    }];

    const assignment = (
      frontendTracksFromCanonicalSession(session, catalog)[0] as CurveTrack
    ).curves[0];

    expect(assignment.scaleMin).toBe(-0.07529999999999999);
    expect(assignment.scaleMax).toBe(0.0219);
    expect(assignment.scaleMinLabel).toBe('-0.0753');
    expect(assignment.scaleMaxLabel).toBe('0.0219');
  });
});
