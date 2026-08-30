import { fetchWlvJson } from '../../../api/wlvBackendClient';
import type {
  WbvInteractionMode,
  WbvInteractionStateV2,
  WbvObservationCommandV2,
  WbvTrackCommandV2,
} from './contracts';

function base(managedWellId: string): string {
  return `/api/wlv/wbv/wells/${encodeURIComponent(managedWellId)}/interaction-v2`;
}

export const wbvInteractionApiV2 = {
  get(managedWellId: string): Promise<WbvInteractionStateV2> {
    return fetchWlvJson<WbvInteractionStateV2>(base(managedWellId));
  },
  setMode(managedWellId: string, mode: WbvInteractionMode, expectedRevision?: number): Promise<WbvInteractionStateV2> {
    return fetchWlvJson<WbvInteractionStateV2>(`${base(managedWellId)}/mode`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, expected_revision: expectedRevision }),
    });
  },
  observe(managedWellId: string, command: WbvObservationCommandV2): Promise<WbvInteractionStateV2> {
    return fetchWlvJson<WbvInteractionStateV2>(`${base(managedWellId)}/observe`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(command),
    });
  },
  startTracking(managedWellId: string, command: WbvTrackCommandV2): Promise<WbvInteractionStateV2> {
    return fetchWlvJson<WbvInteractionStateV2>(`${base(managedWellId)}/tracking/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(command),
    });
  },
  updateTracking(managedWellId: string, command: WbvTrackCommandV2): Promise<WbvInteractionStateV2> {
    return fetchWlvJson<WbvInteractionStateV2>(`${base(managedWellId)}/tracking/update`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(command),
    });
  },
  commitTracking(managedWellId: string, command: WbvTrackCommandV2): Promise<WbvInteractionStateV2> {
    return fetchWlvJson<WbvInteractionStateV2>(`${base(managedWellId)}/tracking/commit`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(command),
    });
  },
  cancelTracking(managedWellId: string, command: WbvTrackCommandV2): Promise<WbvInteractionStateV2> {
    return fetchWlvJson<WbvInteractionStateV2>(`${base(managedWellId)}/tracking/cancel`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(command),
    });
  },
  clearInterval(managedWellId: string, expectedRevision?: number): Promise<WbvInteractionStateV2> {
    const suffix = expectedRevision === undefined ? '' : `?expected_revision=${expectedRevision}`;
    return fetchWlvJson<WbvInteractionStateV2>(`${base(managedWellId)}/interval${suffix}`, { method: 'DELETE' });
  },
  sendIntervalToWdv(managedWellId: string): Promise<unknown> {
    return fetchWlvJson(`${base(managedWellId)}/interval/send-to-wdv`, { method: 'POST' });
  },
};
