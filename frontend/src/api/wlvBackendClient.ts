export function wlvApiBaseUrl(): string {
  const runtimeConfig = window as unknown as { __WLV_API_BASE_URL__?: string };
  if (runtimeConfig.__WLV_API_BASE_URL__) {
    return runtimeConfig.__WLV_API_BASE_URL__.replace(/\/$/, '');
  }

  const protocol = window.location.protocol || 'http:';
  const hostname = window.location.hostname || '127.0.0.1';
  const port = window.location.port;

  if (port === '8001') {
    return '';
  }

  if (port === '5173' || port === '5174' || port === '5175') {
    return `${protocol}//${hostname}:8001`;
  }

  return 'http://127.0.0.1:8001';
}

function responseContentType(response: Response): string {
  return response.headers.get('content-type') ?? '';
}

async function responseErrorMessage(response: Response): Promise<string> {
  const prefix = `${response.status} ${response.statusText}`.trim();
  try {
    if (responseContentType(response).includes('application/json')) {
      const payload = await response.json();
      const detail = typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload);
      return detail ? `${prefix}: ${detail}` : prefix;
    }
    const text = await response.text();
    return text ? `${prefix}: ${text.slice(0, 500)}` : prefix;
  } catch {
    return prefix;
  }
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
    throw new Error(await responseErrorMessage(response));
  }

  return response.json() as Promise<T>;
}
