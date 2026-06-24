import { describe, expect, it } from 'vitest';
import {
  parseCanonicalViewerPackageV21,
  executeCanonicalSessionCommandV21,
} from '../canonicalViewerPackageV21';

const WELL = '019ede00-0000-7000-8000-000000000001';
const WELLBORE = '019ede00-0000-7000-8000-000000000002';
const CURVE = '019ede00-0000-7000-8000-000000000003';
const PRODUCT = '019ede00-0000-7000-8000-000000000004';
const SOURCE = '019ede00-0000-7000-8000-000000000005';
const SESSION = '019ede00-0000-7000-8000-000000000006';
const TRACK = '019ede00-0000-7000-8000-000000000007';
const ASSIGNMENT = '019ede00-0000-7000-8000-000000000008';

function packagePayload() {
  return {
    contract_version: 'wdv_viewer_package_v2_2',
    managed_well_uid: WELL,
    managed_wellbore_uid: WELLBORE,
    well_name: 'Test Well',
    wellbore_name: 'Main Bore',
    depth_range: { minimum: 1000, maximum: 2000, unit: 'ft' },
    curves: [
      {
        contract_version: 'wdv_identity_v2_1',
        managed_curve_uid: CURVE,
        managed_product_uid: PRODUCT,
        managed_well_uid: WELL,
        managed_wellbore_uid: WELLBORE,
        managed_source_uid: SOURCE,
        kr_curve_type_id: 'gamma_ray',
        observed_mnemonic: 'GR',
        normalized_mnemonic: 'GR',
        display_name: 'Gamma Ray',
        unit: 'API',
        curve_family: 'gamma_ray',
        description: 'Gamma Ray',
        legacy_ids: [],
        display_policy: {
          curve_class: 'gamma',
          lattice: 'linear',
          scale_type: 'linear',
          display_min: 0,
          display_max: 200,
          review_required: false,
          scale_direction: 'normal',
          default_color: '#2f80ed',
          source: 'template_default',
          warnings: [],
        },
      },
    ],
    session: {
      contract_version: 'wdv_session_layout_state_v2_1',
      session_uid: SESSION,
      managed_well_uid: WELL,
      revision: 1,
      state_status: 'active',
      source: 'backend_owned_session_state',
      selected_track_uid: TRACK,
      tracks: [
        {
          track_uid: TRACK,
          track_key: 'gamma',
          track_number: 1,
          track_name: 'Gamma Ray',
          track_type: 'curve',
          renderer_type: null,
          track_role: null,
          width_px: 240,
          lattice: 'linear',
          lattice_source: 'front_curve_default',
          source_template_key: null,
          source_application_plan_uid: null,
          assignments: [
            {
              assignment_uid: ASSIGNMENT,
              managed_curve_uid: CURVE,
              managed_product_uid: PRODUCT,
              managed_well_uid: WELL,
              managed_wellbore_uid: WELLBORE,
              managed_source_uid: SOURCE,
              track_uid: TRACK,
              kr_curve_type_id: 'gamma_ray',
              observed_mnemonic: 'GR',
              normalized_mnemonic: 'GR',
              display_name: 'Gamma Ray',
              curve_family: 'gamma_ray',
              unit: 'API',
              stack_index: 0,
              visible: true,
              scale_min: 0,
              scale_max: 200,
              scale_type: 'linear',
              scale_direction: 'normal',
              color: '#2f80ed',
              line_style: 'solid',
              line_width: 1.8,
              fill_mode: null,
              source: 'manual_backend_command',
            },
          ],
        },
      ],
      warnings: [],
      updated_at: '2026-06-19T08:00:00+00:00',
    },
    warnings: [],
  };
}

describe('canonical viewer package v2.1 adapter', () => {
  it('parses backend-owned identities and display policy', () => {
    const parsed = parseCanonicalViewerPackageV21(packagePayload());
    expect(parsed.managedWellUid).toBe(WELL);
    expect(parsed.curves[0].managedCurveUid).toBe(CURVE);
    expect(parsed.curves[0].defaultMin).toBe(0);
    expect(parsed.curves[0].defaultMax).toBe(200);
    expect(parsed.curves[0].reviewRequired).toBe(false);
    expect(parsed.curves[0].defaultColor).toBe('#2f80ed');
    expect(parsed.session.tracks[0].trackUid).toBe(TRACK);
    expect(parsed.session.tracks[0].trackType).toBe('curve');
    if (parsed.session.tracks[0].trackType === 'curve') {
      expect(parsed.session.tracks[0].curves[0].assignmentUid).toBe(ASSIGNMENT);
      expect(parsed.session.tracks[0].curves[0].managedCurveUid).toBe(CURVE);
    }
  });

  it('parses null display bounds with review_required=true (Tier-3 no-bounds contract)', () => {
    const payload = packagePayload();
    const curve = payload.curves[0] as Record<string, unknown>;
    curve.display_policy = {
      ...(curve.display_policy as object),
      display_min: null,
      display_max: null,
      review_required: true,
    };
    const parsed = parseCanonicalViewerPackageV21(payload);
    expect(parsed.curves[0].defaultMin).toBeNull();
    expect(parsed.curves[0].defaultMax).toBeNull();
    expect(parsed.curves[0].reviewRequired).toBe(true);
  });

  it('rejects legacy identity fields in assignments', () => {
    const payload = packagePayload();
    (
      payload.session.tracks[0].assignments[0] as Record<string, unknown>
    ).curve_id = 'GR';
    expect(() => parseCanonicalViewerPackageV21(payload)).toThrow(
      /forbidden active identity field/,
    );
  });

  it('rejects assignments whose curve is absent from the package', () => {
    const payload = packagePayload();
    payload.session.tracks[0].assignments[0].managed_curve_uid =
      '019ede00-0000-7000-8000-000000000099';
    expect(() => parseCanonicalViewerPackageV21(payload)).toThrow(
      /unknown managed_curve_uid/,
    );
  });

  it('posts backend session commands and parses the returned session', async () => {
    const payload = packagePayload();
    const parsed = parseCanonicalViewerPackageV21(payload);
    let calledUrl = '';
    let calledBody = '';

    const fetchImpl = (async (url: RequestInfo | URL, init?: RequestInit) => {
      calledUrl = String(url);
      calledBody = String(init?.body ?? '');
      return new Response(JSON.stringify(payload.session), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;

    const session = await executeCanonicalSessionCommandV21(
      parsed.managedWellUid,
      {
        kind: 'select_track',
        body: {
          expected_revision: parsed.session.revision,
          track_uid: TRACK,
        },
      },
      parsed.curves,
      fetchImpl,
    );

    expect(calledUrl).toContain('/api/wlv/v2/wdv/session-commands/');
    expect(calledUrl).toContain('/selection');
    expect(JSON.parse(calledBody).expected_revision).toBe(1);
    expect(session.selectedTrackUid).toBe(TRACK);
  });
});
