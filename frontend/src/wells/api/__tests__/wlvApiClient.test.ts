import { describe, expect, it, vi } from 'vitest';
import { fetchWlvApi, wlvApiBaseUrl, wlvApiUrl } from '../wlvApiClient';

describe('canonical WLV API transport', () => {
  it('routes Vite requests to backend port 8001', () => {
    const environment = {
      location: { protocol: 'http:', hostname: '127.0.0.1', port: '5173' },
    };
    expect(wlvApiBaseUrl(environment)).toBe('http://127.0.0.1:8001');
    expect(wlvApiUrl('/api/wlv/v2/viewer-packages/example', environment))
      .toBe('http://127.0.0.1:8001/api/wlv/v2/viewer-packages/example');
  });

  it('uses relative requests when served by backend', () => {
    expect(wlvApiUrl('/api/wlv/v2/curve-samples', {
      location: { protocol: 'http:', hostname: '127.0.0.1', port: '8001' },
    })).toBe('/api/wlv/v2/curve-samples');
  });

  it('honours runtime override', () => {
    expect(wlvApiUrl('/api/wlv/v2/curve-samples', {
      __WLV_API_BASE_URL__: 'https://wlv.example.test/',
    })).toBe('https://wlv.example.test/api/wlv/v2/curve-samples');
  });

  it('preserves relative URLs outside browser runtime', () => {
    expect(wlvApiUrl('/api/wlv/v2/curve-samples', {}))
      .toBe('/api/wlv/v2/curve-samples');
  });

  it('passes resolved URL to fetch', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200 }));
    await fetchWlvApi(
      '/api/wlv/v2/curve-samples',
      { method: 'POST' },
      fetchImpl as typeof fetch,
    );
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/wlv\/v2\/curve-samples$/),
      { method: 'POST' },
    );
  });
});
