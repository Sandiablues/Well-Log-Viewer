import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const source = fs.readFileSync(
  path.resolve(process.cwd(), 'src/wells/wbv/WellboreTrajectoryRenderer.tsx'),
  'utf8',
);

describe('WBV selected-point tracking controller integration', () => {
  it('delegates Shift + MB1 tracking to the dedicated controller', () => {
    expect(source).toContain('new SelectedPointTrackingController');
    expect(source).toContain('trackingController.start(event.pointerId, pointer, observation)');
    expect(source).toContain('trackingController.move(event.pointerId, pointer, observation)');
    expect(source).toContain('trackingController.commit(event.pointerId, observation)');
    expect(source).toContain('trackingController.cancel(event.pointerId)');
  });

  it('uses a fixed projected trajectory snapshot for the active drag', () => {
    expect(source).toContain('const projectTrackingStations = ()');
    expect(source).toContain('position.clone().project(camera)');
    expect(source).toContain('screenX: (projected.x * 0.5 + 0.5) * rect.width');
    expect(source).toContain('screenY: (-projected.y * 0.5 + 0.5) * rect.height');
  });

  it('retains transient presentation across backend-driven React synchronization', () => {
    expect(source).toContain('const point = activeTransientPoint ?? selectedPointRef.current');
    expect(source).toContain('activeTransientPoint = location.point');
    expect(source).toContain('activeTransientPoint = null');
  });

  it('keeps normal click observation and delegates backend tracking commands', () => {
    expect(source).toContain("kind: 'observe'");
    expect(source).toContain('sendInteractionCommand');
    expect(source).toContain('trackingController.start(event.pointerId, pointer, observation)');
    expect(source).toContain('trackingController.move(event.pointerId, pointer, observation)');
    expect(source).toContain('trackingController.commit(event.pointerId, observation)');
    expect(source).toContain('trackingController.cancel(event.pointerId)');
  });

  it('cancels on pointer loss, blur, visibility loss, Escape, and renderer disposal', () => {
    expect(source).toContain("addEventListener('lostpointercapture', handleLostPointerCapture, true)");
    expect(source).toContain("window.addEventListener('blur', handleWindowBlur)");
    expect(source).toContain("window.addEventListener('keydown', handleKeyDown)");
    expect(source).toContain("document.addEventListener('visibilitychange', handleVisibilityChange)");
    expect(source).toContain('trackingController?.dispose()');
  });

  it('does not retain the old embedded tracking lifecycle', () => {
    expect(source).not.toContain('interactionLifecycleRef');
    expect(source).not.toContain('trackingUpdatePromise: Promise<void>');
    expect(source).not.toContain('const flushTrackingUpdate =');
  });
});
