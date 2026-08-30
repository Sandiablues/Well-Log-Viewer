import { describe, expect, it } from 'vitest';
import {
    canHydrateCommittedStartupView,
    canHydrateRecoveryStartupView,
} from '../startupViewHydrationControl';

const VIEW = { global_viewport: { min: 1000, max: 1100 } };

describe('startupViewHydrationControl', () => {
    it('accepts a committed view for the exact canonical revision', () => {
        expect(canHydrateCommittedStartupView({
            available: true,
            stale: false,
            session_revision: 12,
            current_session_revision: 12,
            view_state: VIEW,
        }, 12)).toBe(true);
    });

    it('rejects a stale committed view', () => {
        expect(canHydrateCommittedStartupView({
            available: false,
            stale: true,
            session_revision: 11,
            current_session_revision: 12,
            view_state: null,
        }, 12)).toBe(false);
    });

    it('rejects committed state with ambiguous or mismatched revisions', () => {
        expect(canHydrateCommittedStartupView({
            available: true,
            stale: false,
            session_revision: 11,
            current_session_revision: 12,
            view_state: VIEW,
        }, 12)).toBe(false);
        expect(canHydrateCommittedStartupView({
            available: true,
            stale: false,
            session_revision: 12,
            view_state: VIEW,
        }, 12)).toBe(false);
    });

    it('accepts recovery only for the exact canonical revision', () => {
        expect(canHydrateRecoveryStartupView({
            available: true,
            stale: false,
            session_revision: 12,
            current_session_revision: 12,
            view_state: VIEW,
        }, 12)).toBe(true);
    });

    it('rejects legacy revision-less recovery', () => {
        expect(canHydrateRecoveryStartupView({
            available: true,
            stale: false,
            view_state: VIEW,
        }, 12)).toBe(false);
    });

    it('rejects stale recovery even if a payload is present', () => {
        expect(canHydrateRecoveryStartupView({
            available: true,
            stale: true,
            session_revision: 11,
            current_session_revision: 12,
            view_state: VIEW,
        }, 12)).toBe(false);
    });
});
