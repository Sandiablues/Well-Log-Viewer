import { describe, expect, it, vi } from 'vitest';
import { publishedWbvRenderPackageUrl } from '../publicationApi';

describe('WDV to WBV publication API', () => {
  it('builds the retained-package render URL', () => {
    expect(publishedWbvRenderPackageUrl('well uid', 'package uid')).toBe(
      '/api/wlv/wbv/publications/wells/well%20uid/packages/package%20uid/render-package',
    );
  });

  it('keeps update routes well and package scoped', async () => {
    vi.resetModules();
    const fetchWlvJson = vi.fn()
      .mockResolvedValueOnce({ package_revision: 2, update_available: true, publishable: true, changes: {} })
      .mockResolvedValueOnce({ package: { package_revision: 3 }, changes: {} });
    vi.doMock('../../../api/wlvBackendClient', () => ({ fetchWlvJson }));
    vi.doMock('../../wdv/canonicalCommandId', () => ({ createCanonicalCommandId: () => '019f0000-0000-7000-8000-000000000001' }));
    const api = await import('../publicationApi');

    await api.previewWbvPackageUpdate('well uid', 'package uid');
    await api.updateExistingWbvPackage('well uid', 'package uid', 2);

    expect(fetchWlvJson.mock.calls[0][0]).toBe(
      '/api/wlv/wbv/publications/wells/well%20uid/packages/package%20uid/update-preview',
    );
    expect(fetchWlvJson.mock.calls[1][0]).toBe(
      '/api/wlv/wbv/publications/wells/well%20uid/packages/package%20uid',
    );
    expect(fetchWlvJson.mock.calls[1][1]).toMatchObject({ method: 'PUT' });
  });
});
