import type {
  ManagedCurveUid,
  ManagedWellUid,
} from '../identity/wdvIdentityV21';
import {
  WdvIdentityContractError,
  asManagedCurveUid,
  asManagedWellUid,
} from '../identity/wdvIdentityV21';

export interface ManagedCurveSampleV21 {
  depth: number;
  value: number;
}

export interface ManagedCurveSampleRequestV21 {
  managedWellUid: ManagedWellUid;
  managedCurveUid: ManagedCurveUid;
  sampleRevision: string | null;
  maxSamples: number;
}

export interface ManagedCurveSampleResponseV21 {
  contractVersion: 'wdv_curve_samples_v2_1';
  managedWellUid: ManagedWellUid;
  managedCurveUid: ManagedCurveUid;
  sampleRevision: string | null;
  samples: ManagedCurveSampleV21[];
}

export type ManagedCurveSamplesByUidV21 = ReadonlyMap<
  ManagedCurveUid,
  readonly ManagedCurveSampleV21[]
>;

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function requireRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new WdvIdentityContractError('Sample response must be an object');
  }
  return value as Record<string, unknown>;
}

export function parseManagedCurveSamplesV21(
  value: unknown,
): ManagedCurveSampleResponseV21 {
  const payload = requireRecord(value);

  if (payload.contract_version !== 'wdv_curve_samples_v2_1') {
    throw new WdvIdentityContractError(
      'Sample response contract_version must be wdv_curve_samples_v2_1',
    );
  }

  for (const forbidden of ['product_id', 'curve_id', 'curve_uid', 'mnemonic']) {
    if (Object.prototype.hasOwnProperty.call(payload, forbidden)) {
      throw new WdvIdentityContractError(
        `Sample response contains forbidden active identity field: ${forbidden}`,
      );
    }
  }

  if (!Array.isArray(payload.samples)) {
    throw new WdvIdentityContractError('Sample response samples must be an array');
  }

  const samples: ManagedCurveSampleV21[] = [];
  for (const raw of payload.samples) {
    if (!Array.isArray(raw) || raw.length < 2) {
      throw new WdvIdentityContractError(
        'Each sample must be a [depth, value] tuple',
      );
    }
    const depth = finiteNumber(raw[0]);
    const sampleValue = finiteNumber(raw[1]);
    if (depth === null || sampleValue === null) {
      throw new WdvIdentityContractError(
        'Sample depth and value must be finite numbers',
      );
    }
    samples.push({ depth, value: sampleValue });
  }

  samples.sort((left, right) => left.depth - right.depth);

  const returnedCount = finiteNumber(payload.returned_sample_count);
  if (returnedCount === null || returnedCount !== samples.length) {
    throw new WdvIdentityContractError(
      'returned_sample_count must equal the number of samples',
    );
  }

  return {
    contractVersion: 'wdv_curve_samples_v2_1',
    managedWellUid: asManagedWellUid(payload.managed_well_uid),
    managedCurveUid: asManagedCurveUid(payload.managed_curve_uid),
    sampleRevision:
      typeof payload.sample_revision === 'string'
        ? payload.sample_revision
        : null,
    samples,
  };
}

export function buildCanonicalSampleRequestBodyV21(
  request: ManagedCurveSampleRequestV21,
): {
  contract_version: 'wdv_curve_samples_v2_1';
  managed_well_uid: ManagedWellUid;
  managed_curve_uid: ManagedCurveUid;
  sample_revision: string | null;
  max_samples: number;
} {
  if (!Number.isInteger(request.maxSamples) || request.maxSamples < 2) {
    throw new WdvIdentityContractError('maxSamples must be an integer >= 2');
  }

  return {
    contract_version: 'wdv_curve_samples_v2_1',
    managed_well_uid: request.managedWellUid,
    managed_curve_uid: request.managedCurveUid,
    sample_revision: request.sampleRevision,
    max_samples: request.maxSamples,
  };
}

export async function loadManagedCurveSamplesV21(
  request: ManagedCurveSampleRequestV21,
  fetchJson: (
    url: string,
    init: RequestInit,
  ) => Promise<unknown>,
): Promise<ManagedCurveSampleResponseV21> {
  const payload = await fetchJson('/api/wlv/v2/curve-samples', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buildCanonicalSampleRequestBodyV21(request)),
  });

  const parsed = parseManagedCurveSamplesV21(payload);
  if (parsed.managedWellUid !== request.managedWellUid) {
    throw new WdvIdentityContractError(
      'Sample response managedWellUid does not match request',
    );
  }
  if (parsed.managedCurveUid !== request.managedCurveUid) {
    throw new WdvIdentityContractError(
      'Sample response managedCurveUid does not match request',
    );
  }
  return parsed;
}

export function indexManagedCurveSamplesV21(
  responses: readonly ManagedCurveSampleResponseV21[],
): ManagedCurveSamplesByUidV21 {
  const index = new Map<
    ManagedCurveUid,
    readonly ManagedCurveSampleV21[]
  >();

  for (const response of responses) {
    if (index.has(response.managedCurveUid)) {
      throw new WdvIdentityContractError(
        `Duplicate sample response for managedCurveUid: ${response.managedCurveUid}`,
      );
    }
    index.set(response.managedCurveUid, response.samples);
  }

  return index;
}
