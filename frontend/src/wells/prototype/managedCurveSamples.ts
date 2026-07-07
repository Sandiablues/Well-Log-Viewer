export type ManagedCurveSample = {
  depth: number;
  value: number;
};

export type ManagedCurveSamplesPayload = {
  ok?: boolean;
  contract_kind?: string;
  contract_version?: string;
  managed_well_id?: string;
  managed_well_uid?: string;
  product_id?: string;
  managed_product_uid?: string;
  curve_id?: string | null;
  managed_curve_uid?: string;
  managed_source_uid?: string;
  mnemonic?: string | null;
  observed_mnemonic?: string | null;
  normalized_mnemonic?: string | null;
  display_name?: string | null;
  curve_family?: string | null;
  depth_unit?: string | null;
  value_unit?: string | null;
  depth_min?: number | null;
  depth_max?: number | null;
  value_min?: number | null;
  value_max?: number | null;
  robust_value_min?: number | null;
  robust_value_max?: number | null;
  value_p01?: number | null;
  value_p05?: number | null;
  value_p50?: number | null;
  value_p95?: number | null;
  value_p99?: number | null;
  sample_count?: number | null;
  returned_sample_count?: number | null;
  raw_numeric_sample_count?: number | null;
  rejected_sample_count?: number | null;
  rejected_null_count?: number | null;
  rejected_sentinel_count?: number | null;
  rejected_nonfinite_count?: number | null;
  rejected_plausibility_count?: number | null;
  rejected_row_count?: number | null;
  decimation_stride?: number | null;
  provenance?: {
    sample_source?: string | null;
    source_path?: string | null;
    source_intake_candidate_id?: string | null;
    checksum?: string | null;
    generated_at?: string | null;
  } | null;
  samples?: unknown;
};

export type ManagedCurveSampleContractsByCurveId = Record<
  string,
  ManagedCurveSamplesPayload
>;

export type ManagedCurveSampleRequest = {
  managedWellId: string;
  curveId: string;
  curveUid: string;
  managedCurveUid?: string | null;
  productId: string;
  samplesUrl: string;
  sampleRevision?: string | null;
};

export type ManagedCurveSampleLoadResult = {
  request: ManagedCurveSampleRequest;
  contract: ManagedCurveSamplesPayload | null;
  samples: ManagedCurveSample[];
  error: string | null;
};

export type ManagedCurveSamplesByCurveId = Record<string, ManagedCurveSample[]>;

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function parseManagedCurveSamples(payload: ManagedCurveSamplesPayload): ManagedCurveSample[] {
  if (!payload || payload.ok === false || !Array.isArray(payload.samples)) return [];

  const parsed: ManagedCurveSample[] = [];
  for (const raw of payload.samples) {
    let depthValue: unknown;
    let curveValue: unknown;

    if (Array.isArray(raw)) {
      depthValue = raw[0];
      curveValue = raw[1];
    } else if (raw && typeof raw === 'object') {
      const record = raw as {
        depth?: unknown;
        value?: unknown;
        values?: Record<string, unknown>;
      };
      depthValue = record.depth
        ?? record.values?.DEPT
        ?? record.values?.DEPTH
        ?? record.values?.MD
        ?? record.values?.TDEP;
      curveValue = record.value
        ?? record.values?.[String(payload.curve_id || '')]
        ?? record.values?.[String(payload.mnemonic || '')];
    }

    const depth = finiteNumber(depthValue);
    const value = finiteNumber(curveValue);
    if (depth === null || value === null) continue;
    parsed.push({ depth, value });
  }

  parsed.sort((left, right) => left.depth - right.depth);
  return parsed;
}

export function managedCurveSampleKeys(request: ManagedCurveSampleRequest): string[] {
  return [
    request.curveId,
    request.curveUid,
    request.managedCurveUid ?? null,
  ].filter((value, index, all): value is string => (
    typeof value === 'string' && value.length > 0 && all.indexOf(value) === index
  ));
}

export async function loadManagedCurveSamples(
  request: ManagedCurveSampleRequest,
  fetchJson: (url: string) => Promise<ManagedCurveSamplesPayload>,
): Promise<ManagedCurveSampleLoadResult> {
  try {
    const payload = await fetchJson(request.samplesUrl);
    const samples = parseManagedCurveSamples(payload);
    if (samples.length === 0) {
      return { request, contract: payload, samples: [], error: `No usable samples returned for ${request.curveId}` };
    }
    return { request, contract: payload, samples, error: null };
  } catch (error) {
    return {
      request,
      contract: null,
      samples: [],
      error: error instanceof Error ? error.message : `Unable to load ${request.curveId}`,
    };
  }
}

export function indexManagedCurveSamples(
  results: ManagedCurveSampleLoadResult[],
): {
  samplesByCurveId: ManagedCurveSamplesByCurveId;
  contractsByCurveId: ManagedCurveSampleContractsByCurveId;
  errorsByCurveId: Record<string, string>;
} {
  const samplesByCurveId: ManagedCurveSamplesByCurveId = {};
  const contractsByCurveId: ManagedCurveSampleContractsByCurveId = {};
  const errorsByCurveId: Record<string, string> = {};

  for (const result of results) {
    const keys = managedCurveSampleKeys(result.request);
    if (result.contract) {
      keys.forEach((key) => {
        contractsByCurveId[key] = result.contract as ManagedCurveSamplesPayload;
      });
    }
    if (result.samples.length > 0) {
      keys.forEach((key) => {
        samplesByCurveId[key] = result.samples;
      });
    }
    if (result.error) {
      keys.forEach((key) => {
        errorsByCurveId[key] = result.error as string;
      });
    }
  }

  return { samplesByCurveId, contractsByCurveId, errorsByCurveId };
}
