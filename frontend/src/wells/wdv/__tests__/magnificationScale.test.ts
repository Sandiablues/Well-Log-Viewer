import { describe, expect, it } from 'vitest';
import {
  standardizedMagnificationLabel,
  standardizedMagnificationValue,
  standardizedZoomSpan,
} from '../magnificationScale';

describe('magnificationScale', () => {
  const REFERENCE = { min: 0, max: 3600 };

  it('uses one canvas reference instead of per-track content coverage', () => {
    expect(
      standardizedMagnificationLabel(
        REFERENCE,
        { min: 1000, max: 1300 },
      ),
    ).toBe('12×');

    expect(
      standardizedMagnificationLabel(
        REFERENCE,
        { min: 2000, max: 2300 },
      ),
    ).toBe('12×');
  });

  it('snaps zoom-in to the next standardized integer magnification', () => {
    const span = standardizedZoomSpan({
      referenceRange: REFERENCE,
      currentRange: { min: 1000, max: 1300 }, // 12×
      factor: 0.75,
      minSpan: 0.01,
      maxSpan: 3000,
    });

    expect(standardizedMagnificationValue(
      REFERENCE,
      { min: 0, max: span },
    )).toBe(16);
  });

  it('uses fine 10 percent toolbar steps around 19x', () => {
    const reference = { min: 0, max: 3600 };
    const current = { min: 1000, max: 1000 + (3600 / 19) };

    const outSpan = standardizedZoomSpan({
      referenceRange: reference,
      currentRange: current,
      factor: 1.1,
      minSpan: 0.01,
      maxSpan: 3600,
    });
    expect(standardizedMagnificationValue(
      reference,
      { min: 0, max: outSpan },
    )).toBe(17);

    const inSpan = standardizedZoomSpan({
      referenceRange: reference,
      currentRange: current,
      factor: 1 / 1.1,
      minSpan: 0.01,
      maxSpan: 3600,
    });
    expect(standardizedMagnificationValue(
      reference,
      { min: 0, max: inSpan },
    )).toBe(21);
  });

  it('keeps Full/content-fit independent until the next zoom command', () => {
    expect(
      standardizedMagnificationLabel(
        REFERENCE,
        { min: 100, max: 3100 },
      ),
    ).toBe('1×');

    expect(
      standardizedZoomSpan({
        referenceRange: REFERENCE,
        currentRange: { min: 100, max: 3100 },
        factor: 0.75,
        minSpan: 0.01,
        maxSpan: 3000,
      }),
    ).toBe(1800);
  });
});
