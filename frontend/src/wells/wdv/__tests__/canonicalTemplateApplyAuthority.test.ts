import { afterEach, describe, expect, it, vi } from 'vitest';
import { applyCanonicalWdvTemplate } from '../WdvPresentationPrimitives';

describe('canonical template apply authority', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts template mutation only to the canonical template command endpoint', async () => {
    vi.stubGlobal('window', {
      location: {
        protocol: 'http:',
        hostname: '127.0.0.1',
        port: '8001',
      },
    });

    const response = {
      revision: 4,
      state_status: 'active',
      selected_track_uid: '0197f5dc-1234-7000-8000-000000000001',
      tracks: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => response,
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await applyCanonicalWdvTemplate(
      '0197f5dc-1234-7000-8000-000000000002',
      3,
      'triple_combo',
      'open_hole',
    );

    expect(result).toEqual(response);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/wlv/v2/wdv/template-commands/0197f5dc-1234-7000-8000-000000000002/apply');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      expected_revision: 3,
      template_key: 'triple_combo',
      workflow_context: 'open_hole',
    });
    expect(String(url)).not.toContain('/application-plans/apply');
  });

  it('does not send a mutation when canonical session revision is unavailable', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      applyCanonicalWdvTemplate(
        '0197f5dc-1234-7000-8000-000000000002',
        -1,
        'triple_combo',
      ),
    ).rejects.toThrow('Canonical WDV session is not ready');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
