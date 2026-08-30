import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const controller = fs.readFileSync(
  path.resolve(process.cwd(), 'src/wells/wbv/selectedPointTracking/transientContinuityController.ts'),
  'utf8',
);

describe('WBV transient continuity authority boundary', () => {
  it('has no backend command ownership', () => {
    expect(controller).not.toContain('track-start');
    expect(controller).not.toContain('track-update');
    expect(controller).not.toContain('track-commit');
    expect(controller).not.toContain('track-cancel');
    expect(controller).not.toContain('sendCommand');
  });

  it('has no revision, sequence, session, promise, or persistence behavior', () => {
    expect(controller).not.toMatch(/\b(active_tracking_session_id|sessionId)\s*[:=]/);
    expect(controller).not.toMatch(/\brevision\s*[:=+\-]/);
    expect(controller).not.toMatch(/\bsequence\s*[:=+\-]/);
    expect(controller).not.toContain('Promise<');
    expect(controller).not.toContain('async ');
    expect(controller).not.toContain('await ');
    expect(controller).not.toContain('localStorage');
    expect(controller).not.toContain('sessionStorage');
  });
});
