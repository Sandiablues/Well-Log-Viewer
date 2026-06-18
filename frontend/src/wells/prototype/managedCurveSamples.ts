export type ManagedCurveSample = {
  depth: number;
  value: number;
};

export type ManagedCurveSamplesPayload = {
  ok?: boolean;
  contract_kind?: string;
  contract_version?: string;
  managed_well_id?: string;
  product_id?: string;
  curve_id?: string | null;
  mnemonic?: string | null;
  sample_count?: number | null;
  depth_min?: number | null;
  depth_max?: number | null;
  samples?: unknown;
};

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
      return { request, samples: [], error: `No usable samples returned for ${request.curveId}` };
    }
    return { request, samples, error: null };
  } catch (error) {
    return {
      request,
      samples: [],
      error: error instanceof Error ? error.message : `Unable to load ${request.curveId}`,
    };
  }
}

export function indexManagedCurveSamples(
  results: ManagedCurveSampleLoadResult[],
): { samplesByCurveId: ManagedCurveSamplesByCurveId; errorsByCurveId: Record<string, string> } {
  const samplesByCurveId: ManagedCurveSamplesByCurveId = {};
  const errorsByCurveId: Record<string, string> = {};

  for (const result of results) {
    const keys = managedCurveSampleKeys(result.request);
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

  return { samplesByCurveId, errorsByCurveId };
}
