import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const source = fs.readFileSync(
  path.resolve(process.cwd(), 'src/wells/wbv/WellboreTrajectoryRenderer.tsx'),
  'utf8',
);

describe('WBV Shift + MB1 frame-rate transient preview', () => {
  it('captures the newest coalesced pointer sample', () => {
    expect(source).toContain('const captureTrackingPointerSample = (event: PointerEvent)');
    expect(source).toContain("typeof event.getCoalescedEvents === 'function'");
    expect(source).toContain('coalesced[coalesced.length - 1]');
  });

  it('uses pointerrawupdate while the drag is active', () => {
    expect(source).toContain("addEventListener('pointerrawupdate', handlePointerRawUpdate as EventListener, true)");
    expect(source).toContain("removeEventListener('pointerrawupdate', handlePointerRawUpdate as EventListener, true)");
  });

  it('projects the latest pointer sample from the animation loop', () => {
    const start = source.indexOf('const renderScene = (frameTime = performance.now())');
    const end = source.indexOf('resizeObserver = new ResizeObserver', start);
    const block = source.slice(start, end);
    expect(block).toContain('latestTrackingPointerSample');
    expect(block).toContain('applyTransientTrackingPreview(latestTrackingPointerSample);');
  });

  it('does not drive the visible marker directly from pointermove', () => {
    const start = source.indexOf('const handlePointerMove = (event: PointerEvent)');
    const end = source.indexOf('const handlePointerRawUpdate', start);
    const block = source.slice(start, end);
    expect(block).toContain('captureTrackingPointerSample(event);');
    expect(block).not.toContain('applyTransientTrackingPreview(event)');
  });

  it('bypasses smoothing only for the actively dragged selection marker', () => {
    expect(source).toContain(
      'const activeTracking = interactionLifecycle.trackingPointerId !== null;',
    );
    expect(source).toContain('if (activeTracking && marker === selectionMarker)');
    expect(source).toContain('basePosition.copy(targetPosition);');
    expect(source).toContain('basePosition.lerp(targetPosition, smoothingAlpha);');
  });

  it('clears frame-local input and retains backend commit authority', () => {
    expect(source).toContain('latestTrackingPointerSample = null;');
    expect(source).toContain("kind: 'track-update'");
    expect(source).toContain("kind: commit ? 'track-commit' : 'track-cancel'");
  });
});
