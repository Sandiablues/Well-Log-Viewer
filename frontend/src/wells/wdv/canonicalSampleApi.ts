import { fetchWlvApi } from '../api/wlvApiClient';
import type {
  ManagedCurveSampleRequestV21,
  ManagedCurveSampleResponseV21,
} from '../prototype/managedCurveSamplesV21';
import {
  loadManagedCurveSamplesV21,
} from '../prototype/managedCurveSamplesV21';

async function fetchJson(
  url: string,
  init: RequestInit,
  fetchImpl: typeof fetch,
): Promise<unknown> {
  const response = await fetchWlvApi(url, init, fetchImpl);
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const record =
      payload && typeof payload === 'object' && !Array.isArray(payload)
        ? payload as Record<string, unknown>
        : {};
    const detail =
      typeof record.detail === 'string'
        ? record.detail
        : `Canonical curve-sample request failed (${response.status})`;
    throw new Error(detail);
  }

  return payload;
}

export async function loadCanonicalManagedCurveSamples(
  request: ManagedCurveSampleRequestV21,
  fetchImpl: typeof fetch = fetch,
): Promise<ManagedCurveSampleResponseV21> {
  return loadManagedCurveSamplesV21(
    request,
    (url, init) => fetchJson(url, init, fetchImpl),
  );
}
