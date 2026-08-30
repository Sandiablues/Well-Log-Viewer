import type { DepthViewRange } from './WdvPresentationPrimitives';

function span(range: DepthViewRange): number {
  return range.max - range.min;
}

export function standardizedMagnificationValue(
  referenceRange: DepthViewRange,
  currentRange: DepthViewRange,
): number {
  const referenceSpan = span(referenceRange);
  const currentSpan = span(currentRange);
  if (
    !Number.isFinite(referenceSpan)
    || !Number.isFinite(currentSpan)
    || referenceSpan <= 0
    || currentSpan <= 0
  ) {
    return 1;
  }
  return Math.max(1, Math.round(referenceSpan / currentSpan));
}

export function standardizedMagnificationLabel(
  referenceRange: DepthViewRange,
  currentRange: DepthViewRange,
): string {
  return `${standardizedMagnificationValue(referenceRange, currentRange)}×`;
}

/**
 * Convert the current viewport into the next shared integer magnification step.
 *
 * Full/content-fit remains outside this ladder. The first + / - command after
 * Full snaps onto the nearest next standardized canvas magnification.
 */
export function standardizedZoomSpan(input: {
  referenceRange: DepthViewRange;
  currentRange: DepthViewRange;
  factor: number;
  minSpan: number;
  maxSpan: number;
}): number {
  const referenceSpan = span(input.referenceRange);
  const currentSpan = span(input.currentRange);

  if (
    !Number.isFinite(referenceSpan)
    || referenceSpan <= 0
    || !Number.isFinite(currentSpan)
    || currentSpan <= 0
  ) {
    return Math.max(input.minSpan, Math.min(input.maxSpan, currentSpan));
  }

  const currentMagnification = Math.max(
    1,
    Math.round(referenceSpan / currentSpan),
  );

  let targetMagnification = currentMagnification;

  if (input.factor < 1) {
    targetMagnification = Math.max(
      currentMagnification + 1,
      Math.round(currentMagnification / input.factor),
    );
  } else if (input.factor > 1) {
    if (currentMagnification <= 1) {
      targetMagnification = 1;
    } else {
      targetMagnification = Math.max(
        1,
        Math.min(
          currentMagnification - 1,
          Math.round(currentMagnification / input.factor),
        ),
      );
    }
  }

  const standardizedSpan = referenceSpan / targetMagnification;
  return Math.max(
    input.minSpan,
    Math.min(input.maxSpan, standardizedSpan),
  );
}
