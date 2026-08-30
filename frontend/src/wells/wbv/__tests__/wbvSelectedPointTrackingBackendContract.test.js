import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const source = fs.readFileSync(
  path.resolve(
    process.cwd(),
    'src/wells/wbv/selectedPointTracking/selectedPointTrackingController.ts',
  ),
  'utf8',
);

describe('WBV selected-point controller backend command contract', () => {
  it('owns the four tracking command constructions', () => {
    expect(source).toContain("kind: 'track-start'");
    expect(source).toContain("kind: 'track-update'");
    expect(source).toContain("kind: 'track-commit'");
    expect(source).toContain("kind: 'track-cancel'");
  });

  it('preserves backend session and sequence authority', () => {
    expect(source).toContain('sessionId');
    expect(source).toContain('#sequence += 1');
    expect(source).toContain('active_tracking_session_id');
  });

  it('does not persist transient tracking state', () => {
    expect(source).not.toContain('localStorage');
    expect(source).not.toContain('sessionStorage');
  });
});
