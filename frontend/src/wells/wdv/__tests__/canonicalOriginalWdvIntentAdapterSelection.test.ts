import { describe, expect, it, vi } from 'vitest';
import { CanonicalOriginalWdvMutationAdapter } from '../canonicalOriginalWdvIntentAdapter';

describe('canonical assignment edit focus', () => {
  it('restores the edited assignment after the canonical update resolves', async () => {
    const calls: string[] = [];
    const execute = vi.fn(async () => {
      calls.push('execute');
      return {} as any;
    });
    const setPresentationSelection = vi.fn(() => {
      calls.push('selection');
    });

    const adapter = new CanonicalOriginalWdvMutationAdapter({
      actions: {
        execute,
        applyTemplate: vi.fn(),
        setPresentationSelection,
      },
      getPresentation: () => ({
        tracks: [
          {
            trackType: 'curve',
            trackId: '019f0000-0000-7000-8000-000000000001',
            curves: [
              {
                assignmentId: '019f0000-0000-7000-8000-000000000010',
                curveId: '019f0000-0000-7000-8000-000000000100',
                scaleMin: 0,
                scaleMax: 100,
              },
              {
                assignmentId: '019f0000-0000-7000-8000-000000000020',
                curveId: '019f0000-0000-7000-8000-000000000200',
                scaleMin: 1,
                scaleMax: 10,
              },
            ],
          },
        ],
      } as any),
    });

    await adapter.updateAssignment(
      '019f0000-0000-7000-8000-000000000020' as any,
      { rangeOverrideMode: 'fit_to_curve_p05_p95' },
    );

    expect(calls).toEqual(['execute', 'selection']);
    expect(setPresentationSelection).toHaveBeenCalledWith({
      kind: 'assignment',
      trackUid: '019f0000-0000-7000-8000-000000000001',
      assignmentUid: '019f0000-0000-7000-8000-000000000020',
      managedCurveUid: '019f0000-0000-7000-8000-000000000200',
    });
  });
});
