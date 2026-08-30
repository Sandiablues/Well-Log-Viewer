import { describe, expect, it } from 'vitest';
import { buildViewportToolbarPresentation } from '../viewportToolbarPresentationModel';

describe('buildViewportToolbarPresentation', () => {
  it('disables Lock when no track is eligible', () => {
    const result = buildViewportToolbarPresentation({ quickView: false, combinationSelectedCount: 0, combinationSelectedUnlockedCount: 0, viewportTieCandidates: [], viewportTieCanCreate: false, viewportTieCanUntie: false, viewportTieCreateDisabledReason: '' });
    expect(result.lock.action).toBe('none');
    expect(result.lock.disabled).toBe(true);
  });

  it('projects Lock when any selected track is unlocked', () => {
    const result = buildViewportToolbarPresentation({ quickView: false, combinationSelectedCount: 3, combinationSelectedUnlockedCount: 1, viewportTieCandidates: [], viewportTieCanCreate: false, viewportTieCanUntie: false, viewportTieCreateDisabledReason: '' });
    expect(result.lock.action).toBe('lock');
    expect(result.lock.label).toBe('Lock');
  });

  it('projects Unlock when all action tracks are locked', () => {
    const result = buildViewportToolbarPresentation({ quickView: false, combinationSelectedCount: 2, combinationSelectedUnlockedCount: 0, viewportTieCandidates: [], viewportTieCanCreate: false, viewportTieCanUntie: false, viewportTieCreateDisabledReason: '' });
    expect(result.lock.action).toBe('unlock');
    expect(result.lock.label).toBe('Unlock');
  });

  it('prioritizes Untie over Tie', () => {
    const result = buildViewportToolbarPresentation({ quickView: false, combinationSelectedCount: 2, combinationSelectedUnlockedCount: 2, viewportTieCandidates: [{ trackId: 't1', label: 'T1' }], viewportTieCanCreate: true, viewportTieCanUntie: true, viewportTieCreateDisabledReason: '' });
    expect(result.tie.action).toBe('untie');
    expect(result.tie.visualState).toBe('tied');
  });

  it('disables all relationship actions in Quick View', () => {
    const result = buildViewportToolbarPresentation({ quickView: true, combinationSelectedCount: 2, combinationSelectedUnlockedCount: 2, viewportTieCandidates: [{ trackId: 't1', label: 'T1' }], viewportTieCanCreate: true, viewportTieCanUntie: false, viewportTieCreateDisabledReason: '' });
    expect(result.lock.disabled).toBe(true);
    expect(result.tie.disabled).toBe(true);
    expect(result.tie.candidates).toEqual([]);
  });
});
