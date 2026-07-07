import { describe, expect, it } from 'vitest';
import { wmdRecoveryAction, wmdRecoveryLabel, type WmdDownstreamRecoveryStatus } from '../wmdRecoveryApi';

function status(overrides: Partial<WmdDownstreamRecoveryStatus> = {}): WmdDownstreamRecoveryStatus {
  return {
    managed_well_id: 'well-1',
    source_recovery_state: 'available',
    payload_available: true,
    wdv_load_allowed: true,
    wbv_load_allowed: true,
    export_allowed: true,
    saved_workspace_resume_allowed: true,
    blocked_product_ids: [],
    recovery_message: null,
    ...overrides,
  };
}

describe('WMD backend recovery presentation', () => {
  it('renders available state without a recovery action', () => {
    const value = status();
    expect(wmdRecoveryLabel(value)).toBe('Available');
    expect(wmdRecoveryAction(value)).toBeNull();
  });

  it('requires source restoration for missing or changed sources', () => {
    expect(wmdRecoveryLabel(status({ payload_available: false, source_recovery_state: 'missing' }))).toBe('Source missing');
    expect(wmdRecoveryAction(status({ payload_available: false, source_recovery_state: 'changed' }))).toBe('restore-source');
  });

  it('offers rebuild only when the source is available but payload is cleared', () => {
    const value = status({ payload_available: false, source_recovery_state: 'available' });
    expect(wmdRecoveryLabel(value)).toBe('Rebuild required');
    expect(wmdRecoveryAction(value)).toBe('rebuild');
  });
});
