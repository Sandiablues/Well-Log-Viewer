import { describe, expect, it, vi } from 'vitest';
import {
  MWD_TRANSIENT_FLUSH_CONFIRMATION,
  MWD_TRANSIENT_FLUSH_ENDPOINT,
  buildMwdTransientFlushRequest,
  flushMwdTransientData,
} from '../mwdTransientFlushApi';

describe('MWD transient flush API contract', () => {
  it('uses the explicit backend-owned destructive confirmation contract', () => {
    expect(MWD_TRANSIENT_FLUSH_ENDPOINT).toBe('/api/wlv/inventory/mwd/flush');
    expect(buildMwdTransientFlushRequest()).toEqual({
      confirm: MWD_TRANSIENT_FLUSH_CONFIRMATION,
      actor: 'mwd-ui',
      reason: 'Flush transient MWD managed data from the Managed Data page',
      dry_run: false,
    });
  });

  it('posts exactly one backend-owned flush command', async () => {
    const requester = vi.fn().mockResolvedValue({
      ok: true,
      action: 'flush_mwd_transient_data',
      destructive: true,
      dry_run: false,
      removed_managed_well_count: 3,
    });

    const result = await flushMwdTransientData(requester);

    expect(requester).toHaveBeenCalledTimes(1);
    expect(requester).toHaveBeenCalledWith(
      '/api/wlv/inventory/mwd/flush',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const init = requester.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      confirm: 'FLUSH_MWD_TRANSIENT_DATA',
      actor: 'mwd-ui',
      reason: 'Flush transient MWD managed data from the Managed Data page',
      dry_run: false,
    });
    expect(result.ok).toBe(true);
  });
});
