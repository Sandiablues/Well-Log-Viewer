export function wlvApiBaseUrl(): string {
  const runtimeConfig = window as unknown as { __WLV_API_BASE_URL__?: string };
  if (runtimeConfig.__WLV_API_BASE_URL__) {
    return runtimeConfig.__WLV_API_BASE_URL__.replace(/\/$/, '');
  }

  if (window.location.port === '8010') {
    return '';
  }

  return 'http://127.0.0.1:8010';
}

export async function fetchWlvJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${wlvApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}
