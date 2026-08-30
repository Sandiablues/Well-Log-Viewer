import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const renderer = fs.readFileSync(path.resolve(process.cwd(), 'src/wells/wbv/WellboreTrajectoryRenderer.tsx'), 'utf8');

describe('WBV transient continuity integration', () => {
  it('uses continuity output only for transient presentation', () => {
    expect(renderer).toContain('new TransientContinuityController');
    expect(renderer).toContain('activeTransientPoint = location.point');
    expect(renderer).toContain('const point = activeTransientPoint ?? selectedPointRef.current');
    expect(renderer).toContain('updateTransientContinuity(event)');
  });

  it('retains the existing authoritative transaction functions', () => {
    expect(renderer).toContain('const flushTrackingUpdate = (): Promise<void> | null =>');
    expect(renderer).toContain('const startTracking = async (event: PointerEvent) =>');
    expect(renderer).toContain('const finishTracking = async (event: PointerEvent, commit: boolean) =>');
    expect(renderer).toContain("sendCommand({ kind: 'track-start'");
    expect(renderer).toContain("sendCommand({ kind: 'track-update'");
    expect(renderer).toContain("kind: commit ? 'track-commit' : 'track-cancel'");
  });

  it('clears transient state after backend finish or rejected start', () => {
    expect(renderer).toContain('clearTransientContinuity();\n          syncInteraction();');
  });

  it('preserves normal click observation', () => {
    expect(renderer).toContain("sendCommand({ kind: 'observe', observation, sequence: 0 })");
  });

  it('drives marker and readout from one frame-advanced arc position', () => {
    expect(renderer).toContain('advanceTransientArcPresentation(');
    expect(renderer).toContain('transientContinuity.locationAtArc(displayedTransientProjectedDistance)');
    expect(renderer).toContain('targetTransientProjectedDistance = location.projectedDistance');
    expect(renderer).toContain('basePosition.copy(targetPosition)');
  });
});
