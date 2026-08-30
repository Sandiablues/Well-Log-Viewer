import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const source = fs.readFileSync(
  path.resolve(process.cwd(), 'src/wells/wbv/WellboreTrajectoryRenderer.tsx'),
  'utf8',
);

describe('WBV Shift + MB1 transient tracking preview', () => {
  it('projects against the already-loaded renderer trajectory', () => {
    expect(source).toContain(
      'const transientPointForPointer = (pointer: { clientX: number; clientY: number })',
    );
    expect(source).toContain('normalizedPoints.length !== renderPoints.length');
    expect(source).toContain(
      'transientProjectedStart.copy(transientSegmentStart).project(camera)',
    );
    expect(source).toContain(
      'transientProjectedEnd.copy(transientSegmentEnd).project(camera)',
    );
  });

  it('moves the visible marker from the animation loop rather than backend cadence', () => {
    const renderStart = source.indexOf(
      'const renderScene = (frameTime = performance.now())',
    );
    const renderEnd = source.indexOf(
      'resizeObserver = new ResizeObserver',
      renderStart,
    );
    const renderBlock = source.slice(renderStart, renderEnd);

    expect(renderBlock).toContain(
      'applyTransientTrackingPreview(latestTrackingPointerSample);',
    );
    expect(renderBlock).toContain(
      'interactionLifecycle.trackingPointerId !== null',
    );
  });

  it('keeps pointermove limited to input capture and backend observation dispatch', () => {
    const moveStart = source.indexOf(
      'const handlePointerMove = (event: PointerEvent)',
    );
    const moveEnd = source.indexOf(
      'const handlePointerRawUpdate',
      moveStart,
    );
    const moveBlock = source.slice(moveStart, moveEnd);

    expect(moveBlock).toContain('captureTrackingPointerSample(event);');
    expect(moveBlock).toContain(
      'interactionLifecycle.pendingTrackingObservation = observation;',
    );
    expect(moveBlock).toContain('void flushTrackingUpdate();');
    expect(moveBlock).not.toContain('applyTransientTrackingPreview(event)');
  });

  it('keeps backend state authoritative after release', () => {
    expect(source).toContain(
      "kind: commit ? 'track-commit' : 'track-cancel'",
    );
    expect(source).toContain('transientTrackingPoint = null;');
    expect(source).toContain('latestTrackingPointerSample = null;');
    expect(source).toContain('syncInteraction();');
  });

  it('prevents backend acknowledgements from overwriting the active preview', () => {
    expect(source).toContain(
      'interactionLifecycleRef.current.trackingPointerId !== null && transientTrackingPoint',
    );
  });

  it('does not introduce durable frontend interaction state', () => {
    expect(source).not.toContain('setTransientTrackingPoint');
    expect(source).not.toContain('localStorage');
    expect(source).not.toContain('sessionStorage');
  });
});
