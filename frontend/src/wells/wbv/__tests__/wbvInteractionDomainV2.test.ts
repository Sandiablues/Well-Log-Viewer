import { describe, expect, it, vi } from 'vitest';
import { createWbvInteractionCoordinator } from '../interactionDomain/coordinator';
import type { WbvInteractionStateV2 } from '../interactionDomain/contracts';

const state = (session: string | null, status: WbvInteractionStateV2['tracking_status']): WbvInteractionStateV2 => ({
  contract_kind: 'wbv_interaction_state', contract_version: 'wbv_interaction_state_v2',
  managed_well_id: 'well', revision: 1, selection_mode: 'point', selected_point_visible: true,
  interval_visible: false, selected_point: null, interval_draft_start: null, saved_interval: null,
  active_tracking_session_id: session, tracking_status: status, fallback_status: 'none', updated_at: 'now',
});
const observation = {
  pointer_x_px: 10, pointer_y_px: 10, viewport_width_px: 100, viewport_height_px: 100,
  view_projection_matrix: Array(16).fill(0), activation_tolerance_px: 20,
};

describe('WBV interaction domain v2 coordinator', () => {
  it('freezes orbit only during tracking and restores on commit', async () => {
    const orbit: boolean[] = [];
    const transport = {
      observe: vi.fn(async () => state(null, 'committed')),
      start: vi.fn(async () => state('session', 'tracking')),
      update: vi.fn(async () => state('session', 'tracking')),
      commit: vi.fn(async () => state(null, 'committed')),
      cancel: vi.fn(async () => state(null, 'cancelled')),
    };
    const coordinator = createWbvInteractionCoordinator({
      transport, applyState: vi.fn(), applyFallback: vi.fn(),
      setOrbitEnabled: (enabled) => orbit.push(enabled), setPointerCapture: vi.fn(), releasePointerCapture: vi.fn(),
    });
    await coordinator.start(1, observation);
    coordinator.move(1, observation);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await coordinator.commit(1, observation);
    expect(orbit).toEqual([false, true]);
  });

  it('restores orbit when backend commit fails', async () => {
    const orbit: boolean[] = [];
    const coordinator = createWbvInteractionCoordinator({
      transport: {
        observe: vi.fn(), start: vi.fn(async () => state('session', 'tracking')), update: vi.fn(),
        commit: vi.fn(async () => { throw new Error('offline'); }), cancel: vi.fn(),
      },
      applyState: vi.fn(), applyFallback: vi.fn(), setOrbitEnabled: (enabled) => orbit.push(enabled),
      setPointerCapture: vi.fn(), releasePointerCapture: vi.fn(),
    });
    await coordinator.start(1, observation);
    await coordinator.commit(1, observation);
    expect(orbit).toEqual([false, true]);
  });
});
