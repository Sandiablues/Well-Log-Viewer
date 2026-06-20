export interface WlvRuntimeLocation {
  protocol: string;
  hostname: string;
  port: string;
}

export interface WlvRuntimeEnvironment {
  __WLV_API_BASE_URL__?: string;
  location?: WlvRuntimeLocation;
}

function runtimeEnvironment(): WlvRuntimeEnvironment {
  return globalThis as unknown as WlvRuntimeEnvironment;
}

export function wlvApiBaseUrl(
  environment: WlvRuntimeEnvironment = runtimeEnvironment(),
): string {
  const configured = environment.__WLV_API_BASE_URL__?.trim();
  if (configured) return configured.replace(/\/+$/, '');

  const location = environment.location;
  if (!location) return '';

  const protocol = location.protocol || 'http:';
  const hostname = location.hostname || '127.0.0.1';
  const port = location.port;
  const backendPort = '8001';

  if (port === backendPort) return '';
  if (port === '5173' || port === '5174' || port === '5175') {
    return `${protocol}//${hostname}:${backendPort}`;
  }
  return `http://127.0.0.1:${backendPort}`;
}

export function wlvApiUrl(
  path: string,
  environment: WlvRuntimeEnvironment = runtimeEnvironment(),
): string {
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${wlvApiBaseUrl(environment)}${normalizedPath}`;
}

export async function fetchWlvApi(
  path: string,
  init?: RequestInit,
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  return fetchImpl(wlvApiUrl(path), init);
}
