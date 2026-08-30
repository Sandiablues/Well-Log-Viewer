import { describe, expect, it } from 'vitest';
import { createWbvInteractionCommandAuthority } from '../interactionDomain/authority';
import type { WbvInteractionStateV2 } from '../interactionDomain/contracts';

const state = (revision: number): WbvInteractionStateV2 => ({
  contract_kind: 'wbv_interaction_state', contract_version: 'wbv_interaction_state_v2',
  managed_well_id: 'well', revision, selection_mode: 'point', selected_point_visible: true,
  interval_visible: false, selected_point: null, interval_draft_start: null, saved_interval: null,
  active_tracking_session_id: null, tracking_status: 'idle', fallback_status: 'none', updated_at: String(revision),
});

describe('WBV interaction command authority', () => {
  it('serializes revisioned commands and advances expected revision from acknowledgements', async () => {
    const seen: number[] = [];
    const applied: number[] = [];
    const authority = createWbvInteractionCommandAuthority({ applyState: (next) => applied.push(next.revision), applyError: () => undefined });
    authority.seed(state(290));
    const first = authority.runRevisioned(async (expected) => { seen.push(expected); await new Promise((r) => setTimeout(r, 10)); return state(291); });
    const second = authority.runRevisioned(async (expected) => { seen.push(expected); return state(292); });
    await Promise.all([first, second]);
    expect(seen).toEqual([290, 291]);
    expect(applied).toEqual([290, 291, 292]);
  });

  it('does not apply an older session response over newer state', async () => {
    const applied: number[] = [];
    const authority = createWbvInteractionCommandAuthority({ applyState: (next) => applied.push(next.revision), applyError: () => undefined });
    authority.seed(state(50));
    await authority.runSession(async () => state(52));
    await authority.runSession(async () => state(51));
    expect(applied).toEqual([50, 52]);
    expect(authority.latestRevision()).toBe(52);
  });
});
