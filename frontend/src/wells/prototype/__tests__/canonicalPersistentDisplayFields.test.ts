import { describe, expect, it } from 'vitest';
import { parseCanonicalViewerPackageV21 } from '../canonicalViewerPackageV21';

describe('canonical viewer persistent display fields', () => {
  it('preserves backend-owned track and assignment display state', () => {
    const well = '019ede00-0000-7000-8000-000000000201';
    const curve = '019ede00-0000-7000-8000-000000000202';
    const product = '019ede00-0000-7000-8000-000000000203';
    const source = '019ede00-0000-7000-8000-000000000204';
    const track = '019ede00-0000-7000-8000-000000000205';
    const assignment = '019ede00-0000-7000-8000-000000000206';
    const session = '019ede00-0000-7000-8000-000000000207';

    const parsed = parseCanonicalViewerPackageV21({
      contract_version: 'wdv_viewer_package_v2_2',
      managed_well_uid: well,
      managed_wellbore_uid: null,
      well_name: 'Well',
      wellbore_name: null,
      depth_range: { minimum: 1000, maximum: 2000, unit: 'ft' },
      curves: [{
        contract_version: 'wdv_identity_v2_1',
        managed_curve_uid: curve,
        managed_product_uid: product,
        managed_well_uid: well,
        managed_wellbore_uid: null,
        managed_source_uid: source,
        kr_curve_type_id: 'gamma_ray',
        observed_mnemonic: 'GR',
        normalized_mnemonic: 'GR',
        display_name: 'Gamma Ray',
        unit: 'API',
        curve_family: 'gamma_ray',
        description: null,
        display_policy: {
          curve_class: 'gamma',
          lattice: 'linear',
          display_min: 0,
          display_max: 150,
          scale_direction: 'normal',
          default_color: '#111111',
        },
      }],
      session: {
        contract_version: 'wdv_session_layout_state_v2_1',
        session_uid: session,
        managed_well_uid: well,
        revision: 5,
        state_status: 'active',
        selected_track_uid: track,
        warnings: [],
        updated_at: '2026-06-19T09:00:00+00:00',
        tracks: [{
          track_uid: track,
          track_key: 'gamma',
          track_number: 0,
          track_name: 'Gamma',
          track_type: 'curve',
          renderer_type: 'line_curve',
          track_role: 'open_hole',
          width_px: 280,
          lattice: 'linear',
          lattice_source: 'governed_template',
          source_template_key: 'triple_combo',
          source_application_plan_uid:
            '019ede00-0000-7000-8000-000000000208',
          visible: false,
          scale_mode: 'dual',
          lattice_override: true,
          depth_basis: null,
          assignments: [{
            assignment_uid: assignment,
            managed_curve_uid: curve,
            managed_product_uid: product,
            managed_well_uid: well,
            managed_wellbore_uid: null,
            managed_source_uid: source,
            track_uid: track,
            stack_index: 0,
            visible: true,
            scale_min: 10,
            scale_max: 140,
            scale_type: 'linear',
            scale_direction: 'reversed',
            color: '#222222',
            line_style: 'dash',
            line_width: 2,
            line_visible: false,
            line_opacity: 65,
            range_mode: 'fixed',
            position_anchor: 'right',
            horizontal_offset_pct: 10,
            clip_to_track: false,
            fill_side: 'left',
            fill_color: '#333333',
            fill_opacity: 40,
            infill_source: 'solid',
            infill_pattern: 'dense',
            infill_interval_column: 'lithology',
            paired_managed_curve_uid: null,
            display_priority: 'foreground',
            show_qaqc_warnings: false,
            show_null_gaps: false,
            show_out_of_range: false,
          }],
        }],
      },
      warnings: [],
    });

    const parsedTrack = parsed.session.tracks[0];
    expect(parsedTrack.visible).toBe(false);
    expect(parsedTrack.trackType).toBe('curve');
    if (parsedTrack.trackType !== 'curve') throw new Error('curve track expected');
    expect(parsedTrack.scaleMode).toBe('dual');
    expect(parsedTrack.latticeOverride).toBe(true);
    expect(parsedTrack.sourceTemplateKey).toBe('triple_combo');
    const item = parsedTrack.curves[0];
    expect(item.scaleDirection).toBe('reverse');
    expect(item.lineVisible).toBe(false);
    expect(item.lineOpacity).toBe(65);
    expect(item.positionAnchor).toBe('right');
    expect(item.clipToTrack).toBe(false);
    expect(item.fillSide).toBe('left');
    expect(item.displayPriority).toBe('foreground');
    expect(item.showQaqcWarnings).toBe(false);
  });
});
