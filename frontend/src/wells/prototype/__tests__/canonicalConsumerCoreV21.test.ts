import { describe, expect, it } from 'vitest';

import {
  asAssignmentUid,
  asManagedCurveUid,
  asManagedProductUid,
  asManagedSourceUid,
  asManagedWellUid,
  asTrackUid,
} from '../../identity/wdvIdentityV21';
import {
  buildCurveAssignmentV21,
  curveByManagedUidV21,
  indexCurveCatalogV21,
  resolveTrackLatticeV21,
  validateTrackGraphV21,
  type CurveCatalogItemV21,
  type CurveTrackV21,
} from '../trackLayoutModelV21';
import {
  buildCanonicalSampleRequestBodyV21,
  indexManagedCurveSamplesV21,
  parseManagedCurveSamplesV21,
} from '../managedCurveSamplesV21';

const WELL = asManagedWellUid('019f0000-0000-7000-8000-000000000001');
const CURVE = asManagedCurveUid('019f0000-0000-7000-8000-000000000002');
const PRODUCT = asManagedProductUid('019f0000-0000-7000-8000-000000000003');
const SOURCE = asManagedSourceUid('019f0000-0000-7000-8000-000000000004');
const TRACK = asTrackUid('019f0000-0000-7000-8000-000000000005');
const ASSIGNMENT = asAssignmentUid('019f0000-0000-7000-8000-000000000006');

const curve: CurveCatalogItemV21 = {
  managedCurveUid: CURVE,
  managedProductUid: PRODUCT,
  managedWellUid: WELL,
  managedWellboreUid: null,
  managedSourceUid: SOURCE,
  krCurveTypeId: 'gamma_ray',
  observedMnemonic: 'GR',
  normalizedMnemonic: 'GR',
  displayName: 'Gamma Ray',
  unit: 'API',
  curveFamily: 'gamma_ray',
  description: 'Natural gamma ray',
  curveClass: 'gamma',
  defaultLattice: 'linear',
  defaultMin: 0,
  defaultMax: 150,
  defaultScaleDirection: 'normal',
  defaultColor: '#111111',
  recognised: true,
};

describe('WDV canonical consumer core v2.1', () => {
  it('builds assignments only from backend-governed UUIDv7 seeds', () => {
    const assignment = buildCurveAssignmentV21(
      {
        assignmentUid: ASSIGNMENT,
        trackUid: TRACK,
        managedCurveUid: CURVE,
        managedProductUid: PRODUCT,
        managedWellUid: WELL,
        managedWellboreUid: null,
        managedSourceUid: SOURCE,
      },
      curve,
      0,
    );

    expect(assignment.assignmentUid).toBe(ASSIGNMENT);
    expect(assignment.managedCurveUid).toBe(CURVE);
    expect(assignment.trackUid).toBe(TRACK);
  });

  it('indexes and resolves only by managedCurveUid', () => {
    expect(indexCurveCatalogV21([curve]).get(CURVE)).toEqual(curve);
    expect(curveByManagedUidV21([curve], CURVE)).toEqual(curve);
  });

  it('resolves the front-curve lattice by managedCurveUid', () => {
    const assignment = buildCurveAssignmentV21(
      {
        assignmentUid: ASSIGNMENT,
        trackUid: TRACK,
        managedCurveUid: CURVE,
        managedProductUid: PRODUCT,
        managedWellUid: WELL,
        managedWellboreUid: null,
        managedSourceUid: SOURCE,
      },
      curve,
      0,
    );
    const track: CurveTrackV21 = {
      trackUid: TRACK,
      trackIndex: 0,
      title: 'Gamma Ray',
      widthPx: 220,
      visible: true,
      trackType: 'curve',
      trackKey: null,
      rendererType: null,
      trackRole: null,
      sourceTemplateKey: null,
      sourceApplicationPlanUid: null,
      lattice: 'linear',
      latticeSource: 'front_curve_default',
      latticeOverride: false,
      scaleMode: 'shared',
      curves: [assignment],
    };

    expect(resolveTrackLatticeV21(track, [curve]).frontCurve).toEqual(curve);
    expect(() => validateTrackGraphV21([track])).not.toThrow();
  });

  it('rejects assignment-to-track graph mismatch', () => {
    const assignment = buildCurveAssignmentV21(
      {
        assignmentUid: ASSIGNMENT,
        trackUid: TRACK,
        managedCurveUid: CURVE,
        managedProductUid: PRODUCT,
        managedWellUid: WELL,
        managedWellboreUid: null,
        managedSourceUid: SOURCE,
      },
      curve,
      0,
    );
    const otherTrack = asTrackUid('019f0000-0000-7000-8000-000000000007');
    const track: CurveTrackV21 = {
      trackUid: otherTrack,
      trackIndex: 0,
      title: 'Invalid',
      widthPx: 220,
      visible: true,
      trackType: 'curve',
      trackKey: null,
      rendererType: null,
      trackRole: null,
      sourceTemplateKey: null,
      sourceApplicationPlanUid: null,
      lattice: 'linear',
      latticeSource: 'front_curve_default',
      latticeOverride: false,
      scaleMode: 'shared',
      curves: [assignment],
    };

    expect(() => validateTrackGraphV21([track])).toThrow('wrong trackUid');
  });

  it('builds sample requests without product or mnemonic identity', () => {
    expect(buildCanonicalSampleRequestBodyV21({
      managedWellUid: WELL,
      managedCurveUid: CURVE,
      sampleRevision: 'rev-1',
      maxSamples: 12000,
    })).toEqual({
      contract_version: 'wdv_curve_samples_v2_1',
      managed_well_uid: WELL,
      managed_curve_uid: CURVE,
      sample_revision: 'rev-1',
      max_samples: 12000,
    });
  });

  it('parses and indexes sample responses only by managedCurveUid', () => {
    const response = parseManagedCurveSamplesV21({
      contract_version: 'wdv_curve_samples_v2_1',
      managed_well_uid: WELL,
      managed_curve_uid: CURVE,
      returned_sample_count: 2,
      sample_revision: 'rev-1',
      samples: [[1001, 20], [1000, 10]],
    });

    expect(response.samples).toEqual([
      { depth: 1000, value: 10 },
      { depth: 1001, value: 20 },
    ]);
    expect(indexManagedCurveSamplesV21([response]).get(CURVE)).toEqual(
      response.samples,
    );
  });

  it('rejects legacy sample identity fields', () => {
    expect(() => parseManagedCurveSamplesV21({
      contract_version: 'wdv_curve_samples_v2_1',
      managed_well_uid: WELL,
      managed_curve_uid: CURVE,
      product_id: 'legacy',
      returned_sample_count: 1,
      samples: [[1000, 10]],
    })).toThrow('forbidden active identity field');
  });
});
